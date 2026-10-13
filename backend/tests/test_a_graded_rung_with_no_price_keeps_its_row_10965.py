"""#10965 — a settled game page skipped the graded team-total lines that had no price.

## What a reader saw

`/events/14626073` (Boston 10, Detroit 3, final). Kalshi's "Boston vs Detroit: Team
Total" (market 54069274, `resolved`, 14 legs, all graded `game_score`) served
Detroit over 1.5 Won, 2.5 Won, 3.5 Lost, **7.5** Lost — the ladder jumped from 3.5
to 7.5. `/api/futures/54069274` carried the three missing legs, Detroit over 4.5 /
5.5 / 6.5, at `is_winner=False`, `game_score`, `probability=null`; `/game-markets`
dropped them at the totals branch's `if prob is None: continue`, before the
verdict was ever read. 3.5 and 7.5 survived only because they still held a stale
0.01.

## The rule these tests pin

A priceless leg is served on the totals ladder only when `_verdict_is_provable`
accepts its grade — authoritative tier AND a winner on its own market — and its
number is the 0/1 the verdict implies on the row's own axis. Everything else that
has no price stays off the page: a live leg, an ungraded leg on a finished game,
and every leg of a voided (all-lost) market.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw
from tests.integration.test_route_events_seeded import (
    _make_event,
    _make_event_detail_session,
    _make_futures_market,
    _make_outcome,
)

EVENT_ID = 14626073
HOME = "Detroit Tigers"
AWAY = "Boston Red Sox"
K_TEAM_TOTAL = 54069274
PM_DET_TT = 64990001  # an illustrative Polymarket single-club line, for the Under axis
K_F5_TOTAL = 54069300  # an illustrative period total: the branch whose None rows bypass 7b

# Fixed clock, offset first (gotcha #44): the game is long over.
KICKOFF = datetime(2026, 5, 5, 22, 40, tzinfo=timezone.utc)
FINAL_AT = KICKOFF + timedelta(hours=3)
SETTLED_AT = FINAL_AT + timedelta(minutes=40)

MARKETS = {
    K_TEAM_TOTAL: (
        "Boston vs Detroit: Team Total",
        "kalshi",
        "KXMLBTEAMTOTAL-26MAY051840BOSDET",
    ),
    PM_DET_TT: ("Tigers Team Total: O/U 3.5", "polymarket", "pm-det-tt-3-5"),
    K_F5_TOTAL: (
        "Boston vs Detroit: First 5 Innings Total Runs",
        "kalshi",
        "KXMLBF5TOTAL-26MAY051840BOSDET",
    ),
}

# The production specimen, id for id: `(outcome_id, market_id, name, price,
# is_winner, resolution_source)`, read from `/api/futures/54069274` at 00:04Z.
SPECIMEN = [
    (202058556, K_TEAM_TOTAL, "Detroit over 1.5 runs scored", 0.995, True, "game_score"),
    (202058557, K_TEAM_TOTAL, "Detroit over 2.5 runs scored", 0.995, True, "game_score"),
    (202058558, K_TEAM_TOTAL, "Boston over 1.5 runs scored", 0.995, True, "game_score"),
    (202058559, K_TEAM_TOTAL, "Boston over 2.5 runs scored", 0.995, True, "game_score"),
    (202058560, K_TEAM_TOTAL, "Boston over 3.5 runs scored", 0.995, True, "game_score"),
    (202058561, K_TEAM_TOTAL, "Boston over 4.5 runs scored", 0.995, True, "game_score"),
    (202058562, K_TEAM_TOTAL, "Boston over 5.5 runs scored", 0.995, True, "game_score"),
    (202058563, K_TEAM_TOTAL, "Boston over 6.5 runs scored", 0.995, True, "game_score"),
    (202058564, K_TEAM_TOTAL, "Boston over 7.5 runs scored", 0.995, True, "game_score"),
    (202058565, K_TEAM_TOTAL, "Detroit over 5.5 runs scored", None, False, "game_score"),
    (202058566, K_TEAM_TOTAL, "Detroit over 6.5 runs scored", None, False, "game_score"),
    (202058567, K_TEAM_TOTAL, "Detroit over 4.5 runs scored", None, False, "game_score"),
    (202058568, K_TEAM_TOTAL, "Detroit over 3.5 runs scored", 0.01, False, "game_score"),
    (202058569, K_TEAM_TOTAL, "Detroit over 7.5 runs scored", 0.01, False, "game_score"),
]
PRICELESS_LOSERS = {
    "Detroit over 4.5 runs scored",
    "Detroit over 5.5 runs scored",
    "Detroit over 6.5 runs scored",
}


def _game(rows, *, finished=True):
    event = _make_event(
        id=EVENT_ID,
        home_team=HOME,
        away_team=AWAY,
        status="completed" if finished else "live",
        sport_key="baseball_mlb",
        home_score=3 if finished else 2,
        away_score=10 if finished else 2,
    )
    event.llm_league = "MLB"
    event.commence_time = KICKOFF
    event.completed_at = FINAL_AT if finished else None
    event.period = "Final" if finished else "Top 3rd"
    event.game_clock = None
    event.box_score_data = {"players": {}}

    futures = []
    for mid in sorted({r[1] for r in rows}):
        name, source, external_id = MARKETS[mid]
        market = _make_futures_market(id=mid, name=name, source=source)
        market.category = "game_prop"
        market.external_id = external_id
        market.event_id = EVENT_ID
        market.commence_time = KICKOFF
        market.status = "resolved" if finished else "open"
        market.settled_at = SETTLED_AT if finished else None
        futures.append(market)

    outcomes = []
    for oid, mid, name, price, won, source in rows:
        outcome = _make_outcome(
            id=oid,
            market_id=mid,
            name=name,
            probability=price or 0.0,
            is_winner=won,
            resolution_source=source,
        )
        outcome.current_probability = price
        outcome.opening_probability = None
        outcomes.append(outcome)
    return event, futures, outcomes


async def _payload(rows=SPECIMEN, *, finished=True) -> dict:
    from app.main import app
    from app.routes.events import _game_markets_cache

    _game_markets_cache.clear()
    event, futures, outcomes = _game(rows, finished=finished)
    session = _make_event_detail_session(event=event, futures=futures, outcomes=outcomes)

    async def _mock_get_db():
        yield session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user
    try:
        with patch("app.main.init_db", new_callable=AsyncMock):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.get(f"/api/events/{EVENT_ID}/game-markets")
    finally:
        _game_markets_cache.clear()
        app.dependency_overrides.clear()
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _team_totals(rows=SPECIMEN, *, finished=True) -> list[dict]:
    return (await _payload(rows, finished=finished)).get("team_totals") or []


async def _period_rows(rows, *, finished=True) -> list[dict]:
    return (await _payload(rows, finished=finished)).get("period_markets") or []


def _by_name(rows) -> dict:
    return {(r["_market_id"], r["outcome_name"]): r for r in rows}


def test_the_specimen_really_holds_priceless_graded_losers_between_priced_ones():
    """Without this the tests below could pass on the old code: the three rungs
    must be priceless, graded and LOST, and sit between two priced losers."""
    priceless = {r[2] for r in SPECIMEN if r[3] is None}
    assert priceless == PRICELESS_LOSERS
    assert all(r[4] is False and r[5] == "game_score" for r in SPECIMEN if r[3] is None)
    assert any(r[4] is True for r in SPECIMEN), "the market must have a winner"


@pytest.mark.asyncio
async def test_the_three_priceless_detroit_losers_are_served_as_lost():
    """The whole defect: 4.5 / 5.5 / 6.5 reach the payload, printed Lost at 0%."""
    served = _by_name(await _team_totals())

    for name in PRICELESS_LOSERS:
        row = served.get((K_TEAM_TOTAL, name))
        assert row is not None, f"{name} was dropped from the settled ladder"
        assert row["over_probability"] == 0.0
        assert row["is_winner"] is False
        assert row["resolution_source"] == "game_score"
        assert row["team_side"] == "home"


@pytest.mark.asyncio
async def test_detroits_ladder_is_whole_and_the_priced_rungs_are_unchanged():
    """Low-line controls: 1.5 / 2.5 Won, 3.5 and 7.5 Lost exactly as served
    before, and the Detroit ladder runs 1.5 through 7.5 with no gap."""
    rows = await _team_totals()
    served = _by_name(rows)

    detroit = sorted(r["threshold"] for r in rows if r["outcome_name"].startswith("Detroit"))
    assert detroit == [1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5]
    for name, over, won in [
        ("Detroit over 1.5 runs scored", 1.0, True),
        ("Detroit over 2.5 runs scored", 1.0, True),
        ("Detroit over 3.5 runs scored", 0.0, False),
        ("Detroit over 7.5 runs scored", 0.0, False),
    ]:
        assert served[(K_TEAM_TOTAL, name)]["over_probability"] == over
        assert served[(K_TEAM_TOTAL, name)]["is_winner"] is won
    boston = sorted(r["threshold"] for r in rows if r["outcome_name"].startswith("Boston"))
    assert boston == [1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5]
    assert len(rows) == 14


@pytest.mark.asyncio
async def test_a_priceless_under_that_won_lands_on_the_over_axis():
    """Axis inversion holds for a readmitted leg: an Under that WON is an over
    that did not happen — 0.0, `is_winner False` on the over axis."""
    rows = [
        (91001, PM_DET_TT, "Over", 0.01, False, "game_score"),
        (91002, PM_DET_TT, "Under", None, True, "game_score"),
    ]
    served = _by_name(await _team_totals(rows))

    under = served[(PM_DET_TT, "Under")]
    assert under["over_probability"] == 0.0
    assert under["is_winner"] is False


# ── What must NOT change ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_live_priceless_leg_is_still_hidden():
    """Unrelated live control: an open, ungraded leg with no quote never gets a
    row; its priced sibling does."""
    rows = [
        (92001, K_TEAM_TOTAL, "Detroit over 2.5 runs scored", 0.71, None, None),
        (92002, K_TEAM_TOTAL, "Detroit over 3.5 runs scored", None, None, None),
    ]
    served = _by_name(await _team_totals(rows, finished=False))

    assert (K_TEAM_TOTAL, "Detroit over 2.5 runs scored") in served
    assert (K_TEAM_TOTAL, "Detroit over 3.5 runs scored") not in served


@pytest.mark.asyncio
async def test_an_ungraded_priceless_leg_on_a_finished_game_is_still_hidden():
    """No `resolution_source` is no verdict (#4788): finished game, winners on
    the market, and still no row for a leg nobody graded."""
    rows = [r for r in SPECIMEN if r[2] != "Detroit over 5.5 runs scored"] + [
        (202058565, K_TEAM_TOTAL, "Detroit over 5.5 runs scored", None, False, None),
    ]
    served = _by_name(await _team_totals(rows))

    assert (K_TEAM_TOTAL, "Detroit over 5.5 runs scored") not in served
    assert (K_TEAM_TOTAL, "Detroit over 4.5 runs scored") in served


@pytest.mark.asyncio
async def test_a_voided_market_readmits_only_the_priceless_legs_the_score_proves():
    """Every leg lost and none won may be a void (`_verdict_is_provable`), and a
    void's signature is a leg stored LOST on a line the score says came in:
    Detroit scored 3, so "over 1.5" and "over 2.5" stored losers prove nothing.
    The priceless 1.5 stays off the page; the priced 2.5 keeps its quote and no
    verdict. The lines the final score agrees with (3.5, 4.5) are decided by the
    scoreboard whatever the venue did, and read Lost (#10965, `/events/14454995`;
    this guard pinned all four off before the all-lost slice)."""
    rows = [
        (93001, K_TEAM_TOTAL, "Detroit over 2.5 runs scored", 0.4, False, "game_score"),
        (93002, K_TEAM_TOTAL, "Detroit over 3.5 runs scored", None, False, "game_score"),
        (93003, K_TEAM_TOTAL, "Detroit over 4.5 runs scored", None, False, "game_score"),
        (93004, K_TEAM_TOTAL, "Detroit over 1.5 runs scored", None, False, "game_score"),
    ]
    served = _by_name(await _team_totals(rows))

    assert served[(K_TEAM_TOTAL, "Detroit over 2.5 runs scored")]["over_probability"] == 0.4
    assert (K_TEAM_TOTAL, "Detroit over 1.5 runs scored") not in served
    for leg in ("Detroit over 3.5 runs scored", "Detroit over 4.5 runs scored"):
        row = served[(K_TEAM_TOTAL, leg)]
        assert row["is_winner"] is False
        assert row["over_probability"] == 0.0


# ── The period branch: a None row there would bypass 7b's filter entirely ────
#
# Step 7b routes a period row with `over_probability is None` to
# `period_non_totals`, which nothing filters. So on this branch the bucket-build
# gate is the ONLY thing between a readmitted priceless leg and the page; on the
# team-total branch `_enforce_monotonicity` would also drop it. These tests are
# the ones that bite if the gate is widened past `_verdict_is_provable`.


@pytest.mark.asyncio
async def test_a_priceless_graded_period_loser_is_served_as_lost():
    rows = [
        (94001, K_F5_TOTAL, "Over 3.5 runs", 0.995, True, "game_score"),
        (94002, K_F5_TOTAL, "Over 6.5 runs", None, False, "game_score"),
    ]
    served = _by_name(await _period_rows(rows))

    row = served.get((K_F5_TOTAL, "Over 6.5 runs"))
    assert row is not None
    assert row["over_probability"] == 0.0
    assert row["is_winner"] is False


@pytest.mark.asyncio
async def test_a_live_priceless_period_leg_is_still_hidden():
    rows = [
        (95001, K_F5_TOTAL, "Over 3.5 runs", 0.62, None, None),
        (95002, K_F5_TOTAL, "Over 4.5 runs", None, None, None),
    ]
    served = _by_name(await _period_rows(rows, finished=False))

    assert (K_F5_TOTAL, "Over 3.5 runs") in served
    assert (K_F5_TOTAL, "Over 4.5 runs") not in served


@pytest.mark.asyncio
async def test_a_voided_period_market_does_not_readmit_its_priceless_legs():
    rows = [
        (96001, K_F5_TOTAL, "Over 3.5 runs", 0.4, False, "game_score"),
        (96002, K_F5_TOTAL, "Over 4.5 runs", None, False, "game_score"),
    ]
    served = _by_name(await _period_rows(rows))

    assert (K_F5_TOTAL, "Over 3.5 runs") in served
    assert (K_F5_TOTAL, "Over 4.5 runs") not in served


@pytest.mark.asyncio
async def test_an_ungraded_priceless_period_leg_beside_a_winner_is_still_hidden():
    """A winner on the market is not a grade on THIS leg. Behaviour pin only: the
    tier half of `_verdict_is_provable` refuses it at bucket-build, and the #1588
    window filter would also drop it behind that (a mutant removing the tier
    half survives this test for that reason — measured, not assumed)."""
    rows = [
        (97001, K_F5_TOTAL, "Over 3.5 runs", 0.995, True, "game_score"),
        (97002, K_F5_TOTAL, "Over 6.5 runs", None, False, None),
    ]
    served = _by_name(await _period_rows(rows))

    assert (K_F5_TOTAL, "Over 3.5 runs") in served
    assert (K_F5_TOTAL, "Over 6.5 runs") not in served
