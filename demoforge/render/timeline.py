"""Run replay: ``events.jsonl`` → ``timeline.json`` (docs/video-pipeline.md §5).

The timeline is the mechanism that makes fabrication structurally impossible. Every
scene is built from one or more recorded events in an approved bundle; there is no
hand-authored timeline and no way to add a scene without an event behind it. Each
scene carries the ``event_seqs`` it came from, so any frame can be traced back to the
capture that justifies it.

Pacing is deliberately *not* wall-clock (§5.2). A scene lasts as long as it takes to
read what is on screen, bounded by config — so a real 90-second benchmark becomes a
short beat. Where the run spent materially longer than the replay does, the scene is
flagged ``compressed`` and the renderer shows a time-compressed affordance: accurate
about what happened, honest that time was squeezed.

This module is a pure function of (events, config). No I/O beyond an explicit write.
"""

from __future__ import annotations

import json
import difflib
import math
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable, Sequence

from demoforge.model import Event
from demoforge.render import markdown
from demoforge.render.config import Limits, SceneMap, SceneStyle, Timing

# Durations are rounded so timeline.json is byte-stable across machines.
_PRECISION = 3


@dataclass(frozen=True)
class Scene:
    """One beat of the replay, derived from the recorded events it names.

    ``real_seconds`` is what the record measures this step took (a command until
    its output arrived), or 0 when it measures nothing; ``duration`` is what the
    replay spends showing it. They differ on
    purpose, and ``compressed`` records when the gap is big enough to tell the
    audience about.
    """

    index: int
    kind: str
    template: str
    label: str
    event_seqs: tuple[int, ...]
    duration: float
    real_seconds: float = 0.0
    compressed: bool = False
    data: dict[str, Any] = field(default_factory=dict)
    narration: str | None = None
    explain: str = ""
    # The narration's words, shown on screen so the video reads without sound.
    caption: str = ""

    def frame_count(self, fps: int) -> int:
        """Whole frames this scene occupies; always at least one."""
        return max(1, round(self.duration * fps))

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "index": self.index,
            "kind": self.kind,
            "template": self.template,
            "label": self.label,
            "event_seqs": list(self.event_seqs),
            "duration": self.duration,
            "real_seconds": self.real_seconds,
            "compressed": self.compressed,
            "data": self.data,
        }
        if self.narration is not None:
            out["narration"] = self.narration
        if self.explain:
            out["explain"] = self.explain
        if self.caption:
            out["caption"] = self.caption
        return out

    @classmethod
    def from_json(cls, obj: dict[str, Any]) -> "Scene":
        return cls(
            index=int(obj["index"]),
            kind=str(obj["kind"]),
            template=str(obj["template"]),
            label=str(obj.get("label", "")),
            event_seqs=tuple(int(s) for s in obj.get("event_seqs", ())),
            duration=float(obj["duration"]),
            real_seconds=float(obj.get("real_seconds", 0.0)),
            compressed=bool(obj.get("compressed", False)),
            data=dict(obj.get("data", {})),
            narration=obj.get("narration"),
            explain=str(obj.get("explain", "")),
            caption=str(obj.get("caption", "")),
        )


@dataclass(frozen=True)
class Timeline:
    """An ordered, self-describing replay plan for one demo."""

    demo_id: str
    scenes: tuple[Scene, ...]
    fps: int = 30

    @property
    def total_seconds(self) -> float:
        return round(sum(s.duration for s in self.scenes), _PRECISION)

    @property
    def total_frames(self) -> int:
        return sum(s.frame_count(self.fps) for s in self.scenes)

    @property
    def real_seconds(self) -> float:
        """The measured time of the steps we show (commands running, mostly)."""
        return round(sum(s.real_seconds for s in self.scenes), _PRECISION)

    @property
    def compressed_scenes(self) -> tuple[Scene, ...]:
        return tuple(s for s in self.scenes if s.compressed)

    def to_json(self) -> dict[str, Any]:
        return {
            "demo_id": self.demo_id,
            "fps": self.fps,
            "total_seconds": self.total_seconds,
            "real_seconds": self.real_seconds,
            "scenes": [s.to_json() for s in self.scenes],
        }

    @classmethod
    def from_json(cls, obj: dict[str, Any]) -> "Timeline":
        return cls(
            demo_id=str(obj["demo_id"]),
            scenes=tuple(Scene.from_json(s) for s in obj.get("scenes", ())),
            fps=int(obj.get("fps", 30)),
        )


def build_timeline(
    demo_id: str,
    events: Sequence[Event],
    *,
    scenes: SceneMap,
    timing: Timing,
    clocked: bool = False,
) -> Timeline:
    """Derive a :class:`Timeline` from recorded ``events``.

    ``clocked`` says the events' ``t`` values are measured seconds. Without it,
    ``t`` only orders the events, so no scene claims how long its step took.

    Events configured in ``merge_into_previous`` are folded onto the scene they
    belong to (a command's output shares its command's terminal card). An event
    with no style and no merge target is not shown — which is a config decision,
    visible in ``scenes.yaml``, not a silent drop in code.
    """
    groups = _group(events, scenes)
    # The chapter end says how many times the person stepped in, which is what a
    # viewer can count. The CLI's own num_turns counts the agent's internal steps.
    follow_ups = sum(1 for e in events if e.type == "user_message")
    out: list[Scene] = []
    explained: set[str] = set()
    for i, (style, primary, merged) in enumerate(groups):
        # A step's real time is only what the record measures for it: from the
        # action to its own last recorded result (a command to its output). The
        # gap before the next event is Claude composing that next step, or the
        # person reading, and is not this step's time.
        real = max(0.0, merged[-1].t - primary.t) if merged and clocked else 0.0
        # A long text event becomes several consecutive pages, all traced to it.
        pages = _scene_pages(style.kind, primary, merged, scenes.limits)
        for p, data in enumerate(pages):
            if style.kind == "ChapterEnd":
                data = data | {"follow_ups": follow_ups}
            explain = _explain(style.explain, data)
            # The explainer is read once per kind: the first card of a kind gets time
            # for it, later ones show the same line as a reminder at no extra cost.
            extra = 0.0
            if explain and style.kind not in explained:
                explained.add(style.kind)
                extra = len(explain) / timing.reading_chars_per_second
            duration = _duration(style.kind, data, timing, extra)
            if p > 0 and timing.replay_style == "session":
                # A later page streams on under the same message; it is skimmed as
                # it arrives, not read as a fresh card.
                duration = round(timing.clamp_read(
                    int(data.get("chars", 0)) / timing.stream_chars_per_second
                    + timing.continued_page_hold_seconds
                ), _PRECISION)
            # The step's real time belongs to its last page, the one shown last.
            page_real = real if p == len(pages) - 1 else 0.0
            out.append(
                Scene(
                    index=len(out),
                    kind=style.kind,
                    template=style.template,
                    label=style.label,
                    event_seqs=tuple([primary.seq] + [e.seq for e in merged]),
                    duration=duration,
                    real_seconds=round(page_real, _PRECISION),
                    compressed=_is_compressed(page_real, duration, timing),
                    data=data,
                    explain=explain,
                )
            )
    return Timeline(demo_id=demo_id, scenes=tuple(out), fps=timing.fps)


def with_narration(
    timeline: Timeline,
    assignments: dict[int, str],
    captions: dict[str, str] | None = None,
) -> Timeline:
    """Attach narration block keys to scenes by scene index.

    ``captions`` maps a block key to its on-screen text; a scene that speaks a
    block also shows it, so someone watching without sound misses nothing.
    """
    texts = captions or {}
    scenes = []
    for s in timeline.scenes:
        key = assignments.get(s.index, s.narration)
        scenes.append(replace(s, narration=key, caption=texts.get(key or "", s.caption)))
    # The later pages of a narrated message keep showing its words.
    leaders = narration_spans(scenes)
    scenes = [
        replace(s, caption=scenes[leaders[s.index]].caption)
        if leaders[s.index] != s.index and not s.caption else s
        for s in scenes
    ]
    return replace(timeline, scenes=tuple(scenes))


def narration_spans(scenes: Sequence[Scene]) -> dict[int, int]:
    """Scene index → index of the scene whose narration plays over it.

    A long message is paged over consecutive scenes; narration anchored on its first
    page plays once across all of them, rather than leaving the later pages silent.
    Every other scene is its own span.
    """
    leaders: dict[int, int] = {}
    prev: Scene | None = None
    for s in scenes:
        continues = (
            prev is not None
            and int(s.data.get("page", 1) or 1) > 1
            and s.event_seqs == prev.event_seqs
            and not s.narration
        )
        leaders[s.index] = leaders[prev.index] if continues and prev else s.index
        prev = s
    return leaders


def stretch_for_narration(
    timeline: Timeline,
    audio_seconds: dict[str, float],
    *,
    tail: float = 0.0,
    floors: dict[int, float] | None = None,
) -> Timeline:
    """Fit scenes to their narration (§6, "narration drives pacing").

    A narration block plays across its span (a scene, or every page of a long
    message), and the span is lengthened so the speech is never cut off.
    ``scene_max_seconds`` deliberately does not apply: truncating recorded narration
    to honour a style bound would misrepresent it. ``tail`` is the pause left after
    the speech ends, so a cut never lands on the last word.

    ``floors`` gives scenes that may also be *shortened* when narrated: each drops to
    its floor, and the span then grows back only as far as the speech needs. Without
    a floor a scene is only ever extended.
    """
    scenes = list(timeline.scenes)
    leaders = narration_spans(scenes)
    spans: dict[int, list[int]] = {}
    for index, leader in leaders.items():
        spans.setdefault(leader, []).append(index)
    for leader, members in spans.items():
        needed = audio_seconds.get(scenes[leader].narration or "", 0.0)
        if not needed:
            continue
        needed += tail
        for i in members:
            floor = (floors or {}).get(i)
            if floor is not None and floor < scenes[i].duration:
                scenes[i] = replace(scenes[i], duration=round(floor, _PRECISION))
        # Only a shortfall lengthens the span, and it lengthens the last page, the
        # one that holds the whole message.
        short = round(needed - sum(scenes[i].duration for i in members), _PRECISION)
        if short > 0:
            last = members[-1]
            scenes[last] = replace(
                scenes[last], duration=round(scenes[last].duration + short, _PRECISION)
            )
    return replace(timeline, scenes=tuple(scenes))


def write_timeline(timeline: Timeline, path: Path) -> Path:
    """Write ``timeline.json`` deterministically (stable key order, LF endings)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(timeline.to_json(), ensure_ascii=False, indent=2, sort_keys=True)
    path.write_text(text + "\n", encoding="utf-8", newline="\n")
    return path


def read_timeline(path: Path) -> Timeline:
    return Timeline.from_json(json.loads(path.read_text(encoding="utf-8")))


# ---- grouping ---------------------------------------------------------
def _group(
    events: Iterable[Event], scenes: SceneMap
) -> list[tuple[SceneStyle, Event, list[Event]]]:
    """Pair each shown event with its style and the events folded into it."""
    groups: list[tuple[SceneStyle, Event, list[Event]]] = []
    for ev in events:
        merge_target = scenes.merge_into_previous.get(ev.type)
        if merge_target is not None:
            if groups and groups[-1][1].type == merge_target:
                groups[-1][2].append(ev)
            else:
                # Parallel tool calls can return a result after another step (a
                # command's output after an edit made alongside it); it still belongs
                # to the latest step of its kind that has had no result yet.
                owner = next(
                    (g for g in reversed(groups) if g[1].type == merge_target), None
                )
                if owner is not None and not owner[2]:
                    owner[2].append(ev)
            continue  # nothing to merge onto: not shown
        style = scenes.style_for(ev.type)
        if style is None:
            continue
        groups.append((style, ev, []))
    return groups


# ---- view models ------------------------------------------------------
_TEXT_KINDS = ("PromptCard", "FollowUp", "NarratedText")


def _scene_pages(
    kind: str, primary: Event, merged: list[Event], limits: Limits
) -> list[dict[str, Any]]:
    """The view model for each page this event is shown on (usually one)."""
    if kind not in _TEXT_KINDS:
        return [_scene_data(kind, primary, merged, limits)]
    pages = _paginate(str(primary.data.get("text", "")), limits)
    return [
        _text_data(page["text"])
        | {"page": n + 1, "pages": len(pages), "resumes": page["resumes"],
           "continues": page["continues"]}
        for n, page in enumerate(pages)
    ]


def _scene_data(
    kind: str, primary: Event, merged: list[Event], limits: Limits
) -> dict[str, Any]:
    d = primary.data
    if kind in _TEXT_KINDS:
        return _text_data(str(d.get("text", "")))
    if kind == "TerminalRun":
        return _terminal_data(d, merged, limits)
    if kind == "FileGlance":
        return _path_data(d) | {"query": str(d.get("query", ""))}
    if kind == "DiffReveal":
        return _path_data(d) | _change_data(primary.type, d, limits)
    if kind == "ArtifactReveal":
        return _path_data(d)
    if kind == "ResultBadge":
        return {k: v for k, v in d.items()}
    if kind == "ToolCard":
        return {"tool": str(d.get("tool", ""))}
    if kind == "ChapterEnd":
        return {
            "subtype": str(d.get("subtype", "")),
            "is_error": bool(d.get("is_error", False)),
            "num_turns": d.get("num_turns"),
            "follow_ups": None,
        }
    return {k: v for k, v in d.items()}


def _text_data(text: str) -> dict[str, Any]:
    return {
        "text": text,
        "html": markdown.to_html(text),
        "chars": len(markdown.plain(text).strip()),
    }


def paginate(text: str, limits: Limits) -> list[str]:
    """Split Markdown ``text`` into pages that each fit a card.

    Pages break between blocks (paragraphs, lists, tables, code); a block too big
    for one page is split by sentence, item or line. Nothing is dropped: the pages
    together hold every word of ``text``.
    """
    return [page["text"] for page in _paginate(text, limits)]


def _paginate(text: str, limits: Limits) -> list[dict[str, Any]]:
    """The pages, each with the kind of split block ("table", "code") it resumes
    from the page before and continues onto the page after, if any."""
    budget = max(1, limits.text_page_lines)
    width = max(10, limits.text_line_chars)
    pages: list[dict[str, Any]] = []
    current: list[str] = []
    resumes: str | None = None
    continues: str | None = None
    used = 0
    for block in markdown.blocks(text):
        pieces = _split_block(block, budget, width)
        for n, piece in enumerate(pieces):
            height = _height(piece, width)
            cost = height + (1 if current else 0)  # the gap between blocks
            if current and used + cost > budget:
                pages.append({"text": "\n\n".join(current), "resumes": resumes,
                              "continues": continues})
                current, used, cost, resumes = [], 0, height, None
            if not current and n > 0:
                resumes = block.kind
            current.append(piece)
            used += cost
            continues = block.kind if n < len(pieces) - 1 else None
    if current:
        pages.append({"text": "\n\n".join(current), "resumes": resumes, "continues": None})
    return pages or [{"text": text, "resumes": None, "continues": None}]


def _height(source: str, width: int) -> int:
    """Estimated on-screen lines for a piece of Markdown."""
    return sum(max(1, math.ceil(len(line) / width)) for line in source.split("\n"))


def _split_block(block: markdown.Block, budget: int, width: int) -> list[str]:
    source = block.text()
    if _height(source, width) <= budget:
        return [source]
    if block.kind == "p":
        sentences = re.split(r"(?<=[.!?:])\s+", " ".join(line.strip() for line in block.lines))
        parts: list[str] = []
        for sentence in sentences:
            # A sentence longer than a page splits between words.
            if _height(sentence, width) > budget:
                parts.extend(_pack(sentence.split(" "), budget, width, " "))
            else:
                parts.append(sentence)
        return _pack(parts, budget, width, " ")
    if block.kind in ("code", "table"):
        # Each part stays well-formed: code keeps its fences, a table repeats its
        # header row and rule.
        if block.kind == "code":
            head, body, tail = [block.lines[0]], list(block.lines[1:-1]), [block.lines[-1]]
        else:
            head, body, tail = list(block.lines[:2]), list(block.lines[2:]), []
        room = max(1, budget - len(head) - len(tail))
        return ["\n".join(head + body[i:i + room] + tail) for i in range(0, len(body), room)]
    # A list splits between items.
    items: list[list[str]] = []
    for line in block.lines:
        if line.startswith((" ", "\t")) and items:
            items[-1].append(line)
        else:
            items.append([line])
    return _pack(["\n".join(item) for item in items], budget, width, "\n")


def _pack(parts: list[str], budget: int, width: int, joiner: str) -> list[str]:
    out: list[str] = []
    current: list[str] = []
    for part in parts:
        if current and _height(joiner.join(current + [part]), width) > budget:
            out.append(joiner.join(current))
            current = [part]
        else:
            current.append(part)
    if current:
        out.append(joiner.join(current))
    return out


def _terminal_data(d: dict[str, Any], merged: list[Event], limits: Limits) -> dict[str, Any]:
    command = str(d.get("command", ""))
    cmd_lines = command.replace("\r\n", "\n").split("\n")
    width = max(10, limits.terminal_max_line_chars)
    cap = max(1, limits.terminal_command_max_lines)
    # Fill the command's budget, counting how its lines wrap on screen.
    shown: list[str] = []
    used = 0
    for line in cmd_lines:
        cost = max(1, math.ceil(len(line) / width))
        if used + cost > cap:
            break
        shown.append(line)
        used += cost
    if not shown:  # a single very long first line: show its start
        shown, used = [cmd_lines[0][: width * cap]], cap
    command_cut = "\n".join(shown) != command
    raw = "".join(str(e.data.get("output", "")) for e in merged)
    room = max(3, limits.terminal_max_lines - used - (1 if command_cut else 0))
    lines, dropped = _clip_lines(raw, room, limits.terminal_max_line_chars)
    return {
        "command": "\n".join(shown),
        "command_cut": command_cut,
        "tool": str(d.get("tool", "")),
        "output_lines": lines,
        "dropped_lines": dropped,
        "has_output": bool(merged),
        "chars": sum(len(line) for line in lines),
    }


# The capture step runs the agent in ``<bundle>/working``; paths it recorded are
# absolute inside that folder, which on screen is just a machine-specific run id.
_WORK_DIR_MARKER = "/working/"


def _path_data(d: dict[str, Any]) -> dict[str, Any]:
    path = str(d.get("path", ""))
    posix = path.replace("\\", "/").rstrip("/")
    marker = posix.rfind(_WORK_DIR_MARKER)
    return {
        "path": path,
        # Basename for display: captured paths are absolute inside the run's work dir.
        "name": posix.rsplit("/", 1)[-1],
        # Where the file sits in the demo's own tree, without the machine prefix.
        "rel": posix[marker + len(_WORK_DIR_MARKER):] if marker >= 0 else posix,
        "tool": str(d.get("tool", "")),
    }


def _change_data(etype: str, d: dict[str, Any], limits: Limits) -> dict[str, Any]:
    """The code a write or edit put in the file, as ``(sign, text)`` lines.

    A write shows its first lines. An edit shows only what changed, with one line
    of context, as removed (``-``) and added (``+``) lines. Either way the card
    says how many lines it left off. Bundles recorded before the code was kept
    have none, and the card shows the file name alone.
    """
    room = max(3, limits.terminal_max_lines - 3)  # the file name takes the top
    width = limits.terminal_max_line_chars
    if etype == "file_edit":
        rows: list[tuple[str, str]] = []
        for e in d.get("edits") or []:
            if rows:
                rows.append(("~", ""))
            old = str(e.get("old", "")).splitlines()
            new = str(e.get("new", "")).splitlines()
            for line in list(difflib.unified_diff(old, new, n=1, lineterm=""))[2:]:
                if line.startswith("@@"):
                    if rows and rows[-1][0] != "~":
                        rows.append(("~", ""))
                    continue
                rows.append((line[:1], line[1:]))
        while rows and rows[0][0] == "~":
            rows.pop(0)
    elif "content" in d:
        rows = [(" ", line) for line in str(d.get("content", "")).splitlines()]
    else:
        rows = []
    shown, dropped = rows[:room], max(0, len(rows) - room)
    while shown and shown[-1][0] == "~":
        shown.pop()
    return {
        "action": "edit" if etype == "file_edit" else "write",
        "code_lines": [
            {"sign": s, "text": t.rstrip() if len(t) <= width else t[: width - 1] + "…"}
            for s, t in shown
        ],
        "dropped_lines": dropped,
        "chars": sum(len(t) for _, t in shown),
    }


def _clip_lines(raw: str, max_lines: int, max_chars: int) -> tuple[list[str], int]:
    """Lines as they will appear on the frame, plus how many were left off."""
    # Shells pad table columns out to the console width. Nobody reads the padding,
    # and keeping it pushes every row past the line limit.
    all_lines = [
        line.rstrip() for line in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ]
    while all_lines and all_lines[-1] == "":
        all_lines.pop()
    kept = [
        line if len(line) <= max_chars else line[: max_chars - 1] + "…"
        for line in all_lines[:max_lines]
    ]
    return kept, max(0, len(all_lines) - max_lines)


def _explain(template: str, data: dict[str, Any]) -> str:
    """Fill an explainer's ``{field}`` slots from the scene's recorded data.

    A slot the data lacks renders empty rather than failing: the explainer is a
    caption, and a missing tool name must not take a whole chapter down with it.
    """
    if not template:
        return ""

    class _Fields(dict):
        def __missing__(self, key: str) -> str:
            return ""

    fields = _Fields({k: v for k, v in data.items() if isinstance(v, (str, int, float))})
    return " ".join(template.format_map(fields).split())


# ---- pacing -----------------------------------------------------------
def _duration(kind: str, data: dict[str, Any], timing: Timing, extra: float = 0.0) -> float:
    """How long the replay shows this scene, from what is actually on screen.

    ``extra`` is reading time for anything shown on top of the scene's own content
    (the explainer line), added before the kind's bounds are applied.
    """
    if kind == "ChapterEnd":
        return round(timing.clamp(timing.chapter_end_seconds + extra), _PRECISION)
    if kind == "TerminalRun":
        seconds = (
            len(str(data.get("command", ""))) / timing.reading_chars_per_second
            + int(data.get("chars", 0)) / timing.terminal_chars_per_second
        )
        return round(timing.clamp_terminal(seconds + extra), _PRECISION)
    if kind == "DiffReveal" and data.get("code_lines"):
        seconds = int(data.get("chars", 0)) / timing.terminal_chars_per_second
        return round(timing.clamp_terminal(seconds + extra), _PRECISION)
    if kind in ("PromptCard", "FollowUp", "NarratedText"):
        seconds = int(data.get("chars", 0)) / timing.reading_chars_per_second
        return round(timing.clamp_read(seconds + extra), _PRECISION)
    # Path/label cards carry little text; these floor to scene_min_seconds.
    seconds = len(str(data.get("name") or data.get("tool") or "")) / (
        timing.reading_chars_per_second
    )
    return round(timing.clamp(seconds + extra), _PRECISION)


def _is_compressed(real_seconds: float, duration: float, timing: Timing) -> bool:
    if not timing.compress_idle:
        return False
    return (real_seconds - duration) >= timing.compress_notice_seconds
