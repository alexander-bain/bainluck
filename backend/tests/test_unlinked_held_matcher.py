"""Precision tests for the unlinked-held matchup matcher (Queue #223 Item 4).

_matchup_matches_event requires BOTH market teams to correspond to the event's two
teams (either orientation) — stricter than match_teams_to_event's one-side fire — so
a filed miss is a real matcher failure, not a coincidental one-name overlap."""

from types import SimpleNamespace
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.routes.admin_matching import (
    _compute_unlinked_held,
    _is_non_game_winner_derivative,
    _matchup_matches_event,
)


def _instant(value):
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def _market(*, name="Southern Jaguars vs. Minnesota Golden Gophers", source="polymarket",
            external_id="6737021", category="basketball", slug="cbb-south-minnst-2026-11-12",
            start="2026-11-13T01:00:00", market_id=69305233):
    return SimpleNamespace(
        id=market_id, name=name, source=source, external_id=external_id,
        llm_sport_category=category,
        market_metadata={"polymarket_event_slug": slug, "venue_game_start": start},
    )


def _event(*, home="Minnesota Golden Gophers", away="Southern Jaguars",
           sport="basketball_ncaab", start="2026-11-13T01:00:00", event_id=77):
    return SimpleNamespace(id=event_id, sport_key=sport, home=home, away=away,
                           matchup=f"{away} @ {home}", commence_time=_instant(start))


async def _compute(markets, events):
    db = SimpleNamespace(execute=AsyncMock(side_effect=[
        None, SimpleNamespace(all=lambda: events), SimpleNamespace(all=lambda: markets),
    ]))
    return await _compute_unlinked_held(db)


class TestFixtureScope:
    # Fixed historical venue fixtures from #12072, compared to each other, never now.
    @pytest.fixture(autouse=True)
    def fixed_fixture_clock(self, monkeypatch):
        class FixtureClock(datetime):
            @classmethod
            def now(cls, tz=None):
                instant = _instant("2026-11-12T08:00:00")
                return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)

        monkeypatch.setattr("app.routes.admin_matching.datetime", FixtureClock)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("market,event", [
        (_market(), _event(sport="basketball_wncaab", start="2026-11-11T01:00:00", event_id=15342190)),
        (_market(name="New Mexico State Aggies vs. UTEP Miners", slug="cbb-nmxst-utep-2026-11-12",
                 start="2026-11-13T02:00:00", market_id=69311396),
         _event(home="New Mexico State Aggies", away="UTEP Miners (W)", sport="basketball_other",
                start="2026-11-11T02:00:00", event_id=15342183)),
        (_market(name="Temple Owls vs. La Salle Explorers", slug="cbb-templ-lasal-2026-11-15",
                 start="2026-11-15T19:00:00", market_id=69716122),
         _event(home="Temple Owls", away="La Salle Explorers (W)", sport="basketball_other",
                start="2026-11-11T23:30:00", event_id=15342862)),
    ])
    async def test_accepted_12072_false_alerts_are_not_misses(self, market, event):
        result = await _compute([market], [event])
        assert result["misses"] == []
        assert result["headline_unlinked_held"] == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("event", [
        _event(sport="basketball_wncaab"),
        _event(sport="basketball_other", away="Southern Jaguars (W)"),
        _event(sport="americanfootball_ncaaf"),
        _event(start="2026-11-12T01:00:00"),
    ])
    async def test_each_scope_guard_works_without_the_others(self, event):
        result = await _compute([_market()], [event])
        assert result["misses"] == []

    @pytest.mark.asyncio
    async def test_true_miss_survives_an_earlier_wrong_candidate(self):
        result = await _compute([_market()], [_event(sport="basketball_wncaab", event_id=66), _event()])
        assert [m["event_id"] for m in result["misses"]] == [77]
        assert result["by_source"] == {"polymarket": 1}

    @pytest.mark.asyncio
    async def test_kalshi_day_is_eastern_not_close_time_or_utc_day(self):
        market = _market(name="Oklahoma City vs Portland", source="kalshi",
                         external_id="KXNBAGAME-26NOV11OKCPOR", start=None)
        events = [
            _event(home="Portland Trail Blazers", away="Oklahoma City Thunder", sport="basketball_nba",
                   start="2026-11-11T04:00:00", event_id=15345479),
            _event(home="Portland Trail Blazers", away="Oklahoma City Thunder", sport="basketball_nba",
                   start="2026-11-12T03:00:00", event_id=15345987),
        ]
        result = await _compute([market], events)
        assert [m["event_id"] for m in result["misses"]] == [15345987]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("market,event", [
        (_market(slug="wnba-chi-ind-2026-11-12"), _event(sport="basketball_wnba")),
        (_market(source="kalshi", external_id="KXWNBAGAME-26NOV12CHIIND"),
         _event(sport="basketball_wnba")),
        (_market(slug="uel-ars-bay-2026-11-12", category="soccer"),
         _event(sport="soccer_epl")),
        (_market(source="kalshi", external_id="KXNBAGAME-26JUL121900BOSPHI"),
         _event(start="2026-07-12T23:00:00", sport="basketball_nba")),
        (_market(source="kalshi", external_id="KXNBAGAME-26NOV121900BOSPHI"),
         _event(start="2026-11-13T00:00:00", sport="basketball_nba")),
    ])
    async def test_true_misses_keep_family_gender_and_dst_semantics(self, market, event):
        result = await _compute([market], [event])
        assert result["headline_unlinked_held"] == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("changes,reason", [
        ({"start": None}, "unknown_fixture_date"),
        ({"start": "not-a-date"}, "unknown_fixture_date"),
        ({"slug": None}, "unknown_gender"),
        ({"slug": "unmapped-south-minnst-2026-11-12"}, "unknown_gender"),
        ({"slug": None, "category": "unknown"}, "unknown_sport"),
    ])
    async def test_unknown_evidence_is_visible_not_a_confirmed_miss(self, changes, reason):
        result = await _compute([_market(**changes)], [_event()])
        assert result["misses"] == []
        assert result["unassessed_pairs"] == 1
        assert result["fixture_pair_refusals"] == {reason: 1}

    @pytest.mark.asyncio
    async def test_unknown_event_gender_is_not_mens_evidence(self):
        result = await _compute([_market()], [_event(sport="basketball_other")])
        assert result["misses"] == []
        assert result["fixture_pair_refusals"] == {"unknown_gender": 1}

    @pytest.mark.asyncio
    @pytest.mark.parametrize("minutes,expected", [(180, 1), (181, 0)])
    async def test_polymarket_keeps_the_matcher_fixture_window(self, minutes, expected):
        from datetime import timedelta

        event = _event()
        event.commence_time += timedelta(minutes=minutes)
        result = await _compute([_market()], [event])
        assert result["headline_unlinked_held"] == expected

    @pytest.mark.asyncio
    async def test_malformed_metadata_is_unassessed(self):
        market = _market()
        market.market_metadata = ["not", "a", "mapping"]
        result = await _compute([market], [_event()])
        assert result["unassessed_pairs"] == 1 and not result["misses"]

    @pytest.mark.asyncio
    async def test_derivative_with_valid_fixture_still_does_not_alert(self):
        market = _market(name="Southern Jaguars vs. Minnesota Golden Gophers - Player Props")
        result = await _compute([market], [_event()])
        assert result["derivatives_excluded"] == 1
        assert result["misses"] == []

    @pytest.mark.asyncio
    async def test_main_draw_and_qualifying_share_the_known_family_and_gender(self):
        market = _market(slug="ucl-ars-bay-2026-11-12", category="soccer")
        result = await _compute([market], [_event(sport="soccer_epl")])
        # Either known competition has the same scope; exact league equality is
        # not needed for an EPL club playing its European cup fixture.
        assert result["headline_unlinked_held"] == 1


def _mu(a, b):
    return SimpleNamespace(team_a=a, team_b=b, yes_team=a)


class TestMatcher:
    def test_both_teams_match_either_orientation(self):
        mu = _mu("Red Sox", "Rays")
        assert _matchup_matches_event(mu, "Boston Red Sox", "Tampa Bay Rays", None)
        # reversed orientation
        assert _matchup_matches_event(mu, "Tampa Bay Rays", "Boston Red Sox", None)

    def test_only_one_team_matches_is_rejected(self):
        mu = _mu("Red Sox", "Yankees")
        # Yankees is not in this event — only Red Sox overlaps → reject (high precision)
        assert not _matchup_matches_event(mu, "Boston Red Sox", "Tampa Bay Rays", None)

    def test_no_team_matches_is_rejected(self):
        mu = _mu("Dodgers", "Padres")
        assert not _matchup_matches_event(mu, "Boston Red Sox", "Tampa Bay Rays", None)

    def test_ticker_fallback_when_names_generic(self):
        # Generic market name (no teams), but the Kalshi ticker encodes them.
        mu = _mu("Yes", "No")
        ext = "KXNBAGAME-26APR24BOSPHI"  # BOS away, PHI home (Kalshi convention)
        assert _matchup_matches_event(mu, "Philadelphia 76ers", "Boston Celtics", ext)

    def test_empty_matchup_is_rejected(self):
        mu = _mu(None, None)
        assert not _matchup_matches_event(mu, "Boston Red Sox", "Tampa Bay Rays", None)


class TestDerivativeExclusion:
    """#224: the check is defined as game-WINNER (moneyline) misses. Derivative /
    prop sub-markets carry both team names but are not the moneyline — they must be
    excluded so the metric stays honest and the Flow Sentinel doesn't cry wolf.
    The production regression this guards: 9/10 flagged 'misses' were Player Props
    or First-5-Innings-Winner derivatives, not game-winner gaps."""

    def test_pure_moneylines_are_not_excluded(self):
        for name in [
            "Botafogo vs Santos",                              # the genuine kalshi soccer miss
            "New York Mets vs. Milwaukee Brewers",
            "Los Angeles Dodgers vs. San Diego Padres",
            "Real Madrid vs Barcelona",
            "Kansas City Chiefs vs. Buffalo Bills",
        ]:
            assert not _is_non_game_winner_derivative(name), name

    def test_player_props_excluded(self):
        for name in [
            "New York Mets vs. Milwaukee Brewers - Player Props",
            "Miami Marlins vs. Houston Astros - Player Props",
        ]:
            assert _is_non_game_winner_derivative(name), name

    def test_first_n_innings_winner_excluded(self):
        for name in [
            "Washington Nationals vs. Colorado Rockies - First 5 Innings Winner",
            "Cincinnati Reds vs. Seattle Mariners - First 5 Innings Winner",
        ]:
            assert _is_non_game_winner_derivative(name), name

    def test_other_derivative_families_excluded(self):
        for name in [
            "Team A vs. Team B - Total Runs",
            "Team A vs. Team B - Run Line",
            "Team A vs. Team B - First Half",
            "Team A vs. Team B - Correct Score",
            "Team A vs. Team B - Winning Margin",
        ]:
            assert _is_non_game_winner_derivative(name), name
