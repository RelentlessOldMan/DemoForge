function [accept, d2] = measurement_gate_ref(y, S, gamma)
  % MEASUREMENT_GATE_REF  Correct CVT measurement validation gate (hidden reference).
  %
  % DemoForge-owned golden implementation of CVT-SRS-003 Rev C §7.3, used only by the
  % verification harness. Never shown to the agent. The distinct name lets it coexist
  % with the agent's measurement_gate.m on the Octave path; the harness also writes it
  % out as measurement_gate.m (and as mutants of it) to run the agent's tests against.

  % G-BC-1/2: fail closed on non-finite y or S, or a gamma that is not a finite
  % positive scalar.
  if any(~isfinite(y(:))) || any(~isfinite(S(:))) || ...
     ~isscalar(gamma) || ~isfinite(gamma) || ~(gamma > 0)
    accept = false;
    d2 = Inf;
    return;
  end

  % G1: NIS by solving S x = y.
  Ssym = (S + S') / 2;
  d2 = y(:)' * (Ssym \ y(:));

  % G2: admit iff d2 <= gamma.
  accept = (d2 <= gamma);
end
