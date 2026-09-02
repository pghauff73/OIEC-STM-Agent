# EGCFv1 Migration Guide

EGCFv1 is additive. It introduces `egcf` beside the existing `ourd-agent`
entry point and preserves the existing OURD/EON transaction boundary.

## Compatibility Contract

- Existing `ourd-agent` commands, authority manifests, policies, candidate
  transactions, evidence, event history, rollback, and CFEL behavior remain
  authoritative.
- EGCF uses the same `OURDAgent`, `PolicyEngine`, and `TransactionManager` for
  local mutation. It does not add a second write path.
- Existing event history is not rewritten. EGCF adds content-addressed records,
  a separate chained event stream, and rebuildable projections.
- The conversational model receives a bounded read-only
  `invoke_semantic_command` tool. It cannot call C2-C5 operations or authority
  management through that tool.

## Recommended Adoption

1. Install version `0.3.x` and keep existing automation on `ourd-agent`.
2. Use `egcf ... --dry-run --why --graph --trace` for read-only inspection.
3. Compare legacy and EGCF read-only results with differential tests.
4. Register repository-specific algorithms as proposal records.
5. Qualify exact algorithm versions with independent deterministic evidence.
6. Introduce C2 simulations for migrations and filesystem changes.
7. Enable C3 only with existing authority manifests, exact EON plans, human
   approval, verification, and rollback coverage.
8. Retire a legacy path only after parity, rollback, and explicit approval.

The repository uses a small local PEP 517 backend in `tools/build_backend.py`.
It has no network or third-party build dependency and emits a deterministic
pure-Python wheel containing the two console entry points.

## Mapping Existing Operations

| Existing operation | EGCF operation |
| --- | --- |
| Read workspace or file | qualified C0 repository/capability command |
| Model codebase analysis | C1 HRT/OURD/debug proposal record |
| Run test or benchmark | `verify.*`, `experiment.*`, or `performance.*` algorithm |
| Stage file change | `eon.draft` |
| Validate candidate | `eon.validate`, `ieps.gate` |
| Apply transaction | approved `eon.execute` C3 node |
| Roll back transaction | `eon.rollback` using exact recovery transaction ID |
| Retry after failure | revised-evidence workflow subject to CFEL and budget limits |

## Project Extensions

Repository-specific semantic commands should be added by registering immutable
command and algorithm records. Do not embed Python callbacks, shell fragments,
or floating executable references in command definitions. Privileged executor
kinds require trusted host registration, exact source digests, contextual
qualification, and an applicable capability grant.

Domain adapters should implement the `DomainPack` contract, produce
deterministic or explicitly reported evidence, and return data only. They cannot
mint approval, capability grants, or human identity.

## Qwen Integration

Local Qwen tooling is used only for bounded interpretation, critique,
counterexample proposals, and missing-test suggestions. Current OIEC model
traffic should use the `llama_cpp_process` provider and bind the exact runner,
GGUF digest, llama.cpp source, build directory, grammar set, response quality,
token metrics, and source snapshot. If a requested model is unavailable,
evaluation fails rather than silently selecting a different model.

Run:

```bash
python3 tools/evaluate_egcf_qwen.py --model qwen3.8:16b
```

An installed legacy VisualGrammar2d alternative can be evaluated explicitly
outside Agent Chat:

```bash
python3 tools/evaluate_egcf_qwen.py --model qwen3.8-27b-fast:latest
```

The report is proposal-only. Deterministic tests, source hashes, immutable
evidence, explicit approval, and rollback remain authoritative.

## Validation And Promotion

```bash
python3 tools/validate_egcf.py
```

The validator binds compilation, the complete unit suite, wheel construction,
entry-point inspection, CLI projection smoke tests, contract parity, and source
stability to one candidate snapshot. The resulting bundle still requires a
human to approve its exact candidate hash and validation payload hash.

## Rollback

Removing the `egcf` entry point and package leaves the legacy `ourd-agent`
surface intact. Applied C3 operations must be rolled back through their exact
transaction ID and original authority record; source drift or unrelated pending
transactions are not accepted as recovery authority.
