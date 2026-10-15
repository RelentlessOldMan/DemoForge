"""analyze.py - DemoForge verification harness for the CSV-analysis demo.

Recomputes the structure of validation_runs.csv independently, then checks the agent's
findings.json against that recomputation. Nothing the agent reports is trusted.

Ground truth, derived from the data (never hard-coded):
  * per version: runs, mean and median max_abs_error, fail rate (max_abs_error >= 1e-7);
  * regression version = the version whose median error is furthest above the median
    of the version before it (versions ordered by first batch date);
  * regression start = first batch date on that version;
  * affected workers = workers whose median error on/after that date is > 10x their
    median before it.

Writes metrics.json (1 = pass, 0 = fail, plus display numbers):
  findings_valid     findings.json parses and has the schema
  start_date_ok      regression_start_date equals the recomputed date exactly
  attribution_ok     explained_by == "version"
  version_ok         culprit and baseline are the regressed version and the one before
                     it (leading "v" and trailing ".0" ignored: v2.3 == v2.3.0)
  factor_ok          magnitude_factor within +-20 % of the recomputed median ratio
                     (culprit/baseline; the pooled post-change ratio is also accepted)
  workers_ok         affected_workers is exactly the set of affected workers
  per_version_ok     every version reported, runs exact, mean/median within 3 %,
                     fail_rate within 0.005
  regression_version, error_factor, worker_runtime_ratio, n_rows (display)

Stdlib only. Exits non-zero only if the dataset itself is missing or unreadable.
"""

from __future__ import annotations

import csv
import json
import statistics
import sys
from collections import defaultdict

PASS_LIMIT = 1e-7


def recompute(rows):
    by_ver = defaultdict(list)
    first_date = {}
    for r in rows:
        v = r["version"]
        by_ver[v].append(float(r["max_abs_error"]))
        first_date[v] = min(first_date.get(v, r["run_date"]), r["run_date"])
    order = sorted(by_ver, key=lambda v: first_date[v])
    stats = {
        v: {
            "runs": len(e),
            "mean": statistics.fmean(e),
            "median": statistics.median(e),
            "fail_rate": sum(x >= PASS_LIMIT for x in e) / len(e),
        }
        for v, e in by_ver.items()
    }
    jumps = {order[i]: stats[order[i]]["median"] / stats[order[i - 1]]["median"]
             for i in range(1, len(order))}
    suspect = max(jumps, key=jumps.get) if jumps else order[0]
    baseline = order[order.index(suspect) - 1] if jumps else order[0]
    start = first_date[suspect]
    after = [float(r["max_abs_error"]) for r in rows if r["run_date"] >= start]
    pooled = statistics.median(after) / stats[baseline]["median"]

    workers = sorted({r["worker"] for r in rows})
    affected = set()
    for w in workers:
        pre = [float(r["max_abs_error"]) for r in rows if r["worker"] == w and r["run_date"] < start]
        post = [float(r["max_abs_error"]) for r in rows if r["worker"] == w and r["run_date"] >= start]
        if pre and post and statistics.median(post) > 10 * statistics.median(pre):
            affected.add(w)

    rt = defaultdict(list)
    for r in rows:
        rt[r["worker"]].append(float(r["runtime_ms"]))
    means = sorted(statistics.fmean(x) for x in rt.values())
    return {
        "stats": stats, "suspect": suspect, "baseline": baseline, "start": start,
        "factor": jumps.get(suspect, 1.0), "pooled_factor": pooled,
        "affected": affected, "runtime_ratio": means[-1] / means[0] if means else 1.0,
    }


def num(x):
    if isinstance(x, bool):
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def norm_ver(v) -> str:
    """'v2.3.0', '2.3.0' and 'v2.3' compare equal; 'v2.3.1' stays distinct."""
    s = str(v).strip().lower().lstrip("v")
    while s.endswith(".0"):
        s = s[:-2]
    return s


def close(a, b, rel):
    return a is not None and b != 0 and abs(a - b) <= rel * abs(b)


def main() -> int:
    try:
        with open("validation_runs.csv", newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
    except OSError as exc:
        print(f"analyze: cannot read validation_runs.csv: {exc}", file=sys.stderr)
        return 1
    if not rows:
        print("analyze: dataset is empty", file=sys.stderr)
        return 1

    t = recompute(rows)
    m = {k: 0 for k in ("findings_valid", "start_date_ok", "version_ok", "factor_ok",
                        "workers_ok", "attribution_ok", "per_version_ok")}
    m.update({
        "n_rows": len(rows),
        "regression_version": t["suspect"],
        "error_factor": round(t["factor"], 1),
        "worker_runtime_ratio": round(t["runtime_ratio"], 3),
    })

    def finish(msg):
        with open("metrics.json", "w", encoding="utf-8") as fh:
            json.dump(m, fh)
        print(msg)
        print(f"  truth: start={t['start']} suspect={t['suspect']} baseline={t['baseline']} "
              f"factor={t['factor']:.1f} (pooled {t['pooled_factor']:.1f}) "
              f"affected={sorted(t['affected'])}")
        for k, v in m.items():
            print(f"  {k} = {v}")
        return 0

    try:
        with open("findings.json", encoding="utf-8") as fh:
            f = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return finish(f"findings.json missing or not JSON: {exc}")
    keys = ("regression_start_date", "explained_by", "culprit", "baseline",
            "magnitude_factor", "affected_workers", "per_version")
    if not isinstance(f, dict) or any(k not in f for k in keys) \
            or not isinstance(f["affected_workers"], list) \
            or not isinstance(f["per_version"], dict):
        return finish("findings.json does not match the schema")
    m["findings_valid"] = 1

    m["start_date_ok"] = int(str(f["regression_start_date"]).strip() == t["start"])
    m["version_ok"] = int(norm_ver(f["culprit"]) == norm_ver(t["suspect"])
                          and norm_ver(f["baseline"]) == norm_ver(t["baseline"]))
    fac = num(f["magnitude_factor"])
    m["factor_ok"] = int(close(fac, t["factor"], 0.20) or close(fac, t["pooled_factor"], 0.20))
    m["workers_ok"] = int({str(w).strip() for w in f["affected_workers"]} == t["affected"])
    m["attribution_ok"] = int(str(f["explained_by"]).strip().lower() == "version")

    ok = set(f["per_version"]) == set(t["stats"])
    for v, s in t["stats"].items():
        got = f["per_version"].get(v)
        if not ok or not isinstance(got, dict):
            ok = False
            break
        runs = num(got.get("runs"))
        fr = num(got.get("fail_rate"))
        ok &= runs is not None and int(runs) == s["runs"]
        ok &= close(num(got.get("mean_max_abs_error")), s["mean"], 0.03)
        ok &= close(num(got.get("median_max_abs_error")), s["median"], 0.03)
        ok &= fr is not None and abs(fr - s["fail_rate"]) <= 0.005
    m["per_version_ok"] = int(bool(ok))
    return finish("findings.json checked")


if __name__ == "__main__":
    sys.exit(main())
