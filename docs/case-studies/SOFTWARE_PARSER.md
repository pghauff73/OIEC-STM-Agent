# Software: Parser Regression

## Problem

A parser changes operator precedence after a recent edit.

## Governed analysis

The failing input, expected syntax tree, current source snapshot, grammar, tests, and callers form the problem boundary. EGCF compiles a dry-run objective. EON binds any candidate to exact files and tests. CFEL records failed hypotheses and regressions.

## Evidence status

**Implemented teaching pattern.** The repository contains EGCF parser-regression workflow fixtures and governed mutation infrastructure, but this page does not certify a particular repair.

## Lesson

A focused reproducer and exact candidate identity are stronger than repeated speculative edits.
