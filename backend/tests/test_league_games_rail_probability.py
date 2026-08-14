"""The league games rail must show the blended probability (#1776).

## Why this file exists

`league_futures._event_probability` read `win_probability_sources["aggregate"]["home"]`
for its whole life. **That key has never existed.** The column's schema is
`{source: {value, display_name, type, color}}` — the blend is COMPUTED by
`utils/aggregation.compute_aggregate_probability`, not stored — so the function
returned `None` unconditionally and every league page rendered its fixtures with
no number: measured 118 of 118 upcoming games across all 29 registered leagues,
including a LIVE MLB game holding five sources.

The frontend was innocent: `LeagueGameRail` correctly withholds the bar when the
probability is null (register E2 — null must never be drawn as a claim). So the
defect was invisible from the render side; it looked like an upstream coverage
gap, and the tier census counted all 118 games as unpriced, which made Alex's
games amendment contribute exactly zero to every league's tier.

## The shape of the guard

Both directions, per gotcha #43: a game WITH sources must render a number, and a
game with genuinely none must still render `None` rather than a fabricated 50%.
The fixtures below are the REAL production payload of event 15189168 (Pittsburgh
Pirates @ Miami Marlins, status `live`, 2026-08-11), not an invented shape — the
whole bug was a mismatch between the assumed shape and the real one, so a
hand-drawn fixture would have reproduced the assumption instead of the data.
"""

from __future__ import annotations

import pytest

from app.routes.league_futures import _event_probability, _format_game_brief
from app.utils.aggregation import compute_aggregate_probability

from datetime import datetime, timezone


#: Verbatim from production event 15189168, a live MLB game. Note the absence of
#: any "aggregate" member — that absence IS the bug this file guards.
PRODUCTION_SOURCES = {
    "mlb": {"value": 0.693, "display_name": "MLB Model", "type": "model", "color": "#06b6d4"},
    "espn": {"value": 0.642, "display_name": "ESPN", "type": "model", "color": "#f97316"},
    "kalshi": {"value": 0.485, "display_name": "Kalshi", "type": "market", "color": "#22c55e"},
    "polymarket": {"value": 0.285, "display_name": "Polymarket", "type": "market", "color": "#3b82f6"},
    "stat_model": {"value": 0.7186, "display_name": "Bain Luck Model", "type": "model", "color": "#8b5cf6"},
}


class FakeEvent:
    """Duck-typed Event. `compute_aggregate_probability` reads exactly these.

    UX-P074 widened it to the columns the SHARED event card's payload reads
    (`external_id`, `completed_at`, the opening pair, the live-clock trio). A
    fixture narrower than the row is how a formatter comes to depend on an
    attribute nothing in the suite has — which is exactly what happened when the
    rail's payload grew.
    """

    def __init__(
        self,
        *,
        sources=None,
        status="scheduled",
        espn=None,
        opening=None,
        opening_away=None,
        period=None,
        game_clock=None,
        broadcast=None,
        scores=(None, None),
    ):
        self.id = 15189168
        self.external_id = "odds-api-15189168"
        self.home_team_name = "Miami Marlins"
        self.away_team_name = "Pittsburgh Pirates"
        self.commence_time = datetime(2026, 8, 11, 22, 40, tzinfo=timezone.utc)
        self.completed_at = None
        self.status = status
        self.home_score, self.away_score = scores
        self.win_probability_sources = sources
        self.espn_win_prob_home = espn
        self.opening_home_probability = opening
        self.opening_away_probability = opening_away
        self.period = period
        self.game_clock = game_clock
        self.broadcast_info = broadcast


class TestTheRegression:
    def test_a_game_with_sources_renders_a_probability(self):
        """The headline. This returned None for every event before #1776."""
        p = _event_probability(FakeEvent(sources=PRODUCTION_SOURCES, status="live"))
        assert p is not None, (
            "the league games rail is blank again — _event_probability is not "
            "reading the canonical blend"
        )
        assert 0.0 <= p <= 1.0

    def test_the_nonexistent_aggregate_key_is_not_what_we_read(self):
        """Pins the ACTUAL defect, not just its symptom.

        A payload carrying the old assumed shape and nothing else must still
        resolve to None — proving we no longer depend on `aggregate`. If someone
        reintroduces the old read, this passes while the test above fails; if
        someone hardcodes a constant, this one fails. The pair is what localises
        a future regression instead of just detecting it.
        """
        only_aggregate = {"aggregate": {"home": 0.77}}
        assert _event_probability(FakeEvent(sources=only_aggregate)) is None

    def test_no_sources_still_renders_nothing(self):
        """The other direction (gotcha #43): absence must stay absence.

        A fabricated 50% here would be worse than the bug — doctrine A3, and
        register E2's null-drawn-as-a-claim.
        """
        assert _event_probability(FakeEvent(sources=None)) is None
        assert _event_probability(FakeEvent(sources={})) is None

    def test_a_non_dict_sources_column_does_not_raise(self):
        """The rail is built inside a per-item formatter; a throw here empties
        the whole rail (gotcha #42)."""
        for junk in ("", [], 0, "aggregate"):
            assert _event_probability(FakeEvent(sources=junk)) is None


class TestItIsTheCanonicalBlendAndNotASecondAlgorithm:
    """Register E9 records a SECOND blend in `teams.py`. This must not be a third."""

    @pytest.mark.parametrize("status", ["scheduled", "live", "completed", "closed"])
    def test_matches_compute_aggregate_probability_exactly(self, status):
        e = FakeEvent(sources=PRODUCTION_SOURCES, status=status)
        assert _event_probability(e) == compute_aggregate_probability(e)

    def test_settled_games_drop_the_market_sources(self):
        """Not a detail — the RESULTS rail shares this formatter.

        Kalshi/Polymarket prices go stale post-final, so the canonical blend
        excludes them once a game is completed/closed. A locally re-derived rule
        would silently diverge from the rest of the product the first time that
        policy changed.
        """
        live = _event_probability(FakeEvent(sources=PRODUCTION_SOURCES, status="live"))
        done = _event_probability(FakeEvent(sources=PRODUCTION_SOURCES, status="completed"))
        assert live != done, (
            "completed games are blending the market sources back in — the status "
            "is not reaching the canonical blend"
        )


class TestTheRailPayload:
    def test_format_game_brief_carries_the_number(self):
        brief = _format_game_brief(FakeEvent(sources=PRODUCTION_SOURCES, status="live"))
        assert brief["home_win_probability"] is not None
        assert brief["home_team"] == "Miami Marlins"
        assert brief["away_team"] == "Pittsburgh Pirates"

    def test_the_census_sees_a_priced_game_as_an_answer(self):
        """The second-order half of #1776, and the reason the census looked frozen.

        `league_futures` shapes each upcoming game into the tier census as
        `{"top_outcomes": [{"probability": home_win_probability}]}`. With a null
        probability every game is 'unpriced', so the games amendment contributes
        nothing to any league's tier. This asserts the shape the route builds is
        one the resolver can actually count.
        """
        from app.utils.entity_page_tiers import resolve_entity_tier

        brief = _format_game_brief(FakeEvent(sources=PRODUCTION_SOURCES, status="live"))
        census = {
            "games": [
                {"id": f"game:{brief['id']}",
                 "top_outcomes": [{"probability": brief["home_win_probability"]}]}
            ]
        }
        out = resolve_entity_tier(census, now=datetime.now(timezone.utc))
        assert out["pool_counts"]["answers"] == 1, (
            "a priced game is still not counted as an answer — the games "
            "amendment is inert and the tier census will not move"
        )
        assert out["pool_counts"]["dropped"] == 0

    def test_an_unpriced_game_is_still_dropped_not_counted(self):
        """The guard's other direction: fixing the read must not make a
        probability-less fixture start counting as an answer."""
        from app.utils.entity_page_tiers import resolve_entity_tier

        brief = _format_game_brief(FakeEvent(sources=None))
        census = {"games": [{"id": "game:1",
                             "top_outcomes": [{"probability": brief["home_win_probability"]}]}]}
        out = resolve_entity_tier(census, now=datetime.now(timezone.utc))
        assert out["pool_counts"]["answers"] == 0
        assert out["pool_counts"]["dropped"] == 1


class FakeTeam:
    """The columns `_format_team_data` reads. Values are the Marlins' real ones."""

    def __init__(self, name, primary="#00A3E0", logo="marlins.png"):
        self.id = 1
        self.slug = name.lower().replace(" ", "-")
        self.abbreviation = None
        self.primary_color = primary
        self.secondary_color = "#EF3340"
        self.logo_url_small = logo
        self.logo_url_large = None
        self.current_record = "60-58"


class TestTheSharedCardContract:
    """UX-P074 (#1860), ruling 047 — the rail renders the SHARED event card.

    "League pages get no bespoke variants." The card is not this file's business;
    what IS, is that the payload carries the card's contract, under the SAME key
    names `/api/events` uses. A rail-local synonym for `current_odds` would leave
    the shared card rendering a blank where it has a number, which is the
    silently-degraded version of the fork the ruling forbids.
    """

    def test_the_card_gets_both_sides_of_the_blend(self):
        brief = _format_game_brief(
            FakeEvent(sources=PRODUCTION_SOURCES, status="live"), "baseball_mlb"
        )
        assert brief["current_odds"]["home_probability"] == brief["home_win_probability"]
        assert brief["current_odds"]["away_probability"] == pytest.approx(
            1.0 - brief["home_win_probability"]
        )

    def test_the_flat_key_and_current_odds_can_never_disagree(self):
        """One blend, stated twice, from ONE call.

        `home_win_probability` feeds the tier census and `current_odds` feeds the
        card. If these were computed separately the page could show a number the
        census did not count — the divergence #1776's second half was about.
        """
        brief = _format_game_brief(FakeEvent(sources=PRODUCTION_SOURCES), "baseball_mlb")
        assert brief["current_odds"]["home_probability"] == brief["home_win_probability"]

    def test_an_unpriced_game_carries_NO_current_odds(self):
        """Absent, not zeroed. The card withholds on absence; a `{"home": null}`
        would be a measured null, and a 0.0 would be a claim."""
        brief = _format_game_brief(FakeEvent(sources=None), "baseball_mlb")
        assert "current_odds" not in brief
        assert brief["home_win_probability"] is None

    def test_the_census_key_survives_the_widening(self):
        """The flat key is what `resolve_entity_tier` reads. Dropping it while
        adding `current_odds` would silently retier all 29 leagues."""
        brief = _format_game_brief(FakeEvent(sources=PRODUCTION_SOURCES), "baseball_mlb")
        assert "home_win_probability" in brief

    def test_the_league_chip_comes_from_the_route_not_a_lazy_relationship(self):
        """`sport` is passed in. Reading `event.sport.key` here would be a
        MissingGreenlet: the rails' query joins Sport for the WHERE clause and
        never eager-loads the relationship."""
        brief = _format_game_brief(FakeEvent(sources=None), "baseball_mlb")
        assert brief["sport"] == "baseball_mlb"
        assert not hasattr(FakeEvent(sources=None), "sport")

    def test_team_colours_and_logos_ride_the_envelope(self):
        lookup = {
            "Miami Marlins": FakeTeam("Miami Marlins"),
            "Pittsburgh Pirates": FakeTeam("Pittsburgh Pirates", "#FDB827", "pirates.png"),
        }
        brief = _format_game_brief(FakeEvent(sources=None), "baseball_mlb", lookup)
        assert brief["home_team_data"]["primary_color"] == "#00A3E0"
        assert brief["away_team_data"]["logo_small"] == "pirates.png"

    def test_a_team_we_have_no_media_for_is_simply_absent(self):
        """Chrome degrades; content does not. No colour is no key, not a
        placeholder colour the card would draw as if it were the team's."""
        lookup = {"Miami Marlins": FakeTeam("Miami Marlins", primary=None, logo=None)}
        brief = _format_game_brief(FakeEvent(sources=None), "baseball_mlb", lookup)
        assert "home_team_data" not in brief
        assert "away_team_data" not in brief

    def test_the_live_clock_is_normalised_not_passed_raw(self):
        """#1710: an un-normalised period field put ESPN's pre-game sentence
        where "Q3" belongs. The rail goes through the same helper the event route
        does rather than forwarding the column."""
        brief = _format_game_brief(
            FakeEvent(status="live", period="7", game_clock="Top 7th", broadcast="MLBN"),
            "baseball_mlb",
        )
        assert brief["espn"]["broadcast"] == "MLBN"
        assert "Mon, August" not in str(brief["espn"].get("period", ""))

    def test_the_opening_line_rides_along_and_derives_its_other_side(self):
        brief = _format_game_brief(FakeEvent(opening=0.55), "baseball_mlb")
        assert brief["opening_odds"]["home_probability"] == pytest.approx(0.55)
        assert brief["opening_odds"]["away_probability"] == pytest.approx(0.45)

    def test_no_opening_line_means_no_opening_key(self):
        brief = _format_game_brief(FakeEvent(), "baseball_mlb")
        assert "opening_odds" not in brief

    def test_the_signature_still_works_with_one_argument(self):
        """The task path and any other caller keep working. A required new
        parameter would have moved the failure to import time somewhere else."""
        brief = _format_game_brief(FakeEvent(sources=PRODUCTION_SOURCES))
        assert brief["sport"] is None
        assert brief["home_win_probability"] is not None
