# OIEC-SR Reasoning Benchmarks

This directory contains the SR-0 benchmark harness inputs and frozen outputs.

`baseline-v1.json` is a **deterministic development-fixture baseline**. It
validates schema strictness, task ordering, scoring, evidence coverage,
counterexample metrics, provenance, reproducibility, and the A/B/C reporting
shape. It is not a model-backed performance result and cannot support a claim
that OIEC-SR outperforms another system.

The three system identifiers are:

```text
base     provider answer without governed OIEC reasoning
oiec     governed single-path OIEC answer
oiec_sr  bounded multi-path OIEC-SR answer
```

The fixture observations are deliberately recorded data. The provider-bound
runner preserves the same `BenchmarkExecutor` contract and binds the exact
model digest, provider endpoint, context and output limits, observed decoding
fields, source snapshot, hardware inventory, Ollama allocation, token usage,
response hashes, and zero-retry setting.

Generate a new deterministic fixture artifact from the current source only when
creating a new baseline version. `baseline-v1.json` is immutable historical
evidence and must not be overwritten after source drift:

```bash
python3 tools/run_reasoning_benchmark.py \
  --date 2026-08-28 \
  --output benchmarks/reasoning/baseline-v1.json
```

Verify the recorded baseline's internal signature and pinned SHA-256 checksum:

```bash
python3 tools/run_reasoning_benchmark.py \
  --date 2026-08-28 \
  --output benchmarks/reasoning/baseline-v1.json \
  --check
```

To test whether that historical artifact can still be regenerated from the
current checkout, add `--check-current-source`. A failure after source changes
is expected evidence of drift, not permission to rewrite the old baseline.

Run the source-, provider-, model-, and hardware-bound development benchmark:

```bash
python3 tools/run_reasoning_model_benchmark.py \
  --date 2026-08-28 \
  --model qwen2.5:14b \
  --base-url http://127.0.0.1:11434/v1 \
  --context-budget-tokens 2000 \
  --max-output-tokens 2048 \
  --output benchmarks/reasoning/runs/model-bound-2026-08-28-qwen2.5-14b-provider-default.json
```

For the SR-1A qualification run, use a new append-only artifact name:

```bash
python3 tools/run_reasoning_model_benchmark.py \
  --date 2026-08-28 \
  --model qwen2.5:14b \
  --base-url http://127.0.0.1:11434/v1 \
  --context-budget-tokens 2000 \
  --max-output-tokens 2048 \
  --output benchmarks/reasoning/runs/model-bound-2026-08-28-qwen2.5-14b-sr1a-current-source.json
```

The OIEC-SR arm now constructs a signed immutable `HypothesisSet` before path
generation. Fixed-point evidence and CFEL changes produce content-addressed
`HypothesisUpdateRecord` entries, while the legacy dictionary remains a
validated derived projection. RuntimeState schema v4 migration and update
replay are part of the source-bound qualification surface.

For the SR-2A grounded-topology qualification run, use another append-only
artifact name:

```bash
python3 tools/run_reasoning_model_benchmark.py \
  --date 2026-08-28 \
  --model qwen3.8-27b-benchmark-4k:latest \
  --base-url http://127.0.0.1:11434/v1 \
  --reasoning-effort low \
  --context-budget-tokens 2000 \
  --max-output-tokens 2048 \
  --output benchmarks/reasoning/runs/model-bound-2026-08-28-qwen3.8-27b-sr2a-current-source.json
```

The OIEC-SR system descriptor for this slice is
`super_reasoning_kernel_four_path_grounded_topology_v2`. Its source-bound
surface includes content-addressed inference edges, explicit inference modes,
finite evidence-node validation, positive grounding traces, typed attack
relations, disconnected-branch rejection, and removal of Qwen3.8's visible
`</think>`-terminated scratch prefix before strict JSON parsing or persistence.

The runner refuses to overwrite an existing artifact or `baseline-v1.json`.
Each new JSON run receives a sibling `.sha256` file and both paths must be new.
It requires an exact model digest and, for local Ollama comparisons, an observed
`100% GPU` allocation with sufficient runtime context. Provider errors become
explicit benchmark results; transport retries remain disabled.

The current development tasks expose standardized evidence handles to exercise
the evidence-provenance wiring. Consequently model-backed runs are labelled
`development_model_plumbing_only`, record that one run is not reproducibility
evidence, and keep `performance_claim_allowed=false`. Raw private reasoning is
not persisted; only answer text, bounded metrics, usage, and sanitized response
hashes enter the artifact.

The initial live probe showed that this local model's `medium` effort exhausted
the 2,048-token output allowance before emitting proposer JSON. The bound
development profile therefore uses `low` effort and records that choice. Batch
reasoning also halts after the first empty or malformed JSON response instead of
spending the remaining proposer or verifier calls on an invalid episode.
The first full run is preserved as failed evidence: the original model's 8K
context checkpoint cache exhausted host/GPU memory and systemd restarted
Ollama. Its inherited template also hardcodes xhigh reasoning regardless of the
requested profile. The compensated model is built from
`models/qwen3.8-27b-benchmark-4k.Modelfile`, removes that hardcoded instruction,
uses a 4,096-token context, a 2,000-token input budget, a 2,048-token output cap,
and a two-step path limit. The runner requires input plus output budgets to fit
inside the observed runtime context.

The neutral 4K Qwen3.8 profile avoided the OOM but still exhausted proposer
output before producing valid JSON. The installed `qwen2.5:14b` model completes
the proposer, verifier, falsifier, and synthesizer request sequence under the
same bounded contracts when the unsupported Responses `reasoning` field is
omitted. The development runner therefore defaults to this exact model with
`reasoning_effort=provider_default`; its digest remains mandatory in the run.

Benchmark task and output schemas are strict: unknown fields fail closed,
task IDs are unique, task files are read in lexical file order and line order,
and every task requires one observation from each system.

Qualification results must use held-out tasks with non-leaking evidence choices
and must be written to a new content-addressed report. They
must never overwrite `baseline-v1.json` or convert fixture metrics into release
evidence.

The first failed and compensated live runs are retained under `runs/`; see
`runs/SR-0B_FAILURE_ANALYSIS.md` for their exact hashes, OOM evidence,
limitations, and the no-performance-claim conclusion.
