# kalman_update optimization (CVT estimator v2.2.0)

`kalman_update_fast.m` is a drop-in replacement for `kalman_update.m` (v2.1.0):
same signature `X = kalman_update_fast(Z, model)`, same recursion, and output
that is **bit-identical** to the original's, not merely within tolerance. An
optional third argument, `kalman_update_fast(Z, model, false)`, turns off the
gain-cycle shortcut for benchmarking; the output is the same either way.

## Results

Every figure below comes from a single run of `benchmark_kalman_update.m`
(GNU Octave 11.3.0, Windows 11). MATLAB was not available on the test machine.
The script should run unchanged in MATLAB, but it has not been run there, and
absolute times would differ.

### Sample (`test_vectors.csv` + `model.json`)

| | Runtime (median of 5) | min – max | Speedup |
|---|---|---|---|
| Original (`kalman_update`) | 4.477 s | 4.470 – 4.524 s | — |
| Optimized, as shipped | 0.146 s | 0.144 – 0.147 s | **30.7x** |
| Optimized, gain-cycle shortcut off (`kalman_update_fast(Z, model, false)`) | 0.477 s | 0.473 – 0.480 s | **9.4x** |

**Read these two speedups together.** 9.4x is what the exact-order arithmetic
alone gives. This is the speed every step runs at when the covariance never
repeats. The rest of the 30.7x comes from the gain-cycle shortcut (change 2
below). On this model the covariance stops changing at step 59, so the other
1441 of the 1500 steps skip the covariance computation.
How much a model gains from the shortcut depends on how soon its covariance
repeats and how long the stream is. Expect something between the two figures,
and quote 9.4x for a model whose covariance has not been checked.

- Vectors: **1500** (state n = 4, measurement m = 2)
- Maximum absolute error: **0** (bit-identical) with the shortcut on and off;
  largest |x| reached 1.50e3
- The three routines were timed interleaved. The spread across the 5 runs was
  about 1% for each, so the sample timings were not affected by machine load.

### Long streams (100,000 vectors each, simulated from the CV model)

| Stream | Max abs error | Bit-identical | Largest \|x\| | Original | Optimized | Speedup |
|---|---|---|---|---|---|---|
| `model.json` (dt = 1) | 0 | yes | 2.71e6 (velocity 64.3) | 443.7 s | 8.51 s | 52x\* |
| dt = 0.1, DWNA Q, R = [0.25 0.10; 0.10 0.16], x0 ≠ 0 | 0 | yes | 3.50e5 (velocity 93.8) | 300.2 s | 8.55 s | 35x |

\* **Machine-load variance.** The original routine does the same work per step
on both streams, yet took 443.7 s on stream 1 and 300.2 s on stream 2. Both
are single runs. Stream 1's original run was slowed by machine load, and its
52x is inflated accordingly. At stream 2's per-step rate, stream 1 would be
about 35x. The optimized times (8.51 s and 8.55 s) agree, so they look
unaffected. The long-stream timings are each a single run; treat them as
indicative, and use the interleaved sample timings above for speedup figures.

### Other models

Four random models with m = 2 and state sizes n = 2, 3, 4, 6 (1500 vectors each)
are also bit-identical (maximum absolute error 0).

The benchmark now fails unless **every** check is bit-identical. Because the
output reproduces the original's bits, the 1e-9 absolute tolerance holds for any
stream length and any |x|.

## What changed

1. **Exact-order vectorized arithmetic.** The original ran every product
   through scalar loops (`s = 0; s = s + A(i,p)*B(p,j)`). The new version
   computes each product a whole matrix at a time, as
   `C = 0; for p = 1:inner, C = C + A(:,p) .* B(p,:); end`. This performs the
   same multiplies and the same additions, in the same order, from the same
   starting value, so every element is rounded identically. The built-in
   matrix multiply (`A*B`) is deliberately **not** used: BLAS adds the terms in
   a different order, which gives last-bit differences that grow with |x|. The
   loops are written inline because Octave's function-call overhead would
   otherwise dominate.
2. **Periodic-gain shortcut (exact).** The covariance recursion (P, S, K) does
   not depend on the measurements: each gain and the next posterior P are a
   deterministic function of the previous posterior P. After each step, the
   bit pattern of P is compared with the posteriors of the last 64 steps.
   Once P_k equals P_{k-L} bit-for-bit, every later gain is exactly a
   repetition of the last L gains. The remaining steps then compute only the
   state update, using the same operations in the same order. A separate
   probe, not part of the benchmark, measured the onset: `model.json` reaches
   a fixed point (L = 1) at step 59, and the dt = 0.1 model reaches a cycle of
   length 16 at step 153.
3. **Hoisted loop invariants and row-at-a-time I/O.** `F'`, `H'`, `eye(n)`,
   the zero matrices, and the transposed measurement block are built once,
   and each output row is written in one assignment.

## Behavior notes

- **No covariance cycle.** If the covariance never repeats within a 64-step
  window (for example, the random n = 6 model, which in the same probe did not
  settle within 3000 steps), every step is computed in full with the exact-order
  arithmetic. The output is still bit-identical, but the speedup is that of
  the shortcut-off row above (9.4x on the sample), not 30.7x.
- **Platform assumption.** Bit-identity relies on `C + A .* B` being evaluated
  as a separately rounded multiply and add, never as a fused multiply-add.
  That holds in Octave and was verified here. MATLAB has not been verified,
  so run the benchmark there before relying on it.
- **Measurement dimension.** The original only works for m = 2 (`inv2x2`).
  For any other m, the fast version computes `K = P H' / S`. There is no
  v2.1.0 reference to compare that path against; it has only been smoke-tested
  with m = 1 and m = 3.
- `x0` is accepted as a row or column vector, as in the original. Columns of
  `Z` beyond the first m are ignored, as before.
