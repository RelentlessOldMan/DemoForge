`validation_runs.csv` is an export of our nightly `cvt-regression` results for May and
June: one row per test case per nightly batch. A case passes when its `max_abs_error`
against the reference filter is below 1e-7. The nightly has been going red a lot more
than it used to, and so far all I've heard are theories, from flaky tests to one of the
worker machines. Nobody has actually gone through the numbers.

Could you dig into it and tell me what is really going on: when it started, what it
lines up with, how big the effect is, and which explanations the data rules out? Write
it up in `analysis.md`, with at least one plot (PNG) I can drop into the team update.

Please also put the key numbers in `findings.json` so I can paste them into the
tracker:

```json
{
  "regression_start_date": "YYYY-MM-DD, the first nightly batch affected",
  "explained_by": "the column that explains it: one of version, worker, test_id, none",
  "culprit": "the value of that column responsible",
  "baseline": "the value of that column you compare the culprit against",
  "magnitude_factor": 0.0,
  "affected_workers": ["worker names"],
  "per_version": {
    "vX.Y.Z": {"runs": 0, "mean_max_abs_error": 0.0, "median_max_abs_error": 0.0, "fail_rate": 0.0}
  }
}
```

`magnitude_factor` is the median `max_abs_error` for `culprit` divided by the median
for `baseline`. `per_version` covers every version in the file, over all of its rows;
`fail_rate` is the fraction (0 to 1) of cases at or above 1e-7.
