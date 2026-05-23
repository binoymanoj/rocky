# Audio
MIC_DEVICE = "plughw:0,0"  # Update from arecord -l
SAMPLE_RATE = 16000
CHANNELS = 1

# Paths
WHISPER_PATH = "/home/pi/Applications/whisper.cpp/build/bin/main"
WHISPER_MODEL = "/home/pi/Applications/whisper.cpp/models/ggml-base.en.bin"
PIPER_VOICE = "/home/pi/rocky/voices/en_US-arctic-medium.onnx"

# Directories
RECORDINGS_DIR = "recordings"
RESPONSES_DIR = "responses"

# LLM
OLLAMA_MODEL = "gemma3:4b"
OLLAMA_URL = "http://localhost:11434"

# Wake Word
WAKE_WORD = "hey rocky"

# Display
DISPLAY_WIDTH = 480
DISPLAY_HEIGHT = 320
