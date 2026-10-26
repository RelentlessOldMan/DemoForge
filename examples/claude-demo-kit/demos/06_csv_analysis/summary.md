<!-- What this demo is, for the index page shipped with the videos.
     Same wording as docs/demos.md; keep the two in step. -->

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
