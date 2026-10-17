"""Run capture and approval.

``run_demo`` stages a working copy, invokes the agent (via an injectable
``invoker`` so the pipeline is testable without a live agent), normalizes the
stream into a bundle, and verifies the result. ``approve_run`` freezes a chosen
bundle into ``approved/`` — the committed source of truth. A failed run never
touches an approved bundle (architecture.md §3.2).
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from demoforge.capture import isolation, turnjob
from demoforge.capture.conversation import (
    SIMULATOR_PROMPT_HASH, Responder, converse, default_user_simulator,
)
from demoforge.capture.normalize import normalize
from demoforge.capture.preflight import capture_env, preflight
from demoforge.discovery import ContentSet
from demoforge.errors import DemoError, DemoForgeError
from demoforge.redact import OWNER_PLACEHOLDER, PATH_LIST_PLACEHOLDER, PathRewriter, scrub_file_owners, scrub_path_lists
from demoforge.model import (
    CheckResult, Demo, Event, Results, RunBundle, RunMetadata, new_run_id,
)
from demoforge.staleness import hash_file as _sha256_file, hash_text as _sha256
from demoforge.verify import VerifyOutcome, verify_demo

# An invoker runs the agent in ``work_dir`` against ``prompt`` and returns the
# raw stream-json lines it emitted (side effect: it writes files into work_dir).
# Each line is either a bare string or ``(seconds_since_start, line)`` when the
# invoker measured when it arrived; only measured times are shown as real time.
# A follow-up turn is invoked with ``resume=True`` and continues the same session.
Invoker = Callable[..., list[str] | list[tuple[float, str]]]

# Fields of the CLI's init event that describe the operator's machine, not the
# run: their MCP servers, skills, plugins, agents and memory locations. They are
# dropped before anything is written, so a published bundle cannot leak them.
_PRIVATE_INIT_FIELDS = (
    "mcp_servers", "skills", "plugins", "agents", "slash_commands",
    "memory_paths", "output_style", "plugin_errors", "terminal_slash_commands",
    "messaging_socket_path", "powershell_path",
)

# Canonical bundle members copied when freezing (scratch dirs are excluded).
_FROZEN_MEMBERS = (
    "metadata.json",
    "prompt.md",
    "events.jsonl",
    "transcript.jsonl",
    "transcript.md",
    "results.json",
    "user.md",
)
# Folders frozen with the bundle: the simulated user's own session streams.
_FROZEN_DIRS = ("user_simulator",)
USER_SIM_DIR = "user_simulator"

# Where the engine itself lives: a run that names a path under it has looked
# outside its sandbox (capture/isolation.py).
_ENGINE_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class RunResult:
    run_id: str
    bundle: RunBundle
    outcome: VerifyOutcome
    events: list[Event]
    auth_source: str | None = None

    @property
    def passed(self) -> bool:
        return self.outcome.passed

    @property
    def billed_to_api_key(self) -> bool:
        """Whether the CLI reported authenticating with an API key, not its login."""
        return api_key_billed(self.auth_source)


def api_key_billed(auth_source: str | None) -> bool:
    """``apiKeySource`` names an API-key credential (e.g. ``ANTHROPIC_API_KEY``)."""
    return bool(auth_source) and auth_source.lower() != "none"


def sandbox_env(env: dict[str, str], sandbox: Path) -> dict[str, str]:
    """The agent's environment, with what it writes outside its folder kept in the sandbox.

    Scratch files: a shared temp folder is outside the demo, outlives it, and collides
    between captures that run at the same time (two demos backing up the same file name).

    Python packages: a `pip install` would otherwise land in the machine's own Python
    (the user site when the system one is read-only) and outlive the run. PIP_TARGET
    sends it to the sandbox, and PYTHONPATH lets the agent import what it installed
    there. Both go when the sandbox does. The machine's existing packages stay
    importable, so a demo that relies on them still runs.
    """
    tmp = sandbox / "tmp"
    site = sandbox / "site-packages"
    tmp.mkdir(exist_ok=True)
    site.mkdir(exist_ok=True)
    paths = [str(site), *([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])]
    return dict(env, TMP=str(tmp), TEMP=str(tmp), TMPDIR=str(tmp),
                PIP_TARGET=str(site), PYTHONPATH=os.pathsep.join(paths))


def run_demo(
    demo: Demo,
    content_set: ContentSet,
    *,
    invoker: Invoker | None = None,
    run_id: str | None = None,
    when: datetime | None = None,
    octave_bin: Path | None = None,
    git_commit: str | None = None,
    responder: Responder | None = None,
    follow_ups: bool = True,
) -> RunResult:
    """Capture one run of ``demo`` into ``runs/<demo>/<run-id>/`` and verify it.

    A demo with a ``user`` brief is a conversation: after each answer the
    responder (by default Claude playing the person in the brief) may reply, up
    to ``max_follow_ups`` times. ``follow_ups=False`` captures the first prompt
    alone.
    """
    when = when or datetime.now(timezone.utc)
    prompt_text = demo.prompt_path.read_text(encoding="utf-8")
    run_id = run_id or new_run_id(when, seed=_sha256(prompt_text))

    # Only the real agent needs a real environment; an injected invoker owns its
    # own. Check before touching the run dir, so a refusal changes nothing.
    env = capture_env(content_set.config.capture)
    real = invoker is None
    if real:
        check = preflight(demo, env)
        if not check.ok:
            raise DemoForgeError(check.message())
    brief = ""
    if demo.user_path is not None:
        if not demo.user_path.is_file():
            raise DemoError(f"user brief is missing: {demo.user_path}", path=demo.dir)
        brief = demo.user_path.read_text(encoding="utf-8")
    if not follow_ups:
        responder = None

    # The code that runs is the checkout as it is now, before the (long) capture:
    # an edit made while the agent works must not be recorded as what ran.
    git_state = (
        (git_commit, None) if git_commit is not None
        else (_git_commit(demo.dir), _git_dirty(demo.dir))
    )

    bundle_root = content_set.run_dir_for(demo.id, run_id)
    if bundle_root.exists():
        shutil.rmtree(bundle_root)
    bundle = RunBundle(bundle_root).create()

    # The agent works in a scratch folder OUTSIDE the repository, then the result
    # is copied into the bundle. A work dir inside the repo puts the project's path
    # in front of the agent, and a run that wanders up from it can read the demo's
    # hidden checks or earlier approved answers. The folder keeps the name
    # `working` so recorded paths display the same as before.
    sandbox_root = content_set.config.capture.sandbox_root
    if sandbox_root:
        Path(sandbox_root).mkdir(parents=True, exist_ok=True)
    sandbox = Path(tempfile.mkdtemp(prefix=f"demoforge-{demo.id}-", dir=sandbox_root or None))
    try:
        agent_work = sandbox / "working"
        agent_work.mkdir()
        if real:
            env = sandbox_env(env, sandbox)
            deny = isolation.deny_rules(_forbidden_roots(content_set))
            invoker = default_claude_invoker(env=env, deny=deny)
            if responder is None and demo.user:
                responder = default_user_simulator(
                    env=env, log_dir=bundle_root / USER_SIM_DIR, deny=deny,
                )
        input_hashes = _stage_inputs(demo, agent_work)
        raw_lines, sent = converse(
            prompt_text, agent_work, invoker,
            responder=responder, brief=brief, max_follow_ups=demo.max_follow_ups,
        )
        work = bundle_root / "working"
        shutil.copytree(agent_work, work)
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)

    timed, clocked = _timed_objects(raw_lines)
    objs = [obj for _, obj in timed]

    events = normalize(prompt_text, timed)
    bundle.write_events(events)
    _write_transcripts(bundle, objs, events)
    bundle.prompt_path.write_text(prompt_text, encoding="utf-8", newline="\n")
    if brief:
        # The bundle shows who the person was told they are.
        (bundle_root / "user.md").write_text(brief, encoding="utf-8", newline="\n")
    _collect_artifacts(work, input_hashes, bundle.artifacts_dir)

    # Metadata goes down before verification, so a harness that crashes leaves
    # a complete bundle that can be inspected and re-verified, not a lost run.
    meta = _build_metadata(demo, content_set, objs, when, prompt_text, git_state)
    meta.extra["run_id"] = run_id
    meta.extra["event_times"] = "wallclock" if clocked else "none"
    if brief:
        meta.user_hash = _sha256(brief)
    if responder is not None:
        meta.extra["follow_ups"] = sent
        meta.extra["max_follow_ups"] = demo.max_follow_ups
        meta.extra["user"] = f"simulated from {demo.user}" if demo.user else "simulated"
        meta.extra["user_simulator_prompt"] = SIMULATOR_PROMPT_HASH
    if real:
        version = _claude_version(env)
        if version:
            meta.extra["claude_cli"] = version
    meta.extra["isolation"] = _isolation(demo, content_set, objs, bundle_root / USER_SIM_DIR)
    bundle.write_metadata(meta)

    try:
        outcome = verify_demo(
            demo, content_set,
            artifacts_dirs=[work],
            work_dir=bundle_root / "verify",
            octave_bin=octave_bin,
        )
    except DemoForgeError as exc:
        outcome = VerifyOutcome(
            demo_id=demo.id,
            results=Results(checks=[CheckResult(
                id="verify", kind="harness", passed=False, message=f"verification crashed: {exc}",
            )]),
        )
    bundle.write_results(outcome.results)

    return RunResult(
        run_id=run_id, bundle=bundle, outcome=outcome, events=events,
        auth_source=meta.extra.get("auth_source"),
    )


def _isolation(demo: Demo, cs: ContentSet, objs: list[dict], sim_dir: Path) -> dict[str, Any]:
    """Audit every session of this run for a look at what the demo hides."""
    streams: dict[str, list[dict[str, Any]]] = {"agent": objs}
    if sim_dir.is_dir():
        for path in sorted(sim_dir.glob("turn-*.jsonl")):
            streams[f"user simulator {path.stem}"] = isolation.read_stream(path)
    checks = demo.dir / "checks"
    # A check file named like a staged input (a byte copy of the baseline, say) is
    # not hidden by its name: the sessions were handed a file called that.
    given = {
        f.name.lower() for p in demo.input_paths()
        for f in ([p, *p.rglob("*")] if p.is_dir() else [p])
    }
    hidden = [
        p.name for p in checks.rglob("*") if p.is_file() and p.name.lower() not in given
    ] if checks.is_dir() else []
    findings = isolation.audit(
        streams, _forbidden_roots(cs), hidden, _hidden_lines(demo),
    )
    return {
        "sessions": sorted(streams),
        "clean": not findings,
        "findings": [f.to_json() for f in findings],
    }


def _hidden_lines(demo: Demo) -> list[str]:
    """Distinctive lines of the demo's hidden checks (harness, mutants, expected data).

    Only ``checks/``: a reference *solution* shares lines with any correct answer
    (the required signature, the obvious asserts), so it would flag honest work.
    """
    given: list[Path] = [demo.prompt_path, *([demo.user_path] if demo.user_path else [])]
    for path in demo.input_paths():  # an input may be a whole directory tree
        given += [p for p in path.rglob("*") if p.is_file()] if path.is_dir() else [path]
    allowed = [p.read_text(encoding="utf-8", errors="replace") for p in given if p.is_file()]
    hidden = [
        p for p in (demo.dir / "checks").rglob("*") if p.is_file()
    ] if (demo.dir / "checks").is_dir() else []
    return isolation.fingerprints(hidden, allowed)


def _forbidden_roots(cs: ContentSet) -> list[Path]:
    """Where neither session may look: the engine's checkout and the content set."""
    roots = [_ENGINE_ROOT]
    root = cs.root.resolve()
    if not root.is_relative_to(_ENGINE_ROOT):
        roots.append(root)
    return roots


def _claude_version(env: dict[str, str]) -> str | None:
    """The CLI version the run used, as ``claude --version`` reports it."""
    exe = shutil.which("claude", path=env.get("PATH"))
    if exe is None:
        return None
    cmd = [exe, "--version"]
    if os.name == "nt" and exe.lower().endswith((".cmd", ".bat")):
        cmd = [env.get("COMSPEC", "cmd.exe"), "/c", *cmd]
    try:
        proc = subprocess.run(
            cmd, env=env, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() or None if proc.returncode == 0 else None


def approve_run(
    content_set: ContentSet,
    demo_id: str,
    *,
    run_id: str | None = None,
    force: bool = False,
) -> Path:
    """Freeze a run bundle into ``approved/<demo>/``. Refuses a failing run unless forced."""
    src_root = _resolve_run(content_set, demo_id, run_id)
    bundle = RunBundle(src_root)
    if not bundle.exists():
        raise DemoError(f"{src_root} is not a run bundle (no metadata.json)")

    results = bundle.read_results() if bundle.results_path.exists() else None
    if not force and (results is None or not results.passed):
        raise DemoForgeError(
            f"run {src_root.name} did not pass its checks; refusing to approve "
            f"(use force=True to override)"
        )

    # Audit again with the current rules, on the raw streams (the scrub below
    # rewrites the very paths the audit looks for), and freeze the verdict.
    demo = next((d for d in content_set.demos() if d.id == demo_id), None)
    audit = _bundle_isolation(demo, content_set, src_root) if demo else None

    dest = content_set.approved_dir_for(demo_id)
    rewriter = content_set.path_rewriter

    def scrub(staging: Path) -> None:
        _scrub_frozen(staging, rewriter)
        if audit is not None:
            _set_extra(staging / "metadata.json", "isolation_at_approve", audit)

    _atomic_freeze(src_root, bundle.artifacts_dir, dest, scrub=scrub)
    return dest


def reverify_run(
    content_set: ContentSet,
    demo_id: str,
    *,
    run_id: str | None = None,
    octave_bin: str | None = None,
) -> tuple[Path, VerifyOutcome]:
    """Check a captured run again with the demo's current checks, and record that.

    For when the checks were wrong, not the run: a harness bug found after capture.
    The run is untouched (the agent's files, the transcript); only results.json is
    replaced, and metadata.json keeps the earlier verdict beside the commit of the
    checks that gave the new one, so an approved bundle shows it was re-checked.
    """
    src_root = _resolve_run(content_set, demo_id, run_id)
    bundle = RunBundle(src_root)
    work = src_root / "working"
    if not bundle.exists() or not work.is_dir():
        raise DemoError(f"{src_root} is not a run bundle with its working folder")
    demo = next((d for d in content_set.demos() if d.id == demo_id), None)
    if demo is None:
        raise DemoError(f"unknown demo {demo_id!r}")

    before = bundle.read_results() if bundle.results_path.exists() else None
    verify_dir = src_root / "verify"
    if verify_dir.exists():
        shutil.rmtree(verify_dir)
    outcome = verify_demo(demo, content_set, artifacts_dirs=[work], work_dir=verify_dir,
                          octave_bin=octave_bin)
    bundle.write_results(outcome.results)
    _set_extra(bundle.root / "metadata.json", "reverified", {
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "checks_commit": _git_commit(demo.dir),
        "checks_dirty": _git_dirty(demo.dir),
        "passed_before": None if before is None else before.passed,
        "failed_before": [] if before is None else [c.id for c in before.checks if c.passed is False],
    })
    return src_root, outcome


def _bundle_isolation(demo: Demo, cs: ContentSet, root: Path) -> dict[str, Any]:
    stream = root / "transcript.jsonl"
    objs = isolation.read_stream(stream) if stream.exists() else []
    return _isolation(demo, cs, objs, root / USER_SIM_DIR)


def _set_extra(meta_path: Path, key: str, value: Any) -> None:
    if not meta_path.exists():
        return
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta.setdefault("extra", {})[key] = value
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )


def _scrub_frozen(staging: Path, rewriter: PathRewriter) -> None:
    """Remove the machine's own paths from a bundle about to be committed.

    Every text file gets the set's ``[display] paths`` rules and loses any
    search-path listing. The operator's home folder, wherever no rule already
    renamed it, becomes ``~``. Only the spelling of paths changes, never an
    action, and ``metadata.json`` says so.
    """
    home = PathRewriter({str(Path.home()): "~"})
    streams = [staging / "transcript.jsonl", *sorted((staging / USER_SIM_DIR).glob("*.jsonl"))]
    for stream in streams:
        if not stream.exists():
            continue
        records = (
            _scrub_account(json.loads(line))
            for line in stream.read_text(encoding="utf-8").splitlines() if line.strip()
        )
        stream.write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records if r is not None),
            encoding="utf-8", newline="\n",
        )
    for path in sorted(p for p in staging.rglob("*") if p.is_file()):
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue  # binary artifact (an image, a workbook): nothing to rewrite
        clean = home(rewriter(scrub_file_owners(scrub_path_lists(_scrub_saved_output(text)))))
        if clean != text:
            path.write_bytes(clean.encode("utf-8"))
    meta_path = staging / "metadata.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta.setdefault("extra", {})["redaction"] = (
            f"display paths rewritten (an unmapped home folder becomes ~), search-path "
            f"listings replaced by {PATH_LIST_PLACEHOLDER!r}, Claude Code's saved-output "
            f"paths replaced by {SAVED_OUTPUT_PLACEHOLDER!r}, file owners in long listings "
            f"shown as {OWNER_PLACEHOLDER!r}, account details (rate "
            f"limits, cost, session ids, tool list) and the text of Claude's private "
            f"reasoning removed from the raw transcripts"
        )
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n",
        )


# When a tool's output is too large, Claude Code saves it under its own data
# folder and shows the agent that path. The path names the operator's folder
# layout and the session id; what was saved is already in the record.
SAVED_OUTPUT_PLACEHOLDER = "<output saved by Claude Code>"


def _saved_output_pattern(sep: str) -> re.Pattern[str]:
    seg = rf"{sep}[\w.-]+"
    return re.compile(
        rf"(?:[A-Za-z]:|~)?(?:{seg})*?{sep}\.claude{sep}projects(?:{seg})+"
    )


# JSON text spells a backslash as two (a lone one starts an escape such as \n);
# a raw file spells it as one. Each spelling is matched on its own, so the path
# never runs on into the escape that follows it.
_SAVED_OUTPUT = (
    _saved_output_pattern(r"(?:\\\\|/)"),
    _saved_output_pattern(r"(?:\\|/)"),
)


def _scrub_saved_output(text: str) -> str:
    for pattern in _SAVED_OUTPUT:
        text = pattern.sub(SAVED_OUTPUT_PLACEHOLDER, text)
    return text


# Raw stream content that describes the operator's account and build, not the
# run: dropped from the frozen raw transcripts.
_ACCOUNT_RECORD_TYPES = ("rate_limit_event",)
_ACCOUNT_FIELDS = ("session_id", "request_id", "total_cost_usd", "modelUsage")
_ACCOUNT_INIT_FIELDS = ("tools", "capabilities")


def _scrub_account(record: Any) -> Any:
    """One raw stream record without account details; None to drop it."""
    if not isinstance(record, dict):
        return record
    if record.get("type") in _ACCOUNT_RECORD_TYPES:
        return None
    drop = _ACCOUNT_FIELDS
    if record.get("type") == "system" and record.get("subtype") == "init":
        drop += _ACCOUNT_INIT_FIELDS
    out = {k: v for k, v in record.items() if k not in drop}
    # The replay never shows Claude's private reasoning (normalize.py); the
    # published raw transcript keeps only that a thinking block was there.
    msg = out.get("message")
    if isinstance(msg, dict) and isinstance(msg.get("content"), list):
        out["message"] = dict(msg, content=[
            {"type": "thinking", "thinking": "", "removed": True}
            if isinstance(b, dict) and b.get("type") in ("thinking", "redacted_thinking") else b
            for b in msg["content"]
        ])
    return out


def _atomic_freeze(
    src_root: Path,
    artifacts_dir: Path,
    dest: Path,
    *,
    scrub: Callable[[Path], None] | None = None,
) -> None:
    """Freeze a bundle into ``dest`` without ever leaving it partial.

    The approved bundle is immutable (architecture.md §3.2): a failed freeze must
    not destroy the previously-approved one. So we fully assemble the new bundle in
    a sibling staging dir, then swap it into place with two atomic renames and roll
    back on any error — the old bundle survives intact if assembly fails, and no
    reader ever observes a half-written ``dest``.
    """
    parent = dest.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = parent / f".{dest.name}.incoming"
    backup = parent / f".{dest.name}.backup"
    for scratch in (staging, backup):
        if scratch.exists():
            shutil.rmtree(scratch)

    # 1. Assemble the complete new bundle off to the side. If anything here throws,
    #    `dest` has not been touched.
    try:
        staging.mkdir(parents=True)
        for name in _FROZEN_MEMBERS:
            src = src_root / name
            if src.exists():
                shutil.copy2(src, staging / name)
        for name in _FROZEN_DIRS:
            if (src_root / name).is_dir():
                shutil.copytree(src_root / name, staging / name)
        if artifacts_dir.is_dir():
            shutil.copytree(artifacts_dir, staging / "artifacts")
        if scrub is not None:
            scrub(staging)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    # 2. Swap atomically: move the current bundle aside, move the new one in, and
    #    only then discard the old. Roll back if the final rename fails. The backup
    #    is deleted only once the swap is confirmed; if the rollback itself fails,
    #    the backup is the only copy of the prior bundle, so it is kept and named.
    try:
        if dest.exists():
            _rename(dest, backup)
        _rename(staging, dest)
    except BaseException as exc:
        shutil.rmtree(staging, ignore_errors=True)
        if not dest.exists() and backup.exists():
            try:
                _rename(backup, dest)  # restore the prior approved bundle
            except OSError as restore_exc:
                raise DemoForgeError(
                    f"approve failed and the previous approved bundle could not be "
                    f"restored; it is preserved at {backup}: {restore_exc}"
                ) from exc
        raise
    shutil.rmtree(backup, ignore_errors=True)


def _rename(src: Path, dst: Path, attempts: int = 10, wait: float = 0.5) -> None:
    """``os.replace``, retried briefly: on Windows a virus scanner or the search
    indexer can hold a just-written folder open for a moment, and the rename then
    fails with "access denied" although nothing is wrong."""
    for attempt in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(wait)


# ---- default (real) invoker -------------------------------------------
def default_claude_invoker(
    claude_bin: str = "claude",
    *,
    allowed_tools: str = "Read,Edit,Write,Bash,PowerShell,Grep,Glob",
    timeout: float | None = 1800.0,
    env: dict[str, str] | None = None,
    deny: str = "",
) -> Invoker:
    """Invoke the real Claude Code CLI headlessly (architecture.md §3.1).

    ``env`` is the agent's environment — normally from
    :func:`demoforge.capture.preflight.capture_env`, so the agent can find tools
    pinned by the content set even when DemoForge's own shell cannot.
    """

    # One session per invoker, so a follow-up continues the same conversation.
    session_id = str(uuid.uuid4())
    # The longest single command: two thirds of a turn, leaving time to report.
    max_cmd_ms = int(timeout * 1000 * 2 / 3) if timeout else 0

    def invoke(prompt: str, work_dir: Path, *, resume: bool = False) -> list[tuple[float, str]]:
        child_env = dict(os.environ) if env is None else dict(env)
        # Git must not walk up out of the sandbox: a repository higher up (the
        # user's home, a parent project) would show the agent files that are not
        # part of the demo, and whatever it prints is recorded.
        child_env["GIT_CEILING_DIRECTORIES"] = str(work_dir.parent)
        # A headless turn ends when the agent stops talking, and takes any background
        # job with it, so the agent would be left waiting on output that never comes.
        # Long commands run in the foreground instead, up to most of a turn.
        child_env["CLAUDE_CODE_DISABLE_BACKGROUND_TASKS"] = "1"
        if max_cmd_ms:
            child_env["BASH_MAX_TIMEOUT_MS"] = str(max_cmd_ms)
        # Resolve on the same PATH the child will get, so the CLI we find is the
        # CLI it runs.
        exe = shutil.which(claude_bin, path=child_env.get("PATH"))
        if exe is None:
            raise DemoForgeError(
                f"claude CLI {claude_bin!r} not found on PATH; is Claude Code installed?"
            )
        cmd = [
            exe, "-p",
            "--output-format", "stream-json",
            "--verbose",
            "--allowedTools", allowed_tools,
            # A capture shows what Claude does with the demo alone. The operator's
            # own CLAUDE.md, skills, plugins, hooks and MCP servers would steer the
            # agent in ways a viewer can't see or reproduce.
            "--safe-mode",
            "--strict-mcp-config",
            # Say how the session really works: nothing runs between replies.
            *(["--append-system-prompt", turnjob.TURN_NOTE.format(minutes=max_cmd_ms // 60000)]
              if max_cmd_ms else []),
            *(["--resume", session_id] if resume else ["--session-id", session_id]),
            # Permission rules keeping the file tools out of the repository
            # (capture/isolation.py); the post-capture audit covers the shell.
            *(["--disallowedTools", deny] if deny else []),
        ]
        # On Windows the resolved CLI is a .cmd/.bat shim, which CreateProcess
        # cannot launch directly — route it through the command interpreter.
        if os.name == "nt" and exe.lower().endswith((".cmd", ".bat")):
            cmd = [child_env.get("COMSPEC", "cmd.exe"), "/c", *cmd]
        try:
            return _stream_timed(cmd, prompt, work_dir, child_env, timeout)
        except subprocess.TimeoutExpired as exc:
            raise DemoForgeError(
                f"claude did not finish within {timeout:g}s; aborting capture"
            ) from exc
        except OSError as exc:
            raise DemoForgeError(f"failed to launch claude ({exe}): {exc}") from exc

    return invoke


def _stream_timed(
    cmd: list[str], prompt: str, cwd: Path, env: dict[str, str], timeout: float | None,
) -> list[tuple[float, str]]:
    """Run ``cmd`` and stamp each stdout line with seconds since launch.

    stream-json carries no timestamps, so the time a line *arrives* is the only
    honest measure of when the agent did that step. It is what the video's
    "this step took Ns" note is allowed to quote.
    """
    proc = subprocess.Popen(
        cmd, cwd=str(cwd), env=env,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        # Claude emits UTF-8 JSON; decode as such regardless of the console code
        # page (Windows defaults to cp1252, which mangles —, ×, emoji).
        text=True, encoding="utf-8", errors="replace",
        **turnjob.popen_kwargs(),
    )
    job = turnjob.TurnJob(proc)
    stderr: list[str] = []
    drain = threading.Thread(target=lambda: stderr.append(proc.stderr.read()), daemon=True)
    drain.start()
    timed_out = threading.Event()

    def _kill() -> None:
        timed_out.set()
        job.close()
        proc.kill()

    timer = threading.Timer(timeout, _kill) if timeout else None
    if timer:
        timer.start()
    start = time.monotonic()
    lines: list[tuple[float, str]] = []
    try:
        proc.stdin.write(prompt)
        proc.stdin.close()
        for line in proc.stdout:
            lines.append((round(time.monotonic() - start, 3), line.rstrip("\r\n")))
        proc.wait()
    finally:
        if timer:
            timer.cancel()
        # Whatever the agent left running ends with its turn (capture/turnjob.py).
        job.close()
    drain.join(timeout=5)
    if timed_out.is_set():
        raise subprocess.TimeoutExpired(cmd, timeout)
    if proc.returncode != 0:
        raise DemoForgeError(
            f"claude exited {proc.returncode}: {''.join(stderr).strip()[:500]}"
        )
    return lines


# ---- helpers ----------------------------------------------------------
# Tool caches an agent's commands leave behind; they are not its work.
_SCRATCH_DIRS = {"__pycache__", ".pytest_cache", ".git", "octave-workspace"}


def _stage_inputs(demo: Demo, work: Path) -> dict[str, str]:
    """Stage the demo's inputs into the agent's working copy, preserving structure.

    Returns each staged relative path with its content hash, so
    :func:`_collect_artifacts` can tell the agent's output, including edits it
    made to a file it was given, apart from the files as they were handed over.
    """
    staged: dict[str, str] = {}
    for src, rel in demo.staged_inputs():
        if not src.exists():
            raise DemoError(f"declared input is missing: {src}", path=demo.dir)
        dest = work / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        staged[Path(rel).as_posix()] = _sha256_file(dest)
    return staged


def _collect_artifacts(work: Path, inputs: dict[str, str], dest: Path) -> None:
    """Copy every file the agent created or changed, keeping its relative path.

    A staged input the agent left untouched is not an artifact; one it edited is.
    """
    dest.mkdir(parents=True, exist_ok=True)
    for f in sorted(p for p in work.rglob("*") if p.is_file()):
        rel = f.relative_to(work)
        if _SCRATCH_DIRS.intersection(rel.parts[:-1]):
            continue
        key = rel.as_posix()
        if key in inputs and inputs[key] == _sha256_file(f):
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target)


def _timed_objects(lines: list) -> tuple[list[tuple[float, dict[str, Any]]], bool]:
    """Parse stream-json lines into ``(t, obj)`` pairs.

    Returns whether the times are measured. Without measurement ``t`` is just
    the line's position, which orders events but says nothing about duration.
    """
    clocked = bool(lines) and all(isinstance(x, tuple) for x in lines)
    out: list[tuple[float, dict[str, Any]]] = []
    for i, item in enumerate(lines):
        t, line = item if isinstance(item, tuple) else (float(i), item)
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue  # tolerate non-JSON noise on the stream
        if isinstance(obj, dict):
            out.append((float(t), _scrub_init(obj)))
    return out, clocked


def _scrub_init(obj: dict[str, Any]) -> dict[str, Any]:
    if obj.get("type") == "system" and obj.get("subtype") == "init":
        return {k: v for k, v in obj.items() if k not in _PRIVATE_INIT_FIELDS}
    return obj


def _write_transcripts(bundle: RunBundle, objs: list[dict], events: list[Event]) -> None:
    with bundle.transcript_jsonl_path.open("w", encoding="utf-8", newline="\n") as fh:
        for obj in objs:
            fh.write(json.dumps(obj, ensure_ascii=False, sort_keys=True))
            fh.write("\n")
    bundle.transcript_md_path.write_text(_render_markdown(events), encoding="utf-8", newline="\n")


def _render_markdown(events: list[Event]) -> str:
    lines: list[str] = ["# Transcript", ""]
    for ev in events:
        d = ev.data
        if ev.type == "prompt":
            lines += ["## Prompt", "", d.get("text", ""), ""]
        elif ev.type == "user_message":
            lines += ["", "## Follow-up", "", d.get("text", ""), ""]
        elif ev.type == "user_done":
            reason = d.get("reason", "")
            lines += ["", "## End of conversation", "",
                      "The person had nothing more to ask." if reason == "satisfied"
                      else "The follow-up limit was reached.", ""]
        elif ev.type == "assistant_text":
            lines += [d.get("text", ""), ""]
        elif ev.type in ("file_read", "file_write", "file_edit"):
            lines.append(f"- `{ev.type}` {d.get('path', '')}")
        elif ev.type == "file_search":
            lines.append(f"- `search` {d.get('query', '')}")
        elif ev.type == "command":
            cmd = str(d.get("command", ""))
            if "\n" in cmd or "`" in cmd:
                # A multi-line command (or one with back ticks) breaks an inline span.
                lines += ["- command:", "", "  ```", *("  " + c for c in cmd.splitlines()), "  ```", ""]
            else:
                lines.append(f"- `$ {cmd}`")
        elif ev.type == "command_output":
            pass  # output is bulky; kept in events.jsonl, not the readable transcript
        elif ev.type == "tool_call":
            lines.append(f"- `tool` {d.get('tool', '')}")
        elif ev.type == "completion":
            lines += ["", "## Done", ""]
    return "\n".join(lines).rstrip() + "\n"


def _build_metadata(
    demo: Demo,
    cs: ContentSet,
    objs: list[dict],
    when: datetime,
    prompt_text: str,
    git_state: tuple[str | None, bool | None],
) -> RunMetadata:
    return RunMetadata(
        demo_id=demo.id,
        model=_extract_model(objs),
        created=when.strftime("%Y-%m-%dT%H:%M:%SZ"),
        capture_mode="headless",
        git_commit=git_state[0],
        git_dirty=git_state[1],
        prompt_hash=_sha256(prompt_text),
        input_hashes={
            rel: _sha256_file(p) for p, rel in demo.staged_inputs() if p.exists()
        },
        runtimes=dict(cs.config.runtimes),
        os=f"{platform.system()} {platform.release()}",
        extra=_auth_extra(objs),
    )


def _auth_extra(objs: list[dict]) -> dict[str, str]:
    """Record how the CLI said it authenticated, so billing is auditable later."""
    for obj in objs:
        if obj.get("type") == "system" and "apiKeySource" in obj:
            return {"auth_source": str(obj["apiKeySource"])}
    return {}


def _extract_model(objs: list[dict]) -> str | None:
    for obj in objs:
        if obj.get("type") == "system" and obj.get("model"):
            return str(obj["model"])
    return None


def _resolve_run(cs: ContentSet, demo_id: str, run_id: str | None) -> Path:
    if run_id:
        return cs.run_dir_for(demo_id, run_id)
    demo_runs = cs.runs_dir / demo_id
    if not demo_runs.is_dir():
        raise DemoError(f"no runs for demo {demo_id!r} under {demo_runs}")
    candidates = sorted(p for p in demo_runs.iterdir() if (p / "metadata.json").exists())
    if not candidates:
        raise DemoError(f"no run bundles found under {demo_runs}")
    return candidates[-1]  # run-ids sort chronologically


def _git_dirty(start: Path) -> bool | None:
    """Whether the checkout had uncommitted changes, so ``git_commit`` is not the
    whole story of what code ran."""
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=normal"],
            cwd=str(start), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return bool(proc.stdout.strip()) if proc.returncode == 0 else None


def _git_commit(start: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(start), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None
