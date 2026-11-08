"""Red-first tests for #12232 (Decide 74-A): ``subject_sequence`` grouping kind.

PILLAR: DISCOVER / TRUTH · SHIP: a team's next three games as a Discover card
(three-game strip, time order, within a window) that opens the team page
(``/team/<slug>``), with explicit ``relations`` and ``level`` on its definition.
"""

from __future__ import annotations

from datetime import datetime, timezone
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
        assert producer.destination_href == "/sport/basketball/nba/team/boston-celtics"


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
        assert (
            data["collection_ref"]["href"]
            == "/sport/basketball/nba/team/boston-celtics"
        )
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
        assert (
            container["destination_href"]
            == "/sport/basketball/nba/team/boston-celtics"
        )
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


class _AsyncSessionAdapter:
    """Thin async wrapper around an in-memory SQLite ``Session`` for ``_hydrate_event_cards``."""

    def __init__(self, session: Any) -> None:
        self._s = session

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        res = self._s.execute(statement, *args)
        for obj in list(self._s.identity_map.values()):
            for attr in ("commence_time", "captured_at", "completed_at"):
                val = getattr(obj, attr, None)
                if isinstance(val, datetime) and val.tzinfo is None:
                    setattr(obj, attr, val.replace(tzinfo=timezone.utc))
        return res


class TestSubjectSequenceDatabaseLoader:
    """#12232: ``produce_subject_sequence`` through a database session hydrates via ``_hydrate_event_cards`` + ``folded_card_numbers_batch``."""

    @pytest.mark.asyncio
    async def test_produce_subject_sequence_through_session_hydrates_and_folds_twins(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from datetime import timedelta
        from unittest.mock import AsyncMock, patch

        from sqlalchemy import create_engine, select
        from sqlalchemy.dialects.postgresql import ARRAY, JSONB
        from sqlalchemy.ext.compiler import compiles
        from sqlalchemy.orm import Session

        @compiles(JSONB, "sqlite")
        def _jsonb_on_sqlite(type_: Any, compiler: Any, **kw: Any) -> str:
            return "JSON"

        @compiles(ARRAY, "sqlite")
        def _array_on_sqlite(type_: Any, compiler: Any, **kw: Any) -> str:
            return "JSON"

        from app.models.models import Base, Event, OddsSnapshot, Sport, Team
        from app.routes.containers import _hydrate_event_cards
        from app.utils.hero_probability import resolve_hero

        now = NOW_NOV_8
        hero_stamp = (now - timedelta(minutes=10)).isoformat()
        odds_captured_dt = now - timedelta(minutes=25)

        eng = create_engine("sqlite://")
        Base.metadata.create_all(eng)

        nba_sport_id = 41
        nhl_sport_id = 42

        def _portable_odds_query(event_ids: list[int]) -> Any:
            return select(OddsSnapshot).where(OddsSnapshot.event_id.in_(event_ids))

        with (
            patch("app.routes.events._load_gei_percentiles", new=AsyncMock(return_value={})),
            patch("app.routes.events.latest_odds_per_bookmaker_query", new=_portable_odds_query),
            patch("app.routes.events._team_cache", {}),
            patch("app.routes.events._team_cache_time", 0.0),
            Session(eng, expire_on_commit=False) as s,
        ):
            s.add(Sport(id=nba_sport_id, key="basketball_nba", name="NBA", group="Basketball"))
            s.add(Sport(id=nhl_sport_id, key="icehockey_nhl", name="NHL", group="Ice Hockey"))

            teams = [
                (1, nba_sport_id, "Boston Celtics", "BOS"),
                (2, nba_sport_id, "Milwaukee Bucks", "MIL"),
                (3, nba_sport_id, "Philadelphia 76ers", "PHI"),
                (4, nba_sport_id, "Toronto Raptors", "TOR"),
                (5, nba_sport_id, "Washington Wizards", "WAS"),
            ]
            for tid, sid, tname, abbr in teams:
                s.add(
                    Team(
                        id=tid,
                        sport_id=sid,
                        name=tname,
                        abbreviation=abbr,
                        logo_url=f"https://cdn.example/{abbr.lower()}.png",
                        logo_url_small=f"https://cdn.example/{abbr.lower()}-sm.png",
                    )
                )

            # Three upcoming Celtics NBA games (plus a 4th later game, plus a non-NBA row with matching team name)
            games = [
                # Game 2 (Nov 10 ET, away at 76ers): blend home=0.50 (Celtics away=0.50), books home=0.62
                (
                    15341912,
                    nba_sport_id,
                    "Philadelphia 76ers",
                    "Boston Celtics",
                    datetime(2026, 11, 11, 1, 0, tzinfo=timezone.utc),
                    0.50,
                    0.62,
                ),
                # Game 1 (Nov 8 ET, away at Bucks): blend home=0.145 (Celtics away=0.855), books home=0.30
                (
                    15343971,
                    nba_sport_id,
                    "Milwaukee Bucks",
                    "Boston Celtics",
                    datetime(2026, 11, 9, 1, 0, tzinfo=timezone.utc),
                    0.145,
                    0.30,
                ),
                # Game 3 (Nov 11 ET, home vs Raptors): blend home=0.645 (Celtics home=0.645), books home=0.75
                (
                    15342527,
                    nba_sport_id,
                    "Boston Celtics",
                    "Toronto Raptors",
                    datetime(2026, 11, 12, 0, 0, tzinfo=timezone.utc),
                    0.645,
                    0.75,
                ),
                # Non-NBA event with matching team name that must be filtered out after hydrating on card["sport"]
                (
                    15999999,
                    nhl_sport_id,
                    "Boston Celtics",
                    "Toronto Raptors",
                    datetime(2026, 11, 9, 0, 30, tzinfo=timezone.utc),
                    0.55,
                    0.55,
                ),
            ]
            for eid, sid, home_full, away_full, tipoff, blend_home, book_home in games:
                s.add(
                    Event(
                        id=eid,
                        sport_id=sid,
                        home_team_name=home_full,
                        away_team_name=away_full,
                        commence_time=tipoff,
                        status="scheduled",
                        win_probability_sources={
                            "betting": {"value": blend_home, "updated_at": hero_stamp},
                            "kalshi": {"value": blend_home, "updated_at": hero_stamp},
                            "polymarket": {"value": blend_home, "updated_at": hero_stamp},
                        },
                    )
                )
                s.add(
                    OddsSnapshot(
                        event_id=eid,
                        bookmaker="fanduel",
                        home_win_probability=book_home,
                        away_win_probability=round(1.0 - book_home, 4),
                        captured_at=odds_captured_dt,
                    )
                )
            s.commit()

            fake_db = _AsyncSessionAdapter(s)
            hydrated_cards, failed = await _hydrate_event_cards(
                fake_db, [15343971, 15341912, 15342527]
            )
            assert failed == {}

            outcome = await produce_subject_sequence(
                CELTICS_NEXT_3_GAMES_DEFINITION,
                fake_db,
                now=now,
            )
            assert isinstance(outcome, RoundupMembers)
            assert [r["event_id"] for r in outcome.rows] == [15343971, 15341912, 15342527]
            assert [r["rendered_percent"] for r in outcome.rows] == [86, 50, 65]
            assert [r["label"] for r in outcome.rows] == [
                "at Bucks \u00b7 Sun Nov 8",
                "at 76ers \u00b7 Tue Nov 10",
                "vs Raptors \u00b7 Wed Nov 11",
            ]

            for row, member in zip(outcome.rows, outcome.members):
                eid = row["event_id"]
                ev = s.get(Event, eid)
                hero = resolve_hero(ev)
                assert hero is not None
                assert hero.source == "blend"
                expected_celtics_prob = (
                    hero.home_probability
                    if ev.home_team_name == "Boston Celtics"
                    else hero.away_probability
                )
                assert row["probability"] == pytest.approx(expected_celtics_prob)
                assert row["observed_at"] == member["card"]["hero_probability_observed_at"] == hero_stamp
                assert isinstance(member["card"]["home_team"], str)
                assert isinstance(member["card"]["sport"], str)
                assert member["card"]["sport"] == "basketball_nba"

            # All-or-nothing refusal if _hydrate_event_cards fails on any candidate:
            async def _failing_hydrate(_db: Any, _ids: Any) -> tuple[dict[int, Any], dict[Any, str]]:
                return (
                    {k: v for k, v in hydrated_cards.items() if k != 15341912},
                    {("event", 15341912): "hydration_error"},
                )

            monkeypatch.setattr(
                "app.routes.containers._hydrate_event_cards",
                _failing_hydrate,
            )
            refused = await produce_subject_sequence(
                CELTICS_NEXT_3_GAMES_DEFINITION,
                fake_db,
                now=now,
            )
            assert isinstance(refused, RoundupRefusal)
            assert refused.reasons == (("sequence", "hydrate_failed_1"),)

