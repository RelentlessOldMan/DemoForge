<!-- Declarative narration, tagged by moment; TTS is cached per block
     (see docs/video-pipeline.md §6). `during:<seq>` blocks play over the scene
     built from that recorded event, and must describe only what it shows.
     Seq numbers refer to approved run 20261019T173141Z-13c0c389. -->

## intro:The situation

The tracking team runs a regression batch every night. Each test case runs on one of
two worker machines, and its result is compared with a reference filter. A case passes
when its error is below one in ten million. Lately, the nightly goes red far more often
than it used to.

## intro:What they have

They have an export of two months of nightly results, May and June: one row per test case per
night, with the date, the worker, the software version, the error, and the run time.
And a handful of theories: flaky tests, or one of the worker machines.

## intro:What they need

They need an answer the team update can rest on. When did it start, what does it line up with,
how big is the effect, and which theories does the data rule out? Plus a plot for the
update, and the key numbers in a small file the tracker reads.

## intro:Why that's hard

So far, nobody has actually gone through the numbers. The differences that stand out in a
dataset aren't always the ones that matter: one worker is clearly slower than the
other. Is that the cause, or just a difference? Only the data can say.

## during:0

Here's the request, as the engineer typed it. The nightly has been going red far more
than it used to, and all they've heard so far are theories. They ask Claude to dig in:
when it started, what it lines up with, how big the effect is, and which explanations
the data rules out. A write-up with a plot for the team update, and the key numbers in
a small file for the tracker. That file's form is spelled out: when it started, which
column explains it and the value responsible, the size of the effect as a ratio of
medians, the workers affected, and statistics for every version.

## during:1

Claude starts with the file itself. The folder holds just the export. Then the first
rows: the batch, the date, the test, the worker, the version, and then the error and the
run time.

## during:3

Then it loads the whole file, checks each column's type, and counts the missing values
in every column.

## during:5

It groups the results night by night: each night's version, the median and the worst
error, how many cases failed, and the run time. On screen are the first nights of May:
version two point two, a median error around three in ten billion, and no failures. The
rest of the sixty nights is kept in the record.

## during:7

Next, it looks at the failures. One line of its script breaks, but the output before
that line is there. On version two point two, exactly one case failed: test eighteen
thirty-eight, on the fourteenth of May. And every test always runs on the same worker.

## during:9

It runs the statistics again. First, that one test: over its thirty runs on version two
point two, the median error is about three in ten billion, and its worst, the failure,
is more than a hundred times higher. Then the whole file on a log scale: the typical
error moved from about ten to the minus nine and a half before the change, to ten to the
minus seven point three after it.

## during:11

Its conclusion so far: the error jumped about a hundred and seventy times on the first
night of version two point three. Workers and individual tests don't explain it.

## during:12

For the plot, it loads a skill with guidance on chart design.

## during:13

It reads the skill's colour palette: the chart background, the text colours, and the
first series colour.

## during:15

Then the full palette table, and the skill's own check on the two colours it picked,
blue and orange, one for each worker.

## during:17

It writes an analysis script that draws the plot and produces the numbers file.

## during:18

Running it writes the numbers file: version two point three against two point two, a
factor of one hundred and seventy-one point eight, on both workers. Then the statistics
for each version, starting with two point two's fifteen hundred and thirty runs.

## during:20

Then it opens the plot image and looks at it.

## during:21

It spots a label overlapping the legend, and wants the night with no batch, the
fourteenth of June, marked on the chart.

## during:22

First it moves the threshold label, with a short script that edits its own analysis
code.

## during:24

It looks at the plot again.

## during:25

It finds the line in its script that labels the lower panel, the failure counts.

## during:26

There it adds a "no batch" note under the fourteenth of June.

## during:27

It redraws the plot.

## during:29

And it checks the plot once more.

## during:30

Then the write-up: the short version first, then the plot, then a description of the
data itself.

## during:31

Claude reports. The nightly started going red on the thirty-first of May, the first
batch on version two point three. The median error jumped about a hundred and
seventy-two times, on every test and both workers, and two point three point one
didn't fix it. That's also why it looks flaky: the errors now sit just below the
limit, so ordinary noise pushes about one case in five over it each night. The slower
worker was slower before the change too. And one thing it says the data can't
separate: the version and the date changed together, so anything else that changed
that night would look the same.

## during:32

The engineer, played here by a second Claude session that never sees DemoForge's
hidden checks, has gone through the numbers. One line overstates them: the write-up
says the errors before and after the change don't overlap at all, but the single May
failure sits above most of the later errors.

## during:33

Claude rewords that line.

## during:34

And it points out that it made the same overstatement in its summary. Nothing else
changes.

## result

Then DemoForge checked the work on its own. Straight from the raw export, it
recomputed when the regression started, which version caused it, how big it is, and
which workers it hits, plus the run count, mean, median and failure rate of every
version. Claude's numbers file matched all of them, and it put the cause on the
version, not on the slower worker.

## transition

The data held its own answer. Next, Claude builds from a document: a requirements
specification, delivered as a PDF.
