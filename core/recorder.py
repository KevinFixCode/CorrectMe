"""Microphone recording helper (push-to-talk with the Enter key)."""

from __future__ import annotations

import wave
from pathlib import Path

SAMPLE_RATE = 16_000  # Whisper's native rate


def parse_device(value):
    """Turn a CLI value into what sounddevice expects: None, an index, or a name fragment."""
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip()
    return int(text) if text.isdigit() else text


def list_input_devices() -> list:
    """Return (index, name, host_api) for every device that can record."""
    import sounddevice as sd

    apis = sd.query_hostapis()
    return [
        (i, d["name"], apis[d["hostapi"]]["name"])
        for i, d in enumerate(sd.query_devices())
        if d["max_input_channels"] > 0
    ]


def record_until_enter(path, prompt: str = "Press Enter to START recording", device=None) -> Path:
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
    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="int16", device=device, callback=on_audio
        ):
            input("  Recording... press Enter to STOP ")
    except (sd.PortAudioError, ValueError) as exc:
        raise RuntimeError(
            f"Could not open the microphone: {exc}. Run `python main.py devices` to list inputs."
        ) from exc

    if not chunks:
        raise RuntimeError("No audio was captured. Check your microphone.")

    audio = np.concatenate(chunks)
    with wave.open(str(out), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)  # int16
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(audio.tobytes())
    return out
