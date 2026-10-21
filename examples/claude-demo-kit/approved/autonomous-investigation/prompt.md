Validation campaign VAL-2026-09 rejected the v2.4.1 release, and the CCB wants the
root cause before anything else happens to v2.4. Dmitri started on it but is on leave
now; his notes are in `notes/`. This is the CVT estimator repository: source, tests,
controlled documents, configuration, and the data and logs from the campaign. We run
GNU Octave here, not MATLAB.

Please find out why the campaign failed and write it up in `root_cause.md`: what
failed, the root cause, the evidence that establishes it, why it was not caught
earlier, what you ruled out and why, and what you recommend.

Also write `findings.json` so the CCB tracker can pick it up:

```json
{
  "root_cause": "one or two sentences",
  "cause": {"file": "path/in/repo", "line": 0},
  "discriminator": {"field": "column of data/validation_runs.csv", "value": "..."},
  "failing_runs": ["run ids"],
  "wrong_value": {"in_use": 0.0, "correct": 0.0},
  "evidence": [{"file": "path/in/repo", "line": 0, "quote": "text from that line"}],
  "ruled_out": ["explanation, and why it is ruled out"]
}
```

`cause` is the line where the defect is. `discriminator` is the run attribute that
separates the failing runs from the passing ones. `wrong_value` is for a value that
is wrong in use; set it to `null` if the cause is not a wrong value. Line numbers are
1-based and refer to the files as you found them, before any change you make.

If the cause is in the code, fix it, and change the tests so they would have caught it.
