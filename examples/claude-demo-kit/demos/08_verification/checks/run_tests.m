% run_tests.m  DemoForge verification harness for demo 8 (automated verification).
%
% Measures the agent's work, not the provided code:
%
%  1. Runs the agent's test_kalman.m (`octave-cli test_kalman.m`, exit 0 = pass)
%     in a fresh folder per implementation, with kalman_update.m swapped for:
%       ref_correct.m      a correct implementation        -> the test must PASS
%       mut_init_both.m    the provided code: ignores x0, P0 -> must FAIL
%       mut_init_x0.m      ignores model.x0 only            -> must FAIL
%       mut_init_p0.m      ignores model.P0 only            -> must FAIL
%       mut_no_q.m, mut_fixed_q.m, mut_fixed_r.m, mut_cov_update.m,
%       mut_prior_out.m, mut_update_first.m                 -> at least 4 of 6 FAIL
%     The three init mutants are the defect class the task is about; the other six
%     are ordinary recursion slips a test that checks the spec should mostly catch.
%     The agent's other files (helpers, data) are copied alongside.
%  2. Validates findings.json: verdict, the violated requirement (R3), evidence that
%     cites the initialisation lines of the provided kalman_update.m, every citation
%     resolving to a real file:line, and no defect blamed on R1/R2/R4 (which hold).
%  3. Display only: provided-vs-correct discrepancy on the default and a
%     non-default initial condition (why the existing test never saw the defect).
%
% Writes metrics.json. Exits non-zero only if it cannot run at all.

1;

function X = kf(Z, model, honor_init)
  % The CVT-EST-001 §4 recursion; honor_init=false reproduces the provided code.
  F = model.F; Q = model.Q; H = model.H; R = model.R;
  n = rows(F);
  if honor_init
    x = model.x0(:); P = model.P0;
  else
    x = zeros(n, 1); P = eye(n);
  end
  I = eye(n);
  X = zeros(rows(Z), n);
  for k = 1:rows(Z)
    x = F * x;  P = F * P * F' + Q;
    y = Z(k, :)' - H * x;  S = H * P * H' + R;  K = (P * H') / S;
    x = x + K * y;  P = (I - K * H) * P;
    X(k, :) = x';
  end
end

function c = as_cell(v)
  if iscell(v)
    c = v(:)';
  elseif isstruct(v)
    c = num2cell(v(:)');
  elseif isempty(v)
    c = {};
  else
    c = {v};
  end
end

function s = as_text(v)
  if ischar(v)
    s = v;
  elseif iscell(v)
    s = strjoin(cellfun(@as_text, v, 'UniformOutput', false), ' ');
  elseif isnumeric(v) || islogical(v)
    s = num2str(v);
  else
    s = '';
  end
end

function s = ifelse_str(cond, a, b)
  if cond, s = a; else, s = b; end
end

function n = count_lines(path)
  t = fileread(path);
  n = numel(regexp(t, '\n', 'match'));
  if ~isempty(t) && t(end) ~= sprintf('\n')
    n = n + 1;
  end
end

function passed = run_agent_test(octbin, impl, workdir, sandbox)
  % Stage the agent's files plus `impl` as kalman_update.m; run the test there.
  hidden = {'kalman_update.m', 'metrics.json', 'run_tests.m', 'ref_correct.m'};
  if exist(sandbox, 'dir')
    confirm_recursive_rmdir(false, 'local');
    rmdir(sandbox, 's');
  end
  mkdir(sandbox);
  d = dir(workdir);
  for i = 1:numel(d)
    nm = d(i).name;
    if d(i).isdir || any(strcmp(nm, hidden)) || strncmp(nm, 'mut_', 4)
      continue;
    end
    copyfile(fullfile(workdir, nm), fullfile(sandbox, nm));
  end
  copyfile(fullfile(workdir, impl), fullfile(sandbox, 'kalman_update.m'));
  old = cd(sandbox);
  cleanup = onCleanup(@() cd(old));
  [status, ~] = system(sprintf('"%s" --norc --quiet test_kalman.m', octbin));
  passed = (status == 0);
end

workdir = pwd;
try
  octbin = fullfile(OCTAVE_HOME, 'bin', 'octave-cli.exe');
  if ~exist(octbin, 'file')
    octbin = fullfile(OCTAVE_HOME, 'bin', 'octave-cli');
  end
  if ~exist(octbin, 'file')
    error('run_tests:octave', 'cannot locate octave-cli under OCTAVE_HOME');
  end

  % ---- display metrics: what the provided code does -------------------------
  m = jsondecode(fileread('model.json'));
  model = struct('F', m.F, 'Q', m.Q, 'H', m.H, 'R', m.R, 'x0', m.x0(:), 'P0', m.P0);
  Z = csvread('test_vectors.csv', 1, 0);
  Zs = Z(1:25, :);
  default_discrepancy = max(max(abs(kf(Zs, model, false) - kf(Zs, model, true))));
  m2 = model;  m2.x0 = [10; 5; 1; -1];  m2.P0 = 1e-6 * eye(4);
  init_discrepancy = max(max(abs(kf(Zs, m2, false) - kf(Zs, m2, true))));

  % ---- 1. the agent's tests against correct code and mutants ---------------
  init_mutants  = {'mut_init_both.m', 'mut_init_x0.m', 'mut_init_p0.m'};
  other_mutants = {'mut_no_q.m', 'mut_fixed_q.m', 'mut_fixed_r.m', ...
                   'mut_cov_update.m', 'mut_prior_out.m', 'mut_update_first.m'};
  test_present = exist(fullfile(workdir, 'test_kalman.m'), 'file') == 2;
  passes_correct = 0;  kills_provided = 0;  kills_init = 0;  kills_other = 0;
  if test_present
    sbroot = fullfile(workdir, '_sandboxes');
    passes_correct = run_agent_test(octbin, 'ref_correct.m', workdir, fullfile(sbroot, 'ref_correct'));
    printf('  %-20s %s\n', 'ref_correct', ifelse_str(passes_correct, 'pass (required)', 'FAIL (must pass)'));
    for i = 1:numel(init_mutants)
      killed = ~run_agent_test(octbin, init_mutants{i}, workdir, fullfile(sbroot, init_mutants{i}(1:end-2)));
      kills_init = kills_init + killed;
      if i == 1, kills_provided = killed; end
      printf('  %-20s %s\n', init_mutants{i}(1:end-2), ifelse_str(killed, 'killed', 'survived'));
    end
    for i = 1:numel(other_mutants)
      killed = ~run_agent_test(octbin, other_mutants{i}, workdir, fullfile(sbroot, other_mutants{i}(1:end-2)));
      kills_other = kills_other + killed;
      printf('  %-20s %s\n', other_mutants{i}(1:end-2), ifelse_str(killed, 'killed', 'survived'));
    end
    confirm_recursive_rmdir(false, 'local');
    rmdir(sbroot, 's');
  end

  % ---- 2. findings.json -----------------------------------------------------
  % The defect lines are found in the hidden copy of the provided file, so they
  % stay right even if the agent edited kalman_update.m in place.
  src = regexp(fileread('mut_init_both.m'), '\n', 'split');
  init_lines = find(~cellfun(@isempty, regexp(src, '^\s*(x\s*=\s*zeros|P\s*=\s*eye)\(', 'once')));
  provided_nlines = count_lines('mut_init_both.m');

  findings_valid = 0;  findings_verdict_ok = 0;  findings_defect_pinned = 0;
  findings_no_false_requirement = 0;  findings_citations_valid = 0;
  if exist('findings.json', 'file')
    try
      f = jsondecode(fileread('findings.json'));
      verdict = lower(strtrim(as_text(f.verdict)));
      defects = as_cell(f.defects);
      findings_valid = 1;
      findings_verdict_ok = strcmp(verdict, 'defect_found');
      n_cites = 0;  bad_cites = 0;  false_req = 0;
      for i = 1:numel(defects)
        d = defects{i};
        req = upper(as_text(d.requirement));
        if ~isempty(regexp(req, '(^|[^0-9A-Z])R[124]($|[^0-9])', 'once'))
          false_req = 1;
        end
        is_r3 = ~isempty(regexp(req, '(^|[^0-9A-Z])R3($|[^0-9])', 'once'));
        ev = {};
        if isfield(d, 'evidence'), ev = as_cell(d.evidence); end
        for j = 1:numel(ev)
          e = ev{j};
          n_cites = n_cites + 1;
          file = regexprep(strtrim(as_text(e.file)), '^.*[\\/]', '');
          line = e.line;
          if ischar(line), line = str2double(line); end
          if ~isnumeric(line) || ~isscalar(line) || line ~= fix(line)
            bad_cites = bad_cites + 1;  continue;
          end
          if strcmp(file, 'kalman_update.m')
            nlines = provided_nlines;
          elseif exist(fullfile(workdir, file), 'file') == 2
            nlines = count_lines(fullfile(workdir, file));
          else
            bad_cites = bad_cites + 1;  continue;
          end
          if line < 1 || line > nlines
            bad_cites = bad_cites + 1;  continue;
          end
          if is_r3 && strcmp(file, 'kalman_update.m') && any(line == init_lines)
            findings_defect_pinned = 1;
          end
        end
      end
      findings_no_false_requirement = ~false_req;
      findings_citations_valid = (n_cites > 0) && (bad_cites == 0);
    catch err
      fprintf(2, 'findings.json unreadable: %s\n', err.message);
      findings_valid = 0;
    end
  end

  metrics = struct( ...
    'test_present', double(test_present), ...
    'passes_correct', double(passes_correct), ...
    'kills_provided', double(kills_provided), ...
    'kills_init', kills_init, ...
    'kills_other', kills_other, ...
    'findings_valid', findings_valid, ...
    'findings_verdict_ok', double(findings_verdict_ok), ...
    'findings_defect_pinned', findings_defect_pinned, ...
    'findings_no_false_requirement', double(findings_no_false_requirement), ...
    'findings_citations_valid', double(findings_citations_valid), ...
    'default_discrepancy', default_discrepancy, ...
    'init_discrepancy', init_discrepancy, ...
    'n_vectors', rows(Z));
  fid = fopen(fullfile(workdir, 'metrics.json'), 'w');
  fputs(fid, jsonencode(metrics));
  fclose(fid);
  printf('passes_correct=%d kills_init=%d/3 kills_other=%d/6 verdict_ok=%d pinned=%d no_false_req=%d cites_ok=%d\n', ...
         passes_correct, kills_init, kills_other, findings_verdict_ok, ...
         findings_defect_pinned, findings_no_false_requirement, findings_citations_valid);
  exit(0);
catch err
  cd(workdir);
  fprintf(2, 'run_tests failed: %s\n', err.message);
  exit(1);
end
