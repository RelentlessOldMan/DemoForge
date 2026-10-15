% gen_reference.m — produce the authoritative MATLAB-side outputs of
% input/kalman_update.m that the Python-port demo verifies the agent's port against:
%
%   reference_states.csv      model.json over test_vectors.csv (the staged case)
%   reference_states_alt.csv  the hidden model_alt.json (other F, Q, R, x0, P0) over a
%                             hidden stream derived from test_vectors.csv: rows 1..600,
%                             axes swapped, y negated, offset by (3, -2). The agent never
%                             sees this case; it catches ports that hard-code constants.
%
% Deterministic: a pure function of the committed files.
%
% Regenerate (writes both files next to this script, in checks/):
%   octave-cli <demo>/checks/gen_reference.m
%
% reference_states.csv lives in checks/ (DemoForge-owned), NOT input/ — the agent
% must not see the expected output; it only gets the MATLAB source + the vectors.

1;  % script file: the helper below is defined before it is used

function write_states(outfile, X)
  fid = fopen(outfile, 'w');
  fprintf(fid, 'x,y,vx,vy\n');
  fclose(fid);
  dlmwrite(outfile, X, '-append', 'precision', 17);
  printf('wrote %s (%d x %d)\n', outfile, rows(X), columns(X));
end

here  = fileparts(mfilename('fullpath'));
indir = fullfile(here, '..', 'input');
addpath(indir);

m = jsondecode(fileread(fullfile(indir, 'model.json')));
model.F  = m.F;  model.Q = m.Q;  model.H = m.H;  model.R = m.R;
model.x0 = m.x0(:);              % ensure column vector
model.P0 = m.P0;

Z = csvread(fullfile(indir, 'test_vectors.csv'), 1, 0);   % skip header
write_states(fullfile(here, 'reference_states.csv'), kalman_update(Z, model));

a = jsondecode(fileread(fullfile(here, 'model_alt.json')));
alt.F  = a.F;  alt.Q = a.Q;  alt.H = a.H;  alt.R = a.R;
alt.x0 = a.x0(:);
alt.P0 = a.P0;
Z2 = [Z(1:600, 2), -Z(1:600, 1)] + [3, -2];
write_states(fullfile(here, 'reference_states_alt.csv'), kalman_update(Z2, alt));
