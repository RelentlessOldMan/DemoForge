"""Display-time path rewriting (``[display] paths`` in ``demoforge.toml``).

A captured run records the absolute paths the agent really used. What a viewer
*sees* is a different matter: a local folder layout is noise at best and
personal at worst. A :class:`PathRewriter` maps one path prefix to another.
Renderers apply it to what they show, and ``approve`` applies it (with
:func:`scrub_path_lists`) to the bundle it freezes, so a committed bundle never
holds the machine's own paths. The run under ``runs/`` keeps the original.

One rule covers every spelling a run produces for the same folder: native
(``C:\\a\\b``), forward-slash (``C:/a/b``), JSON/C-escaped (``C:\\\\a\\\\b``) and
MSYS (``/c/a/b``) and WSL (``/mnt/c/a/b``), plus the folder-name form Claude Code
uses for its per-project data (``C--a-b``, every character that is not a letter or
digit turned into ``-``). The matched spelling's separator is kept, so ``C:/a/b/x``
becomes ``G:/y/x`` and never a mix. Matching ignores case (Windows paths do) and
stops at a name boundary, so a rule for ``C:\\a`` leaves ``C:\\ab`` alone.

Rewriting changes no action, only how a path is spelled on screen, so it sits
on the right side of "never fabricate".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_SEPARATORS = (r"\\\\", r"\\", "/")  # longest first: an escaped "\\" is one separator


@dataclass(frozen=True)
class _Rule:
    pattern: re.Pattern[str]
    posix: re.Pattern[str] | None
    encoded: re.Pattern[str] | None
    to_drive: str
    to_parts: tuple[str, ...]
    to_rooted: bool


def _encode(drive: str, parts: tuple[str, ...]) -> str:
    """``('C', ('a', 'b.c'))`` → ``'C--a-b-c'``, as Claude Code names project folders."""
    return re.sub(r"[^A-Za-z0-9]", "-", f"{drive}:/" + "/".join(parts))


def _split(path: str) -> tuple[str, tuple[str, ...]]:
    """``'C:\\a\\b\\'`` →``('C', ('a', 'b'))``; a path without a drive gives ``''``."""
    path = path.strip().replace("\\", "/").strip("/")
    drive = ""
    if len(path) >= 2 and path[1] == ":":
        drive, path = path[0], path[2:].lstrip("/")
    return drive, tuple(p for p in path.split("/") if p)


class PathRewriter:
    """Rewrites path prefixes in text. Callable; the identity when it has no rules.

    All rules are matched against the original text in one pass, so one rule's
    output is never rewritten again by another.
    """

    def __init__(self, rules: dict[str, str] | tuple[tuple[str, str], ...] = ()):
        items = rules.items() if isinstance(rules, dict) else rules
        self.rules: tuple[tuple[str, str], ...] = tuple((str(a), str(b)) for a, b in items)
        compiled = []
        # Longest source first, so a nested rule wins over its parent folder.
        for src, dst in sorted(self.rules, key=lambda r: -len(_split(r[0])[1])):
            drive, parts = _split(src)
            if not parts:
                raise ValueError(f"path rule {src!r} names no folder")
            sep = "(?P<sep>" + "|".join(_SEPARATORS) + ")"
            body = "(?P=sep)".join(re.escape(p) for p in parts)
            head = f"{re.escape(drive)}:{sep}" if drive else sep
            end = r"(?![\w.-])"
            # MSYS (/c/x) and WSL (/mnt/c/x) spellings of a drive path.
            posix = (
                # Not inside a word or a URL, but a JSON escape (\n, \r, \t) may precede.
                re.compile(rf"(?:(?<![\w:])|(?<=\\[nrt]))(?P<mnt>/mnt)?/{re.escape(drive)}/"
                           + "/".join(map(re.escape, parts)) + end, re.IGNORECASE)
                if drive else None
            )
            # Claude Code's project-folder name for the path; a deeper folder
            # continues it with "-", so only a letter or digit is a non-boundary.
            encoded = (
                re.compile(r"(?<![A-Za-z0-9-])" + re.escape(_encode(drive, parts))
                           + r"(?![A-Za-z0-9])", re.IGNORECASE)
                if drive else None
            )
            to_drive, to_parts = _split(dst)
            rooted = dst.strip()[:1] in ("/", "\\")
            compiled.append(_Rule(
                re.compile(head + body + end, re.IGNORECASE), posix, encoded,
                to_drive, to_parts, rooted,
            ))
        self._compiled = tuple(compiled)

    def __bool__(self) -> bool:
        return bool(self.rules)

    def __call__(self, text: str) -> str:
        if not self._compiled:
            return text
        found: list[tuple[int, int, int, str]] = []  # start, end, rule rank, replacement
        for rank, rule in enumerate(self._compiled):
            for m in rule.pattern.finditer(text):
                found.append((m.start(), m.end(), rank, self._native(rule, m.group("sep"))))
            if rule.posix is not None:
                for m in rule.posix.finditer(text):
                    found.append((m.start(), m.end(), rank, self._posix(rule, bool(m.group("mnt")))))
            if rule.encoded is not None and rule.to_drive:
                for m in rule.encoded.finditer(text):
                    found.append((m.start(), m.end(), rank, _encode(rule.to_drive, rule.to_parts)))
        if not found:
            return text
        out, pos = [], 0
        for start, end, _, repl in sorted(found):
            if start < pos:
                continue  # overlaps a match already taken (earlier, or a longer rule)
            out += [text[pos:start], repl]
            pos = end
        out.append(text[pos:])
        return "".join(out)

    @staticmethod
    def _native(rule: _Rule, sep: str) -> str:
        body = sep.join(rule.to_parts)
        if rule.to_drive:
            return f"{rule.to_drive}:{sep}{body}"
        return (sep if rule.to_rooted else "") + body

    @staticmethod
    def _posix(rule: _Rule, mnt: bool) -> str:
        body = "/".join(rule.to_parts)
        if rule.to_drive:
            return ("/mnt" if mnt else "") + f"/{rule.to_drive.lower()}/{body}"
        return ("/" if rule.to_rooted else "") + body

    def apply(self, obj: Any) -> Any:
        """Rewrite every string inside a JSON-shaped value (keys included)."""
        if not self:
            return obj
        if isinstance(obj, str):
            return self(obj)
        if isinstance(obj, list):
            return [self.apply(v) for v in obj]
        if isinstance(obj, dict):
            return {self.apply(k): self.apply(v) for k, v in obj.items()}
        return obj

    def fingerprint(self) -> str:
        """Stable text for build cache keys: a rule change must re-render."""
        return "\n".join(f"{a}\t{b}" for a, b in self.rules)


IDENTITY = PathRewriter()


# A search-path listing (an echoed PATH, `which: no x in (...)`) names every tool
# installed on the machine. It is never part of what a demo shows, so approve
# removes the whole list. Five or more absolute entries joined by the list
# separator mark one: posix entries joined by ":", drive entries by ";". JSON
# escapes are honoured: an entry may hold "\\" (an escaped backslash) but stops at
# "\n", "\r", "\t" or a quote, so removal never runs past the end of a string.
_POSIX_ENTRY = r'/[^:;"\\\r\n]*'
_DRIVE_ENTRY = r'[A-Za-z]:(?:\\\\|\\(?![nrt"])|[^;"\\\r\n])*'
_PATH_LIST = re.compile(
    rf"(?<![\w/]){_POSIX_ENTRY}(?::{_POSIX_ENTRY}){{4,}}"
    rf"|(?<![\w]){_DRIVE_ENTRY}(?:;{_DRIVE_ENTRY}){{4,}}"
)
PATH_LIST_PLACEHOLDER = "<search path removed>"


def scrub_path_lists(text: str) -> str:
    """Replace every search-path listing in ``text`` with a placeholder."""
    return _PATH_LIST.sub(PATH_LIST_PLACEHOLDER, text)


# A long listing (``ls -l``) names each file's owner and group: the operator's
# account name. The mode string in front is specific enough to find the columns
# in raw text and inside JSON strings alike.
_LONG_LISTING = re.compile(
    r"(?P<lead>(?:(?<![\w-])|(?<=\\n)|(?<=\\t))[-dlcbps][rwxsStT-]{9}[.+@]?[ \t]+\d+[ \t]+)"
    r"(?P<owner>[^\s\\\"]+)(?P<gap>[ \t]+)(?P<group>[^\s\\\"]+)(?P<tail>[ \t]+\d)"
)
OWNER_PLACEHOLDER = "user"


def scrub_file_owners(text: str) -> str:
    """Replace the owner and group columns of every long file listing in ``text``."""
    return _LONG_LISTING.sub(
        lambda m: f"{m['lead']}{OWNER_PLACEHOLDER}{m['gap']}{OWNER_PLACEHOLDER}{m['tail']}", text
    )
