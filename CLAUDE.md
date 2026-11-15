# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@AGENTS.md

AGENTS.md (imported above) holds the architecture summary, safety rules, and issue-tracker/triage/domain-doc conventions. This file adds what you need to work in the code.

## Commands

Run from repo root; `pytest.ini` sets `pythonpath = .` so `from pipelines.compact import ...` works. A local `.venv` is used; deps are in `requirements.txt`. The Makefile uses `SHELL := /bin/bash` and `-include .env`, so on Windows run it from Git Bash.

- `make test-offline` → `pytest tests/offline -v`. Runs compaction against a local moto S3 server. No credentials, no network beyond DuckDB's one-time `httpfs` install. This is the PR check and the factory's `test:` command.
- `make test` → `pytest tests/live -v -s`. **This hits real Cloudflare R2**: it needs `.env` populated (`CLOUDFLARE_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`).
- Run `tests/offline` and `tests/live` in separate pytest processes: `compact.py` reads env at import, and the offline conftest overwrites it.
- Single test: `pytest tests/offline/test_compaction_offline.py::<test_name> -v`
- `make ingest` / `make compact` run `pipelines/ingest.py` / `pipelines/compact.py` against the real bucket. `compact` **deletes** source files after it compacts them.
- `make modal-test` runs the cron job once on Modal (`modal run`). `make modal-deploy` deploys it.
- `make init-bucket`, `make cors`, `make clean` (deletes the bucket) go through `npx wrangler r2 ...`. All three act on `R2_BUCKET_NAME`, so `make cors` on the default `.env` would reopen the private bucket; it's meant for the demo bucket.
- `make demo-init` creates `gantry-demo` and applies CORS; `make demo-ingest` loads the taxi sample into it with the `DEMO_R2_*` token (see Buckets below).

CI (`.github/workflows/ci.yml`) has two jobs on Python 3.11. `offline-tests` runs on every push and PR with no secrets. `live-r2-tests` runs the live test only on push to `main` or manual dispatch, bound to the `r2-live` GitHub environment, which holds the R2 secrets and requires owner approval. PRs never reach it. No linter, formatter or type checker is configured.

`.gantry.yml` has `test: pytest tests/offline`, so Gantry factory runs here can open regular PRs.

## Architecture

- R2 is accessed two ways: **DuckDB** `httpfs` with a `TYPE R2` secret, reading and writing `r2://<bucket>/...` URLs, and **boto3** against `https://<account>.r2.cloudflarestorage.com` for listing and deletes. `pipelines/compact.py` exposes `get_s3_client()` and `init_duckdb()`, and the Modal job and the tests both reuse them.
- Data layout: Hive-style partitions under `data/` (e.g. `data/year=2024/month=01/`). Telemetry from the Gantry control plane lands in `telemetry/year=YYYY/month=MM/<taskId>.json` (contract: `docs/telemetry.md` in the gantry repo).
- Compaction flow: `discover_small_files` (parquet files <32MB, grouped by directory, skipping `compacted-*` files) → `pack_batches` (greedy, up to 128MB) → `compact_partition_batch`. That last step writes `compacted-<id>.parquet` with SNAPPY compression and ~120k-row row groups, checks that row counts match, and then deletes the source files. It skips batches with fewer than 2 files.
- Compaction scope: `discover_small_files` defaults to `prefix="data/"` and only considers `.parquet`, so `telemetry/` JSON is never touched today. `data/` includes `data/test_runs/`, so `make compact` also compacts any test prefix left behind by a failed teardown. `ingest.py` writes a single file (`data/year=2024/month=01/yellow_trips.parquet`), so on its own it gives compaction nothing to do.
- `compact.py` reads env vars into module-level globals **at import time**, after `load_dotenv()`. Set env before importing it.
- `jobs/scheduled_compaction.py` is a Modal app (`gantry-maintenance`) with a daily cron at 02:00 UTC. It bundles `pipelines/` through `add_local_python_source` and reads credentials from the Modal secret `r2-credentials`. It repeats the `compact.main()` loop instead of calling it, so keep the two in sync.
- `tests/live/test_compaction_live.py` uses a module-scoped autouse fixture. It writes 5 synthetic micro-files to `data/test_runs/run_<uuid>`, runs compaction, checks parity, and deletes the prefix on teardown. It calls `compact_partition_batch` on one batch directly.
- `tests/offline/` runs the same pipeline against moto. Its `conftest.py` sets the four R2 env vars and `R2_ENDPOINT_OVERRIDE` before `compact` is imported; `compact.py` uses that override for both boto3 and the DuckDB R2 secret (path-style, no SSL). It also covers `compact.main()` and checks that `telemetry/` is untouched. The Modal job's loop is still untested.
- `make cors` opens a bucket to cross-origin `GET`/`HEAD` so a future browser DuckDB-Wasm UI can query it directly (see `docs/design-notes/01-lakehouse-and-factory-origins.md`). Only `gantry-demo` has this policy.

## Buckets

- **`gantry`** (`R2_BUCKET_NAME`): private, with no CORS policy. Holds factory `telemetry/` and is what CI, the Modal secret `r2-credentials` and `make test`/`compact` use. Keys: `R2_ACCESS_KEY_ID`/`R2_SECRET_ACCESS_KEY`.
- **`gantry-demo`** (`DEMO_BUCKET_NAME` in the Makefile): public demo, with open CORS for `GET`/`HEAD`. The policy exposes `Content-Range`, `Content-Length`, `Accept-Ranges` and `ETag` so DuckDB-Wasm range reads work, and caches preflights for 1h. Holds only the NYC Taxi sample (`make demo-ingest` rebuilds it), never telemetry. Keys: `DEMO_R2_ACCESS_KEY_ID`/`DEMO_R2_SECRET_ACCESS_KEY`, an Object Read & Write token scoped to this bucket only, so it can't read `gantry`.
- The pipelines read only `R2_*` vars. To target the demo bucket, override `R2_BUCKET_NAME` and both key vars with the demo values, as `demo-ingest` does. Overriding only the bucket name gets `AccessDenied`, because the main token is scoped to `gantry`.
- The CORS file format for wrangler 4.x is `{"rules":[{"allowed":{...}}]}`, passed with `--file`. The older S3-style array is rejected.
