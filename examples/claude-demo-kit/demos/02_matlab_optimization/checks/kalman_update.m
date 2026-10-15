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
  %     K = P H' inv(S);    x = x + K y;   P = (I - K H) P
  %
  % CVT estimator v2.1.0, per CVT-EST-001 Rev B section 4. The matrix helpers
  % below are line-for-line ports of the C reference implementation, kept so
  % the two could be diffed during qualification. S is inverted in closed form,
  % so the measurement dimension must be 2.

  F = model.F; Q = model.Q; H = model.H; R = model.R;
  x = model.x0; P = model.P0;

  N = size(Z, 1);
  n = numel(x);
  X = zeros(N, n);

  for k = 1:N
    z = zeros(size(H, 1), 1);
    for i = 1:size(H, 1)
      z(i) = Z(k, i);
    end

    % --- predict ---
    x  = matvec(F, x);
    P  = madd(matmul(matmul(F, P), transpose_m(F)), Q);

    % --- update ---
    Ht  = transpose_m(H);
    PHt = matmul(P, Ht);                 % n x m
    S   = madd(matmul(H, PHt), R);       % m x m
    Sinv = inv2x2(S);
    K   = matmul(PHt, Sinv);             % n x m
    y   = vsub(z, matvec(H, x));         % m x 1
    x   = vadd(x, matvec(K, y));
    KH  = matmul(K, H);                  % n x n
    P   = matmul(msub(eye_m(n), KH), P);

    for j = 1:n
      X(k, j) = x(j);
    end
  end
end

% ---- matrix helpers (ported from the C reference) -------------------------
function C = matmul(A, B)
  [ra, ca] = size(A);
  [rb, cb] = size(B);
  C = zeros(ra, cb);
  for i = 1:ra
    for j = 1:cb
      s = 0;
      for p = 1:ca
        s = s + A(i, p) * B(p, j);
      end
      C(i, j) = s;
    end
  end
end

function y = matvec(A, x)
  [ra, ca] = size(A);
  y = zeros(ra, 1);
  for i = 1:ra
    s = 0;
    for p = 1:ca
      s = s + A(i, p) * x(p);
    end
    y(i) = s;
  end
end

function C = madd(A, B)
  [r, c] = size(A);
  C = zeros(r, c);
  for i = 1:r
    for j = 1:c
      C(i, j) = A(i, j) + B(i, j);
    end
  end
end

function C = msub(A, B)
  [r, c] = size(A);
  C = zeros(r, c);
  for i = 1:r
    for j = 1:c
      C(i, j) = A(i, j) - B(i, j);
    end
  end
end

function y = vadd(a, b)
  y = zeros(numel(a), 1);
  for i = 1:numel(a)
    y(i) = a(i) + b(i);
  end
end

function y = vsub(a, b)
  y = zeros(numel(a), 1);
  for i = 1:numel(a)
    y(i) = a(i) - b(i);
  end
end

function B = transpose_m(A)
  [r, c] = size(A);
  B = zeros(c, r);
  for i = 1:r
    for j = 1:c
      B(j, i) = A(i, j);
    end
  end
end

function I = eye_m(n)
  I = zeros(n, n);
  for i = 1:n
    I(i, i) = 1;
  end
end

function Si = inv2x2(S)
  % Closed-form inverse of a 2x2 matrix.
  d = S(1, 1) * S(2, 2) - S(1, 2) * S(2, 1);
  Si = zeros(2, 2);
  Si(1, 1) =  S(2, 2) / d;
  Si(1, 2) = -S(1, 2) / d;
  Si(2, 1) = -S(2, 1) / d;
  Si(2, 2) =  S(1, 1) / d;
end
