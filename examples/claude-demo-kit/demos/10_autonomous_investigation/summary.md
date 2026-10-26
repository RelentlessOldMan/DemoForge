<!-- What this demo is, for the index page shipped with the videos.
     Same wording as docs/demos.md; keep the two in step. -->

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
