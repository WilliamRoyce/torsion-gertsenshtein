"""Cobaya extension: a new sector's linear perturbations as spectators on ΛCDM.

Evolves a candidate Lagrangian's linear perturbations as *spectator* fields on the
established ΛCDM background supplied by CAMB, and turns them into CMB observables that
can be compared with real data through a Cobaya ``Theory`` extension.

This package is built *beside* the legacy ``tidal`` package rather than on top of it:
new code never imports legacy code, capabilities are ported rather than adapted, and the
legacy tree is deleted per capability once its replacement is live.  Design:
``docs/cosmology/repo_reshape.md``.  Programme record: ``docs/COSMOLOGY_PROGRAM.md``.

``tidalcosmo`` is a placeholder name.  Once the legacy tree is gone this package is
renamed to ``tidal``, so nothing here carries cosmology-specific naming, and nothing
naming ``tidalcosmo`` should be circulated outside the project -- an external
``theory: {tidalcosmo.SpectatorTheory: ...}`` breaks on the day of the rename.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

# One distribution, named ``tidal``, ships both packages through the transition, so the
# version is read from that distribution rather than written as a literal here.  There is
# a single number for the project, ``scripts/bump_version.py`` moves it without needing to
# know this package exists, and the two cannot drift apart.  The distribution name changes
# only at the rename, when there is one package again.
try:
    __version__ = _pkg_version("tidal")
except (
    PackageNotFoundError
):  # pragma: no cover - only outside an installed distribution
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
