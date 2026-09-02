#!/usr/bin/env python3
"""Build the interactive OIEC-STM-Agent systems-architecture site.

The generator deliberately uses only the Python standard library so the
checked-in documentation can be rebuilt without adding a package dependency.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import html
import json
import os
import re
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

try:
    from tools.docs_concept_catalog import CORE_CONCEPTS, Concept, discover_concepts
    from tools.docs_cli_catalog import (
        COMMAND_BUILDER_SCHEMA,
        PROGRAMS,
        PROVIDERS,
        RECIPES,
        REJECTED_RECIPES,
        records_for_manifest as cli_records_for_manifest,
        validate_recipes,
    )
    from tools.docs_learning_catalog import (
        ACRONYMS,
        CASE_STUDIES,
        CONTENT_KINDS,
        DOCUMENTATION_STATUSES,
        INVENTION_TIMELINE,
        LEARNING_PATHS,
        TASK_ROUTES,
        TUTORIAL_HEADINGS,
        TUTORIALS,
        records_for_manifest as learning_records_for_manifest,
        teaching_record_for,
        validate_catalog_sources,
        validate_prerequisite_graph,
    )
    from tools.docs_status_catalog import (
        discover_statuses,
        records_for_manifest as status_records_for_manifest,
        validate_statuses,
    )
    from tools.docs_visual_grammar import (
        edge_attributes,
        grammar_manifest,
        node_attributes,
        root_attributes,
        validate_svg,
    )
except ModuleNotFoundError:
    from docs_concept_catalog import CORE_CONCEPTS, Concept, discover_concepts
    from docs_cli_catalog import (
        COMMAND_BUILDER_SCHEMA,
        PROGRAMS,
        PROVIDERS,
        RECIPES,
        REJECTED_RECIPES,
        records_for_manifest as cli_records_for_manifest,
        validate_recipes,
    )
    from docs_learning_catalog import (
        ACRONYMS,
        CASE_STUDIES,
        CONTENT_KINDS,
        DOCUMENTATION_STATUSES,
        INVENTION_TIMELINE,
        LEARNING_PATHS,
        TASK_ROUTES,
        TUTORIAL_HEADINGS,
        TUTORIALS,
        records_for_manifest as learning_records_for_manifest,
        teaching_record_for,
        validate_catalog_sources,
        validate_prerequisite_graph,
    )
    from docs_status_catalog import (
        discover_statuses,
        records_for_manifest as status_records_for_manifest,
        validate_statuses,
    )
    from docs_visual_grammar import (
        edge_attributes,
        grammar_manifest,
        node_attributes,
        root_attributes,
        validate_svg,
    )


ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = ROOT / "docs"
EDUCATIONAL_DIRECTORIES = {"tutorial", "tasks", "case-studies"}


@functools.lru_cache(maxsize=1)
def documentation_version() -> str:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    return str(project["version"])


@functools.lru_cache(maxsize=1)
def source_snapshot_digest() -> str:
    paths = {
        ROOT / "pyproject.toml",
        DOCS_ROOT / "assets" / "site.js",
        DOCS_ROOT / "assets" / "styles.css",
    }
    paths.update(DOCS_ROOT.rglob("*.md"))
    paths.update((ROOT / "ourd").rglob("*.py"))
    paths.update((ROOT / "ourd_gui").rglob("*.py"))
    paths.update((ROOT / "tools").glob("docs_*.py"))
    paths.add(ROOT / "tools" / "build_docs_site.py")
    digest = hashlib.sha256()
    for path in sorted(path for path in paths if path.is_file()):
        relative = path.relative_to(ROOT).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        content = path.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def page_snapshot_attributes(build_date: str) -> str:
    return (
        f'data-docs-version="{html.escape(documentation_version(), quote=True)}" '
        f'data-source-snapshot="sha256:{source_snapshot_digest()}" '
        f'data-build-date="{html.escape(build_date, quote=True)}"'
    )


REFERENCE_LIBRARY = (
    {
        "id": "R1",
        "title": "Software Architecture in Practice, 4th Edition",
        "authors": "Len Bass, Paul Clements, and Rick Kazman",
        "url": "https://www.sei.cmu.edu/library/software-architecture-in-practice-fourth-edition/",
        "summary": (
            "The textbook treats architecture as the disciplined management of "
            "quality attributes, trade-offs, lifecycle change, and organizational value."
        ),
    },
    {
        "id": "R2",
        "title": "NIST SP 800-160 Vol. 1 Rev. 1: Engineering Trustworthy Secure Systems",
        "authors": "Ron Ross, Mark Winstead, and Michael McEvilley",
        "url": "https://csrc.nist.gov/pubs/sp/800/160/v1/r1/final",
        "summary": (
            "NIST frames trustworthiness as a whole-system engineering concern that must "
            "be addressed through requirements, architecture, implementation, verification, "
            "validation, and lifecycle evidence."
        ),
    },
    {
        "id": "R3",
        "title": "NIST SP 800-218: Secure Software Development Framework 1.1",
        "authors": "Murugiah Souppaya, Karen Scarfone, and Donna Dodson",
        "url": "https://csrc.nist.gov/pubs/sp/800/218/final",
        "summary": (
            "The Secure Software Development Framework recommends integrating secure "
            "practices into the development lifecycle and using a shared vocabulary for "
            "producers, acquirers, and reviewers."
        ),
    },
    {
        "id": "R4",
        "title": "RFC 2119 and BCP 14 requirement language",
        "authors": "Scott Bradner and the IETF",
        "url": "https://www.rfc-editor.org/info/rfc2119/",
        "summary": (
            "The RFC distinguishes absolute requirements, recommendations, and optional "
            "behaviour so readers can tell policy force from ordinary emphasis."
        ),
    },
    {
        "id": "R5",
        "title": "Engineering a Safer World: Systems Thinking Applied to Safety",
        "authors": "Nancy G. Leveson",
        "url": "https://mitpress.mit.edu/9780262016629/engineering-a-safer-world/",
        "summary": (
            "Leveson argues that complex software-intensive systems should be understood "
            "through interacting controls, constraints, feedback, and sociotechnical context "
            "rather than through isolated component failure alone."
        ),
    },
    {
        "id": "R6",
        "title": "Design and Analysis of Experiments, 10th Edition",
        "authors": "Douglas C. Montgomery",
        "url": "https://uat.store.wiley.com/en-us/design-and-analysis-of-experiments-10th-edition-p-9781119492443R150",
        "summary": (
            "Montgomery presents experimental design as a disciplined way to vary factors, "
            "measure responses, discover interactions, and draw objective engineering conclusions."
        ),
    },
    {
        "id": "R7",
        "title": "The Protection of Information in Computer Systems",
        "authors": "Jerome H. Saltzer and Michael D. Schroeder",
        "url": "https://ieeexplore.ieee.org/document/1451869",
        "summary": (
            "The classic protection principles include least privilege, fail-safe defaults, "
            "complete mediation, economy of mechanism, and explicit design rather than secrecy."
        ),
    },
    {
        "id": "R8",
        "title": "NASA Systems Engineering Handbook",
        "authors": "National Aeronautics and Space Administration",
        "url": "https://www.nasa.gov/reference/systems-engineering-handbook/",
        "summary": (
            "NASA explains systems engineering as a lifecycle discipline that connects "
            "stakeholder needs, requirements, design, implementation, verification, "
            "validation, and technical decision-making."
        ),
    },
    {
        "id": "R9",
        "title": "WAI-ARIA Authoring Practices: Developing a Keyboard Interface",
        "authors": "World Wide Web Consortium Web Accessibility Initiative",
        "url": "https://www.w3.org/WAI/ARIA/apg/practices/keyboard-interface/",
        "summary": (
            "W3C guidance explains that interactive interfaces need predictable keyboard "
            "movement, visible focus, and controls whose behaviour is understandable "
            "without relying on a mouse."
        ),
    },
    {
        "id": "R10",
        "title": "RFC 8785: JSON Canonicalization Scheme",
        "authors": "Anders Rundgren, Bruce Jordan, and Samuel Erdtman",
        "url": "https://www.rfc-editor.org/rfc/rfc8785.html",
        "summary": (
            "The RFC defines a repeatable JSON representation so hashing and signing use "
            "the same bytes even when ordinary serializers could choose different layouts."
        ),
    },
    {
        "id": "R11",
        "title": "Atomic Commit in SQLite",
        "authors": "SQLite Project",
        "url": "https://sqlite.org/atomiccommit.html",
        "summary": (
            "SQLite describes atomic commit as making a transaction appear fully applied "
            "or not applied at all, including recovery when interruption happens mid-write."
        ),
    },
    {
        "id": "R12",
        "title": "Git Internals: Git Objects",
        "authors": "Git Project",
        "url": "https://git-scm.com/book/en/v2/Git-Internals-Git-Objects",
        "summary": (
            "Git stores content-addressed objects whose identifiers depend on content, "
            "allowing snapshots and relationships to be checked rather than trusted by name."
        ),
    },
    {
        "id": "R13",
        "title": "NIST SP 800-92: Guide to Computer Security Log Management",
        "authors": "Karen Kent and Murugiah Souppaya",
        "url": "https://csrc.nist.gov/pubs/sp/800/92/final",
        "summary": (
            "NIST treats logs as evidence that must be generated, protected, reviewed, and "
            "managed across a lifecycle so events can support detection and investigation."
        ),
    },
    {
        "id": "R14",
        "title": "Python Standard Library: dataclasses",
        "authors": "Python Software Foundation",
        "url": "https://docs.python.org/3/library/dataclasses.html",
        "summary": (
            "Python documents data classes as a way to declare named fields and generate "
            "standard methods, making record structure explicit and inspectable."
        ),
    },
    {
        "id": "R15",
        "title": "RFC 8259: The JavaScript Object Notation Data Interchange Format",
        "authors": "Tim Bray and the IETF",
        "url": "https://www.rfc-editor.org/rfc/rfc8259.html",
        "summary": (
            "The RFC defines JSON as a text format for structured values and specifies the "
            "grammar needed for different implementations to exchange the same information."
        ),
    },
    {
        "id": "R16",
        "title": "NIST Technical Note 1297: Measurement Uncertainty Terminology",
        "authors": "National Institute of Standards and Technology",
        "url": "https://www.nist.gov/pml/nist-technical-note-1297/nist-tn-1297-appendix-d1-terminology",
        "summary": (
            "NIST explains uncertainty as information about the spread of values that could "
            "reasonably describe a measured result, rather than as a vague feeling of doubt."
        ),
    },
)


REFERENCE_BY_ID = {reference["id"]: reference for reference in REFERENCE_LIBRARY}


REFERENCE_KEYWORDS = {
    "R1": ("architecture", "quality", "trade-off", "component", "interface", "design"),
    "R2": ("trust", "safety", "secure", "risk", "authority", "boundary", "lifecycle"),
    "R3": ("software", "development", "test", "evidence", "vulnerability", "release"),
    "R4": ("must", "should", "may", "requirement", "normative", "policy"),
    "R5": ("control", "feedback", "collision", "system", "interaction", "constraint"),
    "R6": ("experiment", "factor", "dimension", "baseline", "variation", "response"),
    "R7": ("privilege", "permission", "access", "authorization", "deny", "capability"),
    "R8": ("verification", "validation", "requirement", "stakeholder", "engineering", "decision"),
    "R9": ("gui", "ui", "view", "keyboard", "focus", "accessibility", "interaction"),
    "R10": ("canonical", "hash", "signature", "stable", "deterministic", "json"),
    "R11": ("transaction", "atomic", "rollback", "recovery", "write", "commit"),
    "R12": ("snapshot", "content", "object", "repository", "version", "provenance"),
    "R13": ("event", "log", "audit", "trace", "record", "replay"),
    "R14": ("class", "dataclass", "field", "record", "type", "schema"),
    "R15": ("json", "serialization", "payload", "schema", "interchange", "parser"),
    "R16": ("uncertainty", "measure", "score", "information", "confidence", "estimate"),
}


REFERENCE_TOPIC_GROUPS = (
    (("transaction", "atomic", "rollback", "recovery", "migration"), ("R11", "R12", "R10", "R13", "R8")),
    (("canonical", "hash", "signature", "json", "serialization", "schema"), ("R10", "R15", "R12", "R14", "R13")),
    (("gui", "user interface", "keyboard", "focus", "accessibility", "view"), ("R9", "R1", "R8", "R5", "R2")),
    (("authority", "approval", "capability", "permission", "privilege"), ("R7", "R2", "R4", "R3", "R13")),
    (("security", "threat", "safe", "refusal", "fail closed"), ("R2", "R3", "R7", "R5", "R13")),
    (("experiment", "dimension", "baseline", "variation", "uncertainty"), ("R6", "R16", "R8", "R5", "R3")),
    (("test", "verification", "validation", "evidence", "audit", "completion"), ("R8", "R3", "R13", "R16", "R2")),
    (("event", "log", "trace", "replay", "history"), ("R13", "R12", "R10", "R2", "R8")),
    (("object", "relation", "dependency", "graph", "architecture"), ("R1", "R5", "R8", "R12", "R16")),
    (("command", "namespace", "adapter", "execution"), ("R7", "R4", "R3", "R8", "R1")),
)


GLOSSARY = {
    "ADR": "Architecture Decision Record: a short document that records a significant design choice, its context, and its consequences.",
    "API": "Application Programming Interface: a defined way for software components to request services from one another.",
    "BCP": "Best Current Practice: an Internet standards document that records widely accepted operational guidance.",
    "C0": "Capability class 0: observation only; it may inspect information but cannot create proposals or change the workspace.",
    "C1": "Capability class 1: analysis and internal proposal creation without ordinary workspace mutation.",
    "C2": "Capability class 2: simulation in a disposable, synthetic, or otherwise isolated environment.",
    "C3": "Capability class 3: local workspace mutation through the governed EON execution boundary with exact authority and approval.",
    "C4": "Capability class 4: mutation of an external system; EGCFv1 currently fails closed for this class.",
    "C5": "Capability class 5: critical or destructive mutation; EGCFv1 currently fails closed for this class.",
    "CERTIFIED": "A status label claiming that named certification checks and approvals have been satisfied; the label is trustworthy only when it is tied to current evidence.",
    "C0-C5": "The full capability-class ladder, from observation-only C0 through critical or destructive C5 operations.",
    "C2-C5": "Capability classes 2 through 5: simulation, local mutation, external mutation, and critical or destructive mutation.",
    "C3-C5": "The mutation-capable classes: governed local mutation, external mutation, and critical or destructive mutation.",
    "CAD": "Computer-Aided Design: software and data used to create or analyse engineered geometry.",
    "CFEL": "Collision, Failure, Evidence, and Learning feedback: the project loop that records meaningful failures and prevents unchanged blind retries.",
    "CLI": "Command-Line Interface: a text-based way to operate software by entering commands.",
    "DAG": "Directed Acyclic Graph: a one-way network with no cycles, often used to represent workflows and dependencies.",
    "EGCF": "Evidence-Governed Command Fabric: the semantic command layer that compiles intent into typed, content-addressed, policy-checked workflow plans.",
    "EON": "Execution and Operational Nexus: the governed boundary that binds authority, evidence, approval, exact targets, commands, and rollback before execution.",
    "GIF": "Graphics Interchange Format: a bitmap image format that can contain simple animation.",
    "GLB": "The binary container form of glTF, used to package 3D scenes and assets into one file.",
    "GLTF": "GL Transmission Format: a standard format for transmitting 3D scenes and models.",
    "GPU": "Graphics Processing Unit: a processor designed for highly parallel work such as graphics and machine-learning calculations.",
    "GUI": "Graphical User Interface: windows, controls, and visual feedback through which a person operates the system.",
    "HRT": "Human-Readable Task interpretation: the project layer that turns a request into explicit claims, assumptions, ambiguities, scope, and provenance.",
    "HTML": "HyperText Markup Language: the structural language used to describe web pages.",
    "HTTP": "Hypertext Transfer Protocol: the request-and-response protocol commonly used by web clients and servers.",
    "ID": "Identifier: a value used to name and distinguish one object from another.",
    "IEPS": "Invariant and Evidence Production System: the project namespace for generating coverage, oracles, counterexamples, mutations, and qualification evidence.",
    "IETF": "Internet Engineering Task Force: the open standards community that publishes RFC technical specifications and best-current-practice documents.",
    "IURM": "Invariant-Uncertainty-Response Modeling: the project method for defining dimensions, baselines, controlled variations, interactions, sensitivity, and minimum viable designs.",
    "JPEG": "Joint Photographic Experts Group image: a compressed bitmap format commonly used for photographs.",
    "JSON": "JavaScript Object Notation: a text format for structured data made from objects, arrays, strings, numbers, booleans, and null values.",
    "JSONL": "JSON Lines: a log-friendly format with one complete JSON value on each line.",
    "L0": "Evidence or risk level 0: the lowest project level, normally suitable for observation or automatic handling.",
    "L1": "Evidence or risk level 1: a bounded level that requires stronger policy and evidence than simple observation.",
    "L2": "Evidence or risk level 2: a higher-impact level requiring grounded evidence, counterexamples, and explicit human review unless exact authority says otherwise.",
    "L0-L2": "The project evidence or risk ladder from low-impact observation through higher-impact work requiring stronger evidence and review.",
    "LRU": "Least Recently Used: a cache policy that removes the items that have gone unused for the longest time.",
    "MCP": "Model Context Protocol: a protocol for connecting AI applications to tools and structured external context.",
    "MVD": "Minimum Viable Design: the smallest design that still satisfies the declared constraints and learning objective.",
    "NASA": "National Aeronautics and Space Administration: the United States civil space agency, which publishes systems-engineering guidance used here as a lifecycle reference.",
    "NIST": "National Institute of Standards and Technology: a United States public agency that publishes technical guidance on measurement, security, risk, and trustworthy systems.",
    "OBJ": "Wavefront OBJ: a text-based file format for polygonal 3D geometry.",
    "OFAT": "One Factor At a Time: an experiment strategy that varies one input while holding the others steady.",
    "OIEC-STM": "Operationally Isolated Epistemic Control State-Transition Model: this project's bounded control layer for deciding whether a proposed state transition may proceed.",
    "OURD": "Orthogonal Unique Relational Decomposition modeling: the project layer that identifies system objects, their boundaries, relations, dependencies, impacts, exclusions, and scope.",
    "PEP": "Python Enhancement Proposal: a design document used to propose and explain changes to Python.",
    "PLY": "Polygon File Format: a format for storing 3D meshes and point-cloud attributes.",
    "PNG": "Portable Network Graphics: a lossless bitmap image format with transparency support.",
    "PTY": "Pseudo-terminal: a software endpoint that behaves like a terminal so another program can control interactive command-line processes.",
    "RFC": "Request for Comments: a published technical specification or best-current-practice document in the Internet standards process.",
    "README": "The conventional project overview file that explains purpose, setup, usage, and important repository guidance; the name is a filename label rather than an acronym.",
    "SDK": "Software Development Kit: libraries, tools, examples, and documentation used to build software against a platform.",
    "SHA-256": "Secure Hash Algorithm 256-bit: a function that produces a fixed-size digest used here to identify and verify exact content.",
    "SQL": "Structured Query Language: a language for storing, querying, and updating relational data.",
    "SQLite": "A compact relational database engine stored in a local file rather than a separate database server.",
    "SSDF": "Secure Software Development Framework: NIST guidance for integrating secure practices into the software lifecycle.",
    "STL": "Stereolithography file format: a widely used representation of triangulated 3D surfaces.",
    "SVG": "Scalable Vector Graphics: XML-based vector artwork that can remain sharp at any size and can be manipulated with JavaScript.",
    "TCP": "Transmission Control Protocol: a reliable ordered transport protocol used by many network applications.",
    "UI": "User Interface: the controls and information through which a person interacts with a system.",
    "URL": "Uniform Resource Locator: the address used to locate a resource such as a web page or file.",
    "W3C": "World Wide Web Consortium: the standards community that develops technical and accessibility guidance for the Web.",
    "WAI-ARIA": "Web Accessibility Initiative Accessible Rich Internet Applications: W3C guidance for making interactive web controls understandable to assistive technology and keyboard users.",
    "XML": "Extensible Markup Language: a text format that represents nested structured data with named tags and attributes.",
    "X11": "The X Window System protocol commonly used to display graphical Linux applications.",
}


CONSTANT_DEFINITIONS = {
    "COUNT": "A configuration field that limits or reports how many items are involved.",
    "KEY": "A configuration field or lookup name used to select a value.",
    "MODEL": "A configuration field that names the language or reasoning model to use.",
    "SECONDS": "A duration field measured in seconds.",
    "TOKENS": "A limit expressed in model tokens, which are small units of text processed by a language model.",
}


BEGINNER_VOCABULARY = {
    "architecture": "the high-level arrangement of responsibilities, connections, and design decisions in a system",
    "artifact": "a saved result such as a file, log, report, test output, or transaction record",
    "atomic": "all-or-nothing; either the complete change is accepted or none of it remains",
    "authority": "permission granted by an allowed human or policy source, not permission invented by the software itself",
    "canonical": "the single representation treated as the official source from which other views are derived",
    "capability": "a narrowly described action that a component is permitted and technically able to perform",
    "collision": "a recorded mismatch between what the system expected and what actually happened",
    "deterministic": "producing the same result whenever the same exact inputs are supplied",
    "evidence": "recorded information that another person or program can inspect when judging a claim",
    "fail closed": "refusing the action when required permission, evidence, or state is missing or uncertain",
    "falsifiable": "written so a test or observation could show that the claim is wrong",
    "governance": "the rules that decide what may happen, who may approve it, and what proof is required",
    "hash": "a fixed-size digital fingerprint calculated from content so unexpected changes can be detected",
    "idempotent": "safe to repeat without creating an additional effect after the first successful application",
    "immutable": "not allowed to change after it has been created",
    "invariant": "a rule that must remain true while other parts of the system change",
    "lifecycle": "the sequence from planning and creation through use, change, recovery, and retirement",
    "namespace": "a named group that keeps related commands or identifiers separate from other groups",
    "projection": "a view calculated from canonical facts for a particular purpose",
    "provenance": "the trace showing where information came from and how it was produced",
    "rollback": "restoring the earlier known state after a change fails or is rejected",
    "runtime": "the period when the program is actually running rather than merely being described in source code",
    "schema": "a machine-checkable description of the fields and value shapes that a record may contain",
    "semantic": "concerned with meaning and responsibility rather than only spelling or file format",
    "serialization": "turning structured data into bytes or text that can be stored or transmitted",
    "snapshot": "a recorded view of the exact files or state at one point in time",
    "state": "the information the system currently remembers and uses to decide what happens next",
    "telemetry": "measurements and status information collected while a system operates",
    "transaction": "a bounded group of changes treated as one all-or-nothing operation",
    "uncertainty": "the explicitly recorded range of plausible explanations or values that remain unresolved",
    "validation": "checking that the finished system solves the real stakeholder need",
    "verification": "checking that an implementation satisfies a stated requirement or design rule",
}


ESSAY_LOGIC_TOPOLOGY = (
    (
        "Claim",
        (
            ("claim-proposition", "Proposition"),
            ("claim-language", "Beginner language"),
            ("claim-local-evidence", "Local evidence"),
            ("claim-reference", "Reference lens"),
            ("claim-test", "Proof question"),
        ),
    ),
    (
        "Mechanism",
        (
            ("mechanism-path", "Operating path"),
            ("mechanism-tutorial", "Trace tutorial"),
            ("mechanism-reference", "Lifecycle lens"),
            ("mechanism-objection", "Objection"),
            ("mechanism-result", "Mechanism result"),
        ),
    ),
    (
        "Proof",
        (
            ("proof-requirement", "Required evidence"),
            ("proof-method", "Proof recipe"),
            ("proof-reference", "Evidence lens"),
            ("proof-counterexample", "Counterexample"),
            ("proof-result", "Proof result"),
        ),
    ),
    (
        "Challenge",
        (
            ("challenge-defeat", "Defeat condition"),
            ("challenge-failures", "Failure stories"),
            ("challenge-reference", "Resilience lens"),
            ("challenge-tradeoff", "Trade-off"),
            ("challenge-result", "Challenge result"),
        ),
    ),
    (
        "Verdict",
        (
            ("verdict-comparison", "Evidence comparison"),
            ("verdict-principle", "Governing principle"),
            ("verdict-exercise", "Learner test"),
            ("verdict-limit", "Known limit"),
            ("verdict-winner", "Winning position"),
        ),
    ),
)


def flattened_essay_logic_nodes() -> tuple[tuple[str, str, str], ...]:
    return tuple(
        (stage, node_id, topic)
        for stage, nodes in ESSAY_LOGIC_TOPOLOGY
        for node_id, topic in nodes
    )


ESSAY_LOGIC_EDGES = tuple(
    (current[1], following[1])
    for current, following in zip(
        flattened_essay_logic_nodes(),
        flattened_essay_logic_nodes()[1:],
    )
)


def essay_logic_topological_order() -> tuple[str, ...]:
    nodes = flattened_essay_logic_nodes()
    node_ids = tuple(node_id for _, node_id, _ in nodes)
    if len(node_ids) != len(set(node_ids)):
        raise ValueError("essay logic topology contains duplicate node identifiers")

    node_set = set(node_ids)
    indegree = {node_id: 0 for node_id in node_ids}
    successors = {node_id: [] for node_id in node_ids}
    for source, target in ESSAY_LOGIC_EDGES:
        if source not in node_set or target not in node_set:
            raise ValueError("essay logic topology edge references an unknown node")
        successors[source].append(target)
        indegree[target] += 1

    ready = sorted(node_id for node_id, count in indegree.items() if count == 0)
    ordered: list[str] = []
    while ready:
        node_id = ready.pop(0)
        ordered.append(node_id)
        for target in sorted(successors[node_id]):
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
                ready.sort()

    if len(ordered) != len(node_ids):
        raise ValueError("essay logic topology must be acyclic")
    if tuple(ordered) != node_ids:
        raise ValueError("essay paragraph declaration must follow the topology order")
    return tuple(ordered)


ESSAY_LOGIC_ORDER = essay_logic_topological_order()


def essay_logic_node(block_index: int, paragraph_index: int) -> tuple[str, str, str]:
    stage, nodes = ESSAY_LOGIC_TOPOLOGY[block_index]
    node_id, topic = nodes[paragraph_index]
    return stage, node_id, topic


def logic_paragraph_id(prefix: str, node_id: str) -> str:
    return f"logic-{slugify(prefix)}-{node_id}"


def render_essay_logic_map(prefix: str) -> str:
    stages = []
    order_by_node = {
        node_id: order
        for order, node_id in enumerate(ESSAY_LOGIC_ORDER, start=1)
    }
    predecessor_by_node = {target: source for source, target in ESSAY_LOGIC_EDGES}
    successor_by_node = {source: target for source, target in ESSAY_LOGIC_EDGES}
    for stage_index, (stage, nodes) in enumerate(ESSAY_LOGIC_TOPOLOGY, start=1):
        node_markup = "".join(
            f'<li><button type="button" data-logic-target="{html.escape(logic_paragraph_id(prefix, node_id), quote=True)}" '
            f'data-logic-node="{html.escape(node_id, quote=True)}" '
            f'data-logic-order="{order_by_node[node_id]}" '
            f'data-logic-predecessor="{html.escape(predecessor_by_node.get(node_id, ""), quote=True)}" '
            f'data-logic-successor="{html.escape(successor_by_node.get(node_id, ""), quote=True)}">'
            f'<span>{order_by_node[node_id]:02d}</span>{html.escape(topic)}</button></li>'
            for node_id, topic in nodes
        )
        stages.append(
            f'<li class="logic-stage" data-logic-stage="{stage_index}"><strong>{html.escape(stage)}</strong>'
            f'<ol>{node_markup}</ol></li>'
        )
    return (
        '<figure class="essay-logic-topology" data-essay-logic-map data-logic-ordering="topological">'
        '<figcaption><span>LOGIC TOPOLOGY</span> Every paragraph topic follows this directed path from the claim to the winning position. Select any node to inspect that step and the path already completed.</figcaption>'
        f'<ol class="logic-stage-list">{"".join(stages)}</ol></figure>'
    )


def render_essay_paragraph(
    *,
    prefix: str,
    block_index: int,
    paragraph_index: int,
    paragraph: str,
    data_attribute: str,
) -> str:
    stage, node_id, topic = essay_logic_node(block_index, paragraph_index)
    paragraph_id = logic_paragraph_id(prefix, node_id)
    order = ESSAY_LOGIC_ORDER.index(node_id) + 1
    predecessor = ESSAY_LOGIC_ORDER[order - 2] if order > 1 else ""
    successor = ESSAY_LOGIC_ORDER[order] if order < len(ESSAY_LOGIC_ORDER) else ""
    return (
        f'<p id="{html.escape(paragraph_id, quote=True)}" '
        f'data-{data_attribute}="{paragraph_index + 1}" '
        f'data-logic-node="{html.escape(node_id, quote=True)}" '
        f'data-logic-stage="{html.escape(stage, quote=True)}" '
        f'data-logic-topic="{html.escape(topic, quote=True)}" '
        f'data-logic-order="{order}" '
        f'data-logic-predecessor="{html.escape(predecessor, quote=True)}" '
        f'data-logic-successor="{html.escape(successor, quote=True)}">'
        f'<span class="paragraph-topic"><strong>{html.escape(stage)}</strong>'
        f'<span>{order:02d}. {html.escape(topic)}</span></span>{paragraph}</p>'
    )


@dataclass(frozen=True)
class Section:
    level: int
    title: str
    slug: str
    markdown: str
    ordinal: int


@dataclass(frozen=True)
class Document:
    source_path: Path
    relative_path: Path
    output_path: Path
    title: str
    sections: tuple[Section, ...]


@dataclass(frozen=True)
class RelationalObject:
    object_id: str
    kind: str
    title: str
    description: str
    parent_id: str
    relation: str
    href: str
    source_key: str
    symbol_path: str
    related_ids: tuple[str, ...] = ()


def slugify(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"[`*_]", "", value)
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return value or "section"


def clean_heading(value: str) -> str:
    return re.sub(r"\s+#+\s*$", "", value).strip()


def parse_sections(text: str) -> tuple[Section, ...]:
    matches = list(re.finditer(r"^(#{1,6})\s+(.+?)\s*$", text, re.MULTILINE))
    if not matches:
        return (Section(1, "Document", "document", text.strip(), 1),)

    seen: dict[str, int] = {}
    sections: list[Section] = []
    for ordinal, match in enumerate(matches, start=1):
        title = clean_heading(match.group(2))
        base_slug = slugify(title)
        seen[base_slug] = seen.get(base_slug, 0) + 1
        slug = base_slug if seen[base_slug] == 1 else f"{base_slug}-{seen[base_slug]}"
        content_start = match.end()
        content_end = matches[ordinal].start() if ordinal < len(matches) else len(text)
        sections.append(
            Section(
                level=len(match.group(1)),
                title=title,
                slug=slug,
                markdown=text[content_start:content_end].strip(),
                ordinal=ordinal,
            )
        )
    return tuple(sections)


def discover_documents() -> tuple[Document, ...]:
    documents: list[Document] = []
    for source_path in sorted(DOCS_ROOT.rglob("*.md")):
        relative_path = source_path.relative_to(DOCS_ROOT)
        if relative_path.parts and relative_path.parts[0] in EDUCATIONAL_DIRECTORIES:
            continue
        output_path = DOCS_ROOT / relative_path.with_suffix(".html")
        sections = parse_sections(source_path.read_text(encoding="utf-8"))
        title = sections[0].title if sections else source_path.stem.replace("_", " ")
        documents.append(
            Document(source_path, relative_path, output_path, title, sections)
        )
    return tuple(documents)


def strip_markdown(value: str) -> str:
    value = re.sub(r"```.*?```", " ", value, flags=re.DOTALL)
    value = re.sub(r"`([^`]+)`", r"\1", value)
    value = re.sub(r"!\[([^]]*)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"[*_~]", "", value)
    value = re.sub(r"^\s*[-+*]\s+", "", value, flags=re.MULTILINE)
    value = re.sub(r"^\s*\d+\.\s+", "", value, flags=re.MULTILINE)
    value = value.replace("|", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def evidence_fragments(section: Section) -> tuple[str, ...]:
    fragments: list[str] = []
    in_code = False
    for raw_line in section.markdown.splitlines():
        line = raw_line.strip()
        if line.startswith("```"):
            in_code = not in_code
            continue
        if not line or re.fullmatch(r"\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?", line):
            continue
        if in_code:
            line = line.lstrip("-+>| ")
        cleaned = strip_markdown(line)
        if len(cleaned) < 12:
            continue
        if cleaned not in fragments:
            fragments.append(cleaned[:320])
        if len(fragments) == 8:
            break
    if not fragments:
        fragments.append(
            f"The source introduces {section.title} as part of the documented system architecture."
        )
    return tuple(fragments)


def select_stance(title: str, markdown: str) -> tuple[str, str]:
    haystack = f"{title} {markdown}".lower()
    if any(word in haystack for word in ("threat", "safety", "approval", "authority", "security")):
        return (
            "a trust boundary that should fail closed when authority or evidence is incomplete",
            "The strongest position is that safety and authority must be demonstrated before convenience is allowed to dominate.",
        )
    if any(word in haystack for word in ("test", "validation", "completion", "audit", "evidence")):
        return (
            "an evidence discipline that separates a plausible claim from a defensible conclusion",
            "The strongest position is that implementation, validation, approval, certification, and release are different claims and must not be collapsed.",
        )
    if any(word in haystack for word in ("migration", "recovery", "state", "replay", "persistence")):
        return (
            "a reversible lifecycle mechanism rather than a one-way data transformation",
            "The strongest position is that durable facts should remain canonical while projections stay rebuildable and migrations remain reversible.",
        )
    if any(word in haystack for word in ("gui", "view", "selection", "renderer", "event")):
        return (
            "a human-facing projection that must improve comprehension without bypassing governance",
            "The strongest position is that usability is an assurance aid only when visual controls preserve the same authority and identity contracts as the core.",
        )
    if any(word in haystack for word in ("command", "capability", "namespace", "adapter")):
        return (
            "a least-privilege semantic contract rather than a convenient alias for arbitrary execution",
            "The strongest position is that commands should state intent, scope, evidence, and authority before any executor is selected.",
        )
    return (
        "an architectural decision that must make responsibilities, evidence, and consequences inspectable",
        "The strongest position is that a system becomes trustworthy through explicit boundaries and reviewable evidence, not through naming or implementation volume alone.",
    )


def section_concepts(section: Section) -> tuple[str, ...]:
    tokens = set(re.findall(r"\b[A-Z][A-Z0-9.-]{1,14}\b", f"{section.title}\n{section.markdown}"))
    concepts = [token.strip(".-") for token in tokens]
    concepts = [token for token in concepts if token in GLOSSARY or token in CONSTANT_DEFINITIONS]
    return tuple(sorted(set(concepts)))


def concept_plain_language(section: Section) -> str:
    concepts = section_concepts(section)
    if concepts:
        token = concepts[0]
        return f"{token} means {definition_for(token).lower()}"
    noun = re.sub(r"[^A-Za-z0-9 ]", "", section.title).strip().lower()
    return (
        f"the phrase {noun!r} names the responsibility, rule, or architectural boundary "
        "that this part of the documentation asks the reader to inspect"
    )


def definition_for(token: str) -> str:
    return GLOSSARY.get(token) or CONSTANT_DEFINITIONS.get(token) or (
        "A project-specific identifier whose exact meaning is established by the source "
        "sentence and the surrounding governance contract."
    )


def topic_reference_ids(text: str, limit: int = 5) -> tuple[str, ...]:
    haystack = strip_markdown(text).casefold()
    group_scores = []
    for group_index, (keywords, reference_ids) in enumerate(REFERENCE_TOPIC_GROUPS):
        score = sum(
            1
            for keyword in keywords
            if re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", haystack)
        )
        if score:
            group_scores.append((-score, group_index, reference_ids))
    group_scores.sort()
    selected = []
    for _, _, reference_ids in group_scores:
        for reference_id in reference_ids:
            if reference_id not in selected:
                selected.append(reference_id)
            if len(selected) == limit:
                return tuple(selected)

    ranked = []
    for reference_id, keywords in REFERENCE_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword in haystack)
        ranked.append((reference_id, score))
    ranked.sort(key=lambda item: (-item[1], item[0]))
    for reference_id, score in ranked:
        if score > 0 and reference_id not in selected:
            selected.append(reference_id)
        if len(selected) == limit:
            return tuple(selected)
    for fallback in ("R1", "R8", "R2", "R3", "R4"):
        if len(selected) == limit:
            break
        if fallback not in selected:
            selected.append(fallback)
    return tuple(selected)


def reference_lens(reference_id: str) -> str:
    reference = REFERENCE_BY_ID[reference_id]
    return html.escape(reference["summary"])


def detected_acronyms(text: str) -> tuple[str, ...]:
    tokens = re.findall(r"\b[A-Z][A-Z0-9]*(?:[-.][A-Z0-9]+)*\b", text)
    ignored = {"A", "I", "MUST", "SHOULD", "MAY"}
    return tuple(
        sorted(
            {
                token.strip(".-")
                for token in tokens
                if token not in ignored and len(token.strip(".-")) > 1
            }
        )
    )


def beginner_entries(text: str) -> tuple[tuple[str, str], ...]:
    entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for token in detected_acronyms(text):
        normalized = token.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        entries.append((token, definition_for(token)))
    lowered = strip_markdown(text).casefold()
    for term, definition in BEGINNER_VOCABULARY.items():
        if len(entries) >= len(detected_acronyms(text)) + 8:
            break
        if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", lowered):
            normalized = term.casefold()
            if normalized not in seen:
                seen.add(normalized)
                entries.append((term, definition))
    return tuple(entries)


def beginner_explanation(text: str) -> str:
    entries = beginner_entries(text)
    if not entries:
        return (
            "No specialist abbreviation is required for this claim. The important words "
            "are used in their ordinary sense, and the lesson explains each system rule "
            "before asking the reader to judge it."
        )
    explanations = "; ".join(
        f"<strong>{html.escape(term)}</strong> means {html.escape(definition).rstrip('.')}"
        for term, definition in entries
    )
    return f"The specialist language used here is defined before the argument continues: {explanations}."


SOURCE_STOPWORDS = {
    "about", "after", "again", "also", "another", "because", "before", "being",
    "body", "conclusion", "final", "introduction", "introductory", "movement",
    "between", "cannot", "could", "does", "each", "from", "have", "into", "more",
    "must", "only", "other", "section", "should", "that", "their", "there", "these", "this",
    "through", "under", "using", "when", "where", "which", "while", "with", "without",
}


def source_keywords(fragment: str, limit: int = 5) -> tuple[str, ...]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9_.-]{2,}", strip_markdown(fragment))
    candidates = []
    seen = set()
    for word in words:
        normalized = word.casefold().strip(".-")
        if normalized in SOURCE_STOPWORDS or normalized in seen:
            continue
        seen.add(normalized)
        candidates.append(word.strip(".-"))
    candidates.sort(key=lambda item: (-len(item), item.casefold()))
    return tuple(candidates[:limit])


def paraphrase_source_point(section: Section, fragment_index: int) -> str:
    fragments = evidence_fragments(section)
    fragment = fragments[min(fragment_index, len(fragments) - 1)]
    keywords = source_keywords(fragment)
    if keywords:
        topic_list = ", ".join(html.escape(keyword) for keyword in keywords)
        return (
            f"The checked-in source connects {html.escape(section.title)} with {topic_list}. "
            "In plain terms, it presents these as a concrete rule, responsibility, record, "
            "or limit that can be inspected rather than as a slogan."
        )
    return (
        f"The checked-in source presents {html.escape(section.title)} as a specific system "
        "responsibility. In plain terms, the heading is evidence of an intended boundary, "
        "but runtime tests are still needed to prove that the boundary is enforced."
    )


def citation(reference_id: str) -> str:
    return f'<a class="citation-chip" href="#ref-{reference_id}">[{reference_id}]</a>'


def _legacy_generate_essay_blocks(document: Document, section: Section) -> tuple[tuple[str, ...], ...]:
    evidence = evidence_fragments(section)
    e1 = html.escape(evidence[0])
    e2 = html.escape(evidence[min(1, len(evidence) - 1)])
    e3 = html.escape(evidence[min(2, len(evidence) - 1)])
    e4 = html.escape(evidence[min(3, len(evidence) - 1)])
    stance, thesis = select_stance(section.title, section.markdown)
    stance_html = html.escape(stance)
    thesis_html = html.escape(thesis)
    plain = html.escape(concept_plain_language(section))
    title = html.escape(section.title)
    document_title = html.escape(document.title)
    source_ref = citation("S1")
    architecture_ref = citation("R1")
    systems_ref = citation("R2")
    secure_ref = citation("R3")
    language_ref = citation("R4")

    blocks = (
        (
            f"This lesson argues that <strong>{title}</strong> should be understood as {stance_html}. {thesis_html} The claim is grounded first in the local document {source_ref} and then tested against systems-architecture and trustworthy-systems guidance {architecture_ref} {systems_ref}.",
            f"For a reader without specialist training, {plain}. That plain-language definition matters because technical labels can otherwise create the illusion of understanding while hiding who may act, what may change, and how a result is checked. The educational goal is therefore to connect the label to observable responsibilities rather than ask the reader to memorise vocabulary.",
            f"The first source observation is: <q>{e1}</q> {source_ref} This statement supplies evidence because it identifies a concrete rule, component, relationship, or limitation rather than merely praising the design. An architect should ask what artifact, test, event, or immutable identifier would prove that the statement remains true in a running system.",
            f"A useful systems-architecture point of view is that structure exists to protect quality attributes such as modifiability, security, usability, availability, and testability {architecture_ref}. From that perspective, <strong>{title}</strong> is valuable only if its boundary makes at least one quality attribute easier to reason about. The design should be challenged whenever the boundary adds ceremony without improving a measurable property.",
            f"The introductory conclusion is that <strong>{title}</strong> deserves attention because it turns an implicit assumption into an inspectable design claim. The local evidence supports that interpretation, while the external references warn that a trustworthy claim must survive lifecycle change and independent review {systems_ref}. The next body section therefore tests how the mechanism works rather than accepting the heading as self-validating.",
        ),
        (
            f"The first body movement examines mechanism. The source adds: <q>{e2}</q> {source_ref} Read as an argument, this evidence says that responsibility is intentionally placed somewhere specific, and that placement should reduce ambiguity about which component owns a decision.",
            f"A beginner can analyse the mechanism with a five-step tutorial: identify the input, name the component that owns the rule, trace the permitted transformation, locate the recorded evidence, and inspect the failure path. Applying those steps to <strong>{title}</strong> converts a diagram into a falsifiable explanation. If any step has no answer, the architecture description is incomplete even when the implementation appears to work.",
            f"The textbook lens reinforces this method because architecture is not only a list of modules; it is a set of decisions that shape system qualities and trade-offs {architecture_ref}. The local source is strongest where it connects a component to a constraint or recovery action. It is weakest where a component is named without an observable contract.",
            f"A reasonable counterargument is that explicit boundaries, identifiers, and evidence records can slow development. That objection is important because governance can become performative if every low-risk action receives the same ceremony as a destructive one. The answer is proportionality: capability classes, risk levels, budgets, and scoped evidence should make simple work inexpensive while preserving hard gates for consequential work.",
            f"This body section concludes that the mechanism is justified when it reduces uncertainty more than it increases process cost. The evidence around <strong>{title}</strong> points toward an explicit owner and inspectable path, which is preferable to hidden coupling. However, the conclusion remains provisional until tests and runtime artifacts demonstrate that the described path is the path actually used.",
        ),
        (
            f"The second body movement examines evidence quality. A further source statement reads: <q>{e3}</q> {source_ref} The relevant question is not whether the statement sounds precise, but whether another person can reproduce the observation from a named source snapshot, command, event stream, or content hash.",
            f"NIST's systems-security guidance treats trustworthiness as an engineering outcome supported across requirements, architecture, implementation, verification, validation, and operation {systems_ref}. In plain language, no single screenshot, test, or approval can prove the entire lifecycle. Evidence must match the exact claim it is being used to support.",
            f"The Secure Software Development Framework similarly recommends integrating security practices into the development lifecycle rather than adding them after implementation {secure_ref}. Applied here, that means <strong>{title}</strong> should expose evidence during ordinary work: inputs, authority, decisions, outputs, failures, and rollback facts. A separate audit performed after source drift cannot restore a broken chain of provenance.",
            f"Try a classroom exercise: write the claim about <strong>{title}</strong> on one card, write each supporting artifact on separate cards, and draw an arrow only when the artifact directly proves the claim. Remove arrows based only on chronology, naming similarity, or confidence. The remaining graph reveals both real support and missing evidence.",
            f"The evidence conclusion is that local documentation provides a reasoned hypothesis, not automatic certification. Its point of view is persuasive where exact boundaries and records are described, and less persuasive where current runtime proof is absent. A careful reader should preserve that distinction rather than convert educational explanation into a release claim.",
        ),
        (
            f"The third body movement examines consequences and trade-offs. The source states: <q>{e4}</q> {source_ref} This evidence matters because an architectural choice is defined partly by what it prevents, delays, exposes, or makes recoverable—not only by the successful path it enables.",
            f"Requirement words must also be read carefully. Under BCP 14, words such as MUST, SHOULD, and MAY communicate different levels of obligation rather than different levels of enthusiasm {language_ref}. When <strong>{title}</strong> uses normative language, the reader should look for the authority and verification method that give that language operational force.",
            f"A systems architect should test at least three failure stories: the input is stale, the authority is incomplete, and the projection is corrupted. For each story, ask whether the system fails closed, records the reason, preserves canonical facts, and offers a bounded recovery path. This tutorial turns abstract resilience into scenarios that can become deterministic tests.",
            f"The principal trade-off is between local speed and global comprehensibility. Hidden shortcuts may complete one task quickly but increase the cost of review, recovery, delegation, and future change. Explicit contracts may feel slower at first, yet they can lower total system risk by preventing incompatible interpretations from accumulating.",
            f"This body section concludes that the design should favour reversible, observable decisions over irreversible convenience. The evidence supports that position when <strong>{title}</strong> names both the successful path and the refusal or recovery path. Where only success is documented, the educational conclusion is to add failure evidence before increasing authority.",
        ),
        (
            f"The final conclusion returns to the thesis: <strong>{title}</strong> is best treated as {stance_html}. The local source provides concrete architectural evidence {source_ref}, while the reference material supplies broader criteria for quality attributes, lifecycle trustworthiness, secure development, and precise requirement language {architecture_ref} {systems_ref} {secure_ref} {language_ref}.",
            f"The evidence-based point of view is not that governance is always good or that more documentation is always safer. The stronger claim is narrower: explicit ownership, bounded authority, reproducible evidence, and reversible recovery make consequential actions easier to understand and challenge. Those properties justify complexity only when they are actually enforced.",
            f"For a practical tutorial, a learner should now open the source-evidence panel, choose one sentence, identify its subject and verb, find the corresponding code or schema owner, and design one test that could disprove it. Next, the learner should inspect the interactive SVG and follow the path from claim to evidence to boundary to decision. This exercise transforms passive reading into architecture review.",
            f"The remaining limitation is provenance. This generated lesson explains and argues from checked-in documentation, but it does not independently certify that historical reports still match the current source or runtime. Exact-snapshot validation, human approval, and release decisions remain separate activities that require current artifacts.",
            f"The final judgement is therefore conditional but clear: retain <strong>{title}</strong> when it strengthens traceability, proportional authority, and recovery; revise it when it merely renames hidden coupling. That conclusion follows from the source evidence and the referenced systems literature rather than from visual style or rhetorical confidence. The reader should leave with both a position and a method for testing that position.",
        ),
    )
    assert all(len(block) == 5 for block in blocks)
    return blocks


def generate_essay_blocks(document: Document, section: Section) -> tuple[tuple[str, ...], ...]:
    stance, thesis = select_stance(section.title, section.markdown)
    stance_html = html.escape(stance)
    thesis_html = html.escape(thesis)
    title = html.escape(section.title)
    document_title = html.escape(document.title)
    source_ref = citation("S1")
    reference_ids = topic_reference_ids(
        f"{document.title}\n{section.title}\n{section.markdown}",
    )
    refs = [citation(reference_id) for reference_id in reference_ids]
    lenses = [reference_lens(reference_id) for reference_id in reference_ids]
    reference_language = "\n".join(
        f"{REFERENCE_BY_ID[reference_id]['title']} {REFERENCE_BY_ID[reference_id]['summary']}"
        for reference_id in reference_ids
    )
    vocabulary = beginner_explanation(
        f"{document.title}\n{section.title}\n{section.markdown}\n{stance}\n{thesis}\n{reference_language}",
    )

    blocks = (
        (
            f"<strong>Claim to prove:</strong> <strong>{title}</strong> should be treated as {stance_html}. {thesis_html} The claim matters inside <strong>{document_title}</strong> because a named feature is useful only when its responsibility, limits, and proof can be inspected {source_ref}.",
            vocabulary,
            f"{paraphrase_source_point(section, 0)} {source_ref} This is local evidence of intended design, not automatic proof that the running program obeys the design.",
            f"A clearly relevant external lens says, in paraphrased form, that {lenses[0]} {refs[0]} Applied to <strong>{title}</strong>, the reference asks whether the claimed boundary improves an observable system quality rather than merely adding another name.",
            f"The question that can prove or defeat the claim is simple: can a beginner trace one input, one responsible owner, one permitted result, and one refusal path for <strong>{title}</strong>? If any part is missing, the claim remains unproved.",
        ),
        (
            f"<strong>How the proposed mechanism works:</strong> {paraphrase_source_point(section, 1)} {source_ref} The practical idea is to make responsibility visible enough that another person can follow it without guessing hidden state.",
            f"A beginner can trace the mechanism in five steps: name the incoming information, identify the component that owns the rule, describe the allowed change, locate the saved evidence, and identify what happens when the rule is not satisfied. These steps turn <strong>{title}</strong> into a checkable explanation.",
            f"The matched reference explains, in paraphrased wording, that {lenses[1]} {refs[1]} This supports the mechanism only if the repository exposes those lifecycle links in code, records, tests, or schemas.",
            f"The strongest challenge is that explicit controls can slow simple work. That challenge wins whenever the control adds paperwork but no safer decision. The claim survives only when the control is proportional: low-impact work remains inexpensive, while consequential work receives stronger checks.",
            f"The mechanism is provisionally supported when it replaces hidden coupling with an explicit owner and a visible path. It is weakened when the name exists but the implementation cannot show where the decision is made.",
        ),
        (
            f"<strong>What evidence would prove the claim:</strong> {paraphrase_source_point(section, 2)} {source_ref} Evidence is useful only when a different reader can inspect how it was produced and what it does not cover.",
            f"Use this proof recipe: write the claim in one sentence, record the exact source snapshot, run the smallest test that could fail, save the observed result, and state the known gap. A result without those links is information, but it is not strong proof.",
            f"The topic-matched guidance says, in paraphrased form, that {lenses[2]} {refs[2]} For <strong>{title}</strong>, that means proof should be designed with the rule instead of being attached after the implementation is finished.",
            f"A passing test can still mislead when it covers only one path or one machine. The honest response is to bind the result to exact inputs, preserve counterexamples, name uncovered cases, and rerun the check after relevant source changes.",
            f"The claim gains support when its evidence is reproducible, source-bound, and limited to what was actually observed. It loses support when prose, old reports, or a successful demonstration are treated as universal certification.",
        ),
        (
            f"<strong>What could defeat the claim:</strong> {paraphrase_source_point(section, 3)} {source_ref} A design must be judged by the failures it contains and exposes, not only by the successful path shown in a diagram.",
            f"Test three beginner-friendly failure stories: the input is old, permission is missing, and saved state is damaged. For each story, ask whether the system refuses unsafe work, records the reason, protects the official facts, and offers a bounded recovery route.",
            f"The relevant reference adds, in paraphrased wording, that {lenses[3]} {refs[3]} This makes refusal, recovery, and review part of the topic rather than optional details.",
            f"The main trade-off is local speed against system-wide understanding. A shortcut may finish one task quickly while making review, recovery, delegation, and later change more expensive. An explicit rule earns its cost only when it lowers that wider risk.",
            f"The stronger side of the argument favours reversible and observable decisions. If <strong>{title}</strong> documents only success, the claim is not ready to win; failure evidence must be added before the system receives broader authority.",
        ),
        (
            f"<strong>How the evidence compares:</strong> the local source gives the project-specific claim {source_ref}; the matched references contribute architecture, lifecycle, security, measurement, interface, or data rules that fit this topic {refs[0]} {refs[1]} {refs[2]} {refs[3]} {refs[4]}.",
            f"The argument does not say that more governance or more documentation is automatically better. It says that explicit ownership, bounded permission, reproducible proof, and recoverable change are better than hidden assumptions when the action can affect important work.",
            f"A learner can test this position now: open the source panel, choose one rule, identify the code or schema that owns it, and design one observation that would show the rule is false. Then follow the interactive diagram from claim to evidence to boundary to decision.",
            f"The limit of this lesson is clear. Generated teaching text does not certify runtime behaviour, historical reports, human approval, or release readiness. Those claims need fresh evidence from the exact current snapshot.",
            f"<strong>The winning position is to retain {title} as {stance_html}</strong> when it creates a traceable owner, proportional authority, reproducible evidence, and a recovery path; otherwise the winning choice is to revise or remove it. This verdict follows from the tested claim and the topic-matched references, not from confident wording or visual polish.",
        ),
    )
    assert all(len(block) == 5 for block in blocks)
    return blocks


def inline_markdown(value: str) -> str:
    escaped = html.escape(value, quote=False)
    code_fragments: list[str] = []

    def save_code(match: re.Match[str]) -> str:
        code_fragments.append(f"<code>{match.group(1)}</code>")
        return f"\x00CODE{len(code_fragments) - 1}\x00"

    escaped = re.sub(r"`([^`]+)`", save_code, escaped)
    escaped = re.sub(r"\[([^]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", escaped)
    for index, fragment in enumerate(code_fragments):
        escaped = escaped.replace(f"\x00CODE{index}\x00", fragment)
    return escaped


def render_markdown(markdown: str) -> str:
    if not markdown.strip():
        return '<p class="source-empty">No additional source text appears beneath this heading.</p>'

    lines = markdown.splitlines()
    output: list[str] = []
    index = 0
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            joined = " ".join(part.strip() for part in paragraph)
            output.append(f"<p>{inline_markdown(joined)}</p>")
            paragraph.clear()

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped.startswith("```"):
            flush_paragraph()
            language = stripped[3:].strip() or "text"
            index += 1
            code_lines: list[str] = []
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code_lines.append(lines[index])
                index += 1
            output.append(
                f'<pre data-language="{html.escape(language)}"><code>{html.escape(chr(10).join(code_lines))}</code></pre>'
            )
            index += 1
            continue

        if stripped.startswith("|") and index + 1 < len(lines):
            delimiter = lines[index + 1].strip()
            if re.fullmatch(r"\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?", delimiter):
                flush_paragraph()
                table_lines = [line]
                index += 2
                while index < len(lines) and lines[index].strip().startswith("|"):
                    table_lines.append(lines[index])
                    index += 1
                rows = [[cell.strip() for cell in row.strip().strip("|").split("|")] for row in table_lines]
                header_cells = "".join(f"<th>{inline_markdown(cell)}</th>" for cell in rows[0])
                body_rows = "".join(
                    "<tr>" + "".join(f"<td>{inline_markdown(cell)}</td>" for cell in row) + "</tr>"
                    for row in rows[1:]
                )
                output.append(
                    f'<div class="table-scroll"><table><thead><tr>{header_cells}</tr></thead><tbody>{body_rows}</tbody></table></div>'
                )
                continue

        unordered = re.match(r"^\s*[-+*]\s+(.+)$", line)
        ordered = re.match(r"^\s*\d+\.\s+(.+)$", line)
        if unordered or ordered:
            flush_paragraph()
            tag = "ul" if unordered else "ol"
            items: list[str] = []
            pattern = r"^\s*[-+*]\s+(.+)$" if unordered else r"^\s*\d+\.\s+(.+)$"
            while index < len(lines):
                match = re.match(pattern, lines[index])
                if not match:
                    break
                items.append(f"<li>{inline_markdown(match.group(1))}</li>")
                index += 1
            output.append(f"<{tag}>{''.join(items)}</{tag}>")
            continue

        if not stripped:
            flush_paragraph()
            index += 1
            continue

        paragraph.append(line)
        index += 1

    flush_paragraph()
    return "\n".join(output)


def render_glossary(section: Section) -> str:
    entries = beginner_entries(f"{section.title}\n{section.markdown}")
    if not entries:
        return (
            '<div class="glossary-empty">This section uses ordinary architecture language; '
            "specialist terms are explained in the essay and source evidence.</div>"
        )
    markup = []
    for term, definition in entries:
        markup.append(
            f'<div class="glossary-entry"><dt>{html.escape(term)}</dt>'
            f'<dd>{html.escape(definition)}</dd></div>'
        )
    return f"<dl class=\"glossary-grid\">{''.join(markup)}</dl>"


def relative_url(from_path: Path, to_path: Path) -> str:
    return Path(os.path.relpath(to_path, from_path.parent)).as_posix()


def render_references(document: Document) -> str:
    source_url = relative_url(document.output_path, document.source_path)
    items = [
        (
            '<li id="ref-S1"><span class="reference-id">S1</span>'
            f'<a href="{html.escape(source_url)}">{html.escape(document.relative_path.as_posix())}</a>'
            "<p>The checked-in Markdown is the primary local evidence. Its claims remain subject "
            "to current-source validation and exact-snapshot review.</p></li>"
        )
    ]
    reference_ids = []
    for section in document.sections:
        for reference_id in topic_reference_ids(
            f"{document.title}\n{section.title}\n{section.markdown}",
        ):
            if reference_id not in reference_ids:
                reference_ids.append(reference_id)
    for reference_id in reference_ids:
        reference = REFERENCE_BY_ID[reference_id]
        items.append(
            f'<li id="ref-{reference["id"]}"><span class="reference-id">{reference["id"]}</span>'
            f'<a href="{html.escape(reference["url"])}" rel="noreferrer">{html.escape(reference["title"])}</a>'
            f'<p><strong>{html.escape(reference["authors"])}</strong> — {html.escape(reference["summary"])}</p></li>'
        )
    return f'<ol class="reference-list">{"".join(items)}</ol>'


def concept_citations(concept: Concept) -> tuple[str, ...]:
    return topic_reference_ids(
        "\n".join(
            (
                concept.title,
                concept.category,
                concept.definition,
                concept.thesis,
                concept.central_question,
                concept.inputs,
                concept.controls,
                concept.evidence,
                concept.outcome,
                " ".join(concept.related),
            )
        )
    )


def _legacy_generate_concept_essay_blocks(concept: Concept) -> tuple[tuple[str, ...], ...]:
    title = html.escape(concept.title)
    definition = html.escape(concept.definition)
    thesis = html.escape(concept.thesis)
    question = html.escape(concept.central_question)
    inputs = html.escape(concept.inputs)
    controls = html.escape(concept.controls)
    evidence = html.escape(concept.evidence)
    outcome = html.escape(concept.outcome)
    related = ", ".join(html.escape(item) for item in concept.related) or "the surrounding governed architecture"
    reference_ids = concept_citations(concept)
    refs = [citation(reference_id) for reference_id in reference_ids]
    blocks = (
        (
            f"<strong>{title}</strong> means {definition[0].lower() + definition[1:] if definition else definition} The architectural position of this lesson is explicit: {thesis} That position is tested against the checked-in source and broader systems guidance {refs[0]} {refs[1]}.",
            f"For an unqualified reader, the central question is: <q>{question}</q> The question matters because software names often sound explanatory while leaving ownership, authority, inputs, and proof unstated. A useful concept must tell the reader what responsibility exists and how to inspect it.",
            f"The repository evidence locates this concept in {html.escape(', '.join(concept.sources))}. Those files are treated as source evidence rather than as automatic certification because current runtime behaviour may still diverge from prose or type names. The first learning habit is therefore to connect the concept to its canonical owner before accepting its description.",
            f"A systems-architecture textbook lens treats a concept as significant when it shapes quality attributes, constraints, interfaces, or lifecycle decisions {refs[0]}. <strong>{title}</strong> is therefore not included merely because it has a class or namespace name. It is included because it changes how the agent understands, authorizes, records, executes, verifies, or learns from engineering work.",
            f"The introductory conclusion is that <strong>{title}</strong> deserves a distinct place in the architecture when its responsibility cannot be safely merged into another owner. Its relationship to {related} should be explicit rather than inferred from chronology or naming similarity. The next body section examines the mechanism that makes the concept operational.",
        ),
        (
            f"The first body movement begins with inputs: {inputs} Inputs matter because a deterministic boundary can only govern facts that are represented explicitly. Hidden ambient state weakens review because a later reader cannot reconstruct why the concept behaved as it did.",
            f"The controlling rules are: {controls} These controls turn the concept from an informal convention into an architectural contract. When one of these controls is absent, the safer conclusion is that the concept is advisory or incomplete rather than fully governed.",
            f"The systems-safety point of view is that accidents and failures in complex software-intensive systems often emerge from inadequate constraints and feedback across interacting components, not merely from one broken part {refs[2]}. Applied here, <strong>{title}</strong> should make its upstream assumptions and downstream effects visible. That visibility allows reviewers to reason about the loop rather than inspect a component in isolation.",
            f"A counterargument is that separate records, services, and controls increase architecture surface area. That concern is valid when the concept duplicates a fact already owned elsewhere. The rebuttal is canonical ownership: retain one authoritative representation, compute derivatives with provenance, and remove labels that do not create a distinct review or enforcement boundary.",
            f"This body section concludes that the mechanism is justified only when its inputs and controls reduce ambiguity. <strong>{title}</strong> should either expose a clear contract or be folded into the concept that actually owns the fact. Architecture diagrams must not preserve decorative boxes that the implementation cannot distinguish.",
        ),
        (
            f"The second body movement asks what evidence the concept produces: {evidence} Evidence is stronger than description because it allows another person or process to repeat, compare, or falsify a claim. The evidence must still be bound to the exact source state and limitations that produced it.",
            f"A practical tutorial has five steps: open the listed source file, find the public type or catalog entry, identify the fields or verbs it owns, trace one caller, and locate the event, record, or test that proves the path. If the trace stops at a label with no producing code or artifact, mark the concept as a documentation hypothesis. Do not silently promote it to an implemented guarantee.",
            f"Secure-development guidance recommends integrating security and verification into ordinary lifecycle work rather than treating them as a final inspection {refs[2]}. For <strong>{title}</strong>, that means evidence should be emitted where the concept acts, not reconstructed later from memory. A source-bound record is more defensible than a retrospective narrative.",
            f"Requirement language also needs precision. Words such as MUST, SHOULD, and MAY have different normative force, so a concept page should not use them as decorative emphasis {refs[3]}. If <strong>{title}</strong> is mandatory, the source should identify the enforcement mechanism and the deterministic test that fails when it is bypassed.",
            f"The evidence conclusion is conditional: the source inventory shows that <strong>{title}</strong> is represented, but representation alone does not prove current correctness. The concept becomes persuasive when its owner, inputs, controls, artifacts, and refusal paths align. That alignment is the evidence-based point of view used throughout this atlas.",
        ),
        (
            f"The third body movement examines the outcome: {outcome} An architectural outcome should be observable and bounded, not merely described as progress. It should also feed a known next step rather than leave unowned state between components.",
            f"The related concepts are {related}. Treat these relationships as hypotheses to verify through typed IDs, function calls, stored references, workflow edges, or tests. Correlation, adjacent filenames, and similar names do not establish an authority or provenance link.",
            f"Least-privilege design argues that a component should receive only the authority needed for its responsibility, while fail-safe defaults deny action when permission is missing {refs[4]}. For <strong>{title}</strong>, this means its successful outcome must not quietly broaden the scope of later components. Authority transfer should be explicit, exact, and usually absent.",
            f"Another counterargument is that a strongly bounded outcome can make adaptation slower. The answer is not to remove the boundary but to make change a first-class lifecycle operation: supersede records, recompile plans, generate new evidence, or obtain new approval. Controlled change is different from hidden mutation.",
            f"This body section concludes that <strong>{title}</strong> belongs in the architecture when its output is both useful and accountable. A reviewer should be able to say what changed, why it changed, which rule permitted it, what evidence resulted, and what happens next. If those questions cannot be answered, the concept needs redesign rather than stronger rhetoric.",
        ),
        (
            f"The final conclusion returns to the thesis: {thesis} The local source establishes the concept's intended role, while the reference lenses provide criteria for architecture, trustworthy systems, lifecycle security, feedback, experiments, and protection {refs[0]} {refs[1]} {refs[2]} {refs[3]} {refs[4]}.",
            f"The strongest argument for <strong>{title}</strong> is not that the repository contains code with that name. The stronger argument is that the concept gives one semantic fact a canonical owner and makes its controls and evidence inspectable. That is the difference between a vocabulary list and an architecture.",
            f"For a final tutorial, write the concept name in the centre of a page and draw five boxes labelled purpose, inputs, controls, evidence, and outcome. Populate them from the interactive SVG, then challenge every arrow with a source reference or deterministic test. Remove any arrow supported only by intuition.",
            f"The remaining limitation is that this educational page is generated from the current source tree, catalog, and documentation. It does not independently certify runtime behaviour, historical evidence, release state, or human approval. Those claims require fresh validation against an exact snapshot.",
            f"The final evidence-based judgement is to retain <strong>{title}</strong> when it reduces uncertainty, clarifies authority, or preserves provenance; otherwise merge or remove it. The concept atlas therefore treats architecture as a set of testable responsibilities rather than a museum of names. That point of view is consistent with the repository's broader separation between model intelligence and mutation authority.",
        ),
    )
    assert all(len(block) == 5 for block in blocks)
    return blocks


def generate_concept_essay_blocks(concept: Concept) -> tuple[tuple[str, ...], ...]:
    title = html.escape(concept.title)
    definition = html.escape(concept.definition)
    thesis = html.escape(concept.thesis)
    question = html.escape(concept.central_question)
    inputs = html.escape(concept.inputs)
    controls = html.escape(concept.controls)
    evidence = html.escape(concept.evidence)
    outcome = html.escape(concept.outcome)
    sources = html.escape(", ".join(concept.sources))
    related = ", ".join(html.escape(item) for item in concept.related) or "the surrounding governed architecture"
    reference_ids = concept_citations(concept)
    refs = [citation(reference_id) for reference_id in reference_ids]
    lenses = [reference_lens(reference_id) for reference_id in reference_ids]
    reference_language = "\n".join(
        f"{REFERENCE_BY_ID[reference_id]['title']} {REFERENCE_BY_ID[reference_id]['summary']}"
        for reference_id in reference_ids
    )
    vocabulary = beginner_explanation(
        "\n".join(
            (
                concept.title,
                concept.definition,
                concept.thesis,
                concept.inputs,
                concept.controls,
                concept.evidence,
                concept.outcome,
                reference_language,
            )
        )
    )

    blocks = (
        (
            f"<strong>Claim to prove:</strong> <strong>{title}</strong> deserves a separate place in the architecture because {definition} The position being tested is: {thesis}",
            vocabulary,
            f"The checked-in owners are {sources} {citation('S1')}. In plain terms, these files show where the concept is represented and which part of the repository is expected to maintain it. A name in source code proves representation, but not correct runtime behaviour.",
            f"The first matched reference says, in paraphrased form, that {lenses[0]} {refs[0]} This is relevant because <strong>{title}</strong> should be judged by the system responsibility it clarifies, not by how impressive its name sounds.",
            f"The claim can be tested by answering this question without specialist knowledge: <q>{question}</q> If the answer cannot identify an owner, a rule, and observable proof, the concept has not yet justified its separate existence.",
        ),
        (
            f"<strong>How the concept receives information:</strong> {inputs} An input is simply information available before a decision. Listing inputs prevents the system from quietly depending on hidden files, ambient settings, or assumptions.",
            f"<strong>How the concept is controlled:</strong> {controls} A control is a rule that limits what may happen. These rules are what turn <strong>{title}</strong> from an informal idea into a responsibility that can be reviewed.",
            f"The topic-matched guidance explains, in paraphrased wording, that {lenses[1]} {refs[1]} The concept therefore needs visible links from its inputs to its controls and onward to a bounded result.",
            f"A reasonable challenge is that another named concept may already own the same fact. That challenge should win when duplication creates two competing sources of truth. The safer design keeps one official owner and derives other views with provenance.",
            f"The mechanism is supported when a beginner can follow the path from input to rule to result without guessing. It is unsupported when the diagram shows a box but the implementation cannot distinguish that box from its neighbours.",
        ),
        (
            f"<strong>What proof the concept should produce:</strong> {evidence} Proof is stronger than description because another reviewer can repeat the observation, compare it with the claim, and discover a disagreement.",
            f"Use this beginner proof recipe: locate the owning source, identify one declared rule, run or inspect the smallest check that could fail, save the observed result, and write down the limitation. This method keeps a successful example from becoming an exaggerated claim.",
            f"The relevant reference adds, in paraphrased form, that {lenses[2]} {refs[2]} For <strong>{title}</strong>, evidence should therefore identify exact inputs, exact state, and the rule used to interpret the result.",
            f"A counterexample is especially valuable because it shows a case where the claim does not hold. If new evidence conflicts with earlier evidence, the architecture should record the conflict instead of deleting the inconvenient observation.",
            f"The proof case is strongest when evidence is reproducible, source-bound, and honest about coverage. It is weakest when a class name, a diagram, or an old report is treated as proof by itself.",
        ),
        (
            f"<strong>What result the concept is supposed to create:</strong> {outcome} A result should state what changed, what remained unchanged, and which component may use the result next.",
            f"The nearest related ideas are {related}. A relation means that the concepts exchange information or constrain one another; it does not mean they are interchangeable or that one automatically proves the other.",
            f"The matched reference says, in paraphrased wording, that {lenses[3]} {refs[3]} This makes lifecycle, recovery, accessibility, security, data form, or measurement part of the result whenever those topics are relevant.",
            f"The strongest opposing case is unnecessary complexity. If <strong>{title}</strong> produces no unique decision, evidence, refusal, or reusable record, merging it with the true owner is clearer and safer than preserving a decorative abstraction.",
            f"The concept survives this challenge only when its output is both useful and accountable. A reviewer must be able to explain what it adds that no neighbouring concept already owns.",
        ),
        (
            f"<strong>How the evidence compares:</strong> the repository sources establish the intended project meaning {citation('S1')}, while the topic-matched references supply wider criteria that fit this concept {refs[0]} {refs[1]} {refs[2]} {refs[3]} {refs[4]}.",
            f"The argument for <strong>{title}</strong> is not that software architecture needs more names. The argument is that one semantic fact needs one visible owner, explicit controls, and evidence that can be challenged.",
            f"A learner can test the concept with a five-box sketch labelled purpose, inputs, controls, evidence, and outcome. Fill each box from this page, then remove every arrow that lacks a source link or a deterministic check.",
            f"This educational page cannot certify live behaviour, historical reports, approval, or release readiness. It is a source-derived explanation whose claims still require current runtime evidence from an exact snapshot.",
            f"<strong>The winning position is to retain {title}</strong> when it reduces uncertainty, owns a distinct responsibility, limits authority, or preserves provenance; otherwise the winning position is to merge or remove it. That verdict chooses the clearer testable architecture over a larger vocabulary.",
        ),
    )
    assert all(len(block) == 5 for block in blocks)
    return blocks


def concept_source_references(concept: Concept, output_path: Path) -> str:
    items = []
    for index, source in enumerate(concept.sources, start=1):
        source_path = ROOT / source
        source_url = relative_url(output_path, source_path)
        items.append(
            f'<li id="ref-S{index}"><span class="reference-id">S{index}</span>'
            f'<a href="{html.escape(source_url)}">{html.escape(source)}</a>'
            '<p>Checked-in local source used to discover and define this concept. The source is evidence of representation, not automatic runtime certification.</p></li>'
        )
    for reference_id in concept_citations(concept):
        reference = REFERENCE_BY_ID[reference_id]
        items.append(
            f'<li id="ref-{reference["id"]}"><span class="reference-id">{reference["id"]}</span>'
            f'<a href="{html.escape(reference["url"])}" rel="noreferrer">{html.escape(reference["title"])}</a>'
            f'<p><strong>{html.escape(reference["authors"])}</strong> — {html.escape(reference["summary"])}</p></li>'
        )
    return f'<ol class="reference-list">{"".join(items)}</ol>'


def concept_page_template(
    concept: Concept,
    previous: Concept | None,
    following: Concept | None,
    build_date: str,
) -> str:
    teaching = teaching_record_for(concept)
    output_path = DOCS_ROOT / "concepts" / f"{concept.slug}.html"
    styles_url = relative_url(output_path, DOCS_ROOT / "assets" / "styles.css")
    script_url = relative_url(output_path, DOCS_ROOT / "assets" / "site.js")
    docs_index_url = relative_url(output_path, DOCS_ROOT / "index.html")
    atlas_url = relative_url(output_path, DOCS_ROOT / "concepts" / "index.html")
    figure_path = DOCS_ROOT / "figures" / "concepts" / f"{concept.slug}.svg"
    figure_url = relative_url(output_path, figure_path)
    blocks = generate_concept_essay_blocks(concept)
    block_markup = []
    labels = ("Claim to prove", "How it works", "What proves it", "What could defeat it", "Winning position")
    for block_index, block in enumerate(blocks):
        heading = f"<h3>{html.escape(concept.title)}</h3>" if block_index == 0 else ""
        paragraphs = "".join(
            render_essay_paragraph(
                prefix=concept.slug,
                block_index=block_index,
                paragraph_index=paragraph_index,
                paragraph=paragraph,
                data_attribute="concept-paragraph",
            )
            for paragraph_index, paragraph in enumerate(block)
        )
        block_markup.append(
            f'<section class="essay-block essay-block-{block_index + 1}" aria-label="{labels[block_index]}">'
            f"{heading}{paragraphs}</section>"
        )
    previous_link = (
        f'<a class="pager-link previous" href="{html.escape(previous.slug)}.html">← {html.escape(previous.title)}</a>'
        if previous
        else '<span class="pager-link disabled">Start of concept atlas</span>'
    )
    next_link = (
        f'<a class="pager-link next" href="{html.escape(following.slug)}.html">{html.escape(following.title)} →</a>'
        if following
        else '<span class="pager-link disabled">End of concept atlas</span>'
    )
    source_list = "".join(
        f'<li><code>{html.escape(source)}</code></li>' for source in concept.sources
    )
    related_list = "".join(f"<li>{html.escape(item)}</li>" for item in concept.related)
    prerequisite_list = "".join(
        f'<li><a href="{html.escape(item)}.html">{html.escape(item)}</a></li>'
        for item in teaching.prerequisites
    ) or "<li>No concept prerequisite.</li>"
    teaching_sources = "".join(
        f'<li><code>{html.escape(source)}</code></li>' for source in teaching.source_links
    )
    cli_examples = command_cards(teaching.cli_examples)
    digest = hashlib.sha256(
        "\n".join(
            hashlib.sha256((ROOT / source).read_bytes()).hexdigest()
            for source in teaching.source_links
        ).encode("utf-8")
    ).hexdigest()
    return f"""<!doctype html>
<html lang="en" data-doc-view="learn" data-doc-depth="novice">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Systems architecture concept essay and infographic for {html.escape(concept.title, quote=True)}">
  <title>{html.escape(concept.title)} · OIEC-STM Concept Atlas</title>
  <link rel="stylesheet" href="{styles_url}">
</head>
<body data-page="concept" data-concept="{html.escape(concept.slug)}" data-source-hash="{digest}" {page_snapshot_attributes(build_date)}>
  <div class="scanline-overlay" aria-hidden="true"></div>
  <div class="reading-progress" aria-hidden="true"><span></span></div>
  <header class="site-header">
    <a class="brand" href="{docs_index_url}"><span class="brand-mark">OS</span><span><strong>OIEC-STM CONCEPT ATLAS</strong><small>{html.escape(concept.category)}</small></span></a>
    <nav class="header-actions"><button type="button" data-action="focus-mode">FOCUS</button><a href="{atlas_url}">ATLAS</a><a href="{docs_index_url}">INDEX</a></nav>
  </header>
  <main class="concept-main">
    {view_controls()}
    <section class="concept-hero">
      <p class="eyebrow">CONCEPT CIRCUIT · BUILT {html.escape(build_date)}</p>
      <span class="concept-category">{html.escape(concept.category)}</span>
      <h1>{html.escape(concept.title)}</h1>
      <p class="concept-definition">{html.escape(concept.definition)}</p>
      <p class="concept-thesis">{html.escape(concept.thesis)}</p>
      <dl class="hero-metrics"><div><dt>SOURCES</dt><dd>{len(concept.sources):02d}</dd></div><div><dt>ESSAY PARAGRAPHS</dt><dd>25</dd></div><div><dt>RELATED CONCEPTS</dt><dd>{len(concept.related):02d}</dd></div></dl>
    </section>
    <article class="concept-teaching" data-view-content="learn" data-authorship="{html.escape(teaching.authorship, quote=True)}">
      <div class="teaching-heading"><div><p class="terminal-label">LEARN VIEW · {html.escape(teaching.authorship.upper())}</p><h2>{html.escape(teaching.full_name)}</h2><p class="lead">{html.escape(teaching.short_meaning)}</p></div>{evidence_badge(teaching.documentation_status, teaching.status_evidence)}</div>
      <section class="teaching-grid"><article><h3>Why it exists</h3><p>{html.escape(teaching.why_it_exists)}</p></article><article><h3>Everyday analogy</h3><p>{html.escape(teaching.everyday_analogy)}</p></article><article><h3>OIEC example</h3><p>{html.escape(teaching.oiec_example)}</p></article><article class="misconception"><h3>This does not mean…</h3><p>{html.escape(teaching.misconception)}</p></article><article><h3>Input</h3><p>{html.escape(teaching.inputs)}</p></article><article><h3>Output</h3><p>{html.escape(teaching.outputs)}</p></article><article><h3>Failure example</h3><p>{html.escape(teaching.failure_example)}</p></article><article><h3>Before this page</h3><ul>{prerequisite_list}</ul></article></section>
      <section class="formalism-levels"><article data-depth-content="novice"><h3>Novice explanation</h3><p>{html.escape(teaching.formal_novice)}</p></article><article data-depth-content="intermediate"><h3>Intermediate explanation</h3><p>{html.escape(teaching.formal_intermediate)}</p></article><article data-depth-content="expert"><h3>Expert explanation</h3><p>{html.escape(teaching.formal_expert)}</p></article></section>
      <section><h3>Direct CLI examples</h3><div class="command-grid">{cli_examples}</div></section>
      <section class="source-bridge"><h3>Show me where this lives</h3><p>Start with these simplified source owners, then open the Technical view for the complete claim-and-evidence essay.</p><ul>{teaching_sources}</ul></section>
    </article>
    <div data-view-content="technical">
    <section class="map-panel concept-map-panel">
      <div><p class="terminal-label">INTERACTIVE INFOGRAPHIC</p><h2>Concept control map</h2><p>Select purpose, inputs, controls, evidence, or outcome to inspect the concept as a systems boundary.</p></div>
      <figure><object class="concept-map" type="image/svg+xml" data="{figure_url}"><a href="{figure_url}">Open the {html.escape(concept.title)} SVG</a></object><figcaption class="concept-map-caption">Select an SVG node to inspect its source-derived explanation.</figcaption></figure>
    </section>
    <section class="concept-facts">
      <article><h2>Central question</h2><p>{html.escape(concept.central_question)}</p></article>
      <article><h2>Related concepts</h2><ul>{related_list}</ul></article>
      <article><h2>Source owners</h2><ul>{source_list}</ul></article>
    </section>
    <article class="concept-essay"><p class="terminal-label">CLAIM-AND-EVIDENCE LEARNING ESSAY</p>{render_essay_logic_map(concept.slug)}<div class="essay-sequence">{''.join(block_markup)}</div></article>
    <section class="references" id="references"><p class="terminal-label">SOURCE AND REFERENCE BUS</p><h2>Topic-matched references in beginner wording</h2><p>Local entries show where the concept is represented. External entries were selected because their subjects match this concept; every summary is a teaching paraphrase of the linked source.</p>{concept_source_references(concept, output_path)}</section>
    </div>
    <nav class="document-pager" aria-label="Previous and next concepts">{previous_link}{next_link}</nav>
  </main>
  <div class="pixel-crew" aria-hidden="true"></div>
  <script src="{script_url}" defer></script>
</body>
</html>
"""


def concept_atlas_template(concepts: tuple[Concept, ...], build_date: str) -> str:
    categories = sorted({concept.category for concept in concepts})
    namespace_count = sum(
        concept.category == "Semantic Command Namespaces" for concept in concepts
    )
    runtime_count = len(concepts) - len(CORE_CONCEPTS) - namespace_count
    filters = "".join(
        f'<button type="button" class="concept-filter" data-concept-category="{html.escape(category.lower(), quote=True)}">{html.escape(category)} <span>{sum(1 for concept in concepts if concept.category == category)}</span></button>'
        for category in categories
    )
    cards = "".join(
        f'<article class="concept-card" data-category="{html.escape(concept.category.lower(), quote=True)}" data-search="{html.escape((concept.title + " " + concept.category + " " + concept.definition + " " + " ".join(concept.related)).lower(), quote=True)}">'
        f'<span class="concept-card-index">{index:03d}</span><p>{html.escape(concept.category)}</p><h2>{html.escape(concept.title)}</h2><p>{html.escape(concept.definition)}</p>'
        f'<a href="{html.escape(concept.slug)}.html">OPEN CLAIM + LOGIC MAP →</a></article>'
        for index, concept in enumerate(concepts, start=1)
    )
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="description" content="Beginner-readable OIEC-STM-Agent claim and concept atlas"><title>OIEC-STM Claim and Concept Atlas</title><link rel="stylesheet" href="../assets/styles.css"></head>
<body data-page="concept-atlas" {page_snapshot_attributes(build_date)}>
  <div class="scanline-overlay" aria-hidden="true"></div>
  <header class="site-header"><a class="brand" href="../index.html"><span class="brand-mark">OS</span><span><strong>OIEC-STM CONCEPT ATLAS</strong><small>{len(concepts)} source-derived concepts</small></span></a><nav class="header-actions"><button type="button" data-action="focus-mode">FOCUS</button><a href="../index.html">INDEX.HTML</a></nav></header>
  <main class="atlas-main">
    <section class="atlas-hero"><div><p class="eyebrow">SOURCE-DERIVED CLAIM INVENTORY · {html.escape(build_date)}</p><h1>Every concept begins as a claim that must earn its place.</h1><p>This atlas searches the governed loop, {namespace_count} semantic namespaces, and {runtime_count} public runtime types. Each page defines unfamiliar language, matches references to the concept's actual topic, and maps 25 paragraph topics from proposition through evidence and challenge to a winning position.</p></div><object class="atlas-map" type="image/svg+xml" data="../figures/concept-atlas.svg"><a href="../figures/concept-atlas.svg">Open the concept atlas SVG</a></object></section>
    <section class="atlas-controls"><label for="concept-search">SEARCH CONCEPTS<input id="concept-search" type="search" placeholder="authority, workflow, collision..."></label><div class="concept-filters"><button type="button" class="concept-filter is-active" data-concept-category="all">ALL <span>{len(concepts)}</span></button>{filters}</div><p class="concept-search-status" role="status" aria-live="polite">{len(concepts)} CONCEPTS ONLINE</p></section>
    <section class="concept-grid">{cards}</section>
  </main>
  <div class="pixel-crew" aria-hidden="true"></div><script src="../assets/site.js" defer></script>
</body></html>
"""


def governed_loop_hero(concept_count: int, build_date: str) -> str:
    return f"""
<section class="loop-hero" id="governed-loop">
  <div class="loop-hero-grid">
    <div class="loop-hero-copy">
      <p class="eyebrow">GOVERNED REASONING-TO-ACTION LOOP · {html.escape(build_date)}</p>
      <h1>Understand.<br>Experiment.<br>Act.<br><span>Learn.</span></h1>
      <p class="loop-lead">In OIEC-STM-Agent, OURD, IURM, EON, and CFEL are not isolated algorithms. They form a closed systems-architecture loop that turns human intent into an exact, evidence-gated action and then turns reality's response into a better problem model.</p>
      <div class="pipeline-banner"><span>HRTv1</span><b>→</b><span>OURD</span><b>→</b><span>IURMv1.1.1</span><b>→</b><span>EONv1</span><b>→</b><span>EVIDENCE GATE</span><b>→</b><span>ACTION</span><b>→</b><span>CFEL</span></div>
      <blockquote>The language model may reason and propose, but it cannot grant itself authority, lower deterministic risk, approve unsupported evidence, or certify its own work.</blockquote>
      <div class="hero-actions"><a class="primary-action" href="#loop-systems">EXPLORE THE LOOP</a><a href="concepts/index.html">OPEN {concept_count} CONCEPT INFOGRAPHICS</a></div>
    </div>
    <figure class="loop-map-figure">
      <object class="governed-loop-map" type="image/svg+xml" data="figures/governed-loop.svg"><a href="figures/governed-loop.svg">Open the governed reasoning-loop SVG</a></object>
      <figcaption class="loop-console">SELECT OURD, IURM, EON, OR CFEL TO TRACE ITS ROLE.</figcaption>
    </figure>
  </div>

  <div class="loop-system-grid" id="loop-systems">
    <article class="loop-system-card" data-loop-system="ourd" tabindex="0">
      <span>01 / MAP THE TERRITORY</span><h2>OURD</h2>
      <p><strong>Central question:</strong> What actually belongs to this problem, how is it related, and which boundaries make a candidate legitimate?</p>
      <p>OURD constructs a semantic graph of objects, relationships, dependencies, goals, exclusions, and unresolved uncertainty. In plain language, it prevents the agent from confusing the task with the first implementation idea that comes to mind.</p>
      <div class="equation-panel"><code>O = (V, E, B, G, U)</code><small>objects · edges · boundaries · goals · uncertainty</small></div>
      <p>A parser regression therefore becomes a map of parser, tokenizer, grammar tests, abstract syntax tree, callers, compatibility constraints, and uncertain causes—not an immediate command to edit one file.</p>
      <p class="card-conclusion">The evidence-based position is that decomposition is valuable when it exposes canonical owners and falsifiable relations. OURD is the agent's map of the territory, not permission to alter it.</p>
    </article>
    <article class="loop-system-card" data-loop-system="iurm" tabindex="0">
      <span>02 / ISOLATE THE VARIABLE</span><h2>IURM</h2>
      <p><strong>Central question:</strong> Which meaningful dimension should change, what must remain invariant, and what response would reduce uncertainty?</p>
      <p>IURM turns the OURD problem map into controlled experiments. It defines dimensions, a baseline, candidate values, interactions, sensitivity, and a minimum viable design so the system can learn causally rather than perturb everything at once.</p>
      <div class="equation-panel"><code>x(i) = baseline + δi</code><small>move one discriminating dimension while controlling the rest</small></div>
      <p>For a parser, tokenization, precedence, scope, and abstract-syntax-tree generation become separate dimensions. A tutorial experiment changes one factor, reruns the same evidence gate, and compares quality, regressions, cost, and invariant satisfaction.</p>
      <p class="card-conclusion">The evidence-based position is that variation is useful only when the comparison can teach us why an outcome changed. IURM is the experimental microscope of the loop.</p>
    </article>
    <article class="loop-system-card" data-loop-system="eon" tabindex="0">
      <span>03 / BIND THE EXACT ACTION</span><h2>EON</h2>
      <p><strong>Central question:</strong> What exact operation is proposed, against which exact source state, under whose authority, with which tests and rollback?</p>
      <p>EON is the transactional membrane between cognition and mutation. It binds authority hash, source snapshot, target set, candidate hash, canonical command arguments, capabilities, invariants, evidence, risk, expiry, and use count into one stale-detecting identity.</p>
      <div class="equation-panel"><code>ID(A) = H(S ∥ T ∥ HC ∥ P ∥ I ∥ R)</code><small>change a bound fact and the action identity changes</small></div>
      <p>Change the patch, command arguments, targets, or source repository and the earlier action is no longer the same proposal. Immutable candidate transactions are staged before the action crosses the evidence gate.</p>
      <p class="card-conclusion">The evidence-based position is that execution should be exact, proportional, and reviewable. EON is not the agent's will; it is the governed boundary that may permit one specific effect.</p>
    </article>
    <article class="loop-system-card" data-loop-system="cfel" tabindex="0">
      <span>04 / LEARN FROM COLLISION</span><h2>CFEL</h2>
      <p><strong>Central question:</strong> What did reality contradict, and what genuinely new evidence justifies a revised hypothesis or another attempt?</p>
      <p>CFEL records collisions between expected and observed outcomes. It blocks unchanged failed tool calls, bounds revised-evidence retries, disables automatic high-risk retries, and feeds the discrepancy back into the semantic model.</p>
      <div class="equation-panel"><code>M(t+1) = F(Mt, At, Ot, Ct)</code><small>revise the model from action, observation, and collision</small></div>
      <p>A failed parser test is not an invitation to repeat the same assumption with different prose. It becomes evidence linked to the attempted action, current source, failure fingerprint, and next discriminating experiment.</p>
      <p class="card-conclusion">The evidence-based position is that failure creates value only when it changes the next model or action. CFEL is the epistemic feedback loop that prevents blind retry.</p>
    </article>
  </div>

  <section class="loop-synthesis">
    <div><p class="terminal-label">SYSTEMS ARCHITECT POINT OF VIEW</p><h2>The agent is an uncertainty-reduction machine.</h2></div>
    <div class="loop-synthesis-copy">
      <p>The strongest conceptual feature is the separation of reasoning power from mutation power. The model can inspect, explain, propose records, author candidates, generate tests, and analyse collisions; deterministic code remains authoritative for scope, risk, evidence sufficiency, approval, execution, rollback, certification, and release.</p>
      <div class="formal-loop"><code>Pt → OURD → Rt → IURM → Xt → EON → At → Gate → Ot → CFEL → P(t+1)</code></div>
      <p>That loop suggests a measurable architectural objective: uncertainty should decrease only when evidence increases. A new action should differ from a failed action because the model, candidate, experiment, or evidence changed—not because the explanation became more confident.</p>
      <table><thead><tr><th>System</th><th>Central question</th><th>Produces</th></tr></thead><tbody><tr><td>OURD</td><td>What belongs to the problem?</td><td>Relational problem model</td></tr><tr><td>IURM</td><td>What should vary to learn?</td><td>Controlled candidate experiment</td></tr><tr><td>EON</td><td>What exactly may execute?</td><td>Immutable governed action</td></tr><tr><td>CFEL</td><td>What did reality teach?</td><td>Collision evidence and revised hypothesis</td></tr></tbody></table>
      <p class="synthesis-conclusion">The conclusion is conditional but strong: model intelligence becomes useful engineering capability only when multiplied by bounded authority and evidence quality. The architecture should therefore be judged by uncertainty reduction, provenance, refusal quality, rollback, and convergence—not by how quickly it emits code.</p>
    </div>
  </section>
</section>
"""


def render_lesson(document: Document, section: Section) -> str:
    blocks = generate_essay_blocks(document, section)
    block_markup: list[str] = []
    labels = ("Claim to prove", "How it works", "What proves it", "What could defeat it", "Winning position")
    for block_index, block in enumerate(blocks):
        heading = f"<h3>{html.escape(section.title)}</h3>" if block_index == 0 else ""
        paragraphs = "".join(
            render_essay_paragraph(
                prefix=section.slug,
                block_index=block_index,
                paragraph_index=paragraph_index,
                paragraph=paragraph,
                data_attribute="essay-paragraph",
            )
            for paragraph_index, paragraph in enumerate(block)
        )
        block_markup.append(
            f'<section class="essay-block essay-block-{block_index + 1}" '
            f'aria-label="{labels[block_index]}">{heading}{paragraphs}</section>'
        )

    points = list(evidence_fragments(section)[:4])
    while len(points) < 4:
        points.append(f"Inspect {section.title} through the documented architecture boundary.")
    diagram_data = html.escape(json.dumps(points), quote=True)
    source_html = render_markdown(section.markdown)
    return f"""
<section class="lesson" id="{html.escape(section.slug)}" data-original-level="{section.level}">
  <header class="lesson-header">
    <span class="lesson-index">MODULE {section.ordinal:02d}</span>
    <h2>{html.escape(section.title)}</h2>
    <p class="lesson-thesis">{html.escape(select_stance(section.title, section.markdown)[1])}</p>
  </header>
  <figure class="interactive-figure section-diagram" data-title="{html.escape(section.title, quote=True)}" data-points="{diagram_data}">
    <div class="diagram-stage" aria-label="Interactive claim, evidence, boundary, and decision diagram"></div>
    <figcaption>Select a node to inspect how this section turns a claim into an architectural decision.</figcaption>
  </figure>
  {render_essay_logic_map(section.slug)}
  <div class="essay-sequence">{''.join(block_markup)}</div>
  <details class="source-evidence">
    <summary>Inspect original Markdown evidence</summary>
    <div class="source-content">{source_html}</div>
  </details>
  <details class="concept-lab">
    <summary>Beginner concept and acronym lab</summary>
    {render_glossary(section)}
  </details>
</section>
"""


def navigation_items(document: Document) -> str:
    items = []
    for section in document.sections:
        indent = max(0, section.level - 1)
        items.append(
            f'<li style="--toc-depth:{indent}"><a href="#{html.escape(section.slug)}">'
            f'<span>{section.ordinal:02d}</span>{html.escape(section.title)}</a></li>'
        )
    return "".join(items)


def document_template(document: Document, previous: Document | None, following: Document | None, build_date: str) -> str:
    styles_url = relative_url(document.output_path, DOCS_ROOT / "assets" / "styles.css")
    script_url = relative_url(document.output_path, DOCS_ROOT / "assets" / "site.js")
    index_url = relative_url(document.output_path, DOCS_ROOT / "index.html")
    source_url = relative_url(document.output_path, document.source_path)
    figure_path = DOCS_ROOT / "figures" / document.relative_path.with_suffix(".svg")
    figure_url = relative_url(document.output_path, figure_path)
    previous_link = (
        f'<a class="pager-link previous" href="{relative_url(document.output_path, previous.output_path)}">← {html.escape(previous.title)}</a>'
        if previous
        else '<span class="pager-link disabled">Start of tree</span>'
    )
    next_link = (
        f'<a class="pager-link next" href="{relative_url(document.output_path, following.output_path)}">{html.escape(following.title)} →</a>'
        if following
        else '<span class="pager-link disabled">End of tree</span>'
    )
    digest = hashlib.sha256(document.source_path.read_bytes()).hexdigest()
    lessons = "\n".join(render_lesson(document, section) for section in document.sections)
    learn_cards = "".join(
        f'<article><span>{section.ordinal:02d}</span><h2>{html.escape(section.title)}</h2><p>{html.escape(concept_plain_language(section))}</p><a href="#{html.escape(section.slug, quote=True)}">Open technical lesson →</a></article>'
        for section in document.sections
    )
    breadcrumb_parts = ["docs", *document.relative_path.parts]
    breadcrumbs = " / ".join(html.escape(part) for part in breadcrumb_parts)
    return f"""<!doctype html>
<html lang="en" data-doc-view="learn" data-doc-depth="novice">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Systems architecture learning edition of {html.escape(document.title, quote=True)}">
  <title>{html.escape(document.title)} · OIEC-STM Systems Architect Academy</title>
  <link rel="stylesheet" href="{styles_url}">
</head>
<body data-page="document" data-source-hash="{digest}" {page_snapshot_attributes(build_date)}>
  <div class="scanline-overlay" aria-hidden="true"></div>
  <div class="reading-progress" aria-hidden="true"><span></span></div>
  <header class="site-header">
    <a class="brand" href="{index_url}" aria-label="Return to documentation index">
      <span class="brand-mark">OA</span>
      <span><strong>OIEC-STM ARCHITECT ACADEMY</strong><small>Evidence before authority</small></span>
    </a>
    <nav class="header-actions" aria-label="Document controls">
      <button type="button" data-action="focus-mode">FOCUS</button>
      <button type="button" data-action="collapse-evidence">EVIDENCE</button>
      <a href="{source_url}">MARKDOWN</a>
    </nav>
  </header>
  <div class="document-shell">
    <aside class="document-sidebar">
      <div class="sidebar-panel">
        <p class="terminal-label">DOC TREE / {breadcrumbs}</p>
        <a class="back-link" href="{index_url}">← INDEX.HTML</a>
        <label class="toc-search-label" for="toc-search">FILTER MODULES</label>
        <input id="toc-search" class="toc-search" type="search" placeholder="TYPE TO FILTER">
        <ol class="toc-list">{navigation_items(document)}</ol>
      </div>
    </aside>
    <main class="document-main">
      {view_controls()}
      <section class="document-hero">
        <p class="eyebrow">SYSTEMS ARCHITECT LEARNING EDITION · BUILT {html.escape(build_date)}</p>
        <h1>{html.escape(document.title)}</h1>
        <p>This page preserves the checked-in source while turning every heading into a beginner-readable claim that must earn support from local evidence, topic-matched references, counterexamples, and a decisive verdict.</p>
        <dl class="hero-metrics">
          <div><dt>MODULES</dt><dd>{len(document.sections):02d}</dd></div>
          <div><dt>ESSAY PARAGRAPHS</dt><dd>{len(document.sections) * 25}</dd></div>
          <div><dt>SOURCE SHA-256</dt><dd>{digest[:12]}</dd></div>
        </dl>
      </section>
      <section class="document-learn-overview" data-view-content="learn"><div class="teaching-heading"><div><p class="terminal-label">LEARN VIEW</p><h2>Plain-language map of this source</h2><p>Use these short explanations first. Switch to Technical for the complete source-bound essays, references, and logic maps.</p></div>{evidence_badge('Implemented', (document.relative_path.as_posix(),))}</div><div class="learning-card-grid">{learn_cards}</div></section>
      <div data-view-content="technical">
      <section class="map-panel" aria-labelledby="map-title">
        <div>
          <p class="terminal-label">INTERACTIVE DOCUMENT CIRCUIT</p>
          <h2 id="map-title">Architecture map</h2>
          <p>Select a module in the SVG to jump to its lesson. Keyboard users can tab through diagram nodes.</p>
        </div>
        <object class="document-map" type="image/svg+xml" data="{figure_url}">
          <a href="{figure_url}">Open the document architecture SVG</a>
        </object>
      </section>
      <article class="lesson-stack">{lessons}</article>
      <section class="references" id="references">
        <p class="terminal-label">REFERENCE BUS</p>
        <h2>References and summarised textbook lenses</h2>
        <p>These summaries are paraphrases for teaching. Follow the links for the authoritative source text.</p>
        {render_references(document)}
      </section>
      </div>
      <nav class="document-pager" aria-label="Previous and next documents">{previous_link}{next_link}</nav>
    </main>
  </div>
  <div class="pixel-crew" aria-hidden="true"></div>
  <script src="{script_url}" defer></script>
</body>
</html>
"""


def category_for(document: Document) -> str:
    name = document.relative_path.as_posix().lower()
    if name.startswith("adr/"):
        return "Architecture Decisions"
    if "gui" in name:
        return "GUI Workbench"
    if "threat" in name or "safety" in name:
        return "Safety and Threats"
    if "reference" in name or "command" in name:
        return "Command Fabric"
    if "audit" in name or "requirement" in name or "testing" in name:
        return "Evidence and Assurance"
    return "Lifecycle and Migration"


def relational_object_id(kind: str, source_key: str) -> str:
    digest = hashlib.sha256(f"{kind}\0{source_key}".encode("utf-8")).hexdigest()[:12]
    readable = slugify(source_key)[:42].rstrip("-") or kind
    return f"rel-{kind}-{readable}-{digest}"


def relational_symbol_path(object_id: str) -> str:
    return f"figures/relational-objects/{object_id}.svg"


def build_relational_objects(
    documents: tuple[Document, ...],
    concepts: tuple[Concept, ...],
) -> tuple[RelationalObject, ...]:
    root_id = relational_object_id("root", "docs/index.html")
    categories = sorted({category_for(document) for document in documents})
    folders = sorted(
        {
            document.relative_path.parts[0]
            for document in documents
            if len(document.relative_path.parts) > 1
        }
    )
    category_ids = {
        category: relational_object_id("category", category)
        for category in categories
    }
    folder_ids = {
        folder: relational_object_id("folder", folder)
        for folder in folders
    }
    document_ids = {
        document.relative_path.as_posix(): relational_object_id(
            "document", document.relative_path.as_posix()
        )
        for document in documents
    }
    heading_ids = {
        (document.relative_path.as_posix(), section.slug): relational_object_id(
            "heading", f"{document.relative_path.as_posix()}#{section.slug}"
        )
        for document in documents
        for section in document.sections
    }
    concept_ids = {
        concept.slug: relational_object_id("concept", concept.slug)
        for concept in concepts
    }
    concept_name_ids: dict[str, str] = {}
    for concept in concepts:
        concept_name_ids[concept.slug.casefold()] = concept_ids[concept.slug]
        concept_name_ids[concept.title.casefold()] = concept_ids[concept.slug]
        concept_name_ids[concept.title.split(":", 1)[0].strip().casefold()] = concept_ids[
            concept.slug
        ]

    objects: list[RelationalObject] = [
        RelationalObject(
            object_id=root_id,
            kind="root",
            title="OIEC-STM Documentation System",
            description=(
                "The invariant root of the generated documentation universe and the "
                "canonical parent for architecture domains, source folders, and concepts."
            ),
            parent_id="",
            relation="root",
            href="index.html",
            source_key="docs/index.html",
            symbol_path=relational_symbol_path(root_id),
        )
    ]

    for category in categories:
        category_id = category_ids[category]
        member_count = sum(category_for(document) == category for document in documents)
        objects.append(
            RelationalObject(
                object_id=category_id,
                kind="category",
                title=category,
                description=f"Architecture domain containing {member_count} source documents.",
                parent_id=root_id,
                relation="partitions",
                href=f"#category-{slugify(category)}",
                source_key=category,
                symbol_path=relational_symbol_path(category_id),
            )
        )

    for folder in folders:
        folder_id = folder_ids[folder]
        member_ids = tuple(
            document_ids[document.relative_path.as_posix()]
            for document in documents
            if document.relative_path.parts[0] == folder
        )
        objects.append(
            RelationalObject(
                object_id=folder_id,
                kind="folder",
                title=f"{folder}/",
                description=f"Source folder indexing {len(member_ids)} generated documents.",
                parent_id=root_id,
                relation="indexes-source",
                href="#source-folders",
                source_key=folder,
                symbol_path=relational_symbol_path(folder_id),
                related_ids=member_ids,
            )
        )

    for document in documents:
        source_key = document.relative_path.as_posix()
        document_id = document_ids[source_key]
        related_ids = ()
        if len(document.relative_path.parts) > 1:
            related_ids = (folder_ids[document.relative_path.parts[0]],)
        objects.append(
            RelationalObject(
                object_id=document_id,
                kind="document",
                title=document.title,
                description=(
                    f"Generated learning document with {len(document.sections)} heading "
                    f"objects in the {category_for(document)} domain."
                ),
                parent_id=category_ids[category_for(document)],
                relation="contains-document",
                href=document.relative_path.with_suffix(".html").as_posix(),
                source_key=source_key,
                symbol_path=relational_symbol_path(document_id),
                related_ids=related_ids,
            )
        )
        for section in document.sections:
            heading_id = heading_ids[(source_key, section.slug)]
            related_concepts = []
            for token in section_concepts(section):
                matched_id = concept_name_ids.get(token.casefold())
                if matched_id and matched_id not in related_concepts:
                    related_concepts.append(matched_id)
            objects.append(
                RelationalObject(
                    object_id=heading_id,
                    kind="heading",
                    title=section.title,
                    description=(
                        f"Level {section.level} learning object derived from heading "
                        f"{section.ordinal} in {source_key}."
                    ),
                    parent_id=document_id,
                    relation="decomposes-into",
                    href=f"{document.relative_path.with_suffix('.html').as_posix()}#{section.slug}",
                    source_key=f"{source_key}#{section.slug}",
                    symbol_path=relational_symbol_path(heading_id),
                    related_ids=tuple(related_concepts),
                )
            )

    for concept in concepts:
        concept_id = concept_ids[concept.slug]
        related_ids = []
        for related in concept.related:
            matched_id = concept_name_ids.get(related.casefold())
            if matched_id and matched_id != concept_id and matched_id not in related_ids:
                related_ids.append(matched_id)
        objects.append(
            RelationalObject(
                object_id=concept_id,
                kind="concept",
                title=concept.title,
                description=concept.definition,
                parent_id=root_id,
                relation="defines-concept",
                href=f"concepts/{concept.slug}.html",
                source_key=concept.slug,
                symbol_path=relational_symbol_path(concept_id),
                related_ids=tuple(related_ids),
            )
        )

    return tuple(objects)


def relational_record(relational_object: RelationalObject) -> dict[str, object]:
    return {
        "object_id": relational_object.object_id,
        "kind": relational_object.kind,
        "title": relational_object.title,
        "description": relational_object.description,
        "parent_id": relational_object.parent_id,
        "relation": relational_object.relation,
        "href": relational_object.href,
        "source_key": relational_object.source_key,
        "symbol": relational_object.symbol_path,
        "related_ids": list(relational_object.related_ids),
    }


def validate_relational_objects(relational_objects: tuple[RelationalObject, ...]) -> None:
    if not relational_objects:
        raise ValueError("relational object universe must not be empty")
    object_ids = [relational_object.object_id for relational_object in relational_objects]
    symbol_paths = [relational_object.symbol_path for relational_object in relational_objects]
    if len(object_ids) != len(set(object_ids)):
        raise ValueError("relational object IDs must be unique")
    if len(symbol_paths) != len(set(symbol_paths)):
        raise ValueError("relational symbol paths must be unique")
    objects_by_id = {
        relational_object.object_id: relational_object
        for relational_object in relational_objects
    }
    roots = [
        relational_object
        for relational_object in relational_objects
        if relational_object.kind == "root"
    ]
    if len(roots) != 1 or roots[0].parent_id:
        raise ValueError("relational universe requires exactly one parentless root")
    for relational_object in relational_objects:
        if relational_object.kind != "root" and relational_object.parent_id not in objects_by_id:
            raise ValueError(
                f"unresolved parent for relational object {relational_object.object_id}"
            )
        if relational_object.object_id in relational_object.related_ids:
            raise ValueError(
                f"self-related relational object {relational_object.object_id}"
            )
        missing_related = set(relational_object.related_ids) - set(objects_by_id)
        if missing_related:
            raise ValueError(
                f"unresolved related objects for {relational_object.object_id}: "
                f"{sorted(missing_related)!r}"
            )


def relational_symbol_markup(relational_object: RelationalObject) -> str:
    sprite_reference = html.escape(
        f"figures/relational-symbols.svg#{relational_object.object_id}",
        quote=True,
    )
    title = html.escape(relational_object.title, quote=True)
    return (
        f'<svg class="relational-symbol" viewBox="0 0 96 96" aria-hidden="true">'
        f'<use href="{sprite_reference}"></use></svg>'
        f'<span class="visually-hidden">Symbol for {title}</span>'
    )


def relational_object_row(
    relational_object: RelationalObject,
    children: str = "",
    *,
    expanded: bool = False,
) -> str:
    search_text = " ".join(
        (
            relational_object.title,
            relational_object.description,
            relational_object.kind,
            relational_object.relation,
            relational_object.source_key,
        )
    ).casefold()
    child_markup = f'<ul class="relational-children">{children}</ul>' if children else ""
    branch_class = " relational-branch" if children else " relational-leaf"
    expanded_class = " is-expanded" if children and expanded else ""
    expanded_attribute = (
        f' aria-expanded="{"true" if expanded else "false"}"'
        if children
        else ""
    )
    return (
        f'<li class="relational-node{branch_class}{expanded_class}" '
        f'data-relational-object="{html.escape(relational_object.object_id, quote=True)}" '
        f'data-relational-kind="{html.escape(relational_object.kind, quote=True)}" '
        f'data-search="{html.escape(search_text, quote=True)}">'
        f'<div class="relational-row">'
        f'<button type="button" class="relational-select" '
        f'data-relational-select="{html.escape(relational_object.object_id, quote=True)}" '
        f'{expanded_attribute} aria-controls="relational-object-inspector">'
        f'{relational_symbol_markup(relational_object)}'
        f'<span class="relational-row-copy"><strong>{html.escape(relational_object.title)}</strong>'
        f'<small>{html.escape(relational_object.kind.upper())} · '
        f'{html.escape(relational_object.relation)}</small></span></button>'
        f'<a class="relational-open" href="{html.escape(relational_object.href, quote=True)}" '
        f'aria-label="Open {html.escape(relational_object.title, quote=True)}">OPEN</a>'
        f'</div>{child_markup}</li>'
    )


def render_relational_explorer(relational_objects: tuple[RelationalObject, ...]) -> str:
    objects_by_id = {
        relational_object.object_id: relational_object
        for relational_object in relational_objects
    }
    children_by_parent: dict[str, list[RelationalObject]] = {}
    for relational_object in relational_objects:
        children_by_parent.setdefault(relational_object.parent_id, []).append(
            relational_object
        )
    for children in children_by_parent.values():
        children.sort(key=lambda item: (item.kind, item.title.casefold(), item.object_id))

    root = next(
        relational_object
        for relational_object in relational_objects
        if relational_object.kind == "root"
    )
    categories = sorted(
        (item for item in relational_objects if item.kind == "category"),
        key=lambda item: item.title.casefold(),
    )
    folders = sorted(
        (item for item in relational_objects if item.kind == "folder"),
        key=lambda item: item.title.casefold(),
    )
    concepts = sorted(
        (item for item in relational_objects if item.kind == "concept"),
        key=lambda item: item.title.casefold(),
    )

    category_rows = []
    for category in categories:
        document_rows = []
        for document in children_by_parent.get(category.object_id, []):
            heading_rows = "".join(
                relational_object_row(heading)
                for heading in children_by_parent.get(document.object_id, [])
            )
            document_rows.append(
                relational_object_row(document, heading_rows, expanded=False)
            )
        category_rows.append(
            relational_object_row(category, "".join(document_rows), expanded=True)
        )

    folder_rows = "".join(relational_object_row(folder) for folder in folders)
    concept_rows = "".join(relational_object_row(concept) for concept in concepts)
    kind_counts = {
        kind: sum(item.kind == kind for item in relational_objects)
        for kind in ("root", "category", "folder", "document", "heading", "concept")
    }
    filter_buttons = "".join(
        f'<button type="button" data-relational-filter="{kind}" aria-pressed="false">'
        f'{kind.upper()} <span>{count}</span></button>'
        for kind, count in kind_counts.items()
        if kind != "root"
    )
    root_record = relational_record(root)
    root_relations = len(children_by_parent.get(root.object_id, []))
    return f"""
<section class="relational-explorer" id="documentation-tree" aria-labelledby="relational-explorer-title">
  <div class="relational-explorer-heading">
    <div>
      <p class="terminal-label">INVARIANT RELATIONAL OBJECT BUS</p>
      <h2 id="relational-explorer-title">Navigate the architecture as objects and relations.</h2>
      <p>Every row has a stable identity, a canonical parent edge, a deterministic SVG symbol, and a manifest record. Select an object to inspect its evidence-bearing position in the tree.</p>
    </div>
    <div class="relational-root-chip" data-relational-object="{html.escape(root.object_id, quote=True)}">
      {relational_symbol_markup(root)}
      <span><strong>{len(relational_objects)} OBJECTS</strong><small>{root_relations} root relations · zero inferred authority</small></span>
    </div>
  </div>
  <div class="relational-controls" role="search">
    <label><span>SEARCH OBJECT UNIVERSE</span><input id="relational-search" type="search" placeholder="authority, replay, GUI, evidence..." autocomplete="off"></label>
    <div class="relational-kind-filters" aria-label="Filter relational objects by kind">
      <button type="button" data-relational-filter="all" aria-pressed="true">ALL <span>{len(relational_objects)}</span></button>
      {filter_buttons}
    </div>
    <p class="relational-search-status" role="status" aria-live="polite">{len(relational_objects)} OBJECTS ONLINE</p>
  </div>
  <div class="relational-workspace">
    <div class="relational-tree-panel" aria-label="Documentation relational tree">
      <section class="relational-tree-zone">
        <div class="relational-zone-label"><span>01</span><h3>Architecture domains</h3><small>category → document → heading</small></div>
        <ul class="relational-tree">{''.join(category_rows)}</ul>
      </section>
      <section class="relational-tree-zone" id="source-folders">
        <div class="relational-zone-label"><span>02</span><h3>Source folders</h3><small>folder ↔ document index relations</small></div>
        <ul class="relational-tree relational-folder-grid">{folder_rows}</ul>
      </section>
      <details class="relational-tree-zone relational-concept-zone">
        <summary><span>03</span><strong>Concept mesh</strong><small>{len(concepts)} concepts with explicit semantic links</small></summary>
        <ul class="relational-tree relational-concept-grid">{concept_rows}</ul>
      </details>
    </div>
    <aside class="relational-inspector" id="relational-object-inspector" aria-live="polite">
      <div class="inspector-scanline" aria-hidden="true"></div>
      <p class="terminal-label">SELECTED OBJECT</p>
      <object class="relational-symbol-preview" id="relational-symbol-preview" type="image/svg+xml" data="{html.escape(root.symbol_path, quote=True)}"><a href="{html.escape(root.symbol_path, quote=True)}">Open root object symbol</a></object>
      <div class="inspector-kind" data-inspector-kind>{html.escape(root.kind.upper())}</div>
      <h3 data-inspector-title>{html.escape(root.title)}</h3>
      <p data-inspector-description>{html.escape(root.description)}</p>
      <dl class="inspector-facts">
        <div><dt>Object ID</dt><dd><code data-inspector-id>{html.escape(root.object_id)}</code></dd></div>
        <div><dt>Relation</dt><dd data-inspector-relation>{html.escape(root.relation)}</dd></div>
        <div><dt>Source key</dt><dd data-inspector-source>{html.escape(root.source_key)}</dd></div>
      </dl>
      <div class="inspector-relations">
        <h4>RELATION PORTS</h4>
        <div data-inspector-relations></div>
      </div>
      <a class="primary-action inspector-open" data-inspector-open href="{html.escape(root.href, quote=True)}">OPEN OBJECT</a>
    </aside>
  </div>
  <script type="application/json" id="relational-root-record">{html.escape(json.dumps(root_record, sort_keys=True), quote=False)}</script>
</section>
"""


def architecture_explorer_template(
    documents: tuple[Document, ...],
    concepts: tuple[Concept, ...],
    relational_objects: tuple[RelationalObject, ...],
    build_date: str,
) -> str:
    heading_count = sum(len(document.sections) for document in documents)
    total_paragraphs = (heading_count + len(concepts)) * 25
    total_svg_figures = len(documents) + len(concepts) + len(relational_objects) + 5
    manifest = [
        {
            "title": document.title,
            "source": document.relative_path.as_posix(),
            "html": document.relative_path.with_suffix(".html").as_posix(),
            "category": category_for(document),
            "headings": [
                {"title": section.title, "slug": section.slug}
                for section in document.sections
            ],
        }
        for document in documents
    ]
    category_cards = []
    categories = sorted({category_for(document) for document in documents})
    category_objects = {
        relational_object.title: relational_object
        for relational_object in relational_objects
        if relational_object.kind == "category"
    }
    for category in categories:
        members = [document for document in documents if category_for(document) == category]
        category_object = category_objects[category]
        category_cards.append(
            f'<button type="button" class="category-card" id="category-{slugify(category)}" '
            f'data-category="{html.escape(category.lower(), quote=True)}" '
            f'data-relational-jump="{html.escape(category_object.object_id, quote=True)}">'
            f'{relational_symbol_markup(category_object)}'
            f'<span class="category-count">{len(members):02d}</span><h3>{html.escape(category)}</h3>'
            f'<p>{sum(len(document.sections) for document in members)} heading objects across {len(members)} source documents.</p>'
            f'<small>TRACE DOMAIN →</small></button>'
        )
    references = "".join(
        f'<li><a href="{html.escape(reference["url"])}" rel="noreferrer">{html.escape(reference["title"])}</a>'
        f'<p>{html.escape(reference["summary"])}</p></li>'
        for reference in REFERENCE_LIBRARY
    )
    relational_json = json.dumps(
        [relational_record(relational_object) for relational_object in relational_objects],
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Complete source-bound relational architecture explorer for OIEC-STM-Agent documentation">
  <title>Architecture Explorer · OIEC-STM-Agent</title>
  <link rel="stylesheet" href="assets/styles.css">
</head>
<body data-page="index" data-page-kind="explorer" {page_snapshot_attributes(build_date)}>
  <div class="scanline-overlay" aria-hidden="true"></div>
  <header class="site-header">
    <a class="brand" href="index.html"><span class="brand-mark">AE</span><span><strong>ARCHITECTURE EXPLORER</strong><small>Complete source-bound expert inventory</small></span></a>
    <div class="header-telemetry" aria-label="Documentation status"><span>STATE <b>BOUNDED</b></span><span>OBJECTS <b>{len(relational_objects):03d}</b></span><span>BUILD <b>{html.escape(build_date)}</b></span></div>
    <nav class="header-actions"><a href="index.html">LEARN</a><a href="#documentation-tree">OBJECT BUS</a><button type="button" data-action="focus-mode">FOCUS</button><a href="../README.md">README</a></nav>
  </header>
  <main class="index-main">
{governed_loop_hero(len(concepts), build_date).lstrip()}
    <section class="index-command-rail" aria-label="Documentation system telemetry">
      <article><span>01</span><div><strong>{len(documents):02d}</strong><small>Markdown sources</small></div></article>
      <article><span>02</span><div><strong>{heading_count:03d}</strong><small>heading objects</small></div></article>
      <article><span>03</span><div><strong>{len(concepts):03d}</strong><small>concept objects</small></div></article>
      <article><span>04</span><div><strong>{len(relational_objects):03d}</strong><small>relational symbols</small></div></article>
      <article><span>05</span><div><strong>{total_svg_figures:03d}</strong><small>SVG artifacts</small></div></article>
      <article><span>06</span><div><strong>{total_paragraphs:,}</strong><small>argument paragraphs</small></div></article>
    </section>
    <section class="relational-topology-panel">
      <div class="topology-copy"><p class="terminal-label">RELATIONAL TOPOLOGY / LIVE MAP</p><h2>The tree is an inspectable system, not a decorative menu.</h2><p>The original Markdown remains the source of record. Categories partition documents, documents decompose into headings, folders index source placement, and concepts create explicit semantic cross-links. Every represented object receives a deterministic SVG identity.</p><div class="hero-actions"><a class="primary-action" href="#documentation-tree">ENTER OBJECT BUS</a><button type="button" data-action="random-module">RANDOM MODULE</button><a href="figures/relational-topology.svg">OPEN SVG MAP</a></div></div>
      <figure><object class="relational-topology-map" type="image/svg+xml" data="figures/relational-topology.svg"><a href="figures/relational-topology.svg">Open the relational topology SVG</a></object><figcaption>SELECT A KIND NODE TO FILTER THE OBJECT BUS.</figcaption></figure>
    </section>
    <section class="category-grid" aria-label="Architecture domains">{''.join(category_cards)}</section>
{render_relational_explorer(relational_objects).lstrip()}
    <section class="concept-atlas-callout"><div><p class="terminal-label">{len(concepts)} SOURCE-DERIVED CONCEPTS</p><h2>Open the claim-and-concept atlas.</h2><p>The object bus is optimized for topology and navigation. Every concept page defines beginner language, tests one architectural claim against topic-matched references, and links 25 paragraph topics through an interactive logic map to a decisive winning position.</p><a class="primary-action" href="concepts/index.html">OPEN CLAIM ATLAS</a></div><object class="atlas-preview" type="image/svg+xml" data="figures/concept-atlas.svg"><a href="figures/concept-atlas.svg">Open the concept atlas SVG</a></object></section>
    <section class="learning-method">
      <div><p class="terminal-label">READING PROTOCOL</p><h2>How to learn from the site</h2></div>
      <ol><li><strong>Orient.</strong> Read the plain-language starting explanation and glossary.</li><li><strong>Challenge.</strong> Compare the thesis with the source evidence and counterargument.</li><li><strong>Trace.</strong> Use the SVG nodes to follow claim, evidence, boundary, and decision.</li><li><strong>Test.</strong> Turn one documented claim into a falsifiable architecture check.</li></ol>
    </section>
    <section class="index-references"><p class="terminal-label">TEXTBOOK LENSES</p><h2>Reference foundation</h2><ul>{references}</ul></section>
  </main>
  <div class="pixel-crew" aria-hidden="true"></div>
  <script>window.DOCS_MANIFEST = {json.dumps(manifest, ensure_ascii=False)};</script>
  <script>window.RELATIONAL_OBJECTS = {relational_json};</script>
  <script src="assets/site.js" defer></script>
</body>
</html>
"""


def source_document(source_path: str) -> Document:
    path = ROOT / source_path
    relative_path = path.relative_to(DOCS_ROOT)
    sections = parse_sections(path.read_text(encoding="utf-8"))
    return Document(
        source_path=path,
        relative_path=relative_path,
        output_path=path.with_suffix(".html"),
        title=sections[0].title,
        sections=sections,
    )


def view_controls() -> str:
    return """<section class="view-controls" aria-label="Explanation controls">
  <div class="view-tabs" role="group" aria-label="Documentation view">
    <button type="button" data-doc-view="learn" aria-pressed="true">Learn</button>
    <button type="button" data-doc-view="technical" aria-pressed="false">Technical</button>
  </div>
  <div class="depth-control">
    <label for="explanation-depth">Explanation depth</label>
    <input id="explanation-depth" type="range" min="0" max="2" step="1" value="0" data-depth-control>
    <div aria-hidden="true"><span>Novice</span><span>Intermediate</span><span>Expert</span></div>
  </div>
  <button type="button" data-action="teacher-mode" aria-pressed="false">Teacher mode</button>
  <button type="button" data-action="reset-learning">Reset learning preferences</button>
</section>
<noscript><p class="noscript-note">JavaScript is optional. Learn and Technical content remain visible in source order.</p></noscript>
"""


def evidence_badge(status: str, evidence: Iterable[str]) -> str:
    evidence_items = "".join(
        f"<li><code>{html.escape(item)}</code></li>" for item in evidence
    )
    return (
        f'<aside class="evidence-badge" data-doc-status="{html.escape(status, quote=True)}">'
        f'<strong>{html.escape(status)}</strong><span>Documentation evidence</span>'
        f"<ul>{evidence_items}</ul></aside>"
    )


def prerequisite_map(
    current_id: str,
    prerequisite_ids: Iterable[str],
    next_id: str = "",
) -> str:
    prerequisites = tuple(prerequisite_ids)
    nodes = []
    for prerequisite in prerequisites:
        nodes.append(
            f'<span class="prerequisite-node is-complete">✓ {html.escape(prerequisite)}</span><span aria-hidden="true">→</span>'
        )
    nodes.append(
        f'<span class="prerequisite-node is-current">{html.escape(current_id)} · YOU ARE HERE</span>'
    )
    if next_id:
        nodes.append(
            f'<span aria-hidden="true">→</span><span class="prerequisite-node">{html.escape(next_id)}</span>'
        )
    return (
        '<section class="prerequisite-map" aria-label="Learning prerequisites">'
        '<p class="terminal-label">YOU ARE HERE</p><div>'
        + "".join(nodes)
        + "</div></section>"
    )


def command_cards(command_ids: Iterable[str]) -> str:
    by_id = {recipe.command_id: recipe for recipe in RECIPES}
    cards = []
    for command_id in command_ids:
        recipe = by_id[command_id]
        explanation = "".join(
            f"<li><code>{html.escape(token)}</code><span>{html.escape(meaning)}</span></li>"
            for token, meaning in recipe.explanation
        )
        cards.append(
            f'<article class="command-card" data-command-id="{html.escape(command_id, quote=True)}">'
            f'<h3>{html.escape(recipe.title)}</h3><pre data-language="bash"><code>{html.escape(recipe.command)}</code></pre>'
            f"<p>{html.escape(recipe.purpose)}</p><ul>{explanation}</ul>"
            '<button type="button" data-copy-command>Copy command</button></article>'
        )
    return "".join(cards) or "<p>No direct command is required for this lesson.</p>"


def load_learning_fixtures() -> dict[str, dict[str, object]]:
    payload = json.loads(
        (DOCS_ROOT / "tutorial" / "fixtures" / "core-learning.json").read_text(
            encoding="utf-8"
        )
    )
    records = {
        str(record["fixture_id"]): record for record in payload.get("fixtures", [])
    }
    records.update(
        {
            str(record["refusal_id"]): record
            for record in payload.get("refusals", [])
        }
    )
    return records


def sandbox_markup(fixture_ids: Iterable[str]) -> str:
    fixtures = load_learning_fixtures()
    records = [fixtures[fixture_id] for fixture_id in fixture_ids]
    if not records:
        return '<p class="sandbox-empty">This lesson has no interactive fixture.</p>'
    sandboxes = []
    for record in records:
        fixture_id = str(record.get("fixture_id", record.get("refusal_id", "fixture")))
        title = str(record.get("title", record.get("choice", fixture_id)))
        payload = json.dumps(record, ensure_ascii=False, separators=(",", ":")).replace(
            "</", "<\\/"
        )
        sandboxes.append(f"""
<section class="tutorial-sandbox" data-tutorial-sandbox="{html.escape(fixture_id, quote=True)}">
  <div><p class="terminal-label">READ-ONLY BROWSER SANDBOX</p><h2>{html.escape(title)}</h2>
  <p>Runs checked-in deterministic fixture data only. It has no provider, network, filesystem, command, or mutation path.</p></div>
  <div class="sandbox-controls"><button type="button" data-sandbox-run>Run next step</button><button type="button" data-sandbox-reset>Reset</button></div>
  <ol class="sandbox-output" aria-live="polite"></ol>
  <script type="application/json" data-sandbox-fixture>{payload}</script>
</section>
""")
    return "".join(sandboxes)


def tutorial_page_template(lesson: object, build_date: str) -> str:
    document = source_document(lesson.source_path)
    authored_headings = tuple(section.title for section in document.sections[1:])
    if authored_headings != TUTORIAL_HEADINGS:
        raise ValueError(
            f"tutorial heading contract failed for {lesson.lesson_id}: {authored_headings!r}"
        )
    digest = hashlib.sha256(document.source_path.read_bytes()).hexdigest()
    sections = "".join(
        f'<section class="learning-section" id="{html.escape(section.slug, quote=True)}"><h2>{html.escape(section.title)}</h2>{render_markdown(section.markdown)}</section>'
        for section in document.sections[1:]
    )
    technical = f"""
<section class="technical-panel" data-view-content="technical">
  <p class="terminal-label">TECHNICAL CONTRACT</p>
  <h2>{html.escape(lesson.lesson_id)} catalog record</h2>
  <dl class="technical-grid">
    <div><dt>Source</dt><dd><code>{html.escape(lesson.source_path)}</code></dd></div>
    <div><dt>Prerequisites</dt><dd>{html.escape(', '.join(lesson.prerequisite_ids) or 'None')}</dd></div>
    <div><dt>Vocabulary</dt><dd>{html.escape(', '.join(lesson.new_vocabulary))}</dd></div>
    <div><dt>Fixture IDs</dt><dd>{html.escape(', '.join(lesson.fixture_ids) or 'None')}</dd></div>
    <div><dt>Source SHA-256</dt><dd><code>{digest}</code></dd></div>
    <div><dt>Build date</dt><dd>{html.escape(build_date)}</dd></div>
  </dl>
  <div class="command-grid">{command_cards(lesson.command_ids)}</div>
</section>
"""
    next_link = (
        f'<a class="primary-action" href="{int(lesson.next_lesson_id[1:]):02d}_{TUTORIALS[int(lesson.next_lesson_id[1:])].source_path.rsplit("/", 1)[1].split("_", 1)[1].replace(".md", ".html")}">Next lesson →</a>'
        if lesson.next_lesson_id
        else '<a class="primary-action" href="../tasks/index.html">Choose a task route →</a>'
    )
    diagram_url = f"../figures/tutorial/{lesson.lesson_id.lower()}.svg"
    return f"""<!doctype html>
<html lang="en" data-doc-view="learn" data-doc-depth="novice">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{html.escape(lesson.reader_outcome, quote=True)}">
<title>{html.escape(lesson.title)} · OIEC Tutorial</title><link rel="stylesheet" href="../assets/styles.css"></head>
<body data-page="tutorial" data-lesson-id="{html.escape(lesson.lesson_id, quote=True)}" data-source-hash="{digest}" {page_snapshot_attributes(build_date)}>
<header class="site-header"><a class="brand" href="../index.html"><span class="brand-mark">{html.escape(lesson.lesson_id)}</span><span><strong>OIEC LEARNING PATH</strong><small>{html.escape(lesson.title)}</small></span></a><nav class="header-actions"><a href="index.html">TUTORIALS</a><a href="../architecture-explorer.html">TECHNICAL EXPLORER</a></nav></header>
<main class="learning-main">
  {view_controls()}
  {prerequisite_map(lesson.lesson_id, lesson.prerequisite_ids, lesson.next_lesson_id)}
  <section class="learning-hero"><p class="eyebrow">LESSON {lesson.ordinal:02d} · BUILT {html.escape(build_date)}</p><h1>{html.escape(lesson.title)}</h1><p>{html.escape(lesson.reader_outcome)}</p>{evidence_badge('Tested', (lesson.source_path, 'tests/test_docs_tutorials.py'))}</section>
  <figure class="learning-diagram"><object type="image/svg+xml" data="{diagram_url}"><a href="{diagram_url}">Open lesson diagram</a></object><figcaption>Shared visual grammar: processes, gates, evidence, authority, and verified or hypothetical relations.</figcaption></figure>
  <article class="learning-prose" data-view-content="learn">{sections}</article>
{technical}
{sandbox_markup(lesson.fixture_ids)}
  <section class="teacher-panel" data-teacher-content hidden><h2>Teacher mode</h2><p><strong>Objective:</strong> {html.escape(lesson.reader_outcome)}</p><details><summary>Exercise and checked answer</summary><p>Explain the lesson using a different domain while preserving its authority and evidence boundaries.</p><p><strong>Answer check:</strong> the explanation must name the input, controlled boundary, evidence, output, and a common misconception.</p></details></section>
  <nav class="learning-pager"><a href="index.html">← Tutorial index</a>{next_link}</nav>
</main><script src="../assets/site.js" defer></script></body></html>
"""


def tutorial_index_template(build_date: str) -> str:
    cards = "".join(
        f'<article class="learning-card"><span>{lesson.lesson_id}</span><h2>{html.escape(lesson.title)}</h2><p>{html.escape(lesson.reader_outcome)}</p><small>{len(lesson.prerequisite_ids)} prerequisites · {len(lesson.fixture_ids)} fixtures</small><a href="{Path(lesson.source_path).with_suffix(".html").name}">Open lesson →</a></article>'
        for lesson in TUTORIALS
    )
    return collection_index_template(
        title="Tutorial Curriculum",
        description="Fourteen ordered lessons from first principles to a complete governed workflow.",
        cards=cards,
        build_date=build_date,
        parent_prefix="../",
        page_kind="tutorial-index",
    )


def learning_source_page_template(record: object, kind: str, build_date: str) -> str:
    document = source_document(record.source_path)
    digest = hashlib.sha256(document.source_path.read_bytes()).hexdigest()
    sections = "".join(
        f'<section class="learning-section" id="{html.escape(section.slug, quote=True)}"><h2>{html.escape(section.title)}</h2>{render_markdown(section.markdown)}</section>'
        for section in document.sections[1:]
    )
    concepts = tuple(getattr(record, "concept_ids", ()))
    route_items = tuple(getattr(record, "ordered_item_ids", ()))
    technical_items = "".join(
        f"<li><code>{html.escape(item)}</code></li>" for item in (*concepts, *route_items)
    )
    fixture_id = str(getattr(record, "fixture_id", ""))
    return f"""<!doctype html>
<html lang="en" data-doc-view="learn" data-doc-depth="novice"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(record.title)} · OIEC {html.escape(kind.title())}</title><link rel="stylesheet" href="../assets/styles.css"></head>
<body data-page="{html.escape(kind, quote=True)}" data-source-hash="{digest}" {page_snapshot_attributes(build_date)}><header class="site-header"><a class="brand" href="../index.html"><span class="brand-mark">{html.escape(kind[:2].upper())}</span><span><strong>{html.escape(kind.upper())}</strong><small>{html.escape(record.title)}</small></span></a><nav class="header-actions"><a href="index.html">ALL {html.escape(kind.upper())}</a><a href="../architecture-explorer.html">EXPLORER</a></nav></header>
<main class="learning-main">{view_controls()}<section class="learning-hero"><p class="eyebrow">{html.escape(kind.upper())} · BUILT {html.escape(build_date)}</p><h1>{html.escape(record.title)}</h1><p>{html.escape(getattr(record, 'plain_language_goal', getattr(record, 'problem', 'Guided learning example.')))}</p>{evidence_badge('Implemented' if kind == 'task guide' else 'Theoretical', (record.source_path,))}</section><article class="learning-prose" data-view-content="learn">{sections}</article><section class="technical-panel" data-view-content="technical"><h2>Technical record</h2><p>Source-bound identifiers and related learning records:</p><ul>{technical_items or '<li>No additional identifiers.</li>'}</ul><p><code>sha256:{digest}</code></p></section>{sandbox_markup((fixture_id,)) if fixture_id else ''}<section class="teacher-panel" data-teacher-content hidden><h2>Teacher mode</h2><details><summary>Discussion prompt</summary><p>Identify one unsupported inference and one evidence-producing next step in this example.</p></details></section></main><script src="../assets/site.js" defer></script></body></html>"""


def collection_index_template(
    title: str,
    description: str,
    cards: str,
    build_date: str,
    parent_prefix: str,
    page_kind: str,
) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(title)} · OIEC Documentation</title><link rel="stylesheet" href="{parent_prefix}assets/styles.css"></head>
<body data-page="{html.escape(page_kind, quote=True)}" {page_snapshot_attributes(build_date)}><header class="site-header"><a class="brand" href="{parent_prefix}index.html"><span class="brand-mark">OL</span><span><strong>{html.escape(title.upper())}</strong><small>Built {html.escape(build_date)}</small></span></a><nav class="header-actions"><a href="{parent_prefix}index.html">HOME</a><a href="{parent_prefix}architecture-explorer.html">EXPLORER</a></nav></header><main class="learning-main"><section class="collection-hero"><p class="eyebrow">GUIDED DOCUMENTATION</p><h1>{html.escape(title)}</h1><p>{html.escape(description)}</p></section><section class="learning-card-grid">{cards}</section></main><script src="{parent_prefix}assets/site.js" defer></script></body></html>"""


def task_index_template(build_date: str) -> str:
    cards = "".join(
        f'<article class="learning-card" data-intent-terms="{html.escape(" ".join(route.search_terms), quote=True)}"><h2>{html.escape(route.title)}</h2><p>{html.escape(route.plain_language_goal)}</p><small>{" → ".join(route.ordered_item_ids)}</small><a href="{Path(route.source_path).with_suffix(".html").name}">Follow route →</a></article>'
        for route in TASK_ROUTES
    )
    return collection_index_template(
        "Learn by Task",
        "Choose the work you want to accomplish; the site introduces only the concepts required for that route.",
        cards,
        build_date,
        "../",
        "task-index",
    )


def case_study_index_template(build_date: str) -> str:
    cards = "".join(
        f'<article class="learning-card"><span>{html.escape(case.domain)}</span><h2>{html.escape(case.title)}</h2><p>{html.escape(case.problem)}</p><small>{html.escape(", ".join(case.concept_ids))}</small><a href="{Path(case.source_path).with_suffix(".html").name}">Open case study →</a></article>'
        for case in CASE_STUDIES
    )
    return collection_index_template(
        "Cross-Domain Case Studies",
        "See the same governed learning pattern in everyday, engineering, research, software, writing, and business settings.",
        cards,
        build_date,
        "../",
        "case-study-index",
    )


def glossary_template(build_date: str) -> str:
    cards = "".join(
        f'<article class="glossary-card" id="term-{slugify(record.token)}" data-acronym="{html.escape(record.token, quote=True)}"><h2>{html.escape(record.token)}</h2><p><strong>{html.escape(record.expansion)}</strong></p><p>{html.escape(record.short_meaning)}</p><details><summary>Analogy and formal meaning</summary><p>{html.escape(record.everyday_analogy)}</p><p>{html.escape(record.formal_meaning)}</p><small>First lesson: {html.escape(record.first_lesson_id)} · Sources: {html.escape(", ".join(record.source_paths))}</small></details></article>'
        for record in ACRONYMS
    )
    glossary_json = json.dumps(
        {record.token: record.expansion for record in ACRONYMS},
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Glossary and Acronym Inspector · OIEC</title><link rel="stylesheet" href="assets/styles.css"></head><body data-page="glossary" {page_snapshot_attributes(build_date)}><header class="site-header"><a class="brand" href="index.html"><span class="brand-mark">AZ</span><span><strong>GLOSSARY</strong><small>Mini encyclopedia</small></span></a><nav class="header-actions"><a href="tutorial/index.html">TUTORIALS</a><a href="architecture-explorer.html">EXPLORER</a></nav></header><main class="learning-main"><section class="collection-hero"><p class="eyebrow">BUILT {html.escape(build_date)}</p><h1>Acronym Inspector</h1><p>Paste a sentence. Recognized terms are expanded from the canonical catalog; unknown uppercase tokens remain unresolved.</p><label for="acronym-input">Text to inspect</label><textarea id="acronym-input" rows="4">OIEC uses OURD and IURM before EON and CFEL.</textarea><button type="button" data-action="inspect-acronyms">Expand terms</button><div class="tool-output" data-acronym-output aria-live="polite"></div></section><section class="glossary-grid">{cards}</section></main><script type="application/json" id="acronym-catalog">{glossary_json}</script><script src="assets/site.js" defer></script></body></html>"""


def status_decoder_template(statuses: tuple[object, ...], build_date: str) -> str:
    status_json = json.dumps(
        {record.status: status_records_for_manifest((record,))[0] for record in statuses},
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    options = "".join(
        f'<option value="{html.escape(record.status, quote=True)}">{html.escape(record.status)}</option>'
        for record in statuses
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Status Decoder · OIEC</title><link rel="stylesheet" href="assets/styles.css"></head><body data-page="status-decoder" {page_snapshot_attributes(build_date)}><header class="site-header"><a class="brand" href="index.html"><span class="brand-mark">SD</span><span><strong>STATUS DECODER</strong><small>{len(statuses)} source-bound records</small></span></a><nav class="header-actions"><a href="glossary.html">GLOSSARY</a><a href="architecture-explorer.html">EXPLORER</a></nav></header><main class="learning-main"><section class="tool-hero"><p class="eyebrow">BUILT {html.escape(build_date)}</p><h1>Translate machine status into next steps</h1><label for="status-input">Status</label><input id="status-input" list="status-options" value="QUALIFIED_KNOWN_SOLUTION_PAIR_FOUND"><datalist id="status-options">{options}</datalist><button type="button" data-action="decode-status">Decode status</button><div class="tool-output" data-status-output aria-live="polite"></div></section></main><script type="application/json" id="status-catalog">{status_json}</script><script src="assets/site.js" defer></script></body></html>"""


def timeline_template(build_date: str) -> str:
    entries = "".join(
        f'<article class="timeline-entry" id="timeline-{html.escape(entry.entry_id, quote=True)}"><span>{index:02d}</span><div><h2>{html.escape(entry.title)}</h2><p><strong>Problem:</strong> {html.escape(entry.problem)}</p><p><strong>Architectural response:</strong> {html.escape(entry.response)}</p><small>Sources: {html.escape(", ".join(entry.source_paths))}</small></div></article>'
        for index, entry in enumerate(INVENTION_TIMELINE, start=1)
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Why Was This Invented? · OIEC</title><link rel="stylesheet" href="assets/styles.css"></head><body data-page="timeline" {page_snapshot_attributes(build_date)}><header class="site-header"><a class="brand" href="index.html"><span class="brand-mark">WT</span><span><strong>WHY WAS THIS INVENTED?</strong><small>Problem-to-system timeline</small></span></a><nav class="header-actions"><a href="tutorial/index.html">TUTORIALS</a><a href="failure-museum.html">FAILURE MUSEUM</a></nav></header><main class="learning-main"><section class="collection-hero"><p class="eyebrow">SOURCE-LINKED · BUILT {html.escape(build_date)}</p><h1>Each named system answers a recurring failure mode.</h1><p>This is an architectural sequence, not a claim about historical invention dates. Every entry links the problem it addresses to current source owners.</p></section><section class="timeline">{entries}</section></main><script src="assets/site.js" defer></script></body></html>"""


def failure_museum_template(statuses: tuple[object, ...], build_date: str) -> str:
    payload = json.loads(
        (DOCS_ROOT / "tutorial" / "fixtures" / "core-learning.json").read_text(
            encoding="utf-8"
        )
    )
    refusals = "".join(
        f'<article class="failure-card"><p class="terminal-label">DETERMINISTIC REFUSAL</p><h2>{html.escape(str(record["choice"]))}</h2><p><strong>Why it stopped:</strong> {html.escape(str(record["violated_invariant"]))}</p><p><strong>Evidence needed:</strong> {html.escape(str(record["required_evidence"]))}</p></article>'
        for record in payload.get("refusals", [])
    )
    failure_statuses = [
        record
        for record in statuses
        if record.category in {"Failure or Refusal", "Pending or Unresolved"}
    ][:18]
    status_cards = "".join(
        f'<article class="failure-card"><p class="terminal-label">{html.escape(record.category.upper())}</p><h2><code>{html.escape(record.status)}</code></h2><p>{html.escape(record.plain_language_meaning)}</p><p><strong>Next:</strong> {html.escape(record.user_action)}</p></article>'
        for record in failure_statuses
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Failure Museum · OIEC</title><link rel="stylesheet" href="assets/styles.css"></head><body data-page="failure-museum" {page_snapshot_attributes(build_date)}><header class="site-header"><a class="brand" href="index.html"><span class="brand-mark">FM</span><span><strong>FAILURE MUSEUM</strong><small>What the system correctly stopped</small></span></a><nav class="header-actions"><a href="status-decoder.html">STATUS DECODER</a><a href="timeline.html">TIMELINE</a></nav></header><main class="learning-main"><section class="collection-hero"><p class="eyebrow">BUILT {html.escape(build_date)}</p><h1>Refusal quality is part of system quality.</h1><p>These examples teach why the architecture stops, what invariant was protected, and which evidence could justify a different next step.</p></section><section class="failure-grid">{refusals}{status_cards}</section></main><script src="assets/site.js" defer></script></body></html>"""


def tools_template(build_date: str) -> str:
    recipe_json = json.dumps(
        cli_records_for_manifest(RECIPES),
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    rejected_json = json.dumps(
        cli_records_for_manifest(REJECTED_RECIPES),
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Learning Tools · OIEC Documentation</title><link rel="stylesheet" href="assets/styles.css"></head>
<body data-page="tools" {page_snapshot_attributes(build_date)}><header class="site-header"><a class="brand" href="index.html"><span class="brand-mark">LT</span><span><strong>LEARNING TOOLS</strong><small>Fixture-only and parser-grounded</small></span></a><nav class="header-actions"><a href="glossary.html">GLOSSARY</a><a href="status-decoder.html">STATUS</a><a href="architecture-explorer.html">EXPLORER</a></nav></header>
<main class="learning-main">
  <section class="tool-hero"><p class="eyebrow">COMMAND BUILDER · BUILT {html.escape(build_date)}</p><h1>Build a safe command</h1><div class="builder-grid"><label>Command type<select data-builder-program><option value="agent-read-repo">Inspect repository</option><option value="agent-write-docs">Bounded documentation write</option><option value="egcf-dry-run">EGCF dry-run</option><option value="egcf-workflow">Strict EGCF workflow</option><option value="gui-first-launch">Open GUI</option></select></label><label>Workspace<input data-builder-workspace value="."></label><label>Target<input data-builder-target value="src/parser.py"></label><label>Risk<select data-builder-risk><option>L0</option><option>L1</option><option>L2</option></select></label></div><button type="button" data-action="build-command">Generate command</button><pre data-language="bash"><code data-command-output></code></pre><div class="tool-output" data-command-explanation></div></section>
  <section class="tool-hero"><p class="eyebrow">PROVIDER SETUP WIZARD</p><h2>Which local model provider are you using?</h2><label for="provider-choice">Provider</label><select id="provider-choice" data-provider-choice><option value="provider-llama-cpp">Direct llama.cpp process</option></select><button type="button" data-action="show-provider-recipe">Show configuration</button><pre data-language="bash"><code data-provider-output></code></pre><p>The browser never asks for or stores a provider secret. Provider choice changes proposal generation, not governance authority.</p></section>
  <section class="tool-hero"><p class="eyebrow">CAPABILITY WORKSHOP</p><h2>From looking to critical action</h2><div class="capability-grid"><article><strong>C0</strong><span>Look at the machine</span><small>Observe only</small></article><article><strong>C1</strong><span>Draw a repair plan</span><small>Analyse and propose</small></article><article><strong>C2</strong><span>Try it on a test machine</span><small>Simulate</small></article><article><strong>C3</strong><span>Repair with permission</span><small>Authorized local mutation</small></article><article class="is-blocked"><strong>C4</strong><span>Change outside the workshop</span><small>Fail closed</small></article><article class="is-blocked"><strong>C5</strong><span>Critical or destructive action</span><small>Fail closed</small></article></div></section>
  <section class="tool-hero"><p class="eyebrow">GUI FIRST LAUNCH</p><h2>Reveal the workbench in five steps</h2><ol class="gui-first-steps"><li><strong>Repository.</strong> Select the workspace.</li><li><strong>Ask.</strong> Use Agent Chat for a bounded question.</li><li><strong>Inspect.</strong> Review the semantic objective and plan.</li><li><strong>Evidence.</strong> Open linked records and limitations.</li><li><strong>Decide.</strong> Approve or reject only through the applicable authority path.</li></ol><pre data-language="bash"><code>oiec-stm-gui --repo .</code></pre><p>Advanced workbench panels and <code>--smoke-test</code> remain Technical reference features.</p></section>
  <section class="tool-grid"><article><h2>Output decoder</h2><p>Translate exact uppercase statuses without interpreting arbitrary output as HTML.</p><a href="status-decoder.html">Open Status Decoder →</a></article><article><h2>Acronym Inspector</h2><p>Expand canonical terms and leave unknown tokens unresolved.</p><a href="glossary.html">Open Acronym Inspector →</a></article><article><h2>Trace This Term</h2><p>Open the Architecture Explorer, select an object, and inspect canonical and related edges.</p><a href="architecture-explorer.html#documentation-tree">Trace a term →</a></article><article><h2>Break the invariant</h2><p>Use tutorial sandboxes to trigger deterministic refusals with no mutation path.</p><a href="tutorial/10_ADAPTATION.html">Open refusal exercise →</a></article><article><h2>Why was this invented?</h2><p>Trace each architecture system back to the recurring problem it addresses.</p><a href="timeline.html">Open timeline →</a></article><article><h2>Failure museum</h2><p>Study correctly refused actions, regressions, and unresolved states.</p><a href="failure-museum.html">Open museum →</a></article></section>
</main><script type="application/json" id="command-recipes">{recipe_json}</script><script type="application/json" id="rejected-recipes">{rejected_json}</script><script src="assets/site.js" defer></script></body></html>"""


def index_template(
    documents: tuple[Document, ...],
    concepts: tuple[Concept, ...],
    relational_objects: tuple[RelationalObject, ...],
    build_date: str,
) -> str:
    task_cards = "".join(
        f'<a class="task-card" href="tasks/{Path(route.source_path).with_suffix(".html").name}" data-intent-terms="{html.escape(" ".join(route.search_terms), quote=True)}"><span>I want to…</span><strong>{html.escape(route.title)}</strong><small>{html.escape(route.plain_language_goal)}</small></a>'
        for route in TASK_ROUTES
    )
    tutorial_cards = "".join(
        f'<a class="start-step" href="tutorial/{Path(lesson.source_path).with_suffix(".html").name}"><span>{lesson.ordinal + 1:02d}</span><div><strong>{html.escape(lesson.title)}</strong><small>{html.escape(lesson.reader_outcome)}</small></div></a>'
        for lesson in TUTORIALS[:5]
    )
    return f"""<!doctype html>
<html lang="en" data-doc-view="learn" data-doc-depth="novice"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="description" content="A novice-first guide to an AI agent that understands, checks, acts carefully, verifies, and learns from evidence."><title>OIEC-STM-Agent Documentation</title><link rel="stylesheet" href="assets/styles.css"></head>
<body data-page="home" {page_snapshot_attributes(build_date)}><header class="site-header home-header"><a class="brand" href="index.html"><span class="brand-mark">OI</span><span><strong>OIEC-STM-AGENT</strong><small>Learn before architecture</small></span></a><nav class="header-actions"><a href="#first-15-minutes">START</a><a href="tutorial/index.html">TUTORIALS</a><a href="tools.html">TOOLS</a><a href="architecture-explorer.html">EXPLORER</a></nav></header>
<main class="home-main">
  <section class="novice-hero"><div class="hero-copy"><p class="eyebrow">WHAT IS THIS?</p><h1>An AI agent designed to work carefully.</h1><p>It tries to understand what you mean, checks what it knows, looks for an existing solution, limits what it is allowed to change, tests proposed work, records failures, and learns from verified results.</p><div class="hero-actions"><a class="primary-action" href="#first-15-minutes">Start your first 15 minutes</a><a href="tutorial/00_WELCOME.html">Explain the idea first</a></div></div><figure><object type="image/svg+xml" data="figures/learning-loop.svg"><a href="figures/learning-loop.svg">Open the careful-work loop</a></object><figcaption>No architecture vocabulary is required to read this loop.</figcaption></figure></section>
  <section class="plain-stages" aria-label="Careful work stages"><article><span>1</span><strong>You ask for work</strong></article><article><span>2</span><strong>Understand it</strong></article><article><span>3</span><strong>Find what is known</strong></article><article><span>4</span><strong>Try safely</strong></article><article><span>5</span><strong>Check the result</strong></article><article><span>6</span><strong>Remember what was learned</strong></article></section>
  <section class="terminology-bridge"><p>In the technical architecture, these responsibilities are implemented by named systems such as OURD, IURM, EON, CFEL, EGCF, IEPS, and SAA.</p><a href="glossary.html">Open the beginner glossary →</a></section>
  <section class="before-after"><div><p class="terminal-label">BEFORE</p><h2>A fast but weak loop</h2><ol><li>Receive “Fix parser.”</li><li>Guess a cause.</li><li>Change a file.</li><li>Retry after failure.</li></ol></div><div><p class="terminal-label">WITH OIEC</p><h2>A governed learning loop</h2><ol><li>Define the problem.</li><li>Check source state and known work.</li><li>Test uncertainty.</li><li>Propose a bounded action.</li><li>Verify and record the result.</li></ol></div></section>
  <section class="first-track" id="first-15-minutes"><div><p class="eyebrow">First 15 Minutes</p><h2>Complete one safe read-only task</h2><p>Install, identify the commands, inspect a repository, and separate facts from proposals.</p></div><div class="start-step-grid">{tutorial_cards}</div><aside class="alias-map"><h3>Five command names, three experiences</h3><p><code>oiec-stm-agent</code> and <code>ourd-agent</code> open the same agent CLI.</p><p><code>oiec-stm-gui</code> and <code>ourd-gui</code> open the same GUI.</p><p><code>egcf</code> is the governed command interface.</p></aside></section>
  <section class="learn-by-task" id="learn-by-task"><div><p class="eyebrow">Learn by Task</p><h2>What do you want to do?</h2><label for="intent-search">Describe your goal</label><input id="intent-search" type="search" placeholder="agent keeps repeating a failed action"><p class="search-status" data-intent-status>{len(TASK_ROUTES)} task routes available</p></div><div class="task-grid">{task_cards}</div></section>
  <section class="core-map"><p class="eyebrow">LEARN THE CORE</p><h2>Follow responsibility, not acronym order</h2><div class="core-map-grid"><a href="tutorial/04_OURD.html"><span>Understand</span><strong>Map what belongs</strong></a><a href="tutorial/05_IURM.html"><span>Experiment</span><strong>Vary one useful dimension</strong></a><a href="tutorial/07_EON.html"><span>Act safely</span><strong>Bind an exact action</strong></a><a href="tutorial/03_EVIDENCE.html"><span>Verify</span><strong>Separate belief from proof</strong></a><a href="tutorial/08_CFEL.html"><span>Learn</span><strong>Record contradiction</strong></a><a href="tutorial/09_SAA.html"><span>Remember and improve</span><strong>Retrieve before reinventing</strong></a></div></section>
  <section class="resource-grid"><article><h2>Tutorial curriculum</h2><p>{len(TUTORIALS)} ordered lessons with deterministic fixtures.</p><a href="tutorial/index.html">Open tutorials →</a></article><article><h2>Learning tools</h2><p>Build commands, decode statuses, inspect acronyms, and break invariants safely.</p><a href="tools.html">Open tools →</a></article><article><h2>Case studies</h2><p>{len(CASE_STUDIES)} domains show the same architecture outside coding.</p><a href="case-studies/index.html">Open case studies →</a></article><article><h2>Architecture Explorer</h2><p>Browse all {len(relational_objects)} source-bound relational objects and {len(concepts)} concepts.</p><a href="architecture-explorer.html">Open expert explorer →</a></article></section>
  <footer class="home-footer"><p>Generated from {len(documents)} expert Markdown sources and novice learning catalogs on {html.escape(build_date)}.</p><a href="../README.md">README</a><a href="site-manifest.json">Manifest</a></footer>
</main><script src="assets/site.js" defer></script></body></html>"""


def svg_text(value: str, limit: int = 28) -> str:
    value = strip_markdown(value)
    if len(value) > limit:
        value = value[: limit - 1].rstrip() + "…"
    return html.escape(value)


def document_svg(document: Document) -> str:
    columns = 3
    node_width = 310
    node_height = 82
    x_gap = 45
    y_gap = 62
    margin_x = 70
    margin_y = 145
    rows = (len(document.sections) + columns - 1) // columns
    width = margin_x * 2 + columns * node_width + (columns - 1) * x_gap
    height = margin_y + rows * node_height + max(0, rows - 1) * y_gap + 90
    nodes: list[str] = []
    edges: list[str] = []
    positions: list[tuple[float, float]] = []
    for index, section in enumerate(document.sections):
        row = index // columns
        column = index % columns
        x = margin_x + column * (node_width + x_gap)
        y = margin_y + row * (node_height + y_gap)
        positions.append((x, y))
        nodes.append(
            f'<g class="module-node" id="node-{section.slug}" data-target="{section.slug}" tabindex="0" role="link">'
            f'<rect x="{x}" y="{y}" width="{node_width}" height="{node_height}" rx="3" />'
            f'<text class="node-index" x="{x + 18}" y="{y + 27}">{section.ordinal:02d}</text>'
            f'<text class="node-title" x="{x + 58}" y="{y + 29}">{svg_text(section.title, 34)}</text>'
            f'<text class="node-meta" x="{x + 18}" y="{y + 60}">LEVEL {section.level} · 25 PARAGRAPHS</text>'
            f'<title>Open module {section.ordinal}: {html.escape(section.title)}</title></g>'
        )
    for index in range(len(positions) - 1):
        x1, y1 = positions[index]
        x2, y2 = positions[index + 1]
        edges.append(
            f'<path class="signal-path" d="M {x1 + node_width} {y1 + node_height / 2} '
            f'C {x1 + node_width + 24} {y1 + node_height / 2}, {x2 - 24} {y2 + node_height / 2}, {x2} {y2 + node_height / 2}" />'
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<style>
  :root {{ color-scheme: light; }}
  svg {{ background:#fbf8ff; font-family:'Courier New',monospace; }}
  .grid {{ stroke:#e5d6ff; stroke-width:1; }}
  .title {{ fill:#2b0a5a; font-size:25px; font-weight:700; letter-spacing:2px; }}
  .subtitle {{ fill:#6e3aa8; font-size:13px; letter-spacing:1.4px; }}
  .signal-path {{ fill:none; stroke:#9b4dff; stroke-width:3; stroke-dasharray:8 8; animation:flow 2s linear infinite; }}
  .module-node {{ cursor:pointer; outline:none; }}
  .module-node rect {{ fill:#ffffff; stroke:#5d168f; stroke-width:3; filter:drop-shadow(6px 6px 0 #d7b8ff); transition:120ms ease; }}
  .module-node:hover rect,.module-node:focus rect,.module-node.active rect {{ fill:#f3e8ff; stroke:#ff3fcf; transform:translate(-2px,-2px); }}
  .node-index {{ fill:#ff2dbf; font-size:17px; font-weight:700; }}
  .node-title {{ fill:#2b0a5a; font-size:15px; font-weight:700; }}
  .node-meta {{ fill:#6e3aa8; font-size:11px; letter-spacing:1px; }}
  @keyframes flow {{ to {{ stroke-dashoffset:-32; }} }}
</style>
<defs><pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse"><path class="grid" d="M 24 0 L 0 0 0 24" fill="none" /></pattern></defs>
<rect width="100%" height="100%" fill="url(#grid)" />
<text class="title" x="70" y="58">{svg_text(document.title, 70)}</text>
<text class="subtitle" x="70" y="88">INTERACTIVE MODULE CIRCUIT · SELECT A NODE TO NAVIGATE</text>
<g class="edges">{''.join(edges)}</g><g class="nodes">{''.join(nodes)}</g>
</svg>
"""


def wrapped_svg_text(value: str, width: int = 28, maximum_lines: int = 3) -> tuple[str, ...]:
    words = strip_markdown(value).split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word])
        if current and len(candidate) > width:
            lines.append(" ".join(current))
            current = [word]
            if len(lines) == maximum_lines:
                break
        else:
            current.append(word)
    if current and len(lines) < maximum_lines:
        lines.append(" ".join(current))
    if len(lines) == maximum_lines and len(" ".join(words)) > len(" ".join(lines)):
        lines[-1] = lines[-1].rstrip(".,;:") + "…"
    return tuple(lines or ["Concept"])


def concept_svg(concept: Concept) -> str:
    nodes = (
        ("PURPOSE", concept.central_question, 55, 115),
        ("INPUTS", concept.inputs, 450, 65),
        ("CONTROLS", concept.controls, 845, 115),
        ("EVIDENCE", concept.evidence, 145, 540),
        ("OUTCOME", concept.outcome, 755, 540),
    )
    center_x, center_y = 600, 365
    node_markup = []
    edge_markup = []
    for index, (label, detail, x, y) in enumerate(nodes, start=1):
        detail_lines = wrapped_svg_text(detail, 34, 2)
        tspans = "".join(
            f'<tspan x="{x + 20}" dy="{0 if line_index == 0 else 17}">{html.escape(line)}</tspan>'
            for line_index, line in enumerate(detail_lines)
        )
        node_markup.append(
            f'<g class="concept-node" tabindex="0" role="button" data-detail="{html.escape(detail, quote=True)}">'
            f'<rect x="{x}" y="{y}" width="300" height="112" rx="3" />'
            f'<text class="node-number" x="{x + 20}" y="{y + 29}">{index:02d}</text>'
            f'<text class="node-label" x="{x + 62}" y="{y + 29}">{label}</text>'
            f'<text class="node-detail" x="{x + 20}" y="{y + 66}">{tspans}</text>'
            f'<title>{html.escape(label)}: {html.escape(detail)}</title></g>'
        )
        edge_markup.append(
            f'<path class="concept-edge" d="M {center_x} {center_y} L {x + 150} {y + 56}" />'
        )
    title_lines = wrapped_svg_text(concept.title, 28, 3)
    title_tspans = "".join(
        f'<tspan x="600" dy="{0 if index == 0 else 34}">{html.escape(line)}</tspan>'
        for index, line in enumerate(title_lines)
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="760" viewBox="0 0 1200 760">
<style>
svg{{background:#fbf8ff;font-family:'Courier New',monospace}}.grid{{stroke:#e8d9ff;stroke-width:1}}.concept-edge{{stroke:#8d35d1;stroke-width:4;stroke-dasharray:10 8;animation:flow 2s linear infinite}}.concept-core rect{{fill:#31075b;stroke:#39e7ff;stroke-width:4;filter:drop-shadow(9px 9px 0 #ff2fc3)}}.core-title{{fill:white;font-size:25px;font-weight:900;text-anchor:middle}}.core-category{{fill:#d8b8ff;font-size:12px;letter-spacing:1.3px;text-anchor:middle}}.concept-node{{cursor:pointer;outline:none}}.concept-node rect{{fill:white;stroke:#5a1489;stroke-width:3;filter:drop-shadow(6px 6px 0 #d4a9ff);transition:120ms ease}}.concept-node:hover rect,.concept-node:focus rect,.concept-node.active rect{{fill:#f3e6ff;stroke:#ff2fc3;transform:translate(-2px,-2px)}}.node-number{{fill:#ff2fc3;font-size:14px;font-weight:900}}.node-label{{fill:#2a0648;font-size:15px;font-weight:900}}.node-detail{{fill:#66318b;font-size:11px}}@keyframes flow{{to{{stroke-dashoffset:-36}}}}
</style><defs><pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse"><path class="grid" d="M24 0L0 0 0 24" fill="none"/></pattern></defs><rect width="100%" height="100%" fill="url(#grid)"/><g>{''.join(edge_markup)}</g><g class="concept-core"><rect x="430" y="275" width="340" height="180" rx="4"/><text class="core-title" x="600" y="330">{title_tspans}</text><text class="core-category" x="600" y="425">{html.escape(concept.category.upper())}</text></g><g>{''.join(node_markup)}</g></svg>"""


def governed_loop_svg() -> str:
    nodes = (
        ("HRT", "Interpret human intent", 40, 285, "hrt"),
        ("OURD", "Map objects, relations, boundaries, and uncertainty", 250, 150, "ourd"),
        ("IURM", "Isolate a discriminating dimension", 500, 150, "iurm"),
        ("EON", "Bind one exact governed action", 750, 150, "eon"),
        ("GATE", "Check authority and evidence", 1000, 150, "gate"),
        ("ACTION", "Execute one permitted effect", 1000, 435, "action"),
        ("CFEL", "Turn collision into revised evidence", 665, 520, "cfel"),
        ("OBSERVE", "Compare expected and actual", 350, 520, "observe"),
    )
    positions = {system: (x, y) for _, _, x, y, system in nodes}
    paths = (
        ("hrt", "ourd"), ("ourd", "iurm"), ("iurm", "eon"), ("eon", "gate"),
        ("gate", "action"), ("action", "cfel"), ("cfel", "observe"),
    )
    edges = []
    for start, end in paths:
        x1, y1 = positions[start]
        x2, y2 = positions[end]
        edges.append(f'<path class="loop-edge" d="M {x1 + 160} {y1 + 58} L {x2} {y2 + 58}" />')
    edges.append('<path class="loop-edge feedback" d="M 350 578 C 180 650, 130 140, 250 208" />')
    node_markup = []
    for index, (label, detail, x, y, system) in enumerate(nodes, start=1):
        node_markup.append(
            f'<g class="loop-node" data-system="{system}" tabindex="0" role="button" data-detail="{html.escape(detail, quote=True)}">'
            f'<rect x="{x}" y="{y}" width="190" height="116" rx="3" />'
            f'<text class="loop-index" x="{x + 16}" y="{y + 27}">{index:02d}</text>'
            f'<text class="loop-label" x="{x + 54}" y="{y + 31}">{label}</text>'
            f'<text class="loop-detail" x="{x + 16}" y="{y + 68}"><tspan x="{x + 16}">{html.escape(wrapped_svg_text(detail, 27, 2)[0])}</tspan>'
            + (f'<tspan x="{x + 16}" dy="17">{html.escape(wrapped_svg_text(detail, 27, 2)[1])}</tspan>' if len(wrapped_svg_text(detail, 27, 2)) > 1 else "")
            + f'</text><title>{html.escape(label)}: {html.escape(detail)}</title></g>'
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1240" height="720" viewBox="0 0 1240 720">
<style>svg{{background:#fbf8ff;font-family:'Courier New',monospace}}.grid{{stroke:#e7d8ff;stroke-width:1}}.loop-edge{{fill:none;stroke:#8f35d4;stroke-width:5;stroke-dasharray:12 9;animation:flow 1.8s linear infinite}}.feedback{{stroke:#ff2fc3}}.loop-node{{cursor:pointer;outline:none}}.loop-node rect{{fill:white;stroke:#4d0e78;stroke-width:4;filter:drop-shadow(7px 7px 0 #d4a9ff);transition:120ms ease}}.loop-node:hover rect,.loop-node:focus rect,.loop-node.active rect{{fill:#f1e1ff;stroke:#ff2fc3;transform:translate(-2px,-2px)}}.loop-index{{fill:#ff2fc3;font-size:14px;font-weight:900}}.loop-label{{fill:#260644;font-size:20px;font-weight:900}}.loop-detail{{fill:#66318b;font-size:11px}}.doctrine{{fill:#31075b;font-size:18px;font-weight:900;text-anchor:middle;letter-spacing:1px}}@keyframes flow{{to{{stroke-dashoffset:-42}}}}</style><defs><pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse"><path class="grid" d="M24 0L0 0 0 24" fill="none"/></pattern></defs><rect width="100%" height="100%" fill="url(#grid)"/><text class="doctrine" x="620" y="65">REASONING POWER ≠ MUTATION AUTHORITY</text><g>{''.join(edges)}</g><g>{''.join(node_markup)}</g></svg>"""


def concept_atlas_svg(concepts: tuple[Concept, ...]) -> str:
    categories = sorted({concept.category for concept in concepts})
    center_x, center_y = 650, 390
    node_width, node_height = 260, 92
    perimeter_positions = (
        (25, 70), (335, 70), (645, 70), (955, 70),
        (25, 235), (25, 410), (1015, 235), (1015, 410),
        (180, 585), (520, 585), (860, 585),
    )
    positions = [
        (category, *perimeter_positions[index])
        for index, category in enumerate(categories)
    ]
    nodes = []
    edges = []
    for category, x, y in positions:
        count = sum(1 for concept in concepts if concept.category == category)
        nodes.append(
            f'<g class="atlas-category" data-category="{html.escape(category.lower(), quote=True)}" tabindex="0" role="button">'
            f'<rect x="{x}" y="{y}" width="{node_width}" height="{node_height}" rx="3" />'
            f'<text class="atlas-title" x="{x + 18}" y="{y + 38}">{svg_text(category, 31)}</text>'
            f'<text class="atlas-count" x="{x + 18}" y="{y + 68}">{count:03d} CONCEPTS</text>'
            f'<title>Filter to {html.escape(category)}</title></g>'
        )
        edges.append(f'<path class="atlas-edge" d="M {center_x} {center_y} L {x + node_width / 2} {y + node_height / 2}" />')
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1300" height="760" viewBox="0 0 1300 760"><style>svg{{background:#fbf8ff;font-family:'Courier New',monospace}}.grid{{stroke:#e8d9ff;stroke-width:1}}.atlas-edge{{stroke:#8e36d2;stroke-width:3;stroke-dasharray:9 8;animation:flow 2.2s linear infinite}}.atlas-core rect{{fill:#31075b;stroke:#39e7ff;stroke-width:4;filter:drop-shadow(8px 8px 0 #ff2fc3)}}.core-title{{fill:white;font-size:23px;font-weight:900;text-anchor:middle}}.core-sub{{fill:#dcc2ff;font-size:12px;text-anchor:middle;letter-spacing:1px}}.atlas-category{{cursor:pointer;outline:none}}.atlas-category rect{{fill:white;stroke:#551081;stroke-width:3;filter:drop-shadow(6px 6px 0 #d4a9ff)}}.atlas-category:hover rect,.atlas-category:focus rect,.atlas-category.active rect{{fill:#f2e4ff;stroke:#ff2fc3}}.atlas-title{{fill:#2b074c;font-size:13px;font-weight:900}}.atlas-count{{fill:#8c32ca;font-size:11px;letter-spacing:1px}}@keyframes flow{{to{{stroke-dashoffset:-34}}}}</style><defs><pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse"><path class="grid" d="M24 0L0 0 0 24" fill="none"/></pattern></defs><rect width="100%" height="100%" fill="url(#grid)"/><g>{''.join(edges)}</g><g class="atlas-core"><rect x="505" y="320" width="290" height="140" rx="4"/><text class="core-title" x="650" y="374">OIEC-STM CONCEPT ATLAS</text><text class="core-sub" x="650" y="407">{len(concepts)} SOURCE-DERIVED CONCEPTS</text><text class="core-sub" x="650" y="430">SELECT A CATEGORY TO FILTER</text></g><g>{''.join(nodes)}</g></svg>"""


def index_svg(documents: tuple[Document, ...]) -> str:
    categories = sorted({category_for(document) for document in documents})
    category_positions = {
        "Architecture Decisions": (80, 160),
        "Command Fabric": (430, 90),
        "Evidence and Assurance": (780, 160),
        "GUI Workbench": (780, 390),
        "Lifecycle and Migration": (430, 470),
        "Safety and Threats": (80, 390),
    }
    center_x, center_y = 570, 315
    nodes = []
    edges = []
    for index, category in enumerate(categories):
        x, y = category_positions.get(category, (80 + (index % 3) * 350, 160 + (index // 3) * 230))
        count = len([document for document in documents if category_for(document) == category])
        nodes.append(
            f'<g class="category-node" data-category="{html.escape(category.lower())}" tabindex="0">'
            f'<rect x="{x}" y="{y}" width="290" height="105" rx="4" />'
            f'<text class="category-title" x="{x + 22}" y="{y + 42}">{svg_text(category, 30)}</text>'
            f'<text class="category-count" x="{x + 22}" y="{y + 76}">{count:02d} DOCUMENTS</text>'
            f'<title>Filter the documentation tree to {html.escape(category)}</title></g>'
        )
        edges.append(
            f'<path class="bus" d="M {center_x} {center_y} L {x + 145} {y + 52}" />'
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1140" height="680" viewBox="0 0 1140 680">
<style>
svg{{background:#fbf8ff;font-family:'Courier New',monospace}}.grid{{stroke:#eadfff;stroke-width:1}}.bus{{stroke:#7a26c9;stroke-width:4;stroke-dasharray:9 8;animation:flow 2.4s linear infinite}}.core rect{{fill:#2b0a5a;stroke:#ff44cc;stroke-width:4;filter:drop-shadow(8px 8px 0 #cda9ff)}}.core-title{{fill:white;font-size:22px;font-weight:700;letter-spacing:2px}}.core-sub{{fill:#e6cfff;font-size:12px;letter-spacing:1px}}.category-node{{cursor:pointer;outline:none}}.category-node rect{{fill:white;stroke:#5c158e;stroke-width:3;filter:drop-shadow(6px 6px 0 #d7b8ff);transition:120ms ease}}.category-node:hover rect,.category-node:focus rect{{fill:#f4e9ff;stroke:#ff31c7;transform:translate(-2px,-2px)}}.category-title{{fill:#2b0a5a;font-size:16px;font-weight:700}}.category-count{{fill:#8c35c4;font-size:12px;letter-spacing:1.5px}}@keyframes flow{{to{{stroke-dashoffset:-34}}}}
</style><defs><pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse"><path class="grid" d="M24 0L0 0 0 24" fill="none"/></pattern></defs><rect width="100%" height="100%" fill="url(#grid)"/><g>{''.join(edges)}</g><g class="core"><rect x="430" y="255" width="280" height="120" rx="4"/><text class="core-title" x="472" y="306">DOCS/INDEX.HTML</text><text class="core-sub" x="476" y="338">SYSTEMS ARCHITECT BUS</text></g><g>{''.join(nodes)}</g></svg>"""


RELATIONAL_KIND_STYLES = {
    "root": ("#2a0648", "#39e7ff", "RT"),
    "category": ("#4b117a", "#ff2fc3", "CT"),
    "folder": ("#6a1aa5", "#fff36a", "FD"),
    "document": ("#7c2bc0", "#54f0a8", "DC"),
    "heading": ("#9a3bd6", "#ffffff", "HD"),
    "concept": ("#38115d", "#d4a9ff", "CP"),
}


def relational_symbol_shape(kind: str, fill: str, accent: str) -> str:
    if kind == "root":
        return (
            f'<path d="M48 10 76 24 86 52 68 80 28 80 10 52 20 24Z" fill="{fill}" stroke="{accent}" stroke-width="4" />'
            f'<rect x="31" y="31" width="34" height="34" fill="#ffffff" stroke="{accent}" stroke-width="4" />'
            f'<path d="M48 10V31M86 52H65M48 65V80M10 52H31" stroke="{accent}" stroke-width="4" />'
        )
    if kind == "category":
        return (
            f'<path d="M16 20H80V76H16Z" fill="{fill}" stroke="{accent}" stroke-width="4" />'
            f'<path d="M24 30H72M24 48H64M24 66H54" stroke="#ffffff" stroke-width="5" />'
            f'<rect x="10" y="38" width="8" height="20" fill="{accent}" /><rect x="78" y="38" width="8" height="20" fill="{accent}" />'
        )
    if kind == "folder":
        return (
            f'<path d="M12 28H39L47 20H84V76H12Z" fill="{fill}" stroke="{accent}" stroke-width="4" />'
            f'<path d="M20 42H76V68H20Z" fill="#ffffff" stroke="{accent}" stroke-width="3" />'
        )
    if kind == "document":
        return (
            f'<path d="M22 10H61L78 27V86H22Z" fill="#ffffff" stroke="{fill}" stroke-width="5" />'
            f'<path d="M61 10V28H78" fill="{accent}" stroke="{fill}" stroke-width="4" />'
            f'<path d="M32 42H68M32 55H68M32 68H58" stroke="{fill}" stroke-width="4" />'
        )
    if kind == "heading":
        return (
            f'<path d="M48 9 86 48 48 87 10 48Z" fill="{fill}" stroke="{accent}" stroke-width="4" />'
            f'<path d="M29 38H67M29 49H67M38 60H58" stroke="#ffffff" stroke-width="4" />'
        )
    return (
        f'<circle cx="48" cy="48" r="28" fill="{fill}" stroke="{accent}" stroke-width="4" />'
        f'<ellipse cx="48" cy="48" rx="42" ry="17" fill="none" stroke="{accent}" stroke-width="3" />'
        f'<circle cx="18" cy="48" r="6" fill="#ffffff" /><circle cx="73" cy="35" r="6" fill="#ffffff" />'
    )


def relational_symbol_svg(relational_object: RelationalObject) -> str:
    fill, accent, kind_code = RELATIONAL_KIND_STYLES[relational_object.kind]
    digest = hashlib.sha256(relational_object.object_id.encode("utf-8")).digest()
    fingerprint_cells = []
    for cell_index in range(16):
        column = cell_index % 4
        row = cell_index // 4
        enabled = digest[cell_index] % 2 == 1
        fingerprint_cells.append(
            f'<rect x="{70 + column * 5}" y="{72 + row * 5}" width="4" height="4" '
            f'fill="{accent if enabled else "#d9c1ef"}" />'
        )
    metadata = html.escape(
        json.dumps(relational_record(relational_object), sort_keys=True, ensure_ascii=False),
        quote=False,
    )
    shape = relational_symbol_shape(relational_object.kind, fill, accent)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96" role="img" data-object-id="{html.escape(relational_object.object_id, quote=True)}" data-object-kind="{html.escape(relational_object.kind, quote=True)}">
<title>{html.escape(relational_object.title)}</title><desc>{html.escape(relational_object.description)} Relation: {html.escape(relational_object.relation)}.</desc><metadata>{metadata}</metadata>
<style>svg{{background:#fbf8ff}}[data-symbol-core]{{transform-origin:48px 48px;transition:transform 160ms ease,filter 160ms ease}}svg[data-active="true"] [data-symbol-core]{{transform:scale(1.05);filter:drop-shadow(0 0 6px {accent})}}@media(prefers-reduced-motion:reduce){{[data-symbol-core]{{transition:none}}}}</style>
<g id="object-symbol" data-symbol-core="true">{shape}<rect x="4" y="4" width="25" height="16" fill="#ffffff" stroke="{fill}" stroke-width="2" /><text x="16.5" y="16" fill="{fill}" font-family="Courier New,monospace" font-size="9" font-weight="700" text-anchor="middle">{kind_code}</text>{''.join(fingerprint_cells)}</g>
</svg>"""


def relational_symbol_sprite_svg(
    relational_objects: tuple[RelationalObject, ...],
) -> str:
    symbols = []
    for relational_object in relational_objects:
        fill, accent, kind_code = RELATIONAL_KIND_STYLES[relational_object.kind]
        digest = hashlib.sha256(relational_object.object_id.encode("utf-8")).digest()
        fingerprint_cells = []
        for cell_index in range(16):
            column = cell_index % 4
            row = cell_index // 4
            enabled = digest[cell_index] % 2 == 1
            fingerprint_cells.append(
                f'<rect x="{70 + column * 5}" y="{72 + row * 5}" width="4" height="4" '
                f'fill="{accent if enabled else "#d9c1ef"}" />'
            )
        shape = relational_symbol_shape(relational_object.kind, fill, accent)
        symbols.append(
            f'<symbol id="{html.escape(relational_object.object_id, quote=True)}" '
            f'viewBox="0 0 96 96">'
            f'<title>{html.escape(relational_object.title)}</title>'
            f'<desc>{html.escape(relational_object.description)}</desc>'
            f'<g data-symbol-core="true">{shape}'
            f'<rect x="4" y="4" width="25" height="16" fill="#ffffff" '
            f'stroke="{fill}" stroke-width="2" />'
            f'<text x="16.5" y="16" fill="{fill}" font-family="Courier New,monospace" '
            f'font-size="9" font-weight="700" text-anchor="middle">{kind_code}</text>'
            f'{"".join(fingerprint_cells)}</g></symbol>'
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" role="img">
<title>OIEC-STM relational object symbol sprite</title>
<desc>Deterministic reusable symbols for every invariant relational object in the documentation tree.</desc>
<defs>{''.join(symbols)}</defs>
</svg>"""


def relational_topology_svg(relational_objects: tuple[RelationalObject, ...]) -> str:
    kind_order = ("category", "folder", "document", "heading", "concept")
    positions = {
        "category": (155, 115),
        "folder": (505, 72),
        "document": (850, 145),
        "heading": (790, 455),
        "concept": (210, 465),
    }
    center_x, center_y = 560, 320
    edges = []
    nodes = []
    for kind in kind_order:
        position_x, position_y = positions[kind]
        count = sum(item.kind == kind for item in relational_objects)
        fill, accent, kind_code = RELATIONAL_KIND_STYLES[kind]
        edges.append(
            f'<path class="topology-edge" d="M {center_x} {center_y} L {position_x + 120} {position_y + 60}" />'
        )
        nodes.append(
            f'<g class="topology-kind" data-relational-kind="{kind}" tabindex="0" role="button" aria-label="Filter to {kind} objects">'
            f'<rect x="{position_x}" y="{position_y}" width="240" height="120" fill="#ffffff" stroke="{fill}" stroke-width="4" />'
            f'<rect x="{position_x + 16}" y="{position_y + 18}" width="48" height="48" fill="{fill}" stroke="{accent}" stroke-width="3" />'
            f'<text x="{position_x + 40}" y="{position_y + 49}" text-anchor="middle" fill="#ffffff" font-size="15" font-weight="700">{kind_code}</text>'
            f'<text x="{position_x + 78}" y="{position_y + 42}" fill="#2a0648" font-size="15" font-weight="700">{kind.upper()}</text>'
            f'<text x="{position_x + 78}" y="{position_y + 65}" fill="#6a1aa5" font-size="12">{count:03d} OBJECTS</text>'
            f'<path d="M {position_x + 18} {position_y + 88} H {position_x + 220}" stroke="{accent}" stroke-width="3" stroke-dasharray="8 6" />'
            f'<title>{count} {kind} relational objects</title></g>'
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1120" height="650" viewBox="0 0 1120 650" role="img">
<title>OIEC-STM documentation relational topology</title><desc>Interactive map of category, folder, document, heading, and concept objects connected to the documentation root.</desc>
<style>svg{{background:#170326;font-family:'Courier New',monospace}}.grid{{stroke:#4b117a;stroke-width:1}}.topology-edge{{fill:none;stroke:#b65cff;stroke-width:4;stroke-dasharray:10 10;animation:signal 2.2s linear infinite}}.topology-kind{{cursor:pointer;outline:none}}.topology-kind rect{{transition:160ms ease;filter:drop-shadow(7px 7px 0 #4b117a)}}.topology-kind:hover rect,.topology-kind:focus rect,.topology-kind.active rect{{stroke:#39e7ff;filter:drop-shadow(7px 7px 0 #ff2fc3)}}.root-core rect{{fill:#ffffff;stroke:#39e7ff;stroke-width:5;filter:drop-shadow(10px 10px 0 #ff2fc3)}}@keyframes signal{{to{{stroke-dashoffset:-40}}}}@media(prefers-reduced-motion:reduce){{.topology-edge{{animation:none}}}}</style>
<defs><pattern id="topology-grid" width="24" height="24" patternUnits="userSpaceOnUse"><path class="grid" d="M24 0H0V24" fill="none" /></pattern></defs><rect width="100%" height="100%" fill="url(#topology-grid)" />
<g>{''.join(edges)}</g><g class="root-core"><rect x="410" y="250" width="300" height="140" /><text x="560" y="300" text-anchor="middle" fill="#2a0648" font-size="22" font-weight="700">OIEC-STM OBJECT BUS</text><text x="560" y="332" text-anchor="middle" fill="#6a1aa5" font-size="13">{len(relational_objects):03d} INVARIANT OBJECTS</text><text x="560" y="362" text-anchor="middle" fill="#ff2fc3" font-size="11">SELECT A KIND TO FILTER</text></g><g>{''.join(nodes)}</g>
</svg>"""


def decorate_svg(
    svg: str,
    visual_role: str,
    node_id: str,
    label: str,
    node_role: str = "process",
) -> str:
    attributes = f"{root_attributes(visual_role)} {node_attributes(node_id, node_role, label)}"
    decorated = svg.replace("<svg ", f"<svg {attributes} ", 1)
    root_end = decorated.find(">")
    root_body = decorated[root_end + 1 :]
    if not re.match(r"\s*<title(?:\s|>)", root_body):
        accessible = (
            f"<title>{html.escape(label)}</title>"
            f"<desc>Generated {html.escape(visual_role)} diagram for {html.escape(label)}.</desc>"
        )
        decorated = decorated[: root_end + 1] + accessible + decorated[root_end + 1 :]
    validate_svg(decorated)
    return decorated


def learning_loop_svg() -> str:
    stages = (
        ("ask", "You ask for work", "concept"),
        ("understand", "Understand it", "process"),
        ("known", "Find what is already known", "process"),
        ("safe", "Try safely", "authority"),
        ("check", "Check the result", "gate"),
        ("remember", "Remember what was learned", "canonical"),
    )
    nodes = []
    edges = []
    for index, (node_id, label, role) in enumerate(stages):
        y = 45 + index * 108
        nodes.append(
            f'<g class="learning-node role-{role}" {node_attributes(node_id, role, label)}>'
            f'<rect x="135" y="{y}" width="450" height="72" rx="18" />'
            f'<text x="360" y="{y + 43}" text-anchor="middle">{html.escape(label)}</text></g>'
        )
        if index:
            edges.append(
                f'<path class="learning-edge" d="M360 {y - 36} V {y}" {edge_attributes("next-stage", "verified")} />'
            )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" {root_attributes('learning-loop')} width="720" height="700" viewBox="0 0 720 700" role="img">
<title>A careful work loop</title><desc>A request moves through understanding, retrieval, bounded action, checking, and learning.</desc>
<style>svg{{background:#fbfdff;font-family:system-ui,sans-serif}}.learning-node{{outline:none;cursor:pointer}}.learning-node rect{{fill:#fff;stroke:#24425f;stroke-width:3}}.learning-node text{{fill:#13283b;font-size:20px;font-weight:700}}.role-authority rect{{fill:#eef8ff;stroke:#176a9a}}.role-gate rect{{fill:#fff8dc;stroke:#9b6b00}}.role-canonical rect{{fill:#effcf3;stroke:#237a43;stroke-width:6}}.learning-node:focus rect,.learning-node:hover rect{{stroke:#b11f72}}.learning-edge{{fill:none;stroke:#24425f;stroke-width:4;marker-end:url(#arrow)}}@media(prefers-reduced-motion:no-preference){{.learning-edge{{stroke-dasharray:8 7;animation:flow 2s linear infinite}}@keyframes flow{{to{{stroke-dashoffset:-30}}}}}}</style>
<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="6" refY="3" orient="auto"><path d="M0 0L0 6L7 3Z" fill="#24425f"/></marker></defs>
<g>{''.join(edges)}</g><g>{''.join(nodes)}</g></svg>"""


def tutorial_svg(lesson: object) -> str:
    fixtures = load_learning_fixtures()
    states: list[str] = []
    for fixture_id in lesson.fixture_ids:
        record = fixtures[fixture_id]
        states.extend(str(item) for item in record.get("states", []))
    if not states:
        states = [lesson.reader_outcome, "Inspect the source record", "Continue safely"]
    states = states[:8]
    width = 1080
    height = 190 + len(states) * 92
    nodes = []
    edges = []
    roles = ("concept", "process", "evidence", "gate", "authority", "canonical")
    for index, state in enumerate(states):
        x = 110 if index % 2 == 0 else 570
        y = 125 + index * 82
        role = roles[min(index, len(roles) - 1)]
        node_id = f"{lesson.lesson_id.lower()}-{index + 1}"
        nodes.append(
            f'<g class="tutorial-node role-{role}" {node_attributes(node_id, role, state)}>'
            f'<rect x="{x}" y="{y}" width="400" height="62" rx="14" />'
            f'<text x="{x + 200}" y="{y + 37}" text-anchor="middle">{svg_text(state, 45)}</text></g>'
        )
        if index:
            previous_x = 310 if (index - 1) % 2 == 0 else 770
            previous_y = 125 + (index - 1) * 82 + 62
            current_x = x + 200
            edges.append(
                f'<path class="tutorial-edge" d="M{previous_x} {previous_y} L{current_x} {y}" {edge_attributes("lesson-sequence", "verified")} />'
            )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" {root_attributes('tutorial-diagram')} width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">
<title>{html.escape(lesson.title)} lesson diagram</title><desc>{html.escape(lesson.reader_outcome)}</desc>
<style>svg{{background:#fbfdff;font-family:system-ui,sans-serif}}.title{{fill:#13283b;font-size:28px;font-weight:800}}.tutorial-node{{outline:none;cursor:pointer}}.tutorial-node rect{{fill:#fff;stroke:#24425f;stroke-width:3}}.tutorial-node text{{fill:#13283b;font-size:15px;font-weight:700}}.role-evidence rect{{fill:#eef8ff}}.role-gate rect{{fill:#fff8dc}}.role-authority rect{{fill:#f4efff}}.role-canonical rect{{fill:#effcf3;stroke-width:6}}.tutorial-node:focus rect,.tutorial-node:hover rect{{stroke:#b11f72}}.tutorial-edge{{fill:none;stroke:#516b80;stroke-width:3;marker-end:url(#arrow)}}</style>
<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="6" refY="3" orient="auto"><path d="M0 0L0 6L7 3Z" fill="#516b80"/></marker></defs>
<text class="title" x="70" y="62">{html.escape(lesson.lesson_id)} · {html.escape(lesson.title)}</text><g>{''.join(edges)}</g><g>{''.join(nodes)}</g></svg>"""


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def build(build_date: str) -> tuple[tuple[Document, ...], tuple[Concept, ...]]:
    documents = discover_documents()
    concepts = discover_concepts()
    statuses = discover_statuses()
    teaching_records = tuple(teaching_record_for(concept) for concept in concepts)
    if not documents:
        raise SystemExit("No Markdown files found under docs/")
    if not concepts:
        raise SystemExit("No OIEC-STM-Agent concepts discovered")
    validate_catalog_sources()
    validate_recipes()
    validate_statuses(statuses)
    validate_prerequisite_graph(teaching_records)
    relational_objects = build_relational_objects(documents, concepts)
    validate_relational_objects(relational_objects)

    figures_root = DOCS_ROOT / "figures"
    for index, document in enumerate(documents):
        previous = documents[index - 1] if index else None
        following = documents[index + 1] if index + 1 < len(documents) else None
        write_text(document.output_path, document_template(document, previous, following, build_date))
        figure_path = figures_root / document.relative_path.with_suffix(".svg")
        write_text(
            figure_path,
            decorate_svg(
                document_svg(document),
                "expert-document",
                f"document-{slugify(document.relative_path.as_posix())}",
                document.title,
            ),
        )

    concepts_root = DOCS_ROOT / "concepts"
    concept_figures_root = figures_root / "concepts"
    concepts_root.mkdir(parents=True, exist_ok=True)
    concept_figures_root.mkdir(parents=True, exist_ok=True)
    for stale_path in concepts_root.glob("*.html"):
        stale_path.unlink()
    for stale_path in concept_figures_root.glob("*.svg"):
        stale_path.unlink()
    for index, concept in enumerate(concepts):
        previous = concepts[index - 1] if index else None
        following = concepts[index + 1] if index + 1 < len(concepts) else None
        write_text(
            concepts_root / f"{concept.slug}.html",
            concept_page_template(concept, previous, following, build_date),
        )
        write_text(
            concept_figures_root / f"{concept.slug}.svg",
            decorate_svg(
                concept_svg(concept),
                "concept",
                f"concept-{concept.slug}",
                concept.title,
                "concept",
            ),
        )

    relational_figures_root = figures_root / "relational-objects"
    relational_figures_root.mkdir(parents=True, exist_ok=True)
    for stale_path in relational_figures_root.glob("*.svg"):
        stale_path.unlink()
    for relational_object in relational_objects:
        write_text(
            DOCS_ROOT / relational_object.symbol_path,
            decorate_svg(
                relational_symbol_svg(relational_object),
                "relational-object",
                relational_object.object_id,
                relational_object.title,
                "object",
            ),
        )

    write_text(concepts_root / "index.html", concept_atlas_template(concepts, build_date))
    write_text(
        DOCS_ROOT / "index.html",
        index_template(documents, concepts, relational_objects, build_date),
    )
    write_text(
        DOCS_ROOT / "architecture-explorer.html",
        architecture_explorer_template(documents, concepts, relational_objects, build_date),
    )
    write_text(DOCS_ROOT / "tutorial" / "index.html", tutorial_index_template(build_date))
    tutorial_figures_root = figures_root / "tutorial"
    for lesson in TUTORIALS:
        write_text(
            (ROOT / lesson.source_path).with_suffix(".html"),
            tutorial_page_template(lesson, build_date),
        )
        write_text(
            tutorial_figures_root / f"{lesson.lesson_id.lower()}.svg",
            tutorial_svg(lesson),
        )
    write_text(DOCS_ROOT / "tasks" / "index.html", task_index_template(build_date))
    for route in TASK_ROUTES:
        write_text(
            (ROOT / route.source_path).with_suffix(".html"),
            learning_source_page_template(route, "task guide", build_date),
        )
    write_text(
        DOCS_ROOT / "case-studies" / "index.html",
        case_study_index_template(build_date),
    )
    for case in CASE_STUDIES:
        write_text(
            (ROOT / case.source_path).with_suffix(".html"),
            learning_source_page_template(case, "case study", build_date),
        )
    write_text(DOCS_ROOT / "glossary.html", glossary_template(build_date))
    write_text(DOCS_ROOT / "status-decoder.html", status_decoder_template(statuses, build_date))
    write_text(DOCS_ROOT / "tools.html", tools_template(build_date))
    write_text(DOCS_ROOT / "timeline.html", timeline_template(build_date))
    write_text(
        DOCS_ROOT / "failure-museum.html",
        failure_museum_template(statuses, build_date),
    )
    write_text(figures_root / "learning-loop.svg", learning_loop_svg())
    write_text(
        figures_root / "index-architecture.svg",
        decorate_svg(
            index_svg(documents),
            "expert-index",
            "expert-document-index",
            "Expert documentation index",
            "object",
        ),
    )
    write_text(
        figures_root / "governed-loop.svg",
        decorate_svg(
            governed_loop_svg(),
            "governed-loop",
            "governed-loop",
            "Governed reasoning and action loop",
        ),
    )
    write_text(
        figures_root / "concept-atlas.svg",
        decorate_svg(
            concept_atlas_svg(concepts),
            "concept-atlas",
            "concept-atlas",
            "Concept atlas",
            "concept",
        ),
    )
    write_text(
        figures_root / "relational-symbols.svg",
        decorate_svg(
            relational_symbol_sprite_svg(relational_objects),
            "relational-sprite",
            "relational-symbol-sprite",
            "Relational object symbol sprite",
            "object",
        ),
    )
    write_text(
        figures_root / "relational-topology.svg",
        decorate_svg(
            relational_topology_svg(relational_objects),
            "relational-topology",
            "relational-topology",
            "Relational topology",
            "object",
        ),
    )

    relational_relations = []
    for relational_object in relational_objects:
        if relational_object.parent_id:
            relational_relations.append(
                {
                    "source_id": relational_object.object_id,
                    "target_id": relational_object.parent_id,
                    "relation": relational_object.relation,
                    "canonical": True,
                }
            )
        for related_id in relational_object.related_ids:
            relational_relations.append(
                {
                    "source_id": relational_object.object_id,
                    "target_id": related_id,
                    "relation": "related-to",
                    "canonical": False,
                }
            )

    teaching_by_id = {record.concept_id: record for record in teaching_records}
    manifest = {
        "schema_version": 2,
        "build_date": build_date,
        "documentation_version": documentation_version(),
        "source_snapshot_sha256": source_snapshot_digest(),
        "content_kinds": list(CONTENT_KINDS),
        "documentation_statuses": list(DOCUMENTATION_STATUSES),
        "documents": [
            {
                "title": document.title,
                "source": document.relative_path.as_posix(),
                "html": document.relative_path.with_suffix(".html").as_posix(),
                "figure": (Path("figures") / document.relative_path.with_suffix(".svg")).as_posix(),
                "source_sha256": hashlib.sha256(document.source_path.read_bytes()).hexdigest(),
                "headings": [
                    {"title": section.title, "slug": section.slug, "level": section.level}
                    for section in document.sections
                ],
            }
            for document in documents
        ],
        "concepts": [
            {
                "slug": concept.slug,
                "title": concept.title,
                "category": concept.category,
                "definition": concept.definition,
                "thesis": concept.thesis,
                "html": f"concepts/{concept.slug}.html",
                "figure": f"figures/concepts/{concept.slug}.svg",
                "sources": [
                    {
                        "path": source,
                        "sha256": hashlib.sha256((ROOT / source).read_bytes()).hexdigest(),
                    }
                    for source in concept.sources
                ],
                "related": list(concept.related),
                "teaching": learning_records_for_manifest((teaching_by_id[concept.slug],))[0],
            }
            for concept in concepts
        ],
        "learning_paths": learning_records_for_manifest(LEARNING_PATHS),
        "tutorials": learning_records_for_manifest(TUTORIALS),
        "task_routes": learning_records_for_manifest(TASK_ROUTES),
        "case_studies": learning_records_for_manifest(CASE_STUDIES),
        "invention_timeline": learning_records_for_manifest(INVENTION_TIMELINE),
        "acronyms": learning_records_for_manifest(ACRONYMS),
        "cli": {
            "programs": cli_records_for_manifest(PROGRAMS),
            "recipes": cli_records_for_manifest(RECIPES),
            "rejected_recipes": cli_records_for_manifest(REJECTED_RECIPES),
            "providers": cli_records_for_manifest(PROVIDERS),
            "command_builder_schema": COMMAND_BUILDER_SCHEMA,
        },
        "statuses": status_records_for_manifest(statuses),
        "visual_grammar": grammar_manifest(),
        "relational_objects": [
            relational_record(relational_object)
            for relational_object in relational_objects
        ],
        "relational_relations": relational_relations,
        "relational_summary": {
            "object_count": len(relational_objects),
            "relation_count": len(relational_relations),
            "symbol_count": len(relational_objects),
            "kinds": {
                kind: sum(item.kind == kind for item in relational_objects)
                for kind in RELATIONAL_KIND_STYLES
            },
            "sprite_figure": "figures/relational-symbols.svg",
            "topology_figure": "figures/relational-topology.svg",
        },
        "governed_loop": {
            "pipeline": ["HRTv1", "OURD", "IURMv1.1.1", "EONv1", "Evidence Gate", "Action", "CFEL"],
            "figure": "figures/governed-loop.svg",
            "thesis": "The agent is an uncertainty-reduction machine whose reasoning remains separate from mutation authority.",
        },
        "essay_logic_topology": [
            {
                "stage": stage,
                "nodes": [
                    {"id": node_id, "topic": topic}
                    for node_id, topic in nodes
                ],
            }
            for stage, nodes in ESSAY_LOGIC_TOPOLOGY
        ],
        "essay_logic_edges": [
            {"source": source, "target": target}
            for source, target in ESSAY_LOGIC_EDGES
        ],
        "essay_contract": {
            "paragraphs_per_essay": 25,
            "stages": len(ESSAY_LOGIC_TOPOLOGY),
            "ordering": "topological",
            "entry_node": ESSAY_LOGIC_ORDER[0],
            "final_node": "verdict-winner",
            "final_requirement": "Summarise the tested claim and name the winning position.",
        },
        "references": list(REFERENCE_LIBRARY),
        "glossary": {
            **GLOSSARY,
            **CONSTANT_DEFINITIONS,
            **{record.token: record.short_meaning for record in ACRONYMS},
        },
        "coverage": {
            "concepts": {
                "total": len(concepts),
                "teaching_records": len(teaching_records),
                "examples": sum(bool(record.oiec_example) for record in teaching_records),
                "diagrams": sum(bool(record.diagram) for record in teaching_records),
                "misconceptions": sum(bool(record.misconception) for record in teaching_records),
                "prerequisites": sum(record.prerequisites is not None for record in teaching_records),
                "evidence_badges": sum(bool(record.status_evidence) for record in teaching_records),
            },
            "tutorials": {"total": len(TUTORIALS), "complete": len(TUTORIALS)},
            "task_routes": {"total": len(TASK_ROUTES), "complete": len(TASK_ROUTES)},
            "case_studies": {"total": len(CASE_STUDIES), "complete": len(CASE_STUDIES)},
            "acronyms": {"total": len(ACRONYMS), "defined": len(ACRONYMS)},
            "statuses": {"total": len(statuses), "decoded": len(statuses)},
            "commands": {"total": len(RECIPES), "parser_validated": len(RECIPES)},
        },
    }
    write_text(DOCS_ROOT / "site-manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
    return documents, concepts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date",
        default=os.environ.get("OURD_DOCS_BUILD_DATE", date.today().isoformat()),
        help="Build date rendered into the generated pages (YYYY-MM-DD).",
    )
    args = parser.parse_args()
    documents, concepts = build(args.date)
    relational_objects = build_relational_objects(documents, concepts)
    heading_count = sum(len(document.sections) for document in documents)
    paragraph_count = (heading_count + len(concepts)) * 25
    svg_count = len(documents) + len(concepts) + len(relational_objects) + 6 + len(TUTORIALS)
    html_count = (
        len(documents)
        + len(concepts)
        + 11
        + len(TUTORIALS)
        + len(TASK_ROUTES)
        + len(CASE_STUDIES)
    )
    print(
        f"Built {html_count} HTML pages, {svg_count} SVG figures, and {paragraph_count} "
        f"essay paragraphs from {heading_count} Markdown headings and {len(concepts)} "
        f"concepts with {len(relational_objects)} relational objects."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
