"""Constant-velocity Kalman filter over a batch of measurements.

Python port of kalman_update.m.  Requires NumPy and SciPy (for the
triangular/Cholesky/LU solves that mirror MATLAB's mrdivide).
"""

import numpy as np
import scipy.linalg as sla


def _mrdivide(B, A):
    """B / A for square A, choosing the factorization the way MATLAB/Octave do.

    B / A is solved as (A' \\ B')'.  MATLAB and Octave inspect A' first:
    triangular -> triangular substitution; exactly symmetric with a positive
    diagonal -> Cholesky (LU if that fails); otherwise LU.  When S is badly
    conditioned those factorizations round differently, and the difference
    is amplified by cond(S).  Always using LU (np.linalg.solve) disagreed
    with Octave by up to 3e-2 on cond(S) ~ 1e10 cases, so we follow the same
    choices here.
    """
    At, Bt = A.T, B.T
    if np.array_equal(At, np.triu(At)):
        return sla.solve_triangular(At, Bt, lower=False, check_finite=False).T
    if np.array_equal(At, np.tril(At)):
        return sla.solve_triangular(At, Bt, lower=True, check_finite=False).T
    if np.array_equal(At, A) and np.all(np.diag(At) > 0):
        try:
            c = sla.cho_factor(At, lower=False, check_finite=False)
        except np.linalg.LinAlgError:
            pass
        else:
            return sla.cho_solve(c, Bt, check_finite=False).T
    return sla.lu_solve(sla.lu_factor(At, check_finite=False), Bt, check_finite=False).T


def kalman_update(Z, model):
    """Run the Kalman filter over every measurement in Z.

    Z      (N, m) array; row k is the measurement z_k.
    model  dict with keys F (n, n), Q (n, n), H (m, n), R (m, m),
           x0 (n,) or (n, 1), P0 (n, n).
    Returns X, an (N, n) array; row k is the posterior state estimate
    after step k.

    Each step predicts with the constant-velocity model, then applies the
    measurement update:
        x = F x;            P = F P F' + Q
        y = z - H x;        S = H P H' + R
        K = P H' / S;       x = x + K y;   P = (I - K H) P
    """
    return _kalman(Z, model)


def _kalman(Z, model, predicted_P_hook=None):
    """kalman_update with a test hook.

    predicted_P_hook(P) -> P, if given, is applied to the predicted
    covariance each step; check_agreement.py uses it to inject rounding-
    sized perturbations and to observe S.
    """
    x = np.asarray(model["x0"], dtype=float).reshape(-1)
    n = x.size
    F = np.asarray(model["F"], dtype=float).reshape(n, n)
    Q = np.asarray(model["Q"], dtype=float).reshape(n, n)
    P = np.asarray(model["P0"], dtype=float).reshape(n, n)
    H = np.asarray(model["H"], dtype=float).reshape(-1, n)
    m = H.shape[0]
    R = np.asarray(model["R"], dtype=float).reshape(m, m)

    # A 1-D Z is a stream of scalar measurements (m == 1), not one row.
    Z = np.asarray(Z, dtype=float).reshape(-1, m)
    N = Z.shape[0]
    X = np.zeros((N, n))
    I = np.eye(n)

    for k in range(N):
        z = Z[k, :]

        # --- predict ---
        x = F @ x
        P = F @ P @ F.T + Q
        if predicted_P_hook is not None:
            P = predicted_P_hook(P)

        # --- update ---
        y = z - H @ x
        S = H @ P @ H.T + R
        K = _mrdivide(P @ H.T, S)
        x = x + K @ y
        P = (I - K @ H) @ P

        X[k, :] = x

    return X
