# Dutch CC-100 SUBTLEX-Style Frequency Project Notes

Last updated: 2026-05-15

## Goal

Build a SUBTLEX-NL-style word frequency table from the local Dutch CC-100 corpus without using LLMs for full-corpus annotation.

## Local Files

- `SUBTLEX-NL with pos and Zipf.xlsx`
  - 36 MB.
  - One worksheet: `Sheet1`.
  - 437,503 data rows, 17 columns.
- `nl.txt.xz`
  - 7.8 GB compressed.
  - XZ metadata reports 29.3 GiB / 31,485,245,121 bytes uncompressed.
  - Sample format: one Dutch web/text segment per line.

## Local Machine

- Apple M4 Mac mini.
- 10 CPU cores.
- 16 GB RAM.
- Around 83-85 GB free disk at project start.
- AC power.

## SUBTLEX Target Columns

The source workbook columns are:

1. `Word`
2. `FREQcount`
3. `CDcount`
4. `FREQlow`
5. `CDlow`
6. `FREQlemma`
7. `SUBTLEXWF`
8. `Zipf`
9. `SUBTLEXCD`
10. `Lg10CD`
11. `dominant.pos`
12. `dominant.pos.freq`
13. `dominant.pos.lemma`
14. `dominant.pos.lemma.freq`
15. `all.pos`
16. `all.pos.freq`
17. `all.pos.lemma.freq`

Observed SUBTLEX totals:

- Sum of `FREQcount`: 43,729,424.
- Maximum `CDcount`: 8,070.
- `SUBTLEXWF = FREQcount / total_tokens * 1,000,000`.
- `Zipf = log10(FREQcount / total_tokens * 1,000,000,000)`.
- `SUBTLEXCD = CDcount / total_documents * 100`.
- `Lg10CD = log10(CDcount)`.

## CC-100 Field Mapping Decisions

- `Word`: lowercase normalized token type.
- `FREQcount`: total occurrences of the lowercase token type across all original case forms.
- `CDcount`: number of corpus document units containing the token type.
- `FREQlow`: occurrences where the original token form is lowercase.
- `CDlow`: number of corpus document units containing at least one lowercase original form.
- `FREQlemma`: total corpus frequency of the lemma(s) associated with this word, summed through the POS+lemma records used by the word.
- `SUBTLEXWF`: frequency per million words.
- `Zipf`: log10 frequency per billion words.
- `SUBTLEXCD`: percent of document units containing the word.
- `Lg10CD`: log10 of `CDcount`.
- `dominant.pos`: most frequent POS for the word.
- `dominant.pos.freq`: frequency of the word under the dominant POS.
- `dominant.pos.lemma`: most frequent lemma for the word under the dominant POS.
- `dominant.pos.lemma.freq`: full-corpus frequency of that dominant POS+lemma.
- `all.pos`: all POS values for the word, ordered by descending word POS frequency, wrapped in dot delimiters to match SUBTLEX style.
- `all.pos.freq`: corresponding word POS frequencies, dot-delimited.
- `all.pos.lemma.freq`: corresponding full-corpus POS+lemma frequencies, dot-delimited.

Important caveat: SUBTLEX-NL `CDcount` counts movies. CC-100 has no movie/document ID. This project defines the document unit as one input line unless later changed after pilot inspection.

## Preferred NLP Approach

- Full-corpus annotation should not use LLMs.
- Preferred Dutch NLP tool: Frog/Tadpole-family pipeline because it is closest to the original SUBTLEX-NL processing lineage.
- Use only the modules required for tokenization, POS tagging, and lemmatization.
- Avoid dependency parsing, NER, or other expensive modules for the full run.
- Use Stanza or spaCy only for sample QC if needed, not as the primary full-corpus source.

## Pipeline Shape

1. Stream `nl.txt.xz` directly; do not write a full decompressed copy.
2. Normalize text with Unicode NFC.
3. Filter only clearly bad lines in the first version:
   - empty/whitespace lines;
   - severe URL/HTML/noise lines if pilot confirms a threshold;
   - exact duplicate lines if memory/disk strategy is acceptable.
4. Send batches of lines to the NLP annotator.
5. Aggregate counts into bounded shard files rather than holding everything in RAM.
6. Merge shards.
7. Calculate derived SUBTLEX-style fields.
8. Export:
   - full compressed CSV/TSV for complete results;
   - Excel workbook for the highest-frequency rows that fit Excel's row limit;
   - metadata and QC report.

## Expected Outputs

- `outputs/cc100_subtlex_nl_top.xlsx`
- `outputs/cc100_subtlex_nl_full.csv.xz`
- `outputs/cc100_subtlex_nl_metadata.json`
- `outputs/cc100_subtlex_nl_qc_report.md`

## Quality Gates

- Pilot first, then full run.
- Validate invariants:
  - `FREQlow <= FREQcount`.
  - `CDlow <= CDcount`.
  - `sum(FREQcount) == total emitted tokens`.
  - For each word, sum of `all.pos.freq` equals `FREQcount`.
  - `SUBTLEXWF`, `Zipf`, `SUBTLEXCD`, and `Lg10CD` recompute from stored totals.
- Inspect top frequency rows manually.
- Record tool versions and exact commands.
- Keep all long-run commands resumable or checkpointed.

## Current Status

- User approved starting the project on 2026-05-15.
- Directory is not a git repository, so no commits are expected.
- Frog and ucto were not installed at start.
- Homebrew is available at `/opt/homebrew/bin/brew`.
- Homebrew has no `frog` or `ucto` formula on this machine.
- Docker command exists at `/usr/local/bin/docker`, but the Docker daemon was not running during the first probe.
- Docker Desktop was started successfully later; daemon reports version 29.2.1, Linux/aarch64.
- Docker Hub CLI checks for `proycon/lamachine:latest` and `docker search lamachine` initially hung for nearly 2 minutes and were killed.
- Docker Desktop later worked and `proycon/lamachine:latest` was usable for annotated pilots, but amd64 emulation is too slow for the full corpus.
- Created project docs:
  - `docs/superpowers/specs/2026-05-15-cc100-subtlex-nl-design.md`
  - `docs/superpowers/plans/2026-05-15-cc100-subtlex-nl.md`
- Created code/tests:
  - `cc100_subtlex/core.py`
  - `cc100_subtlex/frog.py`
  - `cc100_subtlex/annotated.py`
  - `tests/test_core.py`
  - `tests/test_frog.py`
  - `tests/test_annotated.py`
  - `tests/test_batches.py`
  - `tests/test_merge_annotated_batches.py`
  - `tests/test_pilot_annotated_counts.py`
  - `tests/test_export_top_xlsx.py`
  - `tests/test_qc_report.py`
  - `scripts/probe_environment.py`
  - `scripts/inspect_subtlex_reference.py`
  - `scripts/pilot_token_counts.py`
  - `scripts/probe_frog.py`
  - `scripts/run_token_count_batches.py`
  - `scripts/merge_token_count_batches.py`
  - `scripts/pilot_annotated_counts.py`
  - `scripts/run_annotated_batches.py`
  - `scripts/merge_annotated_batches.py`
  - `scripts/export_top_xlsx.py`
  - `scripts/qc_report.py`
  - `scripts/start_full_live_run.sh`
  - `scripts/run_full_live_worker.sh`
  - `scripts/build_native_frog.sh`
- Tests passed:
  - `/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests/test_core.py tests/test_frog.py -v`
  - Latest expanded command: `/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests/test_core.py tests/test_frog.py tests/test_batches.py -v`
  - Latest full command after XLSX/QC work: `/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests/test_core.py tests/test_frog.py tests/test_batches.py tests/test_annotated.py tests/test_pilot_annotated_counts.py tests/test_merge_annotated_batches.py tests/test_export_top_xlsx.py tests/test_qc_report.py -v`
  - Latest full result: 24 tests, all passed.
- Generated probe outputs:
  - `outputs/environment_probe.json`
  - `outputs/subtlex_reference_profile.json`
  - `outputs/frog_probe.json`
  - `outputs/frog_sample.tsv`
- Completed tokenizer/CD pilots:
  - 8 MiB smoke: 56,973 document units, 1,330,795 tokens, 81,663 unique words, 1.08 seconds.
  - 256 MiB pilot: 1,802,136 document units, 42,498,511 tokens, 787,108 unique words, 36.52 seconds.
  - 1024 MiB pilot: 7,198,213 document units, 169,810,524 tokens, 1,956,354 unique words, 152.15 seconds.
- Preserved 1024 MiB pilot outputs:
  - `outputs/pilot_token_counts_1024mib.json`
  - `outputs/pilot_top_words_1024mib.tsv`
- Full-corpus projection from 1024 MiB prefix:
  - scale factor to 29.3 GiB uncompressed: about 29.32x.
  - estimated document units: about 211,072,620.
  - estimated word tokens: about 4,979,340,333.
  - pure tokenizer/CD runtime at same throughput: about 1.24 hours, but a production full run still needs shard-based aggregation to control memory.
- Added batch-based token counting:
  - smoke command: `/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/run_token_count_batches.py --limit-mib 8 --batch-lines 20000 --run-name smoke_8mib`
  - merge command: `/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/merge_token_count_batches.py --run-name smoke_8mib --top 25`
  - smoke output directory: `outputs/token_count_batches/smoke_8mib/`
  - Found and fixed one merge bug: the parser skipped any row starting with `word\t`, which dropped the real Dutch/English token `word`; it now skips only the exact header line.
  - Verified direct 8 MiB count and batch+merge have identical unique-word sets: 81,663 words, zero set difference.
  - 256 MiB batch benchmark: 1,891,059 input lines, 1,802,136 token-bearing document units, 42,498,511 tokens, 787,108 unique words.
  - 256 MiB batch timing: 37.09 seconds for batch counting, 2.36 seconds for SQLite merge/export top 1,000.
  - 256 MiB batch storage: 8.5 MB gzip batch files, 38 MB SQLite DB, 46 MB total run directory.

## Annotated Frog Status

- Added annotated counting code and tests:
  - `cc100_subtlex/annotated.py`
  - `tests/test_annotated.py`
  - `tests/test_pilot_annotated_counts.py`
  - `tests/test_merge_annotated_batches.py`
  - `scripts/pilot_annotated_counts.py`
  - `scripts/run_annotated_batches.py`
  - `scripts/merge_annotated_batches.py`
  - `scripts/build_native_frog.sh`
- `scripts/pilot_annotated_counts.py` now supports:
  - `--backend auto|native|docker`
  - `--native-prefix`
  - `--frog-threads`
  - automatic preference for `local/frog-llvm-omp` over `local/frog` when present.
- Frog build prefixes:
  - `local/frog`: native Apple Clang build, stable.
  - `local/frog-llvm-omp`: Homebrew LLVM Clang + libomp build, stable.
  - `local/frog-omp`: GCC/libstdc++ OpenMP build; compiles only after patches but segfaults at lemmatizer initialization. Do not use for production.
- Build script modes:
  - default Apple Clang build: `bash scripts/build_native_frog.sh`
  - LLVM/libomp build: `FROG_USE_LLVM=1 FROG_PREFIX="$PWD/local/frog-llvm-omp" FROG_SRC_DIR="$PWD/deps/src-llvm" FROG_LOG_DIR="$PWD/outputs/native_build_logs_llvm_omp" bash scripts/build_native_frog.sh`
  - GCC build is retained only as an experiment.
- Annotated 1 MiB pilot results:
  - Docker/LaMachine amd64 emulation: 233.13 seconds for 169,267 counted tokens.
  - Native Apple Clang `local/frog`: 121.28 seconds total; Frog elapsed 120.62 seconds.
  - LLVM/libomp `local/frog-llvm-omp --threads=1`: Frog total 108.37 seconds; wall clock `real 110.29`.
  - LLVM/libomp `local/frog-llvm-omp --threads=8`: Frog total 104.15 seconds; wall clock `real 105.98`.
  - `--threads=8` output was byte-identical to `--threads=1`, but speedup was only about 4 percent, so Frog's own thread flag is not a useful full-corpus accelerator here.
- Current runtime implication:
  - Single Frog process remains roughly tens of days for the full 5B-token corpus.
  - Full production annotation should use multi-process sharding with one or low Frog thread count per process, plus shard-local aggregation and SQLite/streaming merge.
  - Do not store full token-level Frog TSV for the whole corpus; parse each shard output into compact count shards and delete/optionally compress token TSVs.

## Annotated Batch/Merge Status

- Annotated shard runner:
  - `scripts/run_annotated_batches.py`
  - Streams `nl.txt.xz` directly.
  - Writes per-batch Frog input with `zzzzccdocboundaryzzzz` sentinels.
  - Runs Frog with `--skip=mpcn` and configurable `--backend`, `--native-prefix`, `--frog-threads`, `--workers`, `--batch-lines`, `--limit-mib`, and `--max-lines`.
  - Parses token-level Frog TSV immediately into compact gzip count shards.
  - Deletes intermediate Frog input/output by default unless `--keep-intermediate` is set.
  - Writes `manifest.json` and per-batch metadata.
- Annotated merge/export:
  - `scripts/merge_annotated_batches.py`
  - Merges count shards into `merged_annotated_counts.sqlite`.
  - Exports TSV with the same 17 columns and order as `SUBTLEX-NL with pos and Zipf.xlsx`.
  - Reconstructs `FREQlemma`, `dominant.pos.*`, `all.pos`, `all.pos.freq`, and `all.pos.lemma.freq` from the four count families.
- Real smoke runs:
  - Single-batch command:
    - `/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/run_annotated_batches.py --limit-mib 0 --batch-lines 1 --workers 1 --run-name annotated_batch_smoke --backend native --native-prefix local/frog-llvm-omp --frog-threads 1 --keep-intermediate`
    - Result: 1 input line, 39 counted tokens, 32 unique words, 1 gzip count shard.
    - Merge command: `/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/merge_annotated_batches.py --run-name annotated_batch_smoke --top 20`
  - Multi-batch command:
    - `/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/run_annotated_batches.py --max-lines 2 --batch-lines 1 --workers 2 --run-name annotated_multibatch_smoke --backend native --native-prefix local/frog-llvm-omp --frog-threads 1`
    - Result: 2 input lines, 2 token-bearing document units, 64 counted tokens, 46 unique words after merge.
    - Merge command: `/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/merge_annotated_batches.py --run-name annotated_multibatch_smoke --top 25`
    - Output: `outputs/annotated_batches/annotated_multibatch_smoke/merged_annotated_counts_top.tsv`
- Production shape after this milestone:
  - Use `local/frog-llvm-omp` with `--frog-threads 1`.
  - Scale through `--workers` multi-process sharding, not Frog's internal `--threads`.
  - Choose `--batch-lines` by pilot memory/runtime behavior; larger batches reduce Frog startup overhead but increase temporary TSV size.
  - Keep `--resume` available for interrupted runs.

## Annotated Calibration Results

- `annotated_calib_2000l_b500_w4`
  - Command: `/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/run_annotated_batches.py --max-lines 2000 --batch-lines 500 --workers 4 --run-name annotated_calib_2000l_b500_w4 --backend native --native-prefix local/frog-llvm-omp --frog-threads 1`
  - Result: 2,000 input lines, 1,931 token-bearing document units, 42,991 tokens, 8,204 unique words after merge.
  - Runtime: 9.83 seconds, about 4,374 token/s.
  - Full 4.98B-token projection at this speed: about 316 hours / 13.2 days.
- `annotated_calib_8000l_b1000_w8`
  - Command: `/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/run_annotated_batches.py --max-lines 8000 --batch-lines 1000 --workers 8 --run-name annotated_calib_8000l_b1000_w8 --backend native --native-prefix local/frog-llvm-omp --frog-threads 1`
  - Result: 8,000 input lines, 7,658 token-bearing document units, 195,277 tokens, 23,753 unique words after merge.
  - Runtime: 32.53 seconds, about 6,002 token/s.
  - Full projection: about 230 hours / 9.6 days.
- `annotated_calib_32000l_b4000_w8`
  - Command: `/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/run_annotated_batches.py --max-lines 32000 --batch-lines 4000 --workers 8 --run-name annotated_calib_32000l_b4000_w8 --backend native --native-prefix local/frog-llvm-omp --frog-threads 1`
  - Result: 32,000 input lines, 30,569 token-bearing document units, 734,639 tokens, 57,735 unique words after merge.
  - Runtime: 108.08 seconds, about 6,797 token/s.
  - Full projection: about 203.5 hours / 8.48 days.
  - Run directory size after merge/export/QC: about 20 MB; count shards 2.4 MB; SQLite DB 17 MB.
  - Output samples:
    - `outputs/annotated_batches/annotated_calib_32000l_b4000_w8/merged_annotated_counts_top.tsv`
    - `outputs/annotated_batches/annotated_calib_32000l_b4000_w8/merged_annotated_counts_top.xlsx`
    - `outputs/annotated_batches/annotated_calib_32000l_b4000_w8/qc_report.md`
  - QC passed for 5,000 exported top rows: headers match SUBTLEX workbook, formulas recompute, sort/order and POS/lemma field invariants pass.

Current production recommendation:

- Use `--workers 8 --batch-lines 4000 --frog-threads 1 --backend native --native-prefix local/frog-llvm-omp`.
- Expected annotation runtime on this Mac mini is roughly 8.5 days, excluding final full SQLite merge/export.
- Do not retain token-level Frog TSVs for the full run.
- Ensure at least 60 GB free disk before full annotation. The final SQLite DB may be much larger than pilot linear scaling because unique vocabulary and POS/lemma combinations continue to grow.

## Export and QC Status

- Added `scripts/export_top_xlsx.py`.
  - Reads a merged annotated TSV and writes an XLSX workbook with exactly the 17 SUBTLEX-style columns.
  - Default output for a run: `outputs/annotated_batches/<run_name>/merged_annotated_counts_top.xlsx`.
  - Default row limit is 50,000; `--top 0` exports up to Excel's row limit.
- Added `scripts/qc_report.py`.
  - Validates headers against the pipeline and the reference SUBTLEX workbook profile.
  - Checks manifest/merge totals, formula recomputation, descending frequency order, and POS/lemma dot-list consistency.
  - Default output for a run: `outputs/annotated_batches/<run_name>/qc_report.md`.

## Low-Disk Full Run Status

- Added low-disk live merge mode to `scripts/run_annotated_batches.py`.
  - New flags:
    - `--live-merge`
    - `--keep-count-shards`
    - `--merge-chunk-size`
  - In live merge mode, each completed gzip count shard is merged into `merged_annotated_counts.sqlite` immediately.
  - Unless `--keep-count-shards` is set, the shard is deleted immediately after a successful merge.
  - The SQLite table `merged_batches` records which batch indexes have already been merged, so `--resume` does not double-count them.
- Added `--use-existing-db` to `scripts/merge_annotated_batches.py`.
  - This exports top/full TSV from a live-merged SQLite DB without needing count shard files.
- Low-disk smoke run:
  - Command: `/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/run_annotated_batches.py --max-lines 8 --batch-lines 2 --workers 2 --run-name annotated_live_smoke --backend native --native-prefix local/frog-llvm-omp --frog-threads 1 --live-merge`
  - Result: 8 input lines, 146 tokens, 4 merged batches.
  - `counts/` remained 0B.
  - Existing-DB export, XLSX export, QC, and live `--resume` all passed.
- Full low-disk run:
  - Run name: `annotated_full_live_w8_b4000`
  - Start command: `/Users/cedar/Desktop/dutch-corpus/scripts/start_full_live_run.sh annotated_full_live_w8_b4000`
  - Actual process manager: detached `screen` session `dutch_full_annotated_full_live_w8_b4000`.
  - `nohup` was not reliable in this Codex execution context because child processes were cleaned up after the shell call.
  - LaunchAgent was also not suitable because launchd-started Python hung while opening code under `~/Desktop`, likely due macOS Desktop/TCC access restrictions.
  - Current log path at start: `outputs/annotated_batches/annotated_full_live_w8_b4000/logs/run_20260515T133440Z.log`
  - Current error log path at start: `outputs/annotated_batches/annotated_full_live_w8_b4000/logs/run_20260515T133440Z.err.log`
  - First 8 production batches completed and live-merged:
    - 30,569 token-bearing document units.
    - 734,639 tokens.
    - 57,735 unique words.
    - SQLite `merged_batches` count: 8.
    - `word_counts` frequency sum: 734,639.
    - `counts/` size: 0B.
    - Disk free after first 8 batches: 57GiB.
- Runtime incident on 2026-05-16:
  - The process stopped after batch 4692 with `PermissionError: [Errno 1] Operation not permitted` while deleting `counts/batch-004692.tsv.gz`.
  - Investigation showed batch 4692 had already been merged into SQLite before the delete failed:
    - SQLite `merged_batches` included 4692.
    - `word_counts` frequency sum matched merged token totals.
    - Manifest had only been written through batch 4691 because the exception occurred before manifest update.
  - Code fix: `merge_completed_batch()` now treats post-merge count-shard deletion failures as non-fatal and records `counts_delete_error` in the live-merge result.
  - Added regression test: `test_live_merge_keeps_running_when_shard_delete_is_denied`.
  - Full test command after fix: `/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests/test_core.py tests/test_frog.py tests/test_batches.py tests/test_annotated.py tests/test_pilot_annotated_counts.py tests/test_merge_annotated_batches.py tests/test_export_top_xlsx.py tests/test_qc_report.py tests/test_live_merge.py -v`
  - Result: 27 tests passed.
  - Restart command: `/Users/cedar/Desktop/dutch-corpus/scripts/start_full_live_run.sh annotated_full_live_w8_b4000`
  - Restart log: `outputs/annotated_batches/annotated_full_live_w8_b4000/logs/run_20260516T093944Z.log`
  - Resume successfully replayed through batch 4692 and launched new Frog processes for batch 4693 onward.
- Runtime incident on 2026-05-22:
  - The process stopped after batch 41965 with `PermissionError: [Errno 1] Operation not permitted` while writing `manifest.json`.
  - Investigation showed core SQLite counts were intact:
    - SQLite `word_counts` sum matched `merged_batches` token totals.
    - Batch 41965 had already been merged.
    - Batch 41964 had a completed count shard and metadata but was not yet merged; resume merged it before continuing.
  - Root cause: the runner rewrote a very large manifest on every completed batch, and `--resume` also rewrote it for every replayed historical batch. At 40k+ batches this made manifest writing both slow and fragile.
  - Code fixes:
    - `write_manifest()` now writes through a temp file, atomically replaces the target, and retries transient `OSError`/`PermissionError`.
    - Resume replay no longer writes the manifest for historical batches; it only rebuilds in memory and writes once new progress is made or the run exits.
    - Live merge now commits each batch atomically: count-table upserts and the `merged_batches` marker are committed in the same transaction.
    - `scripts/run_full_live_worker.sh` passes `--manifest-write-interval-seconds 300` to reduce manifest write pressure during the full run.
  - Added regression tests: `test_manifest_write_retries_after_permission_error` and `test_merge_batch_file_can_defer_chunk_commits`.
  - Targeted test command after fix: `python3 -m unittest tests.test_live_merge`
  - Result: 5 tests passed.
  - Restart command: `/Users/cedar/Desktop/dutch-corpus/scripts/start_full_live_run.sh annotated_full_live_w8_b4000`
  - Restart log: `outputs/annotated_batches/annotated_full_live_w8_b4000/logs/run_20260522T134818Z.log`
  - Resume replayed through 40,000+ batches and continued with new Frog processes from batch 41975 onward.
- Full run completion on 2026-05-25:
  - Final batch index: 57478.
  - Final input lines: 229,914,131.
  - Final token-bearing document units: 198,229,800.
  - Final token count: 5,002,252,182.
  - Final unique word forms in SQLite: 22,196,701.
  - Final manifest: `outputs/annotated_batches/annotated_full_live_w8_b4000/manifest.json`.
  - Existing-DB export command: `/Users/cedar/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/merge_annotated_batches.py --run-name annotated_full_live_w8_b4000 --use-existing-db --top 50000`
  - Exported TSV: `outputs/annotated_batches/annotated_full_live_w8_b4000/merged_annotated_counts_top.tsv`.
  - Exported XLSX: `outputs/annotated_batches/annotated_full_live_w8_b4000/merged_annotated_counts_top.xlsx`.
  - QC report: `outputs/annotated_batches/annotated_full_live_w8_b4000/qc_report.md`.
  - QC result: PASS for headers, SUBTLEX workbook column compatibility, manifest/merge totals, formula columns, and row invariants across all 50,000 exported rows.
- Automation:
  - Created heartbeat automation `dutch-corpus-full-run-progress`.
  - It checks this run every 4 hours and reports progress in Chinese.
  - If the run is complete, it should export top 50,000 rows from the existing SQLite DB, create XLSX and QC report, then report artifact paths.
