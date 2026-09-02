# OIEC-Bench Formal-Writing Track

This track evaluates the governed formal-writing pipeline rather than prose
fluency alone. Each task provides a writing question, profile, bounded source
corpus, and expected deterministic audit status.

The runner checks:

- canonical meaning, claim, evidence, graph, plan, draft, and audit artifacts;
- evidence coverage and claim-support metrics;
- semantic drift and graph-integrity gates;
- counterargument and qualification coverage;
- citation traceability;
- `NoNewMaterialClaims` sentence-to-claim mappings; and
- fail-closed novelty status.

Run:

```bash
python3 tools/run_formal_writing_benchmark.py
```

The track is deterministic and dependency-light. It is implementation evidence,
not a truth, originality, academic-acceptance, or release certificate.
