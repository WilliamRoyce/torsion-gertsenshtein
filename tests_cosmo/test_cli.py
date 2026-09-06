"""The ``tidalcosmo`` command-line surface.

At M0 that surface is deliberately two flags, so these tests are less about argparse than
about keeping the entry point wired: a console script that is declared but not importable,
or a package whose version cannot be resolved, fails only at install time -- which no other
gate in this suite would catch.
"""

from __future__ import annotations

import runpy
import sys

import pytest

import tidalcosmo
from tidalcosmo.cli import main


def test_no_arguments_prints_help_and_succeeds(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """With nothing to do, the CLI says what is available rather than exiting silently."""
    assert main([]) == 0
    assert "usage: tidalcosmo" in capsys.readouterr().out


def test_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    """``--help`` is a successful exit, not an error."""
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])

    assert exit_info.value.code == 0
    assert "usage: tidalcosmo" in capsys.readouterr().out


def test_version_reports_the_distribution_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--version`` reports the one project version, not a second literal.

    One distribution named ``tidal`` ships both packages through the transition, so this
    number is the legacy package's number too.  A mismatch here would mean someone had
    hardcoded a version that ``scripts/bump_version.py`` will not move.
    """
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])

    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"tidalcosmo {tidalcosmo.__version__}"


def test_version_is_resolved_from_installed_metadata() -> None:
    """The version is a real resolved version, not the not-installed fallback."""
    assert tidalcosmo.__version__ != "0.0.0+unknown"


def test_module_entry_point_reaches_the_same_cli(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``python -m tidalcosmo.cli`` runs the same entry point as the console script."""
    monkeypatch.setattr(sys, "argv", ["tidalcosmo", "--version"])

    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("tidalcosmo.cli", run_name="__main__")

    assert exit_info.value.code == 0
    assert tidalcosmo.__version__ in capsys.readouterr().out
