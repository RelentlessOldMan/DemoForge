<!-- Declarative narration, tagged by moment; TTS is cached per block
     (see docs/video-pipeline.md §6). `during:<seq>` blocks play over the scene
     built from that recorded event, and must describe only what it shows.
     Seq numbers refer to approved run 20261016T194155Z-e2d5ea88. -->

## intro:The situation

The tracking team's Kalman filter, the same one from the first two demos, is written
in MATLAB. Their data team works in Python, with its own tools for crunching numbers,
and wants to run the filter there too.

## intro:What they need

A Python version that gives the same answers as the MATLAB original: every number
within one billionth. Then results from either one can be trusted the same way.

## intro:Why that's hard

MATLAB and Python look alike but differ in quiet ways: where they start counting, how
they lay out numbers, and how they solve equations behind the scenes. A translation
can look perfect and still drift in the last digits, and in a filter, small
differences can grow. And one sample recording only proves so much. The data team
will run settings the sample never tests.

## during:0

Here's how the engineer put the job to Claude. Port the MATLAB routine to Python,
called exactly the same way, so the data team can use it with their tools. It must
agree with the MATLAB version to within one billionth. There's a recorded stream of
readings to check it on, and they want the check left in the folder too.

## during:1

Claude starts by reading what it was given: the MATLAB routine, the filter settings,
and the readings. And it looks for MATLAB itself.

## during:3

MATLAB isn't installed, but Octave, a free program that runs MATLAB code, is. It also
confirms that Python's number library is there, and that every reading is a clean pair
of numbers.

## during:5

It writes the Python version: the same steps as the original, one reading at a time.

## during:6

Then a short MATLAB script that runs the original routine on the readings and saves
every answer at full precision.

## during:7

And a check that runs the Python version on the same readings and compares every
number.

## during:8

It runs both. Across all fifteen hundred steps, the largest difference is exactly
zero.

## during:10

Claude reports a perfect match. And it's careful about one thing: the reference came
from Octave, not MATLAB, so someone with a MATLAB license should run it there once
before relying on it.

## during:11

The engineer, played here by a second Claude session that never sees DemoForge's
hidden checks, isn't convinced. The sample settings are so simple that the tricky part
of the math is never really exercised. The data team will run much richer models. They
ask for a set of harder cases, including one where a key matrix is nearly impossible to
solve accurately, and an error measured for each one.

## during:12

Claude checks which low-level math libraries Python and Octave use underneath.

## during:14

It makes the port accept models of any size, not just the sample's.

## during:15

Then it writes a generator for thirteen test cases, from a fixed random seed: faster
time steps, correlated sensor noise, a nine-state model, a fifty-thousand-step messy
stream, huge coordinates, and models that are nearly impossible to solve.

## during:16

The MATLAB script now runs the original routine on every case.

## during:17

A small fix, so the script runs as a function.

## during:19

And it corrects one comment.

## during:20

The check now compares every case, and reports how hard each one is to solve, and
where it first goes wrong.

## during:21

It tidies the table it prints.

## during:22

The first run crashes. The generator tried to factor one of its own noise matrices in
a way that matrix doesn't allow.

## during:24

It fixes that.

## during:25

This time all thirteen cases run. Further down the output, four fail. The nine-state
model is just over the limit. The three nearly unsolvable ones are off by up to three hundredths: thirty
million times the limit.

## during:27

Claude digs in. It solves those cases a second way, one MATLAB can also use, called
Cholesky. The three nearly unsolvable cases now agree almost perfectly.

## during:29

It swaps that choice into the port.

## during:30

That was the bug. Python's solver always uses one method. MATLAB first looks at the
matrix and picks: a shortcut for triangular ones, Cholesky for symmetric ones, the
general method otherwise. Claude's new helper makes the same choice.

## during:31

Now twelve of thirteen pass. Only the nine-state model is still just over: one point
zero five billionths.

## during:33

To find out why, it steps through that model in Octave and in Python side by side.
They already differ in the very last digit after the first multiplication.

## during:35

It computes a third version with perfectly rounded arithmetic. That one is about
three quarters of a billionth from Octave, and one point three five billionths from
Python. Ordinary rounding, magnified because the positions grow to about ninety
thousand.

## during:37

It notes that the port now needs one more Python library, SciPy.

## during:38

The final run: twelve pass, and that one model is just over.

## during:40

Claude reports. It found and fixed a real bug: on the hardest cases its first version
was off by up to three hundredths. The one remaining failure isn't a translation
error. The two math libraries round differently, and on this model the positions grow
so large that last-digit differences add up to just over one billionth. It argues no
version could pass there without copying one library's exact rounding, and suggests a limit
that scales with the size of each number. And it flags something the team should know:
a single missing reading turns every later estimate into not-a-number, in MATLAB and
Python alike.

## during:41

The engineer accepts the scaled limit, and wants a check that passes cleanly. But they
push on the hardest cases. Those only agree because the new helper copies Octave's
choice of method, and MATLAB uses a different math library. What error should they
really expect there? And should those cases count at all?

## during:42

Claude starts with the limit, then measures how sensitive the hardest cases are.

## during:43

It rereads its check.

## during:44

MATLAB isn't available, so it estimates instead. It nudges the filter's numbers by one
rounding step at every step, about the difference between two math libraries, and
measures how far the answers move. On most cases, they move less than the limit. On the
most fragile one, they move by about five hundredths: tens of millions of times the limit.

## during:47

It adds a private hook to the port, so the check can apply those nudges itself. The
function the data team calls doesn't change.

## during:49

It rewrites the check: a limit scaled to each number, plus that sensitivity, which it
calls the rounding envelope, for every case.

## during:50

And it catches a mistake in how it scaled the envelope.

## during:51

The check passes, in about eighty seconds. Any case whose envelope reaches a tenth of
the limit is only reported, not held to it. That puts five cases in that group,
including the nine-state model and the huge coordinates.

## during:54

Then Claude raises that cut-off, from a tenth of the limit to the whole limit. Now only
the three nearly unsolvable cases are report-only.

## during:56

Before trusting the check, it tries to break it.

## during:57

It plants three changes in the port. A one-in-a-million change to one matrix fails
nine cases. Dropping part of the sensor noise fails too. A harmless reordering passes,
as it should.

## during:59

Claude answers the question: this check can't gate the hardest cases. Against MATLAB
it expects them to miss the limit by thousands of times or more. On the most fragile
one, a single rounding step moves the estimate by twenty-two standard deviations, so
that answer is noise in MATLAB too. That comes from how the filter is written, not from
the port, and the close match with Octave says nothing about MATLAB there. One small
slip: it says dropping the sensor noise failed nine gated cases, but two of those nine
were report-only.

## during:60

The engineer spots a problem. If the check decides which cases count by measuring the
port itself, a bug that makes the port more fragile could excuse its own failure. And
Claude moved the cut-off only after seeing which cases it excluded. That will be
questioned in review. They want a fixed list, and a real failure whenever a report-only
case strays outside its envelope.

## during:61

Claude will mark the three cases in their own case files, then confirm nothing else
changed.

## during:62

First it records a fingerprint of every input and reference file.

## during:64

It reads through the generator.

## during:67

It regenerates the cases with the marks. But the fingerprint check fails: the
generator had deleted every reference file.

## during:69

So it stops the generator from deleting them, reruns the original in Octave, and
confirms every file is identical to before, byte for byte.

## during:71

The inputs and references are unchanged, and the three cases are marked.

## during:73

The check now takes that list from the case files. It passes, and exits cleanly.

## during:75

Then the three planted changes again, in full.

## during:76

Both real bugs fail the check. The harmless change passes.

## during:78

Claude's final answer owns the cut-off change: the engineer was right. Now nothing is
decided at run time. The three cases are a fixed list, chosen from measured results:
their envelopes are thousands to tens of millions of times the limit, while every other
case's is under a third of it. A report-only case now fails if its error goes past ten
times its envelope. It also admits the generator once overwrote its reference files,
and shows they were rebuilt identical. The harmless mutation doubles as a preview of
MATLAB: it moves the hardest cases by about one envelope, roughly what a correct MATLAB
run should show. And it's frank about what's left. The three hardest cases only catch
gross errors, and their envelope still comes from the port being tested. It offers to
fix that bound from a known-good version, and leaves that choice to the engineer.

## result

Then DemoForge checked the port on its own. On the recorded readings, against the
original routine's output, the error is exactly zero. And on a second model Claude
never saw, with different settings and a sensor that measures at an angle, the port
agrees to the thirteenth decimal place. A careful migration, with the limits of the
evidence stated plainly.

## transition

From one algorithm in two languages to a mystery with no code to write: next, Claude
works out why a test failed, from the logs alone.
