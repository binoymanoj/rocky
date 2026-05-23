# Rocky AI Buddy - Raspberry Pi 5 Setup Guide

Personal AI assistant with animated display, voice interaction, and local LLM processing.

## Hardware
- Raspberry Pi 5 (8GB)
- 3.5" display (auto-boot to terminal)
- USB-C IEM (microphone + speaker)

## Architecture

```
┌─────────────────────────────────────────────────┐
│                   Rocky AI Bot                  │
├─────────────────────────────────────────────────┤
│                                                 │
│  USB-C IEM Mic → Whisper.cpp → Ollama (gemma3)  │
│                       ↓                         │
│                  Piper TTS → IEM Speaker        │
│                                                 │
│  3.5" Display: Animated Eyes & Expressions      │
│  Wake Word: "Hey Rocky"                         │
└─────────────────────────────────────────────────┘
```

## Project Structure

```
~/rocky/
├── app.py                    # Main application
├── display.py                # Animated face renderer
├── wake_word.py              # Wake word detection
├── config.py                 # Configuration
├── requirements.txt          # Python dependencies
├── rocky.service             # Systemd service file
├── install.sh                # Main installer
├── voices/                   # Piper TTS voices
├── recordings/               # Audio captures
├── responses/                # TTS outputs
└── venv/                     # Python virtual environment

~/Applications/
└── whisper.cpp/              # Whisper build
    └── models/
        └── ggml-base.en.bin
```

## Fresh Install

### 1. First Boot Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Set hostname (optional)
sudo hostnamectl set-hostname rocky-pi
```

### 2. Run Installation Script

Save as `~/rocky/install.sh`:

```bash
#!/bin/bash
set -e

echo "🤖 Installing Rocky AI Bot..."

# System dependencies
sudo apt install -y \
    git curl wget build-essential cmake \
    python3 python3-pip python3-venv \
    ffmpeg portaudio19-dev \
    libatlas-base-dev \
    espeak-ng \
    pipewire pipewire-pulse wireplumber \
    alsa-utils

# Ollama
echo "📦 Installing Ollama..."
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable ollama
sudo systemctl start ollama

# Pull model (wait for Ollama to start)
sleep 5
ollama pull gemma2:2b

# Whisper.cpp
echo "🎤 Building Whisper.cpp..."
mkdir -p ~/Applications
cd ~/Applications
git clone https://github.com/ggml-org/whisper.cpp
cd whisper.cpp
cmake -B build
cmake --build build -j4
bash ./models/download-ggml-model.sh base.en

# Python environment
echo "🐍 Setting up Python environment..."
cd ~/rocky
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install piper-tts pyaudio numpy pillow

# Create directories
mkdir -p voices recordings responses models

# Download Piper voice
echo "🔊 Downloading TTS voice..."
cd voices
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/arctic/medium/en_US-arctic-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/arctic/medium/en_US-arctic-medium.onnx.json

echo "✅ Installation complete!"
echo "Next steps:"
echo "1. Test microphone: arecord -D plughw:CARD,DEV -f S16_LE -r 16000 -c 1 test.wav"
echo "2. Configure rocky.service"
echo "3. sudo systemctl enable rocky.service"
```

Make executable and run:
```bash
chmod +x install.sh
./install.sh
```

### 3. Audio Configuration

```bash
# List devices
lsusb
aplay -l
arecord -l

# Test microphone (replace CARD,DEV with your device numbers)
arecord -D plughw:0,0 -f S16_LE -r 16000 -c 1 -d 5 test.wav
aplay test.wav
```

### 4. Create Systemd Service

`~/rocky/rocky.service`:

```ini
[Unit]
Description=Rocky AI Buddy
After=network.target ollama.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/rocky
Environment="PATH=/home/pi/rocky/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/home/pi/rocky/venv/bin/python /home/pi/rocky/app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Install service:
```bash
sudo cp ~/rocky/rocky.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable rocky.service
sudo systemctl start rocky.service
```

## Configuration

`config.py`:

```python
# Audio
MIC_DEVICE = "plughw:0,0"  # Update from arecord -l
SAMPLE_RATE = 16000
CHANNELS = 1

# Paths
WHISPER_PATH = "/home/pi/Applications/whisper.cpp/build/bin/main"
WHISPER_MODEL = "/home/pi/Applications/whisper.cpp/models/ggml-base.en.bin"
PIPER_VOICE = "/home/pi/rocky/voices/en_US-arctic-medium.onnx"

# LLM
OLLAMA_MODEL = "gemma2:2b"
OLLAMA_URL = "http://localhost:11434"

# Wake Word
WAKE_WORD = "hey rocky"

# Display
DISPLAY_WIDTH = 480
DISPLAY_HEIGHT = 320
```

## Display Animation States

The animated face will respond to:
- **Idle**: Blinking, gentle eye movement
- **Listening**: Eyes wide, attentive
- **Thinking**: Eyes looking up-left, processing indicator
- **Speaking**: Mouth sync, expressive eyes
- **Happy**: Wide smile, bright eyes
- **Sad**: Droopy eyes, downturned mouth
- **Angry**: Narrowed eyes, frown
- **Surprised**: Wide eyes, open mouth

## Testing Components

```bash
# Test Ollama
ollama run gemma2:2b "Hello!"

# Test Whisper
cd ~/Applications/whisper.cpp
./build/bin/main -m models/ggml-base.en.bin -f ~/rocky/test.wav

# Test Piper
cd ~/rocky
source venv/bin/activate
echo "Hello, I am Rocky" | piper --model voices/en_US-arctic-medium.onnx --output_file test.wav
aplay test.wav

# View service logs
sudo journalctl -u rocky.service -f
```

## Quick Commands

```bash
# Start Rocky
sudo systemctl start rocky.service

# Stop Rocky
sudo systemctl stop rocky.service

# Restart Rocky
sudo systemctl restart rocky.service

# View logs
sudo journalctl -u rocky.service -f

# Check status
sudo systemctl status rocky.service
```

## Notes

- Wake word detection runs continuously in background
- Display shows animated eyes at all times
- First run may be slow while Ollama loads model
- Audio levels may need tuning via `alsamixer`
- Consider adding a physical mute button for privacy

---

**Status**: Ready to implement  
**Last Updated**: May 2026
