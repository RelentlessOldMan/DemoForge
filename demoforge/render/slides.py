"""Render enabled+approved demos into a Marp slide deck.

The deck's structure is *derived* from the content set — title, one section per
enabled+approved demo, summary, finale — so adding/removing/reordering a demo
changes the deck automatically, with no hand-editing (video-pipeline.md §4).

``deck.md`` (Marp Markdown) is the deterministic, committed artifact. Converting
it to HTML/PDF via the Marp CLI is a downstream, optional step: if Marp is not
available the deck is still produced.
"""

from __future__ import annotations

import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from demoforge.discovery import ContentSet
from demoforge.model import Demo, RunBundle
from demoforge.render.document import md_cell

_PROMPT_MAX = 260


def render_slides(content_set: ContentSet, out_dir: Path, *, formats=("html",)) -> dict[str, Path]:
    """Write ``deck.md`` and convert to the requested ``formats`` when Marp is available."""
    deck = write_deck(content_set, out_dir)
    outputs: dict[str, Path] = {"deck": deck}
    if not marp_available():
        return outputs
    for fmt in formats:
        target = out_dir / f"slides.{fmt}"
        if _marp_convert(deck, target):
            outputs[fmt] = target
    return outputs


def write_deck(content_set: ContentSet, out_dir: Path) -> Path:
    """Build the derived Marp deck markdown. Always succeeds (no external tools)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    deck = out_dir / "deck.md"
    deck.write_text(_build_deck(content_set), encoding="utf-8", newline="\n")
    return deck


def _build_deck(cs: ContentSet) -> str:
    cfg = cs.config
    slides: list[str] = []

    slides.append(
        "---\nmarp: true\npaginate: true\n---\n\n"
        f"# {cfg.title}\n\n### {cfg.subtitle}\n\n{cfg.description}"
    )
    slides.append(
        f"## What is {cfg.title}?\n\n"
        "- Real engineering jobs, not chatbot questions\n"
        "- Claude reads, codes, runs, measures, and verifies\n"
        "- Every result below was **captured from an actual run** and checked by property"
    )

    approved = [d for d in cs.demos(enabled_only=True) if cs.approved_dir_for(d.id).is_dir()]
    for demo in approved:
        slides.append(_demo_slide(cs, demo))

    if approved:
        slides.append(_summary_slide(approved))
    else:
        slides.append("## No approved demos yet\n\nRun `demoforge run <demo>` then "
                       "`demoforge approve <demo>`, and this deck fills in automatically.")

    slides.append(
        "## It demonstrates itself\n\n"
        "These slides — and the per-demo records behind them — were generated from this "
        "repository by `demoforge build`, straight from the approved run bundles.\n\n"
        "**Add a demo, rebuild, and it appears here. Nothing is hand-edited.**"
    )
    return "\n\n---\n\n".join(slides) + "\n"


def _demo_slide(cs: ContentSet, demo: Demo) -> str:
    bundle = cs.display_bundle(demo.id)
    results = bundle.read_results()
    prompt = _short_prompt(bundle)

    lines = [f"## {demo.order}. {demo.title}", ""]
    if prompt:
        lines += ["**The job**", "", f"> {prompt}", ""]
    lines += ["**Verified results**", ""]
    lines += _results_table(results)
    return "\n".join(lines)


def _results_table(results) -> list[str]:
    rows = ["| check | result | value |", "| --- | --- | --- |"]
    for c in results.checks:
        if c.passed is None:
            verdict = "—"
        else:
            verdict = "✅ pass" if c.passed else "❌ fail"
        rows.append(f"| {md_cell(c.id)} | {verdict} | {md_cell(_fmt(c.value))} |")
    return rows


def _summary_slide(approved: list[Demo]) -> str:
    items = "\n".join(f"- **{d.title}** — verified" for d in approved)
    return f"## Summary\n\n{len(approved)} demonstration(s), each independently verified:\n\n{items}"


def _short_prompt(bundle: RunBundle) -> str:
    if not bundle.prompt_path.exists():
        return ""
    text = bundle.read_text(bundle.prompt_path).strip()
    first = text.split("\n\n", 1)[0].replace("\n", " ").strip()
    if len(first) > _PROMPT_MAX:
        first = first[: _PROMPT_MAX - 1].rstrip() + "…"
    return first


def _fmt(value) -> str:
    if isinstance(value, float):
        return f"{value:g}"
    return "" if value is None else str(value)


# ---- Marp CLI (optional) ----------------------------------------------
@lru_cache(maxsize=1)
def marp_available() -> bool:
    npx = shutil.which("npx")
    if not npx:
        return False
    try:
        proc = subprocess.run(
            [npx, "--yes", "@marp-team/marp-cli", "--version"],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
        )
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _marp_convert(deck: Path, target: Path) -> bool:
    npx = shutil.which("npx")
    if not npx:
        return False
    args = [
        npx, "--yes", "@marp-team/marp-cli", str(deck), "-o", str(target),
        "--allow-local-files", "--no-stdin",
    ]
    if target.suffix == ".pdf":
        args.append("--pdf")
    try:
        # Marp reads markdown from stdin when stdin is not a terminal, so an
        # inherited, never-closed pipe (a background shell, CI) blocks it forever.
        # On Windows the timeout cannot rescue that: killing npx leaves node
        # holding the output pipes. Close stdin and tell Marp not to look.
        proc = subprocess.run(
            args, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0 and target.exists()
