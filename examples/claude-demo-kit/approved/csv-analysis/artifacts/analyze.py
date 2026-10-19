"""Analysis of cvt-regression nightly results (validation_runs.csv).

Produces findings.json and regression_timeline.png.
"""
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

THRESHOLD = 1e-7
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
WORKER_COLORS = {"estimator-01": "#2a78d6", "estimator-02": "#eb6834"}

d = pd.read_csv("validation_runs.csv", parse_dates=["run_date"])
d["fail"] = d["max_abs_error"] >= THRESHOLD

# --- first affected batch: first nightly with a median error above the v2.2.0 range
daily = d.groupby("run_date").agg(
    version=("version", "first"),
    median_err=("max_abs_error", "median"),
    fails=("fail", "sum"),
)
first_ver_date = d.groupby("version")["run_date"].min().sort_values()
base_max_median = daily.loc[daily.version == "v2.2.0", "median_err"].max()
start = daily.index[daily.median_err > 10 * base_max_median][0]

per_version = {}
for v, s in d.groupby("version"):
    e = s["max_abs_error"]
    per_version[v] = {
        "runs": int(len(s)),
        "mean_max_abs_error": float(e.mean()),
        "median_max_abs_error": float(e.median()),
        "fail_rate": float((e >= THRESHOLD).mean()),
    }

culprit, baseline = "v2.3.0", "v2.2.0"
factor = per_version[culprit]["median_max_abs_error"] / per_version[baseline]["median_max_abs_error"]

findings = {
    "regression_start_date": start.strftime("%Y-%m-%d"),
    "explained_by": "version",
    "culprit": culprit,
    "baseline": baseline,
    "magnitude_factor": round(factor, 1),
    "affected_workers": sorted(d.loc[d.run_date >= start, "worker"].unique().tolist()),
    "per_version": per_version,
}
with open("findings.json", "w") as f:
    json.dump(findings, f, indent=2)
print(json.dumps(findings, indent=2))
print("version first seen:\n", first_ver_date)

# --- plot
plt.rcParams.update({"font.family": "Segoe UI", "font.size": 10, "text.color": INK,
                     "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2})
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 6.6), sharex=True,
                               gridspec_kw={"height_ratios": [3, 1.2], "hspace": 0.08},
                               facecolor=SURFACE)
rng = np.random.default_rng(0)
for w, c in WORKER_COLORS.items():
    s = d[d.worker == w]
    off = (-0.18 if w == "estimator-01" else 0.18) + rng.uniform(-0.12, 0.12, len(s))
    ax1.scatter(s.run_date + pd.to_timedelta(off, unit="D"), s.max_abs_error, s=9,
                color=c, alpha=0.55, linewidths=0, label=w)
ax1.plot(daily.index, daily.median_err, color=INK, lw=2, label="nightly median")
ax1.axhline(THRESHOLD, color=INK2, lw=1, ls="--")
ax1.text(pd.Timestamp("2026-05-29"), THRESHOLD * 1.25, "pass threshold 1e-7", color=INK2, fontsize=9, ha="right")
ax1.set_yscale("log")
ax1.set_ylabel("max_abs_error (log scale)")
ax1.legend(loc="upper left", bbox_to_anchor=(0, 0.62), frameon=False, fontsize=9, markerscale=1.8)

ax2.bar(daily.index, daily.fails, width=0.8, color="#2a78d6")
ax2.set_ylabel("failing cases\n(of 51)")
ax2.text(pd.Timestamp("2026-06-14"), 0.5, "no\nbatch", ha="center", va="bottom", fontsize=8, color=INK2)

for ax in (ax1, ax2):
    ax.set_facecolor(SURFACE)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_color(GRID)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for v, t in first_ver_date.items():
        if v != "v2.2.0":
            ax.axvline(t - pd.Timedelta(hours=12), color=INK2, lw=1)
ymax = ax1.get_ylim()[1]
labels = list(first_ver_date.items())
for i, (v, t) in enumerate(labels):
    end = labels[i + 1][1] if i + 1 < len(labels) else d.run_date.max()
    mid = t + (end - t) / 2
    ax1.text(mid, ymax / 1.6, v, ha="center", va="top", fontsize=10, fontweight="bold", color=INK)
ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
ax2.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.SU))
fig.suptitle(f"cvt-regression: errors jumped ~{factor:.0f}x when v2.3.0 shipped ({start:%b %d}); "
             "v2.3.1 did not fix it", x=0.06, ha="left", fontsize=12.5, fontweight="bold")
fig.text(0.06, 0.915, "Each dot is one test case in one nightly batch, by worker. Both workers move together.",
         fontsize=9.5, color=INK2)
fig.savefig("regression_timeline.png", dpi=160, bbox_inches="tight", facecolor=SURFACE)
