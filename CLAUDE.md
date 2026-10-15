# CLAUDE.md — DemoForge

Project conventions for agents working in this repo. Read `docs/architecture.md` and
`docs/video-pipeline.md` for the full design.

DemoForge is a generic pipeline (`demoforge/`) that captures, freezes, and renders Claude
agent runs. **ClaudeDemoKit** (`examples/claude-demo-kit/`) is the first *content set*.

## Non-negotiable principles
- **Keep the engine domain-agnostic.** `demoforge/` must not hardcode MATLAB/Excel/demo
  specifics. Domain content lives in a content set under `examples/`.
- **Quarantine non-determinism.** Only the `run` step invokes Claude. Everything after
  `approve` must be a pure function of committed files + pinned tools.
- **Never fabricate.** Video/slide replay is generated *only* from recorded
  `events.jsonl`. Time may be compressed; actions may not be invented.
- **Verify by property, not by bytes.** Demos assert measurable `checks` (tests pass,
  speedup ≥ N, error < tol), never byte-exact output comparison.
- **A failed run must not destroy an approved run.** Approved bundles are immutable.
- **Demos are self-contained.** Everything a demo needs lives in its folder. No
  presentation logic inside a demo.

## Source of truth vs. regenerable
- Committed: `demoforge/`, `examples/<set>/demos/`, `examples/<set>/approved/`,
  `config/`, `templates/`, `docs/`.
- Git-ignored (rebuildable): `examples/<set>/runs/`, `examples/<set>/output/`.

## Adding a demo
Create `examples/<set>/demos/NN_name/` with `demo.yaml`, `prompt.md`, `narration.md`,
`input/`. The framework discovers it automatically — do not edit slide decks or TOCs by
hand.

## Runtimes
- `.m` files run on **GNU Octave** (not MATLAB — not installed here). Octave CLI:
  `%LOCALAPPDATA%\Programs\GNU Octave\Octave-11.3.0\mingw64\bin\octave-cli.exe`
  (not on PATH — invoke by full path or via a config pin). Note MATLAB/Octave
  differences in porting demos, but target Octave for reproducible execution.
- Python 3.12 with numpy/scipy/pandas/matplotlib/openpyxl is the data/analysis runtime.

## Environment
- Windows + PowerShell. Use PowerShell idioms in `PowerShell`-run commands; bash is
  available via the Bash tool for POSIX scripts.
- Keep dependencies minimal and pinned (`config/` holds tool-version pins).
