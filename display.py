#!/usr/bin/env python3
"""
Rocky AI Buddy — Animated Face Display

Renders to /dev/fb0 (Raspberry Pi framebuffer) when available,
otherwise saves frames to /tmp/rocky_frame.png for debugging.
"""

import os
import sys
import time
import math
import struct
import threading
from enum import Enum
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    os.system("pip install pillow")
    from PIL import Image, ImageDraw

from config import DISPLAY_WIDTH, DISPLAY_HEIGHT, TARGET_FPS

FRAMEBUFFER = "/dev/fb0"


class EmotionState(Enum):
    IDLE      = "idle"
    LISTENING = "listening"
    THINKING  = "thinking"
    SPEAKING  = "speaking"
    HAPPY     = "happy"
    SAD       = "sad"
    ANGRY     = "angry"
    SURPRISED = "surprised"


# ─── colour palette ───────────────────────────────────────────────────────────
BG      = (10,  10,  25)    # dark navy
EYE_FG  = (255, 255, 255)   # white iris / brows
PUPIL   = (30,  30,  30)    # near-black pupil
MOUTH   = (255, 255, 255)
SCLERA  = (20,  20,  40)    # eye-ball fill

# Emotion accent colours
ACCENT  = {
    EmotionState.IDLE:      (100, 180, 255),
    EmotionState.LISTENING: (100, 255, 180),
    EmotionState.THINKING:  (255, 220, 80),
    EmotionState.SPEAKING:  (80,  200, 255),
    EmotionState.HAPPY:     (100, 255, 100),
    EmotionState.SAD:       (100, 120, 200),
    EmotionState.ANGRY:     (255,  80,  80),
    EmotionState.SURPRISED: (255, 200,  50),
}


class FaceDisplay:
    def __init__(self):
        self.w   = DISPLAY_WIDTH
        self.h   = DISPLAY_HEIGHT
        self.fps = TARGET_FPS

        self.running         = False
        self.emotion         = EmotionState.IDLE
        self._emotion_lock   = threading.Lock()

        # Animation state
        self.frame       = 0
        self.blink       = False
        self.blink_frame = 0
        self.speak_phase = 0.0

        # Eye geometry
        self.eye_r   = 65
        self.pupil_r = 22
        self.eye_y   = self.h // 2 - 25
        self.eye_lx  = self.w // 2 - 90
        self.eye_rx  = self.w // 2 + 90
        self.mouth_y = self.h // 2 + 70

        # Framebuffer detection
        self._use_fb  = os.path.exists(FRAMEBUFFER)
        self._fb_info = None
        if self._use_fb:
            try:
                self._fb_info = self._detect_fb()
                print(f"🖥️  Framebuffer: {FRAMEBUFFER}  ({self._fb_info})")
            except Exception as e:
                print(f"⚠️  FB detect failed: {e} — using file output")
                self._use_fb = False
        else:
            print(f"🖥️  No {FRAMEBUFFER} — saving frames to /tmp/rocky_frame.png")

        print(f"🖥️  Display initialised ({self.w}×{self.h} @ {self.fps} fps)")

    # ── Public ────────────────────────────────────────────────────────────────

    def set_emotion(self, e: EmotionState):
        with self._emotion_lock:
            self.emotion = e
        print(f"😊 Emotion → {e.value}")

    def run(self):
        self.running = True
        interval = 1.0 / self.fps
        print("🎨 Display loop started")
        while self.running:
            t0 = time.monotonic()
            with self._emotion_lock:
                em = self.emotion
            self._update(em)
            img = self._render(em)
            self._output(img)
            elapsed = time.monotonic() - t0
            time.sleep(max(0.0, interval - elapsed))
        print("🛑 Display loop stopped")

    def stop(self):
        self.running = False

    # ── Animation state ───────────────────────────────────────────────────────

    def _update(self, em: EmotionState):
        self.frame += 1

        # Blink every ~3 s
        if self.frame % (self.fps * 3) == 0:
            self.blink = True
            self.blink_frame = 0
        if self.blink:
            self.blink_frame += 1
            if self.blink_frame > 5:
                self.blink = False

        if em == EmotionState.SPEAKING:
            self.speak_phase += 0.35

    def _pupil_offset(self, em: EmotionState):
        """Return (dx, dy) normalised pupil offset for each emotion."""
        f = self.frame
        if em == EmotionState.IDLE:
            return (0.3 * math.sin(f * 0.018),  0.2 * math.cos(f * 0.025))
        if em == EmotionState.THINKING:
            return (-0.5 + 0.15 * math.sin(f * 0.04), -0.55)
        if em == EmotionState.HAPPY:
            return (0.0, -0.25)
        if em == EmotionState.SAD:
            return (0.0,  0.35)
        if em == EmotionState.ANGRY:
            return (0.0,  0.15)
        if em == EmotionState.SURPRISED:
            return (0.0, -0.1)
        return (0.0, 0.0)

    def _eye_scale(self, em: EmotionState) -> float:
        return {
            EmotionState.LISTENING: 1.10,
            EmotionState.SURPRISED: 1.25,
            EmotionState.ANGRY:     0.80,
            EmotionState.SAD:       0.88,
            EmotionState.HAPPY:     1.05,
        }.get(em, 1.0)

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _render(self, em: EmotionState) -> Image.Image:
        img  = Image.new("RGB", (self.w, self.h), BG)
        draw = ImageDraw.Draw(img)
        acc  = ACCENT[em]

        scale  = self._eye_scale(em)
        er     = int(self.eye_r * scale)
        pr     = int(self.pupil_r * scale)
        dx, dy = self._pupil_offset(em)

        # Subtle glow ring around each eye (accent colour)
        for ex in (self.eye_lx, self.eye_rx):
            draw.ellipse(
                [ex-er-4, self.eye_y-er-4, ex+er+4, self.eye_y+er+4],
                outline=acc, width=2
            )

        # Eyes
        for ex in (self.eye_lx, self.eye_rx):
            self._draw_eye(draw, ex, self.eye_y, er, pr, dx, dy, em)

        # Brows
        self._draw_brows(draw, em, er)

        # Mouth
        self._draw_mouth(draw, em, acc)

        # Emotion label (small, bottom-right)
        # skipped to keep display clean

        return img

    def _draw_eye(self, draw, cx, cy, er, pr, dx, dy, em):
        # Sclera
        draw.ellipse([cx-er, cy-er, cx+er, cy+er], fill=SCLERA, outline=EYE_FG, width=3)

        if self.blink:
            # Closed — draw horizontal line
            draw.line([cx-er, cy, cx+er, cy], fill=EYE_FG, width=5)
            return

        # Pupil
        px = cx + int(dx * pr)
        py = cy + int(dy * pr)
        draw.ellipse([px-pr, py-pr, px+pr, py+pr], fill=PUPIL)

        # Catchlight
        cl = pr // 4
        draw.ellipse([px-cl+cl, py-cl, px+cl, py], fill=(220, 220, 255))

    def _draw_brows(self, draw, em, er):
        lx, rx = self.eye_lx, self.eye_rx
        by = self.eye_y - er - 18

        if em == EmotionState.ANGRY:
            draw.line([(lx-er, by-12), (lx+er//2, by+4)], fill=EYE_FG, width=5)
            draw.line([(rx-er//2, by+4), (rx+er, by-12)], fill=EYE_FG, width=5)
        elif em == EmotionState.SAD:
            draw.line([(lx-er, by+6), (lx+er//2, by-6)], fill=EYE_FG, width=4)
            draw.line([(rx-er//2, by-6), (rx+er, by+6)], fill=EYE_FG, width=4)
        elif em == EmotionState.SURPRISED:
            for ex in (lx, rx):
                draw.arc([ex-er, by-20, ex+er, by+10], 200, 340, fill=EYE_FG, width=4)
        else:
            # Neutral flat brows
            for ex in (lx, rx):
                draw.line([(ex-er+6, by), (ex+er-6, by)], fill=EYE_FG, width=3)

    def _draw_mouth(self, draw, em, acc):
        cx, my = self.w // 2, self.mouth_y
        w2, h2 = 70, 28

        if em == EmotionState.HAPPY:
            draw.arc([cx-w2, my-h2, cx+w2, my+h2], 0, 180, fill=acc, width=5)

        elif em == EmotionState.SAD:
            draw.arc([cx-w2, my-h2//2, cx+w2, my+h2], 180, 360, fill=acc, width=5)

        elif em == EmotionState.ANGRY:
            draw.line([(cx-w2, my+10), (cx+w2, my+10)], fill=acc, width=5)

        elif em == EmotionState.SURPRISED:
            draw.ellipse([cx-22, my-22, cx+22, my+22], outline=acc, fill=SCLERA, width=4)

        elif em == EmotionState.SPEAKING:
            openness = int(abs(math.sin(self.speak_phase)) * 28) + 8
            draw.ellipse(
                [cx-30, my-openness//2, cx+30, my+openness//2],
                outline=acc, fill=SCLERA, width=4
            )

        elif em == EmotionState.THINKING:
            # Dots …
            for i, dx in enumerate((-25, 0, 25)):
                phase = self.frame * 0.08 + i * 1.0
                r = 5 + int(3 * math.sin(phase))
                draw.ellipse([cx+dx-r, my-r, cx+dx+r, my+r], fill=acc)

        elif em == EmotionState.LISTENING:
            # Pulsing smile
            p = 0.6 + 0.4 * math.sin(self.frame * 0.12)
            c = tuple(int(x * p) for x in acc)
            draw.arc([cx-w2, my-h2//2, cx+w2, my+h2//2], 0, 180, fill=c, width=4)

        else:  # IDLE — gentle neutral smile
            draw.arc([cx-w2, my-h2//3, cx+w2, my+h2//3], 0, 180, fill=EYE_FG, width=3)

    # ── Output ────────────────────────────────────────────────────────────────

    @staticmethod
    def _detect_fb() -> str:
        """Read framebuffer resolution from sysfs."""
        try:
            vinfo = Path("/sys/class/graphics/fb0/virtual_size").read_text().strip()
            return f"virtual_size={vinfo}"
        except Exception:
            return "unknown size"

    def _img_to_rgb565(self, img: Image.Image) -> bytes:
        """Convert PIL RGB image to packed RGB565 bytes for /dev/fb0."""
        buf = bytearray()
        for r, g, b in img.getdata():
            pix = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            buf += struct.pack("<H", pix)
        return bytes(buf)

    def _output(self, img: Image.Image):
        if self._use_fb:
            try:
                data = self._img_to_rgb565(img)
                with open(FRAMEBUFFER, "wb") as fb:
                    fb.write(data)
            except PermissionError:
                print("⚠️  No write permission to /dev/fb0 — add user to 'video' group:")
                print("    sudo usermod -aG video $USER")
                self._use_fb = False
            except Exception as e:
                print(f"⚠️  FB write error: {e}")
                self._use_fb = False
        else:
            # Debug: save PNG so you can view it
            img.save("/tmp/rocky_frame.png")


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    d = FaceDisplay()
    t = threading.Thread(target=d.run, daemon=True)
    t.start()

    emotions = list(EmotionState)
    for em in emotions:
        print(f"→ {em.value}")
        d.set_emotion(em)
        time.sleep(2.5)

    d.stop()
    t.join(timeout=2)
