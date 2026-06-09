from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

import openpyxl


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "export_top_xlsx.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("export_top_xlsx", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ExportTopXlsxTests(unittest.TestCase):
    def test_export_top_rows_with_expected_headers_and_types(self):
        script = load_script_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            input_path = tmp / "merged.tsv"
            output_path = tmp / "top.xlsx"
            input_path.write_text(
                "\t".join(script.HEADERS)
                + "\n"
                + "de\t10\t5\t9\t4\t10\t100.0\t8.0\t50.0\t0.6989700043\tLID\t10\tde\t10\t.LID.\t.10.\t.10.\n"
                + "en\t8\t4\t8\t4\t8\t80.0\t7.9\t40.0\t0.6020599913\tVG\t8\ten\t8\t.VG.\t.8.\t.8.\n",
                encoding="utf-8",
            )

            row_count = script.export_xlsx(input_path, output_path, top=1)

            self.assertEqual(row_count, 1)
            workbook = openpyxl.load_workbook(output_path, data_only=True)
            worksheet = workbook.active
            self.assertEqual(worksheet.title, "CC100 SUBTLEX-NL")
            self.assertEqual([cell.value for cell in worksheet[1]], script.HEADERS)
            self.assertEqual(worksheet["A2"].value, "de")
            self.assertEqual(worksheet["B2"].value, 10)
            self.assertAlmostEqual(worksheet["G2"].value, 100.0)
            self.assertIsNone(worksheet["A3"].value)


if __name__ == "__main__":
    unittest.main()
