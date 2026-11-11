# Project Context: gantry-lakehouse

## Architecture & Goals
An open-source, serverless lakehouse reference implementation:
1. **Storage Layer:** Cloudflare R2 (S3-compatible via DuckDB `httpfs`). Zero egress, snappy Parquet files.
2. **Compute:** DuckDB querying Hive-partitioned Parquet directly over S3 range requests. (No catalog yet; DuckLake is a possible future addition.)
3. **Scheduled Maintenance:** Serverless containerized compaction and cleanup running on **Modal** (daily cron, zero idle cost).
4. **CI/CD:** GitHub Actions running PyTest integration tests against ephemeral test namespaces (`data/test_runs/run_<uuid>`).
5. **Factory analytics store:** the [Gantry](https://github.com/adamlefevre/gantry) software factory writes task telemetry into this bucket under `telemetry/`. The record shape and path layout are a contract owned by the factory repo (`docs/telemetry.md` there). This repo is also the factory's first target repo (see `.gantry.yml`).

## Repository Layout
```text
gantry-lakehouse/
├── pipelines/
│   ├── ingest.py                  # Ingests public NYC Taxi parquet to Cloudflare R2
│   └── compact.py                 # Bin-packs small files into ~128MB Parquet
├── jobs/
│   └── scheduled_compaction.py    # Modal cron app for automated daily maintenance
├── tests/
│   └── test_compaction.py         # Ephemeral R2 integration test verifying compaction parity
├── docs/
│   ├── design-notes/              # Historical design context
│   └── agents/                    # Issue tracker, triage labels, domain-doc conventions
├── .gantry.yml                    # Setup config for Gantry factory runs on this repo
├── Makefile                       # Central orchestrator
├── .env.example                   # Template for secrets
└── AGENTS.md                      # Agent context & instructions
```

## Safety & Compliance Rules
- NEVER hardcode secrets or corporate identifiers.
- Read credentials strictly from `.env` using `python-dotenv` locally and `modal.Secret` in remote jobs.
- All R2 writes must be confined to the configured bucket (`R2_BUCKET_NAME`).
- Always run tests against ephemeral prefixes (`data/test_runs/run_<uuid>`) and ensure fixtures clean up after themselves.
- Never compact, rewrite or delete under `telemetry/` without checking the factory's telemetry contract first.

## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues for this repo via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`. Labelling an issue `ready-for-agent` is how the Gantry factory will pick it up.

### Domain docs

Single-context layout: one `GLOSSARY.md` and `docs/adr/` at the repo root (created lazily). See `docs/agents/domain.md`.
