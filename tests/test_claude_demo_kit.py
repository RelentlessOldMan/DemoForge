"""Integration: the real ClaudeDemoKit content set loads and validates.

Guards the committed content set against schema/registry drift as the engine evolves.
"""

from __future__ import annotations

import pytest

from conftest import CLAUDE_DEMO_KIT

from demoforge.checks import validate_check
from demoforge.discovery import load_content_set

pytestmark = pytest.mark.skipif(
    not (CLAUDE_DEMO_KIT / "demoforge.toml").exists(),
    reason="claude-demo-kit content set not present",
)


def test_content_set_loads():
    cs = load_content_set(CLAUDE_DEMO_KIT)
    assert cs.config.id == "claude-demo-kit"


def test_all_demos_are_valid_and_self_contained():
    cs = load_content_set(CLAUDE_DEMO_KIT)
    demos = cs.demos()
    assert {
        "matlab-implementation", "matlab-optimization", "matlab-python-port",
        "log-investigation", "excel-investigation", "csv-analysis",
        "spec-implementation", "verification", "traceability",
        "autonomous-investigation",
    } <= {d.id for d in demos}
    for d in demos:
        for c in d.checks:
            validate_check(c)
        assert d.prompt_path.is_file(), d.id
        if d.narration:
            assert d.narration_path.is_file(), d.id
        if d.harness:
            assert d.harness_path.is_file(), d.id
        for p in d.input_paths():
            assert p.is_file(), (d.id, p)


def test_demo2_discovered_and_valid():
    cs = load_content_set(CLAUDE_DEMO_KIT)
    by_id = {d.id: d for d in cs.demos()}
    assert "matlab-optimization" in by_id
    demo = by_id["matlab-optimization"]
    assert demo.runtime == "octave"
    assert demo.prompt_path.is_file()
    assert demo.narration_path and demo.narration_path.is_file()
    # Every declared check must be valid against the registry.
    for c in demo.checks:
        validate_check(c)
    kinds = {c.kind for c in demo.checks}
    assert {"file_exists", "numeric_tolerance", "threshold", "metric"} <= kinds
    # Inputs and the independent harness/reference solution are present on disk.
    assert demo.harness == "checks/run_tests.m"
    assert demo.harness_path.is_file()
    for p in demo.input_paths():
        assert p.is_file(), p
    assert (demo.dir / "reference" / "kalman_update_fast.m").is_file()
