"""Red-first tests for #12232 (Decide 74-A): ``subject_sequence`` grouping kind.

PILLAR: DISCOVER / TRUTH · SHIP: a team's next three games as a Discover card
(three-game strip, time order, within a window) that opens the team page
(``/team/<slug>``), with explicit ``relations`` and ``level`` on its definition.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from app.utils.roundup_containers import (
    CONTAINERS_DATA_DIR,
    ROUNDUP_PRODUCERS,
    RoundupMembers,
    RoundupRefusal,
    build_roundup_producer_from_definition,
    compose_roundup_container,
    compose_roundup_feed_item,
    load_roundup_definition,
)
from app.utils.subject_sequence import (
    CELTICS_NEXT_3_GAMES_DEFINITION,
    CELTICS_NEXT_3_GAMES_SLUG,
    PRODUCER_KIND_SUBJECT_SEQUENCE,
    build_subject_sequence_producer,
    produce_subject_sequence,
    select_subject_sequence,
)

NOW_NOV_8 = datetime(2026, 11, 8, 19, 30, 0, tzinfo=timezone.utc)
OBS_NOV_8 = "2026-11-08T19:20:00Z"


def _make_celtics_fixture_cards() -> list[dict[str, Any]]:
    return [
        # Game 2 (out of order in input to test chronological sorting): Away @ 76ers (50%)
        {
            "id": 15341912,
            "sport": "basketball_nba",
            "status": "scheduled",
            "commence_time": "2026-11-11T01:00:00Z",  # Tue Nov 10, 8:00 PM ET
            "home_team": "Philadelphia 76ers",
            "home_team_name": "Philadelphia 76ers",
            "away_team": "Boston Celtics",
            "away_team_name": "Boston Celtics",
            "home_team_data": {"name": "Philadelphia 76ers", "short_name": "76ers"},
            "away_team_data": {"name": "Boston Celtics", "short_name": "Celtics"},
            "hero_probability": 0.50,
            "hero_probability_away": 0.50,
            "hero_probability_source": "blend",
            "hero_probability_observed_at": OBS_NOV_8,
            "current_odds": {"home": 0.50, "away": 0.50},
        },
        # Game 1: Away @ Bucks (85.5% Celtics)
        {
            "id": 15343971,
            "sport": "basketball_nba",
            "status": "scheduled",
            "commence_time": "2026-11-09T01:00:00Z",  # Sun Nov 8, 8:00 PM ET
            "home_team": "Milwaukee Bucks",
            "home_team_name": "Milwaukee Bucks",
            "away_team": "Boston Celtics",
            "away_team_name": "Boston Celtics",
            "home_team_data": {"name": "Milwaukee Bucks", "short_name": "Bucks"},
            "away_team_data": {"name": "Boston Celtics", "short_name": "Celtics"},
            "hero_probability": 0.145,
            "hero_probability_away": 0.855,
            "hero_probability_source": "blend",
            "hero_probability_observed_at": OBS_NOV_8,
            "current_odds": {"home": 0.145, "away": 0.855},
        },
        # Game 3: Home vs Raptors (64% Celtics)
        {
            "id": 15342527,
            "sport": "basketball_nba",
            "status": "scheduled",
            "commence_time": "2026-11-12T00:00:00Z",  # Wed Nov 11, 7:00 PM ET
            "home_team": "Boston Celtics",
            "home_team_name": "Boston Celtics",
            "away_team": "Toronto Raptors",
            "away_team_name": "Toronto Raptors",
            "home_team_data": {"name": "Boston Celtics", "short_name": "Celtics"},
            "away_team_data": {"name": "Toronto Raptors", "short_name": "Raptors"},
            "hero_probability": 0.64,
            "hero_probability_away": 0.36,
            "hero_probability_source": "blend",
            "hero_probability_observed_at": OBS_NOV_8,
            "current_odds": {"home": 0.64, "away": 0.36},
        },
        # Game 4 (beyond the next 3): Away @ Wizards
        {
            "id": 15197757,
            "sport": "basketball_nba",
            "status": "scheduled",
            "commence_time": "2026-11-15T01:00:00Z",
            "home_team": "Washington Wizards",
            "home_team_name": "Washington Wizards",
            "away_team": "Boston Celtics",
            "away_team_name": "Boston Celtics",
            "home_team_data": {"name": "Washington Wizards", "short_name": "Wizards"},
            "away_team_data": {"name": "Boston Celtics", "short_name": "Celtics"},
            "hero_probability": 0.384,
            "hero_probability_away": 0.616,
            "hero_probability_source": "blend",
            "hero_probability_observed_at": OBS_NOV_8,
            "current_odds": {"home": 0.384, "away": 0.616},
        },
    ]


class TestSubjectSequenceDefinitionAndRegistration:
    """#12232: definition file declares relations, level, and team_slug selector."""

    def test_celtics_definition_loads_with_relations_and_level(self) -> None:
        path = CONTAINERS_DATA_DIR / f"{CELTICS_NEXT_3_GAMES_SLUG}.json"
        assert path.exists()
        defn = load_roundup_definition(path)
        assert defn["slug"] == CELTICS_NEXT_3_GAMES_SLUG
        assert defn["relations"] == ["same_subject", "same_measure", "same_window"]
        assert defn["level"] == "member"
        assert defn["rule"]["producer"] == PRODUCER_KIND_SUBJECT_SEQUENCE
        assert defn["rule"]["team_slug"] == "boston-celtics"
        assert CELTICS_NEXT_3_GAMES_SLUG in ROUNDUP_PRODUCERS

    def test_one_definition_loader_builds_subject_sequence_producer(self) -> None:
        producer = build_roundup_producer_from_definition(
            CELTICS_NEXT_3_GAMES_DEFINITION
        )
        assert producer.slug == CELTICS_NEXT_3_GAMES_SLUG
        assert producer.relations == ("same_subject", "same_measure", "same_window")
        assert producer.level == "member"
        assert producer.destination_href == "/team/boston-celtics"


class TestSubjectSequenceSelectorAndTruthChecks:
    """#12232: selector preserves time order, orientations, and all-or-nothing truth checks."""

    def test_selects_next_three_games_in_chronological_order_with_team_orientation(
        self,
    ) -> None:
        cards = _make_celtics_fixture_cards()
        res = select_subject_sequence(
            cards,
            now=NOW_NOV_8,
            team_slug="boston-celtics",
            team_name="Boston Celtics",
            team_short_name="Celtics",
            count=3,
            window_days=14,
        )
        assert isinstance(res, RoundupMembers)
        # Chronological order (Nov 8 ET, Nov 10 ET, Nov 11 ET), NOT probability order (86%, 50%, 64%)!
        assert [r["event_id"] for r in res.rows] == [15343971, 15341912, 15342527]
        assert [r["rendered_percent"] for r in res.rows] == [86, 50, 64]
        assert [r["label"] for r in res.rows] == [
            "at Bucks \u00b7 Sun Nov 8",
            "at 76ers \u00b7 Tue Nov 10",
            "vs Raptors \u00b7 Wed Nov 11",
        ]

    def test_refuses_when_fewer_than_three_blended_games_in_window(self) -> None:
        cards = _make_celtics_fixture_cards()[:2]
        res = select_subject_sequence(
            cards,
            now=NOW_NOV_8,
            team_slug="boston-celtics",
            team_name="Boston Celtics",
            team_short_name="Celtics",
            count=3,
            window_days=14,
        )
        assert isinstance(res, RoundupRefusal)
        assert ("sequence", "eligible_2_below_count_3") in res.reasons

    def test_refuses_when_one_of_next_three_scheduled_games_is_unpriced_even_with_fourth_game(
        self,
    ) -> None:
        cards = _make_celtics_fixture_cards()
        # Game 2 (Nov 10 @ 76ers, id 15341912) is unpriced, while Game 4 (Nov 14 @ Wizards) is priced.
        cards[0] = {
            **cards[0],
            "hero_probability": None,
            "hero_probability_away": None,
            "hero_probability_source": None,
            "current_odds": None,
        }
        res = select_subject_sequence(
            cards,
            now=NOW_NOV_8,
            team_slug="boston-celtics",
            team_name="Boston Celtics",
            team_short_name="Celtics",
            count=3,
            window_days=14,
        )
        assert isinstance(res, RoundupRefusal)
        assert ("sequence", "unpriced_game_15341912") in res.reasons
        assert ("sequence", "eligible_2_below_count_3") in res.reasons

    def test_excludes_unblended_twin_settled_tbd_out_of_window_and_other_teams(self) -> None:
        base = _make_celtics_fixture_cards()[:3]
        noise = [
            # Unblended twin of Game 1 (opening only)
            {
                **base[1],
                "id": 99001,
                "hero_probability_source": "opening",
            },
            # Completed game
            {
                **base[0],
                "id": 99002,
                "commence_time": "2026-11-08T22:00:00Z",
                "status": "completed",
            },
            # TBD kickoff
            {
                **base[0],
                "id": 99003,
                "commence_time": "2026-11-08T23:00:00Z",
                "start_is_tbd": True,
            },
            # Out of 14-day window
            {
                **base[0],
                "id": 99004,
                "commence_time": "2026-12-01T00:00:00Z",
            },
            # Different teams
            {
                **base[0],
                "id": 99005,
                "commence_time": "2026-11-08T20:00:00Z",
                "home_team": "Los Angeles Lakers",
                "home_team_name": "Los Angeles Lakers",
                "away_team": "Detroit Pistons",
                "away_team_name": "Detroit Pistons",
            },
        ]
        res = select_subject_sequence(
            noise + base,
            now=NOW_NOV_8,
            team_slug="boston-celtics",
            team_name="Boston Celtics",
            team_short_name="Celtics",
            count=3,
            window_days=14,
        )
        assert isinstance(res, RoundupMembers)
        assert [r["event_id"] for r in res.rows] == [15343971, 15341912, 15342527]

    def test_reproducibility_invariant_under_input_permutation(self) -> None:
        cards = _make_celtics_fixture_cards()
        res_a = select_subject_sequence(
            cards,
            now=NOW_NOV_8,
            team_slug="boston-celtics",
            team_name="Boston Celtics",
            team_short_name="Celtics",
            count=3,
            window_days=14,
        )
        res_b = select_subject_sequence(
            list(reversed(cards)),
            now=NOW_NOV_8,
            team_slug="boston-celtics",
            team_name="Boston Celtics",
            team_short_name="Celtics",
            count=3,
            window_days=14,
        )
        assert isinstance(res_a, RoundupMembers)
        assert isinstance(res_b, RoundupMembers)
        assert res_a.rows == res_b.rows
        assert [m["id"] for m in res_a.members] == [m["id"] for m in res_b.members]


class TestSubjectSequenceCardAndContainerComposition:
    """#12232 (62-A): the Discover card opens /team/<slug> and carries strip/sequence metadata."""

    @pytest.mark.asyncio
    async def test_feed_item_opens_team_page_and_preserves_sequence_order(self) -> None:
        cards = _make_celtics_fixture_cards()
        producer = build_subject_sequence_producer(CELTICS_NEXT_3_GAMES_DEFINITION)
        members = await produce_subject_sequence(
            CELTICS_NEXT_3_GAMES_DEFINITION,
            cards,
            now=NOW_NOV_8,
        )
        assert isinstance(members, RoundupMembers)

        feed_item = compose_roundup_feed_item(producer, members)
        assert feed_item is not None
        data = feed_item["data"]
        assert data["collection_ref"]["href"] == "/team/boston-celtics"
        assert data["collection_ref"]["slug"] == CELTICS_NEXT_3_GAMES_SLUG
        assert data["collection_ref"]["collection_count"] == 3
        assert data["roundup"]["relations"] == [
            "same_subject",
            "same_measure",
            "same_window",
        ]
        assert data["roundup"]["level"] == "member"
        assert data["roundup"]["order"] == "sequence"
        assert data["roundup"]["presentation"] == "strip"
        assert [r["event_id"] for r in data["roundup"]["rows"]] == [
            15343971,
            15341912,
            15342527,
        ]

        container = compose_roundup_container(producer, members)
        assert container["state"] == "published"
        assert container["destination_href"] == "/team/boston-celtics"
        assert container["relations"] == [
            "same_subject",
            "same_measure",
            "same_window",
        ]
        assert container["level"] == "member"
        assert len(container["sections"]) == 1
        assert [m["id"] for m in container["sections"][0]["members"]] == [
            15343971,
            15341912,
            15342527,
        ]
