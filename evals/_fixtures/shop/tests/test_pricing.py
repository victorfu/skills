import unittest

from pricing import split_cents


class SplitCentsTests(unittest.TestCase):
    def test_even_split(self):
        self.assertEqual(split_cents(900, 3), [300, 300, 300])


if __name__ == '__main__':
    unittest.main()
