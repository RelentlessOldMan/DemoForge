# How Claude's work is captured

Each demo in the videos is a real piece of work Claude did once, on its own, while
every step was logged. This page explains how a demo is set up, how Claude is run
without anyone at the keyboard, how the result is checked, and how a good run is kept
for good. [How the videos are made](how-the-videos-are-made.md) picks up from there.

## 1. A demo is a folder

A demo is a folder under `demos/`, for example
[`demos/01_matlab_implementation/`](../examples/claude-demo-kit/demos/01_matlab_implementation/):

| File | What it is | Does Claude see it? |
|---|---|---|
| `prompt.md` | The request, written the way an engineer would ask a colleague. A real job, not "show off feature X" | Yes, as the first message |
| `input/` | The files the job needs: a spec, data, existing code | Yes, copied into its working folder |
| `user.md` | A short brief on who is asking and what they care about | No: it drives the simulated person (step 3) |
| `checks/`, `reference/` | Hidden tests and the expected answers | No |
| `demo.yaml` | Ties it together: inputs, the runtime (Octave, Python), the checks, how many follow-ups are allowed | No |
| `narration.md`, `summary.md` | What the video says, and the summary on the web page | No |

Nothing else needs registering: DemoForge finds every folder with a `demo.yaml`.

## 2. Claude runs headless, in a clean room

```powershell
python -m demoforge --set examples/claude-demo-kit run matlab-implementation
```

`run` is the only step that ever calls Claude. It starts the
[Claude Code](https://claude.com/claude-code) CLI in headless mode (`claude -p`) with
the prompt, and records everything it streams back.

So that the recording shows what Claude does with this job, and nothing else:

- **A fresh folder outside the repository.** Only the inputs are copied in, so Claude
  can't find the hidden checks, the answers, or earlier runs.
- **None of the operator's setup.** Their own CLAUDE.md, skills, plugins, hooks and MCP
  servers are switched off. A viewer couldn't see or repeat those.
- **Nothing left running between replies.** Background jobs are disabled, and the CLI
  runs in a process group that is closed at the end of each turn, so all the work
  happens where the recording can see it.
- **A preflight first.** Tools the job needs (Octave, a PDF reader) are checked before
  Claude starts, so a missing tool can't waste a run.
- **Audited afterwards.** Every tool call is searched for a path into the repository
  or a hidden check file, and anything found is reported before approval.

Every line Claude Code streams is stamped with the time it arrived. That's what lets
the video say truthfully how long a step took.

## 3. A conversation, not a one-shot

Real work with Claude is a back-and-forth, so each demo is captured as one. After each
answer a **simulated user**, a second Claude session, reads the reply and decides what
to say next: a question, a doubt, a fix to make, or "done". It plays the person in
`user.md`, for example the engineer who has to merge the code and wants a test that
would really catch a bug.

The simulated user sees what a person at the terminal would: the conversation and,
read-only, the working folder. It never sees the hidden checks. Its messages continue
the same Claude session, up to the demo's follow-up limit, and each is recorded at the
moment it was sent. The video shows them like any other step, and the record says how
the conversation ended.

Runs aren't retried for a better take. What you see is how the conversation went.

## 4. Checked by measurement, not by eye

Claude's code is different every run, so a run isn't compared to an expected file.
When the conversation ends, DemoForge copies what Claude produced into another fresh
folder and runs the demo's own hidden harness on it, which measures properties such as:

- the tests pass;
- the output matches a reference within a tolerance (say 10⁻⁶);
- it still matches on a second, hidden set of parameters, so constants can't be hard-coded;
- the optimized version is at least N times faster;
- the test Claude wrote fails on a deliberately broken version, so it actually tests something.

Results go to `results.json`. Claude never sees the harness, and anything it wrote
claiming its own results is deleted before the harness runs. A harness that crashes
counts as a failure.

## 5. The run bundle

Each run is saved under `runs/<demo>/<timestamp>-<id>/` and never overwritten:

```
metadata.json     model, CLI version, git commit, hashes of the prompt and inputs, isolation audit
prompt.md         the exact prompt sent
user.md           the simulated user's brief
user_simulator/   the simulated user's own sessions, so everything it looked at can be checked
transcript.jsonl  the raw stream from Claude Code
transcript.md     the same, readable
events.jsonl      the steps in a small, stable vocabulary: prompt, reply, file read/write, command, test result…
artifacts/        every file Claude created or changed
results.json      each check and the measured numbers
```

`events.jsonl` is what the video is drawn from. Translating Claude Code's own stream
into this vocabulary means the video doesn't depend on how a CLI version formats its
output.

## 6. Approve: a person decides, then it's frozen

```powershell
python -m demoforge --set examples/claude-demo-kit approve matlab-implementation --run <id>
```

A person reads the run and decides whether it's a fair demonstration. Approving copies
it to `approved/<demo>/`, which is committed to git. A run that failed its checks is
refused unless forced. The new bundle replaces the old one in a single swap, so a
failure partway can't leave a demo with no approved run.

The committed copy is cleaned of what describes the operator rather than the work:
their home folder, account and session ids, costs, and the text of Claude's private
reasoning (the video never shows reasoning). Only how paths are spelled changes, never
what was done, and the bundle records what was cleaned.

From here on nothing calls Claude again. If `prompt.md` or the inputs change later, the
approved run is flagged as stale, still rendered faithfully, and only a new `run` can
replace it.

## Going deeper

- [`architecture.md`](architecture.md), the design spec: the `demo.yaml` schema, the
  event vocabulary, check kinds, metadata, the determinism contract.
- [`demos.md`](demos.md), what each of the ten demos asked and what Claude did.
- The code is in [`demoforge/capture/`](../demoforge/capture/): `run.py` (the run),
  `conversation.py` (the simulated user), `turnjob.py` (nothing outlives a turn),
  `isolation.py` (the audit), `normalize.py` (stream to events) and `preflight.py`.
