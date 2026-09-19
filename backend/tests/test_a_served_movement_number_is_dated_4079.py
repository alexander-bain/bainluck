"""#4079 numeric half — the NUMBER beside the sentence is dated too.

## What #7176 left open, and why it could not close it

#7176 taught the copy layer to date its claim: a card says "up 9.5 points today"
only when a banked observation supports the amount, and loses the word
otherwise. It deliberately touched nothing else, and stated so.

What it could not reach is the NUMBER. Three serving sites hand the clients a
movement value off `probability_change_24h` — `new - previous` at WRITE time,
for a previous write of unknown age — and the clients draw it whether or not a
caption was suppressed:

* `top_outcomes[].movement` — `MovementBadge(movement: leader.movement)` on the
  Discover card, in every shipped iOS build;
* `discover_card.distribution_outcomes[].movement` — the per-row arrow;
* `/api/futures/{id}`'s `probability_change_24h` — `FuturesDetailView`'s
  `detailMovementBadge(leader.probabilityChange24h)` and every `OutcomeRow`.

That third one is Alex's phone line 21 verbatim: a green **+30.5** beside a
plotted line that had barely moved, with **-30 to -41** on the rungs below it.
The chart was the honest half of that screen.

## MEASURED, on the 935 outcomes behind page one's 80 futures cards

2026-09-19 13:5xZ, both columns computed from ONE read of those rows so that
cache churn cannot be mistaken for the change:

| | rows |
|---|---|
| carry a movement number today | **102** (59 of them at or above the phone's 1-point draw threshold) |
| …the dated basis AGREES with, within half a point | **8** |
| …corrected to the dated amount | **20**, one of them a SIGN REVERSAL |
| …no qualifying dated basis at all, so silenced | **74** |

Eight of a hundred and two. The rest were a number nothing could date.

## WHAT THIS FILE PINS, AND WHAT IT MUST NOT

Every assertion runs a REAL serializer and reads the served dict — `_score_futures`
for the card, `_format_market_detail` for the ladder — because a ban on a
producer is not a ban on a surface (the rule
`test_score_futures_serves_no_diagnostic_headline_4160` states, and #7226 is the
same lesson arriving from the client side: a server-side gate on a CAPTION left
the badge redrawing the raw field).

The controls are half the file. This change may not move:

* the stored column, which `/api/futures/movers` ranks on and
  `compute_futures_highlight` picks its subject with;
* the CARD'S SHAPE — `_has_recent_movement` decides `probability_timeline`, and
  a market that trades normally but cannot be dated must keep its format;
* the confidence bar, which asks "is this being written" and is honestly
  answered by a per-write delta;
* the wire CONTRACT — same field names, same shapes. The clients that draw these
  badges ship on the App Store's clock, so a new field would reach nobody.

    SHIP     red against the parent. This is the change.
    GUARD    green against the parent, red against a named mutant.
    CONTROL  green against both.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes.feed import _score_futures, _score_sports_mode_futures
from app.routes.futures import _format_market_detail
from app.utils.futures_market_snapshot import (
    DATED_BASIS_METADATA_KEY,
    DATED_BASIS_MIN_AGE_HOURS,
    DATED_BASIS_WINDOW_HOURS,
    dated_movement_points,
)
from app.utils.personalization import PersonalizationContext

UTC = timezone.utc

NOW = datetime(2026, 9, 19, 14, 0, tzinfo=UTC)

#: The age of the GTA specimen's own banked observation, and a basis that is
#: INSIDE the window by a comfortable margin — the boundary cases get their own
#: tests rather than riding on every fixture.
BASIS_AT = NOW - timedelta(hours=19, minutes=18)

CANONICAL_KEY = "served-movement-dated-4079"


class _Outcome:
    def __init__(self, id, name, probability, change_24h):
        self.id = id
        self.name = name
        self.external_id = f"leg-{id}"
        self.current_probability = probability
        self.probability_change_24h = change_24h
        self.opening_probability = None
        self.opening_captured_at = None
        self.rank = None
        self.rank_change_24h = None
        self.team_id = None
        self.calibration_probability = None
        self.current_american_odds = None
        self.opening_american_odds = None
        self.is_winner = None
        self.resolution_source = None
        # A readable two-sided book, so the fabricated-midpoint gate (UX-P011)
        # keeps every leg: a card whose legs were all phantom-dropped would pass
        # this whole file vacuously.
        self.current_yes_bid = max(0.01, (probability or 0.5) - 0.02)
        self.current_yes_ask = min(0.99, (probability or 0.5) + 0.02)
        self.last_updated = NOW - timedelta(minutes=6)


class _Market:
    """A real object, so the `__dict__.get(...)` reads the folds use work."""

    def __init__(self, id, name, outcomes, *, bank=None, category="entertainment"):
        self.id = id
        self.name = name
        self.source = "kalshi"
        self.external_id = f"kx-{id}"
        self.sport_id = None
        self.sport = None
        self.category = category
        self.llm_sport_category = category
        self.market_tier = 1
        self.market_type = "outright"
        self.mutually_exclusive = True
        self.description = None
        self.canonical_market_key = CANONICAL_KEY
        self.group_id = None
        self.group_type = None
        self.image_url = None
        self.image_width = None
        self.image_height = None
        self.hook_description = None
        self.hook_generated_at = None
        self.hook_leader_at_generation = None
        self.market_metadata = (
            {DATED_BASIS_METADATA_KEY: bank} if bank is not None else {}
        )
        self.curation_score_adj = 0
        self.volume_24h = 250_000
        self.updated_at = NOW
        self.commence_time = NOW - timedelta(days=1)
        self.resolution_date = NOW + timedelta(days=90)
        self.status = "open"
        self.created_at = NOW - timedelta(days=30)
        self.llm_league = None
        self.llm_gender = None
        self.llm_level = None
        self.event_concept_key = None
        self.hub_slug = None
        self.category_tags = None
        self.outcomes = outcomes


def _cell(price, at=BASIS_AT):
    """One bank cell in the sweep's own wire shape: `[price, ISO instant]`."""
    return [price, at.strftime("%Y-%m-%dT%H:%M:%SZ")]


# ── THE SPECIMEN ────────────────────────────────────────────────────────────
#
# `The Game Awards: Game of the Year`, market 58321581, read off production
# 2026-09-19 13:40Z. `Grand Theft Auto VI` stores a -2.5 point per-write delta
# and carries a banked observation of 0.705 from 2026-09-18T13:50:38Z against a
# current 0.66 — so the DAY moved -4.5 points and the card printed -2.5. The
# rungs below it store nothing the bank can date.
#
# Alex saw the same market from the other side, with the numbers of an earlier
# hour: +30.5 on the leader, -30 to -41 below it, over a nearly flat chart.
#
# THE BASIS SLIDES, AND A LATER READER MUST EXPECT THAT. It is the oldest
# observation still INSIDE the window, so as the window moves the sweep re-banks
# a newer one: re-read at 14:05Z the same rung answered 0.695 from 20:52Z, and
# -3.5 rather than -4.5. Both are the same rule applied at different minutes.
# The fixture freezes one of them — which is the point of `NOW` — so nobody
# re-measures this file against the clock and reports a defect.


def _game_awards_market(*, bank=True, market_id=58321581):
    """The specimen. `market_id` exists because of a REAL vacuity trap.

    `_score_futures` hydrates its rows through the shared `market_load`
    artifact, whose key is a digest of the candidate market IDS and nothing
    else. Two variants served under one id inside one event loop therefore get
    the FIRST one's rows — so a control that compares "banked" against
    "unbanked" while sharing an id compares a card with itself and passes
    against every mutant. Measured here before it was written around: the
    format and confidence controls below survived their mutants until the ids
    were split.
    """
    leader = _Outcome(216388319, "Grand Theft Auto VI", 0.66, -0.025)
    runner_up = _Outcome(216388320, "Resident Evil Requiem", 0.11, -0.031)
    third = _Outcome(216388327, "Phantom Blade Zero", 0.0505, 0.022)
    return _Market(
        market_id,
        "The Game Awards: Game of the Year",
        [leader, runner_up, third],
        # Only the LEADER is datable, which is the live shape: the sweep banks
        # an observation only where one qualifies, and the two rungs below have
        # none. A fixture where every row were datable could not tell a served
        # refusal from a served number.
        bank={str(leader.id): _cell(0.705)} if bank else None,
    )


# ── running the real card serializer ────────────────────────────────────────


def _mock_db(markets):
    db = AsyncMock()

    def make_result(*a, **k):
        r = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = [m.id for m in markets]
        unique = MagicMock()
        unique.all.return_value = markets
        scalars.unique.return_value = unique
        r.scalars.return_value = scalars
        r.all.return_value = []
        return r

    db.execute = AsyncMock(side_effect=make_result)
    return db


async def _served_card(market):
    """The one futures card the scorer produced, or a failure that says why."""
    with (
        patch(
            "app.routes.feed._external_curator_recall_market_ids",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.routes.feed._get_canonical_source_counts",
            new=AsyncMock(return_value={CANONICAL_KEY: 2}),
        ),
        patch(
            "app.tasks.redis_state.get_async_redis_client",
            side_effect=Exception("no redis in test"),
        ),
    ):
        items = await _score_futures(
            _mock_db([market]), NOW, None, PersonalizationContext()
        )
    futures = [i for i in items if i["type"] == "futures"]
    assert len(futures) == 1, f"the fixture card was not served: {items}"
    return futures[0]["data"]


def _row(card, name):
    for outcome in card["top_outcomes"]:
        if outcome["name"] == name:
            return outcome
    raise AssertionError(f"{name!r} is not on the card: {_names(card)}")


def _names(card):
    return [o["name"] for o in card["top_outcomes"]]


def _distribution_row(card, label):
    rows = (card.get("discover_card") or {}).get("distribution_outcomes") or []
    for row in rows:
        if row["label"] == label:
            return row
    raise AssertionError(f"{label!r} is not in the distribution: {rows}")


# ══════════════════════════════════════════════════════════════════════════
# 1. THE SHIP — the badge states the dated amount, or nothing
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_the_card_badge_states_the_DATED_amount_not_the_per_write_one():
    """The specimen: stored -2.5, banked day -4.5. The card prints -4.5.

    Dies on the parent, whose `movement` was `float(o.probability_change_24h)`.
    """
    card = await _served_card(_game_awards_market())
    assert _row(card, "Grand Theft Auto VI")["movement"] == pytest.approx(
        0.66 - 0.705
    )


@pytest.mark.asyncio
async def test_a_row_with_no_banked_observation_serves_no_number_at_all():
    """The 74-of-102 class: a real stored delta nothing can date.

    `None`, never 0.0 — a zero is the one answer that claims the day was
    MEASURED and flat. Dies on a mutant that falls back to the stored delta.
    """
    card = await _served_card(_game_awards_market())
    row = _row(card, "Resident Evil Requiem")
    assert row["movement"] is None, "a stored delta nothing can date buys nothing"


@pytest.mark.asyncio
async def test_the_distribution_row_is_dated_by_the_same_subtraction():
    """One card may not print two answers to "what did today do".

    The badge and the distribution arrow are built at different call sites off
    the same outcome, which is how they drifted in the first place.
    """
    card = await _served_card(_game_awards_market())
    assert _distribution_row(card, "Grand Theft Auto VI")["movement"] == (
        _row(card, "Grand Theft Auto VI")["movement"]
    )
    assert _distribution_row(card, "Resident Evil Requiem")["movement"] is None


@pytest.mark.asyncio
async def test_the_detail_ladder_serves_the_dated_move_too():
    """`/api/futures/{id}` — the field `FuturesDetailView` draws its badge from.

    The route this file's specimen was READ from, and the surface Alex's line 21
    is about. Served through the real `_format_market_detail`, so a fix that
    lived only in the feed cannot pass it.
    """
    market = _game_awards_market()
    detail = _format_market_detail(market, ["kalshi"], set())
    by_name = {o["name"]: o for o in detail["outcomes"]}
    assert by_name["Grand Theft Auto VI"]["probability_change_24h"] == (
        pytest.approx(0.66 - 0.705)
    )
    assert by_name["Resident Evil Requiem"]["probability_change_24h"] is None


@pytest.mark.asyncio
async def test_a_price_write_between_sweeps_moves_the_badge_to_the_new_truth():
    """The bank holds an OBSERVATION, so the subtraction re-answers itself.

    This is why the cell is `[price, instant]` and not a computed change: the
    sweep runs every ten minutes and a poll lands inside that gap. Same bank,
    a price that moved, a badge that follows it.
    """
    market = _game_awards_market()
    market.outcomes[0].current_probability = 0.60
    card = await _served_card(market)
    assert _row(card, "Grand Theft Auto VI")["movement"] == pytest.approx(
        0.60 - 0.705
    )


# ══════════════════════════════════════════════════════════════════════════
# 1b. THE SPORTS FEED IS THE SAME CARD — and it is a SEPARATE serializer
# ══════════════════════════════════════════════════════════════════════════
#
# `/sports` is served by `_score_sports_mode_futures`, a second scorer holding
# its own copy of these two sites. CERT-622's lesson is exactly this: a read
# added at one of the two, and the other silently keeps the old behaviour. A
# mutation run confirmed the gap is live rather than theoretical — reverting
# only the sports-mode pair left every Discover assertion above green.
#
# The specimen is an entertainment market and Sports mode selects on category,
# so the arithmetic is transplanted onto a championship board rather than the
# fixture being reused whole.


def _sports_market(*, bank=True, market_id=58321591):
    leader = _Outcome(216388401, "Oklahoma City Thunder", 0.66, -0.025)
    second = _Outcome(216388402, "Boston Celtics", 0.11, -0.031)
    third = _Outcome(216388403, "Denver Nuggets", 0.0505, 0.022)
    market = _Market(
        market_id,
        "NBA Championship Winner",
        [leader, second, third],
        bank={str(leader.id): _cell(0.705)} if bank else None,
        category="basketball",
    )
    return market


async def _served_sports_card(market):
    with (
        patch(
            "app.routes.feed._get_canonical_source_counts",
            new=AsyncMock(return_value={CANONICAL_KEY: 2}),
        ),
        patch(
            "app.tasks.redis_state.get_async_redis_client",
            side_effect=Exception("no redis in test"),
        ),
    ):
        items = await _score_sports_mode_futures(
            _mock_db([market]), NOW, None, PersonalizationContext()
        )
    futures = [i for i in items if i["type"] == "futures"]
    assert len(futures) == 1, f"the fixture card was not served: {items}"
    return futures[0]["data"]


@pytest.mark.asyncio
async def test_the_SPORTS_card_states_the_dated_amount_too():
    card = await _served_sports_card(_sports_market())
    assert _row(card, "Oklahoma City Thunder")["movement"] == pytest.approx(
        0.66 - 0.705
    )
    assert _row(card, "Boston Celtics")["movement"] is None


@pytest.mark.asyncio
async def test_MY_STUFF_matched_outcomes_are_dated_too():
    """`matched_outcomes` — a reader's OWN team, on the My Stuff surface.

    A fourth call site, reached only under `my_teams_only`, and therefore the
    one a Discover-only fixture leaves unguarded: a mutation run confirmed
    reverting it alone kept every other assertion in this file green.
    """
    market = _sports_market(market_id=58321593)
    market.outcomes[0].team_id = 4242
    ctx = PersonalizationContext()
    ctx.team_relations = {4242: "favorite"}
    with (
        patch(
            "app.routes.feed._external_curator_recall_market_ids",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.routes.feed._get_canonical_source_counts",
            new=AsyncMock(return_value={CANONICAL_KEY: 2}),
        ),
        patch(
            "app.tasks.redis_state.get_async_redis_client",
            side_effect=Exception("no redis in test"),
        ),
    ):
        items = await _score_futures(
            _mock_db([market]),
            NOW,
            None,
            ctx,
            my_teams_only=True,
            my_team_names=["Oklahoma City Thunder"],
            my_team_sport_categories={"Oklahoma City Thunder": {"basketball"}},
        )
    matched = [i for i in items if i["type"] == "futures"][0]["data"]["matched_outcomes"]
    assert [m["name"] for m in matched] == ["Oklahoma City Thunder"]
    assert matched[0]["movement"] == pytest.approx(0.66 - 0.705)


@pytest.mark.asyncio
async def test_the_SPORTS_distribution_row_is_dated_by_the_same_subtraction():
    card = await _served_sports_card(_sports_market(market_id=58321592))
    assert _distribution_row(card, "Oklahoma City Thunder")["movement"] == (
        pytest.approx(0.66 - 0.705)
    )
    assert _distribution_row(card, "Boston Celtics")["movement"] is None


# ══════════════════════════════════════════════════════════════════════════
# 2. THE REFUSALS — every one of them is the same refusal
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "bank, why",
    [
        (None, "no bank at all"),
        ({}, "an empty bank"),
        ({"216388319": None}, "a null cell"),
        ({"216388319": [0.705]}, "a cell of the wrong length"),
        ({"216388319": ["not-a-price", "2026-09-18T13:50:38Z"]}, "a junk price"),
        ({"216388319": [0.705, "yesterday-ish"]}, "an unparseable instant"),
        ({"216388319": [0.705, None]}, "a missing instant"),
        ({"216388320": _cell(0.2)}, "a bank for a DIFFERENT outcome"),
    ],
)
def test_an_unusable_bank_buys_no_number(bank, why):
    market = _game_awards_market(bank=False)
    market.market_metadata = (
        {DATED_BASIS_METADATA_KEY: bank} if bank is not None else {}
    )
    assert (
        dated_movement_points(market, 216388319, 0.66, -0.025, now=NOW) is None
    ), why


def test_a_basis_younger_than_the_minimum_cannot_date_a_day():
    """A twenty-minute-old price is not yesterday. The producer refuses to bank
    one; the reader refuses to read one, so a bank written by anything else
    cannot smuggle a fresh basis onto a card."""
    fresh = _Market(1, "m", [], bank={"7": _cell(0.5, NOW - timedelta(minutes=20))})
    assert dated_movement_points(fresh, 7, 0.66, -0.025, now=NOW) is None
    aged = _Market(
        1,
        "m",
        [],
        bank={"7": _cell(0.5, NOW - timedelta(hours=DATED_BASIS_MIN_AGE_HOURS, minutes=1))},
    )
    assert dated_movement_points(aged, 7, 0.66, -0.025, now=NOW) == pytest.approx(
        0.16
    )


def test_an_upper_age_bound_makes_a_STOPPED_SWEEP_fail_closed():
    """Nothing has to DETECT the outage. A bank nobody refreshes only ever gets
    older, so it leaves the window by itself and the badges go quiet."""
    stale = _Market(
        1,
        "m",
        [],
        bank={"7": _cell(0.5, NOW - timedelta(hours=DATED_BASIS_WINDOW_HOURS, minutes=1))},
    )
    assert dated_movement_points(stale, 7, 0.66, -0.025, now=NOW) is None


def test_the_bank_never_promotes_a_row_the_writers_left_silent():
    """A real, well-evidenced day with a NULL stored delta stays silent.

    #7176's `US bank failure` specimen — a -9.0 point dated move — and the
    reason is unchanged here: selecting what a surface TALKS ABOUT is a ranking
    policy, and this decides only what may be said about what is already shown.
    """
    market = _Market(1, "m", [], bank={"7": _cell(0.79)})
    assert dated_movement_points(market, 7, 0.70, None, now=NOW) is None
    assert dated_movement_points(market, 7, 0.70, 0.0, now=NOW) is None


def test_a_market_with_no_metadata_column_at_all_is_excluded_not_crashed():
    """A projection that stopped loading `market_metadata` degrades to silence.

    Gotcha #42: an exception here empties the whole futures pool rather than
    dropping one badge.
    """

    class _Slotted:
        __slots__ = ("id",)

        def __init__(self):
            self.id = 1

    assert dated_movement_points(_Slotted(), 7, 0.66, -0.025, now=NOW) is None
    bare = _Market(1, "m", [])
    bare.market_metadata = None
    assert dated_movement_points(bare, 7, 0.66, -0.025, now=NOW) is None


# ══════════════════════════════════════════════════════════════════════════
# 3. THE CONTROLS — what a truth fix is not allowed to move
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_the_stored_column_is_left_on_the_row_for_its_other_readers():
    """`/api/futures/movers` ranks on it and `compute_futures_highlight` picks
    its subject with it. Serving a different number may not rewrite either."""
    market = _game_awards_market()
    await _served_card(market)
    assert [o.probability_change_24h for o in market.outcomes] == [
        -0.025,
        -0.031,
        0.022,
    ]


@pytest.mark.asyncio
async def test_a_card_that_cannot_date_its_day_keeps_its_SHAPE():
    """The archetype's format choice is a liveness question, not a dated claim.

    Both cards below trade identically — same stored deltas, same prices — and
    differ only in whether an observation was banked. A `suggested_format` that
    moved between them would mean this truth fix had quietly become a layout
    change. Dies on a mutant that lets `_has_recent_movement` read the served
    `movement`.
    """
    dated = await _served_card(_game_awards_market(bank=True))
    undatable = await _served_card(
        _game_awards_market(bank=False, market_id=58321582)
    )
    assert undatable["discover_card"]["suggested_format"] == (
        dated["discover_card"]["suggested_format"]
    )
    assert undatable["discover_card"]["reasons"] == dated["discover_card"]["reasons"]


@pytest.mark.asyncio
async def test_a_silenced_badge_does_not_dim_the_confidence_bar():
    """"Is this market being written" is honestly answered by a per-write delta.

    The bar and the badge answer different questions, and #490's glyph may not
    fall off a card because nothing could date its day.
    """
    dated = await _served_card(_game_awards_market(bank=True))
    undatable = await _served_card(
        _game_awards_market(bank=False, market_id=58321583)
    )
    assert undatable.get("confidence_tier") == dated.get("confidence_tier")
    assert undatable.get("confidence_score") == dated.get("confidence_score")
    assert undatable.get("confidence_signals") == dated.get("confidence_signals")


@pytest.mark.asyncio
async def test_the_wire_contract_is_unchanged_so_shipped_CLIENTS_still_read_it():
    """Same field, same name, a corrected value.

    The clients that draw these badges ship on the App Store's clock: a new
    field would reach nobody for weeks, which is exactly how #7226 happened. So
    the guard is that `movement` is still the key on the card row, and
    `probability_change_24h` still the key on the detail row — and that the
    internal liveness key never reaches the wire.
    """
    card = await _served_card(_game_awards_market())
    assert "movement" in _row(card, "Grand Theft Auto VI")
    assert "movement" in _distribution_row(card, "Grand Theft Auto VI")
    for row in card["discover_card"]["distribution_outcomes"]:
        assert "movement_stored" not in row
    detail = _format_market_detail(_game_awards_market(), ["kalshi"], set())
    assert "probability_change_24h" in detail["outcomes"][0]


def test_the_number_is_on_the_STORED_scale_not_a_display_scaled_one():
    """The card normalizes its probabilities for display (gotcha #23/#58) and
    the banked basis is a raw stored price, so the subtraction has to happen
    before the scale. Two rows whose raw prices sum past 100% keep their raw
    moves."""
    market = _Market(1, "m", [], bank={"7": _cell(0.40), "8": _cell(0.30)})
    assert dated_movement_points(market, 7, 0.60, 0.05, now=NOW) == pytest.approx(0.20)
    assert dated_movement_points(market, 8, 0.55, 0.05, now=NOW) == pytest.approx(0.25)


def test_the_caption_and_the_badge_are_ONE_subtraction():
    """`_dated_movement_change` is this helper plus the card floor.

    Pinned by import identity rather than by re-deriving the arithmetic here: a
    second copy of the subtraction is precisely how a card came to say one thing
    in prose and print another in a chip.
    """
    import inspect

    from app.routes import feed

    source = inspect.getsource(feed._dated_movement_change)
    assert "dated_movement_points(" in source, (
        "the caption must be the shared subtraction plus the floor, not its own "
        "copy of the window, the bank read and the age test"
    )
