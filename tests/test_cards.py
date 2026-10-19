"""Presentation cards: derived structure, real counts, and no borrowed claims.

The important assertion here is the negative one — a card must not inherit the scene
chrome that says which recorded events a frame came from, because a card has no run
behind it.
"""

from __future__ import annotations

import pytest

from conftest import requires_jinja

from demoforge.config import ContentSetConfig, PresentationConfig
from demoforge.render.cards import (
    Card,
    card_html,
    chapter_card,
    clock,
    contents_card,
    outro_card,
    title_card,
)
from demoforge.render.config import Timing, VideoEncode

pytestmark = requires_jinja

VIDEO = VideoEncode()
TIMING = Timing()
CONFIG = ContentSetConfig(
    id="kit", title="TestKit", subtitle="doing real work", description="A set of demos."
)


# ---- the line between a card and a scene ------------------------------
def test_a_card_never_claims_a_capture_behind_it():
    cards = [
        title_card(CONFIG, TIMING, demo_count=3),
        chapter_card(
            demo_id="demo-a", title="Demo A", number=1, total=3,
            set_title="TestKit", timing=TIMING,
        ),
        outro_card(CONFIG, TIMING, demo_count=3, event_count=42, seconds=300.0),
    ]
    for card in cards:
        html = card_html(card, VIDEO)
        assert "captured events " not in html, card.kind
        assert "time-compressed" not in html, card.kind


def test_cards_render_with_the_bundled_fonts():
    html = card_html(title_card(CONFIG, TIMING, demo_count=1), VIDEO)
    assert "@font-face" in html and "data:font/woff2;base64," in html
    assert "DemoForge Sans" in html


# ---- derived content --------------------------------------------------
def test_the_title_card_states_what_the_set_is():
    html = card_html(title_card(CONFIG, TIMING, demo_count=4), VIDEO)
    assert "TestKit" in html
    assert "doing real work" in html
    assert "A set of demos." in html
    assert "4 captured demos" in html


def test_the_title_card_counts_one_demo_in_the_singular():
    html = card_html(title_card(CONFIG, TIMING, demo_count=1), VIDEO)
    assert "1 captured demo" in html
    assert "1 captured demos" not in html


def test_a_chapter_card_is_derived_from_its_position():
    card = chapter_card(
        demo_id="log-investigation", title="Log Investigation", number=4, total=10,
        set_title="TestKit", timing=TIMING,
    )
    html = card_html(card, VIDEO)
    assert "04" in html and "of 10" in html
    assert "Log Investigation" in html and "log-investigation" in html
    assert card.id == "chapter-log-investigation"


def test_the_closing_card_counts_what_was_actually_rendered():
    card = outro_card(CONFIG, TIMING, demo_count=2, event_count=37, seconds=312.0)
    html = card_html(card, VIDEO)
    assert ">37<" in html or "37" in html
    assert "5.2" in html          # 312s rendered as minutes
    assert "demoforge build --video" in html
    # The claim the card makes is the property the timeline enforces.
    assert "not re-enacted" in html


def test_the_contents_card_lists_each_demo_with_where_it_starts():
    card = contents_card(
        CONFIG, TIMING, entries=[(1, "Implementation", 10.0), (2, "Optimization", 412.7)]
    )
    html = card_html(card, VIDEO)
    assert "Skip to a demo" in html
    assert "Implementation" in html and "Optimization" in html
    assert ">0:10<" in html and ">6:52<" in html
    assert card.duration == TIMING.contents_card_seconds


def test_a_clock_time_rounds_down_and_shows_hours_only_when_needed():
    assert clock(0.0) == "0:00"
    assert clock(59.99) == "0:59"
    assert clock(412.7) == "6:52"
    assert clock(3600.0) == "1:00:00"
    assert clock(3725.4) == "1:02:05"


# ---- narration stretches, never clips ---------------------------------
def test_narration_only_lengthens_a_card():
    card = chapter_card(
        demo_id="d", title="D", number=1, total=1, set_title="K", timing=TIMING
    )
    assert card.duration == TIMING.chapter_card_seconds

    longer = card.with_duration(card.duration + 5.0)
    assert longer.duration == pytest.approx(card.duration + 5.0)
    assert longer.id == card.id and longer.data == card.data

    # A shorter clip must not shorten the card, and returns the same object.
    assert card.with_duration(0.5) is card


def test_a_chapter_card_records_which_narration_block_it_borrows():
    card = chapter_card(
        demo_id="second", title="Second", number=2, total=2,
        set_title="K", timing=TIMING, narration=("first", "transition"),
    )
    assert card.narration == ("first", "transition")


# ---- config gates -----------------------------------------------------
def test_intro_and_outro_are_switchable_in_content_set_config():
    off = ContentSetConfig(
        id="kit", title="K", presentation=PresentationConfig(intro=False, outro=False)
    )
    assert off.presentation.intro is False and off.presentation.outro is False
    assert CONFIG.presentation.intro is True and CONFIG.presentation.outro is True


def test_card_durations_come_from_config():
    timing = Timing(title_card_seconds=3.0, chapter_card_seconds=2.0, outro_card_seconds=11.0)
    assert title_card(CONFIG, timing, demo_count=1).duration == 3.0
    assert chapter_card(
        demo_id="d", title="D", number=1, total=1, set_title="K", timing=timing
    ).duration == 2.0
    assert outro_card(
        CONFIG, timing, demo_count=1, event_count=1, seconds=1.0
    ).duration == 11.0


def test_a_zero_length_card_is_rejected_in_config():
    from demoforge.errors import ConfigError

    with pytest.raises(ConfigError, match="chapter_card_seconds"):
        Timing(chapter_card_seconds=0.0)


# ---- determinism ------------------------------------------------------
def test_card_markup_is_stable():
    card = title_card(CONFIG, TIMING, demo_count=3)
    assert card_html(card, VIDEO) == card_html(card, VIDEO)


def test_a_card_is_frozen():
    card = title_card(CONFIG, TIMING, demo_count=1)
    with pytest.raises(Exception):
        card.duration = 99.0  # type: ignore[misc]
    assert isinstance(card, Card)
