# SAA Repository Brain Feeding CLI

`oiec-stm-agent brain feed repo` converts an arbitrary local source repository into bounded SAA brain-feed material without executing the repository.

The repository scanner is intentionally **static and read-only**. It never imports project modules, runs tests, invokes build scripts, installs dependencies, or treats the presence of code as proof that the code is correct.

```text
repository
   |
   v
static file inventory
   |
   +--> SHA-256 source evidence
   |
   +--> function/method candidates
   |
   +--> test experiment candidates
   |
   +--> assertion invariant candidates
   |
   +--> documentation/source material
   |
   v
ordinary SAA brain-feed batches
   |
   v
normal SAA qualification gates
```

The hard boundary remains:

```text
repository source exists
    !=
algorithm is correct
    !=
algorithm meaning is resolved
    !=
canonical algorithm admission
```

## Quick start

Feed another repository into the current OIEC workspace:

```bash
oiec-stm-agent brain feed repo /path/to/source-repository --repo .
```

Show detailed extraction information:

```bash
oiec-stm-agent brain feed repo /path/to/source-repository \
  --repo . \
  --verbose
```

Machine-readable output:

```bash
oiec-stm-agent brain feed repo /path/to/source-repository \
  --repo . \
  --json
```

Scan only, without changing SAA state:

```bash
oiec-stm-agent brain feed repo /path/to/source-repository \
  --scan-only \
  --json
```

`repo` and `feed-repo` remain compatibility aliases:

```bash
oiec-stm-agent brain repo /path/to/source-repository --repo .
oiec-stm-agent brain feed-repo /path/to/source-repository --repo .
```

## What happens to source code

For each eligible source file, the scanner computes a SHA-256 digest and creates a grounded `EVIDENCE` item describing the exact path and bytes that were inspected.

The evidence producer is deterministic:

```text
producer = deterministic-repository-static-scanner
method   = sha256-source-fingerprint
oracle   = sha256-file-content
```

This evidence supports a narrow fact:

> these exact bytes were present at this repository path during this scan.

It does **not** support claims such as:

- the implementation is mathematically correct;
- the implementation satisfies its documentation;
- the function is safe;
- a test passes;
- the variable names have the intended physical meaning;
- two implementations are equivalent.

Those claims still require later SAA evidence and qualification.

## Algorithm extraction

For supported languages, function-like symbols are converted to `ALGORITHM_CANDIDATE` feed items.

A candidate contains information such as:

```json
{
  "name": "calculate_drag",
  "inputs": ["density", "speed", "area"],
  "outputs": ["return_value"],
  "implementation": {
    "language": "Python",
    "path": "aero/drag.py",
    "qualified_name": "calculate_drag",
    "line_start": 12,
    "line_end": 25,
    "symbol_sha256": "...",
    "repository_signature": "..."
  },
  "meanings": {
    "status": "UNRESOLVED_FROM_SOURCE_CODE",
    "identifier_clues": ["area", "density", "drag", "speed"],
    "documentation": "...",
    "annotations": ["density:float", "return:float"]
  }
}
```

The important field is:

```text
meanings.status = UNRESOLVED_FROM_SOURCE_CODE
```

A variable called `speed` is a semantic clue, not proof that it represents translational speed, angular speed, network throughput, or something else.

The candidate is therefore staged as:

```text
STAGED_ALGORITHM_CANDIDATE_QUALIFICATION_REQUIRED
```

and never inserted directly into the Canonical Algorithm Store.

## Python extraction

Python receives the richest static extraction because the scanner can use Python's standard-library AST parser without importing the target repository.

It extracts:

- functions and async functions;
- nested qualified names;
- positional and keyword parameters;
- type annotations;
- return annotations;
- docstrings;
- called symbol names;
- source line boundaries;
- exact source-symbol SHA-256 digests;
- `assert` statements as invariant candidates.

Example:

```python
def kinetic_energy(mass: float, speed: float) -> float:
    """Return translational kinetic energy."""
    return 0.5 * mass * speed * speed
```

becomes a staged algorithm candidate with semantic clues such as `mass`, `speed`, `kinetic`, and `energy`.

Those clues are later material for SAA-9 semantic resolution. The repository scanner does not promote them to verified meanings.

## Other languages

The scanner includes conservative signature extraction for common source languages including Python, JavaScript, TypeScript, C, C++, C#, Java, Kotlin, Go, Rust, Swift, Ruby, PHP, shell scripts, R, MATLAB, Fortran, Julia, Lua, Perl, and SQL source recognition.

For languages where an exact parser is not built into OIEC, extraction is deliberately conservative and labelled:

```text
CONSERVATIVE_SIGNATURE_HEURISTIC
```

Unsupported or unparsed text is still useful. The file can be fingerprinted and staged as `SOURCE_DOCUMENT` material instead of disappearing from the feed.

## Tests become experiment candidates

Files and symbols that look like tests are not treated as proof of correctness.

They are converted to:

```text
EXPERIMENT_CANDIDATE
```

with:

```text
execution_status = NOT_EXECUTED_BY_REPOSITORY_SCANNER
```

For example, a Python `test_drag_force()` function becomes a proposal for a future evidence-producing experiment.

This preserves the distinction:

```text
test source exists
    !=
test executed
    !=
test passed
    !=
algorithm qualified
```

## Assertions become invariant candidates

Python `assert` statements can be extracted as:

```text
INVARIANT_CANDIDATE
```

For example:

```python
assert pressure >= 0
```

becomes a candidate invariant carrying its source path and line number.

It still requires semantic and evidence qualification before it can govern canonical algorithms.

Disable invariant extraction with:

```bash
oiec-stm-agent brain feed repo SOURCE --no-invariants
```

## Documentation

README files, Markdown, reStructuredText, plain text and other text/source files can be staged as source material.

Disable documentation-only files:

```bash
oiec-stm-agent brain feed repo SOURCE --no-docs
```

Ignore unknown text formats:

```bash
oiec-stm-agent brain feed repo SOURCE --no-unknown-text
```

## Include and exclude paths

Only inspect matching paths:

```bash
oiec-stm-agent brain feed repo SOURCE \
  --include 'src/**' \
  --include 'tests/**'
```

Exclude generated or irrelevant paths:

```bash
oiec-stm-agent brain feed repo SOURCE \
  --exclude 'examples/generated/**' \
  --exclude 'third_party/**'
```

Standard heavy/generated directories such as `.git`, `.ourd-agent`, `node_modules`, `vendor`, `dist`, `build`, `target`, virtual environments and cache directories are skipped automatically.

Symlinks are not followed.

## Language filtering

List known language identifiers:

```bash
oiec-stm-agent brain feed repo --list-languages
```

Filter a mixed repository:

```bash
oiec-stm-agent brain feed repo SOURCE \
  --language Python \
  --language Rust
```

## Bounds

Repository feeding is bounded.

Defaults:

```text
max files             1024
max total bytes        64 MiB
max file bytes          2 MiB
max extracted symbols 8192
max feed items/batch   4096
```

Override explicitly:

```bash
oiec-stm-agent brain feed repo SOURCE \
  --max-files 5000 \
  --max-total-bytes 268435456 \
  --max-file-bytes 4194304 \
  --max-symbols 30000
```

Large repository plans are automatically split into multiple ordinary brain-feed batches. A dependent algorithm/test/invariant is kept in a batch with the source evidence item it references.

## Emit ordinary brain-feed manifests

The repository scanner can be used only as an extractor.

```bash
oiec-stm-agent brain feed repo SOURCE \
  --scan-only \
  --emit-manifests ./generated-feed
```

This creates feed manifests that can later be inspected or fed using the ordinary batch interface.

```bash
oiec-stm-agent brain feed ./generated-feed/repo-feed-0001.json --repo .
```

This is useful when human review of the extracted knowledge episode is desired before ingestion.

## Strict mode

```bash
oiec-stm-agent brain feed repo SOURCE --repo . --strict
```

Strict mode returns non-zero when:

- any generated feed item is quarantined; or
- material scan incompleteness occurs, such as a Python parse error or configured file/symbol/byte bound being reached.

Ordinary binary files and intentionally skipped symlinks do not by themselves make the scan fail strict qualification.

## Self-feeding

A repository may feed itself:

```bash
cd OIEC-STM-Agent
oiec-stm-agent brain feed repo . --repo .
```

`.ourd-agent` is excluded from repository scanning, so writing brain state does not recursively become new source material on the next scan.

The repository signature therefore describes the scanned source, not the SAA state generated from that source.

## How this connects to the SAA mathematical brain

Repository feeding creates the outer knowledge rings:

```text
arbitrary repository
       |
       v
source fingerprints
       |
       +----> algorithm candidates
       +----> experiment candidates
       +----> invariant candidates
       +----> semantic clues
       +----> documentation
       |
       v
SAA staging
       |
       v
representation analysis
       |
       v
semantic resolution
       |
       v
retrieval / uniqueness search
       |
       v
experimentation / falsification
       |
       v
qualification
       |
       v
canonical algorithm store
```

This makes arbitrary source repositories useful raw material for the SAA Brain without confusing software archaeology with mathematical truth.
