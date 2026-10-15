"""Staleness: an approved bundle that no longer matches its demo must be reported.

A capture is only an answer to the prompt it was given. Editing ``prompt.md`` or an
input after approving leaves the old run in place — faithful to itself, but no longer
the demo. These tests pin that it is detected and surfaced, and (just as important)
that an untouched demo is never falsely flagged.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from demoforge.build import build
from demoforge.capture import approve_run, run_demo
from demoforge.discovery import load_content_set
from demoforge.model import RunBundle, RunMetadata
from demoforge.staleness import (
    approved_staleness,
    bundle_staleness,
    input_hashes,
    prompt_hash,
    stale_approved,
)

WHEN = datetime(2026, 10, 5, 9, 0, 0, tzinfo=timezone.utc)


def _set(tmp_path: Path):
    """A minimal content set: one `none`-runtime demo with two inputs."""
    root = tmp_path / "set"
    demo = root / "demos" / "synth"
    (demo / "input" / "nested").mkdir(parents=True)
    (demo / "input" / "seed.txt").write_text("seed\n", encoding="utf-8")
    (demo / "input" / "nested" / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (demo / "prompt.md").write_text("Produce result.out\n", encoding="utf-8")
    (demo / "demo.yaml").write_text(
        "id: synth\ntitle: Synth\nruntime: none\n"
        "inputs:\n  - input/seed.txt\n  - input/nested/data.csv\n"
        "checks:\n  - id: produced\n    kind: file_exists\n    pattern: result.out\n",
        encoding="utf-8",
    )
    (root / "demoforge.toml").write_text('[set]\nid = "synth-set"\n', encoding="utf-8")
    return load_content_set(root)


def _invoker(prompt, work_dir):
    (work_dir / "result.out").write_text("done\n", encoding="utf-8")
    return [
        json.dumps({"type": "system", "subtype": "init", "model": "claude-test"}),
        json.dumps({"type": "result", "subtype": "success", "is_error": False}),
    ]


def _approved_set(tmp_path):
    """A content set with one demo captured and approved, fresh by construction."""
    cs = _set(tmp_path)
    demo = cs.demos()[0]
    result = run_demo(demo, cs, invoker=_invoker, when=WHEN, git_commit="cafe")
    assert result.passed
    approve_run(cs, demo.id, run_id=result.run_id)
    return cs, demo


# ---- the happy path: do not cry wolf ----------------------------------
def test_untouched_demo_is_not_stale(tmp_path):
    cs, demo = _approved_set(tmp_path)
    st = approved_staleness(cs, demo)
    assert st is not None
    assert st.is_stale is False
    assert st.unrecorded is False
    assert st.reasons() == []
    assert stale_approved(cs) == []


def test_unapproved_demo_has_no_staleness(tmp_path):
    cs = _set(tmp_path)
    assert approved_staleness(cs, cs.demos()[0]) is None


# ---- detection --------------------------------------------------------
def test_edited_prompt_makes_the_approved_bundle_stale(tmp_path):
    cs, demo = _approved_set(tmp_path)
    demo.prompt_path.write_text("Produce result.out, but differently\n", encoding="utf-8")

    st = approved_staleness(cs, demo)
    assert st.is_stale is True
    assert st.prompt_changed is True
    assert st.inputs_changed == ()
    assert "prompt.md changed" in st.summary()
    assert [s.demo_id for s in stale_approved(cs)] == ["synth"]


def test_edited_input_makes_the_approved_bundle_stale(tmp_path):
    cs, demo = _approved_set(tmp_path)
    (demo.dir / "input" / "nested" / "data.csv").write_text("a,b\n9,9\n", encoding="utf-8")

    st = approved_staleness(cs, demo)
    assert st.is_stale is True
    assert st.prompt_changed is False
    # Reported by staged relpath, so nested inputs are identifiable.
    assert st.inputs_changed == ("nested/data.csv",)
    assert "nested/data.csv" in st.summary()


def test_added_and_removed_inputs_are_reported(tmp_path):
    cs, demo = _approved_set(tmp_path)
    (demo.dir / "input" / "seed.txt").unlink()
    (demo.dir / "input" / "extra.txt").write_text("new\n", encoding="utf-8")
    (demo.dir / "demo.yaml").write_text(
        "id: synth\ntitle: Synth\nruntime: none\n"
        "inputs:\n  - input/nested/data.csv\n  - input/extra.txt\n"
        "checks:\n  - id: produced\n    kind: file_exists\n    pattern: result.out\n",
        encoding="utf-8",
    )
    demo = cs.demos()[0]  # re-read the manifest

    st = approved_staleness(cs, demo)
    assert st.inputs_added == ("extra.txt",)
    assert st.inputs_removed == ("seed.txt",)
    assert st.inputs_changed == ()
    assert st.is_stale is True


def test_bundle_without_recorded_hashes_is_unknown_not_stale(tmp_path):
    """Pre-hash bundles must not be flagged — we do not assert what we cannot know."""
    cs, demo = _approved_set(tmp_path)
    bundle = RunBundle(cs.approved_dir_for(demo.id))
    bundle.write_metadata(RunMetadata(demo_id=demo.id, created="2026-01-01T00:00:00Z"))

    st = bundle_staleness(demo, bundle)
    assert st.unrecorded is True
    assert st.is_stale is False
    assert "unknown" in st.summary()
    assert stale_approved(cs) == []


# ---- the hashes capture records are the ones staleness compares -------
def test_capture_records_the_hashes_staleness_compares(tmp_path):
    cs, demo = _approved_set(tmp_path)
    meta = RunBundle(cs.approved_dir_for(demo.id)).read_metadata()
    assert meta.prompt_hash == prompt_hash(demo)
    assert meta.input_hashes == input_hashes(demo)
    assert set(meta.input_hashes) == {"seed.txt", "nested/data.csv"}


# ---- surfaced where the deck is produced ------------------------------
def test_build_reports_stale_approved_demos(tmp_path):
    cs, demo = _approved_set(tmp_path)
    assert build(cs).stale == []

    demo.prompt_path.write_text("A different question entirely\n", encoding="utf-8")
    report = build(cs)
    assert [s.demo_id for s in report.stale] == ["synth"]
    assert report.stale[0].prompt_changed is True


def test_list_marks_stale_approved_demos(tmp_path, capsys):
    from demoforge.cli import main

    cs, demo = _approved_set(tmp_path)
    assert main(["--set", str(cs.root), "list"]) == 0
    fresh = capsys.readouterr().out
    assert "no longer match" not in fresh

    demo.prompt_path.write_text("A different question entirely\n", encoding="utf-8")
    assert main(["--set", str(cs.root), "list"]) == 0
    out = capsys.readouterr().out
    assert "!" in out
    assert "no longer match the demo on disk" in out
    assert "prompt.md changed since capture" in out
    assert "demoforge run synth" in out
