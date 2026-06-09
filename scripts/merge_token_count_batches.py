#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import json
import math
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "outputs" / "token_count_batches"

sys.path.insert(0, str(ROOT))

from cc100_subtlex.batches import parse_count_row
from cc100_subtlex.core import subtlex_cd, subtlex_wf, zipf_frequency


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS word_counts (
            word TEXT PRIMARY KEY,
            freq INTEGER NOT NULL,
            low_freq INTEGER NOT NULL,
            doc_freq INTEGER NOT NULL,
            low_doc_freq INTEGER NOT NULL
        )
        """
    )
    return conn


def upsert_rows(conn: sqlite3.Connection, rows: list[tuple[str, int, int, int, int]]) -> None:
    conn.executemany(
        """
        INSERT INTO word_counts (word, freq, low_freq, doc_freq, low_doc_freq)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(word) DO UPDATE SET
            freq = freq + excluded.freq,
            low_freq = low_freq + excluded.low_freq,
            doc_freq = doc_freq + excluded.doc_freq,
            low_doc_freq = low_doc_freq + excluded.low_doc_freq
        """,
        rows,
    )


def merge_batch_file(conn: sqlite3.Connection, path: Path, chunk_size: int) -> int:
    merged = 0
    rows: list[tuple[str, int, int, int, int]] = []
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            row = parse_count_row(line)
            if row is None:
                continue
            rows.append(row)
            if len(rows) >= chunk_size:
                upsert_rows(conn, rows)
                merged += len(rows)
                rows = []
        if rows:
            upsert_rows(conn, rows)
            merged += len(rows)
    conn.commit()
    return merged


def export_tsv(
    conn: sqlite3.Connection,
    output_path: Path,
    total_tokens: int,
    total_documents: int,
    top: int,
) -> int:
    sql = """
        SELECT word, freq, low_freq, doc_freq, low_doc_freq
        FROM word_counts
        ORDER BY freq DESC, word ASC
    """
    if top > 0:
        sql += f" LIMIT {int(top)}"

    written = 0
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(
            "Word\tFREQcount\tCDcount\tFREQlow\tCDlow\tSUBTLEXWF\tZipf\tSUBTLEXCD\tLg10CD\n"
        )
        for word, freq, low_freq, doc_freq, low_doc_freq in conn.execute(sql):
            handle.write(
                "\t".join(
                    [
                        word,
                        str(freq),
                        str(doc_freq),
                        str(low_freq),
                        str(low_doc_freq),
                        f"{subtlex_wf(freq, total_tokens):.10f}",
                        f"{zipf_frequency(freq, total_tokens):.10f}",
                        f"{subtlex_cd(doc_freq, total_documents):.10f}",
                        f"{math.log10(doc_freq):.10f}",
                    ]
                )
                + "\n"
            )
            written += 1
    return written


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--chunk-size", type=int, default=50_000)
    parser.add_argument("--top", type=int, default=0, help="0 means export all rows")
    args = parser.parse_args()

    run_dir = OUTPUT_ROOT / args.run_name
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    db_path = run_dir / "merged_counts.sqlite"
    output_path = run_dir / ("merged_token_counts_top.tsv" if args.top > 0 else "merged_token_counts.tsv")
    metadata_path = run_dir / "merge_metadata.json"

    started = time.perf_counter()
    conn = connect(db_path)
    conn.execute("DELETE FROM word_counts")
    conn.commit()

    batch_summaries = []
    for batch in manifest["batches"]:
        path = Path(batch["path"])
        batch_started = time.perf_counter()
        merged_rows = merge_batch_file(conn, path, args.chunk_size)
        batch_summaries.append(
            {
                "path": str(path),
                "merged_rows": merged_rows,
                "elapsed_seconds": time.perf_counter() - batch_started,
            }
        )
        print(f"merged {path.name}: rows={merged_rows}")

    unique_words = conn.execute("SELECT COUNT(*) FROM word_counts").fetchone()[0]
    exported_rows = export_tsv(
        conn,
        output_path,
        total_tokens=int(manifest["total_tokens"]),
        total_documents=int(manifest["total_token_documents"]),
        top=args.top,
    )

    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "run_name": args.run_name,
        "manifest": str(manifest_path),
        "database": str(db_path),
        "output": str(output_path),
        "top": args.top,
        "unique_words": unique_words,
        "exported_rows": exported_rows,
        "total_tokens": manifest["total_tokens"],
        "total_documents": manifest["total_token_documents"],
        "elapsed_seconds": time.perf_counter() - started,
        "batches": batch_summaries,
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    conn.close()
    print(f"Wrote {output_path}")
    print(f"Wrote {metadata_path}")


if __name__ == "__main__":
    main()

