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
