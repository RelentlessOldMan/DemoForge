"""Narration: parsing, anchoring to recorded scenes, and the audio cache."""

from __future__ import annotations

import textwrap
import wave
from pathlib import Path

import pytest

from conftest import CLAUDE_DEMO_KIT, KOKORO_PYTHON, requires_kokoro

from demoforge.config import NarrationConfig
from demoforge.errors import DemoError, DemoForgeError
from demoforge.model import Event
from demoforge.render.config import Timing, load_settings
from demoforge.render.narration import (
    AudioClip,
    PiperTTS,
    SilentTTS,
    anchor_narration,
    audio_key,
    clip_seconds,
    load_narration,
    make_provider,
    parse_narration,
    synthesize_narration,
    wav_duration_seconds,
)
from demoforge.render.timeline import (
    build_timeline,
    narration_spans,
    stretch_for_narration,
    with_narration,
)

NARRATION = textwrap.dedent(
    """
    <!-- a comment, and some notes that must never be spoken -->

    ## setup

    We hand Claude a slow routine.

    ## problem

    It runs per sample.

    ## during:3

    Here it runs the benchmark.

    ## result

    It verified the numbers agree.

    ## transition

    Next, the Python port.
    """
)


def _events() -> list[Event]:
    return [
        Event(seq=0, t=0.0, type="prompt", data={"text": "Make it fast."}),
        Event(seq=1, t=2.0, type="assistant_text", data={"text": "Looking."}),
        Event(seq=2, t=3.0, type="file_read", data={"path": "/w/a.m"}),
        Event(seq=3, t=4.0, type="command", data={"command": "octave bench.m"}),
        Event(seq=4, t=5.0, type="command_output", data={"output": "speedup 47x\n"}),
        Event(seq=5, t=6.0, type="completion", data={"subtype": "success"}),
    ]


def _timeline():
    st = load_settings()
    return build_timeline("demo", _events(), scenes=st.scenes, timing=st.timing)


# ---- parsing ----------------------------------------------------------
def test_blocks_are_parsed_in_file_order():
    n = parse_narration(NARRATION, demo_id="demo")
    assert n.keys == ("setup", "problem", "during:3", "result", "transition")
    assert n.get("problem").text == "It runs per sample."
    assert n.get("missing") is None
    assert bool(n) is True


def test_comments_are_never_spoken():
    n = parse_narration(NARRATION)
    assert all("never be spoken" not in b.text for b in n.blocks)


def test_empty_blocks_and_no_narration_are_benign():
    n = parse_narration("## setup\n\n## result\n\nSaid.\n")
    assert n.keys == ("result",)
    assert bool(parse_narration("just prose, no headings")) is False


def test_duplicate_block_is_rejected():
    with pytest.raises(DemoError, match="duplicate block"):
        parse_narration("## setup\n\nOne.\n\n## setup\n\nTwo.\n", demo_id="d")


def test_normalized_text_ignores_reflowing():
    a = parse_narration("## setup\n\nOne two\nthree.\n").get("setup")
    b = parse_narration("## setup\n\nOne   two three.\n").get("setup")
    assert a.normalized_text == b.normalized_text == "One two three."
    assert audio_key("silent", "v", a.normalized_text) == audio_key(
        "silent", "v", b.normalized_text
    )


def test_estimated_seconds_follows_configured_speech_pace():
    block = parse_narration("## setup\n\n" + "x" * 140 + "\n").get("setup")
    assert block.estimated_seconds(Timing(narration_chars_per_second=14.0)) == 10.0


def test_during_block_exposes_its_event():
    n = parse_narration(NARRATION)
    assert n.get("during:3").is_during is True
    assert n.get("during:3").event_seq == 3
    assert n.get("setup").is_during is False
    assert n.get("setup").event_seq is None


def test_during_block_with_a_nonsense_ref_is_rejected():
    block = parse_narration("## during:later\n\nSoon.\n").get("during:later")
    with pytest.raises(DemoError, match="not an event seq"):
        _ = block.event_seq


# ---- anchoring --------------------------------------------------------
def test_moments_anchor_to_the_scenes_they_describe():
    tl = _timeline()
    anchors = anchor_narration(tl, parse_narration(NARRATION, demo_id="demo"))
    assert anchors[0] == "setup"       # the prompt card
    assert anchors[1] == "problem"     # the scene after it
    # during:3 lands on whichever scene was built from event 3 (the terminal card).
    term = next(s for s in tl.scenes if s.kind == "TerminalRun")
    assert anchors[term.index] == "during:3"
    end = next(s for s in tl.scenes if s.kind == "ChapterEnd")
    assert anchors[end.index] == "result"
    # `transition` plays between demos, so it is not a scene.
    assert "transition" not in anchors.values()


def test_narration_over_a_paged_message_starts_on_its_first_page():
    st = load_settings()
    long = " ".join(f"Sentence number {i} of a long report back to the person." for i in range(120))
    tl = build_timeline(
        "d",
        [Event(seq=0, t=0.0, type="prompt", data={"text": "Hi"}),
         Event(seq=1, t=1.0, type="assistant_text", data={"text": long})],
        scenes=st.scenes, timing=st.timing,
    )
    pages = [s.index for s in tl.scenes if 1 in s.event_seqs]
    assert len(pages) > 1
    anchors = anchor_narration(tl, parse_narration("## during:1\n\nIt reports.\n", demo_id="d"))
    assert anchors == {pages[0]: "during:1"}


def test_narration_may_not_describe_an_event_that_never_happened():
    with pytest.raises(DemoError, match="not in the captured run"):
        anchor_narration(_timeline(), parse_narration("## during:99\n\nNope.\n", demo_id="d"))


def test_no_narration_anchors_nothing():
    assert anchor_narration(_timeline(), parse_narration("")) == {}


def test_anchoring_a_single_scene_run_does_not_overflow():
    st = load_settings()
    tl = build_timeline(
        "d", [Event(seq=0, t=0.0, type="prompt", data={"text": "Hi"})],
        scenes=st.scenes, timing=st.timing,
    )
    # No `during:` block here: a one-scene run has no event 3 to speak over.
    moments = textwrap.dedent(
        """
        ## setup

        A.

        ## problem

        B.

        ## result

        C.
        """
    )
    anchors = anchor_narration(tl, parse_narration(moments))
    # Only the prompt card exists; `problem` has nowhere to go and `result`
    # falls back to the last scene, which is that same card — already claimed.
    assert anchors == {0: "setup"}


# ---- providers --------------------------------------------------------
def test_silent_provider_is_chosen_when_piper_is_absent(tmp_path):
    prov = make_provider(NarrationConfig(provider="piper"), Timing(), piper_bin=None)
    assert isinstance(prov, SilentTTS)
    assert prov.id == "silent"
    assert "piper" in prov.reason


def test_disabled_and_unknown_providers_fall_back_with_a_reason():
    off = make_provider(NarrationConfig(enabled=False), Timing())
    assert off.id == "silent" and "disabled" in off.reason
    odd = make_provider(NarrationConfig(provider="kazoo"), Timing())
    assert odd.id == "silent" and "kazoo" in odd.reason


def test_piper_is_used_when_the_binary_is_given(tmp_path):
    fake = tmp_path / "piper.exe"
    fake.write_bytes(b"")
    prov = make_provider(NarrationConfig(provider="piper"), Timing(), piper_bin=fake)
    assert isinstance(prov, PiperTTS)
    assert prov.id == "piper" and prov.binary == fake


def test_piper_failure_is_reported_not_swallowed(tmp_path):
    prov = PiperTTS(binary=tmp_path / "does-not-exist.exe")
    with pytest.raises(DemoForgeError, match="piper"):
        prov.synthesize("hello", "voice")


def test_silence_is_valid_exactly_timed_and_deterministic(tmp_path):
    prov = SilentTTS(timing=Timing(narration_chars_per_second=10.0))
    data = prov.synthesize("x" * 50, "voice")
    assert data[:4] == b"RIFF" and data[8:12] == b"WAVE"
    assert prov.synthesize("x" * 50, "voice") == data

    path = tmp_path / "s.wav"
    path.write_bytes(data)
    assert wav_duration_seconds(path) == pytest.approx(5.0, abs=0.01)
    with wave.open(str(path), "rb") as fh:
        assert fh.getframerate() == 48000 and fh.getnchannels() == 1


def test_silence_is_never_zero_length(tmp_path):
    path = tmp_path / "s.wav"
    path.write_bytes(SilentTTS().synthesize("", "voice"))
    assert wav_duration_seconds(path) > 0


def test_a_non_wav_file_is_rejected_clearly(tmp_path):
    bad = tmp_path / "nope.wav"
    bad.write_text("not audio", encoding="utf-8")
    with pytest.raises(DemoForgeError, match="not readable as WAV"):
        wav_duration_seconds(bad)


# ---- cache ------------------------------------------------------------
def test_audio_is_content_addressed_and_reused(tmp_path):
    n = parse_narration(NARRATION, demo_id="demo")
    prov = SilentTTS()
    first = synthesize_narration(n, prov, "amy", tmp_path)
    assert set(first) == set(n.keys)
    assert all(c.cached is False for c in first.values())
    assert all(c.path.is_file() for c in first.values())

    stamps = {k: c.path.stat().st_mtime_ns for k, c in first.items()}
    second = synthesize_narration(n, prov, "amy", tmp_path)
    assert all(c.cached is True for c in second.values())
    assert {k: c.path.stat().st_mtime_ns for k, c in second.items()} == stamps


def test_changing_one_sentence_resynthesizes_only_that_block(tmp_path):
    prov = SilentTTS()
    before = synthesize_narration(parse_narration(NARRATION), prov, "amy", tmp_path)
    edited = NARRATION.replace("It runs per sample.", "It runs on every single sample.")
    after = synthesize_narration(parse_narration(edited), prov, "amy", tmp_path)

    assert after["problem"].path != before["problem"].path
    assert after["problem"].cached is False
    for key in ("setup", "result", "transition"):
        assert after[key].path == before[key].path
        assert after[key].cached is True


def test_voice_and_provider_are_part_of_the_key(tmp_path):
    n = parse_narration("## setup\n\nSame words.\n")
    a = synthesize_narration(n, SilentTTS(), "amy", tmp_path)["setup"].path
    b = synthesize_narration(n, SilentTTS(), "ryan", tmp_path)["setup"].path
    assert a != b
    assert audio_key("piper", "amy", "Same words.") != audio_key("silent", "amy", "Same words.")


def test_clip_seconds_feeds_the_timeline(tmp_path):
    seconds = clip_seconds({"setup": AudioClip("setup", tmp_path / "x.wav", 9.5, False)})
    assert seconds == {"setup": 9.5}


# ---- against the real demo --------------------------------------------
def test_real_demo_narration_anchors_and_stretches_its_scenes(tmp_path):
    from demoforge.discovery import load_content_set
    from demoforge.model import RunBundle

    cs = load_content_set(CLAUDE_DEMO_KIT)
    demo = next(d for d in cs.demos() if d.id == "matlab-optimization")
    bundle = RunBundle(cs.approved_dir_for(demo.id))
    if not bundle.exists():
        pytest.skip("no approved bundle committed")

    st = load_settings(cs.root)
    narration = load_narration(demo)
    # Problem first: intro cards, then the run, then the result and the hand-off.
    moments = [k for k in narration.keys if not k.startswith("during:")]
    assert moments[0].startswith("intro:") and moments[-2:] == ["result", "transition"]

    tl = build_timeline(demo.id, bundle.read_events(), scenes=st.scenes, timing=st.timing)
    anchors = anchor_narration(tl, narration)
    by_key = {key: idx for idx, key in anchors.items()}
    assert tl.scenes[by_key["during:0"]].kind == "PromptCard"
    assert tl.scenes[by_key["result"]].kind == "ChapterEnd"
    # Each step commentary plays over the scene built from the event it names.
    for block in narration.blocks:
        if block.is_during:
            assert block.event_seq in tl.scenes[by_key[block.key]].event_seqs

    clips = synthesize_narration(narration, SilentTTS(timing=st.timing), "amy", tmp_path)
    stretched = stretch_for_narration(with_narration(tl, anchors), clip_seconds(clips))
    assert stretched.total_seconds >= tl.total_seconds
    # Every narrated span (a scene, or all pages of a long message) is now at least
    # as long as the words spoken over it.
    leaders = narration_spans(stretched.scenes)
    for s in stretched.scenes:
        if s.narration:
            span = sum(x.duration for x in stretched.scenes if leaders[x.index] == s.index)
            assert span >= clips[s.narration].seconds - 1e-6


# ---- Kokoro provider --------------------------------------------------
class _BatchProvider:
    """Counts how work is split, to prove batching is actually used."""

    id = "batchy"

    def __init__(self) -> None:
        self.batches: list[int] = []
        self.singles = 0

    def synthesize(self, text: str, voice: str) -> bytes:
        self.singles += 1
        return SilentTTS().synthesize(text, voice)

    def synthesize_batch(self, jobs, voice: str) -> None:
        self.batches.append(len(jobs))
        for text, path in jobs:
            path.write_bytes(SilentTTS().synthesize(text, voice))


def test_a_batching_provider_loads_once_for_the_whole_narration(tmp_path):
    n = parse_narration(NARRATION)
    prov = _BatchProvider()
    clips = synthesize_narration(n, prov, "amy", tmp_path)

    assert len(clips) == len(n.blocks)
    assert prov.batches == [len(n.blocks)], "all blocks should go in one batch"
    assert prov.singles == 0


def test_batching_only_covers_blocks_that_are_not_cached(tmp_path):
    n = parse_narration(NARRATION)
    prov = _BatchProvider()
    synthesize_narration(n, prov, "amy", tmp_path)

    edited = parse_narration(NARRATION.replace("It runs per sample.", "It runs per frame."))
    prov.batches.clear()
    synthesize_narration(edited, prov, "amy", tmp_path)
    assert prov.batches == [1], "only the edited block needs re-synthesis"


def test_a_provider_without_batching_still_works(tmp_path):
    clips = synthesize_narration(parse_narration(NARRATION), SilentTTS(), "amy", tmp_path)
    assert all(c.path.is_file() for c in clips.values())


def test_kokoro_speed_is_part_of_the_cache_identity(tmp_path):
    from demoforge.render.narration import KokoroTTS

    fast = KokoroTTS(python=tmp_path / "py.exe", speed=1.2)
    slow = KokoroTTS(python=tmp_path / "py.exe", speed=0.9)
    assert fast.id != slow.id
    assert "kokoro" in fast.id
    # Different speed => different audio => different cached file.
    assert audio_key(fast.id, "af_heart", "same words") != audio_key(
        slow.id, "af_heart", "same words"
    )


def test_an_interpreter_without_kokoro_is_not_chosen(tmp_path):
    from demoforge.render.narration import find_kokoro_python

    assert find_kokoro_python([str(tmp_path / "nope.exe")]) is None
    # Falls back with a reason rather than failing the build.
    prov = make_provider(NarrationConfig(provider="kokoro"), Timing(), kokoro_python=None)
    if prov.id == "silent":
        assert "kokoro" in prov.reason


def test_kokoro_failure_is_reported_not_swallowed(tmp_path):
    from demoforge.render.narration import KokoroTTS

    prov = KokoroTTS(python=tmp_path / "does-not-exist.exe")
    with pytest.raises(DemoForgeError, match="kokoro"):
        prov.synthesize("hello", "af_heart")


@requires_kokoro
def test_kokoro_renders_real_audio_in_one_batch(tmp_path):
    from demoforge.render.narration import KokoroTTS

    prov = KokoroTTS(python=KOKORO_PYTHON)
    n = parse_narration("## setup\n\nA short line.\n\n## result\n\nAnother short line.\n")
    clips = synthesize_narration(n, prov, "af_heart", tmp_path)

    assert set(clips) == {"setup", "result"}
    for clip in clips.values():
        assert clip.path.read_bytes()[:4] == b"RIFF"
        assert clip.seconds > 0.3
    # Cached on the way back through.
    assert all(c.cached for c in synthesize_narration(n, prov, "af_heart", tmp_path).values())


# ---- speech preparation -----------------------------------------------
def test_markdown_notation_is_not_read_aloud():
    """Backticks reach the synthesizer as audible quote marks, so they must go."""
    from demoforge.render.narration import prepare_for_speech

    assert prepare_for_speech("the `/` operator") == "the / operator"
    assert prepare_for_speech("a **fast** and _correct_ port") == "a fast and correct port"


def test_a_dot_inside_a_name_does_not_become_a_sentence_break():
    from demoforge.render.narration import prepare_for_speech

    assert prepare_for_speech("it ignores `model.x0` and `model.P0`") == (
        "it ignores model x0 and model P0"
    )
    # A real sentence end is followed by a space, so it survives.
    assert prepare_for_speech("One. Two.") == "One. Two."


def test_hyphenated_words_split_but_identifiers_do_not():
    """"constant-velocity" is spoken as one glued word; "CVT-VAL-002" is not."""
    from demoforge.render.narration import prepare_for_speech

    assert prepare_for_speech("a constant-velocity filter") == "a constant velocity filter"
    assert prepare_for_speech("chi-squared") == "chi squared"
    assert prepare_for_speech("CVT-VAL-002 and v2.3") == "CVT-VAL-002 and v2.3"


def test_em_dashes_become_a_pause():
    from demoforge.render.narration import prepare_for_speech

    assert prepare_for_speech("it failed — badly") == "it failed, badly"


def test_links_flatten_but_pronunciation_overrides_survive():
    from demoforge.render.narration import prepare_for_speech

    assert prepare_for_speech("see [the plan](http://x/y)") == "see the plan"
    assert prepare_for_speech("say [Kalman](/k1/) now") == "say [Kalman](/k1/) now"
    assert prepare_for_speech("make it [really](+0.5) clear") == "make it [really](+0.5) clear"


def test_the_lexicon_fixes_words_and_defers_to_an_inline_override():
    from demoforge.render.narration import apply_lexicon, prepare_for_speech

    lex = {"kalman": "KAL", "matlab": "MAT"}
    assert prepare_for_speech("a Kalman filter in MATLAB", lex) == (
        "a [Kalman](/KAL/) filter in [MATLAB](/MAT/)"
    )
    # Hand-written wins; it is not re-wrapped.
    assert apply_lexicon("a [Kalman](/MINE/) filter", lex) == "a [Kalman](/MINE/) filter"
    assert apply_lexicon("untouched", {}) == "untouched"


def test_the_lexicon_feeds_the_audio_cache_key(tmp_path):
    """Correcting a pronunciation must re-synthesize that block, with no extra step."""
    n = parse_narration("## setup\n\nA Kalman filter.\n")
    plain = synthesize_narration(n, SilentTTS(), "amy", tmp_path)["setup"].path
    fixed = synthesize_narration(
        n, SilentTTS(), "amy", tmp_path, {"kalman": "KAL"}
    )["setup"]
    assert fixed.path != plain
    assert fixed.cached is False


def test_a_lexicon_file_loads_and_ignores_its_notes(tmp_path):
    from demoforge.render.narration import load_lexicon

    path = tmp_path / "lexicon.json"
    path.write_text(
        '{"_README": "notes", "Kalman": "KAL", "bad": 3}', encoding="utf-8"
    )
    assert load_lexicon(path) == {"kalman": "KAL"}
    assert load_lexicon(tmp_path / "absent.json") == {}


def test_the_content_set_ships_an_audited_lexicon():
    from demoforge.render.narration import load_lexicon, load_narration, prepare_for_speech
    from demoforge.discovery import load_content_set

    cs = load_content_set(CLAUDE_DEMO_KIT)
    lex = load_lexicon(cs.root / "config" / "lexicon.json")
    assert {"matlab", "kalman"} <= set(lex)

    # Those words really are in the narration this fixes.
    spoken = " ".join(
        prepare_for_speech(b.normalized_text, lex)
        for d in cs.demos()
        for b in load_narration(d).blocks
    )
    assert "[MATLAB](/" in spoken and "[Kalman](/" in spoken
    assert "`" not in spoken, "no markdown notation should reach the synthesizer"


# ---- on-screen text and joined clips ---------------------------------
def test_display_text_keeps_the_words_and_drops_the_notation():
    from demoforge.render.narration import display_text

    text = "The **[Kalman](/kˈɑlmən/)** filter in\n`model.P0`, [really](+0.5) — see [docs](http://x)."
    assert display_text(text) == "The Kalman filter in model.P0, really — see docs."


def test_joined_clips_play_back_to_back_with_a_pause(tmp_path):
    from demoforge.render.narration import join_clips, wav_duration_seconds

    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    a.write_bytes(SilentTTS().synthesize("x" * 28, "v"))
    b.write_bytes(SilentTTS().synthesize("y" * 14, "v"))
    clips = [
        AudioClip("setup", a, wav_duration_seconds(a), False),
        AudioClip("problem", b, wav_duration_seconds(b), False),
    ]
    joined = join_clips(clips, tmp_path / "out", key="intro", gap=0.5)
    assert joined.key == "intro"
    assert joined.seconds == pytest.approx(clips[0].seconds + clips[1].seconds + 0.5, abs=0.01)
    assert join_clips(clips, tmp_path / "out", key="intro", gap=0.5).cached


def test_two_blocks_on_one_scene_fail_instead_of_one_vanishing():
    tl = _timeline()
    term = next(s for s in tl.scenes if s.kind == "TerminalRun" and len(s.event_seqs) > 1)
    a, b = term.event_seqs[:2]
    text = f"## during:{a}\n\nIt runs it.\n\n## during:{b}\n\nIt passes.\n"
    with pytest.raises(DemoError, match="merge them into one block"):
        anchor_narration(tl, parse_narration(text, demo_id="d"))
