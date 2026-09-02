# Install

## What you will learn

You will install the current checkout, identify the five package commands, and understand which names are aliases rather than separate systems.

## Everyday analogy

A workshop can have two doors leading to the same room. Different labels do not necessarily mean different machinery behind them.

## New vocabulary

**CLI** means command-line interface. **GUI** means graphical user interface. An **alias** is another command name that reaches the same entry point.

## Diagram

The diagram shows one agent core with text and graphical entry points, plus the separate EGCF command interface.

## Command or interaction

```bash
python3 -m pip install -e .
oiec-stm-agent --help
```

## Expected output

The installation exposes `oiec-stm-agent`, `ourd-agent`, `egcf`, `oiec-stm-gui`, and `ourd-gui`. The two `ourd-*` commands are aliases of the corresponding OIEC entry points.

## What just happened?

Editable installation connected the checkout to the command names declared in `pyproject.toml`. The help output came from the real parser rather than a separate documentation-only list.

## Try changing this

Run `ourd-agent --help` and compare it with `oiec-stm-agent --help`. Then compare `ourd-gui --help` with `oiec-stm-gui --help`.

## Common mistake

Do not treat the five names as five independent governance architectures. There are two aliases and three user-facing command experiences.

## Next lesson

Continue to **First Read-Only Task** and inspect a repository without granting write authority.
