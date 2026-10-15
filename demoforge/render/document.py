"""A tiny block document model with Markdown and HTML emitters.

Records are built once as a list of blocks, then emitted to both Markdown and a
self-contained HTML page — so the two formats never drift, and neither needs a
third-party Markdown parser (keeping render dependency-free and deterministic).
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from typing import Iterable

# A block is a small tagged tuple; see the emitters below for the vocabulary.
Block = tuple


@dataclass
class Document:
    blocks: list[Block] = field(default_factory=list)

    def h1(self, text: str) -> "Document":
        return self._add(("h1", text))

    def h2(self, text: str) -> "Document":
        return self._add(("h2", text))

    def h3(self, text: str) -> "Document":
        return self._add(("h3", text))

    def p(self, text: str) -> "Document":
        return self._add(("p", text))

    def quote(self, text: str) -> "Document":
        return self._add(("quote", text))

    def code(self, text: str, lang: str = "") -> "Document":
        return self._add(("code", lang, text))

    def table(self, headers: list[str], rows: Iterable[list[str]]) -> "Document":
        return self._add(("table", list(headers), [list(r) for r in rows]))

    def ul(self, items: list[str]) -> "Document":
        return self._add(("ul", list(items)))

    def _add(self, block: Block) -> "Document":
        self.blocks.append(block)
        return self


# ---- Markdown ---------------------------------------------------------
def to_markdown(doc: Document) -> str:
    out: list[str] = []
    for block in doc.blocks:
        tag = block[0]
        if tag in ("h1", "h2", "h3"):
            hashes = {"h1": "#", "h2": "##", "h3": "###"}[tag]
            out.append(f"{hashes} {block[1]}")
        elif tag == "p":
            out.append(block[1])
        elif tag == "quote":
            out.append("\n".join(f"> {line}" for line in block[1].splitlines() or [""]))
        elif tag == "code":
            fence = _fence(block[2])
            out.append(f"{fence}{block[1]}\n{block[2]}\n{fence}")
        elif tag == "table":
            out.append(_md_table(block[1], block[2]))
        elif tag == "ul":
            out.append("\n".join(f"- {item}" for item in block[1]))
        out.append("")  # blank line between blocks
    return "\n".join(out).rstrip() + "\n"


def md_cell(value) -> str:
    """Escape a value for a GitHub-flavored Markdown table cell.

    A raw ``|`` ends the cell and a newline ends the row, so embedded check
    messages / values (which we do not control) would otherwise corrupt the
    table structure. Backslashes are left alone — Windows paths are common and a
    backslash before an ordinary character is literal in Markdown.
    """
    text = str(value).replace("|", "\\|")
    return text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def _fence(text: str) -> str:
    """A backtick fence guaranteed longer than any backtick run inside ``text``.

    Content embedded in a code block (agent artifacts, command output) may itself
    contain ``` ``` ``` fences; a fixed three-backtick fence would be closed early
    and break the document. CommonMark allows a longer fence to wrap shorter runs.
    """
    longest = run = 0
    for ch in text:
        run = run + 1 if ch == "`" else 0
        longest = max(longest, run)
    return "`" * max(3, longest + 1)


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(md_cell(h) for h in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for r in rows:
        lines.append("| " + " | ".join(md_cell(c) for c in r) + " |")
    return "\n".join(lines)


# ---- HTML -------------------------------------------------------------
_CSS = """
body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; max-width: 52rem;
       margin: 2rem auto; padding: 0 1rem; line-height: 1.5; color: #1a1a1a; }
h1 { border-bottom: 2px solid #ddd; padding-bottom: .3rem; }
h2 { margin-top: 2rem; border-bottom: 1px solid #eee; padding-bottom: .2rem; }
code, pre { font-family: ui-monospace, Consolas, monospace; }
pre { background: #f6f8fa; padding: .8rem; border-radius: 6px; overflow-x: auto; }
blockquote { border-left: 4px solid #ccc; margin: 0; padding: .2rem 1rem; color: #444; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #ddd; padding: .4rem .6rem; text-align: left; }
th { background: #f6f8fa; }
.pass { color: #0a7d28; font-weight: 600; }
.fail { color: #c0281a; font-weight: 600; }
""".strip()


def to_html(doc: Document, *, title: str) -> str:
    body: list[str] = []
    for block in doc.blocks:
        tag = block[0]
        if tag in ("h1", "h2", "h3"):
            body.append(f"<{tag}>{_esc(block[1])}</{tag}>")
        elif tag == "p":
            body.append(f"<p>{_esc(block[1])}</p>")
        elif tag == "quote":
            paras = "".join(f"<p>{_esc(par)}</p>" for par in block[1].split("\n\n"))
            body.append(f"<blockquote>{paras}</blockquote>")
        elif tag == "code":
            body.append(f"<pre><code>{_esc(block[2])}</code></pre>")
        elif tag == "table":
            body.append(_html_table(block[1], block[2]))
        elif tag == "ul":
            items = "".join(f"<li>{_esc(i)}</li>" for i in block[1])
            body.append(f"<ul>{items}</ul>")
    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        f"<title>{_esc(title)}</title>\n<style>\n{_CSS}\n</style>\n</head>\n<body>\n"
        + "\n".join(body)
        + "\n</body>\n</html>\n"
    )


def _html_table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body = ""
    for r in rows:
        cells = "".join(f"<td>{_cell(c)}</td>" for c in r)
        body += f"<tr>{cells}</tr>"
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _cell(text: str) -> str:
    # Let PASS/FAIL badges carry color; everything else is escaped plain text.
    s = str(text)
    if s == "PASS":
        return '<span class="pass">PASS</span>'
    if s == "FAIL":
        return '<span class="fail">FAIL</span>'
    return _esc(s)


def _esc(text: str) -> str:
    return html.escape(str(text))
