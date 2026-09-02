# OIEC-STM-SR-AgentICPI

OIEC-STM-SR-AgentICPI is the interactive command-prompt interface for the
OIEC-STM-Agent workbench. It combines a Codex-like natural-language composer
with deterministic intent interpretation, explicit context references,
bounded command history, live route previews, governed execution, and the
existing OIEC-SR reasoning inspector.

## Purpose

The interface exists to make governed reasoning practical without turning the
language model into an authority engine. Natural language may identify a goal,
request an explanation, propose a candidate, ask for verification, or request
an action. Deterministic code classifies and routes that request before the
model is called. Policy, evidence gates, EON actions, approvals, transactions,
and CFEL remain the only path to repository mutation.

## Launch

Install the repository in an isolated environment and launch the canonical
executable. The custom deterministic build backend does not expose the PEP 660
editable-install hook, so use a normal wheel installation rather than
`pip install -e`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install .
oiec-stm-sr-agent-icpi --repo /path/to/repository
```

The exact-name compatibility alias requested for the product is also installed:

```bash
oiec-stm-sr-AgentICPI --repo /path/to/repository
```

On August 30, 2026, this exact case-sensitive product command gained automatic
local Qwen profile selection. When no provider, model, runner path, or model
path has been supplied by command-line option or OIEC environment configuration,
it:

1. resolves the product label `qwen3.8:27B-Fast` explicitly to
   `qwen3.8-27b-direct`;
2. selects the `llama_cpp_process` provider;
3. records any configured runner path, GGUF path, digest, llama.cpp source,
   build directory, and grammar directory;
4. uses an 8192-token llama.cpp context by default;
5. configures Agent Chat with a 6,000 token context budget, 1,400 output tokens,
   and reasoning effort `none`.

The profile never pulls, starts a service, or silently substitutes a model.
Exact runner and GGUF validation happens during provider preflight, where digest,
source, build, grammar, deadline, and cancellation support are bound into the
provider identity.

Automatic startup can be disabled or requested explicitly:

```bash
oiec-stm-sr-AgentICPI --repo . --no-auto-qwen
python3 oiec_stm_sr_agenticpi.py --repo . --auto-qwen
```

`--no-qwen-warmup`, `--qwen-startup-timeout`, and `--qwen-warmup-timeout` remain
deprecated compatibility flags; direct-process preflight owns startup and
deadline enforcement. Explicit provider/model/runner/model path options or
`OURD_PROVIDER`, `OURD_MODEL`, `OURD_LLAMA_RUNNER`, or
`OURD_LLAMA_MODEL_PATH` disable implicit Qwen profile selection; `--auto-qwen`
remains an explicit override.

The historical `oiec-stm-gui` and `ourd-gui` commands remain available. A
source-tree launch is possible with:

```bash
python3 oiec_stm_sr_agenticpi.py --repo /path/to/repository
```

## Prompt Grammar

Ordinary text is interpreted into one of eleven explicit modes:

```text
INSPECT  EXPLAIN  REASON  COMPARE  PLAN  PROPOSE
WRITE    TEST     EXECUTE RECOVER  EXPORT
```

Context references use bounded syntax. `@file[path]` requires an existing
file, `@folder[path]` requires an existing directory, and `@path[path]` may
refer to a prospective target. `#evidence[id]` binds an evidence identifier and
`!constraint[text]` records an explicit constraint. Every path passes through
the workspace canonicalizer, so absolute paths, traversal, workspace escape,
and internal agent-state access fail closed.

## Slash Commands

The prompt supports deterministic slash commands that are parsed without a
shell:

```text
/new  /status  /help  /model  /preflight  /context [refresh|--refresh]
/attach  /detach
/files  /evidence  /hypotheses  /paths  /topology  /certificate
/diff  /approve  /deny  /stop  /export  /exit
```

Shell metacharacters, redirects, substitutions, and unknown slash commands are
rejected. Partial prefixes such as `/to` remain an autocomplete state and show
matching commands instead of being treated as executable input. Pressing Tab
completes only the slash-command token; existing arguments remain unchanged and
no command is submitted by completion.

## Live Route Preview

The composer previews the deterministic route before submission. A preview
shows the interpreted mode or slash command, destination, proposed risk,
ambiguity score, and whether confirmation is required. For example, an inspect
request routes to `agent.read_only`, while a fix request routes to
`agent.governed_candidate` and requires confirmation. The preview is advisory
state derived from canonical input; it never grants authority.

## Bounded Context Envelopes

Before a natural-language turn reaches the model, AgentICPI converts resolved
references into a content-addressed context envelope. The envelope binds the
route identity, exact source snapshot, interpreted objective, constraints,
evidence identifiers, attachment records, bounded file metadata, bounded text
previews, and a non-authoritative control warning. The GUI transcript preserves
the person's original request while the model receives the structured envelope;
the GUI journal records the envelope ID and signature rather than duplicating
file preview content into GUI state. The core `run_started` trace similarly
records only the task SHA-256 digest, character count, byte count, and line
count. It does not persist the structured task body.

The default projection admits at most 32 references and 128 unique files. A
folder contributes at most 64 files, directory width is limited to 512 entries,
the total folder traversal is limited to 4,096 entries, and traversal depth is
limited to eight levels. Text preview is limited to 8,192 bytes per file and
65,536 bytes in total. Files larger than 16 MiB are not hashed by the prompt
projection; their omitted hash is labelled rather than guessed. Binary content
is identified and omitted from the text preview. Prospective paths carry no
invented content.

The source snapshot is checked before and after projection and again at the GUI
worker boundary. A queued turn therefore fails closed if the repository changes
between context construction and model invocation. These checks make the
envelope useful evidence about what the model was shown, but the envelope still
cannot grant authority, lower policy risk, approve evidence, or approve an EON
action.

## Exact Confirmation Receipts

For a natural-language route that requires confirmation, AgentICPI constructs
the complete context envelope before asking the person to continue. The
confirmation binds the deterministic route, exact source snapshot, envelope ID
and signature, context-budget signature, reference and file counts, SHA-256 of
the complete structured model input, and any pinned-context and pinned-draft
identities. The dialog therefore describes one exact proposed model request,
not a general permission to act on similar text later.

Accepting or rejecting the dialog creates a deterministic
`InteractionConfirmationReceipt`. An accepted receipt must match the exact
confirmation and envelope at dispatch. The GUI checks it synchronously before
starting a task and checks the current workspace snapshot again in the worker
immediately before provider invocation. The synchronous CLI performs the same
snapshot and envelope verification before calling the agent. Repository drift,
an altered envelope, changed model input, a different route, missing pins, or a
different pinned draft blocks the turn and requires a new projection and
confirmation.

Rejected receipts are recorded and start no model turn. Audit records preserve
receipt, confirmation, route, snapshot, envelope, budget, model-input digest,
counts, and pinned-context identities while explicitly recording that neither
the confirmation body nor the structured model input body was persisted. A
receipt is non-authoritative: it confirms interpretation and model-input
identity only, and cannot grant capability, approve evidence, lower risk,
approve an EON action, or authorize repository mutation.

Pinned draft envelopes add a stricter session rule: a natural-language model
turn is blocked whenever the pinned envelope snapshot differs from the current
workspace snapshot. The interface does not silently rebuild pinned content and
send changed bytes to the model. `/context` performs a bounded read-only check;
`/context --refresh` or `/context refresh` explicitly accepts the observed
snapshot and installs the rebuilt in-memory draft envelope.

## Context Inspector

The right-side Context tab renders the active `InteractionContextEnvelope` as a
read-only projection. It shows the envelope ID and signature, exact source
snapshot, route identity, objective, mode, projection budget, attachments,
evidence references, constraints, unresolved references, file sizes, media
types, exact or omitted hash status, preview byte counts, and truncation state.
The table is hard bounded to 32 attachment rows, 128 file rows, and 64 file paths
per attachment even if a separately constructed envelope declares larger
limits.

The Delta tab compares the active pinned draft with a newly observed bounded
projection. Every path is classified as `unchanged`, `changed`, `missing`,
`new`, or `indeterminate`. `Indeterminate` is fail-closed telemetry used when
the configured size limit omitted an exact content hash and metadata alone
cannot prove equality. A global snapshot change marks the draft stale even when
all pinned files are unchanged.

Text preview bodies are redacted by default. The person may explicitly enable
`Reveal bounded previews` for the active in-memory envelope; this changes only
the view and does not change the envelope or inspector identity. The structured
model input is never included in the inspector projection. Restarting the GUI
removes the in-memory preview bodies, while audit streams retain only the exact
identities and counts needed to prove which envelope was used.

`/context` checks freshness and opens this inspector without replacing the
active draft. `/context --refresh` explicitly applies the observed bounded
projection without invoking the model. `/attach <path...>` validates each
workspace path, adds it to an immutable content-addressed `PinnedContextSet`, builds a
read-only draft envelope from the exact current snapshot, and opens the
inspector. It does not call the model or mutate the repository. Unsafe paths,
malformed bracket syntax, and draft envelopes that exceed traversal/file/preview
budgets fail closed before the pinned set changes.

Pinned context is capped at 32 canonical workspace paths. Every later
natural-language turn receives any missing pinned references before deterministic
interpretation, so the route, confirmation dialog, and context envelope all bind
the same visible targets. The live preview begins with the pinned count and a
prefix of the pinned-context signature. Slash commands are never modified by
pinned context. `/detach <path...>` removes selected paths and `/detach --all`
clears them. `/new` clears both the model conversation boundary and pinned paths.
Adding paths or partially detaching from a stale set is blocked because either
operation would otherwise rebind unchanged pins implicitly; refresh first, or
use `/detach --all` or `/new` to discard the stale set without accepting it.
Pinned state is deliberately in memory only and is not silently restored after a
process restart; append-only GUI events retain its transition signatures and
canonical paths for audit. Each check or refresh records snapshot identities,
freshness, delta counts, and the delta signature without persisting preview
bodies.

## Operational Projections

Projection commands open existing canonical GUI surfaces rather than asking the
model to invent state. `/context` checks and opens the Context Inspector, while
`/context --refresh` explicitly replaces only the in-memory pinned draft.
`/files` opens the repository view, `/evidence` opens
the evidence view, `/hypotheses`, `/paths`, `/topology`, and `/certificate`
open the OIEC-SR inspector, `/diff` opens EON, and `/export` opens artifacts.
Local ICPI commands and their route identities are appended to the GUI event
journal. `/preflight` runs through the GUI worker executor so the Tk event loop
remains responsive.

## Prompt History

The composer keeps a bounded in-memory history of the most recent one hundred
submitted prompts. Consecutive duplicates collapse, and `Ctrl+Up` or
`Ctrl+Down` navigates history while preserving the unfinished draft. History
is a convenience projection; canonical task, chat, evidence, and action records
remain in their existing append-only stores.

## Qwen3.8 Configuration

AgentICPI uses the same provider boundary as the CLI. The direct llama.cpp
profile should bind the reviewed runner, exact GGUF digest, llama.cpp source and
build directories, grammar directory, context, sampler, and GPU-layer settings.
The local model may propose, verify, falsify, and synthesize bounded reasoning
artifacts. It may not approve evidence, enlarge authority, lower policy risk, or
certify its own repository mutations.

## Current Limits

The implemented slices provide deterministic interpretation, routing, exact
context-bound confirmation receipts, session dispatch, live preview,
suggestions, history, projection navigation, local-command journaling, and
asynchronous preflight. `/approve` and `/deny`
intentionally navigate to the EON approval surface instead of manufacturing an
approval from prompt text. Runtime model replacement requires restart with an
explicit provider configuration. Attachment commands project only canonical
workspace paths into a bounded draft envelope; they never load arbitrary host
files or bypass the workspace boundary. Pinned context is session-local rather
than a persistent authority or hidden startup configuration. Snapshot drift
requires an explicit refresh before another pinned model turn.
