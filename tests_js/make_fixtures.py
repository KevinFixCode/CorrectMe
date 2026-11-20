"""Regenerate tests_js/fixtures.json from the Python scoring.

Run from the repo root after changing core/pronunciation.py:

    python tests_js/make_fixtures.py

Then make docs/lib.js give the same numbers (node --test "tests_js/*.test.js").
"""
import json
import pathlib
import sys
from difflib import SequenceMatcher

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from core.pronunciation import HeardWord, score_pronunciation  # noqa: E402

CASES = [
    ("I would be delighted to join you.", "i would be delighted to join you"),
    ("this is truly remarkable", "this is remarkable"),
    ("a thorough analysis", "a through analysis"),
    ("we met yesterday", "we met banana"),
    ("good morning", "well good morning everyone"),
    ("good morning", ""),
    ("It was the sheer elegance of the mathematical models that had drawn me to this discipline",
     "it was the sheer elegance of the mathematical model that drawn me to the discipline"),
    ("Seldom have I encountered such an intriguing proposition; do elaborate.",
     "seldom have i encountered such an interesting proposition do a elaborate"),
    ("I think so, and she thinks so too.", "i sink so and she thinks so two"),
    ("Rural areas particularly worry me", "rule areas particular worry me"),
    ("don't you think it's fascinating", "dont you think its fascinating"),
    ("fascinated interdisciplinary culminated", "fascinate it inter disciplinary culminated"),
]
PROB_CASES = [
    ("good morning everyone", [("good", 1.0), ("morning", 0.4), ("everyone", 0.0)]),
    ("she sells sea shells", [("she", 0.95), ("sells", 0.5), ("sea", 0.77), ("shells", 0.123)]),
    ("hello world", [("Hello,", 0.5), ("world.", 0.25)]),
]
WORDS = ["thorough", "through", "think", "sink", "rural", "rule", "fascinated", "fascinate", "a", "", "ab",
         "abcabc", "bcabca", "interdisciplinary", "inter", "night", "knight", "elaborate", "elaborated"]


def dump(r):
    return {
        "overall": r.overall,
        "words": [{"reference": w.reference, "heard": w.heard, "score": w.score, "status": w.status} for w in r.words],
        "extra": r.extra,
    }


out = {"pairs": [[a, b, SequenceMatcher(None, a, b).ratio()] for a in WORDS for b in WORDS], "cases": []}
for ref, heard in CASES:
    out["cases"].append({"reference": ref, "heard": heard, "expected": dump(score_pronunciation(ref, heard))})
for ref, hw in PROB_CASES:
    heard = [HeardWord(w, p) for w, p in hw]
    out["cases"].append({
        "reference": ref,
        "heard": [{"word": w, "probability": p} for w, p in hw],
        "expected": dump(score_pronunciation(ref, heard)),
    })
target = pathlib.Path(__file__).with_name("fixtures.json")
target.write_text(json.dumps(out, indent=1), encoding="utf-8")
print(f"wrote {target.name}: {len(out['pairs'])} pairs, {len(out['cases'])} cases")
