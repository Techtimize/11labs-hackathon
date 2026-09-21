import unittest

from utils.normalise import normalise_ref


class Normalisation(unittest.TestCase):
    def test_arabic_digits_and_spaces(self):
        self.assertEqual(normalise_ref("pa ٢٠٢٦ ٠٠٠١"), "PA-2026-0001")
        self.assertEqual(normalise_ref(" dha–f–0001 "), "DHA-F-0001")
