"""CLI behavior: list / verify / render / build surface and exit codes."""

from __future__ import annotations

from conftest import write_demo

from demoforge.cli import EXIT_OK, main


def test_list_empty_set(content_set, capsys):
    rc = main(["--set", str(content_set), "list"])
    out = capsys.readouterr().out
    assert rc == EXIT_OK
    assert "Test Set" in out
    assert "no demos yet" in out


def test_list_shows_demos(content_set, capsys):
    demos_dir = content_set / "demos"
    write_demo(
        demos_dir,
        "02_opt",
        """
        id: matlab-optimization
        title: MATLAB Algorithm Optimization
        order: 2
        runtime: octave
        checks:
          - id: sp
            kind: threshold
            metric: speedup
            min: 3.0
        """,
    )
    rc = main(["--set", str(content_set), "list"])
    out = capsys.readouterr().out
    assert rc == EXIT_OK
    assert "matlab-optimization" in out
    assert "octave" in out
    assert "1 demo(s)" in out


def test_list_validates_checks(content_set, capsys):
    demos_dir = content_set / "demos"
    write_demo(
        demos_dir,
        "bad",
        """
        id: bad
        title: Bad
        checks:
          - id: oops
            kind: threshold
            metric: speedup
        """,  # threshold with no min/max -> invalid
    )
    rc = main(["--set", str(content_set), "list"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "min" in err and "max" in err


def test_build_is_incremental(content_set, capsys):
    rc = main(["--set", str(content_set), "build"])  # first build: derives the deck
    assert rc == EXIT_OK
    assert "built:" in capsys.readouterr().out

    rc = main(["--set", str(content_set), "build"])  # second build: nothing changed
    assert rc == EXIT_OK
    assert "nothing to do" in capsys.readouterr().out


def test_missing_content_set_errors(tmp_path, capsys):
    empty = tmp_path / "nothing"
    empty.mkdir()
    rc = main(["--set", str(empty), "list"])
    assert rc == 1
    assert "no demoforge.toml" in capsys.readouterr().err
