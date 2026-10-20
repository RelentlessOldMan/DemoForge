# Transcript

## Prompt

Before `kalman_update.m` goes into the v2.1.0 release, I'd like an independent
verification of it against its specification, CVT-EST-001 Rev B
(`kalman_filter_spec.md`). The folder also has `model.json`, the recorded stream
`test_vectors.csv`, and the test we have today, `test_kalman_existing.m`.

Please verify the implementation against the spec and give us a stronger test.
Leave `kalman_update.m` as it is; any fixes go back to its author.

Deliverables:

- `test_kalman.m`: runs with `octave-cli test_kalman.m` from a folder containing
  `kalman_update.m`, `model.json` and `test_vectors.csv`. It must exit non-zero if a
  check fails, and pass for any implementation that meets the spec.
- `verification_report.md`: a short report with your conclusion, what the existing
  test does and doesn't establish, and what your tests cover.
- `findings.json`, in this form (`defects` is empty if you find none):

```json
{
  "verdict": "defect_found or no_defect",
  "defects": [
    {
      "requirement": "the CVT-EST-001 requirement it violates (R1 to R5)",
      "summary": "one sentence",
      "evidence": [{"file": "kalman_update.m", "line": 1}]
    }
  ]
}
```


- `$ ls -la && cat kalman_filter_spec.md && cat -n kalman_update.m && cat model.json && cat test_kalman_existing.m && head -5 test_vectors.csv && wc -l test_vectors.csv; which octave-cli octave`
- `$ octave-cli test_kalman_existing.m; echo "exit=$?"`
- `file_write` G:\Willikers\sandbox\demoforge-verification-hxd_ma7q\working\test_kalman.m
- `$ octave-cli test_kalman.m; echo "exit=$?"`
- command:

  ```
  python - <<'EOF'
  p='test_kalman.m'; s=open(p,encoding='utf-8').read()
  s=s.replace("""  @() deal(isempty(evalc('kalman_update(Z, model);')), ''));""","""  @() prints_nothing(Z, model));""")
  s=s.replace("""% ---------------------------------------------------------------------------
  ""","""function [ok, msg] = prints_nothing(Z, model)
    out = evalc('kalman_update(Z, model);');
    ok = isempty(out);
    msg = '';
    if ~ok, msg = sprintf('printed %d chars', numel(out)); end
  end
  
  % ---------------------------------------------------------------------------
  """,1)
  s=s.replace("""  @() deal(isequal(kalman_update(Z(1:100, :), model), ...
                     kalman_update(Z(1:200, :), model)(1:100, :)) || ...
             max(max(abs(kalman_update(Z(1:100, :), model) - ...
                         kalman_update(Z(1:200, :), model)(1:100, :)))) < TOL, ''));""","""  @() deal(max(max(abs(kalman_update(Z(1:100, :), model) - ...
                         kalman_update(Z(1:200, :), model)(1:100, :)))) < TOL, ''));""")
  open(p,'w',encoding='utf-8').write(s)
  EOF
  octave-cli test_kalman.m; echo "exit=$?"
  T=$(mktemp -d); cp test_kalman.m model.json test_vectors.csv $T/
  sed -e 's/x = zeros(n, 1);/x = model.x0(:);/' -e 's/P = eye(n);/P = model.P0;/' kalman_update.m > $T/kalman_update.m
  grep -n "x0\|P0" $T/kalman_update.m; cd $T && octave-cli test_kalman.m; echo "fixed-copy exit=$?"; rm -rf $T
  ```

The test fails on the shipped implementation (exit 1) and passes on a copy with the two lines corrected (exit 0). Writing the report and findings now.

- `file_write` G:\Willikers\sandbox\demoforge-verification-hxd_ma7q\working\findings.json
- `file_write` G:\Willikers\sandbox\demoforge-verification-hxd_ma7q\working\verification_report.md
- `$ grep -n "Initialise" kalman_filter_spec.md; grep -n x0 model.json; python -c "import json;json.load(open('findings.json'))" && echo ok`
- `$ sed -i 's/"kalman_filter_spec.md", "line": 49/"kalman_filter_spec.md", "line": 67/' findings.json && grep spec findings.json`
**`kalman_update.m` has a defect and shouldn't go into v2.1.0 as it is.** It breaks R3: lines 18–19 start the filter from hard-coded values (`x = zeros(n,1)`, `P = eye(n)`) and never read `model.x0` or `model.P0`. The spec (§4 and §2.3) says to start from those two fields.

The current `model.json` happens to set x0 to zeros and P0 to the identity, which are exactly the hard-coded values. So on the recorded stream the output matches the spec's recursion exactly, the §6 acceptance check passes, and `test_kalman_existing.m` passes too. As soon as x0 or P0 changes, the output is wrong: with changed values the largest state error is 0.61 for x0 and 0.157 for P0, against the spec's 1e-6 tolerance. The rest of the recursion matches the spec. I left `kalman_update.m` unchanged; the fix for the author is `x = model.x0(:); P = model.P0;`.

**What the existing test does and doesn't show:**
- It does check the output shape, that repeated calls give the same result, and a loose "stays within 5.0 of the measurements" bound.
- It never compares the output to the spec's recursion.
- It builds the model by hand instead of reading `model.json`, which §2.3 requires.
- It only ever uses one model, and that model's x0 and P0 match the hard-coded defaults, so it can't catch this defect.

**`test_kalman.m` (16 checks):**
- **Signature and output (R1, R2):** two inputs and one output; N×4 output; 1×4 for a single measurement; earlier rows don't change when more measurements are added.
- **Recursion (R3):** compares the output with my own implementation of the spec's recursion to within 1e-6, using constants read from `model.json`. It then repeats the comparison with each of x0, P0, F, Q, R and H changed in turn, and with all of them changed together, so any hard-coded constant shows up.
- **Other:** no divergence from the measurements, identical results on repeated calls (R4), and the function prints nothing (§3).

**Test results:**
- **On the shipped code:** 13/16 pass and it exits 1. The failures are the x0, P0 and all-changed checks.
- **On a scratch copy with the two-line fix:** 16/16 pass and it exits 0. This confirms the test passes an implementation that meets the spec.

The test doesn't check the §3 rules against reading files or using globals. I checked those by reading the code, and the function does neither.

Files are in the working folder:
- test_kalman.m
- verification_report.md
- findings.json


## End of conversation

The person had nothing more to ask.


## Done
