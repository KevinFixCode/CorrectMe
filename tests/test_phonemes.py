import importlib.util
import unittest

from core.phonemes import reference_phonemes, score_phonemes, similarity

HAS_PRONOUNCING = importlib.util.find_spec("pronouncing") is not None


class SimilarityTests(unittest.TestCase):
    def test_levels(self):
        self.assertEqual(similarity("TH", "TH"), 1.0)
        self.assertEqual(similarity("B", "P"), 0.5)
        self.assertEqual(similarity("IY", "IH"), 0.5)
        self.assertEqual(similarity("S", "SH"), 0.3)
        self.assertEqual(similarity("TH", "T"), 0.0)


class ScorePhonemeTests(unittest.TestCase):
    def test_perfect(self):
        r = score_phonemes(["TH", "IH", "NG", "K"], ["TH", "IH", "NG", "K"])
        self.assertEqual(r.score, 100)
        self.assertTrue(all(p.status == "ok" for p in r.phonemes))

    def test_th_replaced_by_t_is_wrong(self):
        r = score_phonemes(["TH", "IH", "NG", "K"], ["T", "IH", "NG", "K"])
        self.assertEqual(r.phonemes[0].status, "wrong")
        self.assertEqual(r.score, 75)

    def test_voicing_confusion_is_close(self):
        r = score_phonemes(["B", "AE", "T"], ["P", "AE", "T"])
        self.assertEqual(r.phonemes[0].status, "close")
        self.assertEqual(r.phonemes[0].score, 50)

    def test_dropped_phoneme_is_missing(self):
        r = score_phonemes(["S", "T", "R", "IY", "T"], ["T", "R", "IY", "T"])
        self.assertEqual(r.phonemes[0].status, "missing")
        self.assertEqual(r.phonemes[0].expected, "S")

    def test_extra_phoneme_is_reported_not_penalised(self):
        r = score_phonemes(["HH", "AY"], ["HH", "AY", "T"])
        self.assertEqual(r.score, 100)
        self.assertEqual(r.extra, ["T"])

    def test_empty_expected_rejected(self):
        with self.assertRaises(ValueError):
            score_phonemes([], ["T"])


@unittest.skipUnless(HAS_PRONOUNCING, "pronouncing is not installed")
class ReferenceTests(unittest.TestCase):
    def test_known_word(self):
        self.assertEqual(reference_phonemes("think"), ["TH", "IH", "NG", "K"])

    def test_unknown_word(self):
        self.assertIsNone(reference_phonemes("zzzxq"))


if __name__ == "__main__":
    unittest.main()
