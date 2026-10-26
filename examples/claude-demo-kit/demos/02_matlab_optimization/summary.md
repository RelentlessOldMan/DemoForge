<!-- What this demo is, for the index page shipped with the videos.
     Same wording as docs/demos.md; keep the two in step. -->

**The problem.** The filter is correct but slow. It was translated line by line from C,
with every matrix operation spelled out as loops. The team needs a drop-in faster
version that changes no answer by more than one billionth. Rounding makes that hard:
adding numbers in a different order can change the last digit.

**What Claude did.** It wrote `kalman_update_fast.m`, a benchmark, and `OPTIMIZATION.md`.
Over three rounds with the engineer, it added long-stream checks and made the fast
version add in exactly the original's order, so the output is bit-identical. It also
timed the speed without a shortcut that only helps when the filter settles, so the
report gives two honest numbers: about 31× with the shortcut, and 9.4× without.

**The outcome.** On DemoForge's own runs the answers are identical to the original (an
error of exactly zero), and the code is 33 times faster.
