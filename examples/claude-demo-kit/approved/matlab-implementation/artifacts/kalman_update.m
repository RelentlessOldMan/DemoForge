function X = kalman_update(Z, model)
% KALMAN_UPDATE  Constant-velocity tracker state estimator (CVT-EST-001 Rev B).
%
%   X = kalman_update(Z, model)
%
%   Z     - N x 2 matrix of position measurements; row k is z_k = [px py].
%   model - struct with fields F (4x4), Q (4x4), H (2x4), R (2x2),
%           x0 (4x1) and P0 (4x4), as provided in model.json.
%   X     - N x 4 matrix; row k is the posterior state [px py vx vy]
%           after the predict/update step for measurement k.
%
%   Pure function: no file I/O, no printing, no globals.

  F  = model.F;
  Q  = model.Q;
  H  = model.H;
  R  = model.R;
  x  = model.x0(:);
  P  = model.P0;

  N = size(Z, 1);
  I = eye(numel(x));
  X = zeros(N, numel(x));

  for k = 1:N
    % Predict (Section 4.1)
    x = F * x;
    P = F * P * F' + Q;

    % Update (Section 4.2)
    y = Z(k, :)' - H * x;
    S = H * P * H' + R;
    K = (P * H') / S;
    x = x + K * y;
    P = (I - K * H) * P;

    X(k, :) = x';
  end
end
