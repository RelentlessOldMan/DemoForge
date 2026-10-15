# Bundled fonts

Committed so a rendered frame looks the same on any machine, not merely on the one
that happens to have the right fonts installed (docs/video-pipeline.md §5.3).

| Family | Role | Version | Source | Licence |
|---|---|---|---|---|
| **Inter** | UI / prose (`--sans`) | 4.1 | [rsms/inter](https://github.com/rsms/inter/releases/tag/v4.1) | SIL OFL 1.1 — `OFL-Inter.txt` |
| **JetBrains Mono** | code, paths, measured values (`--mono`) | 2.304 | [JetBrains/JetBrainsMono](https://github.com/JetBrains/JetBrainsMono/releases/tag/v2.304) | SIL OFL 1.1 — `OFL-JetBrainsMono.txt` |

Both are under the SIL Open Font License 1.1, which permits redistribution inside a
project like this one provided the licence travels with the files — hence the two
`OFL-*.txt` files beside them. Neither may be sold on its own.

Chosen for the job rather than for taste: Inter is drawn for screens and holds up at
the small sizes the chrome and footers use, and JetBrains Mono distinguishes `0`/`O`
and `1`/`l`/`I` clearly — which matters on a frame whose whole point may be that the
gate threshold reads `5.991` and not `9.210`.

## Weights

Only four faces are committed, one file per weight actually used:

```
Inter-Regular.woff2            400   body prose
Inter-SemiBold.woff2           600   brand mark, headings
JetBrainsMono-Regular.woff2    400   terminal, paths, tables
JetBrainsMono-Bold.woff2       700   emphasis in mono contexts
```

Italics and the other weights are deliberately left out; nothing in the templates asks
for them, and every file here is inlined into every frame's markup.

## How they are used

`demoforge.render.frames.font_face_css` reads these files and emits `@font-face` rules
with the woff2 **inlined as `data:` URIs**, under the neutral family names
`DemoForge Sans` and `DemoForge Mono`.

Inlining is not an optimisation — it is what makes the frame cache work across
machines. A frame's cache key is a hash of its rendered markup, so a `file://` URL
would bake a machine-specific path into every frame and two machines would disagree
about all of them. (It also sidesteps Playwright's `set_content`, which gives the page
no base URL to resolve a relative path against.)

Missing files are not an error. The rules are simply omitted, and the CSS stacks in
`templates/scenes/_base.html.j2` fall through to whatever the machine has.

## Replacing them

Drop in a different woff2, update `BUNDLED_FONTS` in `demoforge/render/frames.py`, and
keep the new licence file here. Every frame's key changes, so the next build
re-renders them all — which is the correct outcome, not a cache bug.
