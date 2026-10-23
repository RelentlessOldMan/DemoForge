# DemoForge — Presentation, Narration & Video Pipeline Spec

**Status:** Built (Phase 5) · **Date:** 2026-10-05

> Implemented in `demoforge/render/`: `timeline.py` (§5), `narration.py` (§6),
> `frames.py` (§5.3), `video.py` (§7), `video_pipeline.py` (the DAG), driven by
> `demoforge video` / `demoforge build --video`.
>
> Title, chapter and closing cards (§7 step 3, §2, §9) render through the same
> Jinja/Chromium path as every scene — not by exporting Marp PNGs — so the video
> layer keeps one renderer and no npx dependency. They sit on their own template
> base (`_card_base.html.j2`), deliberately apart from the scene chrome: a scene
> frame names the captured events behind it, and a card has no run behind it to
> name. `cards.py` is the only place anything on screen is not event-derived, and
> the closing card's figures are measured from the chapters actually rendered.
> A contents card follows the title when there are two or more chapters, listing
> where each chapter card starts so a viewer can skip to a demo; the times come
> from the joined pieces' lengths, chapter cards sized after their narration
> (`[presentation] contents = false` turns it off).
>
> Narration is **Kokoro-82M** run locally on the GPU (§10.1), out of process under
> whichever interpreter has it installed, so the engine keeps no torch dependency.
> `SilentTTS` remains the fallback on a machine without it, and the build says so.

This specifies DemoForge's deterministic rendering layer: how approved run bundles become
records, slides, narrated audio, and a final video — **with zero manual timeline
editing** and **without ever fabricating an action Claude did not perform**.

It builds on [`architecture.md`](./architecture.md). Everything here is downstream of
`approve`, so everything here is a pure function of committed inputs + pinned tools.

> Paths like `output/`, `approved/`, and `demos/` below are **relative to a content set**
> (e.g. `examples/claude-demo-kit/`), not the repo root. DemoForge renders one set at a
> time.

---

## 1. Design goals

1. **Rebuildable, not editable.** No human ever opens a video editor. The video is
   `make`-style output of committed sources.
2. **Derive, don't author.** Slide order, section count, and video chapters are derived
   from enabled demos. Adding a demo changes the deck and video automatically (spec §11).
3. **Never fabricate.** Every on-screen action maps to a recorded event in the approved
   bundle. The renderer can *compress time* and *style* events, but cannot invent them.
4. **Cache expensive, non-deterministic-ish steps.** TTS audio and rendered frames are
   content-addressed and cached under `output/` so rebuilds are fast and stable.
5. **Pluggable, decoupled providers.** TTS and frame-rendering are interfaces, not
   hardcoded vendors (spec §13).

## 2. The rendering DAG

```
approved/<demo>/                config/            templates/
      │                            │                   │
      ├── events.jsonl ──► timeline.json ──► scenes[] ──► frames/*.png ─┐
      ├── transcript ──► record.md / record.html                       │
      ├── artifacts/  ──► artifact views (code, plots, xlsx)           ├─► ffmpeg ─► demo.mp4
      └── results.json ──► results panel                               │
                                                                       │
demos/*/narration.md ──► narration blocks ──► TTS cache ──► audio/*.wav┘
                                                                       
enabled demos ──► deck.md (Marp) ──► slides.html / slides.pdf / slide PNGs ─► intro/outro/chapter cards
```

Final `presentation.mp4` = concat( intro, per-demo chapters, outro ), where each demo
chapter = slides for that demo + the replayed run + results, over its narration track.

## 3. Records (the deterministic core deliverable)

Rendered first and always, because they are the highest-value, lowest-risk artifact and
everything else references them.

`output/records/<demo>.md` (+ `.html`) contains:
- Title, the **job** (prompt verbatim), and input manifest with hashes
- The captured run as a readable transcript with tool calls inlined
- Generated artifacts (syntax-highlighted code, embedded plots, xlsx-as-table)
- **Measurable results** table from `results.json` (speedup, max error, pass/fail)
- Reproducibility footer (model, versions, git commit, run id)

A new engineer reading the repo gets the entire "prompt → work → verified result" story
from this one file. Slides and video are visual reformattings of it.

## 4. Slides

- **Source:** generated Marp Markdown (`output/slides/deck.md`), text and committed.
- **Structure (derived):** title → "What is this content set" → one section per enabled
  demo (job, prompt, selected highlights, artifacts, results) → summary → finale.
- **Render targets:** `slides.html` (reveal-style), `slides.pdf`, and per-slide PNGs
  (for the video). Marp CLI via `npx @marp-team/marp-cli`.
- **Rule:** slides "show the work" — real prompt text, real captured output, real
  numbers. Avoid text-only bullet slides (spec §11).

## 5. Run replay → video scenes (the "never fabricate" mechanism)

The replay is generated **only** from `events.jsonl`. There is no hand-authored
timeline, which is precisely what makes fabrication structurally impossible.

### 5.1 Scene generation
Each canonical event maps to a **scene** via a declarative style map
(`config/scenes.yaml`):

| event type | scene | visual |
|---|---|---|
| `prompt` | PromptCard | the engineering request typed in |
| `user_message` | FollowUp | the person's follow-up after reading an answer |
| `user_done` | (not shown) | how the conversation ended; in the written record only |
| `assistant_text` | NarratedText | Claude's visible explanation |
| `file_read` / `file_search` | FileGlance | filename + brief peek |
| `file_write` / `file_edit` | DiffReveal | before/after or new-file reveal |
| `command` | TerminalRun | command line + streamed output |
| `test_result` | ResultBadge | pass/fail counts |
| `artifact` | ArtifactReveal | code/plot/xlsx view |
| `completion` | ChapterEnd | results summary panel |

Text cards (PromptCard, FollowUp, NarratedText) render the Markdown subset Claude
writes (`render/markdown.py`: paragraphs, headings, lists, fenced code, tables, bold,
italics, inline code; everything HTML-escaped first). Text longer than one card is
split into consecutive pages of the same event (`limits.text_page_lines`), breaking
between blocks, then sentences, list items or table rows; nothing is cut. Each page
is marked "part N of M", and a fit-to-box script shrinks text that still overflows
rather than letting the card clip it. A long command keeps at most
`limits.terminal_command_max_lines` lines, shares the card's line budget with its
output, and says when it was shortened.

### 5.2 Time compression (honest, not fake)
Presentation timing need not match wall clock (spec §14). Each scene's duration is
computed from config, not real elapsed time:

```yaml
# config/timing.yaml
scene_min_seconds: 1.5
scene_max_seconds: 8.0
terminal_chars_per_second: 60      # typewriter speed for command output
compress_idle: true                # a real 90s build shows as a short progress beat
```

A step's real duration is only what the record measures for it: from a command to
its recorded output. The gap before the next event (Claude composing its next step,
or the person reading) is not attributed to anything.

A real 90-second Octave benchmark is shown as a brief, clearly-labeled progress beat —
accurate about *what happened*, honest that *time is compressed*. We render a small
"⏩ time-compressed" affordance so the audience is never misled. The affordance quotes
the step's real duration, so it appears only for runs whose event times were measured
at capture (`metadata.json` `extra.event_times = "wallclock"`). For an older bundle,
whose `t` is just the line index, no scene claims a duration.

### 5.3 Frame rendering
Scenes are HTML templates (Jinja2) rendered to PNG via headless Chromium (Playwright).
- Deterministic: pinned browser version, fixed viewport, disabled animations, and
  Inter + JetBrains Mono committed under `templates/fonts/` (SIL OFL 1.1) and
  **inlined into each frame's markup as `data:` URIs**. Inlining is what makes the
  frame cache portable: the cache key is a hash of the markup, so a `file://` URL
  would bake a machine-specific path into every frame.
- Frames are content-addressed (`hash(scene, template, config)` → filename) and cached
  in `output/frames/`; unchanged scenes are never re-rendered.
- *Alternative considered:* asciinema + `agg` for terminal scenes. Rejected as primary
  (less layout control, extra dep) but left as an optional `TerminalRun` backend.

### 5.4 The animated session (`replay_style: session`)
By default the replay is drawn as one continuous Claude Code window
(`demoforge/render/session.py`, `templates/scenes/session.html.j2`), not one still card
per scene. Each conversation scene becomes a few *beats*, one PNG each:
- the prompt and follow-ups are typed into the input box, then submitted;
- Claude's words stream in, cut at whole words, Markdown kept well-formed;
- a command appears as `Bash(...)`; if the record measured it taking ≥ 1 s, a counter
  climbs to that recorded time, then its output prints line by line;
- writes and edits print their signed code lines; the window keeps the conversation
  so far and scrolls as it grows. The results panel (`ChapterEnd`) stays a still card;
- a read that handed Claude a picture or a PDF shows it under the `Read(...)` line,
  marked "the image Claude was shown" or "the N pages Claude was given"
  (`render/shown.py`). The bytes come from the read's tool result in the raw
  transcript (`capture/normalize.py` `read_attachments`, paired with the read events
  in order, refusing on any mismatch), so a plot Claude redraws is shown as it was at
  each look. PDF pages are drawn by poppler's `pdftoppm` at a fixed 60 dpi. Files
  Claude made but never looked at are not shown: the record holds no picture of them.

Rules that keep it honest and in sync:
- **Durations are untouched.** A scene's beats always sum to exactly its duration, so
  narration timing is the same as in `slides` style; narration plays once across all of
  a scene's frames. Animation speeds in `config/timing.yaml` change only how fast
  recorded text appears inside a scene.
- **Audited every build.** Every string a beat puts on screen must be text from the
  events up to and including that scene (`audit_beats`); otherwise the build fails. A
  beat can show the past, never the future, and never anything invented. The only
  other text is window chrome and the running counter, which shows recorded time.

Pacing long messages (session style only):
- A long message is paged over several scenes. Narration anchored on its first page
  plays **once across all its pages** (`narration_spans`), and its caption stays up on
  every page, so no page sits silent.
- Later pages stream on in place: each lasts its streaming time plus
  `continued_page_hold_seconds`, not a fresh card's reading time.
- A *narrated* message of Claude's is paced by its narration: it drops to the time
  it takes to stream and hold (`streamed_floors`), then grows back only as far as the
  speech needs. An un-narrated message keeps its reading time.

Set `replay_style: slides` to get the one-card-per-scene style back.

### 5.5 Slide numbers
Every frame carries a label in its lower right corner. In a demo's replay it reads
"Event 14 / 25, Slide 17 / 104": the event is the record's `seq + 1` out of the
demo's events, and the slide counts that demo's cards and scenes, intro cards
included. The set's opening cards (title, about cards, contents) read
"Opening · Slide n / N". Numbering is per demo, so a demo's own video and the full
presentation share frames, and adding a demo renumbers nothing.

## 6. Narration

- **Source:** `demos/<demo>/narration.md`, segmented into blocks tagged by moment:
  `intro:<heading>`, `during:<event-ref>`, `result`, `transition` (plus the older
  unheaded `setup` and `problem`). Text lives in git.
- **Problem first:** a demo's video, standalone or in the presentation, opens on its
  intro blocks, one card each, *before* the prompt. They explain the problem to a
  viewer who knows nothing about Claude: the situation, what the team has, what they
  need, and why it is hard. `during:0` then narrates the prompt itself. An intro block
  may show one figure, written as `![caption](input/data.csv#rows=1-30)` on its own
  line. It is plotted from that file in the demo folder only, and the card says which
  file and rows it shows; it is never spoken.
- **Synthesis:** pluggable `TTSProvider` interface:

  ```python
  class TTSProvider(Protocol):
      def synthesize(self, text: str, voice: str) -> bytes: ...   # returns wav
      @property
      def id(self) -> str: ...
  ```
- **Default provider: Kokoro-82M** — offline, free, local GPU, no network or API key.
  Loading the model dominates the cost, so a provider may expose `synthesize_batch`
  and the whole narration is rendered in one process. Piper and cloud providers
  (ElevenLabs/Azure/OpenAI) are drop-in plugins.
- **Cache:** audio keyed by `hash(provider_id, voice, normalized_text)` in
  `output/audio/` (git-ignored, rebuildable). Rebuilding the video does **not** re-synthesize unchanged
  narration (spec §13). Changing one sentence re-synthesizes only that block.
- **The set's own narration:** `examples/<set>/narration.md` speaks over the
  presentation's opening and closing cards: `title`, one `intro:<heading>` per about
  card (shown after the title, before the contents), `contents`, `opening` (the
  first chapter card) and an optional `outro`. Without `outro`, the closing card
  takes the last demo's `transition`. Any other block is an error.
- **Sync:** narration blocks anchor to scenes by ref; the video assembler stretches a
  scene's duration to at least cover its narration block (narration drives minimum
  pacing, so speech is never cut off).

## 7. Video assembly

Pure ffmpeg, driven by a generated `timeline.json` — no editor, no GUI.

1. Concatenate frame PNGs at their computed durations into per-scene clips
   (`ffmpeg -loop 1 -t <dur> -i frame.png ...`).
2. Lay narration `.wav` under the matching scenes; fill gaps with a soft bed or silence.
3. Add chapter/section cards (from slides) as transition scenes between demos.
4. Concatenate all chapters → `output/video/presentation.mp4`.
5. Per-demo videos (`output/video/<demo>.mp4`) also emitted for embedding in records.

Pinned encoding flags (codec, CRF, pixfmt, fps) live in `config/video.yaml` so output
bytes are stable across machines with the same ffmpeg build.

## 8. Incrementality & caching summary

| Artifact | Cache key | Rebuilt when |
|---|---|---|
| record.md/html | hash(bundle) | bundle changes |
| deck.md / slide PNGs | hash(enabled demos + template) | demo set/order/template changes |
| scene frame PNG | hash(scene + template + timing) | that scene or its style changes |
| narration wav | hash(provider, voice, text) | that narration block's text changes |
| demo.mp4 | hash(frames + audio + video cfg) | any input above changes |
| presentation.mp4 | hash(all demo.mp4 + intro/outro) | any chapter changes |

`build` walks this DAG and does the minimum work. No change → identical bytes, no work.

## 9. Self-demonstration (spec §18)

The final chapter states — truthfully — that the records, slides, narration, and the
video itself were all generated from this repository by running `demoforge build`.
The approved bundles are committed, so a fresh clone can `build` the whole
presentation without first running Claude. (For the ClaudeDemoKit content set this is
literally the closing slide — the kit demonstrates the tool that built it.)

## 10. Decisions (resolved 2026-10-05)

Confirmed against what is actually installed and pinned on the build machine, so the
video layer has no blocking prerequisite left. Each is an interface, not a hardcoding —
swapping any one of them is a config change (§1.5).

1. **TTS provider — Kokoro-82M, with silence as the fallback.** *(Revised 2026-10-06:
   originally Piper.)* Piper is not installed here and Kokoro is, already driving an
   audiobook pipeline on the same machine, so the kit narrates with the voice the
   author actually uses rather than a second one. Kokoro needs torch and CUDA, which
   the engine must not depend on, so it runs out of process under the interpreter that
   has it — the provider only has to return WAV bytes. A missing voice must not block
   the video or invent one, so `SilentTTS` stays the fallback: exactly-timed silence,
   content-addressed like any provider, identical pacing. Piper and cloud voices remain
   drop-in plugins. A build narrated by silence says so in its report.
2. **Frame renderer — Playwright/Chromium.** Confirmed available (playwright 1.61.0,
   chromium-1228), so the spec's recommendation stands with no heavy install. Pinned
   viewport, pinned browser revision, animations disabled, fonts bundled under
   `templates/fonts/`.
3. **Terminal replay — styled HTML terminal cards.** Same Jinja2 → Chromium path as
   every other scene: one renderer, one font stack, one cache. asciinema/`agg` stays
   documented as an optional `TerminalRun` backend but is not implemented.
4. **Music bed — none.** v1 ships narration (or silence) only. A bed is a config
   addition later, not a pipeline change.

### 10.1 Pinned toolchain for this layer

| Tool | Version | Role |
|---|---|---|
| playwright | 1.61.0 (chromium-1228) | scene HTML → PNG frames |
| Inter / JetBrains Mono | 4.1 / 2.304 | bundled frame typography (SIL OFL 1.1) |
| Jinja2 | 3.1.6 | scene templates |
| ffmpeg | 7.0.1 | clip + audio assembly |
| poppler (`pdftoppm`) | 25.07.0 | pages of a PDF Claude read, for the replay |
| Kokoro | 0.9.4 + misaki 0.9.4 (torch 2.11.0+cu128) | narration audio, local GPU |
| Piper | *(not installed — kept as a plugin)* | alternative narration |

Records and slides (v1 scope) depend on none of these and keep building without them.
