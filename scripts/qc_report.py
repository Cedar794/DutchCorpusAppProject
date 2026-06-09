#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "outputs" / "annotated_batches"
DEFAULT_REFERENCE_PROFILE = ROOT / "outputs" / "subtlex_reference_profile.json"
DEFAULT_PROJECTED_TOTAL_TOKENS = 4_979_340_333

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


def resolve_run_paths(
    run_name: str | None,
    input_path: Path | None,
    manifest_path: Path | None,
    merge_metadata_path: Path | None,
    output_path: Path | None,
) -> tuple[Path, Path | None, Path | None, Path]:
    run_dir = OUTPUT_ROOT / run_name if run_name else None

    if input_path is None:
        if run_dir is None:
            raise ValueError("--run-name is required when --input is not supplied")
        input_candidates = [
            run_dir / "merged_annotated_counts_top.tsv",
            run_dir / "merged_annotated_counts.tsv",
        ]
        for candidate in input_candidates:
            if candidate.exists():
                input_path = candidate
                break
        if input_path is None:
            raise FileNotFoundError(f"no merged TSV found under {run_dir}")

    if manifest_path is None and run_dir is not None and (run_dir / "manifest.json").exists():
        manifest_path = run_dir / "manifest.json"
    if merge_metadata_path is None and run_dir is not None and (run_dir / "merge_metadata.json").exists():
        merge_metadata_path = run_dir / "merge_metadata.json"
    if output_path is None:
        output_path = run_dir / "qc_report.md" if run_dir is not None else input_path.with_suffix(".qc.md")

    return input_path, manifest_path, merge_metadata_path, output_path


def load_json(path: Path | None) -> dict[str, object] | None:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def dot_values(value: str) -> list[str]:
    if not value:
        return []
    return [part for part in value.split(".") if part]


def parse_number(row: dict[str, str], header: str) -> float:
    raw = row.get(header, "")
    if raw == "":
        return 0.0
    return float(raw)


def read_tsv_sample(path: Path, scan_rows: int) -> tuple[list[str], list[dict[str, str]], bool]:
    rows: list[dict[str, str]] = []
    truncated = False
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise ValueError(f"{path} is empty")
        headers = list(reader.fieldnames)
        for row_index, row in enumerate(reader):
            if row_index >= scan_rows:
                truncated = True
                break
            rows.append(row)
    return headers, rows, truncated


def check_formulas(rows: list[dict[str, str]], total_tokens: int, total_documents: int) -> tuple[bool, str]:
    if not rows:
        return False, "no data rows scanned"

    max_wf_error = 0.0
    max_zipf_error = 0.0
    max_cd_error = 0.0
    max_lg10cd_error = 0.0

    for row in rows:
        freq = int(parse_number(row, "FREQcount"))
        cd = int(parse_number(row, "CDcount"))
        expected_wf = freq / total_tokens * 1_000_000
        expected_zipf = math.log10(freq / total_tokens * 1_000_000_000)
        expected_cd = cd / total_documents * 100
        expected_lg10cd = math.log10(cd)

        max_wf_error = max(max_wf_error, abs(float(row["SUBTLEXWF"]) - expected_wf))
        max_zipf_error = max(max_zipf_error, abs(float(row["Zipf"]) - expected_zipf))
        max_cd_error = max(max_cd_error, abs(float(row["SUBTLEXCD"]) - expected_cd))
        max_lg10cd_error = max(max_lg10cd_error, abs(float(row["Lg10CD"]) - expected_lg10cd))

    tolerance = 1e-8
    passed = max(max_wf_error, max_zipf_error, max_cd_error, max_lg10cd_error) <= tolerance
    detail = (
        f"max errors WF={max_wf_error:.3g}, Zipf={max_zipf_error:.3g}, "
        f"CD={max_cd_error:.3g}, Lg10CD={max_lg10cd_error:.3g}"
    )
    return passed, detail


def check_row_invariants(rows: list[dict[str, str]]) -> tuple[bool, str]:
    failures: list[str] = []
    previous_freq: int | None = None

    for row_index, row in enumerate(rows, start=2):
        freq = int(parse_number(row, "FREQcount"))
        cd = int(parse_number(row, "CDcount"))
        low_freq = int(parse_number(row, "FREQlow"))
        low_cd = int(parse_number(row, "CDlow"))
        dominant_pos_freq = int(parse_number(row, "dominant.pos.freq"))
        dominant_lemma_freq = int(parse_number(row, "dominant.pos.lemma.freq"))

        if previous_freq is not None and freq > previous_freq:
            failures.append(f"row {row_index}: FREQcount is not descending")
        previous_freq = freq

        if low_freq > freq:
            failures.append(f"row {row_index}: FREQlow > FREQcount")
        if low_cd > cd:
            failures.append(f"row {row_index}: CDlow > CDcount")
        if dominant_pos_freq > freq:
            failures.append(f"row {row_index}: dominant.pos.freq > FREQcount")
        if dominant_lemma_freq > int(parse_number(row, "FREQlemma")):
            failures.append(f"row {row_index}: dominant.pos.lemma.freq > FREQlemma")

        pos_values = dot_values(row["all.pos"])
        pos_freqs = dot_values(row["all.pos.freq"])
        lemma_freqs = dot_values(row["all.pos.lemma.freq"])
        if not (len(pos_values) == len(pos_freqs) == len(lemma_freqs)):
            failures.append(f"row {row_index}: all.pos/all.pos.freq/all.pos.lemma.freq lengths differ")
        if pos_values and row["dominant.pos"] != pos_values[0]:
            failures.append(f"row {row_index}: dominant.pos is not first all.pos")
        if pos_freqs and str(dominant_pos_freq) != pos_freqs[0]:
            failures.append(f"row {row_index}: dominant.pos.freq is not first all.pos.freq")

        if len(failures) >= 8:
            break

    if failures:
        return False, "; ".join(failures)
    return True, f"checked {len(rows):,} scanned rows"


def check_metadata_totals(manifest: dict[str, object] | None, merge_metadata: dict[str, object] | None) -> tuple[bool, str]:
    if manifest is None or merge_metadata is None:
        return True, "manifest or merge metadata not supplied"

    manifest_tokens = int(manifest["total_tokens"])
    merge_tokens = int(merge_metadata["total_tokens"])
    manifest_docs = int(manifest.get("total_token_documents") or manifest.get("total_documents") or 0)
    merge_docs = int(merge_metadata["total_documents"])
    passed = manifest_tokens == merge_tokens and manifest_docs == merge_docs
    return passed, f"manifest tokens/docs={manifest_tokens:,}/{manifest_docs:,}; merge tokens/docs={merge_tokens:,}/{merge_docs:,}"


def total_documents_from_manifest(manifest: dict[str, object] | None, merge_metadata: dict[str, object] | None) -> int:
    if merge_metadata is not None:
        return int(merge_metadata["total_documents"])
    if manifest is not None:
        return int(manifest.get("total_token_documents") or manifest.get("total_documents") or 0)
    return 0


def total_tokens_from_manifest(manifest: dict[str, object] | None, merge_metadata: dict[str, object] | None) -> int:
    if merge_metadata is not None:
        return int(merge_metadata["total_tokens"])
    if manifest is not None:
        return int(manifest["total_tokens"])
    return 0


def build_summary_rows(
    manifest: dict[str, object] | None,
    merge_metadata: dict[str, object] | None,
    projected_total_tokens: int,
) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    total_tokens = total_tokens_from_manifest(manifest, merge_metadata)
    total_documents = total_documents_from_manifest(manifest, merge_metadata)
    if total_tokens:
        rows.append(("total_tokens", f"{total_tokens:,}"))
    if total_documents:
        rows.append(("total_documents", f"{total_documents:,}"))

    if manifest is not None:
        batches = manifest.get("batches", [])
        elapsed = float(manifest.get("elapsed_seconds") or 0.0)
        rows.extend(
            [
                ("run_name", str(manifest.get("run_name", ""))),
                ("input_lines", f"{sum(int(batch['input_lines']) for batch in batches):,}"),
                ("batches", f"{len(batches):,}"),
                ("workers", str(manifest.get("workers", ""))),
                ("batch_lines", str(manifest.get("batch_lines", ""))),
                ("frog_threads", str(manifest.get("frog_threads", ""))),
                ("elapsed_seconds", f"{elapsed:.2f}"),
            ]
        )
        if elapsed > 0 and total_tokens > 0:
            tokens_per_second = total_tokens / elapsed
            projected_hours = projected_total_tokens / tokens_per_second / 3600
            rows.append(("tokens_per_second", f"{tokens_per_second:,.1f}"))
            rows.append(("projected_full_runtime", f"{projected_hours:.1f} h / {projected_hours / 24:.2f} d"))

    if merge_metadata is not None:
        rows.extend(
            [
                ("unique_words", f"{int(merge_metadata.get('unique_words', 0)):,}"),
                ("exported_rows", f"{int(merge_metadata.get('exported_rows', 0)):,}"),
                ("merge_elapsed_seconds", f"{float(merge_metadata.get('elapsed_seconds', 0.0)):.3f}"),
            ]
        )
    return rows


def markdown_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return lines


def write_qc_report(
    input_path: Path,
    output_path: Path,
    manifest: dict[str, object] | None,
    merge_metadata: dict[str, object] | None,
    reference_profile: dict[str, object] | None,
    scan_rows: int,
    projected_total_tokens: int,
) -> list[tuple[str, bool, str]]:
    headers, rows, truncated = read_tsv_sample(input_path, scan_rows)
    total_tokens = total_tokens_from_manifest(manifest, merge_metadata)
    total_documents = total_documents_from_manifest(manifest, merge_metadata)

    checks: list[tuple[str, bool, str]] = []
    checks.append(("headers match pipeline", headers == HEADERS, f"{len(headers)} columns"))
    if reference_profile is not None:
        reference_headers = list(reference_profile.get("headers", []))
        checks.append(("headers match SUBTLEX workbook", headers == reference_headers, f"{len(reference_headers)} reference columns"))
    checks.append(("manifest and merge totals match", *check_metadata_totals(manifest, merge_metadata)))
    if total_tokens > 0 and total_documents > 0:
        checks.append(("formula columns", *check_formulas(rows, total_tokens, total_documents)))
    else:
        checks.append(("formula columns", False, "missing total token/document counts"))
    checks.append(("row invariants", *check_row_invariants(rows)))

    top_rows = [
        [
            row["Word"],
            row["FREQcount"],
            row["CDcount"],
            row["FREQlemma"],
            row["dominant.pos"],
            row["dominant.pos.lemma"],
        ]
        for row in rows[:20]
    ]

    lines = [
        f"# QC Report: {input_path.name}",
        "",
        f"Generated UTC: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Inputs",
        "",
        f"- TSV: `{input_path}`",
    ]
    if manifest is not None:
        lines.append(f"- Corpus: `{manifest.get('corpus', '')}`")
    if truncated:
        lines.append(f"- Scan: first {scan_rows:,} rows")
    else:
        lines.append(f"- Scan: all {len(rows):,} rows in TSV")

    lines.extend(["", "## Summary", ""])
    lines.extend(markdown_table(["Metric", "Value"], [[metric, value] for metric, value in build_summary_rows(manifest, merge_metadata, projected_total_tokens)]))

    lines.extend(["", "## Checks", ""])
    lines.extend(markdown_table(["Check", "Status", "Detail"], [[name, "PASS" if passed else "FAIL", detail] for name, passed, detail in checks]))

    lines.extend(["", "## Top Rows", ""])
    lines.extend(markdown_table(["Word", "FREQcount", "CDcount", "FREQlemma", "POS", "Lemma"], top_rows))
    lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-name")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--merge-metadata", type=Path)
    parser.add_argument("--reference-profile", type=Path, default=DEFAULT_REFERENCE_PROFILE)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--scan-rows", type=int, default=5_000)
    parser.add_argument("--projected-total-tokens", type=int, default=DEFAULT_PROJECTED_TOTAL_TOKENS)
    args = parser.parse_args()

    input_path, manifest_path, merge_metadata_path, output_path = resolve_run_paths(
        args.run_name,
        args.input,
        args.manifest,
        args.merge_metadata,
        args.output,
    )
    reference_profile = load_json(args.reference_profile) if args.reference_profile.exists() else None
    checks = write_qc_report(
        input_path,
        output_path,
        load_json(manifest_path),
        load_json(merge_metadata_path),
        reference_profile,
        args.scan_rows,
        args.projected_total_tokens,
    )
    failed = [name for name, passed, _detail in checks if not passed]
    print(f"Wrote {output_path}")
    if failed:
        print(f"QC failed: {', '.join(failed)}")
        raise SystemExit(1)
    print("QC passed")


if __name__ == "__main__":
    main()
