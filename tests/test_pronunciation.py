import unittest

from core.pronunciation import HeardWord, score_pronunciation, tokenize


class TokenizeTests(unittest.TestCase):
    def test_ignores_case_and_punctuation(self):
        self.assertEqual(tokenize("Hello, World! It's fine."), ["hello", "world", "it's", "fine"])

    def test_curly_apostrophe(self):
        self.assertEqual(tokenize("don’t"), ["don't"])


class ScoreTests(unittest.TestCase):
    def test_perfect_match(self):
        result = score_pronunciation("I would be delighted to join you.", "i would be delighted to join you")
        self.assertEqual(result.overall, 100)
        self.assertTrue(all(w.status == "correct" for w in result.words))
        self.assertEqual(result.extra, [])
        self.assertEqual(result.weak_words(), [])

    def test_missing_word(self):
        result = score_pronunciation("this is truly remarkable", "this is remarkable")
        missing = [w for w in result.words if w.status == "missing"]
        self.assertEqual([w.reference for w in missing], ["truly"])
        self.assertEqual(missing[0].score, 0)
        self.assertEqual(result.overall, 65)  # mean 75, minus one failed-word penalty

    def test_close_substitution_is_flagged(self):
        result = score_pronunciation("a thorough analysis", "a through analysis")
        word = next(w for w in result.words if w.reference == "thorough")
        self.assertEqual(word.status, "close")
        self.assertEqual(word.heard, "through")
        self.assertLess(word.score, 70)
        self.assertIn("thorough", [w.reference for w in result.weak_words()])

    def test_completely_wrong_word(self):
        result = score_pronunciation("we met yesterday", "we met banana")
        word = result.words[-1]
        self.assertEqual(word.status, "wrong")
        self.assertLess(word.score, 15)

    def test_extra_words_reported_not_penalised(self):
        result = score_pronunciation("good morning", "well good morning everyone")
        self.assertEqual(result.overall, 100)
        self.assertEqual(result.extra, ["well", "everyone"])

    def test_word_confidence_lowers_score(self):
        heard = [HeardWord("good", 1.0), HeardWord("morning", 0.4)]
        result = score_pronunciation("good morning", heard)
        by_word = {w.reference: w.score for w in result.words}
        self.assertEqual(by_word["good"], 100)
        self.assertEqual(by_word["morning"], 76)
        self.assertEqual(result.overall, 88)

    def test_failed_words_pull_overall_below_the_average(self):
        reference = "I would be delighted to join you for lunch tomorrow"
        heard = "I would be delighted to join you for dinner"
        result = score_pronunciation(reference, heard)
        mean = sum(w.score for w in result.words) / len(result.words)
        failed = [w for w in result.words if w.status in ("wrong", "missing")]
        self.assertEqual(len(failed), 2)
        self.assertLess(result.overall, 65)
        self.assertLess(result.overall, mean)

    def test_nothing_heard(self):
        result = score_pronunciation("good morning", "")
        self.assertEqual(result.overall, 0)
        self.assertTrue(all(w.status == "missing" for w in result.words))

    def test_empty_reference_rejected(self):
        with self.assertRaises(ValueError):
            score_pronunciation("...", "hello")


if __name__ == "__main__":
    unittest.main()
