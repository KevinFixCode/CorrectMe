"""Phoneme recognition with wav2vec2 (espeak IPA output, mapped to ARPAbet).

Needs the optional packages torch and transformers. Nothing else in the app imports
this module unless you ask for phoneme scoring.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

MODEL_ID = "facebook/wav2vec2-lv-60-espeak-cv-ft"
SAMPLE_RATE = 16_000

# Marks that do not change which phoneme it is: stress, length, tie bars, aspiration, palatalisation.
_IGNORED = set("\u02c8\u02cc\u02d0\u02d1\u035c\u0361\u203f\u02b0\u02b2")

# espeak IPA -> ARPAbet. Two-character units are tried first.
_IPA_TO_ARPA = {
    "tʃ": "CH", "dʒ": "JH",
    "aɪ": "AY", "aʊ": "AW", "eɪ": "EY", "oʊ": "OW", "əʊ": "OW", "ɔɪ": "OY",
    "p": "P", "b": "B", "t": "T", "d": "D", "k": "K", "g": "G", "ɡ": "G",
    "f": "F", "v": "V", "θ": "TH", "ð": "DH", "s": "S", "z": "Z",
    "ʃ": "SH", "ʒ": "ZH", "h": "HH", "m": "M", "n": "N", "ŋ": "NG",
    "l": "L", "ɫ": "L", "r": "R", "ɹ": "R", "j": "Y", "w": "W", "ɾ": "D",
    "i": "IY", "ɪ": "IH", "ᵻ": "IH", "ɛ": "EH", "e": "EH", "æ": "AE",
    "ɑ": "AA", "a": "AA", "ɒ": "AA", "ɔ": "AO", "ʌ": "AH", "ɐ": "AH",
    "ə": "AH", "ʊ": "UH", "u": "UW", "ɜ": "ER", "ɚ": "ER", "ɝ": "ER", "o": "OW",
}


def ipa_to_arpabet(token: str) -> list:
    """Convert one IPA token (for example 'θɪŋk') into ARPAbet phonemes."""
    text = unicodedata.normalize("NFD", token)
    text = "".join(ch for ch in text if ch not in _IGNORED and not unicodedata.combining(ch))
    out, i = [], 0
    while i < len(text):
        for size in (2, 1):
            chunk = text[i : i + size]
            if len(chunk) == size and chunk in _IPA_TO_ARPA:
                out.append(_IPA_TO_ARPA[chunk])
                i += size
                break
        else:
            i += 1  # unknown symbol: skip it
    return out


def phonemes_from_raw(raw: str) -> list:
    """Convert the model's space-separated IPA output into a flat ARPAbet list."""
    out = []
    for token in raw.split():
        out.extend(ipa_to_arpabet(token))
    return out


class PhonemeRecognizer:
    """Lazy wrapper: the model (about 1.2 GB) is downloaded and loaded on first use."""

    def __init__(self, model_id: str = MODEL_ID):
        self.model_id = model_id
        self._extractor = None
        self._tokenizer = None
        self._model = None

    def _load(self):
        if self._model is None:
            try:
                from transformers import (
                    Wav2Vec2FeatureExtractor,
                    Wav2Vec2ForCTC,
                    Wav2Vec2PhonemeCTCTokenizer,
                )
            except ImportError as exc:  # pragma: no cover - depends on the environment
                raise ImportError(
                    "Phoneme scoring needs torch and transformers. Run: pip install transformers"
                ) from exc
            self._extractor = Wav2Vec2FeatureExtractor.from_pretrained(self.model_id)
            # do_phonemize=False: we only decode model output, so neither the
            # phonemizer package nor espeak is needed.
            self._tokenizer = Wav2Vec2PhonemeCTCTokenizer.from_pretrained(
                self.model_id, do_phonemize=False
            )
            self._model = Wav2Vec2ForCTC.from_pretrained(self.model_id)
            self._model.eval()
        return self._extractor, self._tokenizer, self._model

    def recognize_raw(self, audio_path) -> str:
        """Return the model's raw phoneme string (IPA, space-separated) for an audio file."""
        path = Path(audio_path)
        if not path.is_file():
            raise FileNotFoundError(f"Audio file not found: {path}")

        extractor, tokenizer, model = self._load()
        import torch
        from faster_whisper.audio import decode_audio

        audio = decode_audio(str(path), sampling_rate=SAMPLE_RATE)
        inputs = extractor(audio, sampling_rate=SAMPLE_RATE, return_tensors="pt")
        with torch.no_grad():
            logits = model(inputs.input_values).logits
        ids = torch.argmax(logits, dim=-1)
        return tokenizer.batch_decode(ids)[0].strip()
