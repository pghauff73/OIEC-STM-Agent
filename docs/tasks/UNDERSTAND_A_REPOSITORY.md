# Understand a Repository

## Goal

Inspect a repository’s structure, canonical owners, entry points, tests, generated artifacts, and unresolved risks without changing files.

## Start safely

```bash
oiec-stm-agent . --task "Explain this repository"
```

The command selects the current directory and remains read-only unless explicit authority is supplied.

## Learning route

Complete T02 First Read-Only Task, T03 Evidence, and T04 OURD. Use OURD to map packages, source-of-truth files, generated outputs, dependencies, and exclusions.

## Evidence to collect

- current commit and worktree status;
- applicable repository guidance;
- package and command entry points;
- source owners and generated artifacts;
- focused and full validation commands; and
- explicit limitations or stale reports.

## Safe completion condition

The explanation distinguishes current source evidence from historical reports, model interpretation, unverified assumptions, and release certification.
