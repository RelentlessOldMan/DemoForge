"""Render an approved run bundle into a per-demo record (Markdown + HTML).

The record is the canonical, highest-value deliverable (video-pipeline.md §3): a
new reader gets the entire "prompt -> work -> verified result" story from one
file. Slides and video are visual reformattings of the same data.
"""

from __future__ import annotations

from pathlib import Path

from demoforge.model import Demo, RunBundle
from demoforge.render.document import Document, to_html, to_markdown

_LANG_BY_EXT = {
    ".m": "matlab", ".py": "python", ".json": "json", ".csv": "text",
    ".md": "markdown", ".txt": "text", ".sh": "bash", ".yaml": "yaml", ".yml": "yaml",
}
_MAX_EMBED_BYTES = 20_000
_MAX_OUTPUT_LINES = 12


# How a conversation ended, in the words the record shows.
_DONE_TEXT = {
    "satisfied": "The person had nothing more to ask.",
    "limit": "The follow-up limit was reached; the person was not asked again.",
}

def render_record(demo: Demo, bundle: RunBundle, out_dir: Path) -> dict[str, Path]:
    """Render ``bundle`` for ``demo`` into ``out_dir`` as ``<demo>.md`` and ``.html``."""
    doc = build_record_doc(demo, bundle)
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"{demo.id}.md"
    html_path = out_dir / f"{demo.id}.html"
    md_path.write_text(to_markdown(doc), encoding="utf-8", newline="\n")
    html_path.write_text(to_html(doc, title=f"{demo.title} — DemoForge record"),
                         encoding="utf-8", newline="\n")
    return {"md": md_path, "html": html_path}


def build_record_doc(demo: Demo, bundle: RunBundle) -> Document:
    meta = bundle.read_metadata()
    results = bundle.read_results()
    events = bundle.read_events()

    doc = Document()
    doc.h1(f"{demo.title}")
    doc.p(f"DemoForge record · runtime: `{demo.runtime}` · "
          f"result: {'PASS' if results.passed else 'FAIL'}")

    # --- the job ---
    doc.h2("The job")
    prompt = bundle.read_text(bundle.prompt_path).strip() if bundle.prompt_path.exists() else ""
    if prompt:
        doc.quote(prompt)

    # --- inputs ---
    if meta.input_hashes:
        doc.h2("Inputs")
        rows = [[name, sha[:12]] for name, sha in sorted(meta.input_hashes.items())]
        doc.table(["file", "sha256"], rows)

    # --- what Claude did ---
    doc.h2("What Claude did")
    _append_transcript(doc, events)

    # --- artifacts ---
    _append_artifacts(doc, bundle)

    # --- results ---
    doc.h2("Measurable results")
    _append_results(doc, results)

    # --- reproducibility ---
    doc.h2("Reproducibility")
    doc.ul(_repro_lines(meta, bundle))
    return doc


def _append_transcript(doc: Document, events: list) -> None:
    for ev in events:
        d = ev.data
        if ev.type == "user_message":
            doc.quote(d.get("text", ""))
        elif ev.type == "user_done":
            doc.p(_DONE_TEXT.get(str(d.get("reason", "")), "The conversation ended."))
        elif ev.type == "assistant_text":
            doc.p(d.get("text", ""))
        elif ev.type == "file_read":
            doc.p(f"Read `{d.get('path', '')}`")
        elif ev.type in ("file_write", "file_edit"):
            verb = "Wrote" if ev.type == "file_write" else "Edited"
            doc.p(f"{verb} `{d.get('path', '')}`")
        elif ev.type == "file_search":
            doc.p(f"Searched `{d.get('query', '')}`")
        elif ev.type == "command":
            doc.code(f"$ {d.get('command', '')}", "bash")
        elif ev.type == "command_output":
            doc.code(_truncate_lines(d.get("output", "")), "text")
        elif ev.type == "tool_call":
            doc.p(f"Used `{d.get('tool', '')}`")


def _append_artifacts(doc: Document, bundle: RunBundle) -> None:
    adir = bundle.artifacts_dir
    if not adir.is_dir():
        return
    files = sorted(f for f in adir.iterdir() if f.is_file())
    if not files:
        return
    doc.h2("Generated artifacts")
    for f in files:
        doc.h3(f.name)
        size = f.stat().st_size
        lang = _LANG_BY_EXT.get(f.suffix.lower())
        if lang is not None and size <= _MAX_EMBED_BYTES:
            doc.code(bundle.read_text(f).rstrip(), lang)
        else:
            doc.p(f"({size} bytes — not embedded)")


def _append_results(doc: Document, results) -> None:
    rows = []
    for c in results.checks:
        if c.passed is None:
            verdict = "metric"
        else:
            verdict = "PASS" if c.passed else "FAIL"
        rows.append([c.id, c.kind, verdict, _fmt_value(c.value), c.message])
    doc.table(["check", "kind", "result", "value", "detail"], rows)


def _repro_lines(meta, bundle: RunBundle) -> list[str]:
    lines = [
        # An approved bundle lives under the demo id; the run it froze is recorded.
        f"run id: {meta.extra.get('run_id') or 'n/a'}",
        f"model: {meta.model or 'n/a'}",
        f"captured: {meta.created or 'n/a'} ({meta.capture_mode})",
        f"git commit: {meta.git_commit or 'n/a'}",
        f"os: {meta.os or 'n/a'}",
    ]
    if meta.runtimes:
        rt = ", ".join(f"{k}={v}" for k, v in sorted(meta.runtimes.items()))
        lines.append(f"runtimes: {rt}")
    if meta.prompt_hash:
        lines.append(f"prompt sha256: {meta.prompt_hash[:12]}")
    return lines


def _truncate_lines(text: str) -> str:
    lines = text.rstrip().splitlines()
    if len(lines) <= _MAX_OUTPUT_LINES:
        return "\n".join(lines)
    kept = lines[:_MAX_OUTPUT_LINES]
    return "\n".join(kept) + f"\n… ({len(lines) - _MAX_OUTPUT_LINES} more lines)"


def _fmt_value(value) -> str:
    if isinstance(value, float):
        return f"{value:g}"
    return "" if value is None else str(value)
