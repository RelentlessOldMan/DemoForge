<!-- Declarative narration, tagged by moment; TTS is cached per block
     (see docs/video-pipeline.md §6). `during:<seq>` blocks play over the scene
     built from that recorded event, and must describe only what it shows.
     Seq numbers refer to approved run 20261015T004630Z-84c9298e. -->

## intro:The situation

A tracking system follows a moving object, say a drone, using a sensor that reports
its position again and again. Every reading is a little off, so the raw positions
jitter. The system needs a steady best estimate of where the object really is, and
how fast it's moving.

## intro:The tool for it

The standard answer is a Kalman filter. It's a short piece of math that blends each
new reading with what it predicted, trusting each one in proportion to how noisy it
is. It's the same idea that smooths out a jumpy GPS signal on your phone's map. This
filter is the thread that runs through the whole series.

## intro:What the team has

Priya, their estimator lead, has written a specification that pins down the exact
math. The team also has a file of settings for the filter, and a recording of one
thousand five hundred noisy position readings. Here are the first thirty, close up:
each dot is one reading, and instead of following a smooth path, they zig-zag.

![The first thirty recorded readings, one dot per reading](input/test_vectors.csv#rows=1-30)

## intro:What they need

Working code that follows the specification exactly, written in MATLAB. And an
automatic test that their build system runs on every change, which must stop with an
error if anyone ever breaks the filter.

## intro:Why that's hard

Nobody can check fifteen hundred rows of numbers by eye. And a test that always
passes is worse than no test, because it gives false confidence. So the question
isn't just whether the code runs. It's whether we can prove it's right, and whether
we'll know if it ever stops being right.

## during:0

Here is how the engineer put that job to Claude, in their own words: implement
Priya's specification in MATLAB, with the test it asks for, using the settings file
and the recorded readings.

## during:1

First, Claude reads the specification, the model settings, and the recorded
measurements.

## during:3

Before relying on the measurements, it checks that every row is a clean pair of
numbers, and scans the horizontal positions for sudden jumps.

## during:5

Then it writes the filter itself, following the spec's equations step by step.

## during:6

And a test, which checks the output against each of the spec's requirements,
including a first step worked out by hand.

## during:7

A one-word fix to how the test prints its result.

## during:8

It runs the test in Octave, a free engine that runs MATLAB code. The test fails: the
filter's first step doesn't match the value worked out by hand.

## during:10

Claude changes the hand-worked value in the test.

## during:11

Now the test passes. And because a test that always passes proves nothing, Claude
breaks the filter on purpose. The test catches it, then passes again once the filter
is restored.

## during:13

Claude reports back. Both files are written, and the test passes: all fifteen hundred
readings match the reference to within a rounding error. It flags a limit honestly:
no reference answers came with the spec, so the test compares against a second
version Claude wrote itself. Then it walks through the test, requirement by
requirement, and says it broke the filter on purpose to prove the test catches it.
What it doesn't mention is that the test failed first, and that it changed the test
before it passed.

## during:14

This is where a real review starts. The engineer, played here by a second Claude
session that never sees the hidden checks, has checked the hand-worked numbers, and
they're right. But they noticed the test failed first and was edited before it
passed, and they ask exactly what changed. They also spot that the hand-worked check
is skipped if the model file loads wrong, so a bad load would pass silently.

## during:15

Claude starts by reading its test file again.

## during:16

Then it says what it will do: check the model file as soon as it loads, so a bad
load fails first, and make the hand-worked check run every time.

## during:17

First edit: right after loading, the test now checks every matrix in the model file
against the released values.

## during:18

Second: the guard is gone, so the hand-worked first step is checked every time.

## during:19

Third: it corrects the comment on its reference version, as the engineer asked.

## during:20

Next, it says how it will prove the new check works.

## during:21

It runs the test, then gives it a deliberately broken copy of the model file. The new
check stops it straight away.

## during:23

Claude answers straight. The mistake was in its own hand-worked value, not in the
filter: it had used the wrong number for the expected velocity gain, and the filter's
first answer had been right all along. It says plainly that it should have told the
engineer this the first time. Then it lists each change, shows the new check stopping
a deliberately broken copy of the model file, and points out two side effects the
engineer should know about. The engineer has nothing more to ask.

## result

The finished filter and its test, checked again independently by DemoForge against a
reference answer and a second model Claude never saw. Everything agrees. Working code,
and a test that actually protects it, reached the way real work gets done: by asking
the hard questions and checking the answers.

## transition

This filter is the foundation for what follows. Next, Claude takes the same algorithm
and makes it fast.
