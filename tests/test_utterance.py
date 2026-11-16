import unittest

from core.phonemes import score_utterance

DICT = {
    "think": ["TH", "IH", "NG", "K"],
    "so": ["S", "OW"],
}


class UtteranceTests(unittest.TestCase):
    def test_perfect(self):
        r = score_utterance("Think so", ["TH", "IH", "NG", "K", "S", "OW"], lookup=DICT.get)
        self.assertEqual(r.overall, 100)
        self.assertEqual([w.score for w in r.words], [100, 100])

    def test_th_to_t_only_hurts_that_word(self):
        r = score_utterance("think so", ["T", "IH", "NG", "K", "S", "OW"], lookup=DICT.get)
        self.assertEqual([w.score for w in r.words], [60, 100])
        self.assertEqual(r.words[0].phonemes[0].status, "wrong")
        self.assertEqual(r.overall, 70)

    def test_dropped_final_sound_belongs_to_the_right_word(self):
        r = score_utterance("think so", ["TH", "IH", "NG", "K", "S"], lookup=DICT.get)
        self.assertEqual([w.score for w in r.words], [100, 35])
        self.assertEqual(r.words[1].phonemes[-1].status, "missing")

    def test_unknown_words_are_skipped(self):
        r = score_utterance("think xyzzy so", ["TH", "IH", "NG", "K", "S", "OW"], lookup=DICT.get)
        self.assertIsNone(r.words[1].score)
        self.assertEqual(r.overall, 100)

    def test_extra_sounds_are_reported(self):
        r = score_utterance("think so", ["TH", "IH", "NG", "K", "S", "OW", "T"], lookup=DICT.get)
        self.assertEqual(r.overall, 100)
        self.assertEqual(r.extra, ["T"])

    def test_nothing_known_is_an_error(self):
        with self.assertRaises(ValueError):
            score_utterance("xyzzy", ["T"], lookup=DICT.get)

    def test_empty_reference_is_an_error(self):
        with self.assertRaises(ValueError):
            score_utterance("...", ["T"], lookup=DICT.get)


if __name__ == "__main__":
    unittest.main()
