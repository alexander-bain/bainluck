"""Every `futures_outcomes` writer names `is_winner`, in BOTH construction shapes.

WHY THIS EXISTS (#4788). `FuturesOutcome.is_winner` is `boolean NULL DEFAULT
false` with a Python-side `default=False` beside it (`models.py:942`). NULL is
"nobody graded this"; `false` is an affirmative graded LOSS. So an INSERT that
merely **omits** the column does not leave the leg ungraded — it declares the
leg a loser. `OutcomeRow.tsx` renders `is_winner === false` on a resolved market
as a red **Lost · 0% · Settled**, so the omission reaches a reader as a verdict
nobody wrote. That is CAL-P1004R.

The class has now been found at three venues in a row. Kalshi was fixed at four
sites in September 2026; #4783 filed it again at Kalshi as stock; #4788 found it
still live at Polymarket (27,197 fabricated legs, 8,907 markets, newest row 36
minutes before filing) and at DataGolf (1,035 of 1,035 legs — every insert). A
per-site test would not have caught the second venue, and did not catch the
third. This is therefore a scan of the CLASS, across all of `app/`.

WHY THE EXISTING GUARD DID NOT FIRE. `test_futures_outcome_insert_grade_p1004r.py`
already covers this defect and covers it well — but it reads exactly one file,
`app/tasks/kalshi.py` (its own structural test hard-codes that path), and it
matches exactly one construction shape, `pg_insert(FuturesOutcome).values(...)`.
Both scopes were right for what CERT-948 was repairing and neither could ever
have seen `polymarket.py`, `datagolf.py` or `futures.py`. That file keeps its
venue-specific behavioural tests and its site-count tripwire for Kalshi; this
one is the class-wide arm. Neither replaces the other.

TWO CONSTRUCTION SHAPES, AND THEY NEED OPPOSITE SPELLINGS. This is the trap the
first version of this guard was specified without, and it is the half that
matters:

* Core — `pg_insert(FuturesOutcome).values(...)`. Here `is_winner=None` is
  correct: Core binds the parameter and emits SQL NULL.
* ORM — `FuturesOutcome(...)` + `session.add()`. Here `is_winner=None` is
  **inert**. SQLAlchemy applies the Python-side `default=False` to a value it
  reads as absent, and it reads an explicit `None` as absent, so the row still
  stores `false`. The model's own annotation says so in as many words: the
  default "still fires, including when ``None`` is passed explicitly". Only
  `null()` — a SQL NULL literal — survives.

So the guard is shape-aware: it requires the column to be NAMED in both shapes,
and on the ORM shape it additionally REFUSES `None`. Without that second rule a
future DataGolf-shaped site could be "fixed" to `is_winner=None`, satisfy a
naming-only scan, and keep fabricating losses at 100% — which is precisely the
outcome this file exists to make impossible. `test_orm_constructor_rejects_none`
below pins the semantics so the rule is demonstrated, not asserted.

WHAT THIS DOES NOT DO. It is static: it proves the column is named, not that the
value written is the right one for the row. It says nothing about the ~10,337
already-resolved fabricated legs (the stock repair, #4788 piece 3), nor about
how a reader should render a leg whose `resolution_source IS NULL` (the render
rule, #4788 piece 4 with #1638/#4783). It stops the flow; it does not drain it.
"""

import ast
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.models import FuturesOutcome

APP_ROOT = Path(__file__).resolve().parents[1] / "app"

#: The column whose omission fabricates a verdict.
GRADED_COLUMN = "is_winner"

#: Names that mean "build an INSERT against this model" — `insert` and the
#: dialect-specific `pg_insert` are both in use in this codebase.
INSERT_FUNCS = {"insert", "pg_insert"}

MODEL = "FuturesOutcome"


def _python_sources():
    for path in sorted(APP_ROOT.rglob("*.py")):
        yield path, ast.parse(path.read_text(), filename=str(path))


def _rel(path):
    return path.relative_to(APP_ROOT.parent)


def _chain_root(node):
    """Return the base call of a chained builder expression.

    `pg_insert(X).values(...).on_conflict_do_update(...).returning(...)` is a
    tree of `Call(func=Attribute(value=<inner call>))`; the base is the
    innermost `Call` whose `func` is a plain `Name`.
    """
    current = node
    while True:
        if isinstance(current, ast.Call):
            if isinstance(current.func, ast.Attribute):
                current = current.func.value
                continue
            return current
        if isinstance(current, ast.Attribute):
            current = current.value
            continue
        return current


def _is_model_insert_base(node):
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in INSERT_FUNCS
        and node.args
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == MODEL
    )


def _is_model_constructor(node):
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == MODEL
    )


def _keyword(call, name):
    for kw in call.keywords:
        if kw.arg == name:
            return kw
    return None


def _is_literal_none(node):
    return isinstance(node, ast.Constant) and node.value is None


def _is_sql_null(node):
    """`null()` / `sa.null()` — a SQL NULL literal, not a Python None."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "null"
    if isinstance(func, ast.Attribute):
        return func.attr == "null"
    return False


def _collect_sites():
    """Every place in `app/` that creates a `futures_outcomes` row.

    Returns (core_sites, orm_sites, unrecognised) where each site is a
    (path, lineno, call_node) triple.
    """
    core_sites = []
    orm_sites = []
    unrecognised = []

    for path, tree in _python_sources():
        # Map each `pg_insert(FuturesOutcome)` base to the `.values()` call
        # that carries its columns.
        values_by_base = {}
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "values"
            ):
                base = _chain_root(node)
                if _is_model_insert_base(base):
                    values_by_base[id(base)] = node

        for node in ast.walk(tree):
            if _is_model_insert_base(node):
                values_call = values_by_base.get(id(node))
                if values_call is None:
                    # An insert against this model that never calls `.values()`
                    # (e.g. `.from_select`) is a shape this guard cannot read.
                    # Fail loudly rather than pass silently.
                    unrecognised.append((path, node.lineno, node))
                else:
                    core_sites.append((path, node.lineno, values_call))
            elif _is_model_constructor(node):
                orm_sites.append((path, node.lineno, node))

    return core_sites, orm_sites, unrecognised


def test_every_futures_outcome_write_names_is_winner():
    """No writer may omit `is_winner` — omission stores a graded LOSS."""
    core_sites, orm_sites, unrecognised = _collect_sites()

    # The scan must actually be finding things; a refactor that renames the
    # model or the insert helpers would otherwise turn this file into a
    # no-op that reports green forever.
    assert core_sites, "found no Core inserts against FuturesOutcome — scan is blind"
    assert orm_sites, "found no ORM constructions of FuturesOutcome — scan is blind"

    offenders = []
    for path, lineno, call in core_sites + orm_sites:
        if _keyword(call, GRADED_COLUMN) is None:
            offenders.append(f"{_rel(path)}:{lineno}")

    assert not offenders, (
        "These `futures_outcomes` writers omit `is_winner`, so every row they "
        "insert stores an affirmative graded LOSS (CAL-P1004R) on a leg nobody "
        "called:\n  " + "\n  ".join(offenders) + "\n\n"
        "Name it explicitly. On a `pg_insert(...).values()` site write "
        "`is_winner=None, resolution_source=None`. On a `FuturesOutcome(...)` "
        "constructor write `is_winner=null(), resolution_source=null()` — see "
        "test_orm_constructor_rejects_none in this file for why `None` does "
        "not work there."
    )

    assert not unrecognised, (
        "Insert against FuturesOutcome in a shape this guard cannot read "
        "(no `.values()` in the chain): "
        + ", ".join(f"{_rel(p)}:{ln}" for p, ln, _ in unrecognised)
        + " — teach the guard this shape rather than deleting the check."
    )


def test_orm_constructor_sites_use_sql_null_not_python_none():
    """On the ORM path `is_winner=None` is silently defaulted back to `false`."""
    _, orm_sites, _ = _collect_sites()

    inert = []
    for path, lineno, call in orm_sites:
        kw = _keyword(call, GRADED_COLUMN)
        if kw is None:
            continue  # reported by the naming test above
        if _is_literal_none(kw.value):
            inert.append(f"{_rel(path)}:{lineno}")
        elif not _is_sql_null(kw.value):
            # A variable or expression: can't be judged statically. Allowed —
            # the naming test has already proved the column is addressed.
            continue

    assert not inert, (
        "These ORM constructor sites pass `is_winner=None`, which SQLAlchemy "
        "treats as absent and overwrites with the Python-side `default=False` "
        "— the row still stores a graded LOSS. Use `null()`:\n  "
        + "\n  ".join(inert)
    )


def _sqlite_engine():
    engine = sa.create_engine("sqlite://")
    # Just this table: the FK targets are irrelevant to what is under test and
    # SQLite does not resolve them at CREATE time.
    FuturesOutcome.__table__.create(engine)
    return engine


def _row(session, external_id):
    return session.execute(
        sa.select(FuturesOutcome.is_winner).where(
            FuturesOutcome.external_id == external_id
        )
    ).scalar_one()


def test_orm_constructor_rejects_none():
    """The semantics the static rule above rests on, demonstrated not asserted.

    Omitting the column and passing `None` are the SAME on the ORM path — both
    store `false`. Only `null()` stores NULL. If SQLAlchemy ever changes this,
    this test tells us before the guard's shape rule becomes cargo cult.
    """
    engine = _sqlite_engine()
    with Session(engine) as session:
        session.add(
            FuturesOutcome(
                market_id=1, external_id="omitted", name="omitted",
                current_probability=0.5,
            )
        )
        session.add(
            FuturesOutcome(
                market_id=1, external_id="python_none", name="python_none",
                current_probability=0.5, is_winner=None,
            )
        )
        session.add(
            FuturesOutcome(
                market_id=1, external_id="sql_null", name="sql_null",
                current_probability=0.5, is_winner=sa.null(),
            )
        )
        session.commit()

    with Session(engine) as session:
        assert _row(session, "omitted") is False, (
            "omitting is_winner should store the DEFAULT false — if this fails "
            "the whole premise of #4788 has changed"
        )
        assert _row(session, "python_none") is False, (
            "an explicit None on the ORM path is expected to be swallowed by "
            "`default=False`; if it now stores NULL, the `null()` calls in "
            "datagolf.py can be simplified and this guard's ORM rule relaxed"
        )
        assert _row(session, "sql_null") is None, (
            "null() must reach the database as SQL NULL — this is the only "
            "spelling that leaves an ORM-inserted leg ungraded"
        )


def test_core_insert_none_is_a_real_null():
    """And on the Core path `None` IS a NULL — which is why the rule is split."""
    engine = _sqlite_engine()
    with engine.begin() as conn:
        conn.execute(
            sa.insert(FuturesOutcome).values(
                market_id=1, external_id="core_omitted", name="core_omitted",
                current_probability=0.5,
            )
        )
        conn.execute(
            sa.insert(FuturesOutcome).values(
                market_id=1, external_id="core_none", name="core_none",
                current_probability=0.5, is_winner=None,
            )
        )

    with Session(engine) as session:
        assert _row(session, "core_omitted") is False
        assert _row(session, "core_none") is None, (
            "a Core insert naming is_winner=None must emit SQL NULL — the "
            "polymarket.py/kalshi.py fixes all rely on this"
        )
