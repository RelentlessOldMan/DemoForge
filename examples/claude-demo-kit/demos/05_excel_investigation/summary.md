<!-- What this demo is, for the index page shipped with the videos.
     Same wording as docs/demos.md; keep the two in step. -->

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
