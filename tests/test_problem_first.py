"""A demo's video explains the problem to the viewer before any of the run is shown."""

from __future__ import annotations

import pytest

from conftest import requires_ffmpeg

from demoforge.discovery import load_content_set
from demoforge.errors import DemoError
from demoforge.render.figures import figure_view
from demoforge.render.narration import parse_narration

from test_video_pipeline import _build, _set


def test_a_figure_is_shown_never_spoken():
    n = parse_narration(
        "## intro:The data\n\nA noisy stream.\n\n![The readings](input/seed.csv)\n"
    )
    [block] = n.blocks
    assert block.text == "A noisy stream."
    assert block.figure.source == "input/seed.csv"
    assert block.figure.caption == "The readings"
    assert block.heading == "The data"
    assert block.is_intro


def test_only_an_intro_block_can_carry_a_figure():
    with pytest.raises(DemoError, match="figure"):
        parse_narration("## during:3\n\nIt reads.\n\n![x](input/a.csv)\n")


def test_intro_blocks_are_left_out_of_the_replay():
    n = parse_narration(
        "## intro:One\n\nA.\n\n## setup\n\nB.\n\n## during:0\n\nC.\n\n## result\n\nD.\n"
    )
    assert [b.key for b in n.intro] == ["intro:One", "setup"]
    assert [b.key for b in n.replayed.blocks] == ["during:0", "result"]


def test_a_figure_is_plotted_from_the_file_and_says_so(tmp_path):
    (tmp_path / "input").mkdir()
    (tmp_path / "input" / "z.csv").write_text(
        "meas_x,meas_y\n0,0\n1,0.5\n2,1.5\n", encoding="utf-8"
    )
    view = figure_view(tmp_path, "input/z.csv", "Readings")
    assert view.svg.count("<circle") == 3
    assert view.source_note == (
        "Plotted from input/z.csv: all 3 rows, meas_y against meas_x."
    )


def test_a_close_up_says_which_rows_it_shows(tmp_path):
    (tmp_path / "z.csv").write_text(
        "x,y\n" + "".join(f"{i},{i % 2}\n" for i in range(10)), encoding="utf-8"
    )
    view = figure_view(tmp_path, "z.csv#rows=2-4", "Close up")
    assert view.svg.count("<circle") == 3
    assert view.source_note == "Plotted from z.csv: rows 2–4 of 10, y against x."
    with pytest.raises(DemoError, match="rows 1-10"):
        figure_view(tmp_path, "z.csv#rows=5-11", "x")
    with pytest.raises(DemoError, match="#rows=A-B"):
        figure_view(tmp_path, "z.csv#first=3", "x")


def test_a_figure_must_live_in_the_demo_folder(tmp_path):
    (tmp_path / "demo").mkdir()
    (tmp_path / "outside.csv").write_text("1,2\n", encoding="utf-8")
    with pytest.raises(DemoError, match="outside the demo folder"):
        figure_view(tmp_path / "demo", "../outside.csv", "x")


def test_a_figure_refuses_rows_that_are_not_numbers(tmp_path):
    (tmp_path / "bad.csv").write_text("a,b\n1,2\nx,3\n", encoding="utf-8")
    with pytest.raises(DemoError, match="row 2"):
        figure_view(tmp_path, "bad.csv", "x")


@requires_ffmpeg
def test_a_demo_rendered_alone_opens_with_its_problem(tmp_path):
    cs = _set(tmp_path)
    summary = _build(cs, presentation=False)

    chapter = summary.chapters[0]
    assert summary.presentation is None
    assert [c.path.stem for c in chapter.intro] == ["problem-alpha"]
    assert chapter.parts == [chapter.intro[0].path, chapter.replay.path]
    # The demo's own file is the intro followed by the replay, not the replay alone.
    assert chapter.video.path.name == "alpha.mp4"
    assert chapter.video.path != chapter.replay.path
    assert chapter.video.seconds == pytest.approx(
        chapter.intro[0].seconds + chapter.replay.seconds
    )


@requires_ffmpeg
def test_each_headed_intro_block_gets_its_own_card(tmp_path):
    cs = _set(tmp_path)
    demo_dir = cs.demos_dir / "alpha"
    (demo_dir / "input" / "stream.csv").write_text("x,y\n0,0\n1,1\n", encoding="utf-8")
    (demo_dir / "narration.md").write_text(
        "## intro:The situation\n\nA drone is tracked by a noisy sensor.\n\n"
        "## intro:The data\n\nHere is what the sensor reported.\n\n"
        "![The readings](input/stream.csv)\n\n"
        "## during:0\n\nThe engineer asks for the filter.\n",
        encoding="utf-8",
    )
    summary = _build(load_content_set(cs.root), presentation=False)

    chapter = summary.chapters[0]
    assert [c.path.stem for c in chapter.intro] == ["problem-alpha-1", "problem-alpha-2"]
    # The prompt is narrated on the replay's first scene, not left silent.
    assert chapter.timeline.scenes[0].narration == "during:0"


@requires_ffmpeg
def test_the_presentation_reuses_the_chapter_parts(tmp_path):
    cs = _set(tmp_path, approve=("alpha", "beta"))
    summary = _build(cs)
    # Intro cards sit inside their chapter, so they are not counted as set cards.
    assert not any(c.path.stem.startswith("problem-") for c in summary.cards)
    assert all(len(c.intro) == 1 for c in summary.chapters)
