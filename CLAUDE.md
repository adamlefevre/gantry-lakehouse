# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@AGENTS.md

AGENTS.md (imported above) holds the architecture summary, safety rules, and issue-tracker/triage/domain-doc conventions. This file adds what you need to work in the code.

## Commands

Run from repo root; `pytest.ini` sets `pythonpath = .` so `from pipelines.compact import ...` works. A local `.venv` is used; deps are in `requirements.txt`. The Makefile uses `SHELL := /bin/bash` and `-include .env`, so on Windows run it from Git Bash.

- `make test` → `pytest tests/test_compaction.py -v -s`. **This hits real Cloudflare R2**: it needs `.env` populated (`CLOUDFLARE_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`). There are no offline tests.
- Single test: `pytest tests/test_compaction.py::<test_name> -v -s`
- `make ingest` / `make compact` run `pipelines/ingest.py` / `pipelines/compact.py` against the real bucket. `compact` **deletes** source files after it compacts them.
- `make modal-test` runs the cron job once on Modal (`modal run`). `make modal-deploy` deploys it.
- `make init-bucket`, `make cors`, `make clean` (deletes the bucket) go through `npx wrangler r2 ...`.

CI (`.github/workflows/ci.yml`) runs the R2 integration test on Python 3.11, using repo secrets.

## Architecture

- R2 is accessed two ways: **DuckDB** `httpfs` with a `TYPE R2` secret, reading and writing `r2://<bucket>/...` URLs, and **boto3** against `https://<account>.r2.cloudflarestorage.com` for listing and deletes. `pipelines/compact.py` exposes `get_s3_client()` and `init_duckdb()`, and the Modal job and the tests both reuse them.
- Data layout: Hive-style partitions under `data/` (e.g. `data/year=2024/month=01/`). Telemetry from the Gantry control plane lands in `telemetry/year=YYYY/month=MM/<taskId>.json` (contract: `docs/telemetry.md` in the gantry repo).
- Compaction flow: `discover_small_files` (parquet files <32MB, grouped by directory, skipping `compacted-*` files) → `pack_batches` (greedy, up to 128MB) → `compact_partition_batch`. That last step writes `compacted-<id>.parquet` with SNAPPY compression and ~120k-row row groups, checks that row counts match, and then deletes the source files. It skips batches with fewer than 2 files.
- `compact.py` reads env vars into module-level globals **at import time**, after `load_dotenv()`. Set env before importing it.
- `jobs/scheduled_compaction.py` is a Modal app (`gantry-maintenance`) with a daily cron at 02:00 UTC. It bundles `pipelines/` through `add_local_python_source` and reads credentials from the Modal secret `r2-credentials`. It repeats the `compact.main()` loop instead of calling it, so keep the two in sync.
- `tests/test_compaction.py` uses a module-scoped autouse fixture. It writes 5 synthetic micro-files to `data/test_runs/run_<uuid>`, runs compaction, checks parity, and deletes the prefix on teardown.
- `make cors` opens the bucket to cross-origin `GET`/`HEAD` so a future browser DuckDB-Wasm UI can query it directly (see `docs/design-notes/01-lakehouse-and-factory-origins.md`).
