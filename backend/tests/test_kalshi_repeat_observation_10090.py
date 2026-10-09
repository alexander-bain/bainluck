"""Fresh identical Kalshi input skips writes; changed DB values remain immediate.

SQLite exercises the actual UPDATE predicate with only its PostgreSQL interval
expression replaced by a fixed cutoff. It cannot certify PostgreSQL RETURNING
book-change publication; these controls assert admission and stored clocks only.
"""

import contextlib
import ast
import copy
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, literal, text
from sqlalchemy.sql import visitors
from sqlalchemy.sql.elements import BinaryExpression, BindParameter

from app.tasks.kalshi_ws import _KalshiPriceOwner
from app.utils.kalshi_price_pipeline import PriceRunResult
from app.utils.kalshi_price_statement import (
    KALSHI_PRICE_STATEMENTS,
    KALSHI_REPEAT_REFRESH_SECONDS,
    kalshi_price_parameters,
)
from app.utils.resolution_authority import AUTHORITATIVE_SOURCES

CUTOFF = datetime(2026, 1, 1)
FRESH = CUTOFF + timedelta(seconds=1)
STALE = CUTOFF - timedelta(seconds=1)


def _fixed_cutoff(statement):
    def replace(node):
        if (
            isinstance(node, BinaryExpression)
            and isinstance(node.right, BindParameter)
            and node.right.value == timedelta(seconds=KALSHI_REPEAT_REFRESH_SECONDS)
        ):
            return literal(CUTOFF)

    return visitors.replacement_traverse(statement, {}, replace)


@pytest.fixture
def database():
    engine = create_engine("sqlite://")
    with engine.begin() as db:
        db.execute(text("""CREATE TABLE futures_outcomes (
            id INTEGER PRIMARY KEY, market_id INTEGER, resolution_source TEXT,
            current_probability NUMERIC(7,6), current_yes_bid NUMERIC(5,4),
            current_yes_ask NUMERIC(5,4), last_updated DATETIME,
            price_changed_at DATETIME)"""))
        db.execute(
            text("""INSERT INTO futures_outcomes VALUES
            (1, 2, NULL, .3, .2, .4, :fresh, :fresh)"""),
            {"fresh": FRESH},
        )
    yield engine
    engine.dispose()


def _write(database, probability=0.3, bid=0.2, ask=0.4, force=False):
    statement = _fixed_cutoff(
        KALSHI_PRICE_STATEMENTS[bid is not None and ask is not None]
    )
    with database.begin() as db:
        return db.execute(
            statement, kalshi_price_parameters(1, probability, bid, ask, force)
        ).all()


def _state(database):
    with database.connect() as db:
        return db.execute(text("SELECT * FROM futures_outcomes")).mappings().one()


def test_repeat_does_not_write_or_mint_a_clock_but_first_receipt_does(database):
    before = dict(_state(database))
    assert not _write(database)
    assert dict(_state(database)) == before
    assert len(_write(database, force=True)) == 1
    assert _state(database)["last_updated"] != before["last_updated"]


@pytest.mark.parametrize(
    "column,value",
    [
        ("current_probability", 0.7),
        ("current_yes_bid", 0.1),
        ("current_yes_ask", 0.5),
    ],
)
def test_database_changes_are_not_hidden_by_prior_equal_input(database, column, value):
    assert not _write(database)
    with database.begin() as db:
        db.execute(
            text(f"UPDATE futures_outcomes SET {column}=:value"), {"value": value}
        )
    assert len(_write(database)) == 1
    state = _state(database)
    assert float(state["current_probability"]) == 0.3
    assert float(state["current_yes_bid"]) == 0.2
    assert float(state["current_yes_ask"]) == 0.4


@pytest.mark.parametrize("clock", [STALE, CUTOFF, None])
def test_real_repeat_renews_due_or_missing_liveness(database, clock):
    with database.begin() as db:
        db.execute(
            text("UPDATE futures_outcomes SET last_updated=:clock"), {"clock": clock}
        )
    assert len(_write(database)) == 1
    assert _state(database)["last_updated"] is not None


def test_half_book_preserves_both_sides_and_does_not_admit_a_repeat(database):
    assert not _write(database, bid=0.1, ask=None)
    assert not _write(database, bid=None, ask=0.5)
    assert len(_write(database, probability=0.6, bid=0.1, ask=None)) == 1
    state = _state(database)
    assert float(state["current_yes_bid"]) == 0.2
    assert float(state["current_yes_ask"]) == 0.4


@pytest.mark.parametrize("force", [False, True])
def test_settlement_refusal_still_dominates_changed_and_first_input(database, force):
    with database.begin() as db:
        db.execute(
            text("UPDATE futures_outcomes SET resolution_source=:source"),
            {"source": sorted(AUTHORITATIVE_SOURCES)[0]},
        )
    assert not _write(database, probability=0.9, force=force)
    assert float(_state(database)["current_probability"]) == 0.3


@pytest.mark.asyncio
async def test_owner_forces_until_outer_commit_and_does_not_cache_values(monkeypatch):
    import app.utils.kalshi_price_pipeline as pipeline

    submissions = []

    class Recorder:
        async def iter_phase(self, _session, phase):
            submissions.append(dict(phase))
            yield PriceRunResult(len(phase), ())

        def close(self):
            pass

    monkeypatch.setattr(pipeline, "install_kalshi_price_pipeline", lambda _: Recorder())
    owner = _KalshiPriceOwner()
    session = SimpleNamespace(bind=object())
    phase = {1: (0.3, 0.2, 0.4)}

    async def submit(**kwargs):
        async with contextlib.aclosing(
            owner.phase(session, phase, **kwargs)
        ) as results:
            async for _ in results:
                pass

    await submit()
    await submit()  # rollback/failed outer commit pays no first observation
    assert submissions == [{1: (0.3, 0.2, 0.4, True)}] * 2
    owner.committed_outcome_ids.add(1)  # caller's successful outer commit
    await submit()
    phase[1] = (0.6, 0.5, 0.7)
    await submit()
    assert submissions[-2:] == [
        {1: (0.3, 0.2, 0.4, False)},
        {1: (0.6, 0.5, 0.7, False)},
    ]
    await submit(force_observation=True)  # final drain keeps original semantics
    assert submissions[-1] == {1: (0.6, 0.5, 0.7, True)}
    owner.close()


def _fresh_admission():
    from app.tasks.live_blend_refresh import event_ids_for_outcomes
    from tests.kalshi_price_statement_support import flush_ast

    queue = next(
        node
        for node in ast.walk(flush_ast())
        if isinstance(node, ast.FunctionDef) and node.name == "queue_committed"
    )
    wrapper = ast.parse("""def admission():
    event_id_by_outcome = {1: 10, 2: 20}
    cohort_event_ids = event_id_by_outcome
    non_blend_outcome_ids = set()
    final_drain = False
    batch_marks = {1: 'one', 2: 'two'}
    queued_events, queued_marks, queued_refresh = set(), {}, False
    def state():
        return queued_events, queued_marks, queued_refresh
    return queue_committed, state, event_id_by_outcome
""")
    wrapper.body[0].body.insert(-1, copy.deepcopy(queue))
    namespace = {"event_ids_for_outcomes": event_ids_for_outcomes}
    exec(
        compile(ast.fix_missing_locations(wrapper), "actual-queue-admission", "exec"),
        namespace,
    )
    return namespace["admission"]()


def test_sql_skipped_repeats_service_implicit_debt_without_fresh_event_reads():
    queue, state, _ = _fresh_admission()
    phase = {1: (0.3, 0.2, 0.4), 2: (0.7, 0.6, 0.8)}
    assert queue(0, phase, []) == set()
    # An empty refresh still services the refresher's previously owed debt.
    assert state() == (set(), {}, True)
    queue, state, _ = _fresh_admission()
    assert queue(1, phase, []) == set()
    assert state() == (set(), {}, False)


def test_actual_writes_keep_late_bridge_adoption_without_admitting_skipped_sibling():
    queue, state, mapping = _fresh_admission()
    mapping.pop(1)
    phase = {1: (0.3, 0.2, 0.4), 2: (0.7, 0.6, 0.8)}
    registered = queue(0, phase, [1])
    assert registered == set()
    mapping[1] = 10
    assert queue(0, phase, [1], registered=registered) == {10}
    assert state() == ({10}, {1: "one"}, True)
