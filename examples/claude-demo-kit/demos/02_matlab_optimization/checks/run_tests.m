% run_tests.m: DemoForge verification harness for the MATLAB optimization demo.
%
% Runs in the verify work dir: the staged inputs (kalman_update.m,
% model.json, test_vectors.csv), the agent's kalman_update_fast.m, and this
% checks/ folder copied on top. Because checks/ is copied last, the
% kalman_update.m here (a byte copy of input/kalman_update.m) replaces any
% version the agent may have edited, so the baseline is always the original.
%
% Equivalence (fast vs. original), on three cases:
%   A  public stream (test_vectors.csv, 1500)  + model.json
%   B  hidden stream (hidden_stream.csv, 4500) + model.json
%   C  hidden stream, first 1500 rows          + hidden model_alt.json
%      (other dt, Q, correlated R, nonzero x0, other P0: catches hard-coding)
%
% Speed is measured here, never taken from the agent: the original's runtime
% on case B against the median of 5 fast runs on case-B-sized streams, each
% offset by a different constant so no run sees an input it has seen before.
% Each timed output is checked against the harness's own vectorized filter
% (cvt_trusted_update.m, itself checked against the original on case B).
%
% Writes metrics.json. Exits non-zero if it cannot produce a result.

1;  % script file: helper functions first, Octave needs them defined before use

function model = load_model(path)
  m = jsondecode(fileread(path));
  model.F  = double(m.F);
  model.Q  = double(m.Q);
  model.H  = double(m.H);
  model.R  = double(m.R);
  model.x0 = double(m.x0(:));
  model.P0 = double(m.P0);
end

function X = call_fast(Z, model)
  X = kalman_update_fast(Z, model);
  if ~isequal(size(X), [rows(Z), numel(model.x0)])
    error('run_tests:shape', 'kalman_update_fast returned %s, expected %dx%d', ...
          mat2str(size(X)), rows(Z), numel(model.x0));
  end
end

function e = max_err(A, B)
  d = abs(A(:) - B(:));
  if any(~isfinite(d))
    e = Inf;
  else
    e = max(d);
  end
end

try
  if exist('kalman_update_fast', 'file') ~= 2
    error('run_tests:missing', 'kalman_update_fast.m not found (produce it)');
  end

  model     = load_model('model.json');
  model_alt = load_model('model_alt.json');
  Za = csvread('test_vectors.csv', 1, 0);
  Zb = csvread('hidden_stream.csv', 1, 0);
  Zc = Zb(1:1500, :);

  % --- A: public case ---
  Xa_orig = kalman_update(Za, model);
  Xa_fast = call_fast(Za, model);
  err_a = max_err(Xa_orig, Xa_fast);

  % --- C: hidden model ---
  Xc_orig = kalman_update(Zc, model_alt);
  Xc_fast = call_fast(Zc, model_alt);
  err_c = max_err(Xc_orig, Xc_fast);

  % --- B: long hidden stream, also the baseline timing ---
  t = tic;
  Xb_orig = kalman_update(Zb, model);
  t_orig = toc(t);
  Xb_fast = call_fast(Zb, model);
  err_b = max_err(Xb_orig, Xb_fast);

  trusted_err = max_err(Xb_orig, cvt_trusted_update(Zb, model));
  if trusted_err > 1e-9
    error('run_tests:trusted', 'harness reference disagrees with original (%g)', trusted_err);
  end

  % --- timed fast runs on fresh inputs ---
  reps = 5;
  t_fast = zeros(reps, 1);
  timed_err = 0;
  for r = 1:reps
    Zr = Zb + 0.37 * r;
    t = tic;
    Xr = call_fast(Zr, model);
    t_fast(r) = toc(t);
    timed_err = max(timed_err, max_err(cvt_trusted_update(Zr, model), Xr));
  end
  t_fast = median(t_fast);

  max_abs_error = max([err_a, err_b, err_c]);
  speedup = t_orig / t_fast;

  metrics = struct( ...
    'original_runtime_ms',  1000 * t_orig, ...
    'optimized_runtime_ms', 1000 * t_fast, ...
    'speedup',              speedup, ...
    'max_abs_error',        max_abs_error, ...
    'max_abs_error_public', err_a, ...
    'max_abs_error_hidden_stream', err_b, ...
    'max_abs_error_hidden_model',  err_c, ...
    'timed_runs_max_abs_error',    timed_err, ...
    'n_vectors',            rows(Za), ...
    'n_vectors_timed',      rows(Zb));

  fid = fopen('metrics.json', 'w');
  fputs(fid, jsonencode(metrics));
  fclose(fid);

  printf(['original=%.1f ms  optimized=%.2f ms  speedup=%.1fx  ' ...
          'err(public/stream/model/timed)=%.3g/%.3g/%.3g/%.3g\n'], ...
         1000 * t_orig, 1000 * t_fast, speedup, err_a, err_b, err_c, timed_err);
  exit(0);
catch err
  fprintf(2, 'run_tests failed: %s\n', err.message);
  exit(1);
end
