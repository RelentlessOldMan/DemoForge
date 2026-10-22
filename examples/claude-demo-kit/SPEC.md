# ClaudeDemoKit

## 1. Purpose

ClaudeDemoKit is a self-contained, reproducible engineering demonstration project designed to show engineers practical examples of what Claude can do as part of real engineering workflows.

The target audience works in a regulatory/engineering environment and commonly deals with:

- MATLAB
- Algorithms and numerical processing
- Technical specifications
- PDF documents
- Excel workbooks
- CSV datasets
- Test results
- Log files
- Requirements
- Verification and validation

The demonstrations should emphasize **Claude performing engineering work**, not simply answering questions or summarizing documents.

The project should demonstrate workflows such as:

- Implementing algorithms
- Running code
- Testing implementations
- Optimizing algorithms
- Porting algorithms between languages
- Investigating failures
- Analyzing structured data
- Manipulating Excel workbooks
- Understanding technical specifications
- Generating verification tests
- Building requirements traceability
- Performing autonomous multi-artifact investigations

A core design principle is:

> **Demo engineering jobs, not AI features.**

For example, do not create a demo whose point is merely "Claude can read Excel."

Instead:

> "These validation results look wrong. Determine why."

Excel happens to be one of the engineering artifacts Claude must understand to solve the problem.

---

# 2. Primary Goal

The repository itself should contain everything necessary to:

1. Define each demonstration.
2. Store its prompts.
3. Store or generate its input artifacts.
4. Execute the demonstration using Claude.
5. Capture what Claude actually did.
6. Preserve Claude's generated output artifacts.
7. Reproduce an approved demonstration run.
8. Generate presentation slides describing the demos.
9. Generate narration/commentary.
10. Generate a polished demonstration video.
11. Rebuild the presentation and video automatically when demos are added, removed, reordered, or modified.

The repository should therefore function as both:

- an engineering demonstration suite, and
- the source code/content for the presentation demonstrating that suite.

---

# 3. Desired Experience

An engineer should be able to clone the repository and understand the project through a simple structure.

Ideally, adding a new demo should require creating something resembling:

```text
demos/
    04_log_investigation/
        demo.yaml
        prompt.md
        input/
        expected/
```

The framework should discover the demo automatically.

The developer should not need to manually modify the presentation, video editing project, table of contents, or narration sequence simply because a demo was added or removed.

The system should derive those from the demo definitions.

---

# 4. Demo Philosophy

Every demo should satisfy most of the following principles.

## 4.1 Give Claude a job

Prompts should resemble realistic engineering requests.

Prefer:

> Test 1847 failed. Determine what happened and provide evidence supporting your conclusion.

Avoid:

> Demonstrate your ability to analyze log files.

## 4.2 Claude should manipulate real artifacts

Whenever practical, demos should involve actual files such as:

```text
.m
.py
.xlsx
.csv
.pdf
.log
.md
.json
```

## 4.3 Execution is better than explanation

Prefer demos where Claude:

```text
understands
    ↓
creates/modifies something
    ↓
executes it
    ↓
observes results
    ↓
iterates
    ↓
verifies the result
```

rather than merely producing an explanation.

## 4.4 Results should be measurable

Where appropriate, demonstrations should produce objective results such as:

- test pass/fail counts
- execution time
- speedup
- numerical error
- coverage
- requirement coverage
- anomaly counts
- before/after comparisons

## 4.5 Problems should be realistic

Input artifacts should resemble things engineers might actually encounter.

Avoid toy examples when a moderately realistic example would remain understandable within the demo.

---

# 5. Initial Demonstration Suite

The initial version should contain ten demonstrations.

The exact fictional engineering domain can be chosen during implementation, but ideally many demos should share artifacts from one coherent fictional engineering project.

This allows the audience to gradually become familiar with the system being demonstrated.

---

# Demo 1 — MATLAB Algorithm Implementation

## Scenario

Claude receives an engineering description of an algorithm including requirements, equations, constants, constraints, and expected behavior.

A starter MATLAB project may be supplied.

## Task

Ask Claude to implement the algorithm.

Claude should:

1. Read and understand the algorithm definition.
2. Identify relevant requirements and constraints.
3. Implement the algorithm in MATLAB.
4. Create appropriate tests.
5. Execute the tests.
6. Diagnose and correct implementation problems if tests fail.
7. Produce a working implementation.

## Demonstrates

- Technical reasoning
- MATLAB programming
- Mathematical interpretation
- Code generation
- Test creation
- Execution and iteration

---

# Demo 2 — MATLAB Optimization

## Scenario

Provide a correct but intentionally inefficient MATLAB implementation.

The implementation should be slow enough that meaningful optimization is possible.

## Task

Prompt Claude approximately as:

> This implementation is too slow for our validation workload. Optimize it without changing its numerical behavior. Benchmark the original and optimized implementations and verify equivalence.

Claude should:

1. Understand the algorithm.
2. Identify performance bottlenecks.
3. Optimize/vectorize the implementation.
4. Execute both implementations.
5. Benchmark them.
6. Compare their outputs.
7. Demonstrate that numerical behavior remains within an explicitly defined tolerance.

## Output

The demonstration should prominently show measurable results such as:

```text
Original runtime
Optimized runtime
Speedup
Number of vectors tested
Maximum absolute error
Pass/fail
```

---

# Demo 3 — MATLAB to Python Port

## Scenario

Use a meaningful MATLAB algorithm rather than a trivial syntax example.

## Task

Ask Claude to port the implementation to Python using appropriate numerical/scientific libraries.

Claude should:

1. Understand the MATLAB implementation.
2. Identify MATLAB/Python semantic differences that matter.
3. Implement the Python version.
4. Generate or consume common reference test vectors.
5. Execute the Python implementation.
6. Compare its output against MATLAB reference output.
7. Verify numerical equivalence within defined tolerances.

## Demonstrates

This should demonstrate engineering migration rather than simple syntax translation.

---

# Demo 4 — Log Investigation

## Scenario

Provide multiple realistic log files representing different system components.

The logs should contain:

- timestamps
- normal noise
- warnings
- unrelated errors
- relevant errors
- events distributed across multiple files

A failure should be deliberately planted.

## Task

Give Claude a simple request such as:

> Test 1847 failed. Figure out what happened.

Claude should autonomously:

1. Locate relevant log files.
2. Search large logs efficiently.
3. Correlate timestamps.
4. Reconstruct the event sequence.
5. Separate irrelevant errors from relevant evidence.
6. Determine the likely failure chain.
7. Cite supporting log evidence.
8. Produce a concise investigation report.

The answer should not be directly discoverable from one obvious error message.

---

# Demo 5 — Excel Investigation

## Scenario

Provide a realistic multi-sheet Excel workbook containing engineering or validation data.

The workbook should include:

- formulas
- cross-sheet relationships
- raw data
- calculated results
- summaries
- at least one deliberately planted problem

## Task

Use a request such as:

> Something is wrong with these validation results. Determine what's happening and correct the workbook.

Claude should:

1. Understand workbook structure.
2. Inspect formulas and data.
3. Follow relationships between sheets.
4. Identify the problem.
5. Explain its impact.
6. Correct the workbook.
7. Save a new output workbook.
8. Validate the correction.

---

# Demo 6 — CSV Data Analysis and Visualization

## Scenario

Provide a reasonably sized engineering test dataset.

The dataset should contain enough complexity for useful exploration and should include planted patterns or anomalies.

## Task

Ask Claude to investigate the dataset rather than prescribe exact analysis steps.

Claude should:

1. Inspect the dataset.
2. Determine useful analyses.
3. Write and execute analysis code.
4. Calculate appropriate statistics.
5. Identify patterns and anomalies.
6. Generate useful visualizations.
7. Explain the engineering significance of the findings.

Generated plots should become demo artifacts.

---

# Demo 7 — Specification to Implementation

## Scenario

Provide a realistic technical specification as a PDF.

The PDF should contain:

- prose requirements
- equations
- constants
- tables
- boundary conditions
- relevant and irrelevant sections

## Task

Use a request similar to:

> Implement the algorithm described in section 7.3 and create tests demonstrating that the implementation satisfies the specification.

Claude should:

1. Navigate the PDF.
2. Locate relevant information.
3. Interpret equations and tables.
4. Identify requirements and edge conditions.
5. Produce working implementation code.
6. Generate tests.
7. Execute them.
8. Verify the result.

The purpose is not to demonstrate PDF summarization.

The PDF is simply the authoritative engineering source from which Claude must perform real work.

---

# Demo 8 — Automated Verification

## Scenario

Provide:

- requirements
- an existing implementation
- existing tests
- existing test vectors

Intentionally leave important verification gaps and include at least one subtle defect.

## Task

Ask Claude to evaluate and improve verification of the implementation.

Claude should:

1. Understand the requirements.
2. Understand existing tests.
3. Determine which behaviors are inadequately tested.
4. Identify important boundary cases.
5. Generate additional tests.
6. Generate test vectors when appropriate.
7. Execute the tests.
8. Discover at least one deliberately planted defect.
9. Document the evidence.

---

# Demo 9 — Requirements Traceability

## Scenario

Provide:

- specifications
- requirements
- implementation
- tests
- test results

## Task

Ask Claude to determine the verification status of the requirements.

Claude should:

1. Extract or identify requirements.
2. Map requirements to implementation where appropriate.
3. Map requirements to tests.
4. Associate test results.
5. Identify missing implementation coverage.
6. Identify missing verification coverage.
7. Identify questionable or ambiguous mappings.
8. Produce a traceability matrix.

A useful output might be:

```text
TraceabilityMatrix.xlsx
```

with columns such as:

```text
Requirement
Source
Implementation
Verification Method
Test
Result
Evidence
Status
Notes
```

The demo should include deliberately missing coverage so Claude has something meaningful to discover.

---

# Demo 10 — Autonomous Engineering Investigation

This is the finale.

## Scenario

Provide Claude with an entire fictional engineering repository.

It should contain a mixture of:

- specifications
- PDFs
- MATLAB
- Python
- Excel
- CSV
- test definitions
- test results
- logs
- documentation
- irrelevant files

A non-obvious system-level failure should be deliberately planted.

The root cause should require information from several artifacts.

For example:

```text
Specification
      ↓
Algorithm requirement
      ↓
Implementation defect
      ↓
Missing boundary test
      ↓
Unexpected runtime behavior
      ↓
Log evidence
```

## Task

The prompt should intentionally provide little guidance:

> Validation failed. Investigate the failure, determine the root cause, and document your findings with supporting evidence.

Claude should autonomously decide:

- which files matter
- what to search
- which tools to use
- whether code needs to be executed
- whether data needs to be analyzed
- how artifacts relate to one another

The final result should contain an evidence-backed root-cause analysis.

This demo should combine capabilities introduced individually by earlier demos.

---

# 6. Shared Fictional Engineering Project

Strongly consider making the demonstrations part of one fictional engineering system.

For example, Demo 1 might create or work with an algorithm that appears throughout subsequent demos.

Possible relationship:

```text
Technical Specification
        ↓
MATLAB Reference Algorithm
        ↓
Optimized MATLAB
        ↓
Python Implementation
        ↓
Validation System
        ↓
Test Data
        ↓
Excel Results
        ↓
Runtime Logs
        ↓
Verification Evidence
        ↓
Requirements Traceability
```

The exact fictional product should be technically credible but should not introduce unnecessary domain complexity.

It should also avoid dependence on confidential, proprietary, or real company information.

Everything required by ClaudeDemoKit should be safe to place in the repository.

---

# 7. Demo Definition

Each demonstration should be declaratively defined.

A possible structure is:

```yaml
id: matlab-optimization
title: MATLAB Algorithm Optimization
order: 2

prompt: prompt.md

inputs:
  - input/algorithm.m
  - input/test_vectors.csv

expected_artifacts:
  - optimized_algorithm.m
  - benchmark_results.json

presentation:
  enabled: true

narration:
  enabled: true
```

The exact schema should be designed during implementation.

Avoid embedding presentation logic directly into individual demos.

---

# 8. Repository Structure

A possible initial organization:

```text
ClaudeDemoKit/
│
├── demos/
│   ├── 01_matlab_implementation/
│   ├── 02_matlab_optimization/
│   ├── 03_matlab_python_port/
│   ├── 04_log_investigation/
│   ├── 05_excel_investigation/
│   ├── 06_csv_analysis/
│   ├── 07_spec_implementation/
│   ├── 08_verification/
│   ├── 09_traceability/
│   └── 10_autonomous_investigation/
│
├── framework/
│   ├── runner/
│   ├── capture/
│   ├── presentation/
│   ├── narration/
│   └── video/
│
├── runs/
│
├── output/
│   ├── presentation/
│   ├── video/
│   └── artifacts/
│
├── templates/
│
├── README.md
└── CLAUDE.md
```

This is illustrative rather than mandatory.

Choose a structure that keeps demo content cleanly separated from framework implementation.

---

# 9. Run Capture

An important requirement is that the video should show **Claude actually performing the work**.

Do not fake results merely for presentation.

A live execution should generate a persistent run bundle containing sufficient information to reconstruct what happened.

For example:

```text
runs/
    <demo>/<run-id>/
        metadata.json
        prompt.md
        transcript.jsonl
        transcript.md
        events.jsonl
        artifacts/
        results.json
```

Capture useful events such as:

- prompt submitted
- Claude response
- tool invocation
- file read
- file search
- file modification
- command execution
- test execution
- artifact creation
- completion

Sensitive/internal reasoning should not be required or captured.

Only observable interaction and tool activity should be recorded.

---

# 10. Execution vs. Presentation

Execution and presentation must be separated.

Claude output cannot be assumed to be byte-for-byte deterministic.

Therefore:

```text
RUN
 ↓
actual Claude execution
 ↓
captured run bundle
 ↓
APPROVE/FREEZE
 ↓
deterministic presentation rendering
```

The final presentation and video should normally render from an approved run rather than requiring a fresh Claude execution.

This ensures that presentation rendering is repeatable.

A useful conceptual CLI might eventually support:

```text
claudedemokit run
claudedemokit run 04
claudedemokit approve 04
claudedemokit render
claudedemokit build
```

Exact commands are implementation decisions.

---

# 11. Presentation Generation

The project should automatically generate a presentation from the currently enabled demos.

Adding, removing, disabling, or reordering a demo should automatically affect the generated presentation.

The presentation should include:

- title/introduction
- concise explanation of ClaudeDemoKit
- demo sections
- relevant prompts
- selected interaction highlights
- screenshots or rendered interaction
- generated artifacts
- measurable results
- summary
- finale

Avoid slides full of text.

Whenever possible:

> Show the work rather than describe the capability.

---

# 12. Video Generation

The project should generate a polished video presentation.

The video should combine:

- generated slides
- captured/replayed Claude interaction
- generated artifacts
- code views
- plots
- Excel views where useful
- narration
- transitions

The video should be rebuildable without manually editing a video timeline.

---

# 13. Narration

Each demo should support declarative narration.

Narration may include:

- setup
- problem description
- commentary during execution
- result explanation
- transition to the next demo

Narration should be stored as text in the repository.

The framework should be capable of converting narration into audio through a configurable text-to-speech mechanism.

The TTS provider should not be unnecessarily coupled to the rest of the architecture.

Cached/generated narration should be reusable so rebuilding a video does not unnecessarily regenerate speech.

---

# 14. Deterministic Replay

The renderer should be able to replay an approved Claude run.

For example, recorded events might contain:

```json
{"time":0.0,"type":"prompt"}
{"time":1.4,"type":"assistant_text"}
{"time":3.2,"type":"file_read","path":"algorithm.m"}
{"time":6.1,"type":"command","command":"..."}
{"time":8.4,"type":"test_result"}
{"time":12.7,"type":"artifact","path":"benchmark.json"}
```

Presentation timing does not have to reproduce actual wall-clock timing.

The renderer may accelerate uneventful operations.

For example, a real 90-second operation could be represented in 15 seconds while still accurately showing what occurred.

The renderer must never fabricate actions Claude did not perform.

---

# 15. Artifact Preservation

The repository should make it easy to inspect exactly what went into and came out of every demonstration.

Important artifacts include:

- original prompt
- input files
- generated files
- transcript
- execution results
- benchmarks
- plots
- spreadsheets
- reports
- approved run metadata

A viewer should be able to inspect a demo after watching the presentation and reproduce or understand what happened.

---

# 16. Reproducibility

Record enough environmental information to understand a run, including where practical:

- Claude model
- date/time
- demo version
- Git commit
- relevant dependency versions
- operating system/runtime information
- MATLAB version if applicable
- Python version
- prompt hash
- input artifact hashes

The objective is engineering reproducibility, not pretending that generative-model responses themselves are perfectly deterministic.

---

# 17. Safety and Data Isolation

ClaudeDemoKit must contain no proprietary company data.

All:

- specifications
- algorithms
- logs
- test results
- spreadsheets
- requirements

should be synthetic and created specifically for the demonstration.

The fictional artifacts should nevertheless look credible enough to resemble real engineering work.

---

# 18. Self-Demonstrating Property

ClaudeDemoKit should ultimately be capable of demonstrating itself.

The repository contains:

- the prompts
- the source artifacts
- Claude's interactions
- generated outputs
- narration
- slides
- video-generation logic

A compelling closing point for the presentation is:

> Everything shown in this presentation—including the demonstrations, captured results, slides, narration, and final video—was generated from the ClaudeDemoKit repository.

Adding another demo to the repository should allow the presentation/video to be regenerated with that demo included.

---

# 19. Initial Development Priorities

Do not attempt to implement every sophisticated feature simultaneously.

Suggested development order:

### Phase 1 — Demo framework

Establish:

- repository structure
- demo manifest/schema
- demo discovery
- input management
- run directories
- artifact management

### Phase 2 — First working demo

Implement one end-to-end demo, preferably MATLAB Implementation or MATLAB Optimization.

Prove:

```text
demo definition
      ↓
Claude execution
      ↓
captured output
      ↓
stored artifacts
```

### Phase 3 — Replay/capture

Create the normalized run/event representation and deterministic replay mechanism.

### Phase 4 — Presentation generation

Generate slides automatically from enabled demos and approved runs.

### Phase 5 — Narration/video

Add narration generation and deterministic video assembly.

### Phase 6 — Remaining demos

Build the complete demonstration suite.

### Phase 7 — Finale

Construct the Autonomous Engineering Investigation using artifacts and concepts introduced by earlier demonstrations.

---

# 20. Engineering Expectations

Treat ClaudeDemoKit as a real software project rather than a throwaway script.

The implementation should favor:

- modular architecture
- clear interfaces
- testability
- deterministic behavior where possible
- good error reporting
- resumability
- caching
- idempotent builds
- explicit configuration
- minimal unnecessary dependencies
- readable logs
- inspectable intermediate artifacts

A failed demo execution should not destroy a previously approved run.

A presentation build should not require rerunning Claude unless explicitly requested.

---

# 21. Definition of Success

ClaudeDemoKit succeeds if an engineer watching the generated presentation comes away understanding that Claude is not merely a chatbot that can summarize documents.

The demonstrations should show Claude acting as an engineering tool capable of:

```text
reading
reasoning
searching
coding
executing
testing
measuring
debugging
analyzing
modifying artifacts
correlating evidence
and autonomously investigating problems
```

The strongest reaction should not be:

> "Claude can read PDFs."

It should be:

> "I can think of several things I could use this for in my own engineering work."

---

# 22. As Built

The sections above are the original brief and are kept as written. The finished suite
(release 1.0.7, all ten demos) departs from it in three places, all deliberately:

- **Demos are conversations, not one-shot prompts.** Each demo's `user.md` briefs a
  second Claude session that plays the engineer who asked: it reads each answer and
  replies, with questions, doubts or corrections, up to `max_follow_ups` times. It sees
  only what the person asking would have, never the hidden checks. Its own tool calls
  are recorded in the run bundle under `user_simulator/`, so this can be audited.
- **The finale's prompt names its deliverables.** Demo 10 asks for `root_cause.md` and
  a `findings.json` with a fixed schema (cause file and line, discriminator, failing
  runs, wrong value, cited evidence), plus a fix and tests if the code is at fault. That
  is what lets the independent checks verify the answer by property. The prompt still
  says nothing about where to look or what the cause is.
- **MATLAB code runs on GNU Octave.** Every `.m` file is executed and checked on Octave,
  and the prompts say so. Where this brief says MATLAB, read MATLAB/Octave.
