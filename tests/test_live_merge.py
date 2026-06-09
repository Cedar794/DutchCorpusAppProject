from __future__ import annotations

import gzip
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from cc100_subtlex.annotated import ANNOTATED_BATCH_HEADER, DOC_SENTINEL, AnnotatedCounter, iter_annotated_count_rows
from cc100_subtlex.frog import FrogToken


RUN_SCRIPT = ROOT / "scripts" / "run_annotated_batches.py"
MERGE_SCRIPT = ROOT / "scripts" / "merge_annotated_batches.py"


def load_script(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def token(word: str, lemma: str, pos: str) -> FrogToken:
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


def write_shard(path: Path) -> AnnotatedCounter:
    counter = AnnotatedCounter()
    for item in [
        token("Fiets", "fiets", "N(soort,ev)"),
        token("fiets", "fietsen", "WW(pv,tgw,ev)"),
        token(DOC_SENTINEL, DOC_SENTINEL, "N(soort,ev)"),
    ]:
        counter.add_token(item)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        handle.write(ANNOTATED_BATCH_HEADER + "\n")
        for row in iter_annotated_count_rows(counter):
            handle.write("\t".join(map(str, row)) + "\n")
    return counter


class LiveMergeTests(unittest.TestCase):
    def test_live_merge_deletes_shard_and_is_idempotent(self):
        run_script = load_script(RUN_SCRIPT, "run_annotated_batches_live_test")
        merge_script = load_script(MERGE_SCRIPT, "merge_annotated_batches_live_test")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            shard_path = tmp / "batch-000000.tsv.gz"
            counter = write_shard(shard_path)
            conn = run_script.open_live_merge_db(tmp / "merged_annotated_counts.sqlite")
            meta = {
                "batch_index": 0,
                "counts_path": str(shard_path),
                "input_lines": 1,
                "total_documents": counter.total_documents,
                "total_tokens": counter.total_tokens,
            }

            first = run_script.merge_completed_batch(conn, meta, chunk_size=2, delete_counts=True)
            second = run_script.merge_completed_batch(conn, meta, chunk_size=2, delete_counts=True)

            self.assertTrue(first["merged"])
            self.assertFalse(second["merged"])
            self.assertTrue(run_script.is_live_batch_merged(conn, 0))
            self.assertFalse(shard_path.exists())

            merge_script.prepare_export_indexes(conn)
            output_path = tmp / "merged.tsv"
            exported = merge_script.export_tsv(conn, output_path, counter.total_tokens, counter.total_documents, top=0)
            conn.close()

            self.assertEqual(exported, 1)
            lines = output_path.read_text(encoding="utf-8").splitlines()
            values = dict(zip(merge_script.HEADERS, lines[1].split("\t")))
            self.assertEqual(values["Word"], "fiets")
            self.assertEqual(values["FREQcount"], "2")

    def test_live_merge_keeps_running_when_shard_delete_is_denied(self):
        run_script = load_script(RUN_SCRIPT, "run_annotated_batches_live_delete_denied_test")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            shard_path = tmp / "batch-000000.tsv.gz"
            counter = write_shard(shard_path)
            conn = run_script.open_live_merge_db(tmp / "merged_annotated_counts.sqlite")
            meta = {
                "batch_index": 0,
                "counts_path": str(shard_path),
                "input_lines": 1,
                "total_documents": counter.total_documents,
                "total_tokens": counter.total_tokens,
            }

            with patch.object(Path, "unlink", side_effect=PermissionError("denied")):
                result = run_script.merge_completed_batch(conn, meta, chunk_size=2, delete_counts=True)

            self.assertTrue(result["merged"])
            self.assertFalse(result["counts_deleted"])
            self.assertIn("denied", result["counts_delete_error"])
            self.assertTrue(run_script.is_live_batch_merged(conn, 0))
            self.assertEqual(conn.execute("SELECT SUM(freq) FROM word_counts").fetchone()[0], 2)
            conn.close()

    def test_manifest_write_retries_after_permission_error(self):
        run_script = load_script(RUN_SCRIPT, "run_annotated_batches_manifest_retry_test")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            manifest = {"_started_perf": 0.0, "batches": []}
            results = {
                0: {
                    "batch_index": 0,
                    "input_lines": 1,
                    "total_documents": 1,
                    "total_tokens": 2,
                    "uncompressed_bytes_approx": 10,
                }
            }
            original_write_text = Path.write_text
            calls = {"count": 0}

            def flaky_write_text(path, *args, **kwargs):
                calls["count"] += 1
                if calls["count"] == 1:
                    raise PermissionError("transient denied")
                return original_write_text(path, *args, **kwargs)

            with patch.object(Path, "write_text", flaky_write_text):
                run_script.write_manifest(tmp, manifest, results)

            written = json.loads((tmp / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(written["total_tokens"], 2)
            self.assertEqual(calls["count"], 2)

    def test_merge_batch_file_can_defer_chunk_commits(self):
        merge_script = load_script(MERGE_SCRIPT, "merge_annotated_batches_deferred_commit_test")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            shard_path = tmp / "batch-000000.tsv.gz"
            write_shard(shard_path)
            conn = merge_script.connect(tmp / "merged_annotated_counts.sqlite")

            merge_script.merge_batch_file(conn, shard_path, chunk_size=1, commit_chunks=False)
            conn.rollback()

            self.assertIsNone(conn.execute("SELECT SUM(freq) FROM word_counts").fetchone()[0])
            conn.close()

    def test_merge_script_can_export_from_existing_live_db(self):
        run_script = load_script(RUN_SCRIPT, "run_annotated_batches_live_export_test")
        merge_script = load_script(MERGE_SCRIPT, "merge_annotated_batches_live_export_test")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            run_name = "live_run"
            run_dir = tmp / run_name
            run_dir.mkdir()
            shard_path = run_dir / "batch-000000.tsv.gz"
            counter = write_shard(shard_path)
            conn = run_script.open_live_merge_db(run_dir / "merged_annotated_counts.sqlite")
            run_script.merge_completed_batch(
                conn,
                {
                    "batch_index": 0,
                    "counts_path": str(shard_path),
                    "input_lines": 1,
                    "total_documents": counter.total_documents,
                    "total_tokens": counter.total_tokens,
                },
                chunk_size=2,
                delete_counts=True,
            )
            conn.close()
            (run_dir / "manifest.json").write_text(
                '{"run_name":"live_run","total_tokens":2,"total_token_documents":1,"batches":[]}\n',
                encoding="utf-8",
            )

            original_output_root = merge_script.OUTPUT_ROOT
            original_argv = sys.argv[:]
            try:
                merge_script.OUTPUT_ROOT = tmp
                sys.argv = [
                    "merge_annotated_batches.py",
                    "--run-name",
                    run_name,
                    "--use-existing-db",
                    "--top",
                    "1",
                ]
                merge_script.main()
            finally:
                merge_script.OUTPUT_ROOT = original_output_root
                sys.argv = original_argv

            self.assertTrue((run_dir / "merged_annotated_counts_top.tsv").exists())
            self.assertFalse(shard_path.exists())


if __name__ == "__main__":
    unittest.main()
