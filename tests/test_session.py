"""The animated session replay (demoforge/render/session.py, video-pipeline.md §5)."""

from __future__ import annotations

import dataclasses
import struct
import wave
from pathlib import Path

import pytest

from demoforge.model.bundle import Event
from demoforge.render.config import VideoEncode, load_settings
from demoforge.render.frames import Frame
from demoforge.render.narration import AudioClip
from demoforge.render.session import audit_beats, session_beats, streamed_floors, visible_text
from demoforge.render.timeline import (
    build_timeline,
    narration_spans,
    stretch_for_narration,
    with_narration,
)
from demoforge.render.video import _build_audio_track, resolve_ffmpeg

from conftest import requires_ffmpeg

PROMPT = "Implement the filter in `kalman_update.m` and **test** it, please."
REPLY = "I've written **both files**, and the test passes on `octave` with error 1.78e-15."

EVENTS = [
    Event(seq=0, t=0.0, type="prompt", data={"text": PROMPT}),
    Event(seq=1, t=1.0, type="command", data={"command": "octave --eval test_kalman_update"}),
    Event(seq=2, t=9.0, type="command_output",
          data={"output": "test_kalman_update: PASS\nexit=0\n"}),
    Event(seq=3, t=10.0, type="file_write",
          data={"path": "kalman_update.m", "content": "function X = kalman_update(Z, model)\n  X = Z;\nend\n"}),
    Event(seq=4, t=11.0, type="assistant_text", data={"text": REPLY}),
    Event(seq=5, t=12.0, type="completion", data={"subtype": "success"}),
]


def _timeline():
    st = load_settings()
    return build_timeline("demo", EVENTS, scenes=st.scenes, timing=st.timing, clocked=True), st


def test_every_scene_lasts_exactly_as_long_as_before():
    """The animation only changes what is on screen inside a scene, never its length."""
    tl, st = _timeline()
    beats = session_beats(tl, st.timing)
    assert beats, "conversation scenes become beats"
    for scene in tl.scenes:
        if scene.index in beats:
            got = sum(b.duration for b in beats[scene.index])
            assert got == pytest.approx(scene.duration, abs=1e-9)
            assert all(b.duration > 0 for b in beats[scene.index])
            assert [b.step for b in beats[scene.index]] == list(range(len(beats[scene.index])))


def test_the_results_panel_stays_a_still_card():
    tl, st = _timeline()
    beats = session_beats(tl, st.timing)
    for scene in tl.scenes:
        if scene.kind == "ChapterEnd":
            assert scene.index not in beats


def test_the_prompt_is_typed_then_submitted():
    tl, st = _timeline()
    beats = session_beats(tl, st.timing)
    prompt = next(s for s in tl.scenes if s.kind == "PromptCard")
    seq = beats[prompt.index]
    typed = [b.session["input"]["text"] for b in seq[:-1]]
    assert typed[0] and len(typed[0]) < len(PROMPT)
    assert all(PROMPT.startswith(t) for t in typed)
    assert typed == sorted(typed, key=len)
    final = seq[-1].session
    assert final["input"]["text"] == ""
    assert [e["text"] for e in final["entries"] if e["role"] == "user"] == [PROMPT]


def test_a_reply_streams_in_whole_words_and_stays_valid_markdown():
    tl, st = _timeline()
    beats = session_beats(tl, st.timing)
    scene = next(s for s in tl.scenes if s.kind == "NarratedText")
    shown = [b.session["entries"][-1] for b in beats[scene.index]]
    assert shown[-1]["text"] == REPLY
    for e in shown[:-1]:
        assert REPLY.startswith(e["text"])
        cut = len(e["text"])
        assert cut == len(REPLY) or REPLY[cut] in " \n", "never cut mid-word"
        assert "**" not in e["html"] and e["html"].count("<code>") == e["html"].count("</code>")


def test_a_command_shows_a_counter_to_its_recorded_time_before_its_output():
    tl, st = _timeline()
    beats = session_beats(tl, st.timing)
    scene = next(s for s in tl.scenes if s.kind == "TerminalRun")
    assert scene.real_seconds >= 1.0
    entries = [b.session["entries"][-1] for b in beats[scene.index]]
    running = [e["running"] for e in entries if e["running"]]
    assert running, "a command that took time shows it running"
    assert running[-1].endswith(f"{scene.real_seconds:.1f}s")
    assert all(not e["lines"] for e in entries if e["running"])
    assert [ln["text"] for ln in entries[-1]["lines"]] == ["test_kalman_update: PASS", "exit=0"]


def test_the_window_keeps_the_conversation_so_far():
    tl, st = _timeline()
    beats = session_beats(tl, st.timing)
    last = max(i for i in beats)
    roles = [e["role"] for e in beats[last][-1].session["entries"]]
    assert roles[0] == "user" and roles[-1] == "assistant" and "tool" in roles


def test_every_string_on_screen_is_recorded_text():
    tl, st = _timeline()
    beats = session_beats(tl, st.timing)
    assert audit_beats(tl, beats, EVENTS) == []
    assert any(visible_text(b) for bs in beats.values() for b in bs)


def test_the_audit_catches_invented_text():
    """A check that always passes proves nothing: plant a line and it must fail."""
    tl, st = _timeline()
    beats = session_beats(tl, st.timing)
    scene = next(s for s in tl.scenes if s.kind == "TerminalRun")
    beat = beats[scene.index][-1]
    forged = [dict(e) for e in beat.session["entries"]]
    forged[-1]["lines"] = forged[-1]["lines"] + [{"sign": "", "text": "speedup 900x"}]
    beats[scene.index][-1] = dataclasses.replace(
        beat, session={**beat.session, "entries": forged}
    )
    problems = audit_beats(tl, beats, EVENTS)
    assert len(problems) == 1 and "speedup 900x" in problems[0]


def test_the_audit_does_not_let_a_scene_show_what_happens_later():
    tl, st = _timeline()
    beats = session_beats(tl, st.timing)
    prompt = next(s for s in tl.scenes if s.kind == "PromptCard")
    beat = beats[prompt.index][-1]
    early = {**beat.session, "entries": beat.session["entries"] + [
        {"role": "assistant", "text": REPLY, "html": ""}]}
    beats[prompt.index][-1] = dataclasses.replace(beat, session=early)
    assert audit_beats(tl, beats, EVENTS)


def test_output_recorded_after_a_parallel_edit_passes_the_audit_on_later_scenes():
    # The command's output (seq 2) is shown with its command, so the edit's scene
    # (seq 1) may keep it in the history; nothing is shown before it happened.
    events = [
        Event(seq=0, t=0.0, type="command", data={"command": "octave smoke.m"}),
        Event(seq=1, t=1.0, type="file_edit",
              data={"path": "NOTES.md", "edits": [{"old": "a", "new": "b"}]}),
        Event(seq=2, t=1.1, type="command_output", data={"output": "smoke finite 1\n"}),
        Event(seq=3, t=2.0, type="completion", data={"subtype": "success"}),
    ]
    st = load_settings()
    tl = build_timeline("demo", events, scenes=st.scenes, timing=st.timing, clocked=True)
    assert [s.event_seqs for s in tl.scenes if s.kind == "TerminalRun"] == [(0, 2)]
    assert audit_beats(tl, session_beats(tl, st.timing), events) == []


def test_replay_style_is_session_or_slides():
    timing = load_settings().timing
    assert timing.replay_style == "session"
    assert dataclasses.replace(timing, replay_style="slides").replay_style == "slides"
    with pytest.raises(Exception, match="replay_style"):
        dataclasses.replace(timing, replay_style="cartoon")


# ---- audio over an animated scene ---------------------------------------
VIDEO = VideoEncode(width=320, height=180, fps=30, preset="ultrafast")


def _ramp_wav(path: Path, seconds: float, rate: int, channels: int) -> Path:
    n = int(seconds * rate)
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(channels)
        fh.setsampwidth(2)
        fh.setframerate(rate)
        fh.writeframes(b"".join(struct.pack("<h", 1 + i % 3000) * channels for i in range(n)))
    return path


@requires_ffmpeg
def test_narration_plays_once_across_a_scenes_beats(tmp_path):
    """Several frames of one scene must not restart its narration on every frame."""
    tl, st = _timeline()
    tl = with_narration(tl, {0: "intro"})
    scene = tl.scenes[0]
    beats = session_beats(tl, st.timing)[0]
    assert len(beats) > 2
    frames = [
        Frame(scene_index=0, kind=scene.kind, path=tmp_path / f"{b.step}.png",
              duration=b.duration, cached=True, step=b.step)
        for b in beats
    ]
    clip = _ramp_wav(tmp_path / "n.wav", scene.duration * 0.8, VIDEO.sample_rate, VIDEO.channels)
    track = _build_audio_track(
        frames, {0: scene}, {"intro": AudioClip("intro", clip, scene.duration * 0.8, False)},
        VIDEO, resolve_ffmpeg(), tmp_path / "a.wav",
    )
    with wave.open(str(track), "rb") as fh:
        pcm = fh.readframes(fh.getnframes())
        assert fh.getnframes() / fh.getframerate() == pytest.approx(scene.duration, abs=0.002)
    stride = 2 * VIDEO.channels
    samples = [struct.unpack_from("<h", pcm, i)[0] for i in range(0, len(pcm), stride)]
    voiced = [s for s in samples if s]
    # One unbroken ramp: the clip's opening sample appears once, not once per beat.
    assert voiced.count(1) == pytest.approx(len(voiced) / 3000, abs=1)
    assert voiced[: 3000] == list(range(1, 3001))


# ---- a long message: paced as it streams, narrated once across its pages ----
LONG = "\n\n".join(
    f"Paragraph {n}: " + " ".join(f"word{n}x{k}" for k in range(60)) for n in range(12)
)
LONG_EVENTS = [
    Event(seq=0, t=0.0, type="prompt", data={"text": "Report back."}),
    Event(seq=1, t=1.0, type="assistant_text", data={"text": LONG}),
    Event(seq=2, t=2.0, type="completion", data={"subtype": "success"}),
]


def _long(style: str = "session"):
    st = load_settings()
    timing = dataclasses.replace(st.timing, replay_style=style)
    tl = build_timeline("demo", LONG_EVENTS, scenes=st.scenes, timing=timing)
    pages = [s for s in tl.scenes if s.kind == "NarratedText"]
    assert len(pages) >= 3, "the fixture must page"
    return tl, pages, timing


def test_later_pages_are_paced_as_they_stream_not_reread_as_cards():
    _, session, timing = _long("session")
    _, slides, _ = _long("slides")
    assert session[0].duration == slides[0].duration
    for s, c in zip(session[1:], slides[1:]):
        want = timing.clamp_read(
            s.data["chars"] / timing.stream_chars_per_second + timing.continued_page_hold_seconds
        )
        assert s.duration == pytest.approx(want, abs=1e-3)
        assert s.duration < c.duration


def _rows(n: int, first: int = 0) -> str:
    return "\n".join(f"| {k:02d} | {k}e-13 |" for k in range(first, first + n))


def _fenced(n: int, first: int = 0) -> str:
    return "```\n" + "\n".join(f"case {k:02d}  {k}e-13" for k in range(first, first + n)) + "\n```"


@pytest.mark.parametrize(
    "body",
    [
        "| Case | Error |\n|---|---|\n" + _rows(80),
        _fenced(80),
        # Separate blocks meeting at a page break stay separate.
        _fenced(4) + "\n\n" + _fenced(4, 4) + "\n\n" + _fenced(4, 8),
        "| Case | Error |\n|---|---|\n" + _rows(4) + "\n\n| Case | Error |\n|---|---|\n" + _rows(4, 4),
    ],
    ids=["table", "code", "adjacent code", "adjacent tables"],
)
def test_a_block_split_across_pages_reads_on_as_the_recorded_block(body):
    text = "Per case:\n\n" + body
    events = [
        Event(seq=0, t=0.0, type="prompt", data={"text": "Report back."}),
        Event(seq=1, t=1.0, type="assistant_text", data={"text": text}),
        Event(seq=2, t=2.0, type="completion", data={"subtype": "success"}),
    ]
    st = load_settings()
    tl = build_timeline("demo", events, scenes=st.scenes, timing=st.timing)
    assert sum(s.kind == "NarratedText" for s in tl.scenes) >= 2, "the blocks must page"
    beats = session_beats(tl, st.timing)
    assert audit_beats(tl, beats, events) == []
    shown = [t for t in visible_text(beats[max(beats)][-1]) if t.startswith("Per case")]
    assert shown == [text]


def test_narration_on_a_paged_message_spans_all_its_pages():
    tl, pages, _ = _long()
    tl = with_narration(tl, {pages[0].index: "during:1"}, {"during:1": "Claude reports."})
    leaders = narration_spans(tl.scenes)
    assert {leaders[p.index] for p in pages} == {pages[0].index}
    assert all(tl.scenes[p.index].caption == "Claude reports." for p in pages)
    assert all(tl.scenes[p.index].narration is None for p in pages[1:])


def test_a_long_narration_lengthens_only_the_last_page_and_only_by_the_shortfall():
    tl, pages, _ = _long()
    tl = with_narration(tl, {pages[0].index: "during:1"})
    span = sum(p.duration for p in pages)
    fits = stretch_for_narration(tl, {"during:1": span - 5}, tail=0.75)
    assert [s.duration for s in fits.scenes] == [s.duration for s in tl.scenes]
    longer = stretch_for_narration(tl, {"during:1": span + 4}, tail=0.75)
    changed = [s.index for s, o in zip(longer.scenes, tl.scenes) if s.duration != o.duration]
    assert changed == [pages[-1].index]
    assert sum(longer.scenes[p.index].duration for p in pages) == pytest.approx(span + 4.75)


@requires_ffmpeg
def test_narration_plays_once_across_a_paged_message(tmp_path):
    tl, pages, _ = _long()
    tl = with_narration(tl, {pages[0].index: "during:1"})
    span = sum(p.duration for p in pages)
    frames = [
        Frame(scene_index=p.index, kind=p.kind, path=tmp_path / f"{p.index}.png",
              duration=p.duration, cached=True)
        for p in pages
    ]
    clip = _ramp_wav(tmp_path / "n.wav", span * 0.9, VIDEO.sample_rate, VIDEO.channels)
    track = _build_audio_track(
        frames, {s.index: s for s in tl.scenes},
        {"during:1": AudioClip("during:1", clip, span * 0.9, False)},
        VIDEO, resolve_ffmpeg(), tmp_path / "a.wav",
    )
    with wave.open(str(track), "rb") as fh:
        pcm = fh.readframes(fh.getnframes())
    stride = 2 * VIDEO.channels
    samples = [struct.unpack_from("<h", pcm, i)[0] for i in range(0, len(pcm), stride)]
    voiced = [s for s in samples if s]
    # The clip runs on through the later pages instead of stopping at the first.
    assert len(voiced) / VIDEO.sample_rate == pytest.approx(span * 0.9, abs=0.05)
    assert voiced[:3000] == list(range(1, 3001))
    assert voiced.count(1) == pytest.approx(len(voiced) / 3000, abs=1)


def test_a_narrated_message_lasts_as_long_as_its_narration_but_can_still_stream():
    tl, pages, timing = _long()
    floors = streamed_floors(tl, timing)
    least = sum(floors[p.index] for p in pages)
    reading = sum(p.duration for p in pages)
    assert least < reading

    narrated = with_narration(tl, {pages[0].index: "during:1"})
    # Short narration: the message drops to streaming pace, never below it.
    quick = stretch_for_narration(narrated, {"during:1": 1.0}, tail=0.75, floors=floors)
    assert sum(quick.scenes[p.index].duration for p in pages) == pytest.approx(least, abs=1e-3)
    # Longer narration: the message lasts exactly as long as the speech.
    want = least + 6.0
    fitted = stretch_for_narration(narrated, {"during:1": want - 0.75}, tail=0.75, floors=floors)
    assert sum(fitted.scenes[p.index].duration for p in pages) == pytest.approx(want, abs=1e-3)
    # No narration: the reading pace stands.
    silent = stretch_for_narration(tl, {}, tail=0.75, floors=floors)
    assert [s.duration for s in silent.scenes] == [s.duration for s in tl.scenes]


def test_a_windows_path_outside_the_work_dir_passes_the_audit_as_shown():
    # The card shows such a path whole, with forward slashes; it is still the
    # recorded path, so the audit must accept it.
    events = [*EVENTS[:3],
              Event(seq=3, t=10.0, type="file_write",
                    data={"path": r"C:\sandbox\tmp\build.py", "content": "print('x')\n"}),
              *EVENTS[4:]]
    st = load_settings()
    tl = build_timeline("demo", events, scenes=st.scenes, timing=st.timing, clocked=True)
    beats = session_beats(tl, st.timing)
    assert any("C:/sandbox/tmp/build.py" in t for bs in beats.values() for b in bs
               for t in visible_text(b))
    assert audit_beats(tl, beats, events) == []
