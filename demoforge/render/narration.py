"""Narration: ``narration.md`` → blocks → anchored, content-addressed audio (§6).

Narration text lives in git, one block per moment, so what is said is reviewable in a
diff like everything else. Synthesis goes through a pluggable
:class:`TTSProvider`; audio is keyed by ``hash(provider, voice, normalized_text)``, so
changing one sentence re-synthesizes exactly one block and rebuilding changes nothing.

Anchoring is declarative and derived: a block attaches to a *scene* of the replay, and
narration only ever lengthens a scene (speech is never cut off). A block that names an
event the capture does not contain is an error rather than a silent no-op — narration
must not describe something that never happened.

The default provider is Piper when it is installed; otherwise :class:`SilentTTS` emits
exactly-timed silence so the pipeline keeps its pacing without inventing a voice. The
fallback is reported, never hidden (docs/video-pipeline.md §10).
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import wave
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Protocol, Sequence, runtime_checkable

from demoforge.config import NarrationConfig
from demoforge.errors import DemoError, DemoForgeError
from demoforge.model import Demo
from demoforge.render.config import Timing
from demoforge.render.timeline import Timeline

# Moment keys with a defined anchor. `transition` is deliberately not a scene: it
# plays over the card *between* demos, which the assembler owns.
MOMENT_SETUP = "setup"
MOMENT_PROBLEM = "problem"
MOMENT_RESULT = "result"
MOMENT_TRANSITION = "transition"
DURING_PREFIX = "during:"
# The set's own narration (``narration.md`` beside ``demoforge.toml``), spoken over
# the presentation's cards: the title, the set's ``intro:<heading>`` cards after it,
# the contents, and the first chapter card, which no earlier demo hands off to. The
# closing card takes ``outro`` if the set writes one, else the last demo's transition.
SET_TITLE = "title"
SET_CONTENTS = "contents"
SET_OPENING = "opening"
SET_OUTRO = "outro"
SET_NARRATION_FILE = "narration.md"
# `intro:<heading>` blocks explain the problem to the viewer, one card each, before
# any of the run is shown. `setup` and `problem` are the older, unheaded form.
INTRO_PREFIX = "intro:"
INTRO_MOMENTS = (MOMENT_SETUP, MOMENT_PROBLEM)

_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
_HEADING = re.compile(r"^##[ \t]+(.+?)[ \t]*$", re.M)
_WHITESPACE = re.compile(r"\s+")
# A block may show one figure, written as a Markdown image on a line of its own:
#   ![The 1,500 recorded readings](input/test_vectors.csv)
_FIGURE = re.compile(r"^[ \t]*!\[([^\]]*)\]\(([^)\s]+)\)[ \t]*$", re.M)

# PCM silence parameters — fixed so a silent track is byte-identical per duration.
SILENT_SAMPLE_RATE = 48000
SILENT_CHANNELS = 1
SILENT_SAMPLE_WIDTH = 2


# ---- blocks -----------------------------------------------------------
@dataclass(frozen=True)
class Figure:
    """A picture an intro card shows beside its words: a file in the demo folder."""

    source: str
    caption: str


@dataclass(frozen=True)
class NarrationBlock:
    """One spoken moment. ``key`` is its heading; ``text`` is what gets said.

    ``figure`` is shown, never spoken, so it is kept out of ``text``.
    """

    key: str
    text: str
    figure: Figure | None = None

    @property
    def normalized_text(self) -> str:
        """Whitespace-collapsed text — the cache key, so reflowing a paragraph is free."""
        return _WHITESPACE.sub(" ", self.text).strip()

    @property
    def is_during(self) -> bool:
        return self.key.startswith(DURING_PREFIX)

    @property
    def is_intro(self) -> bool:
        """Spoken on the demo's own cards, before the replay, not over it."""
        return self.key in INTRO_MOMENTS or self.key.startswith(INTRO_PREFIX)

    @property
    def heading(self) -> str:
        """The card heading an ``intro:<heading>`` block names; empty otherwise."""
        if self.key.startswith(INTRO_PREFIX):
            return self.key[len(INTRO_PREFIX):].strip()
        return ""

    @property
    def event_seq(self) -> int | None:
        """For a ``during:<seq>`` block, the recorded event it speaks over."""
        if not self.is_during:
            return None
        raw = self.key[len(DURING_PREFIX):].strip()
        try:
            return int(raw)
        except ValueError as exc:
            raise DemoError(
                f"narration block {self.key!r}: {raw!r} is not an event seq"
            ) from exc

    def estimated_seconds(self, timing: Timing) -> float:
        """Reserved length before the real audio exists (§6, refined by TTS)."""
        return round(len(self.normalized_text) / timing.narration_chars_per_second, 3)


@dataclass(frozen=True)
class Narration:
    """A demo's parsed narration, in file order."""

    demo_id: str
    blocks: tuple[NarrationBlock, ...] = ()

    def get(self, key: str) -> NarrationBlock | None:
        for b in self.blocks:
            if b.key == key:
                return b
        return None

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(b.key for b in self.blocks)

    @property
    def intro(self) -> tuple[NarrationBlock, ...]:
        """The blocks that explain the problem, in file order."""
        return tuple(b for b in self.blocks if b.is_intro)

    @property
    def replayed(self) -> "Narration":
        """Everything spoken over the replay itself: all but the introduction."""
        return Narration(
            demo_id=self.demo_id,
            blocks=tuple(b for b in self.blocks if not b.is_intro),
        )

    def __bool__(self) -> bool:
        return bool(self.blocks)


def parse_narration(text: str, *, demo_id: str = "") -> Narration:
    """Parse ``## <key>`` sections. Prose before the first heading is ignored."""
    body = _HTML_COMMENT.sub("", text)
    matches = list(_HEADING.finditer(body))
    blocks: list[NarrationBlock] = []
    seen: set[str] = set()
    for i, m in enumerate(matches):
        key = m.group(1).strip()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        content = body[m.end():end].strip()
        figures = _FIGURE.findall(content)
        if len(figures) > 1:
            raise DemoError(
                f"narration for {demo_id or '?'}: block {key!r} has more than one figure"
            )
        content = _FIGURE.sub("", content).strip()
        if not content:
            continue
        if key in seen:
            raise DemoError(f"narration for {demo_id or '?'}: duplicate block {key!r}")
        seen.add(key)
        figure = Figure(source=figures[0][1], caption=figures[0][0]) if figures else None
        if figure and not (key in INTRO_MOMENTS or key.startswith(INTRO_PREFIX)):
            raise DemoError(
                f"narration for {demo_id or '?'}: block {key!r} has a figure, but only "
                "an intro block is shown on a card that can hold one"
            )
        blocks.append(NarrationBlock(key=key, text=content, figure=figure))
    return Narration(demo_id=demo_id, blocks=tuple(blocks))


def load_narration(demo: Demo) -> Narration:
    """Read a demo's ``narration.md``; an absent file is simply no narration."""
    path = demo.narration_path
    if path is None or not path.is_file():
        return Narration(demo_id=demo.id)
    return parse_narration(path.read_text(encoding="utf-8"), demo_id=demo.id)


def load_set_narration(set_root: Path, set_id: str = "") -> Narration:
    """Read the set's own ``narration.md``; absent means the cards stay unspoken."""
    path = set_root / SET_NARRATION_FILE
    if not path.is_file():
        return Narration(demo_id=set_id)
    narration = parse_narration(path.read_text(encoding="utf-8"), demo_id=set_id)
    known = {SET_TITLE, SET_CONTENTS, SET_OPENING, SET_OUTRO}
    stray = [b.key for b in narration.blocks if b.key not in known and not b.is_intro]
    if stray:
        raise DemoError(
            f"{path}: unknown block(s) {', '.join(map(repr, stray))}; the set's "
            f"narration takes {', '.join(sorted(known))} and intro:<heading>"
        )
    if any(b.figure for b in narration.blocks):
        raise DemoError(f"{path}: the set's cards hold no figures")
    return narration


# ---- anchoring --------------------------------------------------------
def anchor_narration(timeline: Timeline, narration: Narration) -> dict[int, str]:
    """Map scene index → narration key, by the declared moment rules.

    ``setup`` opens on the prompt card, ``problem`` on the scene after it, ``result``
    on the chapter-end panel, and ``during:<seq>`` on whichever scene was built from
    that recorded event. ``transition`` is not a scene and is left to the assembler.
    """
    if not narration:
        return {}
    # A long message is paged over several scenes; its narration starts on the first.
    by_seq: dict[int, int] = {}
    for s in timeline.scenes:
        for seq in s.event_seqs:
            by_seq.setdefault(seq, s.index)
    n = len(timeline.scenes)
    assignments: dict[int, str] = {}

    def claim(index: int | None, key: str) -> None:
        if index is None or not (0 <= index < n):
            return
        assignments.setdefault(index, key)

    # Explicit anchors first, so a `during:` block always wins its own scene.
    for block in narration.blocks:
        if not block.is_during:
            continue
        seq = block.event_seq
        if seq not in by_seq:
            raise DemoError(
                f"narration for {narration.demo_id}: block {block.key!r} refers to "
                f"event {seq}, which is not in the captured run"
            )
        index = by_seq[seq]
        if index in assignments:
            # One scene can speak one block (a command and its output share a scene);
            # never drop the other one silently.
            seqs = list(timeline.scenes[index].event_seqs)
            raise DemoError(
                f"narration for {narration.demo_id}: blocks {assignments[index]!r} and "
                f"{block.key!r} both land on the scene built from events {seqs}; "
                "merge them into one block"
            )
        assignments[index] = block.key

    if narration.get(MOMENT_SETUP):
        claim(0 if n else None, MOMENT_SETUP)
    if narration.get(MOMENT_PROBLEM):
        claim(1 if n > 1 else None, MOMENT_PROBLEM)
    if narration.get(MOMENT_RESULT):
        chapter_end = next(
            (s.index for s in reversed(timeline.scenes) if s.kind == "ChapterEnd"),
            n - 1 if n else None,
        )
        claim(chapter_end, MOMENT_RESULT)
    return assignments


# ---- speech preparation ----------------------------------------------
# A markdown-style link whose target is a misaki *feature*, not a URL:
#   /ipa/  explicit phonemes    #tag#  misaki tag    +0.5 / -1  stress
_SPEECH_FEATURE = re.compile(r"^(?:/.+/|#.+#|[+-]?\d+(?:\.\d+)?)$")
_SPEECH_LINK = re.compile(r"\[([^\]]+)\]\(([^)]*)\)")
_SPEECH_MARKS = re.compile(r"\*\*?|__?|`")
# Only between two lowercase words. Splitting an identifier would wreck it:
# "CVT-VAL-002" reads correctly as letters and digits, but "CVT VAL 002"
# becomes "C-V-T val two".
_SPEECH_HYPHEN = re.compile(r"(?<=[a-z])-(?=[a-z])")
# A dot inside a name ("model.P0") is spoken as a full stop, which lands as a
# sentence break mid-phrase. Sentence-ending dots are followed by a space.
_SPEECH_DOT = re.compile(r"(?<=[A-Za-z])\.(?=[A-Za-z0-9])")
# An em/en dash reaches the synthesizer as an unknown token rather than a pause;
# a comma is the punctuation it actually phrases on.
_SPEECH_DASH = re.compile(r"[ \t]*[\u2014\u2013][ \t]*")


def _flatten_plain_links(m: re.Match) -> str:
    """Keep misaki overrides intact; reduce real links to their text."""
    return m.group(0) if _SPEECH_FEATURE.match(m.group(2)) else m.group(1)


def prepare_for_speech(text: str, lexicon: dict[str, str] | None = None) -> str:
    """Turn narration prose into what the synthesizer should actually say.

    Narration is written as Markdown for humans to review in a diff, and a
    synthesizer reads it literally: backticks come out as audible quote marks, a
    dot inside ``model.P0`` lands as a sentence break, and a hyphen glues
    ``constant-velocity`` into one word. This strips what is notation and keeps
    what is speech.

    Pronunciation overrides (``[Kalman](/kˈɑlmən/)``, ``[really](+0.5)``) are
    preserved, and an entry written inline always beats the lexicon.
    """
    text = _SPEECH_LINK.sub(_flatten_plain_links, text)
    text = _SPEECH_MARKS.sub("", text)
    text = _SPEECH_HYPHEN.sub(" ", text)
    text = _SPEECH_DOT.sub(" ", text)
    text = _SPEECH_DASH.sub(", ", text)
    text = re.sub(r"[ 	]{2,}", " ", text).strip()
    return apply_lexicon(text, lexicon or {})


def display_text(text: str) -> str:
    """Narration as it should read on screen, for a viewer watching without sound.

    The counterpart to :func:`prepare_for_speech`: pronunciation overrides
    (``[Kalman](/kˈɑlmən/)``) and Markdown emphasis are for the synthesizer and the
    reviewer, so a caption keeps only the words.
    """
    text = _SPEECH_LINK.sub(lambda m: m.group(1), text)
    text = _SPEECH_MARKS.sub("", text)
    return _WHITESPACE.sub(" ", text).strip()


def load_lexicon(*paths: Path) -> dict[str, str]:
    """Merge word → IPA maps. Later files win; keys starting with ``_`` are notes.

    The engine ships none: which words a narrator says wrong is a property of the
    subject matter, so the lexicon belongs to the content set.
    """
    merged: dict[str, str] = {}
    for path in paths:
        if path is None or not Path(path).is_file():
            continue
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        for word, ipa in data.items():
            if not word.startswith("_") and isinstance(ipa, str):
                merged[word.lower()] = ipa
    return merged


def apply_lexicon(text: str, lexicon: dict[str, str]) -> str:
    """Wrap known words in their phoneme override, leaving existing ones alone."""
    if not lexicon:
        return text
    words = sorted(lexicon, key=len, reverse=True)
    pattern = re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")\b", re.I)

    def wrap(m: re.Match) -> str:
        return f"[{m.group(1)}](/{lexicon[m.group(1).lower()]}/)"

    out, last = [], 0
    for link in _SPEECH_LINK.finditer(text):   # step over overrides already present
        out.append(pattern.sub(wrap, text[last:link.start()]))
        out.append(link.group(0))
        last = link.end()
    out.append(pattern.sub(wrap, text[last:]))
    return "".join(out)


# ---- providers --------------------------------------------------------
@runtime_checkable
class TTSProvider(Protocol):
    """Text → wav bytes. Any provider is interchangeable (§1.5)."""

    @property
    def id(self) -> str:
        """Stable provider identity; part of the audio cache key."""

    def synthesize(self, text: str, voice: str) -> bytes:
        """Return a complete RIFF/WAVE payload for ``text``."""


@dataclass(frozen=True)
class SilentTTS:
    """Exactly-timed silence, used when no voice is installed.

    Keeps the video's pacing identical to a narrated build without inventing a
    performance. Deterministic: the same text always yields the same bytes.
    """

    timing: Timing = field(default_factory=Timing)
    reason: str = "no TTS provider installed"

    @property
    def id(self) -> str:
        return "silent"

    @property
    def cache_id(self) -> str:
        # The pace sets each clip's length, so a pace change must not reuse old clips.
        return f"silent@{self.timing.narration_chars_per_second:g}"

    def synthesize(self, text: str, voice: str) -> bytes:
        seconds = NarrationBlock(key="", text=text).estimated_seconds(self.timing)
        return _silent_wav(max(seconds, 0.1))


@dataclass(frozen=True)
class PiperTTS:
    """Offline Piper synthesis — the v1 default when the binary is available."""

    binary: Path
    model: Path | None = None

    @property
    def id(self) -> str:
        return "piper"

    def synthesize(self, text: str, voice: str) -> bytes:
        cmd = [str(self.binary), "--output_file", "-"]
        cmd += ["--model", str(self.model)] if self.model else ["--model", voice]
        try:
            proc = subprocess.run(
                cmd, input=text.encode("utf-8"), capture_output=True, timeout=300
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise DemoForgeError(f"piper synthesis failed: {exc}") from exc
        if proc.returncode != 0 or not proc.stdout:
            tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()[-3:]
            raise DemoForgeError(
                "piper synthesis failed (exit "
                f"{proc.returncode}): {' / '.join(tail) or 'no output'}"
            )
        return proc.stdout


KOKORO_SCRIPT = Path(__file__).resolve().parent / "_kokoro_synth.py"
# Interpreters likely to have torch + kokoro, in preference order. DemoForge's own
# environment stays small, so synthesis runs wherever the model actually lives.
_KOKORO_CANDIDATES = ("python", "python3", r"C:\Program Files\Python312\python.exe")


@dataclass(frozen=True)
class KokoroTTS:
    """Local neural synthesis via Kokoro-82M, out of process (§6, pluggable).

    Kokoro needs torch and a CUDA build, which the engine does not depend on, so
    the model runs under ``python`` — whichever interpreter has it — and a whole
    batch is rendered per process because loading the model dominates the cost.
    """

    python: Path
    voice_default: str = "af_heart"
    speed: float = 1.0
    lang: str = "a"
    script: Path = KOKORO_SCRIPT

    @property
    def id(self) -> str:
        # Speed changes the audio, so it belongs in the identity that keys the cache.
        return f"kokoro-{self.lang}-s{self.speed:g}"

    def synthesize(self, text: str, voice: str) -> bytes:
        with tempfile.TemporaryDirectory(prefix="demoforge-kokoro-") as tmp:
            out = Path(tmp) / "block.wav"
            self.synthesize_batch([(text, out)], voice)
            return out.read_bytes()

    def synthesize_batch(self, jobs: list[tuple[str, Path]], voice: str) -> None:
        """Render many blocks in one process. Loading the model is the expensive part."""
        if not jobs:
            return
        with tempfile.TemporaryDirectory(prefix="demoforge-kokoro-") as tmp:
            spec = Path(tmp) / "jobs.json"
            spec.write_text(
                json.dumps([{"text": t, "out": str(p)} for t, p in jobs]),
                encoding="utf-8",
            )
            cmd = [
                str(self.python), str(self.script),
                "--jobs", str(spec),
                "--voice", voice or self.voice_default,
                "--speed", str(self.speed),
                "--lang", self.lang,
            ]
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise DemoForgeError(f"kokoro synthesis failed to run: {exc}") from exc
        if proc.returncode != 0:
            tail = (proc.stderr or "").strip().splitlines()[-4:]
            raise DemoForgeError(
                f"kokoro synthesis failed (exit {proc.returncode}): "
                f"{' / '.join(tail) or 'no diagnostics'}"
            )
        missing = [p.name for _t, p in jobs if not p.is_file()]
        if missing:
            raise DemoForgeError(f"kokoro produced no audio for: {', '.join(missing)}")


def find_kokoro_python(candidates: Sequence[str] | None = None) -> Path | None:
    """An interpreter that can actually import kokoro, or ``None``.

    Probed rather than assumed: a `python` on PATH says nothing about whether the
    model is installed under it.
    """
    for name in candidates if candidates is not None else _KOKORO_CANDIDATES:
        exe = shutil.which(name) or (name if Path(name).is_file() else None)
        if not exe:
            continue
        try:
            proc = subprocess.run(
                [str(exe), "-c", "import kokoro"],
                capture_output=True, timeout=120,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if proc.returncode == 0:
            return Path(exe)
    return None


def make_provider(
    config: NarrationConfig,
    timing: Timing,
    *,
    piper_bin: Path | None = None,
    piper_model: Path | None = None,
    kokoro_python: Path | None = None,
    kokoro_speed: float = 1.0,
) -> TTSProvider:
    """Pick a provider from config, falling back to silence rather than failing."""
    if not config.enabled:
        return SilentTTS(timing=timing, reason="narration disabled in demoforge.toml")
    if config.provider == "kokoro":
        found = kokoro_python or find_kokoro_python()
        if found is None:
            return SilentTTS(
                timing=timing, reason="no interpreter on this machine can import kokoro"
            )
        return KokoroTTS(python=found, speed=kokoro_speed)
    if config.provider == "piper":
        found = piper_bin or _which("piper")
        if found is None:
            return SilentTTS(timing=timing, reason="piper not found on PATH")
        return PiperTTS(binary=found, model=piper_model)
    return SilentTTS(
        timing=timing, reason=f"unknown TTS provider {config.provider!r}"
    )


# ---- synthesis + cache ------------------------------------------------
@dataclass(frozen=True)
class AudioClip:
    """One synthesized block on disk, with the duration that drives pacing."""

    key: str
    path: Path
    seconds: float
    cached: bool


def audio_key(provider_id: str, voice: str, normalized_text: str) -> str:
    """Content address for a block's audio (§8). Reflowing text does not change it."""
    h = hashlib.sha256()
    for part in (provider_id, voice, normalized_text):
        h.update(part.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()[:16]


def synthesize_narration(
    narration: Narration,
    provider: TTSProvider,
    voice: str,
    out_dir: Path,
    lexicon: dict[str, str] | None = None,
    force: bool = False,
) -> dict[str, AudioClip]:
    """Synthesize every block, reusing cached audio. Returns clips by block key.

    The text is prepared for speech first, and the *prepared* text is what gets
    hashed — so correcting a pronunciation re-synthesizes exactly the blocks that
    say that word, with no separate cache-busting step to remember.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    planned: list[tuple[NarrationBlock, str, Path, bool]] = []
    for block in narration.blocks:
        speech = prepare_for_speech(block.normalized_text, lexicon)
        path = out_dir / f"{audio_key(getattr(provider, 'cache_id', provider.id), voice, speech)}.wav"
        planned.append((block, speech, path, path.is_file() and not force))

    # A provider whose cost is dominated by start-up (loading a model) renders the
    # whole batch in one go; otherwise fall back to one call per block.
    pending = [(speech, p) for _b, speech, p, cached in planned if not cached]
    batch = getattr(provider, "synthesize_batch", None)
    if pending and callable(batch):
        batch(pending, voice)
    else:
        for text, path in pending:
            path.write_bytes(provider.synthesize(text, voice))

    return {
        block.key: AudioClip(
            key=block.key,
            path=path,
            seconds=wav_duration_seconds(path),
            cached=cached,
        )
        for block, _speech, path, cached in planned
    }


def join_clips(
    clips: Sequence[AudioClip], out_dir: Path, *, key: str, gap: float = 0.6
) -> AudioClip:
    """Play several clips back to back as one, with ``gap`` seconds between them.

    For a card that speaks more than one block. The result is content-addressed
    over its parts, so it is rebuilt exactly when one of them changes.
    """
    if not clips:
        raise DemoForgeError("join_clips needs at least one clip")
    if len(clips) == 1:
        return replace(clips[0], key=key)
    h = hashlib.sha256()
    for c in clips:
        h.update(c.path.name.encode("utf-8"))
        h.update(b"\0")
    h.update(f"gap={gap:g}".encode("ascii"))
    path = out_dir / f"joined-{h.hexdigest()[:16]}.wav"
    cached = path.is_file()
    if not cached:
        params = None
        chunks: list[bytes] = []
        for i, c in enumerate(clips):
            with wave.open(str(c.path), "rb") as fh:
                p = fh.getparams()
                if params is None:
                    params = p
                elif (p.nchannels, p.sampwidth, p.framerate) != (
                    params.nchannels, params.sampwidth, params.framerate
                ):
                    raise DemoForgeError(f"cannot join {c.path.name}: audio format differs")
                if i:
                    pause = int(round(gap * params.framerate))
                    chunks.append(bytes(pause * params.nchannels * params.sampwidth))
                chunks.append(fh.readframes(fh.getnframes()))
        out_dir.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as fh:
            fh.setnchannels(params.nchannels)
            fh.setsampwidth(params.sampwidth)
            fh.setframerate(params.framerate)
            fh.writeframes(b"".join(chunks))
    return AudioClip(key=key, path=path, seconds=wav_duration_seconds(path), cached=cached)


def clip_seconds(clips: dict[str, AudioClip]) -> dict[str, float]:
    """Block key → audio length, for :func:`~demoforge.render.timeline.stretch_for_narration`."""
    return {key: clip.seconds for key, clip in clips.items()}


def wav_duration_seconds(path: Path) -> float:
    """Exact length of a RIFF/WAVE file, from its own header."""
    try:
        with wave.open(str(path), "rb") as fh:
            frames, rate = fh.getnframes(), fh.getframerate()
    except (wave.Error, OSError) as exc:
        raise DemoForgeError(f"{path} is not readable as WAV: {exc}") from exc
    if rate <= 0:
        raise DemoForgeError(f"{path} reports a zero sample rate")
    return round(frames / rate, 3)


def _silent_wav(seconds: float) -> bytes:
    import io

    frames = int(round(seconds * SILENT_SAMPLE_RATE))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as fh:
        fh.setnchannels(SILENT_CHANNELS)
        fh.setsampwidth(SILENT_SAMPLE_WIDTH)
        fh.setframerate(SILENT_SAMPLE_RATE)
        fh.writeframes(b"\0" * (frames * SILENT_CHANNELS * SILENT_SAMPLE_WIDTH))
    return buf.getvalue()


def _which(name: str) -> Path | None:
    found = shutil.which(name)
    return Path(found) if found else None
