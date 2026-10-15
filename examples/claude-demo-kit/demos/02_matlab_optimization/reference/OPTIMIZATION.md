# kalman_update optimization (v2.2.0)

`kalman_update_fast.m` is a drop-in replacement for `kalman_update.m`:
same signature, same recursion, same operation order, any model whose
measurement covariance S is invertible.

## Results

Measured with `benchmark_kalman_update.m` on `test_vectors.csv` (1500 vectors)
with `model.json`, Octave 11.3:

| | runtime |
|---|---|
| original `kalman_update` | 4783 ms |
| `kalman_update_fast` (median of 20) | 52 ms |
| **speedup** | **≈ 92×** |

Maximum absolute error between the two outputs over all 1500 × 4 states:
**2.3e-13** (requirement: < 1e-9).

## What changed

- The hand-written element-by-element helpers (`matmul`, `matvec`, `madd`,
  `transpose_m`, `inv2x2`, ...) are replaced by Octave's native matrix
  operations, so each step is a handful of BLAS calls instead of hundreds of
  interpreted scalar operations.
- The gain is computed as `K = (P*H') / S` (a solve) instead of multiplying
  by the closed-form 2×2 inverse. This also lifts the old restriction that the
  measurement dimension be 2.
- `F'`, `H'` and the identity are formed once, outside the loop; the
  measurement row is taken as a slice instead of copied element by element.

The filter is still a loop over samples: each step needs the previous `x` and
`P`, so the recursion itself cannot be vectorized across time. The remaining
differences (around 1e-13) come from the solve vs. the explicit inverse and
from BLAS summation order.
