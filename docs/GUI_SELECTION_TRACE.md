# OURD GUI Selection Trace

**Read-model schema:** 1  
**Date:** 2026-08-21

## Purpose

`SelectionTrace` makes qualified algorithm selection inspectable without
rerunning selection or replacing historical records with newer definitions.

```text
Intent
  -> Command Invocation
  -> Required Capabilities
  -> Recorded Candidates and Exclusions
  -> Qualification and Evidence
  -> Score Components and Ranking Criteria
  -> Exact Winner and Digest
  -> Compiled Workflow and EON Boundary
```

## Exact Assembly

`SelectionTraceAssembler` starts from a `SelectionDecision` object ID. It then:

1. resolves the task-bound invocation and command definition;
2. resolves the compiled workflow that references the selection;
3. preserves candidate and exclusion order exactly as recorded;
4. resolves each algorithm by both algorithm ID and implementation digest;
5. resolves the exact qualification IDs and their evidence IDs;
6. preserves rejection reasons as stored data;
7. preserves `ranking` as the core's ranking criteria, not as candidate IDs;
8. compares the compiled source snapshot with the current repository snapshot;
9. returns diagnostics for missing, duplicate, mismatched, or stale references.

No active or newer algorithm definition silently replaces the recorded digest.

## Interaction

The Selection Trace view provides:

- keyboard-selectable algorithm cards and non-color state labels;
- deterministic layered graph layout and bounded canvas scrolling;
- Explain Selection, Compare Candidates, Show Rejections, and Show Evidence;
- direct navigation to algorithm, qualification, evidence, invariant, command,
  invocation, selection, and compiled-workflow objects;
- explicit diagnostics when no candidate qualifies or a reference is stale.

Trace assembly occurs on the controller worker. Rendering uses the immutable
read model and never calls an algorithm or mutating adapter.

## First Milestone

For `Implement AxialProfile`, the complete intent-to-EON chain is visible and
navigable. The checked-in schema-v1 fixture covers selected and rejected
algorithms, qualification evidence, an approval-required plan, successful
execution, failure, artifact, confidence, and assurance records without a
model or network dependency.
