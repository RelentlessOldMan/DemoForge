`kalman_update.m` is the measurement-update routine from our CVT estimator as it
shipped in v2.1.0: a constant-velocity Kalman filter that runs over a stream of
position measurements. Its results are correct, but it's slow, and it dominates the
run time of our validation batches. Production streams are much longer than the
sample here; `test_vectors.csv` is a representative 1500-vector stream and
`model.json` holds the filter model we run it with.

For v2.2.0 I'd like a faster version as `kalman_update_fast.m`, a drop-in
replacement with the same signature, `X = kalman_update_fast(Z, model)`, that works
for whatever model it is given. It must not change the numbers: we need it to agree
with the current routine to within 1e-9 (maximum absolute error).

Please leave a benchmark and equivalence check that compares the two on the sample,
as `benchmark_kalman_update.m`, and a short write-up in `OPTIMIZATION.md` with the
original and optimized runtimes, the speedup, the number of vectors, the maximum
absolute error you measured, and what you changed.
