"""Canonical novice-learning contracts for the generated documentation site."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Iterable, Protocol


ROOT = Path(__file__).resolve().parents[1]

CONTENT_KINDS = (
    "tutorial",
    "task-guide",
    "case-study",
    "expert-document",
    "architecture-decision",
    "generated-reference",
    "concept",
    "tool",
    "explorer",
)

DOCUMENTATION_STATUSES = (
    "Implemented",
    "Tested",
    "Experimental",
    "Theoretical",
    "Planned",
)

TUTORIAL_HEADINGS = (
    "What you will learn",
    "Everyday analogy",
    "New vocabulary",
    "Diagram",
    "Command or interaction",
    "Expected output",
    "What just happened?",
    "Try changing this",
    "Common mistake",
    "Next lesson",
)

ACRONYM_PATTERN = re.compile(r"\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*\b")
STRUCTURED_TOKENS = {
    *(f"T{index:02d}" for index in range(14)),
    *(f"C{index}" for index in range(6)),
    *(f"L{index}" for index in range(3)),
}


class ConceptLike(Protocol):
    slug: str
    title: str
    category: str
    definition: str
    thesis: str
    inputs: str
    outcome: str
    sources: tuple[str, ...]
    related: tuple[str, ...]


@dataclass(frozen=True)
class LearningPath:
    path_id: str
    title: str
    plain_language_goal: str
    audience: str
    ordered_item_ids: tuple[str, ...]
    estimated_minutes: int
    prerequisite_ids: tuple[str, ...]
    completion_evidence: str


@dataclass(frozen=True)
class TutorialLesson:
    lesson_id: str
    ordinal: int
    title: str
    source_path: str
    reader_outcome: str
    new_vocabulary: tuple[str, ...]
    prerequisite_ids: tuple[str, ...]
    command_ids: tuple[str, ...]
    fixture_ids: tuple[str, ...]
    next_lesson_id: str


@dataclass(frozen=True)
class TaskRoute:
    route_id: str
    title: str
    source_path: str
    plain_language_goal: str
    ordered_item_ids: tuple[str, ...]
    search_terms: tuple[str, ...]


@dataclass(frozen=True)
class CaseStudy:
    case_id: str
    title: str
    domain: str
    source_path: str
    problem: str
    concept_ids: tuple[str, ...]
    fixture_id: str


@dataclass(frozen=True)
class TimelineEntry:
    entry_id: str
    title: str
    problem: str
    response: str
    source_paths: tuple[str, ...]


@dataclass(frozen=True)
class AcronymRecord:
    token: str
    expansion: str
    short_meaning: str
    everyday_analogy: str
    formal_meaning: str
    related_concepts: tuple[str, ...]
    first_lesson_id: str
    source_paths: tuple[str, ...]


@dataclass(frozen=True)
class ConceptTeachingRecord:
    concept_id: str
    full_name: str
    short_meaning: str
    why_it_exists: str
    everyday_analogy: str
    oiec_example: str
    inputs: str
    outputs: str
    misconception: str
    diagram: str
    formal_novice: str
    formal_intermediate: str
    formal_expert: str
    related_concepts: tuple[str, ...]
    prerequisites: tuple[str, ...]
    cli_examples: tuple[str, ...]
    failure_example: str
    source_links: tuple[str, ...]
    documentation_status: str
    status_evidence: tuple[str, ...]
    authorship: str


LEARNING_PATHS = (
    LearningPath(
        "start-here",
        "Start Here",
        "Understand the problem OIEC solves and complete one safe read-only task.",
        "New readers",
        ("T00", "T01", "T02", "T03"),
        15,
        (),
        "The reader can explain the governed loop and run a read-only inspection command.",
    ),
    LearningPath(
        "understand",
        "Understand",
        "Turn a broad request into an inspectable problem model.",
        "Readers learning problem representation",
        ("T03", "T04"),
        20,
        ("start-here",),
        "The reader can distinguish evidence from a proposal and draw an OURD map.",
    ),
    LearningPath(
        "experiment",
        "Experiment",
        "Vary one useful dimension while preserving declared invariants.",
        "Readers designing discriminating tests",
        ("T05", "T11"),
        25,
        ("understand",),
        "The reader can define a baseline, one variation, and a comparison result.",
    ),
    LearningPath(
        "act-safely",
        "Act Safely",
        "Compile an exact bounded proposal and inspect its authority and evidence gates.",
        "Readers preparing governed actions",
        ("T06", "T07"),
        25,
        ("understand",),
        "The reader can explain scope, risk, approval, evidence, and rollback.",
    ),
    LearningPath(
        "learn-and-improve",
        "Learn and Improve",
        "Record failures, retrieve known work, adapt one dimension, and close the loop.",
        "Readers studying reusable improvement",
        ("T08", "T09", "T10", "T11", "T12", "T13"),
        50,
        ("experiment", "act-safely"),
        "The reader can assemble and explain the complete governed improvement loop.",
    ),
)


TUTORIALS = (
    TutorialLesson("T00", 0, "Welcome", "docs/tutorial/00_WELCOME.md", "Explain what OIEC is for without relying on acronyms.", ("OIEC", "STM"), (), (), ("lamp-loop",), "T01"),
    TutorialLesson("T01", 1, "Install", "docs/tutorial/01_INSTALL.md", "Install the package and identify the five command names.", ("CLI", "GUI"), ("T00",), ("install-editable", "show-help"), (), "T02"),
    TutorialLesson("T02", 2, "First Read-Only Task", "docs/tutorial/02_FIRST_READ_ONLY_TASK.md", "Inspect a repository without granting write authority.", ("workspace", "read-only"), ("T01",), ("agent-read-repo", "agent-one-shot"), ("read-only-run",), "T03"),
    TutorialLesson("T03", 3, "Evidence", "docs/tutorial/03_EVIDENCE.md", "Separate source facts, model proposals, and verified observations.", ("evidence", "proposal", "verification"), ("T02",), (), ("evidence-layers",), "T04"),
    TutorialLesson("T04", 4, "OURD", "docs/tutorial/04_OURD.md", "Map objects, boundaries, relations, and unresolved questions.", ("OURD", "relation", "boundary"), ("T03",), (), ("lamp-ourd",), "T05"),
    TutorialLesson("T05", 5, "IURM", "docs/tutorial/05_IURM.md", "Design a one-variable experiment with a stable baseline.", ("IURM", "invariant", "baseline"), ("T04",), (), ("lamp-iurm",), "T06"),
    TutorialLesson("T06", 6, "EGCF", "docs/tutorial/06_EGCF.md", "Read and assemble an inspectable semantic command.", ("EGCF", "scope", "risk"), ("T05",), ("egcf-capability-list", "egcf-dry-run"), ("egcf-command",), "T07"),
    TutorialLesson("T07", 7, "EON", "docs/tutorial/07_EON.md", "Inspect an exact proposed mutation before it can execute.", ("EON", "authority", "rollback"), ("T06",), ("agent-write-docs",), ("eon-proposal", "write-without-path", "write-with-yolo"), "T08"),
    TutorialLesson("T08", 8, "CFEL", "docs/tutorial/08_CFEL.md", "Record a failed expectation so blind retries stop.", ("CFEL", "collision", "failure memory"), ("T07",), (), ("lamp-cfel",), "T09"),
    TutorialLesson("T09", 9, "SAA", "docs/tutorial/09_SAA.md", "Search qualified knowledge before inventing a replacement.", ("SAA", "qualification", "retrieval"), ("T08",), (), ("saa-retrieval",), "T10"),
    TutorialLesson("T10", 10, "Adaptation", "docs/tutorial/10_ADAPTATION.md", "Adapt one declared dimension without hiding structural changes.", ("adaptation", "lineage", "dimension"), ("T09",), (), ("one-dimension-adaptation", "adapt-two-dimensions"), "T11"),
    TutorialLesson("T11", 11, "A/B Evidence", "docs/tutorial/11_AB_EVIDENCE.md", "Compare a candidate with a frozen baseline using named evidence.", ("candidate", "baseline", "regression"), ("T10",), (), ("ab-evidence",), "T12"),
    TutorialLesson("T12", 12, "Closed Loop", "docs/tutorial/12_CLOSED_LOOP.md", "Promote and re-retrieve only evidence-qualified knowledge.", ("promotion", "re-retrieval", "closed loop"), ("T11",), (), ("closed-loop", "promote-without-evidence"), "T13"),
    TutorialLesson("T13", 13, "Build a Workflow", "docs/tutorial/13_BUILD_A_WORKFLOW.md", "Combine understanding, experimentation, action, verification, and learning.", ("workflow", "DAG", "evidence gate"), ("T12",), ("egcf-workflow" ,), ("complete-workflow",), ""),
)


TASK_ROUTES = (
    TaskRoute("understand-repository", "Understand a repository", "docs/tasks/UNDERSTAND_A_REPOSITORY.md", "Inspect structure, owners, and evidence without changing files.", ("T02", "T03", "T04"), ("explain repository", "map codebase", "what owns this")),
    TaskRoute("debug-bug", "Debug a bug", "docs/tasks/DEBUG_A_BUG.md", "Turn a symptom into competing hypotheses and discriminating tests.", ("T03", "T04", "T05", "T08"), ("debug", "bug", "find cause", "regression")),
    TaskRoute("modify-files", "Safely modify files", "docs/tasks/SAFELY_MODIFY_FILES.md", "Grant a narrow write boundary and verify an exact candidate.", ("T06", "T07"), ("write files", "edit docs", "safe mutation")),
    TaskRoute("write-report", "Write a report", "docs/tasks/WRITE_A_REPORT.md", "Separate supported claims from proposals and limitations.", ("T03", "T07", "T11"), ("report", "evidence-backed writing", "unsupported claim")),
    TaskRoute("run-experiment", "Run an experiment", "docs/tasks/RUN_AN_EXPERIMENT.md", "Hold a baseline, vary one dimension, and record observations.", ("T04", "T05", "T11"), ("experiment", "one variable", "baseline")),
    TaskRoute("compare-algorithms", "Compare algorithms", "docs/tasks/COMPARE_ALGORITHMS.md", "Compare qualified candidates under the same evidence contract.", ("T09", "T10", "T11"), ("compare algorithms", "candidate versus baseline")),
    TaskRoute("use-ollama", "Use OIEC with Ollama", "docs/tasks/USE_OLLAMA.md", "Connect a local OpenAI-compatible provider without changing governance.", ("T01", "T02"), ("ollama", "local model", "provider setup")),
    TaskRoute("understand-failure", "Understand a failure", "docs/tasks/UNDERSTAND_A_FAILURE.md", "Decode a refusal or failed expectation and identify the next safe step.", ("T03", "T08"), ("failure", "refusal", "keeps repeating", "repeating failed action", "blind retry", "CFEL", "Failure Algebra")),
    TaskRoute("build-command", "Build my own command", "docs/tasks/BUILD_A_COMMAND.md", "Assemble an EGCF command from semantic parts rather than memorizing flags.", ("T06",), ("build command", "egcf flags", "dry run")),
)


CASE_STUDIES = (
    CaseStudy("everyday-lamp", "Why will the lamp not turn on?", "Everyday", "docs/case-studies/EVERYDAY_LAMP.md", "A lamp remains dark after a bulb replacement.", ("ourd", "iurm", "cfel"), "lamp-loop"),
    CaseStudy("cooking-bread", "Why did the bread fail?", "Cooking", "docs/case-studies/COOKING_BREAD.md", "A loaf is dense despite following the recipe.", ("ourd", "iurm", "evidence-gate"), "bread-experiment"),
    CaseStudy("engineering-controller", "Controller oscillation", "Engineering", "docs/case-studies/ENGINEERING_CONTROLLER.md", "A temperature controller oscillates around its setpoint.", ("ourd", "iurm", "eon"), "controller-oscillation"),
    CaseStudy("automotive-brakes", "Unexpected brake vibration", "Automotive", "docs/case-studies/AUTOMOTIVE_BRAKES.md", "A vehicle vibrates during braking under limited conditions.", ("ourd", "iurm", "evidence-gate"), "brake-vibration"),
    CaseStudy("research-hypotheses", "Competing scientific hypotheses", "Research", "docs/case-studies/RESEARCH_HYPOTHESES.md", "Several explanations fit the first observation.", ("iurm", "ieps", "cfel"), "research-hypotheses"),
    CaseStudy("software-parser", "Parser regression", "Software", "docs/case-studies/SOFTWARE_PARSER.md", "A parser changes precedence after a recent edit.", ("egcf", "eon", "cfel"), "parser-regression"),
    CaseStudy("writing-claim", "Unsupported report claim", "Writing", "docs/case-studies/WRITING_CLAIM.md", "A report contains a confident claim without adequate evidence.", ("ieps", "evidence-gate", "cfel"), "unsupported-claim"),
    CaseStudy("business-process", "Choosing between two processes", "Business", "docs/case-studies/BUSINESS_PROCESS.md", "Two workflows promise improvement but use different measures.", ("iurm", "ieps", "governed-action"), "business-comparison"),
)


INVENTION_TIMELINE = (
    TimelineEntry("interpretation", "Make intent inspectable", "Broad human requests hide assumptions, scope, and ambiguity.", "HRT records a reviewable interpretation before deeper modeling.", ("README.md", "tools/docs_concept_catalog.py")),
    TimelineEntry("problem-map", "Model the territory", "A plausible first solution can hide missing objects and dependencies.", "OURD decomposes the problem into orthogonal, uniquely identified components while preserving their relations, dependencies, boundaries, exclusions, and unknowns.", ("README.md", "ourd/egcf/catalog.py")),
    TimelineEntry("controlled-learning", "Learn through controlled variation", "Changing several dimensions at once produces weak causal evidence.", "IURM selects baselines, invariants, dimensions, and responses.", ("README.md", "ourd_gui/views/iurm.py")),
    TimelineEntry("exact-action", "Separate reasoning from mutation", "A good idea is not yet an authorized, source-bound action.", "EON binds exact targets, state, authority, evidence, tests, and rollback.", ("README.md", "ourd/egcf/adapters/eon.py")),
    TimelineEntry("failure-memory", "Stop blind retries", "A failed approach can recur with different wording but no new evidence.", "CFEL records expectation, observation, collision, and next learning constraints.", ("README.md", "ourd/cfel.py")),
    TimelineEntry("search-first", "Retrieve before reinventing", "Qualified solutions and known failures are wasted when every task starts from generation.", "SAA represents, qualifies, searches, adapts, and re-retrieves reusable structures.", ("docs/SAA_1_CANONICAL_IR.md", "docs/SAA_11_3_11_4_SAA_12_CLOSED_IMPROVEMENT.md")),
)


ACRONYMS = (
    AcronymRecord("OIEC", "OIEC (canonical project name; no expanded form is declared in current source)", "The governed architecture that separates understanding, evidence, authority, action, and learning.", "A careful workshop process with separate planning, inspection, permission, and quality-control stations.", "The repository-wide architecture name. Documentation must not invent an expansion that the source does not declare.", ("hrt", "ourd", "iurm", "eon", "cfel"), "T00", ("README.md",)),
    AcronymRecord("STM", "State Transition Machine", "The bounded state-transition part of OIEC-STM-Agent.", "A turnstile that admits only a checked transition rather than any movement.", "STM is the State Transition Machine: the bounded-transition layer that governs admissible state changes; it is not ordinary conversational short-term memory.", ("eon", "evidence-gate"), "T00", ("README.md", "OIEC_STMV1_2_IMPLEMENTATION_PLAN.md")),
    AcronymRecord("SR", "Super Reasoning", "A bounded additive layer for generating and comparing reasoning candidates.", "Several engineers propose explanations while a separate process checks evidence and authority.", "OIEC-SR proposes hypotheses and evidence requests but cannot enlarge external authority.", ("iurm", "ieps"), "T03", ("README.md", "OIEC_SR_V1_IMPLEMENTATION_PLAN.md")),
    AcronymRecord("OURD", "Orthogonal Unique Relational Decomposition", "Decomposes a problem into orthogonal, uniquely identified relational components and the relations between them.", "List every part of a lamp circuit before blaming the bulb.", "A canonical decomposition into orthogonal, uniquely identified relational components, together with their relations, dependencies, boundaries, exclusions, and unresolved relations.", ("ourd",), "T04", ("README.md", "tools/docs_concept_catalog.py")),
    AcronymRecord("IURM", "Invariant-Uncertainty-Response Modeling", "Chooses useful controlled variations that reduce uncertainty.", "Change one recipe variable while keeping the rest stable.", "A bounded experiment model containing dimensions, invariants, baselines, variations, and responses.", ("iurm",), "T05", ("README.md", "tools/docs_concept_catalog.py")),
    AcronymRecord("EON", "Exact Governed Action Boundary", "Turns a proposal into an exact action identity with authority and evidence requirements.", "A repair order naming the exact machine, part, permission, checks, and rollback.", "A content-addressed action boundary bound to source state, targets, authority, risk, evidence, and rollback.", ("eon",), "T07", ("README.md", "tools/docs_concept_catalog.py")),
    AcronymRecord("CFEL", "Collision, Failure, Evidence, and Learning Feedback", "Records what failed or contradicted expectations so the system does not retry blindly.", "A mechanic writes down that replacing the bulb did not solve the fault.", "A source-bound feedback record connecting expectations, observations, collisions, failures, and reusable learning.", ("cfel",), "T08", ("README.md", "tools/docs_concept_catalog.py")),
    AcronymRecord("EGCF", "Evidence-Governed Command Fabric", "Compiles semantic commands into inspectable governed plans.", "A work order that states the job, location, risk, proof, approval, and rollback.", "The typed command fabric that compiles namespace and verb intent into governed plan nodes and evidence requirements.", ("egcf",), "T06", ("EGCFV1_IMPLEMENTATION_PLAN.md", "tools/docs_concept_catalog.py")),
    AcronymRecord("HRT", "Human-Readable Task Interpretation", "Makes the request, assumptions, scope, and ambiguity explicit.", "Repeat a repair request back to the owner before touching the machine.", "The inspectable interpretation record that precedes OURD modeling.", ("hrt",), "T04", ("tools/docs_concept_catalog.py",)),
    AcronymRecord("IEPS", "Invariant and Evidence Production System", "Produces tests, counterexamples, coverage, and evidence gates.", "A test bench designed to reveal whether a repair actually works.", "The evidence-production service for qualification, falsification, and bounded gate decisions.", ("ieps", "evidence-gate"), "T03", ("EGCFV1_IMPLEMENTATION_PLAN.md", "ourd/egcf/ieps.py")),
    AcronymRecord("BD", "Boundary Determination", "Determines the supported boundary of a claim or model.", "Mark the operating range in which a machine was actually tested.", "A bounded reasoning stage that derives the domain on which later claims may be evaluated.", ("iurm", "ieps"), "T05", ("OIEC_SR_V1_IMPLEMENTATION_PLAN.md",)),
    AcronymRecord("DL", "Dimension Limiting", "Restricts active dimensions to a tractable and justified set.", "Test temperature before changing temperature, flour, timing, and humidity together.", "A bounded reasoning stage that limits dimensions before experimentation or action.", ("iurm",), "T05", ("OIEC_SR_V1_IMPLEMENTATION_PLAN.md",)),
    AcronymRecord("SAA", "Searchable Algebra of Algorithms", "Represents, qualifies, searches, and adapts reusable algorithmic structures.", "Search a repair manual for a proven procedure before inventing one.", "A staged algebra and store for canonical, semantically resolved, evidence-qualified algorithm and reasoning structures.", ("cfel",), "T09", ("docs/SAA_1_CANONICAL_IR.md", "docs/SAA_6_1_TO_6_4_CANONICAL_STORE.md")),
    AcronymRecord("CLI", "Command-Line Interface", "A text interface for running a program with commands and options.", "Writing a precise work order instead of using a control panel.", "The package exposes agent, EGCF, and GUI launch commands through project scripts.", ("egcf",), "T01", ("pyproject.toml",)),
    AcronymRecord("GUI", "Graphical User Interface", "A visual interface using windows, panels, buttons, and diagrams.", "A workshop control panel rather than a typed work order.", "The Tkinter engineering workbench exposed by the OIEC GUI entry points.", ("governed-action",), "T01", ("pyproject.toml", "ourd_gui/app.py")),
    AcronymRecord("DAG", "Directed Acyclic Graph", "A one-way dependency graph with no loops.", "A set of recipe steps where no later step can become its own prerequisite.", "Used for ordered plans, prerequisites, and workflow dependencies that must remain cycle-free.", ("egcf",), "T13", ("ourd/egcf/models.py",)),
    AcronymRecord("PEP", "Python Enhancement Proposal", "A design document used to specify Python changes and conventions.", "A formally reviewed proposal for changing workshop standards.", "Packaging documentation refers to PEP 517 build-system behavior.", (), "T01", ("pyproject.toml",)),
    AcronymRecord("PEP 517", "Python Enhancement Proposal 517", "The Python standard that defines a build-system interface for source trees and frontend tools.", "A standard handoff form between a workshop design and any approved builder.", "The repository declares a PEP 517-compatible custom build backend in pyproject.toml.", (), "T01", ("pyproject.toml", "tools/build_backend.py")),
    AcronymRecord("EGL", "EGL graphics context interface", "A platform interface used to create graphics contexts, including headless contexts.", "The adapter that connects a renderer to a display or headless surface.", "The visual workbench may use a ModernGL EGL backend for headless rendering.", (), "T01", ("docs/OPENGL_RENDERER.md",)),
    AcronymRecord("API", "Application Programming Interface", "A defined way for software components to communicate.", "A labeled socket whose allowed shape and signals are documented.", "The repository uses local Python APIs and OpenAI-compatible provider APIs behind governed boundaries.", (), "T01", ("README.md",)),
    AcronymRecord("ABI", "Application Binary Interface", "A binary-level compatibility contract between compiled components.", "Machine parts that fit because dimensions and connection rules match.", "ABI appears in technical compatibility discussions and must not be confused with a source-level API.", (), "T01", ("DOCS_NOVICE_FIRST_REDESIGN_IMPLEMENTATION_PLAN.md",)),
)


CORE_ANALOGIES = {
    "hrt": "A mechanic repeats your request and lists uncertainties before opening the toolbox.",
    "ourd": "A lamp diagnosis maps the bulb, fitting, switch, circuit, breaker, and supply before choosing a cause.",
    "iurm": "A baker changes one variable while keeping the rest of the recipe stable.",
    "ieps": "A test bench tries to expose whether a repair claim is false.",
    "eon": "A repair order names the exact machine, part, permitted work, checks, and rollback.",
    "evidence-gate": "A driving test must pass before a licence is issued.",
    "governed-action": "A technician performs only the work order that was approved.",
    "cfel": "A failure log prevents repeating the same unsuccessful repair without new evidence.",
    "egcf": "A dispatcher turns a broad request into an inspectable job card.",
}

CORE_EXAMPLES = {
    "hrt": "The request 'fix the parser' becomes an explicit objective, repository boundary, assumptions, and open questions.",
    "ourd": "The parser, grammar, tests, token stream, precedence rules, and callers become named related objects.",
    "iurm": "One precedence rule changes while the baseline corpus and all other parser settings remain fixed.",
    "ieps": "Regression tests, counterexamples, and source hashes are gathered before a success claim is accepted.",
    "eon": "A candidate patch is bound to exact files, hashes, authority, tests, risk, approval, and rollback.",
    "evidence-gate": "The action stays blocked until the required tests and approvals are present for the exact candidate.",
    "governed-action": "The approved candidate is applied without broadening paths or commands.",
    "cfel": "A failed parser hypothesis is recorded with expected and observed behavior before another attempt.",
    "egcf": "The objective is compiled into namespace, verb, scope, evidence, risk, approval, and rollback fields.",
}

CORE_MISCONCEPTIONS = {
    "hrt": "HRT is not proof that the interpretation is correct; it makes the interpretation reviewable.",
    "ourd": "OURD is not an instruction to implement the first relation the model notices.",
    "iurm": "IURM is not permission to change several coupled variables and call the result an experiment.",
    "ieps": "Evidence is not the model stating a conclusion confidently.",
    "eon": "EON is not authority by itself; it binds a proposal to authority that already exists.",
    "evidence-gate": "A simulation pass is not proof that real execution succeeded.",
    "governed-action": "Tool availability is not authorization to use the tool.",
    "cfel": "A failure record is not a reason to retry the same action under the same conditions.",
    "egcf": "A semantic command is not an alias for arbitrary shell execution.",
}

CORE_PREREQUISITES = {
    "hrt": (),
    "ourd": ("hrt",),
    "iurm": ("ourd",),
    "ieps": ("iurm",),
    "eon": ("ieps",),
    "evidence-gate": ("ieps",),
    "governed-action": ("eon", "evidence-gate"),
    "cfel": ("governed-action",),
    "egcf": ("hrt",),
}


def teaching_record_for(concept: ConceptLike) -> ConceptTeachingRecord:
    authored = concept.slug in CORE_ANALOGIES
    prerequisites = CORE_PREREQUISITES.get(
        concept.slug,
        ("evidence-gate",) if concept.slug != "evidence-gate" else ("ieps",),
    )
    direct_cli = {
        "egcf": ("egcf-capability-list", "egcf-dry-run"),
        "eon": ("agent-write-docs",),
        "ourd": ("agent-one-shot",),
    }.get(concept.slug, ())
    status = "Implemented" if any(path.startswith(("ourd/", "ourd_gui/")) for path in concept.sources) else "Theoretical"
    return ConceptTeachingRecord(
        concept_id=concept.slug,
        full_name=concept.title,
        short_meaning=concept.definition,
        why_it_exists=concept.thesis,
        everyday_analogy=CORE_ANALOGIES.get(
            concept.slug,
            "A labeled station in a careful workshop: it owns one responsibility and hands a checkable result to the next station.",
        ),
        oiec_example=CORE_EXAMPLES.get(
            concept.slug,
            f"OIEC uses {concept.title} for its declared responsibility while preserving source and evidence links.",
        ),
        inputs=concept.inputs,
        outputs=concept.outcome,
        misconception=CORE_MISCONCEPTIONS.get(
            concept.slug,
            f"{concept.title} does not grant new authority or certify success merely because a record exists.",
        ),
        diagram=f"figures/concepts/{concept.slug}.svg",
        formal_novice=f"In plain terms, {concept.definition}",
        formal_intermediate=f"Inputs are constrained by the concept controls described in the technical record, and outputs remain reviewable rather than self-authorizing.",
        formal_expert=f"The expert contract is the source-bound 25-paragraph concept essay, typed implementation references, invariants, and manifest relations generated for {concept.slug}.",
        related_concepts=concept.related,
        prerequisites=prerequisites,
        cli_examples=direct_cli,
        failure_example=f"If {concept.title} receives stale, incomplete, contradictory, or unauthorized inputs, the safe result is an explicit unresolved or refused outcome rather than silent continuation.",
        source_links=concept.sources,
        documentation_status=status,
        status_evidence=concept.sources,
        authorship="authored" if authored else "source-derived",
    )


def validate_prerequisite_graph(records: Iterable[ConceptTeachingRecord]) -> None:
    by_id = {record.concept_id: record for record in records}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(concept_id: str) -> None:
        if concept_id in visited:
            return
        if concept_id in visiting:
            raise ValueError(f"concept prerequisite cycle at {concept_id}")
        visiting.add(concept_id)
        for prerequisite in by_id[concept_id].prerequisites:
            if prerequisite not in by_id:
                raise ValueError(
                    f"unknown prerequisite {prerequisite!r} for {concept_id!r}"
                )
            visit(prerequisite)
        visiting.remove(concept_id)
        visited.add(concept_id)

    for concept_id in by_id:
        visit(concept_id)


def validate_catalog_sources() -> None:
    records = [*TUTORIALS, *TASK_ROUTES, *CASE_STUDIES]
    missing = [record.source_path for record in records if not (ROOT / record.source_path).is_file()]
    if missing:
        raise ValueError(f"missing learning sources: {', '.join(missing)}")
    acronym_missing = [
        source
        for record in ACRONYMS
        for source in record.source_paths
        if not (ROOT / source).is_file()
    ]
    if acronym_missing:
        raise ValueError(f"missing acronym sources: {', '.join(sorted(set(acronym_missing)))}")
    validate_authored_acronyms()


def discovered_authored_acronyms() -> tuple[str, ...]:
    tokens: set[str] = set()
    for directory in ("tutorial", "tasks", "case-studies"):
        for path in sorted((ROOT / "docs" / directory).glob("*.md")):
            for token in ACRONYM_PATTERN.findall(path.read_text(encoding="utf-8")):
                parts = token.strip("-").split("-")
                tokens.update(part for part in parts if len(part) > 1)
    return tuple(sorted(tokens))


def validate_authored_acronyms() -> None:
    defined = {record.token for record in ACRONYMS}
    unresolved = [
        token
        for token in discovered_authored_acronyms()
        if token not in defined and token not in STRUCTURED_TOKENS
    ]
    if unresolved:
        raise ValueError(
            "undefined authored acronym-like tokens: " + ", ".join(unresolved)
        )


def records_for_manifest(records: Iterable[object]) -> list[dict[str, object]]:
    return [asdict(record) for record in records]
