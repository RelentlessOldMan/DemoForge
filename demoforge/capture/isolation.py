"""Did either session look at something a demo keeps from it?

A demo's agent and its simulated user must solve the problem from the demo's
inputs alone. The capture runs them in a sandbox outside the repository, but
their tools can still name any absolute path. So after a capture every recorded
tool call, and every result the tools returned, is searched for:

- a path inside the repository or content set (the hidden checks, the reference
  solution, earlier approved runs), in any spelling the path rules know;
- the name of a file in the demo's ``checks/`` folder;
- a distinctive line of a hidden check file (harness, mutant, expected data),
  so a read that never names the file (a glob, ``find | xargs cat``) still shows
  up in what the tool returned.

A hit is not proof of a breach (an agent may name its own test ``run_tests.m``),
so the audit reports and records findings for a person to judge; it never
silently passes or rejects a run.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from demoforge.redact import PathRewriter

_MARK = "\x00forbidden\x00"
_SNIPPET = 160


@dataclass(frozen=True)
class Finding:
    source: str  # "agent" or "user simulator turn N"
    record: int  # index of the raw stream record
    reason: str
    snippet: str

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def audit(
    streams: dict[str, Iterable[dict[str, Any]]],
    forbidden_roots: Iterable[Path],
    hidden_names: Iterable[str] = (),
    hidden_lines: Iterable[str] = (),
) -> list[Finding]:
    """Findings across every session's raw stream records."""
    roots = [Path(r) for r in forbidden_roots]
    lines = sorted(set(hidden_lines))
    rewriter = PathRewriter(tuple((str(r), _MARK) for r in roots))
    names = sorted({n.lower() for n in hidden_names if n})
    out: list[Finding] = []
    for source, records in streams.items():
        for i, record in enumerate(records):
            for text in _tool_texts(record):
                low = text.lower()
                marked = rewriter(text)
                if marked != text:
                    at = marked.index(_MARK)
                    out.append(Finding(source, i, "names a path inside the repository",
                                       _snip(text, at)))
                    continue
                for name in names:
                    if name in low:
                        out.append(Finding(source, i, f"mentions hidden check file {name!r}",
                                           _snip(text, low.index(name))))
                        break
                else:
                    for line in lines:
                        if line in text:
                            out.append(Finding(source, i, "contains a line of a hidden file",
                                               _snip(text, text.index(line))))
                            break
    return out


# A line shorter than this is too common (``end``, ``x = F * x;``) to point at a file.
_MIN_LINE = 24


def fingerprints(files: Iterable[Path], allowed_texts: Iterable[str] = ()) -> list[str]:
    """Distinctive lines of hidden ``files`` that a session must never be shown.

    A line counts if it is long enough to be specific and its words do not also
    appear in anything the sessions are given (the prompt, the inputs, the brief):
    the spec's own ``X = f(Z, model)`` written with a semicolon is not a leak.
    """
    allowed = "\n".join(allowed_texts)
    out: set[str] = set()
    for path in files:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for raw in text.splitlines():
            line = raw.strip()
            if len(_core(line)) >= _MIN_LINE and _core(line) not in allowed:
                out.add(line)
    return sorted(out)


def _core(line: str) -> str:
    """A line without comment markers and trailing punctuation."""
    return line.strip().lstrip("%#/;* ").rstrip(";, ").strip()


def _tool_texts(record: dict[str, Any]) -> list[str]:
    """The tool inputs and tool results in one raw stream record."""
    msg = record.get("message") if isinstance(record, dict) else None
    content = msg.get("content") if isinstance(msg, dict) else None
    if not isinstance(content, list):
        return []
    texts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "tool_use":
            texts.append(json.dumps(block.get("input") or {}, ensure_ascii=False))
        elif block.get("type") == "tool_result":
            body = block.get("content")
            texts.append(body if isinstance(body, str) else json.dumps(body, ensure_ascii=False))
    return texts


def _snip(text: str, at: int) -> str:
    start = max(0, at - _SNIPPET // 2)
    return text[start:start + _SNIPPET].replace("\n", " ")


def read_stream(path: Path) -> list[dict[str, Any]]:
    """A raw stream file's JSON records (unreadable lines are skipped)."""
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def deny_rules(roots: Iterable[Path]) -> str:
    """Claude Code permission rules that stop file tools reading under ``roots``.

    ``Read(//c/x/**)`` names an absolute path; the rule also covers Grep and Glob.
    For a session with only file tools this is a hard wall. A shell can still
    read anything, which is why :func:`audit` runs after every capture.
    """
    rules: list[str] = []
    for root in roots:
        posix = Path(root).resolve().as_posix()
        if len(posix) >= 2 and posix[1] == ":":
            posix = f"/{posix[0].lower()}{posix[2:]}"
        posix = posix.rstrip("/")
        rules += [f"Read(/{posix}/**)", f"Edit(/{posix}/**)"]
    return ",".join(rules)
