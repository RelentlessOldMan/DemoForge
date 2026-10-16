"""Replay timeline: events.jsonl -> scenes, and the never-fabricate property.

The load-bearing assertions here are the structural ones: every scene names at least
one recorded event, no scene exists without an event behind it, and the whole thing is
a deterministic function of (events, config).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import CLAUDE_DEMO_KIT

from demoforge.errors import ConfigError
from demoforge.model import Event, RunBundle
from demoforge.render.config import ENGINE_CONFIG_DIR, Timing, load_settings
from demoforge.render.timeline import (
    Timeline,
    build_timeline,
    read_timeline,
    stretch_for_narration,
    with_narration,
    write_timeline,
)


def _settings():
    return load_settings()


def _events() -> list[Event]:
    """A small run exercising prose, a command with output, a write, and completion."""
    return [
        Event(seq=0, t=0.0, type="prompt", data={"text": "Make it fast."}),
        Event(seq=1, t=2.0, type="assistant_text", data={"text": "Looking at the file."}),
        Event(seq=2, t=3.0, type="file_read", data={"tool": "Read", "path": "C:\\w\\a.m"}),
        Event(seq=3, t=3.5, type="command", data={"tool": "Bash", "command": "octave bench.m"}),
        Event(seq=4, t=41.0, type="command_output", data={"output": "speedup 47.3x\nok\n"}),
        Event(seq=5, t=42.0, type="file_write", data={"tool": "Write", "path": "/w/fast.m"}),
        Event(seq=6, t=43.0, type="completion", data={"subtype": "success", "is_error": False}),
    ]


def _timeline(events=None, timing: Timing | None = None) -> Timeline:
    st = _settings()
    # `is None`, not truthiness: an empty event list is a case under test.
    return build_timeline(
        "demo",
        _events() if events is None else events,
        scenes=st.scenes,
        timing=timing or st.timing,
        clocked=True,  # the fixture's t values stand for measured seconds
    )


# ---- never fabricate --------------------------------------------------
def test_every_scene_is_backed_by_recorded_events():
    events = _events()
    tl = _timeline(events)
    recorded = {e.seq for e in events}
    assert tl.scenes, "a non-empty run must produce scenes"
    for s in tl.scenes:
        assert s.event_seqs, f"scene {s.index} ({s.kind}) has no event behind it"
        assert set(s.event_seqs) <= recorded


def test_no_events_are_invented_or_duplicated():
    events = _events()
    tl = _timeline(events)
    seen = [seq for s in tl.scenes for seq in s.event_seqs]
    assert len(seen) == len(set(seen)), "an event may back at most one scene"
    # Every recorded event is either shown or merged — none silently vanishes here,
    # because this fixture uses no ignored types.
    assert set(seen) == {e.seq for e in events}


def test_an_empty_run_yields_no_scenes():
    assert _timeline([]).scenes == ()


# ---- grouping ---------------------------------------------------------
def test_command_output_merges_onto_its_command():
    tl = _timeline()
    term = [s for s in tl.scenes if s.kind == "TerminalRun"]
    assert len(term) == 1
    assert term[0].event_seqs == (3, 4)
    assert term[0].data["command"] == "octave bench.m"
    assert term[0].data["output_lines"] == ["speedup 47.3x", "ok"]
    assert term[0].data["has_output"] is True


def test_output_returned_after_a_parallel_edit_still_lands_on_its_command():
    # A command and an edit issued together; the edit's record lands first.
    tl = _timeline([
        Event(seq=0, t=0.0, type="command", data={"command": "octave smoke.m"}),
        Event(seq=1, t=1.0, type="file_edit", data={"path": "NOTES.md", "edits": []}),
        Event(seq=2, t=1.1, type="command_output", data={"output": "finite 1"}),
    ])
    term = [s for s in tl.scenes if s.kind == "TerminalRun"]
    assert [s.event_seqs for s in term] == [(0, 2)]
    assert term[0].data["output_lines"] == ["finite 1"]


def test_a_second_output_never_lands_on_a_command_that_already_has_one():
    tl = _timeline([
        Event(seq=0, t=0.0, type="command", data={"command": "a"}),
        Event(seq=1, t=0.5, type="command_output", data={"output": "one"}),
        Event(seq=2, t=1.0, type="file_edit", data={"path": "N.md", "edits": []}),
        Event(seq=3, t=1.1, type="command_output", data={"output": "stray"}),
    ])
    term = [s for s in tl.scenes if s.kind == "TerminalRun"]
    assert [s.event_seqs for s in term] == [(0, 1)]


def test_orphan_command_output_is_not_shown():
    """Output with no command before it has nothing to merge onto, so it is dropped."""
    tl = _timeline([Event(seq=0, t=0.0, type="command_output", data={"output": "x"})])
    assert tl.scenes == ()


def test_ignored_event_types_produce_no_scene():
    st = _settings()
    scenes = type(st.scenes)(
        styles=st.scenes.styles,
        merge_into_previous=st.scenes.merge_into_previous,
        ignore=frozenset({"file_read"}),
        limits=st.scenes.limits,
    )
    tl = build_timeline("demo", _events(), scenes=scenes, timing=st.timing)
    assert not any(s.kind == "FileGlance" for s in tl.scenes)


def test_event_types_map_to_their_configured_kinds():
    kinds = [s.kind for s in _timeline().scenes]
    assert kinds == [
        "PromptCard", "NarratedText", "FileGlance", "TerminalRun",
        "DiffReveal", "ChapterEnd",
    ]


# ---- pacing -----------------------------------------------------------
def test_durations_stay_inside_configured_bounds():
    st = _settings()
    tl = _timeline()
    for s in tl.scenes:
        assert s.duration >= st.timing.scene_min_seconds, s.kind
        assert s.duration <= st.timing.read_scene_max_seconds, s.kind


def test_glance_scenes_use_the_shorter_ceiling():
    """A filename card must not sit on screen as long as a page of prose may."""
    st = _settings()
    long_path = "/w/" + "x" * 4000 + ".m"
    tl = _timeline([Event(seq=0, t=0.0, type="file_read", data={"path": long_path})])
    assert tl.scenes[0].duration == st.timing.scene_max_seconds


def test_longer_text_is_on_screen_longer():
    short = _timeline([Event(seq=0, t=0.0, type="assistant_text", data={"text": "Hi."})])
    long = _timeline(
        [Event(seq=0, t=0.0, type="assistant_text", data={"text": "word " * 20})]
    )
    assert long.scenes[0].duration > short.scenes[0].duration


def test_replay_time_is_not_wall_clock():
    tl = _timeline()
    # The fixture's benchmark really ran for 37.5 seconds; the replay shows it faster.
    term = next(s for s in tl.scenes if s.kind == "TerminalRun")
    assert term.real_seconds == pytest.approx(37.5)
    assert term.duration < term.real_seconds


def test_only_measured_command_time_counts_as_real_time():
    tl = _timeline()
    # Time between events is the model thinking, not anything the card shows, so a
    # card claims real time only for a command it watched run.
    for s in tl.scenes:
        if s.kind != "TerminalRun":
            assert s.real_seconds == 0.0


def test_a_long_real_gap_is_flagged_compressed():
    tl = _timeline()
    compressed = tl.compressed_scenes
    assert [s.kind for s in compressed] == ["TerminalRun"]
    # Only the measured benchmark counts, not the time between events.
    assert tl.real_seconds == pytest.approx(37.5)


def test_compression_flag_can_be_switched_off():
    st = _settings()
    timing = Timing(**{**st.timing.__dict__, "compress_idle": False})
    assert _timeline(timing=timing).compressed_scenes == ()


def test_frame_counts_follow_fps():
    tl = _timeline()
    assert tl.total_frames == sum(max(1, round(s.duration * tl.fps)) for s in tl.scenes)
    assert all(s.frame_count(tl.fps) >= 1 for s in tl.scenes)


# ---- truncation -------------------------------------------------------
def test_terminal_output_is_capped_and_says_how_much_it_dropped():
    st = _settings()
    n = st.scenes.limits.terminal_max_lines + 5
    raw = "\n".join(f"line {i}" for i in range(n))
    tl = _timeline([
        Event(seq=0, t=0.0, type="command", data={"command": "ls"}),
        Event(seq=1, t=1.0, type="command_output", data={"output": raw}),
    ])
    data = tl.scenes[0].data
    # The one-line command takes one of the card's lines.
    assert len(data["output_lines"]) == st.scenes.limits.terminal_max_lines - 1
    assert data["dropped_lines"] == 6


def test_overlong_text_is_paged_not_clipped():
    st = _settings()
    lim = st.scenes.limits
    words = [f"w{i}" for i in range(lim.text_page_lines * lim.text_line_chars // 2)]
    tl = _timeline([Event(seq=0, t=0.0, type="prompt", data={"text": " ".join(words)})])
    pages = tl.scenes
    assert len(pages) > 1
    assert all(p.event_seqs == (0,) for p in pages)
    assert [p.data["page"] for p in pages] == list(range(1, len(pages) + 1))
    # Every word is shown, once, in order.
    assert " ".join(p.data["text"] for p in pages).split() == words


# ---- determinism / serialization --------------------------------------
def test_building_twice_gives_identical_json():
    a, b = _timeline(), _timeline()
    assert json.dumps(a.to_json(), sort_keys=True) == json.dumps(b.to_json(), sort_keys=True)


def test_timeline_round_trips_through_disk(tmp_path):
    tl = _timeline()
    path = write_timeline(tl, tmp_path / "video" / "timeline.json")
    assert path.read_bytes().endswith(b"\n")
    assert read_timeline(path) == tl


# ---- narration hooks --------------------------------------------------
def test_narration_is_attached_by_scene_index():
    tl = with_narration(_timeline(), {0: "setup", 5: "result"})
    assert tl.scenes[0].narration == "setup"
    assert tl.scenes[5].narration == "result"
    assert tl.scenes[1].narration is None


def test_narration_only_ever_extends_a_scene():
    tl = with_narration(_timeline(), {2: "setup"})
    before = tl.scenes[2].duration
    stretched = stretch_for_narration(tl, {"setup": before + 9.0})
    assert stretched.scenes[2].duration == pytest.approx(before + 9.0)
    # A shorter audio clip must not shorten the scene.
    assert stretch_for_narration(tl, {"setup": 0.1}).scenes[2].duration == before
    # Unnarrated scenes are untouched.
    assert stretched.scenes[1] == tl.scenes[1]


def test_narration_tail_leaves_a_pause_after_the_speech():
    tl = with_narration(_timeline(), {2: "setup"})
    stretched = stretch_for_narration(tl, {"setup": 30.0}, tail=0.75)
    assert stretched.scenes[2].duration == pytest.approx(30.75)
    # The tail pads speech; it never lengthens a scene that has none.
    assert stretched.scenes[1] == tl.scenes[1]


# ---- explainers ---------------------------------------------------------
def test_every_scene_carries_its_kinds_explainer_filled_from_recorded_fields():
    tl = _timeline()
    by_kind = {s.kind: s for s in tl.scenes}
    assert "Bash terminal" in by_kind["TerminalRun"].explain
    assert "fast.m" in by_kind["DiffReveal"].explain
    assert all(s.explain for s in tl.scenes), "every engine scene kind is explained"
    assert "{" not in "".join(s.explain for s in tl.scenes), "no unfilled slot"


def test_an_explainer_slot_the_data_lacks_renders_empty():
    tl = _timeline([Event(seq=0, t=0.0, type="command", data={"command": "make"})])
    assert "a terminal" in tl.scenes[0].explain


def test_the_first_card_of_a_kind_gets_time_to_read_its_explainer():
    reads = [
        Event(seq=i, t=float(i), type="file_read", data={"path": f"/w/{c}.m"})
        for i, c in enumerate("ab")
    ]
    first, second = _timeline(reads).scenes
    assert first.explain == second.explain
    assert first.duration > second.duration


def test_terminal_cards_use_their_own_ceiling():
    st = _settings()
    noisy = [
        Event(seq=0, t=0.0, type="command", data={"command": "x" * 2000}),
        Event(seq=1, t=1.0, type="command_output", data={"output": "line\n" * 500}),
    ]
    assert _timeline(noisy).scenes[0].duration == st.timing.terminal_scene_max_seconds


def test_explainer_survives_a_round_trip(tmp_path):
    tl = _timeline()
    assert read_timeline(write_timeline(tl, tmp_path / "t.json")) == tl


# ---- config -----------------------------------------------------------
def test_engine_config_is_committed_and_loads():
    for name in ("scenes.yaml", "timing.yaml", "video.yaml"):
        assert (ENGINE_CONFIG_DIR / name).is_file(), name
    st = load_settings()
    assert st.scenes.styles["command"].kind == "TerminalRun"
    assert st.scenes.merge_into_previous == {"command_output": "command"}
    assert st.video.video_codec == "libx264"


def test_content_set_config_overrides_the_engine(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "timing.yaml").write_text("scene_min_seconds: 3.0\n", encoding="utf-8")
    (cfg / "scenes.yaml").write_text(
        "limits:\n  terminal_max_lines: 4\n", encoding="utf-8"
    )
    st = load_settings(tmp_path)
    assert st.timing.scene_min_seconds == 3.0
    # One level deep: the overridden key wins, its siblings survive.
    assert st.scenes.limits.terminal_max_lines == 4
    assert st.scenes.limits.text_page_lines == 11
    # Untouched files still come from the engine.
    assert st.scenes.styles["command"].kind == "TerminalRun"


def test_missing_config_falls_back_to_defaults(tmp_path):
    st = load_settings(engine_dir=tmp_path / "nope")
    assert st.timing == Timing()
    assert st.scenes.styles == {}


def test_bad_config_is_rejected_clearly(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "timing.yaml").write_text("scene_max_seconds: 0.1\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="scene_max_seconds"):
        load_settings(tmp_path)

    (cfg / "timing.yaml").write_text("fps: 0\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="fps"):
        load_settings(tmp_path)

    (cfg / "timing.yaml").unlink()
    (cfg / "scenes.yaml").write_text("scenes:\n  prompt:\n    kind: X\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="template"):
        load_settings(tmp_path)


# ---- against the real committed bundle --------------------------------
def test_timeline_from_the_real_approved_bundle():
    bundle = RunBundle(CLAUDE_DEMO_KIT / "approved" / "matlab-optimization")
    if not bundle.exists():
        pytest.skip("no approved bundle committed")
    events = bundle.read_events()
    st = load_settings(CLAUDE_DEMO_KIT)
    tl = build_timeline("matlab-optimization", events, scenes=st.scenes, timing=st.timing)

    # Each captured command keeps its output on one terminal card.
    terminals = [s for s in tl.scenes if s.kind == "TerminalRun"]
    assert len(terminals) == sum(1 for e in events if e.type == "command")
    assert all(len(s.event_seqs) == 2 for s in terminals)
    # The benchmark numbers the demo is about survive into the replay verbatim.
    assert any(
        "speedup" in line.lower() for s in terminals for line in s.data["output_lines"]
    )
    # The replay is derived, traceable, and nothing is conjured.
    assert {q for s in tl.scenes for q in s.event_seqs} <= {e.seq for e in events}
    assert tl.scenes[0].kind == "PromptCard"
    assert tl.scenes[-1].kind == "ChapterEnd"
    assert tl.total_seconds > 0
