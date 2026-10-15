% test_measurement_gate.m  Tests for measurement_gate (CVT-SRS-003 Rev C §7.3, G1-G5).
%
% Run from the repository root:  octave --no-gui tests/test_measurement_gate.m
%
% T6-T9 were added after VAL-2026-09: the v2.3-era tests only ever called the gate
% with gamma = 5.991 and m = 2, so a gate that ignored gamma passed them. They now
% exercise both modes at their configured thresholds and the d2 == gamma boundary.

addpath(fullfile(fileparts(mfilename('fullpath')), '..', 'src'));

tol = 1e-12;
n = 0;

% T1  NIS with S = I equals y'y (G1)
[~, d2] = measurement_gate([3; 4], eye(2), 9.210);
assert(abs(d2 - 25) < tol, 'T1 NIS, S = I');
n++;

% T2  NIS with a non-identity covariance (G1)
[~, d2] = measurement_gate([2; 1], [2 0; 0 0.5], 9.210);
assert(abs(d2 - 4) < tol, 'T2 NIS, diagonal S');
n++;

% T3  a plausible measurement is admitted (G2)
[acc, ~] = measurement_gate([0.2; -0.1], eye(2), 9.210);
assert(acc, 'T3 admit');
n++;

% T4  a measurement beyond gamma is rejected (G2)
[acc, d2] = measurement_gate([3; 2], eye(2), 9.210);          % d2 = 13
assert(~acc && d2 > 9.210, 'T4 reject beyond gamma');
n++;

% T5  non-finite input fails closed without error (G4, R6)
[acc, d2] = measurement_gate([NaN; 0], eye(2), 9.210);
assert(~acc && isinf(d2), 'T5 fail closed');
[acc, d2] = measurement_gate([0.1; 0.1], eye(2), NaN);
assert(~acc && isinf(d2), 'T5 fail closed, NaN gamma');
n++;

% T6  the decision follows the supplied gamma, not a threshold of the gate's own (G3)
y = [2; 2];                                                   % d2 = 8 (planar)
assert(~measurement_gate(y, eye(2), 5.991) && measurement_gate(y, eye(2), 9.210), ...
       'T6 planar decision tracks gamma');
n++;

% T7  Doppler mode (m = 4) at its configured threshold, from the shipped config (G3)
cfg = jsondecode(fileread(fullfile(fileparts(mfilename('fullpath')), '..', ...
                                   'config', 'estimator_config.json')));
g4 = cfg.gate.gamma.doppler;
assert(abs(g4 - 13.277) < 1e-9, 'T7 config: Doppler gamma is chi2(4) at 99 %');
yd = [2; 2; 2; 1];                                            % d2 = 13 (Doppler)
[acc, d2] = measurement_gate(yd, eye(4), g4);
assert(acc && abs(d2 - 13) < tol, 'T7 Doppler d2 = 13 admitted at 13.277');
[acc, ~] = measurement_gate(yd, eye(4), 9.488);
assert(~acc, 'T7 Doppler d2 = 13 rejected at 95 %');
[acc, ~] = measurement_gate([2; 1; 1; 1], eye(4), g4);       % d2 = 7, typical chi2(4)
assert(acc, 'T7 typical Doppler innovation admitted');
n++;

% T8  the boundary: d2 == gamma is admitted (§7.3.2)
[acc, d2] = measurement_gate([3; 0], eye(2), 9);
assert(acc && d2 == 9, 'T8 d2 == gamma admitted');
[acc, ~] = measurement_gate([2; 2; 2; 2], 4 * eye(4), 4);
assert(acc, 'T8 d2 == gamma admitted, m = 4');
n++;

% T9  the bench capture: every row agrees with the definition, both modes (G1, G2)
fid = fopen(fullfile(fileparts(mfilename('fullpath')), '..', 'data', 'gate_vectors.csv'));
fgetl(fid);
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
    assert(abs(d2 - ref) < 1e-9 && acc == (ref <= g), 'T9 capture row: %s', ln);
  else
    assert(~acc && isinf(d2), 'T9 capture dropout row');
  end
end
fclose(fid);
n++;

printf('test_measurement_gate: %d/%d checks passed\n', n, 9);
