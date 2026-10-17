# Transcript

## Prompt

Test 1847 failed in last night's nightly regression batch (`val-2026-02-18`); the other
50 cases passed. Nobody has looked at it yet, and before tonight's run I'd like to know
whether this is a real problem or a one-off. I've copied that night's logs from the
validation node into this folder: scheduler, validation runner, estimator workers, data
ingest and the system log.

Can you work out what happened to 1847 and why? Write it up in `findings.md` for the
team: what caused it, how that led to the failure, the log lines that show it, anything
you looked at and decided had nothing to do with it, and what we should change.

Please also put your conclusion in `findings.json` so the tracker can pick it up:

```json
{
  "test_id": 1847,
  "root_cause_component": "one of: storage, data-ingest, estimator, scheduler, runner, license, network",
  "root_cause": "one sentence",
  "chain": ["component ids, in causal order, from where it started to the failed test"],
  "evidence": [{"file": "system.log", "line": 12, "note": "what this line shows"}],
  "ruled_out": [{"item": "what you ruled out", "file": "scheduler.log", "line": 30, "reason": "why"}]
}
```

`root_cause_component` is where the chain of events started. Line numbers are 1-based
within each log file.


- `$ Get-ChildItem -Recurse | Select-Object FullName, Length; Get-ChildItem *.log | % { "$($_.Name): $((Get-Content $_).Count)" }`
Small enough to read all.

- `file_read` G:\Willikers\sandbox\demoforge-log-investigation-ksjtphv3\working\system.log
- `file_read` G:\Willikers\sandbox\demoforge-log-investigation-ksjtphv3\working\scheduler.log
- `file_read` G:\Willikers\sandbox\demoforge-log-investigation-ksjtphv3\working\validation-runner.log
- `file_read` G:\Willikers\sandbox\demoforge-log-investigation-ksjtphv3\working\data-ingest.log
- `file_read` G:\Willikers\sandbox\demoforge-log-investigation-ksjtphv3\working\estimator-worker.log
- `file_write` G:\Willikers\sandbox\demoforge-log-investigation-ksjtphv3\working\findings.md
- `file_write` G:\Willikers\sandbox\demoforge-log-investigation-ksjtphv3\working\findings.json
- `$ Get-Content findings.json -Raw | ConvertFrom-Json | Select-Object test_id, root_cause_component`
I've written `findings.md` and `findings.json`, and the JSON parses. Test 1847 failed because the disk filled up during the run, not because of a bug in the estimator. The failure itself is a one-off, but the problems that caused it are still there and could cause it again.

**What happened (chain: storage → data-ingest → estimator → runner):**
1. `/var/validation` was already 95% full before the run started. It reached 100% at 02:15:03 (`system.log:21`). The automatic cleanup only runs when usage is over 98%, so it didn't start until the disk was already full.
2. data-ingest was writing `batch_1847_vectors.csv` at that exact moment. The write failed with "No space left on device" (`data-ingest.log:102`), but the cut-off file, 1180 of 1500 rows, was still marked `READY` (`data-ingest.log:103`). The end-of-run summary still says "0 errors" because it only counts errors from the remote archive.
3. estimator-01 read 1181 rows: the 1180 complete ones plus the cut-off last row. It filled that row's empty field with NaN, and the filter then gave up with 0 states (`estimator-worker.log:170–174`).
4. The runner recorded `'non-finite result'` (`validation-runner.log:99`). That looks like a maths bug in the estimator, but the real cause was the truncated input file.

**Ruled out:** the estimator-02 license timeout, the 1823 retry, the estimator-02 slowdowns, the slow reads from the measurement archive, the network-card message, the scheduler, and a possible estimator regression. Each one either happened on the other worker, was minutes away from the failure, or had no effect on any test. estimator-01 passed 1849 right after 1847.

**Main recommendations:**
- data-ingest must never mark a file `READY` after a write error, and should check the row count against the expected 1500. This is the most important fix.
- Run the disk cleanup before the nightly job, or trigger it earlier.
- The estimator should reject short or incomplete input files with a clear error.

**Before tonight:**
- Re-run 1847 on its own to confirm it passes.
- Check free space on `/var/validation`. Cleanup left it at 70%, which should be enough.
- Someone should find out what writes about 1 GB to `/var/validation` during the run. The 51 exported files add up to only about 2.3 MB, and the logs don't show what the rest is.


## Follow-up

The chain checks out against the logs. One wording fix before I forward this. `findings.md` line 19 says "Cleanup only runs after the disk is completely full", but the logs don't show that. `system.log:22` only says the hook runs when usage is "over 98%". It fired at 100% because that was the next df-monitor sample after the 98% reading at 02:14. Please change that sentence and the matching text in section 48–49 so they say only that.

- `file_read` G:\Willikers\sandbox\demoforge-log-investigation-ksjtphv3\working\findings.md
- `file_edit` G:\Willikers\sandbox\demoforge-log-investigation-ksjtphv3\working\findings.md
- `file_edit` G:\Willikers\sandbox\demoforge-log-investigation-ksjtphv3\working\findings.md
I fixed both places in `findings.md`. The added lines push the second spot from 48–50 down to about 50–52.

- **Lines 19–21 (summary):** now say the cleanup hook runs only when usage is over 98% (`system.log:22`). The 98% reading at 02:14 didn't trigger it, and the next df-monitor sample, at 02:15:03, already showed 100%.
- **"How the pieces fit together", item 1:** now says the 02:14:00 sample at 98% didn't trigger the hook, and it fired on the next sample, which read 100%. I removed the line saying cleanup only starts once the disk is full.

I checked the rest of the file for the same claim and didn't find it again. The timeline row "Retention hook triggers, too late for 1847" is still accurate, and so is the recommendation to run retention before the nightly job. `findings.json` never made this claim, so I left it unchanged.


## End of conversation

The person had nothing more to ask.


## Done
