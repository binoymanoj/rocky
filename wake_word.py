#!/usr/bin/env python3
"""
Rocky AI Buddy — Wake Word Detection
Uses sounddevice (not pyaudio) to avoid Pi 5 segfault.
"""

import os
import time
import wave
import threading
import subprocess
from pathlib import Path

import numpy as np
import sounddevice as sd

from config import (
    CHANNELS, SAMPLE_RATE, WAKE_WORD, WAKE_WORD_VARIATIONS,
    WHISPER_PATH, WHISPER_MODEL, RECORDINGS_DIR, WAKE_CHUNK_SECONDS,
    MIC_DEVICE,
)


def pick_input_device() -> int | None:
    """
    Return the sounddevice index for the best input device.
    Prefers USB/IEM by name; falls back to default.
    Run `python3 -m sounddevice` to list devices.
    """
    if MIC_DEVICE is not None:
        return MIC_DEVICE

    devices = sd.query_devices()
    best    = None

    for i, dev in enumerate(devices):
        if dev["max_input_channels"] < 1:
            continue
        name = dev["name"].lower()
        if any(k in name for k in ("usb", "iem", "headset", "c-media", "uac")):
            best = i
            break
        if best is None:
            best = i   # first available input as fallback

    if best is not None:
        print(f"🎙️  Input device [{best}]: {sd.query_devices(best)['name']}")
    else:
        print("🎙️  Using system default input device")
    return best


class WakeWordDetector:
    def __init__(self, callback=None):
        self.callback = callback
        self.running  = False
        self._thread  = None
        self._dev     = pick_input_device()

        self._tmp = Path(RECORDINGS_DIR) / "ww_tmp"
        self._tmp.mkdir(parents=True, exist_ok=True)

        print(f"👂 Wake-word detector ready  (trigger: '{WAKE_WORD}')")

    # ── recording ─────────────────────────────────────────────────────────────

    def _record_chunk(self) -> Path | None:
        """Capture WAKE_CHUNK_SECONDS of audio; return path to .wav."""
        try:
            frames = sd.rec(
                int(SAMPLE_RATE * WAKE_CHUNK_SECONDS),
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                device=self._dev,
                blocking=True,
            )
            wav = self._tmp / f"ww_{int(time.time()*1000)}.wav"
            with wave.open(str(wav), "wb") as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(2)          # int16 = 2 bytes
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(frames.tobytes())
            return wav
        except Exception as e:
            print(f"⚠️  Wake chunk record error: {e}")
            return None

    # ── whisper ───────────────────────────────────────────────────────────────

    def _transcribe(self, wav: Path) -> str:
        txt = wav.with_suffix(".txt")
        try:
            subprocess.run(
                [
                    WHISPER_PATH, "-m", WHISPER_MODEL,
                    "-f", str(wav),
                    "--no-timestamps", "--output-txt",
                    "-t", "2",
                    "--language", "en",
                ],
                capture_output=True,
                timeout=12,
            )
            if txt.exists():
                result = txt.read_text().strip().lower()
                txt.unlink(missing_ok=True)
                return result
        except subprocess.TimeoutExpired:
            print("⚠️  Whisper timed out")
        except Exception as e:
            print(f"⚠️  Whisper error: {e}")
        finally:
            wav.unlink(missing_ok=True)
            txt.unlink(missing_ok=True)
        return ""

    # ── wake word check ───────────────────────────────────────────────────────

    @staticmethod
    def _has_wake_word(text: str) -> bool:
        return any(v in text for v in WAKE_WORD_VARIATIONS)

    # ── main loop ─────────────────────────────────────────────────────────────

    def _loop(self):
        print("👂 Wake-word loop running …")
        errors = 0
        while self.running:
            try:
                wav = self._record_chunk()
                if wav and self.running:
                    text = self._transcribe(wav)
                    if text:
                        print(f"   heard: {text!r}")
                    if text and self._has_wake_word(text):
                        print("✅ Wake word detected!")
                        if self.callback:
                            t = threading.Thread(target=self.callback, daemon=True)
                            t.start()
                            t.join()    # pause detection while Rocky responds
                errors = 0
            except Exception as e:
                errors += 1
                print(f"⚠️  Loop error ({errors}): {e}")
                if errors > 5:
                    print("⚠️  Too many errors — sleeping 10 s")
                    time.sleep(10)
                    errors = 0
        print("🛑 Wake-word loop stopped")

    # ── public API ────────────────────────────────────────────────────────────

    def start(self):
        if not self.running:
            self.running = True
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
            print("✅ Wake-word detection started")

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=8)
        for f in self._tmp.glob("*.wav"):
            f.unlink(missing_ok=True)
        for f in self._tmp.glob("*.txt"):
            f.unlink(missing_ok=True)
        print("✅ Wake-word detector stopped")


# ── standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    def _cb():
        print("\n🎉 CALLBACK FIRED!\n")
        time.sleep(1)

    det = WakeWordDetector(callback=_cb)
    print(f"Listening for '{WAKE_WORD}' — Ctrl-C to quit\n")
    det.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        det.stop()
