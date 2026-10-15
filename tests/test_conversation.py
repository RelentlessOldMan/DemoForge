"""Multi-turn capture: follow-ups are real turns, recorded where they happened."""

import json

from demoforge.capture.conversation import UserView, converse, parse_reply, render_for_user
from demoforge.capture.normalize import normalize
from demoforge.capture.run import approve_run, run_demo

from test_capture_hardening import _PRODUCED, _set_with
from test_run import WHEN


def _turn(text, *, tool_cmd=None):
    content = [{"type": "text", "text": text}]
    if tool_cmd:
        content.append({"type": "tool_use", "id": "t-" + text, "name": "Bash", "input": {"command": tool_cmd}})
    return [
        json.dumps({"type": "assistant", "message": {"content": content}}),
        json.dumps({"type": "result", "subtype": "success", "is_error": False, "num_turns": 1}),
    ]


def test_converse_records_follow_ups_in_order_and_resumes():
    calls = []

    def invoker(message, work_dir, **kw):
        calls.append((message, kw))
        return [(0.5, line) for line in _turn(f"answer {len(calls)}")]

    replies = iter(["Does the test cover F too?", None])
    seen = []

    def responder(view):
        seen.append(view)
        return next(replies)

    lines, sent = converse("do it", None, invoker, responder=responder, brief="b", max_follow_ups=3)
    assert sent == 1
    assert calls == [("do it", {}), ("Does the test cover F too?", {"resume": True})]
    assert [v.follow_ups_left for v in seen] == [3, 2] and seen[0].brief == "b"
    assert "answer 1" in render_for_user(seen[0]) and "answer 2" in render_for_user(seen[1])
    times = [t for t, _ in lines]
    assert times == sorted(times)

    events = normalize("do it", [(t, json.loads(l)) for t, l in lines])
    kinds = [e.type for e in events]
    assert kinds == ["prompt", "assistant_text", "user_message", "assistant_text", "user_done", "completion"]
    assert events[2].data["text"] == "Does the test cover F too?"


def test_converse_stops_at_the_cap():
    lines, sent = converse(
        "go", None, lambda m, w, **kw: _turn("ok"),
        responder=lambda v: "again", max_follow_ups=2,
    )
    assert sent == 2
    assert sum(1 for l in lines if '"follow_up"' in l) == 2


def test_parse_reply():
    assert parse_reply("DONE") is None and parse_reply(" done. ") is None and parse_reply("") is None
    assert parse_reply("Why is the error exactly 0?") == "Why is the error exactly 0?"


def test_run_demo_with_brief_records_the_conversation(tmp_path):
    cs = _set_with(tmp_path, checks=_PRODUCED)
    demo = cs.demos()[0]
    (demo.dir / "user.md").write_text("You are the lead engineer.", encoding="utf-8")
    yaml = demo.dir / "demo.yaml"
    yaml.write_text(yaml.read_text(encoding="utf-8") + "user: user.md\nmax_follow_ups: 2\n", encoding="utf-8")
    demo = cs.demos()[0]

    def invoke(prompt, work_dir, **kw):
        (work_dir / "result.out").write_text("done", encoding="utf-8")
        return _turn("fixed" if kw.get("resume") else "first try")

    briefs = []

    def responder(view):
        briefs.append(view.brief)
        return None if view.follow_ups_sent else "Please double-check that."

    result = run_demo(demo, cs, when=WHEN, git_commit="x", invoker=invoke, responder=responder)
    assert briefs == ["You are the lead engineer."] * 2
    assert [e.type for e in result.events].count("user_message") == 1
    meta = json.loads(result.bundle.metadata_path.read_text(encoding="utf-8"))
    assert meta["extra"]["follow_ups"] == 1 and meta["extra"]["user"] == "simulated from user.md"
    md = result.bundle.transcript_md_path.read_text(encoding="utf-8")
    assert "## Follow-up\n\nPlease double-check that." in md
    dest = approve_run(cs, demo.id, run_id=result.run_id)
    assert '"follow_up"' in (dest / "transcript.jsonl").read_text(encoding="utf-8")

    single = run_demo(demo, cs, when=WHEN, git_commit="x", invoker=invoke,
                      responder=responder, follow_ups=False, run_id="single")
    assert "user_message" not in [e.type for e in single.events]
