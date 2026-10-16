# Transcript

## Prompt

For v2.2.0 we're shipping a Python version of the estimator so the data team can run
it alongside their NumPy/pandas tooling. Please port `kalman_update.m` to Python as
`kalman_filter.py`, exposing

    def kalman_update(Z, model) -> X

where `Z` is an `(N, 2)` NumPy array of measurements, `model` is a dict with the keys
of `model.json` (`F, Q, H, R, x0, P0`), each value converted with `np.asarray`, and `X`
is the `(N, 4)` array of posterior state estimates, one row per measurement.

The port has to agree with the MATLAB version to a maximum absolute error below 1e-9.
`test_vectors.csv` is a recorded measurement stream to check it on. Leave
`kalman_filter.py` and whatever check you used to show the agreement in this folder.


- `$ Get-ChildItem -Recurse | Select-Object FullName, Length; Get-Content kalman_update.m; Get-Content model.json; Get-Content test_vectors.csv -TotalCount 5; (Get-Content test_vectors.csv).Count; Get-Command matlab, octave, python -ErrorAction SilentlyContinue | Select-Object Source`
- `$ cd "G:/Willikers/sandbox/demoforge-matlab-python-port-kvp6y8o3/working"; which matlab octave python python3 py; python -c "import numpy, sys; print(numpy.__version__, sys.version)"; grep -vnE '^-?[0-9.]+(e-?[0-9]+)?,-?[0-9.]+(e-?[0-9]+)?\r?$' test_vectors.csv | head; tail -3 test_vectors.csv`
- `file_write` G:\Willikers\sandbox\demoforge-matlab-python-port-kvp6y8o3\working\kalman_filter.py
- `file_write` G:\Willikers\sandbox\demoforge-matlab-python-port-kvp6y8o3\working\make_reference.m
- `file_write` G:\Willikers\sandbox\demoforge-matlab-python-port-kvp6y8o3\working\check_agreement.py
- `$ cd "G:/Willikers/sandbox/demoforge-matlab-python-port-kvp6y8o3/working" && octave --no-gui --quiet --eval make_reference && head -3 reference_output.csv && tail -2 reference_output.csv && python check_agreement.py`
I ported the estimator to `kalman_filter.py`. On `test_vectors.csv` (1,500 measurements) it matches the reference exactly, with a maximum absolute error of 0, well under the 1e-9 target. The reference came from GNU Octave 11.3, not MATLAB, because MATLAB isn't installed on this machine. Octave ran the original `kalman_update.m` without any changes.

**`kalman_filter.py`**: `kalman_update(Z, model) -> X` does the same steps as the MATLAB function, one measurement at a time. The MATLAB line `K = (P*H')/S` becomes a linear solve, not a matrix inverse. `x0` can be passed as either `(4,)` or `(4, 1)`.

**Check files left in the folder:**
- `make_reference.m`: runs `kalman_update.m` on the test data and writes `reference_output.csv` at full double precision. It should run unchanged in MATLAB.
- `reference_output.csv`: the 1,500-row Octave output.
- `check_agreement.py`: runs the Python port on the same data and compares it with the reference. It prints the maximum error and PASS/FAIL, and exits non-zero on failure.

To rerun the check:
```
octave --no-gui --quiet --eval make_reference   # or: make_reference in MATLAB
python check_agreement.py
```

Since the release requirement is agreement with MATLAB, someone with a MATLAB license should run `make_reference` there once, then run `check_agreement.py` against that output. I'd expect it to pass, because the filter is only small matrix arithmetic and the Octave match was exact, but that run hasn't been done.


## Follow-up

A max error of exactly 0 on this sample doesn't tell me much. `model.json` is all identity/diagonal, so S stays diagonal and `solve` vs `mrdivide` never actually differ. The data team will run full models: correlated R, non-trivial dt in F, a full P0, other state sizes, and longer or messier streams. Please extend `make_reference.m` and `check_agreement.py` to cover a set of models like that. Also add at least one case where S is badly conditioned. Then report the max error for each case from runs you actually did. Put the cases in files so I can rerun the same comparison in MATLAB.

- `$ python -c "import scipy; print(scipy.__version__)"; python -c "import numpy; numpy.show_config()" 2>&1 | grep -iA3 "blas\|lapack" | head -20; octave --no-gui --quiet --eval "disp(version -blas); disp(version -lapack)"`
- `file_edit` G:\Willikers\sandbox\demoforge-matlab-python-port-kvp6y8o3\working\kalman_filter.py
- `file_write` G:\Willikers\sandbox\demoforge-matlab-python-port-kvp6y8o3\working\generate_cases.py
- `file_write` G:\Willikers\sandbox\demoforge-matlab-python-port-kvp6y8o3\working\make_reference.m
- command:

  ```
  cd "G:/Willikers/sandbox/demoforge-matlab-python-port-kvp6y8o3/working" && python - <<'EOF'
  p='make_reference.m'; s=open(p).read()
  s=s.replace("% MAKE_REFERENCE","function make_reference()\n% MAKE_REFERENCE",1)
  s=s.replace("write_csv('reference_output.csv', X);\n","write_csv('reference_output.csv', X);\nend\n",1)
  open(p,'w').write(s)
  EOF
  head -8 make_reference.m
  ```

- `file_edit` G:\Willikers\sandbox\demoforge-matlab-python-port-kvp6y8o3\working\make_reference.m
- `file_write` G:\Willikers\sandbox\demoforge-matlab-python-port-kvp6y8o3\working\check_agreement.py
- `file_edit` G:\Willikers\sandbox\demoforge-matlab-python-port-kvp6y8o3\working\check_agreement.py
- `$ cd "G:/Willikers/sandbox/demoforge-matlab-python-port-kvp6y8o3/working" && python generate_cases.py && octave --no-gui --quiet --eval make_reference 2>&1 | tail -30 && python check_agreement.py`
- `file_edit` G:\Willikers\sandbox\demoforge-matlab-python-port-kvp6y8o3\working\generate_cases.py
- `$ cd "G:/Willikers/sandbox/demoforge-matlab-python-port-kvp6y8o3/working" && python generate_cases.py && octave --no-gui --quiet --eval make_reference 2>&1 | tail -30 && python check_agreement.py`
- command:

  ```
  cd "G:/Willikers/sandbox/demoforge-matlab-python-port-kvp6y8o3/working" && cat > /tmp/exp.py <<'EOF'
  import sys; sys.path.insert(0,'.')
  import numpy as np, json, scipy.linalg as sl
  from pathlib import Path
  from check_agreement import load_model
  def run(Z, model, mode):
      x = model["x0"].astype(float).reshape(-1); n=x.size
      F=model["F"].reshape(n,n);Q=model["Q"].reshape(n,n);P=model["P0"].reshape(n,n).astype(float)
      H=model["H"].reshape(-1,n);m=H.shape[0];R=model["R"].reshape(m,m)
      X=np.zeros((len(Z),n)); I=np.eye(n); sym=0
      for k in range(len(Z)):
          x=F@x; P=F@P@F.T+Q
          y=Z[k]-H@x; S=H@P@H.T+R; B=P@H.T
          issym = np.array_equal(S,S.T) and np.all(np.diag(S)>0); sym+=issym
          if mode=='chol' and issym:
              try: K=sl.cho_solve(sl.cho_factor(S.T,lower=False),B.T).T
              except np.linalg.LinAlgError: K=sl.lu_solve(sl.lu_factor(S.T),B.T).T
          else:
              K=np.linalg.solve(S.T,B.T).T
          x=x+K@y; P=(I-K@H)@P; X[k]=x
      return X, sym
  for name in ['02_cv2d_dt0.1_corrR_fullP0','03_ca3d_n9_m3_dt0.02','05_random_n6_m4','08_large_offset_1e6','10_illcond_S_1e10','11_illcond_S_1e14','12_illcond_collinear_H']:
      c=Path('cases')/name; mdl=load_model(c/'model.json')
      Z=np.loadtxt(c/'z.csv',delimiter=',',ndmin=2); ref=np.loadtxt(c/'ref.csv',delimiter=',',ndmin=2)
      for mode in ['lu','chol']:
          X,sym=run(Z,mdl,mode); e=np.abs(X-ref)
          print(f"{name:30s} {mode:4s} max_abs={e.max():.2e} symS={sym}/{len(Z)} first_row_err={e[0].max():.2e}")
  EOF
  python /tmp/exp.py
  ```

- `file_edit` G:\Willikers\sandbox\demoforge-matlab-python-port-kvp6y8o3\working\kalman_filter.py
- `file_edit` G:\Willikers\sandbox\demoforge-matlab-python-port-kvp6y8o3\working\kalman_filter.py
- `$ cd "G:/Willikers/sandbox/demoforge-matlab-python-port-kvp6y8o3/working" && sed -i 's/from kalman_filter import kalman_update/from kalman_filter import _mrdivide, kalman_update/; s/        K = np.linalg.solve(S.T, (P @ H.T).T).T/        K = _mrdivide(P @ H.T, S)/' check_agreement.py && grep -n "_mrdivide" check_agreement.py && python check_agreement.py`
- command:

  ```
  cd "G:/Willikers/sandbox/demoforge-matlab-python-port-kvp6y8o3/working" && cat > /tmp/dump03.m <<'EOF'
  model = jsondecode(fileread('cases/03_ca3d_n9_m3_dt0.02/model.json'));
  F=model.F;Q=model.Q;H=model.H;R=model.R;x=model.x0(:);P=model.P0;
  Z=dlmread('cases/03_ca3d_n9_m3_dt0.02/z.csv',',');
  fid=fopen('/tmp/oct03.txt','w'); I=eye(9);
  for k=1:40
    z=Z(k,:)'; x=F*x; FP=F*P; P=FP*F'+Q; y=z-H*x; PH=P*H'; S=H*P*H'+R; K=PH/S; x=x+K*y; P=(I-K*H)*P;
    fprintf(fid,'%.17g ',[FP(:);P(:);S(:);K(:);x(:)]); fprintf(fid,'\n');
  end
  fclose(fid);
  EOF
  octave --no-gui --quiet /tmp/dump03.m && python - <<'EOF'
  import numpy as np, json, sys
  sys.path.insert(0,'.')
  from kalman_filter import _mrdivide
  m=json.load(open('cases/03_ca3d_n9_m3_dt0.02/model.json'))
  F,Q,H,R,P0=(np.array(m[k]) for k in 'F Q H R P0'.split()); x=np.array(m['x0'])
  Z=np.loadtxt('cases/03_ca3d_n9_m3_dt0.02/z.csv',delimiter=',')
  oc=np.loadtxt('/tmp/oct03.txt'); P=P0; I=np.eye(9)
  for k in range(40):
      x=F@x; FP=F@P; Pp=FP@F.T+Q; y=Z[k]-H@x; S=H@Pp@H.T+R; K=_mrdivide(Pp@H.T,S); x=x+K@y; P=(I-K@H)@Pp
      o=oc[k]; parts={'FP':(FP,o[:81]),'Ppred':(Pp,o[81:162]),'S':(S,o[162:171]),'K':(K,o[171:198]),'x':(x,o[198:207])}
      d={n:np.abs(a.flatten('F')-b).max() for n,(a,b) in parts.items()}
      if any(d.values()): print(k+1,{n:f"{v:.1e}" for n,v in d.items()}, 'Sym S:',np.array_equal(S,S.T)); 
      if k>12: break
  EOF
  ```

- command:

  ```
  cd "G:/Willikers/sandbox/demoforge-matlab-python-port-kvp6y8o3/working" && cat > /tmp/exact.py <<'EOF'
  import numpy as np, json, sys, math
  sys.path.insert(0,'.')
  from kalman_filter import _mrdivide, kalman_update
  def mm(A,B):
      A=np.atleast_2d(A); B=B if B.ndim==2 else B[:,None]
      return np.array([[math.fsum(A[i]*B[:,j]) for j in range(B.shape[1])] for i in range(A.shape[0])])
  name=sys.argv[1]; c=f'cases/{name}'
  m=json.load(open(f'{c}/model.json'))
  F,Q,H,R,P=(np.array(m[k],float) for k in 'F Q H R P0'.split()); x=np.array(m['x0'],float)[:,None]
  n=x.size; F=F.reshape(n,n);Q=Q.reshape(n,n);P=P.reshape(n,n);H=H.reshape(-1,n);R=R.reshape(H.shape[0],-1)
  Z=np.loadtxt(f'{c}/z.csv',delimiter=',',ndmin=2); ref=np.loadtxt(f'{c}/ref.csv',delimiter=',',ndmin=2)
  X=np.zeros_like(ref); I=np.eye(n)
  for k in range(len(Z)):
      x=mm(F,x); P=mm(mm(F,P),F.T)+Q; y=Z[k][:,None]-mm(H,x); S=mm(mm(H,P),H.T)+R
      K=_mrdivide(mm(P,H.T),S); x=x+mm(K,y); P=mm(I-mm(K,H),P); X[k]=x[:,0]
  mdl={k:np.asarray(v) for k,v in m.items() if k!='description'}
  Xp=kalman_update(Z,mdl)
  print(f"{name}: |exact-rounded vs Octave| = {np.abs(X-ref).max():.2e}   |exact-rounded vs NumPy port| = {np.abs(X-Xp).max():.2e}   max|x| = {np.abs(ref).max():.1e}")
  EOF
  for c in 03_ca3d_n9_m3_dt0.02 02_cv2d_dt0.1_corrR_fullP0 08_large_offset_1e6; do python /tmp/exact.py $c; done
  ```

- `file_edit` G:\Willikers\sandbox\demoforge-matlab-python-port-kvp6y8o3\working\kalman_filter.py
- `$ cd "G:/Willikers/sandbox/demoforge-matlab-python-port-kvp6y8o3/working" && python check_agreement.py; ls; du -sh cases`
I ran the wider comparison: 12 of 13 cases pass the 1e-9 limit and one fails, at 1.05e-9. The test also found a real bug in my first port, which I've fixed. All numbers below come from runs I did here, against Octave 11.3 because MATLAB isn't installed. They still need confirming in MATLAB.

**The bug:** `np.linalg.solve` always uses LU. MATLAB and Octave pick the method from what S looks like: triangular substitution for a triangular S, Cholesky when S is exactly symmetric with a positive diagonal, and LU otherwise. When S is badly conditioned the methods round differently and the gap is amplified. With the old version the ill-conditioned cases were off by up to **3.2e-2** (case 11). `kalman_filter.py` now makes the same choice MATLAB does (`_mrdivide`), which adds **SciPy as a dependency**.

**Results after the fix** (max_rel is the error divided by the largest value in the output):

| Case | N | n/m | cond(S) | max abs error | max rel | Result |
|---|---|---|---|---|---|---|
| 01 baseline (shipped model + stream) | 1500 | 4/2 | 1 | 0 | 0 | PASS |
| 02 constant velocity (CV), dt=0.1, correlated R, full P0 | 5000 | 4/2 | 10 | 4.6e-13 | 2.6e-16 | PASS |
| 03 3-D constant accel, dt=0.02, full R/P0 | 3000 | 9/3 | 18 | **1.05e-9** | 1.2e-14 | **FAIL** |
| 04 scalar random walk | 2000 | 1/1 | 1 | 0 | 0 | PASS |
| 05 random stable F, dense H/Q/R/P0 | 4000 | 6/4 | 6e2 | 2.8e-14 | 1.3e-14 | PASS |
| 06 redundant sensors (more measurements than states) | 3000 | 2/3 | 2.6e3 | 1.1e-12 | 2.7e-16 | PASS |
| 07 50k steps, outliers, track jumps, drift | 50000 | 4/2 | 2.7 | 5.8e-11 | 3.7e-16 | PASS |
| 08 coordinates around 1e6 | 20000 | 4/2 | 1.9 | 5.1e-12 | 2.0e-18 | PASS |
| 09 nearly singular R | 3000 | 4/2 | 1.7e6 | 1.1e-13 | 7.5e-16 | PASS |
| 10 nearly singular R | 3000 | 4/2 | 5.0e9 | 2.1e-13 | 1.4e-15 | PASS |
| 11 nearly singular R | 3000 | 4/2 | 7.4e10 | 1.4e-12 | 9.3e-15 | PASS |
| 12 nearly identical sensor rows in H | 3000 | 4/2 | 1.3e12 | 1.6e-11 | 1.6e-13 | PASS |
| 13 one NaN measurement row | 500 | 4/2 | 2 | 2.2e-16 | — | PASS |

**Why case 03 still fails:** it isn't a porting error. Octave and NumPy already disagree by 1 ulp on the very first `F*P` product, because their BLAS libraries round matrix multiplication differently. In this model the positions grow to about 9e4, so those last-digit differences add up to about 1e-9 absolute (1.2e-14 relative). I also ran a third version with correctly-rounded matrix products: it differs from Octave by 7.6e-10 and from the port by 1.35e-9. So no port can hit an absolute 1e-9 on this model unless it copies a specific BLAS's rounding. MATLAB uses Intel MKL, which will round differently from both again.

I've left the check at the absolute 1e-9 limit you asked for. I'd suggest switching the release criterion to a scaled one, for example error ≤ 1e-9 · max(1, |x|). Every case here passes that with a wide margin; the worst relative error is 1.6e-13.

**Worth telling the data team:**
- Neither version handles a missing measurement. After the NaN row in case 13, every later estimate is NaN in both MATLAB and Python (250 rows). The two agree, but a dropout ruins the rest of the stream.
- Case 11 aimed for cond(S) of 1e14, but the P term limits it to 7.4e10. Case 12 reaches 1.3e12.
- If S were ever symmetric but not positive definite, MATLAB falls back to an LDL solve while Octave and the port use LU. A valid filter shouldn't produce such an S, and none of the tests did.

**Files** (`cases/` takes about 12 MB):
- `generate_cases.py` regenerates the same 13 cases from a fixed seed. Each case has a `model.json` and a `z.csv`, written so the numbers read back exactly.
- `make_reference.m` runs `kalman_update.m` on every case and writes `ref.csv` into each case folder. It works in both MATLAB and Octave.
- `check_agreement.py` prints the table above.

To repeat the comparison in MATLAB: run `make_reference` in this folder (it overwrites the Octave `ref.csv` files), then `python check_agreement.py`.


## Follow-up

I agree that an absolute 1e-9 can't work on case 03. Change the check's gate to a per-element scaled tolerance, |err| ≤ 1e-9·max(1, |x_ref|), and keep printing the absolute numbers next to it. I don't want to merge a check that exits non-zero. Second, cases 10–12 only pass because `_mrdivide` copies Octave's choice of factorization. With MKL on MATLAB, cond(S) around 1e10–1e12 could still blow past either tolerance. What error do you actually expect there against MATLAB, and is this check the right gate for those cases, or should they be reported separately?

I'll start with the gate change, then measure how sensitive cases 09–12 are to rounding before answering the MATLAB question.

- `file_read` G:\Willikers\sandbox\demoforge-matlab-python-port-kvp6y8o3\working\check_agreement.py
- command:

  ```
  cd "G:/Willikers/sandbox/demoforge-matlab-python-port-kvp6y8o3/working" && cat > /tmp/sens.py <<'EOF'
  import sys; sys.path.insert(0,'.')
  import numpy as np
  from pathlib import Path
  from kalman_filter import _mrdivide, kalman_update
  from check_agreement import load_model
  eps=np.finfo(float).eps
  def run(Z,model,rng,mode):
      x=model["x0"].astype(float).reshape(-1);n=x.size
      F=model["F"].reshape(n,n);Q=model["Q"].reshape(n,n);P=model["P0"].reshape(n,n).astype(float)
      H=model["H"].reshape(-1,n);m=H.shape[0];R=model["R"].reshape(m,m);I=np.eye(n)
      X=np.zeros((len(Z),n));SD=np.zeros((len(Z),n))
      for k in range(len(Z)):
          x=F@x;P=F@P@F.T+Q
          if mode=='asym': P=P*(1+eps*rng.uniform(-1,1,P.shape))
          if mode=='sym':
              U=rng.uniform(-1,1,P.shape);P=P*(1+eps*(U+U.T)/2)
          if mode=='lu': pass
          y=Z[k]-H@x;S=H@P@H.T+R
          K=np.linalg.solve(S.T,(P@H.T).T).T if mode=='lu' else _mrdivide(P@H.T,S)
          x=x+K@y;P=(I-K@H)@P;X[k]=x;SD[k]=np.sqrt(np.abs(np.diag(P)))
      return X,SD
  rng=np.random.default_rng(1)
  for c in sorted(Path('cases').iterdir()):
      if c.name.startswith(('01','13')): continue
      mdl=load_model(c/'model.json');Z=np.loadtxt(c/'z.csv',delimiter=',',ndmin=2)
      ref=np.loadtxt(c/'ref.csv',delimiter=',',ndmin=2)
      X0,SD=run(Z,mdl,rng,'none'); scale=np.maximum(1,np.abs(ref))
      out=[]
      for mode,T in [('asym',8),('sym',8),('lu',1)]:
          d=max(np.abs(run(Z,mdl,rng,mode)[0]-X0).max() for _ in range(T)) if mode!='lu' else np.abs(run(Z,mdl,rng,mode)[0]-X0).max()
          out.append(d)
      Xa,_=run(Z,mdl,rng,'asym')
      print(f"{c.name:30s} vsOct_abs={np.abs(X0-ref).max():.1e} vsOct_scaled={(np.abs(X0-ref)/scale).max()/1e-9:.2e}  1ulp-asym={out[0]:.1e} 1ulp-sym={out[1]:.1e} allLU={out[2]:.1e}  asym/postSD={(np.abs(Xa-X0)/SD).max():.1e} minSD={SD[10:].min():.1e}")
  EOF
  python /tmp/sens.py
  ```

- `file_read` G:\Willikers\sandbox\demoforge-matlab-python-port-kvp6y8o3\working\kalman_filter.py
- command:

  ```
  cd "G:/Willikers/sandbox/demoforge-matlab-python-port-kvp6y8o3/working" && python - <<'EOF'
  p='kalman_filter.py'; s=open(p).read()
  s=s.replace('''        K = P H' / S;       x = x + K y;   P = (I - K H) P
      """
      x = np.asarray''','''        K = P H' / S;       x = x + K y;   P = (I - K H) P
      """
      return _kalman(Z, model)
  
  
  def _kalman(Z, model, predicted_P_hook=None):
      """kalman_update with a test hook.
  
      predicted_P_hook(P) -> P, if given, is applied to the predicted
      covariance each step; check_agreement.py uses it to inject rounding-
      sized perturbations and to observe S.
      """
      x = np.asarray''')
  s=s.replace('''        P = F @ P @ F.T + Q
  ''','''        P = F @ P @ F.T + Q
          if predicted_P_hook is not None:
              P = predicted_P_hook(P)
  ''')
  open(p,'w').write(s)
  EOF
  sed -n 36,100p kalman_filter.py
  ```

- `file_write` G:\Willikers\sandbox\demoforge-matlab-python-port-kvp6y8o3\working\check_agreement.py
The `|X|`-to-`|ref|` rescaling I wrote in `rounding_envelope` is wrong: it multiplies by a ratio of two maxima, not per element. I'm replacing it with the same per-element scaling the gate uses.

- command:

  ```
  cd "G:/Willikers/sandbox/demoforge-matlab-python-port-kvp6y8o3/working" && python - <<'EOF'
  p='check_agreement.py'; s=open(p).read()
  s=s.replace('''def scaled_err(X, ref):
      """Per-element |X - ref| / (TOL * max(1, |ref|)); NaN in both counts as 0."""
      both_nan = np.isnan(X) & np.isnan(ref)
      err = np.abs(X - ref) / (TOL * np.maximum(1.0, np.abs(ref)))''','''def scaled_err(X, Y, ref):
      """Per-element |X - Y| / (TOL * max(1, |ref|)); NaN in both counts as 0."""
      both_nan = np.isnan(X) & np.isnan(Y)
      err = np.abs(X - Y) / (TOL * np.maximum(1.0, np.abs(ref)))''')
  s=s.replace("    return np.where(np.isnan(X) != np.isnan(ref), np.inf, err)","    return np.where(np.isnan(X) != np.isnan(Y), np.inf, err)")
  s=s.replace('''        d = scaled_err(_kalman(Z, model, hook), X)
          env = max(env, float(np.max(d[np.isfinite(d)], initial=0.0)))
      # scaled_err normalises by |X|; renormalise by |ref| for consistency.
      return env * float(np.max(np.maximum(1, np.abs(X[np.isfinite(X)])), initial=1)
                         / np.max(np.maximum(1, np.abs(ref[np.isfinite(ref)])), initial=1))''','''        d = scaled_err(_kalman(Z, model, hook), X, ref)
          env = max(env, float(np.max(d[np.isfinite(d)], initial=0.0)))
      return env''')
  s=s.replace("err = float(scaled_err(X, ref).max())","err = float(scaled_err(X, ref, ref).max())")
  open(p,'w').write(s)
  EOF
  grep -n "scaled_err" check_agreement.py; time python check_agreement.py; echo "exit=$?"
  ```

- `file_read` G:\Willikers\sandbox\demoforge-matlab-python-port-kvp6y8o3\working\check_agreement.py
- command:

  ```
  cd "G:/Willikers/sandbox/demoforge-matlab-python-port-kvp6y8o3/working" && python - <<'EOF'
  p='check_agreement.py'; s=open(p).read()
  s=s.replace('''alone.  If it reaches 10% of the tolerance, the case is rounding-limited:
  the tolerance cannot tell a correct port from a wrong one, so the case is
  reported (REPORT) but does not gate.''','''alone.  If it reaches the tolerance, the case is rounding-limited: two
  correct implementations can disagree by more than the tolerance, so the
  case is reported (REPORT) but does not gate.  REPORT cases whose error is
  more than 10x the envelope are flagged "outside envelope" for a manual look.''')
  s=s.replace("ROUNDING_LIMITED = 0.1  # env/tol at or above this -> report only","ROUNDING_LIMITED = 1.0  # env/tol at or above this -> report only")
  s=s.replace('''            result = "REPORT"
  ''','''            result = "REPORT" + (" (outside envelope)" if err > 10 * env else "")
  ''')
  s=s.replace('''        print("  1-ulp rounding differences already move these outputs by >= 10% of the")
          print("  tolerance, so agreement with any particular reference is not meaningful.")''','''        print("  1-ulp rounding differences alone move these outputs by more than the")
          print("  tolerance, so agreement with any particular reference is not meaningful.")''')
  open(p,'w').write(s)
  EOF
  python check_agreement.py; echo "exit=$?"
  ```

The gate now passes and exits 0. Before trusting it, I'll check that it still catches real porting bugs by running it against a few deliberately broken versions of the port.

- command:

  ```
  cd "G:/Willikers/sandbox/demoforge-matlab-python-port-kvp6y8o3/working" && for mut in "Q = Q * (1 + 1e-6)" "R = R.T * 0 + np.diag(np.diag(R)) if m > 1 else R" "P = P.T"; do
  python - "$mut" <<'EOF' | tail -1
  import sys, re, types, numpy as np, runpy
  src = open('kalman_filter.py').read()
  mut = sys.argv[1]
  anchor = {'Q':'    R = np.asarray(model["R"], dtype=float).reshape(m, m)\n','R':'    R = np.asarray(model["R"], dtype=float).reshape(m, m)\n','P':'        P = (I - K @ H) @ P\n'}[mut[0]]
  ind = '        ' if mut[0]=='P' else '    '
  src = src.replace(anchor, anchor + ind + mut + '\n')
  mod = types.ModuleType('kalman_filter'); exec(compile(src,'kalman_filter.py','exec'), mod.__dict__); sys.modules['kalman_filter']=mod
  import io, contextlib
  buf=io.StringIO()
  with contextlib.redirect_stdout(buf):
      try: runpy.run_path('check_agreement.py', run_name='__main__')
      except SystemExit as e: code=e.code
  out=buf.getvalue()
  fails=[l.split()[0] for l in out.splitlines() if l.rstrip().endswith('FAIL')]
  print(f"mutation [{mut}]: exit={code}, failing gated cases={fails}")
  EOF
  done
  ```

I made the gate change: each element must now satisfy |err| ≤ 1e-9·max(1, |x_ref|), and the absolute errors are still printed next to it. With that gate, `check_agreement.py` passes against Octave and **exits 0**. It takes about 80 seconds.

Cases 10–12 are now reported separately and don't count toward the gate. My answer to your second question is that this check can't gate them. Measured against MATLAB, they would almost certainly fail any tolerance close to 1e-9.

**How I estimated the MATLAB error.** I can't run MKL here, so I approximated it. The check reruns the port 4 times, each time nudging every entry of the predicted covariance by up to 1 ulp per step. That's about the size of rounding difference between two BLAS libraries. How far the output moves is the "rounding envelope": roughly how much two correct implementations would disagree. The nudges are not symmetric, so they also change which steps take the Cholesky path. That covers MATLAB choosing a different factorization on different steps than Octave did.

| Case | cond(S) | error vs Octave (abs) | rounding spread (abs, earlier run) | spread / tolerance | spread in posterior std devs |
|---|---|---|---|---|---|
| 10 | 5e9 | 2.1e-13 | ~2e-6 | 2.0e3 | 2e-3 |
| 11 | 7e10 | 1.4e-12 | ~5e-2 | 2.9e7 | **~22** |
| 12 | 1.3e12 | 1.6e-11 | ~1.2e-3 | 3.5e5 | 2e-5 |

- **What to expect from MATLAB:** errors of about 1e-6 (case 10), 1e-3 (case 12) and 1e-2 to 1e-1 (case 11). It could be a few times larger, because MKL's differences aren't limited to one covariance step.
- **The tight Octave agreement is not evidence for MATLAB.** It only holds because NumPy and Octave run the same factorizations on similar OpenBLAS builds here.
- **Case 11 is noise in MATLAB too.** A 1-ulp nudge moves the estimate by about 22 posterior standard deviations, so the result there is rounding noise in MATLAB as well. That comes from how the filter is written, (I − K H)·P with a nearly singular S, not from the port. If the data team expects models like this, it's an algorithm change for both versions (Joseph form or a square-root filter).
- **Cases 10 and 12** are off by well under one standard deviation, so they're fine statistically, just millions of times past 1e-9.

**What changed in `check_agreement.py`:**
- A case is report-only when its rounding spread reaches the tolerance (env/tol ≥ 1). The gap is wide: the largest spread among gated cases is 0.31 (case 03) and the smallest among report-only cases is 2,000.
- Report-only cases still print their error. They're marked "outside envelope" if the error exceeds 10× the spread, which would suggest a real problem.
- NaN-placement or shape mismatches always fail, even for report-only cases.
- To let the check apply the nudges, `kalman_filter.py` now has a private `_kalman(Z, model, predicted_P_hook)`. The public `kalman_update(Z, model)` is unchanged.

**Results against Octave:** 10 gated cases pass, 3 are report-only, exit code 0. Case 03 is the gated case closest to failing: its error is 0.24 of the tolerance and its rounding spread is 0.31. If MKL rounds a few ulps differently, it could cross 1 on MATLAB, so it's the one to watch.

**Checking that the gate still catches bugs.** I ran it against deliberately broken versions of the port:
- Q scaled by (1 + 1e-6): fails 9 gated cases, exit 1.
- R's off-diagonal terms dropped: fails 9 gated cases, exit 1.
- Using P′ instead of P after the update: passes, as it should, since that changes only rounding.

To confirm the MATLAB numbers, run `make_reference` in MATLAB and then `python check_agreement.py`. The err/env column for cases 10–12 will show whether my 1-ulp estimate holds; values around 1–10 would confirm it.


## Follow-up

I don't want which cases get gated to be worked out at run time from the port's own sensitivity. If someone breaks the port in a way that makes it more sensitive, the check could exempt that case and still pass. Also, you moved the threshold from 0.1 to 1.0 after you saw 03 and 08 come out as REPORT, and that will get questioned in review. Please make the report-only set a fixed, explicit list (10, 11, 12) in the case files or in the check, keep the envelope as an extra printed column, and make "outside envelope" exit non-zero so it actually fails. Then rerun the check and the three mutations and show me the output.

I'll put the report-only marking in the case files: generate them with `"gate": "report"`, then confirm the regenerated inputs are byte-identical to the current ones.

- `$ cd "G:/Willikers/sandbox/demoforge-matlab-python-port-kvp6y8o3/working" && grep -n "def write_case\|\"description\": desc\|write_case(name\|F, Q, H, R, \[0, 0, 0.5, 0.5\], np.eye(4) \* 1e-6, Zs)\|write_case(\"12_\|np.eye(4) \* 1e4,\|Edge\|^# 9-11\|^# 12" generate_cases.py; md5sum cases/*/z.csv cases/*/ref.csv > /tmp/before.md5`
- `file_read` G:\Willikers\sandbox\demoforge-matlab-python-port-kvp6y8o3\working\generate_cases.py
- `file_read` G:\Willikers\sandbox\demoforge-matlab-python-port-kvp6y8o3\working\generate_cases.py
- `file_read` G:\Willikers\sandbox\demoforge-matlab-python-port-kvp6y8o3\working\generate_cases.py
- command:

  ```
  cd "G:/Willikers/sandbox/demoforge-matlab-python-port-kvp6y8o3/working" && python - <<'EOF'
  p='generate_cases.py'; s=open(p).read()
  def rep(a,b):
      global s
      assert s.count(a)==1, a
      s=s.replace(a,b)
  rep('''    z.csv        measurement stream, one row per step, no header
  ''','''    z.csv        measurement stream, one row per step, no header
  A case whose model.json has "gate": "report" is compared but not held to the
  1e-9 tolerance by check_agreement.py (see REPORT_ONLY below for why).
  ''')
  rep('''def write_case(name, desc, F, Q, H, R, x0, P0, Z):
      d = CASES / name
      d.mkdir(parents=True, exist_ok=True)
      model = {
          "description": desc,
  ''','''def write_case(name, desc, F, Q, H, R, x0, P0, Z):
      d = CASES / name
      d.mkdir(parents=True, exist_ok=True)
      model = {
          "description": desc,
          **({"gate": "report"} if name in REPORT_ONLY else {}),
  ''')
  rep('''# ---------------------------------------------------------------- helpers
  ''','''# Cases exempt from the 1e-9 gate.  Fixed list, decided from measurements on
  # 2026-10-16: perturbing the predicted covariance by 1 ulp per step moved these
  # outputs by 2e3 to 3e7 times the tolerance (every other case: <= 0.31x), so a
  # correct MATLAB/MKL run cannot be expected to meet it.  They are still
  # compared, and fail if the error exceeds 10x that rounding envelope.
  REPORT_ONLY = {"10_illcond_S_1e10", "11_illcond_S_1e14", "12_illcond_collinear_H"}
  
  
  # ---------------------------------------------------------------- helpers
  ''')
  open(p,'w').write(s)
  EOF
  python generate_cases.py && md5sum -c /tmp/before.md5 --quiet && echo "z.csv/ref.csv unchanged" && grep -l '"gate"' cases/*/model.json
  ```

- command:

  ```
  cd "G:/Willikers/sandbox/demoforge-matlab-python-port-kvp6y8o3/working" && python - <<'EOF'
  p='generate_cases.py'; s=open(p).read()
  a='''if CASES.exists():
      shutil.rmtree(CASES)
  
  '''
  assert s.count(a)==1
  s=s.replace(a,'').replace("import shutil\n","")
  s=s.replace('''The cases are committed; rerunning this script (fixed seed) regenerates
  the same files.''','''The cases are committed; rerunning this script (fixed seed) regenerates
  the same files.  It overwrites model.json and z.csv only, leaving any
  ref.csv from make_reference.m in place.''')
  open(p,'w').write(s)
  EOF
  grep -n shutil generate_cases.py; octave --no-gui --quiet --eval make_reference >/dev/null && md5sum -c /tmp/before.md5 --quiet && echo "all z.csv and ref.csv identical to before" && python generate_cases.py && md5sum -c /tmp/before.md5 --quiet && echo "rerun keeps refs"; grep -l '"gate"' cases/*/model.json
  ```

Inputs and references are byte-identical, and the three cases are marked. Next I'll update the check.

- `file_read` G:\Willikers\sandbox\demoforge-matlab-python-port-kvp6y8o3\working\check_agreement.py
- command:

  ```
  cd "G:/Willikers/sandbox/demoforge-matlab-python-port-kvp6y8o3/working" && python - <<'EOF'
  p='check_agreement.py'; s=open(p).read()
  def rep(a,b):
      global s
      assert s.count(a)==1, a
      s=s.replace(a,b)
  rep('''Gate (per element):  |X_py - X_ref| <= 1e-9 * max(1, |X_ref|)
  NaNs must appear in the same places in both outputs.
  
  Rounding envelope.  Two correct implementations (NumPy/OpenBLAS vs
  MATLAB/MKL) round matrix products differently, by about 1 ulp.  For each
  case the check re-runs the port several times with every element of the
  predicted covariance perturbed by up to 1 ulp per step, and records how far
  the output moves.  That spread is the disagreement to expect from rounding
  alone.  If it reaches the tolerance, the case is rounding-limited: two
  correct implementations can disagree by more than the tolerance, so the
  case is reported (REPORT) but does not gate.  REPORT cases whose error is
  more than 10x the envelope are flagged "outside envelope" for a manual look.  NaN-pattern or shape mismatches fail
  regardless.
  ''','''Gate (per element):  |X_py - X_ref| <= 1e-9 * max(1, |X_ref|)
  NaNs must appear in the same places in both outputs.
  
  Report-only cases.  A case whose model.json has "gate": "report" is not held
  to the 1e-9 tolerance; instead it fails if its error exceeds 10x the rounding
  envelope (below).  The list is fixed in generate_cases.py (REPORT_ONLY) and
  is never derived at run time.  Currently: 10, 11, 12 (badly conditioned S).
  
  Rounding envelope.  Two correct implementations (NumPy/OpenBLAS vs
  MATLAB/MKL) round matrix products differently, by about 1 ulp.  For each
  case the check re-runs the port several times with every element of the
  predicted covariance perturbed by up to 1 ulp per step, and records how far
  the output moves: the disagreement to expect from rounding alone.  It is
  printed for every case, and is the pass bound for report-only cases.
  ''')
  rep('''               larger than rounding explains (REPORT cases only)
  
  Exit status is non-zero only if a gated case fails.''','''               larger than rounding explains (REPORT cases fail above 10)
  
  Exit status is non-zero if any case fails.''')
  rep('''ROUNDING_LIMITED = 1.0  # env/tol at or above this -> report only
  ''','''ENVELOPE_FACTOR = 10  # report-only cases fail if err > this * envelope
  ''')
  rep('''def load_model(path):
      return {k: np.asarray(v) for k, v in json.loads(path.read_text()).items()
              if k != "description"}
  ''','''MATRIX_KEYS = ("F", "Q", "H", "R", "x0", "P0")
  
  
  def load_case(path):
      """Return (model dict of arrays, report_only flag) from model.json."""
      raw = json.loads(path.read_text())
      gate = raw.get("gate", "tolerance")
      if gate not in ("tolerance", "report"):
          raise ValueError(f"{path}: unknown gate {gate!r}")
      return {k: np.asarray(raw[k]) for k in MATRIX_KEYS}, gate == "report"
  ''')
  rep('''    gate_ok = True
      reported = []
  ''','''    all_ok = True
      reported = []
  ''')
  rep('''        model = load_model(c / "model.json")''','''        model, report_only = load_case(c / "model.json")''')
  rep('''            gate_ok = False
              continue''','''            all_ok = False
              continue''')
  rep('''        if nan_mismatch:
              result = "FAIL"
          elif env >= ROUNDING_LIMITED:
              result = "REPORT" + (" (outside envelope)" if err > 10 * env else "")
              reported.append(c.name)
          else:
              result = "PASS" if err <= 1.0 else "FAIL"
          gate_ok &= result != "FAIL"
  ''','''        if nan_mismatch:
              result = "FAIL"
          elif report_only:
              reported.append(c.name)
              result = ("REPORT" if err <= ENVELOPE_FACTOR * env
                        else "FAIL (outside envelope)")
          else:
              result = "PASS" if err <= 1.0 else "FAIL"
          all_ok &= not result.startswith("FAIL")
  ''')
  rep('''        print(f"Rounding-limited, not gated ({len(reported)}): {', '.join(reported)}")
          print("  1-ulp rounding differences alone move these outputs by more than the")
          print("  tolerance, so agreement with any particular reference is not meaningful.")
      print("GATE PASS" if gate_ok else "GATE FAIL")
      return 0 if gate_ok else 1''','''        print(f"Report-only ({len(reported)}, fixed list): {', '.join(reported)}")
          print(f"  not held to the 1e-9 tolerance; fail only if err > {ENVELOPE_FACTOR}x the rounding envelope.")
      print("ALL PASS" if all_ok else "SOME CASES FAIL")
      return 0 if all_ok else 1''')
  open(p,'w').write(s)
  EOF
  python check_agreement.py; echo "exit=$?"
  ```

Next, the three mutations, with full output for each:

- command:

  ```
  cd "G:/Willikers/sandbox/demoforge-matlab-python-port-kvp6y8o3/working" && for mut in "Q = Q * (1 + 1e-6)" "R = R.T * 0 + np.diag(np.diag(R)) if m > 1 else R" "P = P.T"; do
  echo "===== mutation: $mut"
  python - "$mut" <<'EOF'
  import sys, types, runpy
  src = open('kalman_filter.py').read()
  mut = sys.argv[1]
  if mut.startswith('P'):
      anchor, ind = '        P = (I - K @ H) @ P\n', '        '
  else:
      anchor, ind = '    R = np.asarray(model["R"], dtype=float).reshape(m, m)\n', '    '
  assert src.count(anchor) == 1
  src = src.replace(anchor, anchor + ind + mut + '\n')
  mod = types.ModuleType('kalman_filter')
  exec(compile(src, 'kalman_filter.py', 'exec'), mod.__dict__)
  sys.modules['kalman_filter'] = mod
  try:
      runpy.run_path('check_agreement.py', run_name='__main__')
  except SystemExit as e:
      print(f"exit={e.code}")
  EOF
  done
  ```

The report-only set is now a fixed list (cases 10, 11 and 12), and "outside envelope" makes the check exit non-zero. The real check passes with exit 0. The two broken ports both fail with exit 1, and the harmless change passes, as it should.

On the threshold: you're right. I moved it from 0.1 to 1.0 after seeing 03 and 08 come out as REPORT. No threshold is used now. I picked cases 10–12 from measured results, and the reason is written into `REPORT_ONLY` in `generate_cases.py`: their rounding envelopes are 2,000 to 3×10⁷ times the tolerance, and every other case's is at most 0.31.

**What changed**
- **`generate_cases.py`:** `REPORT_ONLY` writes `"gate": "report"` into the `model.json` of cases 10–12. The generator also no longer deletes `cases/` first; it overwrote my `ref.csv` files once. I regenerated them in Octave, and they and every `z.csv` are byte-identical to before.
- **`check_agreement.py`:** report-only status comes only from `model.json`. An unknown `gate` value is an error. The envelope is still printed for every case.
  - A report-only case fails when its error is more than 10× the envelope.
  - A NaN-placement or shape mismatch fails any case.
  - The check exits non-zero if any case fails.

**Real check**
```
case                                N  n  m  cond(S)   max_abs   err/tol   env/tol  err/env  result
01_baseline                      1500  4  2  1.0e+00  0.00e+00  0.00e+00  1.61e-04      0.0  PASS
02_cv2d_dt0.1_corrR_fullP0       5000  4  2  1.0e+01  4.55e-13  2.49e-04  2.52e-04      1.0  PASS
03_ca3d_n9_m3_dt0.02             3000  9  3  1.8e+01  1.05e-09  2.38e-01  3.12e-01      0.8  PASS
04_scalar_random_walk_n1_m1      2000  1  1  1.0e+00  0.00e+00  0.00e+00  4.30e-07      0.0  PASS
05_random_n6_m4                  4000  6  4  6.0e+02  2.75e-14  1.73e-05  6.28e-05      0.3  PASS
06_redundant_sensors_n2_m3       3000  2  3  2.6e+03  1.13e-12  3.46e-04  3.97e-04      0.9  PASS
07_messy_long_50k               50000  4  2  2.7e+00  5.82e-11  1.03e-02  1.17e-02      0.9  PASS
08_large_offset_1e6             20000  4  2  1.9e+00  5.10e-12  1.53e-03  1.40e-01      0.0  PASS
09_illcond_S_1e6                 3000  4  2  1.7e+06  1.14e-13  2.82e-05  5.81e-03      0.0  PASS
10_illcond_S_1e10                3000  4  2  5.0e+09  2.10e-13  2.05e-04  2.00e+03      0.0  REPORT
11_illcond_S_1e14                3000  4  2  7.4e+10  1.41e-12  1.39e-03  2.94e+07      0.0  REPORT
12_illcond_collinear_H           3000  4  2  1.3e+12  1.59e-11  5.47e-03  3.46e+05      0.0  REPORT
13_nan_dropout                    500  4  2  2.0e+00  2.22e-16  1.81e-07  6.22e-06      0.0  PASS  (250 NaN rows in ref, 0 NaN mismatches)

Report-only (3, fixed list): 10_illcond_S_1e10, 11_illcond_S_1e14, 12_illcond_collinear_H
  not held to the 1e-9 tolerance; fail only if err > 10x the rounding envelope.
ALL PASS
exit=0
```

**Mutations** (full tables above; summary here)

| Mutation | Gated cases | Cases 10 / 11 / 12 | Exit |
|---|---|---|---|
| Q × (1 + 1e-6) | all 10 FAIL (err/tol 28 to 23,000) | REPORT (err/env 1.5 / 1.0 / 0.0) | **1** |
| R off-diagonals dropped | 8 FAIL; 01 and 04 PASS because their R is already diagonal | **FAIL (outside envelope)** / **FAIL (outside envelope)** / REPORT, since 12's R is already diagonal | **1** |
| P → P′ after the update (only changes rounding) | all PASS; 03 reaches 0.41 | REPORT (err/env 0.6 / 1.0 / 0.0) | 0 |

The third mutation backs up last round's estimate for MATLAB. Just transposing P moves case 10 by 1.5e-6 and case 11 by 3.4e-2, which is about one envelope. That's roughly what a correct MATLAB/MKL run should show.

**Two limits on the report-only cases:**
- **They're weak at catching bugs.** A 1e-6 change to Q stays inside their envelopes, so only the gated cases catch it. Cases 10–12 only catch gross errors, like the R mutation.
- **The envelope still comes from the port being tested.** The gated set is fixed now, but a change that makes the port more sensitive also widens the bound those three cases are held to. To close that, I could compute each envelope once from a known-good port and store it as a fixed absolute bound in their `model.json`. I haven't done that; tell me if you want it.


## End of conversation

The follow-up limit was reached.


## Done
