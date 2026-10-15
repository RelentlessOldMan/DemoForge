"""Incremental, idempotent build (architecture.md §3.4 / §8, video-pipeline.md §8).

``build`` walks the render DAG and does the minimum work: each output target has a
content-addressed cache key over its inputs, stored in ``output/.build-cache.json``.
A target is rebuilt only when its key changes. Because rendering is deterministic,
running ``build`` twice with no input changes produces identical bytes and (after the
first run) does no work at all.

Phase 4 covers the record + slide targets; the video targets slot into the same cache
model later.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from demoforge.discovery import ContentSet
from demoforge.model import Demo
from demoforge.render.record import render_record
from demoforge.render.slides import render_slides
from demoforge.staleness import Staleness, approved_staleness

# Bump when record/slide rendering changes its output, so stale caches invalidate.
RENDER_VERSION = "1"
CACHE_FILE = ".build-cache.json"


@dataclass
class BuildReport:
    built: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    pruned: list[str] = field(default_factory=list)
    # Approved demos whose prompt/inputs changed after capture. Reported, never
    # auto-corrected: only a fresh `run` can answer the new prompt.
    stale: list[Staleness] = field(default_factory=list)

    @property
    def did_work(self) -> bool:
        return bool(self.built or self.pruned)


def build(
    content_set: ContentSet,
    *,
    force: bool = False,
    slide_formats=("html",),
    out_dir: Path | None = None,
) -> BuildReport:
    """Build all stale record + slide targets; skip up-to-date ones."""
    out = out_dir or content_set.output_dir
    records_dir = out / "records"
    cache_path = out / CACHE_FILE
    cache = _load_cache(cache_path) if not force else {}
    report = BuildReport()

    approved = [
        d for d in content_set.demos(enabled_only=True)
        if content_set.approved_dir_for(d.id).is_dir()
    ]
    approved_ids = {d.id for d in approved}

    # --- records (one target per approved demo) ---
    for demo in approved:
        target = f"record:{demo.id}"
        key = _record_key(content_set, demo)
        if cache.get(target) == key and _record_outputs_exist(records_dir, demo.id):
            report.skipped.append(target)
            continue
        render_record(demo, content_set.display_bundle(demo.id), records_dir)
        cache[target] = key
        report.built.append(target)

    _prune_records(records_dir, approved_ids, cache, report)

    # The bundles are rendered faithfully either way; a stale one just no longer
    # matches the demo it is filed under, so say so rather than silently shipping it.
    for demo in approved:
        st = approved_staleness(content_set, demo)
        if st is not None and st.is_stale:
            report.stale.append(st)

    # --- slides (single derived target) ---
    slides_target = "slides"
    slides_key = _slides_key(content_set, approved, slide_formats)
    slides_dir = out / "slides"
    if cache.get(slides_target) == slides_key and _slides_outputs_exist(slides_dir, slide_formats):
        report.skipped.append(slides_target)
    else:
        render_slides(content_set, slides_dir, formats=slide_formats)
        cache[slides_target] = slides_key
        report.built.append(slides_target)

    _save_cache(cache_path, cache)
    return report


# ---- cache keys -------------------------------------------------------
def _record_key(cs: ContentSet, demo: Demo) -> str:
    approved = cs.approved_dir_for(demo.id)
    return _digest(
        RENDER_VERSION, "record",
        _dir_fingerprint(approved),
        _file_hash(demo.dir / "demo.yaml"),  # title/runtime feed the record
        cs.path_rewriter.fingerprint(),
    )


def _slides_key(cs: ContentSet, approved: list[Demo], formats) -> str:
    parts = [RENDER_VERSION, "slides", ",".join(formats), _file_hash(cs.root / "demoforge.toml")]
    for demo in approved:  # already ordered by (order, id)
        bundle = cs.approved_dir_for(demo.id)
        parts += [
            demo.id, str(demo.order), demo.title,
            _file_hash(bundle / "results.json"),
            _file_hash(bundle / "prompt.md"),
        ]
    return _digest(*parts)


# ---- pruning ----------------------------------------------------------
def _prune_records(records_dir: Path, approved_ids: set[str], cache: dict, report: BuildReport) -> None:
    """Remove rendered records (and cache entries) for demos no longer approved."""
    if records_dir.is_dir():
        for f in sorted(records_dir.glob("*.*")):
            if f.suffix in (".md", ".html") and f.stem not in approved_ids:
                f.unlink()
                report.pruned.append(f.name)
    for target in [t for t in cache if t.startswith("record:")]:
        if target.split(":", 1)[1] not in approved_ids:
            del cache[target]


# ---- hashing / cache io -----------------------------------------------
def _digest(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


def _file_hash(path: Path) -> str:
    if not path.exists():
        return "missing"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dir_fingerprint(root: Path) -> str:
    """Order-stable hash of a directory's file contents."""
    if not root.is_dir():
        return "missing"
    h = hashlib.sha256()
    for f in sorted(p for p in root.rglob("*") if p.is_file()):
        h.update(str(f.relative_to(root)).replace("\\", "/").encode("utf-8"))
        h.update(b"\0")
        h.update(f.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def _record_outputs_exist(records_dir: Path, demo_id: str) -> bool:
    return (records_dir / f"{demo_id}.md").exists() and (records_dir / f"{demo_id}.html").exists()


def _slides_outputs_exist(slides_dir: Path, formats) -> bool:
    # deck.md is always produced; format conversions are best-effort (Marp optional),
    # so their absence must not force an endless rebuild.
    return (slides_dir / "deck.md").exists()


def _load_cache(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data.get("targets", {}) if data.get("version") == RENDER_VERSION else {}


def _save_cache(path: Path, cache: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": RENDER_VERSION, "targets": cache}
    # Written aside and renamed in, so an interrupted build never leaves a torn cache.
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, path)
