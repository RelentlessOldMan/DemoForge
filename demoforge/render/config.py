"""Presentation configuration for the replay layer: scene map, pacing, encoding.

Three committed YAML files drive everything downstream of ``approve``:
``config/scenes.yaml`` (how a recorded event looks), ``config/timing.yaml`` (how long
it is on screen) and ``config/video.yaml`` (how it is encoded). Engine defaults live at
the repo root; a content set may override any of them under ``<set>/config/``.

Loading is pure and total: a missing file falls back to the dataclass defaults rather
than failing, so records and slides keep building on a machine with no video layer
configured (docs/video-pipeline.md §10.1).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml

from demoforge.errors import ConfigError

SCENES_FILE = "scenes.yaml"
TIMING_FILE = "timing.yaml"
VIDEO_FILE = "video.yaml"

# Repo-root config/ — the engine's committed defaults.
ENGINE_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


# ---- scene style map --------------------------------------------------
@dataclass(frozen=True)
class SceneStyle:
    """How one recorded event type is presented."""

    kind: str
    template: str
    label: str = ""
    # One plain-language line telling a newcomer what this kind of step is. It may
    # name recorded fields as ``{name}`` / ``{tool}``; it never describes intent.
    explain: str = ""


@dataclass(frozen=True)
class Limits:
    """What fits on a frame. The timeline paces the *truncated* text, not the raw text."""

    terminal_max_lines: int = 16
    terminal_max_line_chars: int = 110
    # A long command is cut after this many on-screen lines; it shares
    # terminal_max_lines with its output.
    terminal_command_max_lines: int = 5
    # Text cards (the prompt, Claude's words, a follow-up) longer than one page are
    # shown over several consecutive pages instead of being cut. A page holds about
    # this many lines of about this many characters.
    text_page_lines: int = 11
    text_line_chars: int = 100


@dataclass(frozen=True)
class SceneMap:
    """Parsed ``scenes.yaml``: the event → scene mapping and its display caps."""

    styles: dict[str, SceneStyle] = field(default_factory=dict)
    merge_into_previous: dict[str, str] = field(default_factory=dict)
    ignore: frozenset[str] = frozenset()
    limits: Limits = field(default_factory=Limits)

    def style_for(self, event_type: str) -> SceneStyle | None:
        """The style for ``event_type``, or ``None`` if it is not shown."""
        if event_type in self.ignore:
            return None
        return self.styles.get(event_type)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SceneMap":
        styles: dict[str, SceneStyle] = {}
        for etype, spec in (data.get("scenes") or {}).items():
            if not isinstance(spec, dict) or "kind" not in spec or "template" not in spec:
                raise ConfigError(
                    f"scenes.yaml: entry {etype!r} needs both 'kind' and 'template'"
                )
            styles[str(etype)] = SceneStyle(
                kind=str(spec["kind"]),
                template=str(spec["template"]),
                label=str(spec.get("label", "")),
                explain=str(spec.get("explain", "")),
            )
        lim = data.get("limits") or {}
        return cls(
            styles=styles,
            merge_into_previous={
                str(k): str(v) for k, v in (data.get("merge_into_previous") or {}).items()
            },
            ignore=frozenset(str(x) for x in (data.get("ignore") or [])),
            limits=Limits(
                terminal_max_lines=int(lim.get("terminal_max_lines", 16)),
                terminal_max_line_chars=int(lim.get("terminal_max_line_chars", 110)),
                terminal_command_max_lines=int(lim.get("terminal_command_max_lines", 5)),
                text_page_lines=int(lim.get("text_page_lines", 11)),
                text_line_chars=int(lim.get("text_line_chars", 100)),
            ),
        )


# ---- pacing -----------------------------------------------------------
@dataclass(frozen=True)
class Timing:
    """Parsed ``timing.yaml``. Durations come from here, never from wall clock."""

    scene_min_seconds: float = 1.5
    scene_max_seconds: float = 8.0
    read_scene_max_seconds: float = 20.0
    # Terminal output is skimmed, not read line by line, so it gets a shorter cap.
    terminal_scene_max_seconds: float = 20.0
    # Silence after a narrated scene's audio ends, so the cut never clips a word.
    narration_tail_seconds: float = 0.0
    reading_chars_per_second: float = 18.0
    terminal_chars_per_second: float = 60.0
    narration_chars_per_second: float = 14.0
    chapter_end_seconds: float = 6.0
    title_card_seconds: float = 6.0
    chapter_card_seconds: float = 4.0
    outro_card_seconds: float = 9.0
    contents_card_seconds: float = 10.0
    compress_idle: bool = True
    compress_notice_seconds: float = 10.0
    fps: int = 30
    # How the replay is drawn: "session" animates one continuous Claude Code window
    # (typing, streaming, scrolling); "slides" shows one still card per scene.
    replay_style: str = "session"
    # Session animation speeds. They only decide how fast recorded text appears;
    # a scene's length, and so the narration over it, is unchanged.
    typing_chars_per_second: float = 45.0
    stream_chars_per_second: float = 150.0
    output_lines_per_second: float = 12.0
    # Shortest hold between two animation frames.
    session_step_seconds: float = 0.12
    # In a session, the later pages of a long message stream on in place and are
    # skimmed, not read card by card: each shows for its streaming time plus this
    # hold. The narration over the message still decides its full length.
    continued_page_hold_seconds: float = 2.0

    def __post_init__(self) -> None:
        if self.replay_style not in ("session", "slides"):
            raise ConfigError("timing.yaml: replay_style must be 'session' or 'slides'")
        for name in (
            "typing_chars_per_second",
            "stream_chars_per_second",
            "output_lines_per_second",
            "session_step_seconds",
        ):
            if getattr(self, name) <= 0:
                raise ConfigError(f"timing.yaml: {name} must be > 0")
        if self.continued_page_hold_seconds < 0:
            raise ConfigError("timing.yaml: continued_page_hold_seconds must be >= 0")
        if self.scene_min_seconds <= 0:
            raise ConfigError("timing.yaml: scene_min_seconds must be > 0")
        if self.scene_max_seconds < self.scene_min_seconds:
            raise ConfigError("timing.yaml: scene_max_seconds must be >= scene_min_seconds")
        if self.read_scene_max_seconds < self.scene_min_seconds:
            raise ConfigError(
                "timing.yaml: read_scene_max_seconds must be >= scene_min_seconds"
            )
        if self.terminal_scene_max_seconds < self.scene_min_seconds:
            raise ConfigError(
                "timing.yaml: terminal_scene_max_seconds must be >= scene_min_seconds"
            )
        if self.narration_tail_seconds < 0:
            raise ConfigError("timing.yaml: narration_tail_seconds must be >= 0")
        for name in (
            "reading_chars_per_second",
            "terminal_chars_per_second",
            "narration_chars_per_second",
        ):
            if getattr(self, name) <= 0:
                raise ConfigError(f"timing.yaml: {name} must be > 0")
        if self.fps <= 0:
            raise ConfigError("timing.yaml: fps must be > 0")
        for name in (
            "title_card_seconds",
            "chapter_card_seconds",
            "outro_card_seconds",
            "contents_card_seconds",
        ):
            if getattr(self, name) <= 0:
                raise ConfigError(f"timing.yaml: {name} must be > 0")

    def clamp(self, seconds: float) -> float:
        """Hold ``seconds`` inside the glance-scene bounds."""
        return min(max(seconds, self.scene_min_seconds), self.scene_max_seconds)

    def clamp_read(self, seconds: float) -> float:
        """Hold ``seconds`` inside the bounds for a scene that must be read."""
        return min(max(seconds, self.scene_min_seconds), self.read_scene_max_seconds)

    def clamp_terminal(self, seconds: float) -> float:
        """Hold ``seconds`` inside the bounds for a terminal card."""
        return min(max(seconds, self.scene_min_seconds), self.terminal_scene_max_seconds)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Timing":
        return _build(cls, data)


# ---- encoding ---------------------------------------------------------
@dataclass(frozen=True)
class VideoEncode:
    """Parsed ``video.yaml``: pinned ffmpeg flags so output bytes are stable."""

    width: int = 1920
    height: int = 1080
    fps: int = 30
    video_codec: str = "libx264"
    crf: int = 20
    preset: str = "medium"
    pix_fmt: str = "yuv420p"
    audio_codec: str = "aac"
    audio_bitrate: str = "160k"
    sample_rate: int = 48000
    channels: int = 1
    deterministic_metadata: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VideoEncode":
        return _build(cls, data)


@dataclass(frozen=True)
class PresentationSettings:
    """The three replay configs, resolved together for one content set."""

    scenes: SceneMap
    timing: Timing
    video: VideoEncode


def load_settings(
    content_set_root: Path | None = None,
    *,
    engine_dir: Path | None = None,
) -> PresentationSettings:
    """Load scene/timing/video config, overlaying a content set's own ``config/``."""
    engine = engine_dir or ENGINE_CONFIG_DIR
    override = (content_set_root / "config") if content_set_root else None
    return PresentationSettings(
        scenes=SceneMap.from_dict(_layered(engine, override, SCENES_FILE)),
        timing=Timing.from_dict(_layered(engine, override, TIMING_FILE)),
        video=VideoEncode.from_dict(_layered(engine, override, VIDEO_FILE)),
    )


def with_timing(settings: PresentationSettings, timing: Timing) -> PresentationSettings:
    """A copy of ``settings`` with different pacing (used by tests and `--fast`)."""
    return replace(settings, timing=timing)


# ---- loading helpers --------------------------------------------------
def _layered(engine_dir: Path, override_dir: Path | None, name: str) -> dict[str, Any]:
    """Engine defaults, then the content set's override merged one level deep."""
    data = _read_yaml(engine_dir / name)
    if override_dir is not None:
        for key, value in _read_yaml(override_dir / name).items():
            if isinstance(value, dict) and isinstance(data.get(key), dict):
                merged = dict(data[key])
                merged.update(value)
                data[key] = merged
            else:
                data[key] = value
    return data


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} is not valid YAML: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a mapping at the top level")
    return data


def _build(cls, data: dict[str, Any]):
    """Construct a frozen config from ``data``, coercing to each field's type."""
    kwargs = {}
    for name, f in cls.__dataclass_fields__.items():
        if name not in data:
            continue
        value = data[name]
        if f.type in ("bool", bool):
            kwargs[name] = bool(value)
        elif f.type in ("int", int):
            kwargs[name] = int(value)
        elif f.type in ("float", float):
            kwargs[name] = float(value)
        else:
            kwargs[name] = str(value)
    return cls(**kwargs)
