#!/usr/bin/env python3
"""
Rocky AI Buddy — Face Display

Designed for 0fps / e-ink style screens: only redraws when emotion changes.
If TARGET_FPS > 0, also animates the speaking mouth open/close.

Face style: rounded-square (squircle) eyes, small curved mouth,
rich emotion set with tears, angry pupils, thinking dots, etc.
"""

import os
import math
import struct
import threading
import time
from enum import Enum
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFilter
except ImportError:
    os.system("pip install pillow")
    from PIL import Image, ImageDraw, ImageFilter

from config import DISPLAY_WIDTH, DISPLAY_HEIGHT, TARGET_FPS

FRAMEBUFFER = "/dev/fb0"

# ── Palette ───────────────────────────────────────────────────────────────────
BG          = (10,  12,  28)     # deep navy
EYE_WHITE   = (230, 235, 255)    # cool white iris
EYE_FILL    = (18,  20,  45)     # squircle fill (dark inner)
PUPIL_COL   = (15,  15,  30)     # near-black pupil
BROW_COL    = (200, 210, 255)    # eyebrow
MOUTH_COL   = (200, 210, 255)    # neutral mouth
TEAR_COL    = (100, 160, 255)    # tear drop blue
SHINE       = (240, 245, 255)    # eye shine / catchlight

ACCENT = {
    "idle":      (90,  160, 255),
    "listening": (60,  230, 160),
    "thinking":  (255, 200,  60),
    "loading":   (255, 160,  40),
    "speaking":  (60,  200, 255),
    "happy":     (80,  240, 110),
    "sad":       (90,  110, 210),
    "angry":     (255,  60,  60),
    "surprised": (255, 190,  40),
    "scared":    (200,  80, 220),
}


class EmotionState(Enum):
    IDLE      = "idle"
    LISTENING = "listening"
    THINKING  = "thinking"
    LOADING   = "loading"
    SPEAKING  = "speaking"
    HAPPY     = "happy"
    SAD       = "sad"
    ANGRY     = "angry"
    SURPRISED = "surprised"
    SCARED    = "scared"


# ── Squircle helper ───────────────────────────────────────────────────────────

def squircle_points(cx, cy, w, h, n=60):
    """Generate polygon points approximating a squircle (superellipse n=4)."""
    pts = []
    for i in range(n):
        t   = 2 * math.pi * i / n
        cos = math.cos(t)
        sin = math.sin(t)
        x   = cx + w * math.copysign(abs(cos) ** 0.5, cos)
        y   = cy + h * math.copysign(abs(sin) ** 0.5, sin)
        pts.append((x, y))
    return pts


class FaceDisplay:
    def __init__(self):
        self.w   = DISPLAY_WIDTH
        self.h   = DISPLAY_HEIGHT
        self.fps = TARGET_FPS

        self.running       = False
        self._emotion      = EmotionState.IDLE
        self._prev_emotion = None          # track changes for 0fps mode
        self._lock         = threading.Lock()

        # Animation counters (only matter when fps > 0)
        self._frame      = 0
        self._speak_open = False           # toggle for speaking mouth

        # Eye layout
        self._ew   = 88    # eye squircle half-width
        self._eh   = 72    # eye squircle half-height
        self._ey   = self.h // 2 - 20
        self._elx  = self.w // 2 - 100
        self._erx  = self.w // 2 + 100
        self._my   = self.h // 2 + 88     # mouth centre y
        self._pr   = 20                    # pupil radius

        # Framebuffer
        self._use_fb = os.path.exists(FRAMEBUFFER)
        if self._use_fb:
            try:
                vsize = Path("/sys/class/graphics/fb0/virtual_size").read_text().strip()
                print(f"🖥️  Framebuffer {FRAMEBUFFER}  ({vsize})")
            except Exception:
                print(f"🖥️  Framebuffer {FRAMEBUFFER}")
        else:
            print(f"🖥️  No {FRAMEBUFFER} — frames → /tmp/rocky_frame.png")

        mode = f"{self.fps} fps" if self.fps > 0 else "static/0fps"
        print(f"🖥️  Display ready  {self.w}×{self.h}  {mode}")

    # ── Public API ────────────────────────────────────────────────────────────

    def set_emotion(self, e: EmotionState):
        with self._lock:
            self._emotion = e
        print(f"😊 Emotion → {e.value}")
        # In 0fps mode push a frame immediately on every change
        if self.fps == 0:
            self._push_frame(e)

    def run(self):
        """Main loop.  For fps=0 screens this just idles; frames pushed by set_emotion."""
        self.running = True
        print("🎨 Display loop started")

        if self.fps == 0:
            # Draw the initial idle face once, then sit idle
            self._push_frame(EmotionState.IDLE)
            while self.running:
                time.sleep(0.5)
        else:
            interval = 1.0 / self.fps
            while self.running:
                t0 = time.monotonic()
                with self._lock:
                    em = self._emotion
                self._frame += 1

                # Speaking mouth toggle at ~2 Hz
                if em == EmotionState.SPEAKING and self._frame % max(1, self.fps // 2) == 0:
                    self._speak_open = not self._speak_open

                img = self._render(em)
                self._output(img)
                elapsed = time.monotonic() - t0
                time.sleep(max(0.0, interval - elapsed))

        print("🛑 Display loop stopped")

    def stop(self):
        self.running = False

    # ── Frame pipeline ────────────────────────────────────────────────────────

    def _push_frame(self, em: EmotionState):
        """Render and output a single static frame (used in 0fps mode)."""
        # For speaking, alternate open/close on each call
        if em == EmotionState.SPEAKING:
            self._speak_open = not self._speak_open
        img = self._render(em)
        self._output(img)

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _render(self, em: EmotionState) -> Image.Image:
        img  = Image.new("RGB", (self.w, self.h), BG)
        draw = ImageDraw.Draw(img)
        acc  = ACCENT[em.value]
        ev   = em.value

        # Glow ring (accent outline around each eye box)
        for ex in (self._elx, self._erx):
            pts = squircle_points(ex, self._ey, self._ew + 6, self._eh + 6)
            draw.polygon(pts, outline=acc)

        # Eyes
        for ex in (self._elx, self._erx):
            self._draw_eye(draw, ex, self._ey, em, acc)

        # Eyebrows
        self._draw_brows(draw, em)

        # Mouth
        self._draw_mouth(draw, em, acc)

        # Tears for SAD / SCARED
        if ev in ("sad", "scared"):
            self._draw_tears(draw, acc)

        # Angry red pupils (veins) overlay
        if ev == "angry":
            self._draw_anger_marks(draw)

        return img

    # ── Eye ───────────────────────────────────────────────────────────────────

    def _draw_eye(self, draw, cx, cy, em: EmotionState, acc):
        ev = em.value

        # Scale squircle per emotion
        scale = {
            "surprised": 1.25, "listening": 1.12, "scared": 1.20,
            "angry": 0.78, "sad": 0.85, "happy": 1.05,
        }.get(ev, 1.0)
        ew = int(self._ew * scale)
        eh = int(self._eh * scale)

        # Draw squircle eye body
        pts = squircle_points(cx, cy, ew, eh)
        draw.polygon(pts, fill=EYE_FILL, outline=EYE_WHITE)

        # Half-close for SAD / ANGRY (draw filled rect over top half)
        if ev == "sad":
            draw.rectangle([cx - ew, cy - eh, cx + ew, cy], fill=BG)
            # Redraw bottom arc outline
            pts2 = squircle_points(cx, cy, ew, eh)
            draw.polygon(pts2, outline=EYE_WHITE)
        elif ev == "angry":
            # Cover top-third to make squinting look
            cover = eh // 3
            draw.rectangle([cx - ew, cy - eh, cx + ew, cy - eh + cover * 2], fill=BG)

        # Pupil
        pdx, pdy = self._pupil_offset(em)
        px = int(cx + pdx * self._pr)
        py = int(cy + pdy * self._pr)
        pr = self._pr
        draw.ellipse([px - pr, py - pr, px + pr, py + pr], fill=PUPIL_COL)

        # Shine / catchlight
        sl = pr // 3
        draw.ellipse([px - sl + sl, py - sl, px, py], fill=SHINE)

        # Listening: pulsing ring inside eye
        if ev == "listening":
            ring_r = int(ew * 0.55)
            draw.ellipse(
                [cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r],
                outline=acc, width=2
            )

        # Thinking: spinning arc inside eye
        if ev in ("thinking", "loading"):
            arc_r = int(ew * 0.5)
            offset = (self._frame * 8) % 360 if self.fps > 0 else 45
            draw.arc(
                [cx - arc_r, cy - arc_r, cx + arc_r, cy + arc_r],
                offset, offset + 240, fill=acc, width=3
            )

        # Happy: half-moon (upper arc covered — "^" shape eye)
        if ev == "happy":
            draw.rectangle([cx - ew, cy, cx + ew, cy + eh + 2], fill=BG)

        # Stars for surprised: tiny dots at corners
        if ev == "surprised":
            for sx, sy in [(cx - ew + 8, cy - eh + 8), (cx + ew - 8, cy - eh + 8)]:
                draw.ellipse([sx - 3, sy - 3, sx + 3, sy + 3], fill=acc)

    def _pupil_offset(self, em: EmotionState):
        ev = em.value
        f  = self._frame
        if ev == "idle":
            return (0.3 * math.sin(f * 0.05), 0.2 * math.cos(f * 0.07))
        if ev == "thinking":
            return (-0.6, -0.5)
        if ev == "loading":
            return (0.0, -0.5)
        if ev == "happy":
            return (0.0, -0.3)
        if ev in ("sad", "scared"):
            return (0.0, 0.4)
        if ev == "angry":
            return (0.0, 0.2)
        if ev == "surprised":
            return (0.0, 0.0)
        return (0.0, 0.0)

    # ── Eyebrows ──────────────────────────────────────────────────────────────

    def _draw_brows(self, draw, em: EmotionState):
        ev = em.value
        lx, rx = self._elx, self._erx
        by = self._ey - self._eh - 14

        bw = self._ew - 10   # brow half-width

        if ev == "angry":
            # V shape — inner corners raised
            draw.line([(lx - bw, by - 14), (lx + bw, by + 6)], fill=ACCENT["angry"], width=5)
            draw.line([(rx - bw, by + 6),  (rx + bw, by - 14)], fill=ACCENT["angry"], width=5)
        elif ev == "sad":
            # Inverted V — inner corners lowered
            draw.line([(lx - bw, by + 6),  (lx + bw, by - 10)], fill=BROW_COL, width=4)
            draw.line([(rx - bw, by - 10), (rx + bw, by + 6)],  fill=BROW_COL, width=4)
        elif ev == "surprised":
            # High arched brows
            for ex in (lx, rx):
                draw.arc([ex - bw, by - 22, ex + bw, by + 8], 200, 340, fill=BROW_COL, width=4)
        elif ev == "scared":
            # High + slanted outward
            draw.line([(lx - bw, by - 18), (lx + bw, by + 2)], fill=BROW_COL, width=4)
            draw.line([(rx - bw, by + 2),  (rx + bw, by - 18)], fill=BROW_COL, width=4)
        elif ev == "happy":
            # Relaxed slight arch
            for ex in (lx, rx):
                draw.arc([ex - bw, by - 10, ex + bw, by + 14], 210, 330, fill=BROW_COL, width=3)
        else:
            # Flat neutral
            for ex in (lx, rx):
                draw.line([(ex - bw, by), (ex + bw, by)], fill=BROW_COL, width=3)

    # ── Mouth ─────────────────────────────────────────────────────────────────

    def _draw_mouth(self, draw, em: EmotionState, acc):
        ev = em.value
        cx = self.w // 2
        my = self._my
        mw = 52    # mouth half-width (small)
        mh = 20    # mouth arc height

        if ev == "happy":
            # Wide open smile
            draw.arc([cx - mw, my - mh, cx + mw, my + mh], 0, 180, fill=acc, width=4)
            # Teeth hint
            draw.ellipse([cx - mw + 10, my - 4, cx + mw - 10, my + 10],
                         fill=(240, 240, 240))

        elif ev == "sad":
            # Downward curve (frown)
            draw.arc([cx - mw, my - mh // 2, cx + mw, my + mh], 180, 360, fill=acc, width=4)

        elif ev == "angry":
            # Flat with downward corners — zigzag
            pts = [
                (cx - mw, my + 8),
                (cx - mw // 2, my),
                (cx, my + 8),
                (cx + mw // 2, my),
                (cx + mw, my + 8),
            ]
            draw.line(pts, fill=acc, width=4)

        elif ev == "surprised":
            # Open O mouth
            draw.ellipse([cx - 20, my - 18, cx + 20, my + 18],
                         outline=acc, fill=EYE_FILL, width=3)

        elif ev == "scared":
            # Wavy / trembling mouth
            pts = []
            for i in range(21):
                t  = i / 20
                x  = cx - mw + int(t * 2 * mw)
                y  = my + int(8 * math.sin(t * math.pi * 4))
                pts.append((x, y))
            draw.line(pts, fill=acc, width=3)

        elif ev == "speaking":
            # Open/close toggle — open = oval, closed = thin line
            if self._speak_open:
                open_h = mh + 10
                draw.ellipse([cx - mw + 10, my - open_h // 2,
                               cx + mw - 10, my + open_h // 2],
                             outline=acc, fill=EYE_FILL, width=3)
            else:
                draw.arc([cx - mw, my - 4, cx + mw, my + 4], 0, 180, fill=acc, width=3)

        elif ev == "thinking":
            # Three animated dots
            for i, dx in enumerate((-22, 0, 22)):
                phase = (self._frame * 0.15 + i * 1.2) if self.fps > 0 else (i * 1.2)
                r = 5 + int(3 * math.sin(phase))
                draw.ellipse([cx + dx - r, my - r, cx + dx + r, my + r], fill=acc)

        elif ev == "loading":
            # Spinning arc bar below face
            offset = (self._frame * 6) % 360 if self.fps > 0 else 0
            bx, bby = cx, my
            br = 16
            draw.arc([bx - br, bby - br, bx + br, bby + br],
                     offset, offset + 200, fill=acc, width=5)

        elif ev == "listening":
            # Sound wave bars
            bar_h = [10, 18, 26, 18, 10]
            bar_w = 6
            gap   = 5
            total = len(bar_h) * (bar_w + gap) - gap
            bx0   = cx - total // 2
            for i, bh in enumerate(bar_h):
                bx = bx0 + i * (bar_w + gap)
                draw.rectangle(
                    [bx, my - bh // 2, bx + bar_w, my + bh // 2],
                    fill=acc
                )

        else:  # IDLE
            # Small gentle smile
            draw.arc([cx - mw, my - mh // 3, cx + mw, my + mh // 3],
                     0, 180, fill=MOUTH_COL, width=3)

    # ── Tears ─────────────────────────────────────────────────────────────────

    def _draw_tears(self, draw, acc):
        for ex in (self._elx, self._erx):
            # Teardrop starting from bottom of eye
            tx = ex + 10
            ty = self._ey + self._eh - 10
            # Elongated teardrop
            draw.ellipse([tx - 5, ty, tx + 5, ty + 22], fill=TEAR_COL)
            draw.ellipse([tx - 4, ty - 4, tx + 4, ty + 4], fill=TEAR_COL)

    # ── Anger marks ───────────────────────────────────────────────────────────

    def _draw_anger_marks(self, draw):
        # Forehead veins / anger marks
        acc = ACCENT["angry"]
        cx  = self.w // 2
        ay  = self._ey - self._eh - 40
        for side, sx in ((-1, cx - 40), (1, cx + 20)):
            pts = [
                (sx, ay),
                (sx + side * 12, ay - 14),
                (sx + side * 6,  ay - 22),
                (sx + side * 18, ay - 30),
            ]
            draw.line(pts, fill=acc, width=3)

    # ── Output ────────────────────────────────────────────────────────────────

    def _img_to_rgb565(self, img: Image.Image) -> bytes:
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
                print("⚠️  No write permission to /dev/fb0")
                print("    sudo usermod -aG video $USER  then re-login")
                self._use_fb = False
            except Exception as e:
                print(f"⚠️  FB write error: {e}")
                self._use_fb = False
        else:
            img.save("/tmp/rocky_frame.png")


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import time as _time
    d = FaceDisplay()
    t = threading.Thread(target=d.run, daemon=True)
    t.start()

    for em in EmotionState:
        print(f"→ {em.value}")
        d.set_emotion(em)
        _time.sleep(2.0)

    d.stop()
    t.join(timeout=2)
