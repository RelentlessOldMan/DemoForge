"""The whole video DAG: approved bundles -> chapters -> presentation, and the CLI."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from conftest import requires_ffmpeg

from demoforge.capture import approve_run, run_demo
from demoforge.discovery import load_content_set
from demoforge.errors import DemoError
from demoforge.render.cards import clock
from demoforge.render.config import VideoEncode, load_settings
from demoforge.render.timeline import read_timeline
from demoforge.render.video_pipeline import PRESENTATION_NAME, build_videos

WHEN = datetime(2026, 10, 5, 12, 0, 0, tzinfo=timezone.utc)

pytestmark = requires_ffmpeg


class _StubRenderer:
    """Writes a real, tiny PNG so ffmpeg has something to encode, without a browser."""

    def __init__(self) -> None:
        self.calls = 0

    def render(self, html: str, out_path: Path) -> None:
        import struct
        import zlib

        self.calls += 1
        w = h = 64
        raw = b"".join(b"\0" + bytes([18, 24, 42]) * w for _ in range(h))

        def chunk(tag: bytes, body: bytes) -> bytes:
            return (
                struct.pack(">I", len(body))
                + tag
                + body
                + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)
            )

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b"")
        )


def _invoker(prompt, work_dir):
    (work_dir / "result.out").write_text("done\n", encoding="utf-8")
    return [
        json.dumps({"type": "system", "subtype": "init", "model": "claude-test"}),
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "Working on it."},
            {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "make"}},
        ]}}),
        json.dumps({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "built ok"},
        ]}}),
        json.dumps({"type": "result", "subtype": "success", "is_error": False}),
    ]


def _set(
    tmp_path: Path,
    *,
    approve: tuple[str, ...] = ("alpha",),
    narration: bool = True,
    prompt: str = "Produce result.out for {name}.\n",
):
    """A content set with two demos; only the named ones get an approved capture."""
    root = tmp_path / "set"
    for name in ("alpha", "beta"):
        d = root / "demos" / name
        (d / "input").mkdir(parents=True)
        (d / "input" / "seed.txt").write_text("seed\n", encoding="utf-8")
        (d / "prompt.md").write_text(prompt.format(name=name), encoding="utf-8")
        narration_line = "narration: narration.md\n" if narration else ""
        if narration:
            (d / "narration.md").write_text(
                "## setup\n\nWe hand Claude a real engineering job and let it work, "
                "then check what it produced against a harness it never sees.\n\n"
                "## result\n\nIt produced the artifact, and the checks agree.\n",
                encoding="utf-8",
            )
        (d / "demo.yaml").write_text(
            f"id: {name}\ntitle: Demo {name.title()}\nruntime: none\n{narration_line}"
            "inputs:\n  - input/seed.txt\n"
            "checks:\n  - id: produced\n    kind: file_exists\n    pattern: result.out\n",
            encoding="utf-8",
        )
    (root / "demoforge.toml").write_text(
        '[set]\nid = "vid-set"\ntitle = "Video Set"\n', encoding="utf-8"
    )

    cs = load_content_set(root)
    for demo in cs.demos():
        if demo.id in approve:
            result = run_demo(demo, cs, invoker=_invoker, when=WHEN, git_commit="cafe")
            approve_run(cs, demo.id, run_id=result.run_id)
    return cs


def _settings(cs):
    st = load_settings(cs.root)
    small = VideoEncode(**{**st.video.__dict__, "width": 64, "height": 64, "preset": "ultrafast"})
    return type(st)(scenes=st.scenes, timing=st.timing, video=small)


def _build(cs, **kwargs):
    return build_videos(
        cs, settings=_settings(cs), renderer=kwargs.pop("renderer", _StubRenderer()), **kwargs
    )


# ---- happy path -------------------------------------------------------
def test_an_approved_demo_becomes_a_chapter(tmp_path):
    cs = _set(tmp_path)
    summary = _build(cs)

    assert [c.demo_id for c in summary.chapters] == ["alpha"]
    chapter = summary.chapters[0]
    assert chapter.video.path.is_file()
    assert chapter.seconds > 0
    # Every scene is drawn, in order; an animated one as several frames that
    # together last exactly as long as the scene.
    scenes = chapter.timeline.scenes
    assert sorted({f.scene_index for f in chapter.frames}) == [s.index for s in scenes]
    assert [f.scene_index for f in chapter.frames] == sorted(f.scene_index for f in chapter.frames)
    for s in scenes:
        held = sum(f.duration for f in chapter.frames if f.scene_index == s.index)
        assert held == pytest.approx(s.duration, abs=1e-6)
    assert summary.presentation is not None
    assert summary.presentation.path.name == PRESENTATION_NAME


def test_the_timeline_is_written_beside_the_video(tmp_path):
    cs = _set(tmp_path)
    summary = _build(cs)
    path = cs.output_dir / "video" / "alpha" / "timeline.json"
    assert path.is_file()
    assert read_timeline(path) == summary.chapters[0].timeline


def test_narration_lengthens_the_chapter(tmp_path):
    with_words = _build(_set(tmp_path / "a")).seconds
    without = _build(_set(tmp_path / "b", narration=False)).seconds
    assert with_words > without


# ---- honest reporting -------------------------------------------------
def test_unapproved_demos_are_reported_not_invented(tmp_path):
    summary = _build(_set(tmp_path))
    assert summary.skipped == ["beta"]
    assert all(c.demo_id != "beta" for c in summary.chapters)


def test_a_silent_build_does_not_pass_for_a_narrated_one(tmp_path):
    summary = _build(_set(tmp_path))
    assert summary.narration_provider == "silent"
    assert summary.narrated is False
    assert "piper" in summary.narration_note


def test_a_set_with_nothing_approved_renders_nothing(tmp_path):
    summary = _build(_set(tmp_path, approve=()))
    assert summary.chapters == []
    assert summary.presentation is None
    assert sorted(summary.skipped) == ["alpha", "beta"]


# ---- selection + options ----------------------------------------------
def test_a_single_demo_can_be_rendered(tmp_path):
    cs = _set(tmp_path, approve=("alpha", "beta"))
    summary = _build(cs, only="beta")
    assert [c.demo_id for c in summary.chapters] == ["beta"]


def test_an_unknown_demo_id_is_an_error(tmp_path):
    with pytest.raises(DemoError, match="no enabled demo"):
        _build(_set(tmp_path), only="ghost")


def test_the_presentation_can_be_skipped(tmp_path):
    summary = _build(_set(tmp_path), presentation=False)
    assert summary.chapters and summary.presentation is None


def test_chapters_join_in_demo_order(tmp_path):
    cs = _set(tmp_path, approve=("alpha", "beta"))
    summary = _build(cs)
    assert [c.demo_id for c in summary.chapters] == ["alpha", "beta"]
    # The running time is the chapters plus the cards placed around them.
    assert summary.seconds == pytest.approx(
        sum(c.seconds for c in summary.chapters) + sum(c.seconds for c in summary.cards)
    )


# ---- incrementality ---------------------------------------------------
def test_rebuilding_unchanged_does_no_work(tmp_path):
    cs = _set(tmp_path)
    first = _build(cs)
    assert first.chapters[0].video.cached is False

    renderer = _StubRenderer()
    second = _build(cs, renderer=renderer)
    assert renderer.calls == 0
    assert second.chapters[0].video.cached is True
    assert second.presentation.cached is True
    assert all(f.cached for f in second.chapters[0].frames)


def test_force_rebuilds_the_video_layer_rather_than_reporting_it_cached(tmp_path):
    """``--force`` has to reach the video caches, not just the build orchestrator.

    The video caches are content-addressed and keyed separately from the build
    report, so a force that stops at the orchestrator silently returns
    "cached" for every frame and clip — which is exactly what makes a forced
    rebuild useless for proving the cache is telling the truth.
    """
    cs = _set(tmp_path)
    _build(cs)

    renderer = _StubRenderer()
    forced = _build(cs, renderer=renderer, force=True)

    assert renderer.calls > 0, "no frame was re-rendered"
    assert forced.chapters[0].video.cached is False
    assert forced.presentation.cached is False
    assert not any(f.cached for f in forced.chapters[0].frames)
    assert all(c.cached is False for c in forced.cards)


def test_forcing_still_produces_the_same_outputs(tmp_path):
    """A forced rebuild must be a no-op in substance: same scenes, same durations.

    Otherwise "ignore the cache" would quietly mean "render something else", and
    the cache would be hiding a non-determinism bug rather than exposing one.
    """
    cs = _set(tmp_path)
    before = _build(cs)
    after = _build(cs, force=True)

    assert [s.kind for s in before.chapters[0].timeline.scenes] == \
           [s.kind for s in after.chapters[0].timeline.scenes]
    assert before.chapters[0].seconds == after.chapters[0].seconds
    assert [f.path.name for f in before.chapters[0].frames] == \
           [f.path.name for f in after.chapters[0].frames]


# ---- the CLI ----------------------------------------------------------
def test_cli_video_reports_chapters_skips_and_the_silent_track(tmp_path, capsys):
    from demoforge.cli import main

    cs = _set(tmp_path)
    assert main(["--set", str(cs.root), "video"]) == 0
    out = capsys.readouterr().out
    assert "alpha" in out
    assert "presentation" in out
    assert "skipped (enabled, not yet approved): beta" in out
    assert "narration track is silence" in out


# ---- presentation cards -----------------------------------------------
def test_the_presentation_is_bookended_and_chaptered(tmp_path):
    cs = _set(tmp_path, approve=("alpha", "beta"))
    summary = _build(cs)

    ids = [c.path.stem for c in summary.cards]
    assert ids == ["intro", "contents", "chapter-alpha", "chapter-beta", "outro"]
    assert summary.presentation is not None
    # Cards add to the running time on top of the chapters.
    chapters = sum(c.seconds for c in summary.chapters)
    assert summary.seconds > chapters


def test_cards_can_be_switched_off_per_content_set(tmp_path):
    cs = _set(tmp_path, approve=("alpha", "beta"))
    toml = cs.root / "demoforge.toml"
    toml.write_text(
        '[set]\nid = "vid-set"\ntitle = "Video Set"\n\n'
        "[presentation]\nintro = false\noutro = false\n",
        encoding="utf-8",
    )
    summary = _build(load_content_set(cs.root))
    assert [c.path.stem for c in summary.cards] == ["chapter-alpha", "chapter-beta"]


def test_the_contents_card_says_where_each_demo_really_starts(tmp_path):
    """Each time on it is where that chapter's card begins in the joined video."""
    import re

    from demoforge.render.video import probe_seconds

    cs = _set(tmp_path, approve=("alpha", "beta"))
    # A handoff stretches beta's chapter card, so the times must follow the real lengths.
    (cs.demos_dir / "alpha" / "narration.md").write_text(
        "## setup\n\nA job.\n\n## transition\n\n"
        "Next up, a completely different kind of engineering problem for Claude "
        "to work through from first principles, with a long handoff to stretch it.\n",
        encoding="utf-8",
    )

    class Recording(_StubRenderer):
        def __init__(self) -> None:
            super().__init__()
            self.html: list[str] = []

        def render(self, html, out_path):
            self.html.append(html)
            super().render(html, out_path)

    renderer = Recording()
    summary = _build(load_content_set(cs.root), renderer=renderer)
    contents = next(h for h in renderer.html if "Skip to a demo" in h)
    shown = re.findall(r'class="toc__at">([0-9:]+)<', contents)

    cards = {c.path.stem: c.path for c in summary.cards}
    alpha, beta = summary.chapters
    order = [cards["intro"], cards["contents"], cards["chapter-alpha"], *alpha.parts]
    beta_at = sum(probe_seconds(p) for p in order)
    alpha_at = sum(probe_seconds(p) for p in order[:2])
    assert shown == [clock(alpha_at), clock(beta_at)]


def test_the_contents_card_can_be_switched_off(tmp_path):
    cs = _set(tmp_path, approve=("alpha", "beta"))
    (cs.root / "demoforge.toml").write_text(
        '[set]\nid = "vid-set"\ntitle = "Video Set"\n\n[presentation]\ncontents = false\n',
        encoding="utf-8",
    )
    summary = _build(load_content_set(cs.root))
    assert "contents" not in [c.path.stem for c in summary.cards]


def test_a_single_chapter_needs_no_contents_card(tmp_path):
    summary = _build(_set(tmp_path))
    assert [c.path.stem for c in summary.cards] == ["intro", "chapter-alpha", "outro"]


def test_a_chapter_card_is_narrated_by_the_previous_demo_handoff(tmp_path):
    """`transition` is written as a handoff, so it plays over the next demo's card."""
    cs = _set(tmp_path, approve=("alpha", "beta"))
    for name in ("alpha", "beta"):
        (cs.demos_dir / name / "narration.md").write_text(
            "## setup\n\nA job.\n\n## transition\n\n"
            + "Next up, a completely different kind of engineering problem for Claude "
            "to work through from first principles.\n",
            encoding="utf-8",
        )
    summary = _build(load_content_set(cs.root))

    by_id = {c.path.stem: c for c in summary.cards}
    # alpha's card has no predecessor to hand off from; beta's does, so it stretches.
    assert by_id["chapter-beta"].seconds > by_id["chapter-alpha"].seconds


def test_the_closing_card_counts_the_real_captured_events(tmp_path):
    cs = _set(tmp_path)
    summary = _build(cs)
    from demoforge.model import RunBundle

    recorded = len(RunBundle(cs.approved_dir_for("alpha")).read_events())
    assert summary.event_count == recorded
    assert summary.chapters[0].event_count == recorded


def test_an_event_shown_over_several_scenes_is_counted_once(tmp_path):
    # A long prompt is paged over several scenes, all built from the one event.
    long_prompt = "".join(
        f"Paragraph {i} of the request for {{name}}, long enough to fill a line.\n\n"
        for i in range(60)
    )
    cs = _set(tmp_path, prompt=long_prompt)
    summary = _build(cs)
    from demoforge.model import RunBundle

    scenes = summary.chapters[0].timeline.scenes
    assert sum(len(s.event_seqs) for s in scenes) > len({q for s in scenes for q in s.event_seqs})
    recorded = len(RunBundle(cs.approved_dir_for("alpha")).read_events())
    assert summary.chapters[0].event_count == recorded


def test_cards_are_cached_like_everything_else(tmp_path):
    cs = _set(tmp_path)
    _build(cs)
    second = _build(cs)
    assert all(c.cached for c in second.cards)
    assert second.presentation.cached is True


# ---- reading without sound -------------------------------------------
def test_the_introduction_is_spoken_on_its_own_card_not_over_the_replay(tmp_path):
    cs = _set(tmp_path)
    summary = _build(cs)

    chapter = summary.chapters[0]
    spoken = {s.narration for s in chapter.timeline.scenes}
    assert "setup" not in spoken
    assert "result" in spoken
    [problem] = chapter.intro
    assert problem.path.stem == "problem-alpha"
    assert problem.seconds >= chapter.audio["setup"].seconds


def test_a_demo_without_an_introduction_gets_no_problem_card(tmp_path):
    cs = _set(tmp_path, narration=False)
    summary = _build(cs)
    assert summary.chapters[0].intro == []
    assert summary.chapters[0].parts == [summary.chapters[0].video.path]


def test_every_narrated_scene_shows_its_words(tmp_path):
    cs = _set(tmp_path)
    (cs.demos_dir / "alpha" / "narration.md").write_text(
        "## result\n\nThe `checks` agree with [Kalman](/kˈɑlmən/).\n", encoding="utf-8"
    )
    summary = _build(load_content_set(cs.root))
    end = next(s for s in summary.chapters[0].timeline.scenes if s.narration == "result")
    # Shown as words: the pronunciation override and the Markdown are gone.
    assert end.caption == "The checks agree with Kalman."
    assert all(not s.caption for s in summary.chapters[0].timeline.scenes if not s.narration)
