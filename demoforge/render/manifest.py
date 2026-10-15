"""What a rendered presentation was built from (``output/video/manifest.json``).

The video is not committed, so nothing in git says which commit or which
approved runs produced a given MP4. The manifest records it beside the video, and
``release.ps1`` refuses to publish a video whose manifest does not match HEAD.
"""

from __future__ import annotations

import json
import os
import subprocess
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


def write_manifest(
    cs: ContentSet, video: Path, demo_ids: list[str], narration_provider: str | None,
) -> Path:
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
