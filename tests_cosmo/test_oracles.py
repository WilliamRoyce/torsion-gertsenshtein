"""The frozen legacy oracle is intact, self-consistent, and safe to commit.

These fixtures are the only evidence the new package will ever have about what
legacy `tidal` did (``docs/cosmology/repo_reshape.md`` §8).  They are produced
once by ``scripts/oracles/freeze_legacy_oracle.py`` and then read as data.

**This module reads files.  It must never import that generator.**  The generator
shells out to legacy, so importing it from here would transitively put legacy
back inside ``tests_cosmo/`` -- passing ``test_package_boundary.py``, whose regex
sees imports rather than reach, while defeating exactly what that test protects.
The moment a test depends on legacy running, legacy stops being deletable and
"delete per capability" (§7) quietly stops being possible.  Everything below is a
file read.

The byte-for-byte reproducibility gate is deliberately *not* here.  It cannot be:
proving that re-running reproduces the fixtures requires running legacy.  That
gate lives in ``--check``, run by hand and by the orchestrator at merge, and is
kept out of CI so the suite does not fail the day legacy is deleted.

**Retirement:** these fixtures and the shell-out check below go at M7 with the
boundary test, once M3's §5.2 mapping is recorded.  See §7's M7 row.

GH #525, milestone M0.5.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
ORACLES = REPO_ROOT / "tests_cosmo" / "data" / "oracles"
MANIFEST = ORACLES / "manifest.json"
README = ORACLES / "README.md"

EXPECTED_PAIRS = 46
EXPECTED_EXCLUSIONS = 4

ARTIFACT_KINDS = ("spec", "inspect_summary", "inspect_families", "validate")

# ``tests/test_repo_hygiene.py`` enforces this repo-wide today, but it belongs to
# the legacy suite and is deleted at M6 while these fixtures outlive it -- so the
# check is restated here rather than depended on.  Stated *generically*: an
# absolute path from anywhere is a leak, which subsumes that test's container and
# home patterns and catches ones they would miss.  Written this way, this file is
# itself hygiene-clean and needs no allowlist exemption.
FORBIDDEN = {
    "absolute path": re.compile(r"(?<![\w.$])/(?:[A-Za-z0-9_.-]+/)+"),
    "Claude project slug": re.compile(r"-workspaces-[A-Za-z0-9-]+"),
    "ANSI escape": re.compile(r"\x1b"),
}

# A shell-out is the half of the boundary rule the import regex cannot see.
SHELL_OUT = re.compile(
    r"""(?x)
    (?:subprocess|runpy|os\.system|os\.popen|shutil\.which)
    .{0,200}?
    (?:["']tidal["']|tidal\.cli|-m\s+tidal)
    """,
    re.DOTALL,
)
SCRIPTS_IMPORT = re.compile(r"^\s*(?:from|import)\s+scripts\b", re.MULTILINE)


def _manifest() -> dict[str, Any]:
    """Load the manifest, or fail with the command that produces it."""
    assert MANIFEST.is_file(), (
        f"{MANIFEST.relative_to(REPO_ROOT)} is missing; regenerate with "
        "`uv run python -m scripts.oracles.freeze_legacy_oracle`"
    )
    loaded: Any = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _entries() -> list[dict[str, Any]]:
    """Return the manifest's entry rows."""
    rows: Any = _manifest()["entries"]
    assert isinstance(rows, list)
    return rows


def test_corpus_counts_match_the_verified_predicate() -> None:
    """46 pairs and 4 exclusions, from 50 candidate TOMLs.

    The count is asserted here because the enumeration recipe originally given in
    the design silently dropped ``curved_spacetime/conformal_static.toml`` and
    produced 45.  A bare count is what catches that class of mistake.
    """
    summary: Any = _manifest()["summary"]
    assert summary["pairs"] == EXPECTED_PAIRS
    assert summary["excluded"] == EXPECTED_EXCLUSIONS
    assert summary["toml_candidates"] == EXPECTED_PAIRS + EXPECTED_EXCLUSIONS

    idents = [str(entry["id"]) for entry in _entries()]
    assert len(set(idents)) == len(idents), (
        "spec ids must be unique; the layout keys on them"
    )
    assert "conformal_kg_static" in idents, (
        "the spec the `examples/*/theory*.toml` glob dropped must be in the corpus"
    )


def test_every_exclusion_is_named_with_a_reason() -> None:
    """An exclusion without a reason is attrition wearing a list's clothing."""
    exclusions: Any = _manifest()["exclusions"]
    assert len(exclusions) == EXPECTED_EXCLUSIONS
    for excluded in exclusions:
        assert excluded["theory"].endswith(".toml")
        assert excluded["expected_spec"].endswith(".json")
        assert excluded["reason"].strip(), (
            f"{excluded['theory']} excluded with no reason"
        )
        assert not (REPO_ROOT / str(excluded["expected_spec"])).exists(), (
            f"{excluded['theory']} now has a committed spec and should no longer "
            "be excluded; re-run the freeze script"
        )


def test_manifest_and_files_are_a_bijection() -> None:
    """Every listed artifact exists, and every file on disk is listed.

    Both directions matter.  A missing file is an obviously broken fixture; an
    *unlisted* file is a stale artifact from a renamed theory, which the manifest
    would happily describe a corpus without.
    """
    listed: set[Path] = set()
    for entry in _entries():
        artifacts: Any = entry["artifacts"]
        assert set(artifacts) == set(ARTIFACT_KINDS), (
            f"{entry['id']} does not carry all four artifact kinds"
        )
        for kind in ARTIFACT_KINDS:
            path = ORACLES / str(artifacts[kind]["path"])
            assert path.is_file(), f"{entry['id']}/{kind} listed but missing: {path}"
            listed.add(path)

    on_disk = {
        path
        for directory in ("specs", "inspect", "validate")
        for path in (ORACLES / directory).rglob("*")
        if path.is_file()
    }
    assert on_disk == listed, (
        "unlisted fixture files (stale artifacts the manifest cannot see): "
        f"{sorted(str(p.relative_to(ORACLES)) for p in on_disk - listed)}"
    )
    assert len(listed) == EXPECTED_PAIRS * len(ARTIFACT_KINDS)


def test_recorded_hashes_match_the_files() -> None:
    """Catches a hand-edit, a partial commit, or a newline smudge."""
    mismatched: list[str] = []
    for entry in _entries():
        artifacts: Any = entry["artifacts"]
        for kind in ARTIFACT_KINDS:
            record: Any = artifacts[kind]
            data = (ORACLES / str(record["path"])).read_bytes()
            if hashlib.sha256(data).hexdigest() != record["sha256"]:
                mismatched.append(f"{entry['id']}/{kind}")
            elif len(data) != record["bytes"]:
                mismatched.append(f"{entry['id']}/{kind} (size)")
    assert not mismatched, (
        "fixtures no longer match their recorded hashes -- they were edited by "
        f"hand or by a hook: {mismatched}"
    )


def test_text_artifacts_record_the_exit_code_the_manifest_claims() -> None:
    """The header and the manifest must not disagree about what legacy returned.

    The exit code *is* the ``validate`` oracle, so a header that drifts from the
    manifest would let a verdict change without either file looking wrong.
    """
    for entry in _entries():
        artifacts: Any = entry["artifacts"]
        exits: Any = entry["exits"]
        for kind, keys in (
            ("inspect_summary", (("# exit:", "inspect_summary"),)),
            ("inspect_families", (("# exit:", "inspect_families"),)),
            (
                "validate",
                (
                    ("# plain-exit:", "validate"),
                    ("# stability-exit:", "validate_stability"),
                ),
            ),
        ):
            text = (ORACLES / str(artifacts[kind]["path"])).read_text(encoding="utf-8")
            for prefix, exit_key in keys:
                line = next(ln for ln in text.splitlines() if ln.startswith(prefix))
                assert int(line.removeprefix(prefix).strip()) == exits[exit_key], (
                    f"{entry['id']}/{kind}: header {prefix} disagrees with the manifest"
                )
            for marker in ("#--- ", "#--- end ---"):
                assert marker in text, f"{entry['id']}/{kind}: section markers missing"


def test_no_fixture_carries_a_machine_specific_path() -> None:
    """Defense in depth, and the layer that survives M6.

    ``tests/test_repo_hygiene.py`` checks this today, but it is the legacy
    suite's and goes when ``tests/`` does.
    """
    violations: list[str] = []
    for path in sorted(ORACLES.rglob("*")):
        if not path.is_file():
            continue
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            violations.append(f"{path.relative_to(ORACLES)}: not valid UTF-8")
            continue
        for name, pattern in FORBIDDEN.items():
            match = pattern.search(text)
            if match is not None:
                violations.append(
                    f"{path.relative_to(ORACLES)}: {name} {match.group(0)!r}"
                )
    assert not violations, (
        "machine-specific content in committed fixtures:\n  " + "\n  ".join(violations)
    )


def test_fixture_tree_holds_no_python() -> None:
    """A data directory that grows importable code stops being data."""
    stray = sorted(
        p.relative_to(REPO_ROOT)
        for p in (REPO_ROOT / "tests_cosmo" / "data").rglob("*.py")
    )
    assert not stray, f"tests_cosmo/data/ must contain data only, found: {stray}"


def test_readme_counts_match_the_manifest() -> None:
    """Documentation drift is caught rather than assumed away.

    The README carries the reasoning and the numbers a reviewer reads first; if
    it and the data disagree, the data is right and the README is stale.
    """
    assert README.is_file(), "the oracle README is hand-written and must exist"
    text = README.read_text(encoding="utf-8")
    summary: Any = _manifest()["summary"]
    for label, value in (
        ("pairs", summary["pairs"]),
        ("exclusions", summary["excluded"]),
        ("plain-validate failures", summary["validate_fail"]),
        (
            "undefined-parameter stability errors",
            summary["stability_undefined_parameter"],
        ),
    ):
        assert str(value) in text, (
            f"the README does not state the {label} count ({value}); it is stale"
        )


def test_new_trees_never_shell_out_to_legacy() -> None:
    """The half of the boundary rule the import regex cannot see.

    ``test_package_boundary.py`` matches ``import tidal``, so
    ``subprocess.run(["tidal", ...])`` in a new-package test passes it while
    doing the very thing §8 forbids.  Importing ``scripts.oracles`` is the same
    breach one level of indirection away.
    """
    violations: list[str] = []
    for tree in (REPO_ROOT / "tidalcosmo", REPO_ROOT / "tests_cosmo"):
        for path in sorted(tree.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            if path.name == "test_oracles.py":
                continue  # this module, which defines the patterns
            rel = path.relative_to(REPO_ROOT)
            violations.extend(
                f"{rel}: shells out to legacy" for _ in SHELL_OUT.finditer(text)
            )
            violations.extend(
                f"{rel}: imports {m.group(0).strip()!r}, which reaches legacy indirectly"
                for m in SCRIPTS_IMPORT.finditer(text)
            )
    assert not violations, (
        "new-package code must not run legacy, directly or through scripts/oracles/ "
        "-- assert against the frozen fixtures instead:\n  " + "\n  ".join(violations)
    )


def test_generated_artifacts_carry_no_version_string() -> None:
    """No generated fixture may embed a version, or the byte-for-byte gate self-destructs.

    The orchestrator bumps the version once per wave and re-runs this oracle's
    ``--check`` after other branches merge (``repo_reshape.md`` §8).  If a generated
    artifact recorded the ``tidal`` version, every bump would dirty the fixtures and
    the reproducibility gate could never be clean -- the same trap that put the
    ``end-of-file-fixer`` exemption in ``.pre-commit-config.yaml``.

    The freeze script keeps versions out by construction, and provenance lives in the
    hand-written README, which is never regenerated.  That held on inspection but
    nothing enforced it, so a later edit could reintroduce one silently.  This is the
    enforcement (finding: the I-525 session, 2026-09-06).

    Scope is the *generated* text: ``inspect/`` and ``validate/`` reports and the
    manifest.  ``specs/`` is excluded -- those are byte-for-byte copies of committed
    files, so whatever they contain is frozen at the source and is not ours to police.
    """
    semver = re.compile(r"\b\d+\.\d+\.\d+\b")
    generated = [
        *sorted((ORACLES / "inspect").rglob("*.txt")),
        *sorted((ORACLES / "validate").rglob("*.txt")),
        MANIFEST,
    ]
    assert generated, "no generated artifacts found -- has the layout moved?"

    violations = [
        f"{path.relative_to(REPO_ROOT)}: {match.group(0)!r}"
        for path in generated
        for match in semver.finditer(path.read_text(encoding="utf-8"))
    ]
    assert not violations, (
        "a generated oracle artifact embeds a version-like string; every version bump "
        "would then dirty the fixtures and the byte-for-byte gate could never pass. "
        "Put provenance in the hand-written README instead:\n  "
        + "\n  ".join(violations)
    )
