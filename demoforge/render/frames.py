"""Scenes → PNG frames via Jinja2 templates and headless Chromium (§5.3).

Two deliberate properties:

*Content-addressed.* A frame's filename is a hash of the **rendered HTML** plus the
viewport, so it folds in the scene data, the template, and every config value that
reached either. Change a template or a timing constant and exactly the affected frames
re-render; change nothing and no work happens at all.

*Traceable.* The template context is built from the timeline scene — which names the
recorded events behind it — and the approved bundle's ``results.json``. There is no
path by which a frame can show something the capture does not contain.

Jinja2 and Playwright are optional: this module imports them lazily so records and
slides keep building on a machine without the video layer installed.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator, Protocol, Sequence

from demoforge.errors import DemoForgeError
from demoforge.render.config import VideoEncode
from demoforge.render.timeline import Scene, Timeline

if TYPE_CHECKING:
    from demoforge.render.session import Beat

# Bump when frame markup changes in a way templates alone do not capture.
FRAME_VERSION = "1"

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates" / "scenes"
FONTS_DIR = Path(__file__).resolve().parents[2] / "templates" / "fonts"
BASE_TEMPLATE = "_base.html.j2"

# Bundled faces, declared under neutral family names so the CSS stack can fall
# back to system fonts when the files are absent. (family, file, weight)
BUNDLED_FONTS = (
    ("DemoForge Sans", "Inter-Regular.woff2", 400),
    ("DemoForge Sans", "Inter-SemiBold.woff2", 600),
    ("DemoForge Mono", "JetBrainsMono-Regular.woff2", 400),
    ("DemoForge Mono", "JetBrainsMono-Bold.woff2", 700),
)


@dataclass(frozen=True)
class FrameContext:
    """Per-demo values every scene template can draw on."""

    set_title: str
    demo_title: str
    demo_id: str
    scene_count: int
    results: tuple[dict[str, Any], ...] = ()
    # For the corner label a viewer quotes back: the demo's place in the set, the
    # intro cards shown before the replay, and how many events the record holds.
    demo_number: int = 0
    intro_slides: int = 0
    event_total: int = 0

    @property
    def slide_total(self) -> int:
        return self.intro_slides + self.scene_count


def event_label(seqs: Sequence[int], total: int) -> str:
    """``Event 14 / 25`` for the recorded events behind a slide, counted from 1.

    The record numbers its events from 0 (``seq``, and ``during:<seq>`` in a
    narration file), but a viewer counts from 1, so the screen shows ``seq + 1``.
    Empty when the slide is built from no event: a card never claims one.
    """
    shown = sorted({s + 1 for s in seqs})
    if not shown:
        return ""
    of = f" / {total}" if total else ""
    if len(shown) == 1:
        return f"Event {shown[0]}{of}"
    if shown == list(range(shown[0], shown[-1] + 1)):
        return f"Events {shown[0]}–{shown[-1]}{of}"
    return f"Events {', '.join(map(str, shown))}{of}"


def corner_label(
    *, demo_number: int = 0, slide: int = 0, slide_total: int = 0,
    seqs: Sequence[int] = (), event_total: int = 0, prefix: str = "",
) -> str:
    """The lower-right label, e.g. ``Demo 3 · Event 14 / 25 · Slide 17 / 104``.

    Slides are numbered within the demo, so a demo's own video and the full
    presentation show the same numbers, and adding a demo renumbers nothing else.
    """
    parts = []
    if prefix:
        parts.append(prefix)
    elif demo_number:
        parts.append(f"Demo {demo_number}")
    events = event_label(seqs, event_total)
    if events:
        parts.append(events)
    if slide:
        parts.append(f"Slide {slide} / {slide_total}" if slide_total else f"Slide {slide}")
    return " · ".join(parts)


@dataclass(frozen=True)
class Frame:
    """One rendered image: a whole scene, or one animation beat of it."""

    scene_index: int
    kind: str
    path: Path
    duration: float
    cached: bool
    step: int = 0


class FrameRenderer(Protocol):
    """HTML → PNG. Swappable so the pipeline is not welded to one browser (§1.5)."""

    def render(self, html: str, out_path: Path) -> None: ...


# ---- template rendering -----------------------------------------------
def scene_html(
    scene: Scene,
    context: FrameContext,
    video: VideoEncode,
    *,
    templates_dir: Path | None = None,
    fonts_dir: Path | None = None,
    template: str | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    """Render one scene's HTML. Pure: same inputs, same bytes.

    ``template`` and ``extra`` draw the scene another way, such as one beat of the
    animated session, with the same chrome and the same traced event numbers.
    """
    env = _environment(templates_dir or TEMPLATES_DIR)
    name = template or scene.template
    try:
        tmpl = env.get_template(name)
    except Exception as exc:  # jinja2.TemplateNotFound and friends
        raise DemoForgeError(
            f"scene template {name!r} not found under "
            f"{templates_dir or TEMPLATES_DIR} (scenes.yaml names it)"
        ) from exc
    return tmpl.render(**_template_vars(scene, context, video, fonts_dir), **(extra or {}))


def _template_vars(
    scene: Scene,
    context: FrameContext,
    video: VideoEncode,
    fonts_dir: Path | None = None,
) -> dict[str, Any]:
    return {
        "font_css": font_face_css(fonts_dir),
        "kind": scene.kind,
        "label": scene.label,
        "index": scene.index,
        "event_seqs": list(scene.event_seqs),
        "duration": scene.duration,
        "real_seconds": scene.real_seconds,
        "compressed": scene.compressed,
        "narration": scene.narration,
        "explain": scene.explain,
        "caption": scene.caption,
        "data": scene.data,
        "set_title": context.set_title,
        "demo_title": context.demo_title,
        "demo_id": context.demo_id,
        "scene_count": context.scene_count,
        "corner": corner_label(
            demo_number=context.demo_number,
            slide=context.intro_slides + scene.index + 1,
            slide_total=context.slide_total,
            seqs=scene.event_seqs,
            event_total=context.event_total,
        ),
        "results": [dict(r) for r in context.results],
        "width": video.width,
        "height": video.height,
    }


def _environment(templates_dir: Path):
    try:
        from jinja2 import Environment, FileSystemLoader, StrictUndefined
    except ImportError as exc:  # pragma: no cover - exercised by the skip guard
        raise DemoForgeError(
            "frame rendering needs Jinja2: pip install 'demoforge[video]'"
        ) from exc
    if not templates_dir.is_dir():
        raise DemoForgeError(f"no scene templates at {templates_dir}")
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=True,
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    env.filters["num"] = format_number
    return env


def format_number(value: Any, places: int = 4) -> str:
    """Render a measured value readably without implying false precision.

    A harness reports a float at full machine precision; 46.96262994695506 on a
    slide is noise, not rigour. Integers stay exact, floats keep `places`
    decimals with trailing zeros trimmed, and non-numbers pass through.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "" if value is None else str(value)
    if isinstance(value, int):
        return f"{value:,}"
    if value != value or value in (float("inf"), float("-inf")):  # NaN / inf
        return str(value)
    if value != 0 and abs(value) < 10 ** -places:
        return f"{value:.{places}e}"
    text = f"{value:,.{places}f}".rstrip("0").rstrip(".")
    return text or "0"


def font_face_css(fonts_dir: Path | None = None) -> str:
    """``@font-face`` rules for the bundled faces, with the files inlined as data URIs.

    Inlining rather than linking is what makes a frame reproducible on another
    machine. A ``file://`` URL would put a machine-specific path into the markup,
    and the frame cache key is a hash of that markup — so two machines would
    disagree about every frame despite rendering the same thing. A data URI also
    sidesteps the fact that ``set_content`` gives the page no base URL to resolve
    a relative path against.

    Missing fonts are not an error: the rules are simply omitted and the CSS stack
    falls through to whatever the machine has.
    """
    directory = fonts_dir or FONTS_DIR
    present = tuple(
        (family, name, weight, _stat_key(directory / name))
        for family, name, weight in BUNDLED_FONTS
        if (directory / name).is_file()
    )
    return _font_face_css(directory, present)


@lru_cache(maxsize=8)
def _font_face_css(directory: Path, present: tuple) -> str:
    """Build the rules. Cached on the files' identity, so a swap invalidates it."""
    rules: list[str] = []
    for family, name, weight, _stamp in present:
        encoded = base64.b64encode((directory / name).read_bytes()).decode("ascii")
        rules.append(
            f"@font-face{{font-family:'{family}';font-style:normal;"
            f"font-weight:{weight};font-display:block;"
            f"src:url(data:font/woff2;base64,{encoded}) format('woff2');}}"
        )
    return "\n".join(rules)


def _stat_key(path: Path) -> tuple[int, int]:
    info = path.stat()
    return (info.st_size, info.st_mtime_ns)


def frame_key(html: str, video: VideoEncode) -> str:
    """Content address for a frame: its exact markup and the viewport it renders in."""
    h = hashlib.sha256()
    for part in (FRAME_VERSION, str(video.width), str(video.height), html):
        h.update(part.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()[:16]


# ---- Chromium backend -------------------------------------------------
class ChromiumRenderer:
    """Headless Chromium at a pinned viewport, animations disabled.

    Used as a context manager so one browser serves a whole deck of frames::

        with ChromiumRenderer(video) as r:
            render_frames(timeline, ctx, out_dir=..., video=video, renderer=r)
    """

    def __init__(self, video: VideoEncode) -> None:
        self._video = video
        self._playwright = None
        self._browser = None
        self._page = None

    def __enter__(self) -> "ChromiumRenderer":
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise DemoForgeError(
                "frame rendering needs Playwright: pip install 'demoforge[video]' "
                "then `python -m playwright install chromium`"
            ) from exc
        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.launch(
                args=["--force-color-profile=srgb", "--font-render-hinting=none"],
            )
            self._page = self._browser.new_page(
                viewport={"width": self._video.width, "height": self._video.height},
                device_scale_factor=1,
                reduced_motion="reduce",
            )
        except Exception as exc:
            self.__exit__(None, None, None)
            raise DemoForgeError(f"could not launch Chromium: {exc}") from exc
        return self

    def __exit__(self, *_exc: object) -> None:
        for closer in (self._page, self._browser):
            if closer is not None:
                try:
                    closer.close()
                except Exception:  # pragma: no cover - teardown is best-effort
                    pass
        if self._playwright is not None:
            self._playwright.stop()
        self._page = self._browser = self._playwright = None

    def render(self, html: str, out_path: Path) -> None:
        if self._page is None:
            raise DemoForgeError("ChromiumRenderer must be used as a context manager")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        self._page.set_content(html, wait_until="load")
        self._page.screenshot(path=str(out_path), animations="disabled", caret="hide")


def chromium_available() -> bool:
    """Whether a frame can actually be rasterized here (Playwright + a browser)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            browser.close()
    except Exception:
        return False
    return True


# ---- orchestration ----------------------------------------------------
def render_frames(
    timeline: Timeline,
    context: FrameContext,
    *,
    out_dir: Path,
    video: VideoEncode,
    renderer: FrameRenderer,
    templates_dir: Path | None = None,
    force: bool = False,
    beats: "dict[int, list[Beat]] | None" = None,
) -> list[Frame]:
    """Render every scene to cached PNGs under ``out_dir``, in timeline order.

    A scene with ``beats`` becomes one image per beat, each held for its share of
    the scene; any other scene is one image held for the whole scene.

    ``force`` re-renders even on a cache hit. The key is content-addressed, so this
    is not needed to pick up a changed template — it exists to prove the cache is
    telling the truth, and to recover from a PNG left half-written by a crash.
    """
    from demoforge.render.session import SESSION_TEMPLATE

    out_dir.mkdir(parents=True, exist_ok=True)
    frames: list[Frame] = []

    def draw(scene: Scene, html: str, duration: float, step: int, name: str) -> None:
        path = out_dir / f"{scene.index:04d}-{name}-{frame_key(html, video)}.png"
        cached = path.is_file() and not force
        if not cached:
            renderer.render(html, path)
        frames.append(Frame(
            scene_index=scene.index, kind=scene.kind, path=path,
            duration=duration, cached=cached, step=step,
        ))

    for scene in timeline.scenes:
        scene_beats = (beats or {}).get(scene.index)
        if not scene_beats:
            html = scene_html(scene, context, video, templates_dir=templates_dir)
            draw(scene, html, scene.duration, 0, scene.kind)
            continue
        for beat in scene_beats:
            html = scene_html(
                scene, context, video, templates_dir=templates_dir,
                template=SESSION_TEMPLATE, extra={"session": beat.session},
            )
            draw(scene, html, beat.duration, beat.step, f"{scene.kind}-{beat.step:03d}")
    return frames


def scene_markup(
    timeline: Timeline,
    context: FrameContext,
    video: VideoEncode,
    *,
    templates_dir: Path | None = None,
) -> Iterator[tuple[Scene, str]]:
    """Yield ``(scene, html)`` for the whole timeline without rasterizing anything."""
    for scene in timeline.scenes:
        yield scene, scene_html(scene, context, video, templates_dir=templates_dir)


# Check parameters that bound the measured value, and how the card states them.
_LIMIT_PARAMS = (("max_abs_error", "≤"), ("max", "≤"), ("min", "≥"))


def check_limits(checks: Any) -> dict[str, str]:
    """Each check's pass condition as shown beside its value, e.g. ``"≤ 1e-06"``.

    Without it a measured error of 0 reads like a score of zero.
    """
    out: dict[str, str] = {}
    for check in checks or ():
        for param, sign in _LIMIT_PARAMS:
            if param in check.params:
                value = check.params[param]
                shown = f"{value:g}" if isinstance(value, (int, float)) else str(value)
                out[check.id] = f"{sign} {shown}"
                break
    return out


def context_for(
    content_set_title: str,
    demo_title: str,
    timeline: Timeline,
    results: Any = None,
    demo_checks: Any = None,
    *,
    demo_number: int = 0,
    intro_slides: int = 0,
    event_total: int = 0,
) -> FrameContext:
    """Build a :class:`FrameContext` from a demo and its approved results."""
    limits = check_limits(demo_checks)
    checks = () if results is None else tuple(
        c.to_json() | ({"limit": limits[c.id]} if c.id in limits else {})
        for c in results.checks
    )
    return FrameContext(
        set_title=content_set_title,
        demo_title=demo_title,
        demo_id=timeline.demo_id,
        scene_count=len(timeline.scenes),
        results=checks,
        demo_number=demo_number,
        intro_slides=intro_slides,
        event_total=event_total,
    )
