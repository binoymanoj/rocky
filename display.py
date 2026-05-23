#!/usr/bin/env python3
"""
Rocky AI Buddy - Animated Face Display
Renders animated eyes and mouth with various emotional states
"""

import time
import os
import sys
from enum import Enum
import math
import random

try:
    from PIL import Image, ImageDraw
    import numpy as np
except ImportError:
    print("Installing PIL...")
    os.system("pip install pillow numpy")
    from PIL import Image, ImageDraw
    import numpy as np

from config import DISPLAY_WIDTH, DISPLAY_HEIGHT


class EmotionState(Enum):
    """Different emotional states for Rocky"""
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    SURPRISED = "surprised"


class FaceDisplay:
    def __init__(self):
        self.width = DISPLAY_WIDTH
        self.height = DISPLAY_HEIGHT
        self.running = False
        self.current_emotion = EmotionState.IDLE
        self.frame_count = 0
        self.blink_counter = 0
        self.is_blinking = False
        
        # Eye parameters
        self.eye_size = 80
        self.eye_spacing = 100
        self.pupil_size = 30
        self.pupil_x_offset = 0
        self.pupil_y_offset = 0
        
        # Mouth parameters
        self.mouth_y = 220
        self.mouth_width = 120
        self.mouth_height = 20
        
        # Animation state
        self.speaking_phase = 0
        
        print(f"🖥️ Display initialized ({self.width}x{self.height})")
    
    def set_emotion(self, emotion: EmotionState):
        """Change current emotional state"""
        self.current_emotion = emotion
        print(f"😊 Emotion changed to: {emotion.value}")
    
    def draw_eye(self, draw, x, y, size, blink=False):
        """Draw a single eye"""
        if blink:
            # Draw closed eye (horizontal line)
            draw.line(
                [(x - size//2, y), (x + size//2, y)],
                fill='white',
                width=4
            )
        else:
            # Draw eye outline
            draw.ellipse(
                [x - size//2, y - size//2, x + size//2, y + size//2],
                outline='white',
                fill='black',
                width=3
            )
            
            # Draw pupil with offset
            pupil_x = x + int(self.pupil_x_offset * size//4)
            pupil_y = y + int(self.pupil_y_offset * size//4)
            
            draw.ellipse(
                [
                    pupil_x - self.pupil_size//2,
                    pupil_y - self.pupil_size//2,
                    pupil_x + self.pupil_size//2,
                    pupil_y + self.pupil_size//2
                ],
                fill='white'
            )
    
    def draw_mouth(self, draw, emotion):
        """Draw mouth based on emotion"""
        center_x = self.width // 2
        y = self.mouth_y
        w = self.mouth_width
        h = self.mouth_height
        
        if emotion == EmotionState.HAPPY:
            # Smile arc
            draw.arc(
                [center_x - w//2, y - h, center_x + w//2, y + h],
                start=0,
                end=180,
                fill='white',
                width=4
            )
        
        elif emotion == EmotionState.SAD:
            # Frown arc
            draw.arc(
                [center_x - w//2, y - h*2, center_x + w//2, y],
                start=180,
                end=360,
                fill='white',
                width=4
            )
        
        elif emotion == EmotionState.ANGRY:
            # Straight line (angry mouth)
            draw.line(
                [(center_x - w//2, y), (center_x + w//2, y)],
                fill='white',
                width=4
            )
        
        elif emotion == EmotionState.SURPRISED:
            # Open circle (O shape)
            draw.ellipse(
                [center_x - 20, y - 20, center_x + 20, y + 20],
                outline='white',
                fill='black',
                width=3
            )
        
        elif emotion == EmotionState.SPEAKING:
            # Animated mouth (opens/closes)
            mouth_open = abs(math.sin(self.speaking_phase)) * 30
            draw.ellipse(
                [
                    center_x - 25,
                    y - mouth_open//2,
                    center_x + 25,
                    y + mouth_open//2
                ],
                outline='white',
                fill='black',
                width=3
            )
        
        else:
            # Neutral smile
            draw.arc(
                [center_x - w//2, y - h//2, center_x + w//2, y + h//2],
                start=0,
                end=180,
                fill='white',
                width=3
            )
    
    def update_animation(self):
        """Update animation parameters based on emotion"""
        self.frame_count += 1
        
        # Blinking animation
        if self.frame_count % 180 == 0:  # Blink every ~3 seconds
            self.is_blinking = True
            self.blink_counter = 0
        
        if self.is_blinking:
            self.blink_counter += 1
            if self.blink_counter > 6:  # Blink duration
                self.is_blinking = False
        
        # Emotion-specific animations
        if self.current_emotion == EmotionState.LISTENING:
            # Eyes wide, attentive
            self.eye_size = 85
            self.pupil_size = 35
            self.pupil_x_offset = 0
            self.pupil_y_offset = 0
        
        elif self.current_emotion == EmotionState.THINKING:
            # Look up-left
            self.eye_size = 80
            self.pupil_size = 30
            self.pupil_x_offset = -0.5 + 0.3 * math.sin(self.frame_count * 0.02)
            self.pupil_y_offset = -0.5
        
        elif self.current_emotion == EmotionState.SPEAKING:
            # Normal eyes, animated mouth
            self.eye_size = 80
            self.pupil_size = 30
            self.pupil_x_offset = 0
            self.pupil_y_offset = 0
            self.speaking_phase += 0.3
        
        elif self.current_emotion == EmotionState.HAPPY:
            # Wide eyes, slight up look
            self.eye_size = 85
            self.pupil_size = 32
            self.pupil_x_offset = 0
            self.pupil_y_offset = -0.2
        
        elif self.current_emotion == EmotionState.SAD:
            # Droopy eyes
            self.eye_size = 75
            self.pupil_size = 28
            self.pupil_x_offset = 0
            self.pupil_y_offset = 0.3
        
        elif self.current_emotion == EmotionState.ANGRY:
            # Narrowed eyes
            self.eye_size = 70
            self.pupil_size = 25
            self.pupil_x_offset = 0
            self.pupil_y_offset = 0
        
        elif self.current_emotion == EmotionState.SURPRISED:
            # Very wide eyes
            self.eye_size = 95
            self.pupil_size = 40
            self.pupil_x_offset = 0
            self.pupil_y_offset = 0
        
        else:  # IDLE
            # Gentle random eye movement
            self.eye_size = 80
            self.pupil_size = 30
            self.pupil_x_offset = 0.3 * math.sin(self.frame_count * 0.02)
            self.pupil_y_offset = 0.2 * math.cos(self.frame_count * 0.03)
    
    def draw_frame(self):
        """Draw a single frame"""
        # Create black background
        img = Image.new('RGB', (self.width, self.height), color='black')
        draw = ImageDraw.Draw(img)
        
        # Calculate eye positions
        center_x = self.width // 2
        eye_y = self.height // 2 - 30
        left_eye_x = center_x - self.eye_spacing // 2
        right_eye_x = center_x + self.eye_spacing // 2
        
        # Draw angry eyebrows if angry
        if self.current_emotion == EmotionState.ANGRY:
            draw.line(
                [(left_eye_x - 40, eye_y - 50), (left_eye_x + 20, eye_y - 30)],
                fill='white',
                width=4
            )
            draw.line(
                [(right_eye_x - 20, eye_y - 30), (right_eye_x + 40, eye_y - 50)],
                fill='white',
                width=4
            )
        
        # Draw raised eyebrows if surprised
        if self.current_emotion == EmotionState.SURPRISED:
            draw.arc(
                [left_eye_x - 50, eye_y - 70, left_eye_x + 50, eye_y - 30],
                start=0,
                end=180,
                fill='white',
                width=3
            )
            draw.arc(
                [right_eye_x - 50, eye_y - 70, right_eye_x + 50, eye_y - 30],
                start=0,
                end=180,
                fill='white',
                width=3
            )
        
        # Draw eyes
        self.draw_eye(draw, left_eye_x, eye_y, self.eye_size, self.is_blinking)
        self.draw_eye(draw, right_eye_x, eye_y, self.eye_size, self.is_blinking)
        
        # Draw mouth
        self.draw_mouth(draw, self.current_emotion)
        
        return img
    
    def display_frame(self, img):
        """Display frame on screen (or save for terminal display)"""
        # For Raspberry Pi framebuffer, you would write directly to /dev/fb0
        # For terminal display, we'll use ASCII art representation
        
        # Convert to ASCII for terminal (simplified version)
        # In production, write directly to framebuffer
        pass
    
    def run(self):
        """Main display loop"""
        self.running = True
        print("🎨 Display loop started")
        
        try:
            while self.running:
                self.update_animation()
                frame = self.draw_frame()
                self.display_frame(frame)
                time.sleep(1/30)  # 30 FPS
        except Exception as e:
            print(f"❌ Display error: {e}")
    
    def stop(self):
        """Stop display loop"""
        self.running = False
        print("🛑 Display stopped")


# Test display
if __name__ == "__main__":
    display = FaceDisplay()
    
    print("Testing emotions...")
    emotions = [
        EmotionState.IDLE,
        EmotionState.HAPPY,
        EmotionState.SAD,
        EmotionState.ANGRY,
        EmotionState.SURPRISED,
        EmotionState.THINKING,
        EmotionState.LISTENING,
        EmotionState.SPEAKING
    ]
    
    import threading
    thread = threading.Thread(target=display.run, daemon=True)
    thread.start()
    
    for emotion in emotions:
        print(f"\nShowing: {emotion.value}")
        display.set_emotion(emotion)
        time.sleep(3)
    
    display.stop()
