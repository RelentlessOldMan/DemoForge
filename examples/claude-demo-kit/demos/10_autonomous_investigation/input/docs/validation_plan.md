# Validation Plan: Constant-Velocity Tracker Estimator

**Document:** CVT-VAL-002  ·  **Revision:** A  ·  **Date:** 2026-05-12  ·  **Status:** Released
**Covers:** acceptance of a CVT estimator release by validation campaign.

## 1. Purpose

This plan defines how a validation campaign judges an estimator release. Each run
replays a recorded field measurement stream (1500 measurements) through the
estimator on a validation worker and scores the estimate against ground truth.

## 2. Data recorded per run

| Field              | Meaning                                                      |
|--------------------|--------------------------------------------------------------|
| `run_id`           | Validation run identifier (`VR-####`).                       |
| `mode`             | Measurement mode of the recorded stream (`planar`, ...).     |
| `measurement_dim`  | Measurement dimension of that mode.                          |
| `build`            | Estimator release under test (e.g. `v2.4.1`).                |
| `worker`           | Validation worker that executed the run.                     |
| `max_pos_error_m`  | Peak position error over the run against ground truth, m.    |
| `runtime_ms`       | Estimator execution time for the run, ms.                    |
| `status`           | `PASS` or `FAIL` against §4.                                 |

Campaigns are named `VAL-YYYY-MM`. A campaign may include baseline runs on the
previous release for comparison.

## 3. Procedure

The validation runner scores each run as it completes and writes
`validation_runs.csv`. The campaign summary workbook (`validation_summary.xlsx`)
carries totals, the pass rate and the verdict, with breakdowns by mode, build and
worker.

## 4. Acceptance criteria

A run **passes** when both per-run limits hold. The campaign is **ACCEPT** only if
the pass rate meets the minimum.

| Criterion              | Limit            | Applies to |
|------------------------|------------------|------------|
| Max position error     | **≤ 0.5 m**      | each run   |
| Max runtime            | **≤ 50 ms**      | each run   |
| Minimum pass rate      | **≥ 0.95**       | campaign   |

## 5. Change control

The limits in §4 are controlled values. Changing them requires a revision of this
plan.
