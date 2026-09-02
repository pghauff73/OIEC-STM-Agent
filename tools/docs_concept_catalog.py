"""Source-derived concept inventory for the OURD documentation site."""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Concept:
    slug: str
    title: str
    category: str
    definition: str
    thesis: str
    central_question: str
    inputs: str
    controls: str
    evidence: str
    outcome: str
    sources: tuple[str, ...]
    related: tuple[str, ...]


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "concept"


def humanize(value: str) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", value)
    return value.replace("_", " ").strip()


CORE_CONCEPTS = (
    Concept(
        "hrt",
        "HRT: Human-Readable Task Interpretation",
        "Governed Reasoning Loop",
        "HRT turns a human request into explicit claims, assumptions, ambiguities, scope, exclusions, and provenance before deeper reasoning begins.",
        "Human intent should be made inspectable before the system treats it as an engineering problem.",
        "What did the person actually ask, and which uncertainties must be surfaced rather than guessed?",
        "Human language, repository context, stated constraints, and unresolved questions.",
        "Explicit assumptions, provenance, scope boundaries, and clarification requirements.",
        "A reviewable interpretation record that another person can challenge.",
        "A bounded task statement suitable for OURD modeling.",
        ("README.md", "EGCFV1_IMPLEMENTATION_PLAN.md", "ourd/egcf/catalog.py"),
        ("OURD", "Intent Record", "Provenance", "Scope"),
    ),
    Concept(
        "ourd",
        "OURD: Orthogonal Unique Relational Decomposition Modeling",
        "Governed Reasoning Loop",
        "OURD decomposes the problem into orthogonal, uniquely identified relational components, boundaries, dependencies, goals, impacts, exclusions, and unresolved relations.",
        "The agent should model the territory before choosing one imagined implementation path.",
        "What belongs to this problem, how is it connected, and what remains uncertain?",
        "The HRT interpretation, repository objects, constraints, dependencies, and goals.",
        "Canonical identities, typed relations, explicit boundaries, exclusions, and uncertainty markers.",
        "A semantic graph whose nodes and edges can be inspected and compared with source facts.",
        "A problem representation that separates the task from any single candidate solution.",
        ("README.md", "docs/OURD_AGENT_GUI.md", "ourd/egcf/catalog.py", "ourd_gui/views/ourd.py"),
        ("HRT", "IURM", "Semantic Graph", "Canonical Identity"),
    ),
    Concept(
        "iurm",
        "IURM: Invariant-Uncertainty-Response Modeling",
        "Governed Reasoning Loop",
        "IURM identifies dimensions, baselines, controlled variations, interactions, sensitivity, and minimum viable designs.",
        "Useful learning comes from discriminating experiments, not from changing many coupled dimensions at once.",
        "Which variable should move, what must remain invariant, and what observation would reduce uncertainty?",
        "The OURD problem model, candidate dimensions, a baseline, and measurable responses.",
        "Controlled variation, invariant checks, interaction analysis, budgets, and abstention when a dimension is not isolated.",
        "Comparable experiment records showing what changed and what response followed.",
        "A discriminating candidate variation or a justified decision not to vary anything yet.",
        ("README.md", "docs/OURD_AGENT_GUI.md", "ourd/egcf/catalog.py", "ourd_gui/views/iurm.py"),
        ("OURD", "Experiment Designer", "OFAT", "MVD", "Invariant"),
    ),
    Concept(
        "ieps",
        "IEPS: Invariant and Evidence Production System",
        "Governed Reasoning Loop",
        "IEPS produces coverage, oracles, counterexamples, uniqueness checks, mutations, shrinking, qualification, and evidence gates.",
        "A candidate should meet evidence designed to discriminate truth from plausible appearance.",
        "What evidence would expose a false claim, a hidden regression, or an unsupported success story?",
        "Claims, invariants, candidate behavior, datasets, tests, and evidence requirements.",
        "Independent oracles, counterexamples, mutation, coverage, source binding, and limitation records.",
        "Artifacts that state what was observed, how it was produced, and what it cannot prove.",
        "Evidence suitable for an EON gate decision or a fail-closed refusal.",
        ("EGCFV1_IMPLEMENTATION_PLAN.md", "ourd/egcf/ieps.py", "ourd/egcf/evidence.py"),
        ("IURM", "Evidence Artifact", "Invariant Record", "Evidence Gate"),
    ),
    Concept(
        "eon",
        "EON: Exact Governed Action Boundary",
        "Governed Reasoning Loop",
        "EON binds a proposed operation to exact authority, source state, targets, candidate content, commands, tests, invariants, risk, expiry, and use limits.",
        "Reasoning should cross into mutation only through an exact, reviewable, stale-detecting action identity.",
        "What precise operation is proposed, against which exact state, under whose authority, and with which rollback?",
        "A staged candidate, source snapshot, target set, authority manifest, evidence, tests, and risk classification.",
        "Exact hashes, canonical command arguments, capability checks, approval policy, expiry, use count, and rollback binding.",
        "An immutable action identity and gate decision that become stale when any bound fact changes.",
        "One authorized execution, simulation, refusal, comparison, or rollback operation.",
        ("README.md", "IMPLEMENTATION_PLAN.md", "ourd/models.py", "ourd/egcf/adapters/eon.py"),
        ("IURM", "Evidence Gate", "EON Action", "Candidate Transaction", "Rollback"),
    ),
    Concept(
        "evidence-gate",
        "Evidence Gate",
        "Governed Reasoning Loop",
        "The evidence gate compares the proposed action's declared requirements with current artifacts, authority, approval, risk, and invariants.",
        "The gate should decide from deterministic records rather than from the model's confidence or persuasive language.",
        "Does the exact candidate possess enough current, relevant, independent evidence to proceed?",
        "An EON action, evidence artifacts, gate policy, approval records, invariants, and the current source snapshot.",
        "Exact-plan matching, evidence coverage, source binding, expiry, use limits, and deterministic risk floors.",
        "A reasoned pass or refusal whose inputs and missing requirements are inspectable.",
        "Permission to execute one bound action, or a fail-closed requirement for better evidence.",
        ("README.md", "IMPLEMENTATION_PLAN.md", "ourd/policy.py", "ourd/models.py"),
        ("EON", "Gate Decision", "Evidence Artifact", "Approval Record"),
    ),
    Concept(
        "governed-action",
        "Governed Action",
        "Governed Reasoning Loop",
        "A governed action is the actual mutation or command execution performed only after the exact candidate passes its deterministic gate.",
        "Execution should be the consequence of evidence and authority, not a side effect of model reasoning.",
        "What single authorized effect is now allowed, and how will its result be verified?",
        "A passed gate decision, exact action identity, prepared transaction, command capability, and current workspace state.",
        "Atomic apply where possible, post-write hashing, environment sanitization, bounded subprocess execution, and rollback preservation.",
        "Execution events, output artifacts, postconditions, hashes, and failure records.",
        "A verified effect or a collision that feeds CFEL without silently broadening authority.",
        ("README.md", "ourd/transactions.py", "ourd/workspace.py", "ourd/agent.py"),
        ("Evidence Gate", "Transaction Manager", "Execution Record", "CFEL"),
    ),
    Concept(
        "cfel",
        "CFEL: Collision, Failure, Evidence, and Learning Feedback",
        "Governed Reasoning Loop",
        "CFEL records the difference between expectation and observation, blocks unchanged blind retries, and turns failure into bounded evidence for a revised model.",
        "A failure is valuable only when it changes the next hypothesis, experiment, or action.",
        "What did reality contradict, how severe is the collision, and what new evidence justifies another attempt?",
        "Expected outcomes, observed outputs, attempted action identity, current evidence, and failure context.",
        "Collision fingerprints, retry bounds, risk-sensitive recovery policy, and refusal of unchanged failed calls.",
        "A collision record linked to the attempted action, source state, and revised evidence.",
        "A revised OURD model, a new IURM experiment, a bounded recovery, or an explicit stop.",
        ("README.md", "IMPLEMENTATION_PLAN.md", "ourd/cfel.py", "ourd/models.py"),
        ("Governed Action", "OURD", "IURM", "Collision Record", "Failure Record"),
    ),
    Concept(
        "egcf",
        "EGCF: Evidence-Governed Command Fabric",
        "Semantic Command Fabric",
        "EGCF compiles semantic engineering intent into typed, content-addressed workflow plans governed by capabilities, evidence, approvals, and exact execution adapters.",
        "A command should express engineering meaning before it selects an executor.",
        "How can a high-level objective become a typed plan without falling through to arbitrary shell authority?",
        "Intent records, command definitions, command context, registries, algorithms, capabilities, evidence, and workflow definitions.",
        "Schema validation, static refusals, authority intersection, contextual qualification, content addressing, and adapter boundaries.",
        "A compiled workflow and execution plan with reproducible identity and explicit requirements.",
        "A safe semantic path to simulation, EON execution, evidence generation, or refusal.",
        ("EGCFV1_IMPLEMENTATION_PLAN.md", "docs/EGCFV1_COMMAND_REFERENCE.md", "ourd/egcf/engine.py"),
        ("HRT", "OURD", "IURM", "IEPS", "EON", "Command Namespace"),
    ),
)


DEFINITION_OVERRIDES = {
    "AuthorityManifest": "The human-authored declaration of which workspace snapshot, paths, commands, capabilities, evidence rules, risks, and retry limits may be used.",
    "TransactionRecord": "The durable record of a staged or applied file transaction, including original and candidate content hashes needed for verification and rollback.",
    "EONAction": "The exact action object that binds authority, source state, candidate content, target paths, command arguments, evidence, risk, expiry, and use limits.",
    "GateDecision": "The deterministic evidence-gate result that records whether an exact EON action may proceed and why.",
    "CollisionRecord": "The durable CFEL record of a significant mismatch between expectation and observation.",
    "RuntimeState": "The rebuildable current-state projection used to coordinate unresolved transactions, actions, collisions, and execution history.",
    "BoundaryState": "The signed fixed-point projection of semantic scope, authority patterns, governance patterns, experimental dimensions, and boundary uncertainty for one exact source snapshot.",
    "DimensionBudget": "The finite deterministic limits and selected experimental dimensions that constrain active OIEC complexity without enlarging authority.",
    "FiniteEvidenceState": "The action-scoped bitmask and quality projection that keeps active evidence finite while leaving the durable evidence registry append-only.",
    "AttemptKey": "The pre-action identity binding an exact snapshot, EON action, relevant evidence state, boundary state, and dimension state for no-blind-retry enforcement.",
    "ProgressCertificate": "The deterministic proof that an observed transition gained relevant evidence, improved a goal or risk measure, resolved boundary uncertainty, ran a discriminating experiment, or stopped terminally.",
    "BoundedTransitionKernel": "The pure two-phase OIEC control layer that prepares governed actions and accepts evidence-bearing observations without executing commands or writing repository files.",
    "CommandContext": "The shared scope, evidence, approval, risk, rollback, budget, timeout, trace, simulation, and strictness contract inherited by semantic commands.",
    "WorkflowCompiler": "The compiler that turns semantic commands and workflow definitions into typed plans while applying schema, capability, algorithm, evidence, and refusal rules.",
    "EGCFEngine": "The high-level semantic command engine that coordinates catalogs, stores, registries, compilation, evidence, approval, simulation, and execution adapters.",
    "ObjectStore": "The content-addressed canonical store for immutable EGCF records.",
    "ArtifactStore": "The content-addressed store for larger evidence and execution artifacts.",
    "EGCFStore": "The combined persistence boundary for canonical objects, artifacts, events, and rebuildable query projections.",
    "WorkspaceLock": "The exclusive writer lock that prevents concurrent mutation and exposes unresolved transaction state.",
    "EventStore": "The append-only, SHA-256-chained event ledger used as durable provenance and replay history.",
    "StateStore": "The rebuildable state projection derived from canonical events.",
    "TransactionManager": "The service that stages immutable candidates, applies them atomically where possible, verifies results, and restores original bytes during rollback.",
    "PolicyEngine": "The deterministic evaluator for risk floors, evidence sufficiency, authority, approvals, commands, targets, and execution permission.",
    "CapabilityResolver": "The service that intersects capability requirements, grants, facets, scope, expiry, and use limits to compute effective authority.",
    "SelectionEngine": "The service that chooses a context-qualified algorithm using declared qualification strength and deterministic selection order.",
    "OURDAgent": "The runtime coordinator that presents model reasoning as proposals while routing governed tools, candidate transactions, EON actions, evidence, and CFEL through deterministic controls.",
    "LlamaCppProcessProvider": "The bounded direct-process provider adapter for local llama.cpp execution, including exact model identity, grammar-first output, context limits, deadlines, and cancellation points.",
    "IEPS": "The evidence-production service for coverage, counterexamples, mutation, shrinking, uniqueness, qualification, and gates.",
}


def class_category(name: str, source: str) -> str:
    if name.endswith("Error") or source.endswith("errors.py"):
        return "Refusal and Error Semantics"
    if "/adapters/" in source:
        return "Execution Adapters"
    if source.endswith("models.py"):
        return "Canonical Records"
    if "/providers/" in source:
        return "Model Boundary"
    if any(part in source for part in ("persistence.py", "store.py")):
        return "Persistence and Provenance"
    if any(part in source for part in ("authority.py", "policy.py", "capabilities.py", "approval.py", "transactions.py")):
        return "Governance and Authority"
    if any(part in source for part in ("registry.py", "domains.py", "experiments.py", "ieps.py", "invariants.py", "decisions.py", "assurance.py", "simulation.py")):
        return "Engineering Services"
    if any(part in source for part in ("compiler.py", "context.py", "engine.py", "handlers.py", "lifecycle.py", "catalog.py")):
        return "Semantic Command Fabric"
    return "Agent Runtime"


def class_definition(name: str, source: str, docstring: str) -> str:
    if name in DEFINITION_OVERRIDES:
        return DEFINITION_OVERRIDES[name]
    if docstring:
        return docstring.rstrip(".") + "."
    label = humanize(name).lower()
    if name.endswith("Record"):
        return f"A typed canonical record that preserves the identity, provenance, and lifecycle facts for {label.removesuffix(' record')}."
    if name.endswith("Manager"):
        return f"The lifecycle service that creates, validates, queries, or supersedes {label.removesuffix(' manager')} records."
    if name.endswith("Adapter"):
        return f"A controlled execution bridge that translates an authorized EGCF plan node into {label.removesuffix(' adapter')} behaviour without transferring authority."
    if name.endswith("Store"):
        return f"The persistence owner responsible for durable {label.removesuffix(' store')} data and its integrity checks."
    if name.endswith("Registry"):
        return f"The canonical registry that qualifies, indexes, and resolves {label.removesuffix(' registry')} definitions."
    if name.endswith("Engine"):
        return f"The deterministic orchestration service for {label.removesuffix(' engine')} operations."
    if name.endswith("Provider"):
        return f"The bounded model-provider interface for {label.removesuffix(' provider')} requests and responses."
    if name.endswith("Decision"):
        return f"A typed decision object that records the basis and consequence of {label.removesuffix(' decision')}."
    if name.endswith("Definition"):
        return f"The canonical schema-backed definition of {label.removesuffix(' definition')} behaviour."
    return f"A public OURD runtime concept that owns or represents {label} behaviour in {source}."


def class_thesis(name: str, category: str) -> str:
    label = humanize(name)
    if category == "Canonical Records":
        return f"{label} should preserve one canonical, content-addressed account of its fact rather than duplicate mutable interpretations."
    if category == "Execution Adapters":
        return f"{label} should translate already-authorized intent without broadening scope, authority, or evidence claims."
    if category == "Refusal and Error Semantics":
        return f"{label} should make unsafe or inconsistent states explicit and fail closed rather than degrade silently."
    if category == "Persistence and Provenance":
        return f"{label} should keep canonical facts durable, verifiable, replayable, and separable from rebuildable projections."
    if category == "Governance and Authority":
        return f"{label} should make mutation permission deterministic, proportional, exact, and reviewable."
    if category == "Model Boundary":
        return f"{label} should preserve model usefulness while preventing model output from becoming approval or certification authority."
    if category == "Semantic Command Fabric":
        return f"{label} should turn engineering meaning into a typed plan before any executor is selected."
    if category == "Engineering Services":
        return f"{label} should add reusable engineering analysis without hiding evidence, assumptions, or lifecycle state."
    return f"{label} should keep agent coordination subordinate to authority, evidence, and recoverable execution."


def class_facets(name: str, category: str) -> tuple[str, str, str, str, tuple[str, ...]]:
    label = humanize(name)
    if category == "Canonical Records":
        return (
            "Validated fields, typed identifiers, source snapshots, and linked record IDs.",
            "Strict schemas, content hashes, immutable identity, and explicit supersedence.",
            "Canonical JSON, typed IDs, lifecycle events, and references to producing records.",
            f"A durable {label} record suitable for replay, comparison, and assurance.",
            ("Content Addressing", "Typed Identity", "Supersedence"),
        )
    if category == "Execution Adapters":
        return (
            "Authorized plan nodes, bounded inputs, capability facets, and exact context.",
            "No authority transfer, schema checks, environment limits, and adapter qualification.",
            "Execution receipts, simulation labels, outputs, failures, and provenance.",
            f"A bounded {label} result or a deterministic refusal.",
            ("Execution Plan", "Capability Grant", "Evidence Artifact"),
        )
    if category == "Refusal and Error Semantics":
        return (
            "An invalid, unsafe, stale, unauthorized, or inconsistent condition.",
            "Fail-closed policy, typed exceptions, no silent fallback, and explicit caller handling.",
            "The rejected inputs, violated rule, source state, and refusal event.",
            f"A visible {label} that blocks unsupported continuation.",
            ("Fail Closed", "CFEL", "Evidence Gate"),
        )
    return (
        "Typed requests, repository state, policy context, and linked canonical records.",
        "Authority intersection, schemas, budgets, source binding, evidence requirements, and lifecycle rules.",
        "Events, hashes, records, tests, decisions, and explicit limitations.",
        f"A reviewable {label} result that can feed the next governed step.",
        ("EGCF", "Evidence", "Authority", "Replay"),
    )


def discover_public_classes() -> tuple[Concept, ...]:
    concepts: list[Concept] = []
    seen: set[str] = set()
    for path in sorted((ROOT / "ourd").rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.ClassDef) or node.name.startswith("_") or node.name in seen:
                continue
            seen.add(node.name)
            docstring = (ast.get_docstring(node) or "").splitlines()
            first_line = docstring[0] if docstring else ""
            category = class_category(node.name, relative)
            inputs, controls, evidence, outcome, related = class_facets(node.name, category)
            concepts.append(
                Concept(
                    slug=f"type-{slugify(node.name)}",
                    title=humanize(node.name),
                    category=category,
                    definition=class_definition(node.name, relative, first_line),
                    thesis=class_thesis(node.name, category),
                    central_question=f"What architectural responsibility does {humanize(node.name)} own, and how can a reviewer verify that ownership?",
                    inputs=inputs,
                    controls=controls,
                    evidence=evidence,
                    outcome=outcome,
                    sources=(relative,),
                    related=related,
                )
            )
    return tuple(concepts)


def namespace_definition(name: str, verbs: list[str]) -> str:
    formatted = ", ".join(verbs[:-1]) + (f", and {verbs[-1]}" if len(verbs) > 1 else verbs[0])
    return f"The {name} semantic command namespace groups the governed operations {formatted}."


def discover_namespaces() -> tuple[Concept, ...]:
    catalog_path = ROOT / "commands" / "v1" / "catalog.json"
    namespaces = json.loads(catalog_path.read_text(encoding="utf-8"))["namespaces"]
    concepts = []
    for name, verbs in sorted(namespaces.items()):
        display = name.upper() if name in {"hrt", "ourd", "iurm", "ieps", "eon", "cfel"} else name.title()
        concepts.append(
            Concept(
                slug=f"namespace-{slugify(name)}",
                title=f"{display} Command Namespace",
                category="Semantic Command Namespaces",
                definition=namespace_definition(name, verbs),
                thesis=f"The {display} namespace should preserve semantic intent, typed inputs, capability requirements, and evidence policy instead of becoming an alias for arbitrary shell execution.",
                central_question=f"Which engineering responsibility belongs in the {display} namespace, and what evidence should its commands produce?",
                inputs=f"Typed command inputs for the verbs {', '.join(verbs[:6])}{' and others' if len(verbs) > 6 else ''}.",
                controls="CommandContext inheritance, capability classes, risk levels, schemas, algorithm qualification, evidence requirements, and static refusals.",
                evidence="Canonical command invocation, compiled plan, selected algorithm, source snapshot, produced records, and execution or simulation receipts.",
                outcome=f"A governed {display} result, reusable canonical record, simulation, EON action, or explicit refusal.",
                sources=("commands/v1/catalog.json", "commands/v1/contracts.json", "ourd/egcf/catalog.py"),
                related=tuple(verbs[:5]),
            )
        )
    return tuple(concepts)


def discover_concepts() -> tuple[Concept, ...]:
    concepts = [*CORE_CONCEPTS, *discover_namespaces(), *discover_public_classes()]
    by_slug: dict[str, Concept] = {}
    for concept in concepts:
        if concept.slug in by_slug:
            raise ValueError(f"duplicate concept slug: {concept.slug}")
        by_slug[concept.slug] = concept
    return tuple(sorted(by_slug.values(), key=lambda item: (item.category, item.title)))
