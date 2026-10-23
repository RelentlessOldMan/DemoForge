<!-- Declarative narration, tagged by moment; TTS is cached per block
     (see docs/video-pipeline.md §6). `during:<seq>` blocks play over the scene
     built from that recorded event, and must describe only what it shows.
     Seq numbers refer to approved run 20261020T223427Z-dbe37dfc. -->

## intro:The situation

Release two point two of the tracking filter is ready to ship. Its specification is now
at revision C, which added a sixth requirement after the corrupted-file incident from
demo four: bad measurements, like a NaN or an infinity, must be rejected and reported,
never fed into the estimate. The code passes all three of its tests.

## intro:What they need

They need a traceability matrix: a table that links every requirement to the code that
implements it and the tests that prove it, with a status for each. In regulated
engineering, the release decision rests on that table. Anything not implemented, or
not verified, has to be fixed or explicitly signed off.

## intro:Why that's hard

A test report says what passed, not what was checked. A test can carry a requirement's
name and still be unable to tell right code from wrong. So each status has to come
from what the tests actually exercise, not from their labels.

## during:0

Here's the request. Review the filter against revision C, and produce a spreadsheet
with one row per requirement: whether it is implemented, which tests verify it, a
status from four fixed values, and the evidence. Verified means implemented and fully
verified by tests. Partial means the tests cover only part of it. Not verified means
implemented, but no test verifies it. And not implemented means the code doesn't do it.

## during:1

Claude starts by listing the folder: the spec, the code, the model settings, the
register, the test, its recorded report, and the test data.

## during:3

Then it reads the documents one by one, starting with the spec at revision C.

## during:5

The code under review.

## during:7

The latest recorded test run, and the model settings.

## during:9

A look at the test data: a header line and fifteen hundred measurements.

## during:11

It checks that every row holds two valid numbers. No row is reported as bad. And it
finds Octave and Python on this machine.

## during:13

Rather than trust the recorded report, it runs the existing test itself. All three
tests pass.

## during:15

Next, an experiment. Its first attempt is refused: a safety guard blocks the delete in
that command, so it starts again in a fresh folder.

## during:17

It plants deliberate bugs in copies of the code, one at a time. Ignore the starting
state. Ignore the starting uncertainty. Drop the process noise. Skip the covariance
update. Halve the gain. Hard-code the constants. Then it runs the unchanged tests on
each. Every one of these bugs passes all three tests.

## during:19

Then it checks the code against its own calculation from the model file: an error of
exactly zero. And it feeds in bad input. A NaN at row five turns every estimate from
there on into NaN. An infinity does the same. And a one-column input is accepted
without any error.

## during:21

So the code computes correctly, but bad input goes straight through. Now it writes the
spreadsheet.

## during:24

It writes a script that builds the spreadsheet, with the evidence for each row. For
the first requirement: the code declares exactly the required signature, the first
test calls it, and the rule against reading files, printing or globals holds by
reading the code.

## during:25

The first matrix. R1 and R4 verified. R2, R3 and R5 partial. R6 not implemented.

## during:27

Claude's answer: only R1 and R4 are fully verified, and R6 isn't implemented at all, so
it doesn't think release two point two can go out against revision C. The code itself
matches its separate calculation exactly. But the third test only checks that
positions stay within five of the measurements, so it can't catch errors in the
calculation. Then it explains how it checked. It put ten deliberate bugs into copies of
the code, and the tests caught only one: rows returned in reverse order. All fifteen
hundred rows of test data are valid numbers, so the data never exercises R6. Its
recommended fixes start with input validation, plus tests that feed it bad input. That
is the release blocker.

## during:28

The engineer pushes back on two rows. R1 is marked verified, but Claude itself says no
test checks the rule against reading files, printing or globals. And the third test
missed every recursion bug Claude planted, so nothing really verifies R3. Fix both
rows, and the summary.

## during:29

Claude edits its script. R1 becomes partial: the first test only shows that a
two-argument call returns one output, and the missing test is listed.

## during:31

R3's evidence now says the third test is labelled as covering it, but is insufficient.

## during:32

R5's evidence now says that of R1 to R4, only R4 is fully checked.

## during:34

And the Review Notes sheet gets a status summary line and a new release recommendation.

## during:35

It rebuilds the workbook and reads it back. R3 is now not verified, and R4 is the only
requirement still fully verified.

## during:37

Claude replies that the engineer is right on both counts, and explains each change.
It keeps R2 as partial, because the third test does catch the reversed-row-order bug,
and offers to change that cell if the engineer would rather it didn't count.

## result

The engineer, played here by a second Claude session that never sees DemoForge's
hidden checks, pushed back once and was then satisfied. DemoForge then checked the
spreadsheet on its own. Every requirement is traced, every cited test exists, and the
missing sixth requirement is flagged. One check fails. DemoForge reads the first
requirement as the call signature alone, which the first test does check, so it
expects verified. The engineer read it as also covering the rule against reading
files, printing or using globals, which no test checks, and Claude agreed. That is a
judgement call the spec leaves open, so the result stands as six of seven.

## transition

Each demo so far showed one engineering skill. Finally, Claude takes on a whole
investigation on its own.
