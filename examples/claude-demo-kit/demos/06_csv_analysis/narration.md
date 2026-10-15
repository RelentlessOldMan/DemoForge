<!-- Declarative narration, tagged by moment; TTS is cached per block
     (see docs/video-pipeline.md §6). `during:<seq>` blocks play over the scene
     built from that recorded event, and must describe only what it shows. -->

## setup

Here Claude gets a pile of numbers instead of a task: five hundred test runs over
twenty nights, and an open-ended question. What's wrong with this data?

## problem

The real signal is buried. Accuracy, run time, the machine that ran each test, and the
firmware version all vary from run to run, and the most obvious difference, one
machine running slower, is a red herring. The real story only shows up when you group
the data the right way.

## during:5

Claude slices the runs several ways. Grouped by firmware version, one number jumps out.

## during:12

Then it checks the obvious suspect, the slower machine, with a proper statistical
test. The difference is no bigger than chance, so it rules that out.

## during:14

And it draws the chart a manager would want: the jump in error when firmware version
two point three arrived.

## result

Claude shows that firmware two point three made the tracker well over a hundred times
less accurate and pushed a cluster of runs past the failure line, while correctly
dismissing the slower machine as harmless. It measures the effect and plots it.
DemoForge independently recomputes the same numbers from the raw data.

## transition

From finding a problem in data to building from a document: next, Claude works from a
specification delivered as a PDF.
