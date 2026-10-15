We need the measurement validation gate for the CVT estimator's v2.4 release. It is
specified in section 7.3 of `CVT-SRS-003.pdf` (Estimator Software Requirements, Rev C).
Please implement it in MATLAB as `measurement_gate.m`, with the interface the spec
defines, and write `test_measurement_gate.m`: a test we can run in CI with
`octave-cli test_measurement_gate.m`, which must raise an error if the gate does not
meet §7.3. We run GNU Octave here, not MATLAB.

`gate_vectors.csv` is a bench capture of gate inputs from both measurement modes, if
you want real data to exercise it with. Each row is one measurement: the mode, its
dimension `m`, the gamma the bench was configured with, the innovation `y` (`y1..y4`)
and the innovation covariance `S` laid out on a 4-by-4 grid (`s11..s44`). Planar rows
use only the first two components and the upper-left 2-by-2 block; the unused cells
are empty.
