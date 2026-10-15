"""Built-in check kinds and the registry."""

from __future__ import annotations

import sys

import pytest

from demoforge.checks import (
    CheckContext,
    known_kinds,
    run_check,
    validate_check,
)
from demoforge.errors import CheckError
from demoforge.model import Check


def ctx(tmp_path, **metrics):
    return CheckContext(work_dir=tmp_path, metrics=metrics)


def test_all_builtin_kinds_registered():
    assert set(known_kinds()) >= {
        "command", "threshold", "numeric_tolerance", "file_exists", "contains", "metric",
    }


def test_unknown_kind_errors():
    with pytest.raises(CheckError, match="unknown check kind"):
        validate_check(Check(id="x", kind="nope"))


# ---- threshold ---------------------------------------------------------
def test_threshold_pass_and_fail(tmp_path):
    chk = Check(id="sp", kind="threshold", params={"metric": "speedup", "min": 3.0})
    validate_check(chk)
    assert run_check(chk, ctx(tmp_path, speedup=4.2)).passed is True
    assert run_check(chk, ctx(tmp_path, speedup=2.0)).passed is False


def test_threshold_missing_metric_is_failure_not_crash(tmp_path):
    chk = Check(id="sp", kind="threshold", params={"metric": "speedup", "min": 3.0})
    r = run_check(chk, ctx(tmp_path))
    assert r.passed is False and "not recorded" in r.message


def test_threshold_requires_bound():
    with pytest.raises(CheckError, match="min.*max"):
        validate_check(Check(id="sp", kind="threshold", params={"metric": "x"}))


@pytest.mark.parametrize("bad", [None, "fast", [1, 2], True])
def test_threshold_non_numeric_metric_fails_cleanly(tmp_path, bad):
    """A malformed (non-numeric) metric is a clean failure, not a crash."""
    chk = Check(id="sp", kind="threshold", params={"metric": "speedup", "min": 3.0})
    r = run_check(chk, ctx(tmp_path, speedup=bad))
    assert r.passed is False and "not a number" in r.message


# ---- numeric_tolerance -------------------------------------------------
def test_numeric_tolerance(tmp_path):
    chk = Check(id="eq", kind="numeric_tolerance", params={"max_abs_error": 1e-9})
    validate_check(chk)
    assert run_check(chk, ctx(tmp_path, max_abs_error=3e-12)).passed is True
    assert run_check(chk, ctx(tmp_path, max_abs_error=1e-3)).passed is False


def test_numeric_tolerance_requires_bound():
    with pytest.raises(CheckError, match="max_abs_error"):
        validate_check(Check(id="eq", kind="numeric_tolerance"))


@pytest.mark.parametrize("bad", [None, "NaNish", {"x": 1}])
def test_numeric_tolerance_non_numeric_metric_fails_cleanly(tmp_path, bad):
    chk = Check(id="eq", kind="numeric_tolerance", params={"max_abs_error": 1e-9})
    r = run_check(chk, ctx(tmp_path, max_abs_error=bad))
    assert r.passed is False and "not a number" in r.message


# ---- file_exists -------------------------------------------------------
def test_file_exists(tmp_path):
    (tmp_path / "optimized_kalman.m").write_text("x", encoding="utf-8")
    chk = Check(id="f", kind="file_exists", params={"pattern": "optimized_*.m"})
    validate_check(chk)
    r = run_check(chk, ctx(tmp_path))
    assert r.passed is True and r.value == 1
    miss = Check(id="f2", kind="file_exists", params={"pattern": "nope_*.m"})
    assert run_check(miss, ctx(tmp_path)).passed is False


def test_file_exists_requires_pattern_or_path():
    with pytest.raises(CheckError, match="pattern.*path"):
        validate_check(Check(id="f", kind="file_exists"))


# ---- contains ----------------------------------------------------------
def test_contains_text_and_pattern(tmp_path):
    (tmp_path / "report.md").write_text("root cause: units mismatch (deg vs rad)", encoding="utf-8")
    text = Check(id="c", kind="contains", params={"file": "report.md", "text": "units mismatch"})
    validate_check(text)
    assert run_check(text, ctx(tmp_path)).passed is True
    pat = Check(id="c2", kind="contains", params={"file": "report.md", "pattern": r"deg vs rad"})
    assert run_check(pat, ctx(tmp_path)).passed is True
    missing_file = Check(id="c3", kind="contains", params={"file": "absent.md", "text": "x"})
    assert run_check(missing_file, ctx(tmp_path)).passed is False


def test_contains_requires_text_or_pattern():
    with pytest.raises(CheckError, match="text.*pattern"):
        validate_check(Check(id="c", kind="contains", params={"file": "r.md"}))


# ---- metric ------------------------------------------------------------
def test_metric_is_informational(tmp_path):
    chk = Check(id="runtime_ms", kind="metric")
    validate_check(chk)
    r = run_check(chk, ctx(tmp_path, runtime_ms=123))
    assert r.passed is None and r.value == 123 and r.is_metric


# ---- command -----------------------------------------------------------
def test_command_exit_codes(tmp_path):
    ok = Check(id="ok", kind="command", params={"run": f'"{sys.executable}" -c "exit(0)"'})
    validate_check(ok)
    assert run_check(ok, ctx(tmp_path)).passed is True
    bad = Check(id="bad", kind="command", params={"run": f'"{sys.executable}" -c "exit(1)"'})
    assert run_check(bad, ctx(tmp_path)).passed is False


def test_command_requires_run():
    with pytest.raises(CheckError, match="missing required param"):
        validate_check(Check(id="x", kind="command"))


def test_command_timeout_is_failure_not_hang(tmp_path, monkeypatch):
    """A command that overruns the budget fails the check instead of blocking."""
    import demoforge.checks.kinds as kinds
    monkeypatch.setattr(kinds, "_COMMAND_TIMEOUT", 0.3)
    chk = Check(
        id="slow", kind="command",
        params={"run": f'"{sys.executable}" -c "import time; time.sleep(5)"'},
    )
    r = run_check(chk, ctx(tmp_path))
    assert r.passed is False and "timed out" in r.message
