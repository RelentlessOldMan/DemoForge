<!-- Declarative narration, tagged by moment; TTS is cached per block
     (see docs/video-pipeline.md §6). `during:<seq>` blocks play over the scene
     built from that recorded event, and must describe only what it shows.
     Seq numbers refer to approved run 20261019T231901Z-678bfef9. -->

## intro:The situation

The tracking estimator is about to ship version two point four. Its requirements live
in a specification, delivered as a PDF, and section seven point three describes a new
part: a measurement gate. A gate is a bouncer for sensor data. It compares each new
reading with what the filter expects, and turns away readings too far off to be
believable.

## intro:What the spec says

The spec gives a formula for how surprising a reading is, computed without inverting a matrix. A
cut-off the caller passes in, taken from a statistics table. And one hard rule: the
gate was added after a corrupted reading poisoned the filter, so a malformed reading
must never be let through, and must never crash the gate.

## intro:What they need

They need the gate itself, written in MATLAB to the exact interface the spec defines. And a test
the team can run in continuous integration, under GNU Octave, that fails the build if
the gate doesn't meet section seven point three. There's also a bench capture: two dozen
real readings from the two measurement modes.

## intro:Why that's hard

The hard part is the test. It has to be strict enough to catch a gate that's subtly wrong, and fair enough
to pass every gate that meets the spec. And a specification never covers everything.
Where it's silent, someone has to notice, and decide what to do.

## during:0

Here's the request, as the engineer typed it. Implement the gate from section seven
point three of the spec, in MATLAB, with the interface it defines. Write a test that CI
runs with Octave, which must raise an error if the gate doesn't meet the spec. And the
bench capture is there for real data: each row is one measurement, its mode, its size,
the cut-off the bench used, and the reading itself.

## during:1

Claude starts by looking at what it has: the spec PDF and the bench capture.

## during:3

It reads the PDF itself.

## during:4

Then the bench capture.

## during:5

It looks for Octave and Python, and finds both: Octave eleven point three is installed.

## during:7

Before writing anything, it works the bench data through in Python: each row's
surprise score, whether it falls under that row's cut-off, and the smallest eigenvalue
of the covariance, which says whether it is a valid one. On screen, the planar rows at
a cut-off of nine point two one, then the first Doppler rows. The rest of the rows are
kept in the record.

## during:9

Then it probes how Octave behaves on a nearly singular matrix. Octave prints a warning,
and that matters, because the spec says the gate must never print.

## during:11

Spec and data read. Next, the gate and its test.

## during:12

The gate. Its header restates the interface from the spec: the reading, its
covariance, and the cut-off, which the caller supplies so the gate holds none of its
own. The reading is admitted only if its score is at most the cut-off.

## during:13

Then the test. It has its own way of computing the score, so it doesn't share the
gate's method, and it records every failure before raising an error at the end.

## during:14

It removes a placeholder it had left in the test.

## during:15

The first run in Octave fails inside the test itself: it asks for the twelfth item of
a list that only has ten.

## during:17

Octave's string splitting merges empty fields, and the bench file has empty cells.

## during:18

With that fixed, the test passes: three hundred and seventy-three checks.

## during:20

A test that passes proves little on its own, so Claude tests the test.

## during:21

It makes deliberately broken copies of the gate, and runs the test against each one.
It catches a strict less-than at the boundary, a hard-coded cut-off, and an infinite
cut-off. But a copy that inverts the matrix passes, and so does one with no finiteness
check.

## during:23

Three broken copies slipped through, it says: the inverted matrix, the missing
finiteness check, and one that doesn't silence warnings. It sets out to find out why.

## during:24

It tries the patterns its test uses to inspect the gate's source code.

## during:26

Its next try fails in Octave: one pattern won't even compile.

## during:28

One spelling of the pattern does match.

## during:30

It compares that with the pattern in the test, and with the gate's source.

## during:32

It prints that part of the test, and runs a copy of it with a debug line added.

## during:34

Then runs just the first part of the test. Ten checks run, and none fail.

## during:36

It concludes the trouble is how Octave handles backslashes in patterns, and switches
those checks to plain string matching.

## during:37

That edit goes into the test.

## during:38

It runs the broken copies again. The inverted-matrix copy still passes.

## during:40

So it looks again at that check.

## during:41

It tries to make one broken copy by hand and search it. The copy can't be written, and
the search finds the inverse only in a comment.

## during:43

It looks at the gate's source byte by byte.

## during:45

And finds the real cause: the inverted-matrix copy was never made. The text
substitution didn't match the backslash, so the test itself may be fine.

## during:46

It switches to Python to make the broken copies.

## during:48

That fails too: Windows Python can't see the temporary folder.

## during:49

So it makes them in a scratch folder next to the work, and runs the test against each.
Now the inverse and the pseudo-inverse are caught, and so is a missing check for a
nearly singular matrix. Turning off the warning suppression, or removing the finiteness
check, still passes.

## during:51

Claude reports. The gate meets each numbered requirement, and the test passes all three
hundred and seventy-three checks. Then one thing the spec doesn't cover. The spec
assumes the covariance is symmetric positive definite, but never says what to do when
it isn't. A covariance that isn't can give a negative score, which would always be let
through. Claude treats those inputs as malformed, and says it should go back to the
spec owner. It lists what its broken copies showed, and one limitation of its source
check. And it flags the bench capture: its last five planar rows used the old version's
cut-off, five point nine nine one. Two readings rejected there would be admitted at
the new default, so the rig may still be running the old configuration.

## result

The engineer, played here by a second Claude session that never sees DemoForge's
hidden checks, read the answer and had no follow-up. Then DemoForge checked the work on its own. Claude's gate matched the hidden reference
on every decision, honoured the cut-off it was given, and handled malformed input. Its test caught all four hidden broken gates. But it also failed the
hidden correct gate: one that does exactly what the spec lists, and no more. Claude's
test demands the extra rejections it chose itself. It raised that gap openly, but it
built its answer into a CI gate, which would block a correct implementation until the
spec owner decides.

## transition

Here the test was stricter than the spec. Next, the opposite: a test suite that passes,
and the question of whether it proves anything.
