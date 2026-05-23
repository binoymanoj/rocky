#!/usr/bin/env python3
"""
Rocky AI Buddy - Wake Word Detection
Continuously listens for the wake word "Hey Rocky"
"""

import os
import time
import wave
import pyaudio
import subprocess
import threading
from pathlib import Path

from config import *


class WakeWordDetector:
    def __init__(self, callback=None):
        self.running = False
        self.callback = callback
        self.audio = pyaudio.PyAudio()
        self.thread = None
        
        # Create temp directory for wake word detection
        self.temp_dir = Path(RECORDINGS_DIR) / "wake_word_temp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"👂 Wake word detector initialized ('{WAKE_WORD}')")
    
    def record_chunk(self, duration=2):
        """Record a short audio chunk for wake word detection"""
        try:
            # Find input device
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
            
            for _ in range(0, int(SAMPLE_RATE / 1024 * duration)):
                if not self.running:
                    break
                data = stream.read(1024, exception_on_overflow=False)
                frames.append(data)
            
            stream.stop_stream()
            stream.close()
            
            # Save to temporary WAV file
            temp_file = self.temp_dir / f"chunk_{int(time.time())}.wav"
            wf = wave.open(str(temp_file), 'wb')
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(self.audio.get_sample_size(pyaudio.paInt16))
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(b''.join(frames))
            wf.close()
            
            return temp_file
            
        except Exception as e:
            print(f"❌ Wake word recording error: {e}")
            return None
    
    def transcribe_chunk(self, audio_file):
        """Quickly transcribe audio chunk with Whisper"""
        try:
            cmd = [
                WHISPER_PATH,
                "-m", WHISPER_MODEL,
                "-f", str(audio_file),
                "--no-timestamps",
                "--output-txt",
                "-t", "2"  # Use 2 threads for faster processing
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            # Read the generated .txt file
            txt_file = str(audio_file).replace('.wav', '.txt')
            if os.path.exists(txt_file):
                with open(txt_file, 'r') as f:
                    text = f.read().strip().lower()
                os.remove(txt_file)  # Clean up
                return text
            
            return ""
            
        except Exception as e:
            print(f"❌ Wake word transcription error: {e}")
            return ""
        finally:
            # Clean up audio file
            if audio_file.exists():
                audio_file.unlink()
    
    def check_wake_word(self, text):
        """Check if wake word is present in transcribed text"""
        # Normalize text
        text = text.lower().strip()
        wake_word = WAKE_WORD.lower()
        
        # Check for exact match or close variations
        if wake_word in text:
            return True
        
        # Check for common variations
        variations = [
            "hey rocky",
            "hey rockie",
            "a rocky",
            "hey rockey",
            "hey rocket"
        ]
        
        for variant in variations:
            if variant in text:
                return True
        
        return False
    
    def detection_loop(self):
        """Main loop for wake word detection"""
        print("👂 Wake word detection started")
        
        consecutive_errors = 0
        
        while self.running:
            try:
                # Record a chunk
                audio_file = self.record_chunk(duration=2)
                
                if audio_file and self.running:
                    # Transcribe the chunk
                    text = self.transcribe_chunk(audio_file)
                    
                    # Check for wake word
                    if text and self.check_wake_word(text):
                        print(f"✅ Wake word detected! (heard: '{text}')")
                        
                        if self.callback:
                            # Run callback in separate thread to not block detection
                            callback_thread = threading.Thread(
                                target=self.callback,
                                daemon=True
                            )
                            callback_thread.start()
                            
                            # Wait for callback to complete before resuming detection
                            callback_thread.join()
                    
                    consecutive_errors = 0
                
                # Small delay to prevent excessive CPU usage
                time.sleep(0.1)
                
            except Exception as e:
                consecutive_errors += 1
                print(f"⚠️ Detection loop error: {e}")
                
                # If too many consecutive errors, pause longer
                if consecutive_errors > 5:
                    print("⚠️ Too many errors, pausing detection...")
                    time.sleep(5)
                    consecutive_errors = 0
        
        print("🛑 Wake word detection stopped")
    
    def start(self):
        """Start wake word detection in background thread"""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self.detection_loop, daemon=True)
            self.thread.start()
            print("✅ Wake word detection thread started")
    
    def stop(self):
        """Stop wake word detection"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        
        # Clean up temp directory
        try:
            for file in self.temp_dir.glob("*.wav"):
                file.unlink()
            for file in self.temp_dir.glob("*.txt"):
                file.unlink()
        except Exception as e:
            print(f"⚠️ Cleanup error: {e}")
        
        print("✅ Wake word detector stopped")


# Test wake word detector
if __name__ == "__main__":
    def test_callback():
        print("\n🎉 WAKE WORD CALLBACK TRIGGERED!\n")
        time.sleep(2)
    
    detector = WakeWordDetector(callback=test_callback)
    
    print(f"\nListening for '{WAKE_WORD}'...")
    print("Press Ctrl+C to stop\n")
    
    detector.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nStopping detector...")
        detector.stop()
