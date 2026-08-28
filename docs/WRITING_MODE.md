# OIEC-STM-Agent Writing Mode

OIEC-STM-Agent can stage text and code through `prepare_write_file`,
`prepare_replace_text`, and atomic candidate transactions. Writing mode makes
that capability practical from the CLI without weakening the existing
OURD/IURM/EON/CFEL governance path.

## Design

`--write` is an explicit human grant for a single exact workspace snapshot.
It does not turn the model into its own authority. The user must provide at
least one writable path or pattern with `--write-path`.

The generated session authority:

- is bound to the current workspace snapshot;
- allows mutation only inside the supplied path patterns;
- always forbids `.ourd-agent/**`;
- keeps L1 candidate application interactive;
- disables L2 unless the user explicitly supplies `--write-allow-l2`;
- never grants `--yolo`;
- preserves EON candidate hashes, evidence gates, transactions, rollback,
  CFEL collision records, and OIEC no-blind-retry constraints.

The temporary authority manifest exists only for the CLI process. Normal
invocations without `--write` or `--authority` remain read-only.

Because authority is bound to an exact snapshot, a successful mutation makes
that session authority stale. One session should therefore prepare one atomic
transaction, which may contain many file changes. Start a fresh `--write`
session for another transaction so it binds to the new workspace snapshot.

## Formal university writing profiles

Writing mode now supports research-backed formal profiles:

- `general`
- `scientific-essay`
- `argumentative-essay`

The research basis and design rationale are documented in
`docs/FORMAL_WRITING_RESEARCH.md`.

The profiles do not replace an assignment brief, marking rubric, discipline
conventions, citation rules, or academic-integrity requirements. Those local
requirements override generic profile defaults.

### Scientific essay

```bash
oiec-stm-agent . \
  --write \
  --write-path essay.md \
  --writing-profile scientific-essay \
  --task 'Write a 2000-word scientific essay evaluating the evidence for the proposed mechanism.'
```

The scientific profile treats an essay as a thesis-driven scientific argument,
not automatically as an IMRaD laboratory report. It requires the agent to:

- analyse the task, scope and scientific question first;
- organise the body around claims/mechanisms rather than individual sources;
- connect claims to evidence, method/provenance and explicit reasoning;
- compare methodological and evidential quality;
- distinguish correlation, causation, mechanism, necessity and sufficiency;
- examine alternative explanations and relevant limitations;
- calibrate certainty to the strength of evidence;
- consider reproducibility, replicability and robustness where relevant;
- avoid fabricated citations, data, quotations, statistics and results.

### Argumentative essay with logic topology

```bash
oiec-stm-agent . \
  --write \
  --write-path essay.md \
  --writing-profile argumentative-essay \
  --task 'Write an argumentative essay evaluating whether the proposed policy should be adopted.'
```

The argumentative profile asks the model to reason through an explicit topology
before translating it into natural prose:

```text
Evidence / Premises / Warrants
            |
            v
     Supporting Claims -------- Counterclaim
            |                       |
            v                       v
          Thesis <------------ Rebuttal
            |
      Qualifiers / Limits
            |
            v
       Implications
```

The machine representation is `ArgumentTopology` in `ourd/formal_writing.py`.
Supported node roles include thesis, claim, premise, evidence, warrant,
counterclaim, rebuttal, qualifier, limitation and implication. Supported edge
relations include `supports`, `warrants`, `attacks`, `rebuts`, `qualifies`,
`limits`, `entails` and `depends_on`.

The positive support graph must be acyclic, so a claim cannot ultimately justify
itself. Evidence nodes require source references, and material counterclaims
must receive an explicit rebuttal/response. The prose should remain readable;
the topology is an internal reasoning scaffold unless formal notation is useful
for the assignment.

## Write a general document

```bash
oiec-stm-agent . \
  --write \
  --write-path 'docs/**' \
  --task 'Write docs/architecture.md explaining OIEC-STM for a software engineering audience.'
```

The model is instructed to inspect relevant repository sources, separate
purpose/audience/evidence/tone/structure as writing dimensions, prepare the
file as a candidate transaction, bind an EON action, gather evidence, pass the
gate, and present the exact candidate for approval before application.

## Edit a README

```bash
oiec-stm-agent . \
  --write \
  --write-path README.md \
  --task 'Rewrite the installation section for clarity without changing commands.'
```

## Write code with verification

Writing mode can also grant deterministic command capabilities explicitly:

```bash
oiec-stm-agent . \
  --write \
  --write-path 'ourd/**' \
  --write-path 'tests/**' \
  --write-command-capability python.unittest \
  --write-test 'python3 -m unittest discover -s tests -v' \
  --task 'Implement the requested feature and add focused tests.'
```

Supported write-mode command capability names are currently:

- `python.unittest`
- `python.py_compile`
- `ctest.run`
- `cmake.build`
- `compiler.syntax_check`

The exact command still has to pass `PolicyEngine.classify_command`; naming a
capability on the CLI does not authorize arbitrary shell execution.

## L2 changes

Broad, structural, dependency, configuration, build-system, or otherwise
high-impact candidates may receive deterministic L2 risk. They are blocked in
standard writing mode. A user may allow **interactive** L2 review explicitly:

```bash
oiec-stm-agent . \
  --write \
  --write-path 'ourd/**' \
  --write-allow-l2 \
  --task 'Perform the bounded structural refactor described in the task.'
```

This still does not make L2 automatic. The exact candidate remains subject to
OIEC/EON evidence and human approval.

## Why this is not a raw write switch

A conventional `--write` flag often means "let the model modify anything." In
OIEC-STM it means something narrower:

```text
human scope grant
  -> exact-snapshot authority
  -> OURD problem model
  -> Boundary Determination
  -> Dimension Limiting / IURM
  -> formal writing / argument topology
  -> staged candidate
  -> EON exact action
  -> evidence gate
  -> human approval when required
  -> atomic apply
  -> verification / rollback / CFEL
```

The model gains the ability to write documents and code, but not the ability to
silently expand its own authority.
