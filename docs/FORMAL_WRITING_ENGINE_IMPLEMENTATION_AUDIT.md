# Formal Writing Engine and ICPI Implementation Audit

**Audit date:** August 31, 2026  
**Plan:** `FORMAL_WRITING_ENGINE_ICPI_IMPLEMENTATION_PLAN.md`  
**Status:** Implementation complete for the dependency-light core and governed
candidate path; optional PDF/OCR qualification, human visual review, and
release certification remain explicit external gates.

## Implemented Surfaces

- Public compatibility facade: `ourd/formal_writing.py`
- Engine package: `ourd/writing_engine/`
- Dedicated CLI: `ourd/formal_writing_cli.py`
- Existing CLI compatibility: `ourd/cli.py`
- ICPI interpretation, routing, commands, context roles, and turn policy:
  `ourd/interaction/`
- Governed agent tool: `formal_writing_execute` in `ourd/agent.py`
- Read-only GUI projections and views: `ourd_gui/formal_writing_projection.py`
  and `ourd_gui/views/formal_writing.py`
- Contracts: `schemas/formal_writing/contracts.schema.json`
- Governed reasoning IR contracts:
  `schemas/formal_writing/governed-pipeline.schema.json`
- Local grammar constraints: `grammars/formal_writing/`
- OIEC-Bench track: `benchmarks/formal_writing/` and
  `tools/run_formal_writing_benchmark.py`

## Governed Reasoning Pipeline

The source-grounding engine now feeds a signed pipeline:

```text
Question -> Meaning -> Claims -> Evidence -> ArgumentTopology
         -> Draft -> Audit -> Revision -> QualifiedDocument
```

The canonical IR is implemented in
`ourd/writing_engine/pipeline_models.py`; deterministic orchestration is in
`ourd/writing_engine/pipeline.py`. The implementation covers FW-1 through
FW-14 from the August 31 plan: meaning resolution with a semantic-drift gate,
typed claim generation, evidence qualification, graph checks, SAA-first path
retrieval, paragraph compilation, constrained rendering,
counterargument/falsification revision, writing profiles, measurable audits,
the nested CLI, the four-panel GUI workbench, review-bound SAA proposals,
novelty review states, and the OIEC-Bench formal-writing track.

SAA admission remains fail closed. A document must have status
`QUALIFIED_FORMAL_DOCUMENT`, then an exact human reviewer and approval ID may
register the proposal as `PROPOSED`. The existing EGCF qualification process
must still qualify the exact digest before path retrieval may reuse it.

## Requirement Evidence

| ID | Implementation | Current evidence status |
| --- | --- | --- |
| FW-001 | Existing profiles, topology API, imports, and facade retained | Verified by compatibility and writing tests |
| FW-002 | Content-addressed source IDs, deterministic extraction signatures, refresh and retirement | Verified for repeated paths, duplicate bytes, and stale refresh |
| FW-003 | Physical page index and display label are separate contracts | Unit-verified; optional live PDF adapter qualification remains pending |
| FW-004 | Exact quote, prefix/suffix, offsets, line/section, page spans, words, and geometry selectors | Exact anchor/stale-hash tests pass; PDF geometry golden corpus remains pending |
| FW-005 | Deterministic lexical passage index produces verified locators | Verified for reflowable sources; page-aware PDF benchmark pending optional dependency |
| FW-006 | Paraphrase checks cover polarity, qualifiers, scope, causal strength, unsupported additions, and patchwriting | Focused adversarial tests pass; the full benchmark matrix remains a qualification task |
| FW-007 | Concept annotations retain source spans, confidence, proposer, and review state | Implemented and exercised in formal-writing tests |
| FW-008 | Reasoning annotations and existing argument topology retain provenance and review state | Implemented and exercised in explanation/draft tests |
| FW-009 | Signed plans bind task, thesis, sections, claims, sources, topology, policies, gaps, and outputs | Verified through deterministic service results |
| FW-010 | Grounded drafts map citations to references; revisions bind the prior draft hash | Verified, including multi-source mapping and revision provenance |
| FW-011 | CSL-compatible bibliographic records, author-date/numeric rendering, and bibliography export | Verified by draft/export tests; no external citeproc dependency is claimed |
| FW-012 | Signed reference integrity report and writing certificate | Verified for passing drafts and distortion/stale-source cases |
| FW-013 | One shared service owns CLI, legacy CLI, ICPI, agent tool, GUI persistence, and tests | Cross-surface request compilation and projections verified |
| FW-014 | `oiec-stm-formal-write` exposes all planned command groups and common flags | Parser, locate smoke, entry-point declaration, and governed candidate tests pass |
| FW-015 | Natural-language formal-writing recognizer and role-aware context references | Interaction suite verifies operation routing and confirmation boundaries |
| FW-016 | Exact request confirmation prepares transaction and EON action without applying | Candidate preparation verified; human evidence approval/apply is intentionally not automated |
| FW-017 | GUI exposes complete standalone and embedded formal-writing workbenches | Parser, real Tk smoke, display-backed widget tests, signed projection tests, graph/evidence/audit cross-selection, performance targets, and packaging pass; optional PDF/OCR visual review remains pending |
| FW-018 | Repository/source text remains untrusted data | Hostile-source fixture produces data references and no workspace action |
| FW-019 | Reflowable sources never receive fabricated pages; citations use verified spans and locators | Core zero-fabrication invariants pass; expanded golden corpus remains pending |
| FW-020 | Rollback-compatible governed path and qualification documents exist | Release bundle, wheel hash, human approval, and certification remain pending |

## August 31 Governed-Pipeline Evidence

| Plan item | Authoritative implementation evidence |
| --- | --- |
| FW-1 Formal Writing IR | Signed dataclasses and strict schema in `pipeline_models.py` and `governed-pipeline.schema.json` |
| FW-2 Meaning resolver | `resolve_meaning` reuses source-bound `ConceptAnnotation`; `SEMANTIC_DRIFT` is a hard audit failure |
| FW-3 Claim/evidence graph | Typed `Claim` and provenance-bearing `EvidenceLink` artifacts |
| FW-4 Argument topology | Directed `ArgumentGraph` with unsupported, cycle, contradiction, orphan, counterargument, drift, and strength checks |
| FW-5 SAA path retrieval | Qualified EGCF algorithms are searched before built-in topology templates |
| FW-6 Paragraph compiler | `ParagraphPlan` binds claim, evidence, reasoning, qualification, and link |
| FW-7 Constrained renderer | `DraftSection.sentence_claim_map` and `NoNewMaterialClaims` audit gate |
| FW-8 Falsification pass | Challenges revise the graph with explicit qualifications before rendering |
| FW-9 Deterministic audit | Eight requested metrics plus signed status and limitations |
| FW-10 CLI | `oiec-stm-agent write plan/research/argue/draft/audit/revise/explain/export` |
| FW-11 GUI | Document, argument graph, evidence, and audit panels with sentence trace selection |
| FW-12 SAA admission | Exact human approval creates a `PROPOSED` EGCF algorithm; qualification remains separate |
| FW-13 Novelty | `KNOWN`, `KNOWN_COMBINATION`, `NEW_APPLICATION`, and fail-closed potential-novelty review |
| FW-14 OIEC-Bench | Three deterministic qualification and failure-mode tasks |

## August 31 Formal-Writing GUI Candidate Evidence

The current source adds `ourd_gui/formal_writing_gui.py`, a reusable
`FormalWritingView`, typed form/job/preview models, a one-worker controller, and
a hardened signed projection store. Both standalone and main-workbench surfaces
call the same compiler, `FormalWritingService`, and shared governed preparation
function. No GUI approval, apply, certification, novelty acceptance, or SAA
qualification path exists.

Deterministic GUI evidence covers all ten read-only workflow actions; exact
plan-to-draft-to-audit-to-revision identity; ordered phase events; cooperative
cancellation and bounded close; malformed/tampered artifacts; source drift;
500-node/1,000-edge graph completeness; sentence-trace coverage; all canonical
audit statuses; exact novelty and proposal statuses; hostile source text;
input, artifact, page, graph, text, diagnostic, and PDF-preview bounds; exact
signature confirmation; drift rejection; prepared transaction/EON IDs; and
zero ordinary output-file mutation.

Measured local targets pass for warm standalone startup, cached refresh of 100
signed result artifacts, 500-node/1,000-edge projection, loaded selection, and
idle shutdown. The console entry point is included in reproducible wheel/sdist
tests. These results establish an implemented and deterministically validated
candidate only.

## Capability Boundary

The base environment validated on August 31, 2026 did not contain PyMuPDF or
`pytesseract`; Pillow was available. The PDF adapter therefore fails closed with
an explicit capability error, and OCR cannot run without both optional
dependencies and explicit permission. No claim of born-digital PDF or OCR
fixture qualification is made from this environment.

The deterministic lexical retriever is the implemented base. The
`formal-writing-semantic` optional extra is intentionally empty because no
embedding adapter has been selected or qualified. Semantic similarity is not
claimed as an implemented release capability.

## Release Boundary

Passing automated tests establishes implementation evidence, not academic or
release certification. Remaining release gates are:

1. install and lock optional PDF/OCR dependencies in a qualification
   environment;
2. run the planned born-digital, scanned, geometry, locator, paraphrase,
   citation, and adversarial golden corpus;
3. perform human GUI and document-quality review;
4. build and hash wheel/sdist artifacts from one frozen source snapshot;
5. prove apply, verification, finalization, and rollback with an explicitly
   approved disposable fixture; and
6. obtain exact-hash human release approval.
