"""#5481 — a LIVE match page stops printing another game's settled price.

## The specimen, shopped at 390px

`/events/15313672` — Colorado Rockies v San Diego Padres, `live`, 2-9 in the
middle of the 8th, read 2026-09-17 21:43Z. Under *Additional Markets → Novelty
Props*, one row::

    Colorado Rockies vs San Diego Padres            · 16h ago
    San Diego Padres                        ███████   100%

Market `60683971` is a Polymarket container pinned to the **2026-09-15T00:40Z**
fixture, settled at 05:37Z this morning, attached to tonight's 19:10Z event. Its
`1.000` is the settlement price of a game played three days earlier.

Tonight's real book is in the same payload — Kalshi `61072383`, `San Diego 0.99 /
Colorado 0.01`, observed a minute before the read — and the card never shows it:
the frontend filters a two-sided market summing to 1.0 as the hero's own
question, which a one-legged settlement is not. The only match-winner number the
reader gets on that card is the previous game's result.

## Why the fix is server-side, against the issue's own routing

#5481 routed the render half to ux: *a row that declares its own settlement
(`resolution_source = api_settlement`) still prints a live probability*. That
field is no longer on the wire for this population. #6595's
`_settled_grade_fields` withholds `is_winner` AND `resolution_source` whenever a
settlement was observed before the event began — correct, and it stays — so the
payload now reads `is_winner: null, resolution_source: null` beside a price of
1.000 and a frontend rule keyed on the settlement being PRESENT can never fire.
The withhold turned a wrong verdict into a wrong price; this is the price half.

## What this file has to prove, in both directions

`_settled_market_prices_an_unstarted_game` (#5771) already withdraws this shape
before kickoff and deliberately stops there, because the started-but-unfinished
bucket is mostly a live match's genuinely-settled sub-market — a finished first
set — which a withdrawal would destroy. So the load-bearing tests here are the
NEGATIVE ones: `test_a_live_matchs_own_settled_set_winner_survives` and
`test_the_route_keeps_a_live_tennis_pages_own_settled_sets` carry the eight
Polymarket markets on `/events/15313836` (Ortenzi v Badosa), whose pins name
their event's own commence to the second and which must reach the page exactly
as they do today.

Measured on production 2026-09-17 22:0xZ: of 32 settled markets on 23 unfinished
events, this drops 3 — all Polymarket weekly containers holding a previous game
in the same series, no Kalshi market at all.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.routes.events import (
    _ANOTHER_FIXTURE_PIN_GAP,
    _pinned_fixture_time,
    _settled_book_belongs_to_another_fixture,
)
from app.services.database import get_db, get_db_rw
from tests.integration.test_route_events_seeded import (
    _make_event,
    _make_event_detail_session,
    _make_futures_market,
    _make_outcome,
)

# Offset from the clock at call time, never a literal date (gotcha #44): this
# file's anchor is a plain subtraction with no branch in it.
NOW = datetime.now(timezone.utc)
# First pitch two and a half hours ago — the game the reader is watching.
FIRST_PITCH = NOW - timedelta(hours=2, minutes=33)
# The fixture the mis-attached container was actually pinned against.
ANOTHER_NIGHT = FIRST_PITCH - timedelta(days=2, hours=18, minutes=30)


def _event(*, commence=FIRST_PITCH, status="live", completed_at=None):
    event = MagicMock()
    event.commence_time = commence
    event.status = status
    event.completed_at = completed_at
    return event


def _market(*, pin=ANOTHER_NIGHT, status="resolved", metadata=None):
    """A market carrying a pregame pin, `pin=None` for one that carries none."""
    market = MagicMock()
    market.status = status
    if metadata is not None:
        market.market_metadata = metadata
    elif pin is None:
        market.market_metadata = {}
    else:
        market.market_metadata = {
            "pregame_mark": {
                "commence_time": pin.isoformat(),
                "observed_at": (pin - timedelta(minutes=4)).isoformat(),
                "outcomes": {"228423965": 0.635},
            }
        }
    return market


def _outcome(*, probability=1.0, is_winner=None):
    outcome = MagicMock()
    outcome.current_probability = probability
    outcome.is_winner = is_winner
    return outcome


# ── `_pinned_fixture_time`: the fossil, and every way of not having one ──────


def test_the_pin_is_read_as_an_instant():
    assert _pinned_fixture_time(_market(pin=ANOTHER_NIGHT)) == ANOTHER_NIGHT


def test_a_zulu_pin_is_read():
    """`Z` is what a hand-written or re-serialised mark carries; the writer emits
    `+00:00`, and a reader that understood only one of the two would be a gate
    that quietly stops firing the day the writer changes."""
    market = _market(metadata={"pregame_mark": {"commence_time": "2026-09-15T00:40:00Z"}})
    assert _pinned_fixture_time(market) == datetime(2026, 9, 15, 0, 40, tzinfo=timezone.utc)


def test_a_naive_pin_is_read_as_utc():
    market = _market(metadata={"pregame_mark": {"commence_time": "2026-09-15T00:40:00"}})
    assert _pinned_fixture_time(market) == datetime(2026, 9, 15, 0, 40, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "metadata",
    [
        pytest.param({}, id="no pregame_mark"),
        pytest.param({"pregame_mark": None}, id="a null mark"),
        pytest.param({"pregame_mark": "2026-09-15T00:40:00+00:00"}, id="a mark that is a string"),
        pytest.param({"pregame_mark": {"outcomes": {}}}, id="a mark with no commence_time"),
        pytest.param({"pregame_mark": {"commence_time": None}}, id="a null commence_time"),
        pytest.param({"pregame_mark": {"commence_time": ""}}, id="an empty commence_time"),
        pytest.param({"pregame_mark": {"commence_time": 1758000000}}, id="an epoch integer"),
        pytest.param({"pregame_mark": {"commence_time": "tomorrow"}}, id="unparseable"),
    ],
)
def test_an_unreadable_pin_is_no_pin(metadata):
    assert _pinned_fixture_time(_market(metadata=metadata)) is None


def test_a_row_whose_metadata_is_not_a_dict_has_no_pin():
    """The fixtures every other test file in this repo builds are `MagicMock`s
    whose `market_metadata` answers with another `MagicMock`. If that read did not
    fail open, this gate would fire on all of them."""
    assert _pinned_fixture_time(_make_futures_market()) is None
    assert _pinned_fixture_time(MagicMock()) is None


# ── The gate: the specimen, and the cohort it may never reach ────────────────


def test_the_specimen_a_previous_games_settled_container_is_dropped():
    """Market 60683971 on `/events/15313672`: one leg at 1.000, pinned three days
    back, on a game in the middle of the 8th."""
    assert _settled_book_belongs_to_another_fixture(
        _event(), _market(), [_outcome(probability=1.0, is_winner=True)], NOW
    )


def test_a_live_matchs_own_settled_set_winner_survives():
    """The cohort #5771 protected and this gate must not reach: `Set 1 Winner:
    Jazmin Ortenzi vs Paula Badosa`, settled at 18:59Z during a match that is
    still being played, pinned to its own event's commence to the second."""
    assert not _settled_book_belongs_to_another_fixture(
        _event(),
        _market(pin=FIRST_PITCH),
        [_outcome(probability=1.0, is_winner=True)],
        NOW,
    )


@pytest.mark.parametrize(
    "offset,dropped",
    [
        pytest.param(timedelta(0), False, id="pinned to this fixture exactly"),
        pytest.param(timedelta(hours=5), False, id="5h — a revised start time"),
        pytest.param(_ANOTHER_FIXTURE_PIN_GAP, False, id="12h — the boundary keeps the market"),
        pytest.param(_ANOTHER_FIXTURE_PIN_GAP + timedelta(minutes=1), True, id="12h01 — over"),
        pytest.param(timedelta(days=1), True, id="the previous night"),
        pytest.param(timedelta(days=-1), True, id="the NEXT night, the same distance away"),
        pytest.param(timedelta(days=-5), True, id="five days ahead"),
    ],
)
def test_the_gap_is_measured_in_both_directions_from_the_fixture(offset, dropped):
    """`abs`, not a signed comparison: a container re-attached FORWARD is the same
    defect as one re-attached back, and a signed test would serve half of them."""
    assert (
        _settled_book_belongs_to_another_fixture(
            _event(),
            _market(pin=FIRST_PITCH - offset),
            [_outcome(is_winner=True)],
            NOW,
        )
        is dropped
    )


def test_the_threshold_still_sits_in_the_measured_trough():
    """The boundary case above is written in terms of the constant, so it moves
    with it and can never catch a retune — this is the test that holds the value.

    |pin − event commence| over the 21,618 pins on events commencing in the 14
    days to 2026-09-17: 20,354 inside 6h, **8** in the whole 6-to-12h band, 1,256
    beyond 12h. Anywhere in that empty band partitions the same rows to within 8.
    A threshold that leaves it is no longer read off the data, and whoever moves
    it owes a fresh count — not a smaller diff.
    """
    assert timedelta(hours=6) <= _ANOTHER_FIXTURE_PIN_GAP <= timedelta(hours=12)


# ── The four refusals, each costing a real row if it were dropped ────────────


def test_a_finished_event_keeps_everything():
    """Settled means settled (gotcha #43). The finished half of this exact
    mis-attachment is `_verdict_contradicts_the_final_score` (#6627)."""
    assert not _settled_book_belongs_to_another_fixture(
        _event(status="completed", completed_at=NOW - timedelta(minutes=20)),
        _market(),
        [_outcome(is_winner=True)],
        NOW,
    )


def test_a_fixture_that_has_not_started_is_5771s():
    """The two gates partition the unfinished population rather than overlapping
    on it, so neither has to reason about the other's rows."""
    assert not _settled_book_belongs_to_another_fixture(
        _event(commence=NOW + timedelta(hours=3)),
        _market(),
        [_outcome(is_winner=True)],
        NOW,
    )


def test_a_market_with_no_pin_is_kept():
    assert not _settled_book_belongs_to_another_fixture(
        _event(), _market(pin=None), [_outcome(is_winner=True)], NOW
    )


def test_an_unsettled_market_is_kept_however_far_its_pin_has_moved():
    """A pin that has moved is evidence about WHICH fixture, never about whether
    the book is closed. An open market keeps its rows and its price."""
    assert not _settled_book_belongs_to_another_fixture(
        _event(),
        _market(status="open"),
        [_outcome(probability=0.62, is_winner=None)],
        NOW,
    )


def test_a_kalshi_row_settled_while_still_reading_open_is_in_scope():
    """gotcha #33: Kalshi's settled markets keep `status='open'` here, which is why
    the settledness test is `market_assigned_settled` and not a status read."""
    assert _settled_book_belongs_to_another_fixture(
        _event(), _market(status="open"), [_outcome(is_winner=True)], NOW
    )


@pytest.mark.parametrize(
    "event,outcomes",
    [
        pytest.param(_event(commence=None), [_outcome(is_winner=True)], id="no commence_time"),
        pytest.param(_event(), None, id="outcomes not loaded"),
    ],
)
def test_a_missing_signal_keeps_the_market(event, outcomes):
    assert not _settled_book_belongs_to_another_fixture(event, _market(), outcomes, NOW)


def test_an_empty_outcome_list_answers_exactly_as_5771_does():
    """Not reachable from the route — `if not market_outcomes: continue` sits
    above both gates — and pinned here because the two must not drift. An empty
    list is `market_assigned_settled`'s status-only branch, so both read a
    `status='resolved'` market as settled; whichever way that ever changes, it has
    to change for the pair.
    """
    from app.routes.events import _settled_market_prices_an_unstarted_game

    unstarted = _event(commence=NOW + timedelta(hours=3))
    assert _settled_book_belongs_to_another_fixture(_event(), _market(), [], NOW) is (
        _settled_market_prices_an_unstarted_game(unstarted, _market(), [], NOW)
    )


def test_a_naive_commence_time_does_not_throw_the_page():
    """Older fixtures build naive datetimes, and this gate is asked of EVERY market
    on EVERY event — the same coercion #5771 needed one function above."""
    assert _settled_book_belongs_to_another_fixture(
        _event(commence=FIRST_PITCH.replace(tzinfo=None)),
        _market(),
        [_outcome(is_winner=True)],
        NOW,
    )


# ── The route: what the reader gets ──────────────────────────────────────────


def _padres_seed():
    """`/events/15313672` as it was served at 21:43Z, trimmed to the two markets
    that decide the card.

    Both are `other`-classified rather than assumed to be: a control in the wrong
    section proves nothing, and `_classify_game_market` routes a bare matchup name
    to `other` on both of these.
    """
    event = _make_event(
        id=15313672,
        home_team="Colorado Rockies",
        away_team="San Diego Padres",
        status="live",
        sport_key="baseball_mlb",
        home_score=2,
        away_score=9,
    )
    event.commence_time = FIRST_PITCH
    event.completed_at = None

    foreign = _make_futures_market(
        id=60683971,
        name="San Diego Padres vs. Colorado Rockies",
        source="polymarket",
        sport_category="baseball",
    )
    foreign.status = "resolved"
    foreign.event_id = event.id
    foreign.market_metadata = {
        "pregame_mark": {
            "commence_time": ANOTHER_NIGHT.isoformat(),
            "observed_at": (ANOTHER_NIGHT - timedelta(minutes=13)).isoformat(),
            "outcomes": {"228423965": 0.635},
        }
    }

    tonight = _make_futures_market(
        id=61072383,
        name="San Diego vs Colorado",
        source="kalshi",
        sport_category="baseball",
    )
    tonight.status = "open"
    tonight.event_id = event.id
    tonight.market_metadata = {
        "pregame_mark": {
            "commence_time": FIRST_PITCH.isoformat(),
            "observed_at": (FIRST_PITCH - timedelta(minutes=2)).isoformat(),
            "outcomes": {"229449917": 0.62},
        }
    }

    outcomes = [
        _make_outcome(
            id=228423965,
            market_id=foreign.id,
            name="San Diego Padres",
            probability=1.0,
            is_winner=True,
            resolution_source="api_settlement",
        ),
        _make_outcome(
            id=229449917, market_id=tonight.id, name="San Diego", probability=0.99
        ),
        _make_outcome(
            id=229449918, market_id=tonight.id, name="Colorado", probability=0.01
        ),
    ]
    return event, [foreign, tonight], outcomes


def _ortenzi_seed():
    """`/events/15313836` — a live match whose OWN set-winner market has settled.

    The control for the whole ship: same shape as the specimen (resolved, graded,
    priced at 1.000, on an unfinished event) and different in the one field the
    gate reads.
    """
    event = _make_event(
        id=15313836,
        home_team="Jazmin Ortenzi",
        away_team="Paula Badosa",
        status="live",
        sport_key="tennis_wta",
        home_score=None,
        away_score=None,
    )
    event.commence_time = FIRST_PITCH
    event.completed_at = None

    set_one = _make_futures_market(
        id=61276388,
        name="Set 1 Winner: Jazmin Ortenzi vs Paula Badosa",
        source="polymarket",
        sport_category="tennis",
    )
    set_one.status = "resolved"
    set_one.event_id = event.id
    set_one.market_metadata = {
        "pregame_mark": {
            "commence_time": FIRST_PITCH.isoformat(),
            "observed_at": (FIRST_PITCH - timedelta(minutes=6)).isoformat(),
            "outcomes": {"1": 0.41},
        }
    }

    outcomes = [
        _make_outcome(
            id=1,
            market_id=set_one.id,
            name="Jazmin Ortenzi",
            probability=1.0,
            is_winner=True,
            resolution_source="api_settlement",
        ),
    ]
    return event, [set_one], outcomes


async def _served(seed, event_id):
    from app.main import app
    from app.routes.events import _game_markets_cache

    _game_markets_cache.clear()
    event, markets, outcomes = seed
    mock_session = _make_event_detail_session(
        event=event, futures=markets, outcomes=outcomes
    )

    async def _mock_get_db():
        yield mock_session

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
                resp = await ac.get(f"/api/events/{event_id}/game-markets")
        assert resp.status_code == 200, resp.text
        return resp.json()
    finally:
        _game_markets_cache.clear()
        app.dependency_overrides.clear()


def _all_rows(payload):
    return [
        row
        for section in (
            "totals",
            "player_props",
            "team_totals",
            "spreads",
            "period_markets",
            "matchups",
            "other",
        )
        for row in (payload.get(section) or [])
    ]


@pytest.mark.asyncio
async def test_the_route_stops_serving_the_previous_games_100_percent():
    payload = await _served(_padres_seed(), 15313672)
    rows = _all_rows(payload)
    served = {row["market_name"] for row in rows}

    assert "San Diego Padres vs. Colorado Rockies" not in served, (
        "the previous game's settled container is still on a live page — the "
        f"reader sees 'San Diego Padres 100%' in the 8th inning: {rows}"
    )
    assert "San Diego vs Colorado" in served, (
        "tonight's own book left with it; the gate has taken the market it exists "
        f"to leave behind: {rows}"
    )
    assert not any(
        row["probability"] is not None and row["probability"] >= 0.995 for row in rows
    ), f"a 100% row survived on a game that is 2-9 in the 8th: {rows}"


@pytest.mark.asyncio
async def test_the_route_keeps_a_live_tennis_pages_own_settled_sets():
    payload = await _served(_ortenzi_seed(), 15313836)
    served = {row["market_name"] for row in _all_rows(payload)}

    assert "Set 1 Winner: Jazmin Ortenzi vs Paula Badosa" in served, (
        "a live match's own settled first set was withdrawn — this is the "
        "information #5771 kept the started bucket in scope to protect: "
        f"{payload}"
    )
