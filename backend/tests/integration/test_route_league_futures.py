"""Contract tests for League Futures API: GET /api/leagues/{sport_key}.

Tests that the endpoint returns the expected response shape with correct
top-level keys and sectioned market grouping — even when the DB has no data.
Uses the shared ``client`` fixture from conftest.py (mock empty DB session).
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers: mock FuturesMarket / FuturesOutcome for seeded tests
# ---------------------------------------------------------------------------


def _mock_outcome(
    *, outcome_id=1, name="Yes", probability=0.55, opening=None,
    rank=1, change_24h=0, team_id=None,
):
    return SimpleNamespace(
        id=outcome_id,
        name=name,
        current_probability=probability,
        opening_probability=opening,
        probability_change_24h=change_24h,
        rank=rank,
        team_id=team_id,
    )


def _mock_market(
    *, market_id=1, name="NBA Championship Winner", source="kalshi",
    external_id="KXNBA-CHAMP", category="championship",
    llm_sport_category="basketball", llm_league="nba",
    market_tier=1, status="open", event_id=None,
    outcomes=None, resolution_date=None,
    canonical_market_key=None,
    group_id=None,
):
    now = datetime.now(timezone.utc)
    m = SimpleNamespace(
        id=market_id,
        name=name,
        source=source,
        external_id=external_id,
        category=category,
        llm_sport_category=llm_sport_category,
        llm_league=llm_league,
        market_tier=market_tier,
        status=status,
        event_id=event_id,
        outcomes=outcomes or [
            _mock_outcome(outcome_id=market_id * 10, name="Team A", probability=0.35),
            _mock_outcome(outcome_id=market_id * 10 + 1, name="Team B", probability=0.25, rank=2),
        ],
        resolution_date=resolution_date or now + timedelta(days=90),
        canonical_market_key=canonical_market_key,
        # UX-P061 (#1742): the real FuturesMarket has carried `group_id` all along;
        # this stand-in did not, so the route's new read of it AttributeError'd.
        # A fake that is missing a field the model has is a fake that certifies a
        # shape production never serves.
        group_id=group_id,
    )
    return m


def _scalars_result(items):
    """Build a mock result with .scalars().unique().all() returning items."""
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    scalars.unique.return_value = scalars
    result.scalars.return_value = scalars
    return result


# ============================================================================
# GET /api/leagues/{sport_key} — empty DB
# ============================================================================


class TestLeagueFuturesEmpty:
    """GET /api/leagues/{sport_key} with no data in DB."""

    async def test_returns_200_for_known_sport(self, client):
        resp = await client.get("/api/leagues/basketball_nba")
        assert resp.status_code == 200

    async def test_has_top_level_keys(self, client):
        resp = await client.get("/api/leagues/basketball_nba")
        body = resp.json()
        assert "sport_key" in body
        assert "sections" in body
        assert "total_markets" in body

    async def test_sport_key_echoed_back(self, client):
        resp = await client.get("/api/leagues/icehockey_nhl")
        body = resp.json()
        assert body["sport_key"] == "icehockey_nhl"

    async def test_empty_db_has_zero_markets(self, client):
        resp = await client.get("/api/leagues/basketball_nba")
        body = resp.json()
        assert body["total_markets"] == 0
        # Empty sections are removed, so sections should be empty dict
        assert body["sections"] == {}

    @pytest.mark.parametrize("sport_key", [
        "basketball_nba",
        "icehockey_nhl",
        "baseball_mlb",
        "americanfootball_nfl",
        "basketball_wnba",
        "soccer_epl",
        "soccer_usa_mls",
        "mma_mixed_martial_arts",
    ])
    async def test_returns_200_for_all_known_sports(self, client, sport_key):
        resp = await client.get(f"/api/leagues/{sport_key}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["sport_key"] == sport_key

    async def test_unknown_sport_returns_200_empty(self, client):
        """Unknown sport keys should still return 200 with empty sections."""
        resp = await client.get("/api/leagues/curling_world")
        assert resp.status_code == 200
        body = resp.json()
        assert body["sport_key"] == "curling_world"
        assert body["total_markets"] == 0


# ============================================================================
# GET /api/leagues/{sport_key} — seeded data
# ============================================================================


class TestLeagueFuturesSeeded:
    """Tests with seeded mock market data."""

    async def test_awards_market_classified_correctly(self, client, mock_db):
        """A tier-3 market should appear in the awards section."""
        mock_db.execute.return_value = _scalars_result([
            _mock_market(
                market_id=10,
                name="NBA MVP Winner 2025-26",
                market_tier=3,
                category="award",
                llm_sport_category="basketball",
                llm_league="nba",
                external_id="KXNBA-MVP",
                outcomes=[
                    _mock_outcome(outcome_id=100, name="Luka Doncic", probability=0.30),
                    _mock_outcome(outcome_id=101, name="Nikola Jokic", probability=0.25, rank=2),
                ],
            ),
        ])

        resp = await client.get("/api/leagues/basketball_nba")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_markets"] == 1
        assert "awards" in body["sections"]
        assert len(body["sections"]["awards"]) == 1
        award = body["sections"]["awards"][0]
        assert award["name"] == "NBA MVP Winner 2025-26"
        assert award["section"] == "awards"

    async def test_series_market_classified_correctly(self, client, mock_db):
        """A market with 'series' in the name and tier 5 goes to series section."""
        mock_db.execute.return_value = _scalars_result([
            _mock_market(
                market_id=20,
                name="Bruins vs Rangers - Series Winner",
                market_tier=5,
                llm_sport_category="hockey",
                llm_league="nhl",
                external_id="KXNHL-SERIES-BOS-NYR",
                outcomes=[
                    _mock_outcome(outcome_id=200, name="Bruins", probability=0.55),
                    _mock_outcome(outcome_id=201, name="Rangers", probability=0.45, rank=2),
                ],
            ),
        ])

        resp = await client.get("/api/leagues/icehockey_nhl")
        assert resp.status_code == 200
        body = resp.json()
        assert "series" in body["sections"]
        assert body["sections"]["series"][0]["name"] == "Bruins vs Rangers - Series Winner"

    async def test_props_market_classified_correctly(self, client, mock_db):
        """A market with 'win total' in name goes to props section."""
        mock_db.execute.return_value = _scalars_result([
            _mock_market(
                market_id=30,
                name="Yankees Win Total Over 95.5",
                market_tier=5,
                category="team_prop",
                llm_sport_category="baseball",
                llm_league="mlb",
                external_id="KXMLB-WINTOTAL-NYY",
                outcomes=[
                    _mock_outcome(outcome_id=300, name="Over", probability=0.48),
                    _mock_outcome(outcome_id=301, name="Under", probability=0.52, rank=2),
                ],
            ),
        ])

        resp = await client.get("/api/leagues/baseball_mlb")
        assert resp.status_code == 200
        body = resp.json()
        assert "props" in body["sections"]
        assert body["sections"]["props"][0]["name"] == "Yankees Win Total Over 95.5"

    async def test_championship_tier_markets_excluded_from_sections(
        self, client, mock_db
    ):
        """Tier 1/2 markets (championship/conference) are excluded — they're on the grid."""
        mock_db.execute.return_value = _scalars_result([
            _mock_market(
                market_id=40,
                name="NBA Championship Winner",
                market_tier=1,
                llm_sport_category="basketball",
                llm_league="nba",
                external_id="KXNBA-CHAMP",
            ),
            _mock_market(
                market_id=41,
                name="Eastern Conference Winner",
                market_tier=2,
                llm_sport_category="basketball",
                llm_league="nba",
                external_id="KXNBA-EAST",
            ),
        ])

        resp = await client.get("/api/leagues/basketball_nba")
        assert resp.status_code == 200
        body = resp.json()
        # Both championship-tier markets excluded
        assert body["total_markets"] == 0
        assert body["sections"] == {}

    async def test_market_item_shape(self, client, mock_db):
        """Each market in a section should have the expected fields."""
        mock_db.execute.return_value = _scalars_result([
            _mock_market(
                market_id=50,
                name="NFL Defensive Player of the Year",
                market_tier=3,
                category="award",
                llm_sport_category="football",
                llm_league="nfl",
                external_id="KXNFL-DPOY",
                canonical_market_key="nfl_dpoy_2026",
            ),
        ])

        resp = await client.get("/api/leagues/americanfootball_nfl")
        assert resp.status_code == 200
        body = resp.json()
        market = body["sections"]["awards"][0]
        expected_keys = {
            "id", "name", "source", "market_tier", "category",
            "resolution_date", "outcome_count", "top_outcomes",
            "canonical_market_key", "section",
            # UX-P061 (#1742): the tier resolver deduplicates answers by
            # `group_id` + `canonical_market_key`. Pinned in the shape test because
            # dropping it silently would not fail anything else — it would just
            # quietly stop 190 esports rows from collapsing into their questions.
            "group_id",
        }
        assert expected_keys.issubset(set(market.keys()))
        assert isinstance(market["top_outcomes"], list)
        assert len(market["top_outcomes"]) > 0

    async def test_outcome_item_shape(self, client, mock_db):
        """Each outcome should have id, name, probability, rank, etc."""
        mock_db.execute.return_value = _scalars_result([
            _mock_market(
                market_id=60,
                name="Vezina Trophy Winner",
                market_tier=3,
                llm_sport_category="hockey",
                llm_league="nhl",
                external_id="KXNHL-VEZINA",
                outcomes=[
                    _mock_outcome(
                        outcome_id=600, name="Connor Hellebuyck",
                        probability=0.40, opening=0.25, change_24h=0.02, team_id=42,
                    ),
                ],
            ),
        ])

        resp = await client.get("/api/leagues/icehockey_nhl")
        assert resp.status_code == 200
        outcome = resp.json()["sections"]["awards"][0]["top_outcomes"][0]
        assert outcome["id"] == 600
        assert outcome["name"] == "Connor Hellebuyck"
        assert outcome["probability"] == 0.40
        assert outcome["opening_probability"] == 0.25
        assert outcome["movement_24h"] == 0.02
        assert outcome["team_id"] == 42
        assert outcome["rank"] == 1

    async def test_resolved_markets_filtered_out(self, client, mock_db):
        """Markets with leader >= 97% and opening >= 85% should be excluded."""
        mock_db.execute.return_value = _scalars_result([
            _mock_market(
                market_id=70,
                name="Effectively Resolved Award",
                market_tier=3,
                llm_sport_category="basketball",
                llm_league="nba",
                external_id="KXNBA-RESOLVED",
                outcomes=[
                    _mock_outcome(
                        outcome_id=700, name="Winner", probability=0.98, opening=0.90,
                    ),
                    _mock_outcome(
                        outcome_id=701, name="Loser", probability=0.02, rank=2, opening=0.10,
                    ),
                ],
            ),
        ])

        resp = await client.get("/api/leagues/basketball_nba")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_markets"] == 0


class TestEsportsCategoryWideFutures:
    """L2-92 (B4): the esports hub is category-wide + futures-only. There is no
    esports championship GRID, so championship-tier title/winner markets must be
    surfaced in a dedicated "futures" section instead of being dropped (as they
    are for grid sports). Matchup exclusion is a SQL-level filter, so it's not
    exercised by the mock DB — this pins the Python-side remap."""

    async def test_championship_tier_esports_surfaces_in_futures(self, client, mock_db):
        mock_db.execute.return_value = _scalars_result([
            _mock_market(
                market_id=80,
                name="LCK 2026 Season Winner",
                market_tier=1,
                llm_sport_category="esports",
                llm_league="lol",
                external_id="KXLOL-LCK26",
                outcomes=[
                    _mock_outcome(outcome_id=800, name="T1", probability=0.35),
                    _mock_outcome(outcome_id=801, name="Gen.G", probability=0.30, rank=2),
                ],
            ),
        ])

        resp = await client.get("/api/leagues/esports")
        assert resp.status_code == 200
        body = resp.json()
        # NOT dropped as a grid championship — surfaced in the futures section.
        assert "futures" in body["sections"], body["sections"].keys()
        assert body["sections"]["futures"][0]["name"] == "LCK 2026 Season Winner"
        assert body["sections"]["futures"][0]["section"] == "futures"

    async def test_grid_sports_still_drop_championship(self, client, mock_db):
        # Guard: the remap is esports-only — NBA championship markets are still
        # excluded (they live on the playoff grid).
        mock_db.execute.return_value = _scalars_result([
            _mock_market(
                market_id=81,
                name="NBA Championship Winner",
                market_tier=1,
                llm_sport_category="basketball",
                llm_league="nba",
                external_id="KXNBA-CHAMP",
            ),
        ])
        body = (await client.get("/api/leagues/basketball_nba")).json()
        assert "futures" not in body["sections"]
        assert body["total_markets"] == 0


# ============================================================================
# HTTP behavior
# ============================================================================


class TestLeagueFuturesHTTPBehavior:
    """General HTTP contract checks."""

    async def test_rejects_post(self, client):
        resp = await client.post("/api/leagues/basketball_nba")
        assert resp.status_code == 405

    async def test_unexpected_query_params_ignored(self, client):
        resp = await client.get("/api/leagues/basketball_nba?limit=5&source=kalshi")
        assert resp.status_code == 200
        body = resp.json()
        assert "sport_key" in body


# ============================================================================
# UX-P062 (#1743, epic #1741) — the entity envelope + Alex's games/grid amendment
# ============================================================================


def _mock_event(
    *, event_id=1, home="Boston Red Sox", away="New York Yankees",
    status="scheduled", hours_from_now=6, home_prob=0.55,
    home_score=None, away_score=None,
):
    """A stand-in Event for the league rails.

    ⚠️ FIXED (#1776). This fixture used to build
    `{"aggregate": {"home": p, "away": 1 - p}}`, under a docstring asserting that
    was "the real JSONB shape" and warning that "a fake with a flattened
    probability would certify a read production never does".

    **It was itself that fake.** No event has ever carried an `aggregate` member.
    The real schema is `{source: {value, display_name, type, color}}` and the
    blend is COMPUTED (`compute_aggregate_probability`). The route read the
    invented key, this fixture supplied the invented key, and the suite certified
    the agreement between two things that were wrong together — which is why
    every league page shipped with a probability-less games rail (118 of 118
    fixtures in production) and stayed green for a cycle.

    The shape below is the production one, measured on event 15189168. Keep it
    that way: the only thing that can break a tie between a fixture and the code
    it tests is real data.

    One source, so the blend is exactly `home_prob` and the expected values in
    these tests stay legible; `espn_win_prob_home` / `opening_home_probability`
    are present because the canonical blend reads them as later fallback tiers.
    """
    return SimpleNamespace(
        id=event_id,
        # UX-P074: the columns the shared event card's payload reads. The
        # docstring above is about a fake that was NARROWER than the row and
        # certified a read production never does — so when the payload grew, the
        # fixture grew with it rather than leaning on the formatter's getattrs.
        external_id=f"odds-api-{event_id}",
        completed_at=None,
        home_team_name=home,
        away_team_name=away,
        status=status,
        commence_time=datetime.now(timezone.utc) + timedelta(hours=hours_from_now),
        home_score=home_score,
        away_score=away_score,
        espn_win_prob_home=None,
        opening_home_probability=None,
        opening_away_probability=None,
        period=None,
        game_clock=None,
        broadcast_info=None,
        win_probability_sources=(
            {"espn": {"value": home_prob, "display_name": "ESPN", "type": "model"}}
            if home_prob is not None
            else None
        ),
    )


def _mock_team(name, *, sport_id=1, primary="#BD3039", logo="redsox.png"):
    """A Team row as `_build_team_lookup` / `_format_team_data` read it."""
    return SimpleNamespace(
        id=abs(hash(name)) % 10_000,
        name=name,
        alternate_names=[],
        sport_id=sport_id,
        slug=name.lower().replace(" ", "-"),
        abbreviation=None,
        primary_color=primary,
        secondary_color="#0C2340",
        logo_url_small=logo,
        logo_url_large=None,
        current_record="60-58",
        standings_data=None,
        season_stats=None,
    )


def _league_db(mock_db, markets, games=(), results=(), unreported=(), teams=()):
    """Sequence the route's FIVE queries: markets, games, results, unreported,
    team media.

    The existing seeded tests set a single `return_value`, so every query — including
    the two rail queries this queue added — receives the MARKET rows. That silently
    routes real work into the rails' exception guard, which is exactly the shape that
    makes a guard hide a bug instead of surviving one. Anything asserting on the
    rails must sequence the calls.

    UX-P074 (#1860) added the FOURTH: the rails now render the shared event card,
    which draws team colours and logos, so the route calls the same
    `_build_team_lookup` the events and feed routes use. Two consequences the
    caller does not get to ignore:

    1. The count in this helper's NAME is load-bearing — it was `_three_call_db`,
       and every rail assertion in this file went red the moment the route asked
       one more question than the mock had answers for. That is the helper working.
    2. `_build_team_lookup` holds a PROCESS-WIDE 5-minute cache. Left alone, whether
       the fourth call is consumed depends on which test warmed the cache first —
       the sequencing would be order-dependent, which is a flake that reads as a
       real failure. So the cache is reset here, every time.

    🔴 #3211 ADDED THE FIFTH, and it did exactly what point 1 predicts: the
    route grew `unreported_games_query` — matches whose kickoff has passed while
    the row still says `scheduled`, which were on NO rail before — and the mock
    ran out of answers one query early. The team lookup then raised
    `StopIteration` inside the rails' exception guard, so both rails came back
    stripped of their chrome and the failure surfaced as a missing
    `home_team_data` rather than as "you added a query". Worth naming, because
    the misleading symptom is the cost of sequencing by position: the guard that
    stops one bad row from emptying a rail also swallows the reason.

    `unreported` defaults to empty, so every existing caller keeps its meaning
    — the new rail is simply empty for them, which is what it should be for a
    league whose fixtures all settled.
    """
    import app.routes.events as _events_module

    _events_module._team_cache = {}
    _events_module._team_cache_time = 0.0

    mock_db.execute.side_effect = [
        _scalars_result(list(markets)),
        _scalars_result(list(games)),
        _scalars_result(list(results)),
        _scalars_result(list(unreported)),
        _scalars_result(list(teams)),
    ]


class TestLeagueEntityEnvelope:
    """Spec §7: tier, availability and every count arrive IN the payload."""

    async def test_envelope_fields_present(self, client, mock_db):
        _league_db(mock_db, [_mock_market(market_id=1, market_tier=3)])
        body = (await client.get("/api/leagues/basketball_nba")).json()

        for field in ("tier", "availability", "pool_counts", "section_counts"):
            assert field in body, f"{field} missing from the league envelope"
        assert set(body["pool_counts"]) == {"answers", "dropped", "settled"}

    async def test_availability_is_the_ruled_vocabulary(self, client, mock_db):
        """Ruling 025 / register E10: never live | stale_ok | unavailable."""
        _league_db(mock_db, [_mock_market(market_id=1, market_tier=3)])
        body = (await client.get("/api/leagues/basketball_nba")).json()
        assert body["availability"] in {"fresh", "stale", "degraded", "empty"}

    async def test_empty_league_declares_empty_not_fresh(self, client):
        body = (await client.get("/api/leagues/basketball_nba")).json()
        assert body["availability"] == "empty"

    async def test_unregistered_key_gets_no_page(self, client):
        """The generation gate is an IDENTITY question, not a density one."""
        body = (await client.get("/api/leagues/not_a_real_league")).json()
        assert body["tier"] is None


class TestLeaguePriceSkipIsCounted:
    """Register E8 / ruling 025 clause 3: a swallow that counts is detection."""

    async def test_effectively_resolved_market_is_counted_not_vanished(
        self, client, mock_db
    ):
        # Leader at 98% having opened at 90% — the existing price-based skip.
        resolved = _mock_market(
            market_id=70,
            name="NBA Most Improved Player",
            market_tier=3,
            llm_sport_category="basketball",
            llm_league="nba",
            outcomes=[
                _mock_outcome(outcome_id=700, name="Runaway", probability=0.98, opening=0.90),
                _mock_outcome(outcome_id=701, name="Other", probability=0.02, rank=2),
            ],
        )
        live = _mock_market(
            market_id=71,
            name="NBA Sixth Man of the Year",
            market_tier=3,
            llm_sport_category="basketball",
            llm_league="nba",
        )
        _league_db(mock_db, [resolved, live])
        body = (await client.get("/api/leagues/basketball_nba")).json()

        awards = body["section_counts"]["awards"]
        # The skipped market is not rendered...
        assert awards["shown"] == 1
        # ...but the page can still say "1 of 2", which is the whole point.
        assert awards["total"] == 2
        assert awards["dropped"] == 1
        assert body["pool_counts"]["dropped"] >= 1


class TestLeagueGamesAndGridAmendment:
    """Alex's 2026-08-11 amendment: games rails ship, and the census counts
    event content and the championship grid."""

    async def test_games_rails_are_served_by_this_route(self, client, mock_db):
        _league_db(
            mock_db,
            [_mock_market(market_id=1, market_tier=3)],
            games=[_mock_event(event_id=11), _mock_event(event_id=12)],
            results=[_mock_event(event_id=13, status="completed", hours_from_now=-48,
                                 home_score=5, away_score=3)],
        )
        body = (await client.get("/api/leagues/basketball_nba")).json()

        assert len(body["upcoming_games"]) == 2
        assert len(body["recent_results"]) == 1
        assert body["record_n"] == 1
        assert body["upcoming_games"][0]["home_win_probability"] == 0.55

    async def test_championship_markets_are_counted_even_though_the_grid_renders_them(
        self, client, mock_db
    ):
        """THE CENSUS HOLE this amendment closed.

        Tier 1/2/4 rows are dropped from the card sections because the GRID renders
        them. They were dropped from the COUNT too, so the league page's centerpiece
        was invisible to the resolver — which is why MLB measured "awards + props"
        and why zero of 29 leagues could reach T3.
        """
        champ = _mock_market(
            market_id=80, name="World Series Winner", market_tier=1,
            llm_sport_category="baseball", llm_league="mlb", external_id="KXMLB-CHAMP",
        )
        award = _mock_market(
            market_id=81, name="Cy Young Winner", market_tier=3,
            llm_sport_category="baseball", llm_league="mlb", external_id="KXMLB-CY",
        )
        _league_db(mock_db, [champ, award])
        body = (await client.get("/api/leagues/baseball_mlb")).json()

        # Still not rendered as cards — the grid is its rendering.
        assert "championship" not in body["sections"]
        # But it COUNTS now.
        assert body["section_counts"]["championship"]["answers"] == 1
        assert body["pool_counts"]["answers"] == 2

    async def test_priced_game_counts_as_an_answer_unpriced_one_does_not(
        self, client, mock_db
    ):
        """A game with a blended number answers "who wins tonight?"; one without
        is a fixture. The ONE resolver makes that call, not this route."""
        _league_db(
            mock_db,
            [],
            games=[
                _mock_event(event_id=21, home_prob=0.61),
                _mock_event(event_id=22, home_prob=None),
            ],
        )
        body = (await client.get("/api/leagues/baseball_mlb")).json()

        assert body["section_counts"]["games"]["answers"] == 1
        assert body["section_counts"]["games"]["dropped"] == 1

    async def test_registered_league_with_only_a_record_is_T0_not_a_404(
        self, client, mock_db
    ):
        """Doctrine A4 + spec §6: settled content feeds the RECORD, so a registered
        league between seasons is a statement page, not a generation-gate hole."""
        _league_db(
            mock_db,
            [],
            results=[_mock_event(event_id=31, status="completed", hours_from_now=-72,
                                 home_score=2, away_score=1)],
        )
        body = (await client.get("/api/leagues/soccer_italy_serie_a")).json()

        assert body["pool_counts"]["answers"] == 0
        assert body["tier"] == "present", "a real league with receipts must render T0"

    async def test_mlb_shaped_league_reaches_the_rich_tier_on_real_content(
        self, client, mock_db
    ):
        """The amendment's PREDICTION, pinned.

        MLB measured T2 in production (awards 8 + props 27 = 2 populated sections)
        and the spec §8 predicted T3. Alex's resolution was "more content kinds", no
        threshold override — so the same league, once the grid and the games rail
        count, must clear `T3_MIN_SECTIONS_POPULATED`.
        """
        markets = (
            [
                _mock_market(
                    market_id=100 + i, name=f"MLB Award {i}", market_tier=3,
                    llm_sport_category="baseball", llm_league="mlb",
                    external_id=f"KXMLB-AW{i}",
                )
                for i in range(4)
            ]
            + [
                _mock_market(
                    market_id=200 + i, name=f"Team {i} Win Total", market_tier=5,
                    category="prop", llm_sport_category="baseball", llm_league="mlb",
                    external_id=f"KXMLB-WT{i}",
                )
                for i in range(4)
            ]
            + [
                _mock_market(
                    market_id=300, name="World Series Winner", market_tier=1,
                    llm_sport_category="baseball", llm_league="mlb",
                    external_id="KXMLB-CHAMP",
                ),
                _mock_market(
                    market_id=301, name="AL Pennant Winner", market_tier=2,
                    llm_sport_category="baseball", llm_league="mlb",
                    external_id="KXMLB-AL",
                ),
                _mock_market(
                    market_id=302, name="NL Pennant Winner", market_tier=2,
                    llm_sport_category="baseball", llm_league="mlb",
                    external_id="KXMLB-NL",
                ),
            ]
        )
        games = [_mock_event(event_id=400 + i, home_prob=0.5 + i / 100) for i in range(4)]
        _league_db(mock_db, markets, games=games)

        body = (await client.get("/api/leagues/baseball_mlb")).json()

        populated = [
            name for name, c in body["section_counts"].items() if c["answers"] >= 3
        ]
        assert "championship" in populated
        assert "games" in populated
        assert body["tier"] == "full", (
            f"expected the rich tier on real content; got {body['tier']} "
            f"with populated sections {sorted(populated)}"
        )


class TestTheRailsServeTheSharedCard:
    """UX-P074 (#1860), ruling 047 — end to end, through the route.

    `test_league_games_rail_probability.py` pins the formatter. This pins that
    the ROUTE assembles it: that the team lookup actually happens, that its
    output reaches both rails, and that a league with no team media still serves
    its games. The unit test cannot see any of that, because the wiring — one
    lookup, two rails — is the part that lives here.
    """

    async def test_games_carry_the_cards_contract_not_just_a_number(self, client, mock_db):
        _league_db(
            mock_db,
            [_mock_market(market_id=1, market_tier=3)],
            games=[_mock_event(event_id=11, home="Boston Red Sox", away="New York Yankees")],
            teams=[_mock_team("Boston Red Sox"), _mock_team("New York Yankees",
                                                            primary="#132448", logo="yankees.png")],
        )
        game = (await client.get("/api/leagues/baseball_mlb")).json()["upcoming_games"][0]

        assert game["sport"] == "baseball_mlb"
        assert game["current_odds"]["home_probability"] == 0.55
        assert game["current_odds"]["away_probability"] == pytest.approx(0.45)
        assert game["home_team_data"]["primary_color"] == "#BD3039"
        assert game["away_team_data"]["logo_small"] == "yankees.png"
        # The census key survives beside the card's.
        assert game["home_win_probability"] == 0.55

    async def test_one_lookup_serves_ALL_THREE_rails(self, client, mock_db):
        """Every rail gets the same chrome from the same query.

        Sequencing exactly five results is the assertion: a second lookup would
        exhaust the mock and fail, and no lookup would leave the later rails
        bare while the upcoming one was decorated.

        #3211 added the third rail, and it is included here rather than tested
        apart precisely because "one lookup, N rails" is the claim — a new rail
        that quietly triggered its own team query would still render correctly
        and would double the page's cost, which is the kind of regression only
        a sequenced mock can see.
        """
        _league_db(
            mock_db,
            [_mock_market(market_id=1, market_tier=3)],
            games=[_mock_event(event_id=11)],
            results=[_mock_event(event_id=12, status="completed", hours_from_now=-48,
                                 home_score=5, away_score=3)],
            unreported=[_mock_event(event_id=13, status="scheduled", hours_from_now=-48)],
            teams=[_mock_team("Boston Red Sox"), _mock_team("New York Yankees")],
        )
        body = (await client.get("/api/leagues/baseball_mlb")).json()

        assert body["upcoming_games"][0]["home_team_data"]["primary_color"] == "#BD3039"
        assert body["recent_results"][0]["home_team_data"]["primary_color"] == "#BD3039"
        assert body["recent_results"][0]["home_score"] == 5
        assert body["unreported_games"][0]["home_team_data"]["primary_color"] == "#BD3039"

    async def test_the_unreported_rail_carries_no_score_and_its_own_cap_flag(
        self, client, mock_db
    ):
        """#3211's rail, end to end through the route.

        The row arrives with `status: scheduled` and NO score — that pairing is
        what the shared card reads to print "No result reported" with nothing
        after it, rather than half a scoreline. And the rail declares its cap
        like the other two, so "showing 6" can never read as "there are 6".
        """
        _league_db(
            mock_db,
            [_mock_market(market_id=1, market_tier=3)],
            games=[],
            results=[],
            unreported=[_mock_event(event_id=13, status="scheduled", hours_from_now=-72)],
            teams=[],
        )
        body = (await client.get("/api/leagues/baseball_mlb")).json()

        assert len(body["unreported_games"]) == 1
        row = body["unreported_games"][0]
        assert row["status"] == "scheduled"
        assert row["home_score"] is None and row["away_score"] is None
        assert body["unreported_games_has_more"] is False
        # It is NOT also filed as a result — that would be the false Final
        # live/048 removed, and it would print the match twice on one page.
        assert body["recent_results"] == []
        # …and it does not count toward the league's record. A match nobody
        # reported is the absence of a receipt, not a receipt.
        assert body["record_n"] == 0
        # But it IS content: a page whose whole fortnight is unreported matches
        # is not an empty page.
        assert body["availability"] == "fresh"

    async def test_no_team_media_still_serves_the_games(self, client, mock_db):
        """Chrome degrades, content does not. A league whose teams we have no
        colours for renders its fixtures — the card falls back to initials."""
        _league_db(
            mock_db,
            [_mock_market(market_id=1, market_tier=3)],
            games=[_mock_event(event_id=11)],
            teams=[],
        )
        game = (await client.get("/api/leagues/baseball_mlb")).json()["upcoming_games"][0]

        assert "home_team_data" not in game
        assert game["current_odds"]["home_probability"] == 0.55

    async def test_an_unpriced_game_carries_no_current_odds_through_the_route(
        self, client, mock_db
    ):
        _league_db(
            mock_db,
            [_mock_market(market_id=1, market_tier=3)],
            games=[_mock_event(event_id=11, home_prob=None)],
            teams=[],
        )
        game = (await client.get("/api/leagues/baseball_mlb")).json()["upcoming_games"][0]

        assert "current_odds" not in game
        assert game["home_win_probability"] is None

    async def test_ONE_BAD_GAME_DOES_NOT_EMPTY_THE_RAIL(self, client, mock_db):
        """Gotcha #42, at the exact place it bites.

        The formatter reads twice as many columns since UX-P074 and the whole
        rails block sits under ONE except — so before the per-item guard, a
        single unreadable row took all sixteen games with it. The broken row
        below is missing `home_team_name`, which is what a partially-loaded ORM
        row looks like.
        """
        broken = _mock_event(event_id=99)
        del broken.home_team_name
        _league_db(
            mock_db,
            [_mock_market(market_id=1, market_tier=3)],
            games=[broken, _mock_event(event_id=11)],
            teams=[],
        )
        body = (await client.get("/api/leagues/baseball_mlb")).json()

        ids = [g["id"] for g in body["upcoming_games"]]
        assert ids == [11], "one unformattable game emptied the whole rail"
