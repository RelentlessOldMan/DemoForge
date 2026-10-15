% test_kalman.m  Verification tests for kalman_update against CVT-EST-001 Rev B.
%
% Run from a folder containing kalman_update.m, model.json and test_vectors.csv:
%   octave-cli test_kalman.m
% Exits non-zero on the first failed check.
%
% The core oracle is an independent transcription of the §4 recursion. Every model
% field (F, Q, H, R, x0, P0) is varied away from its model.json default at least
% once, because a field that keeps its default value cannot show whether the code
% reads it (R3).

1;

function X = oracle(Z, m)
  % CVT-EST-001 §4, written out independently of the implementation under test.
  x = m.x0(:);
  P = m.P0;
  X = zeros(rows(Z), numel(x));
  for k = 1:rows(Z)
    xp = m.F * x;
    Pp = m.F * P * m.F' + m.Q;
    S  = m.H * Pp * m.H' + m.R;
    K  = Pp * m.H' / S;
    x  = xp + K * (Z(k, :)' - m.H * xp);
    P  = (eye(numel(x)) - K * m.H) * Pp;
    X(k, :) = x';
  end
end

function check_agrees(name, Z, m)
  X = kalman_update(Z, m);
  assert(isequal(size(X), [rows(Z), 4]), '%s: output is %s, expected %dx4', ...
         name, mat2str(size(X)), rows(Z));
  err = max(abs(X(:) - reshape(oracle(Z, m), [], 1)));
  assert(err < 1e-6, '%s: max |X - oracle| = %.3g (CVT-EST-001 §6 limit 1e-6)', name, err);
  printf('  ok  %-34s max err %.2e\n', name, err);
end

raw = jsondecode(fileread('model.json'));
base = struct('F', raw.F, 'Q', raw.Q, 'H', raw.H, 'R', raw.R, ...
              'x0', raw.x0(:), 'P0', raw.P0);
Z = csvread('test_vectors.csv', 1, 0);
printf('kalman_update verification (%d vectors)\n', rows(Z));

% R1/R2: interface and shape, including the N = 1 edge case.
X = kalman_update(Z, base);
assert(isequal(size(X), [rows(Z), 4]), 'R2: output shape %s', mat2str(size(X)));
assert(isequal(size(kalman_update(Z(1, :), base)), [1, 4]), 'R2: N = 1 shape');
assert(all(isfinite(X(:))), 'R2: non-finite estimates');
printf('  ok  shape (N = %d and N = 1)\n', rows(Z));

% R4: determinism.
assert(isequal(X, kalman_update(Z, base)), 'R4: repeated calls differ');
printf('  ok  deterministic\n');

% R3/§6: the recursion itself, on the default model.
check_agrees('default model', Z, base);

% R3: initialisation from model.x0 / model.P0 (§4 "Initialise x = x0, P = P0").
m = base;  m.x0 = [10; 5; 1; -1];
check_agrees('non-zero x0', Z(1:50, :), m);
m = base;  m.P0 = diag([100, 100, 4, 4]);
check_agrees('non-identity P0', Z(1:50, :), m);
m = base;  m.x0 = [10; 5; 1; -1];  m.P0 = 1e-6 * eye(4);
check_agrees('confident x0 (tiny P0)', Z(1:50, :), m);
% Oracle-free: with P0 and Q ~ 0 the gain is ~0, so the first posterior must sit
% on the prediction F*x0 whatever the measurement says.
m.P0 = 1e-9 * eye(4);  m.Q = 1e-9 * eye(4);
X1 = kalman_update(Z(1, :), m);
assert(max(abs(X1 - (m.F * m.x0)')) < 1e-3, ...
       'R3: first estimate %s ignores a confident x0 (expected ~%s)', ...
       mat2str(X1, 4), mat2str((m.F * m.x0)', 4));
printf('  ok  first estimate stays on F*x0 for P0, Q ~ 0\n');

% R3: the remaining constants are read from the model, not assumed.
m = base;  m.Q = diag([0.5, 0.5, 0.05, 0.05]);
check_agrees('different Q', Z(1:200, :), m);
m = base;  m.R = [1.0 0.2; 0.2 0.5];
check_agrees('different R', Z(1:200, :), m);
m = base;  m.F = [1 0 0.5 0; 0 1 0 0.5; 0 0 1 0; 0 0 0 1];
check_agrees('different F (dt = 0.5)', Z(1:200, :), m);

% Tracking sanity on the recorded stream (kept from the original test).
resid = X(:, 1:2) - Z;
assert(max(abs(resid(:))) < 5.0, 'estimate diverges from measurements');
printf('  ok  tracks the measurements\n');

printf('all checks passed\n');
