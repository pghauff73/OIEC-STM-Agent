from __future__ import annotations

from typing import Any, Dict


JSON_VALUE_TYPES = ["object", "array", "string", "number", "boolean", "null"]
JSON_VALUE_SCHEMA: Dict[str, Any] = {"type": JSON_VALUE_TYPES}

COMMON_INPUT_FIELD_NAMES = (
        "acceleration", "activate", "active_dimension", "administrative", "after", "agent_id",
        "agreements", "algorithm_id", "algorithm_ids", "alternatives", "ambiguities",
        "approval_facts", "approval_id", "approver", "assets", "assumptions", "authority",
        "baseline", "before", "benchmarks", "boundaries", "budget", "candidates",
        "capabilities", "capability_facts", "category", "changed", "changes", "checkpoint",
        "choice", "claim_ids", "command", "command_capabilities", "command_id", "commands",
        "comparisons", "constraints", "content", "context", "count", "counterexamples", "current",
        "decision_id", "definition", "description", "design", "designs", "detections",
        "dimension", "dimensions", "disagreements", "duration", "environment", "evidence",
        "evidence_ids", "excluded_scope", "exclusions", "expected", "expires_at", "faces",
        "falsifier", "frames", "freshness_seconds", "frozen_dimensions", "goal", "grid",
        "human_confirmation", "hypotheses", "independence_group", "invariant_id",
        "invariant_ids", "invariants", "justification", "known_failures", "lesson", "level",
        "limit", "limitations", "mandatory", "method", "mode", "model_identity", "mutations",
        "name", "new_record", "nodes", "objective", "objects", "observed", "old_id",
        "operations", "oracle", "other", "outcome", "outcomes", "outputs", "owner",
        "parameters", "path", "pause_at_checkpoint", "pixels", "plan_id", "points", "policy", "position",
        "positions", "postconditions", "preconditions", "predicate_results", "preserve",
        "producer", "qualified_by", "question", "rationale", "reason", "recovery_plan",
        "relations", "repeats", "replacements", "request", "required_items", "required_tests",
        "requirement_ids", "requirements", "result", "results", "retry_count", "reviews",
        "resume", "revisions", "risk", "role", "rollback", "rollback_argument", "root_cause", "samples", "scope",
        "selection_id", "sequence", "simulated", "simulation", "source",
        "source_snapshot_hash", "start", "statement", "statements", "steps", "strength",
        "subject", "subject_id", "success", "summary", "target", "target_faces", "tests",
        "text", "threats", "threshold", "timeout", "tolerance", "top_claim", "trace",
        "transaction_id", "uncertainties", "uncovered", "unit", "units", "updates",
        "use_limit", "validator", "values", "velocity", "version", "vertices",
        "workflow_definition_id", "workflow_definition_ids"
)

BOOLEAN_FIELDS = {
    "activate", "administrative", "changed", "checkpoint", "human_confirmation",
    "mandatory", "pause_at_checkpoint", "preserve", "resume", "simulated", "success",
}
INTEGER_FIELDS = {
    "count", "freshness_seconds", "limit", "repeats", "retry_count", "strength",
    "target_faces", "use_limit", "version",
}
NUMBER_FIELDS = {"acceleration", "duration", "position", "threshold", "timeout", "tolerance", "velocity"}
STRING_LIST_FIELDS = {
    "agreements", "algorithm_ids", "alternatives", "ambiguities", "assumptions",
    "boundaries", "capabilities", "claim_ids", "command_capabilities", "commands",
    "counterexamples", "disagreements", "evidence", "evidence_ids", "excluded_scope",
    "exclusions", "frozen_dimensions", "hypotheses", "invariant_ids", "invariants",
    "known_failures", "limitations", "postconditions", "preconditions", "requirement_ids",
    "scope", "statements", "steps", "threats", "trace", "uncertainties", "uncovered",
    "workflow_definition_ids",
}
ARRAY_FIELDS = {
    "assets", "benchmarks", "candidates", "changes", "comparisons", "designs",
    "detections", "faces", "frames", "grid", "mutations", "nodes", "objects",
    "operations", "outcomes", "pixels", "points", "positions", "predicate_results",
    "relations", "required_items", "required_tests", "requirements", "results", "reviews",
    "revisions", "samples", "sequence", "tests", "updates", "values", "vertices",
}
OBJECT_FIELDS = {
    "approval_facts", "baseline", "before", "budget", "capability_facts", "context",
    "environment", "model_identity", "new_record", "outputs", "parameters", "replacements",
    "rollback_argument", "simulation", "units", "validator",
}
FLEXIBLE_FIELDS: Dict[str, list[str]] = {
    "after": ["object", "string", "null"],
    "constraints": ["object", "array"],
    "content": JSON_VALUE_TYPES,
    "current": JSON_VALUE_TYPES,
    "definition": ["object", "string"],
    "design": ["object", "array", "string"],
    "goal": ["string", "array"],
    "other": JSON_VALUE_TYPES,
    "path": ["string", "array"],
    "recovery_plan": ["object", "array", "string"],
    "result": JSON_VALUE_TYPES,
    "start": ["string", "array"],
}


def field_schema(name: str) -> Dict[str, Any]:
    if name in BOOLEAN_FIELDS:
        return {"type": "boolean"}
    if name in INTEGER_FIELDS:
        return {"type": "integer"}
    if name in NUMBER_FIELDS:
        return {"type": "number"}
    if name in STRING_LIST_FIELDS:
        return {"type": "array", "items": {"type": "string"}}
    if name in ARRAY_FIELDS:
        return {"type": "array", "items": dict(JSON_VALUE_SCHEMA)}
    if name in OBJECT_FIELDS:
        return {"type": "object"}
    if name in FLEXIBLE_FIELDS:
        return {"type": list(FLEXIBLE_FIELDS[name])}
    return {"type": "string"}


COMMON_INPUT_FIELDS = {name: field_schema(name) for name in COMMON_INPUT_FIELD_NAMES}


def command_contract(namespace: str, verb: str) -> Dict[str, Any]:
    key = f"{namespace}.{verb}"
    settings = {
        **NAMESPACE_DEFAULTS[namespace],
        **COMMAND_OVERRIDES.get(key, {}),
    }
    evidence = ["provenance"]
    if settings["level"] == "C2":
        evidence.append("simulation_label")
    if settings["level"] in {"C3", "C4", "C5"}:
        evidence.extend(["verification", "rollback_receipt"])
    return {
        "input_schema": {
            "type": "object",
            "properties": COMMON_INPUT_FIELDS,
            "required": COMMAND_REQUIRED_FIELDS.get(key, []),
            "additionalProperties": False,
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
                "command_id": {"type": "string"},
                "read_only": {"type": "boolean"},
                "result": dict(JSON_VALUE_SCHEMA),
                "provenance": {"type": "object"},
            },
            "required": ["ok", "command_id", "read_only", "result", "provenance"],
            "additionalProperties": False,
        },
        "preconditions": [
            "inputs_validate_against_command_schema",
            "capability_grant_matches_scope",
            "qualified_algorithm_available",
        ],
        "postconditions": [
            "output_validates_against_command_schema",
            "canonical_record_persisted",
        ],
        "invariants": [
            "authority_not_broadened",
            "provenance_preserved",
            "source_snapshot_binding_preserved",
        ],
        "evidence_requirements": evidence,
        "settings": settings,
    }


COMMAND_REQUIRED_FIELDS = {
    "capability.describe": ["name"],
    "algorithm.search": ["command_id"],
    "algorithm.select": ["command_id"],
    "algorithm.explain": ["selection_id"],
    "algorithm.register": ["definition"],
    "algorithm.qualify": ["algorithm_id", "tests"],
    "evidence.collect": ["subject_id", "content"],
    "evidence.graph": ["subject_id"],
    "evidence.export": ["subject_id"],
    "evidence.confidence": ["subject_id"],
    "evidence.conflicts": ["subject_id"],
    "evidence.history": ["subject_id"],
    "ieps.generate": ["subject_id", "requirements"],
    "ieps.coverage": ["subject_id"],
    "ieps.oracle": ["subject_id", "name", "category"],
    "ieps.qualify": ["subject_id"],
    "ieps.gate": ["subject_id"],
    "invariant.discover": ["statements"],
    "invariant.register": ["name", "statement", "validator", "evidence_ids", "falsifier"],
    "invariant.validate": ["invariant_id", "success"],
    "decision.create": ["question", "choice"],
    "decision.explain": ["decision_id"],
    "decision.supersede": ["old_id", "choice", "rationale"],
    "experiment.covering": ["parameters"],
    "simulate.migration": ["before", "operations"],
    "simulate.rollback": ["simulation"],
    "cfel.classify": ["observed"],
    "assurance.generate": ["subject_id"],
    "workflow.create": ["name", "nodes"],
    "workflow.execute": ["plan_id"],
    "workflow.replay": ["plan_id"],
    "eon.validate": ["changes"],
    "eon.compile": ["changes"],
    "eon.simulate": ["changes"],
    "eon.authorise": ["plan_id", "approver", "authority", "human_confirmation"],
    "eon.execute": ["changes"],
    "eon.rollback": ["transaction_id"],
}


NAMESPACE_VERBS = {
    "capability": ["list", "describe", "graph", "check", "request", "grant", "revoke", "audit", "explain"],
    "hrt": ["interpret", "assumptions", "ambiguity", "clarify", "claims", "provenance", "summary", "explain"],
    "ourd": ["model", "objects", "relations", "boundaries", "dependencies", "impact", "trace", "scope", "exclusions", "graph"],
    "iurm": ["dimensions", "baseline", "vary", "screen", "interactions", "sensitivity", "mvd", "optimise"],
    "ieps": ["generate", "coverage", "oracle", "counterexamples", "uniqueness", "mutation", "shrink", "qualify", "gate"],
    "eon": ["draft", "validate", "compile", "simulate", "authorise", "execute", "rollback", "compare"],
    "algorithm": ["register", "search", "compare", "qualify", "benchmark", "compose", "evolve", "retire", "explain", "select"],
    "evidence": ["collect", "classify", "compare", "graph", "export", "confidence", "conflicts", "history"],
    "invariant": ["discover", "register", "validate", "compare", "conflicts", "supersede"],
    "decision": ["create", "query", "history", "supersede", "explain", "conflicts"],
    "debug": ["reproduce", "minimise", "bisect", "hypotheses", "trace", "compare", "rootcause", "verify"],
    "experiment": ["design", "ofat", "factorial", "covering", "benchmark", "analyse", "repeat", "compare"],
    "verify": ["unit", "integration", "property", "fuzz", "mutation", "differential", "metamorphic", "regression", "performance", "security"],
    "simulate": ["worktree", "migration", "dependency", "api", "hardware", "filesystem", "network", "chaos", "rollback"],
    "performance": ["profile", "benchmark", "hotspots", "regression", "memory", "gpu", "io"],
    "security": ["threat-model", "taint", "sast", "secrets", "permissions", "provenance", "sbom", "audit"],
    "repo": ["graph", "symbols", "ownership", "history", "evolution", "metrics", "hotspots", "timeline"],
    "workflow": ["create", "compile", "execute", "pause", "resume", "replay", "branch", "merge", "monitor"],
    "agent": ["spawn", "specialise", "debate", "review", "critic", "merge", "consensus", "terminate"],
    "cfel": ["observe", "classify", "compare", "diagnose", "recover", "learn", "stability", "regression"],
    "physics": ["simulate"],
    "geometry": ["analyse", "fit", "optimise"],
    "grammar": ["parse", "transform", "compare", "verify"],
    "vision": ["detect", "segment", "track"],
    "robotics": ["plan", "verify"],
    "cad": ["mesh", "topology", "simplify", "validate"],
}


ENGINEERING_ALIASES = {
    "prove": "assurance.generate@1",
    "justify": "assurance.generate@1",
    "challenge": "ieps.counterexamples@1",
    "counterexample": "ieps.counterexamples@1",
    "shrink": "ieps.shrink@1",
    "differentiate": "evidence.compare@1",
    "supersede": "decision.supersede@1",
    "qualify": "ieps.qualify@1",
    "attest": "assurance.generate@1",
    "explain-choice": "algorithm.explain@1",
    "confidence": "evidence.confidence@1",
    "scope": "ourd.scope@1",
    "authority": "capability.explain@1",
    "rollback-plan": "simulate.rollback@1",
    "impact-map": "ourd.impact@1",
    "assurance-case": "assurance.generate@1",
}


NAMESPACE_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "capability": {"level": "C0", "facets": ["registry.read"], "risk": "L0", "approval": "automatic", "rollback": "none"},
    "hrt": {"level": "C1", "facets": ["analysis.reason"], "risk": "L0", "approval": "automatic", "rollback": "none"},
    "ourd": {"level": "C1", "facets": ["analysis.model"], "risk": "L0", "approval": "automatic", "rollback": "none"},
    "iurm": {"level": "C1", "facets": ["analysis.experiment"], "risk": "L0", "approval": "automatic", "rollback": "none"},
    "ieps": {"level": "C1", "facets": ["evidence.analyse"], "risk": "L0", "approval": "policy", "rollback": "none"},
    "eon": {"level": "C1", "facets": ["eon.plan"], "risk": "L0", "approval": "policy", "rollback": "none"},
    "algorithm": {"level": "C0", "facets": ["registry.read"], "risk": "L0", "approval": "automatic", "rollback": "none"},
    "evidence": {"level": "C1", "facets": ["evidence.analyse"], "risk": "L0", "approval": "automatic", "rollback": "none"},
    "invariant": {"level": "C1", "facets": ["governance.read"], "risk": "L0", "approval": "policy", "rollback": "none"},
    "decision": {"level": "C1", "facets": ["governance.read"], "risk": "L0", "approval": "policy", "rollback": "none"},
    "debug": {"level": "C1", "facets": ["analysis.debug"], "risk": "L0", "approval": "automatic", "rollback": "none"},
    "experiment": {"level": "C1", "facets": ["analysis.experiment"], "risk": "L0", "approval": "automatic", "rollback": "none"},
    "verify": {"level": "C1", "facets": ["verification.run"], "risk": "L1", "approval": "policy", "rollback": "none"},
    "simulate": {"level": "C2", "facets": ["simulation.run"], "risk": "L1", "approval": "policy", "rollback": "exact"},
    "performance": {"level": "C1", "facets": ["analysis.performance"], "risk": "L0", "approval": "automatic", "rollback": "none"},
    "security": {"level": "C1", "facets": ["analysis.security"], "risk": "L0", "approval": "automatic", "rollback": "none"},
    "repo": {"level": "C0", "facets": ["filesystem.read"], "risk": "L0", "approval": "automatic", "rollback": "none"},
    "workflow": {"level": "C1", "facets": ["workflow.plan"], "risk": "L0", "approval": "policy", "rollback": "none"},
    "agent": {"level": "C2", "facets": ["agent.local"], "risk": "L1", "approval": "policy", "rollback": "none"},
    "cfel": {"level": "C1", "facets": ["evidence.analyse"], "risk": "L0", "approval": "automatic", "rollback": "none"},
    "physics": {"level": "C2", "facets": ["simulation.run"], "risk": "L1", "approval": "policy", "rollback": "none"},
    "geometry": {"level": "C1", "facets": ["analysis.geometry"], "risk": "L0", "approval": "automatic", "rollback": "none"},
    "grammar": {"level": "C1", "facets": ["analysis.grammar"], "risk": "L0", "approval": "automatic", "rollback": "none"},
    "vision": {"level": "C1", "facets": ["analysis.vision"], "risk": "L0", "approval": "automatic", "rollback": "none"},
    "robotics": {"level": "C2", "facets": ["simulation.robotics"], "risk": "L1", "approval": "policy", "rollback": "none"},
    "cad": {"level": "C1", "facets": ["analysis.cad"], "risk": "L0", "approval": "automatic", "rollback": "none"},
    "assurance": {"level": "C1", "facets": ["evidence.analyse"], "risk": "L0", "approval": "policy", "rollback": "none"},
}


COMMAND_OVERRIDES: Dict[str, Dict[str, Any]] = {
    "capability.request": {"level": "C1", "facets": ["governance.propose"], "approval": "human"},
    "capability.grant": {"level": "C5", "facets": ["governance.admin"], "risk": "L2", "approval": "human", "rollback": "compensating"},
    "capability.revoke": {"level": "C5", "facets": ["governance.admin"], "risk": "L2", "approval": "human", "rollback": "compensating"},
    "algorithm.register": {"level": "C1", "facets": ["registry.propose"], "approval": "policy"},
    "algorithm.qualify": {"level": "C1", "facets": ["registry.qualify"], "approval": "policy"},
    "algorithm.evolve": {"level": "C1", "facets": ["registry.propose"], "approval": "policy"},
    "algorithm.retire": {"level": "C3", "facets": ["registry.admin"], "risk": "L1", "approval": "human", "rollback": "compensating"},
    "invariant.register": {"level": "C3", "facets": ["governance.write"], "risk": "L1", "approval": "human", "rollback": "compensating"},
    "invariant.supersede": {"level": "C3", "facets": ["governance.write"], "risk": "L1", "approval": "human", "rollback": "compensating"},
    "decision.create": {"level": "C1", "facets": ["governance.propose"], "risk": "L0", "approval": "policy", "rollback": "none"},
    "decision.supersede": {"level": "C3", "facets": ["governance.write"], "risk": "L1", "approval": "human", "rollback": "compensating"},
    "eon.execute": {"level": "C3", "facets": ["filesystem.write", "process.execute"], "risk": "L1", "approval": "human", "rollback": "exact"},
    "eon.rollback": {"level": "C3", "facets": ["filesystem.write"], "risk": "L1", "approval": "human", "rollback": "exact"},
    "workflow.execute": {"level": "C1", "facets": ["workflow.plan"], "risk": "L0", "approval": "policy", "rollback": "none"},
}


def command_catalog() -> Dict[str, Any]:
    namespaces = dict(NAMESPACE_VERBS)
    namespaces["assurance"] = ["generate"]
    return {
        "schema_version": 1,
        "namespaces": namespaces,
        "defaults": NAMESPACE_DEFAULTS,
        "overrides": COMMAND_OVERRIDES,
        "aliases": ENGINEERING_ALIASES,
    }
