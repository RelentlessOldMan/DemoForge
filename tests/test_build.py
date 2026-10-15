"""Incremental build: cache hits, byte-stability, invalidation, pruning."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from conftest import make_content_set, write_demo

from demoforge.build import CACHE_FILE, build
from demoforge.capture import approve_run, run_demo
from demoforge.discovery import load_content_set

WHEN = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)


def _invoker(produced=True):
    def invoke(prompt, work):
        if produced:
            (work / "result.txt").write_text("the answer", encoding="utf-8")
        return [
            json.dumps({"type": "system", "model": "claude-test"}),
            json.dumps({"type": "assistant", "message": {"content": [
                {"type": "text", "text": "Working."},
                {"type": "tool_use", "id": "t1", "name": "Write", "input": {"file_path": "result.txt"}},
            ]}}),
            json.dumps({"type": "result", "subtype": "success", "is_error": False}),
        ]
    return invoke


def _approved_demo(cs, *, demo_id="synth", folder="01_synth", order=1):
    write_demo(
        cs.demos_dir, folder,
        f"id: {demo_id}\ntitle: Demo {demo_id}\norder: {order}\nruntime: none\n"
        f"inputs:\n  - input/seed.txt\n"
        f"checks:\n  - id: produced\n    kind: file_exists\n    pattern: result.txt\n",
    )
    d = cs.demos_dir / folder
    (d / "input").mkdir()
    (d / "input" / "seed.txt").write_text("seed", encoding="utf-8")
    (d / "prompt.md").write_text(f"Job for {demo_id}.", encoding="utf-8")
    cs2 = load_content_set(cs.root)  # reload so discovery sees the new demo
    demo = next(x for x in cs2.demos() if x.id == demo_id)
    r = run_demo(demo, cs2, invoker=_invoker(), when=WHEN, git_commit="abc")
    approve_run(cs2, demo.id, run_id=r.run_id)
    return cs2


def test_first_build_builds_then_second_is_noop(tmp_path):
    cs = load_content_set(make_content_set(tmp_path / "set"))
    cs = _approved_demo(cs)

    r1 = build(cs)
    assert set(r1.built) == {"record:synth", "slides"}
    assert r1.did_work

    r2 = build(cs)
    assert r2.built == []
    assert set(r2.skipped) == {"record:synth", "slides"}
    assert not r2.did_work


def test_rebuild_is_byte_identical(tmp_path):
    cs = load_content_set(make_content_set(tmp_path / "set"))
    cs = _approved_demo(cs)
    build(cs)
    record = cs.output_dir / "records" / "synth.md"
    deck = cs.output_dir / "slides" / "deck.md"
    before_record, before_deck = record.read_bytes(), deck.read_bytes()

    build(cs, force=True)  # force re-render; deterministic -> identical bytes
    assert record.read_bytes() == before_record
    assert deck.read_bytes() == before_deck


def test_cache_invalidates_when_bundle_changes(tmp_path):
    cs = load_content_set(make_content_set(tmp_path / "set"))
    cs = _approved_demo(cs)
    build(cs)

    # Mutate the approved bundle -> its record key changes -> rebuild.
    results = cs.approved_dir_for("synth") / "results.json"
    results.write_text(results.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    r = build(cs)
    assert "record:synth" in r.built
    assert "slides" in r.built  # slides key includes each bundle's results.json


def test_prune_removes_record_for_unapproved_demo(tmp_path):
    cs = load_content_set(make_content_set(tmp_path / "set"))
    cs = _approved_demo(cs)
    build(cs)
    assert (cs.output_dir / "records" / "synth.md").exists()

    # Remove the approval; next build prunes the stale record.
    import shutil
    shutil.rmtree(cs.approved_dir_for("synth"))

    r = build(cs)
    assert "synth.md" in r.pruned and "synth.html" in r.pruned
    assert not (cs.output_dir / "records" / "synth.md").exists()

    cache = json.loads((cs.output_dir / CACHE_FILE).read_text(encoding="utf-8"))
    assert "record:synth" not in cache["targets"]


def test_force_ignores_cache(tmp_path):
    cs = load_content_set(make_content_set(tmp_path / "set"))
    cs = _approved_demo(cs)
    build(cs)
    r = build(cs, force=True)
    assert set(r.built) == {"record:synth", "slides"}
