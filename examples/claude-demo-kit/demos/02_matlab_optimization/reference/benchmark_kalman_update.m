% benchmark_kalman_update.m: time kalman_update vs kalman_update_fast on the
% sample stream and check they agree. Run: octave-cli benchmark_kalman_update.m
1;

function model = load_model(path)
  m = jsondecode(fileread(path));
  model = struct('F', m.F, 'Q', m.Q, 'H', m.H, 'R', m.R, 'x0', m.x0(:), 'P0', m.P0);
end

model = load_model('model.json');
Z = csvread('test_vectors.csv', 1, 0);   % skip header row
N = rows(Z);

t = tic; X_orig = kalman_update(Z, model); t_orig = toc(t);

reps = 20;
t_fast = zeros(reps, 1);
for r = 1:reps
  t = tic; X_fast = kalman_update_fast(Z, model); t_fast(r) = toc(t);
end
t_fast = median(t_fast);

err = max(abs(X_orig(:) - X_fast(:)));
printf('vectors        %d\n', N);
printf('original       %.1f ms\n', 1000 * t_orig);
printf('optimized      %.2f ms (median of %d)\n', 1000 * t_fast, reps);
printf('speedup        %.1fx\n', t_orig / t_fast);
printf('max abs error  %.3g\n', err);
if ~(isequal(size(X_fast), size(X_orig)) && err < 1e-9)
  error('benchmark:mismatch', 'optimized output differs from original');
end
