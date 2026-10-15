<!-- Declarative narration, tagged by moment; TTS is cached per block
     (see docs/video-pipeline.md §6). `during:<seq>` blocks play over the scene
     built from that recorded event, and must describe only what it shows. -->

## setup

This is the finale. Claude gets an entire project: specifications, configuration,
source code, tests, data, a spreadsheet, logs, and a colleague's handover notes. And
one sentence of direction: the validation campaign failed, find out why.

## problem

Nothing points at the answer. All the tests pass. The handover notes confidently blame
an old firmware bug, a slow machine, or a new sensor that's too noisy. But the failures
are real: eighteen of sixty test runs miss the accuracy limit, and the campaign is
rejected. Finding the true cause means connecting the spec, the settings, the code,
the tests, the data and the logs.

## during:7

Claude starts with the data: sixty runs, each tagged with sensor mode, firmware and
machine. The failures all fall in the new three-dimensional sensor mode.

## during:11

Reading the logs and the code, a suspect emerges. The measurement gate, the bouncer
from demo seven, uses a fixed threshold written straight into the code.

## during:16

Claude tests it directly. It hands the gate wildly different thresholds, even a
million, and the gate's decision never changes. It's ignoring the setting it's given.

## during:20

Then the numbers close the case. A threshold built for the old two-dimensional sensor
should throw away about eleven percent of good three-dimensional readings, and the
logs show exactly that.

## result

Claude's report lays out the chain. The gate's threshold was written for the old
two-dimensional sensor and never updated, so with the new sensor it throws away about
one good reading in nine instead of one in a hundred. Starved of data, the tracker
drifts past the accuracy limit. The tests never caught it because they only tried the
old sensor, with the old threshold. Claude names everything it ruled out and
recommends the fix. DemoForge independently recomputes the failure pattern from the
project's own data and confirms it.

## transition

Ten demonstrations, one engineering system, and every result on screen was captured
from a real run. Everything you have seen, the demos, the captured transcripts, the
slides, and this narration, was generated from this repository.
