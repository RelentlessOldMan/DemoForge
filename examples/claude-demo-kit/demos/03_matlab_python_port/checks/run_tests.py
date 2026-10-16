"""run_tests.py — DemoForge verification harness for the MATLAB->Python port.

Runs from a working directory containing the agent's kalman_filter.py, the staged
inputs (test_vectors.csv, model.json), and the hidden MATLAB reference
(reference_states.csv, staged from checks/). Loads the port, runs it on the vectors,
and independently compares against the MATLAB reference, writing metrics.json:

    { max_abs_error, hidden_model_error, port_runtime_ms, n_vectors }

hidden_model_error re-runs the port on a case the agent never saw: model_alt.json
(other F, Q, H, R, x0, P0; its sensor measures in a rotated frame) over a stream
derived from test_vectors.csv, against reference_states_alt.csv (both produced by
gen_reference.m). It catches a port that hard-codes the model instead of reading it
from ``model``.

Exits non-zero if the port is missing, errors, or has the wrong shape.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent  # the verify work dir


def fail(msg: str) -> None:
    print(f"run_tests failed: {msg}", file=sys.stderr)
    sys.exit(1)


def load_submission(path: Path):
    spec = importlib.util.spec_from_file_location("submission", path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:  # noqa: BLE001 - surface any import error to the harness
        fail(f"could not import {path.name}: {exc}")
    if not hasattr(mod, "kalman_update"):
        fail(f"{path.name} has no kalman_update(Z, model)")
    return mod


def main() -> None:
    sub = HERE / "kalman_filter.py"
    if not sub.exists():
        fail("kalman_filter.py not found (produce it)")
    mod = load_submission(sub)

    m = json.loads((HERE / "model.json").read_text(encoding="utf-8"))
    model = {k: np.array(v, dtype=float) for k, v in m.items()}
    Z = np.loadtxt(HERE / "test_vectors.csv", delimiter=",", skiprows=1)
    Xref = np.loadtxt(HERE / "reference_states.csv", delimiter=",", skiprows=1)

    try:
        X = np.asarray(mod.kalman_update(Z, model), dtype=float)
    except Exception as exc:  # noqa: BLE001
        fail(f"kalman_update raised: {exc}")

    if X.shape != Xref.shape:
        fail(f"output shape {X.shape} != reference {Xref.shape}")

    reps = 5
    t = time.perf_counter()
    for _ in range(reps):
        mod.kalman_update(Z, model)
    port_runtime_ms = (time.perf_counter() - t) / reps * 1000.0

    max_abs_error = float(np.max(np.abs(X - Xref)))

    # Hidden case: same derivation as gen_reference.m (rows 1..600, axes swapped,
    # y negated, offset by (3, -2)).
    alt = json.loads((HERE / "model_alt.json").read_text(encoding="utf-8"))
    alt_model = {k: np.array(v, dtype=float) for k, v in alt.items()}
    Z2 = np.column_stack([Z[:600, 1], -Z[:600, 0]]) + np.array([3.0, -2.0])
    Xref2 = np.loadtxt(HERE / "reference_states_alt.csv", delimiter=",", skiprows=1)
    try:
        X2 = np.asarray(mod.kalman_update(Z2, alt_model), dtype=float)
        ok = X2.shape == Xref2.shape and bool(np.all(np.isfinite(X2)))
        hidden_model_error = float(np.max(np.abs(X2 - Xref2))) if ok else 1e300
    except Exception as exc:  # noqa: BLE001 - a crash here is a failed case, not a harness error
        print(f"kalman_update failed on the hidden model: {exc}", file=sys.stderr)
        hidden_model_error = 1e300

    metrics = {
        "max_abs_error": max_abs_error,
        "hidden_model_error": hidden_model_error,
        "port_runtime_ms": port_runtime_ms,
        "n_vectors": int(Z.shape[0]),
    }
    (HERE / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    print(f"max_abs_error={max_abs_error:.3g}  hidden_model_error={hidden_model_error:.3g}  port={port_runtime_ms:.2f} ms  N={Z.shape[0]}")
    sys.exit(0 if np.isfinite(max_abs_error) else 1)


if __name__ == "__main__":
    main()
