% test_kalman.m  Verification test for kalman_update against CVT-EST-001 Rev B.
%
% Run from a directory containing kalman_update.m, model.json and test_vectors.csv:
%   octave-cli test_kalman.m
%
% Exits with status 1 if any check fails, 0 if all pass.

1;  % mark this file as a script so the local functions below are allowed

function model = load_model(path)
  % Read the §2.3 constants from model.json (spec forbids hard-coding them).
  m = jsondecode(fileread(path));
  model.F  = double(m.F);
  model.Q  = double(m.Q);
  model.H  = double(m.H);
  model.R  = double(m.R);
  model.x0 = double(m.x0(:));
  model.P0 = double(m.P0);
end

function X = reference_kf(Z, model)
  % Independent transcription of the CVT-EST-001 §4 recursion.
  x = model.x0(:);
  P = model.P0;
  I = eye(numel(x));
  X = zeros(size(Z, 1), numel(x));
  for k = 1:size(Z, 1)
    x = model.F * x;
    P = model.F * P * model.F' + model.Q;
    y = Z(k, :)' - model.H * x;
    S = model.H * P * model.H' + model.R;
    K = (P * model.H') / S;
    x = x + K * y;
    P = (I - K * model.H) * P;
    X(k, :) = x';
  end
end

function [ok, msg] = matches_reference(Z, model, tol)
  X = kalman_update(Z, model);
  Xr = reference_kf(Z, model);
  if ~isequal(size(X), size(Xr))
    ok = false;
    msg = sprintf('size %s, expected %s', mat2str(size(X)), mat2str(size(Xr)));
    return;
  end
  err = max(abs(X(:) - Xr(:)));
  if isempty(err), err = 0; end
  ok = err < tol;
  msg = sprintf('max abs error %.3g (tol %.0g)', err, tol);
end

function [ok, msg] = prints_nothing(Z, model)
  out = evalc('kalman_update(Z, model);');
  ok = isempty(out);
  msg = '';
  if ~ok, msg = sprintf('printed %d chars', numel(out)); end
end

% ---------------------------------------------------------------------------

TOL = 1e-6;                                    % §6 acceptance tolerance
model = load_model('model.json');
Z = csvread('test_vectors.csv', 1, 0);         % skip header row
N = size(Z, 1);

checks = {};   % rows: {requirement, name, passed, detail}
function c = add_check(c, req, name, fn)
  try
    [ok, detail] = fn();
  catch err
    ok = false;
    detail = ['error: ' err.message];
  end
  c(end + 1, :) = {req, name, ok, detail};
end

% Sanity on the inputs themselves.
checks = add_check(checks, 'input', 'test_vectors.csv is N x 2 with N > 0', ...
  @() deal(N > 0 && size(Z, 2) == 2, sprintf('%d x %d', size(Z, 1), size(Z, 2))));

% R1: signature X = kalman_update(Z, model).
checks = add_check(checks, 'R1', 'kalman_update takes 2 inputs, returns 1 output', ...
  @() deal(nargin('kalman_update') == 2 && nargout('kalman_update') == 1, ...
           sprintf('nargin=%d nargout=%d', nargin('kalman_update'), nargout('kalman_update'))));

% R2: N x 4 output, one row per measurement, in input order.
checks = add_check(checks, 'R2', 'output is N x 4 on test_vectors.csv', ...
  @() deal(isequal(size(kalman_update(Z, model)), [N 4]), ...
           mat2str(size(kalman_update(Z, model)))));
checks = add_check(checks, 'R2', 'single measurement gives 1 x 4', ...
  @() deal(isequal(size(kalman_update(Z(1, :), model)), [1 4]), ''));
checks = add_check(checks, 'R2', 'row k depends only on z_1..z_k (input order / causality)', ...
  @() deal(max(max(abs(kalman_update(Z(1:100, :), model) - ...
                       kalman_update(Z(1:200, :), model)(1:100, :)))) < TOL, ''));

% R3 / §6: reproduce the §4 recursion with model.json constants.
checks = add_check(checks, 'R3', 'matches §4 recursion on test_vectors.csv + model.json', ...
  @() matches_reference(Z, model, TOL));

% R3: constants must come from `model`, not be hard-coded. Change each one in
% turn; the shipped model.json values alone cannot reveal hard-coding.
alt.x0 = [2; -1; 0.5; 0.3];
alt.P0 = diag([4 4 2 2]);
alt.F  = [1 0 0.5 0; 0 1 0 0.5; 0 0 1 0; 0 0 0 1];
alt.Q  = diag([0.02 0.03 0.005 0.004]);
alt.R  = [0.5 0.1; 0.1 0.3];
alt.H  = [1 0 0.1 0; 0 1 0 0.1];
fields = fieldnames(alt);
for i = 1:numel(fields)
  m2 = model;
  m2.(fields{i}) = alt.(fields{i});
  checks = add_check(checks, 'R3', sprintf('uses model.%s (perturbed value)', fields{i}), ...
    @() matches_reference(Z, m2, TOL));
end
checks = add_check(checks, 'R3', 'all constants perturbed together', ...
  @() matches_reference(Z, setfield(setfield(setfield(setfield(setfield(setfield( ...
        model, 'x0', alt.x0), 'P0', alt.P0), 'F', alt.F), 'Q', alt.Q), 'R', alt.R), 'H', alt.H), TOL));

% R3: posterior position tracks the measurements (no divergence).
checks = add_check(checks, 'R3', 'position estimate tracks measurements', ...
  @() deal(max(max(abs(kalman_update(Z, model)(:, 1:2) - Z))) < 5, ''));

% R4: determinism.
checks = add_check(checks, 'R4', 'repeated calls give identical output', ...
  @() deal(isequal(kalman_update(Z, model), kalman_update(Z, model)), ''));

% §3: pure function — no printing.
checks = add_check(checks, '§3', 'prints nothing', ...
  @() prints_nothing(Z, model));

% Report.
nfail = 0;
for i = 1:size(checks, 1)
  if checks{i, 3}, tag = 'PASS'; else, tag = 'FAIL'; nfail = nfail + 1; end
  fprintf('[%s] %-5s %s', tag, checks{i, 1}, checks{i, 2});
  if ~isempty(checks{i, 4}), fprintf('  (%s)', checks{i, 4}); end
  fprintf('\n');
end
fprintf('\n%d of %d checks passed\n', size(checks, 1) - nfail, size(checks, 1));
if nfail > 0
  exit(1);
end
exit(0);
