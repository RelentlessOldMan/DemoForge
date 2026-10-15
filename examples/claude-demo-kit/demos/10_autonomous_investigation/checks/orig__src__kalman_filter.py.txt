"""Python port of kalman_update for offline analysis.

Same recursion and operation order as src/kalman_update.m, generic over the
measurement model (any H with m rows). The measurement gate is not ported: this
module is for replaying recorded streams in notebooks and is not part of the
validated build (see README).
"""

from __future__ import annotations

import numpy as np


def kalman_update(Z, model):
    """Return the N-by-n posterior state estimates for measurements Z (N-by-m)."""
    F = np.asarray(model["F"], dtype=float)
    Q = np.asarray(model["Q"], dtype=float)
    H = np.atleast_2d(np.asarray(model["H"], dtype=float))
    R = np.atleast_2d(np.asarray(model["R"], dtype=float))
    x = np.asarray(model["x0"], dtype=float).reshape(-1).copy()
    P = np.asarray(model["P0"], dtype=float).copy()

    Z = np.atleast_2d(np.asarray(Z, dtype=float))
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
