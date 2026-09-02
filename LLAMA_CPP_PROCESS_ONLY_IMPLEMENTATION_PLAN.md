# Llama.cpp Process-Only Provider Implementation Plan

**Plan version:** 1.0  
**Plan date:** 2026-09-01, Australia/Brisbane  
**Status:** Candidate implementation plan; not implementation authority, certification, or release approval  
**Primary objective:** Replace all runtime use of `ourd/providers/openai_responses.py` with the direct `llama_cpp_process` method  
**Completion rule:** `openai_responses.py` must not be imported, selected, configured, documented as an active path, or required by tests, GUI launch, supervisor mode, or ICPI chat execution  

## 1. Executive Decision

Move OIEC-STM-AgentICPI to a process-owned local model path:

```text
GUI / CLI / supervisor / ICPI chat
  -> ProviderConfig(provider_kind="llama_cpp_process")
  -> LlamaCppProcessProvider
  -> exact runner binary
  -> exact GGUF model file
  -> exact grammar directory
  -> JSON-lines stdin/stdout protocol
  -> bounded tool-call or final-text response
```

The replacement is not a broad redesign of governance. The stable boundary
remains `ModelProvider`: the agent asks for `preflight()`, `create_response()`,
and `create_responses()`. The implementation behind that boundary becomes the
direct `llama_cpp_process` path only.

The final source tree must not use `openai_responses.py`. Keeping the file as an
unreferenced historical artifact is allowed only if the binary gate proves it is
not importable through `ourd.providers`, not selected by configuration, and not
referenced by runtime code or tests. The stronger preferred final state is to
delete `ourd/providers/openai_responses.py` after migration.

## 2. Current Coupling Snapshot

Current inspection shows these active coupling classes:

| Area | Current coupling | Required final state |
| --- | --- | --- |
| Provider defaults | `ourd/providers/base.py` defaults `provider_kind` to `openai_responses` | Default becomes `llama_cpp_process` |
| Provider registry | `ourd/providers/__init__.py` imports and returns `OpenAIResponsesProvider` | Registry returns only `LlamaCppProcessProvider`; no `OpenAIResponsesProvider` export |
| Agent defaults | `ourd/agent.py` reads `OURD_PROVIDER` defaulting to `openai_responses` | Agent defaults to `llama_cpp_process` and direct-runner env vars |
| CLI | `ourd/cli.py` accepts both providers and defaults to `openai_responses` | CLI accepts only `llama_cpp_process` unless an explicitly separate remote plugin is later added |
| GUI | `ourd_gui/app.py` accepts both providers and defaults to `openai_responses` | GUI defaults to and validates only `llama_cpp_process` |
| Auto Qwen | `ourd_gui/qwen_bootstrap.py` starts/verifies Ollama via HTTP | Replace with direct runner/model bootstrap or remove auto-Ollama startup |
| Model backend UI | `ourd_gui/model_backend.py` labels provider as `openai_responses` | Display process backend, runner digest, model digest, context, GPU layers, grammar profile |
| Tests | `tests/test_provider.py`, `tests/test_reasoning.py`, GUI tests import or assert OpenAI/Ollama behavior | Rewritten around direct process provider; HTTP tests removed or quarantined outside default suite |
| Docs | README and docs describe Ollama/OpenAI-compatible launch | Docs describe direct runner launch; old webserver path is historical only |
| Supervisor plan | Live commands use OpenAI-compatible Ollama route | Supervisor commands use direct process route and exact local artifacts |

## 3. Non-Negotiable Invariants

1. `openai_responses.py` is not used by runtime code.
2. No default path falls back to HTTP, Ollama `/v1/responses`, or OpenAI SDK.
3. Model output remains proposal-only and cannot create approval, authority, certification, or release status.
4. Workspace mutation remains governed by authority manifests, exact candidate hashes, EON, evidence gates, and approval records.
5. Missing runner, model, grammar, build, or digest evidence fails closed before a model request.
6. The direct model call is supervised as a local process with bounded deadline, cancellation, stderr capture, and shutdown.
7. Context budgeting remains enforced before the process call.
8. Structured output uses grammar-first JSON rather than HTTP `json_object` response modes.
9. Provider identity is content-addressed: runner binary hash, GGUF hash, llama.cpp source identity, build identity, grammar hashes, and runtime descriptor.
10. Tests must prove absence of the old provider, not merely successful use of the new one.

## 4. Target Provider Contract

Preserve this contract:

```python
class ModelProvider(Protocol):
    config: ProviderConfig

    def preflight(self) -> dict[str, object]: ...

    def create_response(
        self,
        *,
        instructions: str,
        input_items: list[object],
        tools: list[dict[str, object]],
    ) -> object: ...

    def create_responses(
        self,
        *,
        requests: list[Mapping[str, object]],
        max_responses: int,
    ) -> list[object]: ...
```

Change the supported implementation set to:

```text
provider_kind = "llama_cpp_process"
implementation = ourd.providers.llama_cpp_process.LlamaCppProcessProvider
transport = local subprocess JSONL over stdin/stdout
```

Remove all active support for:

```text
provider_kind = "openai_responses"
implementation = ourd.providers.openai_responses.OpenAIResponsesProvider
transport = OpenAI SDK, Ollama HTTP, /api/version, /api/tags, /api/show, /responses
```

## 5. Direct-Runner Configuration Contract

The new default configuration must be explicit enough to fail closed:

| Field | Source | Required behavior |
| --- | --- | --- |
| `provider_kind` | CLI/env/default | Must be `llama_cpp_process` |
| `model` | CLI/env/default | Human-readable model ID, e.g. `qwen3.8-27b-direct` |
| `runner_path` | `--llama-runner` / `OURD_LLAMA_RUNNER` | Must point to executable runner |
| `model_path` | `--llama-model-path` / `OURD_LLAMA_MODEL_PATH` | Must point to exact GGUF |
| `expected_model_sha256` | `--llama-model-sha256` / `OURD_LLAMA_MODEL_SHA256` | Must match observed GGUF hash when provided; final qualification should provide it |
| `llama_cpp_root` | `--llama-cpp-root` / `OURD_LLAMA_CPP_ROOT` | Must identify source checkout |
| `llama_cpp_build_dir` | `--llama-cpp-build-dir` / `OURD_LLAMA_CPP_BUILD_DIR` | Must identify build output and shared libraries |
| `llama_grammar_dir` | `--llama-grammar-dir` / `OURD_LLAMA_GRAMMAR_DIR` | Defaults to repo grammar directory; hashes recorded |
| `llama_context_tokens` | `--llama-context` / `OURD_LLAMA_CONTEXT` | Runtime context for direct runner |
| `context_budget_tokens` | `--context-budget` / `OURD_CONTEXT_BUDGET` | Maximum serialized prompt/tool budget before call |
| `max_output_tokens` | `--max-output-tokens` / `OURD_MAX_OUTPUT_TOKENS` | Reserved output budget and runner output cap |
| `llama_seed` | `--llama-seed` / `OURD_LLAMA_SEED` | Deterministic response seed |
| `llama_temperature_bp` | `--llama-temperature-bp` | Basis-point temperature |
| `llama_top_p_bp` | `--llama-top-p-bp` | Basis-point nucleus sampling |
| `llama_top_k` | `--llama-top-k` | Top-k sampling cap |
| `timeout_seconds` | `--timeout-seconds` / `OURD_TIMEOUT_SECONDS` | Whole process request deadline |

The following fields become unsupported in default runtime paths:

```text
base_url
api_key
json_object_output
response_temperature_bp
response_top_p_bp
response_seed
max_transport_retries
```

If these fields remain in `ProviderConfig` for compatibility, they must be
ignored by direct process execution and must not be required for launch.

## 6. Implementation Phases

### Phase 0: Baseline Freeze

**Goal:** Capture current behavior before removing the old provider.

1. Record current references:
   - `rg -n "openai_responses|OpenAIResponsesProvider" ourd ourd_gui tests tools README.md docs pyproject.toml`
   - `rg -n "base_url|api_key|json_object_output|auto-qwen|/responses|/api/tags|/api/show" ourd ourd_gui tests tools README.md docs`
2. Record current direct-provider tests:
   - `python -m unittest tests.providers.test_llama_cpp_process`
3. Record CLI and GUI parser tests:
   - `python -m unittest tests.test_cli tests.gui.test_app`
4. Record current failure expectation for old-provider removal in an audit note.

**Gate P0:** Reference inventory exists and names every source/test/docs area
that must change.

### Phase 1: Strengthen the Direct Provider First

**Goal:** Make `LlamaCppProcessProvider` complete enough to be the only provider.

1. Confirm `preflight()` returns:
   - provider name;
   - endpoint type;
   - runner path;
   - runner binary SHA-256;
   - GGUF path;
   - GGUF SHA-256;
   - llama.cpp source commit and dirty-state hash;
   - build library hashes;
   - grammar file hashes;
   - runtime descriptor;
   - context and output budgets;
   - cancellation/deadline/grammar capability flags.
2. Confirm `create_response()` returns the same response shape the agent expects:
   - final text response when no tool call is required;
   - function-call shaped output when a tool is selected;
   - parseable JSON object for grammar-enforced tool output;
   - `ProviderError` or `ContextBudgetError` for bounded failures.
3. Confirm `create_responses()` supports reasoning batches without HTTP features.
4. Confirm process shutdown works on:
   - normal close;
   - deadline exceeded;
   - malformed JSONL;
   - cancellation;
   - runner crash;
   - parent shutdown.

**Gate P1:** Direct provider unit tests pass without importing
`openai_responses.py`.

### Phase 2: Remove Provider Registry Use of OpenAI Responses

**Goal:** Make `ourd.providers` unable to select the old provider.

1. Edit `ourd/providers/__init__.py`:
   - remove `from .openai_responses import OpenAIResponsesProvider`;
   - remove `OpenAIResponsesProvider` from `__all__`;
   - remove branch returning `OpenAIResponsesProvider`;
   - reject `openai_responses` with a clear error.
2. Edit `ourd/providers/base.py`:
   - change `provider_kind` default to `llama_cpp_process`;
   - mark webserver-only fields as deprecated or move them behind a removed compatibility section;
   - keep only fields required by the direct provider in active docs.
3. Add a regression test:
   - importing `ourd.providers` does not import `ourd.providers.openai_responses`;
   - `create_provider(ProviderConfig(..., provider_kind="openai_responses"))` fails closed;
   - `ProviderConfig(model="...")` defaults to `llama_cpp_process`.

**Gate P2:** Package provider selection cannot instantiate or export
`OpenAIResponsesProvider`.

### Phase 3: Migrate Agent Defaults

**Goal:** New agent instances default to direct process execution.

1. Edit `ourd/agent.py`:
   - change `OURD_PROVIDER` default from `openai_responses` to `llama_cpp_process`;
   - stop reading `OURD_BASE_URL`, `OPENAI_BASE_URL`, `OURD_API_KEY`, and `OPENAI_API_KEY` for default local operation;
   - read direct runner defaults from `OURD_LLAMA_*` environment variables;
   - preserve context-budget recovery;
   - preserve provider preflight trace;
   - preserve collision recording on preflight and response failures.
2. Remove source-prioritization assumptions that score `openai_responses.py` as a provider owner.
3. Add tests for:
   - default `OURDAgent` provider config is `llama_cpp_process`;
   - missing direct-runner configuration fails at preflight, not after partial model setup;
   - secrets from old OpenAI env vars are not required or persisted.

**Gate P3:** Agent construction and chat turn setup have no old-provider
default path.

### Phase 4: Migrate CLI Defaults and Arguments

**Goal:** The CLI cannot accidentally select the webserver provider.

1. Edit `ourd/cli.py`:
   - default `--provider` to `llama_cpp_process`;
   - restrict choices to `llama_cpp_process`;
   - remove or hide `--base-url`, `--api-key`, and `--json-object-output` from active direct-runner help;
   - keep direct options: runner, model path, model SHA, source root, build dir, grammar dir, context, GPU layers, threads, seed, temperature, top-p, top-k.
2. Update command validation:
   - if provider is direct, require runner/model/source/build before model call;
   - missing paths produce deterministic `ProviderError` messages;
   - no fallback to HTTP when paths are missing.
3. Update CLI tests:
   - default provider is `llama_cpp_process`;
   - `openai_responses` is rejected;
   - `--base-url` and `--api-key` are not required for direct execution;
   - direct process arguments populate `ProviderConfig`.

**Gate P4:** CLI help and parser make the direct process provider the only
runtime provider.

### Phase 5: Migrate GUI Defaults and Startup

**Goal:** Agent Chat and ICPI launch use the direct process provider only.

1. Edit `ourd_gui/app.py`:
   - default provider to `llama_cpp_process`;
   - remove `openai_responses` from choices;
   - change constructor defaults to direct provider;
   - remove OpenAI/Ollama API key and base URL assumptions from model startup;
   - pass direct runner/model/build/grammar settings into `ProviderConfig`.
2. Replace `--auto-qwen` behavior:
   - either remove it;
   - or redefine it as direct-runner bootstrap that verifies local runner/GGUF/build/grammar without Ollama HTTP.
3. Replace `ourd_gui/qwen_bootstrap.py`:
   - preferred: create `ourd_gui/llama_cpp_bootstrap.py`;
   - record runner digest, model digest, source identity, build identity, grammar identity, and optional warmup result;
   - remove HTTP calls to Ollama `/api/version`, `/api/show`, `/api/tags`, and warmup chat.
4. Update `ourd_gui/model_backend.py`:
   - report provider as `llama_cpp_process`;
   - use `process://<runner-sha>` style endpoint labels;
   - display direct local model path identity without exposing unnecessary absolute paths when redaction is requested;
   - remove active `api_key` terminology from model backend display.
5. Update GUI controller events:
   - replace `icpi_qwen_bootstrap` with `icpi_llama_cpp_bootstrap` or version it;
   - ensure event payload has no credentials and no model response bodies;
   - include process PID only when useful for supervisor diagnostics.

**Gate P5:** GUI launch, Agent Chat, ICPI dispatch, model panel, and supervisor
events no longer require or display HTTP provider settings.

### Phase 6: Remove HTTP/OpenAI Provider Tests

**Goal:** The default test suite proves the old provider is absent.

1. Replace `tests/test_provider.py`:
   - move direct-provider generic tests into `tests/providers/test_llama_cpp_process.py`;
   - move shared helper tests to provider-neutral modules;
   - import token estimation from `ourd.context_budget`, not from the old provider file.
2. Rewrite reasoning tests that instantiate `OpenAIResponsesProvider`:
   - use a fake `ModelProvider` where transport is irrelevant;
   - use `LlamaCppProcessProvider` fixtures where direct process behavior matters.
3. Rewrite GUI tests:
   - default provider captured by app tests is `llama_cpp_process`;
   - auto bootstrap tests cover direct runner verification or are removed;
   - visual asset tests do not instantiate `OpenAIResponsesProvider`.
4. Add no-use tests:
   - `sys.modules` does not contain `ourd.providers.openai_responses` after importing `ourd.providers`;
   - runtime package `__all__` has no `OpenAIResponsesProvider`;
   - provider choices do not include `openai_responses`;
   - direct launch works with fake runner fixtures.

**Gate P6:** `python -m unittest discover` passes with no test importing
`OpenAIResponsesProvider`.

### Phase 7: Delete or Quarantine `openai_responses.py`

**Goal:** Remove the old provider from active source.

Preferred path:

1. Delete `ourd/providers/openai_responses.py`.
2. Remove generated docs/concepts that describe it as active source.
3. Remove stale imports from docs tooling if present.
4. Confirm no package data or build metadata references it.

Fallback path if deletion is too disruptive in one patch:

1. Keep the file temporarily but rename it outside importable provider package
   scope, for example `docs/archived/openai_responses_legacy.md` as prose only.
2. Do not leave an importable Python module at
   `ourd/providers/openai_responses.py`.
3. Add a test proving `import ourd.providers.openai_responses` fails.

**Gate P7:** The Python module `ourd.providers.openai_responses` is not
importable in the completed runtime tree.

### Phase 8: Update Supervisor and Heavy-Test Plans

**Goal:** Supervisor mode uses direct process execution.

1. Update `ICPI_SUPERVISOR_HEAVY_TEST_PLAN.md`:
   - replace live OpenAI-compatible/Ollama commands with direct runner commands;
   - change frozen identity fields to runner digest, GGUF digest, source/build/grammar identity;
   - remove `base-url`, `api-key`, `transport-retries`, and Ollama keepalive fields;
   - keep seed, timeout, context, max output, and quality threshold gates.
2. Update chat scenario runner:
   - direct-provider live lane must validate runner/model/grammar before running scenarios;
   - no scenario command may construct `--provider openai_responses`;
   - live model identity snapshot must report process backend.
3. Update report artifacts:
   - `provider_identity_before`;
   - `provider_identity_after`;
   - `human-review.json`;
   - gate results;
   - requirement audit.
4. Add regression:
   - generated supervisor commands do not contain `openai_responses`;
   - live direct-provider preflight is captured before model invocation.

**Gate P8:** Supervisor deterministic and live-direct paths use only
`llama_cpp_process` provider identity.

### Phase 9: Update Documentation

**Goal:** User-facing docs stop recommending the webserver path.

1. Update `README.md`:
   - make direct runner the primary setup;
   - document required paths and digest checks;
   - remove active `OURD_BASE_URL`, `OPENAI_BASE_URL`, `OURD_API_KEY`, `OPENAI_API_KEY`, and Ollama `/v1` instructions from the ICPI path;
   - keep any remote-provider history only in a clearly labelled archive section if needed.
2. Update `docs/OIEC_STM_SR_AGENTICPI.md`:
   - replace `--auto-qwen` Ollama startup with direct runner startup or no automatic startup;
   - describe JSONL process protocol at a high level;
   - document fail-closed missing-model behavior.
3. Update `docs/OURD_AGENT_GUI.md` and `docs/GUI_EVENT_SCHEMA.md`:
   - model panel fields;
   - supervisor bootstrap event;
   - no credential persistence guarantee.
4. Rebuild generated docs with `tools/build_docs_site.py`.
5. Confirm generated HTML/SVG references do not present `openai_responses.py` as active.

**Gate P9:** Docs describe only the direct local process method for active model
execution.

### Phase 10: Security and Redaction Review

**Goal:** Removing HTTP credentials does not weaken audit safety.

1. Remove credential-specific assumptions where obsolete.
2. Keep generic secret redaction for:
   - accidental old env vars;
   - paths containing tokens;
   - runner diagnostics;
   - model output.
3. Confirm supervisor event payloads do not persist:
   - API keys;
   - bearer tokens;
   - full prompts;
   - full model responses;
   - unredacted sensitive paths unless explicitly intended.
4. Add regression tests for old variables:
   - setting `OPENAI_API_KEY` does not affect provider selection;
   - setting `OURD_BASE_URL` does not switch provider;
   - old credential values do not appear in event projection.

**Gate P10:** Security tests prove old webserver credentials are inert and not
persisted.

### Phase 11: Direct-Runner Qualification

**Goal:** Prove real direct model operation.

1. Run metadata preflight without generation:
   - runner executable exists and is executable;
   - GGUF hash matches;
   - llama.cpp source/build identity captured;
   - grammar files hashed;
   - descriptor returned over JSONL.
2. Run one deterministic tool-call smoke:
   - fixed seed;
   - fixed prompt;
   - one simple tool schema;
   - expected function-call output;
   - no workspace mutation.
3. Run one final-text smoke:
   - fixed seed;
   - no tools;
   - bounded response;
   - output captured by hash and quality notes.
4. Run one cancellation smoke:
   - long prompt or fault runner;
   - cancellation requested;
   - process returns or is killed;
   - state remains restorable.
5. Run one context overflow smoke:
   - request exceeds effective budget;
   - no completion request is sent;
   - failure is `ContextBudgetError`.

**Gate P11:** Direct live model evidence exists without using HTTP or
`openai_responses.py`.

### Phase 12: Full Validation and No-Use Audit

**Goal:** Prove the migration is complete.

Run these checks:

```bash
python -m unittest tests.providers.test_llama_cpp_process
python -m unittest tests.test_cli tests.gui.test_app tests.gui.test_model_backend
python -m unittest tests.test_context_budget tests.test_provider tests.test_reasoning
python -m unittest discover
python tools/build_docs_site.py
git diff --check
```

Run no-use checks:

```bash
rg -n "openai_responses|OpenAIResponsesProvider" \
  ourd ourd_gui tests tools oiec_stm_sr_agenticpi.py pyproject.toml README.md docs \
  --glob '!docs/**.html'
```

Expected result after final migration:

```text
no matches
```

If a historical mention is intentionally kept, it must be outside active source,
excluded from runtime/package discovery, and explicitly listed in the final
audit. The default target remains zero matches.

Run import checks:

```bash
python - <<'PY'
import importlib
import sys
import ourd.providers as providers

assert "OpenAIResponsesProvider" not in getattr(providers, "__all__", ())
assert "ourd.providers.openai_responses" not in sys.modules
try:
    importlib.import_module("ourd.providers.openai_responses")
except ModuleNotFoundError:
    pass
else:
    raise SystemExit("openai_responses module is still importable")
PY
```

**Gate P12:** Tests, docs, import checks, and no-use grep prove the old provider
is gone from active use.

## 7. Required Code Changes by File

| File | Required change |
| --- | --- |
| `ourd/providers/base.py` | Default to `llama_cpp_process`; document direct-runner fields as active |
| `ourd/providers/__init__.py` | Remove old-provider import/export/selection |
| `ourd/providers/openai_responses.py` | Delete or make non-importable outside runtime package |
| `ourd/providers/llama_cpp_process.py` | Ensure parity response shape, preflight identity, lifecycle, cancellation, and batching |
| `ourd/providers/qwen38.py` | Keep as direct-runner config factory; update defaults if needed |
| `ourd/agent.py` | Default env/config to direct provider; remove webserver env defaults |
| `ourd/cli.py` | Restrict provider choices and help to direct process |
| `ourd_gui/app.py` | Default GUI to direct process; remove active Ollama/OpenAI startup |
| `ourd_gui/qwen_bootstrap.py` | Replace with direct-runner bootstrap or remove |
| `ourd_gui/model_backend.py` | Report process backend identity |
| `ourd_gui/controller.py` | Keep credential-free event projection; update bootstrap event type |
| `tools/icpi_chat_scenario_runner.py` | Generate direct-provider live commands and identity snapshots |
| `tools/icpi_chat_scenario_generator.py` | No provider change unless scenario tags mention old provider |
| `tests/providers/test_llama_cpp_process.py` | Promote to primary provider suite |
| `tests/test_provider.py` | Rewrite or replace old HTTP provider coverage |
| `tests/test_cli.py` | Update default provider and rejection tests |
| `tests/gui/test_app.py` | Update GUI defaults and bootstrap assertions |
| `tests/gui/test_model_backend.py` | Update backend labels |
| `tests/gui/test_visual_assets.py` | Remove old provider instantiation |
| `tests/test_reasoning.py` | Replace old provider instances with direct/fake providers |
| `README.md` | Active setup becomes direct local runner |
| `docs/*.md` | Active documentation becomes direct local runner |

## 8. Required Test Additions

1. `test_provider_registry_has_no_openai_responses_export`
2. `test_openai_responses_provider_kind_is_rejected`
3. `test_default_provider_kind_is_llama_cpp_process`
4. `test_cli_rejects_openai_responses_provider`
5. `test_gui_defaults_to_llama_cpp_process`
6. `test_openai_env_vars_do_not_select_provider`
7. `test_direct_preflight_records_runner_model_build_and_grammar_hashes`
8. `test_direct_completion_never_sends_request_after_context_overflow`
9. `test_direct_runner_deadline_kills_process_and_saves_diagnostic`
10. `test_direct_runner_cancellation_leaves_state_restorable`
11. `test_supervisor_live_command_contains_no_openai_responses`
12. `test_importing_ourd_providers_does_not_import_old_provider_module`

## 9. Rollback Strategy

Rollback must not silently restore `openai_responses.py` as an active path.

If direct-provider migration fails:

1. keep the branch in a non-release state;
2. restore only the last known-good source snapshot for local development;
3. record why direct provider failed;
4. do not change docs to claim direct provider completion;
5. do not re-enable HTTP provider by default;
6. require an explicit human decision before reintroducing any remote/webserver provider.

## 10. Completion Definition

The migration is complete only when all are true:

1. `provider_kind` defaults to `llama_cpp_process` everywhere.
2. `openai_responses` is not an accepted provider kind in CLI, GUI, agent defaults, or provider registry.
3. `OpenAIResponsesProvider` is not exported by `ourd.providers`.
4. `ourd.providers.openai_responses` is not imported by normal package import.
5. Preferably, `ourd/providers/openai_responses.py` does not exist.
6. If the old file exists, it is not importable and is explicitly non-runtime.
7. No runtime source, tests, tools, README, or active docs reference `openai_responses` or `OpenAIResponsesProvider`.
8. Direct runner preflight captures exact runner, model, source, build, grammar, and runtime identity.
9. Direct runner completion supports final text, tool-call JSON, reasoning batches, context overflow, timeout, cancellation, and crash diagnostics.
10. Full test discovery passes.
11. Docs are regenerated from current source.
12. Supervisor direct-provider qualification passes or is explicitly marked as requiring external live-model approval without claiming completion.

## 11. Final Audit Template

The implementation should end with a short audit table:

| Gate | Verdict | Evidence |
| --- | --- | --- |
| Provider registry has no old provider | PASS/FAIL | command output |
| CLI rejects old provider | PASS/FAIL | test name |
| GUI defaults to direct provider | PASS/FAIL | test name |
| Direct preflight identity complete | PASS/FAIL | test name/report |
| Direct completion smoke passes | PASS/FAIL | run artifact |
| Context overflow fails before completion | PASS/FAIL | test name |
| Cancellation/restoration passes | PASS/FAIL | test name |
| No-use grep has zero matches | PASS/FAIL | command output |
| Full unittest discovery passes | PASS/FAIL | command output |
| Docs regenerated | PASS/FAIL | command output |

No row may be waived. Any `FAIL`, `NOT_RUN`, or indirect evidence means the
implementation is incomplete.
