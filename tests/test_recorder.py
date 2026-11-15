import unittest

from core.recorder import parse_device


class ParseDeviceTests(unittest.TestCase):
    def test_none_and_blank(self):
        self.assertIsNone(parse_device(None))
        self.assertIsNone(parse_device("  "))

    def test_index(self):
        self.assertEqual(parse_device("24"), 24)

    def test_name_fragment(self):
        self.assertEqual(parse_device("Realtek"), "Realtek")


if __name__ == "__main__":
    unittest.main()
