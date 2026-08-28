# OIEC-STM-Agent Documentation Relational Tree Refactor Plan

**Plan date:** August 28, 2026
**Canonical generator:** `tools/build_docs_site.py`
**Generated entry point:** `docs/index.html`

## Objective

Refactor the generated documentation index into an interactive systems-
architecture explorer. Preserve the purple-and-white 1980s pixel identity while
making the information hierarchy clearer, faster to navigate, and explicitly
relational. Every invariant unique object represented by the tree must have one
stable identity, one deterministic SVG symbol, and machine-checkable relation
metadata.

## Baseline Inventory

The source-derived baseline contains:

- 1 documentation-system root;
- 6 architecture categories;
- 1 nested source folder;
- 18 Markdown documents;
- 105 heading lessons; and
- 136 source-derived concepts.

The initial expected relational universe therefore contains 267 objects. The
generator must derive this count from source rather than freeze it as a magic
number.

## Relational Object Contract

Each object will contain:

- a stable `object_id` derived from semantic kind and source identity;
- a kind from `root`, `category`, `folder`, `document`, `heading`, or `concept`;
- a human-readable title and description;
- a canonical parent object, except for the root;
- a relation label describing its edge to the parent;
- a stable navigation target;
- a deterministic symbol path; and
- a source key suitable for audit and reconstruction.

The following invariants apply:

1. Object IDs are unique and independent of iteration order.
2. Every non-root parent ID resolves to exactly one object.
3. Every object has exactly one standalone `.svg` symbol.
4. Every symbol embeds the matching object ID, kind, title, and relation.
5. Every generated tree row refers to a manifest object and symbol.
6. The manifest contains the complete object universe and relation edges.
7. Rebuilding unchanged source produces byte-identical relational artifacts.
8. Search, filtering, selection, and relation inspection work without granting
   authority or mutating source documents.

## Visual Redesign

The index becomes a systems-architecture command deck with:

- a compact status rail for scope, evidence, state, and navigation counts;
- a hero that explains the governed loop without obscuring the tree;
- an interactive topology viewport for categories and system relationships;
- a two-pane relational explorer with tree controls and a sticky object
  inspector;
- kind filters, text search, parent/child highlighting, and keyboard access;
- SVG symbols in every tree row and a larger interactive symbol in the
  inspector; and
- responsive layouts that preserve legibility on narrow screens and respect
  reduced-motion preferences.

## Implementation Phases

1. Add the relational object model and deterministic inventory builder.
2. Add deterministic symbol geometry and standalone SVG generation.
3. Refactor the index template around the relational explorer.
4. Replace index-specific CSS with the command-deck visual system.
5. Add JavaScript selection, filtering, relation inspection, and symbol motion.
6. Extend the manifest and tests for full object and symbol coverage.
7. Rebuild twice, compare hashes, run syntax/accessibility-oriented checks, and
   audit every objective requirement.

## Issue Log

- No blocking issue at plan creation.
- The `.sgv` spelling in the objective is interpreted as `.svg`, the standard
  Scalable Vector Graphics extension.
- Existing document and concept figures are retained; relational symbols are a
  distinct identity layer rather than replacements for explanatory diagrams.
- The first build-integration patch encountered a context mismatch because the
  existing summary string wrapped differently than expected. The plan was
  adjusted to apply smaller generator patches and validate each integration
  boundary independently.
- The first generated relational index contained an indentation-only line
  before the explorer. The source template now left-strips the injected block,
  preserving the repository-wide no-trailing-whitespace invariant.
- Exhaustive SVG parsing found that the shared `data-symbol-core` attribute was
  emitted with HTML boolean syntax, which is invalid XML. The symbol generator
  now emits an explicit XML attribute value and regenerates every symbol.
- Firefox rendering at 430 pixels exposed hero text and pipeline overflow even
  though static HTML checks passed. The responsive phase now includes real
  desktop/mobile screenshots and explicit narrow-screen containment rules.
- After adding all symbols, bounded Firefox capture timed out because the first
  tree design requested 267 standalone SVG files at once. The plan now retains
  those files as auditable identities, adds one deterministic SVG sprite for
  tree rendering, and loads a standalone symbol only in the selected-object
  inspector.
- The sprite reduced the page to one shared symbol request, but the installed
  Firefox headless runtime still timed out on an `about:blank` control while its
  `glxtest` process saturated a core. Browser screenshot completion is therefore
  an environment limitation, not accepted as site evidence; structural HTML,
  local-asset, XML, JavaScript, responsive-CSS, and deterministic-build checks
  remain mandatory, and the earlier screenshot findings stay resolved in CSS.

## Completion Evidence

Completion requires source changes, generated artifacts, a manifest coverage
proof, deterministic rebuild equality, passing documentation tests, valid SVG
parsing, valid JavaScript syntax, HTML structure checks, and a manual
requirement-to-evidence audit. A visually plausible page alone is insufficient.

Implemented evidence on August 28, 2026:

- 267 relational objects and 460 closed relation records;
- 267 standalone SVG identities plus one shared relational symbol sprite;
- 156 generated HTML pages, 426 SVG artifacts, and 6,025 essay paragraphs;
- byte-identical repeated generation with docs tree SHA-256
  `f5aaa0f5685fe85fbe739285d2c53a461fa6c9047f378f002b52f49a8bc8158d`;
- 267 tree object IDs matched to 267 sprite references;
- zero duplicate HTML IDs, missing local assets, or nested interactive controls;
- JavaScript syntax and Git whitespace validation passed; and
- all 239 repository unit tests passed in 873.978 seconds.

Headless Firefox screenshot capture remains unavailable because the installed
runtime also hangs on `about:blank`; this is recorded as an environment
limitation rather than represented as successful browser evidence.
