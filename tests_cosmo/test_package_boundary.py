"""The strangler-fig boundary, made self-enforcing.

``tidalcosmo`` is built beside legacy ``tidal``, not on top of it: the programme's
hardest structural rule is that **new code never imports old code** (D3, see
``docs/COSMOLOGY_PROGRAM.md`` and ``docs/cosmology/repo_reshape.md`` §8).  Useful
legacy capabilities are *ported* -- redesigned and moved, with their docstrings and
issue references -- never reached into.

``tidalcosmo/README.md`` stated this as already enforced.  It was not: no test
checked it, and ``pyrightconfig.json``/coverage/``testpaths`` all skipped the tree,
so the WS1 gate ("suite green, no old-code imports, pyright clean") would have
passed vacuously on an unchecked package.  This module closes that gap before the
first ``.py`` file lands, which is the cheapest moment to do it.

**Both trees are checked, and the second one matters most.**  ``repo_reshape.md`` §8
bans the legacy import ``under tidalcosmo/`` *or under* ``tests_cosmo/``, because a
*test* that reaches into legacy is precisely how the frozen oracle stops being data
and becomes undeletable infrastructure -- at which point "delete legacy per
capability" (§7) quietly stops being possible.  New-package tests assert against the
committed fixtures under ``tests_cosmo/data/oracles/``, never against a live import.
The first revision of this module scanned ``tidalcosmo/`` only, so the half that
matters most was unenforced while three documents said otherwise.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Both halves of the rule (repo_reshape.md section 8).  ``scripts/oracles/`` is
# deliberately absent: it is the one place allowed to touch legacy, because it runs
# once at M0.5 to *produce* the fixtures and is not imported by anything.
CHECKED_TREES = (REPO_ROOT / "tidalcosmo", REPO_ROOT / "tests_cosmo")

# ``import tidal`` / ``from tidal import ...`` / ``from tidal.x import ...`` but NOT
# ``import tidalcosmo`` -- the word boundary is what separates the two packages.
LEGACY_IMPORT = re.compile(r"^\s*(?:from|import)\s+tidal\b(?!cosmo)", re.MULTILINE)


def test_new_code_never_imports_legacy() -> None:
    """No module under ``tidalcosmo/`` or ``tests_cosmo/`` may import legacy ``tidal``."""
    violations: list[str] = []

    for tree in CHECKED_TREES:
        for path in sorted(tree.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for match in LEGACY_IMPORT.finditer(text):
                lineno = text.count("\n", 0, match.start()) + 1
                rel = path.relative_to(REPO_ROOT)
                violations.append(f"{rel}:{lineno}: {match.group(0).strip()}")

    assert not violations, (
        "tidalcosmo and tests_cosmo must never import legacy tidal -- port the "
        "capability, or assert against the frozen fixtures in tests_cosmo/data/oracles/ "
        "(docs/cosmology/repo_reshape.md section 8):\n  " + "\n  ".join(violations)
    )
