from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "qc_report.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("qc_report", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class QcReportTests(unittest.TestCase):
    def test_dot_values(self):
        script = load_script_module()
        self.assertEqual(script.dot_values(".LID.VNW."), ["LID", "VNW"])
        self.assertEqual(script.dot_values(""), [])

    def test_write_qc_report_passes_for_valid_rows(self):
        script = load_script_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            input_path = tmp / "merged.tsv"
            output_path = tmp / "qc.md"
            total_tokens = 100
            total_documents = 10
            freq = 10
            cd = 5
            row = {
                "Word": "de",
                "FREQcount": str(freq),
                "CDcount": str(cd),
                "FREQlow": "9",
                "CDlow": "4",
                "FREQlemma": "10",
                "SUBTLEXWF": f"{freq / total_tokens * 1_000_000:.10f}",
                "Zipf": f"{__import__('math').log10(freq / total_tokens * 1_000_000_000):.10f}",
                "SUBTLEXCD": f"{cd / total_documents * 100:.10f}",
                "Lg10CD": f"{__import__('math').log10(cd):.10f}",
                "dominant.pos": "LID",
                "dominant.pos.freq": "10",
                "dominant.pos.lemma": "de",
                "dominant.pos.lemma.freq": "10",
                "all.pos": ".LID.",
                "all.pos.freq": ".10.",
                "all.pos.lemma.freq": ".10.",
            }
            input_path.write_text(
                "\t".join(script.HEADERS) + "\n" + "\t".join(row[header] for header in script.HEADERS) + "\n",
                encoding="utf-8",
            )
            manifest = {
                "run_name": "test",
                "total_tokens": total_tokens,
                "total_documents": total_documents,
                "elapsed_seconds": 2.0,
                "workers": 1,
                "batch_lines": 1,
                "frog_threads": 1,
                "batches": [{"input_lines": 1}],
            }
            merge_metadata = {
                "total_tokens": total_tokens,
                "total_documents": total_documents,
                "unique_words": 1,
                "exported_rows": 1,
                "elapsed_seconds": 0.1,
            }
            reference_profile = {"headers": script.HEADERS}

            checks = script.write_qc_report(
                input_path,
                output_path,
                manifest,
                merge_metadata,
                reference_profile,
                scan_rows=10,
                projected_total_tokens=1_000,
            )

            self.assertTrue(output_path.exists())
            self.assertTrue(all(passed for _name, passed, _detail in checks), json.dumps(checks))
            report = output_path.read_text(encoding="utf-8")
            self.assertIn("QC Report", report)
            self.assertIn("PASS", report)


if __name__ == "__main__":
    unittest.main()
