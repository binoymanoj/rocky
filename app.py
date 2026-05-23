#!/usr/bin/env python3
"""
Rocky AI Buddy — Main Application

Controls:
  Say "Hey Rocky" → voice trigger
  Press Enter     → manual trigger (type a question then press Enter again)
  Ctrl-C          → quit
"""

import os
import sys
import time
import wave
import json
import shlex
import threading
import subprocess
from pathlib import Path

# ── Suppress ALSA / JACK stderr noise before any audio import ────────────────
import ctypes
_asound = ctypes.cdll.LoadLibrary("libasound.so.2")
_asound.snd_lib_error_set_handler(ctypes.CFUNCTYPE(None)(lambda: None))
os.environ.setdefault("JACK_NO_START_SERVER", "1")

import pyaudio
import requests

from config import (
    CHANNELS, SAMPLE_RATE, RECORDINGS_DIR, RESPONSES_DIR,
    WHISPER_PATH, WHISPER_MODEL, PIPER_VOICE,
    OLLAMA_MODEL, OLLAMA_URL, OLLAMA_SYSTEM_PROMPT,
    WAKE_WORD, RECORD_SECONDS, MAX_SAVED_AUDIO,
)
from wake_word import WakeWordDetector, _pick_input_device
from display import FaceDisplay, EmotionState


# ─────────────────────────────────────────────────────────────────────────────
class RockyAI:
    def __init__(self):
        self.running        = False
        self._interaction_lock = threading.Lock()   # one interaction at a time

        # Audio
        self._pa      = pyaudio.PyAudio()
        self._dev_idx = _pick_input_device(self._pa)

        # Sub-systems
        self.display      = FaceDisplay()
        self.wake_detector = WakeWordDetector(callback=self._on_wake_word)

        Path(RECORDINGS_DIR).mkdir(exist_ok=True)
        Path(RESPONSES_DIR).mkdir(exist_ok=True)

        print("🤖 Rocky AI initialised")

    # ── Wake-word callback ────────────────────────────────────────────────────

    def _on_wake_word(self):
        """Called from the wake-word thread when trigger is heard."""
        self._run_interaction()

    # ── Core interaction pipeline ─────────────────────────────────────────────

    def _run_interaction(self, typed_text: str | None = None):
        """Full listen → transcribe → LLM → speak pipeline."""
        if not self._interaction_lock.acquire(blocking=False):
            print("⚠️  Already in an interaction — ignoring trigger")
            return
        try:
            self.display.set_emotion(EmotionState.LISTENING)

            if typed_text:
                text = typed_text
                print(f"⌨️  Manual input: {text!r}")
            else:
                # Record speech
                audio_file = self._record_audio()
                if not audio_file:
                    self.display.set_emotion(EmotionState.IDLE)
                    return

                self.display.set_emotion(EmotionState.THINKING)
                text = self._transcribe(audio_file)
                if not text:
                    print("⚠️  Could not understand — try again")
                    self.display.set_emotion(EmotionState.IDLE)
                    return

            print(f"📝 You: {text}")

            # Emotion hint from user words
            hint = self._detect_emotion(text)
            if hint:
                self.display.set_emotion(hint)

            # LLM
            self.display.set_emotion(EmotionState.THINKING)
            response = self._llm(text)
            if not response:
                response = "Sorry, I'm having trouble thinking right now."

            print(f"💭 Rocky: {response}")

            # Speak
            self.display.set_emotion(EmotionState.SPEAKING)
            self._speak(response)

        finally:
            self.display.set_emotion(EmotionState.IDLE)
            self._interaction_lock.release()

    # ── Audio recording ───────────────────────────────────────────────────────

    def _record_audio(self) -> str | None:
        print(f"🎤 Recording {RECORD_SECONDS} s …")
        ts   = int(time.time())
        path = f"{RECORDINGS_DIR}/rec_{ts}.wav"
        try:
            stream = self._pa.open(
                format=pyaudio.paInt16,
                channels=CHANNELS,
                rate=SAMPLE_RATE,
                input=True,
                input_device_index=self._dev_idx,
                frames_per_buffer=512,
            )
            frames = [
                stream.read(512, exception_on_overflow=False)
                for _ in range(int(SAMPLE_RATE / 512 * RECORD_SECONDS))
            ]
            stream.stop_stream()
            stream.close()

            with wave.open(path, "wb") as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(self._pa.get_sample_size(pyaudio.paInt16))
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(b"".join(frames))

            print(f"✅ Saved → {path}")
            return path
        except Exception as e:
            print(f"❌ Recording error: {e}")
            return None

    # ── Whisper transcription ─────────────────────────────────────────────────

    def _transcribe(self, audio_file: str) -> str | None:
        txt = audio_file.replace(".wav", ".txt")
        try:
            subprocess.run(
                [
                    WHISPER_PATH, "-m", WHISPER_MODEL,
                    "-f", audio_file,
                    "--no-timestamps", "--output-txt",
                    "--language", "en",
                ],
                capture_output=True,
                timeout=30,
            )
            if os.path.exists(txt):
                result = Path(txt).read_text().strip()
                Path(txt).unlink(missing_ok=True)
                return result or None
        except Exception as e:
            print(f"❌ Transcription error: {e}")
        return None

    # ── Ollama LLM ────────────────────────────────────────────────────────────

    def _llm(self, user_text: str) -> str | None:
        try:
            resp = requests.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "stream": False,
                    "messages": [
                        {"role": "system",  "content": OLLAMA_SYSTEM_PROMPT},
                        {"role": "user",    "content": user_text},
                    ],
                    "options": {"temperature": 0.7, "num_predict": 120},
                },
                timeout=40,
            )
            if resp.status_code == 200:
                return resp.json()["message"]["content"].strip()
            print(f"❌ Ollama HTTP {resp.status_code}")
        except requests.exceptions.ConnectionError:
            print("❌ Cannot reach Ollama — is it running?  (ollama serve)")
        except Exception as e:
            print(f"❌ LLM error: {e}")
        return None

    # ── Piper TTS ─────────────────────────────────────────────────────────────

    def _speak(self, text: str):
        ts   = int(time.time())
        path = f"{RESPONSES_DIR}/resp_{ts}.wav"
        try:
            # Safe: pass text via stdin, not shell interpolation
            proc = subprocess.run(
                ["piper", "--model", PIPER_VOICE, "--output_file", path],
                input=text.encode(),
                capture_output=True,
                timeout=30,
            )
            if proc.returncode != 0:
                print(f"⚠️  Piper stderr: {proc.stderr.decode()[:200]}")
                return
            subprocess.run(["aplay", path], capture_output=True, timeout=60)
        except FileNotFoundError:
            print("❌ 'piper' not found — is venv activated?")
        except Exception as e:
            print(f"❌ TTS error: {e}")
        finally:
            self._prune(RESPONSES_DIR)

    # ── Emotion hint ──────────────────────────────────────────────────────────

    @staticmethod
    def _detect_emotion(text: str) -> EmotionState | None:
        t = text.lower()
        if any(w in t for w in ("sad","cry","upset","depressed","miss")):
            return EmotionState.SAD
        if any(w in t for w in ("angry","mad","furious","hate","angry")):
            return EmotionState.ANGRY
        if any(w in t for w in ("happy","great","awesome","love","wonderful","yay")):
            return EmotionState.HAPPY
        if any(w in t for w in ("wow","amazing","incredible","surprised","whoa")):
            return EmotionState.SURPRISED
        return None

    # ── Housekeeping ──────────────────────────────────────────────────────────

    @staticmethod
    def _prune(directory: str):
        files = sorted(Path(directory).glob("*.wav"), key=os.path.getmtime, reverse=True)
        for f in files[MAX_SAVED_AUDIO:]:
            try:
                f.unlink()
            except Exception:
                pass

    # ── Manual keyboard trigger ───────────────────────────────────────────────

    def _keyboard_loop(self):
        """
        Runs in its own thread.
        • Press Enter alone  → voice recording mode (same as wake word)
        • Type text + Enter  → skip recording, send text directly to LLM
        """
        print("⌨️  Manual trigger: press Enter (voice) or type a question + Enter")
        while self.running:
            try:
                line = input()          # blocks until Enter
                if not self.running:
                    break
                text = line.strip() or None
                threading.Thread(
                    target=self._run_interaction,
                    args=(text,),
                    daemon=True,
                ).start()
            except EOFError:
                break

    # ── Main run loop ─────────────────────────────────────────────────────────

    def run(self):
        self.running = True

        print("\n" + "═" * 52)
        print("🤖  Rocky AI Buddy is running!")
        print(f"🗣️   Say '{WAKE_WORD}' — or press Enter to trigger manually")
        print("    (type a question + Enter to skip voice recording)")
        print("    Ctrl-C to quit")
        print("═" * 52 + "\n")

        # Display thread
        threading.Thread(target=self.display.run, daemon=True).start()

        # Wake-word detection
        self.wake_detector.start()

        # Keyboard listener
        kb_thread = threading.Thread(target=self._keyboard_loop, daemon=True)
        kb_thread.start()

        try:
            while self.running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n👋 Shutting down …")
        finally:
            self.stop()

    def stop(self):
        self.running = False
        self.wake_detector.stop()
        self.display.stop()
        self._pa.terminate()
        print("✅ Rocky shut down cleanly")


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    RockyAI().run()
