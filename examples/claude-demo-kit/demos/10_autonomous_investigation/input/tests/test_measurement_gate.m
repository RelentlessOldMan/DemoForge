% test_measurement_gate.m  Tests for measurement_gate (CVT-SRS-003 §7.3, G1-G5).
%
% Run from the repository root:  octave --no-gui tests/test_measurement_gate.m

addpath(fullfile(fileparts(mfilename('fullpath')), '..', 'src'));

GAMMA = 5.991;
tol = 1e-12;
n = 0;

% T1  NIS with S = I equals y'y (G1)
[~, d2] = measurement_gate([3; 4], eye(2), GAMMA);
assert(abs(d2 - 25) < tol, 'T1 NIS, S = I');
n = n + 1;

% T2  NIS with a non-identity covariance (G1)
[~, d2] = measurement_gate([2; 1], [2 0; 0 0.5], GAMMA);
assert(abs(d2 - 4) < tol, 'T2 NIS, diagonal S');
n = n + 1;

% T3  a plausible measurement is admitted (G2)
[acc, ~] = measurement_gate([0.2; -0.1], eye(2), GAMMA);
assert(acc, 'T3 admit');
n = n + 1;

% T4  a measurement beyond gamma is rejected (G2, G3)
[acc, d2] = measurement_gate([2; 1.5], eye(2), GAMMA);
assert(~acc && d2 > GAMMA, 'T4 reject beyond gamma');
n = n + 1;

% T5  non-finite input fails closed without error (G4, R6)
[acc, d2] = measurement_gate([NaN; 0], eye(2), GAMMA);
assert(~acc && isinf(d2), 'T5 fail closed');
n = n + 1;

fprintf('test_measurement_gate: %d/%d checks passed\n', n, 5);
