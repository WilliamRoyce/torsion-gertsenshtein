"""Console output helpers carrying the actionable-hint convention.

Ported from ``tidal/cli/_console.py`` (GH #524).  The convention is repo-wide and worth
keeping: a user-facing failure names an actionable next step -- an example of correct
syntax, the available options, a related command -- rather than only reporting that
something went wrong.  ``docs/cosmology/repo_reshape.md`` section 5.6 marks it a ``port``
row for exactly that reason, and every user-facing error in this package uses it from the
first line rather than being retrofitted with hints later.

All messages go to *stderr*, so that structured data on stdout (``--json``, piped output)
is never contaminated.

**Accessibility.** The ``[ERROR]`` prefix is always present, whether or not the terminal
can render color: color is additive and never the sole carrier of meaning.

Two deliberate departures from the original, recorded here per section 5.7's rule that a
port says where it changed behavior and why:

1. :func:`sys.stderr.write` replaces ``print(..., file=sys.stderr)``.  ``print`` trips
   ruff's ``T201``, which the legacy module escapes only through the per-file-ignore
   blanket that section 8 forbids this tree from inheriting.
2. The color decision is computed per call instead of being cached in a module-level
   global.  The cache saved two environment lookups and one ``isatty()`` on an error
   path, and cost correctness under pytest: the whole suite shares one process, so
   whichever test first triggered the decision froze it for every test that followed.
"""

from __future__ import annotations

import os
import sys

# ANSI escape codes.  Only the four the error path uses are carried over; the rest of the
# legacy palette arrives with the functions that need it.
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RED = "\033[0;31m"


def _use_color() -> bool:
    """Report whether stderr can render ANSI color.

    Honours the ``NO_COLOR`` and ``FORCE_COLOR`` conventions, then falls back to asking
    whether stderr is a terminal -- escape codes written into a redirected file or a pipe
    are noise rather than color.

    Returns
    -------
    bool
        ``True`` when color should be emitted.
    """
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    if not hasattr(sys.stderr, "isatty"):
        return False
    return sys.stderr.isatty()


def error(msg: str) -> None:
    """Print ``[ERROR] msg`` to stderr, in red where color is available.

    Parameters
    ----------
    msg : str
        The failure, stated plainly.
    """
    prefix = f"{_RED}{_BOLD}[ERROR]{_RESET}" if _use_color() else "[ERROR]"
    sys.stderr.write(f"{prefix} {msg}\n")


def error_with_hint(msg: str, hints: list[str]) -> None:
    """Print an error followed by actionable hints.

    Parameters
    ----------
    msg : str
        The failure, stated plainly.
    hints : list[str]
        One actionable suggestion per entry -- example syntax, the available options, a
        related command, a troubleshooting step.  A hint that only restates the error is
        worse than no hint.
    """
    error(msg)
    color = _use_color()
    for hint in hints:
        body = f"{_DIM}Hint: {hint}{_RESET}" if color else f"Hint: {hint}"
        sys.stderr.write(f"  {body}\n")
