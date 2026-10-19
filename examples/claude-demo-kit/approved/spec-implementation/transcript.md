# Transcript

## Prompt

We need the measurement validation gate for the CVT estimator's v2.4 release. It is
specified in section 7.3 of `CVT-SRS-003.pdf` (Estimator Software Requirements, Rev C).
Please implement it in MATLAB as `measurement_gate.m`, with the interface the spec
defines, and write `test_measurement_gate.m`: a test we can run in CI with
`octave-cli test_measurement_gate.m`, which must raise an error if the gate does not
meet §7.3. We run GNU Octave here, not MATLAB.

`gate_vectors.csv` is a bench capture of gate inputs from both measurement modes, if
you want real data to exercise it with. Each row is one measurement: the mode, its
dimension `m`, the gamma the bench was configured with, the innovation `y` (`y1..y4`)
and the innovation covariance `S` laid out on a 4-by-4 grid (`s11..s44`). Planar rows
use only the first two components and the upper-left 2-by-2 block; the unused cells
are empty.


- `$ Get-ChildItem -Recurse | Select-Object FullName, Length; Get-Command octave-cli, pdftotext, python -ErrorAction SilentlyContinue | Select-Object Source`
- `file_read` G:\Willikers\sandbox\demoforge-spec-implementation-5zwsx8sr\working\CVT-SRS-003.pdf
- `file_read` G:\Willikers\sandbox\demoforge-spec-implementation-5zwsx8sr\working\gate_vectors.csv
- `$ Get-ChildItem "C:\Program Files*\GNU Octave*", "C:\Octave*", "$env:LOCALAPPDATA\Programs\GNU Octave*" -ErrorAction SilentlyContinue | Select-Object FullName; where.exe octave octave-cli python python3 2>$null`
- command:

  ```
  cd "G:/Willikers/sandbox/demoforge-spec-implementation-5zwsx8sr/working" && python -c "
  import csv, numpy as np
  for i,r in enumerate(csv.DictReader(open('gate_vectors.csv'))):
      m=int(r['m']); g=float(r['gamma'])
      y=np.array([float(r[f'y{k}']) for k in range(1,m+1)])
      S=np.array([[float(r[f's{a}{b}']) for b in range(1,m+1)] for a in range(1,m+1)])
      d2=y@np.linalg.solve(S,y) if np.all(np.isfinite(y)) else float('inf')
      print(i+2, r['mode'], g, round(d2,6), d2<=g, 'acc@9.210' if m==2 and d2<=9.210 else '', np.linalg.eigvalsh(S).min().round(4))
  "
  ```

- `$ cd /tmp && OCT="/c/Users/you/AppData/Local/Programs/GNU Octave/Octave-11.3.0/mingw64/bin/octave-cli.exe"; "$OCT" --no-gui --eval "S=[1 0;0 1e-300]; [R,p]=chol(S), x=R\(R'\[1;1]), S2=[1 1;1 1+1e-15]; [R2,p2]=chol(S2), x2=S2\[1;1], s=evalc('S2\\[1;1];'), exist('evalc')" 2>&1`
Spec and bench data read; Octave 11.3 is installed. Next I'm writing the gate and its test, then running them in Octave.

- `file_write` G:\Willikers\sandbox\demoforge-spec-implementation-5zwsx8sr\working\measurement_gate.m
- `file_write` G:\Willikers\sandbox\demoforge-spec-implementation-5zwsx8sr\working\test_measurement_gate.m
- `file_edit` G:\Willikers\sandbox\demoforge-spec-implementation-5zwsx8sr\working\test_measurement_gate.m
- `$ cd "G:/Willikers/sandbox/demoforge-spec-implementation-5zwsx8sr/working" && "/c/Users/you/AppData/Local/Programs/GNU Octave/Octave-11.3.0/mingw64/bin/octave-cli.exe" test_measurement_gate.m; echo "exit=$?"`
Octave's `strsplit` collapses consecutive delimiters by default, which breaks the empty cells; fixing that.

- `$ cd "G:/Willikers/sandbox/demoforge-spec-implementation-5zwsx8sr/working" && sed -i "s/strsplit(lines{r + 1}, ',')/strsplit(strtrim(lines{r + 1}), ',', 'CollapseDelimiters', false)/; s/strsplit(strtrim(lines{1}), ',')/strsplit(strtrim(lines{1}), ',', 'CollapseDelimiters', false)/" test_measurement_gate.m && grep -n "strsplit" test_measurement_gate.m && "/c/Users/you/AppData/Local/Programs/GNU Octave/Octave-11.3.0/mingw64/bin/octave-cli.exe" test_measurement_gate.m; echo "exit=$?"`
Passes. Now checking that the test actually fails on broken gates, by running it against a few deliberately wrong versions of the gate:

- command:

  ```
  cd "G:/Willikers/sandbox/demoforge-spec-implementation-5zwsx8sr/working" && OCT="/c/Users/you/AppData/Local/Programs/GNU Octave/Octave-11.3.0/mingw64/bin/octave-cli.exe"; cp measurement_gate.m /tmp/orig.m
  mut() { cp /tmp/orig.m measurement_gate.m; sed -i "$1" measurement_gate.m; printf '%-28s ' "$2"; "$OCT" test_measurement_gate.m 2>&1 | head -2 | tr '\n' ' ' | cut -c1-150; echo; }
  mut 's/accept = (d2 <= gamma);/accept = (d2 < gamma);/' "strict <"
  mut 's/x = S \\ y;/x = inv(S) * y;/' "inv(S)"
  mut 's/accept = (d2 <= gamma);/accept = (d2 <= 5.991);/' "hardcoded 5.991"
  mut 's/if ~(all(isfinite(y)) \&\& all(isfinite(S(:))))/if false/' "no finiteness check"
  mut 's/if ~(isfinite(gamma) \&\& gamma > 0)/if ~(gamma > 0)/' "Inf gamma allowed"
  mut 's/\[~, notpd\] = chol(S);/notpd = 0;/' "no PD check"
  mut "s/warning('off', 'all');//" "warnings not silenced"
  mut 's/  if ~(isnumeric(gamma) \&\& isreal(gamma) \&\& isscalar(gamma))/  if false/' "no gamma type check"
  cp /tmp/orig.m measurement_gate.m; "$OCT" test_measurement_gate.m
  ```

Three mutants slip through (`inv(S)`, removing the finiteness check, not silencing warnings). Investigating:

- `$ cd "G:/Willikers/sandbox/demoforge-spec-implementation-5zwsx8sr/working" && OCT="/c/Users/you/AppData/Local/Programs/GNU Octave/Octave-11.3.0/mingw64/bin/octave-cli.exe"; "$OCT" --eval "c='x = inv(S) * y; z = S \\ y;'; regexp(c, '\<(inv|pinv)\s*\(', 'once'), regexp(c, '\binv\s*\(', 'once'), regexp(c, 'S\s*\\\\\s*y', 'once'), regexp('a %c\nb', '%[^\n]*','match')"; "$OCT" --eval "S=[1 NaN;NaN 1]; [R,p]=chol(S), rcond(S)" 2>&1 | head; "$OCT" --eval "s=evalc('warning(\"hi\")')"`
- command:

  ```
  cd "G:/Willikers/sandbox/demoforge-spec-implementation-5zwsx8sr/working" && OCT="/c/Users/you/AppData/Local/Programs/GNU Octave/Octave-11.3.0/mingw64/bin/octave-cli.exe"; cat > /tmp/t.m <<'EOF'
  c = 'x = inv(S) * y; z = S \ y;';
  a1 = regexp(c, 'S\s*\\\s*y', 'once')
  a2 = regexp(c, 'S\s*[\\]\s*y', 'once')
  a3 = regexp(c, 'S\s*\x5C\s*y', 'once')
  src = fileread('measurement_gate.m'); code = regexprep(src, '%[^\n]*', '');
  numel(src), numel(code)
  regexp(code, '\<(inv|pinv)\s*\(', 'once')
  EOF
  "$OCT" /tmp/t.m
  ```

- command:

  ```
  cd "G:/Willikers/sandbox/demoforge-spec-implementation-5zwsx8sr/working" && OCT="/c/Users/you/AppData/Local/Programs/GNU Octave/Octave-11.3.0/mingw64/bin/octave-cli.exe"; cat > /tmp/t.m <<'EOF'
  c = 'x = inv(S) * y; z = S \ y;';
  a4 = regexp(c, 'S\s*\\\\\s*y', 'once')
  src = fileread('measurement_gate.m'); code = regexprep(src, '%[^\n]*', '');
  numel(src), numel(code)
  regexp(code, '\<(inv|pinv)\s*\(', 'once')
  EOF
  "$OCT" /tmp/t.m
  ```

- command:

  ```
  cd "G:/Willikers/sandbox/demoforge-spec-implementation-5zwsx8sr/working" && OCT="/c/Users/you/AppData/Local/Programs/GNU Octave/Octave-11.3.0/mingw64/bin/octave-cli.exe"; grep -n "inv\|S \\\\" measurement_gate.m; grep -n "regexp(code" test_measurement_gate.m; cat > /tmp/t.m <<'EOF'
  src = fileread('measurement_gate.m'); code = regexprep(src, '%[^\n]*', '');
  regexp(code, 'S\s*\\\s*y', 'match')
  regexp(code, 'S\s*\\\\\s*y', 'match')
  EOF
  "$OCT" /tmp/t.m
  ```

- `$ cd "G:/Willikers/sandbox/demoforge-spec-implementation-5zwsx8sr/working" && OCT="/c/Users/you/AppData/Local/Programs/GNU Octave/Octave-11.3.0/mingw64/bin/octave-cli.exe"; sed -n '85,100p' test_measurement_gate.m; sed '96a printf("DBG here=%s n=%d code=%d\\n", here, n_checks, numel(code)); disp(failures)' test_measurement_gate.m > /tmp/dbg_test.m; cp /tmp/dbg_test.m ./dbg_test.m; "$OCT" dbg_test.m 2>&1 | head; rm dbg_test.m`
- command:

  ```
  cd "G:/Willikers/sandbox/demoforge-spec-implementation-5zwsx8sr/working" && OCT="/c/Users/you/AppData/Local/Programs/GNU Octave/Octave-11.3.0/mingw64/bin/octave-cli.exe"; head -96 test_measurement_gate.m > dbg_test.m; cat >> dbg_test.m <<'EOF'
  printf('DBG here=%s n=%d code=%d\n', here, n_checks, numel(code));
  failures
  EOF
  "$OCT" dbg_test.m 2>&1 | head -20; rm dbg_test.m
  ```

The source-inspection checks in the test misbehave because of how Octave handles backslashes in regex patterns. I'm replacing them with plain string matching, then rerunning the broken-gate checks.

- `file_edit` G:\Willikers\sandbox\demoforge-spec-implementation-5zwsx8sr\working\test_measurement_gate.m
- command:

  ```
  cd "G:/Willikers/sandbox/demoforge-spec-implementation-5zwsx8sr/working" && OCT="/c/Users/you/AppData/Local/Programs/GNU Octave/Octave-11.3.0/mingw64/bin/octave-cli.exe"; cp measurement_gate.m /tmp/orig.m
  mut() { cp /tmp/orig.m measurement_gate.m; sed -i "$1" measurement_gate.m; grep -c "$3" measurement_gate.m | tr '\n' ' '; printf '%-24s ' "$2"; "$OCT" test_measurement_gate.m 2>&1 | head -2 | tr '\n' ' ' | cut -c1-140; echo; }
  mut 's/x = S \\ y;/x = inv(S) * y;/' "inv(S)" "inv(S) \*"
  mut 's/x = S \\ y;/x = pinv(S)*y;/' "pinv(S)" "pinv"
  mut 's/accept = (d2 <= gamma);/accept = (d2 <= 9.21);/' "hardcoded 9.21" "9.21"
  mut 's/d = y'"'"' \* x;/d = y'"'"' * x * 2;/' "wrong d2" "x \* 2"
  mut 's/accept = (d2 <= gamma);/accept = (d2 <= gamma); disp(d2);/' "prints" "disp"
  cp /tmp/orig.m measurement_gate.m; "$OCT" test_measurement_gate.m; echo "exit=$?"; cmp measurement_gate.m /tmp/orig.m && echo restored
  ```

The `inv(S)` mutant still passes, so the static check isn't firing at all. Debugging it directly:

- command:

  ```
  cd "G:/Willikers/sandbox/demoforge-spec-implementation-5zwsx8sr/working" && OCT="/c/Users/you/AppData/Local/Programs/GNU Octave/Octave-11.3.0/mingw64/bin/octave-cli.exe"; sed 's/x = S \\ y;/x = inv(S) * y;/' measurement_gate.m > /tmp/mut/measurement_gate.m 2>/dev/null || { mkdir -p /tmp/mut; sed 's/x = S \\ y;/x = inv(S) * y;/' measurement_gate.m > /tmp/mut/measurement_gate.m; }; grep -n "inv(S) \*" /tmp/mut/measurement_gate.m; cat > /tmp/mut/t.m <<'EOF'
  src = fileread('measurement_gate.m'); code = regexprep(src, '%[^\n]*', '');
  code_nows = regexprep(code, '\s', '');
  idx = strfind(code_nows, 'inv')
  code_nows(max(1,idx(1)-10):min(end,idx(1)+10))
  regexp(code_nows, '(^|[^A-Za-z0-9_])p?inv\(', 'once')
  strfind(code_nows, ['S' char(92) 'y'])
  EOF
  cd /tmp/mut && "$OCT" t.m
  ```

- `$ cd "G:/Willikers/sandbox/demoforge-spec-implementation-5zwsx8sr/working" && grep -n 'S \\ y' measurement_gate.m; sed -n '77p' measurement_gate.m | od -c | head -3`
The `inv(S)` mutant was never applied: Git Bash's `sed` didn't match the backslash. So the test itself may be fine. Re-applying the mutants with Python instead:

- command:

  ```
  cd "G:/Willikers/sandbox/demoforge-spec-implementation-5zwsx8sr/working" && OCT="/c/Users/you/AppData/Local/Programs/GNU Octave/Octave-11.3.0/mingw64/bin/octave-cli.exe"; cp measurement_gate.m /tmp/orig.m
  for pair in 'x = S \ y;|x = inv(S) * y;' 'x = S \ y;|x = pinv(S)*y;' 'x = S \ y;|x = (S'"'"' * S) \ (S'"'"' * y);' 'x = S \ y;|x = mldivide(S, y);'; do
    python - "$pair" <<'EOF'
  import sys; a,b = sys.argv[1].split('|'); s=open('/tmp/orig.m').read(); assert a in s; open('measurement_gate.m','w',newline='\n').write(s.replace(a,b))
  EOF
    printf '%-40s ' "${pair#*|}"; "$OCT" test_measurement_gate.m 2>&1 | head -2 | tr '\n' ' ' | cut -c1-120; echo
  done
  cp /tmp/orig.m measurement_gate.m; "$OCT" test_measurement_gate.m; echo "exit=$?"
  ```

Windows Python can't see `/tmp`. Running the mutants in a scratch copy of the folder instead:

- command:

  ```
  cd "G:/Willikers/sandbox/demoforge-spec-implementation-5zwsx8sr/working" && OCT="/c/Users/you/AppData/Local/Programs/GNU Octave/Octave-11.3.0/mingw64/bin/octave-cli.exe"; mkdir -p _mut && cp test_measurement_gate.m gate_vectors.csv _mut/ && cd _mut
  for pair in 'x = S \ y;|x = inv(S) * y;' 'x = S \ y;|x = pinv(S)*y;' 'x = S \ y;|x = mldivide(S, y);' "warning('off', 'all');|" 'if rcond(S) < eps|if false' 'if ~(all(isfinite(y)) && all(isfinite(S(:))))|if false' 'accept = (d2 <= gamma);|accept = (d2 <= gamma); printf("%g\n", d2);'; do
    python - "$pair" <<'EOF'
  import sys; a,b = sys.argv[1].split('|'); s=open('../measurement_gate.m').read(); assert a in s, a; open('measurement_gate.m','w',newline='\n').write(s.replace(a,b))
  EOF
    printf '%-45s ' "${pair}" | cut -c1-45 | tr -d '\n'; "$OCT" test_measurement_gate.m 2>&1 | head -2 | tr '\n' ' ' | cut -c1-120; echo
  done
  cd .. && rm -rf _mut && ls
  ```

I've written `measurement_gate.m` and `test_measurement_gate.m`. `octave-cli test_measurement_gate.m` passes all 373 checks on Octave 11.3 and exits 0. When a check fails, the test lists every failure and then calls `error()`, so the CI job fails.

## The gate
It uses the interface from §7.3.4: `[accept, d2] = measurement_gate(y, S, gamma)`.
- **G1:** it solves `x = S \ y` and computes `d2 = y' * x`, without ever forming `inv(S)`. It works for any dimension m.
- **G2:** it admits the measurement if and only if `d2 <= gamma`, so a d2 exactly equal to gamma is admitted.
- **G3:** it has no threshold of its own and uses only the gamma passed in.
- **G4:** if y or S contains NaN or ±Inf, or gamma is not a finite positive scalar, it returns `false, Inf` and does not raise an error.
- **Purity:** it does no file access, no printing and uses no globals.

**One thing the spec doesn't cover:** the gate also returns `false, Inf` (with no error) for inputs that break the §7.3.4 contract. That covers wrong shapes, a y/S size mismatch, complex or non-numeric data, and an S that is not symmetric positive definite (including numerically singular). Without this, an indefinite S can give a negative d2, and that measurement would be admitted. That goes against the spec's rule that "a malformed measurement … must never lead to a measurement being admitted", so I treated these cases as malformed. If you'd rather tie this to an explicit requirement, it should go back to the spec owner.

## The test
- **Behaviour checks:**
  - d2 matches an independently computed reference for m = 1, 2, 3, 4, 6 and 10, plus one case where the answer is exact.
  - Decisions are right at d2 = gamma and one rounding step either side of it.
  - The decision changes when you pass different Appendix A gamma values.
  - About 80 malformed or non-finite inputs all return `false, Inf`, with no error and no printed output.
- **Bench data:** all 24 rows of `gate_vectors.csv`, covering both modes, are checked against d2 values and decisions computed separately in NumPy. Row 19 has `y4 = NaN` and is rejected as G-BC-1 requires.
- **Source checks on the gate:** no `inv`/`pinv`, a `S \ y` solve is present, no hard-coded thresholds, and no printing or file I/O calls.

**Testing the test:** I ran it against deliberately broken copies of the gate. It caught `<` used instead of `<=`, a hard-coded threshold, a wrong d2, a missing PD check, printing, and use of `inv` or `pinv`. Two broken copies still passed, which is expected: removing the explicit finiteness check, or the warning suppression, is still caught by the later checks in the gate.

**Limitation:** the "solves S x = y" check looks for the text `S \ y`, so an equivalent `mldivide(S, y)` would fail it.

## Check the bench gamma
Bench rows 21–25 (planar) were run with **gamma = 5.991**. That is the fixed 95% threshold from Rev B (v2.3). Rev C makes 99% the default, which gives 9.210 for m = 2.

5.991 is still a valid Appendix A value if 95% was configured on purpose, so the test accepts it and checks the gate against the gamma the bench actually supplied. But it changes results: **rows 23 (d2 = 6.85) and 24 (d2 = 8.12) are rejected at 5.991 and would be admitted at 9.210.** If that rig was supposed to be on the v2.4 default, it may still be running the v2.3 configuration, and that's worth confirming before the release.


## End of conversation

The person had nothing more to ask.


## Done
