# Sign-off review: VAL-2026-05 acceptance workbook (v2.3.0-rc1)

**Conclusion: the ACCEPT is wrong. Against CVT-VAL-002 Rev A the campaign is
REJECT:** 34 of 40 runs pass, a pass rate of 0.85 against the required 0.95.

## What is wrong

1. **Position-error limit (Criteria!B2) is 5 m; the plan (§4) says 0.5 m.** Every
   Result formula compares against this cell, so all 40 runs showed PASS. With
   0.5 m the six `maneuver` runs fail: VR-1901 (0.887 m), VR-1903 (0.750),
   VR-1904 (1.003), VR-1917 (0.931), VR-1929 (0.837), VR-1932 (0.786). No other
   scenario exceeds 0.44 m, except VR-1935 (turn), which is exactly 0.500 m and passes
   (the limit is ≤). The failures are all one scenario, on both workers and on four
   different days, so this is a tracking-accuracy problem in high-acceleration
   profiles, not a worker or date effect.
2. **The Result formula (Runs!H2:H41) ignores the runtime limit.** §3 says a run
   passes only if both its error and its runtime are within limits. No run here is
   over 50 ms (max 43.3 ms; estimator-02 runs about 15–20 % slower than
   estimator-01 but stays inside the limit), so this doesn't change the
   VAL-2026-05 outcome. It would in a future campaign.

## What I changed in `validation_results_corrected.xlsx`

- Criteria!B2: 5 → 0.5.
- Runs!H2:H41: `=IF(AND(F2<=Criteria!$B$2,G2<=Criteria!$B$4),"PASS","FAIL")`.
- Run data and the Summary formulas are unchanged. The Summary now reads 40 total,
  34 passed, 6 failed, pass rate 85.0 %, verdict REJECT.

## Recommendation

v2.3.0's release record should not cite VAL-2026-05 as an acceptance. The
`maneuver` accuracy needs disposition (a fix or a plan change under §5) before
acceptance can be claimed.
