function X = ref_cvt_filter(Z, model)
  % REF_CVT_FILTER  Hidden reference for the harness (never staged to the agent).
  % The CVT-EST-001 section 4 recursion, identical to reference/kalman_update.m
  % under a name that cannot collide with the agent's kalman_update.m.
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
    P = (I - K * H) * P;
    X(k, :) = x';
  end
end
