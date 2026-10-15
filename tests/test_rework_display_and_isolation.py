"""Display fidelity (Markdown, pages, command budget) and capture isolation."""

import json
from pathlib import Path

from demoforge.capture.conversation import converse, parse_reply
from demoforge.capture.isolation import audit, deny_rules, fingerprints
from demoforge.capture.normalize import normalize
from demoforge.capture.run import _scrub_account, _scrub_saved_output, approve_run, run_demo
from demoforge.model import Event
from demoforge.redact import PathRewriter
from demoforge.render import markdown
from demoforge.render.config import Limits, VideoEncode
from demoforge.render.timeline import build_timeline, paginate
from demoforge.render.config import load_settings
from demoforge.staleness import approved_staleness

from test_capture_hardening import _PRODUCED, _set_with
from test_conversation import _turn
from test_run import WHEN


# ---- Markdown ----------------------------------------------------------
def test_markdown_renders_what_claude_writes_and_escapes_the_rest():
    src = (
        "**Bold** and `x < y` <script>alert(1)</script>\n\n"
        "- **R1:** first\n- second\n\n"
        "| Constant | Error |\n|---|---|\n| `Q` | 1.5e-2 |\n\n"
        "```\nerror: R3 <failed>\n```"
    )
    html = markdown.to_html(src)
    assert "<strong>Bold</strong>" in html and "<code>x &lt; y</code>" in html
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert '<ul class="md-list"><li><strong>R1:</strong> first</li><li>second</li></ul>' in html
    assert "<th>Constant</th>" in html and "<td><code>Q</code></td>" in html
    assert '<pre class="md-code">error: R3 &lt;failed&gt;</pre>' in html
    assert "**" not in html and "```" not in html


def test_markdown_bold_can_wrap_code_and_code_stays_literal():
    out = markdown.to_html("**`kalman_update.m`** uses `a*b*c` and `<i>`")
    assert "<strong><code>kalman_update.m</code></strong>" in out
    assert "<code>a*b*c</code>" in out
    assert "<code>&lt;i&gt;</code>" in out
    assert "**" not in out


def test_markdown_blocks_keep_lists_tables_and_code_whole():
    kinds = [b.kind for b in markdown.blocks("Intro.\n- a\n- b\n\n```\nx\n\ny\n```\n# Head")]
    assert kinds == ["p", "ul", "code", "h"]


# ---- pagination ----------------------------------------------------------
def _words(text):
    return markdown.plain(text).replace("|", " ").replace("-", " ").split()


def test_pagination_never_drops_or_cuts_a_word():
    limits = Limits(text_page_lines=4, text_line_chars=40)
    text = (
        "First paragraph that is long enough to wrap across a couple of lines here. "
        "And a second sentence.\n\n- one\n- two\n- three\n- four\n- five\n\n"
        "| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n| 5 | 6 |\n| 7 | 8 |"
    )
    pages = paginate(text, limits)
    assert len(pages) > 1
    for page in pages:
        # every table part keeps its header row and rule, so each renders as a table
        if "|" in page:
            assert "| a | b |" in page and "|---|---|" in page

    def body(t):  # the text without the table header each part repeats
        return _words("\n".join(l for l in t.split("\n") if l not in ("| a | b |", "|---|---|")))

    assert body("\n\n".join(pages)) == body(text)


def test_long_answer_becomes_pages_of_the_same_event():
    st = load_settings()
    long = "\n\n".join(f"Paragraph {i}. " + "word " * 60 for i in range(8))
    tl = build_timeline(
        "demo",
        [Event(seq=0, t=0.0, type="prompt", data={"text": "go"}),
         Event(seq=1, t=1.0, type="assistant_text", data={"text": long})],
        scenes=st.scenes, timing=st.timing,
    )
    pages = [s for s in tl.scenes if s.kind == "NarratedText"]
    assert len(pages) > 1 and all(s.event_seqs == (1,) for s in pages)
    assert [s.data["page"] for s in pages] == list(range(1, len(pages) + 1))
    assert all(s.data["pages"] == len(pages) for s in pages)


def test_a_long_command_shares_the_terminal_budget_and_says_it_was_cut():
    st = load_settings()
    lim = st.scenes.limits
    cmd = "\n".join(f"step {i}" for i in range(20))
    out = "\n".join(f"FAIL {i}" for i in range(6))
    tl = build_timeline(
        "demo",
        [Event(seq=0, t=0.0, type="command", data={"command": cmd}),
         Event(seq=1, t=12.0, type="command_output", data={"output": out})],
        scenes=st.scenes, timing=st.timing,
    )
    data = tl.scenes[0].data
    assert data["command_cut"] and len(data["command"].splitlines()) == lim.terminal_command_max_lines
    assert data["output_lines"] == [f"FAIL {i}" for i in range(6)]


def test_real_time_is_only_what_the_record_measures():
    st = load_settings()
    tl = build_timeline(
        "demo",
        [Event(seq=0, t=0.0, type="command", data={"command": "make"}),
         Event(seq=1, t=12.0, type="command_output", data={"output": "ok"}),
         Event(seq=2, t=40.0, type="assistant_text", data={"text": "Built."}),
         Event(seq=3, t=90.0, type="completion", data={})],
        scenes=st.scenes, timing=st.timing, clocked=True,
    )
    by_kind = {s.kind: s.real_seconds for s in tl.scenes}
    # 12s for the command; nothing for the 28s and 50s of composing that follow.
    assert by_kind["TerminalRun"] == 12.0 and by_kind["NarratedText"] == 0.0


def test_chapter_end_counts_the_persons_follow_ups():
    st = load_settings()
    tl = build_timeline(
        "demo",
        [Event(seq=0, t=0.0, type="prompt", data={"text": "go"}),
         Event(seq=1, t=1.0, type="user_message", data={"text": "why?"}),
         Event(seq=2, t=2.0, type="user_done", data={"reason": "satisfied"}),
         Event(seq=3, t=3.0, type="completion", data={"num_turns": 5})],
        scenes=st.scenes, timing=st.timing,
    )
    assert tl.scenes[-1].data["follow_ups"] == 1
    assert "user_done" not in [s.kind for s in tl.scenes]


# ---- paths -------------------------------------------------------------
def test_path_rules_cover_claude_codes_project_folder_spelling():
    r = PathRewriter({r"C:\DemoForgeSandbox": r"G:\Willikers\sandbox"})
    assert r("projects\\C--DemoForgeSandbox-demoforge-x\\a") == "projects\\G--Willikers-sandbox-demoforge-x\\a"
    assert r("C--DemoForgeSandboxes") == "C--DemoForgeSandboxes"


def test_saved_output_path_with_the_session_id_is_replaced():
    raw = ("Full output saved to: C:\\Users\\you\\.claude\\projects\\C--x-working\\"
           "85ac6ed3-d9a6\\tool-results\\b.txt\n\nPreview")
    for text in (raw, json.dumps(raw)):
        clean = _scrub_saved_output(text)
        assert "85ac6ed3" not in clean and "<output saved by Claude Code>" in clean
        assert "Preview" in clean


def test_approve_keeps_only_that_reasoning_happened():
    rec = {"type": "assistant", "message": {"content": [
        {"type": "thinking", "thinking": "secret plan", "signature": "abc"},
        {"type": "text", "text": "Hello"},
    ]}}
    out = _scrub_account(rec)
    assert out["message"]["content"][0] == {"type": "thinking", "thinking": "", "removed": True}
    assert out["message"]["content"][1]["text"] == "Hello"


# ---- conversation endings ---------------------------------------------
def test_how_the_conversation_ended_is_recorded():
    lines, _ = converse("go", None, lambda m, w, **kw: _turn("ok"),
                        responder=lambda v: None, max_follow_ups=2)
    events = normalize("go", [(float(i), json.loads(l)) for i, l in enumerate(lines)])
    assert [e.type for e in events][-2:] == ["user_done", "completion"]
    assert events[-2].data == {"reason": "satisfied"}

    lines, _ = converse("go", None, lambda m, w, **kw: _turn("ok"),
                        responder=lambda v: "again", max_follow_ups=1)
    assert json.loads(lines[-1]) == {"type": "user_done", "reason": "limit"}


def test_parse_reply_accepts_a_done_with_words_but_not_a_question():
    assert parse_reply("Done, looks good.") is None
    assert parse_reply("DONE - merging it") is None
    assert parse_reply("Done? Not yet: what about R?") == "Done? Not yet: what about R?"
    assert parse_reply("Donezo is not a word") == "Donezo is not a word"


# ---- isolation ---------------------------------------------------------
def _tool_use(cmd):
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "1", "name": "Bash", "input": {"command": cmd}}]}}


def test_audit_flags_a_look_inside_the_repository_or_at_a_hidden_check():
    repo = Path(r"C:\Repo")
    found = audit(
        {"agent": [_tool_use("cat /c/Repo/demos/x/checks/run_tests.m"), _tool_use("ls")],
         "user simulator turn-1": [_tool_use("grep mut_cvt_filter .")]},
        [repo], ["mut_cvt_filter.m", "mut_cvt_filter"],
    )
    assert [(f.source, f.record) for f in found] == [("agent", 0), ("user simulator turn-1", 0)]
    assert "inside the repository" in found[0].reason and "hidden check" in found[1].reason


def _assistant_tool(name, **tool_input):
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": name, "name": name, "input": tool_input}]}}


def test_write_and_edit_cards_show_the_recorded_code():
    from demoforge.capture.normalize import with_file_changes

    events = [
        Event(seq=0, t=0.0, type="file_write", data={"tool": "Write", "path": "/w/f.m"}),
        Event(seq=1, t=1.0, type="file_edit", data={"tool": "Edit", "path": "/w/f.m"}),
    ]
    objs = [
        _assistant_tool("Write", file_path="/w/f.m", content="a = 1;\nb = 2;\nc = 3;\n"),
        _assistant_tool("Edit", file_path="/w/f.m", old_string="a = 1;\nb = 2;", new_string="a = 1;\nb = 4;"),
    ]
    events = with_file_changes(events, objs)
    st = load_settings()
    tl = build_timeline("demo", events, scenes=st.scenes, timing=st.timing)
    write, edit = tl.scenes
    assert [r["text"] for r in write.data["code_lines"]] == ["a = 1;", "b = 2;", "c = 3;"]
    assert [(r["sign"], r["text"]) for r in edit.data["code_lines"]] == [
        (" ", "a = 1;"), ("-", "b = 2;"), ("+", "b = 4;")]


def test_attaching_code_refuses_a_mismatched_record():
    from demoforge.capture.normalize import with_file_changes

    events = [Event(seq=0, t=0.0, type="file_write", data={"tool": "Write", "path": "/w/f.m"})]
    try:
        with_file_changes(events, [_assistant_tool("Write", file_path="/w/other.m", content="x")])
    except ValueError:
        return
    raise AssertionError("a write paired with another file's tool call was accepted")


def test_result_card_shows_each_checks_limit_beside_its_value():
    from demoforge.model.demo import Check
    from demoforge.render.frames import check_limits

    checks = [
        Check.from_dict({"id": "correct", "kind": "numeric_tolerance", "max_abs_error": 1e-6}),
        Check.from_dict({"id": "teeth", "kind": "threshold", "metric": "m", "min": 1}),
        Check.from_dict({"id": "runtime", "kind": "metric"}),
    ]
    assert check_limits(checks) == {"correct": "≤ 1e-06", "teeth": "≥ 1"}


def test_frames_turn_off_font_ligatures():
    from demoforge.render.frames import scene_markup
    from test_frames import _context, _timeline as frames_timeline

    tl = frames_timeline()
    _scene, html = next(iter(scene_markup(tl, _context(tl), VideoEncode())))
    assert "font-variant-ligatures: none" in html


def test_long_listings_lose_their_owner_and_group():
    from demoforge.redact import scrub_file_owners

    raw = "total 53\ndrwxr-xr-x 1 alice 197609     0 Oct 14 17:46 .\n-rw-r--r--@ 1 alice staff 301 Oct  4 m.json\n"
    for text in (raw, json.dumps({"stdout": raw})):
        out = scrub_file_owners(text)
        assert "alice" not in out and "197609" not in out and "staff" not in out
    assert json.loads(scrub_file_owners(json.dumps({"o": raw})))["o"] == scrub_file_owners(raw)
    assert scrub_file_owners("chmod -rwxr-xr-x file") == "chmod -rwxr-xr-x file"


def _tool_result(text):
    return {"type": "user", "message": {"content": [{"type": "tool_result", "content": text}]}}


def test_audit_finds_hidden_content_even_when_no_path_or_name_is_shown(tmp_path):
    hidden = tmp_path / "expected.csv"
    hidden.write_text("1.2345678901,2.3456789012,3.4567890123\nX = f(Z, model);\n", encoding="utf-8")
    spec = "Implement exactly X = f(Z, model) as specified."
    lines = fingerprints([hidden], [spec])
    # The spec's own call, written with a semicolon, is not a hidden line.
    assert lines == ["1.2345678901,2.3456789012,3.4567890123"]
    found = audit(
        {"agent": [_tool_result("ok\n1.2345678901,2.3456789012,3.4567890123\n"),
                   _tool_result("X = f(Z, model);")]},
        [], [], lines,
    )
    assert [(f.record, f.reason) for f in found] == [(0, "contains a line of a hidden file")]


def test_approve_records_a_fresh_audit_and_the_git_state_from_the_start(tmp_path):
    cs = _set_with(tmp_path, checks=_PRODUCED)
    demo = cs.demos()[0]

    def invoke(prompt, work_dir, **kw):
        (work_dir / "result.out").write_text("done", encoding="utf-8")
        return _turn("ok")

    result = run_demo(demo, cs, when=WHEN, git_commit="abc", invoker=invoke)
    meta = result.bundle.read_metadata()
    assert meta.git_commit == "abc" and meta.git_dirty is None
    dest = approve_run(cs, demo.id, run_id=result.run_id)
    frozen = json.loads((dest / "metadata.json").read_text(encoding="utf-8"))
    assert frozen["extra"]["isolation_at_approve"]["clean"] is True


def test_deny_rules_name_absolute_paths_for_the_file_tools():
    rules = deny_rules([Path("C:/Repo/sub")]).split(",")
    assert rules == ["Read(//c/Repo/sub/**)", "Edit(//c/Repo/sub/**)"]


# ---- the brief is part of the record -------------------------------------
def test_user_brief_is_frozen_hashed_and_tracked_for_staleness(tmp_path):
    cs = _set_with(tmp_path, checks=_PRODUCED)
    demo = cs.demos()[0]
    (demo.dir / "user.md").write_text("You are the lead engineer.", encoding="utf-8")
    yaml = demo.dir / "demo.yaml"
    yaml.write_text(yaml.read_text(encoding="utf-8") + "user: user.md\n", encoding="utf-8")
    demo = cs.demos()[0]

    def invoke(prompt, work_dir, **kw):
        (work_dir / "result.out").write_text("done", encoding="utf-8")
        return _turn("ok")

    result = run_demo(demo, cs, when=WHEN, git_commit="x", invoker=invoke, responder=lambda v: None)
    meta = result.bundle.read_metadata()
    assert meta.user_hash and meta.extra["max_follow_ups"] == 3
    assert meta.extra["user_simulator_prompt"].startswith("sha256:")
    assert meta.extra["isolation"]["clean"] is True
    dest = approve_run(cs, demo.id, run_id=result.run_id)
    assert (dest / "user.md").read_text(encoding="utf-8") == "You are the lead engineer."
    assert not approved_staleness(cs, demo).is_stale

    (demo.dir / "user.md").write_text("You are someone else.", encoding="utf-8")
    st = approved_staleness(cs, demo)
    assert st.is_stale and "user.md changed since capture" in st.reasons()
