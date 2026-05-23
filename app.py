#!/usr/bin/env python3
"""
Rocky AI Buddy — Main Application

Controls:
  Say "Hey Rocky"      → voice trigger (always listening)
  Press Enter          → manual voice recording trigger
  Type text + Enter    → skip recording, send text straight to LLM
  Ctrl-C               → quit

Startup behaviour:
  - Model is warmed up immediately on launch (keep_alive = -1 = never unload)
  - Display shows IDLE face right away
  - Wake word loop starts immediately — no need to press Enter
"""

import os
import sys
import json
import time
import threading
import subprocess
from pathlib import Path

import requests

from config import (
    CHANNELS, SAMPLE_RATE, RECORDINGS_DIR, RESPONSES_DIR,
    WHISPER_PATH, WHISPER_MODEL, PIPER_VOICE,
    OLLAMA_MODEL, OLLAMA_URL, OLLAMA_SYSTEM_PROMPT, OLLAMA_KEEP_ALIVE,
    WAKE_WORD, RECORD_SECONDS, MAX_SAVED_AUDIO,
)
from audio_utils import pick_input_device, get_native_rate, record_seconds, save_wav
from wake_word import WakeWordDetector
from display import FaceDisplay, EmotionState


class RockyAI:
    def __init__(self):
        self.running           = False
        self._interaction_lock = threading.Lock()

        # Shared audio device
        self._dev         = pick_input_device()
        self._native_rate = get_native_rate(self._dev)

        # Sub-systems
        self.display       = FaceDisplay()
        self.wake_detector = WakeWordDetector(callback=self._on_wake_word)

        Path(RECORDINGS_DIR).mkdir(exist_ok=True)
        Path(RESPONSES_DIR).mkdir(exist_ok=True)

        self._preflight_check()
        print("🤖 Rocky AI initialised")

    # ── startup checks ────────────────────────────────────────────────────────

    def _preflight_check(self):
        errors = []
        if not os.path.isfile(WHISPER_PATH):
            errors.append(f"Whisper binary not found: {WHISPER_PATH}")
        if not os.path.isfile(WHISPER_MODEL):
            errors.append(f"Whisper model not found: {WHISPER_MODEL}")
        if not os.path.isfile(PIPER_VOICE):
            errors.append(f"Piper voice not found: {PIPER_VOICE}")
        if errors:
            for e in errors:
                print(f"❌ {e}")
            sys.exit(1)

        try:
            r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
            models = [m["name"] for m in r.json().get("models", [])]
            if not any(OLLAMA_MODEL in m for m in models):
                print(f"⚠️  Model '{OLLAMA_MODEL}' not pulled yet. Run: ollama pull {OLLAMA_MODEL}")
        except Exception:
            print(f"⚠️  Ollama not reachable at {OLLAMA_URL} — start with: ollama serve")

    # ── model warm-up ─────────────────────────────────────────────────────────

    def _warmup_model(self):
        """
        Send a tiny dummy request so Ollama loads the model into RAM now,
        not on the first real question.  Uses keep_alive=-1 so it stays loaded.
        """
        print("🔥 Warming up LLM model …")
        self.display.set_emotion(EmotionState.LOADING)
        try:
            resp = requests.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "stream": False,
                    "keep_alive": OLLAMA_KEEP_ALIVE,
                    "messages": [{"role": "user", "content": "hi"}],
                    "options": {"num_predict": 1},
                },
                timeout=120,
            )
            if resp.status_code == 200:
                print("✅ Model loaded and warm — ready!")
            else:
                print(f"⚠️  Warmup got HTTP {resp.status_code}")
        except Exception as e:
            print(f"⚠️  Warmup failed: {e}")
        finally:
            self.display.set_emotion(EmotionState.IDLE)

    # ── wake-word callback ────────────────────────────────────────────────────

    def _on_wake_word(self):
        self._run_interaction()

    # ── core pipeline ─────────────────────────────────────────────────────────

    def _run_interaction(self, typed_text: str | None = None):
        if not self._interaction_lock.acquire(blocking=False):
            print("⚠️  Already responding — ignoring trigger")
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
                    print("⚠️  Could not understand — please try again")
                    return

            print(f"📝 You: {text}")

            hint = self._detect_emotion(text)
            self.display.set_emotion(EmotionState.THINKING)
            response = self._llm(text)
            if not response:
                response = "Sorry, I'm having trouble thinking right now."

            print(f"💭 Rocky: {response}")

            # Set speaking emotion and trigger mouth animation
            self.display.set_emotion(EmotionState.SPEAKING)
            self._speak(response)

        finally:
            self.display.set_emotion(EmotionState.IDLE)
            self._interaction_lock.release()

    # ── audio recording ───────────────────────────────────────────────────────

    def _record_audio(self) -> str | None:
        print(f"🎤 Recording {RECORD_SECONDS} s …")
        path = f"{RECORDINGS_DIR}/rec_{int(time.time())}.wav"
        try:
            frames = record_seconds(RECORD_SECONDS, self._dev, self._native_rate)
            save_wav(path, frames)
            size = os.path.getsize(path)
            print(f"✅ Saved → {path}  ({size:,} bytes)")
            return path
        except Exception as e:
            print(f"❌ Recording error: {e}")
            return None

    # ── whisper transcription ─────────────────────────────────────────────────

    def _transcribe(self, audio_file: str) -> str | None:
        wav      = Path(audio_file)
        out_stem = str(wav.with_suffix(""))
        txt      = wav.with_suffix(".txt")

        print(f"🧠 Transcribing {wav.name} …")
        try:
            proc = subprocess.Popen(
                [
                    WHISPER_PATH, "-m", WHISPER_MODEL,
                    "-f", str(wav),
                    "--no-timestamps", "--output-txt",
                    "--output-file", out_stem,
                    "-t", "2",
                    "--language", "en",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            try:
                _, stderr = proc.communicate(timeout=25)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                print("⚠️  Whisper timed out — skipping")
                return None

            if proc.returncode == -11:
                print("❌ Whisper segfaulted — rebuild with -DGGML_NATIVE=OFF")
                return None

            if proc.returncode != 0:
                print(f"⚠️  Whisper exited {proc.returncode}: {stderr.decode(errors='replace')[:200]}")

            if txt.exists():
                result = txt.read_text().strip()
                txt.unlink(missing_ok=True)
                print(f"📄 Heard: {result!r}")
                return result or None

            print(f"⚠️  Whisper ran (rc={proc.returncode}) but no .txt at {txt}")

        except FileNotFoundError:
            print(f"❌ Whisper binary not found: {WHISPER_PATH}")
        except Exception as e:
            print(f"❌ Transcription error: {e}")
        finally:
            txt.unlink(missing_ok=True)
        return None

    # ── Ollama LLM ────────────────────────────────────────────────────────────

    def _llm(self, user_text: str) -> str | None:
        payload = {
            "model": OLLAMA_MODEL,
            "stream": True,
            "keep_alive": OLLAMA_KEEP_ALIVE,   # never unload between calls
            "messages": [
                {"role": "system", "content": OLLAMA_SYSTEM_PROMPT},
                {"role": "user",   "content": user_text},
            ],
            "options": {"temperature": 0.7, "num_predict": 120},
        }

        # Speaking mouth animation while streaming (0fps screens get a toggle per token batch)
        mouth_toggle = [False]

        for attempt in range(2):
            try:
                tokens = []
                with requests.post(
                    f"{OLLAMA_URL}/api/chat",
                    json=payload,
                    stream=True,
                    timeout=(10, 90),
                ) as resp:
                    if resp.status_code != 200:
                        print(f"❌ Ollama HTTP {resp.status_code}")
                        return None
                    for line in resp.iter_lines():
                        if not line:
                            continue
                        chunk = json.loads(line)
                        tok = chunk["message"]["content"]
                        tokens.append(tok)
                        # Toggle mouth open/close every ~5 tokens for 0fps screens
                        if len(tokens) % 5 == 0:
                            self.display.set_emotion(EmotionState.SPEAKING)
                        if chunk.get("done"):
                            break
                return "".join(tokens).strip() or None

            except requests.exceptions.ConnectionError:
                print("❌ Cannot reach Ollama — run: ollama serve")
                return None
            except requests.exceptions.Timeout:
                print(f"⚠️  Ollama timed out (attempt {attempt + 1}/2) — retrying…")
            except Exception as e:
                print(f"❌ LLM error: {e}")
                return None

        print("❌ Ollama timed out after 2 attempts")
        return None

    # ── Piper TTS ─────────────────────────────────────────────────────────────

    def _speak(self, text: str):
        path = f"{RESPONSES_DIR}/resp_{int(time.time())}.wav"
        try:
            proc = subprocess.run(
                ["piper", "--model", PIPER_VOICE, "--output_file", path],
                input=text.encode(),
                capture_output=True,
                timeout=30,
            )
            if proc.returncode != 0:
                print(f"⚠️  Piper error: {proc.stderr.decode()[:300]}")
                return

            # Play and animate mouth: toggle open/closed every 0.4 s
            play = subprocess.Popen(["aplay", path], stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
            while play.poll() is None:
                self.display.set_emotion(EmotionState.SPEAKING)
                time.sleep(0.4)

        except FileNotFoundError:
            print("❌ 'piper' not found — is the venv active?")
        except Exception as e:
            print(f"❌ TTS error: {e}")
        finally:
            self._prune(RESPONSES_DIR)

    # ── emotion hint ──────────────────────────────────────────────────────────

    @staticmethod
    def _detect_emotion(text: str):
        t = text.lower()
        if any(w in t for w in ("sad", "cry", "upset", "depressed", "miss", "alone")):
            return EmotionState.SAD
        if any(w in t for w in ("angry", "mad", "furious", "hate", "annoying")):
            return EmotionState.ANGRY
        if any(w in t for w in ("happy", "great", "awesome", "love", "wonderful", "yay")):
            return EmotionState.HAPPY
        if any(w in t for w in ("wow", "amazing", "incredible", "surprised", "whoa")):
            return EmotionState.SURPRISED
        if any(w in t for w in ("scared", "afraid", "fear", "terrified", "horror")):
            return EmotionState.SCARED
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
        print(f"🗣️   Say '{WAKE_WORD}'  — always listening")
        print("    Press Enter to trigger manually")
        print("    Type a question + Enter to skip voice")
        print("    Ctrl-C to quit")
        print("═" * 54 + "\n")

        # Start display first (shows IDLE face immediately)
        threading.Thread(target=self.display.run, daemon=True).start()

        # Warm up model in background so first response is fast
        threading.Thread(target=self._warmup_model, daemon=True).start()

        # Start wake word and keyboard
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
