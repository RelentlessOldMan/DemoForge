"""Reference Python port of kalman_update (calibration solution).

Mirrors input/kalman_update.m exactly — same algorithm, same operation order,
same mrdivide-as-solve for the gain — so it reproduces the MATLAB reference output
to within floating-point rounding. Used to prove the demo is solvable and the
tolerance is realistic; it is NOT staged into the agent's working copy (producing
this file is the job).
"""

from __future__ import annotations

import numpy as np


def kalman_update(Z, model):
    F = np.asarray(model["F"], dtype=float)
    Q = np.asarray(model["Q"], dtype=float)
    H = np.asarray(model["H"], dtype=float)
    R = np.asarray(model["R"], dtype=float)
    x = np.asarray(model["x0"], dtype=float).reshape(-1).copy()
    P = np.asarray(model["P0"], dtype=float).copy()

    Z = np.asarray(Z, dtype=float)
    N = Z.shape[0]
    n = x.shape[0]
    X = np.zeros((N, n))
    I = np.eye(n)
    Ht = H.T
    Ft = F.T

    for k in range(N):
        z = Z[k]

        # --- predict ---
        x = F @ x
        P = F @ P @ Ft + Q

        # --- update ---
        y = z - H @ x
        S = H @ P @ Ht + R
        # MATLAB's (P*H')/S is mrdivide: solve K @ S = P@Ht for K.
        K = np.linalg.solve(S.T, (P @ Ht).T).T
        x = x + K @ y
        P = (I - K @ H) @ P

        X[k] = x

    return X
