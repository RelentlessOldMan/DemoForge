"""The replay as one continuous Claude Code session, animated (docs/video-pipeline.md §5).

The timeline already decides *what* is shown and for how long; this module only
decides how a scene's recorded text arrives on screen. Each scene becomes a few
*beats*: snapshots of one terminal window, held for a fraction of the scene. The
prompt is typed into the input box and submitted, Claude's words stream in, a
command's output prints line by line, and the window keeps the conversation so far
and scrolls as it grows.

Nothing here can add content. Every string in a beat is a prefix of text the scene
already carries from ``events.jsonl``; the only other things on screen are the
window's own chrome and, while a recorded command runs, a counter that climbs to the
duration the record measured. A scene's beats always add up to exactly its
duration, so the narration over it is untouched.

Pure: (timeline, timing) in, beats out.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from demoforge.render import markdown
from demoforge.render.config import Timing
from demoforge.render.timeline import Scene, Timeline

SESSION_TEMPLATE = "session.html.j2"

# Scenes that are part of the conversation. Anything else (the closing results
# panel) keeps its own full-screen template.
USER_KINDS = ("PromptCard", "FollowUp")
TEXT_KINDS = ("NarratedText",)
TOOL_KINDS = ("TerminalRun", "DiffReveal", "FileGlance", "ToolCard", "ArtifactReveal",
              "ResultBadge")
SESSION_KINDS = USER_KINDS + TEXT_KINDS + TOOL_KINDS

# At most this share of a scene is spent revealing; the rest holds the whole thing
# so it can be read while the narration finishes.
_REVEAL_SHARE = 0.6
# A cap on animation frames per scene, so a long scene stays cheap to render.
_MAX_STEPS = 80
# How long a command's header sits before its output, and the share of the scene
# its running counter may take.
_HEADER_SECONDS = 0.35
_RUNNING_SHARE = 0.25
_RUNNING_MAX_SECONDS = 1.6
# The window shows the newest entries; older ones have scrolled off the top.
_VISIBLE_ENTRIES = 8
_SPINNER = ("✻", "✽", "✶", "✳")


@dataclass(frozen=True)
class Beat:
    """One animation frame of a scene: what the window shows, and for how long."""

    scene_index: int
    step: int
    duration: float
    session: dict[str, Any] = field(default_factory=dict)


def uses_session(scene: Scene) -> bool:
    return scene.kind in SESSION_KINDS


def session_beats(timeline: Timeline, timing: Timing) -> dict[int, list[Beat]]:
    """Beats for every conversation scene, keyed by scene index."""
    entries: list[dict[str, Any]] = []
    # Paged messages share their first event; their pages extend one entry.
    message_of: dict[int, int] = {}
    out: dict[int, list[Beat]] = {}
    for scene in timeline.scenes:
        if not uses_session(scene):
            continue
        out[scene.index] = _scene_beats(scene, entries, message_of, timing)
    return out


def streamed_floors(timeline: Timeline, timing: Timing) -> dict[int, float]:
    """The least time each of Claude's messages needs when narration covers it.

    A still card is paced for reading. In the session, Claude's words stream in and
    the narration says what they mean, so a narrated message needs only to stream
    and then hold for a moment; the narration sets the rest (``stretch_for_narration``).
    Un-narrated messages keep their reading time.
    """
    floors: dict[int, float] = {}
    explained = False
    for scene in timeline.scenes:
        if scene.kind not in TEXT_KINDS:
            continue
        seconds = (
            int(scene.data.get("chars", 0) or 0) / timing.stream_chars_per_second
            + timing.continued_page_hold_seconds
        )
        # The explainer line is given reading time once, on the first card of its
        # kind, as the timeline does.
        if not explained and scene.explain:
            seconds += len(scene.explain) / timing.reading_chars_per_second
            explained = True
        floors[scene.index] = round(min(scene.duration, timing.clamp_read(seconds)), 3)
    return floors


# ---- per scene ---------------------------------------------------------
def _scene_beats(
    scene: Scene,
    entries: list[dict[str, Any]],
    message_of: dict[int, int],
    timing: Timing,
) -> list[Beat]:
    d = scene.data
    seq = scene.event_seqs[0] if scene.event_seqs else -1
    frames: list[tuple[float, list[dict[str, Any]], dict[str, Any] | None]] = []

    if scene.kind in USER_KINDS:
        prior = message_of.get(seq)
        before = entries[prior]["text"] if prior is not None else ""
        if prior is None:
            message_of[seq] = len(entries)
            entries.append({"role": "user", "text": "", "done": False})
        full = _join(before, d)
        typed_from = len(before)
        last_page = int(d.get("page", 1)) >= int(d.get("pages", 1))
        n = len(full) - typed_from
        reveal = _reveal_time(scene.duration, n, timing.typing_chars_per_second)
        idx = message_of[seq]
        for amount, dt in _steps(n, reveal, timing):
            entries[idx]["text"] = full[: typed_from + amount]
            frames.append((dt, _visible(entries[:idx]), {"text": entries[idx]["text"]}))
        entries[idx]["text"] = full
        if last_page:
            entries[idx]["done"] = True
        hold = scene.duration - reveal
        if hold > 0:
            if last_page:
                frames.append((hold, _visible(entries), {"text": ""}))
            else:
                frames.append((hold, _visible(entries[:idx]), {"text": full}))

    elif scene.kind in TEXT_KINDS:
        prior = message_of.get(seq)
        if prior is None:
            message_of[seq] = len(entries)
            entries.append({"role": "assistant", "text": ""})
        idx = message_of[seq]
        before = entries[idx]["text"]
        full = _join(before, d)
        n = len(full) - len(before)
        reveal = _reveal_time(scene.duration, n, timing.stream_chars_per_second)
        for amount, dt in _steps(n, reveal, timing):
            entries[idx]["text"] = _word_prefix(full, len(before) + amount)
            frames.append((dt, _visible(entries), None))
        entries[idx]["text"] = full
        if scene.duration - reveal > 0:
            frames.append((scene.duration - reveal, _visible(entries), None))

    else:
        entry = _tool_entry(scene)
        entries.append(entry)
        lines = entry.pop("all_lines")
        more = entry.pop("all_more")
        budget = scene.duration
        # The call itself appears first, with a counter while the recorded command
        # ran, so the viewer sees that something is happening before its output.
        running = scene.real_seconds >= 1.0 and scene.kind == "TerminalRun"
        lead = min(_RUNNING_MAX_SECONDS, scene.duration * _RUNNING_SHARE) if running \
            else min(_HEADER_SECONDS, scene.duration * 0.15)
        lead_steps = max(1, min(8, int(lead / timing.session_step_seconds))) if running else 1
        for k in range(lead_steps):
            if running:
                elapsed = scene.real_seconds * (k + 1) / lead_steps
                entry["running"] = (
                    f"{_SPINNER[k % len(_SPINNER)]} Running… {elapsed:.1f}s"
                )
            frames.append((lead / lead_steps, _visible(entries), None))
        entry["running"] = ""
        budget -= lead
        reveal = _reveal_time(budget, len(lines), timing.output_lines_per_second)
        for amount, dt in _steps(len(lines), reveal, timing):
            entry["lines"] = lines[:amount]
            frames.append((dt, _visible(entries), None))
        entry["lines"] = lines
        entry["more"] = more
        if budget - reveal > 0:
            frames.append((budget - reveal, _visible(entries), None))

    return _as_beats(scene, frames)


def _tool_entry(scene: Scene) -> dict[str, Any]:
    """A tool call as the window shows it: ``Tool(argument)`` and what it printed."""
    d = scene.data
    tool = str(d.get("tool") or scene.label or scene.kind)
    lines: list[dict[str, str]] = []
    more = ""
    if scene.kind == "TerminalRun":
        arg = str(d.get("command", ""))
        if d.get("command_cut"):
            arg += " …"
        lines = [{"sign": "", "text": str(t)} for t in d.get("output_lines", ()) or ()]
        dropped = int(d.get("dropped_lines", 0) or 0)
        if dropped:
            more = f"… {dropped} further line{'' if dropped == 1 else 's'} of recorded output, kept in the record"
    elif scene.kind == "DiffReveal":
        arg = str(d.get("rel") or d.get("name") or "")
        lines = [
            {"sign": str(c.get("sign", " ")), "text": str(c.get("text", ""))}
            for c in d.get("code_lines", ()) or ()
        ]
        dropped = int(d.get("dropped_lines", 0) or 0)
        if dropped:
            more = f"… {dropped} further line{'' if dropped == 1 else 's'}, kept in the record"
    elif scene.kind == "FileGlance":
        arg = str(d.get("rel") or d.get("name") or d.get("query") or "")
    elif scene.kind == "ArtifactReveal":
        arg = str(d.get("rel") or d.get("name") or "")
    elif scene.kind == "ResultBadge":
        arg = ""
        lines = [{"sign": "", "text": f"{k.replace('_', ' ')}: {v}"} for k, v in sorted(d.items())]
    else:
        arg = ""
    return {
        "role": "tool",
        "kind": scene.kind,
        "tool": tool,
        "arg": arg,
        "lines": [],
        "more": "",
        "running": "",
        "all_lines": lines,
        "all_more": more,
    }


# ---- timing ------------------------------------------------------------
def _reveal_time(duration: float, units: int, per_second: float) -> float:
    if units <= 0 or duration <= 0:
        return 0.0
    return min(duration * _REVEAL_SHARE, units / per_second)


def _steps(units: int, reveal: float, timing: Timing) -> list[tuple[int, float]]:
    """``(amount shown, hold)`` pairs that reveal ``units`` over ``reveal`` seconds."""
    if units <= 0 or reveal <= 0:
        return []
    count = max(1, min(_MAX_STEPS, units, int(reveal / timing.session_step_seconds)))
    return [(math.ceil(units * (k + 1) / count), reveal / count) for k in range(count)]


def _as_beats(
    scene: Scene,
    frames: list[tuple[float, list[dict[str, Any]], dict[str, Any] | None]],
) -> list[Beat]:
    """Round holds so they add up to the scene's duration exactly."""
    if not frames:
        frames = [(scene.duration, [], None)]
    beats: list[Beat] = []
    total_ms = round(scene.duration * 1000)
    elapsed = 0.0
    start_ms = 0
    for i, (dt, visible, prompt) in enumerate(frames):
        elapsed += dt
        end_ms = total_ms if i == len(frames) - 1 else min(total_ms, round(elapsed * 1000))
        if end_ms <= start_ms:
            continue  # too short to show at millisecond precision
        beats.append(Beat(
            scene_index=scene.index,
            step=len(beats),
            duration=(end_ms - start_ms) / 1000,
            session={"entries": visible, "input": prompt},
        ))
        start_ms = end_ms
    return beats


# ---- text --------------------------------------------------------------
def _join(before: str, page: dict[str, Any]) -> str:
    """A paged message is its pages, one after another, as the reader saw them.

    A table or code block split across pages is whole on each page (its header
    row, its fences); in the transcript it reads on as the one recorded block.
    """
    rows = str(page.get("text", "")).split("\n")
    if page.get("continues") == "code":
        rows = rows[:-1]  # the closing fence comes with the last page
    if not before:
        return "\n".join(rows)
    if page.get("resumes") == "table":
        return before + "\n" + "\n".join(rows[2:])
    if page.get("resumes") == "code":
        return before + "\n" + "\n".join(rows[1:])
    return before + "\n\n" + "\n".join(rows)


def _word_prefix(text: str, amount: int) -> str:
    """The first ``amount`` characters, cut back to a whole word."""
    if amount >= len(text):
        return text
    cut = text.rfind(" ", 0, amount + 1)
    nl = text.rfind("\n", 0, amount + 1)
    cut = max(cut, nl)
    return text[: cut if cut > 0 else amount]


def _close_marks(text: str) -> str:
    """Close Markdown a half-streamed prefix has left open, so it renders as text."""
    if text.count("```") % 2:
        return text + "\n```"
    if text.count("`") % 2:
        text += "`"
    if text.replace("`", "").count("**") % 2:
        text += "**"
    return text


def _visible(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The newest entries, rendered, as plain data a template can draw."""
    shown = []
    for e in entries[-_VISIBLE_ENTRIES:]:
        if e["role"] == "assistant":
            shown.append({"role": "assistant", "text": e["text"],
                          "html": markdown.to_html(_close_marks(e["text"]))})
        elif e["role"] == "user":
            if not e.get("done"):
                continue
            shown.append({"role": "user", "text": e["text"]})
        else:
            shown.append({k: (list(v) if isinstance(v, list) else v) for k, v in e.items()})
    return shown


def visible_text(beat: Beat) -> list[str]:
    """Every recorded string a beat puts on screen, for the faithfulness audit."""
    texts: list[str] = []
    for e in beat.session.get("entries", ()):
        if e["role"] in ("user", "assistant"):
            texts.append(e["text"])
        else:
            texts.append(e["arg"])
            texts.extend(line["text"] for line in e.get("lines", ()))
    prompt = beat.session.get("input")
    if prompt and prompt.get("text"):
        texts.append(prompt["text"])
    return texts


# ---- faithfulness ------------------------------------------------------
def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, (list, tuple)):
        return [s for v in value for s in _strings(v)]
    return []


def _norm(text: str) -> str:
    return " ".join(text.split())


def audit_beats(
    timeline: Timeline, beats: dict[int, list[Beat]], events: Any
) -> list[str]:
    """Every recorded string each beat shows, checked against the events behind it.

    A beat may show the window's history, so a string passes if it occurs in any
    event up to and including the scene's own. A line shortened to fit ends in
    ``…``; the part before it must still be recorded text. Returns the failures.
    """
    by_seq = {e.seq: _norm(" ".join(_strings(e.data))) for e in events}
    problems: list[str] = []
    # The history is what earlier scenes showed, not every seq below this one: a
    # command's output recorded after a parallel edit is shown with its command.
    shown: set[int] = set()
    for scene in timeline.scenes:
        shown.update(scene.event_seqs)
        if scene.index not in beats:
            continue
        haystack = " \u0000 ".join(v for k, v in sorted(by_seq.items()) if k in shown)
        for beat in beats[scene.index]:
            for text in visible_text(beat):
                needle = _norm(text.rstrip("… "))
                if needle and needle not in haystack:
                    problems.append(
                        f"scene {scene.index} beat {beat.step}: {needle[:80]!r} is not in "
                        "the recorded events"
                    )
    return problems
