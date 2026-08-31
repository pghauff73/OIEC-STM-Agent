# OIEC-STM-Agent Formal Writing Website

This directory contains a self-contained, source-derived website that translates
the OIEC-STM-Agent Markdown corpus into a formal argument.

## Entry point

Open [`index.html`](index.html).

When the repository is published from the `docs/` directory with GitHub Pages,
the site is available under the `/formal-writing/` path.

## Editorial contract

The website applies the repository's own Formal Writing rules:

1. define one central thesis;
2. distinguish claims, evidence, and warrants;
3. synthesise sources by issue rather than summarising them one at a time;
4. include and answer a material counterclaim;
5. separate implemented source, dated validation, open plans, and editorial
   synthesis;
6. calibrate certainty and preserve explicit limits; and
7. identify every primary and external source.

The central thesis is:

> Reasoning may propose an action; only governed evidence and external authority
> may permit it.

This thesis is an interpretation of the repository architecture. It is not a
claim that OIEC-STM-Agent is flawless, certified, generally superior, or able to
make its own output authoritative.

## Source hierarchy

The evidence hierarchy is recorded in
[`source-manifest.json`](source-manifest.json).

- **Project sources** establish repository-declared architecture,
  implementation, terminology, status, and limitations.
- **Formal-writing sources** establish the academic and scientific writing
  method.
- **Engineering sources** establish lifecycle, trustworthiness, requirement
  language, and accessibility principles.
- **Editorial synthesis** is labelled explicitly and never presented as a
  verbatim runtime API.

The website is based on Git commit
`d82969ac152281394423d30063a87d4de0f8889b`.

## Site structure

```text
docs/formal-writing/
├── index.html
├── README.md
├── source-manifest.json
├── assets/
│   ├── formal.css
│   └── formal.js
└── figures/
    ├── governed-pipeline.svg
    ├── argument-topology.svg
    └── evidence-boundary.svg
```

The site has no runtime package dependency, remote script, tracking code,
provider call, command execution path, or workspace mutation capability.
JavaScript is limited to colour-theme selection, source filtering, active
navigation, and local copy assistance.

## Validation

Run:

```bash
python3 -m unittest -v tests.test_formal_writing_site
```

The test checks:

- required site artifacts;
- a single top-level heading and unique element IDs;
- internal link resolution;
- source-manifest identities and project-source blob hashes;
- claim-to-source bindings;
- accessible SVG titles and descriptions;
- absence of remote scripts and stylesheets;
- absence of placeholder prose; and
- bounded browser JavaScript without network or dynamic-code APIs.

## Updating the website

1. Re-read every project source used by a changed claim.
2. Update the base commit and any changed Git blob SHA values.
3. Reclassify dated validation and open work rather than silently treating an
   old report as current.
4. Update the source register and claim bindings.
5. Run the focused test.
6. Review the rendered page in light, dark, narrow, keyboard-only, reduced-motion,
   and print modes.
