<!-- Declarative narration. Blocks are tagged by moment; TTS is cached per block
     (see docs/video-pipeline.md §6). Text lives in git; audio is regenerated only
     when a block's text changes. `during:<seq>` blocks play over the scene built
     from that recorded event, and must describe only what it shows. -->

## setup

This is a real engineering job, not a chatbot question. Code can be correct and still
be too slow to use. We hand Claude a working but slow piece of the filter, and ask it
to make it fast, without changing a single answer it produces.

## problem

The code handles measurements one at a time, in a loop, and our test runs push
hundreds of thousands of them through it, so this one routine dominates the run time.
Making it faster is easy. Making it faster and proving every answer is identical is
the job.

## during:3

First, Claude needs a way to run MATLAB code. It searches the machine and finds
Octave, a free engine that runs MATLAB programs.

## during:7

It writes a faster version. The steps are the same, but the slow, hand-written
arithmetic is replaced with the language's built-in matrix operations. Then it writes
a benchmark that times both versions on the same inputs and compares every answer.

## during:11

The result: about thirty-eight times faster, and every answer identical.

## during:12

Then it checks that its comparison isn't fooling itself. Nudge the input slightly, and
the difference shows up, so a wrong answer would have been caught.

## result

Claude made the routine dozens of times faster without changing a single answer, and
proved both halves of that claim. DemoForge then runs its own benchmark on Claude's
code: about forty-eight times faster, with an error of exactly zero. Everything you're
seeing was captured from the actual run.

## transition

Same algorithm, a different job: next, Claude translates it into another programming
language and proves the two versions agree.
