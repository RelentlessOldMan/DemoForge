<!-- Declarative narration, tagged by moment; TTS is cached per block
     (see docs/video-pipeline.md §6). `during:<seq>` blocks play over the scene
     built from that recorded event, and must describe only what it shows. -->

## setup

Same filter, a different language. Teams often need to move working code from one
programming language to another, here from MATLAB to Python, so a data team can use it
with their own tools. We hand Claude the MATLAB version and ask for a faithful
translation.

## problem

Translating code is like translating a legal contract: the words can look right while
the meaning quietly shifts. MATLAB and Python count from different starting points,
arrange numbers differently, and even the order of a calculation can change the last
digits of an answer. Miss any of that, and the translation silently disagrees with the
original.

## during:3

The test data holds only measurements, not the right answers. So Claude decides to
produce the answers itself, by running the original MATLAB code and saving its output
as the reference to compare against.

## during:7

The comparison comes back. Across all fifteen hundred steps, the Python version
matches the original exactly.

## during:9

Then a good engineer's instinct: a perfect score is suspicious. Claude checks that the
reference holds real filter output, and that its comparison would actually catch a
translation that was even slightly wrong.

## result

DemoForge then makes its own comparison, against a reference kept out of Claude's
reach, and the two versions agree exactly. A migration you can trust, not just code
that runs.

## transition

From one algorithm in two languages, next we turn Claude loose on messier material:
logs, spreadsheets, and data it has to investigate.
