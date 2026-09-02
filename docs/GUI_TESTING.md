# OURD GUI Testing

**Date:** 2026-08-31

## Deterministic GUI Suite

```bash
python3 -m unittest discover -s tests/gui -t . -v
```

The suite covers events, immutable state reduction, journal replay, projection
rebuild, partial-line handling, exact selection assembly, governance, approval
matching, semantic terminal parsing, artifact bounds, redaction, evidence and
assurance exports, replay, paging, performance telemetry, safety imports, and
packaging. Chat coverage includes bounded multi-turn history, context reset,
append-only projection replay, first-class provider/model/tool trace events,
cooperative cancellation, and provider option parsing.

## Schema-v1 Fixture

`tests/gui/fixtures_v1.py` installs fixed canonical objects through the same
object-store validation used by the core. The source snapshot and complete
fixture bundle are digest locked. It covers:

```text
selection
workflow
evidence
approval-required plan
human approval
successful execution
failure
confidence
assurance
artifact
```

It requires no model and no network connection.

## Headless Launch

```bash
tmpdir=$(mktemp -d)
printf 'fixture\n' > "$tmpdir/README.md"
xvfb-run -a python3 -m ourd_gui --repo "$tmpdir" --smoke-test
```

The smoke path constructs the workbench, processes idle work, saves state,
closes the controller, and exits without entering the long-running event loop.
The deterministic validator starts Xvfb directly with a temporary authority
cookie and a loopback client connection, avoiding sandbox ownership conflicts
on `/tmp/.X11-unix`.

## Packaging

The custom PEP 517 backend is tested directly. The wheel must contain the full
`ourd_gui` package and:

```text
oiec-stm-gui = ourd_gui.app:main
ourd-gui = ourd_gui.app:main  # compatibility alias
```

The source distribution includes GUI source and documentation.

## Full Repository Validation

```bash
python3 -m compileall -q ourd ourd_gui tests
python3 -m unittest discover -s tests -t . -v
python3 tools/validate.py --no-report
```

Passing tests proves deterministic candidate validation only. Certification
still requires a new exact source snapshot, validation bundle hashes, and
explicit human approval.

## Performance Targets

The Performance panel reports bounded live telemetry for controller startup,
GUI initialization, worker operations, event rendering, event draining, and
projection saves. Task paging and the bounded object cache protect large
sessions. Targets remain diagnostic rather than authority: correctness and
evidence gates always take precedence.

## Formal-Writing GUI Validation

Formal-writing coverage includes canonical GUI/CLI request equivalence, every
read-only workflow action, exact plan/draft/audit/revision lineage, asynchronous
phase ordering, cooperative cancellation, bounded shutdown, malformed and
signature-invalid artifacts, source drift, graph/trace completeness, all audit
statuses, novelty/SAA status preservation, adversarial source isolation,
governed preview drift and confirmation checks, zero ordinary output mutation,
display-backed widget behavior, standalone parsing/smoke, and packaging.

Standalone smoke:

```bash
tmpdir=$(mktemp -d)
xvfb-run -a python3 -m ourd_gui.formal_writing_gui \
  --workspace "$tmpdir" \
  --smoke-test
```

Focused deterministic suite:

```bash
python3 -m unittest \
  tests.gui.test_formal_writing_models \
  tests.gui.test_formal_writing_projection \
  tests.gui.test_formal_writing_controller \
  tests.gui.test_formal_writing_gui \
  tests.gui.test_formal_writing_view \
  tests.gui.test_formal_writing_performance \
  tests.test_formal_writing_cli -v
```

The wheel must include `ourd_gui/formal_writing_gui.py`, its controller,
models, projection, reusable view, and this console entry point:

```text
oiec-stm-formal-writing-gui = ourd_gui.formal_writing_gui:main
```

Measured implementation targets are less than two seconds for warm standalone
startup, 500 ms for a cached refresh of 100 signed result artifacts, one second
for 500 graph nodes and 1,000 edges, 100 ms for loaded-run selection, and one
second for idle close. The GUI-only queue is capped at 1,000 events.

Display-backed tests explicitly skip when Tk cannot open a display. Such skips
do not establish visual qualification. Human review must still cover
keyboard-only use, 100%-200% font scaling, narrow/wide layouts, long paths,
high-density graphs, exact non-color status text, optional PDF rendering, and
focus behavior.

The local August 31, 2026 base environment has Pillow but not PyMuPDF or
`pytesseract`. Base behavior and fail-closed optional-capability detection are
validated; PDF/OCR visual qualification remains a separate optional-dependency
gate.
