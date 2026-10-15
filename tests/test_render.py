"""Render stage: document emitters, records, and the derived slide deck."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from conftest import make_content_set, write_demo

from demoforge.capture import approve_run, run_demo
from demoforge.discovery import load_content_set
from demoforge.model import RunBundle
from demoforge.render import render_all
from demoforge.render.document import Document, to_html, to_markdown
from demoforge.render.record import render_record
from demoforge.render.slides import marp_available, write_deck

WHEN = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)


# ---- document emitters -------------------------------------------------
def test_document_markdown_and_html():
    doc = Document()
    doc.h1("Title").p("hi").quote("a quote").code("x = 1", "python")
    doc.table(["a", "b"], [["1", "PASS"]]).ul(["one", "two"])

    md = to_markdown(doc)
    assert md.startswith("# Title")
    assert "> a quote" in md
    assert "```python\nx = 1\n```" in md
    assert "| a | b |" in md and "| 1 | PASS |" in md
    assert "- one" in md

    html = to_html(doc, title="T")
    assert "<title>T</title>" in html
    assert "<h1>Title</h1>" in html
    assert "<blockquote>" in html and "<pre><code>" in html
    assert '<span class="pass">PASS</span>' in html  # badge coloring


def test_html_escapes_content():
    doc = Document().p("<script>alert(1)</script>")
    assert "<script>" not in to_html(doc, title="t")
    assert "&lt;script&gt;" in to_html(doc, title="t")


def test_markdown_table_escapes_pipes_and_newlines():
    """A cell containing | or a newline must not break the table structure."""
    doc = Document().table(["check", "detail"], [["eq", "a | b\nsecond line"]])
    md = to_markdown(doc)
    table_lines = [ln for ln in md.splitlines() if ln.startswith("|")]
    assert len(table_lines) == 3  # header, separator, exactly one data row
    assert r"a \| b" in md          # pipe escaped, not a column break
    assert "a \\| b second line" in md  # newline collapsed to a space


def test_markdown_code_fence_survives_inner_backticks():
    """Embedded content with its own ``` fence gets a longer wrapping fence."""
    inner = "s = '```'  # a literal fence inside the artifact"
    md = to_markdown(Document().code(inner, "python"))
    assert "````python" in md       # 4 backticks > the 3-backtick run inside
    assert inner in md              # content preserved verbatim
    assert md.count("````") == 2    # exactly one open + one close fence


# ---- a synthetic approved content set (no runtime needed) --------------
def _set_with_approved(tmp_path):
    root = make_content_set(tmp_path / "set")
    write_demo(
        root / "demos", "01_synth",
        """
        id: synth
        title: Synthetic Demo
        order: 1
        runtime: none
        inputs:
          - input/seed.txt
        checks:
          - id: produced
            kind: file_exists
            pattern: result.txt
        """,
    )
    demo_dir = root / "demos" / "01_synth"
    (demo_dir / "input").mkdir()
    (demo_dir / "input" / "seed.txt").write_text("seed", encoding="utf-8")
    (demo_dir / "prompt.md").write_text("Produce result.txt from the seed.", encoding="utf-8")

    cs = load_content_set(root)
    demo = cs.demos()[0]

    def invoke(prompt, work):
        (work / "result.txt").write_text("the answer", encoding="utf-8")
        return [
            json.dumps({"type": "system", "model": "claude-test"}),
            json.dumps({"type": "assistant", "message": {"content": [
                {"type": "text", "text": "Writing the result."},
                {"type": "tool_use", "id": "t1", "name": "Write", "input": {"file_path": "result.txt"}},
            ]}}),
            json.dumps({"type": "result", "subtype": "success", "is_error": False}),
        ]

    r = run_demo(demo, cs, invoker=invoke, when=WHEN, git_commit="abc123")
    approve_run(cs, demo.id, run_id=r.run_id)
    return cs, demo


# ---- records -----------------------------------------------------------
def test_record_has_all_sections(tmp_path):
    cs, demo = _set_with_approved(tmp_path)
    bundle = RunBundle(cs.approved_dir_for(demo.id))
    paths = render_record(demo, bundle, tmp_path / "out")

    md = paths["md"].read_text(encoding="utf-8")
    assert md.startswith("# Synthetic Demo")
    assert "## The job" in md and "Produce result.txt from the seed." in md
    assert "## Inputs" in md and "seed.txt" in md
    assert "## What Claude did" in md and "Writing the result." in md
    assert "Wrote `result.txt`" in md
    assert "## Generated artifacts" in md and "the answer" in md
    assert "## Measurable results" in md and "produced" in md and "PASS" in md
    assert "## Reproducibility" in md and "git commit: abc123" in md

    html = paths["html"].read_text(encoding="utf-8")
    assert "<h1>Synthetic Demo</h1>" in html
    assert '<span class="pass">PASS</span>' in html


# ---- pipeline / slides -------------------------------------------------
def test_render_all_skips_unapproved(tmp_path):
    cs, demo = _set_with_approved(tmp_path)
    # A second enabled demo with no approved bundle.
    write_demo(cs.demos_dir, "02_todo", "id: todo\ntitle: Not Yet\norder: 2\nruntime: none")

    summary = render_all(cs)
    assert set(summary.records) == {"synth"}
    assert summary.skipped == ["todo"]
    assert summary.slides["deck"].exists()


def test_deck_structure(tmp_path):
    cs, _ = _set_with_approved(tmp_path)
    deck = write_deck(cs, tmp_path / "slides")
    text = deck.read_text(encoding="utf-8")
    assert "marp: true" in text
    assert "# Test Set" in text  # from the default fixture config title
    assert "## 1. Synthetic Demo" in text
    assert "produced" in text and "pass" in text
    assert "It demonstrates itself" in text  # finale


def test_render_demo_record_requires_approved_bundle(tmp_path):
    from demoforge.errors import DemoError
    from demoforge.render.pipeline import render_demo_record

    cs, _ = _set_with_approved(tmp_path)
    write_demo(cs.demos_dir, "02_todo", "id: todo\ntitle: Not Yet\norder: 2\nruntime: none")
    todo = next(d for d in cs.demos() if d.id == "todo")
    with pytest.raises(DemoError, match="no approved bundle"):
        render_demo_record(cs, todo, tmp_path / "out")


def test_render_all_unknown_only_errors(tmp_path):
    from demoforge.errors import DemoError

    cs, _ = _set_with_approved(tmp_path)
    with pytest.raises(DemoError, match="no enabled demo"):
        render_all(cs, only="does-not-exist")


def test_deck_notes_when_nothing_approved(content_set):
    cs = load_content_set(content_set)
    deck = write_deck(cs, content_set / "slides")
    assert "No approved demos yet" in deck.read_text(encoding="utf-8")


@pytest.mark.skipif(not marp_available(), reason="Marp CLI not available")
def test_marp_renders_html(tmp_path):
    cs, _ = _set_with_approved(tmp_path)
    summary = render_all(cs, slide_formats=("html",))
    assert "html" in summary.slides and summary.slides["html"].exists()
