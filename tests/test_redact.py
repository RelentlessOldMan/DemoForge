"""Display-time path rewriting: every spelling of a folder, and nothing else."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from demoforge.discovery import load_content_set
from demoforge.model import RunBundle
from demoforge.redact import PathRewriter

REPO = Path(__file__).resolve().parents[1]
KIT = REPO / "examples" / "claude-demo-kit"

RW = PathRewriter({"C:\\Playground": "G:\\Willikers"})


@pytest.mark.parametrize(
    "before, after",
    [
        ("cd C:\\Playground\\DemoForge\\x", "cd G:\\Willikers\\DemoForge\\x"),
        ('cd "C:/Playground/DemoForge/runs/working"', 'cd "G:/Willikers/DemoForge/runs/working"'),
        ("open('C:\\\\Playground\\\\a.pdf')", "open('G:\\\\Willikers\\\\a.pdf')"),
        ("ls /c/Playground/DemoForge", "ls /g/Willikers/DemoForge"),
        ("c:\\playground\\x", "G:\\Willikers\\x"),  # Windows paths ignore case
        ("C:\\Playground", "G:\\Willikers"),  # the folder itself
    ],
)
def test_rewrites_every_spelling_keeping_its_separator(before, after):
    assert RW(before) == after


@pytest.mark.parametrize(
    "text",
    [
        "C:\\PlaygroundOther\\x",  # a different folder sharing the prefix
        "D:\\Playground\\x",  # another drive
        "C:\\Users\\someone\\Playground\\x",  # not at the root
        "the playground is open",
    ],
)
def test_leaves_other_paths_alone(text):
    assert RW(text) == text


def test_trailing_separators_in_the_rule_do_not_matter():
    assert PathRewriter({"C:\\Playground\\": "G:\\Willikers\\"})("C:/Playground/a") == "G:/Willikers/a"


def test_apply_walks_json_and_identity_has_no_effect():
    obj = {"command": "cd C:/Playground/x", "n": 3, "list": ["C:\\Playground\\y", None]}
    assert RW.apply(obj) == {"command": "cd G:/Willikers/x", "n": 3, "list": ["G:\\Willikers\\y", None]}
    assert PathRewriter().apply(obj) is obj
    assert not PathRewriter()


def test_display_bundle_rewrites_reads_but_never_the_files(tmp_path):
    root = tmp_path / "approved" / "demo"
    root.mkdir(parents=True)
    line = {"seq": 0, "t": 0.0, "type": "command", "command": "cd C:/Playground/w"}
    raw = json.dumps(line) + "\n"
    (root / "events.jsonl").write_text(raw, encoding="utf-8")
    (root / "prompt.md").write_text("Work in C:\\Playground\\w.", encoding="utf-8")

    shown = RunBundle(root, rewrite=RW.apply)
    assert shown.read_events()[0].data["command"] == "cd G:/Willikers/w"
    assert shown.read_text(shown.prompt_path) == "Work in G:\\Willikers\\w."
    assert RunBundle(root).read_events()[0].data["command"] == "cd C:/Playground/w"
    assert (root / "events.jsonl").read_text(encoding="utf-8") == raw


def test_claude_demo_kit_shows_no_local_repo_path():
    cs = load_content_set(KIT)
    assert ("C:\\Playground", "G:\\Willikers") in cs.config.display_paths
    # The home folder of whoever runs the tests, in any spelling.
    home = re.compile(r"users[\\/]+" + re.escape(Path.home().name.lower()) + r"(?![\w.-])")
    leaked = []
    for demo in cs.demos(enabled_only=True):
        bundle = cs.display_bundle(demo.id)
        if not bundle.exists():
            continue
        for ev in bundle.read_events():
            text = json.dumps(ev.data, ensure_ascii=False).lower()
            if "playground" in text or home.search(text):
                leaked.append((demo.id, ev.seq))
    assert leaked == []


def test_rules_apply_in_one_pass_and_never_chain():
    rw = PathRewriter({r"C:\Playground": r"G:\Willikers", r"G:\Willikers": r"X:\other"})
    assert rw(r"C:\Playground\a") == r"G:\Willikers\a"
    assert rw(r"G:\Willikers\b") == r"X:\other\b"


def test_destination_without_drive_gets_no_stray_separator():
    assert PathRewriter({r"C:\Playground": "demo"})(r"C:\Playground\a") == r"demo\a"
    assert PathRewriter({r"C:\Playground": "/srv"})("C:/Playground/a") == "/srv/a"


def test_wsl_spelling_is_rewritten():
    rw = PathRewriter({r"C:\Playground": r"G:\Willikers"})
    assert rw("/mnt/c/Playground/a") == "/mnt/g/Willikers/a"
    assert rw("/c/Playground/a") == "/g/Willikers/a"
