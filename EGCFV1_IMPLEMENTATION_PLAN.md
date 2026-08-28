# EGCFv1 Implementation Plan

**System:** Evidence Governed Command Fabric v1  
**Plan date:** 2026-08-21, Australia/Brisbane  
**Plan status:** Candidate plan; not implementation authority, certification, or release approval  
**Implementation baseline:** approved source snapshot `09f55d7190309993339e336dd39d466c07e8d065a1e54a0eef89cfcde8d9ac32`  
**Target state:** semantic engineering commands compiled into evidence-governed execution graphs above the existing OURD/EON transaction boundary  
**Promotion state:** `false` until the resulting implementation has exact-snapshot validation and explicit human approval

## 1. Executive Decision

EGCFv1 will add a semantic command fabric above the repository, process,
provider, MCP, skill, subagent, and sandbox primitives already available to a
coding agent. It will not attempt to replace those primitives or give the model
broader raw access.

The primary abstraction becomes an evidence-governed engineering transaction:

```text
Intent
  -> Typed Command
  -> Capability Resolution
  -> Qualified Algorithm Selection
  -> Evidence Requirements
  -> Compiled Workflow
  -> Simulation
  -> Approval
  -> EON/Executor Actions
  -> Verification
  -> Record
  -> CFEL Learning
```

The existing EON action, policy engine, candidate transaction, evidence gate,
rollback, append-only event chain, and human authority boundary remain the
authoritative mutation path. EGCF compiles into those mechanisms; it does not
bypass them.

## 2. Baseline and Change Boundary

### 2.1 Reuse from the current implementation

EGCFv1 should reuse and strengthen these existing components:

| Existing component | EGCF role |
| --- | --- |
| `ourd.models.AuthorityManifest` | External authority root and scoped grants |
| `ourd.models.EONAction` | Executable leaf-action contract |
| `ourd.policy.PolicyEngine` | Deterministic risk floors and executor checks |
| `ourd.transactions.TransactionManager` | Staging, apply, verification, and exact rollback |
| `ourd.persistence.EventStore` | Append-only, hash-chained canonical history |
| `ourd.persistence.StateStore` | Rebuildable runtime projection |
| `ourd.cfel` | Collision identity and retry discipline |
| `ourd.providers` | Model interpretation and proposal transport |
| `.ourd-agent/evidence/` | Internal evidence artifact boundary |

### 2.2 New layer

EGCFv1 adds:

- typed command definitions and invocations;
- universal command modifiers;
- C0-C5 capability classes plus scoped capability facets;
- a versioned algorithm registry;
- contextual algorithm qualification and deterministic selection;
- an evidence/claim graph and explicit confidence assessment;
- persistent invariants and engineering decisions;
- a workflow compiler and executable DAG format;
- simulation and replay contracts;
- assurance-case generation;
- semantic namespace adapters;
- Codex, MCP, skill, subagent, scientific, and shell executor adapters.

### 2.3 Compatibility rule

`ourd-agent` must remain behaviorally compatible throughout implementation.
EGCF will initially be exposed through a new `egcf` entry point and a Python
library. Migration of the conversational agent to EGCF is a later, gated phase.

The approved baseline hash above covers the implementation before this plan was
added. This plan is a new source delta and must not be represented as part of
that prior approval.

## 3. Goals

1. Convert engineering objectives into typed, inspectable command objects.
2. Require every executable command to resolve through a registered algorithm.
3. Make capability, evidence, approval, budget, risk, and rollback explicit.
4. Compile composite objectives into deterministic workflow graphs.
5. Preserve model reasoning as proposals, never as self-granted authority.
6. Store commands, algorithms, evidence, decisions, failures, executions, and
   artifacts as queryable, provenance-bound records.
7. Support dry-run, simulation, explanation, graphing, recording, and replay as
   shared fabric features rather than per-command implementations.
8. Provide a thin but complete vertical slice before adding broad namespaces.
9. Keep deterministic correctness and human approval ahead of model quality,
   agent consensus, or execution speed.

## 4. Non-Goals

- Reimplementing Codex repository inspection, sandboxing, approvals, MCP, skills,
  cloud execution, or subagent scheduling.
- Adding an arbitrary shell escape under a semantic command name.
- Allowing a model, subagent, algorithm, workflow, or command definition to
  broaden authority.
- Treating a model-generated invariant, confidence score, qualification, or
  assurance case as self-validating.
- Implementing all proposed command namespaces in the first release.
- Treating agent debate or consensus as human approval.
- Making remote or critical mutations available before local mutation and
  rollback semantics are proven.
- Replacing repository-native build systems, test frameworks, or domain tools.
- Claiming formal proof where the evidence is testing, simulation, or argument.

## 5. Preserved System Invariants

1. Human-authored authority is the maximum boundary; every child scope is an
   intersection and can only become narrower.
2. A semantic command never directly invokes implementation code. It resolves
   to a registered algorithm, a qualified implementation, and an executor.
3. An unqualified, retired, missing, stale, or context-incompatible algorithm
   cannot execute.
4. Capability class and contextual risk are separate. Capability states what
   may be done; risk states how dangerous this instance is.
5. A composite command receives the maximum capability requirement of all its
   reachable nodes and cannot launder a high-capability action through a
   low-capability parent.
6. Model-produced intent, assumptions, invariants, algorithms, evidence labels,
   confidence assessments, and decisions remain proposals until deterministically
   checked or externally approved as required.
7. Every executable plan is content-addressed and binds the source snapshot,
   command definition versions, algorithm implementation digests, capability
   grant, evidence set, budget, rollback plan, and executor inputs.
8. Approval binds an exact plan hash. Any drift invalidates approval.
9. Simulation evidence is labelled as simulation and cannot be presented as
   evidence of real-world execution.
10. Minimal recording is mandatory. `--record` may request richer capture but
    cannot disable the canonical audit trail.
11. Replay is non-mutating by default. Mutating replay requires current
    authority, requalification, drift checks, a newly compiled plan, and any
    newly required approval.
12. Evidence conflicts, uncovered requirements, and uncertainty remain explicit.
13. Rollback claims require an executable inverse, compensation action, or an
    explicit declaration that the step is irreversible.
14. C5 operations are never automatic and cannot use `--yolo`.
15. Existing EON, policy, transaction, evidence, and rollback gates remain the
    only local workspace mutation route.

## 6. Target Architecture

```text
User / Codex / API / Workflow File
                 |
                 v
          Intent Interpreter
                 |
                 v
       Typed Command Invocation
                 |
                 v
         Universal Modifiers
                 |
                 v
         Capability Resolver
                 |
                 v
      Command + Algorithm Registry
                 |
                 v
        Qualification Engine
                 |
                 v
         Selection Engine
                 |
                 v
         Workflow Compiler
                 |
        +--------+---------+
        |                  |
        v                  v
 Evidence/Invariant     Budget/Risk/
 Decision Graph        Approval Gates
        |                  |
        +--------+---------+
                 |
                 v
          Simulation Adapter
                 |
                 v
          Exact Plan Approval
                 |
                 v
       EON / Executor Adapters
                 |
                 v
       Verification and Rollback
                 |
                 v
     Append-only Records + CFEL
```

### 6.1 Layer responsibilities

| Layer | Responsibility | Must not do |
| --- | --- | --- |
| Intent interpreter | Produce typed intent, assumptions, ambiguity, and requested outcome | Execute or approve |
| Command registry | Define semantic operations and input/output contracts | Contain arbitrary callbacks |
| Capability resolver | Calculate required capabilities and intersect authority | Grant authority |
| Algorithm registry | Describe available implementations and qualifications | Select itself without a receipt |
| Selection engine | Choose among qualified candidates with explicit scoring | Admit unqualified candidates |
| Workflow compiler | Produce a validated DAG and exact plan identity | Execute nodes while compiling |
| Evidence system | Bind claims, requirements, artifacts, conflicts, and confidence | Convert absence into success |
| Approval system | Bind external approval to an exact plan hash | Accept model self-approval |
| Executor adapter | Translate plan nodes into bounded primitive actions | Broaden scope or substitute algorithms |
| EON/transaction layer | Apply authorized mutations and verify rollback | Accept semantic intent without compilation |
| CFEL | Record collisions, diagnosis, recovery, and learning | Rewrite prior evidence |

## 7. Canonical Object Model

All canonical objects use strict versioned JSON schemas with
`additionalProperties: false`, canonical JSON serialization, SHA-256 identity,
explicit provenance, and append-only supersedence.

### 7.1 Required object types

| Object | Purpose | Key bindings |
| --- | --- | --- |
| `IntentRecord` | User objective and interpretation | raw request hash, actor, assumptions, ambiguity |
| `CommandDefinition` | Namespace/verb semantic contract | input schema, output schema, lifecycle policy |
| `CommandInvocation` | One requested command | definition digest, inputs, modifiers, scope |
| `CapabilitySpec` | Capability class and facet definition | level, resource, operations, constraints |
| `CapabilityGrant` | External scoped authority | subject, ceiling, paths, resources, expiry, budget |
| `AlgorithmDefinition` | Algorithm metadata and implementation reference | version, digest, applicability, executor |
| `QualificationRecord` | Contextual evidence that an algorithm is usable | target context, tests, benchmarks, expiry |
| `SelectionDecision` | Exact candidate set and chosen algorithm | exclusions, score components, tie-break rule |
| `ClaimRecord` | Proposition requiring evidence | scope, falsifier, confidence policy |
| `EvidenceRequirement` | Evidence expected for a claim or action | category, oracle, freshness, independence |
| `EvidenceArtifact` | Immutable evidence reference | content hash, producer, source snapshot, claim IDs |
| `ConfidenceAssessment` | Structured evidence-strength assessment | coverage, relevance, independence, freshness, conflicts |
| `InvariantRecord` | Candidate or accepted preserved property | scope, status, validator, counterexamples |
| `DecisionRecord` | Persistent engineering decision | alternatives, rationale, evidence, status |
| `WorkflowDefinition` | Reusable semantic workflow | typed nodes, edges, parameters, outputs |
| `CompiledWorkflow` | Fully resolved immutable DAG | algorithms, capabilities, gates, budgets, hashes |
| `ExecutionPlan` | Executable projection of a compiled workflow | order, EON actions, approvals, rollback graph |
| `ApprovalRecord` | Human or policy approval | exact plan hash, approver, constraints, expiry |
| `ExecutionRecord` | Node and workflow execution result | inputs, outputs, status, usage, evidence |
| `RollbackRecord` | Inverse or compensation execution | pre/post hashes, restored state, failures |
| `FailureRecord` | Structured failure/collision | expected, observed, active dimension, retry state |
| `AssuranceCase` | Claims-arguments-evidence projection | claims, evidence, gaps, conflicts, conclusion |
| `ArtifactRecord` | Produced files, reports, models, or binaries | content hash, media type, source lineage |
| `SupersedenceRecord` | Append-only replacement relationship | old ID, new ID, reason, authority |

### 7.2 Identity rules

- Definition IDs are stable names plus semantic versions, for example
  `algorithm.select@1`.
- Immutable instance IDs are content hashes prefixed by type, for example
  `plan:sha256:<digest>`.
- Human-readable aliases are projections, never canonical identity.
- All executable references use exact object IDs and implementation digests,
  not floating names such as `latest`.
- Timestamps are recorded in UTC with the caller's asserted authority time kept
  as provenance when supplied.
- Model identity records include provider, exact model tag, model digest when
  available, context configuration, tool protocol, and sampling parameters.

## 8. Typed Command Contract

Each command definition must provide the following semantic contract:

```text
CommandDefinition = (
  Namespace,
  Name,
  Version,
  IntentKinds,
  InputSchema,
  OutputSchema,
  Preconditions,
  Postconditions,
  Invariants,
  EvidenceRequirements,
  CapabilityQuery,
  AlgorithmQuery,
  RiskPolicy,
  RollbackPolicy,
  BudgetPolicy,
  ApprovalPolicy,
  LifecyclePolicy
)
```

A command definition references an algorithm query. It does not contain a
direct Python function, subprocess command, MCP call, or model prompt.

### 8.1 Invocation states

```text
DISCOVERED
  -> INTERPRETED
  -> MODELLED
  -> RESOLVED
  -> QUALIFIED
  -> COMPILED
  -> SIMULATED
  -> AWAITING_APPROVAL
  -> AUTHORIZED
  -> EXECUTING
  -> VERIFYING
  -> COMPLETED
```

Terminal alternatives are:

```text
REFUSED | FAILED | ROLLED_BACK | PARTIALLY_COMPENSATED | SUPERSEDED
```

No lifecycle stage is silently omitted. A low-risk command may compress stages
into one operation, but its record must mark each stage as completed,
`not_required`, or blocked with a policy reason.

## 9. Universal Command Modifiers

All command-line and API invocations pass through one `CommandContext`. Namespace
implementations must not parse or reinterpret universal modifiers.

| Modifier | v1 semantics |
| --- | --- |
| `--dry-run` | Resolve, qualify, and compile; do not invoke simulation or real executors |
| `--why` | Emit the intent, assumptions, selected algorithm, exclusions, and gate rationale |
| `--scope` | Intersect command scope with authority; never broaden it |
| `--evidence` | Select or require an evidence profile; cannot waive mandatory evidence |
| `--approval` | Request an approval mode; effective policy is the stricter result |
| `--risk` | Declare a risk floor or expectation; cannot lower computed risk |
| `--rollback` | Require `exact`, `compensating`, or `best-effort`; `none` requires explicit policy |
| `--budget` | Set upper bounds for tokens, time, actions, subprocesses, writes, bytes, network, or cost |
| `--timeout` | Set a wall-clock upper bound inherited by all children |
| `--trace` | Emit lifecycle and node-level trace projections |
| `--json` | Emit a stable machine-readable result projection |
| `--graph` | Emit the compiled workflow/evidence graph without changing its identity |
| `--record` | Request richer retained artifacts; minimum canonical recording remains mandatory |
| `--replay` | Load a prior invocation as input to recompilation; never implies reauthorization |
| `--strict` | Fail on ambiguity, unqualified algorithms, evidence gaps, drift, conflicts, or non-replayable nodes |
| `--simulate` | Execute through a simulation adapter and label all outputs as simulated |

### 9.1 Modifier inheritance

- Child nodes inherit scope, timeout, strictness, evidence minima, approval minima,
  risk floors, rollback minima, and remaining budget.
- A child may narrow an inherited value but cannot relax it.
- Budget is consumed globally across the workflow; a child cannot reset it.
- Conflicting modifiers fail compilation with a structured conflict record.
- `--json`, `--graph`, `--why`, and `--trace` change presentation only.
- `--simulate` cannot be combined with a request to record real execution success.

## 10. Capability and Authority Model

### 10.1 Capability classes

| Level | Meaning | Examples |
| --- | --- | --- |
| C0 | Observe only | list files, read status, inspect registered definitions |
| C1 | Analyse | parse, compare, infer, classify, profile read-only data |
| C2 | Simulate | disposable worktree, mock API, virtual migration, dry hardware plan |
| C3 | Local mutation | edit files, build artifacts, local package changes |
| C4 | External mutation | push, deploy, issue update, email, remote database mutation |
| C5 | Critical/destructive | irreversible deletion, credential rotation, production-critical action |

### 10.2 Capability facets

The ordinal class is not sufficient by itself. Every requirement and grant also
uses scoped facets such as:

```text
filesystem.read
filesystem.write
process.execute
network.read
network.write
git.local.write
git.remote.write
package.install
secret.use
human.contact
database.read
database.write
deployment.write
hardware.control
```

Each facet binds resources, paths, hosts, repositories, accounts, environments,
methods, expiry, and use limits where relevant.

### 10.3 Resolution rule

For a compiled workflow `W`:

```text
required(W) = union(command requirements,
                    selected algorithm requirements,
                    executor requirements,
                    reachable child-node requirements)

effective_authority(W) = intersection(external grants,
                                      requested scope,
                                      inherited constraints)

authorized(W) = required(W) is a subset of effective_authority(W)
                AND evidence gates pass
                AND approval policy is satisfied
```

The union computes requirements. The intersection computes authority. This
prevents composite commands from hiding or laundering capabilities.

### 10.4 Minimum gate profile

| Class | Minimum evidence | Minimum approval behavior |
| --- | --- | --- |
| C0 | provenance and source identity | automatic within read authority |
| C1 | provenance, assumptions, and confidence limits | automatic if no restricted data egress |
| C2 | simulation model, fidelity limits, and non-real label | scoped authority; explicit approval if secrets or external data are involved |
| C3 | preconditions, invariants, tests, exact diff, rollback evidence | existing EON risk/authority rules and exact plan binding |
| C4 | external target identity, idempotency, compensation, before/after evidence | explicit human approval of exact plan and target |
| C5 | assurance case, counterexamples, recovery rehearsal, irreversibility disclosure | explicit human approval; no automatic or `--yolo` path; optional policy quorum |

### 10.5 Administrative commands

`capability request` may create a proposal. `capability grant` and
`capability revoke` must require an external administrative authority record.
Neither the model nor a workflow may satisfy that authority by generating its
own approval text.

## 11. Algorithm Registry and Selection

### 11.1 Algorithm definition

Every algorithm record includes:

- stable name and semantic version;
- immutable implementation digest;
- implementation kind: Python adapter, executable adapter, MCP tool, skill,
  model procedure, workflow, or domain service;
- typed input and output schemas;
- supported command/intention kinds;
- applicability predicates and exclusions;
- capability requirements;
- risk and rollback properties;
- expected invariants and evidence requirements;
- deterministic tests, benchmarks, known failures, and platform constraints;
- qualification policy and expiry;
- owner, provenance, supersedence, and retirement status.

### 11.2 Algorithm lifecycle

```text
PROPOSED -> CANDIDATE -> QUALIFIED -> DEPRECATED -> RETIRED
```

- `algorithm register` creates `PROPOSED` or `CANDIDATE` records.
- `algorithm qualify` creates a separate contextual qualification record.
- Qualification never mutates the algorithm definition.
- `algorithm evolve` produces a new candidate version; it does not rewrite the
  existing implementation.
- `algorithm retire` prevents new selection but preserves replay history.

### 11.3 Contextual qualification

Qualification is always relative to:

- command and input schema;
- source snapshot or artifact version;
- operating system and architecture;
- language/runtime/tool versions;
- available hardware;
- capability grant;
- evidence profile;
- performance and resource budget;
- known counterexamples and failures;
- qualification expiry.

There is no globally "best" algorithm independent of context.

### 11.4 Selection engine

Selection is gate-first and score-second:

1. Resolve all candidate algorithms matching the command query.
2. Exclude candidates with incompatible schemas or applicability predicates.
3. Exclude candidates above the capability ceiling.
4. Exclude candidates lacking current qualification evidence.
5. Exclude candidates that conflict with active invariants or decisions.
6. Exclude candidates that exceed hard budget or rollback constraints.
7. Rank the remaining set using policy-controlled score components.
8. Apply a deterministic tie-break rule.
9. Emit a `SelectionDecision` containing candidates, exclusions, scores,
   selected version, and evidence.

Suggested v1 ranking is lexicographic rather than a single opaque score:

```text
qualification strength
-> invariant compatibility
-> expected correctness
-> rollback quality
-> evidence freshness
-> deterministic performance fit
-> resource cost
-> stable algorithm ID
```

Models may propose candidates or explain trade-offs, but cannot insert an
unqualified candidate into the executable set.

### 11.5 Composition

`algorithm compose` produces a candidate workflow. Every component algorithm is
qualified separately, and the composition receives its own interaction,
rollback, and integration qualification. Qualified parts do not imply a
qualified composition.

## 12. Evidence, IEPS, Invariants, Decisions, and Assurance

### 12.1 Evidence graph

Evidence is represented as a graph rather than an undifferentiated list:

```text
Claim
  <- supports / refutes / qualifies - EvidenceArtifact
  <- depends_on - Claim
  <- constrained_by - Invariant
  <- conflicts_with - EvidenceArtifact or Decision
```

Required evidence metadata includes producer, method, source snapshot, target,
oracle, environment, command/algorithm identity, timestamps, hashes, success,
limitations, and independence group.

### 12.2 Confidence assessment

`evidence confidence` must return a structured assessment, not an unexplained
model percentage. Its dimensions are:

- requirement coverage;
- relevance to the exact claim and target;
- oracle strength;
- source authority;
- reproducibility;
- independence from other evidence;
- freshness and drift exposure;
- counterexample coverage;
- conflict severity;
- known unknowns.

The result contains per-dimension values, the policy used, blocking gaps, and an
optional policy-derived ordinal conclusion. A model-written explanation may be
included but cannot alter the deterministic conclusion.

### 12.3 IEPSv1 responsibilities

The first IEPS implementation should support:

| Command | Required v1 behavior |
| --- | --- |
| `ieps qualify` | Determine whether a claim, algorithm, workflow, or candidate has the required evidence profile |
| `ieps coverage` | Build requirement-to-evidence coverage matrices |
| `ieps oracle` | Register and compare deterministic or external oracles |
| `ieps counterexamples` | Generate or collect falsifying cases as candidate evidence |
| `ieps mutation` | Measure whether evidence detects seeded policy/code mutations |
| `ieps shrink` | Minimize a reproducer while preserving the failure predicate |
| `ieps uniqueness` | Detect duplicated or non-independent evidence |
| `ieps gate` | Produce a deterministic gate proposal for an exact subject hash |

`ieps generate` may use a model to propose tests or evidence collection actions,
but generated material remains a candidate until executed and evaluated.

### 12.4 Invariant lifecycle

```text
DISCOVERED_CANDIDATE -> VALIDATED -> REGISTERED -> SUPERSEDED
                                      \-> CONFLICTED
```

- `invariant discover` only creates candidates.
- Registration requires scope, validator, evidence, falsifier, and authority.
- Invariants are scoped to artifacts, commands, algorithms, workflows, or
  repositories; they are not universal by default.
- Conflicting active invariants block strict compilation.
- Supersedence is append-only and preserves the prior record.

### 12.5 Decision lifecycle

Decision records include the question, alternatives, rationale, evidence,
constraints, owner, scope, status, and supersedence chain.

- `decision conflicts` compares active decisions against the current command,
  selected algorithms, invariants, and source state.
- A model may draft a decision but cannot activate a decision requiring human
  authority.
- A superseding decision never deletes or rewrites the previous decision.

### 12.6 Assurance cases

`assurance generate` creates a Claims-Arguments-Evidence projection for an exact
command, algorithm, workflow, candidate, or release subject. It must include:

- top-level claim;
- subclaims and argument links;
- supporting and refuting evidence;
- applicable invariants and decisions;
- capability and approval facts;
- rollback/recovery argument;
- unresolved gaps, conflicts, and uncertainty;
- a deterministic release/gate conclusion separate from narrative text.

## 13. Workflow Compiler

### 13.1 Workflow graph

A workflow is a typed directed acyclic graph containing:

- semantic command nodes;
- selected algorithm versions;
- typed inputs and outputs;
- data and control dependencies;
- evidence gates;
- approval boundaries;
- capability requirements;
- budgets and timeouts;
- retry policies;
- rollback or compensation edges;
- conditional branches with explicit predicates;
- pause/resume checkpoints;
- terminal success and failure conditions.

Loops are represented only as statically bounded retry or iteration nodes.
Unbounded model-driven loops are not valid v1 workflows.

### 13.2 Compilation passes

1. Parse and schema-validate the invocation or workflow file.
2. Resolve command definitions and exact versions.
3. Normalize universal modifiers into `CommandContext`.
4. Resolve and intersect scopes.
5. Resolve capability requirements.
6. Resolve candidate algorithms.
7. Qualify and select exact algorithms.
8. Expand composite commands.
9. Type-check node inputs and outputs.
10. Detect cycles and unreachable nodes.
11. Detect target ownership and concurrency conflicts.
12. Propagate risk, budget, timeout, evidence, and approval minima.
13. Build rollback and compensation graph.
14. Resolve evidence requirements and known gaps.
15. Produce a deterministic execution order.
16. Canonicalize and hash the compiled graph.
17. Emit the execution plan and explanation projections.

### 13.3 Static refusals

Compilation must fail before execution for:

- ambiguous high-impact intent in strict mode;
- unresolved command or algorithm versions;
- unqualified algorithms;
- capability requirements outside authority;
- cyclic or unbounded workflows;
- type mismatches;
- overlapping mutation targets without explicit serialization;
- missing rollback for a policy that requires rollback;
- budget impossibility;
- active invariant or decision conflicts;
- stale source, evidence, qualification, or approval identity;
- a command definition that attempts to reference an executor directly.

### 13.4 Composite objective example

`egcf run "fix parser regression"` should compile to a visible graph similar to:

```text
hrt.interpret
  -> hrt.ambiguity
  -> ourd.model
  -> iurm.dimensions
  -> debug.reproduce
  -> debug.minimise
  -> invariant.discover
  -> ieps.coverage
  -> algorithm.select
  -> eon.draft
  -> workflow.compile
  -> simulate.worktree
  -> ieps.qualify
  -> assurance.generate
  -> eon.authorise
  -> eon.execute
  -> verify.regression
  -> cfel.classify
  -> decision.create
```

The exact expansion is determined by a versioned workflow template, not by an
unrecorded model choice.

## 14. Executor and Adapter Model

### 14.1 Executor contract

Every executor adapter implements:

```text
describe_capabilities()
preflight(plan_node)
simulate(plan_node)
execute(authorized_plan_node)
verify(plan_node, execution_record)
rollback_or_compensate(plan_node, execution_record)
```

The adapter must report its exact version and configuration digest. It receives
an authorized node; it cannot modify the node or select a different algorithm.

### 14.2 EON bridge

The first real executor is an adapter over the existing EON and transaction
implementation:

- semantic C3 file mutations compile to prepared `TransactionRecord` objects;
- executable nodes compile to exact `EONAction` objects;
- EGCF evidence requirements map to the existing evidence gate categories;
- an EGCF approval binds the compiled plan hash and the EON action IDs;
- local writes continue through `TransactionManager.apply`;
- verification continues to check exact post-apply hashes;
- rollback continues to restore original bytes, modes, and nonexistence.

No direct EGCF filesystem writer is permitted.

### 14.3 Shell adapter

The shell adapter is only a projection over current exact command capabilities.
It must continue to use canonical argv, `shell=False`, a sanitized environment,
path scope checks, and deterministic policy classification. EGCF does not add a
general shell capability.

### 14.4 Codex, skill, MCP, and subagent adapters

- Codex primitives are executor/provider adapters, not authority roots.
- `AGENTS.md` and skills may contribute command packs, algorithms, invariants,
  or workflow templates, but cannot grant capability.
- MCP tools declare capabilities, schemas, side effects, idempotency, data
  boundaries, and rollback/compensation behavior before qualification.
- Repository or MCP content is untrusted input and cannot alter policy.
- Subagents receive narrowed child grants and budgets.
- Agent reviews, critiques, debates, and consensus produce evidence artifacts,
  not approvals.
- `agent merge` must preserve disagreements and provenance rather than collapse
  them into unsupported consensus.

### 14.5 Model adapter

The model may support intent interpretation, ambiguity detection, hypothesis
generation, candidate algorithm discovery, evidence classification proposals,
and explanation. Every model output is strict schema-validated and recorded
with exact model identity.

The currently verified local Qwen profile is `qwen3.8-27b-fast`, not an assumed
`qwen3.8:16b` tag. Model profiles must be preflighted at runtime and never
silently substituted. Model success is evaluated separately from deterministic
policy certification.

## 15. Simulation, Rollback, and Replay

### 15.1 Dry-run versus simulation

- Dry-run compiles and explains without executing any algorithm adapter.
- Simulation executes through a declared simulation adapter.
- Simulation records the model, fixtures, assumptions, fidelity limits, and
  divergence risks.
- A simulation output cannot satisfy a real-execution postcondition unless the
  evidence policy explicitly asks for simulation evidence.

### 15.2 Rollback classes

| Class | Meaning |
| --- | --- |
| `exact` | Restore exact previous local state and verify hashes/metadata |
| `compensating` | Perform an explicit inverse external action and verify outcome |
| `best_effort` | Attempt recovery with disclosed residual uncertainty |
| `irreversible` | No reliable inverse; requires elevated evidence and approval |

The compiler computes rollback coverage for all mutation nodes. A workflow is
not more reversible than its least reversible reachable mutation.

### 15.3 Replay

Replay loads the prior invocation, definitions, algorithms, evidence references,
and execution records. It then:

1. verifies historical object hashes;
2. determines which original dependencies remain available;
3. compares source and environment state;
4. requalifies algorithms where required;
5. recompiles against current authority;
6. emits a replay-difference report;
7. requires new approval for mutation.

Replay never treats a historical approval as current authority.

## 16. Persistent Command Database

### 16.1 Canonical and projected storage

Use three storage forms with distinct authority:

1. **Hash-chained event ledger:** canonical lifecycle and supersedence history.
2. **Content-addressed object/artifact store:** immutable definitions, plans,
   evidence, outputs, and reports.
3. **SQLite query projection:** rebuildable indexes and graph/query acceleration;
   never canonical authority.

### 16.2 Proposed layout

```text
.ourd-agent/
  events.jsonl                    existing/extended canonical event chain
  egcf/
    objects/
      sha256/<prefix>/<digest>.json
    artifacts/
      sha256/<prefix>/<digest>
    projection.sqlite3
    locks/
    cache/
    exports/

commands/
  v1/
    capability/*.json
    algorithm/*.json
    evidence/*.json
    workflow/*.json
    ...

algorithms/
  v1/
    core/*.json
    software/*.json
    scientific/*.json

workflows/
  v1/
    parser-regression.yaml
    migration-simulation.yaml
    assurance-release.yaml
```

Checked-in definitions are source-controlled candidates. Runtime registration
creates immutable content-addressed records tied to the source snapshot.

### 16.3 Event compatibility

Introduce an event-v2 envelope only if additional first-class lineage fields are
required. Readers must accept existing event-v1 records and new event-v2 records
without rewriting prior events. The SQLite projection must be fully rebuildable
from the canonical ledger and object store.

## 17. Namespace Rollout

Breadth follows a working vertical slice. A namespace is not considered
implemented because its command names parse; it must have schemas, qualified
algorithms, evidence policies, tests, and at least one executor or explicitly
read-only result path.

### 17.1 Tier 0: bootstrap fabric

```text
capability list
capability describe
capability check

algorithm register
algorithm search
algorithm qualify
algorithm select
algorithm explain

workflow compile
workflow execute
workflow replay

eon validate
eon simulate
eon authorise
eon execute
eon rollback
```

### 17.2 Tier 1: highest-value semantic operations

Implement the proposed highest-value commands as the first product slice:

1. `ieps qualify`
2. `algorithm select`
3. `invariant discover`
4. `decision conflicts`
5. `experiment covering`
6. `simulate migration`
7. `cfel classify`
8. `evidence confidence`
9. `workflow compile`
10. `assurance generate`

### 17.3 Tier 2: software engineering families

Add command families in dependency order:

1. `hrt`, `ourd`, and `iurm` interpretation/modeling commands.
2. `evidence`, `invariant`, and `decision` query/history/supersedence commands.
3. `debug`, `verify`, and `experiment` commands.
4. `simulate`, `performance`, `security`, and `repo` commands.
5. `workflow`, `agent`, and expanded `cfel` commands.
6. Engineering aliases such as `prove`, `justify`, `challenge`,
   `counterexample`, `shrink`, `differentiate`, `qualify`, `attest`,
   `explain-choice`, `impact-map`, and `rollback-plan`.

An alias must resolve to a versioned semantic command or workflow. It must not
create a separate bypass implementation.

### 17.4 Tier 3: scientific adapters

Scientific namespaces are independent command/algorithm packs:

```text
physics
geometry
grammar
vision
robotics
cad
```

Each pack defines domain objects, units, coordinate systems, tolerances,
oracles, invariants, algorithms, benchmark datasets, and simulation fidelity.
No domain pack may weaken core capability, evidence, approval, or provenance
requirements.

## 18. Implementation Phases

### Phase 0 - Baseline, specification, and threat model

**Deliverables**

- Freeze the exact source snapshot before implementation.
- Convert Sections 5-16 into normative schemas and architecture decision records.
- Inventory every existing direct tool/executor entry point.
- Characterize current CLI, EON, policy, transaction, persistence, provider, and
  CFEL behavior with tests.
- Create a threat model covering semantic bypass, capability laundering,
  registry poisoning, approval replay, stale evidence, prompt injection,
  rollback fraud, simulation confusion, and secret leakage.

**Gate**

- No implementation begins until existing 78 deterministic tests pass and each
  current mutation path is mapped to an EON/transaction entry point.

### Phase 1 - Core schemas, identity, and object store

**Deliverables**

- Add strict schemas for all Section 7 core objects.
- Add canonical JSON and typed content-addressed ID helpers.
- Add immutable object and artifact stores under `.ourd-agent/egcf/`.
- Extend the event system without rewriting existing events.
- Add a rebuildable SQLite query projection and deterministic rebuild command.
- Add append-only supersedence records.

**Gate**

- Property tests prove identical objects hash identically, changed executable
  fields change plan identity, and projection deletion/corruption rebuilds from
  canonical records.

### Phase 2 - Command registry and universal modifiers

**Deliverables**

- Add `CommandDefinition`, `CommandInvocation`, and `CommandContext` runtime types.
- Implement data-driven namespace/verb registration.
- Implement one universal modifier parser for CLI and API use.
- Implement modifier inheritance and conflict detection.
- Add `egcf --help`, `egcf capability list`, and command schema introspection.
- Reject command definitions containing direct executor callbacks.

**Gate**

- Every universal modifier has focused tests and every child constraint is
  proven monotonic under composition.

### Phase 3 - Capability resolver and authority bridge

**Deliverables**

- Add C0-C5 classes and scoped capability facets.
- Add capability requirement calculation across composite graphs.
- Map existing read/command capabilities into the new model.
- Add `capability list`, `describe`, `graph`, `check`, `request`, and `audit`.
- Keep `grant` and `revoke` behind external administrative authority.
- Add capability explanation receipts and denial reasons.

**Gate**

- Adversarial tests prove no child, algorithm, executor, composite command, or
  model proposal can broaden the external grant.

### Phase 4 - Algorithm registry, qualification, and selection

**Deliverables**

- Add algorithm definitions, implementation digests, lifecycle, and registry.
- Add qualification records with context and expiry.
- Implement `algorithm register`, `search`, `compare`, `qualify`, `select`,
  `benchmark`, `retire`, and `explain` for core algorithms.
- Implement gate-first deterministic selection and complete selection receipts.
- Register existing workspace read, exact command, EON mutation, transaction,
  test, and rollback behaviors as built-in algorithms.

**Gate**

- No semantic command executes an unregistered or unqualified implementation.
- Selection is deterministic for the same canonical context and registry state.

### Phase 5 - Workflow compiler and lifecycle engine

**Deliverables**

- Add typed workflow definitions and compiled DAGs.
- Implement all compilation passes in Section 13.2.
- Add bounded retry nodes, conditional nodes, gates, checkpoints, and rollback
  edges.
- Implement lifecycle state transitions and illegal-transition refusal.
- Add graph, JSON, why, and trace projections.
- Implement `workflow compile`, `monitor`, `pause`, `resume`, and read-only replay.

**Gate**

- Golden graph tests, cycle/type/conflict tests, and property tests prove stable
  compilation and complete capability/risk/budget propagation.

### Phase 6 - Evidence graph, IEPS, invariants, decisions, and assurance

**Deliverables**

- Add claim, requirement, evidence, conflict, confidence, invariant, decision,
  and assurance schemas.
- Implement evidence independence and duplicate-use detection.
- Implement `ieps qualify`, coverage, oracle, counterexamples, uniqueness,
  mutation, shrink, and gate.
- Implement `invariant discover`, register, validate, conflicts, and supersede.
- Implement `decision create`, query, history, conflicts, supersede, and explain.
- Implement structured `evidence confidence`.
- Implement `assurance generate` with deterministic conclusion and explicit gaps.

**Gate**

- Seeded evidence, invariant, and decision faults are detected by mutation and
  conflict tests. A narrative model answer cannot change a failing gate.

### Phase 7 - Simulation, EON execution bridge, rollback, and replay

**Deliverables**

- Implement the executor adapter contract.
- Implement the EON bridge as the only C3 workspace mutation path.
- Implement disposable-worktree and migration simulation adapters.
- Bind plan approval to EON action IDs, transactions, candidate hashes, source
  snapshot, evidence, algorithms, and rollback graph.
- Implement exact local rollback and compensation contracts.
- Implement mutating replay as recompilation with fresh authority and approval.

**Gate**

- Failure-injection tests prove no semantic path bypasses staging, approval,
  exact apply, verification, or rollback.

### Phase 8 - First vertical product slice

**Deliverables**

- Implement the ten Tier 1 commands.
- Add the versioned `fix-parser-regression` workflow template.
- Run a complete disposable-repository scenario from intent through CFEL.
- Produce graph, trace, assurance case, exact plan approval bundle, execution
  record, regression evidence, rollback rehearsal, and replay difference report.
- Add a model-assisted run using the exact verified local Qwen profile, reported
  separately from deterministic results.

**Gate**

- The vertical slice must pass without arbitrary shell access or model authority.
- A deliberately broken candidate must fail IEPS qualification or verification.
- A deliberately stale approval must fail before execution.

### Phase 9 - Extended engineering namespaces

**Deliverables**

- Add the Tier 2 namespaces in dependency order.
- Prefer declarative command definitions and reusable algorithms over bespoke
  handlers.
- Add repository, debugging, verification, experiment, simulation, performance,
  and security algorithm packs.
- Add workflow branching/merge semantics with explicit conflict preservation.

**Gate**

- Each command family ships with schemas, qualified algorithms, adversarial
  tests, evidence profiles, and a documented executor boundary.

### Phase 10 - Codex, MCP, skills, and multi-agent integration

**Deliverables**

- Add adapters that inventory current Codex/MCP/skill/subagent capabilities.
- Compile child-agent roles into narrowed grants, budgets, inputs, and outputs.
- Implement agent critic/review/debate/consensus as evidence-producing workflows.
- Add prompt-injection and untrusted-tool-output defenses.
- Add external mutation adapters only after C4 compensation and approval tests.

**Gate**

- Agent consensus cannot authorize execution.
- MCP or skill metadata cannot broaden capability.
- External mutation tests use disposable or test accounts and prove idempotency or
  compensation before any production eligibility.

### Phase 11 - Scientific command packs

**Deliverables**

- Define a domain-pack SDK for schemas, units, algorithms, oracles, datasets,
  invariants, simulations, and evidence policies.
- Implement one narrow reference pack first, preferably `grammar`, because this
  repository already models structured commands and can validate parse,
  transform, compare, and verify behavior deterministically.
- Add other packs only after the reference pack passes portability tests.

**Gate**

- Domain-specific claims remain tied to explicit datasets, tolerances, models,
  coordinate systems, and evidence. No generic model narrative qualifies a
  scientific algorithm.

### Phase 12 - Hardening, packaging, and promotion

**Deliverables**

- Add `egcf` console packaging and stable Python APIs.
- Add migration and compatibility documentation.
- Add complete schema and command reference generation.
- Run unit, integration, property, fuzz, mutation, differential, regression,
  performance, security, rollback, replay, and live-provider validation.
- Build an exact candidate/evidence/assurance bundle.
- Require explicit human approval of the exact final snapshot and validation
  hashes before certification.

**Gate**

- No unresolved critical/high policy gap.
- No command-to-executor bypass.
- No unqualified algorithm execution.
- No capability broadening.
- No unsupported full-confidence or assurance conclusion.
- No promotion without exact-hash human approval.

## 19. Proposed Source Layout

```text
ourd/
  egcf/
    __init__.py
    cli.py
    models.py
    ids.py
    schemas.py
    context.py
    registry.py
    capabilities.py
    algorithms.py
    qualification.py
    selection.py
    compiler.py
    workflow.py
    lifecycle.py
    evidence.py
    ieps.py
    invariants.py
    decisions.py
    assurance.py
    budgets.py
    replay.py
    store.py
    projections.py
    adapters/
      base.py
      eon.py
      shell.py
      simulation.py
      model.py
      codex.py
      mcp.py
      skill.py
      agent.py
    namespaces/
      core.py
      engineering.py
      scientific.py

commands/v1/
algorithms/v1/
workflows/v1/
schemas/egcf-v1/
tests/egcf/
tools/validate_egcf.py
```

Namespace command definitions should remain data-driven. The `namespaces/`
modules provide shared compilation behavior, not one bespoke implementation per
command name.

## 20. Test and Evaluation Matrix

### 20.1 Deterministic tests

- Strict schema validation and unknown-field rejection.
- Canonical identity and content-hash sensitivity.
- Command registry version resolution.
- Universal modifier parsing, inheritance, and conflicts.
- Capability union/intersection and anti-laundering properties.
- Algorithm qualification expiry, context matching, and retirement.
- Selection candidate exclusion, ranking, and deterministic tie-breaking.
- Workflow type checking, cycle detection, target conflict detection, and stable
  graph hashing.
- Budget accounting and bounded retry behavior.
- Evidence coverage, independence, conflict, and confidence calculation.
- Invariant candidate/registered separation and supersedence.
- Decision conflict and supersedence behavior.
- Assurance gap preservation.
- Approval exact-plan binding and stale-approval refusal.
- EON bridge, transaction staging, atomic apply, verification, and exact rollback.
- Simulation/real evidence separation.
- Replay reauthorization and drift reporting.
- Projection rebuild from canonical records.
- Secret redaction and untrusted-input handling.

### 20.2 Property and adversarial tests

- Child scope is always a subset of parent and authority scope.
- Effective capability never decreases below any reachable node requirement.
- Computed risk never drops below command, algorithm, or executor floors.
- Any executable field change changes the plan hash.
- Evidence cannot satisfy two independence requirements through duplication.
- A retired or unqualified algorithm is never executable.
- A model output cannot create an approval or grant.
- A semantic alias cannot bypass the command registry.
- A workflow cannot exceed its global budget through branching or retries.
- Rollback verification cannot pass on mismatched restored hashes.

### 20.3 Verification families

Use the proposed verification namespace against EGCF itself:

```text
verify unit
verify integration
verify property
verify fuzz
verify mutation
verify differential
verify metamorphic
verify regression
verify performance
verify security
```

### 20.4 Live model evaluation

Live Qwen evaluation is limited to model-suitable roles:

- intent interpretation;
- ambiguity and assumption extraction;
- candidate invariant and hypothesis discovery;
- candidate workflow explanation;
- evidence classification proposals;
- CFEL diagnosis;
- candidate assurance narrative.

Every run records exact model identity and context. Live model success cannot
override deterministic policy, schema, qualification, evidence, transaction, or
rollback failure.

## 21. Threat Model and Required Controls

| Threat | Required control |
| --- | --- |
| Semantic command bypass | No direct executor references; adapter invocation only from authorized plans |
| Capability laundering | Reachable-node requirement union and authority intersection |
| Registry poisoning | Source provenance, strict schemas, content hashes, qualification, administrative authority |
| Algorithm substitution | Exact version and implementation digest in plan and approval |
| Approval replay | Source/plan/evidence/expiry binding and use count |
| Stale evidence | Freshness rules, snapshot binding, drift invalidation |
| Evidence double counting | Independence groups and artifact-use constraints |
| Model self-approval | Approval/grant object constructors unavailable to model tools |
| Prompt injection | Treat repository/MCP/model text as data; deterministic policy remains external |
| Simulation confusion | Mandatory simulated labels and evidence category separation |
| Rollback fraud | Executable inverse/compensation plus post-rollback verification |
| Workflow amplification | Global budgets, bounded retries, static graph limits |
| Secret leakage | Existing redaction plus adapter-specific egress and artifact policies |
| Subagent authority escalation | Narrowed child grants and non-transferable approvals |
| External side-effect duplication | Idempotency keys, target identity, compensation, use limits |
| Projection tampering | Canonical ledger/object validation and rebuild |

## 22. Migration Strategy

1. Keep current APIs and CLI unchanged during Phases 0-7.
2. Introduce EGCF as a library and separate `egcf` CLI.
3. Wrap existing operations as registered built-in algorithms without changing
   their enforcement paths.
4. Add one `invoke_semantic_command` tool to `ourd-agent` only after the vertical
   slice is deterministic and mutation-safe.
5. Keep legacy direct model tools available during a deprecation period, but
   route all mutations through the same EON boundary.
6. Compare legacy and EGCF behavior with differential tests.
7. Disable a legacy path only after its EGCF replacement has parity evidence,
   rollback coverage, and explicit approval.
8. Never rewrite existing event history; add supersedence or migration events.

## 23. Release States

```text
DRAFT_SPEC
  -> IMPLEMENTATION_CANDIDATE
  -> DETERMINISTICALLY_VALIDATED
  -> LIVE_MODEL_EVALUATED
  -> HUMAN_APPROVED
  -> CERTIFIED
```

- Deterministic validation does not imply live-model quality.
- Live-model evaluation does not imply safety certification.
- Human approval must name the exact candidate and validation hashes.
- Certification records unresolved limitations and excluded scope.
- Any post-approval source change creates a new candidate.

## 24. Definition of Done

EGCFv1 is complete only when all of the following are true:

- Every semantic command is a strict typed object with canonical identity.
- Every command supports the universal modifier contract through shared code.
- Every executable command resolves through a registered, context-qualified,
  exact-version algorithm.
- Every workflow has a deterministic graph, capability calculation, budget,
  evidence profile, approval policy, and rollback graph.
- Capability is never broadened by composition, algorithms, adapters, models,
  agents, skills, MCP, or replay.
- The first ten high-value commands work in a complete end-to-end scenario.
- Local mutation remains exclusively controlled by EON and transactions.
- C4 and C5 behavior is fail-closed until its adapters and approval controls are
  explicitly qualified.
- Evidence confidence is structured, reproducible, and conflict-aware.
- Invariants and decisions are persistent, scoped, and append-only supersedable.
- Assurance cases preserve gaps and cannot turn narrative into approval.
- Simulation, execution, rollback, and replay are clearly distinguished and
  independently evidenced.
- Canonical history survives projection loss and detects tampering.
- Deterministic, adversarial, rollback, replay, performance, security, and live
  model reports are generated for one exact source snapshot.
- A human explicitly approves that exact snapshot and validation bundle.

Until those criteria are met, the correct status is:

`egcfv1_candidate_implementation_pending_validation_and_human_approval`

## 25. Immediate Implementation Slice

The first coding iteration should be deliberately narrow:

1. Add `CommandDefinition`, `CommandInvocation`, `CommandContext`,
   `CapabilitySpec`, `AlgorithmDefinition`, `QualificationRecord`,
   `SelectionDecision`, and `CompiledWorkflow` schemas.
2. Add content-addressed object storage and a rebuildable query projection.
3. Implement the shared universal modifier parser.
4. Implement `capability list`, `capability describe`, and `capability check`.
5. Register the existing read-only workspace inspection operation as a built-in
   algorithm.
6. Implement `algorithm search`, `algorithm qualify`, `algorithm select`, and
   `algorithm explain` for that operation.
7. Implement `workflow compile` for a one-node read-only workflow.
8. Produce `--dry-run`, `--why`, `--json`, `--graph`, `--trace`, and `--record`
   outputs from the same immutable compiled object.
9. Add anti-bypass, anti-escalation, identity, projection-rebuild, and stable
   compilation tests.
10. Do not add C3 mutation until this read-only slice passes its phase gate.

This slice proves the central abstraction shift—intent to typed command to
qualified algorithm to evidence-bearing plan—without expanding raw execution
power.
