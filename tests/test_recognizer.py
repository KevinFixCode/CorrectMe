import unittest

from core.recognizer import ipa_to_arpabet, phonemes_from_raw


class IpaMappingTests(unittest.TestCase):
    def test_th_and_ng(self):
        self.assertEqual(ipa_to_arpabet("θɪŋk"), ["TH", "IH", "NG", "K"])

    def test_stress_and_length_marks_are_ignored(self):
        self.assertEqual(ipa_to_arpabet("ˈɑː"), ["AA"])

    def test_two_character_units(self):
        self.assertEqual(ipa_to_arpabet("tʃ"), ["CH"])
        self.assertEqual(ipa_to_arpabet("oʊ"), ["OW"])
        self.assertEqual(ipa_to_arpabet("aɪ"), ["AY"])

    def test_unknown_symbols_are_skipped(self):
        self.assertEqual(ipa_to_arpabet("?!"), [])

    def test_raw_output_is_split_on_spaces(self):
        self.assertEqual(phonemes_from_raw("ð ə k æ t"), ["DH", "AH", "K", "AE", "T"])


if __name__ == "__main__":
    unittest.main()
