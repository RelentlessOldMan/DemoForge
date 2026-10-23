"""The replay shows the picture or PDF a read handed Claude, from the record alone."""

import base64
import json
import shutil

import pytest

from demoforge.capture.normalize import read_attachments
from demoforge.model import Event
from demoforge.render.config import load_settings
from demoforge.render.session import session_beats
from demoforge.render.shown import views, with_read_views
from demoforge.render.timeline import build_timeline

# A 1x1 PNG.
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def _read(tid, path):
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": tid, "name": "Read", "input": {"file_path": path}}]}}


def _result(tid, part):
    return {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": tid, "content": [part]}]}}


def _image(data, kind="image", media="image/png"):
    return {"type": kind, "source": {"type": "base64", "media_type": media,
                                     "data": base64.b64encode(data).decode()}}


def _events():
    return [
        Event(seq=0, t=0.0, type="file_read", data={"tool": "Read", "path": "/w/notes.md"}),
        Event(seq=1, t=1.0, type="file_read", data={"tool": "Read", "path": "/w/plot.png"}),
        Event(seq=2, t=2.0, type="file_read", data={"tool": "Read", "path": "/w/plot.png"}),
    ]


def _objs(first=b"first look", second=b"second look"):
    return [
        _read("a", "/w/notes.md"), _result("a", {"type": "text", "text": "# notes"}),
        _read("b", "/w/plot.png"), _result("b", _image(first)),
        _read("c", "/w/plot.png"), _result("c", _image(second)),
    ]


def test_each_look_at_a_picture_gets_the_pixels_of_that_look():
    found = read_attachments(_events(), _objs())
    assert sorted(found) == [1, 2]
    assert found[1].data == b"first look" and found[2].data == b"second look"
    assert found[1].media_type == "image/png"


def test_pairing_reads_refuses_a_mismatched_record():
    with pytest.raises(ValueError):
        read_attachments(_events(), _objs()[:4])
    renamed = _objs()
    renamed[2] = _read("b", "/w/other.png")
    with pytest.raises(ValueError):
        read_attachments(_events(), renamed)


def test_the_window_shows_the_picture_on_its_read(tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        "".join(json.dumps(o) + "\n" for o in _objs(_PNG, _PNG)), encoding="utf-8"
    )
    events = with_read_views(_events(), transcript)
    assert "views" not in events[0].data
    st = load_settings()
    timeline = build_timeline("demo", events, scenes=st.scenes, timing=st.timing)
    beats = session_beats(timeline, st.timing)
    last = beats[timeline.scenes[1].index][-1]
    entry = last.session["entries"][-1]
    assert entry["views"] == ["data:image/png;base64," + base64.b64encode(_PNG).decode()]
    assert entry["views_note"] == "the image Claude was shown"


def test_without_a_transcript_nothing_is_attached(tmp_path):
    events = _events()
    assert with_read_views(events, tmp_path / "missing.jsonl") is events


@pytest.mark.skipif(not shutil.which("pdftoppm"), reason="poppler not installed")
def test_a_pdf_is_shown_page_by_page():
    from pathlib import Path

    pdf = next(Path("examples/claude-demo-kit/demos").glob("*/input/*.pdf"))
    from demoforge.capture.normalize import Shown

    pages = views(Shown("application/pdf", pdf.read_bytes()))
    assert len(pages) == 5
    assert all(p.startswith("data:image/png;base64,") for p in pages)
