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
