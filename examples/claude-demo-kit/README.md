# ClaudeDemoKit — a DemoForge content set

ClaudeDemoKit is the reference content set for [DemoForge](../../README.md): a suite of
engineering demonstrations that show **Claude doing real engineering work** — not just
answering questions.

Each demo gives Claude a realistic engineering job against real artifacts (`.m`, `.py`,
`.xlsx`, `.csv`, `.pdf`, `.log`) and verifies the result by measurable properties (tests
pass, speedup, numerical error, root cause identified). The demos share one coherent
fictional engineering system so the audience builds familiarity across demos.

The original design brief for this content set is in [`SPEC.md`](./SPEC.md).

## The suite

| # | Demo | Shows | Status |
|---|---|---|---|
| 1 | MATLAB algorithm implementation | spec → code → tests → review → fix | approved |
| 2 | MATLAB optimization | vectorize, benchmark, prove equivalence | approved |
| 3 | MATLAB → Python port | engineering migration, numerical equivalence | approved |
| 4 | Log investigation | autonomous multi-file correlation | approved |
| 5 | Excel investigation | cross-sheet formula debugging + correction | approved |
| 6 | CSV analysis & visualization | exploration, stats, anomaly detection, plots | re-capturing |
| 7 | Spec (PDF) → implementation | interpret equations/tables, implement, verify | re-capturing |
| 8 | Automated verification | find gaps + a planted defect | re-capturing |
| 9 | Requirements traceability | build a traceability matrix, find missing coverage | re-capturing |
| 10 | Autonomous engineering investigation | finale: root-cause across many artifacts | re-capturing |

Only approved demos appear in the video. A demo without an approved run is reported as
pending, never filled in.

## Layout

```
claude-demo-kit/
├── demoforge.toml   # content-set config (title, ordering, defaults)
├── demos/           # one folder per demo (auto-discovered)
├── approved/        # frozen approved run bundles (committed)
├── runs/            # raw run bundles (git-ignored)
├── output/          # rendered records/slides/video (git-ignored)
└── SPEC.md          # original design brief
```

Build it with DemoForge from the repo root:

```
python -m demoforge --set examples/claude-demo-kit build --video
```
