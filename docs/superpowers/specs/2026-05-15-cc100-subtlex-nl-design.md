# CC-100 Dutch SUBTLEX-Style Frequency Design

## Goal

Generate a rigorous Dutch CC-100 word frequency table whose output columns match the local `SUBTLEX-NL with pos and Zipf.xlsx` workbook as closely as possible, without using LLMs for full-corpus annotation.

## Inputs

- `nl.txt.xz`: Dutch CC-100 text corpus, XZ compressed, 29.3 GiB uncompressed.
- `SUBTLEX-NL with pos and Zipf.xlsx`: reference workbook for field names, formulas, and formatting expectations.

## Outputs

- Full results in compressed CSV/TSV form.
- Excel workbook containing the highest-frequency rows that fit Excel limits.
- Metadata file documenting corpus totals, CD definition, formulas, NLP tool versions, and run settings.
- QC report documenting validation checks and representative samples.

## Corpus Unit

CC-100 does not provide the movie-level units used by SUBTLEX-NL. This project defines one input line as one document unit for `CDcount`, `CDlow`, `SUBTLEXCD`, and `Lg10CD`. The metadata must state this explicitly so the table is not mistaken for movie-level contextual diversity.

## Annotation

The preferred annotator is Frog/Tadpole-family Dutch NLP tooling because it provides tokenization, POS tagging, and lemmatization for Dutch and is closest to the original SUBTLEX-NL processing lineage. The full run should disable unnecessary modules such as parsing and NER where the tool allows it.

Current local annotator choice: `local/frog-llvm-omp`, built from source with Homebrew LLVM Clang and libomp. It is stable on smoke tests, but Frog's own `--threads` flag gives only a small speedup, so full runs should use multiple independent Frog processes over corpus shards.

If Frog cannot be installed cleanly on this machine, the fallback is a deterministic Dutch tokenizer plus a documented alternative POS/lemma tool such as Stanza or spaCy. The fallback must be marked in metadata because POS and lemma fields will not be directly comparable to Frog/Tadpole-style output.

## Counting Model

The pipeline streams compressed input, annotates text in batches, writes intermediate shard files, and merges them at the end. It should not require a full 29.3 GiB decompressed file or all counters in memory at once.

Implemented annotated production skeleton:

- `scripts/run_annotated_batches.py` writes per-batch Frog input, calls Frog, parses output, and stores compact gzip count shards.
- `scripts/merge_annotated_batches.py` merges count shards into SQLite and exports the 17 SUBTLEX-style columns.
- `scripts/export_top_xlsx.py` writes top merged TSV rows to XLSX with the same 17 columns.
- `scripts/qc_report.py` validates headers, formulas, totals, row order, and POS/lemma field consistency.
- Intermediate token-level Frog TSV is not retained by default.
- Low-disk mode uses `scripts/run_annotated_batches.py --live-merge` to merge each count shard into SQLite immediately and delete the shard after a successful merge.
- `scripts/merge_annotated_batches.py --use-existing-db` exports from the live SQLite DB without requiring shard files.

For every token, the pipeline tracks:

- lowercase word form;
- whether the original token was lowercase;
- source document unit;
- POS;
- lemma;
- POS+lemma corpus frequency.

The final rows are sorted by `FREQcount` descending, then `Word` ascending for deterministic output.

## Field Formulas

- `SUBTLEXWF = FREQcount / total_tokens * 1,000,000`.
- `Zipf = log10(FREQcount / total_tokens * 1,000,000,000)`.
- `SUBTLEXCD = CDcount / total_documents * 100`.
- `Lg10CD = log10(CDcount)`.
- Dot-delimited POS fields follow the local SUBTLEX style: `.POS1.POS2.` and `.freq1.freq2.`.

## Quality Control

The first production milestone is a pilot over a bounded corpus prefix. The pilot must verify:

- tool installation and version capture;
- throughput;
- sample POS and lemma output;
- count invariants;
- derived formula recomputation;
- top-frequency sanity.

Full-corpus execution should start only after pilot output is internally consistent.

## Calibration Status

The best local calibration so far is:

- Command: `/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/run_annotated_batches.py --max-lines 32000 --batch-lines 4000 --workers 8 --run-name annotated_calib_32000l_b4000_w8 --backend native --native-prefix local/frog-llvm-omp --frog-threads 1`
- Result: 734,639 counted tokens in 108.08 seconds, about 6,797 token/s.
- Projection for the 4,979,340,333-token full corpus estimate: about 203.5 hours / 8.48 days.
- Recommended production settings: `--workers 8 --batch-lines 4000 --frog-threads 1`.
- The 5,000-row calibration TSV, XLSX, and QC report passed formula and field-invariant checks.

Full production run started with low-disk mode:

- Run name: `annotated_full_live_w8_b4000`.
- Start script: `scripts/start_full_live_run.sh`.
- Process manager: detached `screen` session, because ordinary `nohup` did not persist in the Codex shell context and LaunchAgent hit macOS Desktop/TCC access issues.
- First 8 batches completed and live-merged successfully, with `counts/` remaining 0B.
