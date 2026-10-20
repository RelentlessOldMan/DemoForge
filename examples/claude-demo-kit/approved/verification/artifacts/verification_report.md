# Verification report: `kalman_update.m` against CVT-EST-001 Rev B

## Conclusion

**Defect found. Not ready for v2.1.0.**

`kalman_update.m` lines 18–19 initialise the filter with hard-coded values:

```matlab
x = zeros(n, 1);   % should be model.x0
P = eye(n);        % should be model.P0
```

§4 says "Initialise `x = x0`, `P = P0`", and §2.3 says the constants must come from
`model` and must not be hard-coded. The function never reads `model.x0` or `model.P0`,
which violates **R3**.

The current `model.json` happens to set `x0 = [0 0 0 0]` and `P0 = eye(4)`, which are
exactly the hard-coded values. So on the shipped data the output matches the reference
recursion exactly (error 0), and the §6 acceptance criterion passes. The defect shows
up as soon as `model.json` changes x0 or P0. With perturbed values the maximum state
error is 0.61 (x0) and 0.157 (P0), against a tolerance of 1e-6.

Suggested fix for the author: `x = model.x0(:); P = model.P0;`. I checked this fix on
a scratch copy only (the delivered `kalman_update.m` is unchanged), and the new test
passes 16/16 on it.

The rest of the implementation matches §4: predict and update order, the gain computed
with `/ S` rather than `inv(S)`, the `(I − K H) P` covariance update, F/Q/H/R taken
from `model`, N×4 output in input order, deterministic, and nothing printed.

## What the existing test (`test_kalman_existing.m`) does and doesn't establish

It **does** establish:
- the output shape is N×4 on `test_vectors.csv` (R2)
- two calls give identical output (R4)
- the position estimate stays within 5.0 of the measurements (a rough divergence check)

It **does not** establish:
- **Correctness of the recursion (R3, §6).** Nothing compares the output to the §4
  computation. Staying within 5.0 is a very loose bound, so many incorrect filters
  would pass.
- **That constants come from `model`.** The test builds the model by hand, copying
  the `model.json` values, instead of reading `model.json` as §2.3 requires. It only
  ever uses that one model, and its x0/P0 equal the hard-coded defaults, so it cannot
  detect the defect above. It passes on the defective code.
- R1 (the signature), causality or input order, and purity (§3).

## What `test_kalman.m` covers

Run with `octave-cli test_kalman.m`. It prints PASS/FAIL for each check and exits 1
if any check fails.

| Req | Check |
|-----|-------|
| input | `test_vectors.csv` is N×2, N > 0 |
| R1 | `kalman_update` has 2 inputs and 1 output |
| R2 | N×4 output on the full stream; 1×4 for a single measurement; the first 100 rows are the same whether the input has 100 or 200 rows (order and causality) |
| R3 / §6 | Output matches an independent transcription of the §4 recursion to < 1e-6, using constants read from `model.json` with `jsondecode` |
| R3 | Same comparison with each of x0, P0, F, Q, R, H perturbed in turn, then all of them together. This catches any constant that is hard-coded rather than taken from `model` |
| R3 | Position estimate stays within 5.0 of the measurements (no divergence) |
| R4 | Repeated calls give identical output |
| §3 | The function prints nothing (checked with `evalc`) |

Results:
- **Shipped `kalman_update.m`:** 13/16 pass, exit 1. The failures are the x0, P0 and
  all-together perturbation checks.
- **Copy with lines 18–19 fixed:** 16/16 pass, exit 0. This confirms the test accepts
  an implementation that meets the spec.

The perturbed models are well-conditioned, so any faithful implementation of §4 agrees
with the reference far inside 1e-6.

The test does not cover:
- the §3 rules against reading files or using globals; these were checked by reading
  the code, and the function does neither
- input validation, which the spec does not require
