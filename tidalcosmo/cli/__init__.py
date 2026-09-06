"""The command-line adapter: parse arguments, build a config, call the library.

Deliberately thin, and **no physics lives here**.  In the legacy package the CLI *is* the
config object and carries the forward model, which is why four modules outside it import
private names back out of it.  Here the CLI and the Cobaya component are two thin callers
of one library entry point (``docs/cosmology/repo_reshape.md`` section 2.11).

At M0 the surface is ``--version`` and ``--help``.  Subcommands arrive from M1 onward and
grow only as needed; the eventual set is far smaller than legacy's eleven, since Cobaya
supplies sampling and priors and GetDist supplies plots.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from tidalcosmo import __version__

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["main"]


def _build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="tidalcosmo",
        description=(
            "Evolve a Lagrangian's linear perturbations as spectators on a CAMB ΛCDM "
            "background, and turn them into CMB observables."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface.

    Parameters
    ----------
    argv : Sequence[str] | None
        Command-line arguments.  ``None`` reads them from :data:`sys.argv`.

    Returns
    -------
    int
        Process exit code; ``0`` on success.  Like the legacy entry point, this returns
        rather than calling :func:`sys.exit`, so that it stays callable from a test.
    """
    parser = _build_parser()
    parser.parse_args(argv)
    # ``--help`` and ``--version`` exit inside ``parse_args``.  Until subcommands exist,
    # reaching this line means the user asked for nothing in particular, so say what is
    # available rather than succeeding silently.
    parser.print_help()
    return 0
