"""Pre-capture environment checks.

The point of these is that ``run`` spends real agent time and cannot be
recomputed, so a knowably-broken environment must be caught before the agent is
invoked rather than discovered in the verdict afterwards.
"""

from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest

from demoforge.capture.preflight import (
    capture_env,
    missing_requirements,
    preflight,
    resolve_tool,
)
from demoforge.config import CaptureConfig, ContentSetConfig
from demoforge.errors import ConfigError, DemoError
from demoforge.model import Demo
from tests.conftest import make_content_set, write_demo


def _demo(tmp_path: Path, requires: tuple[str, ...] = ()) -> Demo:
    return Demo(id="d", title="D", order=1, dir=tmp_path, requires=requires)


# ---- capture_env ------------------------------------------------------
def test_prepends_pinned_dirs_in_front_of_inherited_path(tmp_path: Path) -> None:
    pinned = tmp_path / "bin"
    pinned.mkdir()
    env = capture_env(CaptureConfig(path_prepend=(str(pinned),)), base={"PATH": "/existing"})
    assert env["PATH"].split(os.pathsep)[0] == str(pinned)
    assert "/existing" in env["PATH"]


def test_pinned_dir_wins_over_a_same_named_tool_already_on_path(tmp_path: Path) -> None:
    """Order matters: a pin is how you *override*, not merely supplement."""
    old, new = tmp_path / "old", tmp_path / "new"
    for d in (old, new):
        d.mkdir()
        (d / "tool.bat").write_text("", encoding="utf-8")
    env = capture_env(CaptureConfig(path_prepend=(str(new),)), base={"PATH": str(old)})
    found = resolve_tool("tool", env)
    # Compare case-insensitively: on Windows shutil.which appends the PATHEXT
    # entry as spelled there, so a .bat resolves as "tool.BAT".
    assert found is not None
    assert Path(found).parent == new
    assert Path(found).name.lower() == "tool.bat"


def test_nonexistent_pinned_dirs_are_dropped_not_fatal(tmp_path: Path) -> None:
    """A content set is shared across machines; a path meaningful on one of them
    must not break capture on the others."""
    env = capture_env(
        CaptureConfig(path_prepend=(str(tmp_path / "nope"),)), base={"PATH": "/existing"}
    )
    assert env["PATH"] == "/existing"


def test_no_pins_leaves_path_untouched() -> None:
    assert capture_env(CaptureConfig(), base={"PATH": "/existing"})["PATH"] == "/existing"


def test_empty_inherited_path_does_not_produce_a_leading_separator(tmp_path: Path) -> None:
    pinned = tmp_path / "bin"
    pinned.mkdir()
    env = capture_env(CaptureConfig(path_prepend=(str(pinned),)), base={"PATH": ""})
    assert env["PATH"] == str(pinned)


def test_capture_env_defaults_to_the_real_environment() -> None:
    assert capture_env(CaptureConfig()).get("PATH") == os.environ.get("PATH")


def test_capture_env_does_not_mutate_the_base_mapping(tmp_path: Path) -> None:
    pinned = tmp_path / "bin"
    pinned.mkdir()
    base = {"PATH": "/existing"}
    capture_env(CaptureConfig(path_prepend=(str(pinned),)), base=base)
    assert base == {"PATH": "/existing"}


# ---- billing ----------------------------------------------------------
def test_api_keys_are_stripped_so_the_agent_uses_the_cli_login() -> None:
    base = {"PATH": "/x", "ANTHROPIC_API_KEY": "sk-test", "ANTHROPIC_AUTH_TOKEN": "t"}
    env = capture_env(CaptureConfig(), base=base)
    assert "ANTHROPIC_API_KEY" not in env
    assert "ANTHROPIC_AUTH_TOKEN" not in env
    assert env["PATH"] == "/x"
    assert base["ANTHROPIC_API_KEY"] == "sk-test"  # only the agent's copy changes


def test_auth_source_is_recorded_and_api_key_billing_is_flagged() -> None:
    from demoforge.capture.run import _auth_extra, api_key_billed

    init = {"type": "system", "subtype": "init", "apiKeySource": "ANTHROPIC_API_KEY"}
    assert _auth_extra([init]) == {"auth_source": "ANTHROPIC_API_KEY"}
    assert _auth_extra([{"type": "system"}]) == {}
    assert api_key_billed("ANTHROPIC_API_KEY")
    assert not api_key_billed("none")
    assert not api_key_billed(None)


# ---- requirement resolution -------------------------------------------
def test_tool_is_resolved_against_the_capture_path_not_demoforges(tmp_path: Path) -> None:
    """The question is always what the *agent* can run, never what we can."""
    pinned = tmp_path / "bin"
    pinned.mkdir()
    (pinned / "rasterize.bat").write_text("", encoding="utf-8")

    demo = _demo(tmp_path, requires=("rasterize",))
    assert missing_requirements(demo, {"PATH": ""}) == ("rasterize",)
    assert missing_requirements(demo, capture_env(
        CaptureConfig(path_prepend=(str(pinned),)), base={"PATH": ""}
    )) == ()


def test_a_demo_with_no_requirements_always_passes(tmp_path: Path) -> None:
    assert preflight(_demo(tmp_path), {"PATH": ""}).ok


def test_every_missing_tool_is_reported_not_just_the_first(tmp_path: Path) -> None:
    demo = _demo(tmp_path, requires=("alpha", "beta"))
    assert set(preflight(demo, {"PATH": ""}).missing) == {"alpha", "beta"}


def test_failure_message_names_the_tool_the_demo_and_the_fix(tmp_path: Path) -> None:
    msg = preflight(_demo(tmp_path, requires=("pdftoppm",)), {"PATH": ""}).message()
    assert "pdftoppm" in msg and "'d'" in msg
    assert "path_prepend" in msg          # how to point at an existing install
    assert "NEW shell" in msg             # the inherited-PATH trap that caused this


# ---- demo.yaml schema -------------------------------------------------
def test_requires_is_parsed_from_demo_yaml(tmp_path: Path) -> None:
    from demoforge.discovery import discover_demos

    demos = tmp_path / "demos"
    write_demo(demos, "01_x", """
        id: x
        title: X
        order: 1
        requires:
          - pdftoppm
    """)
    assert discover_demos(demos)[0].requires == ("pdftoppm",)


def test_requires_defaults_to_empty(tmp_path: Path) -> None:
    from demoforge.discovery import discover_demos

    demos = tmp_path / "demos"
    write_demo(demos, "01_x", "id: x\ntitle: X\norder: 1")
    assert discover_demos(demos)[0].requires == ()


def test_a_bare_string_requires_is_rejected_rather_than_split_into_letters(
    tmp_path: Path,
) -> None:
    from demoforge.discovery import discover_demos

    demos = tmp_path / "demos"
    write_demo(demos, "01_x", """
        id: x
        title: X
        order: 1
        requires: pdftoppm
    """)
    with pytest.raises(DemoError, match="list of executable names"):
        discover_demos(demos)


# ---- demoforge.toml ---------------------------------------------------
def test_capture_path_prepend_is_parsed(tmp_path: Path) -> None:
    root = make_content_set(tmp_path / "set", toml=textwrap.dedent("""
        [set]
        id = "s"
        title = "S"

        [capture]
        path_prepend = ["/one", "/two"]
    """).strip())
    cfg = ContentSetConfig.load(root / "demoforge.toml")
    assert cfg.capture.path_prepend == ("/one", "/two")


def test_capture_defaults_to_no_pins(tmp_path: Path) -> None:
    root = make_content_set(tmp_path / "set")
    assert ContentSetConfig.load(root / "demoforge.toml").capture.path_prepend == ()


def test_a_bare_string_path_prepend_is_rejected(tmp_path: Path) -> None:
    """Silently iterating a string would pin one directory per character."""
    root = make_content_set(tmp_path / "set", toml=textwrap.dedent("""
        [set]
        id = "s"
        title = "S"

        [capture]
        path_prepend = "/one"
    """).strip())
    with pytest.raises(ConfigError, match="list of directories"):
        ContentSetConfig.load(root / "demoforge.toml")


# ---- the real content set ---------------------------------------------
def test_the_pdf_demos_declare_the_rasterizer_they_need() -> None:
    """Demos 7 and 10 hand the agent a PDF; Claude's Read tool rasterizes with
    pdftoppm. Without the declaration those captures fail for an environmental
    reason that is indistinguishable, in the verdict, from a design failure."""
    from demoforge.discovery import load_content_set
    from tests.conftest import CLAUDE_DEMO_KIT

    cs = load_content_set(CLAUDE_DEMO_KIT)
    by_id = {d.id: d for d in cs.demos()}
    for demo_id in ("spec-implementation", "autonomous-investigation"):
        demo = by_id[demo_id]
        assert any(i.lower().endswith(".pdf") for i in demo.inputs), demo_id
        assert "pdftoppm" in demo.requires, demo_id

    # ...and no demo without a PDF carries the requirement for no reason.
    for demo in cs.demos():
        if "pdftoppm" in demo.requires:
            assert any(i.lower().endswith(".pdf") for i in demo.inputs), demo.id
