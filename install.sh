#!/bin/bash
set -e

echo "🤖 Installing Rocky AI Bot..."

# ── System dependencies ────────────────────────────────────────────────────────
sudo apt update
sudo apt install -y \
    git curl wget build-essential cmake \
    python3 python3-pip python3-venv \
    ffmpeg portaudio19-dev \
    libopenblas-dev \
    espeak-ng \
    pipewire pipewire-pulse wireplumber \
    alsa-utils

# ── Ollama ─────────────────────────────────────────────────────────────────────
echo "📦 Installing Ollama..."
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable ollama
sudo systemctl start ollama
sleep 6
ollama pull gemma3:4b

# ── Whisper.cpp ────────────────────────────────────────────────────────────────
echo "🎤 Building Whisper.cpp..."
mkdir -p ~/Applications
cd ~/Applications
if [ ! -d whisper.cpp ]; then
    git clone https://github.com/ggml-org/whisper.cpp
fi
cd whisper.cpp
cmake -B build
cmake --build build -j$(nproc)
bash ./models/download-ggml-model.sh base.en

# ── Python environment ─────────────────────────────────────────────────────────
echo "🐍 Setting up Python environment..."
cd ~/rocky
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip

# Note: correct filename is requirements.txt (was typo 'requiremets.txt' in original)
pip install -r requirements.txt
pip install pyaudio

# ── Directories ────────────────────────────────────────────────────────────────
mkdir -p voices recordings responses

# ── Piper voice ────────────────────────────────────────────────────────────────
echo "🔊 Downloading Piper voice..."
cd ~/rocky/voices
BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/arctic/medium"
wget -nc "$BASE/en_US-arctic-medium.onnx"
wget -nc "$BASE/en_US-arctic-medium.onnx.json"

# ── Add user to video group for framebuffer access ─────────────────────────────
sudo usermod -aG video "$USER"
echo "ℹ️  Added $USER to 'video' group (log out & back in for display to work)"

echo ""
echo "✅ Installation complete!"
echo ""
echo "Next steps:"
echo "  1. Test mic:    arecord -D plughw:0,0 -f S16_LE -r 16000 -c 1 -d 5 test.wav && aplay test.wav"
echo "  2. Find device: arecord -l   (update MIC_DEVICE in config.py if needed)"
echo "  3. Run Rocky:   source venv/bin/activate && python3 app.py"
echo "  4. For autostart:"
echo "     sudo cp ~/rocky/rocky.service /etc/systemd/system/"
echo "     sudo systemctl daemon-reload"
echo "     sudo systemctl enable rocky.service"
echo "     sudo systemctl start rocky.service"
