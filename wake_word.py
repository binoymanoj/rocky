#!/usr/bin/env python3
"""
Rocky AI Buddy — Wake Word Detection
Records at native device rate, resamples to 16 kHz, feeds Whisper safely.
"""

import os
import time
import threading
import subprocess
from pathlib import Path

from config import (
    WAKE_WORD, WAKE_WORD_VARIATIONS,
    WHISPER_PATH, WHISPER_MODEL,
    RECORDINGS_DIR, WAKE_CHUNK_SECONDS,
)
from audio_utils import pick_input_device, get_native_rate, record_seconds, save_wav


class WakeWordDetector:
    def __init__(self, callback=None):
        self.callback = callback
        self.running  = False
        self._thread  = None

        self._dev         = pick_input_device()
        self._native_rate = get_native_rate(self._dev)

        self._tmp = Path(RECORDINGS_DIR) / "ww_tmp"
        self._tmp.mkdir(parents=True, exist_ok=True)

        print(f"👂 Wake-word detector ready  (trigger: '{WAKE_WORD}')")

    # ── recording ─────────────────────────────────────────────────────────────

    def _record_chunk(self) -> Path | None:
        try:
            frames = record_seconds(WAKE_CHUNK_SECONDS, self._dev, self._native_rate)
            wav    = self._tmp / f"ww_{int(time.time()*1000)}.wav"
            save_wav(str(wav), frames)
            return wav
        except Exception as e:
            print(f"⚠️  Wake chunk record error: {e}")
            return None

    # ── whisper (safe Popen — won't crash the parent on segfault) ────────────

    def _transcribe(self, wav: Path) -> str:
        txt = wav.with_suffix(".txt")
        try:
            proc = subprocess.Popen(
                [
                    WHISPER_PATH, "-m", WHISPER_MODEL,
                    "-f", str(wav),
                    "--no-timestamps", "--output-txt",
                    "-t", "2",
                    "--language", "en",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,   # child segfault won't kill us
            )
            try:
                _, stderr = proc.communicate(timeout=12)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                return ""

            if proc.returncode == -11:
                print("❌ Whisper segfaulted — rebuild it:")
                print("   cd ~/Applications/whisper.cpp")
                print("   cmake -B build && cmake --build build -j$(nproc)")
                return ""

            if txt.exists():
                result = txt.read_text().strip().lower()
                txt.unlink(missing_ok=True)
                return result
        except Exception as e:
            print(f"⚠️  Whisper error: {e}")
        finally:
            wav.unlink(missing_ok=True)
            txt.unlink(missing_ok=True)
        return ""

    # ── detection ─────────────────────────────────────────────────────────────

    @staticmethod
    def _has_wake_word(text: str) -> bool:
        return any(v in text for v in WAKE_WORD_VARIATIONS)

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
                            t.join()
                errors = 0
            except Exception as e:
                errors += 1
                print(f"⚠️  Loop error ({errors}): {e}")
                if errors > 5:
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
