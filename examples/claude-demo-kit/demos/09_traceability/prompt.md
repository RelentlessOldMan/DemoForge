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
