% test_kalman_existing.m  Regression test for kalman_update (CVT-EST-001 R5).
%
% Run in Octave from a directory containing kalman_update.m and test_vectors.csv:
%   octave-cli test_kalman_existing.m

function test_kalman_existing()
  model.F  = [1 0 1 0; 0 1 0 1; 0 0 1 0; 0 0 0 1];
  model.Q  = 0.01 * eye(4);
  model.H  = [1 0 0 0; 0 1 0 0];
  model.R  = 0.25 * eye(2);
  model.x0 = [0; 0; 0; 0];
  model.P0 = eye(4);

  Z = csvread('test_vectors.csv', 1, 0);   % skip header
  X = kalman_update(Z, model);

  % 1) output shape: one 4-vector per measurement
  assert(isequal(size(X), [size(Z, 1), 4]), 'output shape wrong');

  % 2) determinism: repeated calls agree
  X2 = kalman_update(Z, model);
  assert(isequal(X, X2), 'not deterministic');

  % 3) tracking: with position measurements, the position estimate should stay
  %    close to the measured position (not diverge)
  resid = X(:, 1:2) - Z;
  assert(max(abs(resid(:))) < 5.0, 'estimate diverges from measurements');

  fprintf('existing tests passed (%d vectors)\n', size(Z, 1));
end

test_kalman_existing();
