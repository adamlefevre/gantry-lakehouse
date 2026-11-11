# gantry-lakehouse

A serverless lakehouse on Cloudflare R2 + DuckDB, with daily compaction on Modal.

- Hive-partitioned Parquet in R2 (zero egress), queried by DuckDB over S3 range requests.
- `pipelines/compact.py` bin-packs small files into ~128MB snappy Parquet; a Modal cron runs it daily.
- CI runs an integration test against an ephemeral prefix in a real bucket.

It also serves as the analytics store and first target repo for [Gantry](https://github.com/adamlefevre/gantry), a software factory that turns labelled GitHub issues into PRs.

## Quick start

```bash
cp .env.example .env   # fill in R2 credentials
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
make init-bucket ingest test
```

See `CLAUDE.md` for every command and `AGENTS.md` for architecture and safety rules.
