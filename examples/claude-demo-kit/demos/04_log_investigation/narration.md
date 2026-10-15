<!-- Declarative narration, tagged by moment; TTS is cached per block
     (see docs/video-pipeline.md §6). `during:<seq>` blocks play over the scene
     built from that recorded event, and must describe only what it shows. -->

## setup

Now a different kind of job: no code to write, just a mystery to solve. Software keeps
logs, running diaries of everything it does. One test in last night's overnight run
failed, and we hand Claude the logs from five parts of the system with a two-line
request: figure out what happened.

## problem

The obvious error is a dead end. The test log just says the estimator returned a
garbage number. The real cause is three steps further back, spread across five log
files, and there are unrelated errors in the same time window that look like the
culprit.

## during:3

Claude reads every log, not just the one that failed. The validation log only reports
the symptom.

## during:6

The system log is where the story starts: the disk filled up, minutes before test
eighteen forty-seven's data was exported.

## during:7

Claude writes up its findings: the chain of events, the exact log lines behind each
step, and the false leads it ruled out.

## result

Claude matches up timestamps across the logs and rebuilds the chain: the disk filled
during the data export, the measurement file for test eighteen forty-seven was
silently cut short and still marked ready, and the estimator then choked on the broken
input. It cites the exact lines, dismisses the red herrings, and points at the real
fix: check the export before marking it ready.

## transition

Same detective work, a different source: next, Claude digs into a spreadsheet instead
of logs.
