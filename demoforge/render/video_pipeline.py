"""The video DAG end to end: approved bundles → chapters → presentation.

One orchestration over the pieces each of which is already deterministic and cached:
``timeline`` derives the scenes, ``narration`` supplies the words, ``frames`` draws
them, ``video`` encodes them. Nothing here decides *what* is shown — that is the
timeline's job, and the timeline can only be built from recorded events.

Everything is reported rather than smoothed over: demos skipped for want of an
approved capture, and a narration track that is silence because no voice is
installed, both come back in the summary instead of quietly looking like success.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from demoforge.discovery import ContentSet
from demoforge.errors import DemoError
from demoforge.model import Demo, RunBundle
from demoforge.render.cards import (
    Card,
    card_html,
    chapter_card,
    contents_card,
    outro_card,
    problem_card,
    title_card,
)
from demoforge.render.config import PresentationSettings, load_settings
from demoforge.render.figures import figure_view
from demoforge.render.session import audit_beats, session_beats, streamed_floors
from demoforge.render.manifest import write_manifest
from demoforge.render.frames import (
    ChromiumRenderer,
    Frame,
    FrameRenderer,
    context_for,
    frame_key,
    render_frames,
)
from demoforge.render.narration import (
    MOMENT_TRANSITION,
    AudioClip,
    Narration,
    NarrationBlock,
    anchor_narration,
    clip_seconds,
    display_text,
    join_clips,
    load_lexicon,
    load_narration,
    make_provider,
    synthesize_narration,
)
from demoforge.render.timeline import (
    Timeline,
    build_timeline,
    stretch_for_narration,
    with_narration,
    write_timeline,
)
from demoforge.render.video import (
    VideoResult,
    assemble_card_clip,
    assemble_demo_video,
    concat_videos,
)

PRESENTATION_NAME = "presentation.mp4"

# A demo's introduction is spoken over its own cards, before the replay, rather than
# over the first replay scenes: a viewer should understand the problem for
# themselves before watching anyone work on it, and a viewer without sound needs
# to read it there. The cards open the demo's own video, not only the presentation.


@dataclass
class Chapter:
    """One demo's rendered chapter and the pieces it was built from."""

    demo_id: str
    title: str
    timeline: Timeline
    frames: list[Frame]
    audio: dict[str, AudioClip]
    # The demo's own video: its intro cards, then the replay.
    video: VideoResult
    narration: Narration = field(default_factory=lambda: Narration(demo_id=""))
    intro: list[VideoResult] = field(default_factory=list)
    replay: VideoResult | None = None

    @property
    def parts(self) -> list[Path]:
        """The encoded pieces in order, so the presentation joins them unchanged."""
        if self.replay is None:
            return [self.video.path]
        return [c.path for c in self.intro] + [self.replay.path]

    @property
    def seconds(self) -> float:
        """The whole chapter: intro cards plus the replay."""
        return round(self.timeline.total_seconds + sum(c.seconds for c in self.intro), 3)

    @property
    def fresh_frames(self) -> int:
        return sum(1 for f in self.frames if not f.cached)

    @property
    def event_count(self) -> int:
        """Recorded events behind this chapter — what the closing card counts.

        Each event once: a long prompt or answer is paged over several scenes.
        """
        return len({seq for s in self.timeline.scenes for seq in s.event_seqs})


@dataclass
class VideoSummary:
    """What a video build produced, and what it could not."""

    chapters: list[Chapter] = field(default_factory=list)
    cards: list[VideoResult] = field(default_factory=list)
    presentation: VideoResult | None = None
    skipped: list[str] = field(default_factory=list)
    narration_provider: str = ""
    narration_note: str = ""

    @property
    def seconds(self) -> float:
        """Everything in the presentation: chapters plus the cards around them."""
        return round(
            sum(c.seconds for c in self.chapters) + sum(c.seconds for c in self.cards), 3
        )

    @property
    def event_count(self) -> int:
        return sum(c.event_count for c in self.chapters)

    @property
    def narrated(self) -> bool:
        """False when the track is silence standing in for an absent voice."""
        return self.narration_provider not in ("", "silent")


def build_videos(
    content_set: ContentSet,
    *,
    only: str | None = None,
    out_dir: Path | None = None,
    settings: PresentationSettings | None = None,
    renderer: FrameRenderer | None = None,
    ffmpeg: Path | str | None = None,
    presentation: bool = True,
    force: bool = False,
) -> VideoSummary:
    """Render every enabled+approved demo to a chapter, then join them.

    ``force`` rebuilds every frame, clip and narration WAV even on a cache hit.
    The caches are content-addressed, so this is never needed to pick up an edit
    — it is how you prove the cache is telling the truth.
    """
    st = settings or load_settings(content_set.root)
    out = out_dir or content_set.output_dir
    summary = VideoSummary()

    demos = content_set.demos(enabled_only=True)
    if only is not None:
        demos = [d for d in demos if d.id == only]
        if not demos:
            raise DemoError(f"no enabled demo with id {only!r}")

    # A demo's number is its place in the whole set, so it reads the same whether
    # it is rendered alone or with the rest.
    numbers = {d.id: i + 1 for i, d in enumerate(content_set.demos(enabled_only=True))}
    ready: list[Demo] = []
    for demo in demos:
        if RunBundle(content_set.approved_dir_for(demo.id)).exists():
            ready.append(demo)
        else:
            summary.skipped.append(demo.id)
    if not ready:
        return summary

    provider = make_provider(content_set.config.narration, st.timing)
    # Which words a narrator says wrong belongs to the subject matter, so the
    # lexicon lives with the content set, not the engine.
    lexicon = load_lexicon(content_set.root / "config" / "lexicon.json")
    summary.narration_provider = provider.id
    summary.narration_note = getattr(provider, "reason", "")

    # One browser serves the chapters and the cards around them.
    if renderer is not None:
        for demo in ready:
            summary.chapters.append(
                _chapter(content_set, demo, st, out, provider, renderer, ffmpeg,
                         lexicon, force, number=numbers[demo.id])
            )
        if presentation:
            _finish(content_set, summary, st, out, renderer, ffmpeg, force)
    else:
        with ChromiumRenderer(st.video) as browser:
            for demo in ready:
                summary.chapters.append(
                    _chapter(content_set, demo, st, out, provider, browser, ffmpeg,
                             lexicon, force, number=numbers[demo.id])
                )
            if presentation:
                _finish(content_set, summary, st, out, browser, ffmpeg, force)
    return summary


def _finish(
    content_set: ContentSet,
    summary: VideoSummary,
    st: PresentationSettings,
    out: Path,
    renderer: FrameRenderer,
    ffmpeg: Path | str | None,
    force: bool = False,
) -> None:
    """Cards + final concat, while the browser is still open."""
    if not summary.chapters:
        return
    parts = _assemble_cards(content_set, summary, st, out, renderer, ffmpeg, force)
    summary.presentation = concat_videos(
        parts, out / "video" / PRESENTATION_NAME, video=st.video, ffmpeg=ffmpeg,
        force=force,
    )
    write_manifest(
        content_set, summary.presentation.path,
        [c.demo_id for c in summary.chapters], summary.narration_provider,
    )

def _assemble_cards(
    cs: ContentSet,
    summary: VideoSummary,
    st: PresentationSettings,
    out: Path,
    renderer: FrameRenderer,
    ffmpeg: Path | str | None,
    force: bool = False,
) -> list[Path]:
    """Build the title/chapter/closing cards and return the full concat order.

    A chapter card is narrated by the *previous* demo's ``transition`` block — which
    is exactly what that block is written for ("next, Claude ports this to Python").
    The first chapter has no predecessor, so its card is silent and the title card
    carries the opening instead.

    The contents card after the title lists where each chapter card starts. The
    chapter cards are sized first, narration included, so those times are exact.
    """
    cards_dir = out / "video" / "_cards"
    total = len(summary.chapters)
    order: list[Path] = []

    def sized(card: Card, audio=None) -> Card:
        if audio is not None:
            card = card.with_duration(audio.seconds + st.timing.narration_tail_seconds)
        return card

    def emit(card: Card, audio=None) -> None:
        card = sized(card, audio)
        image = _card_frame(card, st, cards_dir, renderer, force)
        clip = assemble_card_clip(
            image,
            card.duration,
            out_path=cards_dir / f"{card.id}.mp4",
            video=st.video,
            audio=audio,
            ffmpeg=ffmpeg,
            force=force,
        )
        summary.cards.append(clip)
        order.append(clip.path)

    chapter_cards: list[tuple[Card, object]] = []
    for i, chapter in enumerate(summary.chapters):
        previous = summary.chapters[i - 1] if i else None
        handoff = previous.audio.get(MOMENT_TRANSITION) if previous else None
        handoff_block = previous.narration.get(MOMENT_TRANSITION) if previous else None
        card = chapter_card(
            demo_id=chapter.demo_id,
            title=chapter.title,
            number=i + 1,
            total=total,
            set_title=cs.config.title,
            timing=st.timing,
            narration=(previous.demo_id, MOMENT_TRANSITION) if handoff else None,
            caption=display_text(handoff_block.text) if handoff_block else "",
        )
        chapter_cards.append((card, handoff))

    if cs.config.presentation.intro:
        title = title_card(cs.config, st.timing, demo_count=total)
        emit(title)
        if cs.config.presentation.contents and total > 1:
            contents = contents_card(cs.config, st.timing, entries=[])
            at = title.duration + contents.duration
            entries = []
            for i, (chapter, (card, audio)) in enumerate(zip(summary.chapters, chapter_cards)):
                entries.append((i + 1, chapter.title, at))
                at += sized(card, audio).duration + chapter.seconds
            emit(contents_card(cs.config, st.timing, entries=entries))

    for chapter, (card, audio) in zip(summary.chapters, chapter_cards):
        emit(card, audio=audio)
        # The chapter opens with its own intro cards, already encoded.
        order.extend(chapter.parts)

    if cs.config.presentation.outro:
        emit(
            outro_card(
                cs.config,
                st.timing,
                demo_count=total,
                event_count=summary.event_count,
                seconds=sum(c.seconds for c in summary.chapters),
            )
        )
    return order


def _card_frame(
    card: Card, st: PresentationSettings, out_dir: Path, renderer: FrameRenderer,
    force: bool = False,
) -> Path:
    """Render a card to a content-addressed PNG, cached like any scene frame."""
    html = card_html(card, st.video)
    path = out_dir / f"{card.id}-{frame_key(html, st.video)}.png"
    if force or not path.is_file():
        renderer.render(html, path)
    return path


def _chapter(
    cs: ContentSet,
    demo: Demo,
    st: PresentationSettings,
    out: Path,
    provider,
    renderer: FrameRenderer,
    ffmpeg: Path | str | None,
    lexicon: dict[str, str] | None = None,
    force: bool = False,
    *,
    number: int = 1,
) -> Chapter:
    bundle = cs.display_bundle(demo.id)
    timeline = build_timeline(
        demo.id, bundle.read_events(), scenes=st.scenes, timing=st.timing,
        clocked=bundle.read_metadata().extra.get("event_times") == "wallclock",
    )

    narration = load_narration(demo)
    audio = synthesize_narration(
        narration, provider, cs.config.narration.voice, out / "audio", lexicon, force
    )
    # The introduction belongs to the intro cards, so the replay leaves it out.
    replayed = narration.replayed
    captions = {b.key: display_text(b.text) for b in narration.blocks}
    timeline = stretch_for_narration(
        with_narration(timeline, anchor_narration(timeline, replayed), captions),
        clip_seconds(audio),
        tail=st.timing.narration_tail_seconds,
        # In the session, Claude's narrated messages are paced by their narration.
        floors=streamed_floors(timeline, st.timing)
        if st.timing.replay_style == "session" else None,
    )

    demo_out = out / "video" / demo.id
    write_timeline(timeline, demo_out / "timeline.json")

    context = context_for(
        cs.config.title, demo.title, timeline, bundle.read_results(), demo.checks
    )
    # The replay as one animated Claude Code window, unless the set asks for slides.
    beats = session_beats(timeline, st.timing) if st.timing.replay_style == "session" else None
    if beats:
        # The animation reveals recorded text; it must never show anything else.
        problems = audit_beats(timeline, beats, bundle.read_events())
        if problems:
            raise DemoError(
                f"{demo.id}: the animated replay would show text that is not in the "
                "record:\n  " + "\n  ".join(problems[:10])
            )
    frames = render_frames(
        timeline,
        context,
        out_dir=out / "frames" / demo.id,
        video=st.video,
        renderer=renderer,
        force=force,
        beats=beats,
    )
    intro = _intro_cards(
        demo, narration, audio, number, st, out, renderer, ffmpeg, force
    )
    replay = assemble_demo_video(
        timeline,
        frames,
        out_path=(demo_out / "replay.mp4") if intro else out / "video" / f"{demo.id}.mp4",
        video=st.video,
        audio=audio,
        ffmpeg=ffmpeg,
        force=force,
    )
    video = replay
    if intro:
        joined = concat_videos(
            [c.path for c in intro] + [replay.path],
            out / "video" / f"{demo.id}.mp4",
            video=st.video,
            ffmpeg=ffmpeg,
            force=force,
        )
        video = VideoResult(
            path=joined.path,
            seconds=round(replay.seconds + sum(c.seconds for c in intro), 3),
            cached=joined.cached,
        )
    return Chapter(
        demo_id=demo.id,
        title=demo.title,
        timeline=timeline,
        frames=frames,
        audio=audio,
        video=video,
        narration=narration,
        intro=intro,
        replay=replay,
    )


def _intro_cards(
    demo: Demo,
    narration: Narration,
    audio: dict[str, AudioClip],
    number: int,
    st: PresentationSettings,
    out: Path,
    renderer: FrameRenderer,
    ffmpeg: Path | str | None,
    force: bool,
) -> list[VideoResult]:
    """The demo's introduction as cards, each spoken by its own words, in file order.

    Each ``intro:<heading>`` block gets a card of its own. The older unheaded
    ``setup`` and ``problem`` blocks share one card, as they always have.
    """
    groups: list[list[NarrationBlock]] = []
    for b in narration.intro:
        joins = groups and not b.heading and not groups[-1][0].heading
        if joins and not b.figure and not any(g.figure for g in groups[-1]):
            groups[-1].append(b)
        else:
            groups.append([b])

    cards_dir = out / "video" / demo.id / "cards"
    clips: list[VideoResult] = []
    for part, group in enumerate(groups, start=1):
        figure = next((b.figure for b in group if b.figure), None)
        keys = "+".join(b.key for b in group)
        card = problem_card(
            demo_id=demo.id,
            title=demo.title,
            number=number,
            paragraphs=[display_text(b.text) for b in group],
            timing=st.timing,
            narration=(demo.id, keys),
            heading=group[0].heading,
            part=part if len(groups) > 1 else None,
            figure=(
                figure_view(demo.dir, figure.source, display_text(figure.caption))
                if figure else None
            ),
        )
        spoken = [audio[b.key] for b in group if b.key in audio]
        clip_audio = None
        if len(spoken) == 1:
            clip_audio = spoken[0]
        elif spoken:
            clip_audio = join_clips(spoken, out / "audio", key=keys)
        if clip_audio is not None:
            card = card.with_duration(clip_audio.seconds + st.timing.narration_tail_seconds)
        image = _card_frame(card, st, cards_dir, renderer, force)
        clips.append(
            assemble_card_clip(
                image,
                card.duration,
                out_path=cards_dir / f"{card.id}.mp4",
                video=st.video,
                audio=clip_audio,
                ffmpeg=ffmpeg,
                force=force,
            )
        )
    return clips
