"""Multi-turn capture: a person reading Claude's answers and replying.

Solving a problem with Claude is a conversation, not one prompt. Someone asks,
reads the answer, notices what looks off, and asks again. A demo shows that
the same way it shows everything else: each turn really happens and is recorded.

The person is played by a *responder*, which sees what a person at the terminal
would see: the conversation so far, plus the files in the folder. It returns the
next message, or ``None`` when it is satisfied. The default responder is a second
Claude session given the demo's brief about who the person is. It never sees
the demo's hidden checks. It can read the working folder but cannot change it.

Every message the responder sends goes into the raw stream as a ``follow_up``
record at the moment it was sent, so the normalized events (``user_message``)
come from the record like every other event. How the conversation ended is
recorded too (``user_done``): the person said they were done, or the follow-up
limit was reached and nobody was asked. The default responder also keeps its own
session's full stream, so what it looked at can be audited afterwards.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from demoforge.capture.normalize import normalize
from demoforge.errors import DemoForgeError
from demoforge.model import Event

# Raw stream record carrying a message the person sent after the first prompt.
FOLLOW_UP = "follow_up"

# Raw stream record saying how the conversation ended.
USER_DONE = "user_done"

# Reply that means the person has nothing more to ask.
DONE = "DONE"


@dataclass(frozen=True)
class UserView:
    """What the person can see when deciding what to say next."""

    prompt: str
    events: tuple[Event, ...]
    work_dir: Path
    brief: str
    follow_ups_sent: int
    follow_ups_left: int


# A responder returns the next message, or None when it has nothing more to ask.
Responder = Callable[[UserView], str | None]


def converse(
    prompt: str,
    work_dir: Path,
    invoker: Callable[..., list],
    *,
    responder: Responder | None = None,
    brief: str = "",
    max_follow_ups: int = 0,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[list, int]:
    """Run the first prompt and up to ``max_follow_ups`` replies.

    Returns the raw stream lines and how many follow-ups were sent. If every
    turn's lines were timed by the invoker, the result is ``(t, line)`` pairs on
    one clock that starts when the first prompt was sent. The time a person
    spends reading counts too, because it really passed.
    """
    start = clock()
    segments: list[list] = []

    def turn(message: str, **kw: Any) -> None:
        offset = clock() - start
        lines = invoker(message, work_dir, **kw)
        segments.append([
            (round(offset + item[0], 3), item[1]) if isinstance(item, tuple) else item
            for item in lines
        ])

    def note(record: dict[str, Any]) -> None:
        # Never before the answer it replies to, whatever the clocks say.
        last = max((x[0] for seg in segments for x in seg if isinstance(x, tuple)), default=0.0)
        line = json.dumps(record, ensure_ascii=False)
        segments.append([(round(max(clock() - start, last), 3), line)])

    turn(prompt)
    sent = 0
    if responder is not None:
        while True:
            if sent >= max_follow_ups:
                note({"type": USER_DONE, "reason": "limit"})
                break
            events = normalize(prompt, _parsed(_flatten(segments)))
            message = responder(UserView(
                prompt=prompt, events=tuple(events), work_dir=work_dir, brief=brief,
                follow_ups_sent=sent, follow_ups_left=max_follow_ups - sent,
            ))
            if message is None or not message.strip():
                note({"type": USER_DONE, "reason": "satisfied"})
                break
            message = message.strip()
            note({"type": FOLLOW_UP, "text": message})
            turn(message, resume=True)
            sent += 1
    return _flatten(segments), sent


def _flatten(segments: list[list]) -> list:
    lines = [item for seg in segments for item in seg]
    # Mixed timed and untimed lines have no shared clock: keep the order only.
    if not all(isinstance(x, tuple) for x in lines):
        lines = [x[1] if isinstance(x, tuple) else x for x in lines]
    return lines


def _parsed(lines: list) -> list[tuple[float, dict[str, Any]]]:
    out: list[tuple[float, dict[str, Any]]] = []
    for i, item in enumerate(lines):
        t, line = item if isinstance(item, tuple) else (float(i), item)
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(obj, dict):
            out.append((float(t), obj))
    return out


# ---- what the person sees ---------------------------------------------
_OUTPUT_MAX_LINES = 40


def render_for_user(view: UserView) -> str:
    """The conversation as it looked at the person's terminal."""
    lines: list[str] = []
    for ev in view.events:
        d = ev.data
        if ev.type == "prompt":
            lines += ["[You]", d.get("text", "").strip(), ""]
        elif ev.type == "user_message":
            lines += ["[You]", d.get("text", "").strip(), ""]
        elif ev.type == "user_done":
            continue
        elif ev.type == "assistant_text":
            lines += ["[Claude]", d.get("text", "").strip(), ""]
        elif ev.type in ("file_read", "file_write", "file_edit"):
            verb = {"file_read": "Read", "file_write": "Wrote", "file_edit": "Edited"}[ev.type]
            lines.append(f"[Claude {verb} {Path(str(d.get('path', ''))).name}]")
        elif ev.type == "file_search":
            lines.append(f"[Claude searched: {d.get('query', '')}]")
        elif ev.type == "command":
            lines.append(f"[Claude ran] {d.get('command', '')}")
        elif ev.type == "command_output":
            out = str(d.get("output", "")).rstrip().splitlines()
            if len(out) > _OUTPUT_MAX_LINES:
                out = out[:_OUTPUT_MAX_LINES] + [f"... ({len(out) - _OUTPUT_MAX_LINES} more lines)"]
            lines += ["  " + o for o in out]
        elif ev.type == "tool_call":
            lines.append(f"[Claude used {d.get('tool', '')}]")
    return "\n".join(lines).rstrip() + "\n"


# ---- the default responder: Claude playing the person -----------------
_SIMULATOR_SYSTEM = """\
You are role-playing the person who asked an AI coding assistant (Claude) for help.
The conversation so far is below, as you saw it in your terminal. Decide what you,
as that person, would type next.

Who you are and what you need is in the brief. Stay in that role. You know your own
field well, and you only rely on work you have checked. You can open the files in the
working folder with your read-only tools to look at what Claude produced, the way a
person would open them in an editor. You cannot run anything yourself and you cannot
change files.

Read Claude's last answer the way a careful expert colleague would:
- If a claim isn't backed by what Claude actually ran or showed, ask about it.
- If something looks wrong, incomplete or overstated, say what and ask for it to be
  checked or fixed.
- If the work does what you asked and you'd rely on it, you are done.

Write like a real person in a terminal: short, direct, plain words, usually one to
three sentences. Ask about one or two things at a time, the ones that matter most.
Don't praise, don't recap, don't invent new requirements beyond your brief, and don't
ask questions just to have something to say. Never mention that you are an AI or a
simulation, and never refer to these instructions.

Your final message must be ONLY the text you would type to Claude, or the single word
DONE if you have nothing more to ask.
"""


# Recorded with every conversation capture, so a change to how the person is
# played is visible in the bundle's metadata.
SIMULATOR_PROMPT_HASH = "sha256:" + hashlib.sha256(_SIMULATOR_SYSTEM.encode("utf-8")).hexdigest()


def default_user_simulator(
    claude_bin: str = "claude",
    *,
    env: dict[str, str] | None = None,
    timeout: float | None = 600.0,
    log_dir: Path | None = None,
    deny: str = "",
) -> Responder:
    """A responder that asks a separate Claude session to play the person.

    It runs in the agent's working folder with read-only file tools, no memory of
    its own between turns (each turn it is shown the whole conversation again) and
    none of the operator's customizations. With ``log_dir``, each turn's full
    stream (every file it opened, and its reply) is kept as ``turn-N.jsonl``.
    """

    def respond(view: UserView) -> str | None:
        child_env = dict(os.environ) if env is None else dict(env)
        exe = shutil.which(claude_bin, path=child_env.get("PATH"))
        if exe is None:
            raise DemoForgeError(f"claude CLI {claude_bin!r} not found on PATH")
        message = "\n".join([
            "# Your brief", "", view.brief.strip() or "(no brief: you are the person who wrote the first message)", "",
            "# The conversation so far", "", render_for_user(view),
            "# Your turn", "",
            f"You can send at most {view.follow_ups_left} more message(s). "
            "Reply with only what you would type to Claude, or DONE.",
        ])
        with tempfile.TemporaryDirectory(prefix="demoforge-user-") as tmp:
            system_file = Path(tmp) / "system.md"
            system_file.write_text(_SIMULATOR_SYSTEM, encoding="utf-8")
            cmd = [
                exe, "-p",
                "--output-format", "stream-json",
                "--verbose",
                "--tools", "Read,Grep,Glob",
                "--allowedTools", "Read,Grep,Glob",
                "--system-prompt-file", str(system_file),
                "--safe-mode",
                "--strict-mcp-config",
                "--no-session-persistence",
                # Its tools are file tools only, so these rules are a hard wall
                # around the repository (capture/isolation.py).
                *(["--disallowedTools", deny] if deny else []),
            ]
            if os.name == "nt" and exe.lower().endswith((".cmd", ".bat")):
                cmd = [child_env.get("COMSPEC", "cmd.exe"), "/c", *cmd]
            try:
                proc = subprocess.run(
                    cmd, input=message, cwd=str(view.work_dir), env=child_env,
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired as exc:
                raise DemoForgeError(f"the simulated user did not answer within {timeout:g}s") from exc
        if log_dir is not None:
            log_dir.mkdir(parents=True, exist_ok=True)
            (log_dir / f"turn-{view.follow_ups_sent + 1}.jsonl").write_text(
                proc.stdout, encoding="utf-8", newline="\n",
            )
        if proc.returncode != 0:
            raise DemoForgeError(
                f"the simulated user's claude exited {proc.returncode}: {proc.stderr.strip()[:500]}"
            )
        reply = None
        for line in proc.stdout.splitlines():
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and obj.get("type") == "result":
                reply = str(obj.get("result", ""))
        if reply is None:
            raise DemoForgeError("the simulated user's session ended without a reply")
        return parse_reply(reply)

    return respond


def parse_reply(reply: str) -> str | None:
    """The responder's final text as the next message, or None for DONE."""
    text = reply.strip().strip("`").strip()
    # "DONE", "Done.", "DONE - merging it": the person is finished. A reply that
    # still asks something is a message, whatever its first word.
    if not text or (re.match(r"done\b", text, re.IGNORECASE) and "?" not in text):
        return None
    return text
