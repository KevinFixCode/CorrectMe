"""Pronunciation scoring based on intelligibility.

How it works: the learner reads a known sentence aloud, the audio is transcribed by
Whisper, and the transcript is aligned word-by-word against the sentence they were
supposed to read. A word is "good" when Whisper heard it correctly *and* confidently.

Limits (be honest with users): this measures whether a listener (Whisper) understands
each word, not phoneme-level accuracy. Whisper is also fairly forgiving of accents.
Phoneme-level scoring (wav2vec2 + goodness-of-pronunciation) is a planned upgrade.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional, Sequence, Union

_WORD_RE = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)*")

CLOSE_THRESHOLD = 0.6  # similarity at/above this counts as "close", below as "wrong"
WEAK_THRESHOLD = 70  # words scoring under this are flagged for practice
FAIL_PENALTY = 10  # points off the overall score per wrong or missing word


@dataclass(frozen=True)
class HeardWord:
    """One word returned by speech-to-text, with Whisper's confidence (0-1) if known."""

    word: str
    probability: Optional[float] = None


@dataclass
class WordResult:
    reference: str
    heard: Optional[str]
    score: int
    status: str  # correct | close | wrong | missing


@dataclass
class PronunciationResult:
    overall: int
    words: list = field(default_factory=list)  # list[WordResult]
    extra: list = field(default_factory=list)  # words heard that were not in the reference

    def weak_words(self, threshold: int = WEAK_THRESHOLD) -> list:
        return [w for w in self.words if w.score < threshold]


def tokenize(text: str) -> list:
    """Lowercase and split into words, ignoring punctuation (apostrophes are kept)."""
    text = text.lower().replace("’", "'").replace("‘", "'")
    return _WORD_RE.findall(text)


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _heard_tokens(heard: Union[str, Sequence[HeardWord]]):
    tokens, probs = [], []
    if isinstance(heard, str):
        for token in tokenize(heard):
            tokens.append(token)
            probs.append(None)
    else:
        for item in heard:
            for token in tokenize(item.word):
                tokens.append(token)
                probs.append(item.probability)
    return tokens, probs


def _align(ref: list, hyp: list) -> list:
    """Edit-distance alignment. Returns (ref_index | None, hyp_index | None) pairs."""
    n, m = len(ref), len(hyp)
    cost = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        cost[i][0] = float(i)
    for j in range(1, m + 1):
        cost[0][j] = float(j)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            sub = cost[i - 1][j - 1] + (1.0 - _similarity(ref[i - 1], hyp[j - 1]))
            cost[i][j] = min(sub, cost[i - 1][j] + 1.0, cost[i][j - 1] + 1.0)

    pairs = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and math.isclose(
            cost[i][j], cost[i - 1][j - 1] + (1.0 - _similarity(ref[i - 1], hyp[j - 1])), abs_tol=1e-9
        ):
            pairs.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif i > 0 and math.isclose(cost[i][j], cost[i - 1][j] + 1.0, abs_tol=1e-9):
            pairs.append((i - 1, None))
            i -= 1
        else:
            pairs.append((None, j - 1))
            j -= 1
    pairs.reverse()
    return pairs


def _score_pair(similarity: float, probability: Optional[float]):
    if similarity >= 0.999:
        if probability is None:
            return 100, "correct"
        return round(60 + 40 * min(max(probability, 0.0), 1.0)), "correct"
    if similarity >= CLOSE_THRESHOLD:
        return round(similarity * 70), "close"
    return round(similarity * 30), "wrong"


def score_pronunciation(reference: str, heard: Union[str, Sequence[HeardWord]]) -> PronunciationResult:
    """Score how well `heard` (the transcript of the learner's audio) matches `reference`.

    `heard` can be a plain string or a list of HeardWord (to use Whisper's per-word confidence).
    """
    ref = tokenize(reference)
    if not ref:
        raise ValueError("reference text has no words")
    hyp, probs = _heard_tokens(heard)

    results, extra = [], []
    for ref_i, hyp_j in _align(ref, hyp):
        if ref_i is None:
            extra.append(hyp[hyp_j])
        elif hyp_j is None:
            results.append(WordResult(ref[ref_i], None, 0, "missing"))
        else:
            sim = _similarity(ref[ref_i], hyp[hyp_j])
            score, status = _score_pair(sim, probs[hyp_j])
            results.append(WordResult(ref[ref_i], hyp[hyp_j], score, status))

    failed = sum(1 for w in results if w.status in ("wrong", "missing"))
    mean = sum(w.score for w in results) / len(results)
    overall = max(0, round(mean - FAIL_PENALTY * failed))
    return PronunciationResult(overall=overall, words=results, extra=extra)
