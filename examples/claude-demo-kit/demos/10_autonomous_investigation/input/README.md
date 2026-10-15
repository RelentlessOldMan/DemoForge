# CVT Estimator

Constant-Velocity Tracker state estimator and its measurement-processing front end.
This repository holds the implementation, its tests, the controlled documents, and
the artifacts from the most recent validation campaign.

Estimator lead: Priya Raman. Releases are built by `build-agent-04` from the
`release/vX.Y` branch.

## Layout

    config/   runtime configuration (estimator_config.json) and the model file
    data/     validation campaign results and recorded gate inputs
    docs/     controlled documents, requirements trace, changelog
    logs/     logs from the most recent validation campaign
    notes/    engineering notes (not controlled)
    src/      implementation (MATLAB/Octave; a Python port for offline analysis)
    tests/    test suite and the recorded results of the last test run

## Controlled documents

| Document     | Title                                      | Rev |
|--------------|--------------------------------------------|-----|
| CVT-EST-001  | State Estimator Specification              | C   |
| CVT-SRS-003  | Estimator Software Requirements (PDF)      | C   |
| CVT-VAL-002  | Validation Plan                            | A   |

## Using it

    addpath src
    model = cvt_model('doppler');          % or 'planar'; default is active_mode
    [X, rejected] = kalman_update(Z, model);

## Running the tests

    octave --no-gui tests/test_kalman.m
    octave --no-gui tests/test_measurement_gate.m

The Python port in `src/kalman_filter.py` is for offline analysis only and is not
part of the validated build.
