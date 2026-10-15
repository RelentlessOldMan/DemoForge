% run_tests.m  DemoForge verification harness for the spec-to-implementation demo.
%
% The agent implements measurement_gate(y, S, gamma) from CVT-SRS-003 Rev C §7.3 and
% writes test_measurement_gate.m. This harness measures both, independently, and
% writes metrics.json. It never trusts the agent's own report.
%
% 1. The gate, on the visible bench capture (gate_vectors.csv) and on HIDDEN vectors
%    the agent never saw: m = 1, 2, 3, 4, gammas from every column of Appendix A,
%    d2 placed between the table values (so a gate with any hard-coded threshold gets
%    some wrong), and the exact boundary d2 == gamma (admitted, §7.3.2).
%      max_abs_error      largest |d2 - d2_ref| over all finite vectors        (G1)
%      accept_mismatches  decision disagreements on the bench capture          (G2)
%      hidden_mismatches  decision disagreements on the hidden vectors      (G2, G3)
%      nonfinite_handled  1 iff every malformed input (NaN/Inf in y or S; NaN, Inf,
%                         zero, negative or non-scalar gamma) gives accept = false
%                         and d2 = Inf without raising                     (G-BC-1/2)
%
% 2. The agent's tests (G5), run in a fresh Octave process against:
%      - the hidden correct gate: must pass            -> agent_tests_pass_ref
%      - four hidden mutants, each a defect the §7.3 requirements exist to prevent:
%          hardcoded  ignores gamma, uses 9.21 (the planar default)          (G3)
%          strict     d2 < gamma instead of d2 <= gamma                       (G2)
%          no_guard   no fail-closed guard: Inf in S or an Inf gamma admits,
%                     a NaN innovation returns d2 = NaN                        (G4)
%          wrong_nis  d2 = y'y, ignoring S                                    (G1)
%        A mutant is killed if the agent's test exits non-zero against it.
%        mutants_killed counts them. The bar is all four: G5 asks for a test that
%        exercises G1-G4, and each mutant violates exactly one of them.
%
% measurement_gate_ref.m is staged beside this harness (checks/) and never shown to
% the agent. Exits non-zero only if the harness itself cannot run.

1;

function [ok, out] = run_agent_test(octbin, workdir, gate_src)
  % Copy the agent's test (and any helper .m/.csv it wrote) into a fresh folder with
  % gate_src as measurement_gate.m, and run it in a separate Octave process.
  d = tempname();
  mkdir(d);
  skip = {'measurement_gate.m', 'run_tests.m', 'measurement_gate_ref.m'};
  for pat = {'*.m', '*.csv'}
    lst = dir(fullfile(workdir, pat{1}));
    for i = 1:numel(lst)
      if ~any(strcmp(lst(i).name, skip))
        copyfile(fullfile(workdir, lst(i).name), fullfile(d, lst(i).name));
      end
    end
  end
  fid = fopen(fullfile(d, 'measurement_gate.m'), 'w'); fputs(fid, gate_src); fclose(fid);
  fid = fopen(fullfile(d, 'df_run_agent_test.m'), 'w');
  fputs(fid, "test_measurement_gate;\n"); fclose(fid);
  old = pwd();
  cd(d);
  [st, out] = system(sprintf('"%s" --norc --quiet df_run_agent_test.m 2>&1', octbin));
  cd(old);
  confirm_recursive_rmdir(false, 'local');
  rmdir(d, 's');
  ok = (st == 0);
end

function src = mutate(src, from, to)
  if isempty(strfind(src, from))
    error('run_tests:mutant', 'mutation anchor not found: %s', from);
  end
  src = strrep(src, from, to);
end

try
  if exist('measurement_gate', 'file') ~= 2
    error('run_tests:missing', 'measurement_gate.m not found (implement it)');
  end
  if exist('measurement_gate_ref', 'file') ~= 2
    error('run_tests:missing', 'measurement_gate_ref.m (reference) not found');
  end

  % ---------------- 1a. the visible bench capture ----------------
  fid = fopen('gate_vectors.csv', 'r');
  fgetl(fid);
  cap = {};
  while true
    ln = fgetl(fid);
    if ~ischar(ln), break; end
    f = strsplit(ln, ',', 'CollapseDelimiters', false);
    m = str2double(f{2});
    G = reshape(str2double(f(8:23)), 4, 4)';
    cap{end+1} = {str2double(f(4:3+m))', G(1:m, 1:m), str2double(f{3})};
  end
  fclose(fid);
  n_vectors = numel(cap);

  % ---------------- 1b. hidden vectors ----------------
  hid = {};
  A3 = reshape(sin(1:9), 3, 3);  S3 = A3 * A3' + 1.5 * eye(3);
  A4 = reshape(cos(1:16), 4, 4); S4 = A4 * A4' + 2.0 * eye(4);
  S2 = [1.3 -0.4; -0.4 0.7];
  scale = @(y, S, d) y * sqrt(d / (y' * (S \ y)));   % place d2 at d
  % m = 1
  hid{end+1} = {2, 4, 3.841};                % d2 = 1     admit
  hid{end+1} = {2.5, 1, 3.841};              % 6.25       reject
  hid{end+1} = {2.5, 1, 6.635};              % 6.25       admit
  hid{end+1} = {3, 1, 6.635};                % 9          reject
  hid{end+1} = {3, 1, 10.828};               % 9          admit
  % m = 2, gammas from all three confidence columns
  y2 = [0.9; -1.4];
  for c = {{7.4, 5.991}, {7.4, 9.210}, {11.6, 9.210}, {11.6, 13.816}, {4.1, 5.991}}
    hid{end+1} = {scale(y2, S2, c{1}{1}), S2, c{1}{2}};
  end
  % m = 3
  y3 = [0.6; -1.1; 0.8];
  for c = {{9.6, 7.815}, {9.6, 11.345}, {12.9, 11.345}, {12.9, 16.266}, {5.0, 7.815}}
    hid{end+1} = {scale(y3, S3, c{1}{1}), S3, c{1}{2}};
  end
  % m = 4 (Doppler)
  y4 = [1.1; -0.3; 0.7; -1.6];
  for c = {{7.3, 9.488}, {11.2, 9.488}, {11.2, 13.277}, {12.4, 13.277}, ...
           {15.1, 13.277}, {15.1, 18.467}, {10.1, 9.210}}
    hid{end+1} = {scale(y4, S4, c{1}{1}), S4, c{1}{2}};
  end
  % exact boundary d2 == gamma (admitted): representable with S = I or 4I
  hid{end+1} = {[3; 0], eye(2), 9};
  hid{end+1} = {[1; 2; 2], eye(3), 9};
  hid{end+1} = {[2; 2; 2; 2], 4 * eye(4), 4};
  hid{end+1} = {[2; 2; 2; 2], 4 * eye(4), 3.999};          % just outside
  n_hidden = numel(hid);

  max_abs_error = 0;
  accept_mismatches = 0;
  hidden_mismatches = 0;
  gate_errors = 0;
  sets = {cap, hid};
  for si = 1:2
    vs = sets{si};
    for k = 1:numel(vs)
      v = vs{k};
      [ar, dr] = measurement_gate_ref(v{1}, v{2}, v{3});
      try
        [a, d] = measurement_gate(v{1}, v{2}, v{3});
      catch
        gate_errors++;
        a = ~ar; d = NaN;
      end
      if isfinite(dr)
        if isfinite(d), max_abs_error = max(max_abs_error, abs(d - dr));
        else,           max_abs_error = Inf; end
      end
      if ~isscalar(a) || logical(a) ~= logical(ar)
        if si == 1, accept_mismatches++; else, hidden_mismatches++; end
      end
    end
  end

  % ---------------- 1c. malformed inputs: fail closed, never raise ----------------
  bad = {{[NaN; 0.2], eye(2), 9.21}, {[0.3; Inf], eye(2), 9.21}, ...
         {[0.3; 0.1], [Inf 0; 0 1], 9.21}, {[0.3; 0.1; 0; 0], [eye(3) [NaN;0;0]; 0 0 0 1], 13.277}, ...
         {[0.3; 0.1], eye(2), NaN}, {[0.3; 0.1], eye(2), Inf}, ...
         {[0; 0], eye(2), 0}, {[0.3; 0.1], eye(2), -9.21}, {[0.3; 0.1], eye(2), [9.21 13.277]}};
  nonfinite_handled = 1;
  for i = 1:numel(bad)
    c = bad{i};
    try
      [a, d] = measurement_gate(c{1}, c{2}, c{3});
      if ~isscalar(a) || logical(a) || ~(isscalar(d) && isinf(d) && d > 0)
        nonfinite_handled = 0;
      end
    catch
      nonfinite_handled = 0;
    end
  end

  % ---------------- 2. the agent's tests: pass on the truth, fail on mutants --------
  octbin = fullfile(OCTAVE_HOME(), 'bin', 'octave-cli.exe');
  if ~exist(octbin, 'file'), octbin = fullfile(OCTAVE_HOME(), 'bin', 'octave-cli'); end
  ref_src = strrep(fileread('measurement_gate_ref.m'), 'measurement_gate_ref', 'measurement_gate');
  mutants = struct( ...
    'name', {'hardcoded', 'strict', 'no_guard', 'wrong_nis'}, ...
    'src', {mutate(ref_src, 'accept = (d2 <= gamma);', 'accept = (d2 <= 9.21);'), ...
            mutate(ref_src, 'accept = (d2 <= gamma);', 'accept = (d2 < gamma);'), ...
            mutate(ref_src, 'if any(~isfinite(y(:)))', 'if false && any(~isfinite(y(:)))'), ...
            mutate(ref_src, 'd2 = y(:)'' * (Ssym \ y(:));', 'd2 = y(:)'' * y(:);')});

  has_tests = exist('test_measurement_gate.m', 'file') == 2;
  agent_tests_pass_ref = 0;
  killed = zeros(1, numel(mutants));
  if has_tests
    [ok, out] = run_agent_test(octbin, pwd(), ref_src);
    agent_tests_pass_ref = double(ok);
    if ~ok
      lines = strsplit(strtrim(out), "\n");
      printf('agent tests FAILED against the correct gate:\n  %s\n', ...
             strjoin(lines(max(1, end-3):end), "\n  "));
    end
    for i = 1:numel(mutants)
      [ok, ~] = run_agent_test(octbin, pwd(), mutants(i).src);
      killed(i) = double(~ok);
    end
  end

  metrics = struct( ...
    'n_vectors',            n_vectors, ...
    'n_hidden',             n_hidden, ...
    'max_abs_error',        max_abs_error, ...
    'accept_mismatches',    accept_mismatches, ...
    'hidden_mismatches',    hidden_mismatches, ...
    'gate_errors',          gate_errors, ...
    'nonfinite_handled',    nonfinite_handled, ...
    'agent_tests_pass_ref', agent_tests_pass_ref, ...
    'mutants_total',        numel(mutants), ...
    'mutants_killed',       sum(killed), ...
    'killed_hardcoded',     killed(1), ...
    'killed_strict',        killed(2), ...
    'killed_no_guard',      killed(3), ...
    'killed_wrong_nis',     killed(4));
  if ~isfinite(metrics.max_abs_error), metrics.max_abs_error = 1e300; end

  fid = fopen('metrics.json', 'w');
  fputs(fid, jsonencode(metrics));
  fclose(fid);

  printf(['capture=%d hidden=%d max_abs_error=%.3g accept_mismatches=%d ' ...
          'hidden_mismatches=%d nonfinite_handled=%d\n'], n_vectors, n_hidden, ...
         max_abs_error, accept_mismatches, hidden_mismatches, nonfinite_handled);
  printf('agent tests: pass_ref=%d  mutants killed %d/%d (hardcoded=%d strict=%d no_guard=%d wrong_nis=%d)\n', ...
         agent_tests_pass_ref, sum(killed), numel(mutants), killed);
  exit(0);
catch err
  fprintf(2, 'run_tests failed: %s\n', err.message);
  exit(1);
end
