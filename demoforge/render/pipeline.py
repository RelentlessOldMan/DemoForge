"""Render orchestration: approved bundles across a content set -> records + slides."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from demoforge.discovery import ContentSet
from demoforge.errors import DemoError
from demoforge.model import Demo
from demoforge.render.record import render_record
from demoforge.render.slides import render_slides


@dataclass
class RenderSummary:
    records: dict[str, dict[str, Path]] = field(default_factory=dict)
    slides: dict[str, Path] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)  # enabled demos lacking an approved bundle

    @property
    def rendered(self) -> int:
        return len(self.records)


def render_demo_record(content_set: ContentSet, demo: Demo, out_dir: Path) -> dict[str, Path]:
    """Render one demo's record from its approved bundle (must exist)."""
    approved = content_set.approved_dir_for(demo.id)
    bundle = content_set.display_bundle(demo.id)
    if not bundle.exists():
        raise DemoError(
            f"no approved bundle for {demo.id!r} at {approved}. "
            f"Run `demoforge run {demo.id}` then `demoforge approve {demo.id}`.",
        )
    return render_record(demo, bundle, out_dir)


def render_all(
    content_set: ContentSet,
    *,
    out_dir: Path | None = None,
    only: str | None = None,
    slide_formats=("html",),
) -> RenderSummary:
    """Render records for every enabled+approved demo, then the derived slide deck."""
    out = out_dir or content_set.output_dir
    records_dir = out / "records"
    slides_dir = out / "slides"
    summary = RenderSummary()

    demos = content_set.demos(enabled_only=True)
    if only is not None:
        demos = [d for d in demos if d.id == only]
        if not demos:
            raise DemoError(f"no enabled demo with id {only!r}")

    for demo in demos:
        if not content_set.approved_dir_for(demo.id).is_dir():
            summary.skipped.append(demo.id)
            continue
        summary.records[demo.id] = render_demo_record(content_set, demo, records_dir)

    # Slides are always (re)derived from the full enabled+approved set.
    summary.slides = render_slides(content_set, slides_dir, formats=slide_formats)
    return summary
