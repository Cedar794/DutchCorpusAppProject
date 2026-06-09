#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import json
import lzma
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "nl.txt.xz"
OUTPUT_ROOT = ROOT / "outputs" / "token_count_batches"

sys.path.insert(0, str(ROOT))

from cc100_subtlex.core import count_rows, count_token_lines


def iter_line_batches(path: Path, limit_bytes: int | None, batch_lines: int) -> Iterator[tuple[list[str], int]]:
    read_bytes = 0
    batch: list[str] = []
    batch_bytes = 0

    with lzma.open(path, "rt", encoding="utf-8", errors="replace", newline="") as handle:
        for line in handle:
            encoded_len = len(line.encode("utf-8", errors="replace"))
            if limit_bytes is not None and read_bytes + encoded_len > limit_bytes and read_bytes > 0:
                break
            read_bytes += encoded_len
            batch_bytes += encoded_len
            batch.append(line)

            if len(batch) >= batch_lines:
                yield batch, batch_bytes
                batch = []
                batch_bytes = 0

    if batch:
        yield batch, batch_bytes


def write_batch(path: Path, result) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(tmp_path, "wt", encoding="utf-8", newline="") as handle:
        handle.write("word\tfreq\tlow_freq\tdoc_freq\tlow_doc_freq\n")
        for word, freq, low_freq, doc_freq, low_doc_freq in count_rows(result):
            handle.write(f"{word}\t{freq}\t{low_freq}\t{doc_freq}\t{low_doc_freq}\n")
    tmp_path.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit-mib", type=int, default=None)
    parser.add_argument("--batch-lines", type=int, default=250_000)
    parser.add_argument("--run-name", default=None)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    limit_bytes = None if args.limit_mib is None else args.limit_mib * 1024 * 1024
    if args.run_name:
        run_name = args.run_name
    elif args.limit_mib is None:
        run_name = datetime.now(timezone.utc).strftime("full_%Y%m%dT%H%M%SZ")
    else:
        run_name = f"pilot_{args.limit_mib}mib"

    run_dir = OUTPUT_ROOT / run_name
    batch_dir = run_dir / "batches"
    batch_dir.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "corpus": str(CORPUS),
        "run_name": run_name,
        "limit_mib": args.limit_mib,
        "batch_lines": args.batch_lines,
        "batches": [],
        "total_input_lines": 0,
        "total_token_documents": 0,
        "total_tokens": 0,
        "total_uncompressed_bytes_read_approx": 0,
        "elapsed_seconds": None,
    }

    for batch_index, (lines, batch_bytes) in enumerate(
        iter_line_batches(CORPUS, limit_bytes, args.batch_lines)
    ):
        batch_path = batch_dir / f"batch-{batch_index:06d}.tsv.gz"
        batch_started = time.perf_counter()
        if args.resume and batch_path.exists():
            batch_meta = {
                "batch_index": batch_index,
                "path": str(batch_path),
                "input_lines": len(lines),
                "uncompressed_bytes_approx": batch_bytes,
                "skipped_existing": True,
                "elapsed_seconds": 0,
            }
        else:
            result = count_token_lines(lines)
            write_batch(batch_path, result)
            batch_meta = {
                "batch_index": batch_index,
                "path": str(batch_path),
                "input_lines": len(lines),
                "token_documents": result.total_documents,
                "tokens": result.total_tokens,
                "unique_words_in_batch": len(result.word_freq),
                "uncompressed_bytes_approx": batch_bytes,
                "elapsed_seconds": time.perf_counter() - batch_started,
            }
            manifest["total_token_documents"] += result.total_documents
            manifest["total_tokens"] += result.total_tokens

        manifest["total_input_lines"] += len(lines)
        manifest["total_uncompressed_bytes_read_approx"] += batch_bytes
        manifest["batches"].append(batch_meta)

        manifest_path = run_dir / "manifest.json"
        manifest["elapsed_seconds"] = time.perf_counter() - started
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            f"batch={batch_index} lines={len(lines)} path={batch_path.name} "
            f"elapsed={batch_meta['elapsed_seconds']:.2f}s"
        )

    manifest["elapsed_seconds"] = time.perf_counter() - started
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {run_dir / 'manifest.json'}")


if __name__ == "__main__":
    main()

