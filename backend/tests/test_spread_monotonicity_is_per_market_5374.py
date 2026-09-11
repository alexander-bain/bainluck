"""#5374 — a spread row was capped by a row from a different market.

## What a reader saw

`GET /api/events/15309206/game-markets` (Zverev vs Khachanov, live, measured
2026-09-11 21:07Z) served, against the stored outcome price read in the same minute:

    Alexander Zverev -2.5 games              stored 0.84   SERVED 0.11
    Alexander Zverev -5.5 games              stored 0.60   SERVED 0.11
    Alexander Zverev wins by over 1.5 sets   stored 0.68   SERVED 0.245
    Set Handicap Zverev (-2.5)  Yes          stored 0.375  SERVED 0.245
    Set Handicap Zverev (-2.5)  No           stored 0.625  SERVED 0.245

7 of 11 spread rows wrong, and two of them refute themselves without any ground
truth at all: one binary market served Yes 0.245 AND No 0.245, a pair summing to
0.49.

## Why

Step 7d grouped spreads by `team_side`, and **nothing ever set `team_side` on a
spread row** — it is assigned in 7c on team-TOTAL rows and only read here. So the
default fired for every spread on every event, the whole section became one
group, and `_enforce_monotonicity` — which caps each row at the previous row's
probability — ran across five markets and two sources as if they were one ladder.
The served list came out monotone non-increasing end to end:

    0.72  0.28  0.28  0.23  0.23  0.23  0.23  0.06  0.06  0.06  0.05

The Kalshi ladder 0.84/0.50/0.08 is *already* correctly monotone and needed no
help. It was destroyed by a cap inherited from an unrelated Polymarket market and
from the OPPOSING player's outcome (Khachanov at 0.11), which is not a rung of
Zverev's ladder in any sense.

## The rule these tests pin

A cap never crosses a market, and inside a market it only applies to rows that
are actually rungs of one ladder: every row carries a threshold and the
thresholds are distinct. A Yes/No pair (no threshold) and a mixed-side market
(repeated thresholds) are left alone. A genuine single-market ladder is still
capped exactly as before, and the `> 0` filter still runs on every row so
skipping the cap cannot put a priceless rung back on the page.

The fixture is the production specimen: the same five markets, the same names,
and prices from the same read.
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

EVENT_ID = 15309206

PM_H15 = 60658923  # polymarket, Yes/No, no threshold
PM_H25 = 60658924  # polymarket, Yes/No, no threshold
PM_G55 = 60658925  # polymarket, Yes/No, no threshold
K_SET = 60673350  # kalshi, two outcomes SHARING threshold 1.5 — opposite sides
K_GAME = 60673355  # kalshi, a real ladder at 2.5 / 5.5 / 8.5

# (market_id, outcome_name, stored price) — production values, verbatim.
SPECIMEN = [
    (PM_H15, "Yes", 0.61),
    (PM_H15, "No", 0.39),
    (PM_H25, "No", 0.625),
    (PM_H25, "Yes", 0.375),
    (PM_G55, "Yes", 0.57),
    (PM_G55, "No", 0.43),
    (K_SET, "Alexander Zverev wins by over 1.5 sets", 0.68),
    (K_SET, "Karen Khachanov wins by over 1.5 sets", 0.11),
    (K_GAME, "Alexander Zverev -2.5 games", 0.84),
    (K_GAME, "Alexander Zverev -5.5 games", 0.50),
    (K_GAME, "Alexander Zverev -8.5 games", 0.08),
]

MARKET_NAMES = {
    PM_H15: ("Set Handicap: Zverev (-1.5) vs Khachanov (+1.5)", "polymarket"),
    PM_H25: ("Set Handicap: Zverev (-2.5) vs Khachanov (+2.5)", "polymarket"),
    PM_G55: ("Game Spread: Zverev (-5.5) vs Khachanov (+5.5)", "polymarket"),
    K_SET: ("Alexander Zverev vs Karen Khachanov: Set Spread", "kalshi"),
    K_GAME: ("Alexander Zverev vs Karen Khachanov: Game Spread", "kalshi"),
}


def _zverev_khachanov(rows=None):
    rows = SPECIMEN if rows is None else rows
    event = _make_event(
        id=EVENT_ID,
        home_team="Alexander Zverev",
        away_team="Karen Khachanov",
        status="live",
        sport_key="tennis_atp_us_open",
        home_score=1,
        away_score=0,
    )
    event.llm_league = "ATP"
    event.commence_time = datetime.now(timezone.utc) - timedelta(hours=1)
    event.completed_at = None
    event.box_score_data = {"players": {}}

    used = {mid for mid, _n, _p in rows}
    futures = []
    for mid in sorted(used):
        name, source = MARKET_NAMES[mid]
        market = _make_futures_market(id=mid, name=name, source=source)
        market.status = "open"
        market.event_id = EVENT_ID
        futures.append(market)

    outcomes = []
    for i, (mid, name, prob) in enumerate(rows):
        outcome = _make_outcome(
            id=90000 + i, market_id=mid, name=name, probability=prob or 0.0
        )
        # `probability=None` must survive as None rather than 0.0 — it is the
        # priceless-row case the hoisted `> 0` filter exists for.
        outcome.current_probability = prob
        outcomes.append(outcome)

    return event, futures, outcomes


async def _client(rows=None):
    from app.main import app
    from app.routes.events import _game_markets_cache

    _game_markets_cache.clear()
    event, futures, outcomes = _zverev_khachanov(rows)
    mock_session = _make_event_detail_session(
        event=event, futures=futures, outcomes=outcomes
    )

    async def _mock_get_db():
        yield mock_session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user
    return app, _game_markets_cache


async def _spreads(rows=None) -> list[dict]:
    app, cache = await _client(rows)
    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.get(f"/api/events/{EVENT_ID}/game-markets")
    cache.clear()
    assert resp.status_code == 200, resp.text
    return resp.json().get("spreads") or []


def _served(spreads) -> dict:
    return {(r["_market_id"], r["outcome_name"]): r["probability"] for r in spreads}


# ── The non-vacuity assertion ────────────────────────────────────────────────
#
# Both tests below pass trivially on a specimen that happens to be ordered — if
# the stored prices already descend in the order 7d sorts them, the old cascade
# changed nothing and a green test proves nothing. So pin that this fixture is
# one the bug DEMONSTRABLY corrupts, in the fixture's own terms, before pinning
# what the fix does to it.


def test_the_specimen_really_is_one_the_cascade_corrupts():
    """A cross-market cascade would move these prices — the fixture has teeth."""
    ordered = sorted(
        SPECIMEN,
        key=lambda r: abs(
            {
                "Alexander Zverev -2.5 games": 2.5,
                "Alexander Zverev -5.5 games": 5.5,
                "Alexander Zverev -8.5 games": 8.5,
                "Alexander Zverev wins by over 1.5 sets": 1.5,
                "Karen Khachanov wins by over 1.5 sets": 1.5,
            }.get(r[1], 0)
        ),
    )
    probs = [p for _m, _n, p in ordered]
    rises = [(a, b) for a, b in zip(probs, probs[1:]) if b > a]
    assert rises, (
        "fixture is already monotone non-increasing, so the one-group cascade "
        "would be a no-op and these tests could not fail on the old code"
    )
    # And specifically: the Kalshi ladder sits behind a cheaper row from another
    # market, which is the exact shape that destroyed 0.84 on production.
    assert probs.index(0.84) > probs.index(0.11)


@pytest.mark.asyncio
async def test_a_spread_row_is_never_capped_by_a_row_from_another_market():
    """Every row serves its own market's price. This is the whole defect."""
    served = _served(await _spreads())

    for market_id, name, stored in SPECIMEN:
        assert served.get((market_id, name)) == pytest.approx(stored, abs=0.005), (
            f"{name} (market {market_id}) served {served.get((market_id, name))!r}, "
            f"stored {stored}"
        )


@pytest.mark.asyncio
async def test_a_binary_market_never_serves_both_legs_at_one_price():
    """Yes and No are complements. A pair summing to 0.49 refutes itself."""
    served = _served(await _spreads())

    for market_id in (PM_H15, PM_H25, PM_G55):
        yes = served[(market_id, "Yes")]
        no = served[(market_id, "No")]
        assert yes != no, f"market {market_id} served Yes and No both at {yes}"
        assert yes + no == pytest.approx(1.0, abs=0.01), (
            f"market {market_id} legs sum to {yes + no}, not 1"
        )


@pytest.mark.asyncio
async def test_two_outcomes_on_one_rung_are_opposite_sides_not_a_step_down():
    """Same threshold ⇒ not a ladder. Khachanov's 0.11 must not cap Zverev's 0.68."""
    served = _served(await _spreads())

    assert served[(K_SET, "Alexander Zverev wins by over 1.5 sets")] == pytest.approx(
        0.68, abs=0.005
    )
    assert served[(K_SET, "Karen Khachanov wins by over 1.5 sets")] == pytest.approx(
        0.11, abs=0.005
    )


# ── What must NOT change ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_real_ladder_inside_one_market_is_still_capped():
    """The smoother still smooths where its premise holds: one market, one side,
    distinct rungs. A rung that prices ABOVE an easier rung is still pulled down."""
    rising = [
        (K_GAME, "Alexander Zverev -2.5 games", 0.30),
        (K_GAME, "Alexander Zverev -5.5 games", 0.55),  # harder, yet dearer
        (K_GAME, "Alexander Zverev -8.5 games", 0.70),  # harder still
    ]
    served = _served(await _spreads(rising))

    assert served[(K_GAME, "Alexander Zverev -2.5 games")] == pytest.approx(0.30)
    assert served[(K_GAME, "Alexander Zverev -5.5 games")] == pytest.approx(0.30)
    assert served[(K_GAME, "Alexander Zverev -8.5 games")] == pytest.approx(0.30)


@pytest.mark.asyncio
async def test_a_priceless_rung_is_still_dropped_from_a_group_no_longer_capped():
    """The `> 0` filter lived INSIDE `_enforce_monotonicity`. Groups that no
    longer call it must still lose their priceless rows — skipping the cap is not
    licence to put a rung with no price back on the page."""
    with_blank = [
        (PM_H25, "No", 0.625),
        (PM_H25, "Yes", None),  # no price at all
    ]
    spreads = await _spreads(with_blank)
    served = _served(spreads)

    assert (PM_H25, "Yes") not in served, "a priceless rung reached the payload"
    assert served[(PM_H25, "No")] == pytest.approx(0.625, abs=0.005)
