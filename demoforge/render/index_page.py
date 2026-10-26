"""The ``index.html`` that ships beside a split presentation's videos.

Someone handed the zip (or the folder, on a file share) opens ``index.html`` and
gets what the set is for, a contents list, and each demo with its summary, its
checks and its video. It reads only committed files and the built videos, links
the videos by relative name, and loads nothing from the network, so the folder
works anywhere it is copied.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from demoforge.discovery import ContentSet
from demoforge.model import RunBundle
from demoforge.render.cards import clock
from demoforge.render.markdown import to_html
from demoforge.render.narration import Narration, display_text

INDEX_NAME = "index.html"
PACKAGE_TEMPLATES = Path(__file__).resolve().parents[2] / "templates" / "package"


@dataclass(frozen=True)
class IndexPart:
    """One video on the page: the opening (``number`` 0) or a demo."""

    number: int
    title: str
    file: str
    seconds: float
    summary_html: str = ""
    checks_passed: int = 0
    checks_total: int = 0


def write_index(
    cs: ContentSet,
    parts: list[IndexPart],
    out_path: Path,
    *,
    set_narration: Narration,
    templates_dir: Path | None = None,
) -> Path:
    """Render the page for ``parts`` (opening first) to ``out_path``."""
    from demoforge.render.frames import _environment

    env = _environment(templates_dir or PACKAGE_TEMPLATES)
    opening = next((p for p in parts if p.number == 0), None)
    demos = [p for p in parts if p.number != 0]
    html = env.get_template("index.html.j2").render(
        title=cs.config.title,
        subtitle=cs.config.subtitle,
        about=[
            {"heading": b.heading, "text": display_text(b.text)} for b in set_narration.intro
        ],
        opening=opening,
        demos=demos,
        total=clock(sum(p.seconds for p in parts)),
        clock=clock,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8", newline="\n")
    return out_path


def demo_part(cs: ContentSet, demo_id: str, *, number: int, title: str, file: Path, seconds: float) -> IndexPart:
    """A demo's entry: its ``summary`` file, if it has one, and its approved checks."""
    demo = next(d for d in cs.demos() if d.id == demo_id)
    summary = ""
    if demo.summary_path is not None and demo.summary_path.is_file():
        summary = summary_html(demo.summary_path.read_text(encoding="utf-8"))
    results = RunBundle(cs.approved_dir_for(demo_id)).read_results()
    judged = [c for c in results.checks if c.passed is not None]
    return IndexPart(
        number=number, title=title, file=file.name, seconds=seconds, summary_html=summary,
        checks_passed=sum(1 for c in judged if c.passed), checks_total=len(judged),
    )


_COMMENT = re.compile(r"<!--.*?-->", re.S)
_STARTS_BLOCK = re.compile(r"\s*([-*+]\s|\d+[.)]\s|#|\||```|~~~)")


def summary_html(text: str) -> str:
    """A summary's Markdown as HTML, with wrapped prose lines joined back up.

    The Markdown renderer keeps every line break (it is built for transcripts);
    a summary is prose wrapped for the editor, so a line that only continues a
    paragraph is joined to the one before it.
    """
    lines: list[str] = []
    for line in _COMMENT.sub("", text).strip().splitlines():
        if lines and lines[-1].strip() and line.strip() and not _STARTS_BLOCK.match(line) \
                and not _STARTS_BLOCK.match(lines[-1]):
            lines[-1] = f"{lines[-1].rstrip()} {line.strip()}"
        else:
            lines.append(line)
    return to_html("\n".join(lines))
