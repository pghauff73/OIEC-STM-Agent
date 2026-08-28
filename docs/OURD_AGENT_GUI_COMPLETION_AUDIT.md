# OIEC-STM-Agent GUI Completion Audit

**Audit date:** 2026-08-21, Australia/Brisbane  
**Plan:** `OURD_AGENT_GUI_IMPLEMENTATION_PLAN.md`  
**Implementation state:** feature-complete candidate; exact-snapshot human approval still required  
**Historical certified baseline:** `d1f9ba74cb9fb91228a9924da58eee8f89e2e0f23ead9d42f0eb642f6691b47e`

## Decision

The Tkinter workbench implements the evidence-governed GUI architecture and
the `InteractiveSelectionTrace` milestone without adding a second authority or
mutation path. Views remain read-only request/inspection surfaces; all command,
authorization, execution, and replay requests cross `CoreGateway` into the
existing EGCF core.

This audit does not certify the new source. Deterministic success, candidate
hashes, and human approval are separate records.

## Phase Results

| Phase | Result | Primary implementation and evidence |
| --- | --- | --- |
| 0 - Contract and fixtures | Complete | `tests/gui/fixtures_v1.py` defines schema-v1, source-snapshot-locked, bundle-digest-locked canonical selection, workflow, evidence, approval, execution, failure, assurance, and artifact fixtures; `test_fixtures_v1.py` loads them through GUI read models. |
| 1 - Application scaffold | Complete | `ourd_gui/app.py`, `controller.py`, `events.py`, `state.py`, `views/shell.py`, canonical `oiec-stm-gui` and compatibility `ourd-gui` entry points, wheel/sdist inclusion, structured errors, worker polling, clean headless close. |
| 2 - Event and task projection | Complete | Typed schema-v1 events, core-event mapping, append-only GUI journal, deterministic reducer, task/session projection, navigation, partial-line handling, unknown-event preservation, and provenance requirement for authoritative events. |
| 3 - SelectionTrace model | Complete | Exact command, invocation, selection, algorithm digest, qualification, evidence, candidate, exclusion, score, ranking criteria, tie-break, stale snapshot, missing-object, and duplicate diagnostics. Recorded candidate order is preserved. |
| 4 - InteractiveSelectionTrace | Complete | Layered canvas, scrolling, 75/100/125 percent zoom presets, keyboard navigation, non-color state text, candidate details, evidence links, qualification/command links, comparison, rejections, and 100-node layout test. |
| 5 - OURD and IURM | Complete | Canonical semantic graph output, explicitly labelled `GUI_REFERENCES` fallback, dimensions, baseline, values, interactions, MVD, and command preparation for dimensions, boundary variation, OFAT, and covering designs. |
| 6 - Evidence dashboard | Complete | Six coverage dimensions, classes, requirements, confidence, gaps, conflicts, unknowns, evidence provenance graph, exact record navigation, and JSON/Markdown exports. Simulated evidence is labelled and cannot satisfy real coverage. |
| 7 - EON and approvals | Complete | Plan/action inspector, diff, C0-C5 ladder with full canonical grant/spec details, Simulate, Approve, Execute, Edit Scope, Evidence, Rollback request controls, exact plan/snapshot checks, matching approval checks, and explicit C4/C5 refusal. |
| 8 - Workflow, CFEL, replay | Complete | Lifecycle DAG, execution overlay, failure/root-cause/retry views, regression command proposal, GUI event replay without execution, explicit governed dry-run plan replay, and task navigation/comparison. |
| 9 - Artifacts and tools | Complete within Tk boundary | Passive text/JSON/Markdown/HTML/SVG views, PNG/GIF preview, bounded OBJ/STL/PLY metadata, before/after geometry metadata comparison, algorithm qualification history, model metadata, semantic terminal, command palette, and run comparison with explicit missing duration/cost states. |
| 10 - Assurance and hardening | Complete for v1 candidate | Assurance JSON/Markdown/static HTML exports, scalable fonts, reduced motion, keyboard paths, non-color status, bounded redaction, task paging, bounded LRU object cache, bounded performance telemetry, projection recovery, compatibility docs, event schema v1, and read-model schema v1. |

## Safety Invariants

- `GUIAuthority <= AgentAuthority` remains enforced.
- View modules do not import subprocess execution, EON adapters, transaction managers, or the legacy mutation agent.
- C3-C5 semantic terminal requests cannot execute directly.
- C4 and C5 EON plans do not expose approval or execution controls.
- Authorization and execution are separate user actions.
- A stale source snapshot blocks approval and execution.
- Model output cannot create human approval.
- GUI replay never executes the core.
- Core hash-chain, object schema, object ID, and artifact path validation fail closed.
- Active HTML/SVG execution and network loading are disabled.
- Secret-like fields and deeply nested/oversized structures are bounded before detail rendering or export.

## Validation Evidence

Completed before candidate freeze:

- `python3 -m compileall -q ourd ourd_gui tests` - pass.
- `python3 -m unittest discover -s tests/gui -t . -v` - 55 tests passed.
- `python3 -m unittest discover -s tests -t . -v` - 175 tests passed.
- Headless Tk smoke with authenticated Xvfb transport - pass.
- Wheel and source distribution build - pass.
- Wheel contains `ourd_gui`, `oiec-stm-gui = ourd_gui.app:main`, and the
  compatibility `ourd-gui = ourd_gui.app:main` alias - pass.
- Schema-v1 GUI fixture digest: `4c217e07d70d8feb3e479d8ec1d4d36e6d4ef8f4548ccfc6dc1796d5161c7813`.

The final deterministic validation report and exact source snapshot are created
after this audit so they cover the audit itself.

## Qwen Boundary

On August 21, 2026, `../VisualGrammar2d/qwen_cli.py` was verified as a bounded,
deterministic local drafting interface. The exact requested Ollama tag
`qwen3.8:16b` was not installed. The verified local profile was
`qwen3.8-27b-fast`; it is not silently substituted for 16B. Any Qwen output is
proposal-only and cannot qualify algorithms, satisfy deterministic evidence,
approve a plan, or certify a snapshot.

## Explicit Deferrals and Limits

- PySide6/Qt migration remains deferred until the interaction contract is stable.
- GLTF/GLB and interactive OpenGL geometry views remain deferred; OBJ/STL/PLY are bounded metadata-only inspections.
- JPEG preview depends on the host Tk decoder and may remain metadata-only.
- The semantic terminal intentionally is not an unrestricted PTY.
- Model preflight remains observational in the GUI and does not make network requests.
- Rollback is requested through recorded governed rollback state; the GUI never directly restores files.
- Performance telemetry is diagnostic and host-dependent; it does not weaken correctness or evidence gates.
- Pixel-level screenshot tests are not used as sole evidence; behavior is covered by pure view-model tests and headless construction smoke.

## Release State

```text
FEATURE_COMPLETE
  -> deterministic validation report
  -> exact candidate snapshot and report hashes
  -> HUMAN_APPROVAL_REQUIRED
```

No certification claim is made by this audit.
