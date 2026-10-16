"""Capture isolation, honest timing, and approval guards (the 2026-10 review)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import pytest

from demoforge.capture import approve_run, run_demo
from demoforge.capture import run as runmod
from demoforge.config import ContentSetConfig
from demoforge.discovery import load_content_set
from demoforge.errors import ConfigError, CheckError, DemoForgeError
from demoforge.model import Check

from test_run import WHEN, _stream, _synth_set


def _set_with(tmp_path, *, checks: str, harness: str | None = None, inputs: dict | None = None):
    root = tmp_path / "set"
    demo = root / "demos" / "synth"
    (demo / "input").mkdir(parents=True)
    inputs = inputs or {"seed.txt": "seed"}
    for rel, text in inputs.items():
        p = demo / "input" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    (demo / "prompt.md").write_text("do it", encoding="utf-8")
    yaml = "id: synth\ntitle: Synth\nruntime: python\n" if harness else "id: synth\ntitle: Synth\nruntime: none\n"
    yaml += "inputs:\n" + "".join(f"  - input/{rel}\n" for rel in inputs)
    if harness:
        (demo / "checks").mkdir()
        (demo / "checks" / "harness.py").write_text(harness, encoding="utf-8")
        yaml += "harness: checks/harness.py\n"
    yaml += "checks:\n" + checks
    (demo / "demo.yaml").write_text(yaml, encoding="utf-8")
    (root / "demoforge.toml").write_text(
        f'[set]\nid = "s"\n[runtimes]\npython = {json.dumps(sys.executable)}\n', encoding="utf-8"
    )
    return load_content_set(root)


_PRODUCED = "  - id: produced\n    kind: file_exists\n    pattern: result.out\n"


def _writes(files: dict, lines=None):
    def invoke(prompt, work_dir):
        for rel, text in files.items():
            p = work_dir / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        return lines if lines is not None else _stream(produced=True)
    return invoke


# ---- artifacts ---------------------------------------------------------
def test_nested_and_edited_inputs_are_artifacts(tmp_path):
    cs = _set_with(tmp_path, checks=_PRODUCED, inputs={"seed.txt": "seed", "src/gate.m": "old"})
    result = run_demo(cs.demos()[0], cs, when=WHEN, git_commit="x", invoker=_writes({
        "result.out": "done", "src/gate.m": "fixed", "out/report.md": "r",
        "__pycache__/x.pyc": "junk",
    }))
    art = result.bundle.artifacts_dir
    assert (art / "src" / "gate.m").read_text(encoding="utf-8") == "fixed"
    assert (art / "out" / "report.md").exists()
    assert not (art / "seed.txt").exists()  # untouched input
    assert not (art / "__pycache__").exists()


def test_verify_sees_the_edited_input_not_the_original(tmp_path):
    check = ("  - id: fixed\n    kind: contains\n    file: src/gate.m\n    text: fixed\n")
    cs = _set_with(tmp_path, checks=check, inputs={"src/gate.m": "old"})
    result = run_demo(cs.demos()[0], cs, when=WHEN, git_commit="x",
                      invoker=_writes({"src/gate.m": "fixed"}))
    assert result.passed


# ---- harness authority -------------------------------------------------
_METRIC = "  - id: fast\n    kind: threshold\n    metric: speedup\n    min: 2\n"


def test_failed_harness_fails_results_and_blocks_approve(tmp_path):
    cs = _set_with(tmp_path, checks=_METRIC, harness="raise SystemExit(3)\n")
    # The agent leaves its own flattering metrics behind; they must not count.
    result = run_demo(cs.demos()[0], cs, when=WHEN, git_commit="x",
                      invoker=_writes({"metrics.json": '{"speedup": 99}'}))
    assert not result.passed
    saved = result.bundle.read_results()
    assert not saved.passed
    assert any(c.id == "harness" and c.passed is False for c in saved.checks)
    fast = next(c for c in saved.checks if c.id == "fast")
    assert fast.passed is False  # agent's metrics.json was discarded
    with pytest.raises(DemoForgeError, match="did not pass"):
        approve_run(cs, "synth", run_id=result.run_id)


def test_harness_metrics_are_used(tmp_path):
    harness = "import json; json.dump({'speedup': 5}, open('metrics.json', 'w'))\n"
    cs = _set_with(tmp_path, checks=_METRIC, harness=harness)
    result = run_demo(cs.demos()[0], cs, when=WHEN, git_commit="x", invoker=_writes({}))
    assert result.passed


def test_verify_crash_keeps_a_complete_bundle(tmp_path, monkeypatch):
    cs = _synth_set(tmp_path)

    def boom(*a, **k):
        raise DemoForgeError("harness exploded")

    monkeypatch.setattr(runmod, "verify_demo", boom)
    result = run_demo(cs.demos()[0], cs, when=WHEN, git_commit="x", invoker=_writes({"result.out": "d"}))
    assert result.bundle.metadata_path.exists()
    assert result.bundle.read_metadata().extra["run_id"] == result.run_id
    assert not result.bundle.read_results().passed
    assert "exploded" in result.bundle.read_results().checks[0].message


# ---- recorded stream ---------------------------------------------------
def test_private_init_fields_are_not_recorded(tmp_path):
    cs = _synth_set(tmp_path)
    init = {"type": "system", "subtype": "init", "model": "m", "cwd": "x",
            "mcp_servers": [{"name": "secret"}], "skills": ["mine"], "plugins": ["p"],
            "memory_paths": {"auto": "C:/Users/me/memory"}}
    lines = [json.dumps(init), *_stream(produced=True)[1:]]
    result = run_demo(cs.demos()[0], cs, when=WHEN, git_commit="x",
                      invoker=_writes({"result.out": "d"}, lines))
    text = result.bundle.transcript_jsonl_path.read_text(encoding="utf-8")
    for leak in ("secret", "mine", "memory_paths", "mcp_servers"):
        assert leak not in text
    assert '"model": "m"' in text


def test_untimed_stream_is_marked_and_timed_stream_keeps_times(tmp_path):
    cs = _synth_set(tmp_path)
    untimed = run_demo(cs.demos()[0], cs, when=WHEN, git_commit="x", run_id="a",
                       invoker=_writes({"result.out": "d"}))
    assert untimed.bundle.read_metadata().extra["event_times"] == "none"

    timed_lines = [(0.5 + 10 * i, line) for i, line in enumerate(_stream(produced=True))]
    timed = run_demo(cs.demos()[0], cs, when=WHEN, git_commit="x", run_id="b",
                     invoker=_writes({"result.out": "d"}, timed_lines))
    assert timed.bundle.read_metadata().extra["event_times"] == "wallclock"
    assert max(e.t for e in timed.events) >= 20


def test_untimed_timeline_claims_no_real_duration():
    from demoforge.model import Event
    from demoforge.render.config import load_settings
    from demoforge.render.timeline import build_timeline

    st = load_settings()
    events = [Event(seq=i, t=float(i * 100), type="assistant_text", data={"text": "hi " * 5})
              for i in range(3)]
    plain = build_timeline("d", events, scenes=st.scenes, timing=st.timing)
    assert all(s.real_seconds == 0 and not s.compressed for s in plain.scenes)
    # Measured time is a command until its output; gaps between texts are not it.
    timed = [Event(seq=0, t=0.0, type="command", data={"command": "make"}),
             Event(seq=1, t=100.0, type="command_output", data={"output": "ok"})]
    clocked = build_timeline("d", timed, scenes=st.scenes, timing=st.timing, clocked=True)
    assert any(s.real_seconds > 0 for s in clocked.scenes)
    plain = build_timeline("d", timed, scenes=st.scenes, timing=st.timing)
    assert all(s.real_seconds == 0 for s in plain.scenes)


def test_stream_timed_stamps_lines_and_times_out(tmp_path):
    script = "import sys,time\nprint('a',flush=True)\ntime.sleep(0.4)\nprint(sys.stdin.read().strip())\n"
    lines = runmod._stream_timed([sys.executable, "-c", script], "hello", tmp_path, dict(os.environ), 30)
    assert [l for _, l in lines] == ["a", "hello"]
    assert lines[1][0] - lines[0][0] >= 0.3
    with pytest.raises(subprocess.TimeoutExpired):
        runmod._stream_timed([sys.executable, "-c", "import time; time.sleep(30)"],
                             "", tmp_path, dict(os.environ), 0.5)
    with pytest.raises(DemoForgeError, match="exited 4"):
        runmod._stream_timed([sys.executable, "-c", "raise SystemExit(4)"],
                             "", tmp_path, dict(os.environ), 30)


def test_invoker_isolates_the_agent(tmp_path, monkeypatch):
    seen = {}

    def fake(cmd, prompt, cwd, env, timeout):
        seen.update(cmd=cmd, env=env)
        return []

    monkeypatch.setattr(runmod.shutil, "which", lambda _b, path=None: str(tmp_path / "claude.exe"))
    monkeypatch.setattr(runmod, "_stream_timed", fake)
    work = tmp_path / "sandbox" / "working"
    work.mkdir(parents=True)
    runmod.default_claude_invoker(env={"PATH": ""})("p", work)
    assert "--safe-mode" in seen["cmd"] and "--strict-mcp-config" in seen["cmd"]
    assert seen["env"]["GIT_CEILING_DIRECTORIES"] == str(work.parent)
    # No background jobs to die with the turn; a long command fits inside the turn.
    assert seen["env"]["CLAUDE_CODE_DISABLE_BACKGROUND_TASKS"] == "1"
    assert int(seen["env"]["BASH_MAX_TIMEOUT_MS"]) == 1_200_000


def test_sandbox_root_from_local_config(tmp_path):
    cs = _synth_set(tmp_path)
    sandbox = tmp_path / "sbx"
    (cs.root / "demoforge.local.toml").write_text(
        f"[capture]\nsandbox_root = {json.dumps(str(sandbox))}\n", encoding="utf-8")
    cs = load_content_set(cs.root)
    where = {}

    def invoke(prompt, work_dir):
        where["dir"] = work_dir
        (work_dir / "result.out").write_text("d", encoding="utf-8")
        return _stream(produced=True)

    run_demo(cs.demos()[0], cs, when=WHEN, git_commit="x", invoker=invoke)
    assert where["dir"].parent.parent == sandbox


def test_local_config_rejects_content_overrides(tmp_path):
    (tmp_path / "demoforge.toml").write_text('[set]\nid = "s"\n', encoding="utf-8")
    (tmp_path / "demoforge.local.toml").write_text('[set]\nid = "other"\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="only capture, runtimes"):
        ContentSetConfig.load(tmp_path / "demoforge.toml")


# ---- freeze ------------------------------------------------------------
def test_freeze_keeps_backup_when_rollback_fails(tmp_path, monkeypatch):
    cs = _synth_set(tmp_path)
    first = run_demo(cs.demos()[0], cs, when=WHEN, git_commit="x", run_id="r1",
                     invoker=_writes({"result.out": "d"}))
    approve_run(cs, "synth", run_id=first.run_id)
    run_demo(cs.demos()[0], cs, when=WHEN, git_commit="x", run_id="r2",
             invoker=_writes({"result.out": "d"}))

    real_replace = os.replace
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == 1:
            return real_replace(src, dst)  # dest -> backup succeeds
        raise OSError("disk said no")

    monkeypatch.setattr(runmod.os, "replace", flaky)
    with pytest.raises(DemoForgeError, match="preserved at"):
        approve_run(cs, "synth", run_id="r2")
    backup = cs.approved_dir_for("synth").parent / ".synth.backup"
    assert (backup / "metadata.json").exists()


# ---- check validation --------------------------------------------------
def test_contains_absent_and_validation(tmp_path):
    from demoforge.checks import CheckContext, run_check, validate_check

    (tmp_path / "r.md").write_text("root cause: clock drift", encoding="utf-8")
    ctx = CheckContext(work_dir=tmp_path, metrics={})
    no_decoy = Check(id="d", kind="contains", params={"file": "r.md", "text": "v2.3", "absent": True})
    assert run_check(no_decoy, ctx).passed is True
    named = Check(id="d", kind="contains", params={"file": "r.md", "text": "drift", "absent": True})
    assert run_check(named, ctx).passed is False

    with pytest.raises(CheckError):
        validate_check(Check(id="t", kind="threshold", params={"metric": "x", "min": "fast"}))
    with pytest.raises(CheckError):
        validate_check(Check(id="f", kind="file_exists", params={"pattern": "C:/x/*"}))


def test_nothing_the_agent_starts_outlives_its_turn(tmp_path):
    # The "agent" detaches a long-running child, as Start-Process or nohup would,
    # and returns at once.
    pid_file = tmp_path / "child.pid"
    flags = "creationflags=0x00000008" if os.name == "nt" else "start_new_session=True"
    script = (
        "import subprocess, sys\n"
        f"p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'], {flags})\n"
        f"open({str(pid_file)!r}, 'w').write(str(p.pid))\n"
        "print('started')\n"
    )
    lines = runmod._stream_timed([sys.executable, "-c", script], "", tmp_path, dict(os.environ), 30)
    assert [l for _, l in lines] == ["started"]
    child = int(pid_file.read_text())
    deadline = time.monotonic() + 5
    while _alive(child) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not _alive(child)


def _alive(pid: int) -> bool:
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                             capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_the_agent_is_told_nothing_runs_between_replies(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(runmod.shutil, "which", lambda _b, path=None: str(tmp_path / "claude.exe"))
    monkeypatch.setattr(runmod, "_stream_timed", lambda cmd, *a: seen.update(cmd=cmd) or [])
    work = tmp_path / "w"
    work.mkdir()
    runmod.default_claude_invoker(env={"PATH": ""})("p", work)
    note = seen["cmd"][seen["cmd"].index("--append-system-prompt") + 1]
    assert "cannot check back" in note and "20 minutes" in note
