# First Read-Only Task

## What you will learn

You will start the agent in read-only mode and run one bounded task against the current repository.

## Everyday analogy

This is like asking an inspector to describe a building while keeping every tool locked away. The inspector may observe and explain, but may not renovate.

## New vocabulary

A **workspace** is the repository root the agent may inspect. **Read-only** means the session may analyse and propose but may not mutate workspace files.

## Diagram

The command diagram separates the program name, workspace argument, and task text before showing the bounded run.

## Command or interaction

```bash
oiec-stm-agent . --task "Explain this repository"
```

Interactive mode also supports `/new`, `/help`, `/exit`, and `/quit`.

## Expected output

The agent reports the selected repository, model, authority record, and read-only mode, then returns a governed explanation or an explicit provider/preflight error. No workspace write is authorized.

## What just happened?

The `.` selected the current directory. `--task` requested one run and exit. Because no write authority was supplied, the session remained read-only even though the runtime has code capable of staging mutations.

## Try changing this

Replace the task with “List the major packages and their responsibilities.” Keep the same workspace and do not add `--write`.

## Common mistake

Do not confuse a proposed patch in model text with an authorized or applied change. Read-only mode can describe candidate work without executing it.

## Next lesson

Continue to **Evidence** and learn how source facts differ from model proposals.
