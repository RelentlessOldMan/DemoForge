function X = kalman_update_fast(Z, model)
  % KALMAN_UPDATE_FAST  Vectorized equivalent of kalman_update.
  %
  % Identical math and interface, but every per-step matrix operation uses
  % Octave's native (BLAS-backed) linear algebra instead of explicit scalar
  % loops. The per-sample sequential dependency (each step needs the previous
  % x, P) is inherent to a filter and cannot be removed; the speedup comes
  % entirely from dropping the hand-rolled matmul/transpose/inverse loops.

  F = model.F; Q = model.Q; H = model.H; R = model.R;
  x = model.x0; P = model.P0;

  N = rows(Z);
  n = numel(x);
  X = zeros(N, n);

  I = eye(n);
  Ht = H';
  Ft = F';

  for k = 1:N
    z = Z(k, :)';

    % --- predict ---
    x = F * x;
    P = F * P * Ft + Q;

    % --- update ---
    y = z - H * x;
    S = H * P * Ht + R;
    K = (P * Ht) / S;
    x = x + K * y;
    P = (I - K * H) * P;

    X(k, :) = x';
  end
end
