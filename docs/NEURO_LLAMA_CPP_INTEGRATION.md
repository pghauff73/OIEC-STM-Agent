# Neuro llama.cpp Interface Integration

## Logic Topology

```text
Need for local governed inference
        |
        v
Neuro interface evidence
        |
        v
Reusable provider-neutral contract
        |
        +----> status and diagnostics
        +----> completion options
        +----> capability descriptor
        +----> metrics and streaming
        |
        v
OIEC compatibility constraints
        |
        +----> one attempt only
        +----> isolated native process
        +----> exact GGUF digest
        +----> no mutation authority
        |
        v
LlamaCppProcessProvider
        |
        v
Qwen3.8 grammar-constrained completion
        |
        v
Evidence, EON, policy, and CFEL remain authoritative
```

## Position

The useful part of `../Neuro-main` is not its application runtime; it is the
clear boundary expressed by `include/neuro/local_model.hpp`. That boundary
separates a model request, completion controls, a typed result, runtime metrics,
and a capability descriptor. OIEC-STM-Agent adopts that separation because it
makes local inference observable and testable without allowing model output to
become authority.

The integration deliberately does not copy Neuro state, governance, mutation,
or retry behavior. OIEC retains its own authority manifest, policy engine,
Evidence Gate, EON action binding, transaction manager, CFEL collision records,
and progress certificates. The model adapter can describe or produce text; it
cannot approve evidence, change scope, write a repository, or certify its own
work.

## Extracted Interface Concepts

| Neuro concept | OIEC implementation | Reason |
| --- | --- | --- |
| `LocalModelStatus` | `ourd.providers.LocalModelStatus` | Preserves explicit success, cancellation, deadline, context, contract, output, and provider failures. |
| `LocalModelCompletionOptions` | `ourd.providers.LocalModelCompletionOptions` | Makes sampling, deadline, grammar, chat-template, and token bounds explicit. |
| `LocalModelMetrics` | `ourd.providers.LocalModelMetrics` | Records prompt, context, decode, first-token, cancellation, and timeout observations. |
| `LocalModelDescriptor` | `ourd.providers.LocalModelDescriptor` | Reports model, digest, context, acceleration, and supported contracts. |
| `LocalModelRequest` / result | `LocalModelRequest` / `LocalModelResult` | Gives the native boundary a typed input and output instead of an unstructured subprocess result. |
| stream callback | `LocalModelRequest.stream_callback` | Allows bounded observation and cancellation without granting mutation power. |

## OIEC Adaptations

Neuro permits a bounded `max_attempts` value, but OIEC fixes this value to one.
An internal model retry would otherwise bypass the OIEC `AttemptKey`, CFEL
collision record, evidence update, and no-blind-retry gate. A revised attempt
must therefore return to governed state and receive a new epistemic identity.

Neuro uses an in-process `LlamaCppAdapter`. OIEC keeps llama.cpp in
`oiec-llama-runner`, an isolated process reached through a versioned JSON Lines
protocol. JSON Lines means one JSON object is sent per text line. Isolation
allows cancellation by terminating the model process and prevents a native
failure from sharing the Python agent process.

The native runner now uses the chat template stored in the GGUF model when the
model exposes one. GGUF is the name of the model container format used by
llama.cpp to store weights and metadata; the initials should not be given an
invented expansion. Output remains constrained by GBNF, a grammar notation used
by llama.cpp to limit generated text to an allowed JSON structure.

Arbitrary JSON Schema input remains unsupported by the native runner. The
runner accepts only the reviewed OIEC grammar identifiers. This fails closed:
an unsupported contract returns `unsupported_contract` instead of silently
running an unconstrained completion.

## Qwen3.8 Connection

`ourd.providers.qwen38_direct_config()` creates the reviewed direct profile. It
binds `qwen3.8-27b-direct`, zero transport retries, and the exact Q2_K GGUF
digest:

```text
028a1d47b9c822ca76d1e9295d0078d21351a8816ec5612cb4860d7c1ef429d9
```

Callers must still provide the runner, GGUF, llama.cpp source, and matching
llama.cpp build paths. Similar filenames do not satisfy the digest check.

Backend device identity deliberately excludes current free-memory readings.
Free memory changes as processes load and unload, so it is runtime telemetry,
not a model or build identity. Stable identity retains the device identifier,
capabilities, total memory, exact runner and library hashes, llama.cpp commit,
model digest, context, sampler, grammar, and output bounds. This allows
separately executed qualification shards to prove that they used the same
provider profile without mistaking normal memory fluctuation for source drift.

```python
from ourd.providers import qwen38_direct_config, create_provider

config = qwen38_direct_config(
    runner_path="/absolute/path/to/oiec-llama-runner",
    model_path="../Neuro-llama/Qwen3.8-27B-Q2_K.gguf",
    llama_cpp_root="/absolute/path/to/llama.cpp",
    llama_cpp_build_dir="/absolute/path/to/llama.cpp/build",
)

with create_provider(config) as provider:
    print(provider.preflight())
```

The normal OIEC command-line interface uses the same provider through
`OURD_PROVIDER=llama_cpp_process` and the exact path variables documented in
the README. Read-only reasoning is available immediately; repository mutation
still requires an external authority manifest and the ordinary EON path.

## Live Evidence

The current integration smoke is recorded in
`reports/integration/neuro-qwen38-interface-20260828.json`. The run used one
model attempt and zero transport retries. It loaded the exact GGUF digest,
applied the model chat template, generated a grammar-valid message, and shut
down with no remaining model process or GPU allocation.

The observed completion used 63 prompt tokens and 29 output tokens. First token
latency was 449 milliseconds and total completion time was 2,231 milliseconds.
These numbers describe this host and this run; they are evidence, not a portable
performance guarantee.

## Conclusion

The correct integration is a contract extraction, not a runtime transplant.
Neuro contributes a useful typed model boundary; OIEC contributes deterministic
authority, bounded attempts, evidence provenance, process isolation, and
reasoning-to-action controls. Qwen3.8 is now usable through that combined
boundary, while every decision to mutate a repository remains outside the
model adapter.

## Beginner Glossary

- **API:** an agreed interface that lets software components communicate.
- **CFEL:** Collision Feedback Evidence Loop, which records disagreement between expectation and observation.
- **EON:** the OIEC action record that binds an exact candidate to authority, source state, risk, tests, and evidence requirements.
- **GBNF:** a grammar format used to constrain which text a model may generate.
- **GGUF:** a model file format used by llama.cpp for weights and metadata.
- **GPU:** a graphics processor used here to accelerate model inference.
- **JSON:** a structured text format made from objects, arrays, strings, numbers, booleans, and null values.
- **JSONL:** JSON Lines, where each line is one independent JSON object.
