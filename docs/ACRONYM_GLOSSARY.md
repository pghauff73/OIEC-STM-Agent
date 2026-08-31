# OIEC-STM-Agent Acronym and Abbreviation Glossary

This glossary explains the acronyms, initialisms, abbreviations, composite names, version labels, and coded levels used throughout **OIEC-STM-Agent**.

It is written for readers who may be meeting the architecture for the first time. Each entry answers three questions:

1. **What does the term stand for, when an expansion is actually declared?**
2. **What does it mean inside this repository?**
3. **What should it not be confused with?**

> **Canonical-name rule:** An expansion is not invented merely because a group of letters looks expandable. The repository treats **OIEC** as the canonical project name without a declared expansion. **STM** expands to **State Transition Machine**, the bounded-transition layer.

---

## 1. How to read this glossary

The **status** column uses the following labels.

| Status | Meaning |
| --- | --- |
| **Project-defined** | The repository explicitly declares the expansion and architectural meaning. |
| **Project name** | The repository uses the token as a canonical name but does not declare a letter-by-letter expansion. |
| **Composite name** | The token combines already-defined project names. |
| **Standard term** | The term has its ordinary software, mathematical, scientific, or graphics meaning. |
| **Coded label** | The token identifies a level, version, milestone, test track, or state rather than expanding into words. |

The repository source of truth for the novice documentation vocabulary is [`tools/docs_learning_catalog.py`](../tools/docs_learning_catalog.py). The implementation and design documents linked throughout this glossary provide the detailed contracts.

---

## 2. The architecture at a glance

The major terms fit together conceptually as follows:

```text
                              OIEC-STM-Agent
                                     │
                    ┌────────────────┴────────────────┐
                    │                                 │
             bounded operation                 reusable knowledge
                    │                                 │
                    ▼                                 ▼
                 STM layer                            SAA
                    │                                 │
         ┌──────────┼──────────┐            mathematical algorithms
         ▼          ▼          ▼            reasoning algorithms
        HRT       OURD       IURM            semantic mappings
         │          │          │             failures and evidence
         │          │       BD + DL                    │
         │          │          │                       │
         └──────────┴──────► IEPS ◄────────────────────┘
                              │
                              ▼
                             EON
                              │
                              ▼
                             EGCF
                              │
                              ▼
                       governed action
                              │
                              ▼
                             CFEL
                              │
                              └──── evidence and learning feedback ────► SAA

OIEC-SR explores bounded candidate reasoning paths across this architecture.
```

This is a teaching map, not a claim that every runtime call executes in one fixed linear order. Individual workflows may revisit evidence, boundaries, experiments, or failure records before an action becomes eligible.

---

# 3. Core OIEC architecture terms

## Quick reference

| Term | Expansion or canonical reading | Plain-language meaning | Status |
| --- | --- | --- | --- |
| **OIEC** | Canonical project name; no expanded form is currently declared | The overall governed architecture separating interpretation, evidence, authority, action, learning, and reusable knowledge | Project name |
| **STM** | State Transition Machine | The finite, bounded state-transition part of OIEC-STM-Agent | Project name |
| **OIEC-STM** | OIEC joined to its State Transition Machine | The governed state machine and transition kernel at the centre of the agent | Composite name |
| **SR** | Super Reasoning | A bounded additive process for generating and comparing candidate reasoning paths | Project-defined |
| **OIEC-SR** | OIEC Super Reasoning | The OIEC-governed multi-response reasoning procedure | Composite name |
| **HRT** | Human-Readable Task Interpretation | Makes the requested task, assumptions, scope, and ambiguities inspectable | Project-defined |
| **OURD** | Orthogonal Unique Relational Decomposition | Decomposes a problem into orthogonal, uniquely identified relational components and the relations between them | Project-defined |
| **IURM** | Invariant-Uncertainty-Response Modeling | Designs controlled variations that reduce uncertainty while preserving invariants | Project-defined |
| **IEPS** | Invariant and Evidence Production System | Produces tests, counterexamples, evidence, and gate material | Project-defined |
| **BD** | Boundary Determination | Finds the domain inside which a claim, model, action, or experiment is supported | Project-defined |
| **DL** | Dimension Limiting | Restricts active variables or reasoning dimensions to a bounded justified set | Project-defined |
| **EON** | Exact Governed Action Boundary | Binds a proposed action to exact state, scope, authority, evidence, risk, and rollback | Project-defined |
| **EGCF** | Evidence-Governed Command Fabric | Compiles semantic intentions into typed, inspectable governed plans | Project-defined |
| **CFEL** | Collision, Failure, Evidence, and Learning Feedback | Records expectation collisions and failures so unchanged failed attempts are not repeated blindly | Project-defined |
| **SAA** | Searchable Algebra of Algorithms | Represents, searches, qualifies, relates, adapts, and reuses mathematical and reasoning algorithms | Project-defined |
| **OIEC-Bench** | OIEC benchmark suite | Measures grounding, meaning, progress certification, work quality, and knowledge integrity | Composite name |

---

## OIEC

**Canonical reading:** `OIEC`

**Repository meaning:** The name of the complete governed architecture. It brings together task interpretation, relational problem modeling, uncertainty reduction, evidence production, bounded action, failure feedback, and algorithmic knowledge accumulation.

**Everyday analogy:** A careful engineering workshop in which diagnosing, planning, authorizing, acting, testing, and learning are separate stations. A persuasive idea does not skip the inspection station and become an approved repair.

**Do not confuse it with:** A repository-declared phrase assembled from the four letters. Current source intentionally says that no expanded form is declared. Documentation should write **OIEC** as the project name rather than reverse-engineering a phrase.

**Related:** HRT, OURD, IURM, IEPS, EON, EGCF, CFEL, SAA, STM, SR.

---

## STM

**Expansion:** **State Transition Machine**

**Repository meaning:** The state-transition machinery that limits admissible states, transition choices, retries, dimensions, and progress claims. It is implemented around bounded state and kernel concepts such as `OIECSTMState` and `OIECSTMKernel`.

**Everyday analogy:** A railway interlocking system. A train may move only when the route, points, signals, and occupancy conditions form an admissible transition.

**Do not confuse it with:** Ordinary conversational **short-term memory**. In this repository, STM explicitly means **State Transition Machine**.

**Related:** OIEC-STM, Boundary Determination, Dimension Limiting, progress certificates, transition kernels.

See [`OIEC_STMV1_2_IMPLEMENTATION_PLAN.md`](../OIEC_STMV1_2_IMPLEMENTATION_PLAN.md).

---

## OIEC-STM

**Reading:** OIEC joined to the **State Transition Machine (STM)** bounded-transition layer.

**Repository meaning:** The formal state-and-transition architecture that turns the OIEC governance concepts into executable bounded transitions.

A simplified transition is:

```text
current verified state
        +
proposed action
        +
boundaries, budgets, evidence, and risk
        ↓
deterministic transition gate
        ↓
accepted next state, explicit refusal, or unresolved state
```

**Do not confuse it with:** The language model itself. The model may propose a transition, but the system state determines what has actually been verified or accepted.

---

## SR and OIEC-SR

**Expansion:** **Super Reasoning**.

**Repository meaning:** A bounded additive reasoning layer that generates candidate responses, hypotheses, evidence requests, and reasoning paths, then compares them without enlarging external authority.

**Everyday analogy:** Several engineers independently propose explanations while a separate chairperson checks scope, evidence, and decision rules. Agreement creates a candidate consensus, not permission to operate machinery.

**Do not confuse it with:** SAA. **SR explores candidate reasoning now; SAA stores and retrieves qualified reusable algorithms over time.**

See [`OIEC_SR_V1_IMPLEMENTATION_PLAN.md`](../OIEC_SR_V1_IMPLEMENTATION_PLAN.md).

---

## HRT

**Expansion:** **Human-Readable Task Interpretation**.

**Repository meaning:** An inspectable interpretation of a human request, including objectives, assumptions, ambiguity, scope, and unresolved questions.

**Everyday example:** Before opening a machine, a technician repeats the reported fault, identifies which machine is meant, states assumptions, and asks what “fixed” must look like.

**Produces:** A reviewable task interpretation for OURD and later governance stages.

**Does not prove:** That the interpretation is correct. It makes the interpretation visible enough to review and correct.

---

## OURD

**Expansion:** **Orthogonal Unique Relational Decomposition**.

**Repository meaning:** A canonical decomposition of the problem territory into orthogonal, uniquely identified relational components and their relationships, dependencies, boundaries, exclusions, and unresolved relations.

**Everyday example:** A lamp fault is mapped into the bulb, socket, switch, cable, breaker, supply, user action, and observed symptoms before the bulb is blamed.

**Produces:** A bounded problem map.

**Does not grant:** Permission to implement the first relation the model notices.

---

## IURM

**Expansion:** **Invariant-Uncertainty-Response Modeling**.

**Repository meaning:** A controlled experiment model that identifies a baseline, uncertainty, active dimension, invariant conditions, variation, observation, and response.

**Everyday example:** A baker changes oven temperature while keeping flour, water, yeast, kneading, proofing, and loaf size stable.

A useful teaching form is:

```text
baseline + one bounded variation + preserved invariants → discriminating evidence
```

**Does not mean:** Change several coupled variables and call the result an experiment.

---

## IEPS

**Expansion:** **Invariant and Evidence Production System**.

**Repository meaning:** The evidence-production service used to construct tests, counterexamples, coverage records, falsifiers, and evidence-gate decisions.

**Everyday example:** A test bench checks whether a repaired controller remains stable at normal load, low load, high load, and a boundary condition.

**Does not mean:** The model states a conclusion confidently. A model statement is a proposal until grounded evidence supports it.

---

## BD

**Expansion:** **Boundary Determination**.

**Repository meaning:** The process of finding the supported boundary of a model, claim, experiment, action, or semantic interpretation.

**Everyday example:** A tyre model tested from 20 km/h to 100 km/h is not silently claimed to describe behaviour at 300 km/h.

**Core question:**

> Inside which explicitly identified domain is this conclusion supported?

**Related:** IURM, IEPS, STM, admissible state-space, validity region.

---

## DL

**Expansion:** **Dimension Limiting**.

**Repository meaning:** The process of limiting the number and range of active dimensions so the reasoning or experiment remains finite, discriminating, and governable.

**Everyday example:** Diagnose a heating fault by testing temperature sensing before simultaneously changing the sensor, controller, heater, airflow, insulation, and power supply.

**Core question:**

> Which dimensions are justified and necessary for this transition, and which must remain fixed or excluded?

**Related:** IURM, BD, finite state-space, dimension budget.

---

## EON

**Expansion:** **Exact Governed Action Boundary**.

**Repository meaning:** The content-addressed boundary around a proposed action. It binds the proposal to exact targets, source state, authority, risk, evidence requirements, tests, and rollback information.

**Everyday example:** A repair order names the exact vehicle, component, permitted operation, required checks, approving authority, and reversal procedure.

**Does not create:** Authority. EON binds an action to authority that already exists.

**Related:** EGCF, action identity, source snapshot, risk level, rollback, evidence gate.

---

## EGCF

**Expansion:** **Evidence-Governed Command Fabric**.

**Repository meaning:** The typed command system that turns semantic command intent into inspectable plans, workflow nodes, evidence requirements, capability checks, and bounded execution decisions.

**Everyday example:** A dispatcher transforms “fix the parser” into a job card stating the exact repository, target, operation, scope, risk, proof, approval, and rollback.

**Does not mean:** Arbitrary shell execution with a friendlier name.

See [`EGCFV1_IMPLEMENTATION_PLAN.md`](../EGCFV1_IMPLEMENTATION_PLAN.md) and [`docs/EGCFV1_COMMAND_REFERENCE.md`](EGCFV1_COMMAND_REFERENCE.md).

---

## CFEL

**Expansion:** **Collision, Failure, Evidence, and Learning Feedback**.

**Repository meaning:** A feedback record that compares expectation with observation, identifies a collision or failure, preserves the evidence, and constrains what may happen next.

**Everyday example:** Replacing a lamp bulb did not restore light. The failed bulb hypothesis is recorded so the system investigates the switch or circuit instead of replacing the bulb repeatedly.

**Core rule:**

```text
same attempt + same state + no new evidence → blocked blind retry
```

**Does not mean:** A failure is proof that the opposite hypothesis is true. It changes the evidence state and narrows later reasoning.

---

## SAA

**Expansion:** **Searchable Algebra of Algorithms**.

**Repository meaning:** The mathematical and reasoning knowledge subsystem. It normalizes candidate algorithms, resolves meanings, detects misrepresentation and coupling, searches for representative forms, compares them with known structures, qualifies them with evidence, stores unique canonical algorithms, records failures, and supports controlled improvement.

**Everyday analogy:** A library that does not shelve every photocopy as a new book. It identifies the underlying work, records editions and evidence, separates books with different meanings, marks failed procedures, and retrieves the best-qualified fit before commissioning a new one.

**Important distinction:**

```text
source code found in a repository
        ↓
algorithm candidate
        ↓
representation + semantics + evidence + uniqueness gates
        ↓
canonical algorithm, or staged/unresolved/rejected candidate
```

**Does not mean:** Every equation or function encountered is correct, unique, or canonically admitted.

See the SAA documents beginning with [`docs/SAA_1_CANONICAL_IR.md`](SAA_1_CANONICAL_IR.md) and [`docs/SAA_6_1_TO_6_4_CANONICAL_STORE.md`](SAA_6_1_TO_6_4_CANONICAL_STORE.md).

---

## OIEC-Bench

**Reading:** The OIEC benchmark and qualification suite.

**Repository meaning:** A multi-track benchmark intended to test factual grounding, meaning-path integrity, semantic representation, meaning grounding, work grounding, progress certification, and useful agent work.

**Does not mean:** One average score that can conceal a catastrophic weakness. Important tracks can have independent minimum thresholds.

**Related:** SAA-12.2, canonical promotion governance, longitudinal knowledge integrity.

---

# 4. SAA milestone labels

SAA milestone labels identify implementation stages. They are **coded versions**, not separate acronyms.

| Label | Repository meaning |
| --- | --- |
| **SAA-1** | Canonical intermediate representation for algorithms |
| **SAA-2** | Exact normalization |
| **SAA-3** | Linear dynamics representation |
| **SAA-4 / 4.1** | Coupling analysis and representation gates |
| **SAA-5 / 5.x** | Representative-basis search and semantic resolution |
| **SAA-6 / 6.x** | Canonical representative algorithms, persistence, indexes, uniqueness, and relation graph |
| **SAA-7 / 7.x** | Nonlinear representations, regional evidence, geometry, observability, controllability, and equivalence support |
| **SAA-8 / 8.x** | Reasoning algorithms, topology equivalence, qualification, persistence, retrieval, and composition |
| **SAA-9 / 9.x** | Semantic ontology, physical dimensions, revision, and cross-domain alignment |
| **SAA-10 / 10.x** | Unified retrieval, cross-domain transfer, fit explanation, and retrieve-first policy |
| **SAA-11 / 11.x** | Controlled adaptation, lineage, A/B experiments, and multi-step evolution |
| **SAA-12 / 12.x** | Closed improvement, failure algebra, benchmark gates, integrity measurement, and improvement scheduling |

A suffix such as **SAA-7.8** denotes a numbered milestone, not a decimal measurement.

---

# 5. Governance levels and coded labels

## C0–C5 capability classes

These are **capability codes**, not acronyms.

| Code | Plain-language meaning |
| --- | --- |
| **C0** | Observe or inspect only |
| **C1** | Internal analysis and proposal generation |
| **C2** | Simulation or bounded rehearsal |
| **C3** | Authorized local mutation under governance |
| **C4** | External or broader-impact capability, normally unavailable or fail-closed unless explicitly implemented and governed |
| **C5** | Critical, destructive, or exceptional capability, normally unavailable or fail-closed |

A higher number is not automatically “better.” It denotes greater operational authority and risk.

## L0–L2 risk classes

These are **risk-level codes**, not acronyms.

| Code | Repository meaning |
| --- | --- |
| **L0** | Read-only operation |
| **L1** | Bounded workspace mutation or verification command |
| **L2** | Structural, broad, dependency, configuration, build-system, or difficult-to-reverse change |

The deterministic risk floor can raise the effective risk above a model proposal. A file write cannot be relabelled as L0 merely because a model says it is harmless.

## T00–T13 tutorial identifiers

These codes identify ordered novice tutorial lessons. For example, **T04** is the OURD lesson and **T09** is the SAA lesson. They are navigation IDs rather than acronyms.

## v1, v1.1, v1.2, and similar suffixes

`v` means **version**. A name such as `OIEC-STMv1.2` identifies a versioned architectural contract. Version numbers do not by themselves prove maturity, compatibility, or qualification.

---

# 6. Agent, software, and repository engineering terms

| Term | Expansion | Meaning in this repository |
| --- | --- | --- |
| **A/B** | A-versus-B comparison | A controlled comparison between a baseline and candidate under the same experiment contract; not an acronym |
| **AI** | Artificial Intelligence | General category that includes the model-driven parts of the agent; AI output remains distinct from system-verified state |
| **API** | Application Programming Interface | A defined source-level interface through which software components communicate |
| **ABI** | Application Binary Interface | A binary-level compatibility contract between compiled components; not the same as an API |
| **AST** | Abstract Syntax Tree | A parsed structural representation of source code; used by static repository ingestion for Python symbols |
| **CI** | Continuous Integration | Automated build and test workflows, including GitHub Actions qualification matrices |
| **CLI** | Command-Line Interface | Text commands such as `oiec-stm-agent`, `ourd-agent`, and `egcf` |
| **CPU** | Central Processing Unit | General-purpose processor used by the runtime and tests |
| **DAG** | Directed Acyclic Graph | A directed dependency graph that contains no cycle; used for workflows and prerequisite ordering |
| **GUI** | Graphical User Interface | The visual engineering workbench using windows, panels, controls, and diagrams |
| **HTTP** | Hypertext Transfer Protocol | Network protocol used by compatible provider APIs |
| **HTTPS** | Hypertext Transfer Protocol Secure | HTTP carried through authenticated encrypted transport |
| **IR** | Intermediate Representation | A normalized machine-readable form between source material and later analysis or execution |
| **JSON** | JavaScript Object Notation | Structured text format used for records, manifests, schemas, and CLI output |
| **JSONL** | JSON Lines | One JSON object per line; used for append-oriented event records such as `events.jsonl` |
| **LLM** | Large Language Model | A generative model that proposes text, code, hypotheses, or tool calls; it is not the authority or evidence store |
| **OS** | Operating System | The host system on which the agent runs; the repository does not claim an OS-level sandbox |
| **PEP** | Python Enhancement Proposal | A formal Python design document or standardization proposal |
| **PEP 517** | Python Enhancement Proposal 517 | The standard build-system interface used by Python packaging frontends and backends |
| **PR** | Pull Request | A GitHub review unit proposing a branch be merged into another branch |
| **PTY** | Pseudoterminal | A terminal-like process interface; unrestricted PTY behaviour is intentionally not treated as an ordinary safe capability |
| **REST** | Representational State Transfer | A common HTTP API design style |
| **SHA-256** | Secure Hash Algorithm, 256-bit form | The content digest used for identities, source snapshots, evidence, and tamper-evident records |
| **SQL** | Structured Query Language | Language used to query relational data stores |
| **SQLite** | SQLite embedded relational database | Rebuildable projection/index storage; immutable content-addressed objects remain authoritative where specified |
| **TOML** | Tom's Obvious, Minimal Language | Configuration format used by `pyproject.toml` |
| **UI** | User Interface | Any human-facing interaction surface, including CLI and GUI |
| **URI** | Uniform Resource Identifier | A general identifier for a resource |
| **URL** | Uniform Resource Locator | A resource identifier that also describes where or how it can be accessed |
| **UTF-8** | Unicode Transformation Format, 8-bit | Text encoding used for repository source and documents |
| **UUID** | Universally Unique Identifier | A generated identifier; changing a UUID does not make equivalent evidence or an equivalent attempt genuinely new |
| **YAML** | YAML Ain't Markup Language | Human-readable structured configuration format, including GitHub Actions workflows |

---

# 7. Mathematical, control, and evidence terms

| Term | Expansion | Meaning in this repository |
| --- | --- | --- |
| **AD** | Automatic Differentiation | Programmatic derivative evaluation used as one possible nonlinear evidence route; provenance and exactness still matter |
| **bp / bps** | basis point / basis points | One basis point is 1/100 of one percent; bounded integer scores often use 0–10,000 bps |
| **LTI** | Linear Time-Invariant | A linear dynamic model whose defining coefficients do not change with time |
| **MIMO** | Multiple-Input Multiple-Output | A system with more than one input and more than one output; coupling and semantic representation require explicit analysis |
| **ODE** | Ordinary Differential Equation | An equation relating a function to derivatives with respect to one independent variable, commonly time |
| **SI** | International System of Units | The unit system used by physical semantic contracts and dimensional analysis |
| **SISO** | Single-Input Single-Output | A system with one input and one output |

## Mathematical symbols that are not acronyms

| Symbol | Meaning |
| --- | --- |
| **Δ** | Delta; a change, difference, or measured fit gap |
| **∂** | Partial derivative |
| **∇** | Gradient or differential operator, depending on context |
| **J** | Commonly a Jacobian matrix or objective; consult the local definition |
| **H** | Commonly a Hessian matrix or hash function; consult the local definition |
| **A, B, C** | Often state-space matrices, experiment variants, or generic symbols; they do not have one repository-wide meaning |

A symbol receives meaning from its semantic contract, units, domain, and relation to measurable quantities. The same letter in two equations does not establish semantic identity.

---

# 8. Graphics, image, and 3D terms

| Term | Expansion or reading | Meaning in this repository |
| --- | --- | --- |
| **EGL** | EGL graphics-context interface | Creates graphics contexts and surfaces, including headless contexts used by renderer tests |
| **OpenGL** | Open Graphics Library | Cross-platform graphics API used by the visual and 3D renderer work |
| **GLB** | Binary glTF container | Binary packaging of a glTF scene and associated data |
| **glTF / GLTF** | GL Transmission Format | 3D scene and asset interchange format |
| **GPU** | Graphics Processing Unit | Processor optimized for highly parallel graphics and numerical workloads |
| **JPEG** | Joint Photographic Experts Group image format | Lossy raster-image format |
| **OBJ** | Wavefront OBJ object format | Text-oriented 3D geometry format supporting vertices, faces, material references, and texture coordinates |
| **PBR** | Physically Based Rendering | Material and lighting approach designed to behave consistently under physical-style illumination models |
| **PLY** | Polygon mesh format, also called Polygon File Format or Stanford Triangle Format | 3D geometry format that can store vertices and properties in ASCII or binary form |
| **PNG** | Portable Network Graphics | Lossless raster-image format with optional transparency |
| **RGB** | Red, Green, Blue | Three-channel colour representation |
| **RGBA** | Red, Green, Blue, Alpha | RGB colour plus transparency/coverage channel |
| **STL** | Stereolithography mesh format | Triangle-surface format commonly used for 3D printing and interchange |
| **SVG** | Scalable Vector Graphics | XML-based vector-image format used for educational diagrams and figures |
| **Tk / Tkinter** | Tcl/Tk graphical toolkit and its Python interface | The toolkit used by the current GUI workbench |
| **UV** | Texture-coordinate axes `u` and `v` | Coordinates mapping a 2D texture onto a 3D surface; UV is not normally expanded into words |

---

# 9. File, web, and documentation terms

| Term | Expansion | Meaning |
| --- | --- | --- |
| **CSS** | Cascading Style Sheets | Controls presentation of generated HTML documentation |
| **HTML** | Hypertext Markup Language | Page structure for the generated documentation website |
| **JS** | JavaScript | Browser scripting used for interactive documentation and interface behaviour |
| **Markdown / MD** | Markdown text format / `.md` extension | Human-readable source format from which documentation pages are generated |
| **SVG** | Scalable Vector Graphics | Resolution-independent diagrams that can also carry accessible text and interactions |
| **WCAG** | Web Content Accessibility Guidelines | Accessibility guidance relevant to readable, keyboard-accessible, and screen-reader-compatible documentation |

---

# 10. Common confusions

## OIEC is not given a made-up expansion

Correct:

> OIEC is the canonical name of the governed architecture.

Incorrect:

> OIEC definitely stands for a phrase that is not declared by repository source.

## STM is not ordinary short-term memory

Within this repository, STM means **State Transition Machine**, the bounded-transition layer. A reader should not import an unrelated cognitive-memory meaning.

## SR and SAA solve different problems

- **SR** generates and compares bounded candidate reasoning paths.
- **SAA** accumulates, qualifies, relates, retrieves, adapts, and improves reusable algorithms and reasoning structures.

## EON and EGCF are not synonyms

- **EON** defines the exact governed boundary of an action.
- **EGCF** is the command fabric that compiles semantic intent into governed plans and evidence requirements.

## IURM and IEPS are not synonyms

- **IURM** designs the controlled uncertainty-reducing variation.
- **IEPS** produces the tests, evidence, counterexamples, and gate material needed to evaluate it.

## API and ABI are different contracts

- An **API** describes how source-level software components interact.
- An **ABI** describes how compiled binary components interact.

## A source-code function is not automatically a canonical algorithm

Static repository feeding can establish that exact source bytes and a symbol exist. It cannot, by inspection alone, establish that the function has the correct meaning, is unique, is correct, or is globally valid.

## Several agreeing agents do not create authority

Consensus can improve a candidate reasoning record. It cannot expand file scope, command capability, risk permission, approval, or external authority.

---

# 11. First-use writing rule

When introducing a project-defined acronym in prose, use the full form first unless the page is specifically an acronym reference.

Recommended:

> The **Evidence-Governed Command Fabric (EGCF)** compiles semantic commands into inspectable plans. EGCF then applies capability, evidence, and authority checks.

For OIEC, use the canonical-name rule. Expand STM normally at first use:

> **OIEC-STM-Agent** uses a **State Transition Machine (STM)** bounded-transition layer to constrain admissible state changes.

Do not force a fabricated expansion into the sentence.

---

# 12. Adding a new acronym to the repository

A new acronym should not enter the documentation as an unexplained cluster of capital letters. Add it through the following checklist:

1. **Ownership:** State whether it is project-defined, a canonical project name, a standard term, or a coded label.
2. **Expansion:** Record the exact expansion when one exists. Explicitly state when no expansion is declared.
3. **Plain meaning:** Explain the responsibility in one sentence without using other undefined acronyms.
4. **Everyday example:** Give a non-specialist example.
5. **Formal meaning:** State inputs, outputs, bounds, authority, and evidence role where applicable.
6. **Non-meaning:** Say what the term is commonly confused with.
7. **First use:** Expand it at first use in authored documentation.
8. **Source:** Link the implementation or design document that owns the definition.
9. **Catalog:** Add or update the canonical `AcronymRecord` in [`tools/docs_learning_catalog.py`](../tools/docs_learning_catalog.py) when the term belongs to the novice documentation vocabulary.
10. **Validation:** Run the documentation and repository validation suites so undefined authored acronym-like tokens are caught.

A useful admission rule is:

```text
new token
   + declared ownership
   + exact expansion or explicit no-expansion status
   + plain meaning
   + source
   + misconception boundary
   = documented vocabulary
```

---

# 13. Alphabetical index

| Token | Entry |
| --- | --- |
| A/B | Baseline-versus-candidate experiment |
| ABI | Application Binary Interface |
| AD | Automatic Differentiation |
| AI | Artificial Intelligence |
| API | Application Programming Interface |
| AST | Abstract Syntax Tree |
| BD | Boundary Determination |
| bp / bps | basis point / basis points |
| C0–C5 | capability classes |
| CFEL | Collision, Failure, Evidence, and Learning Feedback |
| CI | Continuous Integration |
| CLI | Command-Line Interface |
| CPU | Central Processing Unit |
| CSS | Cascading Style Sheets |
| DAG | Directed Acyclic Graph |
| DL | Dimension Limiting |
| EGL | graphics-context interface |
| EGCF | Evidence-Governed Command Fabric |
| EON | Exact Governed Action Boundary |
| GLB | binary glTF container |
| glTF / GLTF | GL Transmission Format |
| GPU | Graphics Processing Unit |
| GUI | Graphical User Interface |
| HRT | Human-Readable Task Interpretation |
| HTML | Hypertext Markup Language |
| HTTP | Hypertext Transfer Protocol |
| HTTPS | Hypertext Transfer Protocol Secure |
| IEPS | Invariant and Evidence Production System |
| IR | Intermediate Representation |
| IURM | Invariant-Uncertainty-Response Modeling |
| JPEG | Joint Photographic Experts Group image format |
| JS | JavaScript |
| JSON | JavaScript Object Notation |
| JSONL | JSON Lines |
| L0–L2 | risk classes |
| LLM | Large Language Model |
| LTI | Linear Time-Invariant |
| MIMO | Multiple-Input Multiple-Output |
| OBJ | Wavefront OBJ object format |
| ODE | Ordinary Differential Equation |
| OIEC | canonical project name; no expanded form declared |
| OIEC-Bench | OIEC benchmark suite |
| OIEC-SR | OIEC Super Reasoning |
| OIEC-STM | OIEC plus the STM bounded-transition layer |
| OpenGL | Open Graphics Library |
| OS | Operating System |
| OURD | Orthogonal Unique Relational Decomposition |
| PBR | Physically Based Rendering |
| PEP | Python Enhancement Proposal |
| PEP 517 | Python Enhancement Proposal 517 |
| PLY | polygon mesh format |
| PNG | Portable Network Graphics |
| PR | Pull Request |
| PTY | Pseudoterminal |
| RGB / RGBA | Red, Green, Blue / plus Alpha |
| REST | Representational State Transfer |
| SAA | Searchable Algebra of Algorithms |
| SHA-256 | Secure Hash Algorithm, 256-bit form |
| SI | International System of Units |
| SISO | Single-Input Single-Output |
| SQL | Structured Query Language |
| SR | Super Reasoning |
| STL | Stereolithography mesh format |
| STM | State Transition Machine |
| SVG | Scalable Vector Graphics |
| T00–T13 | tutorial identifiers |
| Tk / Tkinter | Tcl/Tk toolkit and Python interface |
| TOML | Tom's Obvious, Minimal Language |
| UI | User Interface |
| URI | Uniform Resource Identifier |
| URL | Uniform Resource Locator |
| UTF-8 | Unicode Transformation Format, 8-bit |
| UUID | Universally Unique Identifier |
| UV | texture-coordinate axes |
| v1, v1.2, … | version labels |
| WCAG | Web Content Accessibility Guidelines |
| YAML | YAML Ain't Markup Language |

---

# 14. Sources of truth

The glossary is a reader-facing synthesis. When definitions conflict, prefer the owning implementation and canonical registry:

- [`tools/docs_learning_catalog.py`](../tools/docs_learning_catalog.py), canonical novice acronym records;
- [`tools/docs_concept_catalog.py`](../tools/docs_concept_catalog.py), concept definitions and relationships;
- [`README.md`](../README.md), public architecture and runtime overview;
- [`OIEC_STMV1_2_IMPLEMENTATION_PLAN.md`](../OIEC_STMV1_2_IMPLEMENTATION_PLAN.md), STM bounded-transition design;
- [`OIEC_SR_V1_IMPLEMENTATION_PLAN.md`](../OIEC_SR_V1_IMPLEMENTATION_PLAN.md), Super Reasoning design;
- [`EGCFV1_IMPLEMENTATION_PLAN.md`](../EGCFV1_IMPLEMENTATION_PLAN.md), Evidence-Governed Command Fabric design;
- the [`docs/`](.) SAA milestone documents, algorithm-store and improvement architecture;
- `ourd/` and `ourd_gui/`, executable source contracts.

When a concept evolves, update the owning source, the canonical acronym record, and this glossary together. That keeps vocabulary from becoming a fossil bed of once-correct meanings.
