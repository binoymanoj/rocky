# ─── Audio ────────────────────────────────────────────────────────────────────
MIC_DEVICE   = None     # None = auto-detect; set to device index if wrong device picked
                        # Run: python3 -m sounddevice   to list devices
SAMPLE_RATE  = 16000    # Target rate for Whisper — code will resample if mic differs
CHANNELS     = 1        # Mono

# ─── Paths ────────────────────────────────────────────────────────────────────
WHISPER_PATH  = "/home/zoro/Applications/whisper.cpp/build/bin/whisper-cli"
WHISPER_MODEL = "/home/zoro/Applications/whisper.cpp/models/ggml-base.en.bin"
PIPER_VOICE   = "/home/zoro/rocky/voices/en_US-arctic-medium.onnx"

# ─── Directories ──────────────────────────────────────────────────────────────
RECORDINGS_DIR = "recordings"
RESPONSES_DIR  = "responses"

# ─── LLM ──────────────────────────────────────────────────────────────────────
OLLAMA_MODEL = "gemma3:4b"
OLLAMA_URL   = "http://localhost:11434"
OLLAMA_SYSTEM_PROMPT = (
    "You are Rocky, a friendly and concise AI assistant running on a Raspberry Pi. "
    "Keep every reply to 1-3 short sentences. Be warm and helpful."
)

# How long Ollama keeps the model loaded in RAM between calls.
# "-1" = forever (never unload). Keeps responses fast after first load.
OLLAMA_KEEP_ALIVE = "-1"

# ─── Wake Word ────────────────────────────────────────────────────────────────
WAKE_WORD = "hey rocky"
WAKE_WORD_VARIATIONS = [
    "hey rocky", "hey rockie", "hey rockey",
    "hey rocket", "a rocky", "hi rocky",
    "rocky", "okay rocky", "ok rocky",
]

# ─── Recording ────────────────────────────────────────────────────────────────
RECORD_SECONDS     = 6    # how long to record after wake word
WAKE_CHUNK_SECONDS = 2    # shorter chunks = faster wake word response

# ─── Display ──────────────────────────────────────────────────────────────────
DISPLAY_WIDTH  = 480
DISPLAY_HEIGHT = 320

# Set to 0 for e-ink / 0fps screens — face only redraws when emotion changes.
# Set to a number like 10 for animated screens.
TARGET_FPS     = 0

# ─── Misc ─────────────────────────────────────────────────────────────────────
MAX_SAVED_AUDIO = 10
