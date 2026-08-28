# OIEC-STM-Agent Writing Mode

OIEC-STM-Agent can already stage text and code through `prepare_write_file`,
`prepare_replace_text`, and atomic candidate transactions. Writing mode makes
that capability practical from the CLI without weakening the existing
OURD/IURM/EON/CFEL governance path.

## Design

`--write` is an explicit human grant for a single exact workspace snapshot.
It does not turn the model into its own authority. The user must provide at
least one writable path or pattern with `--write-path`.

The generated session authority:

- is bound to the current workspace snapshot;
- allows mutation only inside the supplied path patterns;
- always forbids `.ourd-agent/**`;
- keeps L1 candidate application interactive;
- disables L2 unless the user explicitly supplies `--write-allow-l2`;
- never grants `--yolo`;
- preserves EON candidate hashes, evidence gates, transactions, rollback,
  CFEL collision records, and OIEC no-blind-retry constraints.

The temporary authority manifest exists only for the CLI process. Normal
invocations without `--write` or `--authority` remain read-only.

Because authority is bound to an exact snapshot, a successful mutation makes
that session authority stale. One session should therefore prepare one atomic
transaction, which may contain many file changes. Start a fresh `--write`
session for another transaction so it binds to the new workspace snapshot.

## Write a document

```bash
oiec-stm-agent . \
  --write \
  --write-path 'docs/**' \
  --task 'Write docs/architecture.md explaining OIEC-STM for a software engineering audience.'
```

The model is instructed to inspect relevant repository sources, separate
purpose/audience/evidence/tone/structure as writing dimensions, prepare the
file as a candidate transaction, bind an EON action, gather evidence, pass the
gate, and present the exact candidate for approval before application.

## Edit a README

```bash
oiec-stm-agent . \
  --write \
  --write-path README.md \
  --task 'Rewrite the installation section for clarity without changing commands.'
```

## Write code with verification

Writing mode can also grant deterministic command capabilities explicitly:

```bash
oiec-stm-agent . \
  --write \
  --write-path 'ourd/**' \
  --write-path 'tests/**' \
  --write-command-capability python.unittest \
  --write-test 'python3 -m unittest discover -s tests -v' \
  --task 'Implement the requested feature and add focused tests.'
```

Supported write-mode command capability names are currently:

- `python.unittest`
- `python.py_compile`
- `ctest.run`
- `cmake.build`
- `compiler.syntax_check`

The exact command still has to pass `PolicyEngine.classify_command`; naming a
capability on the CLI does not authorize arbitrary shell execution.

## L2 changes

Broad, structural, dependency, configuration, build-system, or otherwise
high-impact candidates may receive deterministic L2 risk. They are blocked in
standard writing mode. A user may allow **interactive** L2 review explicitly:

```bash
oiec-stm-agent . \
  --write \
  --write-path 'ourd/**' \
  --write-allow-l2 \
  --task 'Perform the bounded structural refactor described in the task.'
```

This still does not make L2 automatic. The exact candidate remains subject to
OIEC/EON evidence and human approval.

## Why this is not a raw write switch

A conventional `--write` flag often means "let the model modify anything." In
OIEC-STM it means something narrower:

```text
human scope grant
  -> exact-snapshot authority
  -> OURD problem model
  -> Boundary Determination
  -> Dimension Limiting / IURM
  -> staged candidate
  -> EON exact action
  -> evidence gate
  -> human approval when required
  -> atomic apply
  -> verification / rollback / CFEL
```

The model gains the ability to write documents and code, but not the ability to
silently expand its own authority.
