"""Build input/gate_vectors.csv: a v2.4 bench capture of gate inputs from both modes.

Provenance only. NOT run during verification (the harness reads the CSV it produces).
Stdlib only:

    python checks/_generate_gate_vectors.py

One row per measurement: mode, measurement dimension m, the gamma the bench was
configured with, the innovation y (y1..y4) and the innovation covariance S laid out in
a 4-by-4 grid (s11..s44). Planar rows (m = 2) use y1..y2 and the upper-left 2-by-2
block; the other cells are empty. One Doppler row carries a sensor dropout (NaN).

Rows are built so the decisions straddle the thresholds in both modes: Doppler rows at
gamma = 13.277 include d2 values between 9.21 and 13.277 (admitted), so a gate that
ignores gamma and uses the planar default gets them wrong, and the planar rows recorded
at 95 % (gamma = 5.991) include d2 values between 5.991 and 9.21 (rejected).
"""

from __future__ import annotations

import math
import random
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "input" / "gate_vectors.csv"
SEED = 20260908          # CVT-SRS-003 Rev C release date

# (mode, m, gamma, target d2)
PLAN = [
    ("planar", 2, 9.210, 0.42), ("planar", 2, 9.210, 1.87), ("planar", 2, 9.210, 3.05),
    ("planar", 2, 9.210, 7.36), ("planar", 2, 9.210, 8.94), ("planar", 2, 9.210, 9.87),
    ("planar", 2, 9.210, 15.2), ("planar", 2, 9.210, 0.96),
    ("doppler", 4, 13.277, 2.31), ("doppler", 4, 13.277, 4.48), ("doppler", 4, 13.277, 6.72),
    ("doppler", 4, 13.277, 9.93), ("doppler", 4, 13.277, 11.6), ("doppler", 4, 13.277, 12.9),
    ("doppler", 4, 13.277, 14.1), ("doppler", 4, 13.277, 21.4), ("doppler", 4, 13.277, 3.37),
    ("doppler", 4, 13.277, None),          # sensor dropout: NaN in the velocity channel
    ("doppler", 4, 13.277, 10.4),
    ("planar", 2, 5.991, 1.12), ("planar", 2, 5.991, 4.70), ("planar", 2, 5.991, 6.85),
    ("planar", 2, 5.991, 8.12), ("planar", 2, 5.991, 2.64),
]


def spd(rng: random.Random, m: int) -> list[list[float]]:
    """A well-conditioned SPD matrix with 4-decimal entries (rounded, kept symmetric)."""
    a = [[rng.uniform(-0.45, 0.45) for _ in range(m)] for _ in range(m)]
    s = [[sum(a[i][k] * a[j][k] for k in range(m)) for j in range(m)] for i in range(m)]
    for i in range(m):
        s[i][i] += rng.uniform(0.35, 1.6)
    for i in range(m):
        for j in range(i + 1, m):
            s[i][j] = s[j][i] = round(s[i][j], 4)
        s[i][i] = round(s[i][i], 4)
    return s


def chol(s):
    m = len(s)
    L = [[0.0] * m for _ in range(m)]
    for i in range(m):
        for j in range(i + 1):
            v = s[i][j] - sum(L[i][k] * L[j][k] for k in range(j))
            L[i][j] = math.sqrt(v) if i == j else v / L[j][j]
    return L


def main() -> None:
    rng = random.Random(SEED)
    cols = ["mode", "m", "gamma"] + [f"y{i}" for i in range(1, 5)] + \
           [f"s{i}{j}" for i in range(1, 5) for j in range(1, 5)]
    lines = [",".join(cols)]
    for mode, m, gamma, d2 in PLAN:
        s = spd(rng, m)
        u = [rng.gauss(0, 1) for _ in range(m)]
        if d2 is not None:
            # y = L u scaled so that y' S^-1 y = |u|^2 = d2 (before rounding y).
            nu = math.sqrt(sum(x * x for x in u))
            u = [x * math.sqrt(d2) / nu for x in u]
        L = chol(s)
        y = [round(sum(L[i][k] * u[k] for k in range(m)), 4) for i in range(m)]
        ycells = [f"{v:.4f}" for v in y]
        if d2 is None:
            ycells[3] = "NaN"
        ycells += [""] * (4 - m)
        scells = []
        for i in range(4):
            for j in range(4):
                scells.append(f"{s[i][j]:.4f}" if i < m and j < m else "")
        lines.append(",".join([mode, str(m), f"{gamma:.3f}"] + ycells + scells))
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(PLAN)} rows)")


if __name__ == "__main__":
    main()
