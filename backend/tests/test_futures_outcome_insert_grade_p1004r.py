"""CAL-P1004R (#1852, repairs CERT-948) — the INSERT arm may not fabricate a loss.

CAL-P1004 closed four UPDATE-shaped sites in ``app/tasks/kalshi.py`` that graded a
Kalshi outcome with a two-state ``result == "yes"``. CERT-948 found the fifth shape
it did not close: an ``INSERT`` that simply *omits* ``is_winner``.

``futures_outcomes.is_winner`` carries BOTH ``default=False`` and
``server_default=text("false")`` (``models.py``). So "write neither column", which
is exactly right on an UPDATE, means ``false`` on an INSERT — the row being born is
recorded as a declared LOSS. ``ON CONFLICT DO NOTHING`` protects rows that already
exist and does nothing at all for that one.

THREE INSERT sites reach ``futures_outcomes`` in that file, and all three must name
the pair explicitly:

1. ``_create_settled_market`` — the one CERT-948 named;
2. the live futures poll's per-outcome upsert — the file's bulk CREATOR of outcome
   rows, whose ``graded_cols`` reached only the conflict arm;
3. **the poll's unpriced-outcome placeholder write (#3518)** — added 2026-09-06.
   When the venue lists a leg whose book cannot be read, the poll now records that
   the outcome EXISTS with ``current_probability = NULL`` instead of skipping it
   entirely (a skip was permanent: the main scan reaches no existing event on any
   beat, and every other channel is UPDATE-only). A placeholder is the
   LEAST-graded row in the system, so it is precisely where an inherited ``false``
   would be most wrong — it would declare a loss on a market nobody has priced,
   let alone settled. This guard's count tripwire is what caught it: the site was
   written naming the pair, and the count still had to be reviewed rather than
   bumped, which is the whole point of asserting on the number.

Test 1 is the ANCHOR: it proves the default really does land ``false``, in a real
database, so the rest of the file is guarding a measured mechanism and not a belief
about SQLAlchemy. Tests 2-4 drive the real ``_create_settled_market`` and read the
statement it actually emits. Test 5 is structural and covers the CLASS, so a third
INSERT site added later cannot reopen this. Test 6 is the real-Postgres round trip
CERT-948 asked for by name; it skips without a throwaway Postgres (CI has none), and
that is precisely why it is not the only guard here.
"""

import ast
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.models import FuturesMarket, FuturesOutcome
from app.services.kalshi_api import KalshiEvent, KalshiMarket
from app.tasks.kalshi import _create_settled_market, _GAP_CREATE_START
from app.utils.market_label_normalization import compute_market_tier

VENUE_SOURCE = "api_settlement"


# --------------------------------------------------------------------------
# 1. THE ANCHOR — what an omitted column actually stores.
# --------------------------------------------------------------------------


def test_omitting_is_winner_stores_false_explicit_none_stores_null():
    """The mechanism the whole file guards, EXECUTED rather than assumed.

    Both of the column's defaults are live here, and they land ``false`` by two
    independent routes: SQLAlchemy fills the Python-side ``default=False`` at
    execute time (this is the production route, since these writes go through
    Core), and ``server_default=text("false")`` catches anything that bypasses
    it. Neither is visible at COMPILE time — an omitted column and an explicit
    ``None`` compile to the same bind param — which is why this test executes and
    why the statement-shape tests below assert on what the caller NAMED.

    If this ever fails because the column stopped defaulting to ``false``, the
    rest of this file is guarding nothing and should be re-read, not deleted.
    """
    from sqlalchemy import Column, MetaData, Table, create_engine, select

    md = MetaData()
    probe = Table(
        "insert_default_probe",
        md,
        *[
            Column(
                c.name,
                c.type,
                primary_key=c.primary_key,
                nullable=c.nullable,
                default=c.default,
                server_default=c.server_default,
            )
            for c in FuturesOutcome.__table__.columns
            if c.name in ("id", "is_winner", "resolution_source")
        ],
    )
    engine = create_engine("sqlite://")
    md.create_all(engine)
    with engine.begin() as conn:
        # Route A: SQLAlchemy Core, column omitted — the production shape.
        conn.execute(probe.insert().values(id=1))
        # Route B: the same write naming the column explicitly as NULL.
        conn.execute(probe.insert().values(id=2, is_winner=None, resolution_source=None))
        # Route C: raw SQL, bypassing SQLAlchemy entirely — server_default only.
        conn.exec_driver_sql("INSERT INTO insert_default_probe (id) VALUES (3)")
        rows = dict(conn.execute(select(probe.c.id, probe.c.is_winner)).fetchall())

    # Omitted: the default fires and the row is born a declared LOSS.
    assert rows[1] is not None and bool(rows[1]) is False, (
        "omitting is_winner no longer lands the false default — re-read this file"
    )
    assert rows[3] is not None and bool(rows[3]) is False
    # Explicit NULL: "the venue has not answered" survives the write.
    assert rows[2] is None


# --------------------------------------------------------------------------
# 2-4. The real gap-create path, read off the statement it emits.
# --------------------------------------------------------------------------


def _event(status, result, ticker="KXATPMATCH-R1"):
    recent = _GAP_CREATE_START + timedelta(days=10)
    return KalshiEvent(
        event_ticker=ticker,
        title="Some tennis match",
        category="Tennis",
        mutually_exclusive=True,
        markets=[
            KalshiMarket(
                ticker=f"{ticker}-A",
                event_ticker=ticker,
                title="A",
                yes_sub_title="Alcaraz",
                status=status,
                close_time=recent,
                last_price=0.62,
                result=result,
                volume=1500,
            )
        ],
    )


async def _outcome_insert_for(status, result):
    """Run the real ``_create_settled_market`` and return its outcome INSERT."""
    svc = MagicMock()
    svc._parse_event = MagicMock(return_value=_event(status, result))
    session = AsyncMock()
    res = MagicMock()
    res.scalar_one_or_none = MagicMock(return_value=4242)
    session.execute = AsyncMock(return_value=res)

    stats = {"markets_created": 0, "outcomes_created": 0}
    out = await _create_settled_market(
        session, svc, {}, pg_insert,
        FuturesMarket, FuturesOutcome, compute_market_tier, stats,
    )
    assert out == "created"

    stmts = [c.args[0] for c in session.execute.await_args_list]
    outcome_stmts = [
        s for s in stmts
        if getattr(getattr(s, "table", None), "name", None) == "futures_outcomes"
    ]
    assert len(outcome_stmts) == 1, "expected exactly one outcome INSERT"
    stmt = outcome_stmts[0]
    # `_values` is what the CALLER named. An omitted column is absent here but
    # still appears in the compiled SQL (SQLAlchemy adds it to apply the default),
    # so this — not the compiled text — is the question the defect turns on.
    named = {col.name: val.value for col, val in stmt._values.items()}
    return stmt, named, str(stmt.compile(dialect=postgresql.dialect()))


@pytest.mark.asyncio
async def test_ungraded_gap_insert_names_the_pair_as_null():
    """status=active, result="" — still trading. Both columns written as NULL."""
    _stmt, named, sql = await _outcome_insert_for("active", "")
    assert "is_winner" in named, (
        "the INSERT does not name is_winner — the column default records a LOSS on a "
        "market the venue is still trading (CERT-948)"
    )
    assert "resolution_source" in named, "the INSERT does not name resolution_source"
    assert named["is_winner"] is None
    assert named["resolution_source"] is None
    # CERT-948's other clause: the conflict arm stays a no-op for ungraded re-runs,
    # so a re-poll cannot even touch-stamp the row.
    assert "DO NOTHING" in sql


@pytest.mark.asyncio
async def test_finalized_yes_gap_insert_writes_the_win():
    _stmt, named, sql = await _outcome_insert_for("finalized", "yes")
    assert named["is_winner"] is True
    assert named["resolution_source"] == VENUE_SOURCE
    assert "DO UPDATE" in sql


@pytest.mark.asyncio
async def test_finalized_no_gap_insert_writes_the_real_loss():
    """The control that keeps this repair from becoming "never grade anything"."""
    _stmt, named, sql = await _outcome_insert_for("finalized", "no")
    assert named["is_winner"] is False
    assert named["resolution_source"] == VENUE_SOURCE
    assert "DO UPDATE" in sql


@pytest.mark.asyncio
async def test_scalar_result_is_not_a_loss():
    """``result="scalar"`` settles on a number, not a side — it is not a loss."""
    _stmt, named, sql = await _outcome_insert_for("finalized", "scalar")
    assert named["is_winner"] is None
    assert named["resolution_source"] is None
    assert "DO NOTHING" in sql


# --------------------------------------------------------------------------
# 5. The CLASS guard — every futures_outcomes INSERT in the task file.
# --------------------------------------------------------------------------


def test_every_futures_outcome_insert_names_the_grade_pair():
    """Structural, so a THIRD insert site cannot reopen this defect silently.

    CAL-P1004's own lesson: its guard matched the NAME SHAPE rather than the one
    spelling already fixed, and that is how sites 3-5 were found. This is the same
    move for the INSERT shape.
    """
    src = Path(__file__).resolve().parents[1] / "app" / "tasks" / "kalshi.py"
    tree = ast.parse(src.read_text())

    sites = []
    for node in ast.walk(tree):
        # Match `pg_insert(FuturesOutcome).values(...)`, however it is chained.
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "values"):
            continue
        inner = node.func.value
        if not (isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Name)
                and inner.func.id == "pg_insert"
                and inner.args
                and isinstance(inner.args[0], ast.Name)
                and inner.args[0].id == "FuturesOutcome"):
            continue
        named = {kw.arg for kw in node.keywords if kw.arg}
        sites.append((node.lineno, named, any(kw.arg is None for kw in node.keywords)))

    # The count is a TRIPWIRE, not bookkeeping: it forces a human to look at any
    # new INSERT site rather than letting the per-site loop below quietly bless
    # one. Three sites today — `_create_settled_market`, the poll's per-outcome
    # upsert, and (#3518) the poll's unpriced-outcome placeholder write. Raise it
    # only after reading the new site; the assertions below are necessary and the
    # count is what makes them get read.
    assert len(sites) == 3, (
        f"expected 3 futures_outcomes INSERT sites in kalshi.py, found {len(sites)} "
        f"at lines {[s[0] for s in sites]} — a new one must name is_winner and "
        "resolution_source explicitly, or it inherits the false default"
    )
    for lineno, named, has_splat in sites:
        assert "is_winner" in named, (
            f"kalshi.py:{lineno} inserts a futures_outcome without naming is_winner; "
            "the column defaults to false, so this records a loss the venue never "
            "declared (CERT-948)"
        )
        assert "resolution_source" in named, (
            f"kalshi.py:{lineno} inserts a futures_outcome without naming "
            "resolution_source"
        )
        assert not has_splat, (
            f"kalshi.py:{lineno} splats a mapping into .values(); an empty mapping "
            "contributes no column and the default fires — name the pair explicitly"
        )


# --------------------------------------------------------------------------
# 6. The real-Postgres round trip CERT-948 named — it lives in CI, not here.
# --------------------------------------------------------------------------
#
# `tests/integration/test_gap_create_grade_real_postgres.py`, run by the
# `search-recall` job's "#1852 gap-create grade round trip" step, which fails
# the build if that gate skips.
#
# It is not in this file because it cannot RUN in this file. There is no local
# Postgres in the agent sandbox (`initdb` fails on `shmget`), so a skipif here
# would be a permanent silent skip — gotcha #53's exact shape, and the failure
# mode the CI job's skip-detection exists to end. Everything above executes on
# every run and is what actually guards this defect day to day; the CI gate is
# what proves the STORED value, since an omitted column and an explicit `None`
# compile identically and only the server owns the default.
