<!-- Declarative narration, tagged by moment; TTS is cached per block
     (see docs/video-pipeline.md §6). `during:<seq>` blocks play over the scene
     built from that recorded event, and must describe only what it shows.
     Seq numbers refer to approved run 20261020T190150Z-920699ac. -->

## intro:The situation

The tracking filter from the first demo is about to go out in release two point one.
The candidate code is written, it has a specification, and it has a test. The test
passes. Before it ships, the release engineer wants someone independent to check the
code against the spec.

## intro:What they need

They need a verdict they can act on. If something is wrong, which requirement it breaks and which
lines cause it, so the fix can go back to the code's author, with the code itself left
untouched. And a stronger test: one that fails on code that doesn't meet the spec, and
passes on code that does.

## intro:Why that's hard

A passing test only proves something if its inputs could have told a right answer from
a wrong one. A filter has settings the caller supplies. If a test only ever tries the
defaults, code that quietly ignores those settings looks perfect.

## during:0

Here's the request, as the engineer typed it. Verify the filter against its spec,
leave the code as it is, and deliver three things. A test that runs in Octave, exits
with an error if a check fails, and passes for any implementation that meets the spec.
A short report: the conclusion, what the existing test does and doesn't establish, and
what the new tests cover. And a findings file, in a fixed form: a verdict, and for each
defect, the requirement it breaks, one sentence, and the file and line as evidence.

## during:1

Claude reads everything in one go: the spec, the code with line numbers, the model
settings, the existing test, and the start of the recorded data.

## during:3

It runs the existing test first. It passes, on fifteen hundred recorded measurements.

## during:5

Then it writes its own test. It computes the spec's recursion independently and
compares. And it repeats the comparison with each setting in the model changed in turn,
so any value the code hard-codes instead of reading will show up.

## during:6

The first run. Most checks pass, but the starting state and the starting uncertainty
both fail, by point six one and point one five seven, against a tolerance of one in a
million. Changing every setting at once fails too. Changing any other single setting
gives an error of zero.

## during:8

Next it patches its own test, rewriting the check that the filter prints nothing, and
runs it again. The starting state and starting uncertainty still fail.

## during:10

That same command also ran the test on a scratch copy with just the two starting lines
corrected. Claude sums it up: the test fails on the shipped code, and passes on the
corrected copy. Now the report and the findings.

## during:11

It writes the findings file: a defect against requirement R3, citing lines eighteen and
nineteen.

## during:12

Then the report, conclusion first: a defect found, and not ready for release two point
one.

## during:13

Then checks its own citations. The spec's initialisation rule is on line sixty-seven.

## during:15

Its findings file had pointed at line forty-nine, so it corrects that.

## during:17

Claude reports. The code shouldn't ship as it is: lines eighteen and nineteen start the
filter from zeros and the identity, and never read the starting values in the model.
The current model happens to use exactly those values, which is why, it says, the existing
test and even the spec's own acceptance check pass. It lists what the old test does and
doesn't show, what its sixteen checks cover, the results on the shipped code and the
corrected copy, and the rules it checked by reading the code rather than by test.

## result

The engineer, played here by a second Claude session that never sees DemoForge's hidden
checks, read the answer and had no follow-up. Then DemoForge checked the work on its
own. Claude's test passed a hidden correct filter, and failed all three hidden versions
that mishandle the starting values, plus all six with other slips in the recursion. Its
findings blamed the right requirement and the right lines, and nothing else. With the
default model, the shipped code's output is exact. With a different starting point, it
is off by more than ten.

## transition

Here Claude checked one function against its spec. Next, the whole picture: tracing
every requirement to the code and the tests that cover it.
