"""Check the Python port against the MATLAB original on test_vectors.csv.

Runs kalman_update.m under Octave (``OCTAVE_CLI`` env var, else ``octave-cli`` on
PATH), runs kalman_filter.kalman_update on the same inputs, and fails if the maximum
absolute difference is not below 1e-9.

    python check_port.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from kalman_filter import kalman_update

TOL = 1e-9
HERE = Path(__file__).resolve().parent


def matlab_states() -> np.ndarray:
    octave = os.environ.get("OCTAVE_CLI", "octave-cli")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "X.csv"
        script = (
            "m = jsondecode(fileread('model.json'));"
            "model = struct('F', m.F, 'Q', m.Q, 'H', m.H, 'R', m.R, 'x0', m.x0(:), 'P0', m.P0);"
            "Z = csvread('test_vectors.csv', 1, 0);"
            f"dlmwrite('{out.as_posix()}', kalman_update(Z, model), 'precision', 17);"
        )
        subprocess.run([octave, "--norc", "--quiet", "--eval", script], cwd=HERE, check=True)
        return np.loadtxt(out, delimiter=",")


def main() -> int:
    m = json.loads((HERE / "model.json").read_text(encoding="utf-8"))
    model = {k: np.asarray(v, dtype=float) for k, v in m.items()}
    Z = np.loadtxt(HERE / "test_vectors.csv", delimiter=",", skiprows=1)

    X = kalman_update(Z, model)
    Xm = matlab_states()
    if X.shape != Xm.shape:
        print(f"FAIL: shape {X.shape} vs MATLAB {Xm.shape}")
        return 1
    err = float(np.max(np.abs(X - Xm)))
    ok = err < TOL
    print(f"{'PASS' if ok else 'FAIL'}: max abs error vs MATLAB = {err:.3g} over {len(Z)} vectors (tol {TOL:g})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
