function test_kalman_update()
% TEST_KALMAN_UPDATE  Acceptance test for kalman_update (CVT-EST-001 Rev B, R5).
%
%   Run with:  octave --eval test_kalman_update
%   Raises an error (non-zero exit) on any failure.

  here = fileparts(mfilename('fullpath'));
  tol  = 1e-6;   % Section 6 acceptance threshold

  % --- Load model constants and recorded measurement stream -----------------
  model = load_model(fullfile(here, 'model.json'));
  Z = load_measurements(fullfile(here, 'test_vectors.csv'));
  N = size(Z, 1);
  assert(N > 0, 'test_vectors.csv contains no measurements');

  % The loaded model must match the released model.json constants exactly;
  % a transposed or mis-parsed load fails here rather than passing silently.
  assert(isequal(model.F, [1 0 1 0; 0 1 0 1; 0 0 1 0; 0 0 0 1]), ...
         'model.json: F does not match the constant-velocity model');
  assert(isequal(model.Q, 0.01 * eye(4)), 'model.json: Q does not match 0.01*I');
  assert(isequal(model.H, [1 0 0 0; 0 1 0 0]), ...
         'model.json: H does not match the position-only measurement model');
  assert(isequal(model.R, 0.25 * eye(2)), 'model.json: R does not match 0.25*I');
  assert(isequal(model.x0, zeros(4, 1)), 'model.json: x0 does not match zeros(4,1)');
  assert(isequal(model.P0, eye(4)), 'model.json: P0 does not match I');

  % --- R1: signature X = kalman_update(Z, model) -----------------------------
  assert(nargin('kalman_update') == 2, 'R1: kalman_update must take 2 inputs');
  assert(nargout('kalman_update') == 1, 'R1: kalman_update must return 1 output');

  X = kalman_update(Z, model);

  % --- R2: N x 4 output, one row per measurement, in input order -------------
  assert(isnumeric(X) && isreal(X), 'R2: output must be a real numeric matrix');
  assert(isequal(size(X), [N 4]), ...
         'R2: expected %dx4 output, got %dx%d', N, size(X, 1), size(X, 2));
  assert(all(isfinite(X(:))), 'R2: output contains non-finite values');

  % Input order: running on a prefix must reproduce the leading rows exactly
  % (a causal filter's k-th row depends only on z_1..z_k).
  M = min(N, 100);
  Xp = kalman_update(Z(1:M, :), model);
  assert(isequal(Xp, X(1:M, :)), 'R2: prefix run does not match leading rows');

  % Empty input yields an empty 0x4 result.
  X0 = kalman_update(zeros(0, 2), model);
  assert(isequal(size(X0), [0 4]), 'R2: empty input must give 0x4 output');

  % --- R3 / Section 6: agreement with an independent reference recursion ----
  Xref = reference_filter(Z, model);
  err = max(abs(X(:) - Xref(:)));
  assert(err < tol, 'R3: max abs state error %.3g exceeds %.0g', err, tol);

  % Sanity check against a hand-computed first step with the model.json values
  % (P0 = I, Q = 0.01 I, R = 0.25 I, x0 = 0): predicted position variance is
  % 2.01 and the position/velocity cross-covariance is 1, with S = 2.26, so
  % the position gain is 2.01/2.26 and the velocity gain is 1/2.26.
  x1 = [2.01/2.26 * Z(1, :), 1/2.26 * Z(1, :)];
  assert(max(abs(X(1, :) - x1)) < 1e-12, 'R3: first-step estimate is wrong');

  % The constant-velocity filter should track the stream: position estimates
  % must sit closer to the trend than the raw measurements' noise level.
  pos_resid = X(:, 1:2) - Z;
  assert(sqrt(mean(pos_resid(:).^2)) < 3 * sqrt(max(diag(model.R))), ...
         'R3: position estimates diverge from the measurements');

  % --- R4: determinism -------------------------------------------------------
  X2 = kalman_update(Z, model);
  assert(isequal(X, X2), 'R4: repeated call produced different output');

  % Must not mutate caller's inputs (pass-by-value, but check anyway).
  assert(isequal(model, load_model(fullfile(here, 'model.json'))), ...
         'R4: model struct was modified');

  fprintf('test_kalman_update: PASS (N = %d, max abs error vs reference = %.3g)\n', ...
         N, err);
end

% -----------------------------------------------------------------------------
function model = load_model(path)
  txt = fileread(path);
  m = jsondecode(txt);
  model.F  = reshape_check(m.F,  [4 4], 'F');
  model.Q  = reshape_check(m.Q,  [4 4], 'Q');
  model.H  = reshape_check(m.H,  [2 4], 'H');
  model.R  = reshape_check(m.R,  [2 2], 'R');
  model.x0 = reshape_check(m.x0(:), [4 1], 'x0');
  model.P0 = reshape_check(m.P0, [4 4], 'P0');
end

function A = reshape_check(A, sz, name)
  A = double(A);
  assert(isequal(size(A), sz), 'model.json: %s has size %s, expected %s', ...
         name, mat2str(size(A)), mat2str(sz));
end

function Z = load_measurements(path)
  Z = dlmread(path, ',', 1, 0);
  assert(size(Z, 2) == 2, 'test_vectors.csv must have 2 columns');
  assert(all(isfinite(Z(:))), 'test_vectors.csv contains non-finite values');
end

% Reference: the same Section 4 matrix recursion, written separately. It differs
% from kalman_update only in form: the gain uses a left solve (K' = S' \ (P H')')
% and the covariance update is P = Pp - K (H Pp).
function Xref = reference_filter(Z, model)
  n = numel(model.x0);
  x = model.x0(:);
  P = model.P0;
  Xref = zeros(size(Z, 1), n);
  for k = 1:size(Z, 1)
    xp = model.F * x;
    Pp = model.F * P * model.F.' + model.Q;
    S  = model.H * Pp * model.H.' + model.R;
    PHt = Pp * model.H.';
    K  = (S.' \ PHt.').';
    x  = xp + K * (Z(k, :).' - model.H * xp);
    P  = Pp - K * (model.H * Pp);
    Xref(k, :) = x.';
  end
end
