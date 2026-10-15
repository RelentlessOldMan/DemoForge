"""Deterministic rendering: approved bundles -> records and slides.

Everything here is a pure function of committed inputs (approved bundles, demo
definitions, config, templates) plus pinned tools — it never re-runs the agent
and never invents an action (docs/video-pipeline.md). Records and slides are the
core deliverable; the replay timeline, frames and video build on the same rule —
every scene is derived from a recorded event.
"""

from demoforge.render.record import render_record
from demoforge.render.slides import render_slides, write_deck
from demoforge.render.pipeline import RenderSummary, render_all
from demoforge.render.config import (
    PresentationSettings,
    SceneMap,
    Timing,
    VideoEncode,
    load_settings,
)
from demoforge.render.frames import (
    ChromiumRenderer,
    Frame,
    FrameContext,
    FrameRenderer,
    chromium_available,
    context_for,
    render_frames,
    scene_html,
)
from demoforge.render.narration import (
    AudioClip,
    Narration,
    NarrationBlock,
    PiperTTS,
    SilentTTS,
    TTSProvider,
    anchor_narration,
    clip_seconds,
    load_narration,
    make_provider,
    parse_narration,
    synthesize_narration,
)
from demoforge.render.video_pipeline import Chapter, VideoSummary, build_videos
from demoforge.render.video import (
    VideoResult,
    assemble_demo_video,
    concat_videos,
    ffmpeg_available,
    probe_seconds,
    resolve_ffmpeg,
)
from demoforge.render.timeline import (
    Scene,
    Timeline,
    build_timeline,
    read_timeline,
    stretch_for_narration,
    with_narration,
    write_timeline,
)

__all__ = [
    "render_record",
    "render_slides",
    "write_deck",
    "render_all",
    "RenderSummary",
    "PresentationSettings",
    "SceneMap",
    "Timing",
    "VideoEncode",
    "load_settings",
    "Scene",
    "Timeline",
    "build_timeline",
    "read_timeline",
    "with_narration",
    "stretch_for_narration",
    "write_timeline",
    "Narration",
    "NarrationBlock",
    "AudioClip",
    "TTSProvider",
    "SilentTTS",
    "PiperTTS",
    "parse_narration",
    "load_narration",
    "anchor_narration",
    "make_provider",
    "synthesize_narration",
    "clip_seconds",
    "Frame",
    "FrameContext",
    "FrameRenderer",
    "ChromiumRenderer",
    "chromium_available",
    "context_for",
    "render_frames",
    "scene_html",
    "VideoResult",
    "assemble_demo_video",
    "concat_videos",
    "ffmpeg_available",
    "probe_seconds",
    "resolve_ffmpeg",
    "Chapter",
    "VideoSummary",
    "build_videos",
]
