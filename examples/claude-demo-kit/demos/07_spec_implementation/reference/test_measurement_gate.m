% test_measurement_gate.m  Tests for measurement_gate (CVT-SRS-003 Rev C, §7.3).
%
% Run from this folder:  octave-cli test_measurement_gate.m
% Any failed check raises an error, so the run exits non-zero in CI.

1;  % script file

function check(cond, msg)
  if ~cond
    error('test_measurement_gate:fail', 'FAILED: %s', msg);
  end
end

tol = 1e-12;
n = 0;

% --- G1: NIS ----------------------------------------------------------------
[~, d2] = measurement_gate([3; 4], eye(2), 9.210);
check(abs(d2 - 25) < tol, 'G1: S = I gives d2 = y''y'); n++;

% diagonal S: d2 = 2^2/2 + 1^2/0.5 = 4
[~, d2] = measurement_gate([2; 1], [2 0; 0 0.5], 9.210);
check(abs(d2 - 4) < tol, 'G1: diagonal S'); n++;

% full 4x4 S (Doppler), against an independent computation
S4 = [1.5 0.2 -0.1 0.0; 0.2 1.1 0.0 0.1; -0.1 0.0 0.8 -0.2; 0.0 0.1 -0.2 0.9];
y4 = [0.7; -1.2; 0.4; 1.9];
[~, d2] = measurement_gate(y4, S4, 13.277);
check(abs(d2 - y4' * inv(S4) * y4) < 1e-10, 'G1: full 4x4 S'); n++;

% m = 1 and m = 3 work too (§7.3.4: any m)
[~, d2] = measurement_gate(2, 4, 6.635);
check(abs(d2 - 1) < tol, 'G1: m = 1'); n++;
[~, d2] = measurement_gate([1; 1; 1], diag([1 2 4]), 11.345);
check(abs(d2 - 1.75) < tol, 'G1: m = 3'); n++;

% --- G2: decision, including the boundary --------------------------------------
[acc, ~] = measurement_gate([0.2; -0.1], eye(2), 9.210);
check(acc == true, 'G2: plausible measurement admitted'); n++;
[acc, ~] = measurement_gate([5; 5], eye(2), 9.210);
check(acc == false, 'G2: outlier rejected'); n++;
[acc, d2] = measurement_gate([3; 0], eye(2), 9);         % d2 == gamma exactly
check(d2 == 9 && acc == true, 'G2: d2 == gamma is admitted'); n++;
[acc, ~] = measurement_gate([3; 0], eye(2), 8.999);
check(acc == false, 'G2: just above gamma is rejected'); n++;
check(islogical(acc) && isscalar(acc), 'G2: accept is a logical scalar'); n++;

% --- G3: the decision follows the supplied gamma -------------------------------
% d2 = 8 (planar): rejected at 95 % (5.991), admitted at 99 % (9.210)
[a95, ~] = measurement_gate([2; 2], eye(2), 5.991);
[a99, ~] = measurement_gate([2; 2], eye(2), 9.210);
check(~a95 && a99, 'G3: planar decision tracks gamma'); n++;
% d2 = 11 (Doppler, m = 4): rejected at 9.488 or 9.210, admitted at 13.277
yd = [2; 2; 1.7320508075688772; 1];                      % d2 = 4+4+3+1 = 11 (approx)
[a1, ~] = measurement_gate(yd, eye(4), 9.210);
[a2, ~] = measurement_gate(yd, eye(4), 9.488);
[a3, ~] = measurement_gate(yd, eye(4), 13.277);
check(~a1 && ~a2 && a3, 'G3: Doppler decision tracks gamma'); n++;
% a large gamma admits what a small one rejects, for the same (y, S)
[aS, ~] = measurement_gate([5; 0], eye(2), 50);           % d2 = 25
check(aS, 'G3: no threshold of the gate''s own'); n++;

% --- G4: fail closed, never error ----------------------------------------------
bad = { {[NaN; 0],  eye(2),        9.210,  'NaN in y'}, ...
        {[Inf; 0],  eye(2),        9.210,  'Inf in y'}, ...
        {[0.1; 0.1], [Inf 0; 0 1], 9.210,  'Inf in S'}, ...
        {[0.1; 0.1], [1 NaN; NaN 1], 9.210, 'NaN in S'}, ...
        {[0.1; 0.1], eye(2),       NaN,    'NaN gamma'}, ...
        {[0.1; 0.1], eye(2),       Inf,    'Inf gamma'}, ...
        {[0; 0],     eye(2),       0,      'zero gamma'}, ...
        {[0.1; 0.1], eye(2),       -1,     'negative gamma'}, ...
        {[0.1; 0.1], eye(2),       [9.21 13.277], 'non-scalar gamma'} };
for i = 1:numel(bad)
  c = bad{i};
  try
    [acc, d2] = measurement_gate(c{1}, c{2}, c{3});
  catch err
    error('test_measurement_gate:fail', 'FAILED: G4 %s raised: %s', c{4}, err.message);
  end
  check(acc == false && isinf(d2) && d2 > 0, ['G4: ' c{4} ' must reject with d2 = Inf']);
  n++;
end

% --- bench capture: every finite row agrees with the definition ---------------
fid = fopen('gate_vectors.csv', 'r');
fgetl(fid);
rows = 0;
while true
  ln = fgetl(fid);
  if ~ischar(ln), break; end
  f = strsplit(ln, ',', 'CollapseDelimiters', false);
  m = str2double(f{2}); g = str2double(f{3});
  y = str2double(f(4:3+m))';
  G = reshape(str2double(f(8:23)), 4, 4)';
  S = G(1:m, 1:m);
  [acc, d2] = measurement_gate(y, S, g);
  if all(isfinite(y))
    ref = y' * (S \ y);
    check(abs(d2 - ref) < 1e-9 && acc == (ref <= g), sprintf('capture row %d', rows + 1));
  else
    check(acc == false && isinf(d2), sprintf('capture row %d (dropout)', rows + 1));
  end
  rows++;
end
fclose(fid);
n++;

printf('test_measurement_gate: %d checks passed (%d capture rows)\n', n, rows);
