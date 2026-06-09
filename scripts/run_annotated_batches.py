#!/usr/bin/env python3
from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
import gzip
import json
import lzma
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "nl.txt.xz"
OUTPUT_ROOT = ROOT / "outputs" / "annotated_batches"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from cc100_subtlex.annotated import ANNOTATED_BATCH_HEADER, DOC_SENTINEL, iter_annotated_count_rows
from merge_annotated_batches import connect as connect_merge_db, merge_batch_file
from pilot_annotated_counts import build_frog_invocation, parse_annotated_output


def iter_line_batches(
    path: Path,
    limit_bytes: int | None,
    batch_lines: int,
    max_lines: int | None = None,
) -> Iterator[tuple[list[str], int]]:
    read_bytes = 0
    read_lines = 0
    batch: list[str] = []
    batch_bytes = 0

    with lzma.open(path, "rt", encoding="utf-8", errors="replace", newline="") as handle:
        for line in handle:
            if max_lines is not None and read_lines >= max_lines:
                break
            encoded_len = len(line.encode("utf-8", errors="replace"))
            if limit_bytes is not None and read_bytes + encoded_len > limit_bytes and read_bytes > 0:
                break
            read_bytes += encoded_len
            read_lines += 1
            batch_bytes += encoded_len
            batch.append(line)

            if len(batch) >= batch_lines:
                yield batch, batch_bytes
                batch = []
                batch_bytes = 0

    if batch:
        yield batch, batch_bytes


def write_frog_input_lines(lines: list[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8", newline="") as handle:
        for line in lines:
            stripped = line.strip()
            if stripped:
                handle.write(f"{stripped} {DOC_SENTINEL}\n")
            else:
                handle.write(f"{DOC_SENTINEL}\n")
    tmp_path.replace(path)


def write_annotated_counts(path: Path, counter) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(tmp_path, "wt", encoding="utf-8", newline="") as handle:
        handle.write(ANNOTATED_BATCH_HEADER + "\n")
        for row in iter_annotated_count_rows(counter):
            handle.write("\t".join(map(str, row)) + "\n")
    tmp_path.replace(path)


def open_live_merge_db(db_path: Path):
    conn = connect_merge_db(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS merged_batches (
            batch_index INTEGER PRIMARY KEY,
            counts_path TEXT NOT NULL,
            input_lines INTEGER NOT NULL,
            total_documents INTEGER NOT NULL,
            total_tokens INTEGER NOT NULL,
            kind_counts_json TEXT NOT NULL,
            merged_utc TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def is_live_batch_merged(conn, batch_index: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM merged_batches WHERE batch_index = ?",
        (int(batch_index),),
    ).fetchone()
    return row is not None


def merge_completed_batch(
    conn,
    meta: dict[str, object],
    chunk_size: int,
    delete_counts: bool,
) -> dict[str, object]:
    batch_index = int(meta["batch_index"])
    if is_live_batch_merged(conn, batch_index):
        return {"batch_index": batch_index, "merged": False, "kind_counts": None}

    counts_path = Path(str(meta["counts_path"]))
    if not counts_path.exists():
        raise FileNotFoundError(counts_path)

    started = time.perf_counter()
    try:
        kind_counts = merge_batch_file(conn, counts_path, chunk_size, commit_chunks=False)
        conn.execute(
            """
            INSERT INTO merged_batches (
                batch_index,
                counts_path,
                input_lines,
                total_documents,
                total_tokens,
                kind_counts_json,
                merged_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch_index,
                str(counts_path),
                int(meta.get("input_lines", 0)),
                int(meta.get("total_documents", 0)),
                int(meta.get("total_tokens", 0)),
                json.dumps(kind_counts, ensure_ascii=False, sort_keys=True),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    counts_deleted = False
    counts_delete_error = ""
    if delete_counts:
        try:
            counts_path.unlink(missing_ok=True)
            counts_deleted = not counts_path.exists()
        except OSError as exc:
            counts_delete_error = f"{type(exc).__name__}: {exc}"

    return {
        "batch_index": batch_index,
        "merged": True,
        "kind_counts": kind_counts,
        "elapsed_seconds": time.perf_counter() - started,
        "counts_deleted": counts_deleted,
        "counts_delete_error": counts_delete_error,
    }


def process_batch(job: dict[str, object]) -> dict[str, object]:
    batch_index = int(job["batch_index"])
    batch_dir = Path(str(job["batch_dir"]))
    input_path = Path(str(job["input_path"]))
    frog_output_path = Path(str(job["frog_output_path"]))
    counts_path = Path(str(job["counts_path"]))
    batch_meta_path = Path(str(job["batch_meta_path"]))
    keep_intermediate = bool(job["keep_intermediate"])

    started = time.perf_counter()
    invocation = build_frog_invocation(
        str(job["backend"]),
        batch_dir,
        input_path,
        frog_output_path,
        native_prefix=job["native_prefix"],
        frog_threads=int(job["frog_threads"]) if job["frog_threads"] is not None else None,
    )
    completed = subprocess.run(
        invocation["command"],
        cwd=ROOT,
        env=invocation["env"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    frog_elapsed = time.perf_counter() - started
    meta: dict[str, object] = {
        "batch_index": batch_index,
        "input_lines": int(job["input_lines"]),
        "uncompressed_bytes_approx": int(job["uncompressed_bytes_approx"]),
        "batch_dir": str(batch_dir),
        "input_path": str(input_path),
        "frog_output_path": str(frog_output_path),
        "counts_path": str(counts_path),
        "batch_meta_path": str(batch_meta_path),
        "backend": invocation["backend"],
        "command": invocation["command"],
        "native_prefix": invocation["native_prefix"],
        "native_frog": invocation["native_frog"],
        "frog_threads": job["frog_threads"],
        "frog_returncode": completed.returncode,
        "frog_elapsed_seconds": frog_elapsed,
        "stdout_tail": completed.stdout[-8000:],
        "stderr_tail": completed.stderr[-8000:],
    }
    if completed.returncode != 0:
        meta["elapsed_seconds"] = time.perf_counter() - started
        batch_meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return meta

    counter = parse_annotated_output(frog_output_path)
    write_annotated_counts(counts_path, counter)
    if not keep_intermediate:
        input_path.unlink(missing_ok=True)
        frog_output_path.unlink(missing_ok=True)
        try:
            batch_dir.rmdir()
        except OSError:
            pass

    meta.update(
        {
            "total_documents": counter.total_documents,
            "total_tokens": counter.total_tokens,
            "unique_words_in_batch": len(counter.word_freq),
            "elapsed_seconds": time.perf_counter() - started,
        }
    )
    batch_meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return meta


def write_manifest(run_dir: Path, manifest: dict[str, object], results_by_index: dict[int, dict[str, object]]) -> None:
    batches = [results_by_index[index] for index in sorted(results_by_index)]
    manifest["batches"] = batches
    manifest["total_input_lines"] = sum(int(batch.get("input_lines", 0)) for batch in batches)
    manifest["total_token_documents"] = sum(int(batch.get("total_documents", 0)) for batch in batches)
    manifest["total_tokens"] = sum(int(batch.get("total_tokens", 0)) for batch in batches)
    manifest["total_uncompressed_bytes_read_approx"] = sum(
        int(batch.get("uncompressed_bytes_approx", 0)) for batch in batches
    )
    manifest["elapsed_seconds"] = time.perf_counter() - float(manifest["_started_perf"])
    serializable = {key: value for key, value in manifest.items() if key != "_started_perf"}
    text = json.dumps(serializable, ensure_ascii=False, indent=2) + "\n"
    target = run_dir / "manifest.json"
    tmp_path = run_dir / f".manifest.{os.getpid()}.tmp"
    for attempt in range(6):
        try:
            tmp_path.write_text(text, encoding="utf-8")
            tmp_path.replace(target)
            return
        except OSError:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            if attempt == 5:
                raise
            time.sleep(min(10.0, 0.5 * (2**attempt)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit-mib", type=int, default=None)
    parser.add_argument("--max-lines", type=int, default=None)
    parser.add_argument("--batch-lines", type=int, default=20_000)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--run-name", default=None)
    parser.add_argument("--backend", choices=["auto", "native", "docker"], default="auto")
    parser.add_argument("--native-prefix", default=None)
    parser.add_argument("--frog-threads", type=int, default=1)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--keep-intermediate", action="store_true")
    parser.add_argument("--live-merge", action="store_true")
    parser.add_argument("--keep-count-shards", action="store_true")
    parser.add_argument("--merge-chunk-size", type=int, default=50_000)
    parser.add_argument("--manifest-write-interval-seconds", type=float, default=300.0)
    args = parser.parse_args()

    limit_bytes = None if args.limit_mib is None else args.limit_mib * 1024 * 1024
    if args.run_name:
        run_name = args.run_name
    elif args.limit_mib is None:
        run_name = datetime.now(timezone.utc).strftime("full_%Y%m%dT%H%M%SZ")
    else:
        run_name = f"pilot_{args.limit_mib}mib"

    run_dir = OUTPUT_ROOT / run_name
    work_dir = run_dir / "work"
    counts_dir = run_dir / "counts"
    batch_meta_dir = run_dir / "batch_metadata"
    counts_dir.mkdir(parents=True, exist_ok=True)
    batch_meta_dir.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    manifest: dict[str, object] = {
        "_started_perf": started,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "corpus": str(CORPUS),
        "run_name": run_name,
        "limit_mib": args.limit_mib,
        "max_lines": args.max_lines,
        "batch_lines": args.batch_lines,
        "workers": args.workers,
        "backend": args.backend,
        "native_prefix": args.native_prefix,
        "frog_threads": args.frog_threads,
        "keep_intermediate": args.keep_intermediate,
        "live_merge": args.live_merge,
        "keep_count_shards": args.keep_count_shards,
        "merge_chunk_size": args.merge_chunk_size,
        "live_merge_db": str(run_dir / "merged_annotated_counts.sqlite") if args.live_merge else None,
        "batches": [],
        "total_input_lines": 0,
        "total_token_documents": 0,
        "total_tokens": 0,
        "total_uncompressed_bytes_read_approx": 0,
        "elapsed_seconds": None,
    }
    results_by_index: dict[int, dict[str, object]] = {}
    live_merge_conn = open_live_merge_db(run_dir / "merged_annotated_counts.sqlite") if args.live_merge else None
    manifest_dirty = False
    last_manifest_write = 0.0

    def maybe_write_manifest(force: bool = False) -> None:
        nonlocal manifest_dirty, last_manifest_write
        if not manifest_dirty:
            return
        now = time.perf_counter()
        interval = float(args.manifest_write_interval_seconds)
        if force or interval <= 0.0 or now - last_manifest_write >= interval:
            write_manifest(run_dir, manifest, results_by_index)
            manifest_dirty = False
            last_manifest_write = time.perf_counter()

    def record_result(
        meta: dict[str, object],
        *,
        emit_log: bool = True,
        update_manifest: bool = True,
        force_manifest: bool = False,
    ) -> None:
        nonlocal manifest_dirty
        batch_index = int(meta["batch_index"])
        if int(meta.get("frog_returncode", 0)) != 0:
            results_by_index[batch_index] = meta
            if update_manifest:
                manifest_dirty = True
                maybe_write_manifest(force=True)
            raise RuntimeError(f"Frog failed for batch {batch_index}; see {meta['batch_meta_path']}")
        if live_merge_conn is not None:
            meta["live_merge"] = merge_completed_batch(
                live_merge_conn,
                meta,
                chunk_size=args.merge_chunk_size,
                delete_counts=not args.keep_count_shards,
            )
        results_by_index[batch_index] = meta
        if update_manifest:
            manifest_dirty = True
            maybe_write_manifest(force=force_manifest)
        if emit_log:
            print(
                f"batch={batch_index} lines={meta['input_lines']} tokens={meta.get('total_tokens', 0)} "
                f"counts={Path(str(meta['counts_path'])).name} elapsed={float(meta['elapsed_seconds']):.2f}s"
            )

    pending: set[Future[dict[str, object]]] = set()
    resumed_batches = 0
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        for batch_index, (lines, batch_bytes) in enumerate(
            iter_line_batches(CORPUS, limit_bytes, args.batch_lines, args.max_lines)
        ):
            batch_dir = work_dir / f"batch-{batch_index:06d}"
            input_path = batch_dir / "frog_input.txt"
            frog_output_path = batch_dir / "frog_output.tsv"
            counts_path = counts_dir / f"batch-{batch_index:06d}.tsv.gz"
            batch_meta_path = batch_meta_dir / f"batch-{batch_index:06d}.json"

            if args.resume and batch_meta_path.exists() and (
                counts_path.exists()
                or (live_merge_conn is not None and is_live_batch_merged(live_merge_conn, batch_index))
            ):
                record_result(
                    json.loads(batch_meta_path.read_text(encoding="utf-8")),
                    emit_log=False,
                    update_manifest=False,
                )
                resumed_batches += 1
                if resumed_batches % 5000 == 0:
                    print(f"resume_replayed={resumed_batches} last_batch={batch_index}")
                continue

            write_frog_input_lines(lines, input_path)
            job = {
                "batch_index": batch_index,
                "batch_dir": batch_dir,
                "input_path": input_path,
                "frog_output_path": frog_output_path,
                "counts_path": counts_path,
                "batch_meta_path": batch_meta_path,
                "input_lines": len(lines),
                "uncompressed_bytes_approx": batch_bytes,
                "backend": args.backend,
                "native_prefix": args.native_prefix,
                "frog_threads": args.frog_threads,
                "keep_intermediate": args.keep_intermediate,
            }
            pending.add(executor.submit(process_batch, job))

            while len(pending) >= args.workers:
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    record_result(future.result())

        while pending:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                record_result(future.result())

    maybe_write_manifest(force=True)
    if live_merge_conn is not None:
        live_merge_conn.close()
    print(f"Wrote {run_dir / 'manifest.json'}")


if __name__ == "__main__":
    main()
