# OIEC-STM-Agent Novice-First Documentation Redesign Implementation Plan

**Plan date:** August 30, 2026
**Baseline commit:** `0f3ce90a2c8360667f67ada20d113c1f7d540514`
**Canonical generator:** `tools/build_docs_site.py`
**Primary generated entry point:** `docs/index.html`
**Plan status:** Proposed implementation plan; no redesign completion claim

## 1. Governing Decision

The documentation redesign is governed by one primary rule:

> A new reader must understand the problem OIEC solves before learning a single
> acronym.

The current expert documentation, concept inventory, relational-object model,
source hashes, generated references, and deterministic SVG artifacts remain
authoritative technical assets. The redesign adds a novice-first educational
layer in front of them and moves the dense relational interface into a clearly
named **Architecture Explorer**.

The homepage stops acting as a complete object inventory. It becomes a guided
entry point that answers five questions in this order:

1. What is OIEC-STM-Agent?
2. What problem does it solve?
3. What happens when a task moves through it?
4. What safe action can the reader try in the first 15 minutes?
5. Where should the reader go next for learning or technical reference?

No runtime authority, provider, persistence, benchmark, or agent behavior is
changed by this documentation program. Browser interactions remain read-only,
deterministic, local, and incapable of mutating a workspace.

## 2. Verified Baseline

The baseline generated site contains:

- 42 authored Markdown sources under `docs/`;
- 606 heading objects;
- 333 source-derived concept objects;
- 989 relational objects and 1,399 recorded relations;
- 1,369 generated SVG artifacts;
- 377 generated HTML pages;
- 23,475 generated essay paragraphs; and
- 72 current glossary keys.

The current homepage baseline is intentionally dense:

- `docs/index.html` is 1,760,381 bytes;
- it contains approximately 10,306 HTML elements;
- it renders 989 relational rows;
- it contains 1,002 buttons and 1,017 links; and
- it embeds the complete relational object inventory directly in the page.

The current `docs/site-manifest.json` is 1,384,468 bytes. That manifest remains
the source-bound audit record, but it must not be required to understand the
first screen.

## 3. Target Outcomes

The redesign succeeds only when all of the following are true:

1. The first viewport explains OIEC in plain English without presenting the
   architecture acronym pipeline as prerequisite knowledge.
2. The homepage provides a visible **First 15 Minutes** path and task-based
   entry points.
3. Learn and Technical views coexist on the same conceptual pages.
4. Every core acronym and status code has one canonical definition owner.
5. Every concept satisfies a machine-checkable teaching contract.
6. All 333 current concepts have novice explanations, examples, diagrams,
   source links, relationships, prerequisites, and evidence-status labels.
7. Fourteen ordered tutorials exist under `docs/tutorial/` and have deterministic
   expected outputs or fixtures.
8. CLI examples are derived from or validated against the actual parsers and
   package entry points.
9. Browser tools cannot invoke providers, execute commands, or mutate files.
10. The current expert relational explorer remains available and complete under
    the name **Architecture Explorer**.
11. All generated SVGs use a shared visual grammar, accessibility metadata, and
    an interaction contract appropriate to their role.
12. The homepage raw HTML payload is at most 350 KiB and contains at most 1,500
    elements before optional explorer content is opened.
13. Repeated generation from the same source is byte-identical.
14. Every source hash, local link, anchor, diagram, tutorial, concept, command,
    status, prerequisite, and manifest relation passes deterministic tests.

## 4. Scope and Compatibility Boundaries

### 4.1 Preserved expert assets

The following remain supported and source-bound:

- all existing Markdown source documents;
- all existing generated technical pages;
- the 25-paragraph claim/evidence/challenge essay contract for expert documents
  and concept essays;
- the complete relational object and relation inventory;
- deterministic standalone relational symbols and the relational sprite;
- the concept atlas;
- source SHA-256 records;
- the governed-loop formal architecture; and
- current package and file-link compatibility.

### 4.2 New content kinds

Tutorials, task guides, command recipes, status explanations, and browser
sandboxes use separate educational contracts. They are not forced into the
25-paragraph expert essay shape.

The generator must classify each source explicitly as one of:

```text
tutorial
task-guide
case-study
expert-document
architecture-decision
generated-reference
concept
tool
explorer
```

Existing expert pages retain their current contract until deliberately migrated.
The implementation must never weaken their current source-hash, logic-topology,
link, SVG, or relational coverage tests merely to make tutorials easier to add.

### 4.3 Non-goals

This program does not:

- claim that OIEC is generally intelligent or generally superior;
- dynamically generate educational prose with a model;
- send documentation activity to a server;
- add authentication or user accounts;
- allow a browser tutorial to execute a real CLI command;
- infer implementation or qualification status from marketing language;
- replace current expert records with simplified prose; or
- treat several agreeing model outputs as approval or evidence.

## 5. Target Information Architecture

The generated documentation navigation becomes:

```text
docs/index.html
│
├── What is OIEC?
├── First 15 Minutes
├── Learn by Task
├── How a Task Moves Through OIEC
├── Learn the Core
├── Tutorial Course
├── Case Studies
├── Interactive Learning Tools
├── Architecture Explorer
└── Reference
    ├── CLI
    ├── EGCF
    ├── GUI
    ├── API and types
    ├── Schemas
    ├── Status decoder
    ├── Glossary
    ├── Source map
    └── Generated reference
```

The core learning path is:

```text
What is this?
    ↓
First 15 Minutes
    ↓
Your First Safe Task
    ↓
Understand → Experiment → Act → Verify → Learn → Reuse → Improve
    ↓
Tutorials and task guides
    ↓
Architecture Explorer and technical reference
```

## 6. Canonical Ownership Map

Each semantic fact must have one canonical owner.

| Responsibility | Canonical owner | Derived outputs |
| --- | --- | --- |
| Site orchestration and deterministic writes | `tools/build_docs_site.py` | HTML, manifest, generated assets |
| Concept inventory and source discovery | `tools/docs_concept_catalog.py` | concept pages, atlas records |
| Learning paths, tutorials, task routes and prerequisites | `tools/docs_learning_catalog.py` | homepage cards, tutorial index, course map |
| CLI commands, aliases, examples and provider recipes | `tools/docs_cli_catalog.py` | CLI walkthroughs, command builder schema |
| Status names and plain-language decoding | `tools/docs_status_catalog.py` | status decoder and status cards |
| SVG shapes, edges, icons and interaction metadata | `tools/docs_visual_grammar.py` | all generated educational SVGs |
| Tutorial prose | `docs/tutorial/*.md` | `docs/tutorial/*.html` |
| Task-oriented guides | `docs/tasks/*.md` | `docs/tasks/*.html` |
| Cross-domain examples | `docs/case-studies/*.md` | `docs/case-studies/*.html` |
| Deterministic tutorial observations | `docs/tutorial/fixtures/*.json` | browser sandbox output |
| Shared behavior | `docs/assets/site.js` and focused companion scripts | mode, depth, search, tools, explorer |
| Shared styling | `docs/assets/styles.css` and focused companion stylesheets | Learn, Technical, print and explorer views |
| Acceptance contracts | `tests/test_docs_site.py` plus focused documentation tests | binary pass/fail evidence |

The new catalog modules may be introduced gradually, but the final state must
avoid duplicate hard-coded definitions across Python, JavaScript, HTML, and
Markdown.

## 7. Data Contracts

### 7.1 Learning path record

Each learning path contains:

```text
path_id
title
plain_language_goal
audience
ordered_item_ids
estimated_minutes
prerequisite_ids
completion_evidence
```

### 7.2 Tutorial lesson record

Each tutorial lesson contains:

```text
lesson_id
ordinal
title
source_path
reader_outcome
new_vocabulary
prerequisite_ids
command_ids
fixture_ids
next_lesson_id
```

Every tutorial Markdown source must contain these headings in order:

```text
What you will learn
Everyday analogy
New vocabulary
Diagram
Command or interaction
Expected output
What just happened?
Try changing this
Common mistake
Next lesson
```

### 7.3 Concept Teaching Contract

Every concept page must expose:

```text
full_name
short_meaning
why_it_exists
everyday_analogy
oiec_example
inputs
outputs
misconception
diagram
formal_novice
formal_intermediate
formal_expert
related_concepts
prerequisites
cli_examples
failure_example
source_links
documentation_status
status_evidence
```

Authored core concepts receive explicit records. Source-discovered public types
receive deterministic teaching facets with source provenance. A generated
fallback must be labeled `source-derived`; it must not masquerade as a
human-reviewed explanation.

### 7.4 Acronym contract

Every acronym record contains:

```text
token
expansion
short_meaning
everyday_analogy
formal_meaning
related_concepts
first_lesson_id
source_paths
```

The initial mandatory authored set includes:

```text
OIEC STM SR OURD IURM EON CFEL EGCF HRT IEPS BD DL SAA
CLI GUI DAG PEP 517 EGL API ABI
```

The acronym linter scans authored Markdown, catalog prose, CLI help, status
descriptions, and generated navigation labels. Machine status codes and ordinary
uppercase words use separate typed registries rather than a broad ignore list.

### 7.5 Documentation evidence badge

Every core concept, tutorial claim, feature guide, and case study receives one
documentation status:

```text
Implemented
Tested
Experimental
Theoretical
Planned
```

Each badge binds named evidence such as source paths, tests, reports, fixtures,
or an explicit plan reference. The generator must fail closed when a badge lacks
evidence. A badge describes documentation maturity and implementation evidence;
it is not release certification.

### 7.6 Status decoder record

Each machine status contains:

```text
status
plain_language_meaning
category
trigger
what_happens_next
user_action
source_paths
related_concepts
```

The catalog must include statuses discovered from runtime constants, schemas,
commands, and authored documentation. Discovery produces a report; publication
requires a complete canonical explanation.

### 7.7 Visual grammar record

The visual grammar defines:

| Token | Meaning |
| --- | --- |
| Circle | concept or state |
| Rounded rectangle | process |
| Hexagon | gate or check |
| Diamond | uncertainty or decision |
| Document shape | evidence |
| Shield | authority or boundary |
| Red edge | contradiction |
| Dashed edge | hypothesis or unverified relation |
| Solid edge | verified relation |
| Double border | canonical knowledge |

Every generated SVG declares its visual role, title, description, nodes, edges,
keyboard targets, fallback link, and reduced-motion behavior.

## 8. Homepage Contract

The homepage is generated in this exact conceptual order.

### 8.1 Plain-language hero

The first heading is `What is OIEC-STM-Agent?`. The first explanation states
that it is an AI agent designed to work carefully and describes understanding,
retrieval, bounded action, verification, failure recording, and qualified
learning without requiring an acronym expansion.

The first SVG is the six-stage plain-language loop:

```text
You ask for work
    ↓
Understand it
    ↓
Find what is already known
    ↓
Try safely
    ↓
Check the result
    ↓
Remember what was learned
```

Only after this explanation may the page introduce OURD, IURM, EON, CFEL, SAA,
or the formal pipeline.

### 8.2 Before OIEC / With OIEC

A deterministic two-column animation contrasts an ordinary speculative agent
loop with the governed OIEC loop. Reduced-motion users receive a static ordered
comparison with identical information.

### 8.3 First 15 Minutes

The homepage exposes:

1. install and verify;
2. identify the five command names and their aliases;
3. run one read-only repository task;
4. decode the returned evidence boundary; and
5. choose the next tutorial.

### 8.4 Learn by task

The initial task routes are:

```text
Understand a repository
Debug a bug
Safely modify files
Write a report
Run an experiment
Compare algorithms
Use OIEC with Ollama
Understand a failure
Build a command
```

Each task route lists the smallest required concept sequence rather than linking
to an undifferentiated category.

### 8.5 Learn the core

The homepage teaches the plain-language stages first:

```text
Understand
Experiment
Act safely
Verify
Learn
Remember and reuse
Improve
```

Technical names appear as secondary labels.

### 8.6 Expert entry

The existing object bus becomes a concise card:

```text
Architecture Explorer
Browse every documented concept, source document, relationship and SVG.
```

The complete 989-object explorer is not embedded in the default homepage DOM.

## 9. Learn, Technical, and Explanation Depth

Every concept and major guide supports:

```text
[ Learn ] [ Technical ]
```

The default is Learn. The selection is stored only in local browser storage and
is never transmitted.

Within Learn mode, a three-position explanation control selects:

```text
Novice
Intermediate
Expert
```

The blocks are pre-authored or deterministically generated from catalog data.
No model is called at runtime.

Mode rules:

1. Both views use the same URL and canonical concept identity.
2. Learn mode shows analogy, task story, inputs, outputs, misconception, failure,
   and the simplest diagram first.
3. Technical mode shows exact types, equations, invariants, source paths, schema
   fields, CLI details, and relationship identifiers.
4. Print mode includes both views with clear labels.
5. Content remains present without JavaScript; JavaScript changes disclosure,
   not availability.

## 10. Tutorial Curriculum

The canonical tutorial sequence is:

| ID | Source | Reader outcome |
| --- | --- | --- |
| T00 | `docs/tutorial/00_WELCOME.md` | Understand what OIEC is for |
| T01 | `docs/tutorial/01_INSTALL.md` | Install and verify the environment |
| T02 | `docs/tutorial/02_FIRST_READ_ONLY_TASK.md` | Inspect a repository safely |
| T03 | `docs/tutorial/03_EVIDENCE.md` | Separate facts from model proposals |
| T04 | `docs/tutorial/04_OURD.md` | Map a bounded problem |
| T05 | `docs/tutorial/05_IURM.md` | Design a one-variable experiment |
| T06 | `docs/tutorial/06_EGCF.md` | Compile an inspectable command |
| T07 | `docs/tutorial/07_EON.md` | Inspect an exact proposed mutation |
| T08 | `docs/tutorial/08_CFEL.md` | Observe and classify a failure |
| T09 | `docs/tutorial/09_SAA.md` | Retrieve an existing algorithm |
| T10 | `docs/tutorial/10_ADAPTATION.md` | Adapt one controlled dimension |
| T11 | `docs/tutorial/11_AB_EVIDENCE.md` | Compare a candidate with a baseline |
| T12 | `docs/tutorial/12_CLOSED_LOOP.md` | Promote and re-retrieve qualified knowledge |
| T13 | `docs/tutorial/13_BUILD_A_WORKFLOW.md` | Combine the complete governed loop |

The first shared story is the failed kitchen light. It teaches OURD, IURM, EON,
CFEL, SAA, and failure memory before domain-specific software examples.

Later lessons add controller oscillation, parser regression, unsupported report
claims, and algorithm comparison. Each lesson uses deterministic expected output
or a checked-in fixture.

## 11. CLI Learning Tracks

### 11.1 Entry-point map

The docs derive the five package command names from `pyproject.toml` and show:

```text
OIEC-STM-Agent
├── oiec-stm-agent
├── ourd-agent       alias
├── oiec-stm-gui
└── ourd-gui         alias

EGCF
└── egcf
```

Tests must prove the documentation matches the package metadata.

### 11.2 Main agent walkthrough

The first command is:

```bash
oiec-stm-agent .
```

The next command is:

```bash
oiec-stm-agent . --task "Explain this repository"
```

The tutorial explains program, workspace, task, bounded run, and the supported
interactive commands `/new`, `/help`, `/exit`, and `/quit`.

### 11.3 Write-mode walkthrough

Write mode receives a separate tutorial that explains the difference between a
tool capability and granted authority. The canonical first example is:

```bash
oiec-stm-agent . \
  --write \
  --write-path "docs/**" \
  --task "Improve the introduction"
```

The guide must prove these current rules:

- `--write` requires at least one explicit `--write-path`;
- `--write-path` is an authority boundary, not a prediction;
- bounded write mode retains exact-candidate approval;
- `--write` and external `--authority` remain mutually constrained by the real
  parser contract; and
- `--yolo` cannot silently broaden bounded write authority.

Every published command example is parser-tested.

### 11.4 Provider wizard

The provider guide offers:

```text
OpenAI
Ollama / local
Other OpenAI-compatible service
```

The wizard generates copyable commands from the actual provider options:
model, base URL, API key, reasoning effort, output limit, context budget,
timeout, transport retries, and maximum reasoning samples.

Secrets are never persisted in local storage, example URLs contain no embedded
credentials, and API keys are represented by placeholders.

### 11.5 EGCF walkthrough

EGCF begins with:

```bash
egcf capability list --repo .
```

The guide teaches the grammar:

```text
egcf namespace verb options
```

Modifiers are introduced through scope, risk, evidence, approval, execution,
and rollback rather than as one flat flag table. Advanced examples remain
parser-tested against `ourd/egcf/cli.py`.

### 11.6 Capability levels

C0 through C5 use the workshop analogy and retain the exact technical meaning.
C4 and C5 must continue to be described as fail-closed states, not merely higher
permission tiers.

### 11.7 GUI first-launch guide

The GUI guide begins with:

```bash
oiec-stm-gui --repo .
```

The first-launch sequence is repository, question, plan, evidence, and approve
or reject. Advanced panels and `--smoke-test` remain available in Technical
view.

## 12. Interactive Learning Tools

All tools use checked-in catalogs and fixtures only.

### 12.1 Command builder

The builder selects command type, workspace, target, risk, explanation, graph,
strictness, simulation, and other valid modifiers. It produces a command and a
plain-language explanation for each token.

The output must parse successfully with the real CLI parser. Invalid option
combinations are disabled or explained before command generation.

### 12.2 Output decoder

The decoder maps exact status values to plain-language meaning, trigger, next
step, user action, and related concepts. It never interprets arbitrary command
output as trusted HTML.

### 12.3 Acronym Inspector

The inspector expands recognized acronyms from the canonical glossary and links
to their concept pages. Unknown uppercase tokens are reported as unresolved;
they are not guessed.

### 12.4 Trace This Term

The tool projects the existing relational graph into explanatory sentences such
as detected by, surfaced by, blocks, recorded by, or prevents. It uses canonical
relations where available and visibly labels non-canonical related links.

### 12.5 Tutorial sandboxes

Browser-only sandboxes load deterministic JSON fixtures, advance through fixed
state transitions, and expose why each result occurred. They have no network,
filesystem, provider, command, clipboard-write-by-default, or mutation path.

### 12.6 Break the invariant

Selected lessons allow a reader to choose an invalid action and observe a
deterministic refusal. The refusal must explain the violated invariant and the
evidence needed to continue safely.

## 13. Shared Visual Grammar and SVG Interaction

The current independent SVG generators move behind
`tools/docs_visual_grammar.py`.

Implementation rules:

1. Every SVG has `<title>` and `<desc>`.
2. Every semantic node has a stable `data-doc-node` ID and typed role.
3. Every semantic edge declares verification state and relation type.
4. Color is never the only carrier of meaning.
5. Keyboard focus and visible focus styling are required for interactive nodes.
6. Reduced-motion mode removes animations without removing information.
7. Clicking a node opens a page-local concept card with plain meaning, input,
   output, related concepts, analogy, and a Learn More link.
8. SVG interaction failure leaves a readable static diagram and fallback link.
9. Standalone relational symbols retain stable object IDs and source bindings.
10. The generator tests all 1,369 baseline SVG roles before migration is called
    complete; the expected count is derived, never frozen.

The migration order is:

1. homepage learning diagrams;
2. tutorial diagrams;
3. core concept diagrams;
4. CLI and GUI diagrams;
5. all remaining concept figures;
6. document figures;
7. relational symbols and topology views.

## 14. Navigation, Search, Prerequisites, and Progress

### 14.1 Prerequisite graph

Every tutorial and core concept lists prerequisites. The generator validates a
closed acyclic prerequisite graph and renders `You are here` course maps.

### 14.2 Intent-oriented search

The first implementation uses a deterministic static intent index with curated
synonyms, task language, misconceptions, failure descriptions, statuses, and
concept relations. Searching for `agent repeats a failed action` must return
CFEL and Failure Algebra even without those exact titles.

This feature is called intent-oriented search until an evaluated semantic index
exists. The documentation must not claim embedding or model-based semantic
search when none is present.

### 14.3 Vocabulary memory

The browser may count local concept views and progressively shorten repeated
definitions. It stores no task text, command text, API key, repository path, or
personal identifier. A visible reset control clears all learning preferences.

### 14.4 Teacher and printable modes

Teacher mode exposes objectives, exercises, hints, and checked answers.
Print mode produces a stable course order with both Learn and Technical blocks,
expanded glossary terms, figure captions, source/version metadata, and no
interactive-only dependency.

## 15. Architecture Explorer Preservation

The complete expert explorer moves to `docs/architecture-explorer.html`.

The page preserves:

- all relational object IDs;
- all canonical parent edges;
- all related links;
- all filters;
- text search;
- object selection;
- relation ports;
- symbol identities;
- source keys;
- topology SVG; and
- manifest reconstruction.

The homepage contains only a preview, current counts, and an explicit link.
No relational object is removed from the manifest to meet the homepage payload
budget.

## 16. Performance, Accessibility, Security, and Privacy Budgets

### 16.1 Homepage budgets

The generated default homepage must satisfy:

```text
raw HTML <= 350 KiB
DOM elements <= 1,500
relational rows embedded by default = 0
full relational JSON embedded by default = 0
initial SVG/object embeds <= 4
```

The Architecture Explorer may have a larger expert payload, but its size and
object counts are reported separately.

### 16.2 Accessibility gates

Required gates include:

- one clear `h1` and logical heading order;
- keyboard operation for all controls;
- visible focus;
- labels for search, mode, depth, builder, and decoder controls;
- alt/fallback text for all diagrams;
- no color-only state;
- reduced-motion parity;
- mobile containment at 320, 375, 430, 768, and 1024 CSS pixels;
- print readability; and
- no hidden Learn content when JavaScript is unavailable.

### 16.3 Security and privacy gates

The browser code must:

- treat pasted output as text;
- never use `innerHTML` for untrusted content;
- never store provider secrets;
- never execute generated commands;
- never fetch a provider or repository endpoint;
- keep sandboxes fixture-only; and
- expose a local-preference reset.

## 17. Implementation Phases

### Phase P0 — Freeze Baseline and Recovery

**Dependencies:** none.

1. Record current commit, status, generator hash, manifest hash, asset hashes,
   current counts, homepage size, and focused test results.
2. Preserve a patch and untracked archive before broad generator changes.
3. Record screenshots or structural captures for desktop and mobile if the
   environment supports them.
4. Freeze current relational IDs and generated-reference compatibility fixtures.

**Gate P0:** baseline artifacts reconstruct the pre-redesign site and all 989
relational object IDs are preserved.

### Phase P1 — Introduce Content Kinds and Catalog Schemas

**Dependencies:** P0.

1. Add `tools/docs_learning_catalog.py`.
2. Add `tools/docs_cli_catalog.py`.
3. Add `tools/docs_status_catalog.py`.
4. Add `tools/docs_visual_grammar.py`.
5. Add strict dataclasses and validation for every contract in Section 7.
6. Classify all existing documents without changing generated appearance.
7. Extend the manifest with versioned `content_kinds`, `learning_paths`,
   `tutorials`, `task_routes`, `status_definitions`, `visual_grammar`, and
   `documentation_statuses` sections.

**Gate P1:** current docs regenerate byte-identically except for the intentional
manifest schema extension, and every new catalog has strict owner tests.

### Phase P2 — Establish the Learning Visual System

**Dependencies:** P1.

1. Define Learn and Technical typography, density, spacing, color, and component
   tokens.
2. Preserve the current console aesthetic as the Technical/Explorer theme.
3. Add textbook cards, lesson steps, analogy blocks, misconception blocks,
   evidence badges, prerequisite maps, and responsive diagrams.
4. Add print styles and reduced-motion parity.
5. Create the first plain-language loop SVG using the shared grammar.

**Gate P2:** component fixture pages pass keyboard, contrast, narrow-screen,
print, and reduced-motion structural tests.

### Phase P3 — Replace the Homepage Shell

**Dependencies:** P2.

1. Replace the jargon-first hero with the plain-language hero.
2. Add the simple six-stage loop.
3. Add Before OIEC / With OIEC.
4. Add First 15 Minutes.
5. Add Learn by Task.
6. Add Learn the Core.
7. Add Tutorial, Tools, Explorer, and Reference entry cards.
8. Remove the complete relational tree and JSON from the default homepage.

**Gate P3:** the first viewport contains no unexplained architecture acronym,
homepage payload budgets pass, and every previous expert destination remains
reachable.

### Phase P4 — Move and Preserve the Architecture Explorer

**Dependencies:** P3.

1. Generate `docs/architecture-explorer.html` from the existing explorer model.
2. Preserve object search, filters, relation inspection, topology interaction,
   source keys, and symbols.
3. Update all index and category jumps to the new page.
4. Preserve old `#documentation-tree` links through a generated redirect or
   stable compatibility anchor.

**Gate P4:** all 989 objects, all manifest relations, and all standalone symbols
remain reachable and machine-checkable from the explorer.

### Phase P5 — Add Learn/Technical Mode and Formalism Depth

**Dependencies:** P2 and P3.

1. Add accessible mode controls to index, tutorial, concept, task, and reference
   templates.
2. Add Novice, Intermediate, and Expert blocks.
3. Persist only display preferences in local storage.
4. Add no-JavaScript and print fallbacks.

**Gate P5:** every target page exposes both modes on one URL, all content is
reachable without JavaScript, and mode state never affects source identity.

### Phase P6 — Enforce the Concept Teaching Contract

**Dependencies:** P1 and P5.

1. Author complete records for core systems and mandatory acronyms.
2. Add deterministic source-derived facets for public classes and namespaces.
3. Add prerequisites, misconceptions, failure examples, formalism blocks,
   evidence badges, and source bridges.
4. Add the acronym linter and exact coverage report.
5. Regenerate all concept pages.

**Gate P6:** `333 / 333` current concepts satisfy the teaching contract, every
detected acronym resolves, and no source-derived fallback is mislabeled as
human-reviewed prose.

### Phase P7 — Build Tutorial Infrastructure

**Dependencies:** P1, P2, and P5.

1. Create `docs/tutorial/` sources T00 through T13.
2. Add tutorial index, previous/next navigation, prerequisites, objectives, and
   progress controls.
3. Add deterministic expected outputs and fixture references.
4. Add the kitchen-light shared story.
5. Keep tutorial pages outside the expert 25-paragraph contract.

**Gate P7:** all 14 lessons exist in exact order, every required tutorial section
is present, every link closes, and every fixture hash is recorded.

### Phase P8 — Implement First 15 Minutes and Main CLI Walkthrough

**Dependencies:** P7.

1. Derive entry points from `pyproject.toml`.
2. Derive main parser options from `ourd/cli.py`.
3. Document aliases and interactive commands.
4. Add parser-tested read-only examples.
5. Add an output explanation for snapshot, preflight, and bounded task runs.

**Gate P8:** every displayed entry point exists and every command example parses
under the current CLI contract.

### Phase P9 — Implement Write-Mode Tutorial

**Dependencies:** P8.

1. Build the read-only versus write-session visual.
2. Explain write-path authority and exact-candidate approval.
3. Add valid and invalid command examples.
4. Add a deterministic refusal example for missing scope.
5. Link authority, evidence, EON, verification, and rollback concepts.

**Gate P9:** positive examples parse, negative examples fail for the intended
reason, and no prose implies that tool capability creates authority.

### Phase P10 — Implement Provider Wizard

**Dependencies:** P8.

1. Add OpenAI, Ollama/local, and other compatible provider recipes.
2. Generate commands from current parser options.
3. Explain each field visually.
4. Add copy controls that exclude secrets by default.
5. Add preflight and common-failure decoding.

**Gate P10:** every generated recipe parses, contains no real credential, and
matches current provider defaults and constraints.

### Phase P11 — Rewrite EGCF and Capability Learning

**Dependencies:** P8.

1. Create the beginner EGCF grammar walkthrough.
2. Teach modifiers through scope, risk, evidence, approval, execution, and
   rollback.
3. Add capability workshop diagrams for C0 through C5.
4. Add dry-run, why, graph, strict, simulation, trace, replay, snapshot, and
   projection examples.
5. Preserve the existing command reference as Technical view.

**Gate P11:** every EGCF example parses, C4/C5 remain fail-closed, and reference
coverage does not regress.

### Phase P12 — Add GUI First-Launch Guide

**Dependencies:** P7 and P8.

1. Document repository selection, Agent Chat, plan inspection, evidence, and
   approval/rejection.
2. Add progressive disclosure for advanced panels.
3. Link workbench panels to the relevant concept pages.
4. Keep backend flags and smoke mode in Technical view.

**Gate P12:** the guide matches the current GUI parser and workbench navigation,
and it grants no GUI mutation authority.

### Phase P13 — Migrate the Universal SVG Grammar

**Dependencies:** P2, P6, P7, P11, and P12.

1. Migrate novice diagrams first.
2. Migrate every concept and document SVG generator.
3. Add typed node and edge metadata.
4. Add interactive concept cards and keyboard handling.
5. Retain static fallback and source-bound identity.
6. Parse every generated SVG as XML.

**Gate P13:** every generated SVG satisfies the visual and interaction contract;
the derived total has zero omissions.

### Phase P14 — Add Task Routes, Prerequisites, and Intent Search

**Dependencies:** P6 and P7.

1. Add the nine initial task routes.
2. Build and validate the prerequisite DAG.
3. Add `You are here` maps.
4. Build the deterministic intent index.
5. Add misconception and failure-language synonyms.

**Gate P14:** task routes resolve to closed learning paths, prerequisite cycles
are impossible, and required natural-language searches return expected concepts.

### Phase P15 — Add Command Builder, Decoder, Inspector, and Trace Tool

**Dependencies:** P8, P10, P11, and P14.

1. Build the command builder from CLI catalog data.
2. Build the status decoder from the status catalog.
3. Build the Acronym Inspector from the glossary.
4. Build Trace This Term from relational records.
5. Escape all pasted or selected text.

**Gate P15:** generated commands parse, all published statuses decode, unknown
tokens fail closed, and browser security tests pass.

### Phase P16 — Add Sandboxes, Failure Museum, and Case Studies

**Dependencies:** P7, P13, and P15.

1. Add fixture-only OURD/IURM/EON/CFEL/SAA sandboxes.
2. Add break-the-invariant exercises.
3. Add a failure museum with preserved limitations and refusal reasons.
4. Add everyday, cooking, engineering, automotive, research, software, writing,
   and business case studies.
5. Add two-perspective diagrams for model belief versus verified state.

**Gate P16:** sandboxes make no external calls, fixtures are deterministic, and
case-study claims bind evidence badges and sources.

### Phase P17 — Add Source Bridge, Timeline, Teacher, Print, and Vocabulary Memory

**Dependencies:** P6, P7, and P16.

1. Add simplified Python source maps before raw source links.
2. Add the `Why was this invented?` timeline.
3. Add teacher objectives, exercises, hints, and answers.
4. Add printable course output.
5. Add local vocabulary-memory behavior and reset controls.
6. Add page commit/version snapshots.

**Gate P17:** source maps resolve, print output is complete, teacher answers are
deterministic, and privacy tests prove only display preferences are stored.

### Phase P18 — Expand Manifest, Linting, and CI Evidence

**Dependencies:** P6 through P17.

1. Version the manifest schema.
2. Add exact coverage summaries for concepts, tutorials, examples, diagrams,
   statuses, prerequisites, commands, badges, and sources.
3. Add concept linting, acronym linting, status linting, alt-text linting, and
   teaching-contract linting.
4. Add homepage payload and DOM budgets.
5. Add JavaScript syntax checks for every asset.
6. Add deterministic build and link checks.

**Gate P18:** CI reports exact numerator/denominator coverage with zero missing
mandatory rows and fails closed on undocumented new acronyms or statuses.

### Phase P19 — Full Regeneration, Validation, and Release Candidate

**Dependencies:** all previous phases.

1. Freeze the final source snapshot.
2. Run the canonical generator twice with the same explicit date.
3. Compare every generated byte and tree hash.
4. Verify every source hash in the manifest.
5. Parse every SVG.
6. Validate all JavaScript.
7. Validate all local pages, anchors, assets, IDs, prerequisites, commands,
   statuses, and relations.
8. Run focused documentation tests.
9. Run complete repository discovery.
10. Run headless GUI and package smoke tests.
11. Record remaining browser or optional-renderer limitations.
12. Produce a rollback manifest and exact commit/tree hashes.

**Gate P19:** all deterministic gates pass on one exact source tree. Human visual
review remains separate from deterministic validation and must approve desktop,
mobile, print, Learn, Technical, and reduced-motion views before release.

## 18. Requirement Traceability Matrix

| Requirement | Primary phases | Required evidence |
| --- | --- | --- |
| R01 Plain-language homepage | P3 | first-viewport language test and visual review |
| R02 Learn/Technical layers | P5 | same-URL mode tests and no-JS fallback |
| R03 Concept Teaching Contract | P6 | exact concept coverage report |
| R04 Everyday system examples | P7, P16 | lesson and case-study fixtures |
| R05 Homepage learning map | P3, P14 | ordered navigation contract |
| R06 Tutorial curriculum | P7 | 14/14 lesson coverage |
| R07 First 15 Minutes | P8 | parser-tested walkthrough |
| R08 Main CLI walkthrough | P8 | CLI catalog parity |
| R09 Write-mode tutorial | P9 | positive and negative parser tests |
| R10 Provider wizard | P10 | recipe and secret-safety tests |
| R11 EGCF beginner guide | P11 | EGCF parser parity |
| R12 Modifier visuals | P11, P13 | visual grammar and content tests |
| R13 Capability analogy | P11 | C0-C5 semantic tests |
| R14 GUI first launch | P12 | GUI parser and panel map checks |
| R15 Universal SVG language | P13 | complete SVG role coverage |
| R16 Interactive SVGs | P13 | node-card and keyboard tests |
| R17 Formalism slider | P5 | three-depth content coverage |
| R18 Misconception sections | P6 | 333/333 misconception coverage |
| R19 Before/with animation | P3, P13 | motion and reduced-motion parity |
| R20 Learn by task | P14 | nine task-route tests |
| R21 CLI command builder | P15 | generated-command parser tests |
| R22 Output decoder | P15 | status catalog coverage |
| R23 Trace This Term | P15 | relation projection tests |
| R24 Concept prerequisites | P14 | closed acyclic graph test |
| R25 Encyclopedia glossary | P6, P15 | acronym and glossary coverage |
| R26 Read-only sandboxes | P16 | no-network/no-mutation tests |
| R27 Real-world domains | P16 | eight case-study records |
| R28 Architecture Explorer | P4 | 989-object compatibility audit |
| R29 Novice visual tone | P2, P3, P5 | responsive visual review |
| R30 Progressive learning progression | P3, P7, P14 | route and course-order tests |

## 19. Additional Feature Traceability

| Feature | Phase | Gate |
| --- | --- | --- |
| Concept linting | P18 | undocumented acronym/status/alt failure |
| Documentation coverage report | P18 | exact numerator/denominator report |
| Evidence badges | P6, P18 | every core record binds evidence |
| Invention timeline | P17 | source-linked timeline entries |
| Failure museum | P16 | preserved failure and limitation evidence |
| Break-the-invariant lessons | P16 | deterministic refusal fixtures |
| Belief versus verified diagrams | P16 | distinct visual states and legend |
| Page source snapshots | P17 | commit/version metadata on every page |
| Intent-oriented search | P14 | natural-language retrieval fixtures |
| Printable course | P17 | print completeness test |
| Teacher mode | P17 | objectives/exercises/answers coverage |
| Source-code bridge | P17 | valid source-path links |
| Status decoder | P15 | complete status coverage |
| Command recipes | P8-P11, P15 | parser-tested recipe coverage |
| Vocabulary memory | P17 | local-only storage and reset test |

## 20. Test Architecture

The final focused test layout should include:

```text
tests/test_docs_site.py
tests/test_docs_learning_catalog.py
tests/test_docs_cli_catalog.py
tests/test_docs_status_catalog.py
tests/test_docs_visual_grammar.py
tests/test_docs_tutorials.py
tests/test_docs_interactions.py
tests/test_docs_accessibility.py
tests/test_docs_performance.py
tests/test_docs_security.py
```

Required deterministic tests include:

1. homepage plain-language ordering;
2. homepage payload and DOM budgets;
3. tutorial file/order/section/fixture coverage;
4. concept teaching-contract coverage;
5. acronym discovery and exact glossary closure;
6. status discovery and exact decoder closure;
7. CLI entry-point and parser parity;
8. positive and negative command recipe behavior;
9. Learn/Technical/depth/no-JS/print coverage;
10. prerequisite DAG closure and acyclicity;
11. task-route closure;
12. intent-search fixtures;
13. visual grammar, SVG XML, metadata, keyboard and fallback coverage;
14. relational explorer completeness;
15. local link, anchor, asset and duplicate-ID checks;
16. source hash and page snapshot checks;
17. deterministic repeated builds;
18. local-storage privacy checks;
19. untrusted output escaping; and
20. complete repository regression discovery.

## 21. Validation Order

Run validation in this order so failures remain attributable:

```text
1. compileall for generator/catalog/test modules
2. catalog schema and owner tests
3. homepage and tutorial focused tests
4. concept/acronym/status coverage tests
5. CLI parser and recipe tests
6. SVG grammar and XML tests
7. interaction, accessibility, security and privacy tests
8. architecture explorer compatibility tests
9. canonical documentation generation
10. repeated-build byte comparison
11. JavaScript syntax checks
12. local link and source-hash audit
13. homepage payload and DOM audit
14. complete documentation suite
15. complete repository unittest discovery
16. headless GUI smoke
17. reproducible wheel and sdist build
18. clean extracted-wheel command smoke
19. git diff and untracked-artifact audit
20. human visual review
```

An interrupted, timed-out, stale-source, or partially discovered test run is not
a pass.

## 22. Rollback Strategy

The redesign is delivered in additive, reviewable slices.

1. Preserve the current homepage generator before P3.
2. Keep current expert templates callable until replacement gates pass.
3. Introduce the Architecture Explorer before removing the object bus from the
   homepage.
4. Keep old anchors or generated compatibility redirects.
5. Version new manifest fields and retain old required fields during migration.
6. Regenerate from source rather than hand-editing HTML or SVG.
7. Record the exact last-known-good source commit, tree hash, docs tree hash,
   manifest hash, and package hashes.
8. Roll back by reverting the smallest failed phase and regenerating from the
   restored source.

## 23. Definition of Done

The novice-first redesign is complete only when:

- the homepage teaches before it catalogs;
- all 30 redesign requirements have passing evidence;
- all additional features selected for this plan have passing evidence;
- every current concept satisfies the teaching contract;
- every detected acronym and published status has one canonical explanation;
- all 14 tutorials and all nine task routes are complete;
- every CLI recipe is parser-valid;
- every sandbox is deterministic and non-mutating;
- every SVG satisfies the common accessibility and interaction contract;
- the Architecture Explorer preserves the full expert relational universe;
- Learn, Technical, depth, print, mobile, reduced-motion, and no-JavaScript views
  remain coherent;
- homepage performance budgets pass;
- generated output is byte-reproducible;
- all focused and complete repository tests pass on one exact source tree;
- human review approves the teaching sequence and visual hierarchy; and
- the final merged commit and remote `main` SHA are identical.

## 24. Recommended First Implementation Tranche

The first implementation tranche should be P0 through P5 only:

1. freeze the current site and compatibility inventory;
2. introduce content kinds and catalogs;
3. establish the learning visual system;
4. replace the homepage shell;
5. move the full object bus into Architecture Explorer; and
6. add Learn/Technical/depth controls.

This tranche proves the central redesign claim without first authoring all
tutorials or migrating all SVGs. Its exit evidence must demonstrate that a new
reader can reach a plain-language explanation and first safe task while experts
retain the complete relational system. Only after that gate passes should the
team expand all 333 concept teaching records and the full tutorial curriculum.
