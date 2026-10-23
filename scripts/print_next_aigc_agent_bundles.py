#!/usr/bin/env python3
"""Print next pending subagent bundles and reusable worker prompts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_DIR = ROOT / "outputs" / "aigc_agent_replacement_v1"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", default="sense", choices=["sense", "example_translation"])
    parser.add_argument("--bundles", type=int, default=6)
    parser.add_argument("--bundle-size", type=int, default=5)
    args = parser.parse_args()

    manifest = json.loads((BASE_DIR / "chunk_manifest.json").read_text(encoding="utf-8"))
    pending = [
        chunk
        for chunk in manifest["chunks"]
        if chunk["kind"] == args.kind and not Path(chunk["output"]).exists()
    ]

    for bundle_index in range(args.bundles):
        bundle = pending[bundle_index * args.bundle_size : (bundle_index + 1) * args.bundle_size]
        if not bundle:
            break
        chunk_ids = [chunk["chunk_id"] for chunk in bundle]
        print(f"bundle_{bundle_index + 1}: {' '.join(chunk_ids)}")
        print(prompt_for(args.kind, chunk_ids))
        print("---")

    print(f"pending_{args.kind}_chunks={len(pending)}")


def prompt_for(kind: str, chunk_ids: list[str]) -> str:
    folder = "sense" if kind == "sense" else "example_translation"
    ids = ", ".join(f"`{chunk_id}`" for chunk_id in chunk_ids)
    return f"""You are one worker in a Dutch lexicon AIGC replacement project. You are not alone in the workspace; do not edit outside assigned chunk folders and do not revert others' work.

Process these chunks in `/Users/cedar/Desktop/dutch-corpus`: {ids}.

For each chunk:
1. Read `/Users/cedar/Desktop/dutch-corpus/outputs/aigc_agent_replacement_v1/chunks/{folder}/<chunk_id>/instructions.md` and `input.tsv`.
2. Write only `/Users/cedar/Desktop/dutch-corpus/outputs/aigc_agent_replacement_v1/chunks/{folder}/<chunk_id>/output.tsv`.
3. `batch_id` must exactly equal that chunk_id for every row.
4. Preserve IDs/POS exactly; generated natural-language fields must end with literal `#aigc`; IDs/POS/confidence/batch_id must not contain `#aigc`.
5. No tabs or newlines inside fields.
6. Generate high-quality content using the evidence critically; if evidence is mismatched, write conservative content and flag it in quality_note.
7. Run validation for each chunk, e.g. `python3 scripts/validate_aigc_agent_replacement_outputs.py --chunk-id <chunk_id> --report outputs/aigc_agent_replacement_v1/validation_<chunk_id>.json`; fix until it passes.

Return a concise summary listing each chunk, row count, validation status, and uncertain items."""


if __name__ == "__main__":
    main()
