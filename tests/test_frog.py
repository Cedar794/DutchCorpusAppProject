import unittest

from cc100_subtlex.frog import parse_frog_line, pos_head


class FrogTests(unittest.TestCase):
    def test_pos_head_strips_cgn_features(self):
        self.assertEqual(pos_head("WW(pv,tgw,ev)"), "WW")
        self.assertEqual(pos_head("N(soort,ev,basis,zijd,stan)"), "N")
        self.assertEqual(pos_head("SPEC(deeleigen)"), "SPEC")

    def test_parse_frog_line_reads_column_output(self):
        line = "3\twerd\tworden\t[word]\tWW(pv,verl,ev)\t0.999799\tO\tB-VP\t0\tROOT"
        parsed = parse_frog_line(line)

        self.assertEqual(parsed.index, 3)
        self.assertEqual(parsed.word, "werd")
        self.assertEqual(parsed.lemma, "worden")
        self.assertEqual(parsed.pos, "WW(pv,verl,ev)")
        self.assertEqual(parsed.pos_head, "WW")

    def test_parse_frog_line_returns_none_for_sentence_separator(self):
        self.assertIsNone(parse_frog_line(""))


if __name__ == "__main__":
    unittest.main()
