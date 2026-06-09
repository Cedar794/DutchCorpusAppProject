#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "outputs" / "annotated_batches"
EXCEL_MAX_ROWS = 1_048_576

sys.path.insert(0, str(ROOT / "scripts"))

from merge_annotated_batches import HEADERS


INT_COLUMNS = {
    "FREQcount",
    "CDcount",
    "FREQlow",
    "CDlow",
    "FREQlemma",
    "dominant.pos.freq",
    "dominant.pos.lemma.freq",
}
FLOAT_COLUMNS = {"SUBTLEXWF", "Zipf", "SUBTLEXCD", "Lg10CD"}
TEXT_COLUMNS = set(HEADERS) - INT_COLUMNS - FLOAT_COLUMNS


def resolve_input_path(run_name: str | None, input_path: Path | None) -> Path:
    if input_path is not None:
        return input_path
    if not run_name:
        raise ValueError("--run-name is required when --input is not supplied")

    run_dir = OUTPUT_ROOT / run_name
    candidates = [
        run_dir / "merged_annotated_counts_top.tsv",
        run_dir / "merged_annotated_counts.tsv",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"no merged TSV found under {run_dir}")


def resolve_output_path(run_name: str | None, input_path: Path, output_path: Path | None) -> Path:
    if output_path is not None:
        return output_path
    if run_name:
        return OUTPUT_ROOT / run_name / "merged_annotated_counts_top.xlsx"
    return input_path.with_suffix(".xlsx")


def coerce_cell(header: str, value: str) -> object:
    if value == "":
        return None
    if header in INT_COLUMNS:
        return int(value)
    if header in FLOAT_COLUMNS:
        return float(value)
    return value


def iter_tsv_rows(path: Path, top: int) -> tuple[list[str], list[list[object]]]:
    limit = EXCEL_MAX_ROWS - 1 if top <= 0 else top
    if limit > EXCEL_MAX_ROWS - 1:
        raise ValueError(f"Excel can hold at most {EXCEL_MAX_ROWS - 1:,} data rows")

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise ValueError(f"{path} is empty")
        headers = list(reader.fieldnames)
        if headers != HEADERS:
            raise ValueError(f"unexpected TSV headers: {headers}")

        rows = []
        for row_index, row in enumerate(reader):
            if row_index >= limit:
                break
            rows.append([coerce_cell(header, row[header]) for header in HEADERS])
    return HEADERS, rows


def style_worksheet(worksheet: openpyxl.worksheet.worksheet.Worksheet, row_count: int) -> None:
    header_fill = PatternFill("solid", fgColor="1F2937")
    header_font = Font(color="FFFFFF", bold=True)
    for cell in worksheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")

    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = f"A1:{get_column_letter(len(HEADERS))}{row_count + 1}"
    worksheet.sheet_view.showGridLines = False

    widths = {
        "Word": 20,
        "FREQcount": 14,
        "CDcount": 12,
        "FREQlow": 12,
        "CDlow": 12,
        "FREQlemma": 14,
        "SUBTLEXWF": 16,
        "Zipf": 12,
        "SUBTLEXCD": 14,
        "Lg10CD": 12,
        "dominant.pos": 14,
        "dominant.pos.freq": 18,
        "dominant.pos.lemma": 22,
        "dominant.pos.lemma.freq": 24,
        "all.pos": 28,
        "all.pos.freq": 28,
        "all.pos.lemma.freq": 30,
    }
    for column_index, header in enumerate(HEADERS, start=1):
        letter = get_column_letter(column_index)
        worksheet.column_dimensions[letter].width = widths[header]
        number_format = "0.0000000000" if header in FLOAT_COLUMNS else "#,##0" if header in INT_COLUMNS else "@"
        for cell in worksheet.iter_cols(min_col=column_index, max_col=column_index, min_row=2, max_row=row_count + 1):
            for item in cell:
                item.number_format = number_format


def export_xlsx(input_path: Path, output_path: Path, top: int) -> int:
    headers, rows = iter_tsv_rows(input_path, top)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = "CC100 SUBTLEX-NL"
    worksheet.append(headers)
    for row in rows:
        worksheet.append(row)
    style_worksheet(worksheet, len(rows))
    workbook.save(output_path)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-name")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--top", type=int, default=50_000, help="0 exports up to Excel's row limit")
    args = parser.parse_args()

    input_path = resolve_input_path(args.run_name, args.input)
    output_path = resolve_output_path(args.run_name, input_path, args.output)
    row_count = export_xlsx(input_path, output_path, args.top)
    print(f"Wrote {output_path} rows={row_count}")


if __name__ == "__main__":
    main()
