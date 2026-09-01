"""Every third-party module the test suite imports must be named in ``requirements.txt``.

WHY THIS EXISTS (CAL-P165). CAL-P164 added
``test_calibration_staged_census_contract_p164.py``, whose whole point is to parse the
frozen statement's rendered SQL with a real Postgres parser — ``import sqlglot``. The
manifest never named it. It passed every local gate, including a full 24,953-test suite,
because the authoring sandbox happened to have sqlglot installed standalone
(``Required-by:`` empty — nothing pulled it in). CI installs from ``requirements.txt``
alone, so that guard would have raised ``ModuleNotFoundError`` at COLLECTION time on the
one machine whose verdict counts.

The class is not "sqlglot was forgotten". It is **a gate that only runs where it was
written**. A guard absent from CI is worse than no guard, because the branch reads green
while the thing the guard watches is unwatched. So this test asserts the manifest is a
superset of what the suite actually imports, and it is deliberately scoped to
``backend/tests/`` — the tree CI collects — rather than to ``scripts/``, where undeclared
imports are pre-existing, intentional and not on any deploy path.

HOW IT RESOLVES A NAME. Import names and distribution names differ (``yaml`` ->
``PyYAML``, ``dateutil`` -> ``python-dateutil``), so the mapping is taken from the live
environment via ``importlib.metadata.packages_distributions()`` rather than guessed from
a hand table that would rot. A module that resolves to NO installed distribution and is
not a local sibling is reported, not skipped: "I could not identify it" and "it is fine"
are different answers, and only one of them is safe to be silent about.

AND IT RAISES ON WHAT IT CANNOT PARSE. A scanner that swallows a ``SyntaxError`` quietly
shrinks its own population and then reports a clean sweep of the files it managed to
read. Unparsable files are collected and failed on explicitly.

WHAT ``LOCAL`` MEANS, AND THE FALSE POSITIVE THAT TAUGHT IT (CAL-P172). The first version
knew three roots a bare import could resolve against — ``tests/`` and the two ``scripts/``
trees — and missed a fourth: ``backend/`` ITSELF. ``pytest.ini`` lives there, so it is
pytest's rootdir and goes on ``sys.path``, which makes ``backend/*.py`` importable by bare
name. The gap was invisible while this branch stood alone and surfaced the moment it was
rebased onto a master that had gained ``tests/test_ws_fast_lane_wiring.py`` and
``tests/test_ws_recycle_cancellation_q460.py``, both of which ``import run_kalshi_ws`` —
``backend/run_kalshi_ws.py``, a runner script. The guard called it an undeclared
third-party package and would have turned master's CI red on merge.

The lesson is the guard's own: **"resolves to NO INSTALLED DISTRIBUTION" is a statement
about the environment, not about the repo.** Before reporting a name, every place it could
legitimately come from has to be enumerated — and the enumeration has to be tight, which
is why the new root is scanned non-recursively (see ``BACKEND_TOPLEVEL_ROOT``).
"""

from __future__ import annotations

import ast
import importlib.metadata as importlib_metadata
import re
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent
TESTS_ROOT = BACKEND_ROOT / "tests"
REQUIREMENTS = BACKEND_ROOT / "requirements.txt"

#: Directories whose ``.py`` files a test can import by bare name because they get put on
#: ``sys.path``. There are TWO `scripts/` trees and they are not the same one:
#: ``backend/scripts/`` and the repo-root ``scripts/`` (which holds the stdlib-only
#: standalone operational scripts, e.g. ``daily_health_check.py``). Scanning only the
#: first reported a sibling import as an undeclared third-party package.
SIBLING_IMPORT_ROOTS = (TESTS_ROOT, BACKEND_ROOT / "scripts", REPO_ROOT / "scripts")

#: ``backend/`` itself is pytest's rootdir (``pytest.ini`` lives there), so pytest puts it
#: on ``sys.path`` and its TOP-LEVEL ``.py`` files are importable by bare name —
#: ``import run_kalshi_ws`` in ``tests/test_ws_fast_lane_wiring.py`` resolves to
#: ``backend/run_kalshi_ws.py``, a runner script, not a package.
#:
#: Scanned NON-recursively, and that is the whole point. ``BACKEND_ROOT`` is not in
#: ``SIBLING_IMPORT_ROOTS`` because those are walked with ``rglob``: adding it there would
#: absorb every module stem under ``backend/`` — all of ``app/``, every test file — into
#: the local-name set, and the guard would then wave through any third-party package that
#: happened to share a name with some module in the tree. Only the files that are actually
#: importable by bare name belong here, and that is exactly ``backend/*.py``.
BACKEND_TOPLEVEL_ROOT = BACKEND_ROOT

#: Modules that are legitimately imported without their own manifest line, each with the
#: reason it is not a defect. Keep this SHORT and keep the reasons honest — an allowlist
#: is where a guard goes to die.
ALLOWED_UNDECLARED = {
    # Celery's own messaging layer. `celery` is declared and pins kombu exactly; the
    # test suite reaches for `kombu.exceptions` directly when asserting retry
    # behaviour. Declaring it separately would let the two versions drift apart.
    "kombu": "transitive of the declared `celery`, and version-locked by it",
}


def _normalise(name: str) -> str:
    """PEP 503 name normalisation, so `python-dateutil` == `python_dateutil`."""
    return re.sub(r"[-_.]+", "-", name).lower()


def declared_distributions(requirements_path: Path) -> set[str]:
    """The set of distribution names ``requirements.txt`` names, normalised."""
    declared: set[str] = set()
    for raw in requirements_path.read_text().splitlines():
        line = raw.split("#")[0].strip()
        if not line or line.startswith("-"):
            continue
        name = re.split(r"[<>=!\[;]", line)[0].strip()
        if name:
            declared.add(_normalise(name))
    return declared


def _local_module_names(*roots: Path) -> set[str]:
    """Module names that resolve to a file in the repo rather than to a package.

    `tests/` and `scripts/` put themselves on `sys.path`, so `import dbq_probe` finds a
    sibling file. Those are not third-party and must not be reported as missing.
    """
    names = {"app", "tests", "scripts", "alembic", "conftest"}
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            names.add(path.stem)
            if (path.parent / "__init__.py").exists():
                names.add(path.parent.name)
    return names


def _toplevel_module_names(root: Path) -> set[str]:
    """Bare-importable module names contributed by ``root`` itself, NOT its subtree.

    Deliberately ``glob``, never ``rglob`` — see ``BACKEND_TOPLEVEL_ROOT``. A recursive
    walk here would make the guard's local-name set swallow the whole backend tree.
    """
    if not root.exists():
        return set()
    return {
        path.stem
        for path in root.glob("*.py")
        if "__pycache__" not in path.parts
    }


def local_import_names() -> set[str]:
    """Every name a test can import without it being a third-party dependency."""
    return _local_module_names(*SIBLING_IMPORT_ROOTS) | _toplevel_module_names(
        BACKEND_TOPLEVEL_ROOT
    )


def _top_level_imports(tree: ast.AST) -> set[str]:
    """Top-level module names imported by a parsed file, ignoring relative imports."""
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            # `level > 0` is a relative import — always local by construction.
            if node.level == 0 and node.module:
                modules.add(node.module.split(".")[0])
    return modules


def scan_undeclared_imports(
    tests_root: Path,
    requirements_path: Path,
    local_names: set[str],
    allowed: dict[str, str] | None = None,
) -> tuple[dict[str, list[str]], list[str], int]:
    """Return ``(violations, unparsable, files_scanned)``.

    ``violations`` maps ``"<module> (dist=<...>)"`` to the files that import it.
    ``unparsable`` is every file that failed to parse — the caller MUST fail on it
    rather than let a shrunken population read as a clean sweep.
    """
    allowed = allowed or {}
    declared = declared_distributions(requirements_path)
    package_map = importlib_metadata.packages_distributions()
    stdlib = set(sys.stdlib_module_names)

    violations: dict[str, list[str]] = {}
    unparsable: list[str] = []
    scanned = 0

    for path in sorted(tests_root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        scanned += 1
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError) as exc:
            unparsable.append(f"{path}: {exc}")
            continue
        for module in _top_level_imports(tree):
            if module in stdlib or module in local_names or module in allowed:
                continue
            dists = [_normalise(d) for d in package_map.get(module, [])]
            if any(d in declared for d in dists):
                continue
            key = f"{module} (resolves to {dists or 'NO INSTALLED DISTRIBUTION'})"
            violations.setdefault(key, []).append(
                str(path.relative_to(tests_root.parent))
            )

    return violations, unparsable, scanned


# --------------------------------------------------------------------------------------
# The guard itself
# --------------------------------------------------------------------------------------


def test_every_third_party_module_the_tests_import_is_declared_in_requirements():
    local_names = local_import_names()
    violations, unparsable, scanned = scan_undeclared_imports(
        TESTS_ROOT, REQUIREMENTS, local_names, ALLOWED_UNDECLARED
    )

    assert not unparsable, (
        "The scanner could not parse these files, so its sweep is INCOMPLETE and its "
        "silence means nothing. Fix the files or the scanner — do not ignore this:\n  "
        + "\n  ".join(unparsable)
    )

    assert not violations, (
        "These modules are imported by the test suite but named nowhere in "
        "backend/requirements.txt. CI installs from that file alone, so each one is a "
        "collection-time ModuleNotFoundError on the only machine whose verdict counts "
        "— even though it passes locally, where the package happens to be installed.\n"
        + "\n".join(
            f"  {module}\n    imported by: {', '.join(files)}"
            for module, files in sorted(violations.items())
        )
    )


def test_the_scan_actually_covered_the_suite():
    """Non-vacuity: a scan that silently walked an empty tree would pass the guard."""
    local_names = local_import_names()
    _, _, scanned = scan_undeclared_imports(
        TESTS_ROOT, REQUIREMENTS, local_names, ALLOWED_UNDECLARED
    )
    assert scanned > 500, (
        f"Only {scanned} test files scanned. The suite is far larger than that, so the "
        "scanner is looking at the wrong place and its clean result is meaningless."
    )


def test_sqlglot_is_declared_because_a_committed_guard_imports_it():
    """The specific regression: CAL-P164's contract guard needs a real SQL parser.

    Pinned by NAME rather than left to the sweep above, because the sweep resolves
    through the LIVE environment: if sqlglot were dropped from the manifest AND
    uninstalled, `packages_distributions()` would return nothing for it and the sweep
    would report it — but if it were dropped from the manifest while staying installed,
    only an explicit check states which file depends on it and why.
    """
    contract_guard = TESTS_ROOT / "test_calibration_staged_census_contract_p164.py"
    assert contract_guard.exists(), (
        "CAL-P164's staged-census contract guard is gone. If it was deliberately "
        "removed, remove this pin and the sqlglot line in requirements.txt with it."
    )
    assert "import sqlglot" in contract_guard.read_text(), (
        "The contract guard no longer imports sqlglot. Either it stopped parsing the "
        "rendered SQL for real — which was the entire point, and a regex would be a "
        "downgrade — or the dependency can now be dropped."
    )
    assert "sqlglot" in declared_distributions(REQUIREMENTS), (
        "sqlglot is imported by a committed test but absent from requirements.txt. "
        "This is the exact CAL-P164 defect: green locally, ModuleNotFoundError in CI."
    )


# --------------------------------------------------------------------------------------
# Negative controls — the guard is shown able to go RED
# --------------------------------------------------------------------------------------


def test_scanner_reports_an_undeclared_third_party_import(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_thing.py").write_text("import sqlglot\n")
    (tmp_path / "requirements.txt").write_text("pytest>=7.4.4\n")

    violations, unparsable, scanned = scan_undeclared_imports(
        tests_dir, tmp_path / "requirements.txt", local_names=set()
    )

    assert scanned == 1
    assert not unparsable
    assert any(
        key.startswith("sqlglot") for key in violations
    ), f"The scanner failed to flag an undeclared import: {violations}"


def test_scanner_accepts_the_import_once_it_is_declared(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_thing.py").write_text("import sqlglot\n")
    (tmp_path / "requirements.txt").write_text("pytest>=7.4.4\nsqlglot>=30.14.0\n")

    violations, _, _ = scan_undeclared_imports(
        tests_dir, tmp_path / "requirements.txt", local_names=set()
    )

    assert not violations, f"A declared dependency was still reported: {violations}"


def test_scanner_surfaces_a_file_it_cannot_parse_instead_of_skipping_it(tmp_path):
    """A swallowed SyntaxError shrinks the population and reads as a clean sweep."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_broken.py").write_text("def (:\n")
    (tmp_path / "requirements.txt").write_text("pytest>=7.4.4\n")

    violations, unparsable, scanned = scan_undeclared_imports(
        tests_dir, tmp_path / "requirements.txt", local_names=set()
    )

    assert scanned == 1
    assert len(unparsable) == 1 and "test_broken.py" in unparsable[0]
    assert not violations


def test_scanner_does_not_flag_local_sibling_modules(tmp_path):
    """`tests/` self-shadows on sys.path, so a sibling import is not third-party."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "helper_thing.py").write_text("VALUE = 1\n")
    (tests_dir / "test_thing.py").write_text("import helper_thing\n")
    (tmp_path / "requirements.txt").write_text("pytest>=7.4.4\n")

    violations, _, _ = scan_undeclared_imports(
        tests_dir,
        tmp_path / "requirements.txt",
        local_names=_local_module_names(tests_dir),
    )

    assert (
        not violations
    ), f"A local sibling was misreported as third-party: {violations}"


def test_a_backend_toplevel_runner_module_is_not_read_as_third_party():
    """CAL-P172's regression, pinned against the REAL tree rather than a fixture.

    ``backend/run_kalshi_ws.py`` is a runner script that two committed WS tests import by
    bare name. It has no distribution and never will. If the local-name set stops
    covering ``backend/*.py``, this goes red here instead of on master's CI.
    """
    runner = BACKEND_ROOT / "run_kalshi_ws.py"
    assert runner.exists(), (
        "backend/run_kalshi_ws.py is gone. If it moved, this pin should name wherever the "
        "top-level runner modules live now — do not just delete it, or the false-positive "
        "class it guards comes back silently."
    )
    assert "run_kalshi_ws" in local_import_names(), (
        "A repo-local top-level module is not in the local-name set, so the sweep will "
        "report it as an undeclared third-party package."
    )


def test_the_toplevel_scan_is_not_recursive(tmp_path):
    """The tightness half of CAL-P172 — an rglob here would gut the whole guard.

    If ``backend/`` were walked recursively, every module stem under ``app/`` and
    ``tests/`` would enter the local-name set, and any third-party package sharing one of
    those names would be waved through. This is the control that keeps the fix narrow.
    """
    (tmp_path / "toplevel_runner.py").write_text("VALUE = 1\n")
    nested = tmp_path / "nested_pkg"
    nested.mkdir()
    (nested / "buried_module.py").write_text("VALUE = 2\n")

    names = _toplevel_module_names(tmp_path)

    assert "toplevel_runner" in names
    assert "buried_module" not in names, (
        "The top-level scan recursed. That widens the local-name set to the entire "
        "backend tree and silently disarms the undeclared-import sweep."
    )


def test_widening_the_local_names_did_not_disarm_the_sweep(tmp_path):
    """Non-vacuity for CAL-P172: the guard must still go RED on a real violation.

    Anchored on the REAL local-name set, not an empty one, so it proves the widened set
    still reports an undeclared package rather than proving a fixture does.
    """
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_thing.py").write_text("import some_undeclared_pkg\n")
    (tmp_path / "requirements.txt").write_text("pytest>=7.4.4\n")

    violations, _, _ = scan_undeclared_imports(
        tests_dir, tmp_path / "requirements.txt", local_names=local_import_names()
    )

    assert any(key.startswith("some_undeclared_pkg") for key in violations), (
        f"The widened local-name set swallowed a genuine violation: {violations}"
    )


def test_relative_imports_are_never_reported(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_thing.py").write_text("from . import sibling\n")
    (tmp_path / "requirements.txt").write_text("pytest>=7.4.4\n")

    violations, _, _ = scan_undeclared_imports(
        tests_dir, tmp_path / "requirements.txt", local_names=set()
    )

    assert not violations, f"A relative import was reported: {violations}"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("sentry-sdk[fastapi,celery]>=2.0.0", "sentry-sdk"),
        ("PyYAML>=6.0  # Horizon Calendar", "pyyaml"),
        ("python_dateutil>=2.8.2", "python-dateutil"),
        ("pytest>=7.4.4", "pytest"),
    ],
)
def test_requirement_lines_normalise_to_comparable_names(tmp_path, raw, expected):
    path = tmp_path / "requirements.txt"
    path.write_text(raw + "\n")
    assert declared_distributions(path) == {expected}


def test_comments_and_blank_lines_are_not_read_as_dependencies(tmp_path):
    path = tmp_path / "requirements.txt"
    path.write_text("# Development\n\n   \npytest>=7.4.4\n")
    assert declared_distributions(path) == {"pytest"}
