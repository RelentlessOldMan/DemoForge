"""Run-bundle model: events, metadata, results, run ids, round-trips."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from demoforge.model import (
    CheckResult,
    Event,
    Results,
    RunBundle,
    RunMetadata,
    new_run_id,
)


def test_event_rejects_unknown_type():
    with pytest.raises(ValueError, match="unknown event type"):
        Event(seq=0, t=0.0, type="thinking")


def test_event_json_roundtrip():
    ev = Event(seq=3, t=6.1, type="file_read", data={"path": "kalman_update.m"})
    obj = ev.to_json()
    assert obj == {"seq": 3, "t": 6.1, "type": "file_read", "path": "kalman_update.m"}
    assert Event.from_json(obj) == ev


def test_new_run_id_is_sortable_and_stable():
    when = datetime(2026, 9, 30, 22, 42, 40, tzinfo=timezone.utc)
    rid = new_run_id(when, seed="abc")
    assert rid.startswith("20260930T224240Z-")
    assert new_run_id(when, seed="abc") == rid  # deterministic for same inputs
    assert new_run_id(when, seed="xyz") != rid  # seed diversifies


def test_results_passed_logic():
    r = Results(
        checks=[
            CheckResult(id="a", kind="threshold", passed=True, value=4.0),
            CheckResult(id="b", kind="metric", passed=None, value=12),  # ignored
        ]
    )
    assert r.passed is True
    assert r.metrics() == {"b": 12}

    r.checks.append(CheckResult(id="c", kind="command", passed=False, value=1))
    assert r.passed is False


def test_bundle_create_and_roundtrip(tmp_path):
    b = RunBundle(root=tmp_path / "runs" / "demo" / "rid").create()
    assert b.artifacts_dir.is_dir()
    assert not b.exists()  # no metadata written yet

    meta = RunMetadata(demo_id="demo", model="claude-opus-4-8", created="2026-09-30T00:00:00Z")
    b.write_metadata(meta)
    assert b.exists()
    assert b.read_metadata().model == "claude-opus-4-8"

    events = [
        Event(seq=0, t=0.0, type="prompt"),
        Event(seq=1, t=1.4, type="assistant_text", data={"text": "hi"}),
        Event(seq=2, t=3.2, type="file_read", data={"path": "a.m"}),
    ]
    b.write_events(events)
    assert b.read_events() == events

    results = Results(checks=[CheckResult(id="sp", kind="threshold", passed=True, value=4.2)])
    b.write_results(results)
    back = b.read_results()
    assert back.passed is True and back.checks[0].value == 4.2


def test_json_writes_are_byte_stable(tmp_path):
    """Determinism contract: same content -> identical bytes (sorted keys)."""
    b1 = RunBundle(root=tmp_path / "a").create()
    b2 = RunBundle(root=tmp_path / "b").create()
    meta = RunMetadata(demo_id="d", model="m", runtimes={"b": "2", "a": "1"})
    b1.write_metadata(meta)
    b2.write_metadata(meta)
    assert b1.metadata_path.read_bytes() == b2.metadata_path.read_bytes()
