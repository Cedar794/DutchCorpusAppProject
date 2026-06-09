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
OUTPUT_ROOT = ROOT / "outputs" / "annotated_batches"

sys.path.insert(0, str(ROOT))

from cc100_subtlex.annotated import parse_annotated_count_row
from cc100_subtlex.core import dot_join, subtlex_cd, subtlex_wf, zipf_frequency


HEADERS = [
    "Word",
    "FREQcount",
    "CDcount",
    "FREQlow",
    "CDlow",
    "FREQlemma",
    "SUBTLEXWF",
    "Zipf",
    "SUBTLEXCD",
    "Lg10CD",
    "dominant.pos",
    "dominant.pos.freq",
    "dominant.pos.lemma",
    "dominant.pos.lemma.freq",
    "all.pos",
    "all.pos.freq",
    "all.pos.lemma.freq",
]


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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS word_pos_counts (
            word TEXT NOT NULL,
            pos TEXT NOT NULL,
            freq INTEGER NOT NULL,
            PRIMARY KEY (word, pos)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS word_pos_lemma_counts (
            word TEXT NOT NULL,
            pos TEXT NOT NULL,
            lemma TEXT NOT NULL,
            freq INTEGER NOT NULL,
            PRIMARY KEY (word, pos, lemma)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pos_lemma_counts (
            pos TEXT NOT NULL,
            lemma TEXT NOT NULL,
            freq INTEGER NOT NULL,
            PRIMARY KEY (pos, lemma)
        )
        """
    )
    return conn


def reset_tables(conn: sqlite3.Connection) -> None:
    for table in ("word_counts", "word_pos_counts", "word_pos_lemma_counts", "pos_lemma_counts"):
        conn.execute(f"DELETE FROM {table}")
    conn.commit()


def upsert_word_rows(conn: sqlite3.Connection, rows: list[tuple[str, int, int, int, int]]) -> None:
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


def upsert_word_pos_rows(conn: sqlite3.Connection, rows: list[tuple[str, str, int]]) -> None:
    conn.executemany(
        """
        INSERT INTO word_pos_counts (word, pos, freq)
        VALUES (?, ?, ?)
        ON CONFLICT(word, pos) DO UPDATE SET
            freq = freq + excluded.freq
        """,
        rows,
    )


def upsert_word_pos_lemma_rows(conn: sqlite3.Connection, rows: list[tuple[str, str, str, int]]) -> None:
    conn.executemany(
        """
        INSERT INTO word_pos_lemma_counts (word, pos, lemma, freq)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(word, pos, lemma) DO UPDATE SET
            freq = freq + excluded.freq
        """,
        rows,
    )


def upsert_pos_lemma_rows(conn: sqlite3.Connection, rows: list[tuple[str, str, int]]) -> None:
    conn.executemany(
        """
        INSERT INTO pos_lemma_counts (pos, lemma, freq)
        VALUES (?, ?, ?)
        ON CONFLICT(pos, lemma) DO UPDATE SET
            freq = freq + excluded.freq
        """,
        rows,
    )


def flush_buffers(conn: sqlite3.Connection, buffers: dict[str, list[tuple]], *, commit: bool = True) -> int:
    row_count = 0
    if buffers["word"]:
        upsert_word_rows(conn, buffers["word"])
        row_count += len(buffers["word"])
        buffers["word"] = []
    if buffers["word_pos"]:
        upsert_word_pos_rows(conn, buffers["word_pos"])
        row_count += len(buffers["word_pos"])
        buffers["word_pos"] = []
    if buffers["word_pos_lemma"]:
        upsert_word_pos_lemma_rows(conn, buffers["word_pos_lemma"])
        row_count += len(buffers["word_pos_lemma"])
        buffers["word_pos_lemma"] = []
    if buffers["pos_lemma"]:
        upsert_pos_lemma_rows(conn, buffers["pos_lemma"])
        row_count += len(buffers["pos_lemma"])
        buffers["pos_lemma"] = []
    if commit:
        conn.commit()
    return row_count


def merge_batch_file(
    conn: sqlite3.Connection,
    path: Path,
    chunk_size: int,
    *,
    commit_chunks: bool = True,
) -> dict[str, int]:
    buffers: dict[str, list[tuple]] = {
        "word": [],
        "word_pos": [],
        "word_pos_lemma": [],
        "pos_lemma": [],
    }
    kind_counts = {kind: 0 for kind in buffers}
    pending = 0
    flushed = 0

    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            row = parse_annotated_count_row(line)
            if row is None:
                continue
            kind, word, pos, lemma, freq, low_freq, doc_freq, low_doc_freq = row
            if kind == "word":
                buffers[kind].append((word, freq, low_freq, doc_freq, low_doc_freq))
            elif kind == "word_pos":
                buffers[kind].append((word, pos, freq))
            elif kind == "word_pos_lemma":
                buffers[kind].append((word, pos, lemma, freq))
            elif kind == "pos_lemma":
                buffers[kind].append((pos, lemma, freq))
            else:
                raise ValueError(f"unknown annotated count row kind: {kind}")
            kind_counts[kind] += 1
            pending += 1
            if pending >= chunk_size:
                flushed += flush_buffers(conn, buffers, commit=commit_chunks)
                pending = 0

    flushed += flush_buffers(conn, buffers, commit=commit_chunks)
    kind_counts["total"] = flushed
    return kind_counts


def prepare_export_indexes(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE INDEX IF NOT EXISTS idx_word_counts_export ON word_counts(freq DESC, word ASC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_word_pos_export ON word_pos_counts(word, freq DESC, pos ASC)")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_word_pos_lemma_export
        ON word_pos_lemma_counts(word, pos, freq DESC, lemma ASC)
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pos_lemma_export ON pos_lemma_counts(pos, lemma)")
    conn.commit()


def format_value(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.10f}"
    return str(value)


def pos_rows_for_word(conn: sqlite3.Connection, word: str) -> list[tuple[str, int, str, int]]:
    rows = []
    for pos, pos_freq in conn.execute(
        """
        SELECT pos, freq
        FROM word_pos_counts
        WHERE word = ?
        ORDER BY freq DESC, pos ASC
        """,
        (word,),
    ):
        lemma_row = conn.execute(
            """
            SELECT lemma
            FROM word_pos_lemma_counts
            WHERE word = ? AND pos = ?
            ORDER BY freq DESC, lemma ASC
            LIMIT 1
            """,
            (word, pos),
        ).fetchone()
        lemma = lemma_row[0] if lemma_row else word
        lemma_freq_row = conn.execute(
            """
            SELECT freq
            FROM pos_lemma_counts
            WHERE pos = ? AND lemma = ?
            """,
            (pos, lemma),
        ).fetchone()
        rows.append((pos, int(pos_freq), lemma, int(lemma_freq_row[0]) if lemma_freq_row else 0))
    return rows


def build_subtlex_row(
    conn: sqlite3.Connection,
    word: str,
    freq: int,
    low_freq: int,
    doc_freq: int,
    low_doc_freq: int,
    total_tokens: int,
    total_documents: int,
) -> dict[str, object]:
    pos_rows = pos_rows_for_word(conn, word)
    pos_values = [row[0] for row in pos_rows]
    pos_freqs = [row[1] for row in pos_rows]
    lemma_values = [row[2] for row in pos_rows]
    lemma_freqs = [row[3] for row in pos_rows]

    return {
        "Word": word,
        "FREQcount": freq,
        "CDcount": doc_freq,
        "FREQlow": low_freq,
        "CDlow": low_doc_freq,
        "FREQlemma": sum(lemma_freqs),
        "SUBTLEXWF": subtlex_wf(freq, total_tokens),
        "Zipf": zipf_frequency(freq, total_tokens),
        "SUBTLEXCD": subtlex_cd(doc_freq, total_documents),
        "Lg10CD": math.log10(doc_freq) if doc_freq > 0 else "",
        "dominant.pos": pos_values[0] if pos_values else "",
        "dominant.pos.freq": pos_freqs[0] if pos_freqs else 0,
        "dominant.pos.lemma": lemma_values[0] if lemma_values else word,
        "dominant.pos.lemma.freq": lemma_freqs[0] if lemma_freqs else 0,
        "all.pos": dot_join(pos_values) if pos_values else "",
        "all.pos.freq": dot_join(pos_freqs) if pos_freqs else "",
        "all.pos.lemma.freq": dot_join(lemma_freqs) if lemma_freqs else "",
    }


def export_tsv(
    conn: sqlite3.Connection,
    output_path: Path,
    total_tokens: int,
    total_documents: int,
    top: int,
) -> int:
    if total_tokens <= 0:
        raise ValueError("total_tokens must be positive")
    if total_documents <= 0:
        raise ValueError("total_documents must be positive")

    sql = """
        SELECT word, freq, low_freq, doc_freq, low_doc_freq
        FROM word_counts
        ORDER BY freq DESC, word ASC
    """
    if top > 0:
        sql += f" LIMIT {int(top)}"

    written = 0
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        handle.write("\t".join(HEADERS) + "\n")
        for word, freq, low_freq, doc_freq, low_doc_freq in conn.execute(sql):
            row = build_subtlex_row(
                conn,
                str(word),
                int(freq),
                int(low_freq),
                int(doc_freq),
                int(low_doc_freq),
                total_tokens,
                total_documents,
            )
            handle.write("\t".join(format_value(row[header]) for header in HEADERS) + "\n")
            written += 1
    return written


def count_paths_from_manifest(manifest: dict[str, object]) -> list[Path]:
    paths = []
    for batch in manifest["batches"]:
        if int(batch.get("frog_returncode", 0)) != 0:
            raise RuntimeError(f"batch {batch.get('batch_index')} failed; cannot merge")
        raw_path = batch.get("counts_path") or batch.get("path")
        if raw_path is None:
            raise KeyError(f"batch {batch.get('batch_index')} has no counts_path")
        path = Path(str(raw_path))
        if not path.exists():
            raise FileNotFoundError(path)
        paths.append(path)
    return paths


def manifest_total_documents(manifest: dict[str, object]) -> int:
    return int(manifest.get("total_token_documents") or manifest.get("total_documents") or 0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--chunk-size", type=int, default=50_000)
    parser.add_argument("--top", type=int, default=0, help="0 means export all rows")
    parser.add_argument("--use-existing-db", action="store_true")
    args = parser.parse_args()

    run_dir = OUTPUT_ROOT / args.run_name
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    db_path = run_dir / "merged_annotated_counts.sqlite"
    output_path = run_dir / ("merged_annotated_counts_top.tsv" if args.top > 0 else "merged_annotated_counts.tsv")
    metadata_path = run_dir / "merge_metadata.json"
    total_tokens = int(manifest["total_tokens"])
    total_documents = manifest_total_documents(manifest)

    started = time.perf_counter()
    if args.use_existing_db and not db_path.exists():
        raise FileNotFoundError(db_path)
    conn = connect(db_path)

    batch_summaries = []
    if not args.use_existing_db:
        reset_tables(conn)
        for path in count_paths_from_manifest(manifest):
            batch_started = time.perf_counter()
            kind_counts = merge_batch_file(conn, path, args.chunk_size)
            batch_summaries.append(
                {
                    "path": str(path),
                    "kind_counts": kind_counts,
                    "elapsed_seconds": time.perf_counter() - batch_started,
                }
            )
            print(f"merged {path.name}: rows={kind_counts['total']}")

    prepare_export_indexes(conn)
    unique_words = conn.execute("SELECT COUNT(*) FROM word_counts").fetchone()[0]
    exported_rows = export_tsv(conn, output_path, total_tokens, total_documents, args.top)

    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "run_name": args.run_name,
        "manifest": str(manifest_path),
        "database": str(db_path),
        "output": str(output_path),
        "top": args.top,
        "unique_words": unique_words,
        "exported_rows": exported_rows,
        "total_tokens": total_tokens,
        "total_documents": total_documents,
        "used_existing_db": args.use_existing_db,
        "elapsed_seconds": time.perf_counter() - started,
        "batches": batch_summaries,
        "headers": HEADERS,
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    conn.close()
    print(f"Wrote {output_path}")
    print(f"Wrote {metadata_path}")


if __name__ == "__main__":
    main()
