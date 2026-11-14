"""Speech-to-text with faster-whisper (runs locally, no API key needed)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .pronunciation import HeardWord


@dataclass
class Transcript:
    text: str
    words: list = field(default_factory=list)  # list[HeardWord]


class Transcriber:
    """Lazy wrapper around faster-whisper. The model loads on first use."""

    def __init__(self, model: str = "small", device: str = "auto", compute_type: str = "int8"):
        self.model_name = model
        self.device = device
        self.compute_type = compute_type
        self._model = None

    def _load(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:  # pragma: no cover - depends on the environment
                raise ImportError(
                    "faster-whisper is not installed. Run: pip install -r requirements.txt"
                ) from exc
            self._model = WhisperModel(
                self.model_name, device=self.device, compute_type=self.compute_type
            )
        return self._model

    def transcribe(self, audio_path, language: str = "en") -> Transcript:
        """Transcribe an audio file and return text plus per-word confidence.

        Note: we deliberately do NOT pass the expected sentence as `initial_prompt`.
        That would bias Whisper toward the target text and make pronunciation
        scoring far too forgiving.
        """
        path = Path(audio_path)
        if not path.is_file():
            raise FileNotFoundError(f"Audio file not found: {path}")

        model = self._load()
        segments, _info = model.transcribe(
            str(path),
            language=language,
            word_timestamps=True,
            vad_filter=True,
            beam_size=5,
            condition_on_previous_text=False,
        )

        parts: list[str] = []
        words: list[HeardWord] = []
        for segment in segments:
            parts.append(segment.text.strip())
            for w in segment.words or []:
                words.append(HeardWord(word=w.word.strip(), probability=float(w.probability)))
        return Transcript(text=" ".join(p for p in parts if p).strip(), words=words)
