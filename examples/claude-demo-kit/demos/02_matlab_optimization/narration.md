<!-- Declarative narration, tagged by moment; TTS is cached per block
     (see docs/video-pipeline.md §6). `during:<seq>` blocks play over the scene
     built from that recorded event, and must describe only what it shows.
     Seq numbers refer to approved run 20261016T011849Z-03c28e04. -->

## intro:The situation

The tracking team's Kalman filter works, and it gives the right answers. But it's
slow. Their validation runs push long streams of readings through it, and almost all
of that time is spent inside this one routine.

## intro:Why it's slow

It's slow because the routine was translated line for line from an older program in C. Every
multiplication and addition of every matrix is spelled out as its own little loop,
one number at a time. Correct, but MATLAB is at its slowest when it's made to work
that way.

## intro:What they need

They need a faster version that can be dropped in place of the old one, for whatever filter
settings it is given. And it must not change the answers: every number has to agree
with the old routine to within one billionth.

## intro:Why that's hard

That's harder than it sounds, because computers round off every result to a fixed number of digits, so adding the same
numbers in a different order can change the last digit. Fast code usually does add
them in a different order. Those tiny differences can grow on a long run, so "the
same answers" has to be proven, not assumed. And speed figures are easy to get wrong:
a busy machine, or a lucky test case, can make code look faster than it is.

## during:0

Here's how the engineer put the job to Claude. The routine is correct but slow, and
real streams are much longer than this fifteen-hundred-reading sample. They want a
faster version under a new name, called exactly the same way, that works for any
filter settings and keeps every answer within one billionth. They also want a
benchmark that compares the two on the sample, and a short write-up with the
runtimes, the speedup, the error, and what changed.

## during:1

Claude starts by reading the slow routine, the filter settings, and the readings.

## during:3

It checks that every reading is a clean pair of numbers, and that Octave, a free
engine that runs MATLAB code, is available.

## during:5

Then it writes the fast version. Same steps, but the hand-written loops are replaced
with MATLAB's built-in matrix arithmetic.

## during:6

And a benchmark that times both versions on the same readings, and compares every
answer they give.

## during:7

It runs it. Fifty-six times faster. On the team's own settings, every answer is identical. On
four made-up filter settings, the answers differ, but only in the thirteenth decimal
place.

## during:9

The benchmark passes, so Claude moves on.

## during:10

A quick check that the new version also runs when the sensor reports one or three
numbers instead of two.

## during:12

Then it writes up what it did and what it measured.

## during:13

And tidies a table in it.

## during:14

Claude reports back: fifty-six times faster, and identical on the sample. It's clear
about the limits: it timed this in Octave, not MATLAB, and for sensors with other
than two numbers there's no old version to compare against.

## during:15

The engineer, played here by a second Claude session that never sees the hidden
checks, pushes back. Real streams are much longer than fifteen hundred readings, and
the one-billionth limit is absolute, so any error grows as the numbers get larger.
They ask for a hundred thousand readings, on the team's settings and on a harder set.

## during:16

Claude warns that this will take a while: the old routine alone needs about six
minutes per long stream.

## during:17

It adds the two long streams to the benchmark.

## during:18

And runs it, in the foreground, from start to finish. The team's own settings stay identical, all the way to positions in the millions.
But on the harder settings the error reaches two point eight ten-billionths. That's
still inside the limit, but by less than four times.

## during:20

It adds both results to the write-up.

## during:21

Claude doesn't bury that. It explains why: the built-in arithmetic adds numbers in a
different order, and the error grows with the size of the position. On longer runs
the limit would eventually fail. So it proposes doing the additions in exactly the
same order as the original, which would make every answer identical, whatever the
settings and however long the stream. The alternative is to loosen the limit, and it
asks which the engineer wants.

## during:22

The engineer chooses identical answers, on any settings, rather than a looser
limit. Then they ask for the full benchmark again, long streams included, with every
figure in the write-up taken from that one run. None of the earlier fifty-six times
numbers. And if a busy machine skews the timings again, say so.

## during:23

Claude sets out to rebuild the fast version.

## during:24

Each product is now built up one term at a time, in exactly the original's order,
but a whole column at a time instead of one number at a time.

## during:25

It checks: identical on the sample and on all four made-up settings. But it's now
only four or five times faster than the original.

## during:27

To win back speed it moves those loops into the main routine.

## during:28

Then it spots a mistake in its own rewrite: the last step reads a matrix it has just
cleared, and calls a helper that doesn't exist.

## during:29

It fixes that.

## during:30

Still identical everywhere, and now about twice as fast as the previous attempt.

## during:32

Then Claude notices something about the filter itself. One of its matrices, the
uncertainty, never depends on the readings at all. So it tests whether that matrix
eventually stops changing. On the team's settings, it stops changing at step fifty-nine.

## during:34

The team's settings settle, but the harder ones, and three of the made-up ones, don't.

## during:35

On the harder settings it never quite settles, so Claude checks whether it falls
into a repeating cycle instead. It does: a sixteen-step cycle, from step one hundred fifty-three. Three of the
made-up settings repeat too. The largest one doesn't, not in three thousand steps.

## during:37

So Claude adds an exact shortcut. Once that matrix repeats, bit for bit, the steps
that depend on it repeat too. The routine reuses them, and only does the work that
depends on each new reading.

## during:38

It checks the shortcut right around step fifty-nine, where it switches on, and on
every other case. All identical.

## during:40

It rereads its benchmark before changing it.

## during:41

It rebuilds the benchmark so that it fails unless every single check is identical.

## during:42

And runs everything, once, from start to finish. Every check is identical, including both long streams. Thirty point six times
faster on the sample.

## during:44

It rewrites the write-up from this one run.

## during:45

It repeats the quick check for sensors that report one or three numbers.

## during:46

In the write-up, it drops the error figure that belonged to the earlier version.

## during:48

And it notes that the step-fifty-nine figure came from a separate test, not the benchmark.

## during:49

The same goes for the model that never settled.

## during:50

Claude reports. Every answer now matches the original exactly, so the limit holds
however long the stream gets. It's open about the cost: models whose uncertainty
never repeats get no shortcut, at about nine times. One small slip here: it says the
timings varied by less than two percent, but the raw output shows up to about three.

## during:51

The engineer spots what matters most. Most of that thirty times comes from the
shortcut, and the nine times only appears in the chat. They ask for both numbers,
side by side, from the same run, before either one is quoted.

## during:52

Claude adds a switch that turns the shortcut off, so the two can be timed on the
same readings.

## during:53

The switch goes in as an optional extra input, so existing calls don't change.

## during:54

With the shortcut on unless it's asked to switch it off.

## during:55

When it's off, every step is computed in full.

## during:56

Next, the benchmark checks that the version without the shortcut is identical too.

## during:57

It adds that case to the benchmark, timing all three versions in turn.

## during:58

And it times all three in turn, keeping the fastest and slowest of each, so a busy machine shows up.

## during:59

And runs the full benchmark again. Thirty point seven times with the shortcut, nine point four without. Every answer
still identical.

## during:61

It rereads the write-up before updating it.

## during:62

It puts both numbers next to each other in the write-up.

## during:63

It explains why the shortcut helps so much here: after step fifty-nine, fourteen hundred and forty-one of the fifteen hundred steps skip the hard part.

## during:64

And for a model whose matrix never repeats, it says to expect nine point four times, not thirty point seven.

## during:65

Finally, it documents the switch, and that the answers are the same either way.

## during:66

Claude's final report puts the two side by side. Nine point four times is what the
exact arithmetic gives on its own. Quote that for a model that hasn't been checked.
And it catches a busy machine: the old routine was much slower on one long stream
than the other, for the same work, so it marks that fifty-two times as inflated.
It says the sample timings varied by about one percent. In fact it was up to about
two, still too small to matter.

## result

Then DemoForge checked Claude's code on its own: a longer stream, and a second set of
filter settings Claude never saw. Against the original, every answer was identical:
an error of exactly zero. Against DemoForge's own independent filter, which adds in a
different order, the timed runs agree to the thirteenth decimal place. And on
DemoForge's own timing, it's thirty-three times faster. The engineer got what they
actually asked for, and two honest numbers to choose from.

## transition

Same algorithm, a different job: next, Claude translates it into another programming
language and proves the two versions agree.
