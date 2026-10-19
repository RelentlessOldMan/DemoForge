function [accept, d2] = measurement_gate(y, S, gamma)
%MEASUREMENT_GATE  Measurement validation gate (CVT-SRS-003 Rev C, section 7.3).
%
%   [accept, d2] = measurement_gate(y, S, gamma)
%
%   y      m-by-1 innovation vector.
%   S      m-by-m innovation covariance (symmetric positive definite).
%   gamma  scalar gate threshold (chi-squared critical value, resolved from
%          configuration by the caller; the gate holds no threshold, G3).
%   accept logical scalar: true iff the measurement passes the gate.
%   d2     normalized innovation squared, d2 = y' * inv(S) * y (7.3.1).
%
%   The measurement is admitted iff d2 <= gamma (G2). d2 is computed by
%   solving S x = y; inv(S) is never formed (G1).
%
%   Fail closed (G4, G-BC-1/G-BC-2): if y or S has a non-finite element, or
%   gamma is not a finite positive scalar, the gate returns accept = false and
%   d2 = Inf without raising an error. The same rejecting result is returned
%   for any other input that is outside the 7.3.4 contract and so cannot
%   yield a trustworthy d2: non-numeric or complex data, a y that is not a
%   column vector, an S whose size does not match y, or an S that is not
%   symmetric positive definite (including numerically singular S).
%
%   The function is pure: no file access, no printing, no globals.

  accept = false;
  d2 = Inf;

  % --- threshold (G-BC-1) ---
  if ~(isnumeric(gamma) && isreal(gamma) && isscalar(gamma))
    return;
  end
  gamma = double(gamma);
  if ~(isfinite(gamma) && gamma > 0)
    return;
  end

  % --- measurement shape and type (malformed => reject, R6) ---
  if ~(isnumeric(y) && isreal(y) && isnumeric(S) && isreal(S))
    return;
  end
  if ndims(y) ~= 2 || ndims(S) ~= 2
    return;
  end
  m = size(y, 1);
  if m < 1 || size(y, 2) ~= 1 || ~isequal(size(S), [m, m])
    return;
  end
  y = double(y);
  S = double(S);

  % --- non-finite values (G-BC-1) ---
  if ~(all(isfinite(y)) && all(isfinite(S(:))))
    return;
  end

  % --- S must be symmetric positive definite (7.3.1 precondition) ---
  if norm(S - S', 'fro') > sqrt(eps) * norm(S, 'fro')
    return;
  end
  [~, notpd] = chol(S);
  if notpd ~= 0
    return;
  end

  % --- NIS (7.3.1, G1): solve S x = y, d2 = y' * x ---
  % Warnings (e.g. "matrix singular to machine precision") are silenced for
  % the solve and restored afterwards so the gate never prints; a
  % numerically singular S is caught by the finiteness check below or by
  % the rcond check.
  wstate = warning();
  restore = onCleanup(@() warning(wstate));
  warning('off', 'all');
  if rcond(S) < eps
    return;
  end
  x = S \ y;
  d = y' * x;
  if ~(isfinite(d) && d >= 0)
    return;
  end

  % --- gate decision (7.3.2, G2) ---
  d2 = d;
  accept = (d2 <= gamma);
end
