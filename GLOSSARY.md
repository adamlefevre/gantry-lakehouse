# Gantry Lakehouse

A serverless lake on object storage that holds a public demo dataset and the private analytics data its owner collects. Terms owned by the factory (Task, Run, Verification) are defined in the gantry repo's `GLOSSARY.md`.

## Language

**Landing zone**:
A prefix where one source writes its raw objects. The source owns it; the lakehouse only reads it, and it is always enough to rebuild the table made from it.
_Avoid_: Raw layer, bronze, staging, inbox

**Task telemetry**:
The record the factory writes when a Task finishes: one per Task, with the latest Run replacing earlier ones.
_Avoid_: Telemetry (unqualified), factory logs

**Session telemetry**:
Usage metadata from the owner's own Claude Code sessions: models, token counts and timing, never prompts, code or tool output.
_Avoid_: Telemetry (unqualified), transcripts, chat history
