% check_investigation.m  DemoForge verification harness for the finale.
%
% Checks the agent's investigation by property, never by keyword:
%
% A. findings.json (schema in the prompt), validated against the repository itself:
%    findings_valid        parsed, with the required fields of the right types
%    n_citations           evidence entries
%    invalid_citations     entries whose file is not a repository input, whose line
%                          does not exist, or whose quote is not on that line (lines
%                          as staged, so a fix the agent made does not move them)
%    key_evidence_groups   how many of the four groups any correct investigation must
%                          cite: the gate's inlined threshold; the config's mode/gate
%                          entries; a failing Doppler run in the data or logs; the gate
%                          test or its G3 trace (why it was not caught). Need all 4.
%    cause_correct         `cause` resolves to the inlined-threshold lines of
%                          src/measurement_gate.m (cause_id names what it resolved to:
%                          kalman_update, config, acceptance_limit, ... are decoys)
%    discriminator_correct field "mode", value "doppler" (not build, not worker)
%    failing_runs_match    exactly the failed runs of data/validation_runs.csv
%    value_correct         wrong_value in_use = 5.991 and correct = 13.277 (+-0.001)
%    ruled_out_count       entries in ruled_out (need >= 2)
% B. The fix: the staged src/measurement_gate.m (the agent's, if it changed it) on
%    the bench capture plus hidden vectors (m = 1..4, other gammas, d2 == gamma,
%    malformed input), against the hidden reference gate.
%    fix_mismatches, fix_nonfinite
% C. The tests: every tests/test_*.m, each in a fresh Octave process, against
%    - the hidden correct gate: all must pass                  agent_tests_pass_ref
%    - the gate as shipped: at least one must fail             agent_tests_fail_shipped
%    - a gate hard-coding 13.277 (metric only)                 tests_catch_hardcoded_doppler
% D. Ground truth recomputed from the campaign data, for display: pass rate, fail
%    and gate-rejection rates per mode, and the attribute that best separates FAIL
%    from PASS.
%
% Exits non-zero only if the repository data it measures is missing or unreadable.

1;

function L = read_lines(p)
  t = fileread(p);
  t = strrep(t, "\r", '');
  if ~isempty(t) && t(end) == "\n", t = t(1:end-1); end
  L = strsplit(t, "\n", 'CollapseDelimiters', false);
end

function s = norm_ws(s)
  s = regexprep(strtrim(s), '\s+', ' ');
end

function L = input_lines(rel)
  % Lines of a repository input as staged (pristine copy if the agent may edit it).
  orig = ['orig__' strrep(rel, '/', '__') '.txt'];
  if exist(orig, 'file') == 2
    L = read_lines(orig);
  else
    L = read_lines(rel);
  end
end

function rel = resolve(p, known)
  rel = '';
  if ~ischar(p) || isempty(p), return; end
  p = strrep(strtrim(p), '\', '/');
  while strncmp(p, './', 2), p = p(3:end); end
  for i = 1:numel(known)
    k = known{i};
    if strcmpi(p, k) || (numel(p) > numel(k) && strcmpi(p(end-numel(k):end), ['/' k]))
      rel = k;
      return;
    end
  end
end

function c = as_cell(x)
  if iscell(x), c = x(:)';
  elseif isstruct(x), c = num2cell(x(:)');
  elseif isempty(x), c = {};
  else, c = {x};
  end
end

function v = num_or_nan(x)
  if isnumeric(x) && isscalar(x), v = double(x);
  elseif ischar(x), v = str2double(x);
  else, v = NaN;
  end
end

function v = field_or(s, f, d)
  if isstruct(s) && isfield(s, f), v = s.(f); else, v = d; end
end

function ok = run_tests_with(octbin, gate_src)
  % Copy the repository's src/tests/config/data/docs into a fresh folder with gate_src as
  % src/measurement_gate.m; run every tests/test_*.m in its own Octave process.
  % ok(i) = 1 if test file i passed.
  d = tempname(); mkdir(d);
  for sub = {'src', 'tests', 'config', 'data', 'docs'}
    if exist(sub{1}, 'dir'), copyfile(sub{1}, fullfile(d, sub{1})); end
  end
  fid = fopen(fullfile(d, 'src', 'measurement_gate.m'), 'w'); fputs(fid, gate_src); fclose(fid);
  T = dir(fullfile(d, 'tests', 'test_*.m'));
  ok = zeros(1, numel(T));
  old = pwd(); cd(d);
  for i = 1:numel(T)
    [~, nm] = fileparts(T(i).name);
    fid = fopen('df_driver.m', 'w');
    fprintf(fid, "addpath(fullfile(pwd, 'src'));\naddpath(fullfile(pwd, 'tests'));\n%s;\n", nm);
    fclose(fid);
    [st, ~] = system(sprintf('"%s" --norc --quiet df_driver.m 2>&1', octbin));
    ok(i) = (st == 0);
  end
  cd(old);
  confirm_recursive_rmdir(false, 'local');
  rmdir(d, 's');
end

try
  KNOWN = {'README.md', 'config/estimator_config.json', 'config/model.json', ...
           'docs/CVT-SRS-003.pdf', 'docs/CHANGELOG.md', 'docs/kalman_filter_spec.md', ...
           'docs/requirements.csv', 'docs/validation_plan.md', 'src/cvt_model.m', ...
           'src/kalman_update.m', 'src/measurement_gate.m', 'src/kalman_filter.py', ...
           'tests/test_kalman.m', 'tests/test_measurement_gate.m', 'tests/test_results.txt', ...
           'data/validation_runs.csv', 'data/validation_summary.xlsx', 'data/gate_vectors.csv', ...
           'logs/estimator-worker.log', 'logs/validation-runner.log', 'logs/scheduler.log', ...
           'notes/handover_notes.md'};
  BINARY = {'docs/CVT-SRS-003.pdf', 'data/validation_summary.xlsx'};

  % ---------------- D. ground truth from the campaign data ----------------
  R = read_lines('data/validation_runs.csv');
  hdr = strsplit(R{1}, ',');
  col = @(name) find(strcmp(hdr, name));
  runs = cellfun(@(l) strsplit(l, ',', 'CollapseDelimiters', false), R(2:end), 'UniformOutput', false);
  runs = runs(~cellfun(@(r) numel(r) < numel(hdr), runs));
  ids    = cellfun(@(r) r{col('run_id')}, runs, 'UniformOutput', false);
  status = cellfun(@(r) r{col('status')}, runs, 'UniformOutput', false);
  isfail = strcmp(status, 'FAIL');
  truth_failing = sort(ids(isfail));
  n_runs = numel(ids);

  spreads = struct();
  rates = struct();
  for attr = {'mode', 'build', 'worker'}
    vals = cellfun(@(r) r{col(attr{1})}, runs, 'UniformOutput', false);
    u = unique(vals);
    fr = zeros(1, numel(u));
    for j = 1:numel(u)
      fr(j) = mean(isfail(strcmp(vals, u{j})));
      rates.([attr{1} '_' strrep(u{j}, '.', '_')]) = fr(j);
    end
    spreads.(attr{1}) = max(fr) - min(fr);
  end
  [~, imax] = max([spreads.mode, spreads.build, spreads.worker]);
  attrs = {'mode', 'build', 'worker'};
  truth_discriminator = attrs{imax};
  modes = cellfun(@(r) r{col('mode')}, runs, 'UniformOutput', false);
  failing_doppler = ids(isfail & strcmp(modes, 'doppler'));

  W = read_lines('logs/estimator-worker.log');
  rej = struct('planar', [], 'doppler', []);
  for i = 1:numel(W)
    tok = regexp(W{i}, '\[gate\] run=\S+ mode=(\w+) complete:.*\(([\d.]+)%\)', 'tokens', 'once');
    if ~isempty(tok) && isfield(rej, tok{1})
      rej.(tok{1})(end+1) = str2double(tok{2});
    end
  end

  % ---------------- key evidence lines (on the files as staged) ----------------
  GL = input_lines('src/measurement_gate.m');
  gate_lines = find(~cellfun(@isempty, strfind(GL, 'GATE_CHI2')));
  CL = input_lines('config/estimator_config.json');
  cfg_lines = find(~cellfun(@isempty, regexp(CL, '13\.277|"doppler"|"confidence"|"gamma"|"measurement_dim": 4', 'once')));
  TL = input_lines('tests/test_measurement_gate.m');
  test_lines = find(~cellfun(@isempty, regexp(TL, 'GAMMA|measurement_gate\(', 'once')));
  QL = input_lines('docs/requirements.csv');
  g3_lines = find(strncmp(QL, 'G3,', 3));
  XL = input_lines('tests/test_results.txt');
  res_lines = find(~cellfun(@isempty, strfind(XL, 'test_measurement_gate')));

  % ---------------- A. findings.json ----------------
  findings_valid = 0; n_citations = 0; invalid_citations = 0; key_groups = 0;
  cause_correct = 0; cause_id = 'none'; discriminator_correct = 0;
  failing_runs_match = 0; value_correct = 0; ruled_out_count = 0;
  if exist('findings.json', 'file') == 2
    try
      F = jsondecode(fileread('findings.json'));
      findings_valid = double(isstruct(F) && all(isfield(F, ...
        {'root_cause', 'cause', 'discriminator', 'failing_runs', 'wrong_value', 'evidence', 'ruled_out'})));
    catch
      F = struct();
    end
  end

  if findings_valid
    % cause
    crel = resolve(field_or(F.cause, 'file', ''), KNOWN);
    cline = num_or_nan(field_or(F.cause, 'line', NaN));
    switch crel
      case 'src/measurement_gate.m'
        if any(cline == gate_lines), cause_id = 'gate_threshold'; else, cause_id = 'gate_other'; end
      case 'src/kalman_update.m',     cause_id = 'kalman_update';
      case 'src/kalman_filter.py',    cause_id = 'python_port';
      case 'src/cvt_model.m',         cause_id = 'cvt_model';
      case {'config/estimator_config.json', 'config/model.json'}, cause_id = 'config';
      case 'docs/validation_plan.md', cause_id = 'acceptance_limit';
      case 'logs/scheduler.log',      cause_id = 'infrastructure_or_worker';
      case '',                        cause_id = 'unresolved';
      otherwise,                      cause_id = 'other';
    end
    cause_correct = double(strcmp(cause_id, 'gate_threshold'));

    % discriminator
    dfield = lower(strtrim(char(field_or(F.discriminator, 'field', ''))));
    dvalue = lower(strtrim(char(field_or(F.discriminator, 'value', ''))));
    discriminator_correct = double(strcmp(dfield, 'mode') && strcmp(dvalue, 'doppler'));

    % failing runs
    fr = as_cell(F.failing_runs);
    if all(cellfun(@ischar, fr))
      fr = unique(upper(strtrim(fr)));
      failing_runs_match = double(isequal(sort(fr), truth_failing));
    end

    % wrong value
    wv = F.wrong_value;
    if isstruct(wv)
      value_correct = double(abs(num_or_nan(field_or(wv, 'in_use', NaN)) - 5.991) <= 1e-3 && ...
                             abs(num_or_nan(field_or(wv, 'correct', NaN)) - 13.277) <= 1e-3);
    end

    % evidence
    ev = as_cell(F.evidence);
    n_citations = numel(ev);
    hit = false(1, 4);
    for i = 1:n_citations
      e = ev{i};
      rel = resolve(field_or(e, 'file', ''), KNOWN);
      if isempty(rel), invalid_citations++; continue; end
      if any(strcmp(rel, BINARY)), continue; end      % PDF / workbook: no line to check
      ln = num_or_nan(field_or(e, 'line', NaN));
      L = input_lines(rel);
      if ~(isfinite(ln) && ln == fix(ln) && ln >= 1 && ln <= numel(L))
        invalid_citations++; continue;
      end
      q = field_or(e, 'quote', '');
      if ~ischar(q) || isempty(strtrim(q)) || isempty(strfind(norm_ws(L{ln}), norm_ws(q)))
        invalid_citations++; continue;
      end
      switch rel
        case 'src/measurement_gate.m',       hit(1) = hit(1) || any(ln == gate_lines);
        case 'config/estimator_config.json', hit(2) = hit(2) || any(ln == cfg_lines);
        case {'data/validation_runs.csv', 'logs/validation-runner.log', 'logs/estimator-worker.log'}
          rid = regexp(L{ln}, 'VR-\d{4}', 'match');
          hit(3) = hit(3) || any(ismember(rid, failing_doppler));
        case 'tests/test_measurement_gate.m', hit(4) = hit(4) || any(ln == test_lines);
        case 'docs/requirements.csv',        hit(4) = hit(4) || any(ln == g3_lines);
        case 'tests/test_results.txt',       hit(4) = hit(4) || any(ln == res_lines);
      end
    end
    key_groups = sum(hit);

    ro = as_cell(F.ruled_out);
    ruled_out_count = sum(cellfun(@(x) (ischar(x) && numel(strtrim(x)) >= 10) || isstruct(x), ro));
  end

  % ---------------- B. the fix, on hidden vectors ----------------
  addpath(fullfile(pwd(), 'src'));
  rehash();
  V = read_lines('data/gate_vectors.csv');
  vec = {};
  for i = 2:numel(V)
    f = strsplit(V{i}, ',', 'CollapseDelimiters', false);
    m = str2double(f{2});
    G = reshape(str2double(f(8:23)), 4, 4)';
    vec{end+1} = {str2double(f(4:3+m))', G(1:m, 1:m), str2double(f{3})};
  end
  A3 = reshape(sin(1:9), 3, 3);  S3 = A3 * A3' + 1.5 * eye(3);
  A4 = reshape(cos(1:16), 4, 4); S4 = A4 * A4' + 2.0 * eye(4);
  S2 = [1.3 -0.4; -0.4 0.7];
  scale = @(y, S, d) y * sqrt(d / (y' * (S \ y)));
  vec(end+1:end+5) = {{2, 4, 3.841}, {2.5, 1, 3.841}, {2.5, 1, 6.635}, {3, 1, 6.635}, {3, 1, 10.828}};
  for c = {{7.4, 5.991}, {7.4, 9.210}, {11.6, 9.210}, {11.6, 13.816}}
    vec{end+1} = {scale([0.9; -1.4], S2, c{1}{1}), S2, c{1}{2}};
  end
  for c = {{9.6, 7.815}, {9.6, 11.345}, {12.9, 11.345}, {12.9, 16.266}}
    vec{end+1} = {scale([0.6; -1.1; 0.8], S3, c{1}{1}), S3, c{1}{2}};
  end
  for c = {{7.3, 9.488}, {11.2, 9.488}, {11.2, 13.277}, {12.4, 13.277}, {15.1, 13.277}, {15.1, 18.467}}
    vec{end+1} = {scale([1.1; -0.3; 0.7; -1.6], S4, c{1}{1}), S4, c{1}{2}};
  end
  vec(end+1:end+3) = {{[3; 0], eye(2), 9}, {[2; 2; 2; 2], 4 * eye(4), 4}, {[2; 2; 2; 2], 4 * eye(4), 3.999}};
  fix_mismatches = 0;
  for k = 1:numel(vec)
    v = vec{k};
    [ar, dr] = measurement_gate_ref(v{1}, v{2}, v{3});
    try
      [a, d] = measurement_gate(v{1}, v{2}, v{3});
      bad = ~isscalar(a) || logical(a) ~= logical(ar) || (isfinite(dr) && ~(abs(d - dr) <= 1e-6));
    catch
      bad = true;
    end
    fix_mismatches += bad;
  end
  badin = {{[NaN; 0.2], eye(2), 9.21}, {[0.3; 0.1], [Inf 0; 0 1], 9.21}, ...
           {[0.3; 0.1; 0; 0], eye(4), NaN}, {[0.3; 0.1], eye(2), Inf}, {[0; 0], eye(2), 0}};
  fix_nonfinite = 1;
  for i = 1:numel(badin)
    c = badin{i};
    try
      [a, d] = measurement_gate(c{1}, c{2}, c{3});
      if logical(a) || ~isinf(d), fix_nonfinite = 0; end
    catch
      fix_nonfinite = 0;
    end
  end

  % ---------------- C. the agent's tests: pass on truth, fail on the shipped gate ----
  octbin = fullfile(OCTAVE_HOME(), 'bin', 'octave-cli.exe');
  if ~exist(octbin, 'file'), octbin = fullfile(OCTAVE_HOME(), 'bin', 'octave-cli'); end
  ref_src = strrep(fileread('measurement_gate_ref.m'), 'measurement_gate_ref', 'measurement_gate');
  shipped_src = fileread('orig__src__measurement_gate.m.txt');
  hard_src = strrep(ref_src, 'accept = (d2 <= gamma);', 'accept = (d2 <= 13.277);');
  ok_ref  = run_tests_with(octbin, ref_src);
  ok_ship = run_tests_with(octbin, shipped_src);
  ok_hard = run_tests_with(octbin, hard_src);
  agent_tests_pass_ref = double(~isempty(ok_ref) && all(ok_ref));
  agent_tests_fail_shipped = double(any(~ok_ship));
  tests_catch_hardcoded_doppler = double(any(~ok_hard));

  metrics = struct( ...
    'findings_valid', findings_valid, 'n_citations', n_citations, ...
    'invalid_citations', invalid_citations, 'key_evidence_groups', key_groups, ...
    'cause_id', cause_id, 'cause_correct', cause_correct, ...
    'discriminator_correct', discriminator_correct, 'failing_runs_match', failing_runs_match, ...
    'value_correct', value_correct, 'ruled_out_count', ruled_out_count, ...
    'fix_mismatches', fix_mismatches, 'fix_nonfinite', fix_nonfinite, ...
    'agent_tests_pass_ref', agent_tests_pass_ref, ...
    'agent_tests_fail_shipped', agent_tests_fail_shipped, ...
    'tests_catch_hardcoded_doppler', tests_catch_hardcoded_doppler, ...
    'n_runs', n_runs, 'n_failed', numel(truth_failing), ...
    'campaign_pass_rate', round(1e4 * (1 - mean(isfail))) / 1e4, ...
    'discriminator', truth_discriminator, ...
    'fail_rate_doppler', round(1e4 * rates.mode_doppler) / 1e4, ...
    'fail_rate_planar', round(1e4 * rates.mode_planar) / 1e4, ...
    'reject_rate_doppler', round(100 * mean(rej.doppler)) / 100, ...
    'reject_rate_planar', round(100 * mean(rej.planar)) / 100);
  fid = fopen('metrics.json', 'w');
  fputs(fid, jsonencode(metrics));
  fclose(fid);

  printf('findings: valid=%d cause=%s discriminator=%d failing_runs=%d value=%d citations=%d (invalid %d) key_groups=%d/4 ruled_out=%d\n', ...
         findings_valid, cause_id, discriminator_correct, failing_runs_match, value_correct, ...
         n_citations, invalid_citations, key_groups, ruled_out_count);
  printf('fix: mismatches=%d nonfinite=%d   tests: pass_ref=%d fail_shipped=%d catch_hardcoded_13.277=%d\n', ...
         fix_mismatches, fix_nonfinite, agent_tests_pass_ref, agent_tests_fail_shipped, ...
         tests_catch_hardcoded_doppler);
  printf('truth: runs=%d failed=%d pass_rate=%.3f discriminator=%s reject doppler=%.2f%% planar=%.2f%%\n', ...
         n_runs, numel(truth_failing), 1 - mean(isfail), truth_discriminator, ...
         mean(rej.doppler), mean(rej.planar));
  exit(0);
catch err
  fprintf(2, 'check_investigation failed: %s\n', err.message);
  exit(1);
end
