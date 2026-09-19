"""#4079 numeric half — the NUMBER beside the sentence is dated too.

## What #7176 left open, and why it could not close it

#7176 taught the copy layer to date its claim: a card says "up 9.5 points today"
only when a banked observation supports the amount, and loses the word
otherwise. It deliberately touched nothing else, and stated so.

What it could not reach is the NUMBER. Serving sites hand the clients a movement
value off `probability_change_24h` — `new - previous` at WRITE time, for a
previous write of unknown age — and the clients draw it whether or not a caption
was suppressed:

* `top_outcomes[].movement` — `MovementBadge(movement: leader.movement)` on the
  Discover card, in every shipped iOS build;
* `discover_card.distribution_outcomes[].movement` — the per-row arrow;
* `matched_outcomes[].movement` — the same badge on My Stuff;
* `/api/futures/{id}`'s `probability_change_24h` — `FuturesDetailView`'s
  `detailMovementBadge(leader.probabilityChange24h)` and every `OutcomeRow`.

That last one is Alex's phone line 21 verbatim: a green **+30.5** beside a
plotted line that had barely moved, with **-30 to -41** on the rungs below it.
The chart was the honest half of that screen.

## THE DETAIL LADDER, AND WHY IT IS BACK

It was cut from `e47d22a0d` when `81083c5cc` landed six hours earlier: the
sibling half of this ship (`test_detail_dates_its_movement_claim_4079.py`) adds
`price_changed_at` to the same dict and pinned, deliberately, that the delta
beside it was served exactly as before. Two answers to one field is the overlap
the commissioning directive forbade, so the withdrawal was right on the day.

Codex ruled it back on 2026-09-19 16:00Z, discover as sole implementation owner
of the complete numeric ship, and answered the coverage argument that motivated
the cut: the bank dates **14.22% of ladder rows** (2,286 of 16,074), so most of
the column goes quiet — but the other 85.78% are rows serving a per-write delta
under the label "24h", and an unbanked row returns null rather than keeping a
number nobody measured. The two halves are complementary and both ship:
`price_changed_at` says WHEN (79.35% of rows), this says HOW MUCH (14.22%), and
the sibling's pin moved from the serialized value to storage/ranking invariance,
which is what it was really protecting. That amendment is written out in the
sibling file's `TestNothingElseMoved` docstring, not left to be discovered.

## THE SCALE RULING (codex, same directive) — WHEN THERE IS NO ANSWER AT ALL

`dated_movement_points` is raw − raw, and the detail ladder prints raw prices,
so the two agree. A Discover card does not always: `_feed_display_scale` divides
every VISIBLE percent on an independent-binary card by the all-outcome sum, and
the bank holds a PRICE, so the raw move is a true statement about a quantity the
reader is not being shown.

MEASURED on production page one 2026-09-19: of **18** movement-carrying cards,
**2 are scaled and both drew a badge** — `58776433` printed **59%** (raw 0.505)
beside **+12.5**, where the percent on screen had moved **+14.6**.

🔴 The +14.6 is NOT the repair and is rejected by name. Dividing the delta (or
the banked price) by TODAY's denominator asserts a historic DISPLAYED percent
nobody observed — the divisor moves whenever any leg moves — and no column
stores one. So on a normalized card the four scaled readers serve `null`: there
is no supported claim about the change in the number on screen. The price, the
card, its rank and its score are untouched. `matched_outcomes` serves a RAW
probability and therefore keeps its raw number; that asymmetry is the rule, not
an oversight, and has its own control below.

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

Every assertion runs a REAL serializer and reads the served dict —
`_score_futures` for Discover and My Stuff, `_score_sports_mode_futures` for
`/sports`, `_format_market_detail` for the ladder — because a ban on a producer
is not a ban on a surface (the rule
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
BASIS_AGE = timedelta(hours=19, minutes=18)

BASIS_AT = NOW - BASIS_AGE


def _real_clock_basis() -> datetime:
    """A basis aged off the REAL clock, for call sites that read the real clock.

    ⚠️ `BASIS_AT` IS AN ABSOLUTE INSTANT AND MUST NEVER FEED A REAL-CLOCK CALL
    SITE. Every test that injects `now=NOW` is correctly frozen; but
    `_format_market_detail` takes no `now` and reads `datetime.now(UTC)`
    itself, so pairing it with `BASIS_AT` dates the basis against a clock that
    keeps moving. `DATED_BASIS_WINDOW_HOURS` is 24 and `BASIS_AT` is
    2026-09-18T18:42:00Z, so those tests began failing the moment real time
    passed 2026-09-19T18:42:00Z — 24.0h — and, because the anchor recedes for
    good, they would have stayed red for ever. That is gotcha #44 in its exact
    form: offset FIRST, then pin. An anchor that is a fixed DATE is only fixed
    until tomorrow.

    The specimen's NUMBERS (0.705 → 0.66, the -4.5 point day) stay frozen — the
    file's docstring is right that they must be. It is the INSTANT that has to
    move, and only for the callers that read the clock themselves.

    Worth knowing when this bit: it also made
    `test_the_ladder_withholds_the_amount_once_the_SQUEEZE_moves_the_column`
    pass VACUOUSLY. That test asserts the amount is withheld, and a basis
    outside the window withholds it for a reason that has nothing to do with
    the squeeze it is named for.
    """
    return datetime.now(UTC) - BASIS_AGE

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


def _game_awards_market(*, bank=True, market_id=58321581, basis_at=BASIS_AT):
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
        bank={str(leader.id): _cell(0.705, basis_at)} if bank else None,
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


async def _served_item(market):
    """The whole feed ITEM, not just its `data` — `score` lives on the item, and
    the scale ruling's invariance control is about the score."""
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
    return futures[0]


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


def test_the_detail_ladder_serves_the_dated_move_too():
    """N3. `/api/futures/{id}` — the field `FuturesDetailView` draws its badge
    from, and the route this file's specimen was READ from.

    Alex's line 21 is about this surface. Served through the real
    `_format_market_detail`, so a fix that lived only in the feed cannot pass
    it, and a withdrawal of it cannot pass it either.
    """
    # `_format_market_detail` reads the real clock, so the basis is aged off it.
    market = _game_awards_market(basis_at=_real_clock_basis())
    detail = _format_market_detail(market, ["kalshi"], set())
    by_name = {o["name"]: o for o in detail["outcomes"]}
    assert by_name["Grand Theft Auto VI"]["probability_change_24h"] == (
        pytest.approx(0.66 - 0.705)
    )
    assert by_name["Resident Evil Requiem"]["probability_change_24h"] is None


def test_the_real_clock_basis_sits_inside_the_window_at_every_hour():
    """The guard for the failure that took this file red at 2026-09-19T18:42Z.

    `BASIS_AT` is an absolute instant and `_format_market_detail` reads the
    real clock, so the pair was only valid for the 24 hours after the specimen
    was captured; at 24.0h exactly the two detail assertions flipped to `None`
    and would have stayed there permanently.

    This asserts the property the detail tests actually depend on — that the
    real-clock basis is strictly inside the dating window, with margin on both
    sides — rather than re-asserting the arithmetic. It holds at every hour of
    every day, which is the whole point.
    """
    age_hours = (datetime.now(UTC) - _real_clock_basis()).total_seconds() / 3600

    assert DATED_BASIS_MIN_AGE_HOURS < age_hours < DATED_BASIS_WINDOW_HOURS, (
        f"the real-clock basis is {age_hours:.2f}h old, outside the "
        f"{DATED_BASIS_MIN_AGE_HOURS}-{DATED_BASIS_WINDOW_HOURS}h window"
    )
    # Margin, so a slow shard cannot drift the basis out mid-run.
    assert age_hours < DATED_BASIS_WINDOW_HOURS - 4


def test_no_real_clock_call_site_is_dated_off_the_absolute_anchor():
    """`BASIS_AT` may only reach callers that are handed a frozen `now`.

    Written as source inspection because the failure mode is silent: pairing
    the absolute anchor with a real-clock caller does not raise, it just
    withholds the number — which reads as a correct refusal and, in the squeeze
    test's case, as a PASS.

    Parsed with `ast`, not a regex: a non-greedy `\\(...\\)` stops at the first
    close-paren and truncates the very nested call this is looking for.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(inspect.getmodule(_real_clock_basis)))

    def _name(node):
        return getattr(node.func, "id", None) if isinstance(node, ast.Call) else None

    checked = 0
    for node in ast.walk(tree):
        if _name(node) != "_format_market_detail" or not node.args:
            continue
        built_inline = node.args[0]
        if _name(built_inline) != "_game_awards_market":
            continue  # built on its own line above; that call is checked below
        checked += 1
        assert any(
            kw.arg == "basis_at" and _name(kw.value) == "_real_clock_basis"
            for kw in built_inline.keywords
        ), f"a real-clock call site is dated off the frozen anchor (line {node.lineno})"

    # Also cover the form where the market is built on a preceding line: any
    # `_game_awards_market(basis_at=...)` in the module must use the helper.
    for node in ast.walk(tree):
        if _name(node) != "_game_awards_market":
            continue
        for kw in node.keywords:
            if kw.arg == "basis_at":
                checked += 1
                assert _name(kw.value) == "_real_clock_basis", (
                    f"`basis_at` on line {node.lineno} is not the real-clock helper"
                )

    assert checked >= 6, (
        f"the inspection matched only {checked} call sites, so it is not "
        "reading this module — the guard would pass on a reverted fix"
    )


def test_the_ladder_is_dated_RAW_because_the_ladder_PRINTS_raw():
    """The scale ruling's other half, and the reason the ladder is not nulled.

    The detail route's prices are the stored ones on every board the squeeze
    does not fire on, so raw − raw is like-with-like and the amount stands. The
    fixture's three legs sum to 0.8205, far under the squeeze band, so this is
    that population — and the served price is asserted beside the move, because
    "the amount is raw" is only true while the price beside it is.
    """
    detail = _format_market_detail(
        _game_awards_market(basis_at=_real_clock_basis()), ["kalshi"], set()
    )
    gta = {o["name"]: o for o in detail["outcomes"]}["Grand Theft Auto VI"]
    assert gta["probability"] == pytest.approx(0.66)
    assert gta["probability_change_24h"] == pytest.approx(0.66 - 0.705)


def test_the_ladder_withholds_the_amount_once_the_SQUEEZE_moves_the_column():
    """A squeezed board prints a divided percent, so the raw move may not stand
    beside it — the same rule, and the same call, as the openings one line up.

    `normalize_display_probs` divides every printed `probability` by the field
    sum; `_withhold_openings` already fires on its measured return for exactly
    this reason (#5835: two columns, two scales, and the reader invited to
    subtract). The dated amount is the third column with that problem.

    The fixture is the specimen's legs re-priced into the squeeze band (0.66 +
    0.45 + 0.30 = 1.41, mutually exclusive) so the ONLY difference from the test
    above is the divisor. Its control is that test: blanket-nulling the ladder
    fails there.
    """
    # Real-clock basis, so the withholding this test asserts can only be the
    # SQUEEZE. Dated off `BASIS_AT` the amount is withheld for staleness and the
    # test passes without exercising the divisor at all.
    market = _game_awards_market(basis_at=_real_clock_basis())
    market.outcomes[1].current_probability = 0.45
    market.outcomes[2].current_probability = 0.30
    detail = _format_market_detail(market, ["kalshi"], set())
    by_name = {o["name"]: o for o in detail["outcomes"]}
    gta = by_name["Grand Theft Auto VI"]

    assert gta["probability"] < 0.66, (
        "PRECONDITION: the fixture did not squeeze, so this proves nothing — "
        f"served {gta['probability']}"
    )
    assert gta["probability_change_24h"] is None, (
        "a raw -4.5 point move printed beside a percent divided by 1.41"
    )
    # Present and null, never omitted: the clients test `!== null`.
    assert all("probability_change_24h" in o for o in detail["outcomes"])
    # And the row's own stored column is untouched by the refusal.
    assert market.outcomes[0].probability_change_24h == -0.025


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
    detail = _format_market_detail(
        _game_awards_market(basis_at=_real_clock_basis()), ["kalshi"], set()
    )
    assert "probability_change_24h" in detail["outcomes"][0]


def test_the_number_is_on_the_STORED_scale_not_a_display_scaled_one():
    """The HELPER is raw − raw, whatever its callers go on to do.

    The banked basis is a raw stored price, so the subtraction happens on that
    scale and nowhere else. A caller whose surface prints a DIVIDED percent does
    not get a divided move out of here — it gets no move at all, which is the
    serving decision pinned in the normalized-card block below, taken at the
    call site where the divisor is known.
    """
    market = _Market(1, "m", [], bank={"7": _cell(0.40), "8": _cell(0.30)})
    assert dated_movement_points(market, 7, 0.60, 0.05, now=NOW) == pytest.approx(0.20)
    assert dated_movement_points(market, 8, 0.55, 0.05, now=NOW) == pytest.approx(0.25)


# ══════════════════════════════════════════════════════════════════════════
# 4. THE SCALE RULING — a normalized card has no supported amount to state
# ══════════════════════════════════════════════════════════════════════════
#
# `_feed_display_scale` divides every VISIBLE percent on an independent-binary
# card by the all-outcome sum. The bank holds a raw PRICE, so raw − raw is a
# true number about a quantity the card is not showing, and the display − display
# alternative divides a historic price by TODAY's denominator — a percentage
# nobody observed. Codex ruled 2026-09-19: suppress the claim on the readers the
# divisor reaches, and on nothing else.
#
# THE FIXTURE MOVES ONE THING. Same specimen, same bank, same stored deltas; the
# two rungs below the leader are re-priced so the field sums to 1.41 instead of
# 0.8205. Every dated assertion in section 1 runs on the unsqueezed original and
# is therefore the control: a mutant that nulls `movement` unconditionally, or
# that drops the scale argument and always dates, fails one side or the other.


def _normalized_market(*, market_id, sports=False):
    """The specimen priced into `_feed_display_scale`'s band.

    0.66 + 0.45 + 0.30 = 1.41 — above the 3-outcome 1.05 threshold and below the
    2.0 ladder cutoff, so the divisor is 1.41 and every printed percent moves.
    Distinct ids per variant: `_score_futures` hydrates through the shared
    `market_load` artifact keyed on the candidate-id digest ALONE, so two
    variants under one id inside one event loop compare a card with itself.
    """
    market = (_sports_market if sports else _game_awards_market)(market_id=market_id)
    market.outcomes[1].current_probability = 0.45
    market.outcomes[2].current_probability = 0.30
    return market


def _assert_card_is_normalized(card, leader_name, raw_leader=0.66):
    printed = _row(card, leader_name)["probability"]
    assert printed is not None and printed < raw_leader - 1e-6, (
        "PRECONDITION: the fixture was served on the RAW basis, so nothing "
        f"below is evidence about a normalized card — printed {printed}"
    )
    return printed


@pytest.mark.asyncio
async def test_a_NORMALIZED_card_states_no_amount_on_either_feed_reader():
    """N1 + N2. The badge and the distribution arrow both go quiet.

    Both readers of ONE card must agree — a card printing 47% with a +12.5 chip
    beside a distribution row printing nothing is the disagreement this rule
    exists to prevent, not a partial fix.
    """
    card = await _served_card(_normalized_market(market_id=58321601))
    _assert_card_is_normalized(card, "Grand Theft Auto VI")
    assert _row(card, "Grand Theft Auto VI")["movement"] is None
    assert _distribution_row(card, "Grand Theft Auto VI")["movement"] is None


@pytest.mark.asyncio
async def test_a_NORMALIZED_card_keeps_its_price_its_rank_and_its_score():
    """The claim is narrowed; the card is not. Measured against the same card
    served with the bank removed, so the only variable is whether an amount
    could have been stated."""
    with_bank_item = await _served_item(_normalized_market(market_id=58321602))
    without = _normalized_market(market_id=58321603)
    without.market_metadata = {}
    without_bank_item = await _served_item(without)
    with_bank, without_bank = with_bank_item["data"], without_bank_item["data"]

    assert with_bank_item["score"] == without_bank_item["score"]
    assert _names(with_bank) == _names(without_bank)
    assert _row(with_bank, "Grand Theft Auto VI")["probability"] == (
        _row(without_bank, "Grand Theft Auto VI")["probability"]
    )
    assert with_bank["discover_card"]["suggested_format"] == (
        without_bank["discover_card"]["suggested_format"]
    )


@pytest.mark.asyncio
async def test_the_NORMALIZED_sports_card_is_the_same_refusal():
    """N4, the twin serializer. `_score_sports_mode_futures` holds its own copy
    of both sites; CERT-622's lesson is that a rule added to one of them leaves
    the other shipping the old number."""
    card = await _served_sports_card(_normalized_market(market_id=58321604, sports=True))
    _assert_card_is_normalized(card, "Oklahoma City Thunder")
    assert _row(card, "Oklahoma City Thunder")["movement"] is None
    assert _distribution_row(card, "Oklahoma City Thunder")["movement"] is None


@pytest.mark.asyncio
async def test_MY_STUFF_keeps_its_number_on_a_normalized_card():
    """🔴 THE ASYMMETRY IS THE RULE. `matched_outcomes` serves the RAW
    `current_probability`, unscaled, on every card — so raw beside raw is
    like-with-like there and the amount is supported exactly where the four
    scaled readers give it up.

    Without this, "null when normalized" reads as a card-level rule and the next
    sweep deletes a true claim. Dies on a mutant that routes this site through
    the scale test.
    """
    market = _normalized_market(market_id=58321605, sports=True)
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
    data = [i for i in items if i["type"] == "futures"][0]["data"]
    # The card's own readers are silent…
    assert _row(data, "Oklahoma City Thunder")["movement"] is None
    matched = data["matched_outcomes"]
    assert [m["name"] for m in matched] == ["Oklahoma City Thunder"]
    # …and this one is not, because its price is the raw one.
    assert matched[0]["probability"] == pytest.approx(0.66)
    assert matched[0]["movement"] == pytest.approx(0.66 - 0.705)


def test_the_scale_test_reads_the_cards_OWN_divisor_not_a_second_threshold():
    """Codex: "use the actual existing normalization decision, not a new
    independent threshold."

    A private copy of the 1.05/2.0 band here would be free to drift from
    `_feed_display_scale`, and the drift would be invisible: both would still
    null SOME cards. Pinned by reading the helper's source for the parameter it
    is handed, the way the caption/badge identity above is pinned.
    """
    import inspect
    import re

    from app.routes import feed

    source = inspect.getsource(feed._dated_movement_on_card_scale)
    assert "scale != 1.0" in source
    for forbidden in ("1.05", "2.0", "current_probability for"):
        assert forbidden not in source, (
            f"{forbidden!r} is a second copy of `_feed_display_scale`'s band"
        )

    # Both scorers, both of their printed-row sites, each handed `_display_scale`
    # — the variable `_feed_display_scale` wrote — and not a locally recomputed
    # one. The counts are exact so a site that quietly reverts to the bare
    # subtraction is a failure rather than a silent survivor.
    call = re.compile(r"_dated_movement_on_card_scale\(\s*market,\s*o,\s*_display_scale,\s*now\s*\)")
    for site, bare_calls in (
        # `_score_futures` keeps exactly one bare call: `matched_outcomes`,
        # whose served probability is raw. See its comment.
        (feed._score_futures, 1),
        (feed._score_sports_mode_futures, 0),
    ):
        body = inspect.getsource(site)
        assert len(call.findall(body)) == 2, (
            f"{site.__name__}: expected both printed-row sites on the scale test"
        )
        assert body.count("dated_movement_points(") == bare_calls, (
            f"{site.__name__}: unexpected bare `dated_movement_points` call sites"
        )


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
