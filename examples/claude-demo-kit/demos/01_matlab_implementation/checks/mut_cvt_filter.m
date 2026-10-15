function X = mut_cvt_filter(Z, model)
  % MUT_CVT_FILTER  Deliberately broken implementation (harness only).
  % Same as ref_cvt_filter but the covariance update is skipped: P stays at the
  % predicted value, so the gain is too large and the estimates are a little too
  % jumpy. The output is finite, the right shape and roughly tracks the data,
  % which is what makes the bug easy to miss. A test that checks the section 4
  % recursion (R3) against known values catches it; one that only checks that
  % the estimate follows the measurements may not.
  F = model.F; Q = model.Q; H = model.H; R = model.R;
  x = model.x0(:); P = model.P0;
  N = rows(Z);
  n = numel(x);
  X = zeros(N, n);
  I = eye(n);
  for k = 1:N
    z = Z(k, :)';
    x = F * x;
    P = F * P * F' + Q;
    y = z - H * x;
    S = H * P * H' + R;
    K = (P * H') / S;
    x = x + K * y;
    % (covariance update P = (I - K*H)*P omitted)
    X(k, :) = x';
  end
end
