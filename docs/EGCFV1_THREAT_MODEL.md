# EGCFv1 Threat Model

| Threat | Enforced control |
| --- | --- |
| Semantic bypass | Command definitions cannot contain callbacks; adapters receive authorized plan nodes only |
| Capability laundering | Reachable requirements are unioned; grants and scopes are intersected |
| Registry poisoning | Strict records, content hashes, qualification, status, and implementation digests |
| Algorithm substitution | Plan stores exact definition ID and implementation digest |
| Approval replay | Approval binds immutable plan ID/hash, source snapshot, expiry, and use limit |
| Stale evidence | Evidence carries source snapshot, timestamps, oracle, producer, and limitations |
| Evidence double counting | Content hashes, independence groups, and requirement bindings |
| Model self-approval | Human approvals are created only through the external engine API/CLI path |
| Prompt injection | Repository, MCP, skill, agent, and model outputs remain untrusted data |
| Simulation confusion | Simulation adapters always emit `simulated: true` and fidelity limits |
| Rollback fraud | EON applies recorded originals and verifies restored hashes |
| Workflow amplification | DAG cycle checks, bounded retries, and global budgets |
| Secret leakage | Existing redaction is reused before evidence/object storage |
| Subagent escalation | Agent outputs preserve `authority_transfer: false` |
| External duplication | C4/C5 executors are unavailable until idempotency/compensation qualification |
| Projection tampering | SQLite is discarded and rebuilt from immutable objects |
