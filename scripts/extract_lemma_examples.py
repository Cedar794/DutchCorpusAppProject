#!/usr/bin/env python3
"""Extract lemma/POS/form-level example candidates from local CC100 text."""

from __future__ import annotations

import argparse
import csv
import json
import lzma
import re
import subprocess
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "nl.txt.xz"
DEFAULT_OUTPUT = ROOT / "outputs" / "app_enrichment" / "lemma_examples"
TOKEN_RE = re.compile(r"[0-9A-Za-zÀ-ÖØ-öø-ÿ]+(?:['’-][0-9A-Za-zÀ-ÖØ-öø-ÿ]+)*")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
BAD_LINE_RE = re.compile(r"https?://|www\.|<[^>]+>|cookie|javascript", re.I)


def run_psql_csv(container: str, sql: str) -> list[dict[str, str]]:
    command = [
        "docker",
        "exec",
        container,
        "psql",
        "-U",
        "postgres",
        "-d",
        "postgres",
        "-c",
        f"copy ({sql}) to stdout with csv header",
    ]
    result = subprocess.run(command, check=True, text=True, capture_output=True)
    return list(csv.DictReader(result.stdout.splitlines()))


def target_query(target_limit: int, forms_per_pos: int) -> str:
    return f"""
with form_scores as (
  select
    l.id as lemma_id,
    p.id as lemma_pos_entry_id,
    f.id as form_id,
    f.form,
    f.form_norm,
    l.level,
    coalesce(pt.app_pos, 'unknown') as app_pos,
    max(coalesce(fs.freq_count, 0)) as freq_count,
    max(case when f.is_canonical then 1 else 0 end) as is_canonical_int
  from public.forms f
  join public.lemmas l on l.id = f.lemma_id
  join public.lemma_pos_entries p on p.id = f.lemma_pos_entry_id
  join public.pos_tags pt on pt.tag = p.pos
  left join public.form_corpus_stats fs on fs.form_id = f.id
  where pt.is_content_pos
    and length(f.form_norm) between 2 and 40
    and f.form_norm ~ '[[:alpha:]]'
  group by l.id, p.id, f.id, f.form, f.form_norm, l.level, pt.app_pos
),
ranked as (
  select *,
    row_number() over (
      partition by lemma_pos_entry_id
      order by freq_count desc, is_canonical_int desc, length(form_norm), form_norm
    ) as pos_form_rank
  from form_scores
)
select
  lemma_id::text,
  lemma_pos_entry_id::text,
  form_id::text,
  form,
  form_norm,
  level::text,
  app_pos,
  freq_count::text
from ranked
where pos_form_rank <= {forms_per_pos}
order by level, freq_count desc, form_norm
limit {target_limit}
""".strip()


def normalize_token(token: str) -> str:
    return token.lower()


def iter_sentences(path: Path, max_lines: int | None):
    with lzma.open(path, "rt", encoding="utf-8", errors="replace") as handle:
        for line_no, line in enumerate(handle, start=1):
            if max_lines and line_no > max_lines:
                break
            line = " ".join(line.strip().split())
            if not line or len(line) < 20 or BAD_LINE_RE.search(line):
                continue
            for sentence in SENTENCE_SPLIT_RE.split(line):
                sentence = sentence.strip()
                if sentence:
                    yield line_no, sentence


def score_sentence(sentence: str, token_count: int) -> float:
    score = 0.85
    if 8 <= token_count <= 18:
        score += 0.08
    if any(ch.isdigit() for ch in sentence):
        score -= 0.08
    if len(sentence) > 180:
        score -= 0.08
    return max(0.4, min(score, 0.98))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--container", default="supabase_db_dutch-corpus-database")
    parser.add_argument("--corpus", type=Path, default=CORPUS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--target-limit", type=int, default=12000)
    parser.add_argument("--forms-per-pos", type=int, default=2)
    parser.add_argument("--per-lemma-pos", type=int, default=2)
    parser.add_argument("--max-lines", type=int)
    parser.add_argument("--min-tokens", type=int, default=5)
    parser.add_argument("--max-tokens", type=int, default=30)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    target_rows = run_psql_csv(args.container, target_query(args.target_limit, args.forms_per_pos))
    by_form: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in target_rows:
        by_form[row["form_norm"]].append(row)

    counts: dict[tuple[str, str], int] = defaultdict(int)
    seen_examples: set[tuple[str, str, str]] = set()
    examples: list[dict[str, str]] = []
    active_targets = {(row["lemma_id"], row["lemma_pos_entry_id"]) for row in target_rows}

    for line_no, sentence in iter_sentences(args.corpus, args.max_lines):
        tokens = [normalize_token(match.group(0)) for match in TOKEN_RE.finditer(sentence)]
        if not (args.min_tokens <= len(tokens) <= args.max_tokens):
            continue
        matched_forms = {token for token in tokens if token in by_form}
        if not matched_forms:
            continue
        quality = f"{score_sentence(sentence, len(tokens)):.3f}"
        for form_norm in matched_forms:
            for target in by_form[form_norm]:
                key = (target["lemma_id"], target["lemma_pos_entry_id"])
                if counts[key] >= args.per_lemma_pos:
                    continue
                dedupe = (target["lemma_id"], target["lemma_pos_entry_id"], sentence)
                if dedupe in seen_examples:
                    continue
                seen_examples.add(dedupe)
                counts[key] += 1
                examples.append(
                    {
                        "lemma_id": target["lemma_id"],
                        "lemma_pos_entry_id": target["lemma_pos_entry_id"],
                        "form_id": target["form_id"],
                        "ex_nl": sentence,
                        "source_key": "cc100_lemma_examples_v1",
                        "external_id": f"cc100-line:{line_no}:form:{target['form_id']}",
                        "quality_score": quality,
                        "raw_payload": json.dumps(
                            {
                                "line_no": line_no,
                                "matched_form_norm": form_norm,
                                "token_count": len(tokens),
                                "app_pos": target["app_pos"],
                                "level": target["level"],
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                    }
                )
                if counts[key] >= args.per_lemma_pos:
                    active_targets.discard(key)
        if not active_targets:
            break

    out_path = args.output_dir / "lemma_examples.tsv"
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "lemma_id",
                "lemma_pos_entry_id",
                "form_id",
                "ex_nl",
                "source_key",
                "external_id",
                "quality_score",
                "raw_payload",
            ],
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(examples)

    manifest = {
        "target_rows": len(target_rows),
        "target_lemma_pos": len({(row["lemma_id"], row["lemma_pos_entry_id"]) for row in target_rows}),
        "examples": len(examples),
        "covered_lemma_pos": len(counts),
        "output_tsv": str(out_path),
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
