"""Video assembly: the concat script, the sample-exact audio track, and the cache.

The ffmpeg-free tests pin the construction; the ffmpeg ones pin that a real file comes
out at exactly the length the timeline declares.
"""

from __future__ import annotations

import wave
from pathlib import Path

import pytest

from conftest import FFMPEG, requires_chromium, requires_ffmpeg, requires_jinja

from demoforge.errors import DemoForgeError
from demoforge.model import Event
from demoforge.render.config import VideoEncode, load_settings
from demoforge.render.frames import Frame
from demoforge.render.narration import AudioClip, SilentTTS, parse_narration, synthesize_narration
from demoforge.render.timeline import build_timeline, with_narration
from demoforge.render.video import (
    _build_audio_track,
    _write_frame_concat,
    assemble_demo_video,
    concat_videos,
    ffmpeg_available,
    probe_seconds,
    resolve_ffmpeg,
)

VIDEO = VideoEncode(width=320, height=180, fps=30, preset="ultrafast")


def _timeline():
    st = load_settings()
    events = [
        Event(seq=0, t=0.0, type="prompt", data={"text": "Make it fast."}),
        Event(seq=1, t=2.0, type="assistant_text", data={"text": "On it."}),
        Event(seq=2, t=3.0, type="command", data={"command": "octave b.m"}),
        Event(seq=3, t=4.0, type="command_output", data={"output": "speedup 47.3x\n"}),
        Event(seq=4, t=5.0, type="completion", data={"subtype": "success"}),
    ]
    return build_timeline("demo", events, scenes=st.scenes, timing=st.timing)


def _png(path: Path, size: tuple[int, int] = (320, 180)) -> Path:
    """A real 1x1-colour PNG, written without Pillow."""
    import struct
    import zlib

    width, height = size
    raw = b"".join(b"\0" + bytes([20, 26, 46]) * width for _ in range(height))

    def chunk(tag: bytes, body: bytes) -> bytes:
        return (
            struct.pack(">I", len(body))
            + tag
            + body
            + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )
    return path


def _frames(tmp_path: Path, timeline) -> list[Frame]:
    return [
        Frame(
            scene_index=s.index,
            kind=s.kind,
            path=_png(tmp_path / "frames" / f"{s.index:04d}.png"),
            duration=s.duration,
            cached=False,
        )
        for s in timeline.scenes
    ]


# ---- tool discovery ---------------------------------------------------
def test_missing_ffmpeg_is_reported_not_guessed(tmp_path):
    with pytest.raises(DemoForgeError, match="ffmpeg not found"):
        resolve_ffmpeg(tmp_path / "nope.exe")


@requires_ffmpeg
def test_ffmpeg_is_discovered_on_path():
    assert ffmpeg_available() is True
    assert resolve_ffmpeg().name.lower().startswith("ffmpeg")


# ---- the concat script ------------------------------------------------
def test_concat_script_holds_each_frame_for_its_scene(tmp_path):
    tl = _timeline()
    frames = _frames(tmp_path, tl)
    lines = _write_frame_concat(frames, tmp_path / "f.txt").read_text().splitlines()

    durations = [float(l.split()[1]) for l in lines if l.startswith("duration")]
    assert durations == [pytest.approx(s.duration) for s in tl.scenes]
    # The demuxer drops the final entry's duration, so the last frame is repeated.
    assert lines[-1] == lines[-3]
    assert lines[-1].startswith("file ")


def test_assembling_nothing_is_an_error(tmp_path):
    with pytest.raises(DemoForgeError, match="no frames"):
        assemble_demo_video(_timeline(), [], out_path=tmp_path / "x.mp4", video=VIDEO)


def test_concatenating_a_missing_chapter_is_an_error(tmp_path):
    with pytest.raises(DemoForgeError, match="missing chapter"):
        concat_videos([tmp_path / "gone.mp4"], tmp_path / "all.mp4", video=VIDEO)
    with pytest.raises(DemoForgeError, match="no chapters"):
        concat_videos([], tmp_path / "all.mp4", video=VIDEO)


# ---- the audio track --------------------------------------------------
@requires_ffmpeg
def test_audio_track_matches_the_scene_boundaries_exactly(tmp_path):
    tl = _timeline()
    narration = parse_narration("## setup\n\nWe hand Claude a slow routine.\n")
    clips = synthesize_narration(narration, SilentTTS(), "amy", tmp_path / "audio")
    tl = with_narration(tl, {0: "setup"})
    frames = _frames(tmp_path, tl)

    track = _build_audio_track(
        frames, {s.index: s for s in tl.scenes}, clips, VIDEO, resolve_ffmpeg(), tmp_path / "a.wav"
    )
    with wave.open(str(track), "rb") as fh:
        assert fh.getframerate() == VIDEO.sample_rate
        assert fh.getnchannels() == VIDEO.channels
        seconds = fh.getnframes() / fh.getframerate()
    assert seconds == pytest.approx(tl.total_seconds, abs=0.001)


@requires_ffmpeg
def test_narration_longer_than_its_scene_is_trimmed_not_allowed_to_drift(tmp_path):
    """Pacing normally prevents this; if it happens, boundaries must still hold."""
    tl = with_narration(_timeline(), {0: "setup"})
    frames = _frames(tmp_path, tl)
    long_clip = tmp_path / "long.wav"
    long_clip.write_bytes(SilentTTS().synthesize("x" * 5000, "amy"))
    clips = {"setup": AudioClip("setup", long_clip, 357.0, False)}

    track = _build_audio_track(
        frames, {s.index: s for s in tl.scenes}, clips, VIDEO, resolve_ffmpeg(), tmp_path / "a.wav"
    )
    with wave.open(str(track), "rb") as fh:
        assert fh.getnframes() / fh.getframerate() == pytest.approx(tl.total_seconds, abs=0.001)


# ---- end to end -------------------------------------------------------
@requires_ffmpeg
def test_video_is_exactly_as_long_as_the_timeline_says(tmp_path):
    tl = _timeline()
    frames = _frames(tmp_path, tl)
    out = tmp_path / "video" / "demo.mp4"

    result = assemble_demo_video(tl, frames, out_path=out, video=VIDEO)
    assert result.cached is False
    assert out.is_file() and out.stat().st_size > 0
    assert result.seconds == pytest.approx(tl.total_seconds)
    assert probe_seconds(out) == pytest.approx(tl.total_seconds, abs=0.05)


@requires_ffmpeg
def test_assembly_is_cached_and_invalidated_by_a_changed_frame(tmp_path):
    tl = _timeline()
    frames = _frames(tmp_path, tl)
    out = tmp_path / "demo.mp4"

    assemble_demo_video(tl, frames, out_path=out, video=VIDEO)
    stamp = out.stat().st_mtime_ns
    assert assemble_demo_video(tl, frames, out_path=out, video=VIDEO).cached is True
    assert out.stat().st_mtime_ns == stamp

    # Frame names are content addresses, so a re-rendered frame changes the key.
    swapped = list(frames)
    swapped[1] = Frame(
        scene_index=1, kind=frames[1].kind,
        path=_png(tmp_path / "frames" / "0001-different.png"),
        duration=frames[1].duration, cached=False,
    )
    assert assemble_demo_video(tl, swapped, out_path=out, video=VIDEO).cached is False


@requires_ffmpeg
def test_changing_encode_settings_invalidates_the_video(tmp_path):
    tl = _timeline()
    frames = _frames(tmp_path, tl)
    out = tmp_path / "demo.mp4"
    assemble_demo_video(tl, frames, out_path=out, video=VIDEO)
    changed = VideoEncode(width=320, height=180, fps=30, preset="ultrafast", crf=30)
    assert assemble_demo_video(tl, frames, out_path=out, video=changed).cached is False


@requires_ffmpeg
def test_chapters_concatenate_into_one_presentation(tmp_path):
    tl = _timeline()
    frames = _frames(tmp_path, tl)
    parts = []
    for name in ("one", "two"):
        path = tmp_path / f"{name}.mp4"
        assemble_demo_video(tl, frames, out_path=path, video=VIDEO)
        parts.append(path)

    out = tmp_path / "presentation.mp4"
    result = concat_videos(parts, out, video=VIDEO)
    assert result.cached is False and out.is_file()
    assert probe_seconds(out) == pytest.approx(2 * tl.total_seconds, abs=0.3)
    assert concat_videos(parts, out, video=VIDEO).cached is True


@requires_ffmpeg
def test_no_work_dir_is_left_behind(tmp_path):
    tl = _timeline()
    assemble_demo_video(tl, _frames(tmp_path, tl), out_path=tmp_path / "demo.mp4", video=VIDEO)
    assert not any(p.name.startswith(".demo") and p.is_dir() for p in tmp_path.iterdir())


# ---- the real demo, all the way through -------------------------------
@requires_ffmpeg
@requires_chromium
@requires_jinja
def test_the_committed_bundle_renders_to_a_watchable_chapter(tmp_path):
    from conftest import CLAUDE_DEMO_KIT

    from demoforge.discovery import load_content_set
    from demoforge.model import RunBundle
    from demoforge.render.frames import ChromiumRenderer, context_for, render_frames
    from demoforge.render.narration import anchor_narration, clip_seconds, load_narration
    from demoforge.render.timeline import stretch_for_narration

    cs = load_content_set(CLAUDE_DEMO_KIT)
    demo = next(d for d in cs.demos() if d.id == "matlab-optimization")
    bundle = RunBundle(cs.approved_dir_for(demo.id))
    if not bundle.exists():
        pytest.skip("no approved bundle committed")

    st = load_settings(cs.root)
    video = VideoEncode(**{**st.video.__dict__, "width": 640, "height": 360, "preset": "ultrafast"})
    tl = build_timeline(demo.id, bundle.read_events(), scenes=st.scenes, timing=st.timing)
    narration = load_narration(demo)
    clips = synthesize_narration(narration, SilentTTS(timing=st.timing), "amy", tmp_path / "audio")
    tl = stretch_for_narration(
        with_narration(tl, anchor_narration(tl, narration)), clip_seconds(clips)
    )

    ctx = context_for(cs.config.title, demo.title, tl, bundle.read_results())
    with ChromiumRenderer(video) as renderer:
        frames = render_frames(
            tl, ctx, out_dir=tmp_path / "frames", video=video, renderer=renderer
        )

    out = tmp_path / f"{demo.id}.mp4"
    result = assemble_demo_video(tl, frames, out_path=out, video=video, audio=clips, ffmpeg=FFMPEG)
    assert out.stat().st_size > 10_000
    assert result.seconds == pytest.approx(tl.total_seconds)
    assert probe_seconds(out) == pytest.approx(tl.total_seconds, abs=0.05)
