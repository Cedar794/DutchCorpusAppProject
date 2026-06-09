#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import lzma
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "nl.txt.xz"
OUTPUT_DIR = ROOT / "outputs"

sys.path.insert(0, str(ROOT))

from cc100_subtlex.core import count_token_lines, subtlex_cd, subtlex_wf, zipf_frequency


def iter_limited_lines(path: Path, limit_bytes: int) -> Iterator[str]:
    read_bytes = 0
    with lzma.open(path, "rt", encoding="utf-8", errors="replace", newline="") as handle:
        for line in handle:
            encoded_len = len(line.encode("utf-8", errors="replace"))
            if read_bytes + encoded_len > limit_bytes and read_bytes > 0:
                break
            read_bytes += encoded_len
            yield line


def write_top_words(result, limit: int, output_path: Path) -> None:
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(
            "Word\tFREQcount\tCDcount\tFREQlow\tCDlow\tSUBTLEXWF\tZipf\tSUBTLEXCD\tLg10CD\n"
        )
        for word, freq in result.word_freq.most_common(limit):
            cd = result.word_doc_freq[word]
            low_freq = result.word_low_freq[word]
            low_cd = result.word_low_doc_freq[word]
            handle.write(
                "\t".join(
                    [
                        word,
                        str(freq),
                        str(cd),
                        str(low_freq),
                        str(low_cd),
                        f"{subtlex_wf(freq, result.total_tokens):.10f}",
                        f"{zipf_frequency(freq, result.total_tokens):.10f}",
                        f"{subtlex_cd(cd, result.total_documents):.10f}",
                        f"{math.log10(cd):.10f}",
                    ]
                )
                + "\n"
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit-mib", type=int, default=256)
    parser.add_argument("--top", type=int, default=1000)
    args = parser.parse_args()

    limit_bytes = args.limit_mib * 1024 * 1024
    started = time.perf_counter()
    result = count_token_lines(iter_limited_lines(CORPUS, limit_bytes))
    elapsed = time.perf_counter() - started

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    top_path = OUTPUT_DIR / "pilot_top_words.tsv"
    write_top_words(result, args.top, top_path)

    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "corpus": str(CORPUS),
        "limit_mib": args.limit_mib,
        "elapsed_seconds": elapsed,
        "throughput_tokens_per_second": result.total_tokens / elapsed if elapsed else None,
        "total_documents": result.total_documents,
        "total_tokens": result.total_tokens,
        "unique_words": len(result.word_freq),
        "top_words_path": str(top_path),
        "top_25": result.word_freq.most_common(25),
    }
    metadata_path = OUTPUT_DIR / "pilot_token_counts.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {metadata_path}")
    print(f"Wrote {top_path}")
    print(
        f"documents={result.total_documents} tokens={result.total_tokens} "
        f"unique={len(result.word_freq)} elapsed={elapsed:.2f}s"
    )


if __name__ == "__main__":
    main()
