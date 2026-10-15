"""Content-set config (demoforge.toml) parsing."""

from __future__ import annotations

import textwrap

import pytest

from demoforge.config import ContentSetConfig
from demoforge.errors import ConfigError


def _write(tmp_path, text):
    p = tmp_path / "demoforge.toml"
    p.write_text(textwrap.dedent(text).strip() + "\n", encoding="utf-8")
    return p


def test_full_config(tmp_path):
    p = _write(
        tmp_path,
        """
        [set]
        id = "kit"
        title = "Kit"
        subtitle = "sub"
        description = "d"

        [presentation]
        intro = true
        outro = false

        [narration]
        enabled = false
        provider = "elevenlabs"
        voice = "v"

        [runtimes]
        octave = "C:/octave.exe"
        python = "python"
        """,
    )
    cfg = ContentSetConfig.load(p)
    assert cfg.id == "kit" and cfg.title == "Kit" and cfg.subtitle == "sub"
    assert cfg.presentation.intro is True and cfg.presentation.outro is False
    assert cfg.narration.enabled is False and cfg.narration.provider == "elevenlabs"
    assert cfg.runtimes == {"octave": "C:/octave.exe", "python": "python"}


def test_defaults_when_tables_absent(tmp_path):
    p = _write(tmp_path, '[set]\nid = "min"')
    cfg = ContentSetConfig.load(p)
    assert cfg.title == "min"  # falls back to id
    assert cfg.presentation.intro is True and cfg.presentation.outro is True
    assert cfg.narration.provider == "piper"
    assert cfg.runtimes == {}


def test_missing_set_table(tmp_path):
    p = _write(tmp_path, '[narration]\nenabled = true')
    with pytest.raises(ConfigError, match=r"\[set\] table"):
        ContentSetConfig.load(p)


def test_invalid_toml(tmp_path):
    p = _write(tmp_path, "this is = = not toml")
    with pytest.raises(ConfigError, match="not valid TOML"):
        ContentSetConfig.load(p)
