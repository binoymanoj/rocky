#!/usr/bin/env python3
"""
Run this standalone to isolate exactly where the segfault happens.
Usage: python3 debug_transcribe.py
"""
import os, sys, subprocess, wave, time
from pathlib import Path

# ── Step 1: verify whisper binary ─────────────────────────────────────────────
WHISPER = "/home/zoro/Applications/whisper.cpp/build/bin/main"
MODEL   = "/home/zoro/Applications/whisper.cpp/models/ggml-base.en.bin"

print("── Step 1: Whisper binary ───────────────────────────────────")
if not os.path.exists(WHISPER):
    print(f"  ❌ Binary not found: {WHISPER}")
    sys.exit(1)
print(f"  ✓ Binary: {WHISPER}")
print(f"  Size: {os.path.getsize(WHISPER):,} bytes")

print("\n── Step 2: Model file ───────────────────────────────────────")
if not os.path.exists(MODEL):
    print(f"  ❌ Model not found: {MODEL}")
    sys.exit(1)
print(f"  ✓ Model: {MODEL}")
print(f"  Size: {os.path.getsize(MODEL):,} bytes  (expect ~142 MB for base.en)")

# ── Step 2: check wav written by rocky ────────────────────────────────────────
print("\n── Step 3: Check last recorded wav ─────────────────────────")
wavs = sorted(Path("recordings").glob("rec_*.wav"), key=os.path.getmtime, reverse=True)
if not wavs:
    print("  ❌ No recordings found — run the app and press Enter first, then re-run this script")
    sys.exit(1)
wav = wavs[0]
print(f"  Using: {wav}")
with wave.open(str(wav)) as wf:
    print(f"  Channels   : {wf.getnchannels()}")
    print(f"  Sample rate: {wf.getframerate()}")
    print(f"  Bit depth  : {wf.getsampwidth()*8}")
    print(f"  Duration   : {wf.getnframes()/wf.getframerate():.1f} s")

# ── Step 3: run whisper with verbose output ────────────────────────────────────
print("\n── Step 4: Run Whisper (verbose) ────────────────────────────")
cmd = [WHISPER, "-m", MODEL, "-f", str(wav), "--no-timestamps", "-t", "2", "--language", "en"]
print(f"  CMD: {' '.join(cmd)}")
print()
try:
    result = subprocess.run(cmd, timeout=30)
    print(f"\n  Return code: {result.returncode}")
except subprocess.TimeoutExpired:
    print("  ❌ TIMEOUT after 30 s")
except Exception as e:
    print(f"  ❌ Exception: {e}")

# ── Step 4: check output txt ───────────────────────────────────────────────────
txt = str(wav).replace(".wav", ".txt")
print(f"\n── Step 5: Output txt file ──────────────────────────────────")
if os.path.exists(txt):
    content = Path(txt).read_text().strip()
    print(f"  ✓ Found: {txt}")
    print(f"  Content: {content!r}")
else:
    print(f"  ❌ Not found: {txt}")
    print("  (Whisper may have crashed before writing it)")
