#!/bin/bash
# Run this first if Rocky won't start — it checks every dependency
echo "═══════════════════════════════════════"
echo " Rocky AI — Diagnostic Check"
echo "═══════════════════════════════════════"

# Python
echo ""
echo "── Python ──────────────────────────────"
python3 --version

# sounddevice + list devices
echo ""
echo "── Audio devices ───────────────────────"
python3 -c "
import sounddevice as sd
devs = sd.query_devices()
for i, d in enumerate(devs):
    tag = '<-- INPUT' if d['max_input_channels'] > 0 else ''
    print(f'  [{i}] {d[\"name\"]}  in={d[\"max_input_channels\"]}  out={d[\"max_output_channels\"]} {tag}')
print()
print('Default input :', sd.query_devices(kind=\"input\")[\"name\"])
print('Default output:', sd.query_devices(kind=\"output\")[\"name\"])
"

# Whisper
echo ""
echo "── Whisper.cpp ─────────────────────────"
WHISPER="$HOME/Applications/whisper.cpp/build/bin/main"
MODEL="$HOME/Applications/whisper.cpp/models/ggml-base.en.bin"
[ -x "$WHISPER" ] && echo "  binary : OK ($WHISPER)" || echo "  binary : MISSING"
[ -f "$MODEL"   ] && echo "  model  : OK" || echo "  model  : MISSING"

# Ollama
echo ""
echo "── Ollama ──────────────────────────────"
curl -s http://localhost:11434/api/tags | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    models = [m['name'] for m in data.get('models', [])]
    print('  running : YES')
    print('  models  :', models)
except:
    print('  running : NO  (start with: ollama serve)')
"

# Piper
echo ""
echo "── Piper TTS ───────────────────────────"
if command -v piper &>/dev/null; then
    echo "  piper   : OK ($(which piper))"
else
    echo "  piper   : NOT FOUND (is venv active?)"
fi
VOICE="$HOME/rocky/voices/en_US-arctic-medium.onnx"
[ -f "$VOICE" ] && echo "  voice   : OK" || echo "  voice   : MISSING ($VOICE)"

# aplay
echo ""
echo "── aplay ───────────────────────────────"
command -v aplay &>/dev/null && echo "  aplay : OK" || echo "  aplay : MISSING (apt install alsa-utils)"

echo ""
echo "═══════════════════════════════════════"
echo " If MIC_DEVICE is None in config.py,"
echo " set it to the [number] of your USB mic above."
echo "═══════════════════════════════════════"
