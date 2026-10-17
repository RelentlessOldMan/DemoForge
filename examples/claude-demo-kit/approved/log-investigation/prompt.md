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
