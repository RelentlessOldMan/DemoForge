"""Just enough Markdown to show Claude's messages the way a reader sees them.

Claude writes its answers in Markdown. Shown raw, a frame is full of ``**``, back
ticks and code fences that the person in the terminal never saw as symbols. This
renders the subset Claude uses (paragraphs, headings, bullet and numbered lists,
fenced code, tables, bold, italics and inline code) to HTML. Everything else stays
as text. All text is HTML-escaped first, so recorded content can never inject
markup into a frame.

It also splits a message into blocks, so a long message can be shown over several
pages without breaking a list, table or code block in the middle.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

_FENCE = re.compile(r"^\s*(```|~~~)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_NUMBERED = re.compile(r"^(\s*)(\d+)[.)]\s+(.*)$")
_TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


@dataclass(frozen=True)
class Block:
    """One paragraph, list, table, code block or heading, as source lines."""

    kind: str  # "p", "h", "ul", "ol", "code", "table"
    lines: tuple[str, ...]

    def text(self) -> str:
        return "\n".join(self.lines)


def blocks(text: str) -> list[Block]:
    """Split Markdown source into top-level blocks, keeping each one whole."""
    out: list[Block] = []
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if _FENCE.match(line):
            fence = _FENCE.match(line).group(1)
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith(fence):
                j += 1
            out.append(Block("code", tuple(lines[i:j + 1])))
            i = j + 1
            continue
        if _HEADING.match(line):
            out.append(Block("h", (line,)))
            i += 1
            continue
        if "|" in line and i + 1 < len(lines) and _TABLE_RULE.match(lines[i + 1]):
            j = i + 2
            while j < len(lines) and "|" in lines[j] and lines[j].strip():
                j += 1
            out.append(Block("table", tuple(lines[i:j])))
            i = j
            continue
        for kind, pat in (("ul", _BULLET), ("ol", _NUMBERED)):
            if pat.match(line):
                j = i + 1
                # A list runs on through its items and their indented continuations.
                while j < len(lines) and lines[j].strip() and (
                    pat.match(lines[j]) or lines[j].startswith((" ", "\t"))
                ):
                    j += 1
                out.append(Block(kind, tuple(lines[i:j])))
                i = j
                break
        else:
            j = i + 1
            while j < len(lines) and lines[j].strip() and not _starts_block(lines, j):
                j += 1
            out.append(Block("p", tuple(lines[i:j])))
            i = j
    return out


def _starts_block(lines: list[str], j: int) -> bool:
    line = lines[j]
    return bool(
        _FENCE.match(line) or _HEADING.match(line) or _BULLET.match(line)
        or _NUMBERED.match(line)
        or ("|" in line and j + 1 < len(lines) and _TABLE_RULE.match(lines[j + 1]))
    )


def to_html(text: str) -> str:
    """Render ``text`` to safe HTML."""
    return "\n".join(_block_html(b) for b in blocks(text))


def _block_html(b: Block) -> str:
    if b.kind == "code":
        body = list(b.lines[1:])
        if body and _FENCE.match(body[-1]):
            body = body[:-1]
        return f'<pre class="md-code">{html.escape(chr(10).join(body))}</pre>'
    if b.kind == "h":
        m = _HEADING.match(b.lines[0])
        return f'<p class="md-h">{_inline(m.group(2))}</p>'
    if b.kind == "table":
        rows = [_cells(r) for r in b.lines if not _TABLE_RULE.match(r)]
        head, body = rows[0], rows[1:]
        th = "".join(f"<th>{_inline(c)}</th>" for c in head)
        trs = "".join(
            "<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in body
        )
        return f'<table class="md-table"><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>'
    if b.kind in ("ul", "ol"):
        pat = _BULLET if b.kind == "ul" else _NUMBERED
        items: list[list[str]] = []
        for line in b.lines:
            m = pat.match(line)
            if m and len(m.group(1)) <= 1:
                items.append([m.group(m.lastindex)])
            elif items:
                sub = _BULLET.match(line) or _NUMBERED.match(line)
                items[-1].append(("• " + sub.group(sub.lastindex)) if sub else line.strip())
        lis = "".join(
            "<li>" + "<br>".join(_inline(part) for part in item) + "</li>" for item in items
        )
        start = ""
        if b.kind == "ol":
            first = _NUMBERED.match(b.lines[0])
            if first and first.group(2) != "1":
                start = f' start="{int(first.group(2))}"'
        return f'<{b.kind} class="md-list"{start}>{lis}</{b.kind}>'
    return f'<p class="md-p">{"<br>".join(_inline(line.strip()) for line in b.lines)}</p>'


def _cells(row: str) -> list[str]:
    row = row.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|"):
        row = row[:-1]
    # An escaped pipe is part of the cell, not a column break (GFM).
    return [c.strip().replace("\\|", "|") for c in _CELL_BREAK.split(row)]


_CELL_BREAK = re.compile(r"(?<!\\)\|")
_CODE_SPAN = re.compile(r"`([^`]+)`")
# A backslash before ASCII punctuation stands for that character itself (CommonMark).
_ESCAPE = re.compile(r"\\([!-/:-@\[-`{-~])")
_BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_ITALIC = re.compile(r"(?<![\w*])\*(?!\s)([^*]+?)(?<!\s)\*(?![\w*])")


def _inline(text: str) -> str:
    """Inline code, bold and italics; code spans are never formatted inside.

    Code spans are set aside as placeholders first, so emphasis can wrap them
    (``**`file.m`**``) without anything inside them being read as Markdown.
    """
    codes: list[str] = []

    def stash(m: re.Match) -> str:
        codes.append(f"<code>{html.escape(m.group(1))}</code>")
        return f"\x00{len(codes) - 1}\x00"

    def literal(m: re.Match) -> str:
        codes.append(html.escape(m.group(1)))
        return f"\x00{len(codes) - 1}\x00"

    s = _ESCAPE.sub(literal, _CODE_SPAN.sub(stash, text.replace("\x00", "")))
    s = html.escape(s, quote=False)
    s = _BOLD.sub(lambda m: f"<strong>{m.group(1) or m.group(2)}</strong>", s)
    s = _ITALIC.sub(lambda m: f"<em>{m.group(1)}</em>", s)
    return re.sub("\x00(\\d+)\x00", lambda m: codes[int(m.group(1))], s)


def plain(text: str) -> str:
    """The words a reader sees, without Markdown symbols (for timing by length)."""
    s = _CODE_SPAN.sub(lambda m: m.group(1), text)
    s = _ESCAPE.sub(lambda m: m.group(1), s)
    s = _BOLD.sub(lambda m: m.group(1) or m.group(2), s)
    s = re.sub(r"^\s*(```|~~~).*$", "", s, flags=re.M)
    s = re.sub(r"^\s*#{1,6}\s+", "", s, flags=re.M)
    return s
