v2.3.0 went out on 30 May, and its release record cites the acceptance campaign
VAL-2026-05: the campaign workbook `validation_results.xlsx` shows ACCEPT. Before the
record is closed, QA wants an independent sign-off review of that workbook against
our validation plan, CVT-VAL-002 Rev A (`validation_plan.md`). Is the ACCEPT right?

Please deliver:

- `validation_results_corrected.xlsx`: the workbook, corrected if anything in it is
  wrong. It's also our template for future campaigns, so keep it formula-driven (no
  pasted values) and don't change the recorded run data.
- `review_note.md`: a short note for the release record with your conclusion and
  what you changed.
- `findings.json`, in this form, with `issues` citing cells of the workbook as you
  received it:

```json
{
  "campaign_verdict": "ACCEPT or REJECT",
  "runs_total": 0,
  "runs_passed": 0,
  "pass_rate": 0.0,
  "failed_runs": ["VR-...."],
  "issues": [{"sheet": "...", "cell": "...", "description": "..."}]
}
```
