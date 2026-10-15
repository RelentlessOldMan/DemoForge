# Root cause: VAL-2026-09 rejection of v2.4.1

**Campaign:** VAL-2026-09 (2026-09-26) · **Build:** v2.4.1, with v2.3.2 planar baseline
runs · **Verdict:** REJECT, pass rate 0.717 against a minimum of 0.95 (CVT-VAL-002 §4)

## What failed

17 of 60 runs exceeded the 0.5 m peak position error limit
(`logs/validation-runner.log:63`). Every one of them is a **Doppler-mode** run:

| Mode / build      | Runs | Failed | Max error | Gate rejections |
|-------------------|------|--------|-----------|-----------------|
| planar, v2.3.2    | 20   | 0      | 0.383 m   | ~5 %            |
| planar, v2.4.1    | 20   | 0      | 0.405 m   | ~5 %            |
| Doppler, v2.4.1   | 20   | 17     | 1.319 m   | ~20 %           |

Failing runs: VR-2101, VR-2102, VR-2103, VR-2105, VR-2106, VR-2113, VR-2114, VR-2118,
VR-2119, VR-2122, VR-2126, VR-2131, VR-2138, VR-2146, VR-2151, VR-2152, VR-2155. The
three Doppler runs that passed (VR-2116, VR-2117, VR-2134) only just did, at 0.42 to
0.47 m. No run came near the 50 ms runtime limit (maximum 39.6 ms).

## Root cause

`src/measurement_gate.m` compares the NIS against a threshold of its own instead of the
`gamma` it is passed:

    15:  GATE_CHI2 = 5.991;
    28:  accept = (d2 <= GATE_CHI2);

5.991 is the chi-squared critical value for m = 2 at 95 %: the fixed threshold of
CVT-SRS-003 Rev B, which v2.3.0 implemented (`docs/CHANGELOG.md:33-34`). Rev C §7.3.3
(requirement G3, `docs/requirements.csv:10`) requires the gate to use the supplied
gamma and hold no threshold of its own. The caller does supply the right one:
`src/cvt_model.m:42` sets `model.gamma = cfg.gate.gamma.(mode)`, which is 13.277 for
Doppler (`config/estimator_config.json:22`; chi-squared, m = 4, 99 %) and 9.210 for
planar. The gate validates `gamma` and then ignores it.

In Doppler mode (H = I4, m = 4), d2 for a good measurement is chi-squared with 4
degrees of freedom, and P(chi2_4 > 5.991) = 0.20. The gate therefore throws away one
good measurement in five instead of one in a hundred. A rejected measurement leaves the
predicted state in place (`src/kalman_update.m`), so the track coasts on prediction for
a fifth of the stream and drifts past 0.5 m. In planar mode P(chi2_2 > 5.991) = 0.05:
too many rejections (5 % instead of 1 %), but not enough to break the limit.

## Evidence chain

1. **The failures separate on mode, not build or worker.** Doppler 17/20 failed,
   planar 0/40 (`data/validation_runs.csv`, e.g. line 2, VR-2101, 1.319 m). v2.4.1
   planar runs pass as well as the v2.3.2 baseline, so this is not a release-wide
   regression. Failures by worker are 8 / 5 / 4, following the mode mix each worker
   happened to get.
2. **The gate rejects ~20 % of Doppler measurements.** Every Doppler run logs a
   rejection-rate alert (`logs/estimator-worker.log:8`, VR-2101: 20.47 %; line 9:
   307 of 1500). Planar runs are at ~5 % (line 29, VR-2104: 5.00 %). Those are exactly
   P(chi2_4 > 5.991) and P(chi2_2 > 5.991).
3. **The rejected values give the threshold away.** Every logged rejection has
   d2 > 5.991, and most Doppler rejections are far below 13.277 (6.208, 6.614 and 8.694
   at lines 5-7). A correct Doppler gate admits all of them.
4. **The code.** The inlined constant at `src/measurement_gate.m:15`, used at line 28.
   Calling the gate directly with d2 = 8 gives the same decision at gamma = 9.21,
   13.277 or 1e6.
5. **The configuration is right.** Gamma per mode at `gate.confidence` 0.99
   (`config/estimator_config.json:19-23`) matches CVT-SRS-003 Rev C Appendix A.

## Why it was not caught

`tests/test_measurement_gate.m` fixes `GAMMA = 5.991` (line 7) and uses only m = 2. The
gate's inlined value equals the value the test passes, so T4 "reject beyond gamma"
passes whether or not the gate honours gamma. requirements.csv still traces G3 to T4
as Verified (`docs/requirements.csv:10`), and the release build was green
(`tests/test_results.txt:13`, 5/5). Nothing exercised the gate in Doppler mode before
the campaign.

## Ruled out

- **v2.3 covariance regression (handover theory 1).** `src/kalman_update.m:41` forms
  `S = H * P * H' + R` from the current P every step, as the v2.3.2 fix requires, and
  v2.4.1 planar runs pass at the same error as v2.3.2. A regression in the shared
  update would hit both modes.
- **estimator-02 (theory 2).** It is about 19 % slower (`logs/scheduler.log:11`), but
  runtimes stay under 40 ms against a 50 ms limit, no run failed on runtime, and its
  failure count (5) is lower than estimator-01's (8).
- **Doppler sensor noise or a limit that is too tight (theory 3).** The rejection rate
  is exactly the chi-squared tail beyond 5.991 for m = 4, which is what a correct R
  produces; an R that understated the noise would push rejections well above that. The
  defect is in the gate, so relaxing CVT-VAL-002 §4 would only hide it.
- **Configuration.** gate.gamma holds the Appendix A values, and cvt_model passes them
  through.

## Fix and recommendation

- `src/measurement_gate.m`: removed `GATE_CHI2`; the decision is now `d2 <= gamma`.
- `tests/test_measurement_gate.m`: uses the configured gammas and adds Doppler (m = 4)
  cases at 13.277 and 9.488, the d2 == gamma boundary, a NaN gamma, and every row of
  `data/gate_vectors.csv`. The updated test fails against the shipped gate (T6) and
  passes against the fix. `test_kalman` still passes.
- Re-trace G3 in `docs/requirements.csv` to the new tests, and rerun VAL-2026-09 in
  both modes before release. Expect about 1 % gate rejections in both modes.
