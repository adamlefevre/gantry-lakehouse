# 0001: Plain Parquet tables rebuilt nightly from landing zones

- Status: Proposed
- Date: 2026-11-10

ADR numbers here are local to gantry-lakehouse. ADRs in the factory repo are cited as "gantry ADR NNNN". Terms in bold on first use are defined in `GLOSSARY.md`.

## Context

The lake today is Hive-partitioned Parquet in R2 with no catalog. A table is whatever `read_parquet('r2://<bucket>/data/**/*.parquet')` globs. Nothing runs except R2 and one daily Modal job, and any reader works (DuckDB, DuckDB-Wasm in the browser, Polars, Spark).

Two sources need to become queryable tables, and neither is in the lake yet:

1. **Task telemetry.** The factory writes one JSON object per Task to `telemetry/year=YYYY/month=MM/<taskId>.json` (telemetry contract v1, `docs/telemetry.md` in the gantry repo). Nothing reads it. A re-run overwrites the object, except when it finishes in a later month, which leaves two objects with the same `taskId`.
2. **Session telemetry.** Claude Code keeps one JSONL file per session on the owner's laptop. It holds token usage per model response, alongside prompts, code and tool output. Claude Code prunes old files, and nothing uploads them.

Both are small (tens of records a day) and both change after first write: a Task can be re-run, and a session file grows when it is resumed.

More personal sources (email, website metrics) may follow. They are out of scope here, but this design should not block them.

## Decision

1. **Every source writes to a landing zone, and only the nightly loader writes tables.** A **landing zone** is owned by its source. The lakehouse reads it and never rewrites or deletes it.
2. **Tables are plain Parquet with no catalog.** Each table is a single file outside `data/`, replaced whole each night: `lake/task_telemetry.parquet` and `lake/session_telemetry.parquet`. One PUT is atomic, so a reader sees the old file or the new one. `compact.py` scans only `data/` and never touches them. Partition a table only when its file gets large.
3. **The loader rebuilds each table in full from its landing zone.** There is no change detection and no upsert. Rebuilding from everything is the upsert.
4. **Task telemetry table: one row per Task.** When two objects share a `taskId`, the latest `completedAt` wins. Earlier Runs are not kept. Every contract field is loaded except `patch`, which is replaced by `patch_bytes`. The full diff stays in the landing zone.
5. **Session telemetry is metadata only, extracted on the laptop.** A sync script in this repo (`make sync-sessions`, run by hand at first) reads the local session files and uploads one object per session to `session-telemetry/year=YYYY/month=MM/<sessionId>.jsonl`, with year and month taken from the session's start so a resumed session overwrites the same key. Prompts, code, tool output, full paths and account IDs never leave the laptop. This repo owns the contract (`docs/session-telemetry.md`).
6. **Session telemetry table: one row per model response, keyed by message ID.** The local files write one response as several lines that share a message ID and each carry a usage block, so the loader dedupes on message ID. Fields: message ID, session ID, timestamp, model, input, output, cache-read and cache-creation tokens, project (last segment of the working directory), git branch, Claude Code version, and whether the response came from a subagent. Cost is derived from tokens at query time.
7. **The nightly Modal job rebuilds both tables as its first step, before compaction.** It calls the loader functions directly. The loader takes paths, so it runs against a local directory as well as R2.
8. **`data/` is unchanged.** The taxi demo stays Hive-partitioned Parquet, compacted by `compact.py`, and is what the public demo bucket serves.

## Conflict with gantry ADR 0001

_Contradicts gantry ADR 0001, decision 5 and rollout step 5 ("telemetry is written to R2 as Parquet, compacted by the existing pipeline"), and the "Planned" section of the telemetry contract (v2 moves to Parquet)._ Worth reopening because:

- writing Parquet from a Worker needs a Parquet writer in the control plane and still produces one tiny file per Task;
- the existing compaction can't apply the overwrite-on-re-run rule;
- keeping v1 JSON means the factory needs no change.

This ADR stays Proposed until a paired gantry PR annotates decision 5 and rollout step 5 and rewrites "Planned" to say there is no v2 and conversion happens on the lakehouse side. Both merge together, and this ADR becomes Accepted in that merge.

## Alternatives considered

- **DuckLake for these tables.** It gives real `UPDATE`/`DELETE`/`MERGE`, snapshots, tracked schema changes and atomic built-in compaction, and its catalog can be a DuckDB file, so it doesn't require Postgres. Deferred: at this volume a nightly full rebuild already gives atomic replacement and upsert, and DuckLake adds a catalog file that every reader must fetch and that becomes state to protect. Because landing zones are never deleted, adopting it later is a replay, not a migration. Revisit when a table is too large to rebuild nightly (tens of GB) or when a source needs guaranteed row-level deletes.
- **Iceberg on R2 Data Catalog.** Managed catalog and many engines, but heavier metadata for tiny tables in a DuckDB-only project. The fallback if multi-engine reads become a goal.
- **Have the factory write Parquet (gantry ADR 0001 as written).** See the conflict section.
- **Upload raw session files.** Keeps every field for later, but puts prompts and code in a bucket that the CI secret and the Modal secret can read.

## Consequences

- The lake undercounts failures. The factory writes task telemetry only when the agent loop returns, and `status` is in R2 object metadata, not in the JSON body, so success rate can't be computed yet. Fix it in the factory with an additive v1 change (`status` in the body, a record on failure), not by reading object metadata here.
- No time travel and no schema enforcement. A new field is a loader change, and old landing objects without it load as null.
- The session telemetry landing zone is the only long-term copy once Claude Code prunes local files. A field that wasn't extracted is gone for old sessions, and sessions are lost if the sync isn't run within the pruning window.
- Session metadata (models, token counts, project names, branch names) sits in the private bucket, readable by anything holding the main R2 token.
- Rebuild time grows with the landing zones, since nothing is ever deleted from them. That is the main trigger for revisiting DuckLake or partitioning.
- The loader gets this repo's first offline test, including a fixture with a multi-line response and one with a cross-month duplicate `taskId`. `.gantry.yml` can then have a `test:` command, which moves factory runs on this repo from draft-only PRs to verifiable ones.
- The Modal job gains a second responsibility. The new step calls shared functions; the existing compaction loop still duplicates `compact.main()`.

## Follow-ups

- Paired gantry PR for ADR 0001 and the telemetry contract (above).
- Factory issue: `status` in the task telemetry body, and a record for failed Tasks.
- Check whether repeated lines for one message ID carry identical usage, and pick the rule (last line or max) in the sync script.
- Run the session sync from a Claude Code session-end hook or a scheduled task.
- Fix the write-then-delete gap in `compact_partition_batch` for `data/`. It is independent of this decision.
- Add `lake/` and `session-telemetry/` to the layout notes in AGENTS.md and CLAUDE.md once the loader exists.
