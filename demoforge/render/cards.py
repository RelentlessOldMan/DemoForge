"""Title, chapter and closing cards — the presentation's own structure (§2, §7, §9).

Cards are the one thing on screen that is *not* derived from a recorded run, and the
distinction is kept sharp on purpose: a :class:`~demoforge.render.timeline.Scene` is
always backed by events, a :class:`Card` never claims to be. Cards carry only facts
about the presentation itself — the set's title, which chapter is next, and a closing
statement about how the video was produced — and those facts are computed from the
chapters actually rendered, never asserted.

Like the deck (§4), the structure is derived: one chapter card per rendered demo, in
demo order. Adding a demo adds its card; nothing is hand-authored.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from demoforge.config import ContentSetConfig
from demoforge.render.config import Timing, VideoEncode
from demoforge.render.figures import FigureView
from demoforge.render.frames import _environment, font_face_css

TITLE_TEMPLATE = "title_card.html.j2"
CHAPTER_TEMPLATE = "chapter_card.html.j2"
OUTRO_TEMPLATE = "outro_card.html.j2"
CONTENTS_TEMPLATE = "contents_card.html.j2"
PROBLEM_TEMPLATE = "problem_card.html.j2"


@dataclass(frozen=True)
class Card:
    """A single presentation frame that stands outside any run's timeline."""

    id: str
    kind: str
    template: str
    duration: float
    data: dict[str, Any] = field(default_factory=dict)
    # A narration block to play over it, named as (demo_id, block key). The
    # `transition` block of the previous demo is what a chapter card is for.
    narration: tuple[str, str] | None = None

    def with_duration(self, seconds: float) -> "Card":
        """A copy at least ``seconds`` long — narration extends a card, never clips it."""
        if seconds <= self.duration:
            return self
        return Card(
            id=self.id,
            kind=self.kind,
            template=self.template,
            duration=round(seconds, 3),
            data=self.data,
            narration=self.narration,
        )


def title_card(config: ContentSetConfig, timing: Timing, *, demo_count: int) -> Card:
    """The opening card: what this content set is."""
    return Card(
        id="intro",
        kind="TitleCard",
        template=TITLE_TEMPLATE,
        duration=timing.title_card_seconds,
        data={
            "title": config.title,
            "subtitle": config.subtitle,
            "description": config.description,
            "demo_count": demo_count,
        },
    )


def clock(seconds: float) -> str:
    """A video position as a viewer types it into a player: ``m:ss`` or ``h:mm:ss``.

    Rounded down, so skipping to it never lands after the chapter has begun.
    """
    s = int(seconds)
    h, m, s = s // 3600, s // 60 % 60, s % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def contents_card(
    config: ContentSetConfig,
    timing: Timing,
    *,
    entries: list[tuple[int, str, float]],
) -> Card:
    """Where each demo starts in the presentation, so a viewer can skip to it.

    ``entries`` are (number, title, start seconds), the starts measured from the
    pieces actually joined, so every time on the card is where that chapter is.
    """
    return Card(
        id="contents",
        kind="ContentsCard",
        template=CONTENTS_TEMPLATE,
        duration=timing.contents_card_seconds,
        data={
            "title": config.title,
            "entries": [
                {"number": n, "title": t, "start": clock(start)} for n, t, start in entries
            ],
        },
    )


def chapter_card(
    *,
    demo_id: str,
    title: str,
    number: int,
    total: int,
    set_title: str,
    timing: Timing,
    narration: tuple[str, str] | None = None,
    caption: str = "",
) -> Card:
    """The card announcing one demo, optionally narrated by the previous one's handoff.

    ``caption`` is that handoff's text, shown so the card reads without sound.
    """
    return Card(
        id=f"chapter-{demo_id}",
        kind="ChapterCard",
        template=CHAPTER_TEMPLATE,
        duration=timing.chapter_card_seconds,
        data={
            "demo_id": demo_id,
            "title": title,
            "number": number,
            "total": total,
            "set_title": set_title,
            "caption": caption,
        },
        narration=narration,
    )


def problem_card(
    *,
    demo_id: str,
    title: str,
    number: int,
    paragraphs: list[str],
    timing: Timing,
    narration: tuple[str, str] | None = None,
    heading: str = "",
    part: int | None = None,
    figure: FigureView | None = None,
) -> Card:
    """One card of the demo's own introduction, on screen before its replay starts.

    The words are the demo's intro narration, so what the card says is exactly what
    the voice says, and it is reviewed in the same file. It lasts long enough to
    read even when the build has no voice. ``part`` numbers the cards when the
    introduction spans several; ``figure`` is drawn from a file in the demo folder.
    """
    chars = sum(len(p) for p in paragraphs)
    seconds = max(timing.scene_min_seconds, chars / timing.reading_chars_per_second)
    if figure is not None:
        # Time to look at the picture as well as read the words.
        seconds += timing.scene_min_seconds
    return Card(
        id=f"problem-{demo_id}" + (f"-{part}" if part is not None else ""),
        kind="ProblemCard",
        template=PROBLEM_TEMPLATE,
        # No upper bound: reading this card is the point of it.
        duration=round(seconds, 3),
        data={
            "demo_id": demo_id,
            "title": title,
            "number": number,
            "paragraphs": list(paragraphs),
            "heading": heading,
            "figure": (
                {"svg": figure.svg, "caption": figure.caption, "source": figure.source_note}
                if figure is not None else None
            ),
        },
        narration=narration,
    )


def outro_card(
    config: ContentSetConfig,
    timing: Timing,
    *,
    demo_count: int,
    event_count: int,
    seconds: float,
) -> Card:
    """The closing card (§9), stating how the video was made — with real counts.

    Every number here is measured from what was actually rendered, so the claim the
    card makes about itself is one the build can stand behind.
    """
    return Card(
        id="outro",
        kind="OutroCard",
        template=OUTRO_TEMPLATE,
        duration=timing.outro_card_seconds,
        data={
            "title": config.title,
            "demo_count": demo_count,
            "event_count": event_count,
            "minutes": round(seconds / 60.0, 1),
        },
    )


def card_html(
    card: Card,
    video: VideoEncode,
    *,
    templates_dir: Path | None = None,
    fonts_dir: Path | None = None,
) -> str:
    """Render a card's HTML. Pure, and shares the scene templates' fonts and chrome."""
    from demoforge.render.frames import TEMPLATES_DIR

    env = _environment(templates_dir or TEMPLATES_DIR)
    template = env.get_template(card.template)
    return template.render(
        kind=card.kind,
        data=card.data,
        duration=card.duration,
        font_css=font_face_css(fonts_dir),
        width=video.width,
        height=video.height,
    )
