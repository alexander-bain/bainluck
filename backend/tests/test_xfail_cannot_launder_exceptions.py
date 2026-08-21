"""Repo-wide: an ``xfail`` may admit ``KnownFailure`` and nothing else.

This is the STRUCTURAL guard for a defect adversarial audit has now found twice,
where the second finding defeated the fix written for the first:

* ``C-2049-2050-REVIEW`` — bare ``xfail(strict=True)`` admitted a matcher raising
  ``RuntimeError``: ``34 passed, 47 xfailed, exit 0``. Fix: ``raises=AssertionError``.
* ``C-2058-REVIEW`` — that fix does not work. The test's own assertion and an
  ``AssertionError`` raised inside the matcher are the same class, so codex's
  crashing matcher produced ``56 xfailed, exit 0`` anyway.

Alex's instruction, 2026-08-21: *delete the capability, do not write rule three.*
So this file does not police a spelling. It asserts the only admissible exception
is one **production code cannot construct** (`backend/tests/known_failure.py`), which
makes "the test's expectation" and "a crash in the code under test" different types
before the marker is ever consulted.

TWO HALVES, AND THE SECOND IS THE ONE THAT WAS MISSING
-------------------------------------------------------

1. **The census** — AST over every test module. Structural: it reads the
   ``raises=`` keyword of each ``xfail`` call node. It is not a substring scan,
   because "substring absence is not an invariant" is how the sibling R5 guard was
   defeated.
2. **The behaviour** — real ``pytest`` subprocesses. The control this replaces
   *simulated* pytest's decision with ``issubclass(RuntimeError, admitted)`` and
   never executed it, which is exactly why it missed the ``AssertionError`` class
   it was written to catch. **A guard that reasons about pytest instead of running
   it cannot see the case where pytest disagrees with the reasoning.**
"""

from __future__ import annotations

import ast
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

TESTS_ROOT = Path(__file__).resolve().parent

#: The one admissible name. Compared as a NAME in the AST, so both
#: ``raises=KnownFailure`` and ``raises=known_failure.KnownFailure`` are accepted
#: and anything else — including a tuple containing it plus something wider — is not.
SANCTIONED = "KnownFailure"


def _label(path: Path) -> str:
    """A readable location that also works for the tmp-path mutant fixtures.

    The census is run both over the real tree and over generated mutants in
    ``tmp_path``; ``relative_to`` raises for the latter, and a guard that crashes
    on its own negative controls cannot demonstrate anything.
    """
    try:
        return str(path.relative_to(TESTS_ROOT))
    except ValueError:
        return path.name


def _test_modules() -> list[Path]:
    return sorted(p for p in TESTS_ROOT.rglob("*.py") if p.name != "__init__.py")


def _is_xfail_call(node: ast.AST) -> bool:
    """``pytest.mark.xfail(...)`` / ``mark.xfail(...)`` / ``xfail(...)`` as a CALL."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr == "xfail"
    return isinstance(func, ast.Name) and func.id == "xfail"


def _names_in(node: ast.AST) -> set[str]:
    out: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            out.add(sub.id)
        elif isinstance(sub, ast.Attribute):
            out.add(sub.attr)
    return out


def _xfail_violations(path: Path) -> list[str]:
    """Every ``xfail`` in this module that admits something other than KnownFailure."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:  # pragma: no cover - a broken test file is its own alarm
        return [f"{_label(path)}: unparseable ({exc})"]

    # This module names the banned constructs in prose and in its own fixtures, so
    # it is the one file that cannot be its own subject. Every OTHER file is.
    if path.resolve() == Path(__file__).resolve():
        return []

    out: list[str] = []
    for node in ast.walk(tree):
        if not _is_xfail_call(node):
            continue
        kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}
        raises = kwargs.get("raises")
        where = f"{_label(path)}:{node.lineno}"
        if raises is None:
            out.append(
                f"{where}: xfail with NO `raises=` — admits every exception, "
                "including a crash in the code under test (C-2049-2050-REVIEW)"
            )
            continue
        admitted = _names_in(raises)
        if admitted != {SANCTIONED}:
            out.append(
                f"{where}: xfail admits {sorted(admitted)} — the only admissible "
                f"exception is {SANCTIONED}, because production code can raise "
                "anything else, and then a crash reads as an expected failure "
                "(C-2058-REVIEW)"
            )
    return out


def _bare_xfail_calls(path: Path) -> list[str]:
    """Imperative ``pytest.xfail()`` — xfails at runtime, admitting everything after it."""
    if path.resolve() == Path(__file__).resolve():
        return []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:  # pragma: no cover
        return []
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "xfail":
            # `pytest.xfail(...)` is a CALL on the pytest module itself; the marker
            # form is `pytest.mark.xfail`, i.e. the attribute's own value is `mark`.
            owner = func.value
            is_marker = isinstance(owner, ast.Attribute) and owner.attr == "mark"
            is_marker = is_marker or (isinstance(owner, ast.Name) and owner.id == "mark")
            if not is_marker:
                out.append(
                    f"{_label(path)}:{node.lineno}: imperative "
                    "`pytest.xfail()` — it xfails unconditionally at runtime, so "
                    "every later exception is laundered"
                )
    return out


class TestTheCensus:
    def test_every_xfail_in_the_test_tree_admits_only_known_failure(self):
        violations: list[str] = []
        for path in _test_modules():
            violations.extend(_xfail_violations(path))
        assert not violations, (
            "xfail may admit ONLY `KnownFailure` (backend/tests/known_failure.py).\n"
            "Use `call_under_test(...)` for the code under test and "
            "`expect_known_failure(cond, reason)` for the characterised wrong "
            "answer.\n  " + "\n  ".join(violations)
        )

    def test_no_imperative_pytest_xfail_calls(self):
        violations: list[str] = []
        for path in _test_modules():
            violations.extend(_bare_xfail_calls(path))
        assert not violations, "\n  ".join(violations)

    def test_the_census_is_not_vacuous(self):
        """It must actually find things — over a real parse, not a claim."""
        seen = 0
        for path in _test_modules():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            seen += sum(1 for n in ast.walk(tree) if _is_xfail_call(n))
        assert seen >= 4, (
            f"only {seen} xfail call sites found across the test tree — the "
            "detector has probably stopped detecting"
        )


# ── the behavioural half: real pytest, not reasoning about pytest ────────────


_PREAMBLE = """
import sys
sys.path.insert(0, {tests_root!r})
sys.path.insert(0, {backend_root!r})
import pytest
from known_failure import KnownFailure, call_under_test, expect_known_failure
"""


def _run_pytest(tmp_path, body: str) -> subprocess.CompletedProcess:
    src = _PREAMBLE.format(
        tests_root=str(TESTS_ROOT), backend_root=str(TESTS_ROOT.parent)
    ) + textwrap.dedent(body)
    f = tmp_path / "test_generated_probe.py"
    f.write_text(src, encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-m", "pytest", str(f), "-p", "no:cacheprovider", "-q",
         "--no-header", "-o", "addopts="],
        capture_output=True, text=True, cwd=str(tmp_path), timeout=300,
    )


class TestTheLaunderingIsActuallyClosed:
    """Each case DRIVES pytest and reads its real verdict.

    The control these replace computed ``issubclass(RuntimeError, admitted)`` by
    hand. That is a model of pytest, and it agreed with pytest on the case it
    modelled while missing entirely the case it did not — the ``AssertionError``
    that ``raises=AssertionError`` happily admits.
    """

    def test_a_matcher_raising_AssertionError_is_NOT_an_expected_failure(self, tmp_path):
        """Codex's exact specimen: ``56 xfailed, exit 0`` must be impossible now."""
        r = _run_pytest(tmp_path, """
            def matcher(a, b):
                raise AssertionError("matcher implementation crashed")

            @pytest.mark.xfail(strict=True, raises=KnownFailure, reason="#2046")
            def test_probe():
                result = call_under_test(matcher, "a", "b")
                expect_known_failure(result is False, "characterised wrong answer")
        """)
        assert r.returncode != 0, (
            "an AssertionError from the code under test was admitted as an "
            f"expected failure — the C-2058-REVIEW laundering.\n{r.stdout}\n{r.stderr}"
        )
        assert "xfailed" not in r.stdout, f"reported as xfailed:\n{r.stdout}"
        assert "ProductionCodeRaised" in r.stdout or "1 failed" in r.stdout, r.stdout

    def test_a_matcher_raising_RuntimeError_is_NOT_an_expected_failure(self, tmp_path):
        """The C-2049-2050 class, re-proved by execution rather than by issubclass."""
        r = _run_pytest(tmp_path, """
            def matcher(a, b):
                raise RuntimeError("simulated matcher regression")

            @pytest.mark.xfail(strict=True, raises=KnownFailure, reason="#2046")
            def test_probe():
                result = call_under_test(matcher, "a", "b")
                expect_known_failure(result is False, "characterised wrong answer")
        """)
        assert r.returncode != 0, f"RuntimeError laundered:\n{r.stdout}\n{r.stderr}"
        assert "xfailed" not in r.stdout, f"reported as xfailed:\n{r.stdout}"

    def test_the_characterised_WRONG_ANSWER_still_xfails(self, tmp_path):
        """The capability that must SURVIVE.

        A guard that turned every known-failure into a failure would 'fix' the
        laundering by deleting the probe suite's reason to exist.
        """
        r = _run_pytest(tmp_path, """
            def matcher(a, b):
                return True          # the #2046 defect: accepts different teams

            @pytest.mark.xfail(strict=True, raises=KnownFailure, reason="#2046")
            def test_probe():
                result = call_under_test(matcher, "a", "b")
                expect_known_failure(result is False, "characterised wrong answer")
        """)
        assert r.returncode == 0, f"a genuine known-failure did not xfail:\n{r.stdout}"
        assert "1 xfailed" in r.stdout, r.stdout

    def test_a_FIXED_matcher_still_XPASSES_and_that_is_still_a_failure(self, tmp_path):
        """`strict=True`'s promotion signal must be intact: fixing #2046 turns the
        suite red, which is how anyone learns to delete the markers."""
        r = _run_pytest(tmp_path, """
            def matcher(a, b):
                return False         # #2046 repaired

            @pytest.mark.xfail(strict=True, raises=KnownFailure, reason="#2046")
            def test_probe():
                result = call_under_test(matcher, "a", "b")
                expect_known_failure(result is False, "characterised wrong answer")
        """)
        assert r.returncode != 0, f"XPASS did not fail the run:\n{r.stdout}"
        assert "xpassed" in r.stdout or "failed" in r.stdout, r.stdout

    def test_the_OLD_form_would_still_launder_which_is_why_it_is_banned(self, tmp_path):
        """The negative control for the BAN itself.

        Proves by execution that `raises=AssertionError` — the fix written after
        the first finding — really does admit a crashing matcher. Without this,
        the census above is a rule with no demonstrated reason.
        """
        r = _run_pytest(tmp_path, """
            def matcher(a, b):
                raise AssertionError("matcher implementation crashed")

            @pytest.mark.xfail(strict=True, raises=AssertionError, reason="old form")
            def test_probe():
                assert matcher("a", "b") is False
        """)
        assert r.returncode == 0 and "1 xfailed" in r.stdout, (
            "the old form no longer launders — if this is genuinely true the ban "
            f"can be revisited, but verify it deliberately:\n{r.stdout}"
        )


class TestTheGuardCatchesTheBannedForms:
    """The census must FAIL on each banned spelling — proven on real source."""

    @pytest.mark.parametrize("snippet,expected", [
        ("@pytest.mark.xfail(strict=True)\ndef test_x(): pass\n", "NO `raises=`"),
        ("@pytest.mark.xfail(strict=True, raises=AssertionError)\ndef test_x(): pass\n",
         "AssertionError"),
        ("@pytest.mark.xfail(raises=RuntimeError)\ndef test_x(): pass\n", "RuntimeError"),
        ("@pytest.mark.xfail(raises=(KnownFailure, AssertionError))\ndef test_x(): pass\n",
         "AssertionError"),
    ])
    def test_banned_forms_are_reported(self, tmp_path, snippet, expected):
        f = tmp_path / "test_mutant.py"
        f.write_text("import pytest\n" + snippet, encoding="utf-8")
        found = _xfail_violations(f)
        assert found, f"the census MISSED a banned form:\n{snippet}"
        assert expected in found[0], f"{expected!r} not named in: {found[0]}"

    def test_the_sanctioned_form_is_accepted(self, tmp_path):
        f = tmp_path / "test_ok.py"
        f.write_text(
            "import pytest\nfrom known_failure import KnownFailure\n"
            "@pytest.mark.xfail(strict=True, raises=KnownFailure)\n"
            "def test_x(): pass\n",
            encoding="utf-8",
        )
        assert _xfail_violations(f) == []

    def test_imperative_xfail_is_reported_but_the_marker_is_not(self, tmp_path):
        f = tmp_path / "test_imperative.py"
        f.write_text(
            "import pytest\n"
            "from known_failure import KnownFailure\n"
            "def test_a():\n    pytest.xfail('nope')\n"
            "@pytest.mark.xfail(raises=KnownFailure)\n"
            "def test_b(): pass\n",
            encoding="utf-8",
        )
        found = _bare_xfail_calls(f)
        assert len(found) == 1 and "imperative" in found[0], found
