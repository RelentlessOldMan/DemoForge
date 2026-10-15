<!-- Declarative narration, tagged by moment; TTS is cached per block
     (see docs/video-pipeline.md §6). `during:<seq>` blocks play over the scene
     built from that recorded event, and must describe only what it shows. -->

## setup

Real engineering specifications usually arrive as PDF documents. Claude gets one, the
estimator's software requirements, and is asked to build one component it describes,
the measurement gate, and prove it meets the spec. A gate is a bouncer for sensor data.
It compares each new reading with what the filter expects, and turns away readings too
far off to be believable.

## problem

The gate's rules are a few pages into a long document: a formula for how surprising a
reading is, a cut-off taken from a statistics table, and one hard rule. The gate was
added after a corrupted reading poisoned the filter, so a garbage reading must always
be turned away, never let through.

## during:3

Claude reads the PDF itself, to find the section it needs.

## during:9

It runs its test in Octave. All thirty-six checks pass, including the ones that feed
the gate garbage readings.

## result

Claude builds the gate to the exact interface the spec demands, computes the formula
the numerically safe way, and turns away garbage readings without crashing. Its tests
cover a normal reading, an outlier, and a corrupted input. DemoForge then checks the
gate against a hidden reference: every decision matches, and garbage never gets
through.

## transition

Next, a test suite that passes. Claude's job is to find out whether it actually proves
anything.
