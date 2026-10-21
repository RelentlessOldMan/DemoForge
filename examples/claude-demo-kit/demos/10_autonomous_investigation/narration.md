<!-- Declarative narration, tagged by moment; TTS is cached per block
     (see docs/video-pipeline.md §6). `during:<seq>` blocks play over the scene
     built from that recorded event, and must describe only what it shows.
     Seq numbers refer to approved run 20261021T203702Z-1493da36. -->

## intro:The situation

A tracking filter estimates where a moving object is from noisy sensor measurements.
Before it uses a measurement, a gate checks whether that measurement is plausible, and
throws it away if it is too far from what the filter predicted. Release two point four
point one added a Doppler mode, which measures velocity as well as position. Its
validation campaign of sixty runs came back rejected: seventeen runs missed the half
metre accuracy limit.

## intro:What they need

The change control board wants the root cause before anything else happens to the
release. Each claim has to be tied to the file and line that shows it. A colleague's
three theories have to be confirmed or ruled out with evidence. And if the code is
wrong, it has to be fixed, with tests that would have caught it.

## intro:Why that's hard

The answer isn't written down anywhere. The repository holds source code, tests that
all pass, controlled documents, a spreadsheet, a dataset and logs full of warnings,
most of them unrelated. The colleague's notes offer three plausible theories, and none
is confirmed.

## during:0

Here's the request. Find out why campaign VAL-2026-09 failed, and write it up: what
failed, the root cause, the evidence, why it wasn't caught earlier, what was ruled
out, and what to do. Also write a findings file for the board's tracker, with the
defect's file and line, the run attribute that separates failures from passes, the
failing runs, and the wrong value if there is one. If the cause is in the code, fix it
and change the tests so they would have caught it.

## during:1

Claude lists the repository and reads the handover notes. The three theories: an old
covariance bug is back, a slow worker machine, or a noisy Doppler sensor.

## during:3

Then it reads the readme, the configuration, every source file, the tests and their
recorded results, the changelog, the specification, the validation plan and the
requirements trace.

## during:5

The campaign results: one row per run, with its mode, build, worker, peak position
error and status.

## during:7

The logs. The scheduler has a late heartbeat, an upload retry, a disk warning and a
certificate notice, and it flags one worker as nineteen percent slower. The validation
runner lists each failure.

## during:9

Now it joins each run's gate rejection rate from the worker log to its result. Every
Doppler run rejected between eighteen and twenty-one percent of its measurements,
including the three that passed. Planar runs rejected about five percent.

## during:11

It checks the rejected values against the configured thresholds: fifty-nine of the
sixty logged Doppler rejections fall below the Doppler threshold of thirteen point two
seven seven, so a correct gate would have kept them. And it finds Octave.

## during:13

It reads the software requirements, which are a PDF.

## during:14

Then the summary workbook. Pass rate point seven two against a minimum of point nine
five. By mode, Doppler passed three of twenty and planar all forty. The by-build tab
makes the new build look bad, but every Doppler run was on the new build.

## during:16

Next, reproducing it in Octave.

## during:17

It replays the recorded gate inputs through the gate. Seven inputs the specification
says to accept are rejected. Then a simulated Doppler run, twenty times over: the
shipped gate rejects forty point eight percent, with a mean peak error of three hundred
ninety-nine metres. And with no gate at all, the error is still one point one metres.

## during:19

A search for the threshold finds it. The gate is passed gamma, the threshold for the
mode, but line fifteen sets its own constant, five point nine nine one.

## during:21

It saves a copy of the original gate and of the whole working folder before changing
anything.

## during:23

The fix: remove the constant, and compare against the gamma the caller passes.

## during:25

It builds a simple stream with sine-wave noise at the configured level, to compare the
two gates. The first attempt can't find its script, because of a path problem.

## during:27

With the path fixed: the corrected gate rejects nothing, with a peak error of point
three three metres. The original gate rejects five point nine percent, and peaks at
point five three, just over the limit.

## during:29

It edits the tests with a script and runs them on both gates. But both gates still
pass the old counts, four and five, so the edits didn't take.

## during:31

Claude suspects Windows line endings.

## during:32

Confirmed: the test files have them.

## during:34

It restores the original test files from its copy.

## during:36

And switches to editing them directly.

## during:37

It reads both test files.

## during:39

The gate tests now use a threshold other than five point nine nine one, so a gate that
ignores gamma can't pass by coincidence.

## during:41

New checks: the same measurement must be rejected at one threshold and accepted at
another, four-dimensional Doppler cases, bad thresholds must fail safe, and every
recorded gate input must be decided correctly.

## during:42

And in the filter tests, the gated path in both modes, on the sine-wave stream.

## during:44

On the fixed gate, both suites pass, six of six and nine of nine. On the original gate,
both fail.

## during:46

Now it collects exact line references for the evidence.

## during:47

The configured thresholds, the list of failing runs, and lines from the worker log.

## during:49

Then the write-up.

## during:50

First the findings file: the cause at line twenty-eight of the gate, the
discriminator is Doppler mode, the seventeen failing runs, and five point nine nine one
in use where thirteen point two seven seven is correct.

## during:51

It checks the cited lines and that the file parses.

## during:53

Then the root-cause report itself.

## during:54

It checks one claim before leaving it in: exactly the twenty Doppler runs, and no
planar run, logged the rejection-rate alert.

## during:56

And corrects the sentence in the report to say so.

## during:57

Claude's answer. The campaign failed because of a bug in the code. The gate ignores the
threshold it is given and uses five point nine nine one, the old two-dimensional value.
In Doppler mode, that throws away about one valid measurement in five, instead of one
in a hundred, and position error goes past half a metre. The evidence: the logged
rejection rates match the theory for that threshold, the rejected values sit between
the two thresholds, and the recorded gate inputs show seven wrong rejections. Planar
mode has the bug too, but there it rejects five percent, the same as the old build. It
rules out all three theories, each for a stated reason. The tests missed it because
they used the same wrong number and only two dimensions, and a warning on every
Doppler run went unread. Then the changes, and a recommendation to release a fixed
build and re-run the campaign.

## during:58

The engineer, played here by a second Claude session, isn't convinced. Claude's own
first simulation contradicts the write-up, and isn't mentioned. It showed forty
percent rejected, not twenty, and over a metre of error even with no gate. Until that
is explained, the engineer can't accept that fixing the gate brings Doppler under half
a metre. Redo the simulation properly, with twenty seeds. And the sine-wave test looks
fragile: is there a more direct check, like counting the rejection rate?

## during:59

Claude starts by rerunning the first simulation, one seed at a time.

## during:60

Every seed loses track. Rejections start within the first fifteen steps and climb to
between twenty-six and sixty-nine percent, with errors from nine to over two thousand
metres.

## during:62

Now the proper replay: shipped gate, fixed gate and no gate, in both modes, twenty
seeds each.

## during:63

With the fixed gate, Doppler rejects one percent, as specified. But no case, in either
mode, gets a single run under half a metre. Even with no gate, the median peak is one
point one metres in Doppler and one point three in planar.

## during:65

So it scales the simulated process and sensor noise down, to look for any setting that
matches the field. None reproduces both the campaign's rejection rates and its planar
error levels.

## during:67

It computes the filter's expected steady-state error from the configured model: a peak
of about one point one metres for Doppler and one point three for planar. Yet the
campaign's planar runs peaked at point four one or less. The model and the campaign data
don't agree, and Claude has found it.

## during:69

It rereads the filter tests.

## during:70

And replaces the sine-wave tests. The new ones place a thousand measurements at evenly
spaced points of the expected distribution, send them through the full configured
path, and require one percent rejected, plus that a measurement between the two
thresholds is used.

## during:72

The same rate check goes into the gate tests, for both dimensions at two confidence
levels.

## during:73

On the fixed gate: six of six and ten of ten. On the shipped gate, exactly twenty
percent rejected in Doppler and five percent in planar, the rates the campaign logged.

## during:75

Now the report. The sine-wave evidence is replaced with the rate result.

## during:76

A new section: what is not established. Whether the fix brings Doppler under half a
metre can't be shown from this repository. It includes the replay table, explains the
first simulation, and says plainly that Claude set it aside without reporting it.

## during:77

The sensor-noise theory is still ruled out as the cause, but whether the half-metre
limit is achievable is now marked open.

## during:79

It reads the report back.

## during:80

The tests section is rewritten for the new rate checks, with results on both gates.

## during:81

The recommendations change. First replay the recorded campaign streams on the fixed
build, and confirm how peak error is computed. Then re-run the campaign. And don't
change the limit on the strength of this investigation.

## during:82

The requirements trace item now points the threshold requirement at the new checks,
including the rate test, and the gated path in each mode at the filter tests.

## during:84

Next, the report's header and the matching entry in the findings file.

## during:85

The status line now says the fix isn't yet shown to bring Doppler under the limit.

## during:86

And the findings file says the same.

## during:87

The findings file still parses, and both suites pass.

## during:89

Claude's reply. The engineer was right: it can't show from this repository that the
fix brings Doppler under half a metre, and it shouldn't have left that simulation out.
The root cause still holds, but only a replay of the recorded streams can show the
fixed build passes. It explains the forty percent: each rejection makes the next more
likely, until the filter loses track. And the one metre with no gate follows from the
configured noise levels. Then the replay table: the fix brings rejection to one
percent, but no case gets under half a metre. The simulation doesn't match the field.
Planar runs in the field peaked at point four one metres or less, where the simulation
gives over one point two even with no gate. The rejection rates say the measurements
are as noisy as configured, but the planar errors say the estimates are far better than
that allows. Both can't be true under the model, and Claude can't check which here.
The sine-wave tests are replaced by the rate checks the engineer suggested. And the
write-up now has a section on what isn't established.

## during:90

The engineer still isn't accepting it. The findings file says the twenty percent
rejection is why the error goes past half a metre, as if proven, and Claude's own
replay says it isn't. Within Doppler, rate doesn't predict error: one run rejected
eighteen percent and failed, another rejected twenty and passed. Separate what's shown
from what's inferred.

## during:91

Claude computes the correlation between rejection rate and peak error over the twenty
Doppler runs, and searches the report for causal wording.

## during:93

The engineer is right: within Doppler, rejection rate and peak error are essentially
uncorrelated, minus point one six. Now it goes through every causal claim in the
write-up.

## during:94

It reads the report again.

## during:95

Its plan: split the root cause into what is shown and what is inferred, then fix every
other place that states the link as fact.

## during:96

The status line: the defect is established, its link to the failures is inferred.

## during:98

Section two splits in two. Shown: the gate ignores gamma, which explains the rejection
rates.

## during:99

Inferred, not confirmed: that the extra rejections cause the half-metre failures. It
lists what supports that, what doesn't establish it, and what would settle it.

## during:100

The sentence calling the passes consistent with the gate driving the failures goes.

## during:102

The findings file's root cause now reads: shown, the gate ignores gamma, which
explains the rejection rate. Inferred, unconfirmed until the streams are replayed:
that these rejections drive the failures.

## during:103

And the ruled-out theories carry a caveat: if the replay still fails, they reopen.

## during:104

A final search for causal wording in both files.

## during:106

Claude summarises the rewording. The findings file's root cause, the status line, and
section two, split into shown and inferred. What would settle it: if the replayed
streams pass on the fixed build, the link is confirmed. If they still fail, the defect
is real and must still be fixed, but it isn't the whole cause. No code or tests
changed in this round. The engineer is satisfied.

## result

The engineer pushed back twice and was then satisfied. DemoForge then checked the work
on its own. Every one of fourteen citations is a real line, quoted correctly. The
cause, the Doppler discriminator, the seventeen failing runs and both threshold values
are right. The fix agrees with a hidden reference gate. And the new tests pass on a
correct gate and fail on the one that shipped. Fourteen of fourteen checks pass. One
thing the checks don't cover: the campaign's error figures don't follow from its own
model. Claude noticed, and said so rather than claim more than it could show.

## transition

That's the ten demonstrations. Every action on screen was replayed from a recorded
run, and every result was checked by DemoForge, independently of Claude.
