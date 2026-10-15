"""Deterministically generate the measurement streams for the optimization demo.

Author tool, never staged to the agent. Writes:

- ``input/test_vectors.csv``: the 1500-vector regression stream the agent sees
  (noisy 2-D constant-velocity track, position measured once per step). CRLF, as
  exported on the Windows validation workers.
- ``checks/hidden_stream.csv``: a longer (4500-vector) stream the harness uses to
  time both implementations and to run them under a second, hidden model. It is a
  different track (other start, other velocity, two gentle turns) so a solution
  that hard-codes the public data cannot pass.

Seed 20251117 is the v2.1.0 release date (STORY.md), the code under optimization.

    python tools/generate_vectors.py

Regenerate only if you intend to change the data; the CSVs are committed.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

SEED = 20251117
DT = 1.0

N_PUBLIC = 1500
VEL = (1.0, 0.5)          # true constant velocity (m/step)
NOISE_SD = 0.5            # measurement noise sd (m), matches R = 0.25 I

N_HIDDEN = 4500

DEMO = Path(__file__).resolve().parent.parent
PUBLIC = DEMO / "input" / "test_vectors.csv"
HIDDEN = DEMO / "checks" / "hidden_stream.csv"


def write_csv(path: Path, data: np.ndarray, newline: str) -> None:
    lines = ["meas_x,meas_y"] + [f"{a:.10f},{b:.10f}" for a, b in data]
    path.write_bytes((newline.join(lines) + newline).encode("ascii"))
    print(f"wrote {path} ({len(data)} rows)")


def public_stream(rng: np.random.Generator) -> np.ndarray:
    k = np.arange(N_PUBLIC)
    true_x = VEL[0] * DT * k
    true_y = VEL[1] * DT * k
    meas_x = true_x + rng.normal(0.0, NOISE_SD, size=N_PUBLIC)
    meas_y = true_y + rng.normal(0.0, NOISE_SD, size=N_PUBLIC)
    return np.column_stack([meas_x, meas_y])


def hidden_stream(rng: np.random.Generator) -> np.ndarray:
    # Speed 1.2 m/step, heading changes by +30 deg at k=1500 and -45 deg at k=3000.
    heading = np.full(N_HIDDEN, np.deg2rad(20.0))
    heading[1500:] += np.deg2rad(30.0)
    heading[3000:] -= np.deg2rad(45.0)
    vel = 1.2 * np.column_stack([np.cos(heading), np.sin(heading)])
    pos = np.array([-250.0, 120.0]) + np.cumsum(vel * DT, axis=0)
    noise = rng.normal(0.0, 0.6, size=(N_HIDDEN, 2))
    return pos + noise


def main() -> None:
    rng = np.random.default_rng(SEED)
    write_csv(PUBLIC, public_stream(rng), "\r\n")
    write_csv(HIDDEN, hidden_stream(rng), "\n")


if __name__ == "__main__":
    main()
