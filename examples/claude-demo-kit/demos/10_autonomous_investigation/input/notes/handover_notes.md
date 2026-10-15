# Handover: VAL-2026-09

Dmitri Volkov, 2026-09-28. I'm on leave from tomorrow for two weeks; this is where
I got to.

## Status

VAL-2026-09 (v2.4.1, with v2.3.2 planar baseline runs) finished on Saturday and the
runner called it REJECT: pass rate well under the 0.95 in CVT-VAL-002. CCB wants a
root cause before anything else happens to the v2.4 release.

The failures are Doppler runs missing the 0.5 m limit. Planar looks fine on both
builds. Tests are green on release/v2.4 (I re-ran them Sunday evening, see
tests/test_results.txt).

## Theories (none confirmed)

1. **The v2.3 covariance regression is back.** v2.3.0 shipped with the update
   re-using the previous step's S and it took until v2.3.2 to fix. Doppler mode
   brought a lot of churn into the update path, and I haven't checked that the fix
   survived it. The by-build tab in the summary workbook is worth a look.
2. **estimator-02.** It has always been the slow node (15-20 % over the others) and
   the scheduler flagged it again. If it is starving runs of time it could skew the
   campaign.
3. **The Doppler sensor.** Maybe the velocity channel is noisier than the R in the
   config and 0.5 m is simply too tight for Doppler streams. If so this is a plan
   change (CVT-VAL-002 §4), not a code fix. I don't want to relax a limit to make a
   failure go away, though, so this needs evidence either way.

My money is on (1).

## Other

- v2.4.1 was the config-only follow-up to v2.4.0 (per-mode thresholds were missing
  from estimator_config.json).
- The /var/spool/cvt disk warning in the scheduler log has an ops ticket; unrelated.
