"""approve removes the machine's own paths from the bundle it freezes."""

from __future__ import annotations

import json
from pathlib import Path

from demoforge.capture import approve_run, run_demo
from demoforge.redact import PATH_LIST_PLACEHOLDER, scrub_path_lists

from test_capture_hardening import _PRODUCED, _set_with
from test_run import WHEN

HOME = str(Path.home())
POSIX_HOME = "/" + HOME[0].lower() + HOME[2:].replace("\\", "/")


# ---- search-path listings ------------------------------------------------
def test_posix_path_list_inside_json_is_removed():
    out = json.dumps({"output": (
        "which: no octave in (/c/Users/u/bin:/mingw64/bin:/usr/bin:"
        "/c/Program Files/Git/cmd:/c/Program Files (x86)/Nmap)\nnext line"
    )})
    clean = scrub_path_lists(out)
    assert "Nmap" not in clean and "mingw64" not in clean
    assert PATH_LIST_PLACEHOLDER in clean
    assert json.loads(clean)["output"].endswith("\nnext line")  # stops at the escape


def test_windows_path_list_is_removed_and_stops_at_the_string():
    out = json.dumps({"output": "C:\\Windows;C:\\Windows\\System32;C:\\a;C:\\b;C:\\Tools\\x\n"})
    clean = scrub_path_lists(out)
    assert json.loads(clean)["output"] == PATH_LIST_PLACEHOLDER + "\n"


def test_short_lists_urls_and_single_paths_are_kept():
    for text in (
        "/usr/bin:/bin",                       # too short to be a machine's PATH
        "see https://example.com/a/b/c/d/e",
        "C:\\Playground\\x;C:\\y",
        "ratio 1:2:3:4:5",
    ):
        assert scrub_path_lists(text) == text


# ---- approve -------------------------------------------------------------
def test_approve_scrubs_home_and_path_lists_but_run_keeps_original(tmp_path):
    cs = _set_with(tmp_path, checks=_PRODUCED)
    leak = f"{POSIX_HOME}/bin:/mingw64/bin:/usr/bin:/c/Tools/a:/c/Tools/b"

    def invoke(prompt, work_dir):
        (work_dir / "result.out").write_text(f"built in {HOME}\\x", encoding="utf-8")
        return [
            json.dumps({"type": "system", "subtype": "init", "model": "m"}),
            json.dumps({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "which octave"}},
            ]}}),
            json.dumps({"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "t1",
                 "content": f"which: no octave in ({leak})\nalso {HOME}\\AppData\n"
                            f"{POSIX_HOME}/AppData/x.exe\n{POSIX_HOME}/AppData/y.exe"},
            ]}}),
            json.dumps({"type": "result", "subtype": "success", "is_error": False}),
        ]

    result = run_demo(cs.demos()[0], cs, when=WHEN, git_commit="x", invoker=invoke)
    assert result.passed
    dest = approve_run(cs, "synth", run_id=result.run_id)

    home_variants = (HOME.lower(), HOME.lower().replace("\\", "\\\\"), POSIX_HOME.lower())
    for f in dest.rglob("*"):
        if f.is_file():
            text = f.read_text(encoding="utf-8").lower()
            assert not any(h in text for h in home_variants), f
            assert "mingw64" not in text, f
    events = (dest / "events.jsonl").read_text(encoding="utf-8")
    assert PATH_LIST_PLACEHOLDER in events and "~\\\\AppData" in events
    assert (dest / "artifacts" / "result.out").read_text(encoding="utf-8") == "built in ~\\x"
    meta = json.loads((dest / "metadata.json").read_text(encoding="utf-8"))
    assert "search-path" in meta["extra"]["redaction"]

    # The local run, which is never committed, keeps what really happened.
    assert "mingw64" in result.bundle.events_path.read_text(encoding="utf-8")


def test_approve_drops_account_details_from_raw_transcript(tmp_path):
    cs = _set_with(tmp_path, checks=_PRODUCED)

    def invoke(prompt, work_dir):
        (work_dir / "result.out").write_text("done", encoding="utf-8")
        return [
            json.dumps({"type": "system", "subtype": "init", "model": "m", "session_id": "s1",
                        "tools": ["Bash", "SecretTool"], "capabilities": ["x"],
                        "claude_code_version": "9.9"}),
            json.dumps({"type": "rate_limit_event", "session_id": "s1",
                        "rate_limit_info": {"utilization": 0.4}}),
            json.dumps({"type": "assistant", "session_id": "s1", "request_id": "r1",
                        "message": {"content": [{"type": "text", "text": "ok"}]}}),
            json.dumps({"type": "result", "subtype": "success", "is_error": False,
                        "session_id": "s1", "total_cost_usd": 0.5,
                        "modelUsage": {"m": {"costUSD": 0.5}}, "num_turns": 1}),
        ]

    result = run_demo(cs.demos()[0], cs, when=WHEN, git_commit="x", invoker=invoke)
    dest = approve_run(cs, "synth", run_id=result.run_id)
    raw = (dest / "transcript.jsonl").read_text(encoding="utf-8")
    for leak in ("rate_limit", "utilization", "session_id", "request_id", "cost", "SecretTool", "capabilities"):
        assert leak not in raw, leak
    records = [json.loads(l) for l in raw.splitlines()]
    assert [r["type"] for r in records] == ["system", "assistant", "result"]
    assert records[0]["claude_code_version"] == "9.9" and records[2]["num_turns"] == 1
    assert "SecretTool" in result.bundle.transcript_jsonl_path.read_text(encoding="utf-8")
