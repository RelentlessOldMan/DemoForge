"""DemoForge command-line interface.

    demoforge list                 # show demos, order, enabled/approved status
    demoforge run [<demo>]         # capture (or re-capture) a run      [Phase 2]
    demoforge approve <demo>       # freeze the latest/selected run     [Phase 2]
    demoforge render [<demo>]      # regenerate records/slides          [Phase 3]
    demoforge video [<demo>]       # replay frames + narrated video      [Phase 5]
    demoforge build                # full incremental build             [Phase 3+]

Run from within a content set, or point at one with ``--set PATH``. Phase 1
implements ``list`` and demo discovery/validation end-to-end; the later stages are
declared here as clearly-labeled stubs so the surface is stable while we build them.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from demoforge import __version__
from demoforge.checks import validate_check
from demoforge.discovery import ContentSet, load_content_set
from demoforge.errors import ContentSetError, DemoError, DemoForgeError
from demoforge.build import build
from demoforge.capture import approve_run, reverify_run, run_demo
from demoforge.model import Demo
from demoforge.render import render_all
from demoforge.render.slides import marp_available
from demoforge.render.video import ffmpeg_available
from demoforge.render.video_pipeline import VideoSummary, build_videos
from demoforge.staleness import Staleness, approved_staleness, stale_approved
from demoforge.verify import VerifyOutcome, verify_demo

EXIT_OK = 0
EXIT_ERROR = 1


def main(argv: list[str] | None = None) -> int:
    _force_utf8_streams()
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return EXIT_OK
    try:
        return args.func(args)
    except DemoForgeError as exc:
        _fail(str(exc))
        return EXIT_ERROR


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="demoforge", description="Capture, freeze, and render Claude agent runs.")
    parser.add_argument("--version", action="version", version=f"demoforge {__version__}")
    parser.add_argument(
        "--set", dest="set_path", metavar="PATH", default=None,
        help="path to the content set (default: current dir, else auto-detect under ./examples)",
    )
    sub = parser.add_subparsers(dest="command")

    p_list = sub.add_parser("list", help="list demos in the content set")
    p_list.set_defaults(func=cmd_list)

    p_verify = sub.add_parser(
        "verify", help="run a demo's harness + checks against produced artifacts"
    )
    p_verify.add_argument("demo", help="demo id")
    p_verify.add_argument(
        "--artifacts", metavar="DIR",
        help="dir of produced artifacts (default: the demo's reference/ solution)",
    )
    p_verify.add_argument(
        "--run", metavar="RUN_ID",
        help="check a captured run again with the current checks and record the new "
             "result in it (for a checks bug found after capture)",
    )
    p_verify.set_defaults(func=cmd_verify)

    p_run = sub.add_parser("run", help="capture a Claude run and verify it")
    p_run.add_argument("demo", help="demo id")
    p_run.add_argument(
        "--no-follow-ups", action="store_true",
        help="capture the first prompt only, even if the demo has a user brief",
    )
    p_run.set_defaults(func=cmd_run)

    p_appr = sub.add_parser("approve", help="freeze the latest/selected run into approved/")
    p_appr.add_argument("demo", help="demo id")
    p_appr.add_argument("--run", metavar="RUN_ID", help="run id (default: latest)")
    p_appr.add_argument("--force", action="store_true", help="approve even if checks failed")
    p_appr.set_defaults(func=cmd_approve)

    p_render = sub.add_parser("render", help="render records + slides from approved bundles")
    p_render.add_argument("demo", nargs="?", help="demo id (default: all approved)")
    p_render.add_argument("--pdf", action="store_true", help="also render slides.pdf (needs Marp)")
    p_render.set_defaults(func=cmd_render)

    p_video = sub.add_parser(
        "video", help="render replay frames + narrated video from approved bundles"
    )
    p_video.add_argument("demo", nargs="?", help="demo id (default: all approved)")
    p_video.add_argument(
        "--no-presentation", action="store_true",
        help="render per-demo chapters only, skip the joined presentation",
    )
    p_video.add_argument(
        "--force", action="store_true",
        help="re-render frames, audio and clips even when cached",
    )
    p_video.set_defaults(func=cmd_video)

    p_build = sub.add_parser("build", help="incremental build of all records + slides")
    p_build.add_argument("--force", action="store_true", help="rebuild everything, ignoring the cache")
    p_build.add_argument("--pdf", action="store_true", help="also render slides.pdf (needs Marp)")
    p_build.add_argument(
        "--video", action="store_true",
        help="also render the replay video (slow; needs Playwright + ffmpeg)",
    )
    p_build.set_defaults(func=cmd_build)

    return parser


# ---- commands ----------------------------------------------------------
def cmd_list(args: argparse.Namespace) -> int:
    cs = _resolve_content_set(args)
    demos = cs.demos()

    print(f"{cs.config.title}  ({cs.config.id})")
    if cs.config.subtitle:
        print(f"  {cs.config.subtitle}")
    print(f"  {cs.root}")
    print()

    if not demos:
        print("  (no demos yet — add demos/NN_name/demo.yaml)")
        return EXIT_OK

    print(f"  {'#':>3}  {'id':24}  {'runtime':8}  {'en':2} {'ap':2}  {'chk':>3}  title")
    print(f"  {'':->3}  {'':-<24}  {'':-<8}  {'':-<2} {'':-<2}  {'':->3}  {'':-<20}")
    stale: list[Staleness] = []
    for d in demos:
        # Validate each demo's checks so `list` doubles as a lint of the set.
        for c in d.checks:
            validate_check(c)
        st = approved_staleness(cs, d)
        if st is None:
            approved = "-"
        elif st.is_stale:
            approved = "!"
            stale.append(st)
        else:
            approved = "y"
        enabled = "y" if d.enabled else "-"
        print(
            f"  {d.order:>3}  {d.id:24}  {d.runtime:8}  {enabled:2} {approved:2}"
            f"  {len(d.checks):>3}  {d.title}"
        )
    print()
    print(f"  {len(demos)} demo(s); en=enabled, ap=approved (!=stale), chk=#checks")
    _print_stale(stale)
    return EXIT_OK


def cmd_run(args: argparse.Namespace) -> int:
    cs = _resolve_content_set(args)
    demo = _find_demo(cs, args.demo)
    print(f"run {demo.id}: invoking Claude Code headless (this is the non-deterministic step)…")
    result = run_demo(demo, cs, follow_ups=not args.no_follow_ups)
    sent = sum(1 for e in result.events if e.type == "user_message")
    turns = f", {sent} follow-up(s)" if sent else ""
    print(f"  captured {len(result.events)} events{turns} -> {result.bundle.root}")
    if result.billed_to_api_key:
        print(
            f"  WARNING: the agent authenticated with {result.auth_source}, so this "
            "capture was billed to that API key, not the CLI's logged-in plan"
        )
    ended = next((e.data.get("reason") for e in result.events if e.type == "user_done"), None)
    if ended == "limit":
        print("  note: the follow-up limit was reached; the person never reviewed the last answer")
    iso = result.bundle.read_metadata().extra.get("isolation") or {}
    for f in iso.get("findings", []):
        print(f"  ISOLATION: {f['source']} record {f['record']} {f['reason']}: {f['snippet']}")
    if iso.get("findings"):
        print("  review these before approving: a session may have seen what the demo hides")
    _print_verify(result.outcome, demo, result.bundle.root / "working")
    if result.passed:
        print(f"  approve with: demoforge approve {demo.id} --run {result.run_id}")
    return EXIT_OK if result.passed else EXIT_ERROR


def cmd_approve(args: argparse.Namespace) -> int:
    cs = _resolve_content_set(args)
    demo = _find_demo(cs, args.demo)
    dest = approve_run(cs, demo.id, run_id=args.run, force=args.force)
    print(f"approved {demo.id} -> {dest}")
    # Approving an older run after editing the demo is the one way a freshly
    # approved bundle can already be stale.
    st = approved_staleness(cs, demo)
    _print_stale([st] if st is not None and st.is_stale else [])
    return EXIT_OK


def cmd_render(args: argparse.Namespace) -> int:
    cs = _resolve_content_set(args)
    formats = ("html", "pdf") if args.pdf else ("html",)
    summary = render_all(cs, only=args.demo, slide_formats=formats)

    if summary.records:
        print("records:")
        for demo_id, paths in summary.records.items():
            print(f"  {demo_id}: {paths['md']}")
    else:
        print("records: (none — no approved bundles yet)")
    if summary.skipped:
        print(f"skipped (enabled, not yet approved): {', '.join(summary.skipped)}")

    print("slides:")
    for fmt, path in summary.slides.items():
        print(f"  {fmt}: {path}")
    if not marp_available():
        print("  (Marp CLI unavailable — wrote deck.md only; install Node/npx for html/pdf)")
    _print_stale(stale_approved(cs))
    return EXIT_OK


def cmd_build(args: argparse.Namespace) -> int:
    cs = _resolve_content_set(args)
    formats = ("html", "pdf") if args.pdf else ("html",)
    report = build(cs, force=args.force, slide_formats=formats)

    if report.built:
        print("built:   " + ", ".join(report.built))
    if report.skipped:
        print("skipped: " + ", ".join(report.skipped) + "  (up to date)")
    if report.pruned:
        print("pruned:  " + ", ".join(report.pruned))
    if not report.did_work:
        print("nothing to do — all outputs up to date.")
    print(f"output -> {cs.output_dir}")

    if args.video:
        if not ffmpeg_available():
            raise DemoForgeError("ffmpeg not found on PATH — needed for --video")
        print("video:")
        _print_video(build_videos(cs, force=args.force), cs)

    _print_stale(report.stale)
    return EXIT_OK


def cmd_video(args: argparse.Namespace) -> int:
    cs = _resolve_content_set(args)
    if not ffmpeg_available():
        raise DemoForgeError(
            "ffmpeg not found on PATH — needed to assemble video. "
            "Records and slides build without it."
        )
    print("video: rendering replay frames (headless Chromium), then encoding…")
    summary = build_videos(
        cs, only=args.demo, presentation=not args.no_presentation, force=args.force
    )
    _print_video(summary, cs)
    return EXIT_OK


def _print_video(summary: VideoSummary, cs: ContentSet) -> None:
    if not summary.chapters:
        print("  (nothing to render — no approved bundles yet)")
    for c in summary.chapters:
        state = "cached" if c.video.cached else "encoded"
        print(
            f"  {c.demo_id:24} {c.seconds:>7.1f}s  {len(c.frames):>3} frames "
            f"({c.fresh_frames} new)  {state}"
        )
    if summary.cards:
        fresh = sum(1 for c in summary.cards if not c.cached)
        seconds = sum(c.seconds for c in summary.cards)
        print(
            f"  {'cards':24} {seconds:>7.1f}s  {len(summary.cards):>3} cards "
            f"({fresh} new)  title/chapter/closing"
        )
    if summary.presentation is not None:
        state = "cached" if summary.presentation.cached else "encoded"
        print(f"  {'presentation':24} {summary.seconds:>7.1f}s  {state}")
    if summary.skipped:
        print(f"skipped (enabled, not yet approved): {', '.join(summary.skipped)}")
    if summary.chapters and not summary.narrated:
        # Never let a silent build pass for a narrated one.
        note = summary.narration_note or "no voice available"
        print(f"note: narration track is silence — {note}")
    print(f"output -> {cs.output_dir / 'video'}")


def cmd_verify(args: argparse.Namespace) -> int:
    cs = _resolve_content_set(args)
    demo = _find_demo(cs, args.demo)

    if args.run:
        if args.artifacts:
            raise DemoError("pass --run or --artifacts, not both", path=demo.dir)
        root, outcome = reverify_run(cs, demo.id, run_id=args.run)
        _print_verify(outcome, demo, root / "working")
        print(f"  recorded in {root.name}: results.json replaced, metadata.json extra.reverified")
        return EXIT_OK if outcome.passed else EXIT_ERROR

    artifacts = Path(args.artifacts) if args.artifacts else (demo.dir / "reference")
    if not artifacts.is_dir():
        raise DemoError(
            f"no artifacts to verify: {artifacts} does not exist. "
            f"Pass --artifacts DIR (a run's output), or add a reference/ solution.",
            path=demo.dir,
        )

    work = cs.runs_dir / "_verify" / demo.id
    if work.exists():
        shutil.rmtree(work)
    outcome = verify_demo(demo, cs, artifacts_dirs=[artifacts], work_dir=work)
    _print_verify(outcome, demo, artifacts)
    return EXIT_OK if outcome.passed else EXIT_ERROR


def _print_verify(outcome: VerifyOutcome, demo: Demo, artifacts: Path) -> None:
    print(f"verify {demo.id}  (artifacts: {artifacts})")
    if outcome.harness_ran:
        status = "ok" if outcome.harness_ok else "FAILED"
        print(f"  harness {demo.harness}: {status}")
        if not outcome.harness_ok and outcome.harness_output:
            for line in outcome.harness_output.strip().splitlines()[-5:]:
                print(f"    | {line}")
    print()
    for c in outcome.results.checks:
        if c.passed is None:
            tag = "[metric]"
        elif c.passed:
            tag = "[PASS]  "
        else:
            tag = "[FAIL]  "
        print(f"  {tag} {c.id:22} {c.message}")
    print()
    verdict = "PASS" if outcome.passed else "FAIL"
    print(f"  => {verdict}")


def _print_stale(stale: list[Staleness]) -> None:
    """Warn that an approved capture no longer matches the demo it is filed under.

    Rendering is still faithful to the recorded run — but the record and the deck
    show the *captured* prompt, so a changed demo needs a fresh capture.
    """
    if not stale:
        return
    print()
    print(f"warning: {len(stale)} approved demo(s) no longer match the demo on disk:")
    for st in stale:
        print(f"  {st.demo_id}: {st.summary()}")
    print("  the deck still shows the captured prompt — re-capture with:")
    for st in stale:
        print(f"    demoforge run {st.demo_id} && demoforge approve {st.demo_id}")


def _find_demo(cs: ContentSet, demo_id: str) -> Demo:
    for d in cs.demos():
        if d.id == demo_id:
            return d
    known = ", ".join(d.id for d in cs.demos()) or "(none)"
    raise DemoError(f"no demo with id {demo_id!r}. Known: {known}")


# ---- helpers -----------------------------------------------------------
def _resolve_content_set(args: argparse.Namespace) -> ContentSet:
    if args.set_path:
        return load_content_set(Path(args.set_path))

    cwd = Path.cwd()
    if (cwd / "demoforge.toml").is_file():
        return load_content_set(cwd)

    candidates = sorted(p.parent for p in cwd.glob("examples/*/demoforge.toml"))
    if len(candidates) == 1:
        return load_content_set(candidates[0])
    if len(candidates) > 1:
        listing = "\n".join(f"  --set {c}" for c in candidates)
        raise ContentSetError(
            "multiple content sets found; pick one with --set:\n" + listing
        )
    raise ContentSetError(
        "no content set here. Run inside a dir with demoforge.toml, or pass --set PATH."
    )


def _fail(message: str) -> None:
    print(f"demoforge: error: {message}", file=sys.stderr)


def _force_utf8_streams() -> None:
    """Emit UTF-8 regardless of the console code page (Windows defaults to cp1252).

    ``errors='replace'`` is a last-resort backstop so output is never a hard crash.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


if __name__ == "__main__":
    raise SystemExit(main())
