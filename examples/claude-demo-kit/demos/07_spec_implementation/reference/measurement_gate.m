function [accept, d2] = measurement_gate(y, S, gamma)
  % MEASUREMENT_GATE  CVT measurement validation gate (CVT-SRS-003 Rev C, §7.3).
  %
  %   [accept, d2] = measurement_gate(y, S, gamma)
  %
  %   y      m-by-1 innovation vector, y = z - H x
  %   S      m-by-m innovation covariance (symmetric positive definite)
  %   gamma  gate threshold: chi-squared critical value for the active mode's m at
  %          the configured confidence (Appendix A), resolved by the caller
  %   accept logical scalar, true iff d2 <= gamma (§7.3.2)
  %   d2     normalized innovation squared, y' * inv(S) * y (§7.3.1)
  %
  % Pure; works for any m. Fails closed (§7.3.5): a non-finite y or S, or a gamma
  % that is not a finite positive scalar, gives accept = false and d2 = Inf without
  % raising an error.

  % G-BC-1/2
  if any(~isfinite(y(:))) || any(~isfinite(S(:))) || ...
     ~isscalar(gamma) || ~isfinite(gamma) || ~(gamma > 0)
    accept = false;
    d2 = Inf;
    return;
  end

  % G1: solve S x = y rather than forming inv(S); symmetrize against round-off.
  y = y(:);
  Ssym = (S + S') / 2;
  d2 = y' * (Ssym \ y);

  % G2/G3: admit iff within the supplied threshold (boundary admitted).
  accept = (d2 <= gamma);
end
