<!-- Declarative narration, tagged by moment; TTS is cached per block
     (see docs/video-pipeline.md §6). `during:<seq>` blocks play over the scene
     built from that recorded event, and must describe only what it shows. -->

## setup

In aerospace, medical and automotive engineering, it isn't enough for software to
work. Every requirement has to be linked to the code that implements it and the test
that proves it. That linking table is called a traceability matrix. Claude is handed
the spec, the list of requirements, the code, the tests and their results, and asked:
which requirements are actually verified?

## problem

Every test passes, but passing isn't the same as proving. Two requirements are
quietly unmet. The starting-values behaviour is implemented but never tested. And the
rule added after the corrupted-file incident from demo four, reject garbage
measurements, is neither implemented nor tested.

## during:8

Claude doesn't just trust the paperwork. It runs experiments. Feed the filter one bad
reading, and forty-one of the fifty outputs turn to garbage, with no error raised.

## during:16

The finished matrix: two requirements fully verified, three only partly, and one not
covered at all.

## result

Claude maps every requirement to its code, its test and its result. It marks the
starting-values requirement as only partly verified and the garbage-input rule as an
outright gap, with the evidence beside each call. DemoForge reads the spreadsheet back
and confirms all six requirements are traced and the gaps are flagged.

## transition

Individually, each demo showed one engineering skill. Finally, we turn Claude loose on
the whole project at once.
