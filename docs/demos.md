# The ClaudeDemoKit demos

ClaudeDemoKit is DemoForge's example content set: ten recorded sessions of Claude doing
engineering work. All ten share one project, a Kalman filter that tracks a moving
object from noisy sensor readings, so each demo builds on the ones before it.

Every demo is a conversation, not a one-shot prompt. A second Claude session plays the
engineer who asked for the work. It reads each answer and replies the way that person
would, and it never sees the hidden checks. After the session, DemoForge checks the
results on its own with checks Claude never saw: tests, reference answers, and
deliberately broken versions of the code that a good test must catch. The numbers below
come from those checks (`approved/<demo>/results.json`).

These ten were chosen because they are interesting to watch. They are a small sample of
what Claude can do, not the limit of it.

---

## 1. MATLAB Algorithm Implementation

**The problem.** The team has a written specification for the filter's math, a file of
settings, and a recording of 1,500 noisy position readings. They need working MATLAB
code that follows the spec exactly, plus an automatic test that stops the build if
anyone ever breaks the filter. Nobody can check 1,500 rows by eye, and a test that
always passes is worse than none.

**What Claude did.** It wrote `kalman_update.m` and `test_kalman_update.m`, and ran them
under GNU Octave. When the engineer noticed that a hand-worked check had failed and been
edited before it passed, Claude explained that the mistake was in its expected value,
not the filter. It said plainly that it should have reported that the first time. It
then made the test stricter: it checks the loaded settings, and the first-step check
now always runs.

**The outcome.** The filter matches the reference with an error of exactly zero, also on
a second set of settings Claude never saw. The test passes on correct code and fails on
a deliberately broken filter.

## 2. MATLAB Algorithm Optimization

**The problem.** The filter is correct but slow. It was translated line by line from C,
with every matrix operation spelled out as loops. The team needs a drop-in faster
version that changes no answer by more than one billionth. Rounding makes that hard:
adding numbers in a different order can change the last digit.

**What Claude did.** It wrote `kalman_update_fast.m`, a benchmark, and `OPTIMIZATION.md`.
Over three rounds with the engineer, it added long-stream checks and made the fast
version add in exactly the original's order, so the output is bit-identical. It also
timed the speed without a shortcut that only helps when the filter settles, so the
report gives two honest numbers: about 31× with the shortcut, and 9.4× without.

**The outcome.** On DemoForge's own runs the answers are identical to the original (an
error of exactly zero), and the code is 33 times faster.

## 3. MATLAB to Python Port

**The problem.** The data team works in Python and wants the same filter there, with
every number within one billionth of the MATLAB original. MATLAB and Python differ in
quiet ways (indexing, array layout, how equations are solved), and one sample recording
only proves so much.

**What Claude did.** It wrote `kalman_filter.py`, then built a set of test cases with
harder settings, MATLAB reference outputs, and `check_agreement.py`. When some cases
couldn't meet an absolute tolerance, the engineer asked for a scaled one and a fixed
list of report-only cases, not one decided at run time. Claude made those changes. It
showed that two deliberately broken ports fail the check while a harmless change
passes, and admitted that it had moved a threshold after seeing the results.

**The outcome.** On the recording, the port matches exactly. On a hidden second model,
with different settings and an angled sensor, it agrees to about 3 × 10⁻¹⁴.

## 4. Log Investigation

**The problem.** One of the 51 nightly tests failed with a "not a number" error in the
filter. The engineer has to know before tonight's run whether it is real or a one-off.
They have five logs to go on, full of other warnings that look just as suspicious.

**What Claude did.** It read all five logs and traced the chain back from the error:
the disk filled up, a data file was cut off but still marked ready, and the filter read
the truncated data. It wrote `findings.md` and `findings.json`, with each step citing a
log line, and ruled out the red herrings. The engineer caught one sentence that went
beyond the logs, and Claude corrected it.

**The outcome.** Every cited line exists, the cause is right, and all three kinds of
decoy are ruled out rather than blamed.

## 5. Excel Investigation

**The problem.** A release has shipped on an acceptance spreadsheet that says ACCEPT.
Quality assurance wants an independent review before closing the record. The
spreadsheet agrees with itself, so any mistake hides in one cell or formula.

**What Claude did.** It checked the workbook against the validation plan. The error
limit had been typed in as 5 m instead of the plan's 0.5 m, ten times too loose. With
the right limit, six runs fail, only 34 of 40 pass (85%, below the 95% required), and the
verdict is REJECT. It also found that the formulas never checked run time, and only
counted the first 40 rows. Claude wrote a corrected workbook with live formulas, a review note, and
`findings.json`. The engineer pointed out that the formulas would miscount a larger
campaign. Claude reworked them and tested them on 60-run copies.

**The outcome.** DemoForge recalculated the corrected workbook on the real data and on
five altered versions. Every result, count and verdict followed the plan.

## 6. CSV Data Analysis and Visualization

**The problem.** The nightly regression tests go red far more often than they used to.
There are theories, such as flaky tests or one slow worker machine, but nobody has
gone through the two months of results (3,060 rows).

**What Claude did.** It wrote `analyze.py`, which produces a numbers file and a plot.
It opened the plot to look at it, fixed a label that overlapped the legend, and marked
a night with no batch. The video shows each version of the plot as Claude saw it. Its
`analysis.md` puts the start on 31 May, the first night on version 2.3.0, with errors
about 172 times larger on both workers. The slower worker is a difference, not the
cause.

**The outcome.** DemoForge recomputed everything from the raw export, and Claude's
numbers matched it. The engineer's one correction, an overstated sentence, was fixed.

## 7. Specification to Implementation

**The problem.** A PDF specification defines a new "measurement gate". The gate
rejects sensor readings too far from what the filter expects, and must never let a
malformed reading through or crash. The team needs the gate in MATLAB and a test strict
enough to run in continuous integration.

**What Claude did.** It read the PDF (the video shows the pages it was given) and wrote
`measurement_gate.m` and a 373-check test. It also pointed out something the spec
doesn't cover: inputs with the wrong shape. It chose to reject those too, and said so.

**The outcome.** The gate matched the hidden reference on every decision and handled
malformed input, and its test caught all four broken gates. **One check fails:** the
test also fails a correct gate that does only what the spec lists, because it demands
the extra rejections Claude chose. Claude flagged the gap, but built its own answer into
the CI gate.

## 8. Automated Verification

**The problem.** Release 2.1's filter has a spec and a passing test. The release
engineer wants an independent check of the code against the spec, without changing the
code.

**What Claude did.** It found that the code starts from hard-coded values instead of
the starting values the spec says to read. The current settings happen to match those
hard-coded values, which is why everything passed. It wrote `verification_report.md`
citing the requirement and lines, plus a stronger test.

**The outcome.** The new test passes a correct filter and fails all three versions that
mishandle the starting values, plus six other broken ones. With different starting
values, the shipped code is off by more than ten.

## 9. Requirements Traceability

**The problem.** Before release 2.2, every requirement needs to be linked to the code
that implements it and the tests that prove it, with an honest status. A test can carry
a requirement's name and still check nothing.

**What Claude did.** It built `TraceabilityMatrix.xlsx`. It injected bugs to see which
tests actually catch them, and flagged the new sixth requirement as missing from the
code. The engineer pushed back on two statuses, and Claude agreed and downgraded them.

**The outcome.** All six requirements are traced, every cited test exists, and the gap
is flagged. **One check fails.** DemoForge reads the first requirement as the call
signature alone and expects "verified". The engineer and Claude read it as also
covering a rule no test checks. The spec leaves this open.

## 10. Autonomous Engineering Investigation

**The problem.** A validation campaign of 60 runs was rejected: 17 runs missed the
accuracy limit after the release added a Doppler mode, which measures velocity as
well as position. The change board wants the root
cause, with every claim tied to a file and line, a colleague's three theories confirmed
or ruled out, and a fix with tests if the code is at fault.

**What Claude did.** It searched the repository: code, controlled documents, a
spreadsheet, data and logs. It found that the gate ignores the threshold it is given
and uses a hard-coded one that is too strict for Doppler, so every failing run
was a Doppler run. It fixed the gate, added
tests, and wrote `root_cause.md` and `findings.json`. The engineer pushed back twice on
claims that went past the evidence. Claude reworded them to separate what is shown from
what is only inferred.

**The outcome.** All fourteen checks pass: real citations, the right cause and failing
runs, a fix that matches a hidden reference, and tests that fail on the shipped gate.
