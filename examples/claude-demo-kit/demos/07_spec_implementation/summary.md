<!-- What this demo is, for the index page shipped with the videos.
     Same wording as docs/demos.md; keep the two in step. -->

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
