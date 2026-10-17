# Test 1847 failure: nightly batch `val-2026-02-18`

## Summary

Test 1847 did not fail because of a regression in the estimator (v2.1.0, build 2.1.0+b412).
It failed because **`/var/validation` ran out of space** at exactly the moment data-ingest
was writing `batch_1847_vectors.csv`. The write failed partway through. **data-ingest logged the
error but still marked the file `READY`**, so the truncated file was dispatched. estimator-01
read a partial last row and turned the empty field into a `NaN`. The Kalman filter then failed
with a non-finite innovation and covariance and returned 0 states. The runner recorded this as
`non-finite result`.

- **Started in:** storage (disk full on `/var/validation`)
- **Made worse by:** a data-ingest bug (a failed write is still published as `READY`)
- **Chain:** storage → data-ingest → estimator → runner

**Real problem or one-off?** The 1847 *result* is a one-off: the input was bad and the estimator
code is fine. The *conditions* that caused it will come back. The disk was already at 95% before
the run started. The cleanup hook runs only when usage is over 98% (system.log:22). The 98%
reading at 02:14 did not trigger it, and by the next df-monitor sample, at 02:15:03, the disk
was already at 100%. Ingest also hides write
errors, so a future disk-full or I/O error will produce the same kind of misleading failure, or
possibly a wrong pass if the truncation happens to land on a row boundary.

## Timeline (all times 2026-02-18, UTC)

| Time | Source | Event |
|---|---|---|
| 01:45:00 | system.log:2 | `/var/validation` already at 18.9G/20.0G (95%) before the run |
| 02:00:00 | system.log:7 | 19.0G (95%) as validation-nightly starts |
| 02:10:00 | system.log:17 | 19.4G (97%) |
| 02:14:00 | system.log:20 | 19.6G (98%). Retention hook does **not** fire (the trigger is "over 98%") |
| 02:15:02.118 | data-ingest.log:101 | Export of `batch_1847_vectors.csv` begins (1500 vectors) |
| 02:15:03 | system.log:21 | **20.0G/20.0G (100%)** |
| 02:15:03.002 | data-ingest.log:102 | **`write failed at offset 37104: [Errno 28] No space left on device`** |
| 02:15:03.004 | data-ingest.log:103 | **Same file marked `1180 rows, 36.2 KB ... status=READY`** |
| 02:15:03 | system.log:22 | Retention hook triggers, too late for 1847 |
| 02:15:08.067 | scheduler.log:71 | 1847 dispatched to estimator-01 (the scheduler waits on READY markers, scheduler.log:5) |
| 02:15:08.271 | estimator-worker.log:170 | `read 1181 measurement rows`: 1180 complete rows plus 1 truncated row |
| 02:15:08.272 | estimator-worker.log:171 | `row 1181 col 2: empty field, value set to NaN` |
| 02:15:08.308 | estimator-worker.log:173 | `step 1181: innovation not finite (z = [0.731, NaN])` |
| 02:15:08.309 | estimator-worker.log:174 | `covariance not finite after step 1181; aborting, 0 states emitted` |
| 02:15:08.380 | validation-runner.log:99 | **`test 1847 FAIL on estimator-01: worker error 'non-finite result'; states=0 expected=1500`** |
| 02:15:18 | system.log:23 | Retention removes 37 old archives and frees 6.1G |
| 02:15:19 | system.log:24 | Disk back to 70%. 1848–1850 export and pass normally |

## How the pieces fit together

1. **Storage.** `/var/validation` went into the night at 95% and filled steadily during the run,
   from 19.0G to 20.0G in about 15 minutes. The retention hook runs only when usage is *over*
   98% (system.log:22). The 98% sample at 02:14:00 did not trigger it. The next df-monitor
   sample, at 02:15:03, read 100%, and the hook fired on that sample.
2. **data-ingest.** The 1847 export hit ENOSPC at byte offset 37104. 37104 B ≈ 36.2 KB, which
   matches the reported size, so the file on disk really is truncated. Instead of failing the
   export, ingest wrote a `status=READY` record for the partial file (1180 rows, about 79% of the
   1500 expected). The end-of-run summary also says `51 exports finished, 0 errors reported by
   archive` (data-ingest.log:110). That line only counts errors from the remote archive, not local
   write errors, so the failure is invisible at summary level.
3. **Scheduler.** The scheduler waits for READY markers (scheduler.log:5). It saw one for 1847 and
   dispatched the test normally. It behaved as designed; it was given a bad signal.
4. **Estimator.** estimator-01 parsed the 1180 complete rows plus the cut-off 1181st row. It
   filled the missing field with `NaN` (a WARN, not an error), ran the filter, and aborted at
   step 1181 when the NaN measurement made the innovation and covariance non-finite. Given that
   input, this is correct behaviour. The same worker passed 1845 and 1849 on either side of it.
   The estimator should still have rejected the input before running: a short row count
   (1181 ≠ 1500) and an empty field are both input errors.
5. **Runner.** The runner reported `'non-finite result'`, which looks like a numerical bug in the
   estimator. The actual cause, a truncated input file, does not appear in the runner log.

## Things I looked at and ruled out

| Item | Where | Why it is not the cause |
|---|---|---|
| estimator-02 license heartbeat timeout | estimator-worker.log:167–168 | Happened on **estimator-02**, but 1847 ran on **estimator-01**. The license was reacquired 1.2 s later with "no task interrupted". estimator-01's own heartbeat at 02:15:02 was ok (line 166). |
| estimator-01 1823 deadline retry | validation-runner.log:50, estimator-worker.log:86 | Same worker but 7 minutes earlier, and a different failure mode (slow response, not non-finite output). 1823 passed on retry with normal numbers. Several estimator-01 tests passed between 1823 and 1847. |
| RT throttling on estimator-02 | system.log:16 | Different worker, at 02:08. All estimator-02 tests passed. |
| estimator-02 slow dispatch acks | scheduler.log:15, 42, 59 | Different worker. The affected tests (1806, 1826, 1838) all passed. |
| meas-archive read latency warnings | data-ingest.log:31, 70 | Remote-read slowness at 02:04 and 02:10. Those exports completed with full row counts. The 1847 failure was a local write error (ENOSPC), not a read problem. |
| NIC link event | system.log:11 | At 02:03:44, 11 minutes before the failure. No link-down and no network errors near 02:15. Ingest kept exporting normally. |
| Estimator build / numerical regression | estimator-worker.log:1–2, 180–182 | Both workers run the same build, and 50/51 tests pass with max_abs_error around 3e-10. estimator-01 passed 1849 right after 1847. The NaN came from the input, not the maths. |
| Scheduler | scheduler.log:4, 71 | Health checks were ok and dispatch followed the parity policy. It acted on the READY marker it was given. |
| Clock drift, apt-daily, ssh sessions, cron | system.log:1, 3–5, 8, 14–15, 18–19, 30 | Unrelated housekeeping. Clock corrections are in the millisecond range. |

## What we should change

1. **data-ingest: never publish READY after a write error** (the most important fix). Any
   `OSError` during export should mark the file `FAILED` and delete or quarantine the partial
   file. Before writing READY, check that the row count equals the manifest (1500) and that the
   checksum is computed over a complete file. The end-of-run summary should count local write
   errors as well as archive errors.
2. **Storage headroom.** The disk was at 95% before the run started. Options:
   - Run retention *before* the nightly job (for example as a pre-start step of
     `validation-nightly.service`) rather than reactively.
   - Trigger retention earlier (for example at ≥90%, and use `>=` rather than `>`), and/or have
     the scheduler refuse to start a batch below a free-space floor.
   - Find out what is writing about 1 GB to `/var/validation` during the run. The 51 exports add
     up to only about 2.3 MB, so most of the growth comes from somewhere else. These logs don't
     show what it is.
3. **Estimator: validate input before filtering.** Reject files with a short row count or
   empty/unparseable fields with a clear error (for example `input truncated: 1181/1500 rows`)
   instead of filling in NaN and running the filter.
4. **Runner: report the input-error category** so that infrastructure failures are not
   misread as numerical regressions.
5. **Immediate action:** re-run test 1847 alone (ingest + estimate) and check that it passes,
   and check `/var/validation` free space before tonight's run. After retention it was at 70%,
   so tonight should have enough room.
