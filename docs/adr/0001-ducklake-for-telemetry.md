# 0001: DuckLake for telemetry, plain Parquet for demo data

- Status: Proposed
- Date: 2026-11-10

ADR numbers here are local to gantry-lakehouse. ADRs in the factory repo are cited as "gantry ADR NNNN".

## Context

The lake today is Hive-partitioned Parquet in R2 with no catalog. A table is whatever `read_parquet('r2://<bucket>/data/**/*.parquet')` globs.

That gives us:

- nothing to run except R2 and one daily Modal job;
- any reader works (DuckDB, DuckDB-Wasm in the browser over CORS, Polars, Spark);
- partition pruning on `year`/`month`, and cheap range reads with no egress cost.

It also has limits:

1. **Compaction isn't atomic.** `compact_partition_batch` writes `compacted-<id>.parquet`, then deletes the source files. A query in between reads both and double-counts. If the delete partly fails, the duplicate rows stay for good, because compacted files are never revisited.
2. **No snapshots.** No updates, deletes, time travel or schema enforcement.
3. **Telemetry isn't in the lake.** The factory writes one small JSON object per task to `telemetry/year=YYYY/month=MM/<taskId>.json` (telemetry contract v1, `docs/telemetry.md` in the gantry repo). Compaction only handles Parquet under `data/`, so nothing reads or compacts it. A re-run of a task overwrites its object, so any table built from it needs upsert by `taskId`, which plain Parquet files can't do.

Telemetry is the data this lake exists to serve (AGENTS.md, goal 5), and it is the case plain Parquet handles worst: many tiny writes plus overwrites.

## Decision

1. **Telemetry becomes a DuckLake table.** The catalog and its Parquet data files live in the private bucket (`R2_BUCKET_NAME`) under `lake/`, never in the public demo bucket. Queries against telemetry go through DuckLake, not through a glob.
2. **The factory keeps writing v1 JSON.** `telemetry/` stays the landing zone, and the lakehouse never rewrites or deletes it. The control plane runs on Workers and can't run DuckDB, so it can't commit to DuckLake itself.
3. **The nightly Modal job loads telemetry.** It reads new and changed JSON objects, upserts them into the DuckLake table by `taskId`, then runs DuckLake's own maintenance (merge small files, expire old snapshots, clean up unreferenced files). Small loads use data inlining, so a night with a few tasks doesn't create a Parquet file.
4. **The catalog is a DuckDB file stored in R2, with one writer.** The Modal job downloads it, commits, and uploads it with a conditional PUT on the ETag it downloaded, so a concurrent local run fails instead of overwriting. Move the catalog to Postgres when a second writer is needed.
5. **`data/` stays plain Parquet.** The taxi demo is small, shows the catalog-less pattern, and is what the public demo bucket serves to DuckDB-Wasm over CORS. `compact.py` stays for it.

## Conflict with gantry ADR 0001

_Contradicts gantry ADR 0001, decision 5 and rollout step 5 ("telemetry is written to R2 as Parquet, compacted by the existing pipeline"), and the "Planned" section of the telemetry contract (v2 moves to Parquet)._ Worth reopening because:

- writing Parquet from a Worker needs a Parquet writer in the control plane, and still produces one tiny file per task;
- the existing compaction can't handle the overwrite-on-re-run rule and has the atomicity gap above;
- keeping v1 JSON means the factory needs no change at all.

If this ADR is accepted, gantry ADR 0001 step 5 and the contract's "Planned" section should be updated to say that conversion to Parquet happens on the lakehouse side.

## Alternatives considered

- **Stay plain Parquet and convert telemetry JSON to Parquet in the Modal job.** Simplest, but upsert means rewriting whole partitions by hand, and the atomicity gap remains.
- **Iceberg on R2 Data Catalog.** Managed catalog, nothing to host, readable by many engines. Rejected for now: heavier metadata, no data inlining for tiny writes, and this project is DuckDB-only. It is the fallback if multi-engine reads become a goal.
- **DuckLake with a Postgres catalog from day one.** Supports many writers, but adds a service, a credential and an idle dependency for a job that runs once a day.

## Consequences

- Telemetry tables are readable only through DuckDB with the `ducklake` extension. Plain `read_parquet` over `lake/` is not a consistent view.
- A browser UI can't read the telemetry lake: it sits in the private bucket, which has no CORS. The DuckDB-Wasm demo stays on the plain Parquet in the demo bucket. Showing telemetry in a browser would need its own decision, such as publishing an aggregated export.
- The catalog file is now state that can be lost. It can be rebuilt by replaying `telemetry/`, which is why the JSON is never deleted.
- The Modal job gains a second responsibility (load, then maintain), and the loops in `jobs/scheduled_compaction.py` and `compact.main()` drift further unless the job calls shared functions.
- Tests need an ephemeral catalog and data path per run (for example under `data/test_runs/run_<uuid>/lake/`), cleaned up on teardown like today.
- New fields planned for `AgentTelemetry` (provider, token split, cost, latency, status) become DuckLake schema changes instead of mixed-schema files.

## Follow-ups

- Fix the write-then-delete gap in `compact_partition_batch` for `data/`. It is independent of this decision.
- Add `lake/` to the layout notes in AGENTS.md and CLAUDE.md once the load job exists.
