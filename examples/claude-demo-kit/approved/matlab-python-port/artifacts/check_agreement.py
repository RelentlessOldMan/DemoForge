"""Compare kalman_filter.kalman_update against the MATLAB/Octave reference.

Workflow:
    python generate_cases.py            # only if cases/ needs regenerating
    make_reference                      # in MATLAB, or:
    octave --no-gui --quiet --eval make_reference
    python check_agreement.py

For every cases/<name>/ it loads model.json and z.csv, runs the Python
port, and compares against ref.csv (written by kalman_update.m).

Gate (per element):  |X_py - X_ref| <= 1e-9 * max(1, |X_ref|)
NaNs must appear in the same places in both outputs.

Report-only cases.  A case whose model.json has "gate": "report" is not held
to the 1e-9 tolerance; instead it fails if its error exceeds 10x the rounding
envelope (below).  The list is fixed in generate_cases.py (REPORT_ONLY) and
is never derived at run time.  Currently: 10, 11, 12 (badly conditioned S).

Rounding envelope.  Two correct implementations (NumPy/OpenBLAS vs
MATLAB/MKL) round matrix products differently, by about 1 ulp.  For each
case the check re-runs the port several times with every element of the
predicted covariance perturbed by up to 1 ulp per step, and records how far
the output moves: the disagreement to expect from rounding alone.  It is
printed for every case, and is the pass bound for report-only cases.

Columns:
    cond(S)    largest 2-norm condition number of the innovation covariance
    max_abs    max |X_py - X_ref|
    err/tol    max over elements of |X_py - X_ref| / (1e-9 * max(1, |X_ref|))
               (gate: <= 1)
    env/tol    the same ratio for the 1-ulp rounding envelope
    err/env    err/tol divided by env/tol; >> 1 means the disagreement is
               larger than rounding explains (REPORT cases fail above 10)

Exit status is non-zero if any case fails.
"""

import json
import sys
import zlib
from pathlib import Path

import numpy as np

from kalman_filter import _kalman, kalman_update

TOL = 1e-9
ENVELOPE_TRIALS = 4
ENVELOPE_FACTOR = 10  # report-only cases fail if err > this * envelope
EPS = np.finfo(float).eps
HERE = Path(__file__).resolve().parent


MATRIX_KEYS = ("F", "Q", "H", "R", "x0", "P0")


def load_case(path):
    """Return (model dict of arrays, report_only flag) from model.json."""
    raw = json.loads(path.read_text())
    gate = raw.get("gate", "tolerance")
    if gate not in ("tolerance", "report"):
        raise ValueError(f"{path}: unknown gate {gate!r}")
    return {k: np.asarray(raw[k]) for k in MATRIX_KEYS}, gate == "report"


def scaled_err(X, Y, ref):
    """Per-element |X - Y| / (TOL * max(1, |ref|)); NaN in both counts as 0."""
    both_nan = np.isnan(X) & np.isnan(Y)
    err = np.abs(X - Y) / (TOL * np.maximum(1.0, np.abs(ref)))
    err = np.where(both_nan, 0.0, err)
    return np.where(np.isnan(X) != np.isnan(Y), np.inf, err)


def max_cond_S(Z, model):
    """Largest cond(S) seen while filtering."""
    n = model["x0"].size
    H = model["H"].reshape(-1, n)
    R = model["R"].reshape(H.shape[0], -1)
    worst = [0.0]

    def hook(P):
        S = H @ P @ H.T + R
        if np.all(np.isfinite(S)):
            worst[0] = max(worst[0], np.linalg.cond(S))
        return P

    _kalman(Z, model, hook)
    return worst[0]


def rounding_envelope(Z, model, X, ref, seed):
    """Max scaled deviation of the port's output under 1-ulp perturbations."""
    rng = np.random.default_rng(seed)

    def hook(P):
        return P * (1 + EPS * rng.uniform(-1, 1, P.shape))

    env = 0.0
    for _ in range(ENVELOPE_TRIALS):
        d = scaled_err(_kalman(Z, model, hook), X, ref)
        env = max(env, float(np.max(d[np.isfinite(d)], initial=0.0)))
    return env


def main():
    cases = sorted(p for p in (HERE / "cases").iterdir() if p.is_dir())
    head = (f"{'case':30s} {'N':>6s} {'n':>2s} {'m':>2s} {'cond(S)':>8s} {'max_abs':>9s}"
            f" {'err/tol':>9s} {'env/tol':>9s} {'err/env':>8s}  result")
    print(head)
    all_ok = True
    reported = []
    for c in cases:
        model, report_only = load_case(c / "model.json")
        Z = np.loadtxt(c / "z.csv", delimiter=",", ndmin=2)
        ref = np.loadtxt(c / "ref.csv", delimiter=",", ndmin=2)
        X = kalman_update(Z, model)
        n = model["x0"].size
        m = model["H"].size // n
        if X.shape != ref.shape:
            print(f"{c.name:30s} shape mismatch: python {X.shape} vs ref {ref.shape}  FAIL")
            all_ok = False
            continue

        nan_mismatch = int((np.isnan(X) != np.isnan(ref)).sum())
        nan_rows = int(np.isnan(ref).any(axis=1).sum())
        fin = np.isfinite(X) & np.isfinite(ref)
        max_abs = float(np.abs(X - ref)[fin].max(initial=0.0))
        err = float(scaled_err(X, ref, ref).max())
        env = rounding_envelope(Z, model, X, ref, zlib.crc32(c.name.encode()))

        if nan_mismatch:
            result = "FAIL"
        elif report_only:
            reported.append(c.name)
            result = ("REPORT" if err <= ENVELOPE_FACTOR * env
                      else "FAIL (outside envelope)")
        else:
            result = "PASS" if err <= 1.0 else "FAIL"
        all_ok &= not result.startswith("FAIL")

        ratio = f"{err / env:8.1f}" if env > 0 else f"{'-':>8s}"
        note = f"  ({nan_rows} NaN rows in ref, {nan_mismatch} NaN mismatches)" if nan_rows or nan_mismatch else ""
        print(f"{c.name:30s} {X.shape[0]:6d} {n:2d} {m:2d} {max_cond_S(Z, model):8.1e} {max_abs:9.2e}"
              f" {err:9.2e} {env:9.2e} {ratio}  {result}{note}")

    print()
    if reported:
        print(f"Report-only ({len(reported)}, fixed list): {', '.join(reported)}")
        print(f"  not held to the 1e-9 tolerance; fail only if err > {ENVELOPE_FACTOR}x the rounding envelope.")
    print("ALL PASS" if all_ok else "SOME CASES FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
