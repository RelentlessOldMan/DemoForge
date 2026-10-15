"""Demo schema parsing and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from demoforge.errors import DemoError
from demoforge.model import Demo


def _demo(data, tmp_path: Path) -> Demo:
    return Demo.from_yaml(data, dir=tmp_path)


def test_minimal_demo_defaults(tmp_path):
    d = _demo({"id": "x", "title": "X"}, tmp_path)
    assert d.id == "x" and d.title == "X"
    assert d.order == 0
    assert d.enabled is True
    assert d.runtime == "none"
    assert d.prompt == "prompt.md"
    assert d.prompt_path == tmp_path / "prompt.md"
    assert d.narration is None and d.narration_path is None
    assert d.checks == ()
    assert d.presentation.enabled is True


def test_full_demo_parse(tmp_path):
    d = _demo(
        {
            "id": "opt",
            "title": "Opt",
            "order": 2,
            "enabled": False,
            "prompt": "p.md",
            "narration": "n.md",
            "inputs": ["input/a.m", "input/b.csv"],
            "runtime": "octave",
            "checks": [
                {"id": "sp", "kind": "threshold", "metric": "speedup", "min": 3.0},
                {"id": "t", "kind": "command", "run": "x", "description": "runs"},
            ],
            "presentation": {"enabled": True, "highlights": [{"tool": "Bash", "match": "bench"}]},
        },
        tmp_path,
    )
    assert d.order == 2 and d.enabled is False
    assert d.runtime == "octave"
    assert d.input_paths() == [tmp_path / "input/a.m", tmp_path / "input/b.csv"]
    assert [c.id for c in d.checks] == ["sp", "t"]
    assert d.checks[0].params == {"metric": "speedup", "min": 3.0}
    assert d.checks[1].description == "runs"
    assert d.presentation.highlights[0]["tool"] == "Bash"


def test_harness_and_metrics_from(tmp_path):
    d = _demo({"id": "x", "title": "X"}, tmp_path)
    assert d.harness is None and d.metrics_from == "metrics.json"
    assert d.harness_path is None

    d2 = _demo(
        {"id": "x", "title": "X", "harness": "checks/run_tests.m", "metrics_from": "m.json"},
        tmp_path,
    )
    assert d2.harness == "checks/run_tests.m"
    assert d2.harness_path == tmp_path / "checks/run_tests.m"
    assert d2.metrics_from == "m.json"


def test_missing_required_field(tmp_path):
    with pytest.raises(DemoError, match="required field 'title'"):
        _demo({"id": "x"}, tmp_path)


def test_invalid_runtime(tmp_path):
    with pytest.raises(DemoError, match="runtime"):
        _demo({"id": "x", "title": "X", "runtime": "matlab"}, tmp_path)


def test_bad_order(tmp_path):
    with pytest.raises(DemoError, match="order"):
        _demo({"id": "x", "title": "X", "order": "two"}, tmp_path)


def test_check_missing_kind(tmp_path):
    with pytest.raises(DemoError, match="missing required field 'kind'"):
        _demo({"id": "x", "title": "X", "checks": [{"id": "c"}]}, tmp_path)


def test_duplicate_check_ids(tmp_path):
    with pytest.raises(DemoError, match="duplicate check id"):
        _demo(
            {
                "id": "x",
                "title": "X",
                "checks": [
                    {"id": "c", "kind": "metric"},
                    {"id": "c", "kind": "metric"},
                ],
            },
            tmp_path,
        )
