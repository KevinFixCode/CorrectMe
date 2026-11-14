"""Vocabulary deck with spaced repetition (SM-2), stored in a local SQLite file."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS words (
    word          TEXT PRIMARY KEY,
    meaning       TEXT NOT NULL DEFAULT '',
    example       TEXT NOT NULL DEFAULT '',
    ease          REAL NOT NULL DEFAULT 2.5,
    interval_days INTEGER NOT NULL DEFAULT 0,
    repetitions   INTEGER NOT NULL DEFAULT 0,
    due           TEXT NOT NULL,
    added         TEXT NOT NULL
)
"""


@dataclass
class Card:
    word: str
    meaning: str
    example: str
    ease: float
    interval_days: int
    repetitions: int
    due: date


class VocabDeck:
    def __init__(self, path=":memory:"):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path))
        self._db.execute(_SCHEMA)
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    @staticmethod
    def _key(word: str) -> str:
        return word.strip().lower()

    def add(self, word: str, meaning: str = "", example: str = "", today: Optional[date] = None) -> bool:
        """Add a word. Returns False if it is already in the deck."""
        today = today or date.today()
        key = self._key(word)
        if not key:
            return False
        cur = self._db.execute(
            "INSERT OR IGNORE INTO words (word, meaning, example, due, added) VALUES (?, ?, ?, ?, ?)",
            (key, meaning, example, today.isoformat(), today.isoformat()),
        )
        self._db.commit()
        return cur.rowcount == 1

    def count(self) -> int:
        return self._db.execute("SELECT COUNT(*) FROM words").fetchone()[0]

    def get(self, word: str) -> Optional[Card]:
        row = self._db.execute(
            "SELECT word, meaning, example, ease, interval_days, repetitions, due FROM words WHERE word = ?",
            (self._key(word),),
        ).fetchone()
        return self._card(row) if row else None

    def due(self, today: Optional[date] = None, limit: int = 20) -> list:
        today = today or date.today()
        rows = self._db.execute(
            "SELECT word, meaning, example, ease, interval_days, repetitions, due FROM words "
            "WHERE due <= ? ORDER BY due, word LIMIT ?",
            (today.isoformat(), limit),
        ).fetchall()
        return [self._card(r) for r in rows]

    def review(self, word: str, quality: int, today: Optional[date] = None) -> Card:
        """Record a review. quality: 0 (blackout) .. 5 (perfect). Below 3 counts as forgotten."""
        if not 0 <= quality <= 5:
            raise ValueError("quality must be between 0 and 5")
        card = self.get(word)
        if card is None:
            raise KeyError(f"'{word}' is not in the deck")
        today = today or date.today()

        if quality < 3:
            repetitions, interval = 0, 1
        else:
            if card.repetitions == 0:
                interval = 1
            elif card.repetitions == 1:
                interval = 6
            else:
                interval = round(card.interval_days * card.ease)
            repetitions = card.repetitions + 1
        ease = max(1.3, card.ease + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        due = today + timedelta(days=interval)

        self._db.execute(
            "UPDATE words SET ease = ?, interval_days = ?, repetitions = ?, due = ? WHERE word = ?",
            (ease, interval, repetitions, due.isoformat(), card.word),
        )
        self._db.commit()
        return Card(card.word, card.meaning, card.example, ease, interval, repetitions, due)

    @staticmethod
    def _card(row) -> Card:
        return Card(row[0], row[1], row[2], row[3], row[4], row[5], date.fromisoformat(row[6]))
