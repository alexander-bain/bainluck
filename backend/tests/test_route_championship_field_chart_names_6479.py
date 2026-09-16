"""The CHART legend on a championship board spells the club (#6479, chart half).

#6479 repaired the two surfaces that render a board's rungs as a LIST — the
detail ladder and the search card — and `test_route_championship_field_club_names_6479`
is that ship's guard. This file is the third reader path on the same page, and
the one that was left printing the lie.

WHY A THIRD FILE AND NOT THREE MORE CASES NEXT DOOR
===================================================

The list surfaces are pure serializers over a market object. `/history` is an
async route that reads snapshots, aggregates them per timestamp and can inject
a synthesized settlement point, so its harness is a mocked session rather than
a function call — a different rig for a different shape, kept apart so neither
file has to carry the other's scaffolding.

WHAT THE READER SAW, ON PRODUCTION, 2026-09-16
==============================================

`/futures/40533` at phone width: the hero read **Los Angeles Rams** and the
Probability Trend legend ~800px below it read **Los Angeles R** — one club, two
spellings, one screen, one of them a club that does not exist. The detail
payload had been repaired; `/api/futures/40533/history` still served the raw
`name` off `futures_outcomes`.

Measured before the fix across the charted top-10: `40533` 1 · `275` 3 ·
`59659428` 2 · `59659433` 1 · `59659439` 1 — **8 labels on 5 boards**, all of
which the engine resolves.

THE ASSERTION THAT IS NOT ABOUT THE LABEL
=========================================

Repairing a name is only safe if nothing MATCHES on it. Two tests at the bottom
hold that line rather than trusting the reading: the client keys its line
selection on `outcome_id` (so ids and history points must be untouched), and the
settled-champion freeze keys on the ORM's own `name` (so it must still fire on a
board whose shipped spelling is the truncated one).

🪤 EVERY QUERY PARAM IS PASSED EXPLICITLY, AND THAT IS LOAD-BEARING
===================================================================

`get_futures_history` is called directly here, so any argument left to its
default arrives as FastAPI's UNRESOLVED ``Query(...)`` object rather than as the
value in it. That object is TRUTHY, so omitting ``outcome_id`` sends the route
down its single-outcome branch with a ``Query`` where an int belongs, and
omitting ``top_n`` raises ``TypeError`` inside ``min()``. The first failure is
the dangerous one: it is silent, and it made an earlier draft of this file pass
nine tests that never executed the top-N branch they claimed to cover.

The route already defends ``champion`` against exactly this ("direct/unit
callers may pass the unresolved Query sentinel rather than None") and does not
defend ``outcome_id``. That asymmetry is harmless over HTTP — FastAPI resolves
both — so it is left alone rather than widened into this ship, and written down
here instead.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

TRUNCATED = re.compile(r"^.+ [A-Z]{1,3}$")

#: `(outcome id, ticker, shipped name)` — production rows, `futures_markets`
#: 40533 (`KXSB-27`). `Buffalo` and `Baltimore` are the controls: real names that
#: must survive byte for byte, and proof the predicate below is not simply never
#: firing.
SUPER_BOWL_RUNGS = [
    (643828, "KXSB-27-LAR", "Los Angeles R"),
    (643833, "KXSB-27-BUF", "Buffalo"),
    (643841, "KXSB-27-BAL", "Baltimore"),
    (643850, "KXSB-27-LAC", "Los Angeles C"),
    (643851, "KXSB-27-NYG", "New York G"),
    (643852, "KXSB-27-NYJ", "New York J"),
]

#: The World Series board, `futures_markets` 275 (`KXMLB-26`). `A's` and
#: `St. Louis` are its controls.
WORLD_SERIES_RUNGS = [
    (700001, "KXMLB-26-LAD", "Los Angeles D"),
    (700002, "KXMLB-26-NYY", "New York Y"),
    (700004, "KXMLB-26-CHC", "Chicago C"),
    (700005, "KXMLB-26-CWS", "Chicago WS"),
    (700008, "KXMLB-26-ATH", "A's"),
    (700009, "KXMLB-26-STL", "St. Louis"),
]

EXPECTED_COMPLETIONS = {
    "Los Angeles R": "Los Angeles Rams",
    "Los Angeles C": "Los Angeles Chargers",
    "New York G": "New York Giants",
    "New York J": "New York Jets",
    "Los Angeles D": "Los Angeles Dodgers",
    "New York Y": "New York Yankees",
    "Chicago C": "Chicago Cubs",
    "Chicago WS": "Chicago White Sox",
}

BOARDS = {
    "super_bowl": SUPER_BOWL_RUNGS,
    "world_series": WORLD_SERIES_RUNGS,
}


def _outcome(oid, ticker, name, *, prob=0.1, is_winner=None):
    # A plain namespace, not a MagicMock: a mock's `external_id` is a truthy
    # auto-attribute, which would hand the repair engine a non-string and hide
    # whether the wiring passes the real ticker.
    return SimpleNamespace(
        id=oid,
        name=name,
        external_id=ticker,
        current_probability=prob,
        is_winner=is_winner,
        # Read by `_drop_unsupported_snapshot_points` (#5611) on the way in.
        # `None` is "ungraded", which keeps every point — the shape a live open
        # board has, so the legend under test is built from real points.
        resolution_source=None,
    )


def _market(rungs, *, market_id=40533, metadata=None, resolution_date=None, settled_at=None):
    return SimpleNamespace(
        id=market_id,
        name="2027 Pro Football Champion",
        market_metadata=metadata,
        resolution_date=resolution_date,
        settled_at=settled_at,
        outcomes=[_outcome(*r) for r in rungs],
    )


def _snapshot(outcome_id, captured_at, prob):
    s = MagicMock()
    s.outcome_id = outcome_id
    s.captured_at = captured_at
    s.probability = prob
    s.bookmaker = "kalshi"
    return s


def _db(market, snapshots):
    """First `execute` returns the market; every later one returns snapshots.

    Keyed on call ORDER rather than on anything in the query text — a stub that
    sniffs a column name swallows whichever unrelated query happens to mention
    it.
    """
    calls = {"n": 0}

    async def execute(_query):
        calls["n"] += 1
        result = MagicMock()
        if calls["n"] == 1:
            result.scalar_one_or_none.return_value = market
            return result
        scalars = MagicMock()
        scalars.all.return_value = snapshots
        result.scalars.return_value = scalars
        return result

    db = AsyncMock()
    db.execute = execute
    return db


async def _served(rungs, **market_kw):
    """The payload `/api/futures/{id}/history` actually returns."""
    from app.routes.futures import get_futures_history

    market = _market(rungs, **market_kw)
    now = datetime.now(timezone.utc)
    snapshots = [
        _snapshot(o.id, now - timedelta(hours=h), 0.1)
        for o in market.outcomes
        for h in range(1, 13)
    ]
    return await get_futures_history(
        market_id=market.id,
        hours=168,
        outcome_id=None,
        top_n=10,
        db=_db(market, snapshots),
    )


def _legend(payload):
    return [o["name"] for o in payload["outcomes"]]


# ─────────────────────────────────────────────────────────────────────────────
# The ship
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("board_key", sorted(BOARDS))
async def test_the_chart_legend_spells_every_club_it_can_6479(board_key):
    rungs = BOARDS[board_key]
    names = _legend(await _served(rungs))
    expected = [EXPECTED_COMPLETIONS.get(r[2], r[2]) for r in rungs]
    assert sorted(names) == sorted(expected)


@pytest.mark.asyncio
@pytest.mark.parametrize("board_key", sorted(BOARDS))
async def test_the_chart_legend_names_no_club_that_does_not_exist_6479(board_key):
    """The reader's complaint, stated as the reader would state it."""
    truncated = [n for n in _legend(await _served(BOARDS[board_key])) if TRUNCATED.match(n)]
    assert truncated == []


@pytest.mark.asyncio
async def test_the_chart_legend_leaves_correct_names_byte_for_byte_6479():
    """A repair that rewrites correct data is worse than the truncation.

    `A's` would be destroyed by a naive "expand the trailing capitals" rule and
    `Buffalo`/`St. Louis` by an over-eager city-plus-nickname compose.
    """
    names = set(_legend(await _served(WORLD_SERIES_RUNGS)))
    assert {"A's", "St. Louis"} <= names
    assert {"Buffalo", "Baltimore"} <= set(_legend(await _served(SUPER_BOWL_RUNGS)))


@pytest.mark.asyncio
async def test_the_hero_and_the_legend_cannot_print_two_spellings_6479():
    """The defect verbatim: the detail ladder and the chart are one page.

    Asserted as agreement between the two serializers rather than as two
    independent expectations, so neither can drift without this failing.
    """
    from app.routes.futures import _format_market_detail

    detail_board = SimpleNamespace(
        id=40533,
        external_id="KXSB-27",
        name="2027 Pro Football Champion",
        description=None,
        sport=None,
        sport_name=None,
        category=None,
        llm_sport_category="football",
        status="open",
        source="kalshi",
        market_type="championship",
        mutually_exclusive=True,
        commence_time=None,
        resolution_date=None,
        created_at=None,
        updated_at=None,
        group_id=None,
        canonical_market_key=None,
        hook_description=None,
        category_tags=None,
        image_url=None,
        outcomes=[
            SimpleNamespace(
                id=oid,
                name=nm,
                external_id=tk,
                current_probability=0.1,
                current_american_odds=400,
                rank=1,
                rank_change_24h=None,
                probability_change_24h=None,
                opening_probability=None,
                opening_american_odds=None,
                is_winner=None,
                resolution_source=None,
                last_updated=None,
            )
            for oid, tk, nm in SUPER_BOWL_RUNGS
        ],
    )
    ladder = {o["name"] for o in _format_market_detail(detail_board)["outcomes"]}
    assert set(_legend(await _served(SUPER_BOWL_RUNGS))) <= ladder


# ─────────────────────────────────────────────────────────────────────────────
# What the repair must NOT touch
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_only_the_prose_moves_ids_and_points_are_untouched_6479():
    """The client selects chart lines by `outcome_id`, never by label."""
    payload = await _served(SUPER_BOWL_RUNGS)
    row = next(o for o in payload["outcomes"] if o["outcome_id"] == 643828)
    assert row["name"] == "Los Angeles Rams"
    assert len(row["history"]) == 12
    assert all(p["probability"] == pytest.approx(0.1) for p in row["history"])
    assert {o["outcome_id"] for o in payload["outcomes"]} == {r[0] for r in SUPER_BOWL_RUNGS}


@pytest.mark.asyncio
async def test_a_rung_with_no_ticker_is_charted_exactly_as_the_venue_sent_it_6479():
    """No ticker, no id-anchored answer — so print what Kalshi sent."""
    rungs = [(643828, None, "Los Angeles R"), (643833, None, "Buffalo")]
    assert sorted(_legend(await _served(rungs))) == ["Buffalo", "Los Angeles R"]


@pytest.mark.asyncio
async def test_a_board_of_unresolvable_rungs_is_charted_unchanged_6479():
    """The common case: most boards are not team sports at all."""
    rungs = [
        (900001, "0x" + "a" * 64, "Option A"),
        (900002, "0x" + "b" * 64, "Option B"),
        (900003, "KXSPORTSEMMY-26OLSSCE-SUP", "Super Bowl LX"),
    ]
    assert sorted(_legend(await _served(rungs))) == ["Option A", "Option B", "Super Bowl LX"]


# ─────────────────────────────────────────────────────────────────────────────
# The settled path — the one place the label is written by a SECOND site
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_settled_champions_line_carries_the_repaired_name_6479():
    """`_apply_settled_winner_freeze` writes its own `name`, from the same dict.

    A board whose champion is the truncated rung would otherwise chart a
    resolved line labelled `Los Angeles R` directly under a hero caption reading
    "Settled — Los Angeles Rams won." — the original defect, on the one surface
    where the two sentences are closest together.
    """
    rungs = [
        (643828, "KXSB-27-LAR", "Los Angeles R"),
        (643833, "KXSB-27-BUF", "Buffalo"),
    ]
    market = _market(rungs, resolution_date=datetime.now(timezone.utc) - timedelta(days=1))
    market.outcomes[0].is_winner = True

    from app.routes.futures import get_futures_history

    now = datetime.now(timezone.utc)
    snaps = [
        _snapshot(o.id, now - timedelta(hours=h), 0.1)
        for o in market.outcomes
        for h in range(1, 13)
    ]
    payload = await get_futures_history(
        market_id=40533, hours=168, outcome_id=None, top_n=10, db=_db(market, snaps)
    )

    champ = next(o for o in payload["outcomes"] if o["outcome_id"] == 643828)
    assert champ["name"] == "Los Angeles Rams"
    assert champ["history"][-1]["probability"] == 1.0


@pytest.mark.asyncio
async def test_repairing_the_label_did_not_move_the_champion_MATCH_6479():
    """The safety argument, asserted instead of reasoned.

    The freeze resolves its champion off `FuturesOutcome.name` on the ORM — the
    SHIPPED spelling — so the display repair must not have quietly changed which
    outcome it selects. A caller passing the truncated crown still freezes the
    right line, and the line still renders repaired.
    """
    rungs = [
        (643828, "KXSB-27-LAR", "Los Angeles R"),
        (643833, "KXSB-27-BUF", "Buffalo"),
    ]
    market = _market(rungs, resolution_date=datetime.now(timezone.utc) - timedelta(days=1))

    from app.routes.futures import get_futures_history

    now = datetime.now(timezone.utc)
    snaps = [
        _snapshot(o.id, now - timedelta(hours=h), 0.1)
        for o in market.outcomes
        for h in range(1, 13)
    ]
    payload = await get_futures_history(
        market_id=40533,
        hours=168,
        outcome_id=None,
        top_n=10,
        db=_db(market, snaps),
        champion="Los Angeles R",
    )

    champ = next(o for o in payload["outcomes"] if o["outcome_id"] == 643828)
    assert champ["history"][-1]["probability"] == 1.0
    assert champ["name"] == "Los Angeles Rams"

    other = next(o for o in payload["outcomes"] if o["outcome_id"] == 643833)
    assert other["history"][-1]["probability"] == pytest.approx(0.1)
