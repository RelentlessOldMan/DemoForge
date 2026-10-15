% run_tests.m - DemoForge verification harness for the MATLAB implementation demo.
%
% Measures the agent's work independently of anything the agent reports, and writes
% metrics.json:
%
%   max_abs_error          agent kalman_update vs the hidden reference_states.csv,
%                          on test_vectors.csv with the model.json model
%   hidden_model_error     agent kalman_update vs the hidden reference filter on a
%                          second model (other F, Q, H, R, x0, P0) and measurement stream
%                          the agent never saw: catches hard-coded constants
%   test_present           1 if the agent left test_kalman_update.m
%   test_passes_reference  1 if the agent's test passes when kalman_update is the
%                          hidden correct implementation
%   test_catches_mutant    1 if the agent's test fails when kalman_update is a
%                          deliberately broken implementation (the test has teeth)
%   runtime_ms, n_vectors  display only
%
% The agent's test runs in a separate octave-cli process in a scratch copy of the
% working folder, with kalman_update.m swapped for a wrapper around the hidden
% reference (ref_cvt_filter.m) or the mutant (mut_cvt_filter.m). Exits non-zero only
% if it cannot produce a valid result for the agent's implementation.

1;  % script file: the helper below is defined before the main body runs

function status = run_agent_test(work, sub, impl)
  % Copy the working folder's files into work/sub, make kalman_update.m a wrapper
  % around impl, and run the agent's test there in a fresh octave-cli process.
  d = fullfile(work, sub);
  if exist(d, 'dir')
    confirm_recursive_rmdir(false, 'local');
    rmdir(d, 's');
  end
  mkdir(d);
  ents = dir(work);
  for i = 1:numel(ents)
    if ~ents(i).isdir && ~strcmp(ents(i).name, 'metrics.json')
      copyfile(fullfile(work, ents(i).name), fullfile(d, ents(i).name));
    end
  end
  fid = fopen(fullfile(d, 'kalman_update.m'), 'w');
  fprintf(fid, 'function X = kalman_update(Z, model)\n  X = %s(Z, model);\nend\n', impl);
  fclose(fid);

  bin = fullfile(OCTAVE_HOME, 'bin', 'octave-cli');
  if ispc
    bin = [bin '.exe'];
  end
  old = cd(d);
  [status, out] = system(sprintf('"%s" --norc --quiet --eval test_kalman_update', bin));
  cd(old);
  lines = strsplit(strtrim(out), "\n");
  printf('  [%s] exit %d: %s\n', sub, status, strtrim(lines{end}));
end

BAD = 1e300;   % stands in for "no usable result" (jsonencode has no Inf)

try
  if exist('kalman_update', 'file') ~= 2
    error('run_tests:missing', 'kalman_update.m not found on path (implement it)');
  end

  % --- default model: the same file the agent was given ---
  m = jsondecode(fileread('model.json'));
  model.F  = m.F;  model.Q = m.Q;  model.H = m.H;  model.R = m.R;
  model.x0 = m.x0(:);
  model.P0 = m.P0;

  Z = csvread('test_vectors.csv', 1, 0);   % skip header row
  n_vectors = rows(Z);

  t = tic;
  X = kalman_update(Z, model);
  runtime_ms = 1000 * toc(t);

  if ~isequal(size(X), [n_vectors, 4])
    error('run_tests:shape', 'kalman_update returned %dx%d, expected %dx4', ...
          rows(X), columns(X), n_vectors);
  end

  ref = csvread('reference_states.csv', 1, 0);   % hidden reference, skip header
  max_abs_error = max(abs(X(:) - ref(:)));

  % --- hidden second model and stream: the agent never saw these values ---
  alt = model;
  alt.F  = [1 0 0.5 0; 0 1 0 0.5; 0 0 1 0; 0 0 0 1];   % half the time step
  alt.H  = [1 0 0.1 0; 0 1 0 0.1];
  alt.Q  = diag([0.02 0.02 0.005 0.005]);
  alt.R  = [0.5 0.1; 0.1 0.3];
  alt.x0 = [3; -2; 0.4; 0.25];
  alt.P0 = diag([5 5 2 2]);
  Z2 = [Z(1:600, 2), -Z(1:600, 1)] + [3, -2];
  ref2 = ref_cvt_filter(Z2, alt);
  try
    X2 = kalman_update(Z2, alt);
    if isequal(size(X2), size(ref2)) && all(isfinite(X2(:)))
      hidden_model_error = max(abs(X2(:) - ref2(:)));
    else
      hidden_model_error = BAD;
    end
  catch err2
    fprintf(2, 'kalman_update failed on the hidden model: %s\n', err2.message);
    hidden_model_error = BAD;
  end

  % --- the agent's own test, run against the reference and against a mutant ---
  test_present = double(exist(fullfile(pwd, 'test_kalman_update.m'), 'file') == 2);
  test_passes_reference = 0;
  test_catches_mutant = 0;
  if test_present
    st_ref = run_agent_test(pwd, '_agent_test_ref', 'ref_cvt_filter');
    st_mut = run_agent_test(pwd, '_agent_test_mut', 'mut_cvt_filter');
    test_passes_reference = double(st_ref == 0);
    test_catches_mutant   = double(st_mut ~= 0);
    printf('agent test: exit %d on reference, exit %d on mutant\n', st_ref, st_mut);
  end

  metrics = struct( ...
    'max_abs_error',         max_abs_error, ...
    'hidden_model_error',    hidden_model_error, ...
    'test_present',          test_present, ...
    'test_passes_reference', test_passes_reference, ...
    'test_catches_mutant',   test_catches_mutant, ...
    'runtime_ms',            runtime_ms, ...
    'n_vectors',             n_vectors);

  fid = fopen('metrics.json', 'w');
  fputs(fid, jsonencode(metrics));
  fclose(fid);

  printf('max_abs_error=%.3g  hidden_model_error=%.3g  runtime=%.1f ms  N=%d\n', ...
         max_abs_error, hidden_model_error, runtime_ms, n_vectors);
  exit(0);
catch err
  fprintf(2, 'run_tests failed: %s\n', err.message);
  exit(1);
end
