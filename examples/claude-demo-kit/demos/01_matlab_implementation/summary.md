<!-- What this demo is, for the index page shipped with the videos.
     Same wording as docs/demos.md; keep the two in step. -->

**The problem.** The team has a written specification for the filter's math, a file of
settings, and a recording of 1,500 noisy position readings. They need working MATLAB
code that follows the spec exactly, plus an automatic test that stops the build if
anyone ever breaks the filter. Nobody can check 1,500 rows by eye, and a test that
always passes is worse than none.

**What Claude did.** It wrote `kalman_update.m` and `test_kalman_update.m`, and ran them
under GNU Octave. When the engineer noticed that a hand-worked check had failed and been
edited before it passed, Claude explained that the mistake was in its expected value,
not the filter. It said plainly that it should have reported that the first time. It
then made the test stricter: it checks the loaded settings, and the first-step check
now always runs.

**The outcome.** The filter matches the reference with an error of exactly zero, also on
a second set of settings Claude never saw. The test passes on correct code and fails on
a deliberately broken filter.
