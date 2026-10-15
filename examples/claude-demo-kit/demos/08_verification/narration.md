<!-- Declarative narration, tagged by moment; TTS is cached per block
     (see docs/video-pipeline.md §6). `during:<seq>` blocks play over the scene
     built from that recorded event, and must describe only what it shows. -->

## setup

Green tests don't always mean correct code. A test is code that checks other code, and
a weak test can pass even when the code is wrong. Here Claude is given the Kalman
filter, its spec, and an existing test that passes, and asked: does this test actually
prove anything?

## problem

The existing test only ever tries the default settings. The spec also says the filter
must start from whatever starting position and uncertainty the caller provides, and
nothing ever checks that. Hiding in that gap is a real bug.

## during:9

Claude runs the existing test first. It passes, which is exactly the problem.

## during:17

Now its own, stronger tests. Five of them fail.

## during:28

Claude proves the cause: on a scratch copy it fixes just two lines, and every test
passes. One bug, five failures.

## result

The bug: the code ignores the starting values it's given and always starts from zero.
Claude found the requirement nobody tested, wrote tests that use a different starting
point, and caught what the old test sailed past. DemoForge confirms it independently:
with the default settings the output is perfect, and with any other starting point it
is off by about ten.

## transition

From proving one component meets its spec to tracing requirements across the whole
project: next, Claude builds the verification picture end to end.
