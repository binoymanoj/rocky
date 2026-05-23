#!/usr/bin/env python3
"""
Rocky AI Buddy - Main Application
Orchestrates wake word detection, speech recognition, LLM processing, and TTS
"""

import os
import sys
import time
import subprocess
import requests
import wave
import pyaudio
from pathlib import Path
import threading
import json

from config import *
from wake_word import WakeWordDetector
from display import FaceDisplay, EmotionState


class RockyAI:
    def __init__(self):
        self.running = False
        self.wake_detector = WakeWordDetector(callback=self.on_wake_word)
        self.display = FaceDisplay()
        self.audio = pyaudio.PyAudio()
        
        # Ensure directories exist
        Path(RECORDINGS_DIR).mkdir(exist_ok=True)
        Path(RESPONSES_DIR).mkdir(exist_ok=True)
        
        print("🤖 Rocky AI initialized")
    
    def on_wake_word(self):
        """Callback when wake word is detected"""
        print("\n👂 Wake word detected!")
        self.display.set_emotion(EmotionState.LISTENING)
        
        # Record user speech
        audio_file = self.record_audio()
        
        if audio_file:
            # Transcribe with Whisper
            self.display.set_emotion(EmotionState.THINKING)
            text = self.transcribe_audio(audio_file)
            
            if text:
                print(f"📝 You said: {text}")
                
                # Get LLM response
                response = self.get_llm_response(text)
                
                if response:
                    print(f"💭 Rocky: {response}")
                    
                    # Speak response
                    self.display.set_emotion(EmotionState.SPEAKING)
                    self.speak(response)
        
        # Return to idle
        self.display.set_emotion(EmotionState.IDLE)
    
    def record_audio(self, duration=5):
        """Record audio from microphone"""
        print("🎤 Recording...")
        
        timestamp = int(time.time())
        filename = f"{RECORDINGS_DIR}/recording_{timestamp}.wav"
        
        try:
            # Parse device string "plughw:X,Y"
            device_index = None
            for i in range(self.audio.get_device_count()):
                dev_info = self.audio.get_device_info_by_index(i)
                if dev_info['maxInputChannels'] > 0:
                    device_index = i
                    break
            
            stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=CHANNELS,
                rate=SAMPLE_RATE,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=1024
            )
            
            frames = []
            
            # Record for duration or until silence
            for _ in range(0, int(SAMPLE_RATE / 1024 * duration)):
                data = stream.read(1024, exception_on_overflow=False)
                frames.append(data)
            
            stream.stop_stream()
            stream.close()
            
            # Save to WAV file
            wf = wave.open(filename, 'wb')
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(self.audio.get_sample_size(pyaudio.paInt16))
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(b''.join(frames))
            wf.close()
            
            print(f"✅ Recorded to {filename}")
            return filename
            
        except Exception as e:
            print(f"❌ Recording error: {e}")
            return None
    
    def transcribe_audio(self, audio_file):
        """Transcribe audio using Whisper.cpp"""
        try:
            cmd = [
                WHISPER_PATH,
                "-m", WHISPER_MODEL,
                "-f", audio_file,
                "--no-timestamps",
                "--output-txt"
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # Read the generated .txt file
            txt_file = audio_file.replace('.wav', '.txt')
            if os.path.exists(txt_file):
                with open(txt_file, 'r') as f:
                    text = f.read().strip()
                os.remove(txt_file)  # Clean up
                return text
            
            return None
            
        except Exception as e:
            print(f"❌ Transcription error: {e}")
            return None
    
    def get_llm_response(self, prompt):
        """Get response from Ollama"""
        try:
            # Detect emotion from prompt for display
            emotion = self.detect_emotion(prompt)
            if emotion:
                self.display.set_emotion(emotion)
            
            url = f"{OLLAMA_URL}/api/generate"
            data = {
                "model": OLLAMA_MODEL,
                "prompt": f"You are Rocky, a friendly AI assistant. Keep responses concise and conversational (2-3 sentences max). User: {prompt}",
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "num_predict": 100
                }
            }
            
            response = requests.post(url, json=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                return result.get('response', '').strip()
            
            return None
            
        except Exception as e:
            print(f"❌ LLM error: {e}")
            return "I'm having trouble thinking right now."
    
    def detect_emotion(self, text):
        """Simple emotion detection from text"""
        text_lower = text.lower()
        
        if any(word in text_lower for word in ['sad', 'cry', 'upset', 'depressed']):
            return EmotionState.SAD
        elif any(word in text_lower for word in ['angry', 'mad', 'furious', 'hate']):
            return EmotionState.ANGRY
        elif any(word in text_lower for word in ['happy', 'great', 'awesome', 'love', 'wonderful']):
            return EmotionState.HAPPY
        elif any(word in text_lower for word in ['wow', 'amazing', 'incredible', 'surprised']):
            return EmotionState.SURPRISED
        
        return None
    
    def speak(self, text):
        """Convert text to speech using Piper and play"""
        try:
            timestamp = int(time.time())
            output_file = f"{RESPONSES_DIR}/response_{timestamp}.wav"
            
            # Generate speech with Piper
            cmd = f"echo '{text}' | piper --model {PIPER_VOICE} --output_file {output_file}"
            subprocess.run(cmd, shell=True, check=True, timeout=30)
            
            # Play audio
            subprocess.run(['aplay', output_file], check=True)
            
            # Clean up old files (keep last 10)
            self.cleanup_old_files(RESPONSES_DIR, keep=10)
            
        except Exception as e:
            print(f"❌ TTS error: {e}")
    
    def cleanup_old_files(self, directory, keep=10):
        """Remove old audio files, keeping only the most recent ones"""
        try:
            files = sorted(Path(directory).glob('*.wav'), key=os.path.getmtime, reverse=True)
            for old_file in files[keep:]:
                old_file.unlink()
        except Exception as e:
            print(f"⚠️ Cleanup error: {e}")
    
    def run(self):
        """Main run loop"""
        self.running = True
        
        print("\n" + "="*50)
        print("🤖 Rocky AI Buddy is now running!")
        print(f"💬 Say '{WAKE_WORD}' to wake me up")
        print("="*50 + "\n")
        
        # Start display in separate thread
        display_thread = threading.Thread(target=self.display.run, daemon=True)
        display_thread.start()
        
        # Start wake word detection
        self.wake_detector.start()
        
        try:
            while self.running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n👋 Shutting down Rocky...")
        finally:
            self.stop()
    
    def stop(self):
        """Clean shutdown"""
        self.running = False
        self.wake_detector.stop()
        self.display.stop()
        self.audio.terminate()
        print("✅ Rocky shut down gracefully")


def main():
    rocky = RockyAI()
    rocky.run()


if __name__ == "__main__":
    main()
