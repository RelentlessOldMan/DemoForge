# DemoForge — Architecture & Engine Spec

**Status:** Built · **Last revised:** 2026-10-13

DemoForge is a generic, domain-agnostic pipeline that captures what a Claude agent
**actually did** on a real task, freezes it immutably, and deterministically renders it
into shareable artifacts — records, slides, and narrated video — without ever re-running
the agent or fabricating a single action.

**ClaudeDemoKit** (`examples/claude-demo-kit/`) is the first *content set* built on
DemoForge: a suite of engineering demos that also serves as DemoForge's own
self-demonstration. The companion document [`video-pipeline.md`](./video-pipeline.md)
specifies the presentation/narration/video layer in depth.

---

## 1. The core idea

> Capture what a Claude agent actually did, freeze it, and deterministically render it
> into records, slides, and video — never re-running the agent, never fabricating an
> action it didn't perform.

Everything follows from one constraint: **Claude execution is not byte-deterministic,
but everything downstream of a frozen run must be.** DemoForge quarantines all
non-determinism inside a single `run` step and makes every later step a pure function of
committed files.

```
NON-DETERMINISTIC          |  DETERMINISTIC (pure, from frozen inputs)
                           |
  run  ──────────────────► |  approve ──► render ──► build
  (Claude executes,        |  (freeze    (records,   (assemble
   events captured)        |   bundle)    slides,     final
                           |              narration)  video)
```

## 2. The DemoForge / content-set split

DemoForge (the engine) knows **nothing** about MATLAB, Excel, or "demos." It understands
only *jobs* and *run bundles*. Domain content lives in a **content set** — a directory
of declarative job definitions plus config. ClaudeDemoKit is one content set; others
(onboarding material, capability changelogs, reproducible eval write-ups) can sit beside
it under `examples/` or in their own repos.

| Layer | Path | Domain-aware? | Role |
|---|---|---|---|
| **Engine** — capture, freeze, render, build | `demoforge/` | no | reusable pipeline |
| **Content set** — job definitions + config | `examples/<set>/` | yes | the story being told |
| **Output** — generated, rebuildable artifacts | `examples/<set>/output/` | n/a | disposable |

Because the engine is domain-agnostic, the same code that renders a MATLAB optimization
demo could render "how our agent triaged a production incident." A content set is just a
consumer of DemoForge.

### 2.1 What is a content set?
A directory DemoForge can discover and build:

```
examples/claude-demo-kit/
    demoforge.toml     # set-level config: title, ordering, defaults, voice
    demos/             # one folder per job (auto-discovered)
    approved/          # frozen approved run bundles (COMMITTED)
    runs/              # raw run bundles (git-ignored)
    output/            # rendered records/slides/video (git-ignored)
    SPEC.md / README   # what this set is
```

## 3. Pipeline stages

### 3.1 `run` — the only non-deterministic step
Invokes Claude Code in **headless mode** and captures a normalized event stream:

```
claude -p --output-format stream-json --verbose \
       --allowedTools "Read,Edit,Write,Bash,PowerShell,Grep,Glob" \
       --safe-mode --strict-mcp-config \
       < prompt.md
```

The raw stream-json is normalized (§5) into a **run bundle**. This is the one place
wall-clock, model choice, and model output vary. We record enough metadata (§7) to
understand the run, not to reproduce Claude's tokens exactly.

- **Isolation.** A capture shows what Claude does with the demo and nothing else.
  The agent works in a fresh folder outside the repository (`[capture]
  sandbox_root`, default the system temp dir), so it cannot wander into the demo's
  hidden `checks/` or `reference/`, or into earlier approved answers.
  `GIT_CEILING_DIRECTORIES` stops git from finding a repository above that folder.
  `--safe-mode` turns off the operator's own CLAUDE.md, skills, plugins and hooks,
  and `--strict-mcp-config` turns off their MCP servers: those would steer the
  agent in ways a viewer cannot see or reproduce. API-billing variables are
  removed from the agent's environment so it runs on the CLI's own login.
- **Nothing runs between replies.** A headless turn ends when the agent stops
  talking, and nothing wakes it later, so work still running then would never
  reach the conversation. Captures make that explicit and enforce it:
  `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` removes background jobs,
  `BASH_MAX_TIMEOUT_MS` lets one foreground command run for two thirds of the
  turn's time limit, and `--append-system-prompt` tells the agent so
  (`capture/turnjob.py` `TURN_NOTE`): finish long work before replying, or say it
  won't fit and propose a run that does. The CLI runs in a Windows job object (a
  process group elsewhere) that is closed when the turn ends, so a detached
  `Start-Process` or `nohup` cannot outlive it.
- **What is recorded.** The CLI's init event lists the operator's tools, skills,
  plugins and memory locations; those fields are dropped before anything is
  written. Each stream line is stamped with the seconds since launch as it
  arrives, which is the only honest measure of how long a step took.
- **A conversation, not a one-shot.** Working with Claude is a back-and-forth, so
  a demo with a `user:` brief (§4) is captured as one. After each answer a
  *responder* playing that person decides what to say next: a question, a doubt, a
  fix to make, or `DONE`. Up to `max_follow_ups` replies continue the same Claude
  session (`--resume`). The default responder is a second Claude session that sees
  what a person at the terminal would: the conversation, plus read-only access to
  the working folder. It never sees the hidden checks, and has none of the
  operator's customizations. Each message it sends goes into the raw stream as a
  `follow_up` record at the moment it was sent and becomes a `user_message` event,
  so the replay shows it like any other recorded step. How the conversation ended
  is recorded too, as a `user_done` event: `satisfied` when the person said they
  were done, `limit` when the follow-up cap was reached and nobody was asked.
  The responder's own session streams are kept in the bundle as
  `user_simulator/turn-N.jsonl`, so every file it opened can be checked.
  `metadata.json` records how many follow-ups there were, the cap, the hash of the
  brief (`user_hash`, which staleness checks like `prompt_hash`) and the hash of
  the responder's instructions; the brief itself is frozen as `user.md`.
- **Isolation is audited, not assumed.** The agent works in a sandbox outside the
  repository, with its temp folder (`TMP`, `TEMP`, `TMPDIR`) inside that sandbox,
  but a tool can still name any absolute path. After every capture each session's
  tool calls and tool results are searched for a path inside the repository or
  content set, and for the name of any file in the demo's `checks/` that was not
  also staged as an input (`capture/isolation.py`). Findings go into `metadata.json` `extra.isolation`
  and are printed by `run`; a person judges them before approving.
- **Verification is the harness's word.** Inputs and artifacts are staged into a
  fresh folder with their relative paths (an edit to `src/gate.m` replaces
  `src/gate.m`). Any metrics file the agent left is deleted before the demo's own
  harness runs, and a harness that exits non-zero is recorded as a failing
  `harness` check, so `results.json` cannot say "passed" for a run the harness
  rejected. Metadata is written before verification, so a harness that crashes
  leaves a complete bundle to inspect.

- A failed run **never** overwrites a previously approved bundle.
- Each run gets an immutable id: `runs/<demo>/<timestamp>-<shorthash>/`.
- **Preflight.** `run` is the one stage that spends unrecoverable agent time, so
  anything knowably wrong about the environment is caught *before* the agent is
  invoked. A demo declares the external executables its agent needs
  (`requires:`, §4); the content set says where they live on this machine
  (`[capture] path_prepend`, §10). Missing tools abort the run having changed
  nothing. Without this a capture can fail for an environmental reason that is
  indistinguishable, in the verdict, from the demo being too hard — the worst
  kind of wasted capture. The engine resolves names against the *agent's* PATH
  and knows nothing about any particular tool.
- The "very first" capture of a demo may be driven interactively and is explicitly
  labeled (`capture_mode: interactive|headless`) in metadata. The *re-run, freeze,
  render, and build* steps are always scripted.

### 3.2 `approve` — freeze
Promotes a chosen run bundle to `approved/<demo>/` (immutable, committed to git).
Downstream stages read **only** approved bundles. Approving is a human gate: "yes, this
run is a good demonstration." A run whose recorded results did not pass is refused
unless forced. The new bundle is assembled beside the old one and swapped in by
rename; if the swap and its rollback both fail, the previous bundle is kept as
`.<demo>.backup` and the error says so.

The frozen copy is scrubbed before it is swapped in, because it is committed. Every
text file gets the set's `[display] paths` rules, the operator's home folder becomes
`~` wherever no rule renamed it, and any search-path listing (an echoed `PATH`, a
`which: no x in (...)`) becomes `<search path removed>`. The raw `transcript.jsonl`
(and each `user_simulator/` stream) also loses what describes the operator's
account rather than the run: rate-limit records, cost, session and request ids, the
init tool list, and the text of Claude's private reasoning blocks (the replay never
shows reasoning; the raw record keeps only that a block was there). Where Claude
Code saved an oversized tool output under its own data folder, the path it showed
(which names the session) becomes `<output saved by Claude Code>`. The path rules
also cover Claude Code's project-folder spelling of a path (`C--a-b` for `C:\a\b`).
Only how a path is spelled changes, never an action, and `metadata.json`
`extra.redaction` records it. The run under `runs/` keeps the original.

### 3.3 `render` — deterministic artifact generation
Pure functions from `approved/` + config + templates → `output/`:
- **record** — bundle → Markdown + static HTML (canonical per-demo deliverable)
- **slides** — enabled demos → Marp deck → HTML/PDF/PNG
- **narration** — narration text → cached audio (pluggable TTS, see video spec)
- **video** — timeline (derived from events) + slides + narration → mp4 (see video spec)

### 3.4 `build` — orchestrated, incremental, idempotent
A small dependency-graph builder (make-like) that discovers demos, computes what is
stale via input hashes, and rebuilds only what changed. Running `build` twice with no
input changes does no work and produces identical bytes.

### 3.5 CLI
`--set` is a global option and goes before the subcommand:

```
demoforge --set <dir> list                     # demos, order, enabled/approved/stale
demoforge --set <dir> verify <demo>            # check the reference solution, no agent
demoforge --set <dir> run <demo>               # capture a real run + verify it
demoforge --set <dir> approve <demo> [--run <id>]  # freeze the latest/selected run
demoforge --set <dir> render [<demo>]          # records/slides from approved bundles
demoforge --set <dir> video [<demo>]           # narrated chapters + presentation
demoforge --set <dir> build [--video]          # incremental build of everything
```

Invoked as `demoforge` (console script) or `python -m demoforge`.

## 4. Demo definition schema (`demos/NN_name/demo.yaml`)

Declarative. Discovery is automatic (any folder under a set's `demos/` with a
`demo.yaml`). Adding/removing/reordering a folder is the *only* action needed to change
the presentation — no manual edits to slide decks or TOCs.

```yaml
id: matlab-optimization
title: MATLAB Algorithm Optimization
order: 2
enabled: true

# What Claude is asked to do (a realistic engineering job, not "demonstrate X")
prompt: prompt.md

# Files staged into Claude's working copy before the run
inputs:
  - input/kalman_update.m
  - input/test_vectors.csv

# External executables the AGENT must be able to run (optional). Names only —
# where they live is per-machine and belongs in [capture] path_prepend (§10).
# Checked before the agent is invoked, so a missing tool costs no agent time.
requires:
  - pdftoppm           # e.g. a demo whose spec is a PDF: Read rasterizes it

# How the run's working environment is executed/validated. Pluggable runtimes.
runtime: octave        # octave | python | node | none

# Property-based success criteria — NOT byte-exact file comparison. See §6.
checks:
  - id: equivalence
    kind: numeric_tolerance
    description: Optimized output matches original within tolerance
    max_abs_error: 1.0e-9
  - id: speedup
    kind: threshold
    description: Optimized runtime is meaningfully faster
    metric: speedup
    min: 3.0
  - id: tests_pass
    kind: command
    run: "octave --eval run_tests"
    expect_exit: 0

# Declarative narration (text in repo; TTS is cached — see video spec)
narration: narration.md

# Who the person asking is (optional). With it, capture is a conversation: a
# simulated user reads each answer and may reply, up to max_follow_ups times (§3.1).
# Never staged, so the agent does not see it.
user: user.md
max_follow_ups: 3

presentation:
  enabled: true
  highlights:            # which captured moments to feature (optional; auto if omitted)
    - tool: Bash
      match: "benchmark"
```

Design rules:
- **No presentation logic inside a demo.** A demo declares *what* to show
  (`highlights`), never *how* slides look.
- Everything a demo needs is inside its folder: prompt, inputs, checks, narration.

## 5. Run bundle format

```
runs/<demo>/<run-id>/
    metadata.json      # model, CLI version, hashes, git commit (+ dirty flag), isolation audit (§7)
    prompt.md          # exact prompt submitted (copied, hashed)
    user.md            # the simulated person's brief, when the demo has one
    user_simulator/    # that person's own session streams, one per turn
    transcript.jsonl   # raw normalized assistant/user turns
    transcript.md      # human-readable rendering
    events.jsonl       # canonical event timeline (§5.1)
    artifacts/         # every file Claude created or modified, as left on disk
    results.json       # check outcomes + measured metrics (§6)
```

### 5.1 Canonical event model
The raw `stream-json` from Claude Code is mapped into a small, stable vocabulary so the
renderer never depends on CLI-internal shapes. Each event:

```json
{"seq": 12, "t": 6.1, "type": "file_read", "path": "kalman_update.m"}
```

Canonical `type` values:
`prompt`, `assistant_text`, `tool_call`, `file_read`, `file_search`, `file_write`,
`file_edit`, `command`, `command_output`, `test_result`, `artifact`, `completion`.

- `t` orders events. When `metadata.json` has `extra.event_times = "wallclock"` it is
  also measured seconds since launch, and only then may the video say how long a step
  really took. Bundles without it carry the line index, and the video makes no time claim.
- Unknown/aux tool calls collapse to a generic `tool_call` with a label.
- **Sensitive/internal reasoning is neither required nor captured** — only observable
  interaction and tool activity (spec §9).

## 6. Checks: property-based verification (not byte-diff)

Because Claude's output varies run-to-run, we assert **measurable properties** of the
result, not exact bytes. `results.json` records each check's pass/fail and any measured
value, which feeds the "measurable results" on slides.

Check kinds (extensible plugin registry):

| kind | asserts | example |
|---|---|---|
| `command` | a command exits 0 (tests pass) | `octave --eval run_tests` |
| `threshold` | a measured metric ≥/≤ bound | speedup ≥ 3.0 |
| `numeric_tolerance` | two artifacts agree within tol | max abs err < 1e-9 |
| `file_exists` | an expected artifact was produced | `optimized_*.m` present |
| `contains` | a report cites required evidence | root-cause names the units bug |
| `metric` | extracts a number for display (no pass/fail) | runtime_ms |

A demo "passes" if all its non-`metric` checks pass. Metrics are surfaced regardless.

## 7. Reproducibility metadata (`metadata.json`)

Recorded where practical: Claude model id, capture date/time, the run id, git commit,
runtime pins, OS, how the CLI authenticated, whether event times are measured, prompt
hash, and per-input hashes. Goal is *engineering* reproducibility, not pretending model
output is deterministic.

The video build also writes `output/video/manifest.json`: the commit and clean/dirty
state it was built from, the video's SHA-256, the narration provider, and each chapter's
run id and bundle hash. The video is not committed, so this is what ties a released MP4
to a commit, and `release.ps1` refuses to publish one whose manifest does not match HEAD.

### 7.1 Staleness

The recorded `prompt_hash` and `input_hashes` are not write-only: `demoforge.staleness`
compares them against the demo on disk, so an approved bundle captured against an older
`prompt.md` or input set is detected. `list` marks such a demo `!` in the `ap` column and
`render`/`build` print a warning naming what changed, because a stale bundle still renders
faithfully — it just no longer answers the question the demo now asks. Nothing is
auto-corrected: only a fresh `run` can answer the new prompt. A bundle with no recorded
hashes is reported as *unknown*, never as stale.

## 8. Determinism contract

| Stage | Deterministic? | Guarantee |
|---|---|---|
| `run` | No | Quarantined; metadata + hashes recorded |
| `approve` | Yes | Copy + content-address; idempotent |
| `render` (record/slides) | Yes | Same bundle + config + pinned tools → identical output |
| `narration` (TTS) | Yes *by cache* | Audio keyed by hash(provider, voice, text); regen only on text change |
| `video` | Yes | Timeline derived only from recorded events; ffmpeg flags pinned |
| `build` | Yes | Incremental via input hashes; re-run with no changes = no-op |
| staleness | Yes | Pure compare of recorded hashes vs. demo on disk (§7.1) |

## 9. Repository layout

```
DemoForge/
├── demoforge/          # THE ENGINE (domain-agnostic package)
│   ├── capture/        # headless Claude invocation, preflight, stream normalization
│   ├── checks/         # check kinds (registry)
│   ├── model/          # demo + run-bundle dataclasses
│   ├── render/         # record, slides, timeline, frames, narration, video, manifest
│   ├── build.py        # incremental build + cache
│   ├── verify.py       # stage + harness + checks
│   ├── redact.py       # display-time path rewriting
│   └── cli.py
├── examples/
│   └── claude-demo-kit/          # first CONTENT SET
│       ├── demoforge.toml        # set config (title, order, defaults, voice)
│       ├── demoforge.local.toml  # per-machine tool paths + sandbox (git-ignored)
│       ├── demos/
│       │   └── 02_matlab_optimization/
│       │       ├── demo.yaml
│       │       ├── prompt.md
│       │       ├── narration.md
│       │       ├── input/
│       │       └── checks/       # optional demo-specific check code
│       ├── approved/             # frozen bundles (COMMITTED — source of truth)
│       ├── runs/                 # raw bundles (git-ignored; regenerable)
│       ├── output/               # records/slides/video (git-ignored; rebuildable)
│       ├── SPEC.md               # original ClaudeDemoKit spec
│       └── README.md
├── templates/          # engine default record/slide/video templates
├── config/             # engine defaults + tool-version pins
├── docs/               # DemoForge spec set (this document + video-pipeline.md)
├── README.md
└── CLAUDE.md
```

Committed vs. ignored: `demoforge/`, `examples/<set>/demos/`, `examples/<set>/approved/`,
`config/`, `templates/`, `docs/` are durable source of truth. `runs/`, `output/` and
`demoforge.local.toml` are per-machine or regenerable and git-ignored.

## 10. Toolchain (pinned)

| Concern | Tool | Present? |
|---|---|---|
| Agent execution | Claude Code CLI headless (`-p --output-format stream-json`) | ✅ 2.1.289 |
| `.m` runtime | GNU Octave 11.3.0 (`octave-cli`; path set in `demoforge.local.toml`) | ✅ |
| Data/analysis/plots | Python 3.12 + numpy/scipy/pandas/matplotlib/openpyxl | ✅ |
| Spec-source PDFs | Markdown/LaTeX → pandoc | ✅ 3.1 |
| Slides | Marp CLI (via npx) | ✅ 4.5.1 (marp-core 4.4.0) |
| Scene frames | Playwright + Chromium | ✅ 1.61.0 / chromium-1228 |
| Scene templates | Jinja2 | ✅ 3.1.3 |
| TTS | Kokoro-82M + misaki, local GPU (`KokoroTTS`) | ✅ 0.9.4 — `SilentTTS` fallback |
| Video mux | ffmpeg | ✅ 7.0.1 |
| PDF rasterization (demo inputs) | Poppler (`pdftoppm`) | ✅ 25.07 — PATH-pinned, see below |

### 10.1 Tools the *agent* needs (`[capture] path_prepend`)

A tool DemoForge calls itself is resolved by an explicit pinned path (e.g. the
Octave CLI). A tool the **captured agent** calls is different: the agent inherits
its environment from whatever shell launched DemoForge, so a tool installed after
that shell started is invisible to it. On Windows this is structural — a process
copies its parent's environment block at creation and never refreshes it, so
restarting Claude Code under the same terminal changes nothing; only a *new*
shell picks up a changed `PATH`.

The machine therefore pins such directories itself, in the git-ignored
`demoforge.local.toml` beside `demoforge.toml`. Only its `[capture]` and `[runtimes]`
tables may be set there; they are merged over the committed ones:

```toml
[capture]
path_prepend = ['C:\...\poppler-25.07.0\Library\bin']
sandbox_root = 'C:\DemoForgeSandbox'

[runtimes]
octave = 'C:\...\octave-cli.exe'
```

These are prepended to the agent's `PATH` (so a pin overrides a same-named tool
already there), non-existent entries are ignored so the set stays portable, and
a demo's `requires:` (§4) is what actually reports a tool as missing. This makes
capture independent of how the terminal happened to be launched.

### 10.2 Paths a viewer sees (`[display] paths`)

A run records the absolute paths the agent really used, and approved bundles are
immutable, so the bundle keeps them. Rendering shows them through a rewrite:

```toml
[display]
paths = { 'C:\Playground' = 'G:\Willikers' }
```

`ContentSet.display_bundle()` hands renderers a `RunBundle` whose reads apply the
rules (`demoforge/redact.py`). The files on disk are never touched. One rule covers
every spelling a run produces (`C:\x`, `C:/x`, escaped `C:\\x`, Git Bash `/c/x`, WSL
`/mnt/c/x`), keeps the matched separator, ignores case, and stops at a name boundary.
All rules match the original text in one pass, so one rule's output is never rewritten
by another. Capture,
approve and staleness read the real bundle. The rules are part of the record cache
key, so changing them re-renders everything. This only changes how a path is
spelled, never what happened, so it doesn't break the "never fabricate" rule.

## 11. Build order

1. **Framework** — engine skeleton: schema, discovery, run-bundle model, checks, run
   dirs. *(Phase 1)*
2. **First vertical slice** — ClaudeDemoKit Demo 2 (MATLAB Optimization on Octave)
   end-to-end: define → run → capture → check → approve → render record. *(Phase 2–3)*
3. **Slides** — auto-generate deck from enabled+approved demos. *(Phase 4)*
4. **Narration + video** — per [`video-pipeline.md`](./video-pipeline.md). *(Phase 5)*
5. **Remaining ClaudeDemoKit demos** 1, 3–9. *(Phase 6)*
6. **Finale** — Demo 10 autonomous investigation reusing earlier artifacts. *(Phase 7)*

All stages are built and all ten demos are captured and approved. The pipeline
renders only what was actually captured, so an unapproved demo contributes nothing.
