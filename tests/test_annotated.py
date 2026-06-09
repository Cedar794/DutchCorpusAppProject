import unittest

from cc100_subtlex.annotated import (
    ANNOTATED_BATCH_HEADER,
    DOC_SENTINEL,
    AnnotatedCounter,
    iter_subtlex_rows,
    iter_annotated_count_rows,
    parse_annotated_count_row,
)
from cc100_subtlex.frog import FrogToken


def token(word, lemma, pos):
    return FrogToken(
        index=1,
        word=word,
        lemma=lemma,
        morphology="[]",
        pos=pos,
        confidence=1.0,
        ner=None,
        chunk=None,
        parse_index=None,
        parse_role=None,
    )


class AnnotatedTests(unittest.TestCase):
    def test_annotated_counter_uses_sentinel_as_document_boundary(self):
        counter = AnnotatedCounter()
        counter.add_token(token("Ik", "ik", "VNW(pers,pron)"))
        counter.add_token(token("fiets", "fiets", "N(soort,ev)"))
        counter.add_token(token(DOC_SENTINEL, DOC_SENTINEL, "N(soort,ev)"))
        counter.add_token(token("ik", "ik", "VNW(pers,pron)"))
        counter.add_token(token("fiets", "fietsen", "WW(pv,tgw,ev)"))
        counter.add_token(token(".", ".", "LET()"))
        counter.add_token(token(DOC_SENTINEL, DOC_SENTINEL, "N(soort,ev)"))

        self.assertEqual(counter.total_documents, 2)
        self.assertEqual(counter.total_tokens, 4)
        self.assertEqual(counter.word_freq["ik"], 2)
        self.assertEqual(counter.word_low_freq["ik"], 1)
        self.assertEqual(counter.word_doc_freq["ik"], 2)
        self.assertEqual(counter.word_low_doc_freq["ik"], 1)
        self.assertEqual(counter.word_pos_freq[("fiets", "N")], 1)
        self.assertEqual(counter.word_pos_freq[("fiets", "WW")], 1)
        self.assertEqual(counter.pos_lemma_freq[("N", "fiets")], 1)
        self.assertEqual(counter.pos_lemma_freq[("WW", "fietsen")], 1)

    def test_iter_subtlex_rows_derives_pos_and_lemma_fields(self):
        counter = AnnotatedCounter()
        for item in [
            token("fiets", "fiets", "N(soort,ev)"),
            token("fiets", "fiets", "N(soort,ev)"),
            token(DOC_SENTINEL, DOC_SENTINEL, "N(soort,ev)"),
            token("fiets", "fietsen", "WW(pv,tgw,ev)"),
            token(DOC_SENTINEL, DOC_SENTINEL, "N(soort,ev)"),
        ]:
            counter.add_token(item)

        row = next(row for row in iter_subtlex_rows(counter) if row["Word"] == "fiets")
        self.assertEqual(row["FREQcount"], 3)
        self.assertEqual(row["CDcount"], 2)
        self.assertEqual(row["dominant.pos"], "N")
        self.assertEqual(row["dominant.pos.freq"], 2)
        self.assertEqual(row["dominant.pos.lemma"], "fiets")
        self.assertEqual(row["dominant.pos.lemma.freq"], 2)
        self.assertEqual(row["all.pos"], ".N.WW.")
        self.assertEqual(row["all.pos.freq"], ".2.1.")
        self.assertEqual(row["all.pos.lemma.freq"], ".2.1.")
        self.assertEqual(row["FREQlemma"], 3)

    def test_annotated_batch_rows_round_trip_all_count_families(self):
        counter = AnnotatedCounter()
        for item in [
            token("Fiets", "fiets", "N(soort,ev)"),
            token("fiets", "fietsen", "WW(pv,tgw,ev)"),
            token(DOC_SENTINEL, DOC_SENTINEL, "N(soort,ev)"),
        ]:
            counter.add_token(item)

        rows = list(iter_annotated_count_rows(counter))
        parsed = [parse_annotated_count_row("\t".join(map(str, row)) + "\n") for row in rows]

        self.assertIsNone(parse_annotated_count_row(ANNOTATED_BATCH_HEADER + "\n"))
        self.assertEqual(parsed, rows)
        self.assertIn(("word", "fiets", "", "", 2, 1, 1, 1), rows)
        self.assertIn(("word_pos", "fiets", "N", "", 1, 0, 0, 0), rows)
        self.assertIn(("word_pos_lemma", "fiets", "WW", "fietsen", 1, 0, 0, 0), rows)
        self.assertIn(("pos_lemma", "", "WW", "fietsen", 1, 0, 0, 0), rows)


if __name__ == "__main__":
    unittest.main()
