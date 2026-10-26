<!-- What this demo is, for the index page shipped with the videos.
     Same wording as docs/demos.md; keep the two in step. -->

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
