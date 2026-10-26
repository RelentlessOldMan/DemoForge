<!-- What this demo is, for the index page shipped with the videos.
     Same wording as docs/demos.md; keep the two in step. -->

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
