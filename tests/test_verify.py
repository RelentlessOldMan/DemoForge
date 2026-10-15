"""Verify pipeline: work-dir staging, harness execution, check evaluation."""

from __future__ import annotations

import json
import shutil
import sys

import pytest

from conftest import CLAUDE_DEMO_KIT, OCTAVE, requires_octave

from demoforge.discovery import load_content_set
from demoforge.errors import DemoError, DemoForgeError
from demoforge.model import Demo
from demoforge.verify import stage_work_dir, verify_demo

try:
    import numpy  # noqa: F401
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False
requires_numpy = pytest.mark.skipif(not _HAS_NUMPY, reason="numpy not available")

try:
    import openpyxl  # noqa: F401
    _HAS_OPENPYXL = True
except ImportError:
    _HAS_OPENPYXL = False
requires_openpyxl = pytest.mark.skipif(not _HAS_OPENPYXL, reason="openpyxl not available")


def _python_set(tmp_path, src):
    """Clone one demo into a temp content set that runs python as the test interpreter."""
    root = tmp_path / "set"
    (root / "demos").mkdir(parents=True)
    shutil.copytree(src, root / "demos" / src.name)
    (root / "demoforge.toml").write_text(
        f'[set]\nid = "t"\n\n[runtimes]\npython = {json.dumps(sys.executable)}\n',
        encoding="utf-8",
    )
    return load_content_set(root)


def _demo(tmp_path, **over) -> Demo:
    data = {"id": "d", "title": "D", "inputs": ["input/a.txt"], **over}
    return Demo.from_yaml(data, dir=tmp_path)


def test_stage_work_dir_flattens_inputs_and_artifacts(tmp_path):
    demo_dir = tmp_path / "demo"
    (demo_dir / "input").mkdir(parents=True)
    (demo_dir / "input" / "a.txt").write_text("input-a", encoding="utf-8")

    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "produced.txt").write_text("made-it", encoding="utf-8")

    demo = _demo(demo_dir)
    dest = tmp_path / "work"
    stage_work_dir(demo, [artifacts], dest)

    assert (dest / "a.txt").read_text(encoding="utf-8") == "input-a"
    assert (dest / "produced.txt").read_text(encoding="utf-8") == "made-it"


def test_artifacts_override_inputs(tmp_path):
    demo_dir = tmp_path / "demo"
    (demo_dir / "input").mkdir(parents=True)
    (demo_dir / "input" / "a.txt").write_text("original", encoding="utf-8")
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "a.txt").write_text("overwritten", encoding="utf-8")

    stage_work_dir(_demo(demo_dir), [artifacts], tmp_path / "work")
    assert (tmp_path / "work" / "a.txt").read_text(encoding="utf-8") == "overwritten"


def test_stage_missing_input_errors(tmp_path):
    demo = _demo(tmp_path / "demo")  # input/a.txt was never created
    (tmp_path / "demo").mkdir()
    with pytest.raises(DemoError, match="declared input is missing"):
        stage_work_dir(demo, [], tmp_path / "work")


def test_verify_without_harness_evaluates_checks(tmp_path):
    """No runtime needed: file_exists/metric checks run against the staged dir."""
    demo_dir = tmp_path / "demo"
    (demo_dir / "input").mkdir(parents=True)
    (demo_dir / "input" / "seed.txt").write_text("x", encoding="utf-8")
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "result.out").write_text("ok", encoding="utf-8")

    demo = Demo.from_yaml(
        {
            "id": "d",
            "title": "D",
            "inputs": ["input/seed.txt"],
            "checks": [{"id": "made", "kind": "file_exists", "pattern": "result.out"}],
        },
        dir=demo_dir,
    )
    cs = load_content_set(_fake_set(tmp_path))
    outcome = verify_demo(demo, cs, artifacts_dirs=[artifacts], work_dir=tmp_path / "work")
    assert outcome.harness_ran is False
    assert outcome.passed is True
    assert outcome.results.checks[0].passed is True


def _fake_set(tmp_path):
    root = tmp_path / "set"
    root.mkdir()
    (root / "demoforge.toml").write_text('[set]\nid = "s"\n', encoding="utf-8")
    return root


@pytest.mark.parametrize(
    "body, match",
    [("{not json", "not valid JSON"), ("[1, 2, 3]", "must contain a JSON object")],
)
def test_verify_rejects_malformed_metrics(tmp_path, body, match):
    """A bad metrics file fails loudly instead of silently yielding no metrics."""
    demo_dir = tmp_path / "demo"
    (demo_dir / "input").mkdir(parents=True)
    (demo_dir / "input" / "a.txt").write_text("x", encoding="utf-8")
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "metrics.json").write_text(body, encoding="utf-8")

    demo = _demo(demo_dir)  # runtime none, no harness -> metrics read straight from artifacts
    cs = load_content_set(_fake_set(tmp_path))
    with pytest.raises(DemoForgeError, match=match):
        verify_demo(demo, cs, artifacts_dirs=[artifacts], work_dir=tmp_path / "work")


# ---- Octave integration ------------------------------------------------
@requires_octave
def test_verify_demo2_with_reference_passes():
    cs = load_content_set(CLAUDE_DEMO_KIT)
    demo = next(d for d in cs.demos() if d.id == "matlab-optimization")
    work = cs.runs_dir / "_verify_test" / demo.id
    outcome = verify_demo(
        demo, cs,
        artifacts_dirs=[demo.dir / "reference"],
        work_dir=work,
        octave_bin=OCTAVE,
    )
    assert outcome.harness_ran and outcome.harness_ok
    assert outcome.passed is True
    # Calibration sanity: the reference solution clears the bounds with margin.
    assert outcome.metrics["max_abs_error"] < 1e-9
    assert outcome.metrics["speedup"] >= 3.0
    assert outcome.metrics["n_vectors"] == 1500
    by_id = {c.id: c for c in outcome.results.checks}
    assert by_id["equivalence"].passed and by_id["speedup"].passed


@requires_octave
def test_verify_demo1_implementation_with_reference():
    cs = load_content_set(CLAUDE_DEMO_KIT)
    demo = next(d for d in cs.demos() if d.id == "matlab-implementation")
    work = cs.runs_dir / "_verify_test" / demo.id
    outcome = verify_demo(
        demo, cs,
        artifacts_dirs=[demo.dir / "reference"],
        work_dir=work,
        octave_bin=OCTAVE,
    )
    assert outcome.harness_ran and outcome.harness_ok
    assert outcome.passed is True
    assert outcome.metrics["max_abs_error"] < 1e-9  # reference reproduces itself exactly
    assert outcome.metrics["n_vectors"] == 1500
    by_id = {c.id: c for c in outcome.results.checks}
    assert by_id["produced_implementation"].passed and by_id["correct"].passed
    # The hidden reference output is never offered to the agent as an input.
    assert all("reference_states" not in p.name for p in demo.input_paths())


@requires_numpy
def test_verify_demo3_python_with_reference(tmp_path):
    """python-runtime harness: port vs the hidden MATLAB reference (no Octave)."""
    src = CLAUDE_DEMO_KIT / "demos" / "03_matlab_python_port"
    root = tmp_path / "set"
    (root / "demos").mkdir(parents=True)
    shutil.copytree(src, root / "demos" / "03_matlab_python_port")
    # Use the test interpreter (has numpy) as the python runtime.
    (root / "demoforge.toml").write_text(
        f'[set]\nid = "t"\n\n[runtimes]\npython = {json.dumps(sys.executable)}\n',
        encoding="utf-8",
    )
    cs = load_content_set(root)
    demo = cs.demos()[0]
    outcome = verify_demo(
        demo, cs, artifacts_dirs=[src / "reference"], work_dir=tmp_path / "work"
    )
    assert outcome.harness_ran and outcome.harness_ok
    assert outcome.passed is True
    assert outcome.metrics["max_abs_error"] < 1e-9
    assert outcome.metrics["n_vectors"] == 1500
    # The hidden reference must never be staged into the agent's view (it's in checks/,
    # not input/); confirm it isn't among the demo's declared inputs.
    assert all("reference_states" not in p.name for p in demo.input_paths())


@requires_octave
def test_verify_fails_when_fast_impl_missing(tmp_path):
    """Empty artifacts -> harness can't find kalman_update_fast.m -> fail."""
    cs = load_content_set(CLAUDE_DEMO_KIT)
    demo = next(d for d in cs.demos() if d.id == "matlab-optimization")
    empty = tmp_path / "empty"
    empty.mkdir()
    outcome = verify_demo(
        demo, cs, artifacts_dirs=[empty], work_dir=tmp_path / "work", octave_bin=OCTAVE
    )
    assert outcome.harness_ran and not outcome.harness_ok
    assert outcome.passed is False


def test_verify_demo4_log_investigation_with_reference(tmp_path):
    """stdlib-only harness validates findings.json citations against the staged logs.

    Positive: the reference passes. Negative: a keyword-stuffed report whose
    findings.json blames the license decoy must NOT verify.
    """
    src = CLAUDE_DEMO_KIT / "demos" / "04_log_investigation"
    cs = _python_set(tmp_path, src)
    demo = cs.demos()[0]
    outcome = verify_demo(
        demo, cs, artifacts_dirs=[src / "reference"], work_dir=tmp_path / "work"
    )
    assert outcome.harness_ran and outcome.harness_ok
    assert outcome.passed is True
    by_id = {c.id: c for c in outcome.results.checks}
    assert all(
        by_id[k].passed
        for k in ("cause_ok", "citations_exist", "evidence_enospc",
                  "evidence_truncation", "evidence_nonfinite")
    )

    ref = json.loads((src / "reference" / "findings.json").read_text(encoding="utf-8"))
    ref["root_cause_component"] = "license"
    ref["root_cause"] = "estimator-02 lost its license heartbeat (disk 100% ENOSPC 1180 truncated)"
    bad = tmp_path / "bad"
    bad.mkdir()
    shutil.copy2(src / "reference" / "findings.md", bad / "findings.md")
    (bad / "findings.json").write_text(json.dumps(ref), encoding="utf-8")
    bad_outcome = verify_demo(demo, cs, artifacts_dirs=[bad], work_dir=tmp_path / "work_bad")
    assert bad_outcome.passed is False
    assert not {c.id: c for c in bad_outcome.results.checks}["cause_ok"].passed
    # Only the raw logs are inputs — the findings answer key is never staged to the agent.
    assert all("findings" not in p.name for p in demo.input_paths())


def test_verify_demo6_csv_analysis_with_reference(tmp_path):
    """python-runtime demo with a stdlib-only harness: runs under any interpreter.

    Uses the test interpreter as the python runtime (the harness needs no third-party
    libs), so this always runs — no numpy/pandas required.
    """
    src = CLAUDE_DEMO_KIT / "demos" / "06_csv_analysis"
    root = tmp_path / "set"
    (root / "demos").mkdir(parents=True)
    shutil.copytree(src, root / "demos" / "06_csv_analysis")
    (root / "demoforge.toml").write_text(
        f'[set]\nid = "t"\n\n[runtimes]\npython = {json.dumps(sys.executable)}\n',
        encoding="utf-8",
    )
    cs = load_content_set(root)
    demo = cs.demos()[0]
    outcome = verify_demo(
        demo, cs, artifacts_dirs=[src / "reference"], work_dir=tmp_path / "work"
    )
    assert outcome.harness_ran and outcome.harness_ok
    assert outcome.passed is True
    assert outcome.metrics["regression_version"] == "v2.3.0"
    assert outcome.metrics["error_factor"] > 10   # the regression dwarfs normal variation
    assert outcome.metrics["n_rows"] == 3060
    by_id = {c.id: c for c in outcome.results.checks}
    assert by_id["produced_plot"].passed and by_id["start_date_ok"].passed
    assert by_id["factor_ok"].passed and by_id["per_version_ok"].passed


@requires_octave
def test_verify_demo7_spec_implementation_with_reference(tmp_path):
    """octave-runtime demo: the gate implemented from the PDF spec vs a hidden reference.

    Positive: the reference gate reproduces the spec exactly. Negative: an
    implementation that ignores the fail-closed boundary condition must NOT verify,
    proving the §7.3.5 requirement is genuinely enforced.
    """
    cs = load_content_set(CLAUDE_DEMO_KIT)
    demo = next(d for d in cs.demos() if d.id == "spec-implementation")

    outcome = verify_demo(
        demo, cs,
        artifacts_dirs=[demo.dir / "reference"],
        work_dir=cs.runs_dir / "_verify_test" / demo.id,
        octave_bin=OCTAVE,
    )
    assert outcome.harness_ran and outcome.harness_ok
    assert outcome.passed is True
    assert outcome.metrics["max_abs_error"] < 1e-9     # reference reproduces the spec
    assert outcome.metrics["accept_mismatches"] == 0
    assert outcome.metrics["nonfinite_handled"] == 1
    assert outcome.metrics["n_vectors"] == 24
    by_id = {c.id: c for c in outcome.results.checks}
    assert by_id["nis_correct"].passed and by_id["handles_nonfinite"].passed
    assert by_id["gamma_honoured"].passed and by_id["tests_have_teeth"].passed
    # The hidden reference is never offered to the agent as an input.
    assert all("_ref" not in p.name for p in demo.input_paths())

    # Negative: a gate that computes NIS correctly but admits non-finite input (no
    # fail-closed guard) must fail handles_nonfinite and not verify.
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "measurement_gate.m").write_text(
        "function [accept, d2] = measurement_gate(y, S, gamma)\n"
        "  d2 = y' * ((S + S')/2 \\ y);\n"   # no non-finite guard
        "  accept = (d2 <= gamma);\n"
        "end\n",
        encoding="utf-8",
    )
    (bad / "test_stub.m").write_text("% present so file_exists passes\n", encoding="utf-8")
    bad_outcome = verify_demo(
        demo, cs, artifacts_dirs=[bad],
        work_dir=tmp_path / "work_bad", octave_bin=OCTAVE,
    )
    assert bad_outcome.harness_ran and bad_outcome.harness_ok
    assert bad_outcome.passed is False
    assert bad_outcome.metrics["nonfinite_handled"] == 0


@requires_octave
def test_verify_demo8_verification_with_reference():
    cs = load_content_set(CLAUDE_DEMO_KIT)
    demo = next(d for d in cs.demos() if d.id == "verification")
    work = cs.runs_dir / "_verify_test" / demo.id
    outcome = verify_demo(
        demo, cs, artifacts_dirs=[demo.dir / "reference"], work_dir=work, octave_bin=OCTAVE
    )
    assert outcome.harness_ran and outcome.harness_ok
    assert outcome.passed is True
    # The planted defect is invisible on the default model but large once the initial
    # state actually matters.
    assert outcome.metrics["default_discrepancy"] < 1e-9
    assert outcome.metrics["init_discrepancy"] > 1.0
    by_id = {c.id: c for c in outcome.results.checks}
    assert by_id["tests_catch_init_defects"].passed and by_id["findings_pins_defect"].passed
    # The hidden correct reference is never offered to the agent as an input.
    assert all("_ref" not in p.name for p in demo.input_paths())


@requires_openpyxl
def test_verify_demo5_excel_investigation_with_reference(tmp_path):
    """python-runtime demo whose harness reads the agent's corrected .xlsx with openpyxl.

    Also a negative case: the uncorrected workbook (defect intact) must FAIL, proving
    the planted defect genuinely drives the verdict rather than passing vacuously.
    """
    src = CLAUDE_DEMO_KIT / "demos" / "05_excel_investigation"
    root = tmp_path / "set"
    (root / "demos").mkdir(parents=True)
    shutil.copytree(src, root / "demos" / "05_excel_investigation")
    (root / "demoforge.toml").write_text(
        f'[set]\nid = "t"\n\n[runtimes]\npython = {json.dumps(sys.executable)}\n',
        encoding="utf-8",
    )
    cs = load_content_set(root)
    demo = cs.demos()[0]

    # Positive: the corrected reference restores the 0.5 m tolerance -> REJECT.
    outcome = verify_demo(
        demo, cs, artifacts_dirs=[src / "reference"], work_dir=tmp_path / "work"
    )
    assert outcome.harness_ran and outcome.harness_ok
    assert outcome.passed is True
    assert outcome.metrics["verdict_reject"] == 1           # verdict flips to REJECT
    assert outcome.metrics["n_failing_runs"] == 6           # the maneuver runs
    by_id = {c.id: c for c in outcome.results.checks}
    assert by_id["criteria_match_plan"].passed and by_id["verdict_follows_plan"].passed

    # Negative: hand it the uncorrected workbook under a corrected name. The 5.0 m
    # tolerance is intact, so everything "passes" and the demo must NOT verify.
    bad = tmp_path / "bad"
    bad.mkdir()
    shutil.copy2(
        src / "input" / "validation_results.xlsx",
        bad / "validation_results_corrected.xlsx",
    )
    for name in ("review_note.md", "findings.json"):
        shutil.copy2(src / "reference" / name, bad / name)
    bad_outcome = verify_demo(demo, cs, artifacts_dirs=[bad], work_dir=tmp_path / "work_bad")
    assert bad_outcome.harness_ran and bad_outcome.harness_ok  # harness runs fine...
    assert bad_outcome.passed is False                         # ...but the checks catch it
    assert bad_outcome.metrics["verdict_reject"] == 0
    # The hidden reference workbook is never offered to the agent as an input.
    assert all("corrected" not in p.name for p in demo.input_paths())


@requires_openpyxl
def test_verify_demo9_traceability_with_reference(tmp_path):
    """python-runtime demo whose harness reads the agent's .xlsx with openpyxl."""
    src = CLAUDE_DEMO_KIT / "demos" / "09_traceability"
    root = tmp_path / "set"
    (root / "demos").mkdir(parents=True)
    shutil.copytree(src, root / "demos" / "09_traceability")
    (root / "demoforge.toml").write_text(
        f'[set]\nid = "t"\n\n[runtimes]\npython = {json.dumps(sys.executable)}\n',
        encoding="utf-8",
    )
    cs = load_content_set(root)
    demo = cs.demos()[0]
    outcome = verify_demo(
        demo, cs, artifacts_dirs=[src / "reference"], work_dir=tmp_path / "work"
    )
    assert outcome.harness_ran and outcome.harness_ok
    assert outcome.passed is True
    assert outcome.metrics["n_requirements_traced"] == 6   # all of R1..R6 traced
    assert outcome.metrics["r6_gap_flagged"] == 1          # the headline gap is flagged
    by_id = {c.id: c for c in outcome.results.checks}
    assert by_id["produced_matrix"].passed and by_id["traced_all_requirements"].passed


# ---- structured (directory-tree) inputs --------------------------------
def test_stage_preserves_input_tree_structure(tmp_path):
    """Inputs keep their path relative to ``input/`` so a demo can stage a repo tree."""
    demo_dir = tmp_path / "demo"
    for rel, body in [
        ("input/README.md", "top"),
        ("input/src/gate.m", "impl"),
        ("input/docs/README.md", "nested"),   # same basename, different dir
    ]:
        f = demo_dir / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body, encoding="utf-8")

    demo = Demo.from_yaml(
        {
            "id": "d", "title": "D",
            "inputs": ["input/README.md", "input/src/gate.m", "input/docs/README.md"],
        },
        dir=demo_dir,
    )
    dest = tmp_path / "work"
    stage_work_dir(demo, [], dest)

    assert (dest / "README.md").read_text(encoding="utf-8") == "top"
    assert (dest / "src" / "gate.m").read_text(encoding="utf-8") == "impl"
    # The nested same-named file must not have clobbered the top-level one.
    assert (dest / "docs" / "README.md").read_text(encoding="utf-8") == "nested"


@pytest.mark.parametrize("bad", ["../escape.txt", "input/../../escape.txt", "/abs.txt"])
def test_inputs_may_not_escape_the_demo(tmp_path, bad):
    """Staging writes into a working copy, so inputs must stay inside the demo."""
    with pytest.raises(DemoError, match="must be a relative path inside the demo"):
        Demo.from_yaml({"id": "d", "title": "D", "inputs": [bad]}, dir=tmp_path)


@requires_octave
def test_verify_demo10_autonomous_investigation_with_reference(tmp_path):
    """The finale: a directory-tree repo demo whose Octave harness checks findings.json.

    Positive: the reference RCA locates the defect, fixes it and passes every check.
    Negative: a findings.json that blames the Kalman update must NOT verify.
    """
    src = CLAUDE_DEMO_KIT / "demos" / "10_autonomous_investigation"
    root = tmp_path / "set"
    (root / "demos").mkdir(parents=True)
    shutil.copytree(src, root / "demos" / "10_autonomous_investigation")
    (root / "demoforge.toml").write_text(
        f'[set]\nid = "t"\n\n[runtimes]\noctave = {json.dumps(str(OCTAVE))}\n',
        encoding="utf-8",
    )
    cs = load_content_set(root)
    demo = cs.demos()[0]

    outcome = verify_demo(
        demo, cs, artifacts_dirs=[src / "reference"], work_dir=tmp_path / "work",
        octave_bin=OCTAVE,
    )
    assert outcome.harness_ran and outcome.harness_ok
    assert outcome.passed is True
    # Ground truth measured from the repo's own data, not from the agent's report.
    assert outcome.metrics["discriminator"] == "mode"      # not version, not worker
    assert outcome.metrics["cause_id"] == "gate_threshold"
    assert outcome.metrics["fail_rate_planar"] == 0.0
    assert outcome.metrics["fail_rate_doppler"] > 0.5
    by_id = {c.id: c for c in outcome.results.checks}
    for cid in ("cause_located", "failing_runs_exact", "wrong_value_correct",
                "fix_correct", "tests_catch_shipped_bug"):
        assert by_id[cid].passed, cid

    ref = json.loads((src / "reference" / "findings.json").read_text(encoding="utf-8"))
    ref["cause"] = {"file": "src/kalman_update.m", "line": 1}
    bad = tmp_path / "bad_cause"
    shutil.copytree(src / "reference", bad)
    (bad / "findings.json").write_text(json.dumps(ref), encoding="utf-8")
    bad_outcome = verify_demo(
        demo, cs, artifacts_dirs=[bad], work_dir=tmp_path / "work_bad_cause", octave_bin=OCTAVE
    )
    assert bad_outcome.passed is False
    assert not {c.id: c for c in bad_outcome.results.checks}["cause_located"].passed

    # The repo is staged as a tree, so the agent sees real directories.
    staged = {rel for _, rel in demo.staged_inputs()}
    assert {"src/measurement_gate.m", "logs/estimator-worker.log",
            "data/validation_runs.csv", "docs/CVT-SRS-003.pdf"} <= staged

    # Negative: a prose-only report repeating the handover notes' theories.
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "root_cause.md").write_text(
        "# Root cause\n\n"
        "The campaign failed because of the slow estimator-02 worker and the v2.3 "
        "covariance regression. Recommend relaxing the acceptance limit.\n",
        encoding="utf-8",
    )
    bad_outcome = verify_demo(
        demo, cs, artifacts_dirs=[bad], work_dir=tmp_path / "work_bad", octave_bin=OCTAVE
    )
    assert bad_outcome.harness_ran and bad_outcome.harness_ok  # harness still measures
    assert bad_outcome.passed is False
    bad_by_id = {c.id: c for c in bad_outcome.results.checks}
    assert bad_by_id["produced_report"].passed          # a report exists...
    assert not bad_by_id["findings_valid"].passed       # ...but establishes nothing
    assert not bad_by_id["cause_located"].passed
