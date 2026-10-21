# Root cause: VAL-2026-09 rejection of v2.4.1

**Status:** defect established; its link to the 0.5 m failures is inferred, not confirmed.
- **Shown:** the gate ignores the gamma it is passed, and that fully explains the Doppler and planar rejection rates in the campaign.
- **Inferred, unconfirmed:** that the extra Doppler rejections drive the 0.5 m failures. This stays unconfirmed until the recorded streams are replayed on the fixed build (sections 2.2 and 3a).
- Code is fixed and tests are updated in the working tree. The release has not been rebuilt or re-validated.
**Date:** 2026-10-21. This continues Dmitri Volkov's handover (`notes/handover_notes.md`).

## 1. What failed

VAL-2026-09 ran 60 runs: 20 Doppler on v2.4.1, 20 planar on v2.4.1, and 20 planar on the v2.3.2 baseline. 17 runs failed, giving a pass rate of 0.717 against the minimum of 0.95, so the verdict was **REJECT** (`logs/validation-runner.log:75`).

- Every failure is a **Doppler** run that broke the 0.5 m `max_pos_error` limit: VR-2101, 2102, 2103, 2105, 2106, 2113, 2114, 2118, 2119, 2122, 2126, 2131, 2138, 2146, 2151, 2152 and 2155. Their peak errors range from 0.64 to 1.32 m.
- No run failed on runtime. The largest runtime was 39.6 ms against a 50 ms limit.
- Planar passed 40/40 on both builds.
- 3 Doppler runs passed narrowly: VR-2116 (0.468 m), VR-2117 (0.470 m) and VR-2134 (0.415 m). They ran with the same defect and the same rejection rate as the failures (section 3).

The attribute that separates the failures is `mode = doppler` (equivalently `measurement_dim = 4`). Build, worker and time do not.

## 2. Root cause

### 2.1 Shown: the gate ignores gamma, which explains the rejection rates

`src/measurement_gate.m` ignores its `gamma` argument and compares against a constant left over from CVT-SRS-003 Rev B:

```matlab
15    GATE_CHI2 = 5.991;
...
28    accept = (d2 <= GATE_CHI2);
```

5.991 is the chi-squared critical value for **m = 2 at 95 %**. CVT-SRS-003 Rev C §7.3.3 and G3 changed this for v2.4. The threshold must now be the value for the active mode's measurement dimension at the configured confidence, supplied by the caller, and "the gate itself holds no threshold value."

The caller does its part correctly:

- `estimator_config.json` has `gamma.doppler = 13.277` and `gamma.planar = 9.210`, which are the Appendix A values at 99 %.
- `cvt_model.m:42` loads the value for the active mode.
- `kalman_update.m:42` passes it to the gate.

The gate then discards it.

In Doppler mode (m = 4), the NIS of a consistent measurement follows a chi-squared distribution with 4 degrees of freedom. The probability that it exceeds 5.991 is e^(-3.0)·(1 + 3.0) ≈ **20 %**. At 13.277, the probability is 1 %.

The campaign matches the wrong threshold, not the configured one (section 3, items 1-4):
- Every Doppler run rejected 17.9-21.1 % of measurements.
- Every rejected d2 is above 5.991, and 59 of the 60 logged Doppler rejections are below 13.277.
- The recorded gate vectors and a deterministic replay through `cvt_model` → `kalman_update` → `measurement_gate` reproduce 20.0 % exactly.

**Wrong value in use:** 5.991. **Correct value:** 13.277 (Doppler). Planar also uses 5.991 where it should use 9.210, and rejects about 5 % instead of 1 %. That is the same threshold and rate as the v2.3.2 baseline, so on v2.4.1 the defect did not change planar gate behaviour from a baseline that passed.

### 2.2 Inferred, not confirmed: that the extra rejections cause the 0.5 m failures

On a rejected step the filter keeps the predicted state (`kalman_update.m:43-45`). Throwing away about 1 in 5 valid Doppler measurements instead of 1 in 100 plausibly raises peak position error. I infer this is why Doppler runs exceed 0.5 m.

**Supports the inference:**
- The failures are confined to the one mode where the defect changes behaviour relative to a passing baseline.
- In simulation, the shipped gate's peak error is never better than the fixed gate's.

**Does not establish it:**
- **The rate doesn't predict the error within Doppler.** Across the 20 Doppler runs, rejection rate and peak error are essentially uncorrelated (Pearson r = −0.16, Spearman ρ = −0.17, p = 0.46). VR-2155 rejected 17.9 % and failed at 1.00 m; VR-2134 rejected 20.0 % and passed at 0.42 m.
  - The rates only spread by about the binomial sampling noise (±1 %), so a correlation was not necessarily expected.
  - What matters may be where the rejections fall in each stream. The worker log records only 3 rejections per run, so that cannot be checked from the artifacts.
- **No simulation reproduces the field results** (section 3a), so the size of the effect on the field streams is unknown.
- **The fix may not be enough.** Under Gaussian noise at the configured Q and R, even an ungated filter peaks at about 1.1 m.

**What confirms or refutes it:** replay the recorded VAL-2026-09 Doppler streams on the fixed build and score them exactly as the runner does.
- If they pass, the link is confirmed.
- If they still fail, the gate defect is still real and must be fixed, but it is not the whole cause of the 0.5 m failures. The Doppler-specific explanations in section 5 would then need reopening, along with the scoring definition of `max_pos_error`.

## 3. Evidence

1. **The rejection rates match the wrong threshold exactly.**
   - Doppler rejection rates in `logs/estimator-worker.log` are 17.9-21.1 % in every v2.4.1 Doppler run, including the 3 that passed. The theoretical tail of chi-squared(4) above 5.991 is 19.99 %, and the binomial spread for n = 1500 is about ±1 %.
   - Planar rejection rates are 3.9-5.7 %, on both v2.4.1 and v2.3.2. The tail of chi-squared(2) above 5.991 is 5.0 %. The correctly applied 9.210 would give 1 %.
   - All 20 Doppler runs, and no planar run, logged "rejection rate ... above alert level 10.0 %" (for example `estimator-worker.log:8`).
2. **The rejected d2 values sit between the two thresholds.**
   - The smallest rejected d2 in the log is 6.005, just above 5.991, in both modes.
   - 59 of the 60 logged Doppler rejections have d2 < 13.277, so a correct gate would have admitted them. Example: `estimator-worker.log:5`, `run=VR-2101 k=501 rejected d2=6.208`.
   - 95 of the 120 logged planar rejections have d2 < 9.210. Example: `estimator-worker.log:26`, `run=VR-2104 ... rejected d2=7.544` on v2.4.1.
3. **The recorded gate vectors reproduce it in Octave.** I replayed `data/gate_vectors.csv` (both modes, gamma per row) through the shipped `measurement_gate`. It rejects 7 vectors that §7.3.2 requires it to admit:
   - planar d2 = 7.36 and 8.94 with gamma 9.210;
   - Doppler d2 = 6.72, 9.93, 10.4, 11.6 and 12.9 with gamma 13.277.

   Every disagreement has 5.991 < d2 ≤ gamma. The rows recorded with gamma = 5.991 all agree, which is the only case the old constant gets right.
4. **The rejection rate is reproduced exactly through the full code path.** I placed innovations at 1000 evenly spaced chi-squared(m) quantiles of NIS and sent them through `cvt_model` → `kalman_update` → `measurement_gate`. This is now tests T5 and T6 in `tests/test_kalman.m`.

   | Gate | Doppler rejected | Planar rejected |
   |------|------------------|-----------------|
   | Shipped | 20.0 % (campaign: 17.9-21.1 %) | 5.0 % (campaign: 3.9-5.7 %) |
   | Fixed | 1.0 % (spec at 99 %) | 1.0 % (spec at 99 %) |

5. **The code is wrong; the configuration is right.** `config/estimator_config.json:21-22` holds the correct values, and `cvt_model.m:42` and `kalman_update.m:42` deliver them. This also explains why the v2.4.1 "configuration fix" changed nothing in behaviour: it supplied a value that the gate never reads.

## 3a. What is not established: whether the fix brings Doppler under 0.5 m

The defect and its effect on gating are established. It is **not** established that the fixed build will meet the 0.5 m limit on the campaign streams. The recorded field streams are not in this repository, and simulation cannot settle the question. (An earlier version of this write-up cited a 1500-step sinusoidal stream as showing the fix removes the failure. That stream does not resemble the campaign: it gave only 5.9 % rejection on the shipped gate and a 0.531 vs 0.5 m margin. I have withdrawn it as evidence.)

**Monte Carlo replay.** I generated truth from the configured F and Q, added Gaussian measurement noise at the configured R, ran 1500 steps, and used 20 seeds per case. The peak 2-D position error is taken over the whole run.

| Mode | Gate | Rejected (min / median / max) | Peak error, m (min / median / max) | Runs ≤ 0.5 m |
|------|------|-------------------------------|------------------------------------|--------------|
| Doppler | Shipped | 25.0 / 38.7 / 72.7 % | 20.4 / 259 / 2944 | 0/20 |
| Doppler | Fixed | 0.5 / 1.0 / 1.7 % | 1.01 / 1.33 / 5.58 | 0/20 |
| Doppler | None | 0 | 0.92 / 1.11 / 1.38 | 0/20 |
| Planar | Shipped | 6.3 / 11.4 / 44.7 % | 5.35 / 48.4 / 1879 | 0/20 |
| Planar | Fixed | 0.7 / 1.2 / 1.7 % | 1.55 / 2.22 / 4.98 | 0/20 |
| Planar | None | 0 | 1.23 / 1.33 / 1.69 | 0/20 |

My first probe during the investigation (40.8 % rejection, 399 m mean peak, 1.116 m ungated) was this same simulation. I set it aside without reporting it, which I should not have done. Its numbers are correct for what it simulates, and it was also internally consistent:

- **Why the rejection rate was above 20 %.** The 20 % figure is the false-rejection rate only while the filter is consistent, meaning its covariance P describes its actual error.
  - The shipped gate removes the largest innovations. After a rejection the true error is therefore larger than P says, so the next innovations are more likely to be rejected too.
  - While coasting, P grows by only Q per step, but the position error grows by the full velocity error.
  - With noise at the configured Q, this compounds into track loss. Every seed loses track, with rejection rates of 25-73 % and errors of tens to thousands of metres.
- **Why the ungated filter was over 0.5 m.** At the configured Q and R, the steady-state posterior position standard deviation is 0.28 m per axis for Doppler and 0.35 m for planar. Over 1500 steps the expected peak of the 2-D error is about 1.1 m and 1.3 m. No gate setting can bring that under 0.5 m.

**The simulation does not represent the field streams.** The campaign contradicts it in three ways:

- Planar runs, with the same R as Doppler's position channels, peaked at 0.07-0.41 m over 40 runs, against 1.2-1.7 m in simulation even with no gate.
- The shipped gate did not cause track loss in the field. Rejection rates clustered tightly at 17.9-21.1 % (Doppler) and 3.9-5.7 % (planar), and peak errors were 0.4-1.3 m.
- No scaling of the true Q (×1 down to 0) and R (×1 down to 0.25) that I tried reproduces both the field rejection rates and the planar error levels. Wherever the shipped gate rejects about 20 % (Doppler) or about 5 % (planar), simulated planar errors exceed 1 m.

There is also an unresolved inconsistency in the campaign artifacts. Rejection rates matching the chi-squared tails imply innovations distributed as the configured S predicts. Planar peak errors of 0.4 m or less over 1500 steps imply estimation error several times smaller than the configured model predicts. Under Gaussian noise both cannot hold. Possible explanations include non-Gaussian field noise, or a `max_pos_error` that is not computed as I assumed (for example a settling window, subsampling or a different norm). I could not check either from this repository.

**What the evidence does support.**

- The defect is real, and it is the only identified difference that is specific to Doppler.
- It makes the Doppler gate reject 20 % of measurements instead of 1 %, which is what the campaign logs show.
- In every simulated condition, the fixed gate's peak error is less than or equal to the shipped gate's, and it rejects at the specified rate.
- The 3 Doppler runs that passed had the same 18-20 % rejection rate as the 17 that failed, and rate does not predict error within Doppler. This neither confirms nor rules out the gate as the driver (section 2.2).

**Whether v2.4.2 passes can only be shown by replaying the recorded VAL-2026-09 streams on the fixed build** (recommendation 2).

## 4. Why it was not caught earlier

- **The gate tests use the same value as the bug.** `tests/test_measurement_gate.m:7` sets `GAMMA = 5.991`, the same number hard-coded in the gate, and every test case is 2-D. A gate that ignores gamma passes all five tests. `docs/requirements.csv:10` records G3 ("use the supplied gamma") as Verified by T4, but T4 cannot tell a gamma it was given from one it holds itself.
- **No test runs the gated Doppler path.** `test_kalman.m` T4 (Doppler, H = I4) builds its model by hand with no `gamma` (line 36, `md = model;`), so the gate never runs. Nothing exercised `cvt_model` → `kalman_update` → `measurement_gate` together.
- **The SRS verification step was never automated.** CVT-SRS-003 §8 requires checking gate decisions over recorded innovation streams from both modes. `data/gate_vectors.csv` exists for that purpose but no test reads it. It would have failed on 7 rows.
- **v2.4.1 was released as "config only, no code changes."** That framing suggested the gate's use of the new table had already been verified, when no code had ever been checked against it.
- **The runtime warnings were not acted on.** Every v2.4.1 Doppler run raised a `rejection rate ... above alert level 10.0%` warning, and nothing escalated it before the campaign verdict.
- **The by-build view pointed in the wrong direction.** Every Doppler run was on v2.4.1, so mode and build are confounded in the "By Build" tab.

## 5. Ruled out

| Hypothesis | Verdict | Why |
|---|---|---|
| (1) The v2.3.0 covariance regression is back | Ruled out | `kalman_update.m:41` forms `S = H*P*H' + R` from the current predicted P on every step. Planar on v2.4.1 (20/20 pass, mean 0.251 m, max 0.405 m) matches v2.3.2 (20/20, mean 0.224 m, max 0.383 m). That regression showed up as an error of about 7e-8, not 1 m. The by-build gap comes entirely from mode confounding. |
| (2) estimator-02 is slow | Ruled out | No run failed on runtime (max 39.6 ms ≤ 50 ms). Failures by worker: estimator-01 8, estimator-02 5, estimator-03 4, so estimator-02 has fewer than estimator-01. Doppler fails on every worker. The 19 % slowdown is real and worth the ops review, but it is unrelated. |
| (3) The Doppler sensor is noisier than R | Ruled out as the cause of this failure | Under-modelled noise would inflate d2 and push rejections above 13.277. Instead the rejections fill exactly the band between 5.991 and 13.277, and the rates match the chi-squared(4) tail above 5.991 to within sampling error. The question of whether 0.5 m is achievable is still open (see section 3a): if the field streams really carried the configured noise, no filter tuning would hold a 1500-step peak under 0.5 m. The planar results say the streams are much quieter than that, but this has to be confirmed by the replay before anyone argues for or against the limit. |
| Bad or missing gamma in config (the v2.4.1 change) | Ruled out | The values match Appendix A at the configured 99 %, and `cvt_model` delivers them correctly. |
| Infrastructure (heartbeat, upload retry, disk at 71 %, TLS notice) | Ruled out | Failures follow the mode, not the time or the worker. No infrastructure event lines up with them. |

These hypotheses are ruled out on the campaign evidence as it stands. If the replay of the recorded streams on the fixed build still fails (section 2.2), Doppler-specific explanations need to be reopened. These include theory (3) and the Doppler H/R configuration.

## 6. Fix made (working tree)

- **`src/measurement_gate.m`:** removed `GATE_CHI2`. The decision is now `accept = (d2 <= gamma)` as required by §7.3.2 and G3, and the header comment states that the gate holds no threshold.
- **`tests/test_measurement_gate.m`** (now 10 checks):
  - The baseline threshold is now 9.210 rather than 5.991.
  - T6 checks that the same `(y, S)` is rejected at 5.991 and admitted at 9.210, and that d2 equal to gamma is admitted.
  - T7 adds 4-D cases at 13.277.
  - T8 checks fail-closed behaviour for a bad gamma (G4).
  - T9 replays every row of `data/gate_vectors.csv`, as CVT-SRS-003 §8 requires.
  - T10 places innovations at 1000 evenly spaced chi-squared(m) quantiles of NIS, through a non-identity S. It requires the rejection fraction to equal 1 − confidence (± 0.2 %) for all four Appendix A entries for m = 2 and m = 4, at 95 % and 99 %.
- **`tests/test_kalman.m`** (now 6 checks): T5 (Doppler) and T6 (planar) go through `cvt_model` → `kalman_update` → `measurement_gate`. Each:
  - checks that the configured gamma is loaded;
  - places 1000 single-step measurements at evenly spaced chi-squared(m) quantiles of NIS under the step-1 S, and requires 1.0 % ± 0.2 % rejected;
  - requires that a measurement with 5.991 < d2 ≤ gamma is applied.

  These tests are deterministic and use no random numbers or tracking-error thresholds. The shipped gate gives 20.0 % (Doppler) and 5.0 % (planar) on them, far outside the tolerance. They replace an earlier draft of T5/T6 that asserted a 0.5 m tracking error on a sinusoidal stream, which was fragile (0.531 vs 0.5 m on the shipped gate) and did not resemble the campaign.

**Test results (local, GNU Octave 11.3.0):**

| Gate | `test_kalman` | `test_measurement_gate` |
|------|---------------|-------------------------|
| Fixed | 6/6 pass | 10/10 pass |
| Original | Fails at T5 (`doppler rejection rate 0.200, expected 0.01`) | Fails at T6 (`admit at gamma 9.210`) |

The original suites passed against the original gate.

I left `tests/test_results.txt` (the build-agent-04 record), the controlled documents and `docs/requirements.csv` unchanged.

## 7. Recommendations

1. **Release v2.4.2** with the gate fix through CCB, built from `release/v2.4` on build-agent-04, with the updated tests.
2. **Before the formal campaign, replay the recorded VAL-2026-09 streams on the fixed build** and score them exactly as the runner does. This is the only way to show the fix brings Doppler under 0.5 m (section 3a).
   - Expect rejection rates of about 1 % and no 10 % alerts.
   - At the same time, confirm with the validation-runner owner how `max_pos_error` is computed: window, norm and subsampling. The planar error levels are hard to reconcile with the configured R and Q.
3. **Then re-run the full campaign: Doppler and planar.** The fix also changes planar behaviour on v2.4, from 5 % rejection to 1 %, so the v2.4.1 planar passes do not carry over.
4. **Do not change CVT-VAL-002 on the basis of this investigation.** Nothing here shows the 0.5 m limit is wrong. If the replay in item 2 shows the fixed Doppler build still misses the limit, open a separate investigation; do not relax the limit.
5. **Correct the requirements trace.**
   - G3 was marked Verified on the strength of a test that could not detect a violation. Re-trace it to the new T6, T7 and T10.
   - Trace §8 / G5 to T9.
   - Trace the gated path in each mode to `test_kalman` T5 and T6.
   - Raise a nonconformance for G3 against v2.4.0 and v2.4.1.
6. **Process changes.**
   - Do not set test inputs equal to the value a parameter is meant to override.
   - Treat a change to a threshold table as untested until something exercises its consumer.
   - Make the gate's 10 % rejection alert block a campaign, or at least require sign-off before one proceeds.
   - Add an `active_mode` column to the summary workbook's by-build view, or cross-tab mode by build, so confounding is visible.
7. **Separate follow-up:** the scheduler's estimator-02 review and the /var/spool/cvt ticket are unrelated to this failure.
