import unittest
from datetime import date, timedelta

from core.vocab import VocabDeck

D = date(2026, 11, 14)


class VocabDeckTests(unittest.TestCase):
    def setUp(self):
        self.deck = VocabDeck(":memory:")

    def tearDown(self):
        self.deck.close()

    def test_add_is_case_insensitive_and_deduplicated(self):
        self.assertTrue(self.deck.add("Meticulous", "teliti", today=D))
        self.assertFalse(self.deck.add("meticulous", "teliti", today=D))
        self.assertEqual(self.deck.count(), 1)

    def test_new_word_is_due_immediately(self):
        self.deck.add("ubiquitous", "ada di mana-mana", today=D)
        self.assertEqual([c.word for c in self.deck.due(today=D)], ["ubiquitous"])

    def test_sm2_intervals_grow(self):
        self.deck.add("candid", today=D)
        first = self.deck.review("candid", 4, today=D)
        self.assertEqual((first.interval_days, first.repetitions), (1, 1))
        self.assertEqual(first.due, D + timedelta(days=1))

        second = self.deck.review("candid", 4, today=first.due)
        self.assertEqual(second.interval_days, 6)

        third = self.deck.review("candid", 4, today=second.due)
        self.assertEqual(third.interval_days, 15)  # round(6 * 2.5)

    def test_forgetting_resets_progress(self):
        self.deck.add("candid", today=D)
        self.deck.review("candid", 5, today=D)
        card = self.deck.review("candid", 1, today=D + timedelta(days=1))
        self.assertEqual((card.repetitions, card.interval_days), (0, 1))

    def test_ease_never_below_floor(self):
        self.deck.add("candid", today=D)
        card = None
        for _ in range(20):
            card = self.deck.review("candid", 0, today=D)
        self.assertGreaterEqual(card.ease, 1.3)

    def test_not_due_yet_is_hidden(self):
        self.deck.add("candid", today=D)
        self.deck.review("candid", 4, today=D)
        self.assertEqual(self.deck.due(today=D), [])

    def test_invalid_quality_and_unknown_word(self):
        self.deck.add("candid", today=D)
        with self.assertRaises(ValueError):
            self.deck.review("candid", 9)
        with self.assertRaises(KeyError):
            self.deck.review("missing", 3)


if __name__ == "__main__":
    unittest.main()
