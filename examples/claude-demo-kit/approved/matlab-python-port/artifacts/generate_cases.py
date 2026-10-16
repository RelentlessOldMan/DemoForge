"""Write the MATLAB-vs-Python comparison cases to cases/<name>/.

Each case directory gets
    model.json   F, Q, H, R, x0, P0 (same layout as ../model.json)
    z.csv        measurement stream, one row per step, no header
A case whose model.json has "gate": "report" is compared but not held to the
1e-9 tolerance by check_agreement.py (see REPORT_ONLY below for why).
Numbers are written with repr(), which round-trips doubles exactly, so
MATLAB/Octave and NumPy start from bit-identical inputs.

The cases are committed; rerunning this script (fixed seed) regenerates
the same files.  It overwrites model.json and z.csv only, leaving any
ref.csv from make_reference.m in place.
"""

import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
CASES = HERE / "cases"
rng = np.random.default_rng(20261016)


# Cases exempt from the 1e-9 gate.  Fixed list, decided from measurements on
# 2026-10-16: perturbing the predicted covariance by 1 ulp per step moved these
# outputs by 2e3 to 3e7 times the tolerance (every other case: <= 0.31x), so a
# correct MATLAB/MKL run cannot be expected to meet it.  They are still
# compared, and fail if the error exceeds 10x that rounding envelope.
REPORT_ONLY = {"10_illcond_S_1e10", "11_illcond_S_1e14", "12_illcond_collinear_H"}


# ---------------------------------------------------------------- helpers

def random_spd(n, cond=10.0, scale=1.0):
    """Random symmetric positive definite matrix with given condition number."""
    U, _ = np.linalg.qr(rng.standard_normal((n, n)))
    eig = scale * np.geomspace(1.0, 1.0 / cond, n)
    A = U @ np.diag(eig) @ U.T
    return (A + A.T) / 2


def cv_model(dims, dt, q):
    """Constant-velocity model, state [pos(dims), vel(dims)], DWNA process noise."""
    I = np.eye(dims)
    Z0 = np.zeros((dims, dims))
    F = np.block([[I, dt * I], [Z0, I]])
    Q = q * np.block([[dt**4 / 4 * I, dt**3 / 2 * I], [dt**3 / 2 * I, dt**2 * I]])
    H = np.hstack([I, Z0])
    return F, Q, H


def ca_model(dims, dt, q):
    """Constant-acceleration model, state [pos, vel, acc] per axis (axis-blocked)."""
    f = np.array([[1, dt, dt**2 / 2], [0, 1, dt], [0, 0, 1]])
    g = np.array([[dt**2 / 2], [dt], [1.0]])
    F = np.kron(np.eye(dims), f)
    Q = np.kron(np.eye(dims), q * (g @ g.T))
    H = np.kron(np.eye(dims), np.array([[1.0, 0, 0]]))
    return F, Q, H


def simulate(F, Q, H, R, x_true0, N):
    """Simulate a truth trajectory and noisy measurements."""
    n, m = F.shape[0], H.shape[0]
    w, V = np.linalg.eigh(Q)  # Q may be rank-deficient (DWNA), so no Cholesky
    LQ = V @ np.diag(np.sqrt(np.clip(w, 0, None)))
    LR = np.linalg.cholesky(R)
    x = np.array(x_true0, dtype=float)
    Z = np.empty((N, m))
    for k in range(N):
        x = F @ x + LQ @ rng.standard_normal(n)
        Z[k] = H @ x + LR @ rng.standard_normal(m)
    return Z


def write_case(name, desc, F, Q, H, R, x0, P0, Z):
    d = CASES / name
    d.mkdir(parents=True, exist_ok=True)
    model = {
        "description": desc,
        **({"gate": "report"} if name in REPORT_ONLY else {}),
        "F": np.asarray(F, float).tolist(),
        "Q": np.asarray(Q, float).tolist(),
        "H": np.asarray(H, float).tolist(),
        "R": np.asarray(R, float).tolist(),
        "x0": np.asarray(x0, float).reshape(-1).tolist(),
        "P0": np.asarray(P0, float).tolist(),
    }
    (d / "model.json").write_text(json.dumps(model, indent=1) + "\n")
    with open(d / "z.csv", "w", newline="\n") as f:
        for row in np.atleast_2d(Z):
            f.write(",".join("NaN" if np.isnan(v) else repr(float(v)) for v in row) + "\n")


# ------------------------------------------------------------------ cases

# 1. The shipped model and recorded stream.
base = json.loads((HERE / "model.json").read_text())
Zb = np.loadtxt(HERE / "test_vectors.csv", delimiter=",", skiprows=1)
write_case("01_baseline", "model.json + test_vectors.csv as shipped",
           base["F"], base["Q"], base["H"], base["R"], base["x0"], base["P0"], Zb)

# 2. 2-D CV, dt = 0.1, correlated R, full P0, non-zero x0.
F, Q, H = cv_model(2, 0.1, 0.5)
R = np.array([[0.30, 0.21], [0.21, 0.40]])
P0 = random_spd(4, cond=50, scale=5.0)
x0 = [10.0, -5.0, 1.0, 0.5]
write_case("02_cv2d_dt0.1_corrR_fullP0", "2-D constant velocity, dt=0.1, correlated R, full P0",
           F, Q, H, R, x0, P0, simulate(F, Q, H, R, [12.0, -4.0, 1.3, 0.2], 5000))

# 3. 3-D constant acceleration, n = 9, m = 3, dt = 0.02.
F, Q, H = ca_model(3, 0.02, 2.0)
R = random_spd(3, cond=20, scale=0.5)
P0 = random_spd(9, cond=1e3, scale=10.0)
write_case("03_ca3d_n9_m3_dt0.02", "3-D constant acceleration, 9 states, 3 measurements, full R and P0",
           F, Q, H, R, np.zeros(9), P0, simulate(F, Q, H, R, rng.standard_normal(9), 3000))

# 4. Scalar random walk, n = m = 1.
F, Q, H, R = [[1.0]], [[0.04]], [[1.0]], [[0.9]]
write_case("04_scalar_random_walk_n1_m1", "Scalar random walk, n=m=1",
           F, Q, H, R, [0.0], [[100.0]],
           simulate(np.array(F), np.array(Q), np.array(H), np.array(R), [3.0], 2000))

# 5. Generic random model, n = 6, m = 4, non-trivial F and H.
A = rng.standard_normal((6, 6))
F = 0.98 * A / max(abs(np.linalg.eigvals(A)))
H = rng.standard_normal((4, 6))
Q = random_spd(6, cond=100, scale=0.1)
R = random_spd(4, cond=100, scale=1.0)
P0 = random_spd(6, cond=1e4, scale=50.0)
write_case("05_random_n6_m4", "Random stable F, dense H, Q, R, P0 (n=6, m=4)",
           F, Q, H, R, rng.standard_normal(6), P0, simulate(F, Q, H, R, rng.standard_normal(6), 4000))

# 6. Redundant sensors, m > n: three sensors on a 1-D CV target.
F, Q, H1 = cv_model(1, 0.5, 0.1)
H = np.vstack([H1, H1, [[1.0, 0.5]]])
R = random_spd(3, cond=30, scale=0.2)
write_case("06_redundant_sensors_n2_m3", "1-D CV target seen by 3 sensors (m > n)",
           F, Q, H, R, [0.0, 0.0], np.diag([10.0, 1.0]),
           simulate(F, Q, H, R, [1.0, 0.3], 3000))

# 7. Long, messy stream: 50k steps, outliers, track jumps, slowly drifting bias.
F, Q, H = cv_model(2, 0.25, 0.2)
R = np.array([[1.0, -0.4], [-0.4, 0.8]])
N = 50000
Z = simulate(F, Q, H, R, [0.0, 0.0, 2.0, -1.0], N)
out = rng.random(N) < 0.03
Z[out] += rng.standard_normal((out.sum(), 2)) * 50.0
for k in rng.choice(N, 20, replace=False):
    Z[k:] += rng.standard_normal(2) * 200.0
Z += np.linspace(0, 30, N)[:, None]
write_case("07_messy_long_50k", "50k-step CV stream with 3% 50-sigma outliers, 20 track jumps, drift",
           F, Q, H, R, [0, 0, 0, 0], np.eye(4) * 1e3, Z)

# 8. Large absolute coordinates (~1e6), e.g. projected map coordinates.
F, Q, H = cv_model(2, 1.0, 0.01)
R = np.array([[4.0, 1.0], [1.0, 3.0]])
write_case("08_large_offset_1e6", "2-D CV at ~1e6 absolute coordinates",
           F, Q, H, R, [1.0e6, 2.5e6, 0, 0], np.diag([1e4, 1e4, 1e2, 1e2]),
           simulate(F, Q, H, R, [1.0e6 + 30, 2.5e6 - 20, 3.0, -2.0], 20000))

# 9-11. Badly conditioned S.  S = H P H' + R; make R nearly singular and
#       keep P small, so cond(S) is driven by R.
F, Q, H = cv_model(2, 0.1, 1e-6)
for name, rho in [("09_illcond_S_1e6", 1 - 1e-6),
                  ("10_illcond_S_1e10", 1 - 1e-10),
                  ("11_illcond_S_1e14", 1 - 1e-14)]:
    R = np.array([[1.0, rho], [rho, 1.0]])
    # Simulate with a well-conditioned R; the filter's R is what matters for S.
    Zs = simulate(F, Q, H, np.array([[1.0, 0.99], [0.99, 1.0]]), [0, 0, 0.5, 0.5], 3000)
    write_case(name, f"Nearly singular R (rho = 1 - {1 - rho:.0e}), tiny P0 and Q",
               F, Q, H, R, [0, 0, 0.5, 0.5], np.eye(4) * 1e-6, Zs)

# 12. Badly conditioned S from nearly collinear sensor rows in H.
F, Q, _ = cv_model(2, 0.1, 0.01)
H = np.array([[1.0, 0, 0, 0], [1.0, 1e-6, 0, 0]])
R = np.eye(2) * 1e-8
write_case("12_illcond_collinear_H", "Two nearly identical sensor rows in H, tiny R",
           F, Q, H, R, [0, 0, 0, 0], np.eye(4) * 1e4,
           simulate(F, Q, H, R, [1.0, 2.0, 0.1, 0.1], 3000))

# 13. Dropout: a NaN measurement mid-stream (neither implementation skips it).
F, Q, H = cv_model(2, 0.1, 0.5)
R = np.array([[0.3, 0.1], [0.1, 0.3]])
Z = simulate(F, Q, H, R, [0, 0, 1, 1], 500)
Z[250, :] = np.nan
write_case("13_nan_dropout", "CV stream with one all-NaN measurement row at step 251",
           F, Q, H, R, [0, 0, 0, 0], np.eye(4), Z)

print("wrote", len(list(CASES.iterdir())), "cases to", CASES)
