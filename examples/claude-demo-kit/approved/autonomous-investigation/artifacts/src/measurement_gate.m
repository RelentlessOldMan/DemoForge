function [accept, d2] = measurement_gate(y, S, gamma)
  % MEASUREMENT_GATE  Measurement validation gate (CVT-SRS-003 §7.3).
  %
  %   [accept, d2] = measurement_gate(y, S, gamma)
  %
  %   y      m-by-1 innovation vector
  %   S      m-by-m innovation covariance
  %   gamma  gate threshold (chi-squared critical value)
  %   accept true iff the measurement passes the gate
  %   d2     normalized innovation squared, y' * inv(S) * y
  %
  % Malformed input fails closed (accept = false, d2 = Inf) without raising, so a
  % non-finite measurement never reaches the update (CVT-EST-001 R6).
  %
  % The gate holds no threshold of its own (CVT-SRS-003 Rev C §7.3.3, G3): gamma
  % depends on the confidence level and the mode's measurement dimension and is
  % resolved by the caller (cvt_model).

  if any(~isfinite(y(:))) || any(~isfinite(S(:))) || ...
     ~isscalar(gamma) || ~isfinite(gamma) || gamma <= 0
    accept = false;
    d2 = Inf;
    return;
  end

  % NIS by solving S x = y (do not form inv(S)).
  Ssym = (S + S') / 2;
  d2 = y' * (Ssym \ y);

  accept = (d2 <= gamma);
end
