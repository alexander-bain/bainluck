"""#6815 — a live match page stops pricing a question the venue already closed.

## The specimen, shopped at 390px

`/events/15313988` — Guadalajara Open Akron doubles, Bucsa/Melichar v
Kozyreva/Lumsden, `live`, read 2026-09-17 23:35Z. The hero reads `LIVE 83% – 17%`
over a win-probability chart whose last point is six seconds old. Directly
beneath it, *Additional Markets*, stamped `9h ago`::

    Bucsa/Melichar vs Kozyreva/Lumsden                        9h ago
      Bucsa/Melichar wins Set 1     ████████████████████     >99%
      Kozyreva/Lumsden wins Set 1                             <1%
      Bucsa/Melichar wins Set 2     ██████████████           71%
      Kozyreva/Lumsden wins Set 2   ██████                   30%

Set 1 finished hours before that read. Market `61276254` is `status='resolved'`,
and BOTH of its legs are stored `is_winner=False` with
`resolution_source='clob_authoritative'` beside prices of `0.999500` and
`0.000500` — the venue graded the market and nobody won it. So the page cannot
say who took the set, and offers a reader a 99% *probability* on a question that
was answered before they opened the page.

## What #6169 left behind, and why it is the same trap as #5481

`_verdict_is_provable` already refuses the VERDICT here: a voided market is
graded a loser on every leg, so "this leg lost" proves nothing about the other
side, and the row is served with no winner stated. That refusal is right and it
stays. But it is a refusal about the verdict channel only — the price channel
keeps the fossil number, and withholding the grade removed the one field that
marked the number as a settlement. The page stopped saying "Bucsa/Melichar — won
Set 1" and started saying ">99%", live, under a freshness stamp. That is exactly
what #6595's withhold did to #5481's population, one gate over.

## The discriminator is the GRADE, not `status` — and the existing suite said so

#6815's body rules out `fm.status`: `_build_game_markets` deliberately ignores it
for LINKED rows ("resolved markets on completed games should show") and keying
the serve on status would blank correct settled cards. It is right. The gate was
first written on `market_assigned_settled` alone and two existing tests refused
it, which is why it has its last line:

* `test_game_markets.test_linked_market_ignores_stale_category_and_status_filters`
  — a linked `status='closed'` market with an UNGRADED 0.54 leg on a `live`
  event, asserted to render. The contract #6815 warned about, as a test.
* `test_…_6312.test_a_resolved_margin_market_on_a_LIVE_game_publishes_nothing` —
  a `resolved` market with one graded loser beside one ungraded 0.40 leg, where
  #6312 drops the graded leg and keeps the other.

Neither is the specimen. What makes the specimen decidable is not that the book
is shut but that **the market was graded, at verdict tier, on every leg, and none
of them won** — exactly the population `_verdict_is_provable` already refuses to
speak for. So this is #6169 extended into the price channel, and the two tests
above stay green. `test_a_closed_book_that_was_never_graded_is_LEFT_ALONE` and
`test_one_ungraded_leg_keeps_the_whole_market` are the scope statements.

## The measured scope, twice over

**Why `live` and not every unfinished event.** Assigned-settled markets by the
event's own status, production 2026-09-17 23:4xZ::

                     has a winner   NO winner
    live <6h               39                 13   ← the filed class
    suspended           4,756              1,090
    voided             13,349             18,828
    scheduled           2,751                481

The `voided` tail is 3,710 fixtures cancelled days ago and `suspended` is this
codebase's graveyard as much as a rain delay (915 of its events commenced over a
day before the read). Taking them would be a 20,000-market behaviour change
riding a 13-market ship. Hence `_IN_PLAY_EVENT_STATUSES`.

**What the shipped predicate actually drops**, replayed with the tier test,
production 2026-09-18 00:0xZ (`sql_fingerprint f501b6da7ac1f79a`): of 78 settled
markets on 24 live events, **13 on 7 events** — 11 Polymarket, 2 Kalshi. 64 keep
their rows because the market produced a winner, 1 because it is not fully
graded. Seven of the thirteen are one page: `/events/15313712` (Lys v Podoroska),
whose set winner, both match totals, total sets, set handicap and game spread all
sit at 0.9995 with every leg graded a loser.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.routes.events import (
    _IN_PLAY_EVENT_STATUSES,
    _closed_book_cannot_price_a_live_game,
)
from app.services.database import get_db, get_db_rw
from tests.integration.test_route_events_seeded import (
    _make_event,
    _make_event_detail_session,
    _make_futures_market,
    _make_outcome,
)

# Offset from the clock at call time, never a literal date (gotcha #44): the
# anchor is a plain subtraction and carries no branch.
NOW = datetime.now(timezone.utc)
# The doubles match started a little over three hours ago and is still on court.
FIRST_BALL = NOW - timedelta(hours=3, minutes=5)


def _event(*, status="live", commence=FIRST_BALL, completed_at=None):
    event = MagicMock()
    event.status = status
    event.commence_time = commence
    event.completed_at = completed_at
    return event


def _market(*, status="resolved"):
    market = MagicMock()
    market.status = status
    return market


def _outcome(*, probability=0.9995, is_winner=None, resolution_source=None):
    outcome = MagicMock()
    outcome.current_probability = probability
    outcome.is_winner = is_winner
    outcome.resolution_source = resolution_source
    return outcome


def _all_legs_lost():
    """Set 1's two legs exactly as production stores them: graded at tier 3 by
    the venue's own CLOB, both losers, priced 0.9995 / 0.0005. A fresh list per
    call — a module-level one is shared mutable state across 21 tests."""
    return [
        _outcome(probability=0.9995, is_winner=False, resolution_source="clob_authoritative"),
        _outcome(probability=0.0005, is_winner=False, resolution_source="clob_authoritative"),
    ]


# ── The specimen ─────────────────────────────────────────────────────────────


def test_the_specimen_a_closed_set_winner_is_dropped_from_a_live_page():
    """Market `61276254` on `/events/15313988`: `resolved`, both legs graded
    losers, priced 0.9995/0.0005, on a match still being played."""
    assert _closed_book_cannot_price_a_live_game(
        _event(), _market(), _all_legs_lost(), NOW, False
    )


def test_a_closed_book_that_was_never_graded_is_LEFT_ALONE():
    """🔴 #6815'S OTHER SPECIMEN, AND THIS SHIP DOES NOT TAKE IT. Set 2 at 71%
    beside Set 1 on the same card: the venue closed the book, nothing was ever
    graded, and the last price keeps printing.

    The gate was first written on `market_assigned_settled` alone, which reaches
    this row through `status` — and the existing suite refused it, twice:
    `test_game_markets.test_linked_market_ignores_stale_category_and_status_filters`
    asserts a linked `status='closed'` market with an ungraded 0.54 leg renders
    on a `live` event, which is the "trust linked markets for status" contract
    #6815's body warned about, stated as a test. Overruling it without blanking
    the settled cards it protects is a separate rule and stays open on #6815.

    So this assertion is a SCOPE STATEMENT, not an oversight. If a later ship
    takes this population it has to come here and delete this test on purpose."""
    assert not _closed_book_cannot_price_a_live_game(
        _event(),
        _market(status="resolved"),
        [_outcome(probability=0.705), _outcome(probability=0.295)],
        NOW,
        False,
    )


def test_one_ungraded_leg_keeps_the_whole_market():
    """`all`, not `any`. #6312's own live-game fixture is this shape — a
    `resolved` margin market with one graded loser beside one ungraded 0.40 leg —
    and #6312 drops the graded leg while keeping the other. A market with
    anything left to say keeps every leg; this gate only takes one that has
    nothing."""
    assert not _closed_book_cannot_price_a_live_game(
        _event(),
        _market(),
        [
            _outcome(probability=0.0, is_winner=False, resolution_source="api_settlement"),
            _outcome(probability=0.40),
        ],
        NOW,
        False,
    )


def test_all_losers_on_a_market_the_venue_still_lists_as_OPEN_is_left_alone():
    """🔴 THE ONE RESIDUAL, PINNED RATHER THAN LEFT TO BE DISCOVERED. Found by
    mutation: deleting the `market_assigned_settled` line changed nothing,
    because every fixture here carries a settled STATUS, so the check was
    unkillable and therefore unexamined.

    It is doing something real. `market_assigned_settled`'s grade arm is
    `any(bool(o.is_winner))`, and `False` is falsy — so an all-LOSERS market
    reaches it only through its status. Gotcha #33 says Kalshi leaves settled
    markets at `status='open'`, so a Kalshi market graded all-losers on a live
    page is a reachable shape that this gate declines to take.

    Measured on production 2026-09-18 00:0xZ: **zero such rows** across every
    live event (`sql_fingerprint 10eefc36ca4e9fa2`), so the scope costs nothing
    today. Named here, and on #6815, so the day it costs something the reason is
    already written down rather than re-derived from a blank card."""
    assert not _closed_book_cannot_price_a_live_game(
        _event(), _market(status="open"), _all_legs_lost(), NOW, False
    )


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("ungradeable_result", id="a RETRACTION, tier 1"),
        pytest.param("clean_resolution", id="tier 1"),
        pytest.param(None, id="no source at all"),
        pytest.param("", id="empty"),
        pytest.param("something_invented_later", id="unknown, tier 0"),
    ],
)
def test_a_grade_below_verdict_tier_is_not_a_verdict(source):
    """The tier half of `_row_is_graded_at_verdict_tier`, and #5411 is why it
    exists: both live US Open finalists carried `ungradeable_result` WHILE
    TRADING, so a gate keyed on "there is a resolution_source" freezes exactly
    the rows that most need to move. Below tier 2 the row is a reading of a
    price and stays a price."""
    assert not _closed_book_cannot_price_a_live_game(
        _event(),
        _market(),
        [
            _outcome(probability=0.9995, is_winner=False, resolution_source=source),
            _outcome(probability=0.0005, is_winner=False, resolution_source=source),
        ],
        NOW,
        False,
    )


def test_a_tier_2_grade_from_the_box_score_is_a_verdict():
    """Not only tier 3: `game_score` recomputes to the same winner from cited
    data and is an answer by the same test. Pins that the gate reads the TIER
    rather than a hard-coded list of CLOB sources."""
    assert _closed_book_cannot_price_a_live_game(
        _event(),
        _market(),
        [
            _outcome(probability=0.9995, is_winner=False, resolution_source="game_score"),
            _outcome(probability=0.0005, is_winner=False, resolution_source="game_score"),
        ],
        NOW,
        False,
    ) is True


# ── The four refusals. Each of these is a real row the gate must not take. ───


def test_a_live_matchs_own_graded_set_winner_survives():
    """🔴 THE COHORT THE WHOLE SHIP IS SHAPED AROUND. A first set that finished
    and was graded to a WINNER is real information about the match the reader is
    watching, and #5771 kept the started-but-unfinished bucket in scope precisely
    to protect it. Identical to the specimen in every field the gate reads except
    that this market produced a winner."""
    assert not _closed_book_cannot_price_a_live_game(
        _event(),
        _market(),
        [_outcome(probability=1.0, is_winner=True), _outcome(probability=0.0, is_winner=False)],
        NOW,
        True,
    )


@pytest.mark.parametrize(
    "status,completed_at",
    [
        pytest.param("completed", NOW - timedelta(minutes=8), id="completed"),
        pytest.param("closed", NOW - timedelta(hours=2), id="closed"),
    ],
)
def test_a_settled_card_on_a_finished_game_is_untouched(status, completed_at):
    """Settled means settled (gotcha #43). A finished page keeps its whole
    journey, and what it may CLAIM about a voided market is #6169/#6312's
    question, already answered there. This gate never reaches it.

    Kept as a behaviour test after the gate's own `_event_is_really_finished`
    call was measured DEAD and removed: a `completed` event fails the in-play
    scope, so this is the assertion that goes red if that scope is ever widened
    past a match in play."""
    assert not _closed_book_cannot_price_a_live_game(
        _event(status=status, completed_at=completed_at),
        _market(),
        _all_legs_lost(),
        NOW,
        False,
    )


@pytest.mark.parametrize(
    "status",
    [
        pytest.param("voided", id="voided — 3,710 cancelled fixtures"),
        pytest.param("suspended", id="suspended — the graveyard status"),
        pytest.param("scheduled", id="scheduled"),
        pytest.param("in_progress", id="a state this codebase does not write"),
        pytest.param("", id="empty"),
        pytest.param(None, id="null"),
    ],
)
def test_the_gate_is_scoped_to_a_match_in_play(status):
    """The honest rule is true of more rows than this, and asked of every
    unfinished event it reaches 20,000 markets on pages nobody is watching. The
    scope is the measurement, not a hedge — see `_IN_PLAY_EVENT_STATUSES`."""
    assert not _closed_book_cannot_price_a_live_game(
        _event(status=status), _market(), _all_legs_lost(), NOW, False
    )


def test_live_is_the_only_in_play_status():
    """Pins the set itself: a later widening has to come here and say so, rather
    than arrive as a one-word edit that silently takes the voided tail."""
    assert _IN_PLAY_EVENT_STATUSES == frozenset({"live"})


def test_a_live_row_that_has_not_kicked_off_belongs_to_5771():
    """#46: a row can be `live` with a commence_time in the FUTURE. #5771 owns
    every settled market on a fixture that has not started, so the two gates
    partition the population instead of overlapping on it."""
    assert not _closed_book_cannot_price_a_live_game(
        _event(commence=NOW + timedelta(minutes=40)), _market(), _all_legs_lost(), NOW, False
    )


@pytest.mark.parametrize(
    "status",
    [
        pytest.param("open", id="open"),
        pytest.param("active", id="active"),
        pytest.param("", id="empty"),
    ],
)
def test_an_unsettled_market_is_never_touched(status):
    """No status, no grade, no drop. A quiet book on a live match is #6734's
    ingest question — this gate may not reach a market the venue still trades,
    whatever its price is doing."""
    assert not _closed_book_cannot_price_a_live_game(
        _event(),
        _market(status=status),
        [_outcome(probability=0.705), _outcome(probability=0.295)],
        NOW,
        False,
    )


def test_a_market_with_no_outcomes_at_all_is_not_dropped():
    """`None` is "we did not load them", not "there are none". A page build must
    never throw on a lookup and must never drop on an absence."""
    assert not _closed_book_cannot_price_a_live_game(
        _event(), _market(), None, NOW, False
    )


def test_a_null_commence_time_does_not_drop_the_market():
    """Unknown is not "has started". `_event_has_not_kicked_off` abstains on a
    NULL, so the only thing standing between this row and a drop is the status
    scope — asserted here so the abstention is not silently load-bearing."""
    assert _closed_book_cannot_price_a_live_game(
        _event(commence=None), _market(), _all_legs_lost(), NOW, False
    )


def test_the_winner_flag_is_the_callers_and_is_obeyed():
    """The loop passes `market.id in markets_with_a_winner`, built by #6169 from
    the UNFILTERED outcomes, so this gate and `_verdict_is_provable` cannot
    disagree about whether a market settled. Recomputing it from the filtered
    list here would be a second opinion — this asserts the argument wins even
    when the rows it is given say otherwise."""
    graded = [
        _outcome(probability=1.0, is_winner=True, resolution_source="clob_authoritative")
    ]
    assert not _closed_book_cannot_price_a_live_game(
        _event(), _market(), graded, NOW, True
    )
    assert _closed_book_cannot_price_a_live_game(
        _event(), _market(), graded, NOW, False
    )


# ── The route. What the reader actually gets. ────────────────────────────────


def _guadalajara_seed():
    """`/events/15313988` as production held it at 23:35Z.

    Four markets, and the page must keep three of them: the live match-winner,
    the still-trading Set 2, and the set handicap. Only the closed, ungradeable
    Set 1 leaves.
    """
    event = _make_event(
        id=15313988,
        home_team="Bucsa/Melichar",
        away_team="Kozyreva/Lumsden",
        status="live",
        sport_key="tennis_wta",
        home_score=None,
        away_score=None,
    )
    event.commence_time = FIRST_BALL
    event.completed_at = None

    set_one = _make_futures_market(
        id=61276254,
        name="Set 1 Winner: Bucsa/Melichar vs Kozyreva/Lumsden",
        source="polymarket",
        sport_category="tennis",
    )
    set_one.status = "resolved"
    set_one.event_id = event.id

    set_two = _make_futures_market(
        id=61276255,
        name="Set 2 Winner: Bucsa/Melichar vs Kozyreva/Lumsden",
        source="polymarket",
        sport_category="tennis",
    )
    set_two.status = "open"
    set_two.event_id = event.id

    match_winner = _make_futures_market(
        id=61276253,
        name="Guadalajara Open Akron (Doubles): Bucsa/Melichar vs Kozyreva/Lumsden",
        source="polymarket",
        sport_category="tennis",
    )
    match_winner.status = "open"
    match_winner.event_id = event.id

    outcomes = [
        # Graded, both losers, `clob_authoritative` — the stored shape verbatim.
        _make_outcome(
            id=230617588,
            market_id=set_one.id,
            name="Bucsa/Melichar",
            probability=0.9995,
            is_winner=False,
            resolution_source="clob_authoritative",
        ),
        _make_outcome(
            id=230617589,
            market_id=set_one.id,
            name="Kozyreva/Lumsden",
            probability=0.0005,
            is_winner=False,
            resolution_source="clob_authoritative",
        ),
        _make_outcome(
            id=230617590, market_id=set_two.id, name="Bucsa/Melichar", probability=0.705
        ),
        _make_outcome(
            id=230617591, market_id=set_two.id, name="Kozyreva/Lumsden", probability=0.295
        ),
        _make_outcome(
            id=230617580, market_id=match_winner.id, name="Bucsa/Melichar", probability=0.83
        ),
        _make_outcome(
            id=230617581, market_id=match_winner.id, name="Kozyreva/Lumsden", probability=0.17
        ),
    ]
    return event, [set_one, set_two, match_winner], outcomes


def _graded_set_seed():
    """The control at route level: the same page, with Set 1 graded to a WINNER.

    Nothing may leave. If this ever goes red the ship has eaten #5771's cohort.
    """
    event, markets, outcomes = _guadalajara_seed()
    for outcome in outcomes:
        if outcome.market_id == 61276254:
            outcome.is_winner = outcome.name == "Bucsa/Melichar"
    return event, markets, outcomes


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
async def test_the_route_stops_printing_a_closed_sets_99_percent():
    payload = await _served(_guadalajara_seed(), 15313988)
    rows = _all_rows(payload)
    served = {row["market_name"] for row in rows}

    assert "Set 1 Winner: Bucsa/Melichar vs Kozyreva/Lumsden" not in served, (
        "the closed, ungradeable first set is still priced on a live page — the "
        f"reader is offered '>99%' on a set that finished hours ago: {rows}"
    )
    assert "Set 2 Winner: Bucsa/Melichar vs Kozyreva/Lumsden" in served, (
        "the set still being played left with it; the gate has taken a market "
        f"the venue is trading: {rows}"
    )
    assert any(
        "Guadalajara Open Akron" in row["market_name"] for row in rows
    ), f"the live match-winner market was withdrawn: {rows}"
    # `.get`, because the sections do not share one row shape — a player-prop row
    # carries no `probability` key at all, and indexing it turns a real assertion
    # into a KeyError that passes for a failure without ever testing anything.
    assert not any(
        row.get("probability") is not None and row["probability"] >= 0.995
        for row in rows
    ), f"a >99% row survived on a match still being played: {rows}"


@pytest.mark.asyncio
async def test_the_route_keeps_a_set_that_was_graded_to_a_winner():
    payload = await _served(_graded_set_seed(), 15313988)
    served = {row["market_name"] for row in _all_rows(payload)}

    assert "Set 1 Winner: Bucsa/Melichar vs Kozyreva/Lumsden" in served, (
        "a live match's own settled first set was withdrawn — this is the "
        f"information #5771 kept the started bucket in scope to protect: {payload}"
    )
