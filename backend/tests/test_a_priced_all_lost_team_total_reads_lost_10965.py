"""#10965 — a priced team total in which EVERY leg lost is still a decided question.

## What a reader saw

`/api/events/14454995/game-markets` (San Diego 1 at Colorado 0, final), read
2026-10-13 04:30Z after Root's 52-leg `game_score` apply: Kalshi's
`KXMLBTEAMTOTAL-26APR212040SDCOL` holds 14 legs, Colorado over 1.5 … 7.5 and
San Diego over 1.5 … 7.5, every one a CORRECT `game_score` loser — and every one
still carrying its last quote (Colorado over 1.5 at 0.86, San Diego over 7.5 at
0.315). No leg won, so `_verdict_is_provable(row, market_has_a_winner=False)`
read the market as possibly voided: the ladder served the stale quotes, and the
Game question matrix — what the iPhone's Team totals section reads — published
all 14 as `quoted` / `unknown`. iPhone 0/14 Lost (lane1, sim 04B41542); web 390px
14/14 (it reads `is_winner` off the row).

PR #10975 (7e042c05b0) proves team totals from the score only on its two
ADMISSION paths (a refused price, an all-unpriced market). A priced market enters
neither, so its legs never carried `_SCORE_PROVED_KEY`.

## The rule these tests pin

#6312's spreads rule, for the family `_score_proves_this_grade` cannot read: a
team-total leg whose grade `_score_proves_team_total_grade` recomputes from the
final score carries `_SCORE_PROVED_KEY`, so it serves its 0/1 verdict and the
matrix prints Lost — on its own evidence, with or without a winning sibling.
It is an OR. An Under, a contradicted grade, a live game and an unresolved club
carry no key and keep the sibling-winner rule exactly.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
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

EVENT_ID = 14454995
HOME = "Colorado Rockies"
AWAY = "San Diego Padres"
MARKET_ID = 12234671
TICKER = "KXMLBTEAMTOTAL-26APR212040SDCOL"
MARKET_NAME = "San Diego vs Colorado: Team Total"

KICKOFF = datetime(2026, 4, 22, 0, 40, tzinfo=timezone.utc)
FINAL_AT = KICKOFF + timedelta(hours=3)
SETTLED_AT = FINAL_AT + timedelta(minutes=40)

# The production specimen, id for id: `(outcome_id, name, stored price)`, every
# leg `is_winner=False`, `game_score`. Colorado scored 0 and San Diego 1, so no
# line from 1.5 up came in for either club.
SPECIMEN = [
    (70151704, "Colorado over 1.5 runs scored", "0.860000"),
    (70151707, "Colorado over 2.5 runs scored", "0.770000"),
    (70151709, "Colorado over 3.5 runs scored", "0.650000"),
    (70151711, "Colorado over 4.5 runs scored", "0.480000"),
    (70151714, "Colorado over 5.5 runs scored", "0.410000"),
    (70151715, "Colorado over 6.5 runs scored", "0.310000"),
    (70151717, "Colorado over 7.5 runs scored", "0.215000"),
    (70151705, "San Diego over 1.5 runs scored", "0.620000"),
    (70151706, "San Diego over 2.5 runs scored", "0.570000"),
    (70151708, "San Diego over 3.5 runs scored", "0.570000"),
    (70151710, "San Diego over 4.5 runs scored", "0.570000"),
    (70151712, "San Diego over 5.5 runs scored", "0.570000"),
    (70151713, "San Diego over 6.5 runs scored", "0.445000"),
    (70151716, "San Diego over 7.5 runs scored", "0.315000"),
]
SPECIMEN_IDS = {oid for oid, *_ in SPECIMEN}


def _rows(won=False, source="game_score"):
    return [(oid, leg, price, won, source) for oid, leg, price in SPECIMEN]


def _game(rows, *, finished=True, home_score=0, away_score=1):
    event = _make_event(
        id=EVENT_ID,
        home_team=HOME,
        away_team=AWAY,
        status="completed" if finished else "live",
        sport_key="baseball_mlb",
        home_score=home_score,
        away_score=away_score,
    )
    event.llm_league = "MLB"
    event.commence_time = KICKOFF
    event.completed_at = FINAL_AT if finished else None
    event.period = "Final" if finished else "Top 7th"
    event.game_clock = None
    event.box_score_data = {"players": {}}

    market = _make_futures_market(id=MARKET_ID, name=MARKET_NAME, source="kalshi")
    market.category = "game_prop"
    market.external_id = TICKER
    market.event_id = EVENT_ID
    market.commence_time = KICKOFF
    market.status = "resolved" if finished else "open"
    market.settled_at = SETTLED_AT if finished else None

    outcomes = []
    for oid, leg, price, won, source in rows:
        outcome = _make_outcome(
            id=oid, market_id=MARKET_ID, name=leg, probability=0.0,
            is_winner=won, resolution_source=source,
        )
        outcome.current_probability = None if price is None else Decimal(price)
        outcome.current_yes_bid = None
        outcome.current_yes_ask = None
        outcome.opening_probability = None
        outcomes.append(outcome)
    return event, [market], outcomes


async def _payload(rows, **kw) -> dict:
    from app.main import app
    from app.routes.events import _game_markets_cache

    _game_markets_cache.clear()
    event, futures, outcomes = _game(rows, **kw)
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


def _team_totals(payload: dict) -> dict:
    return {r["outcome_name"]: r for r in payload.get("team_totals") or []}


def _matrix_options(payload: dict) -> dict:
    """outcome id → the matrix option that publishes it (the iPhone's reader)."""
    found: dict = {}
    matrix = payload.get("game_question_matrix") or {}
    for question in matrix.get("questions") or []:
        for option in question.get("options") or []:
            ids = option.get("contributor_outcome_ids") or []
            if len(ids) == 1:
                found[ids[0]] = option
    return found


# ── the specimen ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_every_priced_all_lost_leg_reads_lost_in_the_question_matrix():
    """The acceptance: `game_question_matrix` result is Lost on 14/14 options."""
    options = _matrix_options(await _payload(_rows()))

    assert SPECIMEN_IDS <= set(options), sorted(SPECIMEN_IDS - set(options))
    for oid in SPECIMEN_IDS:
        option = options[oid]
        assert option["result"]["state"] == "lost", (option["label"], option["result"])
        assert option["published"]["value_state"] == "result", option["label"]
        assert option["published"]["value"] is None, option["label"]


@pytest.mark.asyncio
async def test_the_ladder_serves_each_leg_its_verdict_not_its_stale_quote():
    served = _team_totals(await _payload(_rows()))

    assert len(served) == 14
    for _oid, leg, _price in SPECIMEN:
        row = served[leg]
        assert row["is_winner"] is False, leg
        assert row["resolution_source"] == "game_score", leg
        assert row["over_probability"] == 0.0, (leg, row["over_probability"])


@pytest.mark.asyncio
async def test_an_all_lost_market_stored_at_zero_reads_lost():
    """56946034's shape: every leg priced 0.0. Before, the ladder's `> 0` filter
    dropped each row because no sibling won; the score's proof keeps them."""
    rows = [(oid, leg, "0.000000", False, "game_score") for oid, leg, _p in SPECIMEN]
    payload = await _payload(rows)

    assert len(_team_totals(payload)) == 14
    options = _matrix_options(payload)
    assert all(options[oid]["result"]["state"] == "lost" for oid in SPECIMEN_IDS)


@pytest.mark.asyncio
async def test_an_all_lost_market_with_every_quote_gone_reads_lost():
    rows = [(oid, leg, None, False, "game_score") for oid, leg, _p in SPECIMEN]
    payload = await _payload(rows)

    assert len(_team_totals(payload)) == 14
    options = _matrix_options(payload)
    assert all(options[oid]["result"]["state"] == "lost" for oid in SPECIMEN_IDS)


# ── what still carries no proof ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_leg_the_score_contradicts_is_never_printed_lost():
    """San Diego scored 4 here: its over 1.5–3.5 came in, so a stored LOSER on
    those lines is wrong (a void shape) and keeps today's behaviour — no Lost,
    and its stale quote is not dressed as a result. The lines the score agrees
    with still read Lost."""
    options = _matrix_options(await _payload(_rows(), away_score=4))
    contradicted = {70151705, 70151706, 70151708}  # San Diego over 1.5 / 2.5 / 3.5

    for oid in contradicted:
        assert options[oid]["result"]["state"] != "lost", options[oid]["label"]
        assert options[oid]["published"]["value_state"] != "result"
    for oid in SPECIMEN_IDS - contradicted:
        assert options[oid]["result"]["state"] == "lost", options[oid]["label"]


@pytest.mark.asyncio
async def test_a_team_named_under_in_an_all_lost_market_carries_no_proof():
    """The ladder reads "San Diego under 0.5" on the Over axis
    (10965-TEAM-NAMED-UNDER-AXIS), so it is never proved here and keeps its quote."""
    rows = _rows() + [(70159999, "San Diego under 0.5 runs scored", "0.400000", False, "game_score")]
    payload = await _payload(rows)

    assert _matrix_options(payload)[70159999]["result"]["state"] == "unknown"
    under = _team_totals(payload)["San Diego under 0.5 runs scored"]
    assert "_score_proves_verdict" not in under
    assert under["over_probability"] == 0.4


@pytest.mark.asyncio
async def test_an_ungraded_all_lost_market_carries_no_proof():
    rows = [(oid, leg, price, False, None) for oid, leg, price in SPECIMEN]
    options = _matrix_options(await _payload(rows))

    assert all(o["result"]["state"] != "lost" for o in options.values())


@pytest.mark.asyncio
async def test_a_live_game_carries_no_proof():
    options = _matrix_options(await _payload(_rows(), finished=False))

    assert all(o["result"]["state"] != "lost" for o in options.values())


@pytest.mark.asyncio
async def test_a_market_with_a_winner_is_unchanged():
    """Control, 13722478's shape (Los Angeles 7 at Colorado 1): winners on the
    market, so every leg was already provable; the result set is identical."""
    rows = [
        (80000 + i, leg, price, won, "game_score")
        for i, (leg, price, won) in enumerate([
            ("Colorado over 1.5 runs scored", "0.000000", False),
            ("Colorado over 2.5 runs scored", "0.000000", False),
            ("San Diego over 1.5 runs scored", "1.000000", True),
            ("San Diego over 6.5 runs scored", "1.000000", True),
            ("San Diego over 7.5 runs scored", "0.000000", False),
        ])
    ]
    options = _matrix_options(await _payload(rows, home_score=1, away_score=7))

    assert [options[80000 + i]["result"]["state"] for i in range(5)] == [
        "lost", "lost", "won", "won", "lost",
    ]
