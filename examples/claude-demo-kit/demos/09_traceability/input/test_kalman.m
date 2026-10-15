% test_kalman.m — unit tests for kalman_update (CVT-EST-001 R5).
%
% Run:  octave --eval test_kalman      (needs test_vectors.csv in the working folder)

function test_kalman()
  model.F  = [1 0 1 0; 0 1 0 1; 0 0 1 0; 0 0 0 1];
  model.Q  = 0.01 * eye(4);
  model.H  = [1 0 0 0; 0 1 0 0];
  model.R  = 0.25 * eye(2);
  model.x0 = [0; 0; 0; 0];
  model.P0 = eye(4);

  Z = csvread('test_vectors.csv', 1, 0);

  % T1 — output shape is N-by-4 (exercises R1 signature, R2 shape)
  X = kalman_update(Z, model);
  assert(isequal(size(X), [size(Z, 1), 4]), 'T1 shape');

  % T2 — determinism (exercises R4)
  assert(isequal(X, kalman_update(Z, model)), 'T2 determinism');

  % T3 — tracking: position estimate stays near the measurements (exercises R3)
  resid = X(:, 1:2) - Z;
  assert(max(abs(resid(:))) < 5.0, 'T3 tracking');

  fprintf('T1 T2 T3 passed\n');
end

test_kalman();
