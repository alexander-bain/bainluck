"""Guard: nothing under backend/ may import itself via a `backend.` prefix.

CI runs pytest with `working-directory: backend` (see .github/workflows/ci.yml),
so `backend` is NOT an importable package from inside it. A module that does
`from backend.scripts.evals.X import y` raises ModuleNotFoundError at COLLECTION
time -- and pytest exits non-zero on a collection error no matter how many tests
pass, so a single one of these reds the whole deploy.

This is not hypothetical and it is not a one-off. Fifteen eval contract tests
landed with this exact wrong prefix across two Integrator cycles (INT-025,
INT-026), each batch found only because someone happened to run collection over
the shared master tree before pushing. Repairing the instances did not stop the
next batch arriving, so the class gets a guard instead of another manual sweep.

The correct convention is the one the other ~107 eval tests already use:

    RIGHT:  from scripts.evals.my_contract import verdict
    WRONG:  from backend.scripts.evals.my_contract import verdict

(The examples above carry RIGHT/WRONG prefixes deliberately -- an unprefixed
bad example would trip this module's own guard, which is how the guard's first
run failed on its own docstring.)
"""

import re
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent

# Directories that ship to CI and are therefore subject to the collection gate.
SCANNED_DIRS = ("app", "scripts", "tests")

# `from backend.x import y` / `import backend.x` at the start of a line, allowing
# for indentation (a function-local import fails just as hard, only later).
#
# Indentation is `[ \t]*`, NOT `\s*`: `\s` matches newlines, so `\s*` would let a
# match begin on a preceding blank line and the reported statement would come back
# empty. That is exactly what the first version of this guard did.
BAD_IMPORT_RE = re.compile(r"^[ \t]*(?:from|import)[ \t]+backend\.", re.MULTILINE)


def _python_files():
    for directory in SCANNED_DIRS:
        root = BACKEND_ROOT / directory
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            yield path


def test_no_module_imports_itself_through_the_backend_prefix():
    offenders = []
    for path in _python_files():
        try:
            source = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for match in BAD_IMPORT_RE.finditer(source):
            line_no = source.count("\n", 0, match.start()) + 1
            statement = source[match.start() : source.find("\n", match.start())].strip()
            offenders.append(f"{path.relative_to(BACKEND_ROOT)}:{line_no}: {statement}")

    assert not offenders, (
        "These modules import through a `backend.` prefix, which cannot resolve "
        "under CI's `working-directory: backend` and will fail at collection "
        "(reddening the entire backend-tests job):\n  "
        + "\n  ".join(sorted(offenders))
        + "\n\nDrop the `backend.` prefix -- e.g. `from scripts.evals.X import y`."
    )


def test_guard_actually_detects_the_bad_pattern():
    """The guard above is only worth having if it can fail.

    Without this, deleting the regex body would leave a permanently-green test
    that asserts nothing -- the exact failure mode the guard exists to prevent.
    """
    assert BAD_IMPORT_RE.search("from backend.scripts.evals.foo import bar")
    assert BAD_IMPORT_RE.search("import backend.app.main")
    assert BAD_IMPORT_RE.search("    from backend.scripts.evals.foo import bar")

    # Must NOT fire on the correct convention, nor on unrelated names that
    # merely start with the same letters.
    assert not BAD_IMPORT_RE.search("from scripts.evals.foo import bar")
    assert not BAD_IMPORT_RE.search("from app.utils.sport_keys import SPORT_LEAGUE_MAP")
    assert not BAD_IMPORT_RE.search("from backend_helpers import thing")
    assert not BAD_IMPORT_RE.search("# from backend.scripts.evals.foo import bar\n")
