"""#3594 — a team game's Runs map is not four different players' prop lines.

THE DEFECT, MEASURED. `GET /api/events/15305464/game-markets` on production,
2026-09-06 (Phillies at Braves, pre-game), served this as its `totals` ladder:

    2.5   game_total   Brandon Marsh: Total Bases O/U 2.5
    3.5   game_total   Bryce Harper: Total Bases O/U 3.5
    4.5   game_total   Drake Baldwin: Total Bases O/U 4.5
    5.5   game_total   Drake Baldwin: Total Bases O/U 5.5

Every rung is a different player's prop, and the event page's Runs map draws its
density band from them. A totals ladder means "the probability the SAME quantity
clears each of these lines" — which is why the renderer enforces monotonicity
across it. Marsh's 2.5 bases and Harper's 3.5 bases are not two points on one
curve. The band is a picture of nothing.

WHY THE CLASSIFIER LET THEM THROUGH. `_is_player_prop_ou_market` is structural and
correct — non-matchup subject, then a stat word, then the O/U line — but the stat
vocabulary it consults had never heard of "bases". So the name fell past the player
branch into `game_total`. Measured the same morning, `Total Bases` was the only
missing family: 52 open markets over 5 events, while every other subject-prefixed
O/U stat on the page (home runs, hits, strikeouts, hits + runs + rbis) matched.

AND THE SECTION THEY BELONG TO WAS ALSO WRONG. That event carries 45 player-prop
markets, 14 of them Total Bases, and served **8 props at 8 distinct thresholds** —
0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5. One survivor per number is the signature of
a dedup key, not of a market: the cross-source dedup read the player off the OUTCOME
name, and a Polymarket prop's outcome is a bare "Over"/"Under". So every prop on the
page had one of two identities, distinct players collided on a shared threshold, and
one was averaged away under the other's name.

THE TWO HALVES SHIP TOGETHER ON PURPOSE. Re-bucketing alone would move 14 Total
Bases markets into a section whose key then merges them across players — trading a
false band for a false number under a named person, which is worse. Fixing the key
alone leaves the Runs map drawn from props.

WHAT A READER LOSES, SAID PLAINLY. That event has no game-total market at all — all
59 of its markets are player props — so with the props re-bucketed the Runs map is
gone rather than wrong, and `MarketMapSection` hides an empty card. The `Projected 8`
it used to carry was true (it comes from the event's own over/under, not from the
rungs); the rail under it, 0…12+, was built from prop thresholds and was not. A card
with one true number in it is not a reason to keep three false ones.

RED-FIRST. On the parent commit `TestATotalBasesLineIsAPlayerProp`,
`TestTheRunsMapIsNotBuiltFromProps` and `TestEveryPlayerKeepsHisOwnLine` all fail:
the four rungs classified `game_total`, and two players sharing a threshold came back
as one row.

THE CONTROL ARM. `TestNothingElseMoves` holds the shapes this rule must not touch —
a genuine game total that carries O/U, a matchup-subject "Total Bases", a team stat
market, and Kalshi's outcome-side player naming, which keeps its own identity path.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes.events import (
    _classify_game_market,
    _game_markets_cache,
    _is_player_prop_ou_market,
    _prop_player_and_stat,
    _prop_side,
    get_game_markets,
)

# The four rungs, verbatim from the production payload.
PRODUCTION_RUNGS = [
    "Brandon Marsh: Total Bases O/U 2.5",
    "Bryce Harper: Total Bases O/U 3.5",
    "Drake Baldwin: Total Bases O/U 4.5",
    "Drake Baldwin: Total Bases O/U 5.5",
]


# ---------------------------------------------------------------- fixtures --


def _make_result(scalar=None, rows=None, all_rows=None):
    rows = rows or []
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value.all.return_value = rows
    result.all.return_value = all_rows if all_rows is not None else []
    return result


def _make_event(*, id=15305464):
    event = MagicMock()
    event.id = id
    event.home_team_name = "Atlanta Braves"
    event.away_team_name = "Philadelphia Phillies"
    event.status = "scheduled"
    # None on purpose: roster enrichment is a separate query path and this test is
    # about which section a market lands in, not about headshots.
    event.sport_id = None
    event.sport = MagicMock()
    event.sport.key = "baseball_mlb"
    event.commence_time = datetime(2026, 9, 6, 22, 15, tzinfo=timezone.utc)
    event.home_score = None
    event.away_score = None
    event.period = None
    event.game_clock = None
    event.box_score_data = None
    return event


def _make_market(*, id, name, event_id, source="polymarket"):
    market = MagicMock()
    market.id = id
    market.name = name
    market.external_id = f"0x{id:064x}"
    market.event_id = event_id
    market.category = "game_prop"
    market.status = "open"
    market.source = source
    market.sport_id = None
    market.llm_sport_category = "baseball"
    market.commence_time = datetime(2026, 9, 6, 22, 15, tzinfo=timezone.utc)
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
            # #2693 — `folded_event_ids`: the canonical's suppressed twins, so
            # the surviving card carries the prices the ghost was holding. The
            # list is a POSITIONAL contract with the query sequence.
            _make_result(rows=[]),
            _make_result(rows=markets),
            _make_result(all_rows=[]),  # polymarket parent groups
            _make_result(rows=[]),  # unlinked fallback
            _make_result(rows=outcomes),
        ]
    )
    return db


def _payload_for(rows, event=None):
    """Build the endpoint response for `[(market_name, outcome_name, prob), ...]`."""
    event = event or _make_event()
    markets, outcomes = [], []
    for i, (name, outcome_name, prob) in enumerate(rows, start=1):
        markets.append(_make_market(id=1000 + i, name=name, event_id=event.id))
        outcomes.append(
            _make_outcome(
                id=2000 + i, market_id=1000 + i, name=outcome_name, probability=prob
            )
        )
    return get_game_markets(event.id, _db_for(event, markets, outcomes))


@pytest.fixture(autouse=True)
def clear_game_markets_cache():
    _game_markets_cache.clear()
    yield
    _game_markets_cache.clear()


# -------------------------------------------------------------- bucketing --


class TestATotalBasesLineIsAPlayerProp:
    @pytest.mark.parametrize("name", PRODUCTION_RUNGS)
    def test_the_production_rungs_are_props(self, name):
        assert _is_player_prop_ou_market(name) is True
        assert _classify_game_market(name) == "player_prop", (
            f"{name!r} is still a rung on the Runs map"
        )

    @pytest.mark.parametrize(
        "name",
        [
            "Jose Altuve: Total Bases O/U 1.5",
            "Vladimir Guerrero Jr.: Total Bases O/U 3.5",
            "Ronald Acuña Jr.: Total Bases O/U 5.5",
            "Pete Crow-Armstrong: Total Bases O/U 4.5",
            "Heriberto Hernández: Total Bases O/U 1.5",
        ],
        ids=["altuve", "guerrero-jr", "acuna-accent", "hyphenated", "accent"],
    )
    def test_the_rest_of_the_population_too(self, name):
        """Names taken from the 52 open Total Bases markets, 2026-09-06."""
        assert _classify_game_market(name) == "player_prop"

    @pytest.mark.parametrize(
        "name",
        [
            "Jose Altuve: RBIs O/U 1.5",
            "Kyle Schwarber: Walks O/U 0.5",
            "Matt Olson: Doubles O/U 0.5",
        ],
        ids=["rbis", "walks", "doubles"],
    )
    def test_the_neighbouring_batting_stats_are_props_too(self, name):
        """The same family. Named now rather than after the next page renders one."""
        assert _classify_game_market(name) == "player_prop"


class TestNothingElseMoves:
    """The control arm: every shape this rule must leave exactly where it was."""

    @pytest.mark.parametrize(
        "name,expected",
        [
            # A genuine game total that carries the same O/U token.
            ("Cardinals vs. Reds: O/U 10.5", "game_total"),
            ("Reds vs. Cardinals: O/U 10.5", "game_total"),
            # A matchup subject means the line belongs to the GAME, whatever the
            # stat word says — this one is in the LAT-P154 fixtures verbatim.
            ("Chiefs vs. Bills: Total Bases", "game_total"),
            ("Yankees at Red Sox: Total Bases O/U 12.5", "game_total"),
            # Team stat markets keep their own branch.
            ("Cleveland at LA: Points", "team_total"),
            # Kalshi's shape, where the player is named in the OUTCOME and the
            # MARKET reads as a team stat — the per-player split happens downstream.
            ("Reds at Cardinals: Home Runs", "team_total"),
            # Period and team totals are untouched.
            ("Braves vs. Phillies: 1st Half O/U 4.5", "half_total"),
            ("Braves Team Total O/U 4.5", "team_total"),
        ],
    )
    def test_unchanged(self, name, expected):
        assert _classify_game_market(name) == expected

    @pytest.mark.parametrize(
        "name",
        [
            "Cardinals vs. Reds: O/U 10.5",
            "Chiefs vs. Bills: Total Bases",
            "Yankees at Red Sox: Total Bases O/U 12.5",
        ],
    )
    def test_a_matchup_subject_is_never_a_person(self, name):
        assert _is_player_prop_ou_market(name) is False


# --------------------------------------------------------------- identity --


class TestWhoThePropIsAbout:
    @pytest.mark.parametrize(
        "market_name,outcome_name,expected",
        [
            # Polymarket: the outcome names nobody, so the subject does.
            ("Brandon Marsh: Total Bases O/U 2.5", "Over", ("brandon marsh", "total bases")),
            ("Drake Baldwin: Total Bases O/U 5.5", "Under", ("drake baldwin", "total bases")),
            ("Aaron Nola: Strikeouts O/U 6.5", "Over", ("aaron nola", "strikeouts")),
            # Kalshi: the outcome names the player, the market names the stat.
            ("Reds at Cardinals: Home Runs", "Soto: 2+", ("soto", "home runs")),
            ("Boston at Atlanta: Points", "Jayson Tatum: 30+", ("jayson tatum", "points")),
        ],
    )
    def test_the_player_is_read_from_whichever_field_carries_him(
        self, market_name, outcome_name, expected
    ):
        assert _prop_player_and_stat(market_name, outcome_name) == expected

    def test_two_players_at_one_threshold_are_two_identities(self):
        """The whole defect, in one assertion."""
        marsh = _prop_player_and_stat("Brandon Marsh: Total Bases O/U 2.5", "Over")
        harper = _prop_player_and_stat("Bryce Harper: Total Bases O/U 2.5", "Over")
        assert marsh != harper

    def test_one_player_two_stats_are_two_identities(self):
        hits = _prop_player_and_stat("Trea Turner: Hits O/U 2.5", "Over")
        bases = _prop_player_and_stat("Trea Turner: Total Bases O/U 2.5", "Over")
        assert hits != bases

    @pytest.mark.parametrize(
        "outcome_name,expected",
        [
            ("Over", "over"),
            ("Under", "under"),
            ("under 2.5", "under"),
            ("No", "under"),
            ("Yes", "over"),
            ("Soto: 2+", "over"),
            ("", "over"),
            (None, "over"),
        ],
    )
    def test_the_side_survives_the_key(self, outcome_name, expected):
        assert _prop_side(outcome_name) == expected


# ------------------------------------------------------------------ route --


class TestTheRunsMapIsNotBuiltFromProps:
    @pytest.mark.asyncio
    async def test_the_four_rungs_leave_the_totals_ladder(self):
        response = await _payload_for(
            [(name, "Under", 0.895) for name in PRODUCTION_RUNGS]
        )
        assert response["totals"] == [], (
            "the Runs map is still drawn from four different players' bases lines"
        )

    @pytest.mark.asyncio
    async def test_and_arrive_in_the_section_they_belong_to(self):
        response = await _payload_for(
            [(name, "Under", 0.895) for name in PRODUCTION_RUNGS]
        )
        served = {p["market_name"] for p in response["player_props"]}
        assert served == set(PRODUCTION_RUNGS), (
            "a re-bucketed prop must reach Player Props, not vanish between sections"
        )

    @pytest.mark.asyncio
    async def test_a_real_game_total_still_draws_the_map(self):
        """The control: a page WITH a runs market keeps its rungs and its card."""
        response = await _payload_for(
            [
                ("Phillies vs. Braves: O/U 8.5", "Over", 0.52),
                ("Phillies vs. Braves: O/U 9.5", "Over", 0.41),
                ("Brandon Marsh: Total Bases O/U 2.5", "Under", 0.895),
            ]
        )
        assert sorted(t["threshold"] for t in response["totals"]) == [8.5, 9.5]
        assert [p["market_name"] for p in response["player_props"]] == [
            "Brandon Marsh: Total Bases O/U 2.5"
        ]


class TestEveryPlayerKeepsHisOwnLine:
    @pytest.mark.asyncio
    async def test_two_players_sharing_a_threshold_both_survive(self):
        """One survivor per number was the production signature of the old key."""
        response = await _payload_for(
            [
                ("Trea Turner: Hits O/U 2.5", "Over", 0.34),
                ("Kyle Schwarber: Hits O/U 2.5", "Over", 0.22),
                ("Drake Baldwin: Hits O/U 2.5", "Over", 0.18),
            ]
        )
        served = {p["market_name"] for p in response["player_props"]}
        assert len(served) == 3, f"players were averaged into one another: {served}"

    @pytest.mark.asyncio
    async def test_one_player_two_stats_at_one_threshold_both_survive(self):
        response = await _payload_for(
            [
                ("Trea Turner: Hits O/U 2.5", "Over", 0.34),
                ("Trea Turner: Total Bases O/U 2.5", "Over", 0.46),
            ]
        )
        by_name = {p["market_name"]: p["over_probability"] for p in response["player_props"]}
        assert set(by_name) == {
            "Trea Turner: Hits O/U 2.5",
            "Trea Turner: Total Bases O/U 2.5",
        }
        # Not averaged into 0.40 — two questions, two prices.
        assert by_name["Trea Turner: Hits O/U 2.5"] == 0.34
        assert by_name["Trea Turner: Total Bases O/U 2.5"] == 0.46

    @pytest.mark.asyncio
    async def test_one_players_ladder_is_still_made_monotonic(self):
        """Within ONE player and stat the rungs are one curve, and the house rule
        that P(Over X) may not rise with X still applies to it."""
        response = await _payload_for(
            [
                ("Trea Turner: Total Bases O/U 2.5", "Over", 0.46),
                ("Trea Turner: Total Bases O/U 3.5", "Over", 0.58),
            ]
        )
        by_threshold = {p["threshold"]: p["over_probability"] for p in response["player_props"]}
        assert by_threshold[3.5] <= by_threshold[2.5]

    @pytest.mark.asyncio
    async def test_the_two_sides_of_one_market_are_not_folded_together(self):
        """A cross-SOURCE dedup must not become a cross-side one: the Over row and
        the Under row are two rows on the page and one venue, not two venues."""
        event = _make_event()
        market = _make_market(
            id=1, name="Brandon Marsh: Total Bases O/U 2.5", event_id=event.id
        )
        outcomes = [
            _make_outcome(id=1, market_id=1, name="Over", probability=0.105),
            _make_outcome(id=2, market_id=1, name="Under", probability=0.895),
        ]
        response = await get_game_markets(event.id, _db_for(event, [market], outcomes))

        props = response["player_props"]
        assert len(props) == 2
        assert {p["outcome_name"] for p in props} == {"Over", "Under"}
        assert all(p.get("source_count") in (None, 1) for p in props), (
            "one venue's two sides were counted as two venues"
        )
