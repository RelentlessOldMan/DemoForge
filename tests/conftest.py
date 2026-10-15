"""Shared test fixtures: builders for throwaway content sets."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

DEFAULT_TOML = textwrap.dedent(
    """
    [set]
    id = "test-set"
    title = "Test Set"
    subtitle = "fixtures"

    [narration]
    enabled = true
    provider = "piper"
    voice = "en_US-amy-medium"

    [runtimes]
    python = "python"
    """
).strip()


def write_demo(demos_dir: Path, folder: str, yaml_text: str) -> Path:
    """Create ``demos/<folder>/demo.yaml`` with the given YAML body."""
    d = demos_dir / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / "demo.yaml").write_text(textwrap.dedent(yaml_text).strip() + "\n", encoding="utf-8")
    return d


def make_content_set(root: Path, *, toml: str = DEFAULT_TOML) -> Path:
    """Materialize a content set at ``root`` and return it."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "demoforge.toml").write_text(toml + "\n", encoding="utf-8")
    (root / "demos").mkdir(exist_ok=True)
    return root


@pytest.fixture
def content_set(tmp_path: Path) -> Path:
    return make_content_set(tmp_path / "set")


REPO_ROOT = Path(__file__).resolve().parents[1]
CLAUDE_DEMO_KIT = REPO_ROOT / "examples" / "claude-demo-kit"


def octave_binary() -> Path | None:
    """The pinned octave-cli path from the real content set, if present on disk."""
    from demoforge.config import ContentSetConfig

    toml = CLAUDE_DEMO_KIT / "demoforge.toml"
    if not toml.exists():
        return None
    cfg = ContentSetConfig.load(toml)
    configured = cfg.runtimes.get("octave")
    if not configured:
        return None
    path = Path(configured)
    return path if path.exists() else None


OCTAVE = octave_binary()
requires_octave = pytest.mark.skipif(OCTAVE is None, reason="octave-cli not available")


def _module_available(name: str) -> bool:
    import importlib.util

    return importlib.util.find_spec(name) is not None


HAS_JINJA = _module_available("jinja2")
requires_jinja = pytest.mark.skipif(not HAS_JINJA, reason="Jinja2 not installed")


def _chromium_available() -> bool:
    if not _module_available("playwright"):
        return False
    from demoforge.render.frames import chromium_available

    return chromium_available()


HAS_CHROMIUM = _chromium_available()
requires_chromium = pytest.mark.skipif(
    not HAS_CHROMIUM, reason="Playwright/Chromium not available"
)


def ffmpeg_binary() -> Path | None:
    """ffmpeg from PATH, used by the video-assembly tests."""
    import shutil

    found = shutil.which("ffmpeg")
    return Path(found) if found else None


FFMPEG = ffmpeg_binary()
requires_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="ffmpeg not available")


def _kokoro_python():
    """An interpreter with Kokoro installed, if this machine has one."""
    from demoforge.render.narration import find_kokoro_python

    return find_kokoro_python()


KOKORO_PYTHON = _kokoro_python()
requires_kokoro = pytest.mark.skipif(
    KOKORO_PYTHON is None, reason="no interpreter with kokoro installed"
)
