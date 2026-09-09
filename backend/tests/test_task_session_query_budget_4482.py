"""A per-job query budget outlives its connection — #4482, ship #4456.

Eight task call sites armed a budget TIGHTER than #3776's resting bound with a
bare ``SET statement_timeout`` / ``SET lock_timeout`` at the top of their
session. ``app/tasks/kalshi.py`` stated the assumption in a comment: *"SET (not
SET LOCAL) persists across the incremental commits on this one connection."*

It is one connection only by luck. Measured on ``sqlalchemy.pool`` + ``Session``
(three statements, a commit after each, ``pool_size=3``, ``pool_pre_ping=True``)::

    pool_recycle=1800   dbapi conn id 4485521200 / 4485521200 / 4485521200 -> 1 distinct
    pool_recycle=0      dbapi conn id 4485806448 / 4485806928 / 4485806208 -> 3 distinct
    checkedout: 1 -> 0 after EVERY commit

So the connection goes back to the pool at each commit, and once ``pool_recycle``
(1800 s) or a ``pool_pre_ping`` failure replaces it, the next statement runs on a
connection carrying none of those ``SET``s: the statement bound reverts to the
resting 30 minutes and ``lock_timeout``, which has no resting value at all,
reverts to UNBOUNDED. No error, no log line.

``SET LOCAL`` is not the repair — at the five sites that commit in a loop it
would end the budget at the *first* commit of every run rather than at an
unlucky one. A budget that must outlive commits belongs to the CONNECTION, which
is what asyncpg's ``server_settings`` startup channel is.

The behaviour on a live server — that the budget survives a forced connection
replacement, and that the bare-``SET`` control does not — is graded in
``tests/integration/test_task_session_budget_recycle_pg.py``. What is graded
here is the contract and the ban.
"""

import ast
import pathlib
import re

import pytest

import app.tasks.base as base_mod
from app.services.database import DB_STATEMENT_TIMEOUT_MS, build_connect_args


PROD_URL = "postgresql+asyncpg://u:p@ec2-1-2-3-4.compute.amazonaws.com:5432/d"
LOCAL_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/bainluck"
SQLITE_URL = "sqlite+aiosqlite:///:memory:"

APP_DIR = pathlib.Path(base_mod.__file__).resolve().parents[1]


class TestConnectArgsCarryThePerJobBudget:
    def test_default_is_unchanged_by_this_change(self):
        # #3776's contract, restated here so that widening the new kwargs
        # cannot quietly change what an UNARMED engine gets.
        args = build_connect_args(PROD_URL)
        assert args["server_settings"] == {
            "statement_timeout": str(DB_STATEMENT_TIMEOUT_MS)
        }
        assert "lock_timeout" not in args["server_settings"]

    def test_statement_override_replaces_the_resting_value(self):
        args = build_connect_args(PROD_URL, statement_timeout_ms=60_000)
        assert args["server_settings"]["statement_timeout"] == "60000"
        assert args["server_settings"]["statement_timeout"] != str(
            DB_STATEMENT_TIMEOUT_MS
        )

    def test_lock_timeout_is_only_present_when_asked_for(self):
        # lock_timeout has NO resting value; adding one by default would be a
        # database-wide behaviour change riding a task fix.
        assert "lock_timeout" not in build_connect_args(PROD_URL)["server_settings"]
        armed = build_connect_args(PROD_URL, lock_timeout_ms=15_000)
        assert armed["server_settings"]["lock_timeout"] == "15000"

    def test_both_budgets_travel_together(self):
        args = build_connect_args(
            PROD_URL, statement_timeout_ms=90_000, lock_timeout_ms=20_000
        )
        assert args["server_settings"] == {
            "statement_timeout": "90000",
            "lock_timeout": "20000",
        }

    def test_values_are_strings_because_the_startup_packet_takes_strings(self):
        # asyncpg rejects a non-str server_settings value at connect time, which
        # would take down every task's connection rather than one statement.
        settings = build_connect_args(
            PROD_URL, statement_timeout_ms=1, lock_timeout_ms=2
        )["server_settings"]
        assert all(isinstance(v, str) for v in settings.values())

    def test_ssl_behaviour_is_untouched(self):
        assert build_connect_args(PROD_URL, statement_timeout_ms=1)["ssl"] == "require"
        assert "ssl" not in build_connect_args(LOCAL_URL, statement_timeout_ms=1)

    def test_non_asyncpg_url_takes_the_budget_without_raising(self):
        # sqlite in tests has no startup-parameter channel. Silently dropping
        # the budget there is correct; raising would make every unit test that
        # touches an armed session fail for a reason that is not the defect.
        args = build_connect_args(
            SQLITE_URL, statement_timeout_ms=60_000, lock_timeout_ms=15_000
        )
        assert "server_settings" not in args


class TestTheEngineThreadsItThrough:
    def test_engine_receives_the_budget_in_its_connect_args(self, monkeypatch):
        captured = {}

        def fake_create_async_engine(url, **kwargs):
            captured.update(kwargs)
            return object()

        monkeypatch.setattr(
            base_mod, "create_async_engine", fake_create_async_engine
        )
        monkeypatch.setattr(base_mod, "DATABASE_URL", PROD_URL)

        base_mod._get_task_engine(statement_timeout_ms=90_000, lock_timeout_ms=20_000)

        assert captured["connect_args"]["server_settings"] == {
            "statement_timeout": "90000",
            "lock_timeout": "20000",
        }

    def test_unarmed_engine_still_gets_only_the_resting_bound(self, monkeypatch):
        captured = {}

        monkeypatch.setattr(
            base_mod,
            "create_async_engine",
            lambda url, **kwargs: captured.update(kwargs) or object(),
        )
        monkeypatch.setattr(base_mod, "DATABASE_URL", PROD_URL)

        base_mod._get_task_engine()

        assert captured["connect_args"]["server_settings"] == {
            "statement_timeout": str(DB_STATEMENT_TIMEOUT_MS)
        }

    def test_get_task_session_forwards_both_kwargs_to_the_engine(self):
        # Asserted on the parsed CALL, not on a value: a test that only compared
        # a resulting number would pass against a forwarder that hardcoded it.
        # (CAL-P1075's banked lesson — a value comparison cannot grade a
        # derivation.)
        tree = ast.parse(pathlib.Path(base_mod.__file__).read_text())
        fn = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "get_task_session"
        )
        params = {a.arg for a in fn.args.kwonlyargs}
        assert {"statement_timeout_ms", "lock_timeout_ms"} <= params

        call = next(
            n
            for n in ast.walk(fn)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "_get_task_engine"
        )
        forwarded = {
            kw.arg: ast.unparse(kw.value)
            for kw in call.keywords
            if kw.arg is not None
        }
        assert forwarded.get("statement_timeout_ms") == "statement_timeout_ms"
        assert forwarded.get("lock_timeout_ms") == "lock_timeout_ms"


# ---------------------------------------------------------------------------
# The ban: no ninth site.
# ---------------------------------------------------------------------------

_BARE_SET = re.compile(r"\bSET\s+(?!LOCAL\b)(statement_timeout|lock_timeout)\b", re.I)


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """Ids of the string Constants that are docstrings, module/class/function."""
    out: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            out.add(id(first.value))
    return out


def find_bare_set(source: str, label: str = "<src>") -> list[str]:
    """Every bare ``SET <timeout>`` in a real string literal of ``source``.

    Comments and docstrings are invisible to this by construction: comments are
    not in the AST at all, and docstring Constants are excluded by identity.
    That is deliberate — a source-scan guard that reads prose is a guard its own
    target's documentation can blind (banked: a scan went green under the
    mutation it existed to catch because the function's docstring named the
    helper it grepped for). f-strings are covered: their literal segments are
    ``Constant`` children of a ``JoinedStr``.

    Scope stated rather than implied: only the FIRST statement of a module,
    class or function is a docstring. A triple-quoted string sitting loose in
    the middle of a block is an ordinary expression and IS flagged — found while
    running this battery's negative control, which was written that way and
    turned red for the right reason. The prose forms that actually occur in this
    repo are a comment and a real docstring, and both are live today with this
    green: ``app/tasks/base.py``'s ``get_task_session`` docstring says "SET
    statement_timeout" in so many words.
    """
    tree = ast.parse(source)
    skip = _docstring_nodes(tree)
    hits: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in skip:
            continue
        if _BARE_SET.search(node.value):
            hits.append(f"{label}:{node.lineno}: {node.value.strip()[:90]}")
    return hits


class TestTheDetectorItself:
    """A positive control validates the CALL; these validate the PREDICATE."""

    def test_it_flags_a_bare_set_in_code(self):
        src = 'await s.execute(text("SET statement_timeout = \'60s\'"))'
        assert find_bare_set(src)

    def test_it_flags_a_bare_set_built_by_an_fstring(self):
        src = 'await s.execute(text(f"SET statement_timeout = \'{n}s\'"))'
        assert find_bare_set(src)

    def test_it_flags_a_bare_lock_timeout(self):
        assert find_bare_set('text("SET lock_timeout = \'15s\'")')

    def test_it_does_not_flag_set_local(self):
        assert not find_bare_set('text("SET LOCAL statement_timeout = 50000")')
        assert not find_bare_set('text("SET LOCAL lock_timeout = \'15s\'")')

    def test_it_does_not_flag_a_module_docstring(self):
        assert not find_bare_set('"""We no longer SET statement_timeout here."""\nx = 1')

    def test_it_does_not_flag_a_function_docstring(self):
        src = 'def f():\n    """Never SET lock_timeout on the session."""\n    return 1'
        assert not find_bare_set(src)

    def test_it_does_not_flag_a_comment(self):
        assert not find_bare_set("# SET statement_timeout = '60s' was here\nx = 1")

    def test_it_is_case_insensitive_and_whitespace_tolerant(self):
        assert find_bare_set('text("set   statement_timeout = 0")')


class TestNoBareSetSurvivesInApp:
    def test_app_has_no_bare_set_of_either_timeout(self):
        hits: list[str] = []
        for path in sorted(APP_DIR.rglob("*.py")):
            rel = path.relative_to(APP_DIR.parent)
            hits.extend(find_bare_set(path.read_text(), str(rel)))
        assert hits == [], (
            "a session-scoped SET of a query budget is lost the moment the pool "
            "replaces the connection (#4482). Pass the budget to "
            "get_task_session(statement_timeout_ms=..., lock_timeout_ms=...) "
            "instead, or use SET LOCAL if the bound is meant to end with its "
            "transaction:\n  " + "\n  ".join(hits)
        )

    def test_the_scan_actually_reached_the_files_it_claims_to(self):
        # A rglob that matched nothing would make the assertion above vacuous.
        files = list(APP_DIR.rglob("*.py"))
        assert len(files) > 200, f"only {len(files)} files scanned under {APP_DIR}"
        assert (APP_DIR / "tasks" / "kalshi.py") in files


# ---------------------------------------------------------------------------
# The eight converted sites, asserted on the parsed call.
# ---------------------------------------------------------------------------

# (file, statement_timeout_ms expression, lock_timeout_ms expression). The
# probe sites pass a variable, so the expectation is the SOURCE of the argument,
# not a number — a literal that happens to equal today's value must not pass.
EXPECTED_ARMED_CALLS = {
    "futures_price_refresh.py": [("60000", "15000")],
    "kalshi_cliff.py": [
        ("60000", "15000"),
        ("int(timeout_s) * 1000", None),
        ("int(timeout_s) * 1000", None),
        ("int(timeout_s) * 1000", None),
    ],
    "kalshi.py": [
        ("90000", "20000"),
        ("90000", "20000"),
        ("60000", "15000"),
    ],
}


def _armed_calls(path: pathlib.Path):
    tree = ast.parse(path.read_text())
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if name != "get_task_session":
            continue
        kw = {k.arg: ast.unparse(k.value) for k in node.keywords if k.arg}
        if "statement_timeout_ms" not in kw:
            continue
        out.append((kw["statement_timeout_ms"], kw.get("lock_timeout_ms")))
    return out


@pytest.mark.parametrize("filename,expected", sorted(EXPECTED_ARMED_CALLS.items()))
def test_each_converted_site_still_arms_its_own_budget(filename, expected):
    found = _armed_calls(APP_DIR / "tasks" / filename)
    assert sorted(found, key=str) == sorted(expected, key=str), (
        f"{filename}: armed get_task_session() calls drifted. A site that loses "
        "its kwargs silently falls back to the 30-minute resting bound and an "
        "unbounded lock wait."
    )


def test_all_eight_sites_are_accounted_for():
    total = sum(len(v) for v in EXPECTED_ARMED_CALLS.values())
    assert total == 8, "the issue names eight sites; this table must cover them all"
