"""Frame rendering: scene templates, the content-addressed cache, and Chromium."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from conftest import requires_chromium, requires_jinja

from demoforge.errors import DemoForgeError
from demoforge.model import CheckResult, Event, Results
from demoforge.render.config import VideoEncode, load_settings
from demoforge.render.frames import (
    FrameContext,
    context_for,
    format_number,
    frame_key,
    render_frames,
    scene_html,
    scene_markup,
)
from demoforge.render.timeline import build_timeline

pytestmark = requires_jinja

VIDEO = VideoEncode()


def _events() -> list[Event]:
    return [
        Event(seq=0, t=0.0, type="prompt", data={"text": "Make it fast."}),
        Event(seq=1, t=2.0, type="assistant_text", data={"text": "Looking at it."}),
        Event(seq=2, t=3.0, type="file_read", data={"tool": "Read", "path": "C:\\w\\a.m"}),
        Event(seq=3, t=4.0, type="file_search", data={"tool": "Grep", "query": "kalman"}),
        Event(seq=4, t=5.0, type="file_write", data={"tool": "Write", "path": "/w/fast.m"}),
        Event(seq=5, t=6.0, type="file_edit", data={"tool": "Edit", "path": "/w/fast.m"}),
        Event(seq=6, t=6.5, type="command", data={"tool": "Bash", "command": "octave b.m"}),
        Event(seq=7, t=41.0, type="command_output", data={"output": "speedup 47.3x\nok\n"}),
        Event(seq=8, t=42.0, type="test_result", data={"passed": 8, "failed": 0}),
        Event(seq=9, t=43.0, type="artifact", data={"path": "/w/plot.png"}),
        Event(seq=10, t=44.0, type="tool_call", data={"tool": "WebFetch"}),
        Event(seq=11, t=44.5, type="user_message", data={"text": "Is that measured?"}),
        Event(seq=12, t=45.0, type="completion", data={"subtype": "success", "num_turns": 9}),
    ]


def _timeline():
    st = load_settings()
    return build_timeline("demo", _events(), scenes=st.scenes, timing=st.timing, clocked=True)


def _context(timeline) -> FrameContext:
    results = Results(checks=[
        CheckResult(id="speedup", kind="threshold", passed=True, value=46.96262994695506),
        CheckResult(id="n_vectors", kind="metric", passed=None, value=1500),
    ])
    return context_for("TestKit", "A Demo", timeline, results)


# ---- every configured scene actually has a working template -----------
def test_every_scene_kind_in_the_config_renders():
    tl = _timeline()
    kinds = {s.kind for s in tl.scenes}
    # The fixture is built to touch every style in the committed scenes.yaml.
    assert kinds == {
        "PromptCard", "FollowUp", "NarratedText", "FileGlance", "DiffReveal",
        "TerminalRun", "ResultBadge", "ArtifactReveal", "ToolCard", "ChapterEnd",
    }
    for _scene, html in scene_markup(tl, _context(tl), VIDEO):
        assert html.lstrip().startswith("<!doctype html>")
        assert "</html>" in html


def test_a_missing_template_is_reported_with_its_name(tmp_path):
    tl = _timeline()
    with pytest.raises(DemoForgeError, match="prompt_card.html.j2"):
        scene_html(tl.scenes[0], _context(tl), VIDEO, templates_dir=tmp_path)


def test_a_missing_templates_dir_is_reported(tmp_path):
    tl = _timeline()
    with pytest.raises(DemoForgeError, match="no scene templates"):
        scene_html(tl.scenes[0], _context(tl), VIDEO, templates_dir=tmp_path / "gone")


# ---- traceability on screen -------------------------------------------
def test_each_frame_names_the_events_it_was_built_from():
    tl = _timeline()
    for scene, html in scene_markup(tl, _context(tl), VIDEO):
        assert "captured events" in html
        for seq in scene.event_seqs:
            assert str(seq) in html


def test_a_terminal_frame_shows_the_real_recorded_output():
    tl = _timeline()
    term = next(s for s in tl.scenes if s.kind == "TerminalRun")
    html = scene_html(term, _context(tl), VIDEO)
    assert "octave b.m" in html
    assert "speedup 47.3x" in html


def test_truncated_output_says_how_much_it_left_off():
    st = load_settings()
    raw = "\n".join(f"line {i}" for i in range(st.scenes.limits.terminal_max_lines + 7))
    tl = build_timeline(
        "demo",
        [
            Event(seq=0, t=0.0, type="command", data={"command": "ls"}),
            Event(seq=1, t=1.0, type="command_output", data={"output": raw}),
        ],
        scenes=st.scenes,
        timing=st.timing,
    )
    html = scene_html(tl.scenes[0], _context(tl), VIDEO)
    # The one-line command takes one of the card's lines, so 8 are left off.
    assert "8 further lines" in html


def test_a_compressed_scene_is_labelled_and_an_honest_one_is_not():
    tl = _timeline()
    compressed = next(s for s in tl.scenes if s.compressed)
    assert "time-compressed" in scene_html(compressed, _context(tl), VIDEO)

    plain = next(s for s in tl.scenes if not s.compressed)
    assert "time-compressed" not in scene_html(plain, _context(tl), VIDEO)


def test_the_results_panel_shows_measured_values_from_the_bundle():
    tl = _timeline()
    end = next(s for s in tl.scenes if s.kind == "ChapterEnd")
    html = scene_html(end, _context(tl), VIDEO)
    assert "VERIFIED" in html and "speedup" in html
    assert "46.9626" in html          # formatted, not raw float noise
    assert "46.96262994695506" not in html


def test_a_failing_run_is_not_dressed_up_as_a_pass():
    tl = _timeline()
    end = next(s for s in tl.scenes if s.kind == "ChapterEnd")
    failing = Results(checks=[CheckResult(id="equivalence", kind="numeric_tolerance", passed=False, value=3.2)])
    html = scene_html(end, context_for("Kit", "A Demo", tl, failing), VIDEO)
    assert "FAILED" in html and "VERIFIED" not in html


# ---- number formatting ------------------------------------------------
@pytest.mark.parametrize(
    "value,expected",
    [
        (1500, "1,500"),
        (46.96262994695506, "46.9626"),
        (0.0, "0"),
        (1.5, "1.5"),
        (-2.25, "-2.25"),
        (1e-9, "1.0000e-09"),
        (None, ""),
        ("PASS", "PASS"),
        (True, "True"),
    ],
)
def test_measured_values_read_as_engineering_numbers(value, expected):
    assert format_number(value) == expected


# ---- cache ------------------------------------------------------------
class _FakeRenderer:
    """Counts renders and writes a stand-in file, so cache behaviour is observable."""

    def __init__(self) -> None:
        self.calls: list[Path] = []

    def render(self, html: str, out_path: Path) -> None:
        self.calls.append(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"\x89PNG\r\n\x1a\n")


def test_frames_are_rendered_once_and_then_reused(tmp_path):
    tl = _timeline()
    ctx = _context(tl)
    r = _FakeRenderer()

    first = render_frames(tl, ctx, out_dir=tmp_path, video=VIDEO, renderer=r)
    assert len(first) == len(tl.scenes)
    assert len(r.calls) == len(tl.scenes)
    assert all(f.cached is False for f in first)

    second = render_frames(tl, ctx, out_dir=tmp_path, video=VIDEO, renderer=_FakeRenderer())
    assert all(f.cached is True for f in second)
    assert [f.path for f in second] == [f.path for f in first]


def test_frames_are_ordered_and_carry_their_durations(tmp_path):
    tl = _timeline()
    frames = render_frames(tl, _context(tl), out_dir=tmp_path, video=VIDEO, renderer=_FakeRenderer())
    assert [f.scene_index for f in frames] == list(range(len(tl.scenes)))
    assert [f.duration for f in frames] == [s.duration for s in tl.scenes]
    assert [f.path.name[:4] for f in frames] == [f"{i:04d}" for i in range(len(tl.scenes))]


def test_the_frame_key_folds_in_markup_and_viewport():
    tl = _timeline()
    html = scene_html(tl.scenes[0], _context(tl), VIDEO)
    assert frame_key(html, VIDEO) == frame_key(html, VIDEO)
    assert frame_key(html, VIDEO) != frame_key(html + " ", VIDEO)
    assert frame_key(html, VIDEO) != frame_key(html, VideoEncode(width=1280, height=720))


def test_editing_a_template_invalidates_only_its_frames(tmp_path):
    """The cache key is the rendered HTML, so a template edit re-renders exactly its scenes."""
    tl = _timeline()
    ctx = _context(tl)
    templates = tmp_path / "templates"
    templates.mkdir()
    src = Path(__file__).resolve().parents[1] / "templates" / "scenes"
    for f in src.glob("*.j2"):
        (templates / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")

    out = tmp_path / "frames"
    before = {
        s.index: frame_key(h, VIDEO)
        for s, h in scene_markup(tl, ctx, VIDEO, templates_dir=templates)
    }
    tool = templates / "tool_card.html.j2"
    tool.write_text(tool.read_text(encoding="utf-8").replace("{{ label }}", "{{ label }}!"), encoding="utf-8")
    after = {
        s.index: frame_key(h, VIDEO)
        for s, h in scene_markup(tl, ctx, VIDEO, templates_dir=templates)
    }

    changed = {i for i in before if before[i] != after[i]}
    tool_scenes = {s.index for s in tl.scenes if s.kind == "ToolCard"}
    assert changed == tool_scenes
    assert not out.exists()  # nothing rasterized by this test


# ---- the real browser -------------------------------------------------
@requires_chromium
def test_chromium_writes_a_png_at_the_configured_viewport(tmp_path):
    from demoforge.render.frames import ChromiumRenderer

    tl = _timeline()
    video = VideoEncode(width=1280, height=720)
    with ChromiumRenderer(video) as renderer:
        frames = render_frames(
            tl, _context(tl), out_dir=tmp_path, video=video, renderer=renderer
        )
    assert len(frames) == len(tl.scenes)
    for f in frames:
        raw = f.path.read_bytes()
        assert raw[:8] == b"\x89PNG\r\n\x1a\n", f.path.name
        width, height = struct.unpack(">II", raw[16:24])
        assert (width, height) == (1280, 720)


@requires_chromium
def test_renderer_refuses_use_outside_its_context_manager(tmp_path):
    from demoforge.render.frames import ChromiumRenderer

    renderer = ChromiumRenderer(VIDEO)
    with pytest.raises(DemoForgeError, match="context manager"):
        renderer.render("<html></html>", tmp_path / "x.png")


# ---- bundled fonts ----------------------------------------------------
def test_the_committed_fonts_are_present_with_their_licences():
    from demoforge.render.frames import BUNDLED_FONTS, FONTS_DIR

    for _family, name, _weight in BUNDLED_FONTS:
        assert (FONTS_DIR / name).is_file(), name
    # The OFL requires the licence to travel with the files.
    assert (FONTS_DIR / "OFL-Inter.txt").is_file()
    assert (FONTS_DIR / "OFL-JetBrainsMono.txt").is_file()


def test_fonts_are_inlined_so_markup_is_machine_independent():
    from demoforge.render.frames import font_face_css

    tl = _timeline()
    html = scene_html(tl.scenes[0], _context(tl), VIDEO)
    assert "@font-face" in html
    assert "data:font/woff2;base64," in html
    # A file:// URL here would bake this machine's paths into every frame's
    # cache key, so two machines would disagree about identical frames.
    assert "file://" not in html
    assert font_face_css().count("@font-face") == 4


def test_the_scene_stylesheet_prefers_the_bundled_families():
    tl = _timeline()
    html = scene_html(tl.scenes[0], _context(tl), VIDEO)
    assert "'DemoForge Sans'" in html and "'DemoForge Mono'" in html
    # ...while still naming system fallbacks for a build without the files.
    assert "monospace" in html and "sans-serif" in html


def test_absent_fonts_degrade_instead_of_failing(tmp_path):
    from demoforge.render.frames import font_face_css

    assert font_face_css(tmp_path) == ""
    tl = _timeline()
    html = scene_html(tl.scenes[0], _context(tl), VIDEO, fonts_dir=tmp_path)
    assert "@font-face" not in html
    assert "DemoForge Mono" in html  # the stack still falls through


def test_swapping_a_font_reraises_every_frame(tmp_path):
    """Font files feed the markup, so changing one must invalidate the frame cache."""
    from demoforge.render.frames import BUNDLED_FONTS, FONTS_DIR

    for _family, name, _weight in BUNDLED_FONTS:
        (tmp_path / name).write_bytes((FONTS_DIR / name).read_bytes())

    tl = _timeline()
    ctx = _context(tl)
    before = frame_key(scene_html(tl.scenes[0], ctx, VIDEO, fonts_dir=tmp_path), VIDEO)

    swapped = tmp_path / BUNDLED_FONTS[0][1]
    swapped.write_bytes(swapped.read_bytes() + b"\0")
    after = frame_key(scene_html(tl.scenes[0], ctx, VIDEO, fonts_dir=tmp_path), VIDEO)
    assert before != after
