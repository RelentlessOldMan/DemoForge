<!-- Declarative narration, tagged by moment; TTS is cached per block
     (see docs/video-pipeline.md §6). `during:<seq>` blocks play over the scene
     built from that recorded event, and must describe only what it shows. -->

## setup

Engineering teams live in spreadsheets, and spreadsheets hide mistakes. Claude is
handed a workbook summarising a batch of test runs, and the plan that defines what
passing means. The workbook says everything passed. The request: something looks
wrong, find it and fix it.

## problem

The workbook agrees with itself. Every run says PASS and the pass rate is a hundred
percent, which is exactly why the mistake is easy to miss. The pass limit lives on one
sheet, the raw numbers on another, and the verdict on a third.

## during:5

There it is. The plan says tracking error must stay under half a metre. The
spreadsheet's limit says five metres: ten times too loose.

## during:6

Before trusting its fix, Claude recomputes the verdict both ways. With the correct
limit, ten runs fail and the campaign flips from ACCEPT to REJECT.

## result

Claude corrects the limit, lets the pass and fail marks recalculate, and saves a
corrected workbook. The bad batch now fails, the pass rate drops below the required
ninety-five percent, and the verdict reads REJECT. Along the way it also catches a
second mistake nobody planted: the verdict formula ignored the runtime limit entirely.
DemoForge recomputes the verdict straight from the data and confirms the fix.

## transition

The spreadsheet held the answer this time. Next, Claude gets raw data, and no hint at
all about what's wrong with it.
