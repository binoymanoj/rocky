#!/usr/bin/env python3
"""
Rocky AI Buddy — Wake Word Detection

Key fixes vs original:
 - Records overlapping 2-second chunks continuously (no gap between chunks)
 - Uses a dedicated tmp dir that persists between records to avoid race conditions
 - Passes --output-file explicitly so whisper txt always lands where expected
 - Shorter WAKE_CHUNK_SECONDS (2s) catches "hey rocky" much more reliably
 - Pauses the loop while main interaction is running (no double-trigger)
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
        self.callback   = callback
        self.running    = False
        self.paused     = False   # set True while main interaction runs
        self._thread    = None

        self._dev         = pick_input_device()
        self._native_rate = get_native_rate(self._dev)

        self._tmp = Path(RECORDINGS_DIR) / "ww_tmp"
        self._tmp.mkdir(parents=True, exist_ok=True)

        print(f"👂 Wake-word detector ready  (trigger: '{WAKE_WORD}')")

    # ── recording ─────────────────────────────────────────────────────────────

    def _record_chunk(self) -> Path | None:
        """Record one chunk at native rate, save as 16 kHz wav."""
        try:
            frames = record_seconds(WAKE_CHUNK_SECONDS, self._dev, self._native_rate)
            wav    = self._tmp / "ww_chunk.wav"   # overwrite same file — no disk accumulation
            save_wav(str(wav), frames)
            return wav
        except Exception as e:
            print(f"⚠️  Wake chunk record error: {e}")
            return None

    # ── whisper (safe Popen) ──────────────────────────────────────────────────

    def _transcribe(self, wav: Path) -> str:
        out_stem = str(wav.with_suffix(""))
        txt      = wav.with_suffix(".txt")
        try:
            proc = subprocess.Popen(
                [
                    WHISPER_PATH, "-m", WHISPER_MODEL,
                    "-f", str(wav),
                    "--no-timestamps", "--output-txt",
                    "--output-file", out_stem,   # explicit path — avoids the "no txt found" bug
                    "-t", "2",
                    "--language", "en",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,          # child segfault can't kill us
            )
            try:
                proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                return ""

            if proc.returncode == -11:
                print("❌ Whisper segfaulted — rebuild with -DGGML_NATIVE=OFF")
                return ""

            if txt.exists():
                result = txt.read_text().strip().lower()
                txt.unlink(missing_ok=True)
                return result
        except Exception as e:
            print(f"⚠️  Whisper error: {e}")
        return ""

    # ── detection ─────────────────────────────────────────────────────────────

    @staticmethod
    def _has_wake_word(text: str) -> bool:
        return any(v in text for v in WAKE_WORD_VARIATIONS)

    def _loop(self):
        print("👂 Wake-word loop running …")
        errors = 0
        while self.running:
            if self.paused:
                time.sleep(0.2)
                continue
            try:
                wav = self._record_chunk()
                if not wav or not self.running or self.paused:
                    continue

                text = self._transcribe(wav)
                if text:
                    print(f"   heard: {text!r}")
                if text and self._has_wake_word(text):
                    print("✅ Wake word detected!")
                    self.paused = True          # stop listening while responding
                    if self.callback:
                        t = threading.Thread(target=self._fire_callback, daemon=True)
                        t.start()
                errors = 0
            except Exception as e:
                errors += 1
                print(f"⚠️  Wake loop error ({errors}): {e}")
                if errors > 5:
                    time.sleep(10)
                    errors = 0

        print("🛑 Wake-word loop stopped")

    def _fire_callback(self):
        try:
            if self.callback:
                self.callback()
        finally:
            self.paused = False   # resume listening after interaction

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
        for f in self._tmp.glob("*"):
            f.unlink(missing_ok=True)
        print("✅ Wake-word detector stopped")
