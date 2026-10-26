"""What a rendered presentation was built from (``output/video/manifest.json``).

The video is not committed, so nothing in git says which commit or which
approved runs produced a given MP4. The manifest records it beside the video, and
``release.ps1`` refuses to publish a video whose manifest does not match HEAD.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

from demoforge.discovery import ContentSet
from demoforge.model import RunBundle
from demoforge.staleness import hash_file, hash_text

MANIFEST_NAME = "manifest.json"


def bundle_digest(root: Path) -> str:
    """One hash over every file in an approved bundle, by relative path."""
    parts = [
        f"{p.relative_to(root).as_posix()}\t{hash_file(p)}"
        for p in sorted(root.rglob("*")) if p.is_file()
    ]
    return hash_text("\n".join(parts))


def write_package(files: list[Path], out_path: Path, *, folder: str) -> Path:
    """Zip a split presentation's files into one download, under ``folder/``.

    Stored, not deflated: MP4 does not compress, and storing keeps unzipping
    instant. Every entry carries a fixed timestamp, so the same files always make
    the same zip, byte for byte.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(out_path.name + ".tmp")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_STORED) as zf:
        for f in files:
            info = zipfile.ZipInfo(f"{folder}/{f.name}", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o644 << 16
            with f.open("rb") as src, zf.open(info, "w", force_zip64=True) as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
    os.replace(tmp, out_path)
    return out_path


def write_manifest(
    cs: ContentSet, video: Path, demo_ids: list[str], narration_provider: str | None,
    *, files: list[Path] | None = None,
) -> Path:
    """Record what ``video`` was built from; ``files`` are a split presentation's parts.

    For a split presentation ``video`` is the zip that ships, and each part's own
    hash is listed too.
    """
    commit, dirty = _git_state(cs.root)
    demos = []
    for demo_id in demo_ids:
        root = cs.approved_dir_for(demo_id)
        meta = RunBundle(root).read_metadata()
        demos.append({
            "id": demo_id,
            "run_id": meta.extra.get("run_id"),
            "captured": meta.created,
            "bundle_sha256": bundle_digest(root),
        })
    payload = {
        "git_commit": commit,
        "git_dirty": dirty,
        "video": video.name,
        "video_sha256": hash_file(video),
        "narration_provider": narration_provider,
        "demos": demos,
    }
    if files is not None:
        payload["files"] = [{"name": f.name, "sha256": hash_file(f)} for f in files]
    path = video.with_name(MANIFEST_NAME)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, path)
    return path


def _git_state(start: Path) -> tuple[str | None, bool]:
    def git(*args: str) -> str | None:
        try:
            proc = subprocess.run(
                ["git", *args], cwd=str(start), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return proc.stdout if proc.returncode == 0 else None

    head = git("rev-parse", "HEAD")
    status = git("status", "--porcelain")
    return (head.strip() if head else None), bool(status and status.strip())
