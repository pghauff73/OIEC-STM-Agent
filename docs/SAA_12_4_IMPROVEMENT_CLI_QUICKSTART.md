# SAA-12.4 Improvement CLI Quickstart

```bash
# 1. Register an evidence-grounded opportunity
oiec-stm-agent improvement add --repo . \
  --id parser-precedence \
  --kind FAILURE_PATTERN \
  --source-signature aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
  --objective "Investigate repeated parser precedence failure" \
  --evidence-value-bp 9000 \
  --impact-bp 8500 \
  --uncertainty-reduction-bp 8000 \
  --cost-bp 2500 \
  --risk-bp 1500 \
  --evidence 'evidence-artifact:sha256:<digest>'

# 2. Inspect all known opportunities
oiec-stm-agent improvement list --repo .

# 3. Preview a bounded schedule
oiec-stm-agent improvement schedule --repo . \
  --max-selected 4 \
  --cost-budget-bp 20000 \
  --max-risk-bp 6000 \
  --min-priority-bp 1000 \
  --why

# 4. Persist the reviewed schedule
oiec-stm-agent improvement schedule --repo . \
  --max-selected 4 \
  --cost-budget-bp 20000 \
  --max-risk-bp 6000 \
  --min-priority-bp 1000 \
  --record --why

# 5. Inspect schedule history
oiec-stm-agent improvement history --repo .
```

The schedule ranks investigations only. It never grants mutation authority.
