"""#10965 — the three missing Detroit rungs were refused by their BOOK, not by a NULL.

## What a reader saw after PR #10969 went live

`/api/events/14626073/game-markets` (Boston 10, Detroit 3, final) still served 11
team-total rows: Detroit over 1.5 Won, 2.5 Won, 3.5 Lost, 7.5 Lost — 4.5 / 5.5 /
6.5 absent, and the 390px "Team scoring & period lines" had the same gap.

#10969's specimen was read from `/api/futures/54069274`, which WITHHOLDS a stale
number and keeps the result, so it showed the three legs at `probability=null`.
The stored rows (Root's read-only db-query, 2026-10-13 02:47Z) are not null:

    202058567  Detroit over 4.5  current 0.020000  bid 0.0000  ask 0.0100
    202058565  Detroit over 5.5  current 0.900000  bid 0.0000  ask 0.0100
    202058566  Detroit over 6.5  current 0.330000  bid 0.0000  ask 0.0100

all `is_winner=false`, `game_score`. #8753's `_leg_price_refuted_by_its_book`
refuses every one of those prices (a graded loser asked the ask arm: 0.02, 0.90
and 0.33 all sit above the 0.01 ask) and used to drop the LEG with the price,
above the #10965 per-leg gate, so that gate was never reached.

## The rule these tests pin

A refused price is not a refused result. A settled TEAM-TOTAL leg whose grade the
final score recomputes (`_score_proves_team_total_grade`) keeps its row with its
price withheld, and is served at the 0/1 its verdict implies — never the refused
number. The same recomputation admits a settled team-total market whose quotes
are ALL gone. Everything else is refused exactly as before: a live game, an
ungraded leg, a grade the score contradicts, a club that resolves to neither
side, a unit that is not the sport's, a voided market, a player-shaped leg, and
every other market type.

## CERT-4082: one agreeing leg does not vouch for its siblings

The all-null admission used to let the WHOLE market in on one proved leg, and the
siblings then met only `_verdict_is_provable` (the market was decided), not the
score. Detroit 3 with an unpriced "over 2.5" stored as a loser was served Lost.
A market admitted on the proof now keeps exactly the legs that pass it, each on
its own score, unit, club and period. And an Under leg is never admitted on the
proof: the totals ladder reads "Boston under 7.5 runs scored" on the Over axis
(follow-up 10965-TEAM-NAMED-UNDER-AXIS), so its loss would print as 0% Over.

## CERT-4083: a final score answers only a full-game question

A Polymarket market carries a numeric id, so no ticker names its period, and the
backfill name parser reads only halves. "Boston vs Detroit: First 5 innings Team
Total Runs" therefore reached the proof as full-game and its fourteen all-null
legs were served from the FINAL score (Detroit over 1.5 Won). The proof now
refuses any market or leg title the shipped segment readers place in part of the
game, and any regulation-time window, whatever the id or ticker says.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw
from app.utils.futures_unsupported_price import price_refuted_by_live_book
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
K_GAME_TOTAL = 54069280  # illustrative: the "other market type" control

KICKOFF = datetime(2026, 5, 5, 22, 40, tzinfo=timezone.utc)
FINAL_AT = KICKOFF + timedelta(hours=3)
SETTLED_AT = FINAL_AT + timedelta(minutes=40)

MARKETS = {
    K_TEAM_TOTAL: (
        "Boston vs Detroit: Team Total",
        "KXMLBTEAMTOTAL-26MAY051840BOSDET",
    ),
    K_GAME_TOTAL: (
        "Boston vs Detroit: Total Runs",
        "KXMLBTOTAL-26MAY051840BOSDET",
    ),
}

W = ("0.995000", "0.9900", "1.0000")  # a settled winner's stored triple
# The production specimen, id for id and byte for byte:
# `(outcome_id, name, current, bid, ask, is_winner, resolution_source)`.
SPECIMEN = [
    (202058556, "Detroit over 1.5 runs scored", *W, True, "game_score"),
    (202058557, "Detroit over 2.5 runs scored", *W, True, "game_score"),
    (202058558, "Boston over 1.5 runs scored", *W, True, "game_score"),
    (202058559, "Boston over 2.5 runs scored", *W, True, "game_score"),
    (202058560, "Boston over 3.5 runs scored", *W, True, "game_score"),
    (202058561, "Boston over 4.5 runs scored", *W, True, "game_score"),
    (202058562, "Boston over 5.5 runs scored", *W, True, "game_score"),
    (202058563, "Boston over 6.5 runs scored", *W, True, "game_score"),
    (202058564, "Boston over 7.5 runs scored", *W, True, "game_score"),
    (202058565, "Detroit over 5.5 runs scored", "0.900000", "0.0000", "0.0100", False, "game_score"),
    (202058566, "Detroit over 6.5 runs scored", "0.330000", "0.0000", "0.0100", False, "game_score"),
    (202058567, "Detroit over 4.5 runs scored", "0.020000", "0.0000", "0.0100", False, "game_score"),
    (202058568, "Detroit over 3.5 runs scored", "0.010000", "0.0000", "0.0100", False, "game_score"),
    (202058569, "Detroit over 7.5 runs scored", "0.010000", "0.0000", "0.0100", False, "game_score"),
]
REFUSED = {
    "Detroit over 4.5 runs scored": 0.02,
    "Detroit over 5.5 runs scored": 0.90,
    "Detroit over 6.5 runs scored": 0.33,
}


def _dec(v):
    return None if v is None else Decimal(v)


def _game(
    rows, *, finished=True, sport_key="baseball_mlb", market_id=K_TEAM_TOTAL,
    market_name=None, external_id=None, source="kalshi",
):
    event = _make_event(
        id=EVENT_ID,
        home_team=HOME,
        away_team=AWAY,
        status="completed" if finished else "live",
        sport_key=sport_key,
        home_score=3 if finished else 2,
        away_score=10 if finished else 2,
    )
    event.llm_league = "MLB"
    event.commence_time = KICKOFF
    event.completed_at = FINAL_AT if finished else None
    event.period = "Final" if finished else "Top 3rd"
    event.game_clock = None
    event.box_score_data = {"players": {}}

    name, ticker = MARKETS[market_id]
    market = _make_futures_market(id=market_id, name=market_name or name, source=source)
    market.category = "game_prop"
    market.external_id = external_id or ticker
    market.event_id = EVENT_ID
    market.commence_time = KICKOFF
    market.status = "resolved" if finished else "open"
    market.settled_at = SETTLED_AT if finished else None

    outcomes = []
    for oid, leg, price, bid, ask, won, source in rows:
        outcome = _make_outcome(
            id=oid, market_id=market_id, name=leg, probability=0.0,
            is_winner=won, resolution_source=source,
        )
        outcome.current_probability = _dec(price)
        outcome.current_yes_bid = _dec(bid)
        outcome.current_yes_ask = _dec(ask)
        outcome.opening_probability = None
        outcomes.append(outcome)
    return event, [market], outcomes


async def _payload(rows=SPECIMEN, **kw) -> dict:
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


async def _team_totals(rows=SPECIMEN, **kw) -> dict:
    rows_out = (await _payload(rows, **kw)).get("team_totals") or []
    return {r["outcome_name"]: r for r in rows_out}


def _all_null(rows):
    return [(oid, leg, None, None, None, won, src) for oid, leg, _p, _b, _a, won, src in rows]


def _served_numbers(payload: dict) -> list:
    """Every number the payload serves, in any section, under any key."""
    found = []

    def walk(node):
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif isinstance(node, (int, float)) and not isinstance(node, bool):
            found.append(node)

    walk(payload)
    return found


# ── the specimen really is #8753's shape ─────────────────────────────────────


def test_the_specimens_three_detroit_prices_are_refused_by_their_own_book():
    """Strawman guard: without this the tests below could pass on a fixture that
    never reaches #8753 (the #10969 fixture carried no book, so it never did)."""
    for oid, leg, price, bid, ask, won, src in SPECIMEN:
        refused = price_refuted_by_live_book(
            "kalshi", src, won, float(price), float(bid), float(ask)
        )
        assert refused is (leg in REFUSED), leg


# ── the repair ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_three_book_refused_detroit_losers_are_served_as_lost():
    served = await _team_totals()

    for leg in REFUSED:
        row = served.get(leg)
        assert row is not None, f"{leg} was dropped from the settled ladder"
        assert row["over_probability"] == 0.0
        assert row["is_winner"] is False
        assert row["resolution_source"] == "game_score"
        assert row["movement"] is None
        assert row["team_side"] == "home"


@pytest.mark.asyncio
async def test_the_whole_fourteen_leg_ladder_is_served_with_its_verdicts():
    served = await _team_totals()

    assert len(served) == 14
    detroit = sorted(r["threshold"] for n, r in served.items() if n.startswith("Detroit"))
    boston = sorted(r["threshold"] for n, r in served.items() if n.startswith("Boston"))
    assert detroit == [1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5]
    assert boston == [1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5]
    for leg, row in served.items():
        won = leg.startswith("Boston") or leg in (
            "Detroit over 1.5 runs scored", "Detroit over 2.5 runs scored",
        )
        assert row["is_winner"] is won, leg
        assert row["over_probability"] == (1.0 if won else 0.0), leg


@pytest.mark.asyncio
async def test_no_refused_number_is_served_anywhere():
    """Withheld means withheld: 0.90 and 0.33 are in no section of the payload
    (0.02 included). The result is printed; the refused quote is not."""
    numbers = _served_numbers(await _payload())

    for refused in REFUSED.values():
        assert not any(abs(n - refused) < 1e-9 for n in numbers), refused


@pytest.mark.asyncio
async def test_a_settled_team_total_with_every_quote_gone_is_served():
    """The all-null admission: no leg carries a price, the market is graded, and
    the final score recomputes every grade — the ladder is served, losers
    included, instead of the whole market being dropped by `has_no_real_price`."""
    served = await _team_totals(_all_null(SPECIMEN))

    assert len(served) == 14
    assert served["Detroit over 3.5 runs scored"]["is_winner"] is False
    assert served["Detroit over 3.5 runs scored"]["over_probability"] == 0.0
    assert served["Detroit over 2.5 runs scored"]["is_winner"] is True
    assert served["Boston over 7.5 runs scored"]["over_probability"] == 1.0


# ── what must NOT change ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_refused_price_on_a_live_game_still_takes_its_leg():
    rows = [
        (98001, "Detroit over 1.5 runs scored", "0.710000", "0.7000", "0.7200", None, None),
        (98002, "Detroit over 2.5 runs scored", "0.900000", "0.0000", "0.4000", None, None),
    ]
    served = await _team_totals(rows, finished=False)

    assert "Detroit over 1.5 runs scored" in served
    assert "Detroit over 2.5 runs scored" not in served


@pytest.mark.asyncio
async def test_a_refused_price_whose_grade_the_score_contradicts_stays_dropped():
    """Detroit scored 3, so "over 2.5" graded a LOSER disagrees with the score:
    the grade is not recomputed, the leg is not readmitted."""
    rows = SPECIMEN[:1] + [
        (99001, "Detroit over 2.5 runs scored", "0.900000", "0.0000", "0.0100", False, "game_score"),
    ]
    served = await _team_totals(rows)

    assert "Detroit over 1.5 runs scored" in served
    assert "Detroit over 2.5 runs scored" not in served


@pytest.mark.asyncio
async def test_a_refused_price_on_an_ungraded_leg_stays_dropped():
    rows = SPECIMEN[:1] + [
        (99002, "Detroit over 5.5 runs scored", "0.900000", "0.0000", "0.0100", False, None),
    ]
    served = await _team_totals(rows)

    assert "Detroit over 5.5 runs scored" not in served


@pytest.mark.asyncio
async def test_a_refused_player_shaped_leg_in_a_team_total_market_stays_dropped():
    rows = SPECIMEN[:1] + [
        (99003, "Riley Greene: 2+", "0.900000", "0.0000", "0.0100", False, "game_score"),
    ]
    payload = await _payload(rows)

    names = {r["outcome_name"] for r in payload.get("player_props") or []}
    names |= {r["outcome_name"] for r in payload.get("team_totals") or []}
    assert "Riley Greene: 2+" not in names


@pytest.mark.asyncio
async def test_a_refused_price_on_another_market_type_still_takes_its_leg():
    """#8753's scope is unchanged outside team totals: a game-total loser whose
    stored 0.50 sits above its 0.01 ask is still dropped."""
    rows = [
        (99101, "Over 9.5 runs scored", "0.995000", "0.9900", "1.0000", True, "game_score"),
        (99102, "Over 14.5 runs scored", "0.500000", "0.0000", "0.0100", False, "game_score"),
    ]
    payload = await _payload(rows, market_id=K_GAME_TOTAL)

    served = {r["outcome_name"] for r in payload.get("totals") or []}
    assert "Over 14.5 runs scored" not in served


@pytest.mark.asyncio
async def test_an_all_null_market_with_a_club_on_neither_side_is_still_dropped():
    rows = [
        (99201, "New York over 1.5 runs scored", None, None, None, True, "game_score"),
        (99202, "New York over 4.5 runs scored", None, None, None, False, "game_score"),
    ]
    assert await _team_totals(rows) == {}


@pytest.mark.asyncio
async def test_an_all_null_market_in_a_foreign_unit_is_still_dropped():
    rows = [
        (99301, "Detroit over 1.5 goals scored", None, None, None, True, "game_score"),
        (99302, "Detroit over 4.5 goals scored", None, None, None, False, "game_score"),
    ]
    assert await _team_totals(rows) == {}


@pytest.mark.asyncio
async def test_an_all_null_market_in_a_sport_with_no_score_unit_is_still_dropped():
    assert await _team_totals(_all_null(SPECIMEN), sport_key="tennis_atp_us_open") == {}


@pytest.mark.asyncio
async def test_an_all_null_ungraded_market_is_still_dropped():
    rows = [(oid, leg, None, None, None, False, None) for oid, leg, *_ in SPECIMEN]
    assert await _team_totals(rows) == {}


@pytest.mark.asyncio
async def test_an_all_null_all_lost_market_serves_only_the_legs_the_score_proves():
    """Every leg lost and none won. Detroit scored 3: its over 4.5 and 5.5 losses
    are decided by the scoreboard and read Lost (#10965's all-lost slice,
    `/events/14454995`; this guard pinned them off before it). "over 1.5" stored
    a loser is the void's signature — the score says it came in — so it is never
    printed."""
    rows = [
        (99401, "Detroit over 4.5 runs scored", None, None, None, False, "game_score"),
        (99402, "Detroit over 5.5 runs scored", None, None, None, False, "game_score"),
        (99403, "Detroit over 1.5 runs scored", None, None, None, False, "game_score"),
    ]
    served = await _team_totals(rows)

    assert set(served) == {"Detroit over 4.5 runs scored", "Detroit over 5.5 runs scored"}
    for row in served.values():
        assert row["is_winner"] is False
        assert row["over_probability"] == 0.0


# ── CERT-4082: each newly admitted leg carries its own proof ────────────────


@pytest.mark.asyncio
async def test_an_all_null_market_serves_only_the_legs_the_score_proves():
    """CERT-4082's witness. Detroit scored 3: over 1.5 Won and over 4.5 Lost
    agree with the score, over 2.5 stored a LOSER does not. The agreeing legs are
    served; the contradicted one is withheld rather than printed as Lost."""
    rows = [
        (70001, "Detroit over 1.5 runs scored", None, None, None, True, "game_score"),
        (70002, "Detroit over 2.5 runs scored", None, None, None, False, "game_score"),
        (70003, "Detroit over 4.5 runs scored", None, None, None, False, "game_score"),
    ]
    served = await _team_totals(rows)

    assert set(served) == {"Detroit over 1.5 runs scored", "Detroit over 4.5 runs scored"}
    assert served["Detroit over 1.5 runs scored"]["is_winner"] is True
    assert served["Detroit over 1.5 runs scored"]["over_probability"] == 1.0
    assert served["Detroit over 4.5 runs scored"]["is_winner"] is False
    assert served["Detroit over 4.5 runs scored"]["over_probability"] == 0.0


@pytest.mark.asyncio
async def test_an_all_null_market_withholds_an_unprovable_sibling():
    """A sibling whose club resolves to neither side cannot be recomputed, so the
    proved legs beside it do not carry it in."""
    rows = [
        (70101, "Detroit over 1.5 runs scored", None, None, None, True, "game_score"),
        (70102, "New York over 3.5 runs scored", None, None, None, True, "game_score"),
        (70103, "Boston over 7.5 runs scored", None, None, None, True, "game_score"),
    ]
    served = await _team_totals(rows)

    assert set(served) == {"Detroit over 1.5 runs scored", "Boston over 7.5 runs scored"}


@pytest.mark.asyncio
async def test_an_all_null_market_withholds_a_contradicted_sibling_stored_at_zero():
    """0.0 is "no real price" to `has_no_real_price` but is not None, so it never
    meets the priceless gate: the proof must hold for it at admission too."""
    rows = [
        (70201, "Detroit over 1.5 runs scored", None, None, None, True, "game_score"),
        (70202, "Detroit over 2.5 runs scored", "0.000000", "0.0000", "0.0000", False, "game_score"),
    ]
    served = await _team_totals(rows)

    assert set(served) == {"Detroit over 1.5 runs scored"}


@pytest.mark.asyncio
async def test_a_refused_team_named_under_leg_is_not_readmitted():
    """Boston scored 10, so "Boston under 7.5" lost. The ladder reads a
    team-named Under on the Over axis, so readmitting it would print 0% Over on a
    line Boston cleared; it stays dropped, as it was before #10965."""
    rows = [SPECIMEN[0], (70301, "Boston under 7.5 runs scored", "0.900000", "0.0000", "0.0100", False, "game_score")]
    served = await _team_totals(rows)

    assert "Detroit over 1.5 runs scored" in served
    assert "Boston under 7.5 runs scored" not in served


@pytest.mark.asyncio
async def test_an_all_null_team_named_under_leg_is_not_admitted():
    rows = [
        (70401, "Detroit over 1.5 runs scored", None, None, None, True, "game_score"),
        (70402, "Boston under 7.5 runs scored", None, None, None, False, "game_score"),
    ]
    served = await _team_totals(rows)

    assert set(served) == {"Detroit over 1.5 runs scored"}


# ── CERT-4083: a period window is never proved from the final score ─────────

POLY_ID = "977353"  # a numeric Polymarket id: no ticker token names a period
FIRST_FIVE = "Boston vs Detroit: First 5 innings Team Total Runs"
FULL_GAME = "Boston vs Detroit: Team Total Runs"


def _served_results(payload: dict) -> dict:
    """Every served row anywhere in the payload that names a leg AND a verdict."""
    found: dict = {}

    def walk(node):
        if isinstance(node, dict):
            if node.get("outcome_name") and node.get("is_winner") is not None:
                found[node["outcome_name"]] = node
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    return found


@pytest.mark.asyncio
async def test_a_numeric_id_first_five_all_null_market_serves_no_result():
    """CERT-4083's witness. Detroit's three runs are a full-game fact; nothing
    shows they fell inside five innings, so no leg is served a verdict."""
    payload = await _payload(
        _all_null(SPECIMEN), market_name=FIRST_FIVE, external_id=POLY_ID, source="polymarket",
    )

    assert payload.get("team_totals") in (None, [])
    leg_names = {leg for _, leg, *_ in SPECIMEN}
    assert not leg_names & set(_served_results(payload))


@pytest.mark.asyncio
async def test_the_same_numeric_id_market_on_the_full_game_serves_its_fourteen_legs():
    """The control: identical rows, id and venue; only the period words differ."""
    served = await _team_totals(
        _all_null(SPECIMEN), market_name=FULL_GAME, external_id=POLY_ID, source="polymarket",
    )

    assert len(served) == 14
    assert served["Detroit over 1.5 runs scored"]["is_winner"] is True
    assert served["Detroit over 1.5 runs scored"]["over_probability"] == 1.0
    assert served["Detroit over 4.5 runs scored"]["over_probability"] == 0.0


@pytest.mark.asyncio
async def test_a_full_game_ticker_does_not_vouch_for_a_first_five_name():
    """The ticker wins only when it NAMES a period; a full-game ticker beside a
    first-five title does not make the question full-game."""
    payload = await _payload(_all_null(SPECIMEN), market_name=FIRST_FIVE)

    assert payload.get("team_totals") in (None, [])


@pytest.mark.parametrize(
    "market_name",
    [
        "Boston vs Detroit: 1st 5 Innings Team Total",
        "Boston vs Detroit: F5 Team Total Runs",
        "Boston vs Detroit: First Five Innings Team Total Runs",
        "Boston vs Detroit: 1st Inning Team Total",
        "Boston vs Detroit: Team Total Runs (First 3 Innings)",
    ],
)
@pytest.mark.asyncio
async def test_every_named_period_window_is_withheld(market_name):
    served = await _team_totals(
        _all_null(SPECIMEN), market_name=market_name, external_id=POLY_ID, source="polymarket",
    )

    assert served == {}


@pytest.mark.asyncio
async def test_a_period_named_only_on_the_leg_is_withheld():
    rows = [
        (70501, "Detroit over 1.5 runs scored", None, None, None, True, "game_score"),
        (70502, "Detroit over 1.5 runs scored in the first 5 innings", None, None, None, True, "game_score"),
    ]
    served = await _team_totals(
        rows, market_name=FULL_GAME, external_id=POLY_ID, source="polymarket",
    )

    assert "Detroit over 1.5 runs scored in the first 5 innings" not in served
    assert served["Detroit over 1.5 runs scored"]["is_winner"] is True


@pytest.mark.asyncio
async def test_book_refused_legs_on_a_first_five_market_stay_dropped():
    """The refused-price readmission uses the same proof, so a first-five
    market's three book-refused Detroit losers are not printed as Lost. (Kalshi:
    #8753's book refusal is the one that refuses these three prices; the
    full-game control is `test_the_three_book_refused_detroit_losers_are_served_as_lost`.)"""
    served = await _team_totals(SPECIMEN, market_name=FIRST_FIVE)

    assert not set(REFUSED) & set(served)
    assert served["Detroit over 1.5 runs scored"]["is_winner"] is True  # priced, unchanged


@pytest.mark.parametrize(
    ("market_name", "expected"),
    [
        ("Detroit vs Boston: Team Total Goals", 2),
        ("Detroit vs Boston: Team Total Goals (Regulation)", 0),
        ("Detroit vs Boston: Team Total Goals - 1st Period", 0),
    ],
)
@pytest.mark.asyncio
async def test_a_regulation_or_period_hockey_total_is_withheld(market_name, expected):
    """A final that may include overtime answers only the full-game question."""
    rows = [
        (70601, "Detroit over 1.5 goals scored", None, None, None, True, "game_score"),
        (70602, "Detroit over 4.5 goals scored", None, None, None, False, "game_score"),
    ]
    served = await _team_totals(
        rows, sport_key="icehockey_nhl", market_name=market_name,
        external_id=POLY_ID, source="polymarket",
    )

    assert len(served) == expected
