# How the videos are made, with no video editor

The [ClaudeDemoKit videos](https://github.com/RelentlessOldMan/DemoForge/releases/latest)
are eleven narrated, captioned MP4s, about 87 minutes in all, plus an `index.html` that
plays them. Nobody opened a video editor, a slide tool, a screen recorder or a sound
studio to make them. Every frame, every second of speech and every cut comes out of one
command:

```powershell
python -m demoforge --set examples/claude-demo-kit build --video
```

This page explains what that command does. It's written for someone who knows how
videos are usually made and wants to see the other way.

## The usual way, and what replaces it

| A typical demo video | Here |
|---|---|
| Screen-record someone doing the task live, retake the mistakes | Claude does the task once, for real, and every step is logged to a file ([how that works](how-capture-works.md)). The video is drawn from the log. |
| Build slides by hand in PowerPoint or Keynote | Every card and screen is an HTML template filled in from the log and from text files, then photographed by a headless browser |
| Record a voiceover, re-record when the script changes | The script is a text file. A text-to-speech model on the local GPU reads it |
| Cut and line up clips on a timeline | The timeline is computed: each scene lasts long enough to read and long enough for its narration |
| Add captions by hand | The narration text is also the caption, so they always match |
| Export, upload, write a web page for it | The build exports each video, writes the web page, zips both and records a checksum. One script publishes the release |

The whole pipeline (the code, the templates, the scripts, this page) was written in
[Claude Code](https://claude.com/claude-code) sessions, with a person deciding what it
should do and reviewing the results. Changing the video means changing a text or code
file, usually by asking Claude Code to, and building again. There is no project file in
an editor to keep in sync.

## What goes in

Everything is plain files in git:

- **The recorded run** of each demo (`approved/<demo>/events.jsonl`): the prompt, every
  file Claude read or wrote, every command it ran and what it printed, each of its
  replies, and the follow-ups from the person it was working with.
- **The narration** of each demo (`demos/<demo>/narration.md`), in sections tagged with
  where they play: before the prompt, over a given recorded step, over the result.
- **The set's own narration** (`narration.md`): the opening title, the "about" cards,
  the contents and the closing card.
- **Templates** (`templates/scenes/*.html.j2`): the look of each kind of screen.
- **Settings** (`config/`): how fast text appears, the shortest and longest a scene may
  last, and the exact video encoding flags.

## What the build does

```
recorded run ─► scenes ─► timeline ─► frames (PNG) ─┐
                                                    ├─► ffmpeg ─► MP4s ─► zip + index.html
narration text ───────────────► speech (WAV) ───────┘
```

### 1. Turn the recorded run into scenes

Each logged step becomes a scene: the prompt being typed, Claude's reply streaming in,
a command and its output, a file being written, a test result, the final checks. This
is a fixed mapping from step type to scene type, so a scene can only exist if the step
does. **The video can't show anything Claude didn't do.**

By default the replay looks like one Claude Code window. Text types in and streams out
word by word, commands print their output line by line, and the window scrolls as the
conversation grows. When Claude looked at a picture or a PDF, the page it saw is shown
under that step.

Every build checks that every word on screen comes from the log, up to that point in
the conversation. A screen that shows anything else stops the build.

### 2. Work out the timing

The real run took as long as it took: a benchmark can run for minutes, and Claude can
spend a while thinking between steps. The video compresses that. Each scene gets a
duration from the settings, long enough to read and then stretched to fit its narration
so speech is never cut off. When a step really ran long, the screen says so with a
"time-compressed" label and the real time, so nobody is misled about how fast it was.

The result is a timeline: a list of scenes, each with a duration and the narration that
plays over it. No one drags clips around. The timeline is computed again on every build.

### 3. Draw the frames

Each scene is an HTML page built from a template (Jinja2) and the scene's data. A
headless Chromium browser (Playwright) renders it to a 1920×1080 PNG. An animated scene
is a short run of these, one per step of the animation: the current release is about
21,000 frames.

The fonts are embedded in each page and the browser version is pinned, so the same
scene always gives the same picture. Each frame's file name is a hash of its HTML, so
a frame that hasn't changed is never drawn again.

The cards around the replay use the same renderer: the title, the "about" cards, the
contents list, the chapter card that opens each demo, the cards that explain the
problem before Claude is asked, the results panel and the closing card. A chart on a
problem card is drawn from the demo's real input file, and the card names the file and
the rows it shows.

### 4. Speak the narration

The narration is read by [Kokoro](https://github.com/hexgrad/kokoro), an open
text-to-speech model that runs locally on the GPU: no service, no API key, no
recording session. Each block of narration becomes a WAV file named by a hash of the
voice and the text, so changing one sentence re-records only that block. The current
release has about 600 of them.

The same text is shown as a caption, so the video works with the sound off and the
captions can't drift from the speech.

### 5. Put it together

[ffmpeg](https://ffmpeg.org) does all the editing:

1. Each frame becomes a clip of its computed length, and the narration is laid under its scenes.
2. The clips are joined into one video per demo, opened by its chapter card.
3. The opening cards become `00_intro.mp4`, and each demo becomes `01_…mp4` to `10_…mp4`.
   Played in order, they make the full presentation.
4. The encoding settings (codec, quality, frame rate, audio) are fixed in
   `config/video.yaml`, so the same inputs give the same bytes.

### 6. Package and publish

The build writes an `index.html` beside the videos: what the set is for, a contents
list, and each demo with its video, its length, a short summary and how many of its
checks passed. It loads nothing from the internet, so it works from a file share or an
unzipped folder. The page and the videos are zipped into `ClaudeDemoKit.zip`.

The build also writes a `manifest.json`: the git commit it was built from, which
recorded run each demo used, and the checksum of the zip. `release.ps1` publishes the
zip and the manifest as a GitHub release, and refuses to if the zip wasn't built from
the current, clean commit.

## Why this is easier to live with

- **Rebuild, don't re-edit.** Fixing a typo in the narration is a one-line text change
  and a rebuild. The pipeline re-records that one sentence and redraws the scenes that
  moved. A new template look redraws every frame without anyone touching a timeline.
- **Builds are incremental.** Frames, speech and each video are cached by content.
  Building again with nothing changed does no work and gives the same files.
- **Adding a demo is adding a folder.** The contents card, the chapter numbers, the
  file names and the web page all follow from the demos that exist.
- **It's honest by construction.** What Claude did on screen comes only from the
  recording. Time is compressed and labeled; actions are never invented. The only
  screens not drawn from a recording are the cards that frame the story, and those
  never say Claude did anything.
- **Anyone can rebuild it.** The recorded runs are in the repository, so a fresh clone
  can build the whole presentation without running Claude at all.

## Going deeper

- [`video-pipeline.md`](video-pipeline.md), the design spec for this layer: scene
  types, timing rules, narration tags, caching, pinned tool versions.
- [`how-capture-works.md`](how-capture-works.md), how the recordings themselves are made.
- The code is in [`demoforge/render/`](../demoforge/render/): `timeline.py` (scenes and
  timing), `session.py` (the animated window), `frames.py` (HTML to PNG),
  `narration.py` (speech), `video.py` (ffmpeg), `index_page.py` (the web page) and
  `video_pipeline.py`, which runs them in order.
