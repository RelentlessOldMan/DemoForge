"""trace_check.py - DemoForge verification harness for the traceability demo.

Reads the agent's TraceabilityMatrix.xlsx and checks it against the known truth of
the audited revision (v2.2.0 kalman_update.m + test_kalman.m against CVT-EST-001
Rev C), never against keywords in prose. The prompt fixes the columns
(Requirement, Implemented, Tests, Status, Evidence) and the Status enumeration.

Truth, derived from the staged inputs:

  R1  interface         Y  T1          VERIFIED
  R2  N-by-4, in order  Y  T1 (T3)     VERIFIED   (PARTIAL accepted: row order is
                                                   only loosely checked by T3)
  R3  recursion + init  Y  T3 (T1,T2)  PARTIAL    (NOT_VERIFIED accepted: T3's 5.0
                                                   bound barely checks the recursion,
                                                   and no test uses a non-default
                                                   x0/P0, so initialization is untested)
  R4  determinism       Y  T2          VERIFIED
  R5  runnable test     Y  T1-T3       VERIFIED   (PARTIAL accepted: the suite only
                                                   partly exercises R3)
  R6  reject non-finite N  none        NOT_IMPLEMENTED (no finiteness or validity
                                                   check anywhere in kalman_update.m)

Writes metrics.json:

  n_requirements_traced    R1..R6 rows found under a valid header row
  status_correct           requirements whose Status is in the accepted set
  implemented_correct      requirements whose Implemented value is accepted
  unknown_test_citations   cited tests that do not exist in test_kalman.m
  citations_consistent     1 if every VERIFIED/PARTIAL row cites a real test, R6
                           cites none, and R1/R2 cite T1 and R4 cites T2
  r6_gap_flagged           1 if R6 is Implemented=N and Status=NOT_IMPLEMENTED
  n_data_rows              requirement rows read (display)

Exits non-zero only if it cannot read a workbook at all.
"""

from __future__ import annotations

import glob
import json
import re
import sys
from pathlib import Path

REQS = [f"R{i}" for i in range(1, 7)]
ENUM = {"VERIFIED", "PARTIAL", "NOT_VERIFIED", "NOT_IMPLEMENTED"}

ACCEPT_STATUS = {
    "R1": {"VERIFIED"},
    "R2": {"VERIFIED", "PARTIAL"},
    "R3": {"PARTIAL", "NOT_VERIFIED"},
    "R4": {"VERIFIED"},
    "R5": {"VERIFIED", "PARTIAL"},
    "R6": {"NOT_IMPLEMENTED"},
}
ACCEPT_IMPL = {
    "R1": {"Y"},
    "R2": {"Y"},
    "R3": {"Y"},
    "R4": {"Y"},
    "R5": {"Y", "PARTIAL"},
    "R6": {"N"},
}
# Tests any correct trace must cite for these requirements.
KEY_TESTS = {"R1": {"T1"}, "R2": {"T1"}, "R4": {"T2"}}
# The audited suite's tests. Used if test_kalman.m is missing from the work dir.
AUDITED_TESTS = {"T1", "T2", "T3"}

NONE_RE = re.compile(r"^(none|n/?a|-+|—|–|no tests?|nil)$", re.I)
SUITE_RE = re.compile(r"^(test_kalman(\.m)?|all|all tests)$", re.I)
RANGE_RE = re.compile(r"\bT(\d+)\s*[-–]\s*T?(\d+)\b", re.I)
TEST_RE = re.compile(r"\bT(\d+)\b", re.I)


def norm_header(v) -> str:
    return re.sub(r"[^a-z]", "", str(v).lower()) if v is not None else ""


def find_columns(row) -> dict[str, int] | None:
    """Map required column names to indexes if ``row`` is the header row."""
    heads = [norm_header(v) for v in row]
    cols: dict[str, int] = {}

    def pick(name: str, exact: tuple[str, ...], prefix: str) -> None:
        for i, h in enumerate(heads):
            if h in exact:
                cols[name] = i
                return
        for i, h in enumerate(heads):
            if h.startswith(prefix):
                cols[name] = i
                return

    pick("req", ("requirement", "requirementid", "req", "reqid", "id"), "requirement")
    pick("impl", ("implemented",), "implemented")
    pick("tests", ("tests", "test", "testids", "testid"), "tests")
    pick("status", ("status",), "status")
    return cols if len(cols) == 4 else None


def norm_impl(v) -> str:
    s = str(v or "").strip().upper()
    word = re.split(r"[\s(,;:/]+", s)[0] if s else ""
    if word in ("Y", "YES"):
        return "Y"
    if word in ("N", "NO"):
        return "N"
    if word.startswith("PARTIAL"):
        return "PARTIAL"
    return s or "?"


def norm_status(v) -> str:
    return re.sub(r"[\s\-]+", "_", str(v or "").strip().upper())


def parse_tests(v) -> tuple[set[str], list[str]]:
    """Return (cited test ids, items that name no test id)."""
    cited: set[str] = set()
    unknown: list[str] = []
    text = str(v or "")
    for a, b in RANGE_RE.findall(text):
        lo, hi = sorted((int(a), int(b)))
        cited.update(f"T{i}" for i in range(lo, hi + 1))
    text = RANGE_RE.sub(" ", text)
    for item in re.split(r"[,;/\n]+", text):
        item = item.strip().strip(".")
        if not item or NONE_RE.match(item) or SUITE_RE.match(item):
            continue
        ids = {f"T{n}" for n in TEST_RE.findall(item)}
        if ids:
            cited |= ids
        else:
            unknown.append(item)
    return cited, unknown


def known_tests() -> set[str]:
    p = Path("test_kalman.m")
    if not p.is_file():
        return set(AUDITED_TESTS)
    found = {f"T{n}" for n in re.findall(r"%\s*T(\d+)\b", p.read_text(encoding="utf-8", errors="replace"))}
    return found & AUDITED_TESTS


def read_rows(path: str) -> list[dict]:
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    for ws in wb.worksheets:
        cols = None
        out: list[dict] = []
        for row in ws.iter_rows(values_only=True):
            if cols is None:
                cols = find_columns(row)
                continue
            if max(cols.values()) >= len(row):
                row = tuple(row) + (None,) * (max(cols.values()) + 1 - len(row))
            m = re.match(r"^\s*(R\d+)\b", str(row[cols["req"]] or ""), re.I)
            if not m:
                continue
            out.append({
                "req": m.group(1).upper(),
                "impl": norm_impl(row[cols["impl"]]),
                "tests": row[cols["tests"]],
                "status": norm_status(row[cols["status"]]),
            })
        if cols is not None and out:
            return out
    return []


def main() -> int:
    try:
        import openpyxl  # noqa: F401
    except ImportError:
        print("trace_check: openpyxl is required to read the matrix", file=sys.stderr)
        return 1
    matches = sorted(glob.glob("TraceabilityMatrix.xlsx")) or sorted(glob.glob("*.xlsx"))
    if not matches:
        print("trace_check: no .xlsx traceability matrix found", file=sys.stderr)
        return 1

    rows = read_rows(matches[0])
    real_tests = known_tests()
    by_req: dict[str, list[dict]] = {}
    for r in rows:
        by_req.setdefault(r["req"], []).append(r)

    status_ok = impl_ok = 0
    unknown_citations = 0
    consistent = bool(rows)
    problems: list[str] = []
    for rid in REQS:
        entries = by_req.get(rid, [])
        if not entries:
            problems.append(f"{rid}: missing")
            consistent = False
            continue
        if all(e["status"] in ACCEPT_STATUS[rid] for e in entries):
            status_ok += 1
        else:
            problems.append(f"{rid}: status {[e['status'] for e in entries]}")
        if all(e["impl"] in ACCEPT_IMPL[rid] for e in entries):
            impl_ok += 1
        else:
            problems.append(f"{rid}: implemented {[e['impl'] for e in entries]}")
        for e in entries:
            cited, odd = parse_tests(e["tests"])
            bad = sorted(cited - real_tests) + odd
            if bad:
                unknown_citations += len(bad)
                problems.append(f"{rid}: cites tests not in test_kalman.m: {bad}")
            real = cited & real_tests
            if e["status"] in ("VERIFIED", "PARTIAL") and not real:
                consistent = False
                problems.append(f"{rid}: {e['status']} but cites no test")
            if rid == "R6" and cited:
                consistent = False
                problems.append(f"R6: cites {sorted(cited)} but no test exercises R6")
            if rid in KEY_TESTS and not KEY_TESTS[rid] <= real:
                consistent = False
                problems.append(f"{rid}: does not cite {sorted(KEY_TESTS[rid])}")

    r6 = by_req.get("R6", [])
    r6_gap = int(bool(r6) and all(e["status"] == "NOT_IMPLEMENTED" and e["impl"] == "N" for e in r6))

    metrics = {
        "n_requirements_traced": sum(1 for rid in REQS if rid in by_req),
        "status_correct": status_ok,
        "implemented_correct": impl_ok,
        "unknown_test_citations": unknown_citations,
        "citations_consistent": int(consistent),
        "r6_gap_flagged": r6_gap,
        "n_data_rows": len(rows),
    }
    with open("metrics.json", "w", encoding="utf-8") as fh:
        json.dump(metrics, fh)
    print(f"matrix: {matches[0]}  " + "  ".join(f"{k}={v}" for k, v in metrics.items()))
    for p in problems:
        print(f"  - {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
