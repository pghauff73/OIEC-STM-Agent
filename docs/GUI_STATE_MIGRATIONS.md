# OURD GUI State Migrations

**Date:** 2026-08-21

## Current Versions

| State | Version | Authority |
| --- | ---: | --- |
| GUI `AgentEvent` envelope | 1 | append-only observational journal |
| GUI task/session/chat projection | 2 | rebuildable cache |
| GUI preferences | 2 | non-authoritative local settings |
| Selection/read models | 1 | derived from canonical EGCF objects |

## Projection Version 2

- Version 2 adds bounded chat messages, chat status, active turn identity, and
  the active context boundary.
- Existing schema-v1 projection databases are not authoritative and are rebuilt
  from the append-only GUI journal instead of being rewritten in place.
- The projection keeps the newest 500 messages. Dropped projection rows do not
  remove historical journal events.

## Event Version 1 Rules

- Missing `AgentEvent.schema_version` is read as version 1 for compatibility with pre-freeze candidate journals.
- Unknown event names inside schema version 1 become `AGENT_STEP` and retain their original name.
- Event schema versions other than 1 fail closed.
- Projection metadata must match schema version 2, event count, and state digest; otherwise it is rebuilt from the validated journal.
- Invalid preferences fall back to safe defaults and never affect capability or approval.

## Future Migration Procedure

1. Add an explicit pure migration from the previous serialized version.
2. Preserve the original append-only journal; never rewrite historical events in place.
3. Rebuild projections into a new schema version and compare state digests.
4. Add fixture and replay tests for both the old and new version.
5. Document authority-neutral field changes and any newly displayed uncertainty.
6. Require deterministic validation before changing the default writer version.

Canonical EGCF objects and core events are not migrated by GUI preference or
projection migrations.
