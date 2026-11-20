"""Tests for #9715 & #12221 Stage 3: Playoff series hub, 3-family series context, labeled game-start baseline, and ``advances_to`` graph writer.

Exit criteria covered:
1. A 2026 MLB playoff series page built from stored IDs (``mlb-2026-alwc-bos-nyy``)
   shows its games, series winner, exact series score, total games, and props together.
   A clinched/finished series yields no Discover card while keeping the collection
   page published for its results.
2. Series context is grouped into one coherent section across the three families
   (``series_winner``, ``exact_series_score``, ``series_total_games``), handling both
   complete 3-family inventory and partial inventory.
3. Exhaustive outcome distributions (``series_winner``, ``exact_series_score``) vs
   independent binary rungs (``series_total_games``) carry explicit distribution
   contracts, and ``series_total_games`` ladders are never squeezed to 100%.
4. During-game movement is computed only when comparable timestamped observations
   exist at or before ``game_start`` from the same venue, with an explicit
   ``"since game start"`` baseline label; ``opening_probability`` (market open) and
   ``probability_change_24h`` are never conflated with game start.
5. Settled states (``Won`` / ``Lost``) are preserved and never overwritten by
   live movement logic.
6. First ``advances_to`` writer on the container graph validates through
   ``app.utils.container_graph`` and upserts into ``event_edges`` (``EventEdge``),
   ready for MLB, NBA, and NHL playoffs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from app.utils.roundup_containers import (
    ROUNDUP_PRODUCERS,
    RoundupMembers,
    build_roundup_producer_from_definition,
    compose_roundup_container,
    compose_roundup_feed_item,
    evaluate_roundup_producer,
    load_roundup_definition,
    reset_roundup_cache_for_tests,
)
from app.utils.series_hub import (
    DISTRIBUTION_EXHAUSTIVE,
    DISTRIBUTION_INDEPENDENT_BINARY,
    FAMILY_EXACT_SERIES_SCORE,
    FAMILY_SERIES_TOTAL_GAMES,
    FAMILY_SERIES_WINNER,
    MLB_2026_ALWC_BOS_NYY_DEFINITION,
    MLB_2026_ALWC_BOS_NYY_DEFINITION_PATH,
    MLB_2026_ALWC_BOS_NYY_PRODUCER,
    MLB_2026_ALWC_BOS_NYY_SLUG,
    PRODUCER_KIND_SERIES_HUB,
    build_event_series_context,
    build_series_advances_to_edge,
    classify_series_market_family,
    compute_series_game_start_movement,
    mlb_2026_alwc_bos_nyy,
    produce_series_hub,
    series_family_distribution_contract,
    write_series_advances_to_edges,
)

GAME_1_START = datetime(2026, 9, 30, 0, 0, 0, tzinfo=timezone.utc)
GAME_1_LIVE_NOW = datetime(2026, 9, 30, 1, 15, 0, tzinfo=timezone.utc)


def _alwc_bos_nyy_fixture(
    *,
    g1_status: str = "live",
    g1_home_score: int = 2,
    g1_away_score: int = 1,
    g2_status: str = "scheduled",
    g2_home_score: int | None = None,
    g2_away_score: int | None = None,
    include_if_necessary_g3: bool = False,
    series_market_status: str = "open",
) -> dict[str, Any]:
    """2026 AL Wild Card: Boston Red Sox at New York Yankees built from verified production IDs."""
    games: list[dict[str, Any]] = [
        {
            "id": 15319563,
            "sport": "baseball_mlb",
            "status": g1_status,
            "commence_time": "2026-09-30T00:00:00Z",
            "home_team": "New York Yankees",
            "home_team_name": "New York Yankees",
            "away_team": "Boston Red Sox",
            "away_team_name": "Boston Red Sox",
            "home_score": g1_home_score,
            "away_score": g1_away_score,
            "hero_probability": 0.64,
            "hero_probability_away": 0.36,
            "hero_probability_source": "blend",
        },
        {
            "id": 15321907,
            "sport": "baseball_mlb",
            "status": g2_status,
            "commence_time": "2026-10-01T00:00:00Z",
            "home_team": "New York Yankees",
            "home_team_name": "New York Yankees",
            "away_team": "Boston Red Sox",
            "away_team_name": "Boston Red Sox",
            "home_score": g2_home_score,
            "away_score": g2_away_score,
            "hero_probability": 0.56,
            "hero_probability_away": 0.44,
            "hero_probability_source": "blend",
        },
    ]
    if include_if_necessary_g3:
        games.append(
            {
                "id": 15321999,
                "sport": "baseball_mlb",
                "status": "scheduled",
                "commence_time": "2026-10-02T00:00:00Z",
                "home_team": "New York Yankees",
                "home_team_name": "New York Yankees",
                "away_team": "Boston Red Sox",
                "away_team_name": "Boston Red Sox",
                "home_score": None,
                "away_score": None,
                "hero_probability": 0.55,
                "hero_probability_away": 0.45,
                "hero_probability_source": "blend",
            }
        )
    return {
        "sport": "baseball_mlb",
        "round": "ALWC",
        "best_of": 3,
        "team_a": "Boston Red Sox",
        "team_b": "New York Yankees",
        "games": games,
        "series_markets": [
            {
                "id": 62383730,
                "market_id": 62383730,
                "name": "Series Winner: Boston vs New York Y",
                "external_id": "KXMLBSERIES-26BOSNYYWC",
                "source": "kalshi",
                "status": series_market_status,
                "outcomes": [
                    {
                        "id": 235705604,
                        "outcome_id": 235705604,
                        "name": "New York Y",
                        "external_id": "KXMLBSERIES-26BOSNYYWC-NYY",
                        "probability": 0.64,
                        "opening_probability": 0.55,
                        "probability_change_24h": 0.09,
                    },
                    {
                        "id": 235705605,
                        "outcome_id": 235705605,
                        "name": "Boston",
                        "external_id": "KXMLBSERIES-26BOSNYYWC-BOS",
                        "probability": 0.36,
                        "opening_probability": 0.45,
                        "probability_change_24h": -0.09,
                    },
                ],
            },
            {
                "id": 62455755,
                "market_id": 62455755,
                "name": "Series Exact Score: Boston vs New York Y",
                "external_id": "KXMLBSERIESSCORE-26BOSNYYWC",
                "source": "kalshi",
                "status": series_market_status,
                "outcomes": [
                    {
                        "id": 236000923,
                        "outcome_id": 236000923,
                        "name": "NYY wins 2-0",
                        "external_id": "KXMLBSERIESSCORE-26BOSNYYWC-NYY20",
                        "probability": 0.38,
                        "opening_probability": 0.31,
                    },
                    {
                        "id": 236000924,
                        "outcome_id": 236000924,
                        "name": "NYY wins 2-1",
                        "external_id": "KXMLBSERIESSCORE-26BOSNYYWC-NYY21",
                        "probability": 0.26,
                        "opening_probability": 0.24,
                    },
                    {
                        "id": 236000925,
                        "outcome_id": 236000925,
                        "name": "BOS wins 2-1",
                        "external_id": "KXMLBSERIESSCORE-26BOSNYYWC-BOS21",
                        "probability": 0.21,
                        "opening_probability": 0.23,
                    },
                    {
                        "id": 236000926,
                        "outcome_id": 236000926,
                        "name": "BOS wins 2-0",
                        "external_id": "KXMLBSERIESSCORE-26BOSNYYWC-BOS20",
                        "probability": 0.15,
                        "opening_probability": 0.22,
                    },
                ],
            },
            {
                "id": 62455756,
                "market_id": 62455756,
                "name": "Series Total Games: Boston vs New York Y",
                "external_id": "KXMLBSERIESGAMES-26BOSNYYWC",
                "source": "kalshi",
                "status": series_market_status,
                "outcomes": [
                    {
                        "id": 236000927,
                        "outcome_id": 236000927,
                        "name": "Yes",
                        "external_id": "KXMLBSERIESGAMES-26BOSNYYWC-3",
                        "probability": 0.47,
                        "opening_probability": 0.49,
                    },
                ],
            },
        ],
        "prop_markets": [
            {
                "id": 63367383,
                "market_id": 63367383,
                "name": "Payton Tolle: Outs Recorded O/U 13.5",
                "source": "polymarket",
                "status": "open",
                "event_id": 15319563,
                "outcomes": [
                    {"id": 238772907, "name": "Over", "probability": 0.54},
                    {"id": 238772908, "name": "Under", "probability": 0.46},
                ],
            },
            {
                "id": 63398300,
                "market_id": 63398300,
                "name": "Ben Rice: Home Runs O/U 0.5",
                "source": "polymarket",
                "status": "open",
                "event_id": 15321907,
                "outcomes": [
                    {"id": 238879398, "name": "Under", "probability": 0.805},
                    {"id": 238879399, "name": "Over", "probability": 0.195},
                ],
            },
        ],
        "path_markets": [],
        "snapshots_by_outcome_id": {
            235705604: [
                {
                    "probability": 0.575,
                    "captured_at": "2026-09-29T23:55:00Z",
                    "bookmaker": "kalshi",
                }
            ],
            235705605: [
                {
                    "probability": 0.400,
                    "captured_at": "2026-09-29T23:55:00Z",
                    "bookmaker": "kalshi",
                }
            ],
            236000923: [
                {
                    "probability": 0.325,
                    "captured_at": "2026-09-29T23:55:00Z",
                    "bookmaker": "kalshi",
                }
            ],
            236000927: [
                {
                    "probability": 0.485,
                    "captured_at": "2026-09-29T23:55:00Z",
                    "bookmaker": "kalshi",
                }
            ],
        },
    }


class TestSeriesHub2026MlbPlayoffPageFromStoredIds:
    """Exit 1: A 2026 MLB playoff series page built from stored IDs shows its games, series winner, exact series score, total games, and props together."""

    def test_definition_loads_and_registers_in_roundup_producers(self) -> None:
        assert MLB_2026_ALWC_BOS_NYY_DEFINITION_PATH.exists()
        defn = load_roundup_definition(MLB_2026_ALWC_BOS_NYY_DEFINITION_PATH)
        assert defn["slug"] == MLB_2026_ALWC_BOS_NYY_SLUG
        assert defn["rule"]["producer"] == PRODUCER_KIND_SERIES_HUB
        assert defn["relations"] == ["same_series", "same_event", "path"]
        assert defn["level"] == "member"
        assert defn["rule"]["event_ids"] == [15319563, 15321907]
        assert defn["rule"]["series_market_ids"] == [62383730, 62455755, 62455756]
        assert defn["rule"]["prop_market_ids"] == [63367383, 63398300]
        assert defn["rule"]["path_market_ids"] == []
        assert MLB_2026_ALWC_BOS_NYY_SLUG in ROUNDUP_PRODUCERS

        rebuilt = build_roundup_producer_from_definition(defn)
        assert rebuilt.slug == MLB_2026_ALWC_BOS_NYY_SLUG
        assert rebuilt.relations == ("same_series", "same_event", "path")

    @pytest.mark.asyncio
    async def test_mlb_2026_alwc_bos_nyy_builds_container_and_discover_card_while_live(
        self,
    ) -> None:
        fixture = _alwc_bos_nyy_fixture(include_if_necessary_g3=True)
        selection = await mlb_2026_alwc_bos_nyy(fixture, now=GAME_1_LIVE_NOW)
        assert isinstance(selection, RoundupMembers)
        assert selection.suppress_feed_item is False

        container = compose_roundup_container(
            MLB_2026_ALWC_BOS_NYY_PRODUCER, selection
        )
        assert container is not None
        assert container["state"] == "published"
        assert container["slug"] == MLB_2026_ALWC_BOS_NYY_SLUG
        assert [sec["title"] for sec in container["sections"]] == [
            "Series Outlook",
            "Series Games",
            "Series & Game Props",
        ]

        # Section 1: Series Outlook has all 3 series families with repaired club & rung names
        outlook_sec = container["sections"][0]
        assert [m["id"] for m in outlook_sec["members"]] == [
            62383730,
            62455755,
            62455756,
        ]
        assert [
            m["card"]["series_family"] for m in outlook_sec["members"]
        ] == [
            FAMILY_SERIES_WINNER,
            FAMILY_EXACT_SERIES_SCORE,
            FAMILY_SERIES_TOTAL_GAMES,
        ]
        # Verify #9139 relabeling ran on the series hub members
        winner_card = outlook_sec["members"][0]["card"]
        assert winner_card["name"] == "Series Winner: Boston vs New York Yankees"
        assert winner_card["outcomes"][0]["name"] == "New York Yankees"
        total_games_card = outlook_sec["members"][2]["card"]
        assert (
            total_games_card["outcomes"][0]["name"] == "Over 2.5 total games"
        )
        assert (
            total_games_card["distribution_kind"]
            == DISTRIBUTION_INDEPENDENT_BINARY
        )
        assert (
            total_games_card["sum_note"]
            == "Each line is its own yes-or-no question, so these don't add up to 100%."
        )

        # Section 2: Series Games (15319563, 15321907, plus if-necessary 15321999)
        games_sec = container["sections"][1]
        assert [m["id"] for m in games_sec["members"]] == [
            15319563,
            15321907,
            15321999,
        ]
        assert games_sec["members"][0]["card"]["if_necessary"] is False
        assert games_sec["members"][1]["card"]["if_necessary"] is False
        assert games_sec["members"][2]["card"]["if_necessary"] is True

        # Section 3: Series & Game Props (63367383, 63398300)
        props_sec = container["sections"][2]
        assert [m["id"] for m in props_sec["members"]] == [63367383, 63398300]

        # Verify Discover card composition while live
        feed_item = compose_roundup_feed_item(
            MLB_2026_ALWC_BOS_NYY_PRODUCER, selection
        )
        assert feed_item is not None
        assert feed_item["type"] == "bundle"
        assert feed_item["data"]["collection_ref"]["slug"] == MLB_2026_ALWC_BOS_NYY_SLUG
        rows = feed_item["data"]["roundup"]["rows"]
        assert len(rows) == 3
        assert rows[0]["label"] == "Series Winner · New York Yankees"
        assert rows[0]["rendered_percent"] == 64
        assert rows[0]["baseline_kind"] == "game_start"
        assert rows[0]["baseline_label"] == "since game start"
        assert rows[0]["movement_since_baseline"] == pytest.approx(0.065)
        assert rows[2]["label"] == "Over 2.5 total games"
        assert rows[2]["distribution_kind"] == DISTRIBUTION_INDEPENDENT_BINARY

    @pytest.mark.asyncio
    async def test_clinched_series_yields_no_discover_card_while_keeping_collection_page(
        self,
    ) -> None:
        # Yankees win Game 1 (9-0, 15319563) and Game 2 (9-2, 15321907) -> clinch best-of-3 2-0:
        # 1. Unplayed Game 3 is dropped from Series Games.
        # 2. Collection page stays published for its results.
        # 3. Discover card is refused (feed_item is None) so a finished series never seats on Discover.
        reset_roundup_cache_for_tests()
        fixture = _alwc_bos_nyy_fixture(
            g1_status="completed",
            g1_home_score=9,
            g1_away_score=0,
            g2_status="completed",
            g2_home_score=9,
            g2_away_score=2,
            include_if_necessary_g3=True,
            series_market_status="resolved",
        )
        selection = await mlb_2026_alwc_bos_nyy(fixture, now=GAME_1_LIVE_NOW)
        assert selection.suppress_feed_item is True
        assert compose_roundup_feed_item(MLB_2026_ALWC_BOS_NYY_PRODUCER, selection) is None

        feed_item, container = await evaluate_roundup_producer(
            MLB_2026_ALWC_BOS_NYY_PRODUCER, fixture
        )
        assert feed_item is None
        assert container is not None
        assert container["state"] == "published"
        games_sec = container["sections"][1]
        assert [m["id"] for m in games_sec["members"]] == [15319563, 15321907]


class TestThreeFamilySeriesContextAndBaselineRules:
    """Exits 2–5: 3-family example, partial inventory, missing baseline, market-open vs game-start separation, and settled preservation."""

    def test_three_family_complete_inventory_and_distribution_contracts(
        self,
    ) -> None:
        fixture = _alwc_bos_nyy_fixture()
        enriched, ctx = build_event_series_context(
            fixture["series_markets"],
            event_id=15319563,
            game_start=GAME_1_START,
            event_status="live",
            snapshots_by_outcome_id=fixture["snapshots_by_outcome_id"],
            now=GAME_1_LIVE_NOW,
        )
        assert ctx["inventory_status"] == "complete"
        assert ctx["series_hub_slug"] == MLB_2026_ALWC_BOS_NYY_SLUG
        assert ctx["series_hub_href"] == f"/collections/{MLB_2026_ALWC_BOS_NYY_SLUG}"
        assert ctx["series_score_summary"] == "Red Sox vs Yankees: AL Wild Card Series"
        assert ctx["families_present"] == [
            FAMILY_SERIES_WINNER,
            FAMILY_EXACT_SERIES_SCORE,
            FAMILY_SERIES_TOTAL_GAMES,
        ]
        assert ctx["missing_families"] == []
        assert ctx["baseline_status"] == "ok"
        assert ctx["baseline_kind"] == "game_start"
        assert ctx["baseline_label"] == "since game start"

        by_fam = {m["series_family"]: m for m in enriched}
        assert (
            by_fam[FAMILY_SERIES_WINNER]["distribution_kind"]
            == DISTRIBUTION_EXHAUSTIVE
        )
        assert by_fam[FAMILY_SERIES_WINNER]["normalize_to_unit_sum"] is True
        assert (
            by_fam[FAMILY_EXACT_SERIES_SCORE]["distribution_kind"]
            == DISTRIBUTION_EXHAUSTIVE
        )
        assert (
            by_fam[FAMILY_SERIES_TOTAL_GAMES]["distribution_kind"]
            == DISTRIBUTION_INDEPENDENT_BINARY
        )
        assert (
            by_fam[FAMILY_SERIES_TOTAL_GAMES]["normalize_to_unit_sum"] is False
        )
        assert (
            by_fam[FAMILY_SERIES_TOTAL_GAMES]["sum_note"]
            == "Each line is its own yes-or-no question, so these don't add up to 100%."
        )

        # Verify Yankees outcome movement vs game start (0.640 - 0.575 = +0.065),
        # distinct from opening_probability (0.55 -> +0.09)
        nyy_out = by_fam[FAMILY_SERIES_WINNER]["outcomes"][0]
        assert nyy_out["baseline_status"] == "ok"
        assert nyy_out["baseline_kind"] == "game_start"
        assert nyy_out["baseline_label"] == "since game start"
        assert nyy_out["baseline_probability"] == pytest.approx(0.575)
        assert nyy_out["movement_since_baseline"] == pytest.approx(0.065)
        assert nyy_out["movement_percentage_points"] == pytest.approx(6.5)
        assert nyy_out["market_open_probability"] == pytest.approx(0.55)
        assert nyy_out["market_open_label"] == "market open"

    def test_partial_inventory_and_missing_baseline_never_conflate_market_open(
        self,
    ) -> None:
        """When Exact Series Score is absent and no pre-game snapshot exists, inventory is partial and baseline is missing_baseline (never using opening_probability)."""
        fixture = _alwc_bos_nyy_fixture()
        partial_markets = [
            m
            for m in fixture["series_markets"]
            if m["id"] != 62455755  # drop exact_series_score
        ]
        enriched, ctx = build_event_series_context(
            partial_markets,
            game_start=GAME_1_START,
            event_status="live",
            snapshots_by_outcome_id={},  # no game-start snapshots
            now=GAME_1_LIVE_NOW,
        )
        assert ctx["inventory_status"] == "partial"
        assert ctx["core_families_present"] == [
            FAMILY_SERIES_WINNER,
            FAMILY_SERIES_TOTAL_GAMES,
        ]
        assert ctx["missing_families"] == [FAMILY_EXACT_SERIES_SCORE]
        assert ctx["baseline_status"] == "missing_baseline"
        assert ctx["baseline_kind"] is None
        assert ctx["baseline_label"] is None

        # Even though opening_probability=0.55 and probability_change_24h=0.09 are present,
        # movement_since_baseline MUST be None.
        nyy_out = enriched[0]["outcomes"][0]
        assert nyy_out["baseline_status"] == "missing_baseline"
        assert nyy_out["baseline_kind"] is None
        assert nyy_out["movement_since_baseline"] is None
        assert nyy_out["market_open_probability"] == pytest.approx(0.55)
        assert nyy_out["market_open_label"] == "market open"

    def test_cross_venue_snapshot_is_refused_for_game_start_baseline(self) -> None:
        """A sportsbook snapshot (draftkings) is never compared against a Kalshi series market (#1844)."""
        mov = compute_series_game_start_movement(
            [
                {
                    "outcome_id": 235705604,
                    "name": "New York Yankees",
                    "probability": 0.64,
                }
            ],
            game_start=GAME_1_START,
            event_status="live",
            market_status="open",
            market_source="kalshi",
            snapshots_by_outcome_id={
                235705604: [
                    {
                        "probability": 0.58,
                        "captured_at": "2026-09-29T23:55:00Z",
                        "bookmaker": "draftkings",
                    }
                ]
            },
            now=GAME_1_LIVE_NOW,
        )
        assert mov["baseline_status"] == "missing_baseline"
        assert mov["outcomes"][0]["movement_since_baseline"] is None

    def test_settled_states_preserved_and_never_overwritten_by_live_movement(
        self,
    ) -> None:
        """Settled states (Won / Lost) are preserved and never overwritten even when pre-game snapshots exist."""
        mov = compute_series_game_start_movement(
            [
                {
                    "outcome_id": 236000923,
                    "name": "NYY wins 2-0",
                    "probability": 1.0,
                    "settled": True,
                    "is_winner": True,
                },
                {
                    "outcome_id": 236000926,
                    "name": "BOS wins 2-0",
                    "probability": None,
                    "settled": True,
                    "is_winner": False,
                },
            ],
            game_start=GAME_1_START,
            event_status="live",
            market_status="settled",
            market_source="kalshi",
            snapshots_by_outcome_id={
                236000923: [
                    {
                        "probability": 0.325,
                        "captured_at": "2026-09-29T23:55:00Z",
                        "bookmaker": "kalshi",
                    }
                ],
                236000926: [
                    {
                        "probability": 0.220,
                        "captured_at": "2026-09-29T23:55:00Z",
                        "bookmaker": "kalshi",
                    }
                ],
            },
            now=GAME_1_LIVE_NOW,
        )
        assert mov["baseline_status"] == "settled_preserved"
        assert mov["outcomes"][0]["settled_state"] == "Won"
        assert mov["outcomes"][0]["movement_since_baseline"] is None
        assert mov["outcomes"][1]["settled_state"] == "Lost"
        assert mov["outcomes"][1]["movement_since_baseline"] is None


class TestContainerGraphAdvancesToWriterAndPlayoffReadiness:
    """Exit 6: First ``advances_to`` writer on the container graph and NBA/NHL playoff readiness."""

    @pytest.mark.asyncio
    async def test_write_series_advances_to_edges_for_mlb_nba_and_nhl(
        self,
    ) -> None:
        sink: list[dict[str, Any]] = []
        edges = [
            build_series_advances_to_edge(
                from_series_slug="mlb-2026-alwc-bos-nyy",
                to_series_slug="mlb-2026-alds-yankees-guardians",
                sport="baseball_mlb",
                from_round="ALWC",
                to_round="ALDS",
            ),
            build_series_advances_to_edge(
                from_series_slug="nba-2027-r1-celtics-heat",
                to_series_slug="nba-2027-r2-east-semis-1",
                sport="basketball_nba",
                from_round="R1",
                to_round="R2",
            ),
            build_series_advances_to_edge(
                from_series_slug="nhl-2027-r1-rangers-devils",
                to_series_slug="nhl-2027-r2-metro-final",
                sport="icehockey_nhl",
                from_round="R1",
                to_round="R2",
            ),
        ]
        written = await write_series_advances_to_edges(sink, edges)
        assert len(written) == 3
        assert len(sink) == 3
        for row in written:
            assert row["parent_type"] == "container"
            assert row["child_type"] == "container"
            assert row["kind"] == "advances_to"
            assert row["edge_class"] is None
            assert row["source"] == "register"
            assert row["confidence"] == 1.0
            assert row["parent_id"] > 0
            assert row["child_id"] > 0
            assert row["parent_id"] != row["child_id"]

    @pytest.mark.asyncio
    async def test_write_series_advances_to_edges_executes_against_event_edges_table_and_mapping_branch(
        self,
    ) -> None:
        from sqlalchemy.dialects import postgresql
        from app.models.models import EventEdge

        executed_stmts: list[Any] = []

        class _RecordingSession:
            async def execute(self, stmt: Any) -> None:
                executed_stmts.append(stmt)

        written = await write_series_advances_to_edges(
            _RecordingSession(),
            [
                {
                    "from_series_slug": "mlb-2026-alwc-bos-nyy",
                    "to_series_slug": "mlb-2026-alds-yankees-guardians",
                    "sport": "baseball_mlb",
                    "from_round": "ALWC",
                    "to_round": "ALDS",
                }
            ],
        )
        assert len(written) == 1
        assert written[0]["parent_id"] > 0
        assert written[0]["child_id"] > 0
        assert len(executed_stmts) == 1
        stmt = executed_stmts[0]
        assert stmt.table.name == EventEdge.__tablename__
        sql = str(stmt.compile(dialect=postgresql.dialect()))
        assert "INSERT INTO event_edges" in sql
        assert "ON CONFLICT (parent_type, parent_id, child_type, child_id, kind) DO NOTHING" in sql

    def test_self_advancement_edge_is_refused(self) -> None:
        with pytest.raises(ValueError, match="cannot advance to itself"):
            build_series_advances_to_edge(
                from_series_slug="mlb-2026-alwc-bos-nyy",
                to_series_slug="mlb-2026-alwc-bos-nyy",
            )

    @pytest.mark.asyncio
    async def test_nba_best_of_7_series_hub_and_independent_binary_rungs(
        self,
    ) -> None:
        """Verify April NBA/NHL best-of-7 series readiness with multi-rung Series Total Games (Over 4.5 / 5.5 / 6.5)."""
        nba_def = {
            "slug": "nba-2027-r1-bos-mia",
            "membership": "series_hub",
            "kind": "roundup",
            "relations": ["same_series", "same_event", "path"],
            "level": "member",
            "kicker": "NBA FIRST ROUND",
            "name": "Celtics vs Heat: Eastern Conference First Round",
            "category": "nba",
            "tag": "NBA",
            "section_title": "Series Outlook",
            "footer": "Best-of-seven playoff series.",
            "rule": {
                "producer": "series_hub",
                "sport": "basketball_nba",
                "round": "R1",
                "best_of": 7,
                "series_code": "27BOSMIAR1",
                "team_a": "Boston Celtics",
                "team_b": "Miami Heat",
            },
        }
        nba_fixture = {
            "sport": "basketball_nba",
            "round": "R1",
            "best_of": 7,
            "team_a": "Boston Celtics",
            "team_b": "Miami Heat",
            "games": [
                {
                    "id": 16000001,
                    "sport": "basketball_nba",
                    "status": "scheduled",
                    "commence_time": "2027-04-18T19:00:00Z",
                    "home_team": "Boston Celtics",
                    "away_team": "Miami Heat",
                }
            ],
            "series_markets": [
                {
                    "id": 70000001,
                    "name": "Series Total Games: Miami vs Boston",
                    "external_id": "KXNBASERIESGAMES-27BOSMIAR1",
                    "source": "kalshi",
                    "status": "open",
                    "outcomes": [
                        {
                            "id": 700000011,
                            "name": "Over 4.5 total games",
                            "external_id": "KXNBASERIESGAMES-27BOSMIAR1-5",
                            "probability": 0.78,
                        },
                        {
                            "id": 700000012,
                            "name": "Over 5.5 total games",
                            "external_id": "KXNBASERIESGAMES-27BOSMIAR1-6",
                            "probability": 0.51,
                        },
                        {
                            "id": 700000013,
                            "name": "Yes",
                            "external_id": "KXNBASERIESGAMES-27BOSMIAR1-7",
                            "probability": 0.24,
                        },
                    ],
                }
            ],
        }
        selection = await produce_series_hub(nba_def, nba_fixture)
        assert isinstance(selection, RoundupMembers)
        assert selection.suppress_feed_item is False
        games_card = selection.sections[0]["members"][0]["card"]
        assert games_card["series_family"] == FAMILY_SERIES_TOTAL_GAMES
        assert (
            games_card["distribution_kind"] == DISTRIBUTION_INDEPENDENT_BINARY
        )
        # Rung 7 bare "Yes" relabeled to "Over 6.5 total games", and probabilities
        # (0.78 + 0.51 + 0.24 = 1.53) are NEVER squeezed to 1.0!
        assert [o["name"] for o in games_card["outcomes"]] == [
            "Over 4.5 total games",
            "Over 5.5 total games",
            "Over 6.5 total games",
        ]
        assert [o["probability"] for o in games_card["outcomes"]] == [
            0.78,
            0.51,
            0.24,
        ]

    @pytest.mark.asyncio
    async def test_held_licence_blocks_auto_promotion_while_kill_switch_and_suspension_halt_producer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify HELD blocks automated promotion while kill switch or SUSPENDED halts evaluate_roundup_producer."""
        from app.utils.grouping_licences import (
            is_kind_licensed_for_promotion,
            load_grouping_licences,
            suspend_grouping_kind,
        )
        from app.utils.series_hub import series_hub_enabled

        registry = load_grouping_licences()
        assert registry["kinds"]["series_hub"]["status"] == "HELD"
        assert registry["kinds"]["series_hub"]["mode"] == "hand_defined"
        assert is_kind_licensed_for_promotion(registry, "series_hub") is False

        # Kill switch SERIES_HUB_ENABLED=false halts producer evaluation
        monkeypatch.setenv("SERIES_HUB_ENABLED", "false")
        assert series_hub_enabled() is False
        reset_roundup_cache_for_tests()
        fixture = _alwc_bos_nyy_fixture(
            g1_status="completed",
            g1_home_score=9,
            g1_away_score=0,
            g2_status="completed",
            g2_home_score=9,
            g2_away_score=2,
            series_market_status="resolved",
        )
        feed_item, container = await evaluate_roundup_producer(
            MLB_2026_ALWC_BOS_NYY_PRODUCER, fixture
        )
        assert feed_item is None
        assert container is None

        # produce_series_hub and build_event_series_context also refuse directly when SERIES_HUB_ENABLED=false
        direct_refusal = await produce_series_hub(
            MLB_2026_ALWC_BOS_NYY_DEFINITION, fixture
        )
        assert getattr(direct_refusal, "reasons", None) == (
            ("series_hub", "series_hub_disabled"),
        )
        _disabled_mkts, disabled_ctx = build_event_series_context(
            fixture["series_markets"],
            event_id=15319563,
            game_start=GAME_1_START,
            event_status="live",
        )
        assert disabled_ctx is None

        # SUSPENDED licence also halts producer evaluation even when SERIES_HUB_ENABLED=true
        monkeypatch.setenv("SERIES_HUB_ENABLED", "true")
        assert series_hub_enabled() is True
        suspended_reg = suspend_grouping_kind(
            registry,
            "series_hub",
            wrong_card_slug=MLB_2026_ALWC_BOS_NYY_SLUG,
            reason="settled_member_served",
        )
        reset_roundup_cache_for_tests()
        feed_item_susp, container_susp = await evaluate_roundup_producer(
            MLB_2026_ALWC_BOS_NYY_PRODUCER,
            fixture,
            licences_registry=suspended_reg,
        )
        assert feed_item_susp is None
        assert container_susp is None

    def test_series_context_exception_in_events_route_is_guarded(
        self,
    ) -> None:
        """Verify _build_related_futures wraps build_event_series_context in a try/except fallback."""
        from pathlib import Path
        import app.routes.events as events_mod

        src = Path(events_mod.__file__).read_text(encoding="utf-8")
        assert "_, _series_context = build_event_series_context(" in src
        assert 'related-futures %s: series_context refused on error (%s)' in src
        assert "_series_context = None" in src

