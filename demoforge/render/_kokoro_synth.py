"""Out-of-process Kokoro synthesis helper (see :class:`demoforge.render.narration.KokoroTTS`).

Kokoro needs torch, a CUDA build and an 82M-parameter model; DemoForge's own
environment deliberately stays tiny. So this runs under whatever interpreter *does*
have Kokoro installed, and the engine talks to it over a jobs file — the same shape
as the Books project's renderer, so the two stay recognisable to each other.

    python _kokoro_synth.py --jobs jobs.json --voice af_heart --speed 1.0

``jobs.json`` is a list of ``{"text": "...", "out": "<file.wav>"}``. Loading the model
is the expensive part, so the whole batch is rendered in one process.

Deliberately dumb: no caching, no text cleaning, no block logic. The engine decides
what needs synthesizing; this just turns text into WAV.
"""

import argparse
import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")  # torch LSTM/weight_norm chatter

SAMPLE_RATE = 24000  # Kokoro's native rate
DEFAULT_GAP = 0.25   # seconds of silence between the pieces Kokoro returns


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True)
    ap.add_argument("--voice", default="af_heart")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--lang", default="a", help="'a'=US English, 'b'=UK English")
    ap.add_argument("--gap", type=float, default=DEFAULT_GAP)
    args = ap.parse_args()

    jobs = json.loads(Path(args.jobs).read_text(encoding="utf-8"))
    if not jobs:
        return 0

    import numpy as np
    import soundfile as sf
    import torch

    from kokoro import KPipeline

    device = "cuda" if torch.cuda.is_available() else "cpu"
    pipeline = KPipeline(lang_code=args.lang, repo_id="hexgrad/Kokoro-82M", device=device)
    gap = np.zeros(max(0, int(round(args.gap * SAMPLE_RATE))), dtype="float32")

    for job in jobs:
        out = Path(job["out"])
        out.parent.mkdir(parents=True, exist_ok=True)
        # Kokoro splits on newlines and returns the pieces with no silence between
        # them, so pad the seams or sentences run together.
        pieces = []
        for _, _, audio in pipeline(job["text"], voice=args.voice, speed=args.speed):
            if pieces and gap.size:
                pieces.append(gap)
            pieces.append(
                audio.detach().cpu().numpy() if hasattr(audio, "detach") else np.asarray(audio)
            )
        if not pieces:
            print(f"EMPTY {out.name}", file=sys.stderr)
            continue
        sf.write(str(out), np.concatenate(pieces).astype("float32"), SAMPLE_RATE, subtype="PCM_16")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
