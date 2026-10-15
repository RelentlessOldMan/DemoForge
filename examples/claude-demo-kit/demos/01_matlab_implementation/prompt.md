Priya has released the estimator spec for the Constant-Velocity Tracker,
CVT-EST-001 Rev B (`kalman_filter_spec.md`). Please implement it in MATLAB/Octave as
`kalman_update.m`, together with the runnable test the spec asks for, as
`test_kalman_update.m`. We'll run the test in CI with `octave --eval test_kalman_update`,
so it should stop with an error if anything is wrong.

`model.json` has the model constants and `test_vectors.csv` is a recorded measurement
stream. Leave both files you write in this folder.
