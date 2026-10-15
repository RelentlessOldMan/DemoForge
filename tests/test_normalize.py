"""stream-json -> canonical event normalization (pure function)."""

from __future__ import annotations

from demoforge.capture import normalize
from demoforge.model import EVENT_TYPES


def _timed(objs):
    return [(float(i), o) for i, o in enumerate(objs)]


def test_prompt_event_is_synthesized_first():
    events = normalize("do the thing", [])
    assert len(events) == 1
    assert events[0].type == "prompt"
    assert events[0].seq == 0 and events[0].t == 0.0
    assert events[0].data["text"] == "do the thing"


def test_assistant_text_and_tools_map_to_canonical():
    stream = [
        {"type": "system", "subtype": "init", "model": "claude-opus-4-8"},
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "Let me look."},
            {"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "a.m"}},
            {"type": "tool_use", "id": "t2", "name": "Bash", "input": {"command": "octave run.m"}},
            {"type": "tool_use", "id": "t3", "name": "Write", "input": {"file_path": "fast.m"}},
            {"type": "tool_use", "id": "t4", "name": "Grep", "input": {"pattern": "kalman"}},
        ]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t2", "content": "ran ok"},
        ]}},
        {"type": "result", "subtype": "success", "is_error": False, "num_turns": 3},
    ]
    events = normalize("job", _timed(stream))
    types = [e.type for e in events]
    assert types == [
        "prompt", "assistant_text", "file_read", "command", "file_write",
        "file_search", "command_output", "completion",
    ]
    assert all(e.type in EVENT_TYPES for e in events)
    assert [e.seq for e in events] == list(range(len(events)))

    by_type = {e.type: e for e in events}
    assert by_type["file_read"].data["path"] == "a.m"
    assert by_type["command"].data["command"] == "octave run.m"
    assert by_type["file_write"].data["path"] == "fast.m"
    assert by_type["file_search"].data["query"] == "kalman"
    assert by_type["command_output"].data["output"] == "ran ok"
    assert by_type["completion"].data["subtype"] == "success"


def test_unknown_tool_becomes_generic_tool_call():
    stream = [{"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "t1", "name": "WebFetch", "input": {"url": "x"}},
    ]}}]
    events = normalize("j", _timed(stream))
    assert events[1].type == "tool_call"
    assert events[1].data["tool"] == "WebFetch"


def test_powershell_is_a_command_like_bash():
    """On Windows the agent reaches for PowerShell; it must not replay as a blank step."""
    stream = [
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "PowerShell",
             "input": {"command": "octave-cli run.m"}},
        ]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "ok"},
        ]}},
    ]
    events = normalize("j", _timed(stream))
    assert [e.type for e in events] == ["prompt", "command", "command_output"]
    assert events[1].data["command"] == "octave-cli run.m"
    assert events[2].data["output"] == "ok"


def test_non_bash_tool_results_are_not_timeline_events():
    stream = [
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "a"}},
        ]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "file body"},
        ]}},
    ]
    events = normalize("j", _timed(stream))
    assert [e.type for e in events] == ["prompt", "file_read"]


def test_empty_assistant_text_skipped():
    stream = [{"type": "assistant", "message": {"content": [{"type": "text", "text": "   "}]}}]
    events = normalize("j", _timed(stream))
    assert [e.type for e in events] == ["prompt"]


def test_command_output_flattens_list_content():
    """A tool_result whose content is a list of text blocks is joined to one string."""
    stream = [
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls"}},
        ]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1",
             "content": [{"type": "text", "text": "line1\n"}, {"type": "text", "text": "line2"}]},
        ]}},
    ]
    out = [e for e in normalize("j", _timed(stream)) if e.type == "command_output"][0]
    assert out.data["output"] == "line1\nline2"


def test_malformed_and_minimal_objects_are_robust():
    """Missing/!list content and a bare result object produce no spurious events."""
    stream = [
        {"type": "assistant"},                                  # no message/content
        {"type": "assistant", "message": {"content": "nope"}},  # content is not a list
        {"type": "user", "message": {"content": [               # non-tool_result block
            {"type": "text", "text": "ignored"},
        ]}},
        {"type": "result"},                                     # minimal completion, no fields
    ]
    events = normalize("j", _timed(stream))
    assert [e.type for e in events] == ["prompt", "completion"]
    assert events[-1].data == {}
