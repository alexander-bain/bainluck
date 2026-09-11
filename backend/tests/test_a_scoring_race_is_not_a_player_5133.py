"""#5133 defect A — a scoring race is a team market, and stops being served as a player.

WHAT A READER SAW, PHOTOGRAPHED. `https://bainluck.com/events/14780145` (New
Orleans vs Detroit) at 390px on 2026-09-11, inside the **Player Props** section,
between "PASSING COMPLETIONS" and Jahmyr Gibbs's Rushing + Receiving Yards
ladder:

    RACE TO 14 POINTS
      Detroit reaches 14 points first          60%
      New Orleans reaches 14 points first      40%
      Neither team reaches 14 points           13%
    PASSING COMPLETIONS            ▸ More props (16)
    RACE TO 10 POINTS
      Detroit reaches 10 points first          50%
      …

Six of them per NFL game — "Race to 7/10/14/21/28/35 Points" — each rendered as
a PLAYER by `playerPropsGrouping`, with the group name "Race to 14" sitting in
the same list as "Jahmyr Gibbs" and "Amon-Ra St. Brown". They reached
`props_script` too, so THE SCRIPT printed the prop mark "Detroit reaches 14
points first".

THE CAUSE. Kalshi names these "New Orleans vs Detroit: Race to 14 Points"
(`KXNFLRACE-26SEP09NESEA-14`). `_PLAYER_PROP_RE` matches the bare word "Points",
and `_is_team_stat_market` is False because the text after the colon is not a
LONE stat word — so `_classify_game_market` fell to its "player props without
over/under" branch and returned `player_prop`. The `player_prop` branch of
`_build_game_markets` then appends EVERY outcome unconditionally.

MEASURED, production, 2026-09-11, 11 NFL events (the 9/10–9/15 slate):

    total player_props = 2,543   no-colon rows = 174
      153  "…: Race to {7,10,14,21,28,35} Points"    <- this ship
       19  "…: Most Receiving/Rushing Yards"          <- NOT this ship, see below
        2  "… Passing Yards O/U 249.5"                <- NOT this ship

    futures_markets ILIKE '%race to%'  =  94 rows, all Kalshi, all NFL.

THE FIX IS AT THE MARKET LEVEL, NOT THE OUTCOME LEVEL, AND THAT IS THE POINT.
#5133 proposed "assert an outcome with no player component never lands in
`player_props`". That rule would be wrong: the `Most Receiving Yards` outcomes
are a BARE PLAYER NAME — "Rashid Shaheed", "Drake Maye" — with no colon and no
digits, so an outcome-shape rule drops 19 real props with the 153 junk ones.
What is wrong here is the MARKET's type, so that is where it is fixed, and
`TestNothingElseMoves` holds the bare-name rows in `player_props` to prove the
distinction is load-bearing rather than incidental.

TWO PLACES DECIDE, SO TWO PLACES ARE GUARDED. `_build_game_markets` asks the same
"does this name carry a stat word" question twice — once through
`_classify_game_market`, and again in the `else` rescue that pulls player props
out of `other`. Fixing only the classifier moves a race to `scoring_race`, drops
it into the `else`, and the rescue puts it straight back, because the name still
matches `_PLAYER_PROP_RE` and is still not a lone-stat-word team market.
`TestTheRescueBranchDoesNotPutItBack` is the arm that fails on a
classifier-only fix.

AND THE PROJECTION POOL IS THE #3948 TRAP. A race used to wear `player_prop`,
which `_PM_NON_GAME_TOTAL_SCOPES` already refuses the game total. Moving it to a
label this pass treats as quantity-neutral (`other` defers to the outcome names)
would have HANDED the projection "Detroit reaches 14 points first", out of which
`extract_spread_threshold` can read a 14. The outcome pass happens to refuse it
today only because the same "Points" substring that caused this bug also makes
each outcome classify `player_prop` — which is precisely the accident #3948 says
not to leave the answer resting on. So `scoring_race` is dropped at the MARKET
level, like a period is: it prices the total and the margin equally little.

RED-FIRST. On the parent commit `63f9fac9`, `TestARaceIsNotAPlayerProp`,
`TestTheEndpointStopsServingRacesAsProps`, `TestTheRescueBranchDoesNotPutItBack`
and `TestARaceNeverPricesTheProjection` all fail; `TestNothingElseMoves` and
`TestTheRuleIsNarrowerThanTheWords` pass on both sides, which is what makes them
a control.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes.events import (
    _PM_MARKET_PRICES_NEITHER_ARM,
    _PM_NON_GAME_TOTAL_SCOPES,
    _PM_PERIOD_SCOPES,
    _classify_game_market,
    _game_markets_cache,
    _is_scoring_race_market,
    get_game_markets,
)

#: Verbatim from `GET /api/events/14780145/game-markets`, 2026-09-11 09:52Z.
#: Three outcomes per race, and the "Neither" leg is the one that can never
#: belong to a person under any reading.
PRODUCTION_RACE_ROWS = [
    ("New Orleans vs Detroit: Race to 14 Points", "Detroit reaches 14 points first", 0.56),
    ("New Orleans vs Detroit: Race to 14 Points", "New Orleans reaches 14 points first", 0.43),
    ("New Orleans vs Detroit: Race to 14 Points", "Neither team reaches 14 points", 0.125),
    ("New Orleans vs Detroit: Race to 10 Points", "Detroit reaches 10 points first", 0.5),
    ("New Orleans vs Detroit: Race to 10 Points", "New Orleans reaches 10 points first", 0.5),
    ("New Orleans vs Detroit: Race to 10 Points", "Neither team reaches 10 points", 0.08),
    ("New Orleans vs Detroit: Race to 21 Points", "Detroit reaches 21 points first", 0.495),
    ("New Orleans vs Detroit: Race to 21 Points", "Neither team reaches 21 points", 0.25),
]

#: The six families Kalshi ships per NFL game, as market names.
PRODUCTION_RACE_MARKETS = [
    f"New England vs Seattle: Race to {n} Points" for n in (7, 10, 14, 21, 28, 35)
]

#: Verbatim from `GET /api/events/14780138/game-markets` — a REAL player prop
#: whose outcome is a bare name. It has no colon and no digits and must stay.
PRODUCTION_BARE_NAME_ROWS = [
    ("New England vs Seattle: Most Receiving Yards", "Nick Kallerup", 0.37),
    ("New England vs Seattle: Most Receiving Yards", "Montorie Foster Jr.", 0.37),
    ("New England vs Seattle: Most Rushing Yards", "Drake Maye", 0.11),
    ("New England vs Seattle: Most Rushing Yards", "Rhamondre Stevenson", 0.24),
]


def _make_result(scalar=None, rows=None, all_rows=None):
    rows = rows or []
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value.all.return_value = rows
    result.all.return_value = all_rows if all_rows is not None else []
    return result


def _make_event(*, id=14780145):
    event = MagicMock()
    event.id = id
    event.home_team_name = "Detroit Lions"
    event.away_team_name = "New Orleans Saints"
    event.status = "scheduled"
    # None on purpose: roster enrichment is a separate query path, and this test
    # is about which section a market lands in.
    event.sport_id = None
    event.sport = MagicMock()
    event.sport.key = "americanfootball_nfl"
    event.commence_time = datetime(2026, 9, 14, 17, 0, tzinfo=timezone.utc)
    event.home_score = None
    event.away_score = None
    event.period = None
    event.game_clock = None
    event.box_score_data = None
    return event


def _make_market(*, id, name, event_id, source="kalshi"):
    market = MagicMock()
    market.id = id
    market.name = name
    market.external_id = f"KXNFLRACE-26SEP14NODET-{id}"
    market.event_id = event_id
    market.category = "game_prop"
    market.status = "open"
    market.source = source
    market.sport_id = None
    market.llm_sport_category = "football"
    market.commence_time = datetime(2026, 9, 14, 17, 0, tzinfo=timezone.utc)
    market.group_id = None
    market.group_type = None
    return market


def _make_outcome(*, id, market_id, name, probability):
    outcome = MagicMock()
    outcome.id = id
    outcome.market_id = market_id
    outcome.name = name
    outcome.current_probability = probability
    outcome.opening_probability = None
    outcome.resolution_source = None
    outcome.is_winner = None
    return outcome


def _db_for(event, markets, outcomes):
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _make_result(scalar=event),
            # #2693 `folded_event_ids` — POSITIONAL contract with the query order.
            _make_result(rows=[]),
            _make_result(rows=markets),
            _make_result(all_rows=[]),  # polymarket parent groups
            _make_result(rows=[]),  # unlinked fallback
            _make_result(rows=outcomes),
            # #4970 — `load_latest_observed_at`, the newest priced observation per
            # outcome. Positional contract, so it appears even when empty.
            _make_result(all_rows=[]),
        ]
    )
    return db


def _payload_for(rows, event=None):
    """Build the endpoint response for `[(market_name, outcome_name, prob), ...]`.

    One market per DISTINCT market name, so a three-outcome race arrives as one
    market with three outcomes — the shape the serializer actually sees.
    """
    event = event or _make_event()
    markets, outcomes, by_name = [], [], {}
    for i, (name, outcome_name, prob) in enumerate(rows, start=1):
        if name not in by_name:
            mid = 1000 + len(by_name) + 1
            by_name[name] = mid
            markets.append(_make_market(id=mid, name=name, event_id=event.id))
        outcomes.append(
            _make_outcome(
                id=2000 + i, market_id=by_name[name], name=outcome_name, probability=prob
            )
        )
    return get_game_markets(event.id, _db_for(event, markets, outcomes))


@pytest.fixture(autouse=True)
def clear_game_markets_cache():
    _game_markets_cache.clear()
    yield
    _game_markets_cache.clear()


def _names(rows):
    return [r.get("outcome_name") for r in rows]


# ------------------------------------------------------------- the label --


class TestARaceIsNotAPlayerProp:
    @pytest.mark.parametrize("name", PRODUCTION_RACE_MARKETS)
    def test_every_production_race_family_is_a_scoring_race(self, name):
        assert _is_scoring_race_market(name) is True
        assert _classify_game_market(name) == "scoring_race", (
            f"{name!r} is still bucketed as a player prop"
        )

    def test_the_kalshi_ticker_does_not_rescue_the_old_label(self):
        # The ticker fallback runs only when the NAME says nothing. It must not
        # be what decides this family — the name already did.
        assert (
            _classify_game_market(
                "New England vs Seattle: Race to 28 Points",
                external_id="KXNFLRACE-26SEP09NESEA-28",
            )
            == "scoring_race"
        )


# ---------------------------------------------------------- the endpoint --


class TestTheEndpointStopsServingRacesAsProps:
    @pytest.mark.asyncio
    async def test_no_race_outcome_is_served_as_a_player_prop(self):
        payload = await _payload_for(PRODUCTION_RACE_ROWS)
        assert payload["player_props"] == [], (
            "a scoring race is still in player_props: "
            f"{_names(payload['player_props'])}"
        )

    @pytest.mark.asyncio
    async def test_the_race_is_still_served_somewhere_a_reader_can_find_it(self):
        # Moved aside, not deleted. A scoring race is a real market and belongs
        # in the section that auto-categorises game markets.
        payload = await _payload_for(PRODUCTION_RACE_ROWS)
        served = _names(payload["other"])
        for _market, outcome, _prob in PRODUCTION_RACE_ROWS:
            assert outcome in served, f"{outcome!r} vanished from the payload entirely"

    @pytest.mark.asyncio
    async def test_the_script_stops_printing_a_race_as_a_prop_mark(self):
        # THE SCRIPT is built from `player_props`, so this follows from the
        # first test — pinned separately because it is the surface Alex reads
        # pre-game, and 17 of this event's 292 script marks were races.
        payload = await _payload_for(PRODUCTION_RACE_ROWS)
        labels = [m.get("label") for m in (payload.get("props_script") or [])]
        assert not [x for x in labels if x and "reaches" in x], (
            f"THE SCRIPT still carries a scoring race: {labels}"
        )


class TestTheRescueBranchDoesNotPutItBack:
    """The arm that fails if only `_classify_game_market` is fixed.

    With the classifier fixed and the rescue untouched, a race lands in the
    `else` branch, matches `_PLAYER_PROP_RE` on "Points", is not a lone-stat-word
    team market — and is appended to `player_props` again.
    """

    @pytest.mark.asyncio
    async def test_the_other_bucket_rescue_refuses_a_scoring_race(self):
        payload = await _payload_for(
            [("New Orleans vs Detroit: Race to 35 Points", "Neither team reaches 35 points", 0.03)]
        )
        assert payload["player_props"] == []
        assert "Neither team reaches 35 points" in _names(payload["other"])


# --------------------------------------------------------- the projection --


class TestARaceNeverPricesTheProjection:
    def test_a_race_is_dropped_at_the_market_level(self):
        assert "scoring_race" in _PM_MARKET_PRICES_NEITHER_ARM

    def test_the_period_scopes_it_joins_are_all_still_dropped(self):
        # The new set is a SUPERSET, never a replacement: #3921/#3992's labels
        # keep the drop they were added for.
        assert _PM_PERIOD_SCOPES <= _PM_MARKET_PRICES_NEITHER_ARM

    def test_it_is_a_stronger_refusal_than_the_one_it_replaces(self):
        # Under `player_prop` a race was refused the TOTAL and left eligible for
        # the spread arm. Dropping it outright must not be quietly weaker.
        assert "player_prop" in _PM_NON_GAME_TOTAL_SCOPES
        assert "scoring_race" not in _PM_NON_GAME_TOTAL_SCOPES, (
            "belt-and-braces would be harmless, but naming it in both sets hides "
            "which one is doing the work"
        )


# ------------------------------------------------------------- controls --


class TestNothingElseMoves:
    @pytest.mark.asyncio
    async def test_a_bare_player_name_outcome_is_still_a_player_prop(self):
        # The 19 rows an outcome-shape rule would have taken with the 153.
        payload = await _payload_for(PRODUCTION_BARE_NAME_ROWS)
        served = _names(payload["player_props"])
        for _market, outcome, _prob in PRODUCTION_BARE_NAME_ROWS:
            assert outcome in served, f"{outcome!r} lost its player prop"

    @pytest.mark.asyncio
    async def test_a_normal_player_ladder_is_untouched(self):
        rows = [
            ("New Orleans vs Detroit: Passing Yards", "Jared Goff: 175+", 0.9),
            ("New Orleans vs Detroit: Passing Yards", "Jared Goff: 200+", 0.78),
        ]
        payload = await _payload_for(rows)
        assert _names(payload["player_props"]) == ["Jared Goff: 175+", "Jared Goff: 200+"]

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("New Orleans vs Detroit: Total Points", "game_total"),
            ("Cleveland at LA: Points", "team_total"),
            ("Celtics at Warriors: 1st Half Total", "half_total"),
            ("New England vs Seattle: Most Receiving Yards", "player_prop"),
            ("Drake Maye Passing Yards O/U 249.5", "game_total"),
        ],
    )
    def test_the_neighbouring_labels_are_unchanged(self, name, expected):
        assert _classify_game_market(name) == expected


class TestTheRuleIsNarrowerThanTheWords:
    """The pattern requires the SCORE unit, not just the words "race to".

    Every one of the 94 rows in the table on 2026-09-11 is a team scoring race.
    A player race is a shape nobody has measured, so it is deliberately left
    outside a rule derived from team races rather than swept in by grammar.
    """

    @pytest.mark.parametrize(
        "name",
        [
            "Race to 5 catches",
            "New England vs Seattle: Race to 100 receiving yards",
            "Presidential race to 270",
        ],
    )
    def test_a_race_that_is_not_a_scoring_race_is_not_caught(self, name):
        assert _is_scoring_race_market(name) is False

    @pytest.mark.parametrize(
        "name",
        [
            "New Orleans vs Detroit: Race to 14 Points",
            "Lakers vs Celtics: Race to 20 points",
            "Race to 7 Point",
        ],
    )
    def test_the_scoring_races_are(self, name):
        assert _is_scoring_race_market(name) is True
