# ClaudeDemoKit story bible

One fictional engineering project runs through all ten demos. Every fact a demo's
inputs state (names, versions, dates, numbers, people) must agree with this file.
It is for authors, never staged to the agent. If a demo needs a fact that isn't
here, add it here first.

## The product

**CVT** (Constant-Velocity Tracker) is the estimator software that tracks a moving
object from noisy measurements. It ships as numbered **estimator releases**
(`v2.1`, `v2.2.0` …). There is no separate "firmware": every version number is an
estimator release. Releases are built by `build-agent-04` from the
`release/vX.Y` branch.

- State `x = [px; py; vx; vy]`, 2-D, constant-velocity model, dt = 1.
- Defaults (`model.json`): Q = 0.01·I4, R = 0.25·I2, H = [I2 0], x0 = 0, P0 = I4.
- Reference algorithm: `kalman_update(Z, model)` in MATLAB/Octave, returns N×4.
- Python port: `kalman_filter.py` (`kalman_update(Z, model)` with NumPy).

## Controlling documents

| Document | Rev | Date | Content |
|---|---|---|---|
| CVT-EST-001 *State Estimator Specification* | B | 2025-11-03 | §3 interface, §4 recursion, §5 R1–R5, §6 acceptance (< 1e-6 vs reference) |
| CVT-EST-001 | C | 2026-03-02 | adds **R6**: non-finite or malformed measurements shall be rejected and reported, never propagated into the state (raised by the 2026-02-18 incident) |
| CVT-SRS-003 *Estimator Software Requirements* (PDF) | B | 2026-04-20 | adds §7.3 measurement gate for v2.3: NIS gate at 95 %, m = 2, so γ = 5.991, **fixed in the spec** |
| CVT-SRS-003 | C | 2026-09-08 | §7.3 revised for v2.4: γ is **configuration**, the χ² critical value for the configured confidence and the measurement dimension m of the active mode; default confidence 99 %. Appendix A table. Fail-closed boundary rules G-BC-1/2. Requirements G1–G5 |
| CVT-VAL-002 *Validation Plan* | A | 2026-05-12 | acceptance per campaign: max position error ≤ 0.5 m per run, pass rate ≥ 0.95, runtime ≤ 50 ms per run |

Demos 1 and 8 predate Rev C and use **CVT-EST-001 Rev B** (R1–R5). Demos 9 and 10 use
**Rev C** (R1–R6). Demo 7 implements §7.3 from **CVT-SRS-003 Rev C**. Demo 10 ships
both documents at Rev C.

## Release history

| Version | Date | Change |
|---|---|---|
| v2.1.0 | 2025-11-17 | First release built on CVT-EST-001 Rev B. Scalar-loop MATLAB update |
| v2.2.0 | 2026-03-11 | Vectorized Kalman update (the work of demo 2); Python port added (demo 3). Does **not** yet implement R6, although EST-001 Rev C (2026-03-02) requires it |
| v2.3.0 | 2026-05-30 | R6 implemented by the new measurement gate (SRS-003 Rev B §7.3, γ = 5.991 fixed; non-finite input rejected). **Also a regression:** the update re-used last step's innovation covariance, so the estimate error rose about 200× (still small in metres, but it fails the nightly 1e-7 agreement check) |
| v2.3.1 | 2026-06-09 | Packaging only |
| v2.3.2 | 2026-07-14 | Fixes the v2.3.0 covariance regression |
| v2.4.0 | 2026-09-21 | SRS-003 Rev C: new **Doppler mode** (sensor also measures velocity, so H = I4, m = 4); gate confidence moved to configuration at 99 %. CCB-2026-114 |
| v2.4.1 | 2026-09-25 | Config-file fix: `estimator_config.json` gained the per-mode χ² table. **The gate code itself was never changed** and still uses the inlined 5.991 |

## The validation system

- **Nightly regression** (`cvt-regression` suite): test IDs **1800–1850** (51
  cases), each a 1500-vector measurement stream, scored by `max_abs_error` against
  the reference filter (pass < 1e-7). Batches are named `val-YYYY-MM-DD` and run at
  02:00 UTC.
- **Validation campaigns** (CVT-VAL-002): run IDs **VR-xxxx**, scored in metres
  against ground truth. Campaigns are named `VAL-YYYY-MM`.
- **Workers:** `estimator-01` and `estimator-02` until 2026-08; `estimator-03`
  added 2026-08-03. Odd test IDs go to estimator-01, even to estimator-02.
  **estimator-02 is older hardware and runs 15–20 % slower.** That is known, harmless
  and inside every limit. It is the standing red herring.
- Validation storage `/var/validation` has a 20 G quota.

## Incidents, in order (one per demo, no two demos discover the same thing)

| When | What | Demo |
|---|---|---|
| 2026-02-18 02:15 UTC | Batch `val-2026-02-18`: `/var/validation` hit 100 %; the data export for **test 1847** wrote 1180 of 1500 rows and marked the file READY anyway; the estimator read a truncated last row as NaN; test 1847 failed with a non-finite result. Fix: export verifies row count; R6 added to EST-001 Rev C | 4 |
| 2026-05-20 … 05-27 campaign VAL-2026-05 (acceptance of the v2.3.0 release candidate, workbook) | The workbook's limit cell read **5** m instead of **0.5** m, so a campaign that should have been REJECT showed ACCEPT and v2.3.0 shipped. The failing runs are the `maneuver` scenario runs (high-acceleration profiles a constant-velocity model can't follow): 0.6–1.1 m. It is a scenario effect, not a version effect. The v2.3.0 covariance regression is far too small in metres to show here | 5 |
| 2026-06-01 … 06-30 nightly data | The v2.3.0 covariance regression: from 05-31 (first nightly on v2.3.0) `max_abs_error` jumps from about 3e-10 to about 7e-8, with roughly 1 in 5 tests failing the 1e-7 check, on every worker. estimator-02's slowness is the decoy | 6 |
| 2026-09-26 VAL-2026-09 (v2.4.1, Doppler mode's first campaign) | Doppler-mode runs fail: the gate still inlines γ = 5.991 (95 %, m = 2), but Doppler mode needs γ(99 %, m = 4) = 13.277, so the gate drops about 1 in 5 good measurements and the track drifts. Planar runs pass (they are gated at 5.991 instead of 9.210, slightly over-rejecting but still inside limits). No test covers the gate with m ≠ 2 or with γ taken from config | 10 |

Demos 1, 2, 3, 7, 8 and 9 are build or verification tasks, not incidents. Demo 8's
planted defect is in a **pre-release** `kalman_update.m` that ignores `model.x0` and
`model.P0`; it was caught before release. Demo 9 audits the **v2.2.0** code against
EST-001 Rev C. R6 is required there but is not implemented in the audited code
revision, and R3's initialization has no test.

## People

- Priya Raman: estimator lead, owns CVT-EST-001.
- Dmitri Volkov: validation engineer, wrote the handover notes in demo 10.
- Change Control Board ticket: CCB-2026-114 (v2.4.0 scope).

## Fixed numbers

| Quantity | Value |
|---|---|
| χ² critical values, 95 % / 99 % | m=1: 3.841 / 6.635; m=2: 5.991 / 9.210; m=3: 7.815 / 11.345; m=4: 9.488 / 13.277 |
| Nightly pass | max_abs_error < 1e-7 |
| Healthy nightly error | about 3e-10 |
| v2.3.0 nightly error | about 7e-8 (about 200×) |
| Measurement streams | 1500 vectors |
| Generator seeds | the demo's own incident date as YYYYMMDD |
