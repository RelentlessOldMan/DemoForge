"""Figures for intro cards, drawn only from files committed in the demo folder.

An intro card may show the viewer what the problem's data looks like before any of
the run is played. The picture is computed from the named file and nothing else, and
the card says which file and how many rows it shows, so a figure can never stand in
for something the demo does not contain.

The drawing is a plain inline SVG, so it is deterministic and needs no plotting
library at render time.
"""

from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass
from html import escape
from pathlib import Path

from demoforge.errors import DemoError

WIDTH = 760
HEIGHT = 640
_PAD_LEFT = 96
_PAD_RIGHT = 24
_PAD_TOP = 20
_PAD_BOTTOM = 84


@dataclass(frozen=True)
class FigureView:
    """A figure ready for a card: the SVG and the line that says where it came from."""

    svg: str
    caption: str
    source_note: str


def resolve_figure_source(demo_dir: Path, source: str) -> Path:
    """The figure's file, which must exist inside the demo's own folder."""
    root = demo_dir.resolve()
    path = (root / source).resolve()
    if root not in path.parents:
        raise DemoError(f"figure {source!r} is outside the demo folder")
    if not path.is_file():
        raise DemoError(f"figure {source!r} does not exist in {demo_dir}")
    return path


def figure_view(demo_dir: Path, source: str, caption: str) -> FigureView:
    """Plot ``source``, optionally only ``#rows=A-B`` of it (1-based, inclusive).

    A close-up shows what the whole file would hide, such as noise that is small
    next to the overall range; the note always says which rows are shown.
    """
    file, _, fragment = source.partition("#")
    path = resolve_figure_source(demo_dir, file)
    if path.suffix.lower() != ".csv":
        raise DemoError(f"figure {source!r}: only .csv files can be plotted")
    x_name, y_name, points = _read_xy(path, file)
    total = len(points)
    first, last = _row_range(fragment, total, source)
    shown = points[first - 1:last]
    which = (
        f"all {total:,} rows" if (first, last) == (1, total)
        else f"rows {first:,}–{last:,} of {total:,}"
    )
    note = f"Plotted from {file}: {which}, {y_name} against {x_name}."
    return FigureView(svg=_xy_svg(shown, x_name, y_name), caption=caption, source_note=note)


def _row_range(fragment: str, total: int, source: str) -> tuple[int, int]:
    if not fragment:
        return 1, total
    m = re.fullmatch(r"rows=(\d+)-(\d+)", fragment)
    if not m:
        raise DemoError(f"figure {source!r}: expected '#rows=A-B' after the file name")
    first, last = int(m.group(1)), int(m.group(2))
    if not 1 <= first <= last <= total:
        raise DemoError(f"figure {source!r}: the file has rows 1-{total}")
    return first, last


def _read_xy(path: Path, source: str) -> tuple[str, str, list[tuple[float, float]]]:
    """The first two columns, as numbers. A header row names them."""
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.reader(f) if r and any(c.strip() for c in r)]
    if not rows:
        raise DemoError(f"figure {source!r} is empty")
    header = rows[0]
    try:
        float(header[0])
        names, body = ("column 1", "column 2"), rows
    except ValueError:
        names, body = (header[0].strip(), header[1].strip()), rows[1:]
    points: list[tuple[float, float]] = []
    for i, r in enumerate(body, start=1):
        try:
            points.append((float(r[0]), float(r[1])))
        except (IndexError, ValueError) as exc:
            raise DemoError(
                f"figure {source!r}: row {i} is not a pair of numbers"
            ) from exc
    if not points:
        raise DemoError(f"figure {source!r} has no data rows")
    return names[0], names[1], points


def _ticks(lo: float, hi: float, count: int = 5) -> list[float]:
    """Round tick values covering [lo, hi]."""
    if hi <= lo:
        hi = lo + 1.0
    raw = (hi - lo) / count
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 5, 10) if m * mag >= raw)
    start = math.ceil(lo / step) * step
    ticks = []
    v = start
    while v <= hi + step * 1e-9:
        ticks.append(round(v, 10))
        v += step
    return ticks


def _fmt(v: float) -> str:
    return f"{v:g}"


def _xy_svg(points: list[tuple[float, float]], x_name: str, y_name: str) -> str:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x_lo, x_hi = min(xs), max(xs)
    y_lo, y_hi = min(ys), max(ys)
    x_span = (x_hi - x_lo) or 1.0
    y_span = (y_hi - y_lo) or 1.0
    x_lo, x_hi = x_lo - 0.03 * x_span, x_hi + 0.03 * x_span
    y_lo, y_hi = y_lo - 0.03 * y_span, y_hi + 0.03 * y_span

    left, right = _PAD_LEFT, WIDTH - _PAD_RIGHT
    top, bottom = _PAD_TOP, HEIGHT - _PAD_BOTTOM

    def sx(v: float) -> float:
        return left + (v - x_lo) / (x_hi - x_lo) * (right - left)

    def sy(v: float) -> float:
        return bottom - (v - y_lo) / (y_hi - y_lo) * (bottom - top)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" '
        f'width="{WIDTH}" height="{HEIGHT}" class="figure-plot">'
    ]
    for t in _ticks(x_lo, x_hi):
        x = sx(t)
        parts.append(f'<line class="grid" x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{bottom}"/>')
        parts.append(
            f'<text class="tick" x="{x:.1f}" y="{bottom + 30}" text-anchor="middle">'
            f"{_fmt(t)}</text>"
        )
    for t in _ticks(y_lo, y_hi):
        y = sy(t)
        parts.append(f'<line class="grid" x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}"/>')
        parts.append(
            f'<text class="tick" x="{left - 12}" y="{y + 7:.1f}" text-anchor="end">'
            f"{_fmt(t)}</text>"
        )
    parts.append(
        f'<rect class="frame" x="{left}" y="{top}" width="{right - left}" '
        f'height="{bottom - top}"/>'
    )
    path = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in points)
    parts.append(f'<polyline class="trace" points="{path}"/>')
    parts.extend(
        f'<circle class="point" cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="5"/>'
        for x, y in points
    )
    parts.append(
        f'<text class="axis" x="{(left + right) / 2:.1f}" y="{HEIGHT - 12}" '
        f'text-anchor="middle">{escape(x_name)}</text>'
    )
    parts.append(
        f'<text class="axis" x="22" y="{(top + bottom) / 2:.1f}" text-anchor="middle" '
        f'transform="rotate(-90 22 {(top + bottom) / 2:.1f})">{escape(y_name)}</text>'
    )
    parts.append("</svg>")
    return "".join(parts)
