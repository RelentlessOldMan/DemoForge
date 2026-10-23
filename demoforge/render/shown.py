"""What Claude was shown when it read a picture or a PDF, drawn for the replay.

A read of a picture or a PDF hands Claude the file itself, and the raw transcript
keeps those bytes (capture/normalize.py :func:`read_attachments`). The replay shows
the viewer that same picture, or the pages of that same PDF, on the read that
received it, so what is on screen is what Claude looked at, at that moment. A plot
Claude redraws is shown as it was at each look, never as it ended up.

A picture is used as recorded. A PDF's pages are drawn by poppler's ``pdftoppm``
(config/tools.toml pins the version) at a fixed resolution, so the same record
always gives the same frames.
"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from demoforge.capture.normalize import Shown, read_attachments
from demoforge.errors import DemoForgeError
from demoforge.model import Event

# Pages are drawn small: the replay shows that Claude read the document, and which
# one, not a page to read along with.
PDF_DPI = 60
_PICTURES = ("image/png", "image/jpeg", "image/gif", "image/webp")


def resolve_pdftoppm(pdftoppm: Path | str | None = None) -> Path:
    """The pdftoppm binary to use: explicit, else from PATH."""
    if pdftoppm is not None:
        path = Path(pdftoppm)
        if path.is_file() or shutil.which(str(pdftoppm)):
            return path
        raise DemoForgeError(f"pdftoppm not found at {pdftoppm}")
    found = shutil.which("pdftoppm")
    if not found:
        raise DemoForgeError(
            "pdftoppm (poppler) not found on PATH: the replay draws the PDF pages "
            "Claude read with it (config/tools.toml pins the expected version)"
        )
    return Path(found)


def views(shown: Shown, *, pdftoppm: Path | str | None = None) -> list[str]:
    """The pictures to show for one attachment, as data URIs: the image, or each page."""
    if shown.media_type in _PICTURES:
        return [_uri(shown.media_type, shown.data)]
    if shown.media_type == "application/pdf":
        return [_uri("image/png", page) for page in pdf_pages(shown.data, pdftoppm=pdftoppm)]
    return []


def pdf_pages(data: bytes, *, pdftoppm: Path | str | None = None) -> list[bytes]:
    """Every page of a PDF, drawn as PNG at :data:`PDF_DPI`."""
    tool = resolve_pdftoppm(pdftoppm)
    with tempfile.TemporaryDirectory(prefix="demoforge-pdf-") as tmp:
        src = Path(tmp) / "shown.pdf"
        src.write_bytes(data)
        proc = subprocess.run(
            [str(tool), "-png", "-r", str(PDF_DPI), str(src), str(Path(tmp) / "page")],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            raise DemoForgeError(f"pdftoppm failed: {proc.stderr.strip()[:300]}")
        pages = sorted(Path(tmp).glob("page-*.png"), key=lambda p: int(p.stem.rsplit("-", 1)[1]))
        return [p.read_bytes() for p in pages]


def with_read_views(
    events: list[Event], transcript: Path, *, pdftoppm: Path | str | None = None
) -> list[Event]:
    """Each read that showed Claude a picture or a PDF, with what it showed attached.

    The pictures go in the event's ``views``; a PDF also gets ``pages``. Without a
    transcript there is nothing to attach, and the events come back unchanged.
    """
    if not transcript.is_file():
        return events
    attached = read_attachments(events, _objs(transcript))
    if not attached:
        return events
    out: list[Event] = []
    for e in events:
        shown = attached.get(e.seq)
        if shown is None:
            out.append(e)
            continue
        extra: dict[str, Any] = {"views": views(shown, pdftoppm=pdftoppm)}
        if shown.media_type == "application/pdf":
            extra["pages"] = len(extra["views"])
        out.append(Event(seq=e.seq, t=e.t, type=e.type, data={**e.data, **extra}))
    return out


def _objs(transcript: Path) -> list[dict[str, Any]]:
    with transcript.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _uri(media_type: str, data: bytes) -> str:
    return f"data:{media_type};base64,{base64.b64encode(data).decode('ascii')}"
