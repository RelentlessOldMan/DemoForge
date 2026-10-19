% TEST_MEASUREMENT_GATE  Verification of measurement_gate against CVT-SRS-003
% Rev C section 7.3 (requirements G1-G4; this script is the G5 test).
%
% Run from CI with:
%   octave-cli test_measurement_gate.m
%
% Every check is run; failures are collected and reported together, and the
% script ends with error() if any check failed, so octave-cli exits non-zero.
1;

function d2 = reference_nis(y, S)
  % Independent NIS reference via eigendecomposition (does not share code
  % or method with the gate's linear solve).
  [V, E] = eig((S + S') / 2);
  z = V' * y;
  d2 = sum(z .^ 2 ./ diag(E));
end

function [accept, d2, out, err] = run_gate(y, S, gamma)
  % Call the gate, capturing anything it prints and any error it raises.
  accept = []; d2 = []; err = '';
  try
    out = evalc('[accept, d2] = measurement_gate(y, S, gamma);');
  catch e
    out = '';
    err = e.message;
  end
end

function S = spd(m, seed)
  % Deterministic, well-conditioned SPD matrix of size m.
  A = reshape(sin((1:m*m) * seed), m, m);
  S = A * A' + m * eye(m);
end

here = fileparts(mfilename('fullpath'));
if isempty(here)
  here = pwd;
end
addpath(here);

% Each check increments n_checks and appends a message to failures on failure.
failures = {};
n_checks = 0;

% ---------------------------------------------------------------------------
% Interface (7.3.4): output types for a normal call
% ---------------------------------------------------------------------------
[a, d, out, err] = run_gate([1; 2], [2 0; 0 3], 9.210);
n_checks++;
if ~isempty(err)
  failures{end+1} = sprintf('7.3.4: gate raised an error on a valid call: %s', err);
else
  if ~(islogical(a) && isscalar(a))
    failures{end+1} = '7.3.4: accept is not a logical scalar';
  end
  if ~(isnumeric(d) && isreal(d) && isscalar(d))
    failures{end+1} = '7.3.4: d2 is not a real numeric scalar';
  end
end

% ---------------------------------------------------------------------------
% G1 / 7.3.1: d2 = y' inv(S) y, computed by solving S x = y
% ---------------------------------------------------------------------------
% Exact case: S = diag(4,1), y = [2;1] -> x = [0.5;1], d2 = 2 exactly.
[a, d, out, err] = run_gate([2; 1], diag([4 1]), 9.210);
n_checks++;
if ~isempty(err) || ~isequal(d, 2)
  failures{end+1} = sprintf('G1: exact case expected d2 = 2, got %s', mat2str(d));
end

% Any measurement dimension m (7.3.4).
for m = [1 2 3 4 6 10]
  y = cos((1:m)' * 1.7) * 2;
  S = spd(m, m + 0.3);
  [a, d, out, err] = run_gate(y, S, 1e6);
  ref = reference_nis(y, S);
  n_checks++;
  if ~isempty(err)
    failures{end+1} = sprintf('G1: m = %d raised an error: %s', m, err);
  elseif ~(abs(d - ref) <= 1e-10 * max(1, ref)) || ~isequal(a, true)
    failures{end+1} = sprintf('G1: m = %d d2 = %.15g, reference %.15g', m, d, ref);
  end
end

% inv(S) must not be formed: static check of the gate source (comments removed).
src = fileread(fullfile(here, 'measurement_gate.m'));
code = regexprep(src, '%[^\n]*', '');
% (Plain string search on whitespace-free code: Octave applies its own escape
% processing to regexp patterns, which makes backslash patterns unreliable.)
code_nows = regexprep(code, '\s', '');
n_checks++;
if ~isempty(regexp(code_nows, '(^|[^A-Za-z0-9_])p?inv\(', 'once'))
  failures{end+1} = 'G1: measurement_gate.m forms inv(S)/pinv(S)';
end
n_checks++;
if isempty(strfind(code_nows, ['S' char(92) 'y']))
  failures{end+1} = 'G1: measurement_gate.m does not solve S x = y (x = S \ y)';
end

% ---------------------------------------------------------------------------
% G2 / 7.3.2: admit iff d2 <= gamma; d2 == gamma is admitted
% ---------------------------------------------------------------------------
y = [2; 1]; S = diag([4 1]);          % d2 = 2 exactly
cases = { 2,             true,  'd2 == gamma';
          2 + eps(2),    true,  'd2 just below gamma';
          2 - eps(2),    false, 'd2 just above gamma';
          100,           true,  'd2 well below gamma';
          0.5,           false, 'd2 well above gamma' };
for k = 1:rows(cases)
  [a, d, out, err] = run_gate(y, S, cases{k, 1});
  n_checks++;
  if ~isempty(err) || ~isequal(a, cases{k, 2})
    failures{end+1} = sprintf('G2: %s (gamma = %.17g): expected accept = %d, got %s', ...
                              cases{k, 3}, cases{k, 1}, cases{k, 2}, mat2str(a));
  end
  n_checks++;
  if ~isequal(d, 2)
    failures{end+1} = sprintf('G2: %s: d2 must not depend on gamma, got %s', ...
                              cases{k, 3}, mat2str(d));
  end
end
% A rejected outlier still reports its true d2 (needed for 7.4 logging).
[a, d] = run_gate([10; 0], eye(2), 9.210);
n_checks++;
if ~isequal(a, false) || ~isequal(d, 100)
  failures{end+1} = sprintf('G2: outlier expected (false, 100), got (%s, %s)', mat2str(a), mat2str(d));
end

% ---------------------------------------------------------------------------
% G3 / 7.3.3: the supplied gamma is used; the gate holds no threshold
% ---------------------------------------------------------------------------
% d2 = 7.5 for this measurement: rejected at 95 % m=2 (5.991), admitted at
% 99 % (9.210) and 99.9 % (13.816), so the decision must follow gamma.
y = [sqrt(7.5); 0]; S = eye(2);
appendix_a = [3.841 6.635 10.828; 5.991 9.210 13.816; 7.815 11.345 16.266; 9.488 13.277 18.467];
expect = [false true true];
for j = 1:3
  a = run_gate(y, S, appendix_a(2, j));
  n_checks++;
  if ~isequal(a, expect(j))
    failures{end+1} = sprintf('G3: d2 = 7.5, gamma = %.3f: expected accept = %d, got %s', ...
                              appendix_a(2, j), expect(j), mat2str(a));
  end
end
% Doppler (m = 4): d2 = 12 rejected at 95 % (9.488), admitted at 99 % (13.277).
y = [sqrt(12); 0; 0; 0]; S = eye(4);
n_checks++;
if ~isequal(run_gate(y, S, appendix_a(4, 1)), false) || ~isequal(run_gate(y, S, appendix_a(4, 2)), true)
  failures{end+1} = 'G3: m = 4 decision does not follow supplied gamma (9.488 / 13.277)';
end
% Static check: no threshold constants or chi-squared lookups in the gate.
n_checks++;
if ~isempty(regexp(code, '(chi2inv|gammaincinv|5\.991|9\.21|13\.277|9\.488)', 'once'))
  failures{end+1} = 'G3: measurement_gate.m contains a built-in threshold';
end

% ---------------------------------------------------------------------------
% G4 / 7.3.5: fail closed, without error
% ---------------------------------------------------------------------------
y0 = [0.1; -0.2; 0.05; 0.0]; S0 = spd(4, 1.1); g0 = 13.277;   % admitted baseline
[a, d] = run_gate(y0, S0, g0);
n_checks++;
if ~isequal(a, true)
  failures{end+1} = 'G4: baseline measurement for fail-closed tests is not admitted';
end

bad = {};
for v = [NaN Inf -Inf]
  for i = 1:4
    y = y0; y(i) = v;
    bad(end+1, :) = {y, S0, g0, sprintf('y(%d) = %g', i, v)};
  end
  for i = 1:16
    S = S0; S(i) = v;
    bad(end+1, :) = {y0, S, g0, sprintf('S(%d) = %g', i, v)};
  end
  bad(end+1, :) = {y0, S0, v, sprintf('gamma = %g', v)};
end
bad(end+1, :) = {y0, S0, 0,           'gamma = 0'};
bad(end+1, :) = {y0, S0, -0,          'gamma = -0'};
bad(end+1, :) = {y0, S0, -13.277,     'gamma negative'};
bad(end+1, :) = {y0, S0, [],          'gamma empty'};
bad(end+1, :) = {y0, S0, [9.21 13.277], 'gamma non-scalar'};
bad(end+1, :) = {y0, S0, '13.277',    'gamma char'};
bad(end+1, :) = {y0, S0, 13.277 + 1i, 'gamma complex'};
bad(end+1, :) = {y0, S0, true,        'gamma logical'};
bad(end+1, :) = {y0, S0, {13.277},    'gamma cell'};
% Malformed measurements (R6): never admitted, never an error.
bad(end+1, :) = {[],           S0,                 g0, 'y empty'};
bad(end+1, :) = {y0',          S0,                 g0, 'y row vector'};
bad(end+1, :) = {y0(1:2),      S0,                 g0, 'y/S dimension mismatch'};
bad(end+1, :) = {y0,           S0(1:4, 1:3),       g0, 'S not square'};
bad(end+1, :) = {y0,           [],                 g0, 'S empty'};
bad(end+1, :) = {y0,           zeros(4),           g0, 'S zero (singular)'};
bad(end+1, :) = {y0,           -S0,                g0, 'S negative definite'};
bad(end+1, :) = {y0,           diag([1 1 1 -1]),   g0, 'S indefinite'};
bad(end+1, :) = {y0,           diag([1 1 1 1e-300]), g0, 'S numerically singular'};
bad(end+1, :) = {y0,           S0 + triu(ones(4), 1), g0, 'S not symmetric'};
bad(end+1, :) = {y0 + 1i,      S0,                 g0, 'y complex'};
bad(end+1, :) = {num2cell(y0), S0,                 g0, 'y cell'};
bad(end+1, :) = {'abcd''',     S0,                 g0, 'y char'};
bad(end+1, :) = {[1 2;3 4],    S0,                 g0, 'y matrix'};
bad(end+1, :) = {[0; 0], [1 NaN; NaN 1],           g0, 'S off-diagonal NaN'};
bad(end+1, :) = {[0; 0], eye(2),                   NaN, 'zero innovation with NaN gamma'};

warn_before = warning();
for k = 1:rows(bad)
  [a, d, out, err] = run_gate(bad{k, 1}, bad{k, 2}, bad{k, 3});
  n_checks++;
  if ~isempty(err)
    failures{end+1} = sprintf('G-BC-2: %s raised an error: %s', bad{k, 4}, err);
  elseif ~(isequal(a, false) && islogical(a) && isequal(d, Inf))
    failures{end+1} = sprintf('G-BC-1: %s: expected (false, Inf), got (%s, %s)', ...
                              bad{k, 4}, mat2str(a), mat2str(d));
  end
  n_checks++;
  if ~isempty(out)
    failures{end+1} = sprintf('7.3.4 purity: gate printed output for %s: %s', bad{k, 4}, strtrim(out));
  end
end
n_checks++;
if ~isequal(warning(), warn_before)
  failures{end+1} = '7.3.4 purity: gate changed the global warning state';
end

% ---------------------------------------------------------------------------
% Purity (7.3.4): static check for file access, printing and globals
% ---------------------------------------------------------------------------
n_checks++;
forbidden = '\<(global|persistent|fopen|fclose|fprintf|fwrite|fputs|puts|disp|display|printf|load|save|csvread|dlmread|textscan|input|keyboard)\>';
if ~isempty(regexp(code, forbidden, 'once'))
  failures{end+1} = sprintf('7.3.4 purity: measurement_gate.m uses "%s"', ...
                            regexp(code, forbidden, 'match', 'once'));
end

% ---------------------------------------------------------------------------
% Section 8: recorded innovation streams from both modes (gate_vectors.csv)
% ---------------------------------------------------------------------------
% Expected d2 and decisions were computed independently (NumPy, solve) from
% the bench capture; the gate must reproduce them using each row's gamma.
expected = [ ...  % csv line, d2 (Inf = rejected as non-finite), accept
   2   0.420000  1;   3   1.870065  1;   4   3.050076  1;   5   7.360036  1;
   6   8.939874  1;   7   9.870146  0;   8  15.199901  0;   9   0.960035  1;
  10   2.309936  1;  11   4.479996  1;  12   6.720033  1;  13   9.930125  1;
  14  11.600160  1;  15  12.899736  1;  16  14.100012  0;  17  21.400290  0;
  18   3.369985  1;  19        Inf  0;  20  10.399811  1;  21   1.120041  1;
  22   4.699852  1;  23   6.850050  0;  24   8.119925  0;  25   2.640067  1];

csv_path = fullfile(here, 'gate_vectors.csv');
fid = fopen(csv_path, 'r');
if fid < 0
  failures{end+1} = sprintf('8: cannot open %s', csv_path);
  lines = {};
else
  text = fread(fid, Inf, 'char=>char')';
  fclose(fid);
  lines = regexp(text, '\r?\n', 'split');
  lines = lines(~cellfun(@isempty, strtrim(lines)));
end
if ~isempty(lines)
  header = strsplit(strtrim(lines{1}), ',', 'CollapseDelimiters', false);
  col = @(name) find(strcmp(header, name));
  n_rows = numel(lines) - 1;
  n_checks++;
  if n_rows ~= rows(expected)
    failures{end+1} = sprintf('8: gate_vectors.csv has %d rows, expected %d', n_rows, rows(expected));
  end
  modes_seen = {};
  for r = 1:min(n_rows, rows(expected))
    f = strsplit(strtrim(lines{r + 1}), ',', 'CollapseDelimiters', false);
    mode = f{col('mode')};
    m = str2double(f{col('m')});
    gamma = str2double(f{col('gamma')});
    y = zeros(m, 1); S = zeros(m);
    for i = 1:m
      y(i) = str2double(f{col(sprintf('y%d', i))});
      for j = 1:m
        S(i, j) = str2double(f{col(sprintf('s%d%d', i, j))});
      end
    end
    modes_seen{end+1} = mode;
    where = sprintf('8: gate_vectors.csv line %d (%s)', r + 1, mode);

    n_checks++;
    if ~((strcmp(mode, 'planar') && m == 2) || (strcmp(mode, 'doppler') && m == 4))
      failures{end+1} = sprintf('%s: m = %d does not match the mode (section 2)', where, m);
    end
    n_checks++;
    if ~any(abs(appendix_a(min(max(m, 1), 4), :) - gamma) < 5e-4)
      failures{end+1} = sprintf('%s: gamma %.3f is not an Appendix A value for m = %d', where, gamma, m);
    end

    [a, d, out, err] = run_gate(y, S, gamma);
    n_checks++;
    if ~isempty(err)
      failures{end+1} = sprintf('%s: gate raised an error: %s', where, err);
      continue;
    end
    exp_d2 = expected(r, 2);
    exp_acc = logical(expected(r, 3));
    if isfinite(exp_d2)
      ref = reference_nis(y, S);
      n_checks++;
      if abs(d - ref) > 1e-9 * max(1, ref)
        failures{end+1} = sprintf('%s: d2 = %.12g, eig reference %.12g', where, d, ref);
      end
      n_checks++;
      if abs(d - exp_d2) > 1e-5
        failures{end+1} = sprintf('%s: d2 = %.6f, expected %.6f', where, d, exp_d2);
      end
      % Same measurement with gamma set exactly to its own d2 must be admitted.
      n_checks++;
      if ~isequal(run_gate(y, S, d), true)
        failures{end+1} = sprintf('%s: not admitted with gamma == d2', where);
      end
    else
      n_checks++;
      if ~isequal(d, Inf)
        failures{end+1} = sprintf('%s: non-finite input expected d2 = Inf, got %s', where, mat2str(d));
      end
    end
    n_checks++;
    if ~isequal(a, exp_acc)
      failures{end+1} = sprintf('%s: accept = %s, expected %d (d2 = %.6f, gamma = %.3f)', ...
                                where, mat2str(a), exp_acc, d, gamma);
    end
  end
  n_checks++;
  if ~all(ismember({'planar', 'doppler'}, modes_seen))
    failures{end+1} = '8: gate_vectors.csv does not cover both measurement modes';
  end
end

% ---------------------------------------------------------------------------
% Report
% ---------------------------------------------------------------------------
if isempty(failures)
  printf('test_measurement_gate: PASS (%d checks, CVT-SRS-003 Rev C 7.3 G1-G4)\n', n_checks);
else
  printf('test_measurement_gate: FAIL (%d of %d checks)\n', numel(failures), n_checks);
  printf('  - %s\n', failures{:});
  error('test_measurement_gate: measurement_gate does not meet CVT-SRS-003 section 7.3');
end
