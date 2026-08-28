# OURD GUI Testing

**Date:** 2026-08-21

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
ourd-gui = ourd_gui.app:main
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
