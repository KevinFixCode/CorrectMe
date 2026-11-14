"""Microphone recording helper (push-to-talk with the Enter key)."""

from __future__ import annotations

import wave
from pathlib import Path

SAMPLE_RATE = 16_000  # Whisper's native rate


def record_until_enter(path, prompt: str = "Press Enter to START recording") -> Path:
    """Record mono 16 kHz audio from the default microphone to a WAV file.

    The user presses Enter to start and Enter again to stop.
    """
    try:
        import numpy as np
        import sounddevice as sd
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ImportError(
            "Microphone recording needs numpy and sounddevice. "
            "Run: pip install -r requirements.txt "
            "(on Linux you may also need: sudo apt install libportaudio2)"
        ) from exc

    out = Path(path)
    chunks = []

    def on_audio(indata, _frames, _time, _status):
        chunks.append(indata.copy())

    input(f"  {prompt} ")
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", callback=on_audio):
        input("  Recording... press Enter to STOP ")

    if not chunks:
        raise RuntimeError("No audio was captured. Check your microphone.")

    audio = np.concatenate(chunks)
    with wave.open(str(out), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)  # int16
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(audio.tobytes())
    return out
