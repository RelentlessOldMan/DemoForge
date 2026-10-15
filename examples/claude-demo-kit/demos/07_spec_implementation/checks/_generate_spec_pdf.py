"""Build input/CVT-SRS-003.pdf: CVT-SRS-003 Rev C, the specification the agent implements from.

Provenance only. NOT run during verification: the harness is Octave and never reads
the PDF. This script only has to lay out a credible, text-extractable specification.

Run with a python that has matplotlib (renders selectable vector text to a multi-page
PDF; the system interpreter here has it):

    python checks/_generate_spec_pdf.py

The same PDF is shipped by demo 10 (docs/CVT-SRS-003.pdf). After regenerating, copy
the output there byte for byte so both demos carry the identical Rev C document.

Facts follow examples/claude-demo-kit/STORY.md: Rev B (2026-04-20) introduced the gate
for v2.3.0 with gamma fixed at 5.991 (95 %, m = 2); Rev C (2026-09-08, CCB-2026-114)
makes gamma configuration (chi-squared critical value for the configured confidence and
the active mode's measurement dimension, default 99 %) and adds Doppler mode (m = 4).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42  # embed TrueType so text extracts cleanly
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

OUT = Path(__file__).resolve().parent.parent / "input" / "CVT-SRS-003.pdf"

FOOTER = "CVT-SRS-003 Rev C  ·  Released 2026-09-08  ·  Page %d of %d"

# Each string is one page, laid out as monospace text.
PAGES = [
    r"""CVT ESTIMATOR — SOFTWARE REQUIREMENTS SPECIFICATION

Document:   CVT-SRS-003
Revision:   C
Date:       2026-09-08
Status:     Released
Change ref: CCB-2026-114 (v2.4.0 scope)
Approved:   Priya Raman, estimator lead


REVISION HISTORY

  Rev  Date        Change
  ---  ----------  ------------------------------------------------------
  A    2025-12-15  Initial release: §1–§6, §7.1, §7.2, §7.4.
  B    2026-04-20  Adds §7.3 measurement validation gate for v2.3.
                   Threshold fixed in this document at 5.991
                   (chi-squared, 95 % confidence, m = 2).
  C    2026-09-08  §7.3 revised for v2.4: the threshold becomes a
                   configuration value that depends on the confidence
                   level and on the measurement dimension of the active
                   mode. Adds Doppler mode (§2, §6). Adds Appendix A,
                   the fail-closed rules of §7.3.5 and requirements
                   G1–G5.


1. SCOPE

This specification defines software requirements for the Constant-Velocity
Tracker (CVT) state estimator and its measurement-processing front end. The
core recursion (predict/update) is specified separately in CVT-EST-001; this
document specifies the surrounding measurement-processing behaviour.

The implementation language is MATLAB (executed on GNU Octave for
validation).


2. DEFINITIONS

  state           x = [px; py; vx; vy]  (position and velocity, 2-D)
  measurement     z = H x + noise; its dimension m depends on the mode
  planar mode     position-only sensor: z = [px; py], H = [I2 0], m = 2
  Doppler mode    position and velocity sensor (v2.4 onward):
                  z = [px; py; vx; vy], H = I4, m = 4
  innovation      y = z - H x            (measurement residual, m-by-1)
  innovation      S = H P H' + R         (m-by-m)
   covariance
  NIS             normalized innovation squared (see 7.3.1)
  gate            a test that admits or rejects a measurement before
                  it is applied in the update
""",
    r"""3. APPLICABLE DOCUMENTS

  CVT-EST-001   State Estimator Specification, Rev C (2026-03-02)
  CVT-VAL-002   Validation Plan, Rev A (2026-05-12)


4. MEASUREMENT INTERFACE

Measurements arrive as the rows of an N-by-m matrix Z, where m is the
measurement dimension of the active mode. Row k is z_k. The estimator
processes them in order. Timestamps, framing and transport are out of scope
for this document.

The active mode is selected by configuration (estimator_config.json,
key active_mode). A campaign run may override it per run.


5. STATE INITIALISATION

Initial state x0 and covariance P0 are supplied in model.json and are not
redefined here. See CVT-EST-001 §2.3.


6. PROCESS AND MEASUREMENT MODELS

The process model F and process noise Q are as defined in CVT-EST-001. The
measurement model H and measurement noise R are per mode:

  planar    H = [I2 0] (2-by-4), R from model.json (2-by-2)
  Doppler   H = I4     (4-by-4), R from the mode entry in
            estimator_config.json (4-by-4)

This document adds no new constants to the process model.


7. MEASUREMENT PROCESSING

7.1 Innovation computation

    For each measurement the front end forms the innovation y and its
    covariance S from the current predicted state, exactly as in
    CVT-EST-001 §4.2. These are the inputs to the gate of §7.3.

7.2 Ordering

    Measurements are gated in arrival order. Gating has no memory between
    measurements; each decision depends only on that measurement's (y, S)
    and the threshold in force.
""",
    r"""7.3 MEASUREMENT VALIDATION GATE

Rationale. On 2026-02-18 (validation batch val-2026-02-18, test 1847) a
truncated input file put a non-finite measurement into the filter, and the
non-finite value propagated through the state. CVT-EST-001 Rev C added
requirement R6: non-finite or malformed measurements shall be rejected and
reported, never propagated into the state. This gate implements R6 and also
screens statistically implausible measurements.

Rev B of this document introduced the gate for v2.3.0 with a fixed
threshold of 5.991 (95 % confidence, m = 2). Rev C supersedes that: with
Doppler mode the measurement dimension is no longer always 2, so the
threshold is a configuration value (7.3.3).

7.3.1 Normalized innovation squared (NIS)

    For a measurement with innovation y (m-by-1) and innovation covariance
    S (m-by-m, symmetric positive definite), the normalized innovation
    squared is

        d2 = y' * inv(S) * y

    Compute d2 by solving S x = y (x = S \ y in MATLAB) and forming
    d2 = y' * x. Do not form inv(S) explicitly.

7.3.2 Gate decision

    The gate admits the measurement if and only if

        d2 <= gamma

    where gamma is the gate threshold (7.3.3). A measurement with d2
    exactly equal to gamma is admitted. If d2 > gamma the measurement is
    rejected as a statistical outlier.

7.3.3 Gate threshold

    Under the hypothesis of a valid measurement, d2 is chi-squared
    distributed with m degrees of freedom. gamma is the chi-squared
    critical value for m degrees of freedom at the configured confidence
    level, where m is the measurement dimension of the active mode
    (Appendix A). The confidence level is a configuration item; the
    default is 99 %.

    gamma is resolved from the configuration by the caller and supplied to
    the gate as a parameter. The gate itself holds no threshold value.
""",
    r"""7.3.4 Required interface

    The gate is this MATLAB function:

        [accept, d2] = measurement_gate(y, S, gamma)

      y       m-by-1 innovation vector.
      S       m-by-m innovation covariance (symmetric positive definite).
      gamma   scalar gate threshold (a chi-squared critical value).
      accept  logical scalar: true iff the measurement passes the gate.
      d2      scalar normalized innovation squared (7.3.1).

    The function SHALL be pure: no file access, no printing, no globals.
    It SHALL work for any measurement dimension m.

7.3.5 Boundary conditions (fail closed)

    G-BC-1  If any element of y or S is non-finite (NaN or +/-Inf), or
            gamma is not a finite positive scalar, the gate SHALL reject
            the measurement: return accept = false and d2 = Inf. A
            malformed measurement or threshold must never lead to a
            measurement being admitted.

    G-BC-2  The gate SHALL NOT raise an error for the inputs of G-BC-1;
            it returns the rejecting result of G-BC-1.

7.3.6 Requirements summary

    G1  Compute d2 per 7.3.1 (solving S x = y; not forming inv(S)).
    G2  Admit iff d2 <= gamma (7.3.2).
    G3  Use the supplied gamma (7.3.3); the gate holds no threshold of
        its own.
    G4  Fail closed on non-finite y or S and on a non-finite or
        non-positive gamma (G-BC-1), without error (G-BC-2).
    G5  Be accompanied by a runnable test that exercises G1–G4.


7.4 LOGGING

    Rejected measurements may be logged with their d2 for later analysis.
    Logging format and transport are out of scope for this document.
""",
    r"""8. VERIFICATION

    The gate is verified by exercising measurement_gate over recorded
    innovation streams from both modes, confirming d2 and the accept/reject
    decisions against this specification, and confirming the boundary
    behaviour of 7.3.5.


APPENDIX A — CHI-SQUARED CRITICAL VALUES

    Critical value gamma of the chi-squared distribution, by degrees of
    freedom (DOF = measurement dimension m) and confidence level:

        DOF |   95 %   |   99 %   |  99.9 %
       -----+----------+----------+----------
          1 |   3.841  |   6.635  |  10.828
          2 |   5.991  |   9.210  |  13.816
          3 |   7.815  |  11.345  |  16.266
          4 |   9.488  |  13.277  |  18.467

    Measurement dimensions of the defined modes are given in §2.


                              --- END OF DOCUMENT ---
""",
]


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    n = len(PAGES)
    # Fixed metadata so a rerun is byte-stable apart from what matplotlib controls.
    meta = {"Title": "CVT-SRS-003 Rev C", "Author": "CVT estimator team",
            "CreationDate": None}
    with PdfPages(OUT, metadata=meta) as pdf:
        for i, text in enumerate(PAGES, start=1):
            fig = plt.figure(figsize=(8.5, 11))
            fig.text(0.08, 0.95, text, va="top", ha="left",
                     family="DejaVu Sans Mono", fontsize=8.5)
            fig.text(0.5, 0.03, FOOTER % (i, n), ha="center", va="bottom",
                     family="DejaVu Sans Mono", fontsize=7)
            pdf.savefig(fig)
            plt.close(fig)
    print(f"wrote {OUT}  ({n} pages)")


if __name__ == "__main__":
    main()
