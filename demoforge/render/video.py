"""Video assembly: frames + narration → mp4, driven by ffmpeg alone (§7).

No editor, no GUI, no hand-cut timeline. The frame list and its durations come
straight from ``timeline.json``, so the video inherits the replay's guarantee: it can
only show scenes that recorded events produced.

Two passes, both deterministic:

1. **Audio.** Each scene gets exactly its own duration of audio — its narration clip
   padded with silence, or silence alone. Clips are normalized to the configured PCM
   format through ffmpeg first, then assembled with the stdlib ``wave`` module, so the
   track is sample-exact against the scene boundaries rather than drifting.
2. **Mux.** The frames go through ffmpeg's concat demuxer at their computed durations
   and are encoded with the pinned flags from ``config/video.yaml``.

Output is cached against a key over the frames, durations, audio and encode settings;
every one of those is itself content-addressed, so an unchanged build does no work.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from demoforge.errors import DemoForgeError
from demoforge.render.config import VideoEncode
from demoforge.render.frames import Frame
from demoforge.render.narration import AudioClip
from demoforge.render.timeline import Scene, narration_spans
from demoforge.render.timeline import Timeline

# Bump when assembly changes its output for unchanged inputs.
VIDEO_VERSION = "3"
KEY_SUFFIX = ".key.json"


@dataclass(frozen=True)
class VideoResult:
    """One assembled file and how it got there."""

    path: Path
    seconds: float
    cached: bool


# ---- tool discovery ---------------------------------------------------
def resolve_ffmpeg(ffmpeg: Path | str | None = None) -> Path:
    """The ffmpeg binary to use: explicit, else from PATH."""
    if ffmpeg is not None:
        path = Path(ffmpeg)
        if path.is_file() or shutil.which(str(ffmpeg)):
            return path
        raise DemoForgeError(f"ffmpeg not found at {ffmpeg}")
    found = shutil.which("ffmpeg")
    if not found:
        raise DemoForgeError(
            "ffmpeg not found on PATH — video assembly needs it "
            "(config/tools.toml pins the expected version)"
        )
    return Path(found)


def ffmpeg_available(ffmpeg: Path | str | None = None) -> bool:
    try:
        resolve_ffmpeg(ffmpeg)
    except DemoForgeError:
        return False
    return True


# ---- per-demo video ---------------------------------------------------
def assemble_demo_video(
    timeline: Timeline,
    frames: Sequence[Frame],
    *,
    out_path: Path,
    video: VideoEncode,
    audio: dict[str, AudioClip] | None = None,
    ffmpeg: Path | str | None = None,
    work_dir: Path | None = None,
    force: bool = False,
) -> VideoResult:
    """Assemble one demo chapter from its rendered frames and narration.

    ``force`` re-encodes even on a cache hit; see :func:`render_frames`.
    """
    if not frames:
        raise DemoForgeError(f"no frames to assemble for {timeline.demo_id!r}")
    exe = resolve_ffmpeg(ffmpeg)
    scenes_by_index = {s.index: s for s in timeline.scenes}
    clips = audio or {}

    key = _demo_key(timeline, frames, clips, video)
    if not force and _key_matches(out_path, key):
        return VideoResult(path=out_path, seconds=_total(frames), cached=True)

    work = work_dir or out_path.parent / f".{out_path.stem}.work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    try:
        concat = _write_frame_concat(frames, work / "frames.txt")
        track = _build_audio_track(
            frames, scenes_by_index, clips, video, exe, work / "audio.wav"
        )
        _encode(exe, concat, track, out_path, video, _total(frames))
    finally:
        shutil.rmtree(work, ignore_errors=True)

    _write_key(out_path, key)
    return VideoResult(path=out_path, seconds=_total(frames), cached=False)


def assemble_card_clip(
    image: Path,
    seconds: float,
    *,
    out_path: Path,
    video: VideoEncode,
    audio: AudioClip | None = None,
    ffmpeg: Path | str | None = None,
    force: bool = False,
) -> VideoResult:
    """Encode one still card as a clip, so it concatenates like any other chapter.

    Same encode settings as a demo chapter — a card that differed in codec, rate or
    pixel format would force the final concat to re-encode everything.
    """
    if not image.is_file():
        raise DemoForgeError(f"card image not found: {image}")
    exe = resolve_ffmpeg(ffmpeg)

    key = _digest(
        VIDEO_VERSION, "card", image.name, f"{seconds:.3f}",
        audio.path.name if audio else "-", _encode_signature(video),
    )
    if not force and _key_matches(out_path, key):
        return VideoResult(path=out_path, seconds=round(seconds, 3), cached=True)

    work = out_path.parent / f".{out_path.stem}.work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    try:
        frame = Frame(
            scene_index=0, kind="Card", path=image, duration=seconds, cached=True
        )
        track = _build_audio_track(
            [frame], {0: Scene(index=0, kind="Card", template="", label="", event_seqs=(),
                          duration=seconds, narration=audio.key if audio else None)},
            {audio.key: audio} if audio else {}, video, exe, work / "audio.wav",
        )
        _encode(exe, _write_frame_concat([frame], work / "frames.txt"), track,
                out_path, video, seconds)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    _write_key(out_path, key)
    return VideoResult(path=out_path, seconds=round(seconds, 3), cached=False)


def concat_videos(
    parts: Sequence[Path],
    out_path: Path,
    *,
    video: VideoEncode,
    ffmpeg: Path | str | None = None,
    force: bool = False,
) -> VideoResult:
    """Join per-demo chapters into the full presentation, re-encoding once."""
    if not parts:
        raise DemoForgeError("no chapters to concatenate")
    missing = [p for p in parts if not p.is_file()]
    if missing:
        raise DemoForgeError(f"missing chapter video(s): {', '.join(str(m) for m in missing)}")
    exe = resolve_ffmpeg(ffmpeg)

    key = _digest(VIDEO_VERSION, "concat", _encode_signature(video), *(_file_hash(p) for p in parts))
    if not force and _key_matches(out_path, key):
        return VideoResult(path=out_path, seconds=0.0, cached=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    listing = out_path.parent / f".{out_path.stem}.concat.txt"
    listing.write_text(
        "".join(f"file {_concat_path(p)}\n" for p in parts),
        encoding="utf-8",
        newline="\n",
    )
    try:
        _run(exe, [
            "-f", "concat", "-safe", "0", "-i", str(listing),
            *_video_flags(video), *_audio_flags(video), *_determinism_flags(video),
            str(out_path),
        ])
    finally:
        listing.unlink(missing_ok=True)

    _write_key(out_path, key)
    return VideoResult(path=out_path, seconds=probe_seconds(out_path, ffmpeg=exe), cached=False)


def probe_seconds(path: Path, *, ffmpeg: Path | str | None = None) -> float:
    """Duration of a media file, read back from the file itself."""
    exe = resolve_ffmpeg(ffmpeg)
    probe = exe.parent / ("ffprobe.exe" if exe.suffix.lower() == ".exe" else "ffprobe")
    if not probe.is_file():
        found = shutil.which("ffprobe")
        if not found:
            return 0.0
        probe = Path(found)
    proc = subprocess.run(
        [str(probe), "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    try:
        return round(float(proc.stdout.strip()), 3)
    except ValueError:
        return 0.0


# ---- frames -----------------------------------------------------------
def _concat_path(path: Path) -> str:
    """Quote a path for ffmpeg's concat demuxer.

    Nothing can be escaped inside single quotes, so each apostrophe closes the
    quote, is written escaped, and reopens it: ``it's`` becomes ``'it'\\''s'``.
    """
    return "'" + path.resolve().as_posix().replace("'", "'\\''") + "'"


def _write_frame_concat(frames: Sequence[Frame], path: Path) -> Path:
    """ffmpeg concat demuxer script: each frame held for its scene's duration.

    The demuxer ignores the final entry's ``duration``, so the last frame is listed
    twice — otherwise the closing results panel would flash past.
    """
    lines: list[str] = []
    for frame in frames:
        lines.append(f"file {_concat_path(frame.path)}")
        lines.append(f"duration {frame.duration:.3f}")
    lines.append(f"file {_concat_path(frames[-1].path)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


# ---- audio ------------------------------------------------------------
def _build_audio_track(
    frames: Sequence[Frame],
    scenes_by_index: dict[int, Scene],
    clips: dict[str, AudioClip],
    video: VideoEncode,
    ffmpeg: Path,
    out_path: Path,
) -> Path:
    """One PCM track whose scene boundaries line up exactly with the frames.

    An animated scene is several frames in a row, and a long message is several
    scenes in a row; its narration plays once across all of them, not again on
    every frame or page.
    """
    normalized: dict[str, bytes] = {}
    leaders = narration_spans(sorted(scenes_by_index.values(), key=lambda s: s.index))
    runs: list[tuple[int, int]] = []  # (scene index the narration comes from, samples)
    for frame in frames:
        samples = int(round(frame.duration * video.sample_rate))
        leader = leaders.get(frame.scene_index, frame.scene_index)
        if runs and runs[-1][0] == leader:
            runs[-1] = (leader, runs[-1][1] + samples)
        else:
            runs.append((leader, samples))
    with wave.open(str(out_path), "wb") as out:
        out.setnchannels(video.channels)
        out.setsampwidth(2)
        out.setframerate(video.sample_rate)
        for scene_index, want in runs:
            scene = scenes_by_index.get(scene_index)
            key = getattr(scene, "narration", None)
            payload = b""
            if key and key in clips:
                if key not in normalized:
                    normalized[key] = _normalized_pcm(
                        clips[key].path, video, ffmpeg, out_path.parent
                    )
                payload = normalized[key]
            out.writeframes(_fit(payload, want, video))
    return out_path


def _normalized_pcm(path: Path, video: VideoEncode, ffmpeg: Path, work: Path) -> bytes:
    """Raw PCM frames for a clip, resampled to the configured track format."""
    dest = work / f"norm-{path.stem}.wav"
    _run(ffmpeg, [
        "-i", str(path),
        "-ar", str(video.sample_rate), "-ac", str(video.channels),
        "-c:a", "pcm_s16le", "-f", "wav", str(dest),
    ])
    with wave.open(str(dest), "rb") as fh:
        data = fh.readframes(fh.getnframes())
    dest.unlink(missing_ok=True)
    return data


def _fit(payload: bytes, want_frames: int, video: VideoEncode) -> bytes:
    """Pad with silence, or trim, so the segment is exactly ``want_frames`` long."""
    stride = 2 * video.channels
    want_bytes = want_frames * stride
    if len(payload) >= want_bytes:
        return payload[:want_bytes]
    return payload + b"\0" * (want_bytes - len(payload))


# ---- encoding ---------------------------------------------------------
def _encode(
    ffmpeg: Path,
    concat: Path,
    audio: Path,
    out_path: Path,
    video: VideoEncode,
    seconds: float,
) -> None:
    """Encode to exactly ``seconds`` — the timeline's length, by construction.

    The concat demuxer ignores the last entry's duration, so the list repeats the
    final frame to make it apply; that repeat would otherwise run past the end.
    `-t` is used rather than `-shortest` because the timeline, not whichever input
    happens to end first, is what defines how long the chapter is.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run(ffmpeg, [
        "-f", "concat", "-safe", "0", "-i", str(concat),
        "-i", str(audio),
        "-map", "0:v:0", "-map", "1:a:0",
        "-fps_mode", "cfr", "-r", str(video.fps),
        *_video_flags(video), *_audio_flags(video), *_determinism_flags(video),
        "-t", f"{seconds:.3f}",
        str(out_path),
    ])


def _video_flags(video: VideoEncode) -> list[str]:
    return [
        "-c:v", video.video_codec,
        "-crf", str(video.crf),
        "-preset", video.preset,
        "-pix_fmt", video.pix_fmt,
        "-vf", f"scale={video.width}:{video.height}",
    ]


def _audio_flags(video: VideoEncode) -> list[str]:
    return [
        "-c:a", video.audio_codec,
        "-b:a", video.audio_bitrate,
        "-ar", str(video.sample_rate),
        "-ac", str(video.channels),
    ]


def _determinism_flags(video: VideoEncode) -> list[str]:
    """Drop capture timestamps and encoder tags so rebuilt bytes are stable."""
    if not video.deterministic_metadata:
        return []
    return ["-map_metadata", "-1", "-fflags", "+bitexact", "-flags:v", "+bitexact",
            "-flags:a", "+bitexact", "-movflags", "+faststart"]


def _run(ffmpeg: Path, args: list[str]) -> None:
    cmd = [str(ffmpeg), "-nostdin", "-hide_banner", "-loglevel", "error", "-y", *args]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DemoForgeError(f"ffmpeg failed to run: {exc}") from exc
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()[-5:]
        raise DemoForgeError(
            f"ffmpeg exited {proc.returncode}: {' / '.join(tail) or 'no diagnostics'}"
        )


# ---- cache ------------------------------------------------------------
def _demo_key(
    timeline: Timeline,
    frames: Sequence[Frame],
    clips: dict[str, AudioClip],
    video: VideoEncode,
) -> str:
    parts = [VIDEO_VERSION, "demo", timeline.demo_id, _encode_signature(video)]
    for frame in frames:
        # Frame filenames are already content addresses, so the name is the content.
        parts += [frame.path.name, f"{frame.duration:.3f}"]
    for key in sorted(clips):
        parts += [key, clips[key].path.name, f"{clips[key].seconds:.3f}"]
    return _digest(*parts)


def _encode_signature(video: VideoEncode) -> str:
    return json.dumps(video.__dict__, sort_keys=True)


def _digest(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


def _key_path(out_path: Path) -> Path:
    return out_path.with_suffix(out_path.suffix + KEY_SUFFIX)


def _key_matches(out_path: Path, key: str) -> bool:
    sidecar = _key_path(out_path)
    if not (out_path.is_file() and sidecar.is_file()):
        return False
    try:
        return json.loads(sidecar.read_text(encoding="utf-8")).get("key") == key
    except (json.JSONDecodeError, OSError):
        return False


def _write_key(out_path: Path, key: str) -> None:
    _key_path(out_path).write_text(
        json.dumps({"version": VIDEO_VERSION, "key": key}, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _total(frames: Sequence[Frame]) -> float:
    return round(sum(f.duration for f in frames), 3)
