#!/usr/bin/env python3
"""
Rocky AI Buddy — Main Application

Controls:
  Say "Hey Rocky"      → voice trigger
  Press Enter          → manual trigger: records your voice
  Type text + Enter    → skip recording, send text straight to LLM
  Ctrl-C               → quit
"""

import os
import sys
import time
import wave
import threading
import subprocess
from pathlib import Path

import numpy as np
import sounddevice as sd
import requests

from config import (
    CHANNELS, SAMPLE_RATE, RECORDINGS_DIR, RESPONSES_DIR,
    WHISPER_PATH, WHISPER_MODEL, PIPER_VOICE,
    OLLAMA_MODEL, OLLAMA_URL, OLLAMA_SYSTEM_PROMPT,
    WAKE_WORD, RECORD_SECONDS, MAX_SAVED_AUDIO,
    MIC_DEVICE,
)
from wake_word import WakeWordDetector, pick_input_device
from display import FaceDisplay, EmotionState


class RockyAI:
    def __init__(self):
        self.running           = False
        self._interaction_lock = threading.Lock()

        # Audio device (sounddevice — no PyAudio, no segfault)
        self._dev = pick_input_device()

        # Sub-systems
        self.display       = FaceDisplay()
        self.wake_detector = WakeWordDetector(callback=self._on_wake_word)

        Path(RECORDINGS_DIR).mkdir(exist_ok=True)
        Path(RESPONSES_DIR).mkdir(exist_ok=True)

        print("🤖 Rocky AI initialised")

    # ── wake-word callback ────────────────────────────────────────────────────

    def _on_wake_word(self):
        self._run_interaction()

    # ── core pipeline ─────────────────────────────────────────────────────────

    def _run_interaction(self, typed_text: str | None = None):
        """listen → transcribe → LLM → speak"""
        if not self._interaction_lock.acquire(blocking=False):
            print("⚠️  Already in an interaction — ignoring trigger")
            return
        try:
            self.display.set_emotion(EmotionState.LISTENING)

            if typed_text:
                text = typed_text
                print(f"⌨️  Manual input: {text!r}")
            else:
                audio_file = self._record_audio()
                if not audio_file:
                    return
                self.display.set_emotion(EmotionState.THINKING)
                text = self._transcribe(audio_file)
                if not text:
                    print("⚠️  Could not understand speech — try again")
                    return

            print(f"📝 You: {text}")

            hint = self._detect_emotion(text)
            if hint:
                self.display.set_emotion(hint)

            self.display.set_emotion(EmotionState.THINKING)
            response = self._llm(text)
            if not response:
                response = "Sorry, I'm having trouble thinking right now."

            print(f"💭 Rocky: {response}")
            self.display.set_emotion(EmotionState.SPEAKING)
            self._speak(response)

        finally:
            self.display.set_emotion(EmotionState.IDLE)
            self._interaction_lock.release()

    # ── audio recording (sounddevice) ─────────────────────────────────────────

    def _record_audio(self) -> str | None:
        print(f"🎤 Recording {RECORD_SECONDS} s …")
        path = f"{RECORDINGS_DIR}/rec_{int(time.time())}.wav"
        try:
            frames = sd.rec(
                int(SAMPLE_RATE * RECORD_SECONDS),
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                device=self._dev,
                blocking=True,
            )
            with wave.open(path, "wb") as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(2)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(frames.tobytes())
            print(f"✅ Saved → {path}")
            return path
        except Exception as e:
            print(f"❌ Recording error: {e}")
            return None

    # ── whisper transcription ─────────────────────────────────────────────────

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
                        {"role": "system", "content": OLLAMA_SYSTEM_PROMPT},
                        {"role": "user",   "content": user_text},
                    ],
                    "options": {"temperature": 0.7, "num_predict": 120},
                },
                timeout=40,
            )
            if resp.status_code == 200:
                return resp.json()["message"]["content"].strip()
            print(f"❌ Ollama HTTP {resp.status_code}: {resp.text[:200]}")
        except requests.exceptions.ConnectionError:
            print("❌ Cannot reach Ollama — run: ollama serve")
        except Exception as e:
            print(f"❌ LLM error: {e}")
        return None

    # ── Piper TTS ─────────────────────────────────────────────────────────────

    def _speak(self, text: str):
        path = f"{RESPONSES_DIR}/resp_{int(time.time())}.wav"
        try:
            # Safe: text via stdin, not shell interpolation
            proc = subprocess.run(
                ["piper", "--model", PIPER_VOICE, "--output_file", path],
                input=text.encode(),
                capture_output=True,
                timeout=30,
            )
            if proc.returncode != 0:
                print(f"⚠️  Piper error: {proc.stderr.decode()[:300]}")
                return
            subprocess.run(["aplay", path], capture_output=True, timeout=60)
        except FileNotFoundError:
            print("❌ 'piper' not found — is the venv active?")
        except Exception as e:
            print(f"❌ TTS error: {e}")
        finally:
            self._prune(RESPONSES_DIR)

    # ── emotion hint from user words ──────────────────────────────────────────

    @staticmethod
    def _detect_emotion(text: str):
        t = text.lower()
        if any(w in t for w in ("sad","cry","upset","depressed","miss")):
            return EmotionState.SAD
        if any(w in t for w in ("angry","mad","furious","hate")):
            return EmotionState.ANGRY
        if any(w in t for w in ("happy","great","awesome","love","wonderful","yay")):
            return EmotionState.HAPPY
        if any(w in t for w in ("wow","amazing","incredible","surprised","whoa")):
            return EmotionState.SURPRISED
        return None

    # ── housekeeping ──────────────────────────────────────────────────────────

    @staticmethod
    def _prune(directory: str):
        files = sorted(Path(directory).glob("*.wav"), key=os.path.getmtime, reverse=True)
        for f in files[MAX_SAVED_AUDIO:]:
            try:
                f.unlink()
            except Exception:
                pass

    # ── keyboard trigger ──────────────────────────────────────────────────────

    def _keyboard_loop(self):
        print("⌨️  Press Enter = voice | Type question + Enter = text mode")
        while self.running:
            try:
                line = input()
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

    # ── main run loop ─────────────────────────────────────────────────────────

    def run(self):
        self.running = True

        print("\n" + "═" * 54)
        print("🤖  Rocky AI Buddy is running!")
        print(f"🗣️   Say '{WAKE_WORD}'  — or press Enter to trigger manually")
        print("    Type a question + Enter to skip voice recording")
        print("    Ctrl-C to quit")
        print("═" * 54 + "\n")

        threading.Thread(target=self.display.run, daemon=True).start()
        self.wake_detector.start()
        threading.Thread(target=self._keyboard_loop, daemon=True).start()

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
        print("✅ Rocky shut down cleanly")


if __name__ == "__main__":
    RockyAI().run()
