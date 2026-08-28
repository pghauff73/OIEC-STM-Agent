# Formal University Writing for OIEC-STM-Agent

This document records the research basis for OIEC-STM-Agent's formal writing profiles. The implementation turns the findings into deterministic genre guidance plus an explicit argument-topology model. It is guidance for drafting and validation, not a substitute for a unit's assessment instructions or marking rubric.

## Research findings

### 1. University essays are thesis-driven arguments

Monash University describes an academic essay as a position on a topic supported by evidence, with an introduction, logically connected evidence-bearing body paragraphs, and a conclusion that shows how the argument answered the question. The University of Melbourne and Oxford similarly emphasise responding directly to the task, using a clear supported structure, and making each body paragraph contribute evidence to the developing argument.

Implementation consequence: every formal profile requires task analysis, a central thesis, a roadmap, evidence-bearing body claims, and a conclusion that answers the task without adding new evidence.

Sources:
- https://www.monash.edu/student-academic-success/excel-at-writing/how-to-write/essay
- https://students.unimelb.edu.au/academic-skills/reading-writing-and-referencing/writing-effectively/using-a-writing-process
- https://students.unimelb.edu.au/academic-skills/reading-writing-and-referencing/essays/six-top-tips-for-writing-a-great-essay
- https://www.ox.ac.uk/students/academic/guidance/skills/essay

### 2. Synthesis is more than summary

Monash's critical-thinking guidance frames argument creation as synthesis: combine evidence, reasoning, one's own conclusions, supporting views and opposing views into a coherent main claim. It explicitly identifies a good academic argument as having a clear claim, logical structure, evidence, reasoning that links evidence to claims, analysis/evaluation of sources, and balanced clear writing.

Implementation consequence: OIEC-STM instructs the writer to organise by themes/claims and relationships among sources, not one paragraph per source. Evidence and reasoning are separate writing dimensions.

Sources:
- https://www.monash.edu/student-academic-success/sharpen-your-thinking/critical-thinking/create-argument
- https://www.monash.edu/student-academic-success/sharpen-your-thinking/critical-thinking/create-argument/bring-together-your-evidence-and-reasoning
- https://www.monash.edu/student-academic-success/sharpen-your-thinking/critical-thinking/analyse-sources-and-arguments/analyse-sources

### 3. Science essays are essays, not automatically laboratory reports

Sheffield Hallam's undergraduate science-writing guide explicitly distinguishes science essays from lab reports, literature reviews and other scientific genres. The University of Sussex recommends that science-based essay paragraphs use sources, explanation, examples and data to support a topic idea, with critical analysis and synthesis of evidence. Science essays may need discipline-specific data/diagram conventions, but the assessment brief remains authoritative.

Implementation consequence: `scientific-essay` retains the thesis-driven essay form unless the assignment explicitly asks for IMRaD/report structure. It asks for scientific claim/evidence/method/limitation analysis rather than mechanically applying a research-paper template.

Sources:
- https://libguides.shu.ac.uk/writingscience
- https://www.sussex.ac.uk/skills-hub/writing-and-assessments
- https://www.ox.ac.uk/students/academic/guidance/skills/essay

### 4. Argument maps expose logical structure

Monash recommends argument maps for complex academic arguments because they make relationships among claims, reasons and evidence visible. Stanford's current Informal Logic entry similarly describes standardising arguments into premises and conclusions and using diagrams to distinguish linked and convergent support. It stresses the importance of identifying implicit premises and evaluating them.

Implementation consequence: `ArgumentTopology` models the essay as a directed graph containing thesis, claims, premises, evidence, warrants, counterclaims, rebuttals, qualifiers, limitations and implications. Positive support must be acyclic to block circular justification.

Sources:
- https://www.monash.edu/student-academic-success/sharpen-your-thinking/critical-thinking/create-argument/structure-your-argument
- https://plato.stanford.edu/entries/logic-informal/
- https://plato.stanford.edu/entries/argument/

### 5. Counterarguments must be answered, not merely mentioned

University argument guidance asks writers to consider claims and counterclaims, test their main claim against opposing perspectives, and identify missing or weakly evidenced claims. Informal logic treats rebutting and undercutting defeaters as materially different ways an inference can fail.

Implementation consequence: serious counterclaims in the topology must target a claim, premise or inference, and the argumentative profile requires an explicit response: rebuttal, undermining premise evidence, or undercutting the warrant/inference.

Sources:
- https://www.monash.edu/student-academic-success/sharpen-your-thinking/critical-thinking/create-argument/refine-your-argument
- https://www.monash.edu/student-academic-success/sharpen-your-thinking/critical-thinking/evaluate-arguments-of-others
- https://plato.stanford.edu/entries/reasoning-defeasible/

### 6. Scientific writing should preserve the claim-evidence-method relationship

Nature Genetics recommends planning scientific papers by laying out claims together with supporting evidence and methods so the semantic structure of the argument remains visible. Nature Methods describes scientific writing as selecting data and interpretation to deliver a message to an audience, while enabling the reader to understand observations, reproduce analysis where needed, and assess how interpretation was reached.

Implementation consequence: the scientific-essay profile requires every major scientific claim to track evidence, method/source, reasoning, limitations, competing explanation and claim strength.

Sources:
- https://www.nature.com/articles/ng.3271
- https://www.nature.com/articles/nmeth.4532

### 7. Scientific certainty must be calibrated

Evidence communication guidance warns against unwarranted certainty and over-neat narratives. Reproducibility scholarship stresses that scientific credibility rests on transparent evidence, methods, data and interpretation, and that reproducibility, replicability and robustness provide different information about a finding.

Implementation consequence: the scientific profile separates observation from interpretation and requires calibrated language. It explicitly distinguishes correlation, causation, mechanism, necessity and sufficiency, and asks the writer to discuss relevant uncertainty, contradictory evidence, null results and methodological limitations.

Sources:
- https://www.nature.com/articles/d41586-020-03189-1
- https://www.nature.com/articles/s41562-016-0021
- https://www.nature.com/articles/s41467-024-54614-2

## OIEC logic topology

The argumentative profile formalises an essay as:

```text
Evidence / Premises / Warrants
            |
            v
     Supporting Claims ----------- Counterclaim
            |                         |
            v                         v
          Thesis <-------------- Rebuttal/Response
            |
       Qualifiers / Limits
            |
            v
       Implications
```

Edges are typed as:

- `supports`
- `warrants`
- `entails`
- `depends_on`
- `attacks`
- `rebuts`
- `qualifies`
- `limits`

The positive support graph is required to be acyclic. This does not mean an essay cannot discuss dialectical back-and-forth; attack and rebuttal edges may cross the support hierarchy. The constraint means a claim cannot ultimately justify itself.

Linked premises may share an `inference_id`; ungrouped support is treated as convergent/independent unless otherwise specified. Material inference modes may be labelled deductive, inductive, abductive, causal, analogical, authority/expert, or defeasible.

## Scientific essay profile

The scientific profile adds these dimensions to ordinary university writing:

- scientific claim calibration;
- methodological quality;
- causal inference;
- uncertainty;
- reproducibility;
- limitations.

A major scientific claim should be mentally represented as:

```text
Claim
  <- Evidence
  <- Method / provenance
  <- Reasoning / warrant
  <- Competing explanation check
  <- Limitations
  <- Confidence qualifier
```

## Argumentative essay profile

The argumentative profile adds:

- argument topology;
- implicit warrants;
- counterarguments;
- rebuttals;
- inference validity;
- defeaters.

The writer should distinguish:

- deductive inference, where validity and premise acceptability are tested;
- inductive inference, where evidential strength and representativeness matter;
- abductive inference, where alternative explanations are compared;
- causal inference, where correlation alone is insufficient;
- analogical inference, where relevant similarities and disanalogies must be examined;
- authority/expert inference, where expertise, domain, independence and evidence base must be checked.

## Academic integrity and local rules

The agent must not invent citations, quotations, statistics, page numbers, DOIs, experimental results or sources. Assignment instructions, faculty conventions and marking rubrics override generic profile defaults. Where GenAI use must be disclosed, the student remains responsible for following the institution's current disclosure and academic-integrity requirements.
