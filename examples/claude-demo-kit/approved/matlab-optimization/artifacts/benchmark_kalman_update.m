% BENCHMARK_KALMAN_UPDATE  Equivalence check and benchmark of kalman_update
% (v2.1.0) against kalman_update_fast (v2.2.0).
%
% Runs in MATLAB or GNU Octave from this directory. Errors unless every output
% is bit-identical to the original's (which also implies the 1e-9 maximum
% absolute error requirement). Checks the sample stream, random models, and
% two long production-length streams, then times both routines on the sample.

tol   = 1e-9;
nreps = 5;                                   % timed repetitions per routine

here  = fileparts(mfilename('fullpath'));
if isempty(here), here = pwd; end
Z     = dlmread(fullfile(here, 'test_vectors.csv'), ',', 1, 0);   % skip header
model = jsondecode(fileread(fullfile(here, 'model.json')));

% Bitwise equality (also distinguishes +0/-0 and compares NaN payloads).
bitsame = @(A, B) isequal(size(A), size(B)) && ...
          isequal(typecast(A(:), 'uint64'), typecast(B(:), 'uint64'));

N = size(Z, 1);
fprintf('Vectors: %d   (state n = %d, measurement m = %d)\n', ...
        N, numel(model.x0), size(model.H, 1));

% --- equivalence on the sample ---------------------------------------------
X_ref  = kalman_update(Z, model);
X_fast = kalman_update_fast(Z, model);
assert(isequal(size(X_ref), size(X_fast)), 'Output sizes differ.');
max_err = max(abs(X_ref(:) - X_fast(:)));
all_bitsame = bitsame(X_ref, X_fast);
fprintf('Sample:         max abs error %.3e, max |x| %.3e, bit-identical %d\n', ...
        max_err, max(abs(X_ref(:))), bitsame(X_ref, X_fast));
% Same, with the periodic-gain shortcut disabled (every step computed in full).
X_full = kalman_update_fast(Z, model, false);
max_err = max(max_err, max(abs(X_ref(:) - X_full(:))));
all_bitsame = all_bitsame && bitsame(X_ref, X_full);
fprintf('Sample, no gain-cycle shortcut: max abs error %.3e, bit-identical %d\n', ...
        max(abs(X_ref(:) - X_full(:))), bitsame(X_ref, X_full));

% --- equivalence on other models the original supports (any n, m = 2) ------
rand('seed', 1); randn('seed', 1);           % reproducible in MATLAB and Octave
max_err_other = 0;
for n = [2 3 4 6]
  A = randn(n);  B = randn(2);  C = randn(n);
  m2.F  = eye(n) + 0.1 * randn(n);
  m2.Q  = 0.01 * (A * A') + 1e-3 * eye(n);
  m2.H  = randn(2, n);
  m2.R  = 0.1 * (B * B') + 0.05 * eye(2);
  m2.x0 = randn(n, 1);
  m2.P0 = C * C' + eye(n);
  Zr = randn(1500, 2);
  Xr = kalman_update(Zr, m2);
  Xf = kalman_update_fast(Zr, m2);
  max_err_other = max(max_err_other, max(abs(Xr(:) - Xf(:))));
  all_bitsame = all_bitsame && bitsame(Xr, Xf);
  fprintf('Random n = %d:   max abs error %.3e, bit-identical %d\n', ...
          n, max(abs(Xr(:) - Xf(:))), bitsame(Xr, Xf));
end

% --- equivalence on long, production-length streams ------------------------
% The tolerance is absolute and positions grow along the stream, so check
% streams simulated from the CV model that reach much larger |x| than the
% sample. Slow: the original routine needs several minutes per stream.
% Set run_long = false to skip.
run_long = true;
N_long   = 100000;
max_err_long = 0;
if run_long
  % Stream 1: the production model.json (dt = 1).
  % Stream 2: CV model with dt = 0.1, discrete white-noise-acceleration Q,
  %           correlated (non-diagonal) R, nonzero x0.
  dt = 0.1; q = 0.5; I2 = eye(2);
  cv.F  = [I2, dt * I2; zeros(2), I2];
  cv.Q  = q * [dt^3 / 3 * I2, dt^2 / 2 * I2; dt^2 / 2 * I2, dt * I2];
  cv.H  = [I2, zeros(2)];
  cv.R  = [0.25, 0.10; 0.10, 0.16];
  cv.x0 = [100; -50; 0; 0];
  cv.P0 = diag([10, 10, 100, 100]);
  streams = {model, [1; 0.5]; cv, [30; -20]};   % {model, initial true velocity}
  names   = {'model.json, dt = 1', 'dt = 0.1, non-diagonal R'};

  for s = 1:size(streams, 1)
    ms = streams{s, 1};
    % Simulate the true trajectory and noisy measurements from the model.
    randn('seed', 100 + s);
    LQ = chol(ms.Q + 1e-15 * eye(4), 'lower');
    LR = chol(ms.R, 'lower');
    xt = [ms.x0(1:2); streams{s, 2}];
    Zl = zeros(N_long, 2);
    for k = 1:N_long
      xt = ms.F * xt + LQ * randn(4, 1);
      Zl(k, :) = (ms.H * xt + LR * randn(2, 1)).';
    end

    t0 = tic; Xr = kalman_update(Zl, ms);      tr = toc(t0);
    t0 = tic; Xf = kalman_update_fast(Zl, ms); tf = toc(t0);
    e  = max(abs(Xr(:) - Xf(:)));
    max_err_long = max(max_err_long, e);
    all_bitsame = all_bitsame && bitsame(Xr, Xf);
    fprintf(['Long stream %d (%s): %d vectors\n' ...
             '    max abs error %.3e, bit-identical %d, max |x| %.3e ' ...
             '(position %.3e, velocity %.3e)\n' ...
             '    original %.1f s, optimized %.2f s, speedup %.0fx\n'], ...
            s, names{s}, N_long, e, bitsame(Xr, Xf), max(abs(Xr(:))), ...
            max(max(abs(Xr(:, 1:2)))), max(max(abs(Xr(:, 3:4)))), ...
            tr, tf, tr / tf);
  end
end

assert(max_err <= tol && max_err_other <= tol && max_err_long <= tol, ...
       'kalman_update_fast differs from kalman_update by more than %g', tol);
assert(all_bitsame, 'kalman_update_fast output is not bit-identical.');
fprintf('Equivalence: PASS (bit-identical on every check; tolerance %g)\n', tol);

% --- timing on the sample --------------------------------------------------
% Times the original, the optimized routine as shipped, and the optimized
% routine with the gain-cycle shortcut disabled. The last one is the speed of
% the exact-order arithmetic alone, i.e. what to expect on a model whose
% covariance never repeats. Runs are interleaved, and min/max are reported
% so that variance from machine load is visible.
t_ref  = zeros(nreps, 1);
t_fast = zeros(nreps, 1);
t_full = zeros(nreps, 1);
for r = 1:nreps
  t0 = tic; kalman_update(Z, model);             t_ref(r)  = toc(t0);
  t0 = tic; kalman_update_fast(Z, model);        t_fast(r) = toc(t0);
  t0 = tic; kalman_update_fast(Z, model, false); t_full(r) = toc(t0);
end
fprintf('Original:                    median %.4f s  (min %.4f, max %.4f) over %d runs\n', ...
        median(t_ref), min(t_ref), max(t_ref), nreps);
fprintf('Optimized (as shipped):      median %.4f s  (min %.4f, max %.4f) over %d runs\n', ...
        median(t_fast), min(t_fast), max(t_fast), nreps);
fprintf('Optimized, no cycle shortcut: median %.4f s  (min %.4f, max %.4f) over %d runs\n', ...
        median(t_full), min(t_full), max(t_full), nreps);
fprintf('Speedup (median), as shipped:          %.1fx\n', median(t_ref) / median(t_fast));
fprintf('Speedup (median), no cycle shortcut:   %.1fx\n', median(t_ref) / median(t_full));
