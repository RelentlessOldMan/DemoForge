"""End-to-end run capture + approval, using an injected invoker (no live agent)."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone

import pytest

from conftest import CLAUDE_DEMO_KIT, OCTAVE, requires_octave

from demoforge.capture import approve_run, run_demo
from demoforge.discovery import load_content_set
from demoforge.errors import DemoForgeError

WHEN = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)


# ---- synthetic content set (no runtime) --------------------------------
def _synth_set(tmp_path):
    root = tmp_path / "set"
    demo = root / "demos" / "synth"
    (demo / "input").mkdir(parents=True)
    (demo / "input" / "seed.txt").write_text("seed", encoding="utf-8")
    (demo / "prompt.md").write_text("Produce result.out", encoding="utf-8")
    (demo / "demo.yaml").write_text(
        "id: synth\ntitle: Synth\nruntime: none\n"
        "inputs:\n  - input/seed.txt\n"
        "checks:\n  - id: produced\n    kind: file_exists\n    pattern: result.out\n",
        encoding="utf-8",
    )
    (root / "demoforge.toml").write_text('[set]\nid = "synth-set"\n', encoding="utf-8")
    return load_content_set(root)


def _stream(*, produced: bool):
    lines = [
        json.dumps({"type": "system", "subtype": "init", "model": "claude-test"}),
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "Working on it."},
            {"type": "tool_use", "id": "t1", "name": "Write", "input": {"file_path": "result.out"}},
        ]}}),
        json.dumps({"type": "result", "subtype": "success", "is_error": False}),
    ]
    if not produced:
        # Agent "wrote" nothing useful.
        lines = [lines[0], lines[-1]]
    return lines


def _invoker(produced: bool):
    def invoke(prompt, work_dir):
        if produced:
            (work_dir / "result.out").write_text("done", encoding="utf-8")
        return _stream(produced=produced)
    return invoke


def test_run_pipeline_builds_verified_bundle(tmp_path):
    cs = _synth_set(tmp_path)
    demo = cs.demos()[0]
    result = run_demo(demo, cs, invoker=_invoker(True), when=WHEN, git_commit="deadbeef")

    assert result.passed is True
    b = result.bundle
    assert b.metadata_path.exists() and b.events_path.exists()
    assert b.results_path.exists() and b.prompt_path.exists()
    assert b.transcript_md_path.exists() and b.transcript_jsonl_path.exists()

    # Events normalized, prompt synthesized.
    types = [e.type for e in result.events]
    assert types[0] == "prompt"
    assert "file_write" in types and types[-1] == "completion"
    assert b.read_events() == result.events

    # Artifacts: produced file captured, staged input excluded.
    assert (b.artifacts_dir / "result.out").exists()
    assert not (b.artifacts_dir / "seed.txt").exists()

    # Metadata recorded.
    meta = b.read_metadata()
    assert meta.model == "claude-test"
    assert meta.git_commit == "deadbeef"
    assert meta.created == "2026-09-30T12:00:00Z"
    assert meta.prompt_hash and "seed.txt" in meta.input_hashes

    # Readable transcript.
    assert "## Prompt" in b.transcript_md_path.read_text(encoding="utf-8")


def test_the_agent_works_outside_the_content_set_and_the_result_is_kept(tmp_path):
    """A work dir inside the repo lets a wandering agent find the hidden checks."""
    cs = _synth_set(tmp_path)
    seen = {}

    def invoke(prompt, work_dir):
        seen["dir"] = work_dir
        seen["staged"] = sorted(p.name for p in work_dir.iterdir())
        (work_dir / "result.out").write_text("done", encoding="utf-8")
        return _stream(produced=True)

    result = run_demo(cs.demos()[0], cs, invoker=invoke, when=WHEN)

    agent_dir = seen["dir"].resolve()
    assert cs.root.resolve() not in agent_dir.parents
    assert agent_dir.name == "working"  # recorded paths still display relative to it
    assert seen["staged"] == ["seed.txt"]
    assert not agent_dir.exists(), "the scratch copy is cleaned up"
    # Everything the agent left behind is in the bundle, and it verified from there.
    assert (result.bundle.root / "working" / "result.out").is_file()
    assert result.passed is True


def test_run_id_is_deterministic_for_same_prompt(tmp_path):
    cs = _synth_set(tmp_path)
    demo = cs.demos()[0]
    r1 = run_demo(demo, cs, invoker=_invoker(True), when=WHEN, git_commit="x")
    r2 = run_demo(demo, cs, invoker=_invoker(True), when=WHEN, git_commit="x")
    assert r1.run_id == r2.run_id


def test_approve_refuses_failing_run_then_force(tmp_path):
    cs = _synth_set(tmp_path)
    demo = cs.demos()[0]
    result = run_demo(demo, cs, invoker=_invoker(False), when=WHEN, git_commit="x")
    assert result.passed is False

    with pytest.raises(DemoForgeError, match="refusing to approve"):
        approve_run(cs, demo.id, run_id=result.run_id)

    dest = approve_run(cs, demo.id, run_id=result.run_id, force=True)
    assert (dest / "metadata.json").exists()
    assert (dest / "results.json").exists()


def test_approve_failure_preserves_existing_bundle(tmp_path, monkeypatch):
    """A failed re-approval must not destroy the previously-approved bundle.

    Regression: approve used to rmtree approved/ before copying, so a mid-copy
    failure left it empty/partial — violating the immutability invariant.
    """
    import demoforge.capture.run as runmod

    cs = _synth_set(tmp_path)
    demo = cs.demos()[0]
    result = run_demo(demo, cs, invoker=_invoker(True), when=WHEN, git_commit="x")
    dest = approve_run(cs, demo.id, run_id=result.run_id)
    good = (dest / "metadata.json").read_text(encoding="utf-8")
    assert (dest / "artifacts" / "result.out").exists()

    # Re-approve, but force every file copy to fail partway through the freeze.
    real_copy2 = shutil.copy2
    monkeypatch.setattr(
        runmod.shutil, "copy2",
        lambda *a, **k: (_ for _ in ()).throw(OSError("simulated disk failure")),
    )
    with pytest.raises(OSError):
        approve_run(cs, demo.id, run_id=result.run_id)
    monkeypatch.setattr(runmod.shutil, "copy2", real_copy2)

    # The original approved bundle is still complete and unchanged.
    assert (dest / "metadata.json").read_text(encoding="utf-8") == good
    assert (dest / "results.json").exists()
    assert (dest / "artifacts" / "result.out").exists()
    # No staging/backup scratch left behind.
    leftovers = [p.name for p in dest.parent.iterdir() if p.name.startswith(".")]
    assert leftovers == []


def test_approve_swap_failure_restores_prior_bundle(tmp_path, monkeypatch):
    """If the final atomic swap fails, the prior approved bundle is restored.

    Covers the rollback branch: the new bundle assembled cleanly, dest was moved
    aside, but moving the new one in failed — the old bundle must come back.
    """
    import os
    import demoforge.capture.run as runmod

    cs = _synth_set(tmp_path)
    demo = cs.demos()[0]
    result = run_demo(demo, cs, invoker=_invoker(True), when=WHEN, git_commit="x")
    dest = approve_run(cs, demo.id, run_id=result.run_id)
    good = (dest / "metadata.json").read_text(encoding="utf-8")

    real_replace = os.replace
    state = {"n": 0}

    def flaky_replace(src, dst):
        state["n"] += 1
        if state["n"] == 2:  # the staging -> dest swap (after dest -> backup)
            raise OSError("simulated rename failure")
        return real_replace(src, dst)

    monkeypatch.setattr(runmod.os, "replace", flaky_replace)
    with pytest.raises(OSError):
        approve_run(cs, demo.id, run_id=result.run_id)
    monkeypatch.setattr(runmod.os, "replace", real_replace)

    assert (dest / "metadata.json").read_text(encoding="utf-8") == good
    assert (dest / "artifacts" / "result.out").exists()
    leftovers = [p.name for p in dest.parent.iterdir() if p.name.startswith(".")]
    assert leftovers == []


def test_claude_invoker_wraps_launch_and_timeout(tmp_path, monkeypatch):
    """A launch failure or timeout becomes a clean DemoForgeError, not a traceback."""
    import subprocess
    import demoforge.capture.run as runmod
    from demoforge.capture.run import default_claude_invoker

    monkeypatch.setattr(
        runmod.shutil, "which", lambda _bin, path=None: str(tmp_path / "claude.exe")
    )

    def timeout_run(*a, **k):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=1)

    monkeypatch.setattr(runmod, "_stream_timed", timeout_run)
    with pytest.raises(DemoForgeError, match="did not finish"):
        default_claude_invoker(timeout=1.0)("prompt", tmp_path)

    def oserror_run(*a, **k):
        raise OSError("boom")

    monkeypatch.undo()
    monkeypatch.setattr(
        runmod.shutil, "which", lambda _bin, path=None: str(tmp_path / "claude.exe")
    )
    monkeypatch.setattr(runmod.subprocess, "Popen", oserror_run)
    with pytest.raises(DemoForgeError, match="failed to launch"):
        default_claude_invoker()("prompt", tmp_path)


def test_approve_is_idempotent(tmp_path):
    """Approving the same passing run twice yields an identical bundle."""
    cs = _synth_set(tmp_path)
    demo = cs.demos()[0]
    result = run_demo(demo, cs, invoker=_invoker(True), when=WHEN, git_commit="x")
    first = approve_run(cs, demo.id, run_id=result.run_id)
    meta1 = (first / "metadata.json").read_text(encoding="utf-8")
    second = approve_run(cs, demo.id, run_id=result.run_id)
    assert second == first
    assert (second / "metadata.json").read_text(encoding="utf-8") == meta1
    assert (second / "artifacts" / "result.out").exists()


def test_approve_without_runs_errors(tmp_path):
    cs = _synth_set(tmp_path)
    with pytest.raises(DemoForgeError, match="no runs for demo"):
        approve_run(cs, cs.demos()[0].id)


def test_approve_unknown_run_id_errors(tmp_path):
    cs = _synth_set(tmp_path)
    demo = cs.demos()[0]
    run_demo(demo, cs, invoker=_invoker(True), when=WHEN, git_commit="x")
    with pytest.raises(DemoForgeError, match="not a run bundle"):
        approve_run(cs, demo.id, run_id="20260101T000000Z-deadbeef")


def test_approve_defaults_to_latest_run(tmp_path):
    cs = _synth_set(tmp_path)
    demo = cs.demos()[0]
    run_demo(demo, cs, invoker=_invoker(True),
             when=datetime(2026, 9, 30, 10, 0, 0, tzinfo=timezone.utc), git_commit="x")
    late = run_demo(demo, cs, invoker=_invoker(True),
                    when=datetime(2026, 9, 30, 11, 0, 0, tzinfo=timezone.utc), git_commit="x")
    dest = approve_run(cs, demo.id)  # no run_id -> latest
    approved_events = (dest / "events.jsonl").read_text(encoding="utf-8")
    assert approved_events == late.bundle.events_path.read_text(encoding="utf-8")


# ---- real Demo 2 on Octave (cloned into a temp set) --------------------
@requires_octave
def test_run_and_approve_demo2(tmp_path):
    src = CLAUDE_DEMO_KIT / "demos" / "02_matlab_optimization"
    root = tmp_path / "set"
    (root / "demos").mkdir(parents=True)
    shutil.copytree(src, root / "demos" / "02_matlab_optimization")
    (root / "demoforge.toml").write_text(
        f'[set]\nid = "t"\n\n[runtimes]\noctave = {json.dumps(str(OCTAVE))}\n',
        encoding="utf-8",
    )
    cs = load_content_set(root)
    demo = cs.demos()[0]

    def invoke(prompt, work_dir):
        # Simulate the agent producing the optimized implementation.
        for f in (src / "reference").iterdir():
            shutil.copy2(f, work_dir / f.name)
        return _stream(produced=True)

    result = run_demo(demo, cs, invoker=invoke, when=WHEN, git_commit="x", octave_bin=OCTAVE)
    assert result.passed is True
    assert result.outcome.metrics["speedup"] >= 3.0
    assert (result.bundle.artifacts_dir / "kalman_update_fast.m").exists()

    dest = approve_run(cs, demo.id, run_id=result.run_id)
    assert (dest / "artifacts" / "kalman_update_fast.m").exists()
    assert (dest / "results.json").exists()
    assert not (dest / "working").exists()  # scratch not frozen
