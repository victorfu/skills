import unittest

from pricing import split_cents


class SplitCentsTests(unittest.TestCase):
    def test_even_split(self):
        self.assertEqual(split_cents(900, 3), [300, 300, 300])

    def test_leftover_cents_go_to_the_earliest_shares(self):
        self.assertEqual(split_cents(100, 3), [34, 33, 33])
        self.assertEqual(sum(split_cents(1000, 3)), 1000)


if __name__ == '__main__':
    unittest.main()
