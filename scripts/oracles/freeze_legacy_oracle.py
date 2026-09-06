#!/usr/bin/env python3
"""Freeze legacy ``tidal``'s outputs across the example corpus as committed data.

The new package ``tidalcosmo`` is built beside legacy ``tidal`` and **never
imports it** (``tests_cosmo/test_package_boundary.py``).  So the equivalence
evidence for a port cannot be produced by calling legacy from a test: a test that
imports or shells out to legacy is precisely how the oracle becomes undeletable
infrastructure, and "delete legacy per capability" (``repo_reshape.md`` §7)
quietly stops being possible.  This script is the sanctioned exception -- **the
one place in the repository allowed to touch legacy** -- and it exists so that
nothing else has to.  It runs by hand, writes files, and is imported by nothing,
including by the test that guards its output.

What it freezes, per theory in the example corpus (``repo_reshape.md`` §8, as
amended 2026-09-06):

* the derived spec JSON, copied byte-for-byte -- never regenerated, which would
  need the Wolfram lane;
* ``tidal inspect --detail summary`` -- the proven-sign table;
* ``tidal inspect --families`` -- family and index structure, which is invariant
  under the renaming #513 introduces while prose summaries are not;
* ``tidal validate`` **and** ``tidal validate --stability`` -- both, because
  ``--stability`` alone errors on 40 of 46 specs with "cannot evaluate symbolic
  coefficient", a verdict about missing parameter defaults rather than about the
  physics.

Two properties are load-bearing and are asserted rather than hoped for.
**Determinism**: the child environment is a constructed allowlist, so a
developer's ``FORCE_COLOR`` or ``COLUMNS`` cannot reach committed data, and
re-running must reproduce every byte (``--check``).  **Cleanliness**: no absolute
path may survive into a fixture, because ``tests/test_repo_hygiene.py`` scans
``tests_cosmo/`` content-agnostically and one machine path fails the whole suite.

The two failure modes are deliberately asymmetric.  A spec that legacy cannot
load is recorded as a status row and the run continues -- a corpus tool that dies
on one file answers nothing about the rest.  A scrub violation **aborts**: data
integrity outranks completeness, because the failure being prevented is
committing a machine-specific path, not missing a row.

Usage
-----
    uv run python -m scripts.oracles.freeze_legacy_oracle
    uv run python -m scripts.oracles.freeze_legacy_oracle --check
    uv run python -m scripts.oracles.freeze_legacy_oracle --list
    uv run python -m scripts.oracles.freeze_legacy_oracle --only <id>
    uv run python -m scripts.oracles.freeze_legacy_oracle --verify-determinism

See ``tests_cosmo/data/oracles/README.md`` for what the fixtures mean, the
numbered scrub, and the exclusions.  GH #525, milestone M0.5, umbrella #488.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import re
import socket
import subprocess  # noqa: S404 -- running legacy is this script's entire purpose
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EXAMPLES = REPO / "examples"
ORACLES = REPO / "tests_cosmo" / "data" / "oracles"

SPECS_DIR = ORACLES / "specs"
INSPECT_DIR = ORACLES / "inspect"
VALIDATE_DIR = ORACLES / "validate"
MANIFEST = ORACLES / "manifest.json"

GENERATOR = "scripts/oracles/freeze_legacy_oracle.py"
REGENERATE = "uv run python -m scripts.oracles.freeze_legacy_oracle"

# Why not `examples/*/theory*.toml`, which repo_reshape.md section 8 gave until
# the 2026-09-06 amendment: that glob matches 48 files and silently drops
# examples/curved_spacetime/conformal_static.toml, which does have a committed
# spec -- 45 pairs, not 46.  Filtering on the [output].path suffix instead also
# drops the five sweep_*.toml configs, whose output path is a directory.
CORPUS_PREDICATE = (
    "every examples/*/*.toml whose [output].path, resolved relative to the "
    "TOML's own directory, ends in .json"
)

# Deriving these needs a wolframscript kernel (one machine-wide, held by another
# session in Wave 0), so they are named here rather than silently missed.
NO_COMMITTED_SPEC = (
    "no committed spec; re-deriving it needs the Wolfram lane, unavailable to "
    "the session that froze this corpus"
)

# tests/test_repo_hygiene.py:43-47, restated so the two cannot drift apart.  Any
# match aborts the run; see the module docstring on why this is not a status row.
HYGIENE_PATTERNS = {
    "container/clone path": re.compile(r"/workspaces/"),
    "user home path": re.compile(r"/home/[A-Za-z0-9_.-]+/"),
    "Claude project slug": re.compile(r"-workspaces-[A-Za-z0-9-]+"),
}

# Wider than the hygiene test, because a fixture only has to be *portable*; the
# hygiene test is what makes a violation fatal, this is what makes it visible.
VOLATILE_PATTERNS = {
    "absolute path": re.compile(r"(?<![\w/])/(?:usr|opt|tmp|var|srv|mnt|root|Users)/"),
    "windows path": re.compile(r"[A-Za-z]:\\"),
    "ANSI escape": re.compile(r"\x1b"),
    "timestamp": re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}"),
    "timing line": re.compile(r"\[TIME\]|completed in \d"),
}

ANSI_CSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")

SECTION_MARKER = re.compile(r"^#--- .* ---$", re.MULTILINE)


class OracleScrubError(RuntimeError):
    """A captured artifact carried something that must not be committed.

    Raised rather than recorded, and it aborts the whole run: the point of the
    scrub is that no machine-specific byte reaches a committed file, and a
    partial freeze that skipped the offending entry would look successful.
    """


@dataclass(frozen=True)
class Pair:
    """One theory TOML and the committed spec JSON it derives."""

    ident: str
    theory: str
    spec: str


@dataclass(frozen=True)
class Exclusion:
    """A TOML in the corpus predicate that has no committed spec."""

    theory: str
    expected_spec: str
    reason: str


@dataclass
class Capture:
    """One legacy invocation: what ran, what came back, and on which stream."""

    argv: list[str]
    command: str
    exit_code: int
    stdout: str
    stderr: str


@dataclass
class Entry:
    """Everything frozen for one pair, ready to write and to record."""

    pair: Pair
    derivation_hash: str | None
    has_metadata_parameters: bool
    artifacts: dict[str, bytes] = field(default_factory=dict)
    exits: dict[str, int] = field(default_factory=dict)
    error_class: str | None = None


# --------------------------------------------------------------------------
# corpus
# --------------------------------------------------------------------------


def resolve_corpus() -> tuple[list[Pair], list[Exclusion]]:
    """Return the (pairs, exclusions) split of the example corpus.

    Sorted, so the manifest and the pruning order are deterministic.  A TOML
    that cannot be parsed is a hard error: an unreadable theory silently
    dropping out of the corpus is exactly the failure this predicate replaced.
    """
    pairs: list[Pair] = []
    exclusions: list[Exclusion] = []
    for toml_path in sorted(EXAMPLES.glob("*/*.toml")):
        config = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        raw = config.get("output", {}).get("path")
        if not isinstance(raw, str) or not raw.endswith(".json"):
            continue
        # tidal/cli/_derive.py:6305-6310 resolves a relative output path against
        # the config's own directory, not the working directory.
        spec_path = (toml_path.parent / raw).resolve()
        theory_rel = toml_path.relative_to(REPO).as_posix()
        spec_rel = spec_path.relative_to(REPO).as_posix()
        if spec_path.is_file():
            pairs.append(Pair(spec_path.stem, theory_rel, spec_rel))
        else:
            exclusions.append(Exclusion(theory_rel, spec_rel, NO_COMMITTED_SPEC))

    seen: dict[str, str] = {}
    for pair in pairs:
        if pair.ident in seen:
            msg = (
                f"two theories map to spec id {pair.ident!r}: "
                f"{seen[pair.ident]} and {pair.theory}. The fixture layout keys "
                f"on the spec stem, so one would silently overwrite the other."
            )
            raise RuntimeError(msg)
        seen[pair.ident] = pair.theory
    return pairs, exclusions


# --------------------------------------------------------------------------
# running legacy
# --------------------------------------------------------------------------


def child_env() -> dict[str, str]:
    """Build the subprocess environment as an allowlist, never inherited.

    Inheriting ``os.environ`` would let a developer's ``FORCE_COLOR``,
    ``COLUMNS`` or ``TIDAL_BANNER_THEME`` leak into committed data, and the
    resulting fixture would differ between machines with nothing to explain why.
    ``NO_COLOR`` is set explicitly rather than relying on pipe detection:
    ``tidal/cli/_console.py`` caches its color decision from
    ``sys.stderr.isatty()`` in a module global.

    The BLAS thread pins are not superstition.  ``tidal/solver/validation.py``
    formats eigenvalue diagnostics with ``{:.4g}``/``{:.2e}``, and reduction
    order varies with thread count; pinning these four to one removes the
    only
    floating-point path into an artifact.  ``PYTHONWARNINGS=ignore`` is a scrub
    decision documented in the oracle README, not tidiness: Python's warning
    format embeds an absolute path *and* a legacy line number.
    """
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", str(Path.cwd())),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "TZ": "UTC",
        "PYTHONHASHSEED": "0",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONWARNINGS": "ignore",
        "NO_COLOR": "1",
        "TERM": "dumb",
        "COLUMNS": "80",
        "LINES": "24",
        "TIDAL_NO_BANNER": "1",
        "MPLBACKEND": "Agg",
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
    }


def run_legacy(args: list[str], *, hashseed: str | None = None) -> Capture:
    """Invoke the legacy CLI once and capture both streams separately.

    ``-m tidal.cli`` rather than the ``tidal`` console script, so the run does
    not depend on PATH and uses the interpreter already selected.  Paths are
    passed **relative** to the repository root: neither ``inspect`` nor
    ``validate`` resolves its argument, and both print only the basename on
    success, so no absolute path can reach an artifact by this route.
    """
    env = child_env()
    if hashseed is not None:
        env["PYTHONHASHSEED"] = hashseed
    argv = [sys.executable, "-m", "tidal.cli", "--no-banner", *args]
    completed = subprocess.run(
        argv,
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=900,
        check=False,
    )
    return Capture(
        argv=argv,
        command=" ".join(["tidal", "--no-banner", *args]),
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


# --------------------------------------------------------------------------
# the scrub
# --------------------------------------------------------------------------


def scrub(text: str) -> str:
    """Normalize one captured stream into committable bytes.

    Layered rather than single-shot, so each layer is a no-op the next one can
    still catch: color is already off, paths are already relative, and warnings
    are already suppressed -- these substitutions are the second line, and
    :func:`assert_clean` is the third.
    """
    text = ANSI_CSI.sub("", text)
    # Only the two roots that legitimately differ between checkouts are
    # substituted.  The home directory and sys.base_prefix are deliberately NOT:
    # ``sys.base_prefix`` is ``/usr`` here, so rewriting it would turn any stray
    # stdlib path into a portable-looking ``<python>/...`` token and the guard
    # below would never see it.  A path from outside the repository means
    # something leaked that this scrub did not anticipate, and that should abort
    # the run rather than be tidied away.
    for needle, token in ((str(REPO), "<repo>"), (sys.prefix, "<venv>")):
        if len(needle) > 1:
            text = text.replace(needle, token)
    # `inspect` ends on a bare print(), so stdout finishes '\n\n'.  Left as-is,
    # pre-commit's end-of-file-fixer would rewrite the committed file and the
    # next run would rewrite it back -- a byte gate that can never be clean.
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return "".join(f"{line}\n" for line in lines)


def assert_clean(text: str, where: str) -> None:
    """Abort the run if anything machine-specific or volatile survived.

    The hygiene patterns are restated from ``tests/test_repo_hygiene.py`` rather
    than imported, because that test belongs to the legacy suite and will be
    deleted at M6 while these fixtures outlive it.
    """
    for name, pattern in {**HYGIENE_PATTERNS, **VOLATILE_PATTERNS}.items():
        match = pattern.search(text)
        if match is not None:
            msg = f"{where}: {name} in captured output: {match.group(0)!r}"
            raise OracleScrubError(msg)
    for name, value in (("hostname", socket.gethostname()), ("username", _username())):
        if len(value) > 3 and value in text:
            msg = f"{where}: {name} {value!r} in captured output"
            raise OracleScrubError(msg)


def _username() -> str:
    """Return the invoking user's name, or a value that can never match."""
    try:
        return getpass.getuser()
    except (OSError, KeyError):  # pragma: no cover - depends on the environment
        return "\0"


def assert_utf8(data: bytes, where: str) -> None:
    """Reject a non-UTF-8 artifact.

    ``tests/test_repo_hygiene.py`` silently ``continue``s on
    ``UnicodeDecodeError``, so an artifact that fails to decode would escape the
    absolute-path check entirely rather than failing it.
    """
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        msg = f"{where}: not valid UTF-8, so the hygiene test would skip it ({exc})"
        raise OracleScrubError(msg) from exc


# --------------------------------------------------------------------------
# artifact rendering
# --------------------------------------------------------------------------


def render_artifact(
    pair: Pair, title: str, captures: list[tuple[str, Capture]]
) -> bytes:
    """Render captures into one fixture file.

    Both streams are emitted for every capture even when empty, which turns
    "stderr was empty" from an absence into an asserted, diffable fact: a future
    legacy change that starts writing to the other stream shows up as a diff
    rather than as silence.  Streams are captured to separate pipes and written
    in a fixed order, so interleaving is impossible by construction.

    No field here varies with HEAD, the machine, or the clock.  The orchestrator
    re-runs the byte gate after other branches merge, so a commit SHA or a
    version string in a generated file would guarantee it fails; that provenance
    lives in the hand-written README instead.
    """
    head = [
        f"# frozen legacy oracle -- {title}",
        f"# generator: {GENERATOR} -- do not edit by hand",
        f"# regenerate: {REGENERATE}",
        f"# theory: {pair.theory}",
        f"# spec: {pair.spec}",
    ]
    for label, capture in captures:
        prefix = f"{label}-" if label else ""
        head.extend(
            (
                f"# {prefix}command: {capture.command}",
                f"# {prefix}exit: {capture.exit_code}",
            )
        )
    head.append(
        "# scrub: ansi-stripped; warnings-suppressed; paths-relative; "
        "trailing-whitespace-normalized"
    )

    body: list[str] = []
    for label, capture in captures:
        prefix = f"{label}:" if label else ""
        for stream, raw in (("stdout", capture.stdout), ("stderr", capture.stderr)):
            cleaned = scrub(raw)
            where = f"{pair.ident} {title} {prefix}{stream}"
            assert_clean(cleaned, where)
            if SECTION_MARKER.search(cleaned):
                msg = f"{where}: payload contains a section marker, which would corrupt the fixture"
                raise OracleScrubError(msg)
            body.extend((f"#--- {prefix}{stream} ---", cleaned))
    body.append("#--- end ---")

    text = (
        "\n".join(head)
        + "\n"
        + "".join(line if line.endswith("\n") else line + "\n" for line in body)
    )
    data = text.encode("utf-8")
    assert_utf8(data, f"{pair.ident} {title}")
    return data


def freeze_entry(pair: Pair, *, hashseed: str | None = None) -> Entry:
    """Run legacy for one pair and return its four frozen artifacts."""
    spec_bytes = (REPO / pair.spec).read_bytes()
    assert_utf8(spec_bytes, pair.spec)
    assert_clean(spec_bytes.decode("utf-8"), pair.spec)

    metadata = json.loads(spec_bytes).get("metadata", {})
    derivation_hash = metadata.get("derivation_hash")
    entry = Entry(
        pair=pair,
        derivation_hash=derivation_hash if isinstance(derivation_hash, str) else None,
        has_metadata_parameters=bool(metadata.get("parameters")),
    )

    summary = run_legacy(
        [
            "inspect",
            pair.spec,
            "--detail",
            "summary",
        ],
        hashseed=hashseed,
    )
    families = run_legacy(["inspect", pair.spec, "--families"], hashseed=hashseed)
    plain = run_legacy(["validate", pair.spec], hashseed=hashseed)
    stability = run_legacy(["validate", pair.spec, "--stability"], hashseed=hashseed)

    entry.artifacts = {
        "spec": spec_bytes,
        "inspect_summary": render_artifact(
            pair, "tidal inspect --detail summary", [("", summary)]
        ),
        "inspect_families": render_artifact(
            pair, "tidal inspect --families", [("", families)]
        ),
        "validate": render_artifact(
            pair,
            "tidal validate, plain and --stability",
            [("plain", plain), ("stability", stability)],
        ),
    }
    entry.exits = {
        "inspect_summary": summary.exit_code,
        "inspect_families": families.exit_code,
        "validate": plain.exit_code,
        "validate_stability": stability.exit_code,
    }
    entry.error_class = classify(stability)
    return entry


def classify(stability: Capture) -> str | None:
    """Name why ``--stability`` did not return a stability verdict.

    Recorded per entry so the corpus-level weakness is measurable rather than
    anecdotal: 40 of 46 specs have free symbolic parameters and no committed
    defaults, so the tachyon check never runs at all.
    """
    if stability.exit_code == 0:
        return None
    if "Cannot evaluate symbolic coefficient" in stability.stderr:
        return "symbolic-coefficient-undefined"
    if "Failed to load equation system" in stability.stderr:
        return "spec-load-failure"
    return "other"


# --------------------------------------------------------------------------
# layout and manifest
# --------------------------------------------------------------------------

ARTIFACT_PATHS = {
    "spec": (SPECS_DIR, ".json"),
    "inspect_summary": (INSPECT_DIR, ".summary.txt"),
    "inspect_families": (INSPECT_DIR, ".families.txt"),
    "validate": (VALIDATE_DIR, ".txt"),
}


def artifact_path(kind: str, ident: str) -> Path:
    """Return the committed location of one artifact."""
    directory, suffix = ARTIFACT_PATHS[kind]
    return directory / f"{ident}{suffix}"


def build_manifest(entries: list[Entry], exclusions: list[Exclusion]) -> bytes:
    """Render the manifest.

    Deliberately free of anything that varies with HEAD, the machine or the
    clock -- see :func:`render_artifact`.  The verdict histogram is what lets
    ``tests_cosmo/test_oracles.py`` check the README's stated counts against the
    data, so documentation drift is caught rather than assumed away.
    """
    rows = []
    for entry in entries:
        artifacts = {}
        for kind, data in entry.artifacts.items():
            path = artifact_path(kind, entry.pair.ident)
            artifacts[kind] = {
                "path": path.relative_to(ORACLES).as_posix(),
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
            }
        rows.append(
            {
                "id": entry.pair.ident,
                "theory": entry.pair.theory,
                "source_spec": entry.pair.spec,
                "derivation_hash": entry.derivation_hash,
                "has_metadata_parameters": entry.has_metadata_parameters,
                "artifacts": artifacts,
                "exits": entry.exits,
                "stability_error_class": entry.error_class,
            }
        )

    summary = {
        "toml_candidates": len(entries) + len(exclusions),
        "pairs": len(entries),
        "excluded": len(exclusions),
        "validate_pass": sum(1 for e in entries if e.exits["validate"] == 0),
        "validate_fail": sum(1 for e in entries if e.exits["validate"] != 0),
        "stability_pass": sum(1 for e in entries if e.exits["validate_stability"] == 0),
        "stability_undefined_parameter": sum(
            1 for e in entries if e.error_class == "symbolic-coefficient-undefined"
        ),
    }

    document = {
        "generator": GENERATOR,
        "regenerate": REGENERATE,
        "corpus_predicate": CORPUS_PREDICATE,
        "summary": summary,
        "exclusions": [
            {
                "theory": x.theory,
                "expected_spec": x.expected_spec,
                "reason": x.reason,
            }
            for x in exclusions
        ],
        "entries": rows,
    }
    return (json.dumps(document, indent=2, sort_keys=False) + "\n").encode("utf-8")


def planned_files(entries: list[Entry]) -> dict[Path, bytes]:
    """Map every path this run owns to the bytes it should hold."""
    planned: dict[Path, bytes] = {MANIFEST: b""}
    for entry in entries:
        for kind, data in entry.artifacts.items():
            planned[artifact_path(kind, entry.pair.ident)] = data
    return planned


def prune(planned: set[Path]) -> list[Path]:
    """Delete fixtures this run did not produce.

    Without this, a renamed or removed theory leaves a stale fixture that
    ``--check`` can never see, and the corpus quietly stops matching the
    manifest that describes it.
    """
    removed = []
    for directory in (SPECS_DIR, INSPECT_DIR, VALIDATE_DIR):
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if path.is_file() and path not in planned:
                path.unlink()
                removed.append(path)
    return removed


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def cmd_list(pairs: list[Pair], exclusions: list[Exclusion]) -> int:
    """Print the resolved corpus without running legacy."""
    print(f"corpus predicate: {CORPUS_PREDICATE}")
    print(
        f"candidates: {len(pairs) + len(exclusions)}   pairs: {len(pairs)}   excluded: {len(exclusions)}"
    )
    print("\npairs:")
    for pair in pairs:
        print(f"  {pair.ident:<52} {pair.theory}")
    print("\nexcluded:")
    for excl in exclusions:
        print(
            f"  {excl.theory}\n      expected {excl.expected_spec}\n      {excl.reason}"
        )
    return 0


def freeze_all(pairs: list[Pair], *, hashseed: str | None = None) -> list[Entry]:
    """Run legacy across every pair, reporting progress to stderr."""
    entries = []
    for index, pair in enumerate(pairs, start=1):
        print(f"[{index}/{len(pairs)}] {pair.ident}", file=sys.stderr)
        entries.append(freeze_entry(pair, hashseed=hashseed))
    return entries


def cmd_write(entries: list[Entry], exclusions: list[Exclusion]) -> int:
    """Write every artifact and the manifest, pruning what is no longer ours."""
    for directory in (SPECS_DIR, INSPECT_DIR, VALIDATE_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    planned = planned_files(entries)
    planned[MANIFEST] = build_manifest(entries, exclusions)
    for path, data in planned.items():
        path.write_bytes(data)
    for removed in prune(set(planned)):
        print(f"pruned {removed.relative_to(REPO)}", file=sys.stderr)
    print(f"wrote {len(planned)} files under {ORACLES.relative_to(REPO)}")
    return 0


def cmd_check(entries: list[Entry], exclusions: list[Exclusion]) -> int:
    """Compare a fresh capture against the committed fixtures, writing nothing."""
    planned = planned_files(entries)
    planned[MANIFEST] = build_manifest(entries, exclusions)
    drift = []
    for path, data in sorted(planned.items()):
        if not path.is_file():
            drift.append(f"missing: {path.relative_to(REPO)}")
        elif path.read_bytes() != data:
            drift.append(f"differs: {path.relative_to(REPO)}")
    for directory in (SPECS_DIR, INSPECT_DIR, VALIDATE_DIR):
        if directory.is_dir():
            for path in sorted(directory.iterdir()):
                if path.is_file() and path not in planned:
                    drift.append(f"unlisted: {path.relative_to(REPO)}")
    if drift:
        print("\n".join(drift))
        print(f"\n{len(drift)} file(s) out of date. Regenerate with: {REGENERATE}")
        return 1
    print(f"{len(planned)} fixture(s) are current")
    return 0


def cmd_verify_determinism(pairs: list[Pair]) -> int:
    """Capture everything twice under different hash seeds and compare.

    Makes non-reproducibility a *detected* condition rather than one pinned away
    by the environment allowlist, which is the honest way to hold a byte gate.
    """
    first = {e.pair.ident: e.artifacts for e in freeze_all(pairs, hashseed="0")}
    second = {e.pair.ident: e.artifacts for e in freeze_all(pairs, hashseed="524287")}
    unstable = [
        f"{ident}/{kind}"
        for ident, artifacts in first.items()
        for kind, data in artifacts.items()
        if second[ident][kind] != data
    ]
    if unstable:
        print("non-deterministic artifacts:\n  " + "\n  ".join(unstable))
        return 1
    print(
        f"all {sum(len(a) for a in first.values())} artifacts reproduced byte-for-byte"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Freeze, verify, or describe the legacy oracle corpus."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="re-run legacy and compare against the committed fixtures; write nothing",
    )
    mode.add_argument(
        "--list",
        action="store_true",
        help="print the resolved corpus and exclusions; do not run legacy",
    )
    mode.add_argument(
        "--verify-determinism",
        action="store_true",
        help="capture twice under different hash seeds and assert equality",
    )
    parser.add_argument(
        "--only",
        metavar="ID",
        help="restrict to one spec id (debugging; not for writing fixtures)",
    )
    args = parser.parse_args(argv)

    if args.only and args.check:
        # A subset check would report every other committed fixture as unlisted.
        print("--only cannot be combined with --check: the check is corpus-wide")
        return 1

    pairs, exclusions = resolve_corpus()
    if args.only:
        pairs = [p for p in pairs if p.ident == args.only]
        if not pairs:
            print(f"no pair with id {args.only!r}; try --list")
            return 1

    if args.list:
        return cmd_list(pairs, exclusions)
    if args.verify_determinism:
        return cmd_verify_determinism(pairs)

    if args.only and not args.check:
        # Writing a subset would leave the manifest describing a corpus that is
        # not on disk, and prune() would delete every other fixture.
        entry = freeze_all(pairs)[0]
        for kind, data in entry.artifacts.items():
            print(f"--- {kind} ({len(data)} bytes) ---")
            print(data.decode("utf-8"), end="")
        return 0

    entries = freeze_all(pairs)
    if args.check:
        return cmd_check(entries, exclusions)
    return cmd_write(entries, exclusions)


if __name__ == "__main__":
    sys.exit(main())
