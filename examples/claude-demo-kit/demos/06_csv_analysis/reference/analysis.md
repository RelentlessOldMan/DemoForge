# Nightly cvt-regression, May–June 2026: why the nightly went red

## Data

`validation_runs.csv`: 3060 case results from 60 nightly batches
(`val-2026-05-01` … `val-2026-06-30`; no batch on 2026-06-14), 51 cases per batch
(tests 1800–1850). Odd tests run on estimator-01, even tests on estimator-02. Three
estimator versions appear: v2.2.0 up to the 05-30 batch, v2.3.0 from 05-31, v2.3.1
from 06-10. A case passes when `max_abs_error < 1e-7`; the file has no pass/fail
column, so failures below are counted against that limit.

## Finding: a step change in error at v2.3.0 (2026-05-31)

| version | batches | cases | median max_abs_error | mean | failing (≥ 1e-7) |
|---|---|---|---|---|---|
| v2.2.0 | 05-01 … 05-30 | 1530 | 2.96e-10 | 3.97e-10 | 1 (0.07 %) |
| v2.3.0 | 05-31 … 06-09 | 510 | 5.09e-08 | 7.40e-08 | 118 (23.1 %) |
| v2.3.1 | 06-10 … 06-30 | 1020 | 4.78e-08 | 6.95e-08 | 200 (19.6 %) |

- The error jumps by a factor of **about 170 (median 5.09e-8 vs 2.96e-10)** in the
  first batch on v2.3.0, `val-2026-05-31`, and stays there. Every batch from 05-31 on
  has 6–17 failing cases; no batch before it has more than one.
- The whole distribution moves, not a few tests: on v2.3.x the median case error is
  already about half the pass limit, so roughly **1 case in 5** crosses 1e-7 on any
  given night, and which tests fail changes from night to night. That is why it looks
  flaky.
- v2.3.1 did not change anything (same distribution as v2.3.0), consistent with it
  being a packaging release. The defect came in with v2.3.0.
- The mean ratio (about 186×) is a little higher than the median ratio; the v2.2.0 mean
  is pulled up by one isolated outlier (below), so the median is the better summary.

See `error_by_version.png`: every case on a log scale by batch date, coloured by
version, with the 1e-7 limit.

## Ruled out

- **The workers.** estimator-02 is about **17 % slower** (mean runtime 55.8 ms vs
  47.6 ms) throughout the two months, before and after the change, so the speed gap
  is not new and does not line up with the failures. Accuracy is the same on both:

  | worker | median before 05-31 | median from 05-31 | failing from 05-31 |
  |---|---|---|---|
  | estimator-01 | 2.94e-10 | 4.96e-08 | 21.5 % |
  | estimator-02 | 2.99e-10 | 4.80e-08 | 20.1 % |

  Both workers moved by the same factor on the same night. (The v2.2.0 *mean* for
  estimator-02 looks worse, 4.9e-10 vs 3.0e-10, but that is the single outlier below.)
- **Flaky tests.** The only failure before 05-31 is test 1838 on 2026-05-14
  (1.38e-7, estimator-02), a one-off: 1838 passes on every other v2.2.0 night at
  ~3e-10. After 05-31 every one of the 51 tests fails at least twice and none more than 11 times out of 30 nights.
- **Specific test IDs.** No test is consistently failing on v2.3.x; per-test
  baselines differ slightly but every test shifts by about the same factor.

## Conclusion

The nightly failures are an accuracy regression in **estimator release v2.3.0**, first
seen in batch `val-2026-05-31`: `max_abs_error` rose about 170× (from ~3e-10 to
~5e-8 median, ~7e-8 mean) on both workers, enough that about 20 % of cases fail the
1e-7 agreement check every night. It is not a worker or test problem. Recommended:
diff the estimator update between v2.2.0 and v2.3.0 (anything that changed the
covariance or gain computation), and add a nightly guard on the median error per batch
so a step change like this blocks the release rather than surfacing as flaky failures.
