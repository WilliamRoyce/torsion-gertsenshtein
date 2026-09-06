"""The ported actionable-hint convention.

``error_with_hint`` is the first capability ported out of legacy (GH #524), so these tests
also pin the two deliberate departures recorded in the module docstring: output goes
through :func:`sys.stderr.write` rather than ``print``, and the color decision is *not*
cached for the life of the process.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

# ``_console`` is private by design -- the CLI's internals are not this package's API --
# and it is the module under test, so the private-module import is deliberate here.
from tidalcosmo.cli._console import error, error_with_hint  # noqa: PLC2701

if TYPE_CHECKING:
    import pytest

HINTS = [
    "Run `tidalcosmo --help` to see the available options.",
    "Check the spelling of the option name.",
]


def test_error_is_prefixed_and_goes_to_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An error carries the ``[ERROR]`` prefix and never lands on stdout."""
    error("the spec could not be read")

    captured = capsys.readouterr()
    assert not captured.out
    assert "[ERROR] the spec could not be read" in captured.err


def test_every_hint_is_printed_after_the_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Each hint gets its own indented line, in order, below the error."""
    error_with_hint("unrecognized option", HINTS)

    err = capsys.readouterr().err
    lines = err.splitlines()
    assert lines[0].endswith("unrecognized option")
    assert err.count("Hint:") == len(HINTS)
    for hint, line in zip(HINTS, lines[1:], strict=True):
        assert line == f"  Hint: {hint}"


def test_hints_never_contaminate_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    """Standard output stays clean, so piped or ``--json`` output is never corrupted."""
    error_with_hint("unrecognized option", HINTS)

    assert not capsys.readouterr().out


def test_no_color_suppresses_escapes_but_never_the_prefix(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Color is additive: with ``NO_COLOR`` the message still identifies itself."""
    monkeypatch.setenv("NO_COLOR", "1")

    error_with_hint("unrecognized option", HINTS)

    err = capsys.readouterr().err
    assert "\033[" not in err
    assert "[ERROR]" in err
    assert "Hint:" in err


def test_force_color_emits_escapes(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``FORCE_COLOR`` overrides the not-a-terminal default that applies under pytest."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("FORCE_COLOR", "1")

    error_with_hint("unrecognized option", HINTS)

    assert "\033[" in capsys.readouterr().err


def test_color_is_decided_per_call_not_cached(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A color decision must not outlive the call that made it.

    This is the regression test for the port's second deliberate departure.  The legacy
    module cached the answer in a module-level global, which is safe in a CLI process and
    unsafe under pytest, where the whole suite shares one process: whichever test first
    triggered the decision froze it for every test after it.  With a cache in place, the
    second half of this test reads the first half's answer and fails.
    """
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("FORCE_COLOR", "1")
    error("colored")
    assert "\033[" in capsys.readouterr().err

    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.setenv("NO_COLOR", "1")
    error("plain")
    assert "\033[" not in capsys.readouterr().err
