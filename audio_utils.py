#!/usr/bin/env python3
"""
Rocky AI Buddy — Audio Utilities
Handles device detection, native sample rate discovery, and resampling.
Centralised here so both wake_word.py and app.py share the same logic.
"""

import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

from config import MIC_DEVICE, SAMPLE_RATE, CHANNELS


# ── Device detection ──────────────────────────────────────────────────────────

def pick_input_device() -> int | None:
    """
    Return the best input device index.
    Preference order: explicit config → USB/IEM by name → system default.
    """
    if MIC_DEVICE is not None:
        dev = sd.query_devices(MIC_DEVICE)
        print(f"🎙️  Config-specified device [{MIC_DEVICE}]: {dev['name']}")
        return MIC_DEVICE

    devices = sd.query_devices()
    best = None
    for i, dev in enumerate(devices):
        if dev["max_input_channels"] < 1:
            continue
        name = dev["name"].lower()
        if best is None:
            best = i
        if any(k in name for k in ("usb", "iem", "headset", "c-media", "uac", "audio")):
            best = i
            break

    if best is not None:
        print(f"🎙️  Auto-selected device [{best}]: {sd.query_devices(best)['name']}")
    else:
        print("🎙️  Using system default input device")
    return best


# ── Native rate detection ─────────────────────────────────────────────────────

# Rates to probe, in preference order (most USB-C IEMs use 48000 or 44100)
_PROBE_RATES = [48000, 44100, 32000, 22050, 16000, 8000]

def get_native_rate(device_index: int | None) -> int:
    """
    Find the highest sample rate the device actually accepts.
    Falls back gracefully through common rates.
    """
    dev_info = sd.query_devices(device_index, "input")
    # sounddevice reports default_samplerate — try that first
    default_sr = int(dev_info.get("default_samplerate", 0))
    probe_list = ([default_sr] if default_sr else []) + _PROBE_RATES

    for rate in probe_list:
        try:
            sd.check_input_settings(
                device=device_index,
                channels=CHANNELS,
                dtype="int16",
                samplerate=rate,
            )
            if rate != SAMPLE_RATE:
                print(f"🎙️  Device native rate: {rate} Hz  (will resample → {SAMPLE_RATE} Hz for Whisper)")
            else:
                print(f"🎙️  Device native rate: {rate} Hz  ✓")
            return rate
        except Exception:
            continue

    raise RuntimeError(
        f"Device [{device_index}] supports none of {probe_list}. "
        "Set MIC_DEVICE to a different index in config.py."
    )


# ── Resampling ────────────────────────────────────────────────────────────────

def resample(frames: np.ndarray, from_rate: int, to_rate: int) -> np.ndarray:
    """
    Simple linear-interpolation resample for mono int16 audio.
    Good enough for speech; avoids scipy dependency.
    """
    if from_rate == to_rate:
        return frames
    ratio      = to_rate / from_rate
    old_len    = len(frames)
    new_len    = int(old_len * ratio)
    old_idx    = np.arange(old_len, dtype=np.float64)
    new_idx    = np.linspace(0, old_len - 1, new_len)
    resampled  = np.interp(new_idx, old_idx, frames.flatten())
    return resampled.astype(np.int16).reshape(-1, 1)


# ── WAV writer ────────────────────────────────────────────────────────────────

def save_wav(path: str, frames: np.ndarray, rate: int = SAMPLE_RATE):
    """Write int16 mono frames to a WAV file at the given rate."""
    with wave.open(path, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)          # int16 = 2 bytes
        wf.setframerate(rate)
        wf.writeframes(frames.tobytes())


# ── Recording helper ──────────────────────────────────────────────────────────

def record_seconds(
    duration: float,
    device: int | None,
    native_rate: int,
) -> np.ndarray:
    """
    Record `duration` seconds at native_rate, then resample to SAMPLE_RATE.
    Returns int16 numpy array ready for Whisper.
    """
    raw = sd.rec(
        int(native_rate * duration),
        samplerate=native_rate,
        channels=CHANNELS,
        dtype="int16",
        device=device,
        blocking=True,
    )
    return resample(raw, native_rate, SAMPLE_RATE)
