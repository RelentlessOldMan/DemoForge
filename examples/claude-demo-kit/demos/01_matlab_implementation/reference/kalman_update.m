function X = kalman_update(Z, model)
  % KALMAN_UPDATE  Constant-velocity Kalman filter over a batch of measurements.
  %
  %   X = kalman_update(Z, model)
  %
  %   Z      N-by-m matrix; row k is the measurement z_k.
  %   model  struct with fields F (n-by-n), Q (n-by-n), H (m-by-n), R (m-by-m),
  %          x0 (n-by-1), P0 (n-by-n).
  %   X      N-by-n matrix; row k is the posterior state estimate after step k.
  %
  % Each step predicts with the constant-velocity model, then applies the
  % measurement update:
  %     x = F x;            P = F P F' + Q
  %     y = z - H x;        S = H P H' + R
  %     K = P H' / S;       x = x + K y;   P = (I - K H) P

  F = model.F; Q = model.Q; H = model.H; R = model.R;
  x = model.x0; P = model.P0;

  N = rows(Z);
  n = numel(x);
  X = zeros(N, n);
  I = eye(n);

  for k = 1:N
    z = Z(k, :)';

    % --- predict ---
    x = F * x;
    P = F * P * F' + Q;

    % --- update ---
    y = z - H * x;
    S = H * P * H' + R;
    K = (P * H') / S;          % mrdivide: solves K*S = P*H'
    x = x + K * y;
    P = (I - K * H) * P;

    X(k, :) = x';
  end
end
