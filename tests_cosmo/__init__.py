"""Test suite for the ``tidalcosmo`` package.

Separate from ``tests/`` by design: the legacy suite stays untouched and green
while this one grows (``docs/cosmology/repo_reshape.md`` section 8).

**House style, set at M0 (#524) because later milestones port tests in bulk.**  The legacy
suite is not the model: ``tests/test_cli.py`` alone is ~5,300 class-grouped lines leaning on
a large shared ``conftest.py``, much of it testing the CLI *as* the config object, which is
the structural inversion this package exists to undo.  New tests here:

* **Module-level functions, not classes**, with a docstring on every test.  This tree
  carries **no ruff per-file-ignore blanket** (section 8), so the full rule set applies;
  a targeted ``# noqa: CODE  # reason`` at a site that warrants one is the intended escape
  hatch, an inherited blanket is not.  If a single code proves systematically unavoidable,
  report the count rather than reinstating a blanket.
* **Test through the public surface.**  pyright runs strict here with
  ``reportPrivateUsage`` on.  Where something private genuinely needs testing directly,
  prefer promoting it to public; failing that, suppress at the site with a reason.  Note
  the rule is about private *symbols*: importing a public name from a private module is
  accepted, and only ruff's ``PLC2701`` fires.
* **Hermetic.**  No dependence on ``examples/data/`` or on anything a derivation produced.
* **Never import or shell out to legacy** ``tidal`` -- assert against the committed
  fixtures instead.  Enforced by :mod:`tests_cosmo.test_package_boundary`; the moment a
  test reaches into legacy, legacy stops being data and becomes undeletable infrastructure.
* Prefer :func:`runpy.run_module` over ``subprocess`` for entry-point tests -- same
  coverage, and it avoids the ``S404``/``S603`` suppressions a subprocess would need.
"""
