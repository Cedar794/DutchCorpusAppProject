#!/usr/bin/env python3
from __future__ import annotations

import argparse
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
OUTPUT_ROOT = ROOT / "outputs" / "annotated_pilots"
FROG_IMAGE = "proycon/lamachine:latest"
NATIVE_FROG = ROOT / "local" / "frog" / "bin" / "frog"
NATIVE_PREFIX_CANDIDATES = ("local/frog-llvm-omp", "local/frog")
HOMEBREW_PREFIX = Path(os.environ.get("HOMEBREW_PREFIX", "/opt/homebrew"))

sys.path.insert(0, str(ROOT))

from cc100_subtlex.annotated import DOC_SENTINEL, AnnotatedCounter, iter_subtlex_rows
from cc100_subtlex.frog import parse_frog_line


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


def iter_limited_lines(path: Path, limit_bytes: int) -> Iterator[str]:
    read_bytes = 0
    with lzma.open(path, "rt", encoding="utf-8", errors="replace", newline="") as handle:
        for line in handle:
            encoded_len = len(line.encode("utf-8", errors="replace"))
            if read_bytes + encoded_len > limit_bytes and read_bytes > 0:
                break
            read_bytes += encoded_len
            yield line


def write_frog_input(path: Path, limit_mib: int) -> dict[str, int]:
    input_lines = 0
    read_bytes = 0
    limit_bytes = limit_mib * 1024 * 1024
    with lzma.open(CORPUS, "rt", encoding="utf-8", errors="replace", newline="") as source:
        with path.open("w", encoding="utf-8", newline="") as target:
            for line in source:
                encoded_len = len(line.encode("utf-8", errors="replace"))
                if read_bytes + encoded_len > limit_bytes and read_bytes > 0:
                    break
                read_bytes += encoded_len
                stripped = line.strip()
                if stripped:
                    target.write(f"{stripped} {DOC_SENTINEL}\n")
                else:
                    target.write(f"{DOC_SENTINEL}\n")
                input_lines += 1
    return {"input_lines": input_lines, "uncompressed_bytes_approx": read_bytes}


def resolve_native_prefix(root: Path = ROOT, native_prefix: Path | str | None = None) -> Path:
    if native_prefix is not None:
        prefix = Path(native_prefix)
        return prefix if prefix.is_absolute() else root / prefix
    for relative in NATIVE_PREFIX_CANDIDATES:
        candidate = root / relative
        if (candidate / "bin" / "frog").exists():
            return candidate
    return root / "local" / "frog"


def select_backend(requested: str, root: Path = ROOT, native_prefix: Path | str | None = None) -> str:
    if requested == "auto":
        prefix = resolve_native_prefix(root, native_prefix)
        return "native" if (prefix / "bin" / "frog").exists() else "docker"
    if requested in {"native", "docker"}:
        return requested
    raise ValueError(f"Unsupported Frog backend: {requested}")


def native_frog_env(
    root: Path = ROOT,
    native_prefix: Path | str | None = None,
    base_env: dict[str, str] | None = None,
) -> dict[str, str]:
    prefix = resolve_native_prefix(root, native_prefix)
    env = dict(os.environ if base_env is None else base_env)
    path_dirs = [
        prefix / "bin",
        HOMEBREW_PREFIX / "opt" / "llvm" / "bin",
        HOMEBREW_PREFIX / "opt" / "icu4c@78" / "bin",
        HOMEBREW_PREFIX / "opt" / "libxml2" / "bin",
    ]
    lib_dirs = [
        prefix / "lib",
        HOMEBREW_PREFIX / "opt" / "libomp" / "lib",
        HOMEBREW_PREFIX / "opt" / "icu4c@78" / "lib",
        HOMEBREW_PREFIX / "opt" / "libxml2" / "lib",
    ]
    existing_path = env.get("PATH", "")
    existing_lib_path = env.get("DYLD_LIBRARY_PATH", "")
    env["PATH"] = ":".join(str(item) for item in path_dirs + ([existing_path] if existing_path else []))
    env["DYLD_LIBRARY_PATH"] = ":".join(
        str(item) for item in lib_dirs + ([existing_lib_path] if existing_lib_path else [])
    )
    return env


def build_frog_invocation(
    backend: str,
    run_dir: Path,
    input_path: Path,
    output_path: Path,
    root: Path = ROOT,
    native_prefix: Path | str | None = None,
    frog_threads: int | None = None,
    base_env: dict[str, str] | None = None,
) -> dict[str, object]:
    selected = select_backend(backend, root, native_prefix=native_prefix)
    if selected == "native":
        prefix = resolve_native_prefix(root, native_prefix)
        command = [
            str(prefix / "bin" / "frog"),
            "--skip=mpcn",
        ]
        if frog_threads is not None:
            command.append(f"--threads={frog_threads}")
        command.extend(["-t", str(input_path), "-o", str(output_path)])
        return {
            "backend": selected,
            "command": command,
            "env": native_frog_env(root, native_prefix=prefix, base_env=base_env),
            "native_prefix": str(prefix),
            "native_frog": str(prefix / "bin" / "frog"),
        }

    container_input = f"/data/{input_path.name}"
    container_output = f"/data/{output_path.name}"
    thread_arg = f" --threads={frog_threads}" if frog_threads is not None else ""
    return {
        "backend": selected,
        "command": [
            "docker",
            "run",
            "--rm",
            "--platform",
            "linux/amd64",
            "-v",
            f"{run_dir}:/data",
            FROG_IMAGE,
            "bash",
            "-lc",
            f"cd /data && frog --skip=mpcn{thread_arg} -t {container_input} -o {container_output}",
        ],
        "env": None,
        "native_prefix": None,
        "native_frog": None,
    }


def run_frog(
    run_dir: Path,
    input_path: Path,
    output_path: Path,
    backend: str,
    native_prefix: Path | str | None = None,
    frog_threads: int | None = None,
) -> dict[str, object]:
    invocation = build_frog_invocation(
        backend,
        run_dir,
        input_path,
        output_path,
        native_prefix=native_prefix,
        frog_threads=frog_threads,
    )
    started = time.perf_counter()
    completed = subprocess.run(
        invocation["command"],
        cwd=ROOT,
        env=invocation["env"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "backend": invocation["backend"],
        "command": invocation["command"],
        "returncode": completed.returncode,
        "elapsed_seconds": time.perf_counter() - started,
        "stdout_tail": completed.stdout[-8000:],
        "stderr_tail": completed.stderr[-8000:],
        "native_prefix": invocation["native_prefix"],
        "native_frog": invocation["native_frog"],
    }


def parse_annotated_output(path: Path) -> AnnotatedCounter:
    counter = AnnotatedCounter()
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            token = parse_frog_line(line)
            if token is not None:
                counter.add_token(token)
    counter.finish_document()
    return counter


def format_value(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.10f}"
    return str(value)


def write_rows(counter: AnnotatedCounter, output_path: Path, top: int) -> int:
    written = 0
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        handle.write("\t".join(HEADERS) + "\n")
        for row in iter_subtlex_rows(counter):
            handle.write("\t".join(format_value(row[header]) for header in HEADERS) + "\n")
            written += 1
            if top > 0 and written >= top:
                break
    return written


def write_qc(counter: AnnotatedCounter, output_path: Path, rows_path: Path) -> None:
    top_words = counter.word_freq.most_common(25)
    pos_counts = {}
    for (_word, pos), freq in counter.word_pos_freq.items():
        pos_counts[pos] = pos_counts.get(pos, 0) + freq
    top_pos = sorted(pos_counts.items(), key=lambda item: (-item[1], item[0]))[:25]
    lines = [
        "# Annotated Pilot QC",
        "",
        f"- Rows file: `{rows_path}`",
        f"- Token-bearing document units: {counter.total_documents}",
        f"- Tokens counted: {counter.total_tokens}",
        f"- Unique words: {len(counter.word_freq)}",
        "",
        "## Top Words",
        "",
    ]
    lines.extend(f"- {word}: {freq}" for word, freq in top_words)
    lines.extend(["", "## Top POS", ""])
    lines.extend(f"- {pos}: {freq}" for pos, freq in top_pos)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit-mib", type=int, default=1)
    parser.add_argument("--top", type=int, default=1000)
    parser.add_argument("--run-name", default=None)
    parser.add_argument("--backend", choices=["auto", "native", "docker"], default="auto")
    parser.add_argument("--native-prefix", default=None)
    parser.add_argument("--frog-threads", type=int, default=None)
    args = parser.parse_args()

    run_name = args.run_name or f"pilot_{args.limit_mib}mib"
    run_dir = OUTPUT_ROOT / run_name
    run_dir.mkdir(parents=True, exist_ok=True)

    input_path = run_dir / "frog_input.txt"
    frog_output_path = run_dir / "frog_output.tsv"
    rows_path = run_dir / "annotated_subtlex_rows.tsv"
    metadata_path = run_dir / "metadata.json"
    qc_path = run_dir / "qc_report.md"

    started = time.perf_counter()
    input_meta = write_frog_input(input_path, args.limit_mib)
    frog_meta = run_frog(
        run_dir,
        input_path,
        frog_output_path,
        args.backend,
        native_prefix=args.native_prefix,
        frog_threads=args.frog_threads,
    )
    if frog_meta["returncode"] != 0:
        metadata_path.write_text(
            json.dumps({"input": input_meta, "frog": frog_meta}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        raise SystemExit(f"Frog failed, see {metadata_path}")

    counter = parse_annotated_output(frog_output_path)
    exported_rows = write_rows(counter, rows_path, args.top)
    write_qc(counter, qc_path, rows_path)

    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "corpus": str(CORPUS),
        "run_name": run_name,
        "limit_mib": args.limit_mib,
        "top": args.top,
        "requested_backend": args.backend,
        "selected_backend": frog_meta["backend"],
        "image": FROG_IMAGE,
        "native_prefix": frog_meta.get("native_prefix"),
        "native_frog": frog_meta.get("native_frog") or str(NATIVE_FROG),
        "frog_threads": args.frog_threads,
        "doc_sentinel": DOC_SENTINEL,
        "input": input_meta,
        "frog": frog_meta,
        "total_elapsed_seconds": time.perf_counter() - started,
        "total_documents": counter.total_documents,
        "total_tokens": counter.total_tokens,
        "unique_words": len(counter.word_freq),
        "exported_rows": exported_rows,
        "paths": {
            "input": str(input_path),
            "frog_output": str(frog_output_path),
            "rows": str(rows_path),
            "qc": str(qc_path),
        },
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {metadata_path}")
    print(f"Wrote {rows_path}")
    print(f"Wrote {qc_path}")
    print(
        f"documents={counter.total_documents} tokens={counter.total_tokens} "
        f"unique={len(counter.word_freq)} elapsed={metadata['total_elapsed_seconds']:.2f}s"
    )


if __name__ == "__main__":
    main()
