<!-- Declarative narration, tagged by moment; TTS is cached per block
     (see docs/video-pipeline.md §6). `during:<seq>` blocks play over the scene
     built from that recorded event, and must describe only what it shows.
     Seq numbers refer to approved run 20261016T232615Z-9770be85. -->

## intro:The situation

Every night, the tracking team runs a batch of fifty-one tests against their filter on a
dedicated machine. Last night, one of them, test eighteen forty-seven, failed. The other
fifty passed.

## intro:What they have

All they have to go on is the logs: the running diaries that each part of the system writes as it works. There are
five of them. One from the scheduler that hands out tests, one from the service that
prepares each test's data, one from the workers that run the filter, one from the
runner that judges the results, and one from the machine itself.

## intro:What they need

Tonight's batch runs on the same machine. Before then, the engineer in charge needs to
know whether eighteen forty-seven is a real problem or a one-off, and what to change.

## intro:Why that's hard

The error message points at the filter: it says the math produced a result that isn't a
number. But that's only where the failure surfaced. The cause could be anywhere across
five files, and the same few minutes hold other warnings that look just as suspicious.

## during:0

Here's how the engineer put it to Claude. Work out what happened to eighteen forty-seven
and why. Write it up for the team: the cause, the log lines that show it, what was ruled
out, and what to change. Before tonight's run, they want to know whether it's a real
problem or a one-off. And they spell out a small structured file for their issue
tracker: the component where it started, the chain of events, and every piece of
evidence as a file and line number, including the things ruled out.

## during:1

Claude starts by listing the logs and counting their lines.

## during:3

They're small enough to read in full, so it does.

## during:4

Every one of them, not just the log that reported the failure. The machine's own log
first.

## during:5

Then the scheduler's.

## during:6

The runner's, where the failure was reported.

## during:7

The data service's.

## during:8

And last, the filter workers'.

## during:9

Then it writes its findings. The filter isn't to blame. The disk the tests share ran
out of space at the exact moment the data service was writing eighteen forty-seven's
input file. The write failed partway through. The service logged the error, yet still
marked the cut-off file as ready to use.

## during:10

And the structured version for the tracker: where it started, the chain of events, and
the fourteen log lines it rests on, each with a note on what it shows. The disk was
already ninety-five percent full when the batch began, and at one hundred percent by a
quarter past two.

## during:11

It checks that the file reads back correctly.

## during:13

Claude reports. The filter read the cut-off file: eleven hundred and eighty good rows,
then a half-written one. It filled the missing value with not-a-number, and the math
failed from there. So the filter was never the problem: the same worker passed the very
next test. It ruled out the other warnings one by one: a license timeout and slowdowns
on the other worker, an earlier test that needed a retry, network and archive hiccups
minutes before. Its first fix: never mark a file ready after a failed write.
And one thing it can't explain from these logs: the disk grew by about a gigabyte
during the run, far more than the test files themselves.

## during:14

The engineer, played here by a second Claude session that never sees DemoForge's
hidden checks, has checked the chain against the logs, and it holds. But one sentence
claims more than the logs show: that the cleanup only runs once the disk is completely
full. The log only says it runs above ninety-eight percent. It fired at one hundred
because that was the next reading.

## during:15

Claude rereads its write-up.

## during:16

It rewrites the sentence to say only what the log says.

## during:17

And fixes the same claim where it appears again, further down.

## during:18

It confirms both changes and checks the rest of the write-up for the same claim. The
tracker file never made that claim, so it stays as it was.

## result

Then DemoForge checked the findings on its own, against the logs. Every cited line
exists. The evidence includes the full disk, the cut-off file marked ready, and the
failed math. None of the red herrings is cited as a cause, and all three kinds are
explicitly ruled out. A diagnosis the team can check line by line.

## transition

Same detective work, a different source: next, Claude digs into a spreadsheet instead
of logs.
