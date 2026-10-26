<!-- What this demo is, for the index page shipped with the videos.
     Same wording as docs/demos.md; keep the two in step. -->

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
