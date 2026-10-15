function X = kalman_update(Z, model)
  % KALMAN_UPDATE  Constant-velocity Kalman filter over a batch of measurements.
  %
  %   X = kalman_update(Z, model)
  %
  %   Z      N-by-2 matrix; row k is the position measurement z_k.
  %   model  struct with fields F, Q, H, R, x0, P0 (CVT-EST-001 §2.3, model.json).
  %   X      N-by-4 matrix; row k is the posterior state estimate after step k.
  %
  % Implements the predict / measurement-update recursion of CVT-EST-001 Rev B §4.

  F = model.F;
  Q = model.Q;
  H = model.H;
  R = model.R;

  n = rows(F);
  x = model.x0(:);
  P = model.P0;
  I = eye(n);

  N = rows(Z);
  X = zeros(N, n);

  for k = 1:N
    z = Z(k, :)';

    % measurement update
    y = z - H * x;
    S = H * P * H' + R;
    K = (P * H') / S;          % solves K*S = P*H' without forming inv(S)
    x = x + K * y;
    P = (I - K * H) * P;

    X(k, :) = x';

    % predict
    x = F * x;
    P = F * P * F' + Q;
  end
end
