# A/B Evidence

## What you will learn

You will compare a candidate and baseline under the same workload, measures, source binding, and regression constraints.

## Everyday analogy

Two workshop processes must be timed on comparable jobs with the same quality checks. Faster output is not an improvement if defects increase outside the measured step.

## New vocabulary

A **candidate** is the proposed variation. A **baseline** is the frozen comparison. A **regression** is a loss in a protected property.

## Diagram

The diagram sends baseline and candidate through the same evidence contract, then compares objective change, regressions, and limitations.

## Command or interaction

Use the fixture to reveal measurements for both variants. Mark the candidate qualified only when the declared improvement and every protected constraint pass.

## Expected output

The comparison yields qualified improvement, regression detected, inconclusive, or invalid comparison with explicit evidence.

## What just happened?

The candidate did not compete against a moving or selectively measured baseline. The evidence contract determined the verdict.

## Try changing this

Remove one required measure or change the baseline source hash. Observe why the comparison becomes incomplete or stale.

## Common mistake

A focused metric gain does not establish overall improvement when protected constraints or representative workloads are missing.

## Next lesson

Continue to **Closed Loop** and verify that qualified knowledge can be promoted and retrieved again.
