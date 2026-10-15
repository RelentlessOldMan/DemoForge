function model = cvt_model(mode, config_file)
  % CVT_MODEL  Build the estimator model for a measurement mode from configuration.
  %
  %   model = cvt_model()              active_mode from config/estimator_config.json
  %   model = cvt_model(mode)          'planar' or 'doppler'
  %   model = cvt_model(mode, config_file)
  %
  % Returns the struct kalman_update expects: F, Q, x0, P0 from the model file; H and
  % R from the mode entry when the mode defines them, otherwise from the model file;
  % and, when the gate is enabled, gamma, the mode's gate threshold.

  root = fileparts(fileparts(mfilename('fullpath')));
  if nargin < 2 || isempty(config_file)
    config_file = fullfile(root, 'config', 'estimator_config.json');
  end
  cfg = jsondecode(fileread(config_file));
  if nargin < 1 || isempty(mode)
    mode = cfg.active_mode;
  end
  if ~isfield(cfg.modes, mode)
    error('cvt_model:mode', 'unknown measurement mode "%s"', mode);
  end
  md = cfg.modes.(mode);

  base = jsondecode(fileread(fullfile(root, cfg.model_file)));
  model.F  = base.F;
  model.Q  = base.Q;
  model.H  = base.H;
  model.R  = base.R;
  model.x0 = base.x0(:);
  model.P0 = base.P0;
  if isfield(md, 'H')
    model.H = md.H;
    model.R = md.R;
  end
  if size(model.H, 1) ~= md.measurement_dim
    error('cvt_model:dim', 'mode "%s": H has %d rows, measurement_dim is %d', ...
          mode, size(model.H, 1), md.measurement_dim);
  end

  if cfg.gate.enabled
    model.gamma = cfg.gate.gamma.(mode);
  end
end
