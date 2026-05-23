#!/usr/bin/env python3
"""
Rocky AI Buddy — Wake Word Detection
Listens continuously for "Hey Rocky" using Whisper.cpp chunks.
"""

import os
import sys
import time
import wave
import threading
import subprocess
from pathlib import Path

# ── Suppress ALSA / JACK noise before importing pyaudio ──────────────────────
import ctypes
_asound = ctypes.cdll.LoadLibrary("libasound.so.2")
_asound.snd_lib_error_set_handler(ctypes.CFUNCTYPE(None)(lambda: None))
os.environ.setdefault("JACK_NO_START_SERVER", "1")

import pyaudio

from config import (
    CHANNELS, SAMPLE_RATE, WAKE_WORD, WAKE_WORD_VARIATIONS,
    WHISPER_PATH, WHISPER_MODEL, RECORDINGS_DIR, WAKE_CHUNK_SECONDS,
)


def _pick_input_device(pa: pyaudio.PyAudio) -> int | None:
    """Return index of first USB/IEM mic, falling back to any input device."""
    usb_index = None
    fallback   = None
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        if info["maxInputChannels"] < 1:
            continue
        name = info.get("name", "").lower()
        if fallback is None:
            fallback = i
        if any(k in name for k in ("usb", "iem", "headset", "c-media", "audio")):
            usb_index = i
            break
    idx = usb_index if usb_index is not None else fallback
    if idx is not None:
        print(f"🎙️  Using input device [{idx}]: {pa.get_device_info_by_index(idx)['name']}")
    return idx


class WakeWordDetector:
    def __init__(self, callback=None):
        self.callback  = callback
        self.running   = False
        self._thread   = None

        self._pa       = pyaudio.PyAudio()
        self._dev_idx  = _pick_input_device(self._pa)

        self._tmp      = Path(RECORDINGS_DIR) / "ww_tmp"
        self._tmp.mkdir(parents=True, exist_ok=True)

        print(f"👂 Wake-word detector ready  (trigger: '{WAKE_WORD}')")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _record_chunk(self) -> Path | None:
        """Capture WAKE_CHUNK_SECONDS of audio and return path to .wav file."""
        try:
            stream = self._pa.open(
                format=pyaudio.paInt16,
                channels=CHANNELS,
                rate=SAMPLE_RATE,
                input=True,
                input_device_index=self._dev_idx,
                frames_per_buffer=512,
            )
            total_frames = int(SAMPLE_RATE / 512 * WAKE_CHUNK_SECONDS)
            frames = []
            for _ in range(total_frames):
                if not self.running:
                    break
                frames.append(stream.read(512, exception_on_overflow=False))
            stream.stop_stream()
            stream.close()

            wav_path = self._tmp / f"ww_{int(time.time()*1000)}.wav"
            with wave.open(str(wav_path), "wb") as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(self._pa.get_sample_size(pyaudio.paInt16))
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(b"".join(frames))
            return wav_path
        except Exception as e:
            print(f"⚠️  Wake chunk record error: {e}")
            return None

    def _transcribe(self, wav: Path) -> str:
        """Run Whisper on wav; return lowercase transcript."""
        txt = wav.with_suffix(".txt")
        try:
            subprocess.run(
                [
                    WHISPER_PATH, "-m", WHISPER_MODEL,
                    "-f", str(wav),
                    "--no-timestamps", "--output-txt",
                    "-t", "2",       # 2 threads — light touch on Pi
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

    @staticmethod
    def _has_wake_word(text: str) -> bool:
        return any(v in text for v in WAKE_WORD_VARIATIONS)

    def _loop(self):
        print("👂 Wake-word loop running …")
        errors = 0
        while self.running:
            try:
                wav  = self._record_chunk()
                if wav and self.running:
                    text = self._transcribe(wav)
                    if text:
                        print(f"   heard: {text!r}")
                    if text and self._has_wake_word(text):
                        print(f"✅ Wake word detected!")
                        if self.callback:
                            t = threading.Thread(target=self.callback, daemon=True)
                            t.start()
                            t.join()           # pause detection while responding
                errors = 0
            except Exception as e:
                errors += 1
                print(f"⚠️  Loop error ({errors}): {e}")
                if errors > 5:
                    print("⚠️  Too many errors — sleeping 10 s")
                    time.sleep(10)
                    errors = 0
        print("🛑 Wake-word loop stopped")

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self):
        if not self.running:
            self.running  = True
            self._thread  = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
            print("✅ Wake-word detection started")

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=8)
        self._pa.terminate()
        # Clean temp dir
        for f in self._tmp.glob("*.wav"):
            f.unlink(missing_ok=True)
        for f in self._tmp.glob("*.txt"):
            f.unlink(missing_ok=True)
        print("✅ Wake-word detector stopped")


# ── Standalone test ───────────────────────────────────────────────────────────
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
