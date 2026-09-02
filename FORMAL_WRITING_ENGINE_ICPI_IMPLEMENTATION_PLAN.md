# Formal Writing Engine and InteractiveCommandPromptInterface Implementation Plan

**Plan version:** 1.0  
**Plan date:** 2026-08-30, Australia/Brisbane  
**Status:** Candidate implementation plan; not implementation authority, certification, or release approval  
**Primary compatibility owner:** `ourd/formal_writing.py`  
**Natural-language interface name:** `InteractiveCommandPromptInterface` (`ICPI`)  

## 1. Executive Decision

Evolve the current formal-writing support into a source-grounded writing engine
that can:

1. ingest and fingerprint source documents;
2. locate source passages on exact physical and displayed pages;
3. point back to the supporting text with stable quote and position anchors;
4. distinguish quotation, close paraphrase, summary, synthesis, and inference;
5. identify the concept expressed by a reference;
6. identify the argumentative or reasoning role performed by a reference;
7. construct and validate a formal argument topology;
8. plan, draft, revise, and audit formal writing;
9. format citations and bibliographies without inventing metadata;
10. expose the same governed capabilities through a dedicated CLI and the
    `InteractiveCommandPromptInterface` natural-language surface.

The engine will be additive. Existing imports from `ourd/formal_writing.py`,
existing writing profiles, existing `--write` behavior, exact-snapshot write
authority, EON mutation boundaries, evidence gates, human approval, and
rollback semantics must remain compatible.

The architectural rule is:

```text
CLI command or ICPI natural language
  -> deterministic context and intent parsing
  -> typed FormalWritingRequest
  -> FormalWritingService
  -> source registry and page-aware reference engine
  -> argument and writing planner
  -> draft or validation result
  -> exact candidate transaction when mutation is requested
  -> existing OIEC/EON/evidence/approval/apply path
```

Neither the CLI nor ICPI may contain an independent citation engine, policy
engine, document parser, or write path. They are two input surfaces over the
same typed service.

## 2. Verified Current Baseline

### 2.1 Existing assets to preserve

| Existing asset | Reuse decision |
| --- | --- |
| `ourd/formal_writing.py` | Preserve as the public compatibility facade and owner of formal-writing profiles and argument topology exports |
| `WRITING_PROFILES` | Preserve `general`, `scientific-essay`, and `argumentative-essay`; add profiles only through versioned extension |
| `ArgumentNode`, `ArgumentEdge`, `ArgumentTopology` | Preserve behavior and validation; migrate internally only with compatibility tests |
| Positive-support acyclicity | Keep as a hard validation rule |
| Evidence-node `source_refs` requirement | Strengthen so references resolve to typed, hash-bound source spans |
| Counterclaim response requirement | Keep as a hard rule unless an explicit analytical profile permits an unanswered counterclaim |
| `ourd/writing.py` | Retain as the governed task-prompt adapter while progressively replacing prompt-only assumptions with typed artifacts |
| `ourd/cli.py --write` | Preserve as a compatibility entry point |
| `scoped_write_authority` | Reuse for exact-snapshot, path-bounded writing authority |
| ICPI context references | Extend existing `@file[...]`, `@folder[...]`, `@path[...]`, `#evidence[...]`, and `!constraint[...]` parsing rather than replacing it |
| ICPI confirmation flow | Reuse for all mutating formal-writing requests |
| EON, evidence gate, approval, apply, verification, rollback | Remain the only authoritative mutation path |

### 2.2 Current gaps

The current implementation provides research-backed prompt guidance and an
argument graph, but it does not yet provide:

- a durable formal-writing request or plan schema;
- a document source registry;
- source content fingerprints and edition identity;
- PDF page extraction or page-coordinate indexing;
- OCR fallback for scanned sources;
- physical-page and printed-page-label distinction;
- exact quote selectors or text-position selectors;
- quote-to-page round-trip verification;
- paraphrase-to-source alignment;
- concept identification tied to source spans;
- reasoning-role identification tied to source spans;
- bibliographic metadata reconciliation;
- CSL-compatible citation rendering;
- citation completeness and distortion auditing;
- a dedicated formal-writing CLI command;
- a formal-writing ICPI domain parser;
- a page-aware GUI source reader and reference inspector.

### 2.3 Naming decision

The canonical long name is `InteractiveCommandPromptInterface`; the canonical
short name remains `ICPI` to match the existing repository. `CIPI` may be
accepted as an input alias if required for backward compatibility, but it must
not create a second implementation or second set of schemas.

## 3. Scope

### 3.1 In scope

- Born-digital PDF ingestion with page geometry.
- Scanned PDF ingestion through explicit OCR fallback.
- Plain text, Markdown, and HTML source ingestion with non-page locators.
- Optional DOCX ingestion, provided page claims are made only after a stable
  rendered-PDF snapshot is created and fingerprinted.
- Local source libraries and explicit, policy-governed metadata retrieval.
- Exact quotation and page-aware passage lookup.
- Grounded paraphrase, summary, synthesis, and source comparison.
- Concept and reasoning annotation.
- Scientific and argumentative formal-writing workflows.
- Citation and bibliography formatting through CSL-compatible data.
- CLI and ICPI access to the same service.
- GUI inspection of sources, anchors, concepts, reasoning, and draft citations.
- Deterministic fixtures, benchmarks, qualification evidence, migration, and
  rollback.

### 3.2 Out of scope for v1.0

- Circumventing paywalls, authentication, access controls, or licensing terms.
- Treating arbitrary web search snippets as page-accurate primary sources.
- Claiming stable pages for reflowable HTML or EPUB content.
- Automatically trusting OCR text when confidence or visual alignment is poor.
- Fully autonomous academic submission or concealment of AI assistance.
- Replacing unit rubrics, institutional citation rules, or academic-integrity
  requirements.
- Letting model confidence substitute for deterministic source verification.
- Making Crossref or another metadata service the authority for passage text.
- Writing directly from the GUI or ICPI without the existing governed
  candidate, approval, and apply path.

## 4. Non-Negotiable Invariants

### 4.1 Source identity

Every page, quote, paraphrase, concept, reasoning annotation, citation, and
claim must identify the exact source artifact by content hash. A locator from
one edition, scan, or PDF revision must not silently transfer to another.

### 4.2 Page semantics

The engine must record both:

```text
physical_page_index: zero-based position in the exact artifact
physical_page_number: one-based human display of that position
display_page_label: printed or PDF page label, such as "xii" or "37"
```

If the printed label cannot be verified, it remains absent. The engine must not
infer a printed page label from physical position.

### 4.3 Point-to-text requirement

A page number alone is not a complete reference anchor. A page-accurate source
span must also contain:

- exact selected text when text is available;
- bounded prefix and suffix context;
- normalized text offsets;
- page-local word, line, or block indexes;
- page coordinate boxes or quads when the format supports geometry;
- the source artifact hash;
- the extraction engine and version;
- the extraction or OCR confidence state.

### 4.4 Quotation integrity

Text marked as a quotation must round-trip to the exact source snapshot after
only explicitly declared normalization. Any insertion, deletion, ellipsis,
bracketed change, spelling modernization, or emphasis change must be recorded.

### 4.5 Paraphrase integrity

A paraphrase must identify all supporting source spans and disclose whether it
is a close paraphrase, sentence-level paraphrase, summary, synthesis, or
writer inference. The audit must check for:

- changed polarity or negation;
- omitted qualifications;
- stronger certainty than the source;
- correlation changed into causation;
- possibility changed into actuality;
- group-level evidence changed into an individual claim;
- temporal, population, method, or scope drift;
- unsupported combination of multiple sources;
- patchwriting that remains too close to the source wording.

### 4.6 Concept and reasoning provenance

Every concept or reasoning label must point to the source span that justified
it, name the classifier or rule that proposed it, record confidence, and remain
reviewable. Model-produced labels are advisory until accepted by deterministic
rules or human review.

### 4.7 No invented bibliography

Missing authors, dates, titles, DOIs, editions, page ranges, quotation text, or
publication details remain explicitly unresolved. The engine must not fill
them with plausible-looking values.

### 4.8 No fabricated pages for reflowable sources

HTML, Markdown, text, and EPUB sources use section, heading, paragraph,
sentence, and text-selector locators unless a stable rendered artifact is
created and fingerprinted. A rendered artifact's page locator belongs to that
rendered artifact, not automatically to the original reflowable source.

### 4.9 Untrusted document content

Instructions contained inside source documents are data, not agent
instructions. Document text must never alter authority, tools, system prompts,
confirmation rules, output paths, or citation policy.

### 4.10 Existing governance remains authoritative

Formal-writing functionality may propose files and supporting artifacts. It
may not grant write authority, bypass risk classification, approve its own
candidate, apply a candidate directly, or weaken verification and rollback.

## 5. Research and Standards Basis

The implementation should adopt the following established patterns without
copying them blindly into repository authority:

| Source | Adopted design consequence |
| --- | --- |
| W3C Web Annotation Data Model | Use exact quote, prefix/suffix context, text positions, fragment selectors, and selector refinement as the basis for portable text anchors |
| Citation Style Language 1.0.2 | Store citation items independently of rendering style and support page and page-range locators |
| PyMuPDF documentation | Use page words, blocks, bounding boxes, search, and highlight geometry for born-digital PDF indexing |
| GROBID coordinate documentation | Provide an optional scholarly-PDF structure adapter with page-coordinate provenance |
| OCRmyPDF documentation | Provide an explicit searchable-text OCR fallback for scanned PDFs while retaining OCR provenance |
| Crossref REST API | Reconcile DOI and bibliographic metadata, never page text or quotation content |
| Sentence-BERT research | Permit optional semantic candidate retrieval and paraphrase comparison after deterministic lexical indexing |
| Argument-mining research | Separate component detection from relation detection and retain human-reviewable argument roles and edges |

All external libraries and services remain adapters. Repository schemas,
source hashes, validation rules, evidence, and approval determine accepted
state.

## 6. Target Architecture

```text
┌────────────────────────────────────────────────────────────────────┐
│ User surfaces                                                      │
│ dedicated CLI | existing --write compatibility | ICPI | GUI        │
└──────────────────────────────┬─────────────────────────────────────┘
                               │
┌──────────────────────────────▼─────────────────────────────────────┐
│ FormalWritingRequest compiler                                     │
│ operation | profile | sources | rubric | output | style | limits  │
└──────────────────────────────┬─────────────────────────────────────┘
                               │
┌──────────────────────────────▼─────────────────────────────────────┐
│ FormalWritingService                                              │
│ inspect | locate | explain | outline | draft | revise | validate  │
└────────────┬─────────────────┬──────────────────┬─────────────────┘
             │                 │                  │
┌────────────▼──────────┐ ┌────▼────────────────┐ ┌▼────────────────┐
│ SourceRegistry       │ │ ReferenceEngine      │ │ WritingEngine   │
│ identity/metadata    │ │ anchors/alignment    │ │ plan/draft/audit│
│ extraction snapshots│ │ concepts/reasoning   │ │ topology/cites  │
└────────────┬──────────┘ └────┬────────────────┘ └┬────────────────┘
             │                 │                  │
┌────────────▼─────────────────▼──────────────────▼─────────────────┐
│ Durable artifacts and evidence                                    │
│ source manifests | page indexes | anchors | plans | audit reports │
└──────────────────────────────┬─────────────────────────────────────┘
                               │ mutating request only
┌──────────────────────────────▼─────────────────────────────────────┐
│ Existing governed mutation path                                   │
│ exact authority -> candidate -> EON -> evidence -> approval       │
│ -> atomic apply -> verification -> rollback                       │
└────────────────────────────────────────────────────────────────────┘
```

## 7. Proposed Source Layout

`ourd/formal_writing.py` remains a module and public facade. A same-named
package must not be introduced beside it. New implementation ownership should
use a separate package:

```text
ourd/
├── formal_writing.py                 # compatibility facade and stable exports
├── formal_writing_cli.py             # dedicated CLI parser and presentation
├── writing.py                        # governed prompt compatibility adapter
├── writing_engine/
│   ├── __init__.py
│   ├── models.py                     # durable typed contracts
│   ├── signatures.py                 # canonical JSON and content signatures
│   ├── source_registry.py            # source identity and manifests
│   ├── ingestion.py                  # format dispatch and normalization
│   ├── pdf.py                        # born-digital PDF extraction
│   ├── ocr.py                        # scanned-PDF fallback adapter
│   ├── page_labels.py                # physical/display page mapping
│   ├── anchors.py                    # quote/position/geometry selectors
│   ├── passage_index.py              # lexical and optional semantic retrieval
│   ├── metadata.py                   # bibliographic reconciliation
│   ├── references.py                 # reference records and citation uses
│   ├── paraphrase.py                 # alignment and distortion checks
│   ├── concepts.py                   # concept proposals and taxonomy
│   ├── reasoning.py                  # reasoning roles and relations
│   ├── topology.py                   # formal argument graph integration
│   ├── planning.py                   # outline and claim-evidence planning
│   ├── drafting.py                   # bounded model drafting orchestration
│   ├── critique.py                   # source and argument audit
│   ├── citations.py                  # CSL-compatible rendering adapter
│   ├── reports.py                    # integrity and qualification reports
│   └── service.py                    # shared use-case API
├── interaction/
│   ├── formal_writing.py             # ICPI domain recognition and compilation
│   ├── context.py                    # extended role-aware references
│   ├── interpreter.py                # generic mode plus domain dispatch
│   ├── routing.py                    # formal-writing route targets
│   └── commands.py                   # deterministic slash commands
└── agent.py                          # service/tool integration only

ourd_gui/
├── views/
│   ├── writing.py                    # project, plan, draft, and audit workspace
│   └── source_reader.py              # page image/text and anchor display
├── writing_projection.py             # renderer-neutral writing read models
└── icpi_prompt.py                    # route and confirmation previews

schemas/formal_writing/
├── source-document-v1.schema.json
├── source-span-v1.schema.json
├── bibliographic-record-v1.schema.json
├── formal-writing-request-v1.schema.json
├── formal-writing-plan-v1.schema.json
├── argument-topology-v1.schema.json
├── reference-integrity-report-v1.schema.json
└── writing-certificate-v1.schema.json

grammars/formal_writing/
├── request-v1.gbnf
├── plan-v1.gbnf
├── annotation-v1.gbnf
└── audit-v1.gbnf
```

The facade should continue exporting the current profile and topology names.
New contracts may be re-exported only after their schema and serialization are
stable.

## 8. Canonical Data Contracts

### 8.1 `SourceDocument`

Required fields:

```text
schema_version
source_document_id
source_uri_or_path
workspace_relative_path
media_type
content_sha256
byte_size
title
authors
issued_date
publisher
edition
doi
isbn
language
page_count
page_label_map
ingestion_adapter
ingestion_adapter_version
extraction_created_at
ocr_status
ocr_engine
ocr_engine_version
license_or_access_note
metadata_provenance
signature
```

The content hash, not path or title, defines the exact artifact identity.
Bibliographic identity may relate several artifacts, but their locators remain
artifact-specific.

### 8.2 `PageRecord`

Required fields:

```text
source_document_id
physical_page_index
physical_page_number
display_page_label
width
height
coordinate_space
rotation
text_layer_kind
extraction_confidence
page_text_sha256
blocks
lines
words
```

Words and blocks carry page-local bounding boxes or quads and deterministic
indexes. Header/footer suppression is stored as an annotation; original
extracted content remains reproducible.

### 8.3 `TextAnchor`

Use a W3C-inspired selector composition:

```text
anchor_id
source_document_id
source_content_sha256
exact_text
prefix_text
suffix_text
normalized_exact_text
normalization_profile
document_start_offset
document_end_offset
page_spans
section_path
paragraph_index
sentence_indexes
selector_signature
```

Each page span contains:

```text
physical_page_index
display_page_label
page_start_offset
page_end_offset
word_start_index
word_end_index
line_indexes
block_indexes
bounding_quads
```

### 8.4 `ReferenceSpan`

```text
reference_span_id
anchor_id
reference_kind
verbatim_text
bounded_context
locator_display
extraction_confidence
verification_status
verification_failures
created_by
created_at
signature
```

`reference_kind` includes:

```text
quotation
paraphrase_support
summary_support
synthesis_support
definition
data
method
counterevidence
background
```

### 8.5 `ParaphraseLink`

```text
paraphrase_link_id
draft_text
source_span_ids
paraphrase_kind
lexical_overlap
semantic_similarity
support_relation
qualifier_preservation
polarity_preservation
scope_preservation
causal_strength_preservation
patchwriting_risk
unsupported_additions
advisory_model
review_status
signature
```

`support_relation` should distinguish at least:

```text
entailed
supported
partially_supported
contradicted
unresolved
writer_inference
```

A semantic similarity score is never by itself proof of support.

### 8.6 `ConceptAnnotation`

```text
concept_annotation_id
concept_id
preferred_label
definition
aliases
source_span_ids
broader_concept_ids
narrower_concept_ids
related_concept_ids
domain
explicit_or_inferred
confidence
proposed_by
review_status
signature
```

The first implementation should support a project-local concept registry and
free-form proposed concepts. External ontologies may be adapters, not mandatory
authorities.

### 8.7 `ReasoningAnnotation`

```text
reasoning_annotation_id
source_span_ids
component_role
relation_type
inference_mode
source_claim
target_claim
implicit_premises
qualifiers
limitations
alternative_explanations
confidence
proposed_by
review_status
signature
```

`component_role` includes the existing topology kinds:

```text
thesis
claim
premise
evidence
warrant
counterclaim
rebuttal
qualifier
limitation
implication
```

`relation_type` includes the existing topology relations plus an explicit
`cites` or `grounds` relation outside the positive-support graph.

### 8.8 `BibliographicRecord`

Store CSL-compatible fields plus provenance and conflicts:

```text
bibliographic_record_id
csl_item
source_document_ids
metadata_sources
field_provenance
conflicts
unresolved_fields
verified_doi
signature
```

Metadata may come from embedded PDF metadata, parsed title pages, user input,
Crossref, or another configured adapter. Conflicts remain visible and require a
deterministic policy or human resolution.

### 8.9 `FormalWritingRequest`

```text
schema_version
request_id
operation
objective
profile
genre
audience
discipline
word_target
source_document_ids
source_paths
rubric_paths
output_paths
citation_style
locale
quotation_policy
paraphrase_policy
reference_policy
network_policy
constraints
requested_outputs
authority_binding
context_envelope_signature
request_signature
```

Supported operations:

```text
INSPECT_SOURCES
LOCATE_REFERENCE
EXPLAIN_REFERENCE
BUILD_SOURCE_MAP
BUILD_ARGUMENT_MAP
OUTLINE
DRAFT
REVISE
VALIDATE
WRITE
EXPORT_REFERENCES
```

### 8.10 `FormalWritingPlan`

The plan binds the exact request to:

- task interpretation;
- thesis or controlling purpose;
- section structure;
- claim inventory;
- source and evidence allocation;
- concept coverage;
- argument topology;
- counterargument plan;
- citation style;
- quotation and paraphrase policy;
- unresolved evidence gaps;
- planned output paths;
- validation requirements;
- deterministic signature.

### 8.11 `CitationUse`

Each citation in a draft records:

```text
citation_use_id
draft_span
claim_id
bibliographic_record_ids
reference_span_ids
locator
use_kind
quotation_transformations
paraphrase_link_id
concept_annotation_ids
reasoning_annotation_ids
verification_status
```

### 8.12 `ReferenceIntegrityReport`

The report must separate:

```text
verified quotations
verified paraphrases
partially supported claims
unsupported claims
contradicted claims
missing locators
stale source hashes
metadata conflicts
unresolved citation fields
page-label uncertainty
OCR uncertainty
patchwriting risks
concept-review requirements
reasoning-review requirements
```

### 8.13 `WritingCertificate`

A writing certificate records validation evidence for an exact draft hash. It
does not certify truth, academic acceptability, or institutional compliance.
It records only the checks actually performed and their results.

## 9. Page-Accurate Reference Model

### 9.1 Accuracy levels

The user-facing interface must label reference precision explicitly:

| Level | Meaning |
| --- | --- |
| `ARTIFACT_ONLY` | Exact source artifact known; no stable location found |
| `SECTION` | Stable heading or structural path found |
| `PAGE` | Physical page found; printed label may be absent |
| `PAGE_LABEL` | Physical page and displayed page label verified |
| `TEXT` | Exact quote selector and offsets verified |
| `GEOMETRY` | Exact text plus page boxes or quads verified |
| `OCR_GEOMETRY` | OCR-derived exact text and geometry with explicit confidence |

The engine must not present a lower level as a higher one.

### 9.2 Locator display

A reference locator should be rendered from structured data, for example:

```text
Smith 2024, p. 37, paragraph 2, lines 4-7
Artifact SHA-256: 9f...c2
Physical PDF page: 49
Printed page label: 37
Anchor: "the exact selected text..."
```

The full artifact hash should remain available in the audit even when the UI
shows a shortened form.

### 9.3 Multiple-page spans

Quotes or passages spanning pages must store a separate page span and geometry
set for every page. The locator may display `pp. 37-38`, but it must not merge
coordinates into one invalid box.

### 9.4 Normalization

Normalization profiles must be named and versioned. Initial profiles may
handle:

- Unicode normalization;
- line-ending normalization;
- dehyphenation across line breaks;
- ligature expansion;
- whitespace folding;
- discretionary header/footer exclusion.

The original extracted text, normalized text, and transformation log must all
remain available.

## 10. Formal-Writing Workflow

### 10.1 Source intake

```text
resolve explicit source roles
  -> validate workspace paths and media types
  -> fingerprint exact bytes
  -> detect existing source manifest
  -> extract native text and geometry
  -> invoke OCR only when permitted and necessary
  -> create page-label map
  -> reconcile bibliographic metadata
  -> persist signed source manifest and page index
```

### 10.2 Reference discovery

```text
user query, claim, quote fragment, or draft sentence
  -> deterministic lexical candidate search
  -> optional semantic reranking
  -> page and text-anchor reconstruction
  -> exact round-trip validation
  -> source-context projection
  -> user or engine selection
```

### 10.3 Paraphrase analysis

```text
draft sentence
  -> retrieve candidate source spans
  -> bind selected supporting spans
  -> compare lexical overlap
  -> propose semantic support relation
  -> test polarity, qualifiers, scope, and causal strength
  -> identify unsupported additions
  -> return verified, partial, contradicted, or unresolved status
```

### 10.4 Concept analysis

```text
source span
  -> extract candidate key terms and definitions
  -> map to existing project concepts when possible
  -> propose new concepts when necessary
  -> connect broader, narrower, and related concepts
  -> retain source span and review status
```

### 10.5 Reasoning analysis

```text
source span or claim group
  -> detect argumentative components
  -> propose premise/claim/evidence/warrant roles
  -> propose support, attack, qualification, or limitation relations
  -> identify inference mode and implicit premises
  -> validate against topology rules
  -> expose uncertainty and unresolved edges
```

### 10.6 Planning and drafting

```text
validated request
  -> task and rubric analysis
  -> source map
  -> concept map
  -> argument topology
  -> section and paragraph plan
  -> citation allocation
  -> bounded section drafting
  -> section-level source audit
  -> whole-draft coherence and reference audit
  -> exact candidate transaction when writing is requested
```

## 11. CLI Design

### 11.1 Dedicated command

Add a console script without removing existing commands:

```toml
oiec-stm-formal-write = "ourd.formal_writing_cli:main"
```

`ourd/formal_writing.py` supplies the public engine API; CLI argument parsing
belongs in `ourd/formal_writing_cli.py` so importing the domain model never
causes CLI side effects.

### 11.2 Command groups

```text
oiec-stm-formal-write inspect
oiec-stm-formal-write locate
oiec-stm-formal-write explain-reference
oiec-stm-formal-write source-map
oiec-stm-formal-write argument-map
oiec-stm-formal-write outline
oiec-stm-formal-write draft
oiec-stm-formal-write revise
oiec-stm-formal-write validate
oiec-stm-formal-write write
oiec-stm-formal-write references
```

### 11.3 Common flags

```text
--workspace PATH
--source PATH                       repeatable
--rubric PATH                       repeatable
--output PATH                       repeatable for mutating operations
--profile PROFILE
--genre GENRE
--audience TEXT
--discipline TEXT
--word-target INTEGER
--citation-style STYLE
--locale LOCALE
--task TEXT
--network-policy offline|metadata-only|explicit-retrieval
--require-page-accuracy
--allow-ocr
--json
--report PATH
```

### 11.4 Examples

Read-only page-aware lookup:

```bash
oiec-stm-formal-write locate \
  --workspace . \
  --source research/paper.pdf \
  --task 'Locate the passage defining epistemic uncertainty and show its concept and reasoning role.'
```

Read-only paraphrase validation:

```bash
oiec-stm-formal-write validate \
  --workspace . \
  --source research/paper.pdf \
  --task 'Check whether this paraphrase preserves the source qualification: ...'
```

Governed writing:

```bash
oiec-stm-formal-write write \
  --workspace . \
  --source research/paper-a.pdf \
  --source research/paper-b.pdf \
  --rubric assignment/rubric.pdf \
  --output essay.md \
  --profile scientific-essay \
  --citation-style apa-7 \
  --word-target 2500 \
  --task 'Evaluate the evidence for the proposed mechanism.'
```

### 11.5 Compatibility behavior

The existing command remains valid:

```bash
oiec-stm-agent . --write --write-path essay.md --writing-profile scientific-essay --task '...'
```

When formal-writing sources or reference requirements are supplied, it should
compile the same `FormalWritingRequest` as the dedicated command. When they are
not supplied, current prompt-guidance behavior remains available during the
migration period.

## 12. InteractiveCommandPromptInterface Design

### 12.1 Domain recognition

Add a formal-writing domain recognizer after generic context extraction and
before generic route selection. It should recognize combinations of:

- formal-writing nouns: essay, paper, report, literature review, argument,
  thesis, paragraph, citation, bibliography, quotation, paraphrase, source;
- reference actions: locate, cite, quote, paraphrase, verify, explain, trace;
- reasoning actions: identify claim, premise, warrant, counterclaim,
  limitation, implication, inference;
- writing actions: outline, draft, revise, edit, write, validate;
- explicit source, rubric, output, profile, and citation-style references.

Generic intent classification remains available. The domain recognizer adds
typed formal-writing fields; it does not grant authority.

### 12.2 Role-aware reference syntax

Extend context reference kinds with:

```text
@source[path]
@sourcefolder[path]
@rubric[path]
@output[path]
@draft[path]
@style[name]
```

Existing forms remain supported:

```text
@file[path]
@folder[path]
@path[path]
#evidence[id]
!constraint[text]
```

Explicit role references override natural-language inference. Generic
`@file[...]` is treated as a context file until the user or parser assigns a
source, rubric, draft, or output role. `@output[...]` may refer to a prospective
path that does not yet exist; `@source[...]` must resolve to an existing,
readable artifact.

### 12.3 Natural-language examples

Read-only reference lookup:

```text
Using @source[research/paper.pdf], locate the page where the author defines
epistemic uncertainty. Point to the exact text, paraphrase it, identify the
concept, and explain whether the passage is a claim, premise, definition, or
warrant.
```

Read-only source comparison:

```text
Compare @source[research/a.pdf] and @source[research/b.pdf] on causal inference.
Show page-accurate passages, distinguish agreement from disagreement, and map
the reasoning relations without writing files.
```

Plan-only request:

```text
Plan a 2500-word scientific essay from @sourcefolder[research/papers] using
@rubric[assignment/rubric.pdf]. Use APA 7, build a claim-evidence-reasoning map,
and show unresolved evidence gaps. Proposal only.
```

Governed writing request:

```text
Write @output[essay.md] as a 2500-word scientific essay using
@source[research/a.pdf] and @source[research/b.pdf]. Require page-accurate
references, verify every quotation and paraphrase, and include an APA 7
bibliography.
```

Revision request:

```text
Revise @draft[essay.md] using @sourcefolder[research/papers]. Preserve the
thesis, correct unsupported paraphrases, add page locators where available,
and write the candidate back to @output[essay.md].
```

### 12.4 Deterministic slash commands

Add slash commands as an unambiguous escape hatch:

```text
/writing-help
/writing-inspect
/writing-locate
/writing-reference
/writing-paraphrase
/writing-concepts
/writing-argument
/writing-outline
/writing-draft
/writing-validate
/writing-write
```

Slash commands and free language compile to the same request schema and
signature. Slash commands must not bypass confirmation.

### 12.5 Route targets

Add explicit route targets:

```text
agent.formal_writing.inspect
agent.formal_writing.locate
agent.formal_writing.explain_reference
agent.formal_writing.plan
agent.formal_writing.governed_candidate
projection.formal_writing.source
projection.formal_writing.audit
```

### 12.6 Risk and confirmation rules

| Operation | Default risk | Confirmation |
| --- | --- | --- |
| Inspect local sources | L0 | Required only for unresolved or ambiguous context |
| Locate or explain a reference | L0 | Required for unresolved source identity |
| Outline or build maps without file output | L0 proposal | Required when source roles or scope are ambiguous |
| Draft in chat only | L0 proposal | Required when constraints are incomplete or sources unresolved |
| Persist an index or report outside internal governed storage | L1 | Always |
| Write or revise user files | L1 or deterministic L2 | Always exact confirmation |
| Fetch remote metadata | Capability-governed read | Confirm according to network policy |
| Retrieve remote full text | Explicit capability and access policy | Always explicit |

The exact confirmation preview must show:

- operation and writing profile;
- objective and word target;
- source paths and exact source hashes when already indexed;
- rubric and draft paths;
- output paths;
- citation style;
- page-accuracy and OCR policy;
- network policy;
- unresolved references and metadata;
- proposed risk;
- exact context-envelope signature;
- exact authority snapshot for mutating operations.

### 12.7 Fail-closed ICPI cases

Do not route to writing when:

- a source path is unresolved;
- output and source roles conflict;
- the same prospective output is also treated as an immutable source;
- a page-accurate claim is requested for a source without stable pagination;
- the source changed after confirmation;
- a rubric is mentioned but unresolved;
- the requested citation style is unknown and no raw citation export was
  accepted;
- a remote source would require access not explicitly granted;
- context reduction would remove confirmed source or output bindings.

## 13. GUI Design

### 13.1 Writing workspace

Add a renderer-neutral writing projection and a GUI workspace with:

- writing project summary;
- exact request and confirmation status;
- source library;
- task and rubric view;
- outline and claim inventory;
- argument topology;
- concept map;
- draft editor or read-only candidate preview;
- citation and reference audit;
- unresolved gaps;
- evidence and approval status.

### 13.2 Page-aware source reader

The source reader should display:

- physical page and printed page label;
- rendered page image when an approved PDF renderer is available;
- extracted text beside the page;
- selected quote highlight;
- bounding boxes or quads;
- prefix and suffix context;
- extraction/OCR confidence;
- source artifact hash;
- citation metadata and conflicts;
- concept and reasoning annotations for the selected span.

No PDF JavaScript, embedded files, launch actions, or arbitrary links should be
executed by the preview.

### 13.3 Reference inspector

For a draft citation, show:

```text
draft claim
  -> citation use
  -> paraphrase or quotation record
  -> exact source span
  -> page and geometry
  -> bibliographic record
  -> concept annotations
  -> reasoning annotations
  -> verification findings
```

The user must be able to navigate from draft text to source page and back
without losing the exact anchor identity.

## 14. Multi-Phase Implementation Roadmap

### Phase 0: Baseline Freeze and Requirement Audit

**Dependencies:** None.

**Work:**

1. Record the current source snapshot and dirty-worktree boundary.
2. Run focused tests for `formal_writing.py`, writing-mode CLI behavior, ICPI
   context parsing, routing, confirmations, and GUI prompt projection.
3. Record current public imports and CLI examples as compatibility fixtures.
4. Create requirement IDs from this plan and map each to an owner, test class,
   artifact, and release gate.
5. Separate existing unrelated generated-document changes from this work.

**Evidence:**

- baseline test log;
- public API inventory;
- CLI compatibility fixture;
- requirement-to-evidence matrix;
- source snapshot manifest.

**Pass gate:**

```text
current behavior is reproducibly recorded before formal-writing changes begin
```

### Phase 1: Versioned Contracts and Compatibility Facade

**Dependencies:** Phase 0.

**Work:**

1. Add immutable dataclasses for the contracts in Section 8.
2. Add explicit `schema_version`, `to_dict`, `from_dict`, validation, and
   canonical signatures.
3. Add JSON Schemas under `schemas/formal_writing/`.
4. Add structured-output grammars for local model responses.
5. Preserve existing `ArgumentNode`, `ArgumentEdge`, `ArgumentTopology`,
   profiles, and helper imports through `ourd/formal_writing.py`.
6. Decide whether existing argument types remain canonical or become aliases to
   versioned internal types; prove behavior either way.
7. Reject unknown schema versions and non-canonical identifiers.

**Tests:**

- round-trip serialization;
- canonical-signature determinism;
- invalid enum and missing-field rejection;
- unknown-version rejection;
- current import compatibility;
- existing topology validation unchanged.

**Pass gate:**

```text
identical semantic records -> identical signatures, and all legacy imports pass
```

### Phase 2: Source Registry and Artifact Identity

**Dependencies:** Phase 1.

**Work:**

1. Implement `SourceRegistry` over content-addressed source manifests.
2. Fingerprint exact bytes before extraction.
3. Detect path changes, content changes, duplicates, and related editions.
4. Store media type, byte size, provenance, access note, and extraction status.
5. Reuse a prior extraction only when content hash, adapter version,
   normalization profile, and configuration match.
6. Define source registration, refresh, and retirement semantics.
7. Keep caches and derived indexes rebuildable from source manifests.

**Tests:**

- same bytes at two paths produce one artifact identity;
- changed bytes invalidate page anchors;
- stale adapter versions trigger re-extraction;
- source retirement does not silently rewrite historical citations;
- malformed or unsupported files fail closed.

**Pass gate:**

```text
no locator or citation survives an unacknowledged source-content change
```

### Phase 3: Born-Digital PDF Extraction

**Dependencies:** Phase 2.

**Work:**

1. Add an optional PDF extra rather than increasing the base dependency set.
2. Implement page count, dimensions, rotation, blocks, lines, words, and
   bounding boxes through the selected PDF adapter.
3. Preserve source extraction order and add a separately derived reading order.
4. Store deterministic page-text and page-structure hashes.
5. Detect empty or near-empty text layers.
6. Handle multi-column text, footnotes, headers, footers, tables, ligatures,
   hyphenation, and rotated pages without silently discarding original data.
7. Provide page rendering only through a bounded preview adapter.

**Tests:**

- deterministic synthetic PDFs with known words and boxes;
- two-column ordering fixture;
- repeated header/footer fixture;
- rotated-page fixture;
- ligature and dehyphenation fixture;
- table and footnote fixture;
- encrypted or malformed PDF rejection.

**Pass gate:**

```text
golden born-digital fixtures reproduce exact page, text, and geometry records
```

### Phase 4: OCR Fallback and Page-Label Mapping

**Dependencies:** Phase 3.

**Work:**

1. Detect scanned or unusable text layers deterministically.
2. Require `--allow-ocr`, request policy, or explicit ICPI confirmation before
   OCR work.
3. Add an OCR adapter that creates or reads a searchable text layer while
   preserving the original artifact identity and OCR-derived artifact identity.
4. Store engine version, language, confidence, DPI, and transformation log.
5. Extract PDF page labels and distinguish them from physical positions.
6. Support Roman-numeral front matter and discontinuous printed numbering.
7. Mark low-confidence OCR spans as review-required.

**Tests:**

- scanned synthetic page fixture;
- mixed scanned/born-digital PDF;
- Roman-numeral front matter;
- omitted and duplicated printed page numbers;
- skewed and low-resolution scan;
- unsupported OCR language;
- OCR disabled fail-closed behavior.

**Pass gate:**

```text
OCR-derived locators are never presented as native text and page labels are not inferred
```

### Phase 5: Stable Text and Geometry Anchors

**Dependencies:** Phases 3-4.

**Work:**

1. Implement exact quote, prefix/suffix, position, page, and geometry selectors.
2. Compose selectors so one selector can refine another.
3. Add named normalization profiles and transformation logs.
4. Implement anchor creation from user selection, quote fragment, offsets, or
   page geometry.
5. Implement anchor resolution against the exact source artifact.
6. Reject ambiguous matches unless context or geometry resolves them.
7. Support multi-page spans.

**Tests:**

- exact quote round trip;
- repeated quote disambiguation by prefix/suffix;
- offset and quote selector agreement;
- geometry and text agreement;
- multi-page quote;
- normalization-profile drift;
- stale hash rejection.

**Pass gate:**

```text
every accepted TEXT or GEOMETRY anchor resolves uniquely on the exact source snapshot
```

### Phase 6: Bibliographic Metadata and Citation Records

**Dependencies:** Phase 2.

**Work:**

1. Parse embedded metadata and title-page candidates without treating them as
   automatically authoritative.
2. Store CSL-compatible citation items.
3. Add optional DOI lookup and Crossref metadata reconciliation.
4. Record field-level provenance and conflicts.
5. Add user correction and exact confirmation for unresolved conflicts.
6. Store edition and source-artifact relationships.
7. Define citation-key stability and collision handling.

**Tests:**

- embedded metadata only;
- DOI reconciliation;
- title or author conflict;
- multiple editions;
- missing date and missing author;
- offline behavior;
- metadata service failure without data fabrication.

**Pass gate:**

```text
every rendered bibliographic field is present with provenance or explicitly unresolved
```

### Phase 7: Passage Index and Reference Location

**Dependencies:** Phases 5-6.

**Work:**

1. Build deterministic lexical indexes over sentences, paragraphs, headings,
   and page text.
2. Add exact quote-fragment and normalized phrase search.
3. Add optional semantic embeddings as a reranker, not the sole retrieval path.
4. Return bounded candidate passages with page precision, context, and scores.
5. Build a `LOCATE_REFERENCE` service operation.
6. Add quote verification and highlight reconstruction.
7. Explain why a candidate matched and which selector resolved it.

**Tests:**

- exact phrase;
- fuzzy punctuation and line-break changes;
- repeated passage;
- conceptual query with no shared wording;
- negative query with no valid passage;
- stable ranking for identical inputs;
- bounded output and context limits.

**Pass gate:**

```text
accepted locator results point to verifiable source text and never invent a page
```

### Phase 8: Paraphrase and Synthesis Alignment

**Dependencies:** Phase 7.

**Work:**

1. Classify quotation, close paraphrase, paraphrase, summary, synthesis, and
   writer inference.
2. Bind each draft span to one or more source spans.
3. Compute lexical overlap and patchwriting risk.
4. Add advisory semantic support and contradiction checks.
5. Add deterministic checks for negation, qualifiers, modality, numerical
   values, population, time, scope, and causal language.
6. Detect unsupported clauses in otherwise supported sentences.
7. Require explicit writer-inference labeling when the source does not directly
   state the draft conclusion.

**Tests:**

- faithful paraphrase;
- close patchwriting;
- omitted qualifier;
- polarity reversal;
- correlation-to-causation inflation;
- numerical distortion;
- unsupported synthesis;
- valid multi-source synthesis;
- source contradiction.

**Pass gate:**

```text
known adversarial paraphrases cannot receive VERIFIED status on the qualification set
```

### Phase 9: Concept Identification

**Dependencies:** Phase 7.

**Work:**

1. Create a project-local concept registry with aliases and definitions.
2. Extract candidate terms, definitions, and concept mentions from source spans.
3. Distinguish explicit source concepts from inferred organizing concepts.
4. Link broader, narrower, and related concepts.
5. Add concept coverage and concept-conflict reports across sources.
6. Allow human acceptance, correction, merging, and rejection of proposals.
7. Keep model suggestions advisory and provenance-bound.

**Tests:**

- explicit definition extraction;
- synonym and alias mapping;
- homonym separation;
- competing definitions across sources;
- inferred-concept labeling;
- deterministic registry signatures;
- review-state transitions.

**Pass gate:**

```text
every accepted concept annotation identifies its source span and review provenance
```

### Phase 10: Reasoning Identification and Argument Topology

**Dependencies:** Phases 8-9.

**Work:**

1. Propose component roles for claims, premises, evidence, warrants,
   counterclaims, rebuttals, qualifiers, limitations, and implications.
2. Propose relations for support, warrant, attack, rebuttal, qualification,
   limitation, entailment, and dependence.
3. Identify inference modes such as deductive, inductive, abductive, causal,
   analogical, authority-based, and defeasible.
4. Record implicit premises separately from explicit source text.
5. Bind evidence nodes to typed `ReferenceSpan` identifiers.
6. Preserve existing positive-graph acyclicity and counterclaim-response rules.
7. Keep `ourd/reasoning/topology.py` and formal argument topology as distinct
   domain owners; add adapters rather than conflating their schemas.
8. Generate a human-readable reasoning explanation for every accepted edge.

**Tests:**

- linked and convergent premises;
- circular support rejection;
- unsupported evidence node rejection;
- rebutting versus undercutting response;
- qualifier and limitation placement;
- implicit-premise disclosure;
- source-to-topology traceability;
- separation from the general reasoning topology owner.

**Pass gate:**

```text
every accepted evidence-bearing argument node traces to a verified source span
```

### Phase 11: Formal Writing Request Compiler and Planner

**Dependencies:** Phases 1, 6, 9, and 10.

**Work:**

1. Implement `FormalWritingRequest` validation.
2. Parse task, audience, discipline, genre, word target, profile, citation style,
   rubric, source roles, output roles, and constraints.
3. Analyze rubrics as untrusted sources and extract candidate requirements.
4. Create a source map and evidence-gap analysis.
5. Create thesis, claims, section plan, paragraph roles, concept coverage,
   counterargument plan, and citation allocation.
6. Validate the resulting argument topology.
7. Sign the exact plan and bind it to the request and source hashes.

**Tests:**

- scientific essay plan;
- argumentative essay plan;
- general formal document plan;
- rubric conflict with generic profile;
- missing evidence gap;
- word-budget allocation;
- plan signature determinism;
- plan invalidation after source or request change.

**Pass gate:**

```text
no drafting begins until a validated, source-bound FormalWritingPlan exists
```

### Phase 12: Grounded Drafting and Revision Engine

**Dependencies:** Phase 11.

**Work:**

1. Draft section-by-section from bounded plan and source packets.
2. Require structured model output for claims, draft text, citation uses, and
   referenced span IDs.
3. Reject citation identifiers not present in the supplied source packet.
4. Run reference integrity checks after each section.
5. Preserve requested thesis and constraints during revision.
6. Support targeted revision for unsupported claim, weak warrant, missing
   counterargument, poor synthesis, excessive quotation, or style problem.
7. Assemble the whole draft only from validated section artifacts.
8. Record model, prompt, context, plan, source, and output signatures.

**Tests:**

- structured-output rejection and retry limits;
- nonexistent source-span rejection;
- section context isolation;
- thesis preservation;
- unsupported claim repair;
- citation carry-through;
- deterministic assembly from fixed section artifacts;
- no hidden mutation.

**Pass gate:**

```text
every evidence-bearing draft claim has a citation use or an explicit unresolved gap
```

### Phase 13: Citation Rendering and Reference Integrity Gate

**Dependencies:** Phases 6, 8, and 12.

**Work:**

1. Add a CSL-compatible citation-renderer adapter.
2. Support in-text citations, notes where configured, locators, page ranges,
   and bibliographies.
3. Separate citation data from presentation style.
4. Validate every quotation against its exact anchor.
5. Validate every paraphrase link and source hash.
6. Detect uncited evidence claims and unused bibliography entries.
7. Emit `ReferenceIntegrityReport` and machine-readable findings.
8. Block `reference_integrity=PASS` while unresolved high-severity findings
   exist.

**Tests:**

- style switch without changing source data;
- page and page-range rendering;
- quote mismatch;
- stale anchor;
- missing bibliography record;
- uncited claim;
- unused reference;
- unresolved metadata conflict;
- deterministic report signature.

**Pass gate:**

```text
PASS requires zero fabricated, stale, contradicted, or unresolved required references
```

### Phase 14: Shared `FormalWritingService`

**Dependencies:** Phases 7-13.

**Work:**

1. Implement one typed service for all formal-writing operations.
2. Separate pure read operations from candidate-producing operations.
3. Return typed results and bounded user projections.
4. Add cancellation, budget, context, and progress events.
5. Add deterministic error codes and no-blind-retry behavior.
6. Expose service methods through `ourd/formal_writing.py` only after stable.
7. Ensure adapters cannot broaden policy or source scope.

**Tests:**

- every operation through direct service API;
- cancellation at each major stage;
- deterministic errors;
- context-budget failure before provider transport;
- no duplicate source indexing;
- read-only operations cause no user-file mutation.

**Pass gate:**

```text
CLI, ICPI, GUI, and compatibility mode can share one service without semantic forks
```

### Phase 15: Dedicated CLI and Compatibility Integration

**Dependencies:** Phase 14.

**Work:**

1. Add `ourd/formal_writing_cli.py` and the console script.
2. Implement command groups and shared flags from Section 11.
3. Provide human-readable and canonical JSON output.
4. Map mutating commands to `scoped_write_authority` and existing governed
   candidate processing.
5. Compile compatible existing `--write` requests into the new request schema
   when advanced formal-writing fields are present.
6. Preserve old prompt-only behavior behind a documented compatibility path
   until deprecation criteria are met.
7. Add exit codes for validation, unresolved sources, reference failures,
   approval denial, apply failure, and verification failure.

**Tests:**

- CLI parser matrix;
- help text snapshots;
- JSON schema output;
- read-only no-write behavior;
- exact authority paths;
- existing `--write` tests;
- shell-level smoke tests;
- packaging entry-point test.

**Pass gate:**

```text
the dedicated CLI and existing --write path produce equivalent typed requests for equivalent inputs
```

### Phase 16: ICPI Natural-Language Interface

**Dependencies:** Phases 14-15.

**Work:**

1. Extend context reference kinds with source, source-folder, rubric, output,
   draft, and style roles.
2. Add formal-writing domain detection and entity extraction.
3. Compile natural language into `FormalWritingRequest`.
4. Add deterministic slash commands.
5. Add route targets and user-facing route previews.
6. Add exact confirmation summaries for mutating requests.
7. Create bounded write authority only after exact confirmation.
8. Bind confirmation to source hashes, source/output roles, constraints, and
   context-envelope signature.
9. Reconfirm whenever the source set, source hashes, rubric, output, citation
   style, OCR policy, network policy, or request meaning changes.
10. Shorten chat activity display to important milestones while retaining full
    structured event detail in the activity inspector.

**Tests:**

- natural-language examples from Section 12;
- source/output role ambiguity;
- prospective output path;
- unresolved source;
- no-page source with page requirement;
- mutation confirmation;
- source drift after confirmation;
- slash/free-language request equivalence;
- concise activity projection without evidence loss;
- context-reduction preservation of confirmed bindings.

**Pass gate:**

```text
natural language never grants authority and every mutating request is exactly reconfirmable
```

### Phase 17: GUI Source Reader and Writing Workspace

**Dependencies:** Phase 16.

**Work:**

1. Add renderer-neutral writing projections.
2. Add source library and ingestion status.
3. Add safe PDF page rendering and extracted-text view.
4. Add quote and geometry highlighting.
5. Add concept and reasoning panels.
6. Add draft-to-source navigation.
7. Add reference-integrity findings with severity and repair actions.
8. Add exact candidate, diff, evidence, approval, and apply views through the
   existing GUI governance boundary.
9. Keep full event records available while the chat screen shows only important
   progress milestones.

**Tests:**

- projection determinism;
- page navigation;
- anchor highlight accuracy;
- OCR warning display;
- source hash display;
- draft-to-source trace;
- safe PDF behavior;
- GUI thread isolation;
- no direct file writes from views.

**Pass gate:**

```text
a user can inspect every draft citation on its exact source page before approval
```

### Phase 18: Security, Privacy, Copyright, and Reliability Hardening

**Dependencies:** Phases 14-17.

**Work:**

1. Treat all document text and metadata as untrusted data.
2. Reject path traversal, unsupported schemes, unsafe PDF actions, and oversized
   decompression or extraction workloads.
3. Add file-size, page-count, OCR-time, embedding, provider-token, and output
   budgets.
4. Default to local/offline operation; enable metadata or document retrieval
   only through explicit configured capabilities.
5. Do not bypass paywalls or access controls.
6. Limit chat and report excerpts from copyrighted sources; preserve full text
   only in authorized local indexes.
7. Redact secrets and sensitive metadata from prompts and reports.
8. Add cancellation, crash recovery, partial-index cleanup, and atomic artifact
   replacement.
9. Validate external tool versions and record them in provenance.

**Tests:**

- prompt injection in PDF text;
- path traversal;
- malformed and oversized PDF;
- decompression bomb defenses;
- unauthorized network request;
- secret-like text projection;
- OCR timeout;
- interrupted index build;
- stale temporary artifact cleanup.

**Pass gate:**

```text
untrusted sources cannot alter authority, tools, instructions, or output scope
```

### Phase 19: Benchmarks and Adversarial Qualification

**Dependencies:** Phases 8, 10, 13, and 18.

**Work:**

1. Build deterministic golden fixtures with known page labels, text, offsets,
   and geometry.
2. Build separate development and holdout sets for paraphrase and reasoning
   classification.
3. Add adversarial cases for source drift, conflicting editions, repeated
   quotes, OCR noise, omitted qualifiers, contradiction, and fabricated
   citations.
4. Measure deterministic subsystems separately from advisory model subsystems.
5. Freeze thresholds before holdout qualification.
6. Record model, runtime, prompt, grammar, source, and benchmark hashes.
7. Require human review for page highlights and reasoning labels on a sampled
   qualification set.

**Metrics:**

```text
source identity collision count
physical page accuracy
display page-label accuracy
exact quote round-trip rate
anchor unique-resolution rate
geometry overlap on golden boxes
metadata field precision and unresolved rate
paraphrase support precision
contradiction detection recall
qualifier-preservation detection
patchwriting detection
argument component precision/recall
argument relation precision/recall
citation completeness
fabricated citation count
stale-reference detection rate
```

**Minimum deterministic gates:**

```text
golden source hash identity: 100%
golden physical page accuracy: 100%
golden exact quote round trip: 100%
golden stale-source rejection: 100%
golden fabricated citation acceptance: 0
golden unauthorized mutation count: 0
```

Model-quality thresholds must be selected from development evidence and frozen
before holdout execution. A focused green subset cannot establish release
qualification.

**Pass gate:**

```text
all frozen deterministic gates pass and advisory quality meets predeclared holdout thresholds
```

### Phase 20: Migration, Documentation, Packaging, and Release Audit

**Dependencies:** Phases 0-19.

**Work:**

1. Document the new CLI, ICPI syntax, schemas, source identity, page semantics,
   OCR warnings, citation integrity, and governance boundaries.
2. Update `docs/WRITING_MODE.md` without removing existing compatibility
   examples.
3. Extend `docs/FORMAL_WRITING_RESEARCH.md` with page anchoring, paraphrase,
   concept, reasoning, and citation-engine design sources.
4. Add migration guidance for existing `ArgumentTopology.source_refs` strings.
5. Add optional dependency extras for PDF, OCR, citations, and semantic search.
6. Validate clean installation with no extras and each supported extra set.
7. Run focused tests, full test discovery, packaging, CLI smoke tests, GUI
   headless tests, benchmark qualification, and requirement audit.
8. Record exact source, wheel, schema, grammar, fixture, benchmark, and report
   hashes.
9. Obtain exact human approval for the release candidate.
10. Verify rollback from the release candidate to the previous compatible
    writing mode.

**Pass gate:**

```text
every requirement has current exact-snapshot evidence, all release gates pass,
and human approval binds the exact candidate and validation hashes
```

## 15. Test Fixture Inventory

The qualification corpus should include at least:

1. one-page born-digital PDF;
2. multi-page born-digital PDF;
3. Roman-numeral front matter followed by Arabic numbering;
4. page labels that differ from physical page positions;
5. two-column academic layout;
6. repeated headers and footers;
7. footnotes and endnotes;
8. tables and captions;
9. hyphenated line breaks;
10. ligatures and Unicode normalization;
11. rotated page;
12. quote spanning two pages;
13. scanned PDF with accurate OCR;
14. scanned PDF with deliberately poor OCR;
15. mixed native and scanned pages;
16. two editions with similar text and different pagination;
17. duplicate exact quote appearing on several pages;
18. reflowable HTML without stable pages;
19. stable rendered PDF derived from reflowable input;
20. source containing prompt-injection text;
21. faithful paraphrase;
22. patchwriting paraphrase;
23. omitted qualifier;
24. negation reversal;
25. correlation-to-causation inflation;
26. unsupported multi-source synthesis;
27. conflicting source claims;
28. implicit premise and explicit premise pair;
29. rebutting and undercutting counterarguments;
30. fabricated bibliography entry and fabricated page locator.

All deterministic fixtures should be generated or stored with explicit license
and provenance. Fixture changes require new hashes and qualification evidence.

## 16. Requirement-to-Evidence Matrix

| ID | Requirement | Primary phase | Required evidence |
| --- | --- | --- | --- |
| FW-001 | Preserve current formal-writing imports and profiles | 0-1 | compatibility tests and API inventory |
| FW-002 | Exact source artifact identity | 2 | hash and invalidation tests |
| FW-003 | Physical and displayed page distinction | 4 | page-label golden fixtures |
| FW-004 | Exact text and geometry anchors | 5 | quote round-trip and geometry tests |
| FW-005 | Page-aware passage location | 7 | locator benchmark |
| FW-006 | Grounded paraphrase with distortion checks | 8 | adversarial paraphrase benchmark |
| FW-007 | Concept identification with provenance | 9 | concept fixtures and review-state tests |
| FW-008 | Reasoning identification with provenance | 10 | argument-mining fixtures and topology tests |
| FW-009 | Source-bound formal-writing plan | 11 | deterministic plan artifacts |
| FW-010 | Grounded draft and revision | 12 | structured draft and repair tests |
| FW-011 | CSL-compatible citations and bibliography | 6 and 13 | style and locator rendering tests |
| FW-012 | Reference integrity report | 13 | signed reports and negative fixtures |
| FW-013 | Shared service for all surfaces | 14 | cross-surface equivalence tests |
| FW-014 | Dedicated formal-writing CLI | 15 | parser, smoke, and packaging tests |
| FW-015 | Natural-language ICPI | 16 | interpretation and confirmation matrix |
| FW-016 | Exact governed write path | 15-17 | authority, candidate, EON, approval, apply evidence |
| FW-017 | Page-aware GUI inspection | 17 | headless tests and human visual review |
| FW-018 | Untrusted-document isolation | 18 | security adversarial suite |
| FW-019 | No fabricated citations or pages | 13 and 19 | zero-acceptance golden gate |
| FW-020 | Complete release evidence and rollback | 20 | qualification bundle and rollback proof |

## 17. Dependency Strategy

The base installation should remain dependency-light. Add optional extras with
clear capability detection, for example:

```text
writing-pdf       PDF extraction and page rendering
writing-ocr       OCR pipeline integration
writing-citations CSL rendering adapter
writing-semantic  embedding-based retrieval and advisory similarity
writing-all       supported combined formal-writing stack
```

Exact libraries and version bounds must be selected during implementation from
verified compatibility evidence, then locked and recorded. Missing optional
dependencies must produce clear capability errors, not degraded claims of page
accuracy.

GROBID, Crossref, OCR engines, and model providers should be adapters with
explicit health checks and policy. The engine must remain useful for local
born-digital PDFs without requiring a network service.

## 18. Model Use Policy

Models may propose:

- passage candidates;
- paraphrases;
- concepts;
- reasoning roles and relations;
- outlines;
- draft prose;
- critique and repairs.

Models may not authoritatively determine:

- exact source identity;
- page number or page label;
- exact quotation text;
- source hash;
- geometry;
- citation metadata when absent;
- authority scope;
- approval;
- final reference-integrity verdict;
- release qualification.

Deterministic extraction, schemas, signatures, rule checks, golden fixtures,
human review, and the existing governed mutation path remain authoritative.

## 19. Risk Register

| Risk | Consequence | Mitigation |
| --- | --- | --- |
| PDF reading order differs from visual order | Incorrect quote context | Preserve original extraction, derive reading order separately, require geometry review |
| Printed page differs from physical page | Incorrect citation locator | Store both values and never infer display label |
| OCR introduces plausible errors | False quotation or paraphrase | Mark OCR provenance, confidence, and review requirement; compare page image |
| Source edition changes | Stale page and quote anchors | Bind all anchors to content hash and invalidate on drift |
| Semantic similarity accepts contradiction | Unsupported paraphrase | Use similarity only for retrieval; add polarity, qualifier, scope, and contradiction checks |
| Patchwriting passes as paraphrase | Academic-integrity risk | Lexical overlap and phrase-reuse analysis plus user-visible warning |
| Metadata API returns wrong work | Incorrect bibliography | Field provenance, DOI verification, conflict display, human correction |
| Model invents source IDs | Fabricated support | Structured output constrained to supplied identifiers and deterministic rejection |
| Argument roles are overconfident | Misleading reasoning map | Confidence, explicit/inferred distinction, human review, benchmark thresholds |
| ICPI infers wrong output path | Unauthorized mutation | Explicit role syntax, ambiguity gate, exact confirmation, scoped authority |
| Source document contains instructions | Prompt injection | Treat document content as quoted untrusted data and isolate it from instructions |
| Large source library exceeds context | Missing or distorted grounding | Indexed retrieval, bounded source packets, context-budget checks, no silent truncation |
| External service unavailable | Blocked workflow | Offline-first adapters, deterministic capability errors, cached provenance-bound metadata |
| GUI highlight differs from stored anchor | False visual assurance | Projection tests plus sampled human visual qualification |

## 20. Definition of Done

The formal-writing engine is complete only when all of the following are true:

1. Current writing profiles and `ArgumentTopology` compatibility tests pass.
2. Source documents are fingerprinted and versioned.
3. Born-digital PDF fixtures produce exact page, text, and geometry anchors.
4. OCR fixtures disclose OCR provenance and confidence.
5. Physical pages and displayed page labels are distinct and tested.
6. Every accepted quotation round-trips to exact source text.
7. Every accepted paraphrase traces to source spans and passes the declared
   integrity rules.
8. Concept and reasoning annotations include source and review provenance.
9. Argument topology evidence nodes resolve to typed source spans.
10. Citation rendering uses provenance-bearing bibliographic records.
11. Reference-integrity reports reject fabricated, stale, contradicted, and
    unresolved required references.
12. The dedicated CLI is packaged and smoke-tested.
13. Free-language ICPI and slash commands compile equivalent requests.
14. Mutating ICPI and CLI paths use exact confirmation and existing scoped
    authority.
15. The GUI can navigate from draft citation to exact source page and text.
16. Security tests prove that document content cannot modify authority or tool
    behavior.
17. Focused tests, full discovery, packaging, headless GUI tests, benchmark
    qualification, and the requirement audit all pass on one frozen snapshot.
18. Exact source, artifact, schema, grammar, fixture, benchmark, and report
    hashes are recorded.
19. Human visual review approves sampled page highlights and reasoning traces.
20. Exact human approval binds the final candidate and validation evidence.

Focused subsystem success is not sufficient for a completion or release claim.

## 21. Recommended Delivery Slices

To reduce integration risk, deliver the phases in four reviewable slices:

### Slice A: Verifiable References

Phases 0-7. Deliver source identity, PDF/OCR extraction, page labels, anchors,
metadata, and page-aware lookup before any drafting automation.

### Slice B: Meaning and Argument

Phases 8-10. Deliver paraphrase integrity, concepts, reasoning roles, and
source-bound argument topology.

### Slice C: Writing Engine and Interfaces

Phases 11-17. Deliver planning, drafting, integrity gating, service API, CLI,
ICPI, and GUI.

### Slice D: Qualification and Release

Phases 18-20. Deliver security hardening, benchmark qualification, migration,
packaging, complete evidence audit, approval, and rollback.

Each slice requires its own exact-snapshot review. Later slices must not weaken
the verified guarantees of earlier slices.
