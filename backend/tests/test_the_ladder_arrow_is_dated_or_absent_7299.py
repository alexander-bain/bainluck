"""#7299 — the All Outcomes ladder's rank ARROW is dated or absent.

THE DEFECT, as a reader met it on production (build `529dc529`, v4787). One row
of `/futures/60268421` printed, left to right:

    ``↓5``  …  ``LAST MOVE —``  …  ``LATEST 4%``

The LAST MOVE column is blank because #4079's guard refused it: the route could
not date the move, so it said nothing. The arrow immediately to the left of the
same outcome's name then says the row fell five places over that same
twenty-four hours. One 24h number refused and another printed beside it, off a
basis we had just declared unusable. Seven of fourteen visible rows did it;
`/futures/58321581` printed ``↓18`` on a row serving a null move, and a
collapsed row carried ``rank_change_24h: -1`` with ``probability: null`` — a
rank move on a row with no price at all.

WHY THE FIX IS A REFUSAL AND NOT A SECOND SUBTRACTION. `dated_movement_points`
rescues a banked row because it RE-DERIVES the amount from an observed price.
There is nothing to re-derive here: the writers store ``old_rank - new_rank``
for ONE POLL, so the integer is a rank change over the gap between two polls of
unknown length, wearing a "24h" label. Co-dating it with the price bank — the
shape this was first filed with — only narrows the mislabel, and
`test_a_banked_row_that_serves_a_dated_MOVE_still_serves_no_ARROW` is the test
that says so.

A true dated arrow is a property of the whole BOARD, and the route cannot see
one: measured on production 2026-09-21, the bank dates 1.0% of the 162,611
outcomes on open markets and covers every row on just 37 of 24,398 markets —
48 outcomes, 4 arrows, 2 markets. Against the 9,748 arrows now live on 1,785
boards, that is not a coverage problem to tune, it is an answer the payload does
not hold. The wider source (`futures_odds_snapshots`) needs a per-market window
query this route does not make and a bookmaker-consistent ranking, and is a
costed follow-on.

Roles, in this file's own vocabulary:

    SHIP     red against the parent commit. This is the change.
    GUARD    green against the parent, red against a named mutant.
    CONTROL  green against both — what the refusal may not cost.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.routes.futures import _format_market_detail
from app.utils.futures_market_snapshot import (
    DATED_BASIS_METADATA_KEY,
    DATED_BASIS_MIN_AGE_HOURS,
    DATED_BASIS_WINDOW_HOURS,
)

UTC = timezone.utc

#: `_format_market_detail` takes no `now` and reads the real clock — correctly,
#: because production has no clock to inject. So the basis is anchored to the
#: clock the code under test will actually read and THEN offset (gotcha #44):
#: 19h18m sits inside [`DATED_BASIS_MIN_AGE_HOURS`, `DATED_BASIS_WINDOW_HOURS`]
#: with hours of margin at both ends, so this file holds at every hour of every
#: day. An absolute instant here would age out of the window on its own and turn
#: every "serves a number" assertion red while every "withholds one" assertion
#: passed for the wrong reason — which is exactly how #4079's file went red.
LIVE_BASIS_AT = datetime.now(UTC) - timedelta(hours=19, minutes=18)

assert DATED_BASIS_MIN_AGE_HOURS < 19.3 < DATED_BASIS_WINDOW_HOURS, (
    "the window moved under this file; re-derive LIVE_BASIS_AT, do not widen it"
)


class _Outcome:
    def __init__(self, id, name, probability, change_24h, rank, rank_change_24h):
        self.id = id
        self.name = name
        self.external_id = f"leg-{id}"
        self.current_probability = probability
        self.probability_change_24h = change_24h
        self.rank = rank
        self.rank_change_24h = rank_change_24h
        self.opening_probability = None
        self.opening_captured_at = None
        self.opening_american_odds = None
        self.current_american_odds = None
        self.team_id = None
        self.calibration_probability = None
        self.is_winner = None
        self.resolution_source = None
        self.price_changed_at = None
        self.last_updated = datetime.now(UTC) - timedelta(minutes=6)
        # A readable two-sided book on every leg, so the fabricated-midpoint and
        # unbacked-leg gates keep the whole board. A fixture whose rows were all
        # dropped upstream would pass this entire file vacuously.
        self.current_yes_bid = max(0.01, (probability or 0.5) - 0.02)
        self.current_yes_ask = min(0.99, (probability or 0.5) + 0.02)


class _Market:
    """A real object, so the ``__dict__.get(...)`` the bank fold uses works."""

    def __init__(self, id, name, outcomes, *, bank=None):
        self.id = id
        self.name = name
        self.source = "kalshi"
        self.external_id = f"kx-{id}"
        self.sport_id = None
        self.sport = None
        self.category = "entertainment"
        self.llm_sport_category = "entertainment"
        self.llm_league = None
        self.llm_gender = None
        self.llm_level = None
        self.market_tier = 1
        self.market_type = "outright"
        self.mutually_exclusive = True
        self.description = None
        self.canonical_market_key = "ladder-arrow-dated-7299"
        self.group_id = None
        self.group_type = None
        self.image_url = None
        self.image_width = None
        self.image_height = None
        self.hook_description = None
        self.hook_generated_at = None
        self.hook_leader_at_generation = None
        self.curation_score_adj = 0
        self.volume_24h = 250_000
        self.status = "open"
        self.commence_time = datetime.now(UTC) - timedelta(days=1)
        self.resolution_date = datetime.now(UTC) + timedelta(days=90)
        self.created_at = datetime.now(UTC) - timedelta(days=30)
        self.updated_at = datetime.now(UTC)
        self.event_concept_key = None
        self.hub_slug = None
        self.category_tags = None
        self.market_metadata = (
            {DATED_BASIS_METADATA_KEY: bank} if bank is not None else {}
        )
        self.outcomes = outcomes


def _cell(price, at=None):
    """One bank cell in the sweep's own wire shape: ``[price, ISO instant]``."""
    return [price, (at or LIVE_BASIS_AT).strftime("%Y-%m-%dT%H:%M:%SZ")]


# ── THE SPECIMEN ────────────────────────────────────────────────────────────
#
# `The Game Awards: Game of the Year` (58321581), a named #4079 control and the
# board this issue's worst row was read from. The leader is the one rung the
# bank can date, which is the live shape — the sweep banks an observation only
# where one qualifies. Every rung carries a NON-ZERO stored `rank_change_24h`,
# because a fixture that stored nothing could not tell a refusal from an empty
# column and this whole file would pass against the defect.


def _game_awards_market(*, bank=True, leader_price=0.66):
    leader = _Outcome(216388319, "Grand Theft Auto VI", leader_price, -0.025, 1, 5)
    runner_up = _Outcome(216388320, "Resident Evil Requiem", 0.11, -0.031, 2, -3)
    third = _Outcome(216388327, "Phantom Blade Zero", 0.0505, 0.022, 3, 18)
    return _Market(
        58321581,
        "The Game Awards: Game of the Year",
        [leader, runner_up, third],
        bank={str(leader.id): _cell(0.705)} if bank else None,
    )


def _by_name(market):
    return {o["name"]: o for o in _format_market_detail(market, ["kalshi"], set())["outcomes"]}


def _stored_arrows(market):
    return [o.rank_change_24h for o in market.outcomes]


# ── SHIP ────────────────────────────────────────────────────────────────────


def test_the_ladder_refuses_an_undated_rank_arrow():
    """SHIP. The row that printed ``↓5`` beside a blank LAST MOVE.

    `Resident Evil Requiem` has no banked basis at all, so #4079's guard already
    serves `None` for its move. The arrow beside it must not outlive that
    refusal.
    """
    market = _game_awards_market()
    assert _stored_arrows(market) == [5, -3, 18], (
        "PRECONDITION: the fixture stores no arrows, so this proves nothing"
    )

    row = _by_name(market)["Resident Evil Requiem"]

    assert row["probability_change_24h"] is None, (
        "PRECONDITION: the move is datable here, so this row is the wrong "
        "specimen for the undated case"
    )
    assert row["rank_change_24h"] is None, (
        "a rank arrow drawn from a per-poll delta, printed beside a 24h move we "
        f"refused to state — served {row['rank_change_24h']!r}"
    )


def test_no_row_of_the_ladder_carries_an_arrow_the_route_cannot_date():
    """SHIP. The whole board, not one row — seven of fourteen were live."""
    served = _by_name(_game_awards_market())
    assert len(served) == 3, f"the fixture board was not served whole: {served}"
    assert [o["rank_change_24h"] for o in served.values()] == [None, None, None]


def test_a_row_with_no_price_never_carries_an_arrow():
    """SHIP. `Gil Vicente FC 0 - 2 CS Marítimo` carried `rank_change_24h: -1`
    with `probability: null` — a rank move on a row with no price at all. 39
    such rows were live on production the day this was measured."""
    market = _game_awards_market()
    market.outcomes[2].current_probability = None
    market.outcomes[2].current_yes_bid = None
    market.outcomes[2].current_yes_ask = None

    row = _by_name(market)["Phantom Blade Zero"]

    assert row["probability"] is None, (
        "PRECONDITION: the fixture row still carries a price"
    )
    assert row["rank_change_24h"] is None


# ── GUARD ───────────────────────────────────────────────────────────────────


def test_a_banked_row_that_serves_a_dated_MOVE_still_serves_no_ARROW():
    """GUARD, and the one that retires the co-dating shape.

    Mutant: gate the arrow on the same per-row test `dated_movement_points`
    applies, and serve the stored integer wherever that test passes. This row
    passes it — its move is served as a real number below — and its arrow is
    STILL a delta between two polls of unknown length. A per-row price basis
    cannot date a rank claim, so the number must not ride out on it.
    """
    market = _game_awards_market()
    leader = _by_name(market)["Grand Theft Auto VI"]

    assert leader["probability_change_24h"] == pytest.approx(0.66 - 0.705), (
        "PRECONDITION: the bank did not date this row, so the mutant this test "
        "names could not have served an arrow here either"
    )
    assert leader["rank_change_24h"] is None, (
        "the arrow rode out on the PRICE's basis: a per-poll rank delta is a "
        "per-poll rank delta even where the row's price is datable"
    )


def test_the_refusal_is_null_and_never_zero():
    """GUARD. Mutant: serve `0` instead of `None`.

    `0` is reserved for a rank that MEASURED as flat. Every shipped client
    already draws nothing on either value — `OutcomeRow` gates on
    ``rankChange !== null && rankChange !== 0``, `FuturesDetailView` on
    ``if let rankChange, rankChange != 0`` — so the mutant is invisible on the
    page and destroys the only distinction the field has left.
    """
    served = _by_name(_game_awards_market()).values()
    assert all(o["rank_change_24h"] is None for o in served)
    assert not any(o["rank_change_24h"] == 0 for o in served), (
        "a refusal served as 0 makes an unmeasured day indistinguishable from a "
        "flat one"
    )


def test_the_key_is_present_and_never_omitted():
    """GUARD. Mutant: drop the key rather than null it.

    The clients test ``!== null`` and ``undefined !== null`` is true, so an
    omitted key is a different wire contract from a null one — and the iOS
    decoder is the reader that cannot be re-shipped this week (#7226).
    """
    assert all(
        "rank_change_24h" in o
        for o in _format_market_detail(_game_awards_market(), ["kalshi"], set())[
            "outcomes"
        ]
    )


def test_the_stored_column_is_untouched_by_the_refusal():
    """GUARD. Mutant: repair the column instead of the payload.

    This is a serve-time refusal on ONE payload. `/api/futures/movers` ranks on
    the stored column, `compute_futures_highlight` picks its subject with it and
    the A5/A6 sweeps retire it; a write here would move all three and is a
    different ship from the one #7299 asks for.
    """
    market = _game_awards_market()
    _format_market_detail(market, ["kalshi"], set())
    assert _stored_arrows(market) == [5, -3, 18]


# ── CONTROL ─────────────────────────────────────────────────────────────────


def test_the_ladder_keeps_every_priced_row_its_price_and_its_rank():
    """CONTROL. What the refusal may not cost — the acceptance's last bullet.

    A blanket null over the outcome dict, or a drop of the rows that carried an
    arrow, passes every assertion above and fails here.
    """
    served = _by_name(_game_awards_market())

    assert set(served) == {
        "Grand Theft Auto VI",
        "Resident Evil Requiem",
        "Phantom Blade Zero",
    }
    assert served["Grand Theft Auto VI"]["probability"] == pytest.approx(0.66)
    assert served["Resident Evil Requiem"]["probability"] == pytest.approx(0.11)
    assert served["Grand Theft Auto VI"]["probability_change_24h"] == pytest.approx(
        0.66 - 0.705
    )
    assert [served[n]["rank"] for n in ("Grand Theft Auto VI", "Resident Evil Requiem")] == [1, 2]
