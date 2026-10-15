"""Content-set loading and demo discovery."""

from __future__ import annotations

import pytest

from conftest import make_content_set, write_demo

from demoforge.config import ContentSetConfig
from demoforge.discovery import discover_demos, load_content_set
from demoforge.errors import ConfigError, ContentSetError, DemoError


def test_load_content_set_and_paths(content_set):
    cs = load_content_set(content_set)
    assert isinstance(cs.config, ContentSetConfig)
    assert cs.config.id == "test-set"
    assert cs.demos_dir == content_set / "demos"
    assert cs.run_dir_for("d", "r1") == content_set / "runs" / "d" / "r1"
    assert cs.approved_dir_for("d") == content_set / "approved" / "d"


def test_missing_config_errors(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(ConfigError, match="no demoforge.toml"):
        load_content_set(tmp_path / "empty")


def test_not_a_directory_errors(tmp_path):
    with pytest.raises(ContentSetError):
        load_content_set(tmp_path / "does-not-exist")


def test_discovery_orders_by_order_then_id(content_set):
    demos_dir = content_set / "demos"
    write_demo(demos_dir, "z_first", "id: a\ntitle: A\norder: 1")
    write_demo(demos_dir, "a_third", "id: c\ntitle: C\norder: 3")
    write_demo(demos_dir, "m_second", "id: b\ntitle: B\norder: 2")
    demos = discover_demos(demos_dir)
    assert [d.id for d in demos] == ["a", "b", "c"]


def test_discovery_ignores_folders_without_manifest(content_set):
    demos_dir = content_set / "demos"
    write_demo(demos_dir, "real", "id: a\ntitle: A")
    (demos_dir / "not_a_demo").mkdir()
    (demos_dir / "not_a_demo" / "notes.txt").write_text("hi", encoding="utf-8")
    demos = discover_demos(demos_dir)
    assert [d.id for d in demos] == ["a"]


def test_missing_demos_dir_is_empty(content_set):
    # Remove the demos dir entirely.
    (content_set / "demos").rmdir()
    assert discover_demos(content_set / "demos") == []


def test_duplicate_demo_ids_rejected(content_set):
    demos_dir = content_set / "demos"
    write_demo(demos_dir, "one", "id: dup\ntitle: One")
    write_demo(demos_dir, "two", "id: dup\ntitle: Two")
    with pytest.raises(DemoError, match="duplicate demo id"):
        discover_demos(demos_dir)


def test_enabled_only_filter(content_set):
    demos_dir = content_set / "demos"
    # NB: ids are quoted — bare on/off/yes/no are YAML 1.1 booleans.
    write_demo(demos_dir, "a", 'id: "alpha"\ntitle: Alpha\nenabled: true')
    write_demo(demos_dir, "b", 'id: "beta"\ntitle: Beta\nenabled: false')
    cs = load_content_set(content_set)
    assert [d.id for d in cs.demos()] == ["alpha", "beta"]
    assert [d.id for d in cs.demos(enabled_only=True)] == ["alpha"]


def test_malformed_yaml_reports_path(content_set):
    demos_dir = content_set / "demos"
    d = demos_dir / "broken"
    d.mkdir(parents=True)
    (d / "demo.yaml").write_text("id: x\ntitle: [unclosed\n", encoding="utf-8")
    with pytest.raises(DemoError):
        discover_demos(demos_dir)
