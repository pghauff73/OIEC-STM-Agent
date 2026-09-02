# OURD GUI Safety Boundary

**Date:** 2026-08-31

## Primary Invariant

```text
GUIAuthority <= AgentAuthority
```

The GUI may request, display, compare, simulate, replay, and export. It may not
grant capability, invent evidence, authorize on behalf of a person, bypass EON,
or mutate repository files directly.

## Mutation Boundary

- View modules are statically prohibited from importing subprocess execution, EON adapters, transaction managers, or the legacy agent mutation path.
- C0/C1 semantic terminal commands may execute through registered deterministic adapters.
- C2 is forced through simulation.
- C3-C5 terminal requests compile only; authorization and execution remain separate controls.
- C4 and C5 remain blocked when the core denies them.
- Execution requires the current plan snapshot and, when required, an exact unexpired human approval for the same plan hash.
- Rejecting approval creates no execution request.
- Agent Chat calls the existing `OURDAgent` tool dispatcher. It does not expose
  a new write API, shell bypass, or GUI-owned capability grant.
- Every chat turn uses short-lived core ownership. C3 or higher behavior remains
  impossible without the same external authority, governance, evidence gate,
  EON action, exact candidate binding, and approval required outside the GUI.

## Untrusted Data

- Object envelopes are schema-validated and content-address checked before display.
- Core event payload and chain hashes are validated before authoritative replay.
- Partial event lines are ignored until complete.
- JSON/details are depth, count, string, and output bounded.
- Secret-like fields such as passwords, API keys, private keys, and access tokens are redacted in detail and export projections.
- Artifact paths are resolved beneath `.ourd-agent/egcf`; traversal fails closed.
- HTML and SVG are passive text. No scripts, network loads, or embedded active content execute.
- OBJ, STL, and PLY parsers return bounded metadata only.

## Model Boundary

Qwen and compatible model metadata are observational. Agent Chat may
invoke existing governed tools, inspect the repository, draft candidates, or
critique, but model output is never evidence, approval, qualification, or
execution authority. A requested model tag is not silently replaced by another
installed model.

The exact `oiec-stm-sr-AgentICPI` launcher may bootstrap the verified local
Qwen profile before Tk starts. Bootstrap selects the `llama_cpp_process`
provider and maps the product alias `qwen3.8:27B-Fast` openly to
`qwen3.8-27b-direct`. Exact runner, GGUF, digest, llama.cpp source, build, and
grammar checks happen at provider preflight. The profile never pulls, starts a
model service, creates a model, or substitutes a model. No capability, evidence,
governance, approval, EON, or mutation authority is created by model readiness.

Chat history is bounded to user and assistant messages before each provider
request. `New Chat` advances a projection boundary without deleting historical
events. `Stop` is cooperative: cancellation is checked before preflight, before
each model step, during provider streaming when supported, after each provider
response, and before every tool dispatch. The direct process provider terminates
the active runner process when a streaming callback requests cancellation.

ICPI file and folder references are converted into a snapshot-bound context
envelope with hard limits on references, files, traversal, hashing, and preview
bytes. The Context Inspector redacts preview bodies by default and can reveal
only the already bounded in-memory text after an explicit user action. GUI
journal events store envelope identity and counts only. Core `run_started`
events store a task digest and size metrics only, preventing the structured
context body from being duplicated into the append-only trace.

Confirmation-required natural-language turns build the complete envelope before
the confirmation dialog. The resulting non-authoritative receipt binds the
exact route, source snapshot, envelope and budget signatures, model-input
SHA-256, reference/file counts, and pinned-context draft. The controller verifies
the accepted receipt before task creation and again immediately before provider
invocation. Rejection starts no model turn; snapshot drift or any context identity
change invalidates acceptance. Receipt audit metadata stores identities and
counts only, never the confirmation or model-input bodies. This confirmation is
not an EON approval and cannot authorize mutation.

Pinned context is an immutable non-authoritative session projection capped at
32 canonical workspace paths. Attach validates the complete draft envelope
before replacing the current pinned state. Natural-language routing visibly
includes the pins; slash commands never inherit them. Detach and New Chat remove
pins without deleting prior audit events. A controller invariant rejects any
model turn whose context envelope omits a pinned path or whose pinned draft is
bound to a different source snapshot. Snapshot drift is never silently accepted:
`/context` computes a bounded read-only delta and `/context --refresh` explicitly
installs the observed draft. Delta records classify files as unchanged, changed,
missing, new, or indeterminate and persist only identities and counts. Attach
and partial detach also reject stale sets; clearing all pins remains safe because
it accepts no changed content.

## Export Boundary

Evidence and assurance exports are clearly marked non-authoritative and are
stored only under `.ourd-agent/gui/exports`. They preserve canonical IDs,
hashes, snapshots, gaps, conflicts, unknowns, and limitations while redacting
secret-like fields.

## Formal-Writing Boundary

- `FormalWritingView` renders inert text and immutable projections. It imports
  no writing service, agent, transaction, approval, or EON mutation owner.
- The standalone and embedded surfaces use one `FormalWritingController`, one
  worker, a queue capped at 1,000 events, and cooperative phase-boundary
  cancellation. `Stop After Current Phase` does not claim immediate
  interruption of a synchronous extraction or rendering phase.
- Source and rubric paths are workspace-bound, regular non-symlink files. The
  GUI rejects more than 500 inputs, files over 32 MiB, or a combined selection
  over 256 MiB before worker allocation. Unsupported formats fail closed.
- Signed result/source artifacts are limited to 32 MiB and reconstructed through
  their dataclass signatures. Malformed, missing, stale, drifted, or
  signature-invalid artifacts remain diagnostics and are never projected as a
  valid result.
- Source text, HTML text, PDF metadata, OCR output, citations, filenames, and
  draft bodies cannot set network policy, authority, output paths, OCR policy,
  confirmation state, or tool availability. Adversarial source tests verify
  that instruction-like text remains data.
- PDF preview is optional, inert, workspace-contained, and pixel bounded. PDF
  actions, scripts, attachments, links, and macros are never executed. OCR is
  unavailable unless PyMuPDF, Pillow, and `pytesseract` are installed and the
  user explicitly permits OCR.
- Audit statuses and novelty classifications are displayed exactly. The GUI
  cannot convert `REVISION_REQUIRED` or `EVIDENCE_INSUFFICIENT` to qualified,
  accept potential novelty, register an SAA proposal, or create an algorithm
  qualification.
- Diagnostic export requires an explicit destination, is atomic and bounded,
  and applies the canonical string/key redactor. It is labelled diagnostic and
  does not apply a document.
- Governed preparation requires an exact persisted draft, audit, outputs,
  authority digest, source hashes, draft SHA, and typed confirmation of the
  exact request signature. Drift invalidates the preview. The only result is a
  prepared transaction and EON action pending evidence and human approval;
  the GUI exposes no approval or apply shortcut.
