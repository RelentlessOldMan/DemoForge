% test_measurement_gate.m  Tests for measurement_gate (CVT-SRS-003 §7.3 and §8, G1-G5).
%
% Run from the repository root:  octave --no-gui tests/test_measurement_gate.m

root = fullfile(fileparts(mfilename('fullpath')), '..');
addpath(fullfile(root, 'src'));

% Not the Rev B constant 5.991: a gate that ignores gamma must not pass by
% coincidence (VAL-2026-09).
GAMMA = 9.210;                      % chi-squared, 99 %, m = 2 (CVT-SRS-003 App. A)
GAMMA4 = 13.277;                    % chi-squared, 99 %, m = 4
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
[acc, d2] = measurement_gate([2.5; 2], eye(2), GAMMA);
assert(~acc && d2 > GAMMA, 'T4 reject beyond gamma');
n = n + 1;

% T5  non-finite input fails closed without error (G4, R6)
[acc, d2] = measurement_gate([NaN; 0], eye(2), GAMMA);
assert(~acc && isinf(d2), 'T5 fail closed');
n = n + 1;

% T6  the decision follows the supplied gamma, not a built-in value (G2, G3)
y = [2; 1.5];                       % d2 = 6.25
assert(~measurement_gate(y, eye(2), 5.991), 'T6 reject at gamma 5.991');
assert(measurement_gate(y, eye(2), GAMMA), 'T6 admit at gamma 9.210');
assert(measurement_gate([1; 1; 1; 0], eye(4), 3), 'T6 admit at d2 == gamma');
n = n + 1;

% T7  four-dimensional (Doppler) measurement against the m = 4 threshold (G1-G3)
[acc, d2] = measurement_gate([2; 1; 1; 1.5], eye(4), GAMMA4);   % d2 = 8.25
assert(acc && abs(d2 - 8.25) < tol, 'T7 admit m = 4 below gamma');
[acc, d2] = measurement_gate([3; 2; 1; 1], eye(4), GAMMA4);     % d2 = 15
assert(~acc && abs(d2 - 15) < tol, 'T7 reject m = 4 beyond gamma');
n = n + 1;

% T8  a malformed gamma fails closed without error (G4)
for g = {0, -1, Inf, NaN, [5.991 9.210]}
  [acc, d2] = measurement_gate([0.1; 0.1], eye(2), g{1});
  assert(~acc && isinf(d2), 'T8 fail closed on bad gamma');
end
n = n + 1;

% T9  recorded innovations from both modes (CVT-SRS-003 §8): every row of
%     data/gate_vectors.csv is decided as d2 <= gamma, using that row's gamma
V = dlmread(fullfile(root, 'data', 'gate_vectors.csv'), ',', 1, 1);
for i = 1:size(V, 1)
  m = V(i, 1);
  g = V(i, 2);
  y = V(i, 3:2 + m)';
  S = reshape(V(i, 7:22), 4, 4)';
  S = S(1:m, 1:m);
  [acc, d2] = measurement_gate(y, S, g);
  if any(~isfinite(y))
    assert(~acc && isinf(d2), sprintf('T9 row %d fail closed', i + 1));
  else
    ref = y' * (((S + S') / 2) \ y);
    assert(abs(d2 - ref) < 1e-9 && acc == (ref <= g), sprintf('T9 row %d decision', i + 1));
  end
end
n = n + 1;

% T10 rejection rate matches the confidence behind gamma (G2, G3; App. A):
%     innovations placed at 1000 evenly spaced chi-squared(m) quantiles of NIS,
%     through a non-identity S, must be rejected at 1 - confidence.
S4 = [1.5 0.2 -0.1 0.1; 0.2 1.1 0 0.2; -0.1 0 0.8 -0.3; 0.1 0.2 -0.3 0.7];
q = ((1:1000) - 0.5) / 1000;
for c = {2, 0.95, 5.991; 2, 0.99, 9.210; 4, 0.95, 9.488; 4, 0.99, 13.277}'
  [m, conf, g] = c{:};
  S = S4(1:m, 1:m);
  L = chol(S, 'lower');
  u = ones(m, 1) / sqrt(m);
  d2q = 2 * gammaincinv(q, m / 2);
  acc = arrayfun(@(d) measurement_gate(L * u * sqrt(d), S, g), d2q);
  assert(abs(mean(~acc) - (1 - conf)) <= 0.002, ...
         sprintf('T10 m = %d, gamma %.3f: rejected %.3f, expected %.3f', m, g, mean(~acc), 1 - conf));
end
n = n + 1;

fprintf('test_measurement_gate: %d/%d checks passed\n', n, 10);
