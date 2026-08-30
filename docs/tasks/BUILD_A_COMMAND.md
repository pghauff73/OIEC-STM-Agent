# Build My Own Command

## Goal

Assemble an EGCF command from semantic parts and understand why each generated token is present.

## Learning route

Complete T06 EGCF.

## Command shape

```text
egcf namespace verb options
```

Use the browser Command Builder to select workspace, target, risk, explanation, graph, strictness, simulation, evidence, approval, and rollback. Generated commands are checked against the real parser catalog.

## Misconception to avoid

More flags are not automatically safer. Each modifier must express a real boundary or evidence requirement rather than decorative complexity.

## Safe completion condition

The command parses, its objective and inputs are explicit, incompatible choices are rejected, and dry-run or simulation is used before mutation when appropriate.
