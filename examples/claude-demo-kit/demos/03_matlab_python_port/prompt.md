For v2.2.0 we're shipping a Python version of the estimator so the data team can run
it alongside their NumPy/pandas tooling. Please port `kalman_update.m` to Python as
`kalman_filter.py`, exposing

    def kalman_update(Z, model) -> X

where `Z` is an `(N, 2)` NumPy array of measurements, `model` is a dict with the keys
of `model.json` (`F, Q, H, R, x0, P0`), each value converted with `np.asarray`, and `X`
is the `(N, 4)` array of posterior state estimates, one row per measurement.

The port has to agree with the MATLAB version to a maximum absolute error below 1e-9.
`test_vectors.csv` is a recorded measurement stream to check it on. Leave
`kalman_filter.py` and whatever check you used to show the agreement in this folder.
