# Transcript

## Prompt

Before v2.2.0 is released we need a requirements traceability review of the estimator
against the current spec, CVT-EST-001 Rev C (`kalman_filter_spec.md`). The requirements
register is `requirements.csv`. The code under review is `kalman_update.m`, its test
suite is `test_kalman.m` (it reads `test_vectors.csv`), and `test_results.txt` is the
latest recorded run.

Please produce `TraceabilityMatrix.xlsx`, one row per requirement in the register,
with at least these columns:

| Column | Content |
|---|---|
| Requirement | the requirement ID, e.g. `R1` |
| Implemented | `Y`, `N` or `Partial` |
| Tests | the IDs of the tests in `test_kalman.m` that verify it, comma-separated, or `none` |
| Status | one of `VERIFIED`, `PARTIAL`, `NOT_VERIFIED`, `NOT_IMPLEMENTED` |
| Evidence | where in the code and tests you found it, and anything missing |

Status meanings: `VERIFIED` means implemented and fully verified by tests; `PARTIAL`
means implemented but the tests cover only part of it; `NOT_VERIFIED` means
implemented with no test verifying it; `NOT_IMPLEMENTED` means the code doesn't
implement it. Add any other columns you find useful.


- `$ Get-ChildItem -Recurse | Select-Object FullName, Length`
- `file_read` G:\Willikers\sandbox\demoforge-traceability-khmpcmwd\working\kalman_filter_spec.md
- `file_read` G:\Willikers\sandbox\demoforge-traceability-khmpcmwd\working\requirements.csv
- `file_read` G:\Willikers\sandbox\demoforge-traceability-khmpcmwd\working\kalman_update.m
- `file_read` G:\Willikers\sandbox\demoforge-traceability-khmpcmwd\working\test_kalman.m
- `file_read` G:\Willikers\sandbox\demoforge-traceability-khmpcmwd\working\test_results.txt
- `file_read` G:\Willikers\sandbox\demoforge-traceability-khmpcmwd\working\model.json
- `$ Get-Content test_vectors.csv -TotalCount 8; (Get-Content test_vectors.csv | Measure-Object -Line).Lines`
- `$ $l = Get-Content test_vectors.csv; $i=0; foreach ($r in $l) { $i++; if ($i -eq 1) {continue}; $p = $r.Split(','); $ok = $p.Count -eq 2; foreach ($v in $p) { $d=0.0; if (-not [double]::TryParse($v,[Globalization.NumberStyles]::Float,[Globalization.CultureInfo]::InvariantCulture,[ref]$d) -or [double]::IsNaN($d) -or [double]::IsInfinity($d)) {$ok=$false} }; if (-not $ok) { "line ${i}: $r" } }; "lines: $($l.Count)"; (Get-Command octave -ErrorAction SilentlyContinue).Source; (Get-Command python -ErrorAction SilentlyContinue).Source`
- `$ octave-cli --version | Select-Object -First 1; octave-cli --no-gui --eval "test_kalman" 2>&1 | Out-String`
- command:

  ```
  $t = Join-Path $env:TEMP "kf_mut"; Remove-Item -Recurse -Force $t -ErrorAction SilentlyContinue; New-Item -ItemType Directory $t | Out-Null
  Copy-Item test_kalman.m, test_vectors.csv $t
  $src = Get-Content kalman_update.m -Raw
  $muts = [ordered]@{
   'M0_original' = @('','');
   'M1_x0_ignored_zeros' = @('x = model.x0; P = model.P0;','x = zeros(4,1); P = model.P0;');
   'M2_P0_ignored_eye' = @('x = model.x0; P = model.P0;','x = model.x0; P = eye(4);');
   'M3_P0_scaled_100' = @('x = model.x0; P = model.P0;','x = model.x0; P = 100*model.P0;');
   'M4_Q_dropped' = @('P = F * P * F'' + Q;','P = F * P * F'';');
   'M5_no_cov_update' = @('P = (I - K * H) * P;','P = P;');
   'M6_returns_prior' = @("    x = x + K * y;`r`n","    xp = x; x = x + K * y;`r`n");
   'M7_gain_halved' = @('K = (P * H'') / S;','K = 0.5 * (P * H'') / S;');
   'M8_no_predict_state' = @('x = F * x;','x = x;');
   'M9_hardcoded_constants' = @('F = model.F; Q = model.Q; H = model.H; R = model.R;','F = [1 0 1 0; 0 1 0 1; 0 0 1 0; 0 0 0 1]; Q = 0.01*eye(4); H = [1 0 0 0; 0 1 0 0]; R = 0.25*eye(2);');
   'M10_rows_reversed' = @('X(k, :) = x'';','X(N-k+1, :) = x'';')
  }
  foreach ($k in $muts.Keys) {
    $a,$b = $muts[$k]; $s = $src
    if ($k -eq 'M6_returns_prior') { $s = $s.Replace('X(k, :) = x'';','X(k, :) = xp'';') }
    if ($a) { if (-not $s.Contains($a)) { "$k : PATTERN NOT FOUND"; continue }; $s = $s.Replace($a,$b) }
    Set-Content -Path (Join-Path $t 'kalman_update.m') -Value $s -Encoding ascii
    Push-Location $t; $o = (octave-cli --no-gui --eval "try, test_kalman, catch e, disp(['FAIL: ' e.message]), end" 2>&1 | Out-String).Trim(); Pop-Location
    "{0,-24} {1}" -f $k, $o
  }
  ```

- command:

  ```
  $t = Join-Path $env:TEMP ("kf_mut_" + [guid]::NewGuid().ToString('N').Substring(0,8)); New-Item -ItemType Directory $t | Out-Null
  Copy-Item test_kalman.m, test_vectors.csv $t
  $src = Get-Content kalman_update.m -Raw
  $muts = [ordered]@{
   'M0_original' = @('','');
   'M1_x0_ignored_zeros' = @('x = model.x0; P = model.P0;','x = zeros(4,1); P = model.P0;');
   'M2_P0_ignored_eye' = @('x = model.x0; P = model.P0;','x = model.x0; P = eye(4);');
   'M3_P0_scaled_100' = @('x = model.x0; P = model.P0;','x = model.x0; P = 100*model.P0;');
   'M4_Q_dropped' = @('P = F * P * F'' + Q;','P = F * P * F'';');
   'M5_no_cov_update' = @('P = (I - K * H) * P;','P = P;');
   'M6_returns_prior' = @('x = x + K * y;','xp = x; x = x + K * y;');
   'M7_gain_halved' = @('K = (P * H'') / S;','K = 0.5 * (P * H'') / S;');
   'M8_no_predict_state' = @('x = F * x;','x = x;');
   'M9_hardcoded_constants' = @('F = model.F; Q = model.Q; H = model.H; R = model.R;','F = [1 0 1 0; 0 1 0 1; 0 0 1 0; 0 0 0 1]; Q = 0.01*eye(4); H = [1 0 0 0; 0 1 0 0]; R = 0.25*eye(2);');
   'M10_rows_reversed' = @('X(k, :) = x'';','X(N-k+1, :) = x'';')
  }
  foreach ($k in $muts.Keys) {
    $a,$b = $muts[$k]; $s = $src
    if ($k -eq 'M6_returns_prior') { $s = $s.Replace('X(k, :) = x'';','X(k, :) = xp'';') }
    if ($a) { if (-not $s.Contains($a)) { "$k : PATTERN NOT FOUND"; continue }; $s = $s.Replace($a,$b) }
    Set-Content -Path (Join-Path $t 'kalman_update.m') -Value $s -Encoding ascii
    Push-Location $t; $o = (octave-cli --no-gui --eval "try, test_kalman, catch e, disp(['FAIL: ' e.message]), end" 2>&1 | Out-String).Trim(); Pop-Location
    "{0,-24} {1}" -f $k, $o
  }
  $t
  ```

- command:

  ```
  $t = "G:\Willikers\sandbox\demoforge-traceability-khmpcmwd\tmp\kf_mut_b3145541"
  Copy-Item kalman_update.m, model.json $t -Force
  @'
  import json, numpy as np
  m = json.load(open("model.json"))
  F,Q,H,R = (np.array(m[k],float) for k in "FQHR"); x = np.array(m["x0"],float).reshape(4,1); P = np.array(m["P0"],float)
  Z = np.loadtxt("test_vectors.csv", delimiter=",", skiprows=1); X = np.zeros((len(Z),4))
  for k,z in enumerate(Z):
      x = F@x; P = F@P@F.T + Q
      y = z.reshape(2,1) - H@x; S = H@P@H.T + R; K = np.linalg.solve(S.T,(P@H.T).T).T
      x = x + K@y; P = (np.eye(4)-K@H)@P; X[k] = x.ravel()
  np.savetxt("ref.csv", X, delimiter=",", fmt="%.17g")
  '@ | Set-Content (Join-Path $t ref.py) -Encoding ascii
  @'
  m = jsondecode(fileread('model.json')); m.x0 = m.x0(:);
  Z = csvread('test_vectors.csv',1,0); X = kalman_update(Z,m); Xr = csvread('ref.csv');
  printf('max abs err vs reference: %.3e\n', max(abs(X(:)-Xr(:))));
  Zn = Z(1:10,:); Zn(5,1) = NaN; Xn = kalman_update(Zn,m); printf('NaN at row 5 -> NaN rows in X: %s\n', mat2str(find(any(isnan(Xn),2))'));
  Zi = Z(1:10,:); Zi(3,2) = Inf; Xi = kalman_update(Zi,m); printf('Inf at row 3 -> non-finite rows in X: %s\n', mat2str(find(any(~isfinite(Xi),2))'));
  try, X1 = kalman_update(Z(1:10,1),m); printf('N-by-1 input accepted silently, size(X)=%s\n', mat2str(size(X1))); catch e, printf('N-by-1 error: %s\n', e.message); end
  try, X3 = kalman_update([Z(1:10,:) ones(10,1)],m); printf('N-by-3 accepted, size=%s\n', mat2str(size(X3))); catch e, printf('N-by-3 error: %s\n', e.message); end
  try, Xc = kalman_update({1,2},m); disp('cell accepted'); catch e, printf('cell input error: %s\n', e.message); end
  '@ | Set-Content (Join-Path $t chk.m) -Encoding ascii
  Push-Location $t; python ref.py; octave-cli --no-gui --eval "chk" 2>&1 | Out-String; Pop-Location
  ```

The code matches the reference exactly. Bad input is a different story: NaN and Inf spread into the state, and an N-by-1 input is accepted without any error. Now writing the workbook.

- `$ python -c "import openpyxl; print(openpyxl.__version__)"`
- `file_write` G:\Willikers\sandbox\demoforge-traceability-khmpcmwd\tmp\kf_mut_b3145541\build_matrix.py
- `$ python G:\Willikers\sandbox\demoforge-traceability-khmpcmwd\tmp\kf_mut_b3145541\build_matrix.py; python -c "import openpyxl; ws=openpyxl.load_workbook('TraceabilityMatrix.xlsx')['Traceability']; [print(r[0],r[4],r[5],r[6]) for r in ws.iter_rows(values_only=True)]"`
I've created `TraceabilityMatrix.xlsx` with one row per requirement. Only R1 and R4 are fully verified. R6 isn't implemented at all, so I don't think v2.2.0 can be released against Rev C as it stands.

| Req | Implemented | Tests | Status | Why |
|---|---|---|---|---|
| R1 | Y | T1 | VERIFIED | The signature matches §3 exactly. The rule that the function must not read files, print or use globals holds when you read the code, but no test checks it. |
| R2 | Y | T1, T3 | PARTIAL | T1 checks the N×4 shape. Nothing checks that rows are the estimates *after* each update rather than the predictions before it: a version that returns the predictions still passes every test. |
| R3 | Y | T3 | PARTIAL | The code is correct: it matches my own separate computation from `model.json` exactly (error 0.0, well inside the spec's 1e-6). But T3 only checks that positions stay within 5.0 of the measurements, so it can't catch errors in the calculation. |
| R4 | Y | T2 | VERIFIED | T2 checks that two runs give identical output. |
| R5 | Y | T1, T2, T3 | PARTIAL | The test exists and runs on `test_vectors.csv`. It checks R2 and R3 only weakly, hard-codes the model values instead of reading `model.json`, and doesn't apply the spec's 1e-6 acceptance check. |
| R6 | N | none | NOT_IMPLEMENTED | The code doesn't validate its input. A NaN or Inf measurement corrupts every later estimate, and a one-column input is accepted without any error and gives wrong results. No test covers this. R6 was added in Rev C and nothing in the code or tests has been updated for it. |

**How I checked:**
- **Test run:** I re-ran `test_kalman` on Octave 11.3.0 and all three tests passed, matching `test_results.txt`.
- **Fault injection:** I put 10 deliberate bugs into copies of the code in a temp folder and ran the unchanged tests against each. They caught only one: rows returned in reverse order. They missed the other nine, including ignoring `x0` or `P0`, dropping `Q`, skipping the covariance update, halving the gain, and hard-coding the model constants.
  - Because the test model uses `x0 = 0` and `P0 = I`, it can't detect mistakes in how the starting state is set up.
- **Test data:** All 1,500 rows of `test_vectors.csv` are valid numbers, so the current data never exercises R6.

**Recommended fixes (in the Gaps column):**
- Add input validation to `kalman_update.m`, plus tests that feed it NaN, Inf, wrong-width and non-numeric input. This is the release blocker.
- Have the test read `model.json`.
- Add a check against reference output to 1e-6, plus a case with non-zero `x0` and non-identity `P0`. With that in place, R2, R3 and R5 should become VERIFIED.

The workbook has two more sheets: "Mutation Analysis" (the results for each injected bug) and "Review Notes" (method and release recommendation). My scratch files, including the script that builds the workbook, are in `..\tmp\kf_mut_b3145541`. Nothing in `working\` was changed apart from adding the workbook.


## Follow-up

R1 is marked VERIFIED, but you say yourself that no test checks the "no file reads / no printing / no globals" part of §3. T1 only shows that a two-argument call returns something. That makes R1 PARTIAL at most, not VERIFIED. R3 has a similar problem: T3 missed every recursion mutation you injected (Q dropped, gain halved, no covariance update, no predict, x0/P0 ignored, hard-coded constants). So nothing actually verifies R3, and it should be NOT_VERIFIED with T3 noted as insufficient, not PARTIAL. Please fix both rows, and fix the Review Notes summary to match.

- `file_edit` G:\Willikers\sandbox\demoforge-traceability-khmpcmwd\tmp\kf_mut_b3145541\build_matrix.py
- `file_edit` G:\Willikers\sandbox\demoforge-traceability-khmpcmwd\tmp\kf_mut_b3145541\build_matrix.py
- `file_edit` G:\Willikers\sandbox\demoforge-traceability-khmpcmwd\tmp\kf_mut_b3145541\build_matrix.py
- `file_edit` G:\Willikers\sandbox\demoforge-traceability-khmpcmwd\tmp\kf_mut_b3145541\build_matrix.py
- `file_edit` G:\Willikers\sandbox\demoforge-traceability-khmpcmwd\tmp\kf_mut_b3145541\build_matrix.py
- `file_edit` G:\Willikers\sandbox\demoforge-traceability-khmpcmwd\tmp\kf_mut_b3145541\build_matrix.py
- `$ python G:\Willikers\sandbox\demoforge-traceability-khmpcmwd\tmp\kf_mut_b3145541\build_matrix.py; python -c "import openpyxl; wb=openpyxl.load_workbook('TraceabilityMatrix.xlsx'); [print(r[0],r[4],r[5],r[6],r[6] and wb['Traceability'].cell(row=i+1,column=7).fill.fgColor.rgb) for i,r in enumerate(wb['Traceability'].iter_rows(values_only=True))]; [print(r) for r in wb['Review Notes'].iter_rows(min_row=8,values_only=True)]"`
You're right on both counts, and I've updated `TraceabilityMatrix.xlsx` to match. R4 is now the only VERIFIED requirement.

- **R1 → PARTIAL** (Tests: `T1`). T1 only shows that a two-argument call returns one output. The rule that the function must not read files, print or use globals is confirmed only by reading the code. The Gaps column now suggests a test that captures console output and asserts it's empty, and a run with no data files present.
- **R3 → NOT_VERIFIED** (Tests: `none`). Since NOT_VERIFIED means no test verifies the requirement, I set Tests to `none` rather than listing T3. The Evidence column says that T3 is labelled as covering R3 but is insufficient: it caught none of the 8 recursion bugs I injected. It still records that the code itself is correct, matching the reference computation exactly.

To keep the other rows consistent with these changes:
- **R5** stays PARTIAL, but its evidence now says that of R1–R4, only R4 is fully checked. Its recommended action now also covers adding the R1 test.
- **Review Notes** has a new "Status summary" line: VERIFIED R4; PARTIAL R1, R2, R5; NOT_VERIFIED R3; NOT_IMPLEMENTED R6. The release recommendation now says the core recursion (R3) has no test verifying it, alongside the missing R6 implementation.

I left R2 as PARTIAL, because T3 does catch the reversed-row-order bug and T1 checks the shape. If you'd rather T3 not count towards R2 either, that's a one-cell change.


## End of conversation

The person had nothing more to ask.


## Done
