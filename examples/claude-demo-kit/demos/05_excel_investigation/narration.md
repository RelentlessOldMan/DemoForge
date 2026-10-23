<!-- Declarative narration, tagged by moment; TTS is cached per block
     (see docs/video-pipeline.md §6). `during:<seq>` blocks play over the scene
     built from that recorded event, and must describe only what it shows.
     Seq numbers refer to approved run 20261017T035236Z-d4cb09cb. -->

## intro:The situation

The tracking team's latest release, version two point three, has already shipped. Its
release record cites an acceptance campaign: forty test runs that decide whether a
release is good enough. The campaign's spreadsheet says ACCEPT.

## intro:What they have

The spreadsheet has three sheets. One holds the pass limits, one the forty recorded
runs with a PASS or FAIL for each, and one the summary: how many passed, the pass rate,
and the verdict. Next to it is the validation plan, the document that defines what
passing means.

## intro:What they need

Before the release record is closed, quality assurance wants an independent sign-off
review. Is the ACCEPT right? And the spreadsheet is the template for every future
campaign, so whatever is fixed has to give the right answer next time too.

## intro:Why that's hard

The trouble is, the spreadsheet agrees with itself. Every run says PASS, the pass rate is a hundred
percent, and the verdict follows. A mistake in a spreadsheet doesn't show on the
screen; it hides in one cell or one formula, and only shows when you check it against
the plan.

## during:0

Here's the request, as the quality engineer typed it. Version two point three went out
on the thirtieth of May, and the campaign workbook says ACCEPT. Before the record is
closed, they want the workbook reviewed against the validation plan: is the ACCEPT
right? They ask for three things. A corrected copy, which is also the template for future
campaigns, so it has to stay formula-driven, with the recorded run data untouched. A
short note for the release record. And a small structured file, in a set form, that
cites the cells at fault in the workbook as it was received.

## during:1

Claude starts by listing the folder: the plan and the workbook. Then it reads the plan
itself, the document that says what passing means.

## during:3

Then it reads every cell of the workbook, formulas included. On the limits sheet, the
position-error limit is five metres.

## during:5

It looks for hidden rows, formats, and the values the workbook last showed: forty runs,
forty passed, a hundred percent.

## during:7

It saves a corrected copy: the limit set to half a metre, and a PASS formula that checks
both limits. Then it recomputes the result on its own, straight from the run data:
thirty-four of forty pass, and six runs fail.

## during:9

The structured file: REJECT, the counts, the six failing runs, and the cells at fault.

## during:10

With the workbook and the structured file done, it turns to the note for the release
record.

## during:11

The note's conclusion: the ACCEPT recorded for this campaign is wrong.

## during:12

Claude reports. Thirty-four of forty runs pass: a pass rate of eighty-five percent,
against the ninety-five the plan requires. The verdict is REJECT. The five-metre limit
let six runs pass that should have failed, every one of them a maneuver run. Two
smaller defects don't change this result but matter for the template: the runtime limit
was never checked, and the summary only counted the first forty rows. And since the
release already shipped citing this campaign, quality assurance will have to deal with
that.

## during:13

The quality engineer, played here by a second Claude session that never sees
DemoForge's hidden checks, confirms the REJECT against the plan. But two things are
left before they'll sign. The summary now looks a thousand rows down, while the PASS
formulas still stop at row forty-one: in a sixty-run campaign, the numbers wouldn't add
up. And the workbook still names the original preparer next to a REJECT verdict,
claiming a sign-off nobody gave.

## during:14

Claude decides to count passes straight from the run data, so the summary can't depend
on how far the PASS column was filled.

## during:15

To test its formulas, it installs a Python library that can calculate spreadsheet
formulas.

## during:17

It rewrites the workbook's formulas.

## during:19

Then it calculates them: on the corrected file, and on a test copy with sixty runs, a
blank row, and the PASS column left unfilled.

## during:20

The numbers are wrong: no passes at all, and errors in the summary.

## during:22

So it tests the library itself, on a four-row sheet whose answers it knows. The library
miscounts one kind of condition the formulas used.

## during:24

It rewrites the summary with functions it can check, and runs the tests again. The
corrected file now gives forty runs, thirty-four passed, six failed.

## during:26

Two last checks.

## during:27

A clean sixty-run copy passes the data check, and the recorded run data is unchanged.

## during:30

Then it brings the review note up to date.

## during:31

Both changes go into the note.

## during:32

Its answer: the summary now scores every run from the data, and passed plus failed
always adds up to the total. The tests on the sixty-run copies are in a table. And the
original preparer's name is cleared: a new sign-off row is left empty for whoever signs,
and a revision note records that the original ACCEPT came from the wrong limit.

## result

Then DemoForge checked the work on its own. It calculated the corrected workbook's own
formulas, on the real data and on five altered versions Claude never saw: every run
within limits, some runs too slow, values exactly on a limit. Every result, count, and
verdict followed the plan. The limits match the plan, the run data is untouched, and
every cell the findings cite exists.

## transition

The spreadsheet held its own mistake. Next, Claude gets raw data, and only theories
about what's wrong with it.
