function test_kalman_update()
  % TEST_KALMAN_UPDATE  CVT-EST-001 R5: runnable test for kalman_update (R1-R4).
  %
  %   octave --eval test_kalman_update
  %
  % Raises an error on the first failed check; prints a summary when all pass.

  m = jsondecode(fileread('model.json'));
  model = struct('F', m.F, 'Q', m.Q, 'H', m.H, 'R', m.R, 'x0', m.x0(:), 'P0', m.P0);
  Z = csvread('test_vectors.csv', 1, 0);
  N = rows(Z);

  % R1: interface X = kalman_update(Z, model)
  assert(nargin('kalman_update') == 2 && nargout('kalman_update') == 1, ...
         'R1: kalman_update must have signature X = kalman_update(Z, model)');
  X = kalman_update(Z, model);

  % R2: N x 4, finite, one row per measurement
  assert(isequal(size(X), [N 4]), 'R2: expected %dx4 output, got %dx%d', N, rows(X), columns(X));
  assert(all(isfinite(X(:))), 'R2: output contains non-finite values');

  % R3: the section 4 recursion, checked against an independent step-by-step
  % evaluation (explicit inverse, written separately from the implementation)
  Xe = expected(Z, model);
  err = max(abs(X(:) - Xe(:)));
  assert(err < 1e-8, 'R3: recursion differs from section 4 (max abs err %.3g)', err);

  % R3: the constants come from model, including x0/P0 (non-default model)
  alt = model;
  alt.F = [1 0 0.5 0; 0 1 0 0.5; 0 0 1 0; 0 0 0 1];
  alt.H = [1 0 0.1 0; 0 1 0 0.1];
  alt.Q = 0.1 * eye(4); alt.R = diag([1.0 0.5]);
  alt.x0 = [10; -5; 1; 2]; alt.P0 = 3 * eye(4);
  Xa = kalman_update(Z(1:50, :), alt);
  Xae = expected(Z(1:50, :), alt);
  assert(max(abs(Xa(:) - Xae(:))) < 1e-8, 'R3: model constants (F, Q, H, R, x0, P0) not honoured');

  % R3 sanity: the position estimate tracks the measurements
  resid = X(:, 1:2) - Z;
  rms_resid = sqrt(mean(resid(:) .^ 2));
  assert(rms_resid < 1.0, 'R3: estimate does not track the measurements (rms %.3g)', rms_resid);

  % R4: deterministic
  assert(isequal(X, kalman_update(Z, model)), 'R4: repeated calls differ');

  printf('test_kalman_update: all checks passed (N=%d, max err vs recursion %.2g, rms resid %.3f)\n', ...
         N, err, rms_resid);
end

function X = expected(Z, model)
  x = model.x0(:); P = model.P0;
  X = zeros(rows(Z), numel(x));
  for k = 1:rows(Z)
    x = model.F * x;
    P = model.F * P * model.F' + model.Q;
    S = model.H * P * model.H' + model.R;
    K = P * model.H' * inv(S);
    x = x + K * (Z(k, :)' - model.H * x);
    P = (eye(numel(x)) - K * model.H) * P;
    X(k, :) = x';
  end
end
