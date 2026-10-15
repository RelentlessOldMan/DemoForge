# Changelog: CVT estimator

Releases are built by build-agent-04 from the `release/vX.Y` branch.

## v2.4.1 (2026-09-25)

- Configuration fix: `estimator_config.json` gains the per-mode gate threshold table
  (`gate.gamma`), one chi-squared critical value per measurement mode at
  `gate.confidence`, per CVT-SRS-003 Rev C Appendix A. No code changes.

## v2.4.0 (2026-09-21)

- New **Doppler mode** (CVT-SRS-003 Rev C): the sensor also measures velocity, so
  H = I4 and the measurement dimension is 4. Selected with `active_mode` in
  `estimator_config.json`; planar mode is unchanged.
- Gate confidence moved to configuration (`gate.confidence`), set to 99 %.
- `cvt_model.m` builds the model struct for a mode from configuration.
- Scope approved under CCB-2026-114.

## v2.3.2 (2026-07-14)

- Fixes the covariance regression introduced in v2.3.0: the update re-used the
  previous step's innovation covariance, raising the nightly `max_abs_error` about
  200x (around 7e-8 against a 1e-7 pass limit). `S` is now formed from the current
  predicted covariance every step.

## v2.3.1 (2026-06-09)

- Packaging only.

## v2.3.0 (2026-05-30)

- Measurement validation gate `measurement_gate.m` (CVT-SRS-003 Rev B §7.3:
  NIS gate, threshold 5.991). Implements CVT-EST-001 R6: non-finite measurements are
  rejected, never propagated into the state.
- `kalman_update` screens every measurement through the gate when a threshold is
  configured.

## v2.2.0 (2026-03-11)

- Vectorized Kalman update for the validation workload.
- Python port `src/kalman_filter.py` added for offline analysis.

## v2.1.0 (2025-11-17)

- First release built on CVT-EST-001 Rev B. Scalar-loop MATLAB update.
