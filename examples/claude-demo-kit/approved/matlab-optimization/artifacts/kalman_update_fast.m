function X = kalman_update_fast(Z, model, use_cycle)
  % KALMAN_UPDATE_FAST  Constant-velocity Kalman filter over a batch of measurements.
  %
  %   X = kalman_update_fast(Z, model)
  %   X = kalman_update_fast(Z, model, use_cycle)
  %
  %   use_cycle  optional, default true. Pass false to disable the
  %              periodic-gain shortcut (2. below) and compute every step in
  %              full; the output is the same either way. For benchmarking.
  %
  %   Drop-in replacement for KALMAN_UPDATE (CVT estimator v2.1.0) with the
  %   same inputs and outputs:
  %
  %   Z      N-by-m matrix; row k is the measurement z_k (columns beyond m,
  %          the number of rows of H, are ignored, as in the original).
  %   model  struct with fields F (n-by-n), Q (n-by-n), H (m-by-n), R (m-by-m),
  %          x0 (n-by-1), P0 (n-by-n).
  %   X      N-by-n matrix; row k is the posterior state estimate after step k.
  %
  % Same recursion as the original, per CVT-EST-001 Rev B section 4:
  %     x = F x;            P = F P F' + Q
  %     y = z - H x;        S = H P H' + R
  %     K = P H' inv(S);    x = x + K y;   P = (I - K H) P
  %
  % Output is bit-identical to KALMAN_UPDATE for any model with m == 2. Two
  % things make it fast without changing a single bit:
  %
  % 1. Exact-order vectorized products. Every product C = A*B is accumulated as
  %        C = 0;  for p = 1:inner,  C = C + A(:,p) .* B(p,:);  end
  %    This is the same order and starting value as the original's scalar
  %    loops (s = 0; s = s + A(i,p)*B(p,j)), but a whole matrix at a time, and
  %    each term is one correctly rounded element-wise multiply. The built-in
  %    matrix multiply is deliberately not used, because BLAS adds the terms in
  %    a different order and its result is not bit-identical. These loops are
  %    written inline, because function-call overhead would otherwise dominate.
  %
  % 2. Periodic-gain shortcut. The covariance recursion (P, S, K) does not
  %    depend on the measurements: the gain used at step k+1 and the posterior
  %    P_{k+1} are a deterministic function of the posterior P_k alone. After
  %    each step, the bits of P are compared with the posteriors of the last
  %    MAXPERIOD steps. Once P_k is bit-for-bit equal to P_{k-L}, every later
  %    gain repeats the last L gains exactly, so only the state update is
  %    computed from then on (with the same operations, in the same order).
  %    Typical filters reach such a cycle within a few hundred steps. If no
  %    cycle is found, every step is computed in full.
  %
  % For m == 2, S is inverted in closed form exactly as in the original. For any
  % other measurement dimension (which the original does not support), K is
  % obtained by solving against S.

  MAXPERIOD = 64;
  if nargin < 3, use_cycle = true; end

  F = model.F; Q = model.Q; H = model.H; R = model.R;
  x = model.x0(:); P = model.P0;

  N = size(Z, 1);
  n = numel(x);
  m = size(H, 1);
  X = zeros(N, n);

  Ft = F.';
  Ht = H.';
  I  = eye(n);
  Zt = Z(:, 1:m).';                      % m x N, one column per step
  zn1 = zeros(n, 1); znn = zeros(n, n);
  zm1 = zeros(m, 1); zmm = zeros(m, m); znm = zeros(n, m);

  % Ring buffer of the posterior-P bit patterns and gains of recent steps.
  nslot = MAXPERIOD + 1;
  Pbits = zeros(n * n, nslot, 'uint64');
  Kbuf  = zeros(n, m, nslot);
  slotstep = zeros(1, nslot);            % step stored in each slot (0 = empty)

  % --- full steps, until the covariance recursion becomes periodic ---------
  k = 0;
  period = 0;
  while k < N
    k = k + 1;

    % --- predict ---
    % x = F x
    xp = zn1;
    for p = 1:n, xp = xp + F(:, p) .* x(p); end
    x = xp;
    % P = (F P) F' + Q
    FP = znn;
    for p = 1:n, FP = FP + F(:, p) .* P(p, :); end
    P = znn;
    for p = 1:n, P = P + FP(:, p) .* Ft(p, :); end
    P = P + Q;

    % --- update ---
    % PHt = P H'                           n x m
    PHt = znm;
    for p = 1:n, PHt = PHt + P(:, p) .* Ht(p, :); end
    % S = H PHt + R                        m x m
    S = zmm;
    for p = 1:n, S = S + H(:, p) .* PHt(p, :); end
    S = S + R;
    % K = PHt inv(S)                       n x m
    if m == 2
      d    = S(1, 1) * S(2, 2) - S(1, 2) * S(2, 1);
      Sinv = [S(2, 2) / d, -S(1, 2) / d; -S(2, 1) / d, S(1, 1) / d];
      K = znm;
      for p = 1:m, K = K + PHt(:, p) .* Sinv(p, :); end
    else
      K = PHt / S;
    end
    % y = z - H x                          m x 1
    Hx = zm1;
    for p = 1:n, Hx = Hx + H(:, p) .* x(p); end
    y = Zt(:, k) - Hx;
    % x = x + K y
    Ky = zn1;
    for p = 1:m, Ky = Ky + K(:, p) .* y(p); end
    x = x + Ky;
    % P = (I - K H) P
    KH = znn;
    for p = 1:m, KH = KH + K(:, p) .* H(p, :); end
    IKH = I - KH;
    Pn = znn;
    for p = 1:n, Pn = Pn + IKH(:, p) .* P(p, :); end
    P = Pn;

    X(k, :) = x.';

    % --- look for P_k equal (bitwise) to an earlier posterior P_{k-L} -------
    if ~use_cycle, continue; end
    bits = typecast(P(:), 'uint64');
    slot = mod(k - 1, nslot) + 1;
    if all(isfinite(P(:)))
      hit = find(slotstep > 0 & all(Pbits == bits, 1), 1);
      if ~isempty(hit)
        period = k - slotstep(hit);
      end
    end
    Pbits(:, slot) = bits;
    Kbuf(:, :, slot) = K;
    slotstep(slot) = k;
    if period > 0
      break
    end
  end

  if period == 0
    return                               % reached N without a cycle
  end

  % Gains for the steps after k repeat those of steps k-period+1 .. k.
  Kcyc = zeros(n, m, period);
  for j = 1:period
    Kcyc(:, :, j) = Kbuf(:, :, mod(k - period + j - 1, nslot) + 1);
  end

  % --- state-only steps, same operations and order as above ----------------
  j = 0;
  for k = k + 1:N
    j = j + 1;
    if j > period, j = 1; end
    K = Kcyc(:, :, j);

    xp = zn1;
    for p = 1:n, xp = xp + F(:, p) .* x(p); end
    Hx = zm1;
    for p = 1:n, Hx = Hx + H(:, p) .* xp(p); end
    y = Zt(:, k) - Hx;
    Ky = zn1;
    for p = 1:m, Ky = Ky + K(:, p) .* y(p); end
    x = xp + Ky;

    X(k, :) = x.';
  end
end
