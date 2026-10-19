# Sign-off review: VAL-2026-05 (v2.3.0-rc1), checked against CVT-VAL-002 Rev A

**Reviewed:** 2026-10-16 · **Workbook:** `validation_results.xlsx` · **Corrected copy:** `validation_results_corrected.xlsx`

## Conclusion

**The ACCEPT recorded for this campaign is wrong. Under CVT-VAL-002 Rev A the campaign is a REJECT.**

| | Workbook as received | Re-scored against Rev A §4 |
|---|---|---|
| Runs | 40 | 40 |
| Passed / Failed | 40 / 0 | 34 / 6 |
| Pass rate | 100.0 % | 85.0 % (minimum 95 %) |
| Verdict | ACCEPT | **REJECT** |

The six failing runs are **VR-1901, VR-1903, VR-1904, VR-1917, VR-1929 and VR-1932**. All are `maneuver`
scenarios, with peak position errors of 0.75 to 1.003 m against the 0.5 m limit. Every `maneuver` run
in the campaign failed. VR-1935 (0.500 m) is exactly at the limit, so it passes. Every run's runtime is
within the 50 ms limit (the highest is 43.3 ms).

v2.3.0 shipped on 30 May with this campaign cited as its acceptance evidence. As recorded, the campaign
does not support that release. QA should take this up before the release record is closed.

## Defects found (cells as received)

1. **Criteria!B2:** the maximum peak position error is entered as `5` m. §4 sets it at `0.5` m. This
   is the defect that changes the verdict.
2. **Runs!H2:H41:** the PASS/FAIL formula checks only position error. It ignores the 50 ms runtime
   limit (Criteria!B4), although §3 requires both checks. This doesn't change the outcome here, but
   it is wrong for the template.
3. **Summary!B5:B11:** the formulas only cover rows 2–41. In a future campaign with more than 40 runs,
   the extra runs would be silently left out of the counts and the verdict.

## Changes made in `validation_results_corrected.xlsx`

- Criteria!B2 changed from 5 to **0.5**.
- Runs!H2:H41 now checks both limits and treats a missing or non-numeric error or runtime as FAIL.
  A row with no RunID shows blank.
- Summary scoring now works from the run data and no longer depends on column H, so it stays correct
  if column H isn't filled down for runs added after row 41. All ranges run to row 1000.
  - Passed (B6) uses a `SUMPRODUCT` over every row that has a RunID and is within both limits.
  - Failed (B7) is `Total − Passed`, so the two always add up to the total.
  - Rows with no RunID are not counted.
- Summary!B3 (build) and B4 (period) are now calculated from Runs!D and Runs!B. B3 shows
  "MIXED BUILDS" if the runs don't all use the same build. B2 (campaign ID) is still typed in, because
  it isn't recorded per run.
- New **Data check** (Summary!B14): shows "OK" only if every run has a numeric error and runtime and
  column H agrees with the Summary counts. Otherwise it shows a CHECK message.
- **Sign-off:** Summary!B13 ("Prepared by: D. Volkov, 2026-05-28") was cleared, because it stood next
  to an ACCEPT that is now a REJECT. B15 (Sign-off) is empty, waiting for the QA signatory. B16
  records the original preparer and date, the original ACCEPT, and the reason it changed.
- Summary!B12 now uses a fixed reference to the pass-rate limit (`Criteria!$B$3`).
- Formulas were tested with a Python evaluator on the corrected file and on 60-run test copies. The
  test copies had a blank row, column H not filled down, and failures on error, runtime and missing
  data. Every result came out as expected.
- The recorded run data (Runs!A1:G41) is unchanged; I checked it cell by cell against the original.
  Every result is still formula-driven, and no values were pasted in.
- The file is set to recalculate fully when opened. It was saved without cached results, so open it
  in Excel to see the computed values: 40 / 34 / 6 / 85.0 % / REJECT, Data check OK. The figures
  above were also recomputed independently from the run data. `MIN`/`MAX` and `SUMPRODUCT` were used
  instead of `MAXIFS` or `"<>"` criteria so the formulas could be checked with the evaluator; Excel
  gives the same results either way.
