import unittest

from cc100_subtlex.batches import parse_count_row


class BatchTests(unittest.TestCase):
    def test_parse_count_row_reads_batch_tsv_rows(self):
        self.assertEqual(parse_count_row("fiets\t3\t2\t2\t1\n"), ("fiets", 3, 2, 2, 1))

    def test_parse_count_row_skips_header(self):
        self.assertIsNone(parse_count_row("word\tfreq\tlow_freq\tdoc_freq\tlow_doc_freq\n"))

    def test_parse_count_row_keeps_real_word_token(self):
        self.assertEqual(parse_count_row("word\t221\t200\t210\t194\n"), ("word", 221, 200, 210, 194))


if __name__ == "__main__":
    unittest.main()
