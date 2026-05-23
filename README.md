# Rocky AI Buddy 🤖

A fully local AI assistant running on Raspberry Pi 5 with voice interaction, animated display, and LLM processing.

## Quick Start

1. **Create project directory**
   ```bash
   mkdir -p ~/rocky
   cd ~/rocky
   ```

2. **Copy all files to ~/rocky/**
   - app.py
   - display.py
   - wake_word.py
   - config.py
   - requirements.txt
   - rocky.service
   - install.sh (from setup guide)

3. **Run installation**
   ```bash
   chmod +x install.sh
   ./install.sh
   ```

4. **Configure audio device**
   ```bash
   arecord -l  # Note your device number
   ```
   
   Edit `config.py` and update:
   ```python
   MIC_DEVICE = "plughw:X,Y"  # Replace X,Y with your device
   ```

5. **Test components**
   ```bash
   source venv/bin/activate
   
   # Test wake word detection
   python wake_word.py
   
   # Test display (Ctrl+C to stop)
   python display.py
   ```

6. **Install and start service**
   ```bash
   sudo cp rocky.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable rocky.service
   sudo systemctl start rocky.service
   ```

## Usage

Say **"Hey Rocky"** to activate the assistant.

Rocky will:
1. 👂 Listen for your command
2. 🧠 Process with local LLM
3. 🗣️ Respond with voice
4. 😊 Display emotions on screen

## Monitoring

```bash
# View live logs
sudo journalctl -u rocky.service -f

# Check status
sudo systemctl status rocky.service

# Restart service
sudo systemctl restart rocky.service
```

## Troubleshooting

**No audio input:**
```bash
arecord -l  # Verify device exists
alsamixer   # Adjust microphone levels
```

**Wake word not detecting:**
- Speak clearly and louder
- Check microphone placement
- Reduce background noise
- Test with: `python wake_word.py`

**Ollama not responding:**
```bash
sudo systemctl status ollama
ollama list  # Verify model is downloaded
```

**Display not showing:**
- Check framebuffer: `ls /dev/fb*`
- Verify display driver is loaded

## File Structure

```
~/rocky/
├── app.py              # Main orchestrator
├── display.py          # Animated face
├── wake_word.py        # Wake word listener
├── config.py           # Configuration
├── requirements.txt    # Python deps
├── rocky.service       # Systemd service
├── voices/             # TTS voices
├── recordings/         # Audio captures
├── responses/          # TTS outputs
└── venv/              # Python environment

~/Applications/
└── whisper.cpp/       # Speech recognition
```

## Customization

**Change wake word:**
Edit `config.py`:
```python
WAKE_WORD = "hey rocky"  # Change to anything
```

**Change voice:**
Download different Piper voice from:
https://huggingface.co/rhasspy/piper-voices

Update `config.py`:
```python
PIPER_VOICE = "/home/pi/rocky/voices/your-voice.onnx"
```

**Change LLM model:**
```bash
ollama pull llama3.2:3b  # Or any other model
```

Update `config.py`:
```python
OLLAMA_MODEL = "llama3.2:3b"
```

## Performance Tips

- Use smaller models for faster response (gemma2:2b recommended)
- Reduce `MAX_RECORDING_DURATION` in config.py for quicker processing
- Lower display FPS if CPU usage is high
- Consider using a heatsink/fan for Raspberry Pi 5

## Credits

- **Whisper.cpp**: Speech recognition
- **Ollama**: Local LLM
- **Piper TTS**: Text-to-speech
- **PyAudio**: Audio interface

## License

MIT - Feel free to modify and share!
