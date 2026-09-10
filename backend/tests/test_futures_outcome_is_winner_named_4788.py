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

THE RECOGNISER RESOLVES THE MODEL, IT DOES NOT MATCH A SPELLING (#4819). The
first version of this file asked whether a call's `func` was an `ast.Name` whose
`id` was literally `"FuturesOutcome"`. A class guard with a spelling-dependent
blind spot is the failure mode it was written to end — it is exactly why
`test_futures_outcome_insert_grade_p1004r.py` could not see two of the three
venues. Every one of `models.FuturesOutcome(...)`, `m.FuturesOutcome(...)`,
`FuturesOutcome as FO` then `FO(...)`, `pg_insert(models.FuturesOutcome)` and
`sa.insert(...)` is the same INSERT and the same fabricated verdict, and every
one of them walked straight past. Local aliases are now read from the module's
own imports and the qualified forms are accepted on the attribute; the
`sa.insert(...)` case additionally needed `_chain_root`'s stop condition fixed,
which had been losing such sites entirely rather than mis-filing them.

Measured when the widening landed: the site set over `app/` is UNCHANGED —
9 Core + 2 ORM, the same eleven lines before and after — so this closes a blind
spot rather than repairing a live defect, which is the right time to close one.

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


def _module_aliases(tree):
    """Local names in this module that bind to `FuturesOutcome`.

    #4819. The first version of this guard matched the model by SPELLING — an
    `ast.Name` whose `id` was literally `"FuturesOutcome"` — so a writer that
    imported it under any other local name was invisible to a scan whose entire
    purpose is to be class-wide. `from app.models.models import FuturesOutcome
    as FO` then `FO(...)` is the same INSERT and the same fabricated verdict.

    Aliases are read from the module's own imports rather than guessed, and
    `MODEL` itself is always in the set: a file that never imports the name
    cannot construct it, and including the bare spelling keeps the recogniser
    honest on the (common) unaliased case even if an import walk ever misses.
    """
    aliases = {MODEL}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == MODEL:
                    aliases.add(alias.asname or alias.name)
    return aliases


def _insert_aliases(tree):
    """Local names bound to an INSERT builder (`insert`, `pg_insert`, aliases).

    #4819, the same defect one level over: `from sqlalchemy import insert as
    ins` was unreadable, and so was every dialect import under a fresh name.
    """
    aliases = set(INSERT_FUNCS)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in INSERT_FUNCS:
                    aliases.add(alias.asname or alias.name)
    return aliases


def _is_model_ref(node, model_aliases):
    """Does this expression name the model, however it is spelled?

    Two arms, and the second is deliberately broad. A bare `ast.Name` must be a
    known local alias, because `FuturesOutcome` is the only thing that binding
    can be. An `ast.Attribute` is accepted on its `attr` alone — ANY
    `<something>.FuturesOutcome` — rather than by resolving `<something>` back
    to `app.models.models`.

    That is the safe direction on purpose. Resolving the module would mean
    enumerating the spellings that reach it (`import app.models.models as m`,
    `from app.models import models`, `from app import models`, plain
    `import app.models.models` used as a four-dot path…), and every spelling
    missed is a writer the guard cannot see — the exact failure #4819 exists to
    end. The cost of the broad rule is a false POSITIVE: some unrelated
    `foo.FuturesOutcome(...)` would be scanned and required to name `is_winner`.
    There is no such object, and if one ever appears the guard demanding one
    extra keyword is a far better outcome than a fabricated loss shipping.
    """
    if isinstance(node, ast.Name):
        return node.id in model_aliases
    if isinstance(node, ast.Attribute):
        return node.attr == MODEL
    return False


def _is_insert_func(func, insert_aliases):
    """`insert` / `pg_insert` / an alias of either / `sa.insert` / `pg.insert`."""
    if isinstance(func, ast.Name):
        return func.id in insert_aliases
    if isinstance(func, ast.Attribute):
        return func.attr in INSERT_FUNCS
    return False


def _chain_root(node, insert_aliases):
    """Return the base call of a chained builder expression.

    `pg_insert(X).values(...).on_conflict_do_update(...).returning(...)` is a
    tree of `Call(func=Attribute(value=<inner call>))`; the base is the
    innermost builder call.

    🔴 #4819: THE STOP CONDITION CANNOT BE "func is a plain Name". It was, and
    that silently broke the module-qualified form: for `sa.insert(X).values(...)`
    the walk descends through `.values` to the `sa.insert(X)` call, sees an
    `ast.Attribute` func, keeps descending — past the call it was looking for —
    and returns the bare `Name("sa")`. The `.values()` mapping then finds no
    base and the site vanishes from the scan entirely. So the walk stops when it
    reaches a call that IS an insert builder, whichever way that builder is
    spelled.
    """
    current = node
    while True:
        if isinstance(current, ast.Call):
            if _is_insert_func(current.func, insert_aliases):
                return current
            if isinstance(current.func, ast.Attribute):
                current = current.func.value
                continue
            return current
        if isinstance(current, ast.Attribute):
            current = current.value
            continue
        return current


def _is_model_insert_base(node, model_aliases, insert_aliases):
    return (
        isinstance(node, ast.Call)
        and _is_insert_func(node.func, insert_aliases)
        and bool(node.args)
        and _is_model_ref(node.args[0], model_aliases)
    )


def _is_model_constructor(node, model_aliases):
    return isinstance(node, ast.Call) and _is_model_ref(node.func, model_aliases)


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


def _collect_sites_in_tree(path, tree):
    """The three site lists for ONE parsed module.

    Split out from :func:`_collect_sites` for #4819 so the recogniser can be
    exercised against a snippet rather than only against whatever spellings
    `app/` happens to contain today. A guard whose only test data is the code it
    already passes on cannot be shown to catch a spelling nobody has written
    yet, which is the whole subject of this issue.
    """
    model_aliases = _module_aliases(tree)
    insert_aliases = _insert_aliases(tree)

    core_sites = []
    orm_sites = []
    unrecognised = []

    # Map each `pg_insert(FuturesOutcome)` base to the `.values()` call
    # that carries its columns.
    values_by_base = {}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "values"
        ):
            base = _chain_root(node, insert_aliases)
            if _is_model_insert_base(base, model_aliases, insert_aliases):
                values_by_base[id(base)] = node

    for node in ast.walk(tree):
        if _is_model_insert_base(node, model_aliases, insert_aliases):
            values_call = values_by_base.get(id(node))
            if values_call is None:
                # An insert against this model that never calls `.values()`
                # (e.g. `.from_select`) is a shape this guard cannot read.
                # Fail loudly rather than pass silently.
                unrecognised.append((path, node.lineno, node))
            else:
                core_sites.append((path, node.lineno, values_call))
        elif _is_model_constructor(node, model_aliases):
            orm_sites.append((path, node.lineno, node))

    return core_sites, orm_sites, unrecognised


def _collect_sites():
    """Every place in `app/` that creates a `futures_outcomes` row.

    Returns (core_sites, orm_sites, unrecognised) where each site is a
    (path, lineno, call_node) triple.
    """
    core_sites = []
    orm_sites = []
    unrecognised = []

    for path, tree in _python_sources():
        core, orm, unknown = _collect_sites_in_tree(path, tree)
        core_sites.extend(core)
        orm_sites.extend(orm)
        unrecognised.extend(unknown)

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


def _scan(source):
    """Run the recogniser over a snippet. `(core, orm, unrecognised)` counts."""
    tree = ast.parse(source)
    core, orm, unknown = _collect_sites_in_tree(Path("snippet.py"), tree)
    return core, orm, unknown


def _omits_graded_column(sites):
    return [s for s in sites if _keyword(s[2], GRADED_COLUMN) is None]


class TestTheScanResolvesTheModelByNameNotBySpelling:
    """#4819. The guard above is a CLASS guard, and until this class existed it
    recognised its own subject only when spelled `FuturesOutcome(...)` with a
    bare name. Every spelling below is the same INSERT and the same fabricated
    verdict, and every one of them used to walk straight past.

    None of these is a live defect: all seven current writer sites in `app/` use
    the bare name, which is why CERT-2514 graded GREEN. That is exactly the
    condition under which a blind spot is worth closing — before the eighth site
    is written by someone who happened to type `models.FuturesOutcome`.
    """

    def test_a_module_qualified_constructor_is_seen(self):
        core, orm, _ = _scan(
            "from app.models import models\n"
            "models.FuturesOutcome(market_id=1, name='x')\n"
        )
        assert len(orm) == 1
        assert _omits_graded_column(orm), "and it must be reported as an offender"

    def test_an_aliased_module_constructor_is_seen(self):
        _, orm, _ = _scan(
            "import app.models.models as m\n"
            "m.FuturesOutcome(market_id=1, name='x')\n"
        )
        assert len(orm) == 1

    def test_an_aliased_import_constructor_is_seen(self):
        """`ast.Name`, right node type, wrong `id` — the arm a spelling check
        cannot reach without reading the module's imports."""
        _, orm, _ = _scan(
            "from app.models.models import FuturesOutcome as FO\n"
            "FO(market_id=1, name='x')\n"
        )
        assert len(orm) == 1

    def test_a_qualified_model_inside_pg_insert_is_seen(self):
        core, _, _ = _scan(
            "from sqlalchemy.dialects.postgresql import insert as pg_insert\n"
            "from app.models import models\n"
            "pg_insert(models.FuturesOutcome).values(market_id=1)\n"
        )
        assert len(core) == 1
        assert _omits_graded_column(core)

    def test_a_module_qualified_insert_builder_is_seen(self):
        """`sa.insert(...)` — and this one also proves `_chain_root`'s stop
        condition, which used to walk past the builder to the bare `Name('sa')`
        and lose the site entirely rather than merely mis-file it."""
        core, _, unknown = _scan(
            "import sqlalchemy as sa\n"
            "from app.models.models import FuturesOutcome\n"
            "sa.insert(FuturesOutcome).values(market_id=1)\n"
        )
        assert len(core) == 1
        assert not unknown, "it must be a readable Core site, not an unrecognised one"

    def test_an_aliased_insert_function_is_seen(self):
        core, _, _ = _scan(
            "from sqlalchemy import insert as ins\n"
            "from app.models.models import FuturesOutcome\n"
            "ins(FuturesOutcome).values(market_id=1)\n"
        )
        assert len(core) == 1

    def test_the_chain_still_resolves_through_on_conflict_and_returning(self):
        """The shape `kalshi.py` actually writes, module-qualified, so the fix
        is not only true of the two-node case."""
        core, _, unknown = _scan(
            "import sqlalchemy as sa\n"
            "from app.models import models\n"
            "sa.insert(models.FuturesOutcome)"
            ".values(market_id=1, is_winner=None)"
            ".on_conflict_do_update(index_elements=['id'], set_={})"
            ".returning(1)\n"
        )
        assert len(core) == 1
        assert not unknown
        assert not _omits_graded_column(core), "this one DOES name the column"

    def test_a_qualified_write_that_names_the_column_is_not_an_offender(self):
        """The recogniser widened; the verdict did not. A correctly written
        module-qualified site must stay silent, or the guard becomes noise and
        the next person deletes it."""
        _, orm, _ = _scan(
            "import sqlalchemy as sa\n"
            "from app.models import models\n"
            "models.FuturesOutcome(market_id=1, name='x', is_winner=sa.null())\n"
        )
        assert len(orm) == 1
        assert not _omits_graded_column(orm)

    def test_an_unrelated_call_is_not_a_site(self):
        """The broad `attr == MODEL` arm must not swallow the whole file."""
        core, orm, unknown = _scan(
            "import sqlalchemy as sa\n"
            "from app.models.models import FuturesMarket\n"
            "FuturesMarket(id=1)\n"
            "sa.insert(FuturesMarket).values(id=1)\n"
            "session.add(thing)\n"
            "obj.futures_outcome(1)\n"
        )
        assert (core, orm, unknown) == ([], [], [])

    def test_the_alias_sets_always_contain_the_bare_spellings(self):
        """A file that imports nothing still gets the unaliased recogniser, so
        widening the scan can never narrow it."""
        empty = ast.parse("")
        assert MODEL in _module_aliases(empty)
        assert INSERT_FUNCS <= _insert_aliases(empty)


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
