# OIEC-STM-Agent Beginner Essay Rewrite Plan

**Plan date:** August 28, 2026
**Canonical generator:** `tools/build_docs_site.py`
**Generated scope:** every HTML page under `docs/`

## Objective

Rewrite the complete generated documentation tree so every lesson and concept
essay begins with a claim that must be proved, defines specialist language for
a reader with no prior knowledge, explains each paragraph's topic directly,
uses clearly relevant references through paraphrase, and ends with a decisive
winning position.

## Requirements

1. Regenerate every document, concept, atlas, and index HTML page from the
   canonical generator rather than hand-editing generated output.
2. Remove essay narration that calls text an introduction, body, body movement,
   body section, or conclusion.
3. Preserve five groups of five paragraphs for each source heading and concept,
   while naming the groups by argumentative purpose.
4. Explain every detected acronym and project-specific abbreviation, including
   an explicit fail-closed explanation when the source does not provide an
   expansion.
5. Explain common architecture terms such as authority, canonical state,
   deterministic behaviour, evidence, provenance, rollback, schema, and
   verification in beginner wording when they occur.
6. Match external references to the actual topic using deterministic keyword
   rules and cite only references rendered on the same page.
7. Paraphrase external guidance rather than copying passages.
8. Make the final paragraph of every essay summarise the tested claim and name
   a clear winning position.
9. Bind all 25 paragraph topics to an explicit logic topology map that moves
   through claim, mechanism, proof, challenge, and winning position; each map
   node must navigate to exactly one paragraph.
10. Add tests that inspect every generated essay, every detected acronym, every
   citation target, and every final verdict.
11. Rebuild deterministically and run the full repository validation suite.

## Evidence Standard

Completion requires all generated HTML to be current, no forbidden structural
essay narration, closed citation links, beginner definitions for detected
specialist language, decisive final verdicts, byte-identical repeated builds,
focused documentation tests, and full repository tests.

## Completion Evidence

**Validation date:** August 30, 2026

- Regenerated 377 HTML pages, 1,369 interactive SVG figures, and 23,475 essay
  paragraphs from 606 Markdown headings and 333 concept records, with 989
  relational objects in the canonical inventory.
- Bound all 939 essays to a validated 25-node directed acyclic logic topology:
  claim, mechanism, proof, challenge, and winning position. Each paragraph now
  records its global topological order, topic, predecessor, and successor.
- Verified every logic node targets exactly one paragraph and every paragraph
  belongs to exactly one topology node. The manifest records the 24 directed
  edges joining the 25 paragraph topics.
- Verified zero forbidden structural paragraph labels and zero unexplained
  detected source acronyms.
- Verified every essay page uses topic-matched references with closed local
  citation targets and a decisive final winning position.
- Verified every generated page has unique element IDs and every local link
  resolves to an existing file or anchor.
- Rebuilt the documentation twice from the same source and obtained an
  identical SHA-256 tree digest on both runs. The digest remains external to
  this generator input so recording it cannot invalidate itself.
- Passed 19 focused generated-documentation tests and the reasoning,
  hypothesis, model benchmark, OIEC, persistence, GUI, and packaging
  compatibility suites.
- Passed the complete repository suite: 606 tests with one optional OpenGL
  dependency skip.
- Passed JavaScript syntax validation with `node --check docs/assets/site.js`
  parsed all 1,369 SVG files as XML, and passed patch whitespace validation with
  `git diff --check`.

## Countered Issues

- Narrowed the forbidden-word audit after a broad expression incorrectly
  treated legitimate phrases such as “defensible conclusion” as structural
  paragraph narration.
- Added deterministic topic groups after keyword-only matching selected an
  accessibility reference for a migration topic; migration now selects
  transaction, snapshot, canonicalization, logging, and systems references.
- Replaced large context-sensitive patches with smaller patches when generated
  source context changed during the rewrite.
- Replaced a decorative paragraph-topic list with a validated directed graph,
  after the user clarified that paragraph topics must follow the logic topology
  itself. The JavaScript now marks the active and completed path.
- Corrected the final artifact audit to use the current
  `relational_objects` manifest field after an older audit key failed closed.

## Status

The complete generated documentation tree satisfies the beginner essay,
claim-and-evidence, topic-reference, decisive-verdict, and logic-topology
requirements. The evidence above establishes deterministic generation and
repository-wide regression safety for the current source state.
