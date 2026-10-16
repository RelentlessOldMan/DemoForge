function make_reference()
% MAKE_REFERENCE  Run kalman_update.m on every case in cases/ and write the
% posterior estimates to cases/<name>/ref.csv at full double precision.
% Also writes reference_output.csv for test_vectors.csv.
% Works in MATLAB (R2016b+) and GNU Octave (7+).
%
%   Each case directory holds model.json (F, Q, H, R, x0, P0) and z.csv
%   (one measurement per row, no header).

d = dir('cases');
d = d([d.isdir] & ~startsWith({d.name}, '.'));

for i = 1:numel(d)
  cdir = fullfile('cases', d(i).name);
  model = load_model(fullfile(cdir, 'model.json'));
  Z = dlmread(fullfile(cdir, 'z.csv'), ',');
  X = kalman_update(Z, model);
  write_csv(fullfile(cdir, 'ref.csv'), X);
  fprintf('%-32s N=%6d n=%d m=%d\n', d(i).name, size(Z, 1), numel(model.x0), size(model.H, 1));
end

% Original single-file reference, kept for continuity.
model = load_model('model.json');
X = kalman_update(dlmread('test_vectors.csv', ',', 1, 0), model);
write_csv('reference_output.csv', X);
end


function model = load_model(path)
  model = jsondecode(fileread(path));
  n = numel(model.x0);
  model.x0 = reshape(model.x0, n, 1);
  % jsondecode collapses [[a]] to a scalar and [[a, b]] to a row; restore shapes.
  model.F  = reshape(model.F,  n, n);
  model.Q  = reshape(model.Q,  n, n);
  model.P0 = reshape(model.P0, n, n);
  model.H  = reshape(model.H, [], n);
  m = size(model.H, 1);
  model.R  = reshape(model.R,  m, m);
end

function write_csv(path, X)
  fid = fopen(path, 'w');
  fmt = [strjoin(repmat({'%.17g'}, 1, size(X, 2)), ','), '\n'];
  fprintf(fid, fmt, X');
  fclose(fid);
end
