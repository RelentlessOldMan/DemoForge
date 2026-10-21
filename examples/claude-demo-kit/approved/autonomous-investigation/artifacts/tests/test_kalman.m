% test_kalman.m  Tests for kalman_update (CVT-EST-001 R1-R6), ungated and as configured.
%
% Run from the repository root:  octave --no-gui tests/test_kalman.m

addpath(fullfile(fileparts(mfilename('fullpath')), '..', 'src'));

model.F  = [1 0 1 0; 0 1 0 1; 0 0 1 0; 0 0 0 1];
model.Q  = 0.01 * eye(4);
model.H  = [1 0 0 0; 0 1 0 0];
model.R  = 0.25 * eye(2);
model.x0 = [0; 0; 0; 0];
model.P0 = eye(4);

% A deterministic 200-step track: constant velocity (0.5, -0.2) plus bounded noise.
k = (1:200)';
truth = [0.5 * k, -0.2 * k, 0.5 * ones(200, 1), -0.2 * ones(200, 1)];
noise = 0.3 * [sin(1.7 * k), cos(2.3 * k), sin(0.9 * k + 1), cos(1.3 * k + 2)];
n = 0;

% T1  output is N-by-4, one row per measurement (R1, R2)
Z = truth(:, 1:2) + noise(:, 1:2);
X = kalman_update(Z, model);
assert(isequal(size(X), [size(Z, 1), 4]), 'T1 shape');
n = n + 1;

% T2  deterministic (R4)
assert(isequal(X, kalman_update(Z, model)), 'T2 determinism');
n = n + 1;

% T3  the estimate tracks the truth once converged (R3)
err = abs(X(50:end, 1:2) - truth(50:end, 1:2));
assert(max(err(:)) < 0.5, 'T3 tracking');
n = n + 1;

% T4  position-and-velocity measurements (H = I4): shape and tracking (R1-R3)
md = model;
md.H = eye(4);
md.R = diag([0.25 0.25 0.04 0.04]);
Zd = truth + noise .* [1 1 0.4 0.4];
Xd = kalman_update(Zd, md);
errd = abs(Xd(50:end, :) - truth(50:end, :));
assert(isequal(size(Xd), [200, 4]) && max(errd(:)) < 0.5, 'T4 four-component measurement');
n = n + 1;

% T5, T6  each mode as configured, gate on (cvt_model; CVT-SRS-003 §7.3.3).
%     A one-step stream from x0, P0 is placed at an exact NIS: z = H x + L u sqrt(q),
%     where S = L L' is the step-1 innovation covariance, so d2 = q. With q at
%     1000 evenly spaced chi-squared(m) quantiles, a gate at the configured 99 %
%     threshold rejects 1 % of them (a threshold of 5.991 rejects 20 % at m = 4 and
%     5 % at m = 2). A q between 5.991 and gamma must be applied.
modes = {'doppler', 13.277; 'planar', 9.210};
for t = 1:2
  mg = cvt_model(modes{t, 1});
  assert(isfield(mg, 'gamma') && mg.gamma == modes{t, 2}, sprintf('T%d gamma from config', t + 4));
  m = size(mg.H, 1);
  xp = mg.F * mg.x0;
  S = mg.H * (mg.F * mg.P0 * mg.F' + mg.Q) * mg.H' + mg.R;
  L = chol(S, 'lower');
  u = ones(m, 1) / sqrt(m);
  q = 2 * gammaincinv(((1:1000) - 0.5) / 1000, m / 2);
  rej = false(size(q));
  for i = 1:numel(q)
    [~, rej(i)] = kalman_update((mg.H * xp + L * u * sqrt(q(i)))', mg);
  end
  assert(abs(mean(rej) - 0.01) <= 0.002, sprintf('T%d %s rejection rate %.3f, expected 0.01', ...
         t + 4, modes{t, 1}, mean(rej)));
  [X1, r1] = kalman_update((mg.H * xp + L * u * sqrt((5.991 + mg.gamma) / 2))', mg);
  assert(~r1 && norm(X1' - xp) > 0, sprintf('T%d %s admits 5.991 < d2 <= gamma', t + 4, modes{t, 1}));
  n = n + 1;
end

fprintf('test_kalman: %d/%d checks passed\n', n, 6);
