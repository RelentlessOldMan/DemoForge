function X = cvt_trusted_update(Z, model)
  % CVT_TRUSTED_UPDATE  Harness-owned vectorized filter (never staged to the agent).
  %
  % Same recursion as kalman_update.m using native matrix operations. run_tests.m
  % first confirms it agrees with the original, then uses it to check the
  % agent's output on the extra streams used only for timing, where running the
  % slow original again would cost too much.

  F = model.F; Q = model.Q; H = model.H; R = model.R;
  x = model.x0; P = model.P0;
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
    P = (I - K * H) * P;
    X(k, :) = x';
  end
end
