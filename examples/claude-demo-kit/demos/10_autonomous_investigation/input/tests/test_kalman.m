% test_kalman.m  Tests for kalman_update (CVT-EST-001 R1-R5).
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

fprintf('test_kalman: %d/%d checks passed\n', n, 4);
