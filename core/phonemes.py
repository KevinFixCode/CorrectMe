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


# --------------------------------------------------------------------------- whole sentences


PHONEME_FAIL_PENALTY = 15  # points off a word's score per wrong or missing sound
WORD_FAIL_PENALTY = 10  # points off the overall score per word with a failed sound


@dataclass
class WordPhonemeResult:
    word: str
    score: Optional[int]  # None when the word is not in the dictionary
    phonemes: list = field(default_factory=list)  # list[PhonemeResult]


@dataclass
class UtteranceResult:
    overall: int
    words: list = field(default_factory=list)  # list[WordPhonemeResult]
    extra: list = field(default_factory=list)  # phonemes heard that matched nothing


def _grade(sim: float):
    score = round(sim * 100)
    status = "ok" if sim >= 0.999 else "close" if sim >= 0.5 else "wrong"
    return score, status


def score_utterance(reference: str, heard: Sequence[str], lookup=reference_phonemes) -> UtteranceResult:
    """Score a whole sentence: line up every expected phoneme against everything heard,
    then hand each result back to the word it belongs to.

    Words that are not in the pronunciation dictionary are skipped (score None).
    `lookup` maps a word to its expected phonemes (or None); tests pass a fake one.
    """
    from .pronunciation import tokenize

    words = tokenize(reference)
    if not words:
        raise ValueError("reference text has no words")

    expected, owner = [], []
    for index, word in enumerate(words):
        for phone in lookup(word) or []:
            expected.append(phone)
            owner.append(index)
    if not expected:
        raise ValueError("none of the words are in the pronunciation dictionary")

    heard = list(heard)
    per_word = {index: [] for index in range(len(words))}
    extra = []
    for i, j in align(expected, heard):
        if i is None:
            extra.append(heard[j])
        elif j is None:
            per_word[owner[i]].append(PhonemeResult(expected[i], None, 0, "missing"))
        else:
            score, status = _grade(similarity(expected[i], heard[j]))
            per_word[owner[i]].append(PhonemeResult(expected[i], heard[j], score, status))

    results, scored, failed_words = [], [], 0
    for index, word in enumerate(words):
        items = per_word[index]
        if items:
            mean = sum(p.score for p in items) / len(items)
            failures = sum(1 for p in items if p.status in ("wrong", "missing"))
            score = max(0, round(mean - PHONEME_FAIL_PENALTY * failures))
            if failures:
                failed_words += 1
        else:
            score = None
        if score is not None:
            scored.append(score)
        results.append(WordPhonemeResult(word, score, items))
    overall = max(0, round(sum(scored) / len(scored) - WORD_FAIL_PENALTY * failed_words))
    return UtteranceResult(overall=overall, words=results, extra=extra)
