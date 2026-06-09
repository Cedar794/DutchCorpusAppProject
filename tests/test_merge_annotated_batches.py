import gzip
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from cc100_subtlex.annotated import ANNOTATED_BATCH_HEADER, DOC_SENTINEL, AnnotatedCounter, iter_annotated_count_rows
from cc100_subtlex.frog import FrogToken
from merge_annotated_batches import HEADERS, connect, export_tsv, merge_batch_file, prepare_export_indexes


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


class MergeAnnotatedBatchesTests(unittest.TestCase):
    def test_merge_and_export_subtlex_columns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            counter = AnnotatedCounter()
            for item in [
                token("Fiets", "fiets", "N(soort,ev)"),
                token("fiets", "fietsen", "WW(pv,tgw,ev)"),
                token(DOC_SENTINEL, DOC_SENTINEL, "N(soort,ev)"),
            ]:
                counter.add_token(item)

            shard_path = tmp / "batch.tsv.gz"
            with gzip.open(shard_path, "wt", encoding="utf-8", newline="") as handle:
                handle.write(ANNOTATED_BATCH_HEADER + "\n")
                for row in iter_annotated_count_rows(counter):
                    handle.write("\t".join(map(str, row)) + "\n")

            conn = connect(tmp / "counts.sqlite")
            kind_counts = merge_batch_file(conn, shard_path, chunk_size=2)
            prepare_export_indexes(conn)
            output_path = tmp / "merged.tsv"
            exported = export_tsv(conn, output_path, counter.total_tokens, counter.total_documents, top=0)
            conn.close()

            self.assertEqual(kind_counts["word"], 1)
            self.assertEqual(kind_counts["word_pos"], 2)
            self.assertEqual(exported, 1)

            lines = output_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines[0].split("\t"), HEADERS)
            values = dict(zip(HEADERS, lines[1].split("\t")))
            self.assertEqual(values["Word"], "fiets")
            self.assertEqual(values["FREQcount"], "2")
            self.assertEqual(values["CDcount"], "1")
            self.assertEqual(values["FREQlow"], "1")
            self.assertEqual(values["CDlow"], "1")
            self.assertEqual(values["FREQlemma"], "2")
            self.assertEqual(values["dominant.pos"], "N")
            self.assertEqual(values["dominant.pos.lemma"], "fiets")
            self.assertEqual(values["all.pos"], ".N.WW.")
            self.assertEqual(values["all.pos.freq"], ".1.1.")
            self.assertEqual(values["all.pos.lemma.freq"], ".1.1.")


if __name__ == "__main__":
    unittest.main()
