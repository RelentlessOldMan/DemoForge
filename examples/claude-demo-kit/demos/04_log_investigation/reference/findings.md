# Test 1847, batch val-2026-02-18: failure investigation

## Summary

Test 1847 did not fail because of the estimator. The validation volume
`/var/validation` (20G quota) filled up at 02:15:03 while data-ingest was writing
test 1847's measurement file. The write failed with `ENOSPC` after 1180 of the 1500
rows, but the export step still published the file as `READY`. estimator-01 then read
the short file, parsed the half-written last row as NaN, and the filter went
non-finite at step 1181. The runner only saw "non-finite result". A retention cleanup
freed 6.1G fifteen seconds later, so by morning the disk looked fine.

This is real, not a one-off: the volume sat at 95 % before the batch started and will
fill again unless retention runs before the batch.

## Chain of events

1. **Volume near full before the batch.** df-monitor shows `/var/validation` at 95 %
   (19.0G/20.0G) at 02:00 (`system.log:7`), 96 % at 02:05, 97 % at 02:10 and 98 % at
   02:14 (`system.log:20`).
2. **Disk full during 1847's export.** At 02:15:03.002 data-ingest logs
   `write failed at offset 37104: [Errno 28] No space left on device` for
   `batch_1847_vectors.csv` (`data-ingest.log:102`); df-monitor reports 100 % the same
   second (`system.log:21`).
3. **Short file published anyway.** Two milliseconds later the same export is logged
   as `1180 rows, 36.2 KB ... status=READY` (`data-ingest.log:103`). Every other
   export that night is 1500 rows and about 46 KB. The run summary still says
   "0 errors reported by archive", so nothing downstream was told.
4. **Estimator reads the partial row.** estimator-01 reads 1181 rows (1180 complete
   rows plus the row the failed write cut off) (`estimator-worker.log:170`); row 1181
   has an empty second field and is set to NaN (`:171`).
5. **Filter goes non-finite.** The innovation at step 1181 is not finite (`:173`), the
   covariance follows and the worker aborts with 0 states (`:174`).
6. **Runner fails the test.** `test 1847 FAIL on estimator-01: worker error
   'non-finite result'; states=0 expected=1500` (`validation-runner.log:99`).
7. **Evidence disappears.** The retention hook removes 37 old archives and frees 6.1G
   at 02:15:18 (`system.log:23`); the volume is at 70 % from then on.

## Ruled out

- **estimator-02 license heartbeat timeout at 02:15:06** (`estimator-worker.log:167`):
  close in time, but 1847 ran on estimator-01; estimator-02 reacquired the license
  1.2 s later with no task interrupted (`:168`).
- **Test 1823 soft-deadline retry** (`validation-runner.log:50`): a different test on
  the same worker seven minutes earlier; it passed on retry with a normal error of
  2.75e-10 (`:51`).
- **estimator-02 slowness** (slow-to-ack warnings, `scheduler.log:15`, `:42`, `:59`;
  RT throttling, `system.log:16`): it is the older, slower node. All its tests passed
  and it never ran 1847.
- **meas-archive read latency** (`data-ingest.log:70`): affected 1812 and 1831, both
  exported 1500 rows and passed.

## Recommended changes

1. **Export must fail closed.** data-ingest should treat a write error as a failed
   export, verify the written row count against the manifest (1500) before writing
   `READY`, and report it in the run summary.
2. **Estimator must reject bad input.** A non-finite or malformed measurement should be
   rejected and reported, not propagated into the state, and a row count different
   from the manifest should fail the load.
3. **Keep headroom on `/var/validation`.** Run the retention cleanup before the 02:00
   batch (not only as a reaction at 98 %), and alert well below the quota.
4. Re-run test 1847 to confirm it passes on a complete input.
