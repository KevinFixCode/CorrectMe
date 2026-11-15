"""Phoneme-level scoring logic (ARPAbet).

Pure logic, no model needed: reference phonemes come from the CMU dictionary, and the
phonemes the learner actually produced come from a phoneme recogniser (planned:
wav2vec2). Substitutions between similar sounds earn partial credit.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Optional, Sequence

_STRESS = re.compile(r"\d")

_CLASSES = {
    "stop": ["P", "B", "T", "D", "K", "G"],
    "fricative": ["F", "V", "TH", "DH", "S", "Z", "SH", "ZH", "HH"],
    "affricate": ["CH", "JH"],
    "nasal": ["M", "N", "NG"],
    "liquid": ["L", "R"],
    "glide": ["W", "Y"],
    "vowel": [
        "AA", "AE", "AH", "AO", "AW", "AY", "EH", "ER",
        "EY", "IH", "IY", "OW", "OY", "UH", "UW",
    ],
}
_CLASS_OF = {p: name for name, members in _CLASSES.items() for p in members}

_NEAR_PAIRS = {
    frozenset(p)
    for p in [
        ("P", "B"), ("T", "D"), ("K", "G"), ("F", "V"), ("TH", "DH"),
        ("S", "Z"), ("SH", "ZH"), ("CH", "JH"),  # voicing pairs
        ("IY", "IH"), ("UW", "UH"), ("EH", "AE"), ("AA", "AO"), ("AH", "AA"),  # close vowels
    ]
}


def similarity(a: str, b: str) -> float:
    """1.0 identical, 0.5 a near pair, 0.3 same sound class, 0.0 unrelated."""
    if a == b:
        return 1.0
    if frozenset((a, b)) in _NEAR_PAIRS:
        return 0.5
    if _CLASS_OF.get(a) is not None and _CLASS_OF.get(a) == _CLASS_OF.get(b):
        return 0.3
    return 0.0


def reference_phonemes(word: str) -> Optional[list]:
    """ARPAbet phonemes of a word (stress marks removed), or None if the word is unknown."""
    import pronouncing  # lazy: only needed here

    phones = pronouncing.phones_for_word(word.lower())
    if not phones:
        return None
    return [_STRESS.sub("", p) for p in phones[0].split()]


def align(ref: Sequence[str], hyp: Sequence[str]) -> list:
    """Edit-distance alignment. Returns (ref_index | None, hyp_index | None) pairs."""
    n, m = len(ref), len(hyp)
    cost = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        cost[i][0] = float(i)
    for j in range(1, m + 1):
        cost[0][j] = float(j)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            sub = cost[i - 1][j - 1] + (1.0 - similarity(ref[i - 1], hyp[j - 1]))
            cost[i][j] = min(sub, cost[i - 1][j] + 1.0, cost[i][j - 1] + 1.0)

    pairs = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and math.isclose(
            cost[i][j],
            cost[i - 1][j - 1] + (1.0 - similarity(ref[i - 1], hyp[j - 1])),
            abs_tol=1e-9,
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


@dataclass
class PhonemeResult:
    expected: str
    heard: Optional[str]
    score: int
    status: str  # ok | close | wrong | missing


@dataclass
class WordPhonemes:
    score: int
    phonemes: list = field(default_factory=list)  # list[PhonemeResult]
    extra: list = field(default_factory=list)  # phonemes heard that were not expected


def score_phonemes(expected: Sequence[str], heard: Sequence[str]) -> WordPhonemes:
    """Score the phonemes a learner produced against the expected ones for one word."""
    if not expected:
        raise ValueError("expected phonemes are empty")
    results, extra = [], []
    for i, j in align(expected, heard):
        if i is None:
            extra.append(heard[j])
        elif j is None:
            results.append(PhonemeResult(expected[i], None, 0, "missing"))
        else:
            sim = similarity(expected[i], heard[j])
            status = "ok" if sim >= 0.999 else "close" if sim >= 0.5 else "wrong"
            results.append(PhonemeResult(expected[i], heard[j], round(sim * 100), status))
    score = round(sum(r.score for r in results) / len(results))
    return WordPhonemes(score=score, phonemes=results, extra=extra)
