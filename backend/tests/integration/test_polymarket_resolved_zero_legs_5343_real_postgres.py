"""#5343 through the REAL hourly-poll writer, against real Postgres.

The pure rule is pinned in ``tests/test_polymarket_resolved_zero_legs_5343.py``.
This file runs ``_process_event_batch`` over the retained Gamma
``GET /events/106884`` bytes (13 legs, 6 closed + UMA-resolved at ["0","1"]) and
reads what the SQL actually stored:

* the two resolved legs the resolver declines become resolved rows priced at the
  venue's own pair, Yes 0 / No 1 — with no opening, no snapshot and no winner;
* the four resolved legs it already prices, and every open leg, are written
  exactly as without the arm (the gate-off control proves the delta is 2 rows);
* a row an earlier poll stored while the leg still traded is closed, keeps its
  real opening, and gains no snapshot.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the #5343 poll writer against real "
            "Postgres (CI job `search-recall` provides one)"
        ),
    ),
]

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "polymarket_resolved_zero_legs_5343"
    / "gamma-event-106884.json"
)
GROUP_ID = "polymarket:106884"
#: The two resolved legs today's resolver declines (prefixes of their condition ids).
ADMITTED = ("0x626d0441", "0x4d162a40")


@pytest.fixture
async def engine(monkeypatch):
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    import app.tasks.base as task_base
    from app.services.database import Base

    eng = create_async_engine(DB_URL)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(task_base, "DATABASE_URL", DB_URL)
    yield eng
    await eng.dispose()


def _raw() -> dict:
    return json.loads(FIXTURE.read_bytes())


def _event(raw: dict | None = None):
    from app.services.polymarket_api import PolymarketAPIService

    svc = PolymarketAPIService.__new__(PolymarketAPIService)
    event = svc._parse_event(raw if raw is not None else _raw())
    assert event is not None and len(event.markets) == 13
    return event


def _cid(prefix: str) -> str:
    return next(m["conditionId"] for m in _raw()["markets"] if m["conditionId"].startswith(prefix))


async def _poll(event):
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome
    from app.tasks.polymarket import _process_event_batch
    from app.utils.market_label_normalization import compute_market_tier
    from app.utils.odds_math import probability_to_american

    class _Counting(dict):
        def __missing__(self, key):
            return 0

    stats = _Counting(errors=[], by_category={})
    await _process_event_batch(
        [event], stats, FuturesMarket, FuturesOutcome, FuturesOddsSnapshot,
        pg_insert, probability_to_american, compute_market_tier,
    )
    assert not stats["errors"], stats["errors"]
    return stats


async def _children(engine) -> dict:
    """{condition_id: row} for the event's decomposed sub-market rows."""
    from sqlalchemy import text

    async with engine.connect() as conn:
        rows = (
            await conn.execute(text(
                "SELECT m.external_id, m.status, m.settled_at IS NOT NULL, "
                "       m.llm_sport_category, "
                "       y.current_probability::float, n.current_probability::float, "
                "       y.opening_probability::float, n.opening_probability::float, "
                "       y.is_winner, n.is_winner, "
                "       y.resolution_source, n.resolution_source, "
                "       (SELECT count(*) FROM futures_odds_snapshots s "
                "         WHERE s.outcome_id IN (y.id, n.id)) "
                "  FROM futures_markets m "
                "  LEFT JOIN futures_outcomes y "
                "         ON y.market_id = m.id AND y.external_id = m.external_id || '_yes' "
                "  LEFT JOIN futures_outcomes n "
                "         ON n.market_id = m.id AND n.external_id = m.external_id || '_no' "
                " WHERE m.source = 'polymarket' AND m.group_id = :gid "
                "   AND m.group_type = 'polymarket_sub_market'"
            ), {"gid": GROUP_ID})
        ).fetchall()
    keys = (
        "status", "settled", "domain", "yes", "no", "yes_open", "no_open",
        "yes_winner", "no_winner", "yes_src", "no_src", "snapshots",
    )
    return {r[0]: dict(zip(keys, r[1:])) for r in rows}


async def test_106884_stores_its_two_declined_resolved_legs_as_resolved_rows(engine):
    stats = await _poll(_event())
    rows = await _children(engine)

    assert stats["resolved_zero_legs_admitted"] == 2
    assert len(rows) == 10, sorted(rows)  # 8 written before #5343, plus these 2
    for prefix in ADMITTED:
        row = rows[_cid(prefix)]
        assert row["domain"] == "economics"
        # `settled_at` is stamped by the conflict update only, so a FIRST insert
        # of any resolved leg leaves it NULL until the next poll — the four
        # sibling rows behave the same. See the idempotence test for the stamp.
        assert row["status"] == "resolved"
        assert (row["yes"], row["no"]) == (0.0, 1.0), "the venue's own settled pair"
        assert (row["yes_open"], row["no_open"]) == (None, None), "no hindsight opening"
        assert (row["yes_winner"], row["no_winner"]) == (None, None), "ingestion never grades"
        assert (row["yes_src"], row["no_src"]) == (None, None)
        assert row["snapshots"] == 0, "a settled result is not a quote in time"
    # The three open legs the empty-book gates refuse are still absent.
    for prefix in ("0x8f6e229b", "0xee626bbe", "0xc55bf124"):
        assert _cid(prefix) not in rows
    # All six resolved legs now exist and all read resolved.
    resolved = {cid for cid, r in rows.items() if r["status"] == "resolved"}
    assert len(resolved) == 6


async def test_with_the_gate_off_the_same_bytes_store_exactly_two_fewer_rows(engine, monkeypatch):
    """Control on the same input: the delta is the arm and nothing else."""
    import app.tasks.polymarket as pm

    monkeypatch.setattr(pm, "RESOLVED_ZERO_LEG_DOMAINS", frozenset())
    stats = await _poll(_event())
    rows = await _children(engine)

    assert stats["resolved_zero_legs_admitted"] == 0
    assert len(rows) == 8
    assert not any(_cid(p) in rows for p in ADMITTED)


async def test_the_arm_leaves_every_other_row_as_it_was(engine, monkeypatch):
    import app.tasks.polymarket as pm

    with monkeypatch.context() as m:
        m.setattr(pm, "RESOLVED_ZERO_LEG_DOMAINS", frozenset())
        # Twice, so the control already carries the second poll's `settled_at`
        # stamp and the comparison below isolates the arm.
        await _poll(_event())
        await _poll(_event())
        control = await _children(engine)
    await _poll(_event())
    treated = await _children(engine)

    shared = set(control)
    assert set(treated) - shared == {_cid(p) for p in ADMITTED}
    for cid in shared:
        before, after = dict(control[cid]), dict(treated[cid])
        # A second poll adds a snapshot to every priced row; that is the poll,
        # not the arm, so compare everything else.
        before.pop("snapshots"), after.pop("snapshots")
        assert before == after, cid


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"umaResolutionStatus": "proposed"}, id="proposed"),
        pytest.param({"umaResolutionStatus": "disputed"}, id="disputed"),
        pytest.param({"umaResolutionStatus": None}, id="status-null"),
        pytest.param({"outcomePrices": '["0.002", "0.998"]', "lastTradePrice": None}, id="dust"),
        pytest.param({"closed": False}, id="open-at-zero"),
    ],
)
async def test_a_refused_variant_of_the_declined_legs_is_still_dropped(engine, changes):
    raw = _raw()
    for m in raw["markets"]:
        if m["conditionId"].startswith(ADMITTED):
            m.update(changes)
    stats = await _poll(_event(raw))
    rows = await _children(engine)

    assert stats["resolved_zero_legs_admitted"] == 0
    for prefix in ADMITTED:
        row = rows.get(_cid(prefix))
        # A dust quote with no trade is a price the resolver itself may take;
        # what must never happen is a 0/1 settled write from the arm.
        assert row is None or (row["yes"], row["no"]) != (0.0, 1.0)


async def test_a_sports_event_with_the_same_legs_is_not_admitted(engine):
    raw = _raw()
    raw["tags"] = [{"label": "NFL", "slug": "nfl"}, {"label": "Sports", "slug": "sports"}]
    stats = await _poll(_event(raw))
    rows = await _children(engine)

    assert stats["resolved_zero_legs_admitted"] == 0
    assert not any(_cid(p) in rows for p in ADMITTED)


async def test_a_negrisk_event_is_not_admitted(engine):
    raw = _raw()
    raw["negRisk"] = True
    for m in raw["markets"]:
        m["negRisk"] = True
    stats = await _poll(_event(raw))
    assert stats["resolved_zero_legs_admitted"] == 0


async def test_a_row_stored_while_the_leg_traded_is_closed_and_keeps_its_real_opening(engine):
    """The settled poll repairs the frozen open row; it does not rewrite history."""
    raw = _raw()
    target = _cid(ADMITTED[0])
    for m in raw["markets"]:
        if m["conditionId"] == target:
            m.update({
                "closed": False,
                "umaResolutionStatus": None,
                "outcomePrices": '["0.02", "0.98"]',
                "bestBid": 0.015,
                "bestAsk": 0.025,
                "lastTradePrice": 0.02,
                "volume24hr": 900,
                # Still ahead of its own date while it trades, or the #2027
                # hindsight guard (correctly) refuses the opening.
                "endDate": "2099-06-17T00:00:00Z",
            })
    await _poll(_event(raw))
    trading = (await _children(engine))[target]
    assert trading["status"] == "open" and trading["yes"] == pytest.approx(0.02)
    assert trading["yes_open"] == pytest.approx(0.02)
    snapshots_while_trading = trading["snapshots"]
    assert snapshots_while_trading == 2

    stats = await _poll(_event())
    settled = (await _children(engine))[target]

    assert stats["resolved_zero_legs_admitted"] == 2
    # An UPDATE of an existing row, so the conflict set stamps `settled_at` now.
    assert settled["status"] == "resolved" and settled["settled"] is True
    assert (settled["yes"], settled["no"]) == (0.0, 1.0)
    assert settled["yes_open"] == pytest.approx(0.02), "the real opening survives"
    assert settled["no_open"] == pytest.approx(0.98)
    assert (settled["yes_winner"], settled["no_winner"]) == (None, None)
    assert settled["snapshots"] == snapshots_while_trading, "no post-settlement snapshot"


async def test_a_second_settled_poll_is_idempotent(engine):
    await _poll(_event())
    first = await _children(engine)
    await _poll(_event())
    second = await _children(engine)

    for prefix in ADMITTED:
        a, b = dict(first[_cid(prefix)]), dict(second[_cid(prefix)])
        assert (a["settled"], b["settled"]) == (False, True), "stamped on the 2nd poll"
        a.pop("settled"), b.pop("settled")
        assert a == b
