# Verification of `kalman_update.m` against CVT-EST-001 Rev B

## Conclusion

**Defect found. Not ready for v2.1.0.** `kalman_update` ignores the initial state
and covariance in the model. It always starts from `x = zeros(4,1)` and `P = eye(4)`
(`kalman_update.m` lines 18–19) instead of `x = model.x0`, `P = model.P0` as §4
requires. This violates **R3** (the §4 recursion using the constants from `model`).
R1, R2 and R4 hold.

## What the existing test establishes

`test_kalman_existing.m` checks output shape, determinism, and that the position
estimate stays within 5 m of the measurements, all on the default model. That model
has `x0 = 0` and `P0 = I`, which is exactly the hard-coded start, so the defect cannot
show. The test never compares against the §4 recursion, so the 5 m tracking bound
would also accept a filter with a missing `Q`, a wrong covariance update or other
recursion errors. It never varies any model field, so it can't show whether `Q`, `R`,
`F`, `x0` or `P0` are read at all.

## What `test_kalman.m` adds

An independent transcription of the §4 recursion is used as an oracle, with the §6
acceptance limit (max abs error < 1e-6):

| Case | Requirement |
|---|---|
| shape for N = 1500 and N = 1, finite output | R1, R2 |
| repeated calls identical | R4 |
| default model vs oracle | R3, §6 |
| non-zero `x0`; non-identity `P0`; confident `x0` with `P0 = 1e-6·I` | R3 (initialisation) |
| first estimate with tiny `P0` stays on `F·x0` (analytic, oracle-free) | R3 |
| different `Q`, `R`, and `F` (dt = 0.5) vs oracle | R3 (constants from `model`) |
| tracking within 5 m (kept from the old test) | sanity |

## Evidence

`octave-cli test_kalman.m` against the provided code:

```
  ok  shape (N = 1500 and N = 1)
  ok  deterministic
  ok  default model                      max err 0.00e+00
error: non-zero x0: max |X - oracle| = 3.87 (CVT-EST-001 §6 limit 1e-6)
```

It matches the oracle exactly on the default model, which is why the existing test
passes, and fails as soon as `x0` is non-zero. With `x0 = [10; 5; 1; -1]` and
`P0 = 1e-6·I`, the first estimate is `[0.28 0.36 0.14 0.18]`, the same as with
`x0 = 0`, where about `F·x0 = [11 4 1 -1]` is required. Setting
`P0 = diag([100 100 4 4])` changes the output by exactly 0, so `model.P0` is never
read either. With lines 18–19 changed to read `model.x0` and `model.P0` in a scratch
copy, every case in `test_kalman.m` passes.

## Recommendation

Initialise with `x = model.x0(:); P = model.P0;` and keep `test_kalman.m` as the R5
test so initialisation stays covered.
