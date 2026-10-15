# Validation Plan: Constant-Velocity Tracker Estimator

**Document:** CVT-VAL-002  ·  **Revision:** A  ·  **Date:** 2026-05-12  ·  **Status:** Released
**Applies to:** acceptance campaigns for CVT estimator release candidates, run under
the `VAL-YYYY-MM` campaign naming.

## 1. Purpose

This plan defines how a validation campaign decides whether an estimator release
candidate is accepted. Each run replays a recorded scenario through the estimator on
a validation worker and is scored in metres against the scenario's ground truth.
Campaign results are recorded in the campaign workbook (`validation_results.xlsx`).

## 2. Campaign content

A campaign runs one build of the estimator across the standard scenario classes:

| Scenario   | Profile                                                        |
|------------|----------------------------------------------------------------|
| `cruise`   | straight track at constant speed                               |
| `turn`     | coordinated turns at moderate rate                             |
| `crossing` | two targets crossing; tracks the designated target             |
| `stop-go`  | target stops and restarts                                      |
| `maneuver` | high-acceleration profiles (evasive turns, hard braking)       |

Runs are distributed over the validation workers (`estimator-01`, `estimator-02`).
Per-run timing differs between workers because of their hardware; the runtime limit
in §4 applies to every run regardless of worker.

Recorded per run:

| Field            | Meaning                                                      |
|------------------|--------------------------------------------------------------|
| `RunID`          | Validation run identifier (`VR-####`)                        |
| `Date`           | Execution date (UTC)                                         |
| `Scenario`       | Scenario class (§2)                                          |
| `Build`          | Estimator build under test                                   |
| `Worker`         | Validation worker that executed the run                      |
| `PeakPosError_m` | Peak position error over the run against ground truth, in m  |
| `Runtime_ms`     | Estimator execution time for the run, in ms                  |

## 3. Evaluation

A run **passes** when its peak position error and its runtime are both within the
§4 limits; otherwise it **fails**. The pass rate is the number of passing runs
divided by the number of executed runs, over all scenarios. The campaign is
**ACCEPT** when the pass rate meets the §4 minimum, and **REJECT** otherwise.

The workbook summarises the campaign: total, passed and failed runs, pass rate,
position-error statistics, and the verdict.

## 4. Acceptance limits

| Criterion                | Limit       | Applies to |
|--------------------------|-------------|------------|
| Peak position error      | ≤ 0.5 m     | each run   |
| Runtime                  | ≤ 50 ms     | each run   |
| Pass rate                | ≥ 0.95      | campaign   |

## 5. Change control

The §4 limits are controlled values. Changing any of them requires a revision of
this plan.
