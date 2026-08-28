#!/usr/bin/env python3
"""Build the interactive OIEC-STM-Agent systems-architecture site.

The generator deliberately uses only the Python standard library so the
checked-in documentation can be rebuilt without adding a package dependency.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

try:
    from tools.docs_concept_catalog import CORE_CONCEPTS, Concept, discover_concepts
except ModuleNotFoundError:
    from docs_concept_catalog import CORE_CONCEPTS, Concept, discover_concepts


ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = ROOT / "docs"


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
)


GLOSSARY = {
    "ADR": "Architecture Decision Record: a short document that records a significant design choice, its context, and its consequences.",
    "API": "Application Programming Interface: a defined way for software components to request services from one another.",
    "C0": "Capability class 0: observation only; it may inspect information but cannot create proposals or change the workspace.",
    "C1": "Capability class 1: analysis and internal proposal creation without ordinary workspace mutation.",
    "C2": "Capability class 2: simulation in a disposable, synthetic, or otherwise isolated environment.",
    "C3": "Capability class 3: local workspace mutation through the governed EON execution boundary with exact authority and approval.",
    "C4": "Capability class 4: mutation of an external system; EGCFv1 currently fails closed for this class.",
    "C5": "Capability class 5: critical or destructive mutation; EGCFv1 currently fails closed for this class.",
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
    "OBJ": "Wavefront OBJ: a text-based file format for polygonal 3D geometry.",
    "OFAT": "One Factor At a Time: an experiment strategy that varies one input while holding the others steady.",
    "OURD": "Object-Universe-Relation-Dependency modeling: the project layer that identifies system objects, their boundaries, relations, dependencies, impacts, exclusions, and scope.",
    "PEP": "Python Enhancement Proposal: a design document used to propose and explain changes to Python.",
    "PLY": "Polygon File Format: a format for storing 3D meshes and point-cloud attributes.",
    "PNG": "Portable Network Graphics: a lossless bitmap image format with transparency support.",
    "PTY": "Pseudo-terminal: a software endpoint that behaves like a terminal so another program can control interactive command-line processes.",
    "RFC": "Request for Comments: a published technical specification or best-current-practice document in the Internet standards process.",
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
    "X11": "The X Window System protocol commonly used to display graphical Linux applications.",
}


CONSTANT_DEFINITIONS = {
    "COUNT": "A configuration field that limits or reports how many items are involved.",
    "KEY": "A configuration field or lookup name used to select a value.",
    "MODEL": "A configuration field that names the language or reasoning model to use.",
    "SECONDS": "A duration field measured in seconds.",
    "TOKENS": "A limit expressed in model tokens, which are small units of text processed by a language model.",
}


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


def citation(reference_id: str) -> str:
    return f'<a class="citation-chip" href="#references">[{reference_id}]</a>'


def generate_essay_blocks(document: Document, section: Section) -> tuple[tuple[str, ...], ...]:
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
    concepts = section_concepts(section)
    if not concepts:
        return (
            '<div class="glossary-empty">This section uses ordinary architecture language; '
            "specialist terms are explained in the essay and source evidence.</div>"
        )
    entries = []
    for token in concepts:
        entries.append(
            f'<div class="glossary-entry"><dt>{html.escape(token)}</dt>'
            f'<dd>{html.escape(definition_for(token))}</dd></div>'
        )
    return f"<dl class=\"glossary-grid\">{''.join(entries)}</dl>"


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
    for reference in REFERENCE_LIBRARY:
        items.append(
            f'<li id="ref-{reference["id"]}"><span class="reference-id">{reference["id"]}</span>'
            f'<a href="{html.escape(reference["url"])}" rel="noreferrer">{html.escape(reference["title"])}</a>'
            f'<p><strong>{html.escape(reference["authors"])}</strong> — {html.escape(reference["summary"])}</p></li>'
        )
    return f'<ol class="reference-list">{"".join(items)}</ol>'


def concept_citations(concept: Concept) -> tuple[str, ...]:
    if concept.category == "Governed Reasoning Loop":
        return ("R1", "R2", "R5", "R6", "R7")
    if concept.category in {"Governance and Authority", "Execution Adapters", "Refusal and Error Semantics"}:
        return ("R2", "R3", "R4", "R5", "R7")
    if concept.category in {"Engineering Services", "Semantic Command Namespaces"}:
        return ("R1", "R2", "R4", "R6", "R3")
    if concept.category in {"Persistence and Provenance", "Canonical Records"}:
        return ("R1", "R2", "R3", "R4", "R7")
    return ("R1", "R2", "R3", "R5", "R7")


def generate_concept_essay_blocks(concept: Concept) -> tuple[tuple[str, ...], ...]:
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
    for reference in REFERENCE_LIBRARY:
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
    output_path = DOCS_ROOT / "concepts" / f"{concept.slug}.html"
    styles_url = relative_url(output_path, DOCS_ROOT / "assets" / "styles.css")
    script_url = relative_url(output_path, DOCS_ROOT / "assets" / "site.js")
    docs_index_url = relative_url(output_path, DOCS_ROOT / "index.html")
    atlas_url = relative_url(output_path, DOCS_ROOT / "concepts" / "index.html")
    figure_path = DOCS_ROOT / "figures" / "concepts" / f"{concept.slug}.svg"
    figure_url = relative_url(output_path, figure_path)
    blocks = generate_concept_essay_blocks(concept)
    block_markup = []
    labels = ("Introduction", "Body section one", "Body section two", "Body section three", "Conclusion")
    for block_index, block in enumerate(blocks):
        heading = f"<h3>{html.escape(concept.title)}</h3>" if block_index == 0 else ""
        paragraphs = "".join(
            f'<p data-concept-paragraph="{paragraph_index + 1}">{paragraph}</p>'
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
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Systems architecture concept essay and infographic for {html.escape(concept.title, quote=True)}">
  <title>{html.escape(concept.title)} · OIEC-STM Concept Atlas</title>
  <link rel="stylesheet" href="{styles_url}">
</head>
<body data-page="concept" data-concept="{html.escape(concept.slug)}">
  <div class="scanline-overlay" aria-hidden="true"></div>
  <div class="reading-progress" aria-hidden="true"><span></span></div>
  <header class="site-header">
    <a class="brand" href="{docs_index_url}"><span class="brand-mark">OS</span><span><strong>OIEC-STM CONCEPT ATLAS</strong><small>{html.escape(concept.category)}</small></span></a>
    <nav class="header-actions"><button type="button" data-action="focus-mode">FOCUS</button><a href="{atlas_url}">ATLAS</a><a href="{docs_index_url}">INDEX</a></nav>
  </header>
  <main class="concept-main">
    <section class="concept-hero">
      <p class="eyebrow">CONCEPT CIRCUIT · BUILT {html.escape(build_date)}</p>
      <span class="concept-category">{html.escape(concept.category)}</span>
      <h1>{html.escape(concept.title)}</h1>
      <p class="concept-definition">{html.escape(concept.definition)}</p>
      <p class="concept-thesis">{html.escape(concept.thesis)}</p>
      <dl class="hero-metrics"><div><dt>SOURCES</dt><dd>{len(concept.sources):02d}</dd></div><div><dt>ESSAY PARAGRAPHS</dt><dd>25</dd></div><div><dt>RELATED CONCEPTS</dt><dd>{len(concept.related):02d}</dd></div></dl>
    </section>
    <section class="map-panel concept-map-panel">
      <div><p class="terminal-label">INTERACTIVE INFOGRAPHIC</p><h2>Concept control map</h2><p>Select purpose, inputs, controls, evidence, or outcome to inspect the concept as a systems boundary.</p></div>
      <figure><object class="concept-map" type="image/svg+xml" data="{figure_url}"><a href="{figure_url}">Open the {html.escape(concept.title)} SVG</a></object><figcaption class="concept-map-caption">Select an SVG node to inspect its source-derived explanation.</figcaption></figure>
    </section>
    <section class="concept-facts">
      <article><h2>Central question</h2><p>{html.escape(concept.central_question)}</p></article>
      <article><h2>Related concepts</h2><ul>{related_list}</ul></article>
      <article><h2>Source owners</h2><ul>{source_list}</ul></article>
    </section>
    <article class="concept-essay"><p class="terminal-label">ARGUMENTATIVE LEARNING ESSAY</p><div class="essay-sequence">{''.join(block_markup)}</div></article>
    <section class="references" id="references"><p class="terminal-label">SOURCE AND TEXTBOOK BUS</p><h2>References and summarised excerpts</h2><p>Local source entries establish provenance. External entries provide systems, experiment, security, and architecture lenses; summaries are paraphrases.</p>{concept_source_references(concept, output_path)}</section>
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
        f'<a href="{html.escape(concept.slug)}.html">OPEN ESSAY + INFOGRAPHIC →</a></article>'
        for index, concept in enumerate(concepts, start=1)
    )
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="description" content="Source-derived OIEC-STM-Agent concept atlas"><title>OIEC-STM Concept Atlas</title><link rel="stylesheet" href="../assets/styles.css"></head>
<body data-page="concept-atlas">
  <div class="scanline-overlay" aria-hidden="true"></div>
  <header class="site-header"><a class="brand" href="../index.html"><span class="brand-mark">OS</span><span><strong>OIEC-STM CONCEPT ATLAS</strong><small>{len(concepts)} source-derived concepts</small></span></a><nav class="header-actions"><button type="button" data-action="focus-mode">FOCUS</button><a href="../index.html">INDEX.HTML</a></nav></header>
  <main class="atlas-main">
    <section class="atlas-hero"><div><p class="eyebrow">SOURCE-DERIVED ARCHITECTURE INVENTORY · {html.escape(build_date)}</p><h1>Every named concept should own a testable responsibility.</h1><p>This atlas searches the governed loop, {namespace_count} semantic namespaces, and {runtime_count} public runtime types. Every concept receives a beginner definition, an argumentative 25-paragraph essay, source provenance, textbook lenses, and an interactive SVG.</p></div><object class="atlas-map" type="image/svg+xml" data="../figures/concept-atlas.svg"><a href="../figures/concept-atlas.svg">Open the concept atlas SVG</a></object></section>
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
    labels = ("Introduction", "Body section one", "Body section two", "Body section three", "Conclusion")
    for block_index, block in enumerate(blocks):
        heading = f"<h3>{html.escape(section.title)}</h3>" if block_index == 0 else ""
        paragraphs = "".join(
            f'<p data-essay-paragraph="{paragraph_index + 1}">{paragraph}</p>'
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
    breadcrumb_parts = ["docs", *document.relative_path.parts]
    breadcrumbs = " / ".join(html.escape(part) for part in breadcrumb_parts)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Systems architecture learning edition of {html.escape(document.title, quote=True)}">
  <title>{html.escape(document.title)} · OIEC-STM Systems Architect Academy</title>
  <link rel="stylesheet" href="{styles_url}">
</head>
<body data-page="document" data-source-hash="{digest}">
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
      <section class="document-hero">
        <p class="eyebrow">SYSTEMS ARCHITECT LEARNING EDITION · BUILT {html.escape(build_date)}</p>
        <h1>{html.escape(document.title)}</h1>
        <p>This page preserves the checked-in source while expanding every heading into an argumentative, beginner-readable lesson with explicit evidence, counterarguments, tutorials, glossary support, and conditional conclusions.</p>
        <dl class="hero-metrics">
          <div><dt>MODULES</dt><dd>{len(document.sections):02d}</dd></div>
          <div><dt>ESSAY PARAGRAPHS</dt><dd>{len(document.sections) * 25}</dd></div>
          <div><dt>SOURCE SHA-256</dt><dd>{digest[:12]}</dd></div>
        </dl>
      </section>
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


def render_tree(documents: Iterable[Document]) -> str:
    top_level = [doc for doc in documents if len(doc.relative_path.parts) == 1]
    nested: dict[str, list[Document]] = {}
    for doc in documents:
        if len(doc.relative_path.parts) > 1:
            nested.setdefault(doc.relative_path.parts[0], []).append(doc)
    items = []
    for doc in top_level:
        items.append(render_tree_document(doc))
    for folder, folder_docs in sorted(nested.items()):
        children = "".join(render_tree_document(doc) for doc in folder_docs)
        items.append(
            f'<li class="tree-folder"><button type="button" class="tree-toggle" aria-expanded="true">'
            f'<span class="tree-icon">▾</span>{html.escape(folder)}/</button><ul>{children}</ul></li>'
        )
    return f'<ul class="docs-tree">{"".join(items)}</ul>'


def render_tree_document(document: Document) -> str:
    target = document.relative_path.with_suffix(".html").as_posix()
    category = category_for(document)
    keywords = " ".join(section.title for section in document.sections)
    return (
        f'<li class="tree-document" data-search="{html.escape((document.title + " " + category + " " + keywords).lower(), quote=True)}">'
        f'<a href="{html.escape(target)}"><span class="file-icon">HTML</span><span><strong>{html.escape(document.title)}</strong>'
        f'<small>{html.escape(document.relative_path.as_posix())} · {len(document.sections)} modules · {category}</small></span></a></li>'
    )


def index_template(documents: tuple[Document, ...], concepts: tuple[Concept, ...], build_date: str) -> str:
    heading_count = sum(len(document.sections) for document in documents)
    total_paragraphs = (heading_count + len(concepts)) * 25
    total_svg_figures = len(documents) + len(concepts) + 3
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
    for category in categories:
        members = [document for document in documents if category_for(document) == category]
        category_cards.append(
            f'<article class="category-card" data-category="{html.escape(category.lower(), quote=True)}">'
            f'<span>{len(members):02d}</span><h3>{html.escape(category)}</h3>'
            f'<p>{sum(len(document.sections) for document in members)} learning modules derived from {len(members)} source documents.</p></article>'
        )
    references = "".join(
        f'<li><a href="{html.escape(reference["url"])}" rel="noreferrer">{html.escape(reference["title"])}</a>'
        f'<p>{html.escape(reference["summary"])}</p></li>'
        for reference in REFERENCE_LIBRARY
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Interactive systems architecture learning tree for OIEC-STM-Agent documentation">
  <title>OIEC-STM Systems Architect Academy · docs/index.html</title>
  <link rel="stylesheet" href="assets/styles.css">
</head>
<body data-page="index">
  <div class="scanline-overlay" aria-hidden="true"></div>
  <header class="site-header">
    <a class="brand" href="index.html"><span class="brand-mark">OS</span><span><strong>OIEC-STM ARCHITECT ACADEMY</strong><small>docs/index.html</small></span></a>
    <nav class="header-actions"><button type="button" data-action="focus-mode">FOCUS</button><a href="../README.md">PROJECT README</a></nav>
  </header>
  <main class="index-main">
{governed_loop_hero(len(concepts), build_date).lstrip()}
    <section class="index-metrics" aria-label="Site metrics">
      <article><span>{len(documents):02d}</span><p>Markdown sources</p></article>
      <article><span>{heading_count:03d}</span><p>heading lessons</p></article>
      <article><span>{len(concepts):03d}</span><p>unique concepts</p></article>
      <article><span>{total_paragraphs:,}</span><p>argument paragraphs</p></article>
      <article><span>{total_svg_figures:03d}</span><p>SVG figures</p></article>
    </section>
    <section class="index-overview-panel">
      <div><p class="terminal-label">DOCUMENTATION ARCHITECTURE BUS</p><h2>Every Markdown heading becomes a testable lesson.</h2><p>The original Markdown remains the source of record. Each generated page adds one titled introduction, three untitled body sections, and one untitled conclusion; every section contains an introduction paragraph, three body paragraphs, and a conclusion paragraph.</p><div class="hero-actions"><a class="primary-action" href="#documentation-tree">OPEN DOC TREE</a><button type="button" data-action="random-module">RANDOM MODULE</button></div></div>
      <object class="index-map" type="image/svg+xml" data="figures/index-architecture.svg"><a href="figures/index-architecture.svg">Open the architecture overview SVG</a></object>
    </section>
    <section class="concept-atlas-callout"><div><p class="terminal-label">{len(concepts)} SOURCE-DERIVED CONCEPTS</p><h2>Search the full OIEC-STM-Agent concept atlas.</h2><p>The atlas derives concepts from the governed loop, every semantic command namespace, and every public runtime, record, adapter, persistence, authority, provider, service, and refusal type under <code>ourd/</code>.</p><a class="primary-action" href="concepts/index.html">OPEN CONCEPT ATLAS</a></div><object class="atlas-preview" type="image/svg+xml" data="figures/concept-atlas.svg"><a href="figures/concept-atlas.svg">Open the concept atlas SVG</a></object></section>
    <section class="category-grid">{''.join(category_cards)}</section>
    <section class="tree-shell" id="documentation-tree">
      <div class="tree-heading"><div><p class="terminal-label">/DOCS/ HTML TREE</p><h2>Documentation directory</h2><p>Filter by concept, source file, heading, or architecture category.</p></div><label>SEARCH<input id="docs-search" type="search" placeholder="EGCF, replay, authority..."></label></div>
      {render_tree(documents)}
      <p class="search-status" role="status" aria-live="polite"></p>
    </section>
    <section class="learning-method">
      <div><p class="terminal-label">READING PROTOCOL</p><h2>How to learn from the site</h2></div>
      <ol><li><strong>Orient.</strong> Read the plain-language introduction and glossary.</li><li><strong>Challenge.</strong> Compare the thesis with the source evidence and counterargument.</li><li><strong>Trace.</strong> Use the SVG nodes to follow claim, evidence, boundary, and decision.</li><li><strong>Test.</strong> Turn one documented claim into a falsifiable architecture check.</li></ol>
    </section>
    <section class="index-references"><p class="terminal-label">TEXTBOOK LENSES</p><h2>Reference foundation</h2><ul>{references}</ul></section>
  </main>
  <div class="pixel-crew" aria-hidden="true"></div>
  <script>window.DOCS_MANIFEST = {json.dumps(manifest, ensure_ascii=False)};</script>
  <script src="assets/site.js" defer></script>
</body>
</html>
"""


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


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def build(build_date: str) -> tuple[tuple[Document, ...], tuple[Concept, ...]]:
    documents = discover_documents()
    concepts = discover_concepts()
    if not documents:
        raise SystemExit("No Markdown files found under docs/")
    if not concepts:
        raise SystemExit("No OIEC-STM-Agent concepts discovered")

    figures_root = DOCS_ROOT / "figures"
    for index, document in enumerate(documents):
        previous = documents[index - 1] if index else None
        following = documents[index + 1] if index + 1 < len(documents) else None
        write_text(document.output_path, document_template(document, previous, following, build_date))
        figure_path = figures_root / document.relative_path.with_suffix(".svg")
        write_text(figure_path, document_svg(document))

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
        write_text(concept_figures_root / f"{concept.slug}.svg", concept_svg(concept))

    write_text(concepts_root / "index.html", concept_atlas_template(concepts, build_date))
    write_text(DOCS_ROOT / "index.html", index_template(documents, concepts, build_date))
    write_text(figures_root / "index-architecture.svg", index_svg(documents))
    write_text(figures_root / "governed-loop.svg", governed_loop_svg())
    write_text(figures_root / "concept-atlas.svg", concept_atlas_svg(concepts))

    manifest = {
        "build_date": build_date,
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
            }
            for concept in concepts
        ],
        "governed_loop": {
            "pipeline": ["HRTv1", "OURD", "IURMv1.1.1", "EONv1", "Evidence Gate", "Action", "CFEL"],
            "figure": "figures/governed-loop.svg",
            "thesis": "The agent is an uncertainty-reduction machine whose reasoning remains separate from mutation authority.",
        },
        "references": list(REFERENCE_LIBRARY),
        "glossary": {**GLOSSARY, **CONSTANT_DEFINITIONS},
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
    heading_count = sum(len(document.sections) for document in documents)
    paragraph_count = (heading_count + len(concepts)) * 25
    svg_count = len(documents) + len(concepts) + 3
    html_count = len(documents) + len(concepts) + 2
    print(
        f"Built {html_count} HTML pages, {svg_count} SVG figures, and {paragraph_count} "
        f"essay paragraphs from {heading_count} Markdown headings and {len(concepts)} concepts."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
