# DemoForge 🎬

**Capture what a Claude agent actually did on a real task, freeze it, and render it into
records, slides, and a narrated video, without re-running the agent or inventing a single
action.**

DemoForge is a generic pipeline that doesn't know about any particular domain. You give it a
*content set*: a folder of declarative "jobs", each with a realistic prompt, input files, and
measurable success criteria. It runs Claude on each job and captures exactly what happened
as a structured run bundle. You approve the runs you want to keep, and it freezes them. From
then on it rebuilds records, slides, and video from source control as often as you like,
with the same result every time.

▶️ **[Watch the ClaudeDemoKit presentation](https://github.com/RelentlessOldMan/DemoForge/releases/latest/download/ClaudeDemoKit.mp4)**
(narrated and captioned, so it works with the sound off; MP4 from the
[latest release](https://github.com/RelentlessOldMan/DemoForge/releases/latest)).

## Why

Recorded demos of AI agents usually make you pick between two bad options. You can screen-record
a live run, which is slow, can't be repeated, and often goes wrong on camera. Or you can script
a "demo" that shows things the agent never did. DemoForge does neither. Claude runs once, for
real, and each run is checked against measurable properties (tests pass, speedup ≥ N,
error < tolerance). After that, the presentation is a pure function of what was recorded. The
replay can compress time, but it can never show an action that didn't happen.

## Usage

```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[dev,video]"
.venv\Scripts\python -m playwright install chromium

$set = "examples/claude-demo-kit"
.venv\Scripts\python -m demoforge --set $set list                         # discover demos
.venv\Scripts\python -m demoforge --set $set run <demo-id>                # capture a real Claude run + verify it
.venv\Scripts\python -m demoforge --set $set approve <demo-id> --run <id> # freeze it into approved/
.venv\Scripts\python -m demoforge --set $set build --video                # records, slides, narrated video
```

The approved runs are committed, so `build --video` works without ever calling Claude.

**Prerequisites**

| For | You need |
|---|---|
| Everything | Python 3.12 |
| `run` (capturing) | The [Claude Code](https://claude.com/claude-code) CLI on PATH, logged in |
| ClaudeDemoKit demos | GNU Octave (`octave-cli`) for `.m` code; numpy, scipy, pandas, matplotlib, openpyxl; Poppler (`pdftoppm`) so Claude can read the PDF inputs |
| `build --video` | ffmpeg on PATH and Chromium (the `playwright install` line above) |
| Narration | [Kokoro](https://github.com/hexgrad/kokoro) (`pip install kokoro soundfile`) in any Python on PATH; DemoForge finds it. Without it the video gets timed silence and the build says so |

Tools that aren't on PATH, and where captures run, are set per machine in a git-ignored
`demoforge.local.toml` beside the content set's `demoforge.toml`:

```toml
[capture]
path_prepend = ['C:\tools\poppler\Library\bin']   # added to the agent's PATH
sandbox_root = 'C:\DemoForgeSandbox'              # where the agent works (default: temp)

[runtimes]
octave = 'C:\tools\Octave\mingw64\bin\octave-cli.exe'
```

Captures are isolated: the agent works in a fresh folder outside the repo, without your
own CLAUDE.md, skills, plugins, hooks or MCP servers, and on your CLI login rather than
any API key in the environment.

To publish a new video, run `.\release.ps1 v1.0.1 "notes"`. It pushes `main` and creates a GitHub
Release with the rendered video attached as `ClaudeDemoKit.mp4`, plus the build's
`manifest.json` (the commit, run ids and hashes it was built from). The video is never
committed. The script refuses a video that wasn't built from the current, clean commit.

Versions: the last number goes up for small changes (`1.0.1`, `1.0.2`, …, such as another
re-captured demo); the middle number goes up for big ones (`1.1.0`).

## How it works

```
run  ─►  approve  ─►  render  ─►  build
(Claude   (freeze    (records,    (assemble
 executes  the run)   slides,      final
 for real)            narration)   video)
```

- **Only `run` touches Claude.** Everything after `approve` depends only on committed files
  and pinned tools. Approved bundles are immutable, so a failed run can never overwrite a good one.
- **The replay comes only from recorded events.** Each scene comes from the run's
  `events.jsonl`. Title, chapter, and "The problem" cards frame the story, but they never claim
  the agent did anything.
- **Narration is written per demo** (`narration.md`: setup, problem, per-step notes, result).
  It is voiced locally and also shown as on-screen captions, so the video works with the sound off.
- **Builds are incremental.** Frames and audio are cached by content hash, so changing one
  demo re-renders only that demo.

Full design: [`docs/architecture.md`](docs/architecture.md) and
[`docs/video-pipeline.md`](docs/video-pipeline.md).

### ClaudeDemoKit

[`examples/claude-demo-kit/`](examples/claude-demo-kit/) is the first content set. It has ten
engineering demos built around one Kalman-filter story: implementing, optimizing, and porting
MATLAB/Octave code, investigating logs, spreadsheets, and CSVs, implementing from a spec,
verification, traceability, and an open-ended autonomous investigation.

Each demo is captured as a real conversation: Claude does the job, and a second Claude
session plays the engineer who reviews the answer and pushes back. In 1.0.0, demo 1 is
captured, approved and in the video. The other nine are being re-captured the same way and
are added in 1.0.x releases as each one is approved.

## Layout

```
demoforge/            the engine (no domain knowledge)
  capture/            headless Claude runs → run bundles
  checks/             property-based verification
  model/              demo + bundle schemas
  render/             records, slides, frames, narration, video
config/               tool pins, scene + timing settings
templates/            slide and scene templates (Jinja2/HTML)
docs/                 architecture and video-pipeline design
examples/
  claude-demo-kit/
    demos/NN_name/    demo.yaml, prompt.md, narration.md, input/, checks/
    approved/         frozen run bundles (committed)
    runs/, output/    regenerable (git-ignored)
tests/
```

## Contributing

This is a personal tool, published as-is — **issues and pull requests aren't accepted** (PRs auto-close). Fork it and make it your own. 🎬

## License

MIT — see [LICENSE](LICENSE). © 2026 RelentlessOldMan.
