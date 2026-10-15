"""Normalize Claude Code ``stream-json`` into the canonical event model.

This is a **pure function** of its input — no I/O, no clock — so it is exhaustively
unit-testable against recorded fixtures. It insulates the renderer from the CLI's
internal shapes (architecture.md §5.1): only the stable vocabulary in
:data:`demoforge.model.bundle.EVENT_TYPES` ever leaves here.

Only observable interaction is mapped. Internal model reasoning is never emitted.
"""

from __future__ import annotations

from typing import Any, Iterable

from demoforge.model import Event

# Claude Code tool name -> canonical event type.
_TOOL_EVENT = {
    "Read": "file_read",
    "Grep": "file_search",
    "Glob": "file_search",
    "LS": "file_search",
    "Write": "file_write",
    "Edit": "file_edit",
    "MultiEdit": "file_edit",
    "Bash": "command",
    "PowerShell": "command",
}


def normalize(prompt_text: str, timed_objs: Iterable[tuple[float, dict[str, Any]]]) -> list[Event]:
    """Map a submitted prompt + timed stream-json objects to canonical events.

    ``timed_objs`` is an iterable of ``(t_seconds, raw_obj)`` where ``raw_obj`` is
    one parsed stream-json line. ``t`` is informational (the renderer re-times).
    """
    events: list[Event] = [Event(seq=0, t=0.0, type="prompt", data={"text": prompt_text})]
    seq = 1
    # Track tool_use_id -> canonical type so tool results map to the right event.
    tool_by_id: dict[str, str] = {}
    timed_objs = list(timed_objs)
    # Each turn of a conversation ends in its own result; only the last one ends
    # the run. The others are implied by the follow-up that comes next.
    results = [i for i, (_, obj) in enumerate(timed_objs) if obj.get("type") == "result"]
    last_result = results[-1] if results else -1

    # The run is complete once the conversation is: a record of how it ended
    # (user_done) comes after the agent's last result, but before the completion.
    completion: list[tuple[str, dict[str, Any]]] = []
    end_t = 0.0
    for i, (t, obj) in enumerate(timed_objs):
        end_t = max(end_t, t)
        if obj.get("type") == "result":
            if i == last_result:
                completion = _events_from_obj(obj, t, tool_by_id)
            continue
        for ev in _events_from_obj(obj, t, tool_by_id):
            events.append(Event(seq=seq, t=t, type=ev[0], data=ev[1]))
            seq += 1
    for ev in completion:
        events.append(Event(seq=seq, t=end_t, type=ev[0], data=ev[1]))
        seq += 1
    return events


def _events_from_obj(
    obj: dict[str, Any], t: float, tool_by_id: dict[str, str]
) -> list[tuple[str, dict[str, Any]]]:
    otype = obj.get("type")
    if otype == "assistant":
        return _from_assistant(obj, tool_by_id)
    if otype == "user":
        return _from_user(obj, tool_by_id)
    if otype == "result":
        return [("completion", _completion_data(obj))]
    if otype == "follow_up":
        # A message the person sent after reading an answer (capture/conversation.py).
        return [("user_message", {"text": str(obj.get("text", ""))})]
    if otype == "user_done":
        # How the conversation ended: "satisfied" (the person said so) or "limit".
        return [("user_done", {"reason": str(obj.get("reason", ""))})]
    # system/init and anything else carry no observable action.
    return []


def _from_assistant(obj: dict[str, Any], tool_by_id: dict[str, str]) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for block in _content(obj):
        btype = block.get("type")
        if btype == "text":
            text = (block.get("text") or "").strip()
            if text:
                out.append(("assistant_text", {"text": text}))
        elif btype == "tool_use":
            name = block.get("name", "")
            etype = _TOOL_EVENT.get(name, "tool_call")
            tid = block.get("id")
            if tid:
                tool_by_id[tid] = etype
            out.append((etype, _tool_data(name, etype, block.get("input") or {})))
    return out


def _from_user(obj: dict[str, Any], tool_by_id: dict[str, str]) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for block in _content(obj):
        if block.get("type") != "tool_result":
            continue
        # Only surface command output; other results are not on the visual timeline.
        if tool_by_id.get(block.get("tool_use_id")) == "command":
            out.append(("command_output", {"output": _result_text(block.get("content"))}))
    return out


def _tool_data(name: str, etype: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    data: dict[str, Any] = {"tool": name}
    if etype in ("file_read", "file_write", "file_edit"):
        path = tool_input.get("file_path") or tool_input.get("path")
        if path:
            data["path"] = path
        data.update(file_change(etype, tool_input))
    elif etype == "file_search":
        data["query"] = tool_input.get("pattern") or tool_input.get("path") or ""
    elif etype == "command":
        data["command"] = tool_input.get("command", "")
    return data


def file_change(etype: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    """What a write or edit put in the file, exactly as the tool was given it.

    A write keeps the whole new text (``content``); an edit keeps each replaced
    passage and its replacement (``edits``), so a frame can show the real code.
    """
    if etype == "file_write":
        return {"content": str(tool_input.get("content", ""))}
    if etype == "file_edit":
        pairs = tool_input.get("edits") or [tool_input]
        return {"edits": [
            {"old": str(e.get("old_string", "")), "new": str(e.get("new_string", ""))}
            for e in pairs if isinstance(e, dict)
        ]}
    return {}


def _completion_data(obj: dict[str, Any]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    if "subtype" in obj:
        data["subtype"] = obj["subtype"]
    if "is_error" in obj:
        data["is_error"] = bool(obj["is_error"])
    if "num_turns" in obj:
        data["num_turns"] = obj["num_turns"]
    return data


def _content(obj: dict[str, Any]) -> list[dict[str, Any]]:
    msg = obj.get("message") or {}
    content = msg.get("content")
    if isinstance(content, list):
        return [b for b in content if isinstance(b, dict)]
    return []


def _result_text(content: Any) -> str:
    """Flatten a tool_result's content (str, or list of text blocks) to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content if isinstance(b, dict)]
        return "".join(parts)
    return ""


def with_file_changes(events: list[Event], objs: Iterable[dict[str, Any]]) -> list[Event]:
    """Events recorded before writes and edits kept their code, with it attached.

    Each write/edit event is paired, in order, with the matching tool call in the
    raw transcript. The pairing must be exact (same count, same paths), or this
    refuses: the code comes only from the record, never from a guess.
    """
    calls: list[tuple[str, dict[str, Any]]] = []
    for obj in objs:
        if obj.get("type") != "assistant":
            continue
        for block in _content(obj):
            if block.get("type") == "tool_use":
                etype = _TOOL_EVENT.get(block.get("name", ""))
                if etype in ("file_write", "file_edit"):
                    calls.append((etype, block.get("input") or {}))
    changed = [e for e in events if e.type in ("file_write", "file_edit")]
    if len(changed) != len(calls):
        raise ValueError(f"{len(changed)} write/edit events but {len(calls)} tool calls")
    by_seq: dict[int, dict[str, Any]] = {}
    for ev, (etype, tool_input) in zip(changed, calls):
        path = tool_input.get("file_path") or tool_input.get("path")
        if etype != ev.type or path != ev.data.get("path"):
            raise ValueError(f"event {ev.seq} does not match its tool call ({path!r})")
        by_seq[ev.seq] = file_change(etype, tool_input)
    return [
        Event(seq=e.seq, t=e.t, type=e.type, data={**e.data, **by_seq[e.seq]})
        if e.seq in by_seq else e
        for e in events
    ]
