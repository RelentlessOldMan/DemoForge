"""Generate the committed nightly-regression history + the reference plot.

Provenance/regeneration only. NOT run during verification and never staged to the
agent. Deterministic (seed 20260531, the first nightly on v2.3.0), so re-running
reproduces input/validation_runs.csv byte-for-byte. Needs numpy (+ matplotlib for the
reference plot); run it with the system python:

    python checks/_generate_dataset.py

The data (STORY.md, "2026-06-01 ... 06-30 nightly data"):
  * Nightly cvt-regression batches val-2026-05-01 .. val-2026-06-30, tests 1800-1850,
    odd tests on estimator-01, even on estimator-02. No batch on 2026-06-14 (node
    maintenance).
  * Version under test: v2.2.0 through the 2026-05-30 batch, v2.3.0 from 2026-05-31
    (released 05-30), v2.3.1 (packaging only) from 2026-06-10 (released 06-09).
  * Healthy max_abs_error ~3e-10 (lognormal, sigma 0.25, small per-test offset).
    From v2.3.0 on the covariance regression lifts it to a lognormal with median
    ~4.9e-8 and sigma 0.84: mean ~7e-8, ~20 % of cases over the 1e-7 pass limit,
    on both workers alike. As generated: median ratio v2.3.0/v2.2.0 = 172x, mean
    ratio 186x (the outlier below inflates the v2.2.0 mean; without it ~245x).
  * One isolated healthy-era outlier (test 1838 on 2026-05-14, 1.38e-7) so "first
    failing date" is not the same as "when the regression started".
  * Decoy: estimator-02 (older hardware) runs ~17 % slower. Its accuracy is the same.
The reference analysis (reference/analysis.md, findings.json) quotes the numbers this
script prints.
"""

from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
INPUT = HERE.parent / "input" / "validation_runs.csv"
REFPLOT = HERE.parent / "reference" / "error_by_version.png"

rng = np.random.default_rng(20260531)

PASS_LIMIT = 1e-7
TESTS = list(range(1800, 1851))
SKIP = {date(2026, 6, 14)}
OUTLIER = (date(2026, 5, 14), 1838, 1.38e-7)


def version_on(d: date) -> str:
    if d >= date(2026, 6, 10):
        return "v2.3.1"
    if d >= date(2026, 5, 31):
        return "v2.3.0"
    return "v2.2.0"


# Each test has its own healthy baseline (different trajectories, different noise).
test_offset = {t: float(rng.normal(0.0, 0.12)) for t in TESTS}

rows = []
d = date(2026, 5, 1)
while d <= date(2026, 6, 30):
    if d in SKIP:
        d += timedelta(days=1)
        continue
    ver = version_on(d)
    for t in TESTS:
        worker = "estimator-01" if t % 2 else "estimator-02"
        if ver == "v2.2.0":
            err = float(np.exp(np.log(3e-10) + test_offset[t] + rng.normal(0.0, 0.25)))
        else:
            err = float(np.exp(np.log(4.93e-8) + rng.normal(0.0, 0.84)))
        if (d, t) == OUTLIER[:2]:
            err = OUTLIER[2]
        base = 47.6 if worker == "estimator-01" else 55.8
        runtime = float(base + rng.normal(0.0, 1.6))
        rows.append({
            "batch": f"val-{d.isoformat()}",
            "run_date": d.isoformat(),
            "test_id": t,
            "worker": worker,
            "version": ver,
            "n_vectors": 1500,
            "max_abs_error": f"{err:.3e}",
            "runtime_ms": f"{runtime:.1f}",
        })
    d += timedelta(days=1)

INPUT.parent.mkdir(parents=True, exist_ok=True)
with INPUT.open("w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)

# --- summary (the numbers the reference analysis quotes) ---
err = np.array([float(r["max_abs_error"]) for r in rows])
ver = np.array([r["version"] for r in rows])
wkr = np.array([r["worker"] for r in rows])
rt = np.array([float(r["runtime_ms"]) for r in rows])
print(f"rows={len(rows)}  batches={len(set(r['batch'] for r in rows))}")
for v in ("v2.2.0", "v2.3.0", "v2.3.1"):
    m = ver == v
    print(f"{v}: runs={m.sum()} mean={err[m].mean():.3e} median={np.median(err[m]):.3e} "
          f"fail_rate={(err[m] >= PASS_LIMIT).mean():.4f}")
    for w_ in ("estimator-01", "estimator-02"):
        mm = m & (wkr == w_)
        print(f"    {w_}: mean={err[mm].mean():.3e} fail_rate={(err[mm] >= PASS_LIMIT).mean():.4f}")
b = err[ver == "v2.2.0"].mean()
bm = np.median(err[ver == "v2.2.0"])
print(f"median factor v2.3.0/v2.2.0 = {np.median(err[ver == 'v2.3.0']) / bm:.1f}x  "
      f"v2.3.x/v2.2.0 = {np.median(err[ver != 'v2.2.0']) / bm:.1f}x")
print(f"mean factor v2.3.0/v2.2.0 = {err[ver == 'v2.3.0'].mean() / b:.1f}x  "
      f"v2.3.x/v2.2.0 = {err[ver != 'v2.2.0'].mean() / b:.1f}x")
print(f"runtime estimator-02/estimator-01 = {rt[wkr == 'estimator-02'].mean() / rt[wkr == 'estimator-01'].mean():.3f}")

# --- reference plot ---
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    days = np.array([np.datetime64(r["run_date"]) for r in rows])
    colors = {"v2.2.0": "#4c78a8", "v2.3.0": "#e45756", "v2.3.1": "#f58518"}
    fig, ax = plt.subplots(figsize=(9, 4.8))
    for v in ("v2.2.0", "v2.3.0", "v2.3.1"):
        m = ver == v
        jitter = rng.uniform(-0.3, 0.3, m.sum()).astype("timedelta64[h]") * 24
        ax.scatter(days[m].astype("datetime64[h]") + jitter, err[m], s=6, c=colors[v],
                   alpha=0.55, label=v)
    ax.axhline(PASS_LIMIT, color="#555", ls="--", lw=1, label="pass limit 1e-7")
    ax.axvline(np.datetime64("2026-05-31"), color="#999", ls=":", lw=1)
    ax.set_yscale("log")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    ax.set_xlabel("nightly batch (2026)")
    ax.set_ylabel("max_abs_error")
    ax.set_title("cvt-regression max_abs_error per case: step change at v2.3.0 (2026-05-31)")
    ax.legend(loc="center left", fontsize=8, markerscale=2)
    fig.tight_layout()
    REFPLOT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(REFPLOT, dpi=110)
    print(f"wrote {REFPLOT}")
except ImportError:
    print("matplotlib unavailable; skipped reference plot")
