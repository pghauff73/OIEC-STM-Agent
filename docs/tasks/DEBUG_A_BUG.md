# Debug a Bug

## Goal

Turn a symptom into a bounded problem model, competing hypotheses, and discriminating tests before proposing a change.

## Start safely

Freeze the failing input, exact source state, observed output, expected output, and reproduction command. Keep the first pass read-only.

## Learning route

Complete T03 Evidence, T04 OURD, T05 IURM, and T08 CFEL.

## Method

1. Map the relevant objects and dependencies.
2. Name at least two plausible causes when evidence permits.
3. Select one controlled test that separates them.
4. Record failed expectations before proposing another attempt.
5. Bind any candidate to exact files, tests, risk, and rollback.

## Safe completion condition

The root-cause claim is supported by a reproducer and discriminating evidence, and the proposed fix does not rely on a coupled or stale comparison.
