<!-- What this demo is, for the index page shipped with the videos.
     Same wording as docs/demos.md; keep the two in step. -->

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
