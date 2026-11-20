"""#13144 — Strict same-sport event -> team FK linking on saved fixtures.

Production audit found 2,168 unlinked event team names across the next 7 days
(276 of them women's college basketball teams we already hold in ``teams``).
Three structural causes:
1. ``event_registry.find_or_create_event`` never resolved ``home_team_id`` /
   ``away_team_id`` on insert.
2. ``tasks/sports.py`` ran exact case-sensitive ``Team.name.in_(...)`` over an
   unordered ``.limit(200)`` query across all historical events, starving
   upcoming slates behind old unlinked rows and missing ``St``/``State`` and
   diacritic variants.
3. No dry-run-first upcoming-event linker existed.

These tests pin the code-only fix on saved fixtures (zero production reads or
writes).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services.event_registry import (
    EventClaim,
    EventIdentity,
    _sport_id_cache,
    find_or_create_event,
)
from app.utils.event_team_linking import (
    build_sport_team_index,
    event_team_names_equivalent,
    expand_event_team_key,
    link_event_sides_from_index,
    link_unlinked_events_for_sport,
    link_unlinked_upcoming_events,
    normalize_event_team_key,
    resolve_event_team,
)
from app.utils.team_binding_invariant import (
    CROSS_CLUB,
    WRONG_SPORT,
    binding_defect,
)
from tests.test_event_registry import _FakeRegistrySession

FIXED_NOW = datetime(2025, 11, 20, 14, 0, tzinfo=timezone.utc)
WNCAAB_SPORT_ID = 41
NCAAB_SPORT_ID = 12
SOCCER_SPORT_ID = 77
MLS_SPORT_ID = 88


def _team(team_id: int, name: str, sport_id: int, *, alternate_names=None):
    return SimpleNamespace(
        id=team_id,
        name=name,
        sport_id=sport_id,
        alternate_names=alternate_names,
    )


def _event(
    event_id: int,
    sport_id: int,
    home: str,
    away: str,
    commence_time: datetime,
    *,
    home_team_id=None,
    away_team_id=None,
):
    return SimpleNamespace(
        id=event_id,
        sport_id=sport_id,
        home_team_name=home,
        away_team_name=away,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        commence_time=commence_time,
    )


class _ScalarResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _InMemoryLinkingSession:
    """Deterministic fake AsyncSession enforcing WHERE, ORDER BY, and LIMIT."""

    def __init__(self, *, teams, events):
        self.teams = list(teams)
        self.events = list(events)

    async def execute(self, stmt):
        sql = str(stmt)
        params = stmt.compile().params

        if "FROM teams" in sql:
            sid = params.get("sport_id_1")
            rows = [t for t in self.teams if t.sport_id == sid]
            return _ScalarResult(rows)

        if "SELECT DISTINCT events.sport_id" in sql:
            cutoff = params.get("commence_time_1")
            horizon = params.get("commence_time_2")
            sids = sorted(
                {
                    e.sport_id
                    for e in self.events
                    if (e.home_team_id is None or e.away_team_id is None)
                    and (cutoff is None or e.commence_time >= cutoff)
                    and (horizon is None or e.commence_time <= horizon)
                }
            )
            return _ScalarResult(sids)

        if "FROM events" in sql:
            sid = params.get("sport_id_1")
            cutoff = params.get("commence_time_1")
            horizon = params.get("commence_time_2")
            rows = [
                e
                for e in self.events
                if e.sport_id == sid
                and (e.home_team_id is None or e.away_team_id is None)
                and (cutoff is None or e.commence_time >= cutoff)
                and (horizon is None or e.commence_time <= horizon)
            ]
            rows.sort(key=lambda e: e.commence_time)
            limit = getattr(stmt, "_limit_clause", None)
            if limit is not None and getattr(limit, "value", None) is not None:
                rows = rows[: int(limit.value)]
            return _ScalarResult(rows)

        raise AssertionError(f"Unexpected SQL: {sql}")


class TestCanonicalEquivalence:
    @pytest.mark.parametrize(
        "name_a, name_b, expected",
        [
            ("Penn State Lady Lions", "Penn State Lady Lions", True),
            ("Sacramento St Hornets", "Sacramento State Hornets", True),
            ("Murray St Racers", "Murray State Racers", True),
            ("Mt. St. Mary's Mountaineers", "Mount St Mary's Mountaineers", True),
            ("St. Louis Cardinals", "St Louis Cardinals", True),
            ("Grêmio", "Gremio", True),
            ("Atlético Madrid", "Atletico Madrid", True),
            # Leading St is Saint, never State
            ("St. Louis Billikens", "State Louis Billikens", False),
            # Namesake schools always refuse in both directions
            ("Michigan Wolverines", "Michigan State Spartans", False),
            ("Michigan State Spartans", "Michigan Wolverines", False),
            ("Oregon Ducks", "Oregon State Beavers", False),
            ("Texas Longhorns", "Texas A&M Aggies", False),
            ("Miami Hurricanes", "Miami (OH) RedHawks", False),
            ("Georgia Bulldogs", "Georgia Tech Yellow Jackets", False),
            ("Georgia Bulldogs", "Georgia State Panthers", False),
            ("Loyola Chicago Ramblers", "Loyola Maryland Greyhounds", False),
            # Number-only differences always refuse (decision 286: B)
            ("Columbus Crew 2", "Columbus Crew", False),
            ("Columbus Crew", "Columbus Crew 2", False),
            ("Bayern Munich 2", "Bayern Munich", False),
        ],
    )
    def test_equivalence_table(self, name_a, name_b, expected):
        assert event_team_names_equivalent(name_a, name_b) is expected
        if expected:
            assert binding_defect(name_a, name_b, WNCAAB_SPORT_ID, WNCAAB_SPORT_ID) is None
        else:
            assert binding_defect(name_a, name_b, WNCAAB_SPORT_ID, WNCAAB_SPORT_ID) == CROSS_CLUB

    def test_key_normalization_preserves_digits(self):
        assert normalize_event_team_key("Columbus Crew 2") == "columbus crew 2"
        assert expand_event_team_key("Sacramento St Hornets") == "sacramento state hornets"


class TestSportTeamIndexSafety:
    def test_cross_sport_isolation(self):
        mens_team = _team(1001, "Penn State Nittany Lions", NCAAB_SPORT_ID)
        womens_index = build_sport_team_index(WNCAAB_SPORT_ID, [mens_team])
        assert (
            resolve_event_team(
                "Penn State Nittany Lions",
                womens_index,
                side="home",
                event_sport_id=WNCAAB_SPORT_ID,
                source="test",
            )
            is None
        )
        # Even if a caller passes the wrong sport's index, event_sport_id refuses it
        mens_index = build_sport_team_index(NCAAB_SPORT_ID, [mens_team])
        assert (
            resolve_event_team(
                "Penn State Nittany Lions",
                mens_index,
                side="home",
                event_sport_id=WNCAAB_SPORT_ID,
                source="test",
            )
            is None
        )
        assert (
            binding_defect(
                "Penn State Nittany Lions",
                "Penn State Nittany Lions",
                NCAAB_SPORT_ID,
                WNCAAB_SPORT_ID,
            )
            == WRONG_SPORT
        )

    def test_ambiguous_duplicate_teams_in_same_sport_refuse_and_stay_null(self):
        dup_a = _team(2001, "Sacramento St Hornets", WNCAAB_SPORT_ID)
        dup_b = _team(2002, "Sacramento State Hornets", WNCAAB_SPORT_ID)
        index = build_sport_team_index(WNCAAB_SPORT_ID, [dup_a, dup_b])
        # Exact basic match for "Sacramento St Hornets" is still unique (dup_a)
        assert (
            resolve_event_team(
                "Sacramento St Hornets",
                index,
                side="home",
                event_sport_id=WNCAAB_SPORT_ID,
                source="test",
            )
            is dup_a
        )
        # Two rows sharing a basic key ("St. Louis Cardinals" vs "St Louis Cardinals",
        # #7021 / Fable review): exact spelling links to the exact-spelled row,
        # while a non-exact spelling against the ambiguous pair still refuses,
        # and byte-identical duplicates refuse even on exact match.
        cards_dot = _team(2003, "St. Louis Cardinals", WNCAAB_SPORT_ID)
        cards_nodot = _team(2004, "St Louis Cardinals", WNCAAB_SPORT_ID)
        basic_pair = build_sport_team_index(WNCAAB_SPORT_ID, [cards_dot, cards_nodot])
        assert (
            resolve_event_team(
                "St. Louis Cardinals",
                basic_pair,
                side="home",
                event_sport_id=WNCAAB_SPORT_ID,
                source="test",
            )
            is cards_dot
        )
        assert (
            resolve_event_team(
                "St Louis Cardinals",
                basic_pair,
                side="home",
                event_sport_id=WNCAAB_SPORT_ID,
                source="test",
            )
            is cards_nodot
        )
        assert (
            resolve_event_team(
                "St.Louis Cardinals",
                basic_pair,
                side="home",
                event_sport_id=WNCAAB_SPORT_ID,
                source="test",
            )
            is None
        )
        byte_dup_1 = _team(2007, "Oregon St Beavers", WNCAAB_SPORT_ID)
        byte_dup_2 = _team(2008, "Oregon St Beavers", WNCAAB_SPORT_ID)
        byte_ambig = build_sport_team_index(WNCAAB_SPORT_ID, [byte_dup_1, byte_dup_2])
        assert (
            resolve_event_team(
                "Oregon St Beavers",
                byte_ambig,
                side="home",
                event_sport_id=WNCAAB_SPORT_ID,
                source="test",
            )
            is None
        )
        # Expanded-only lookup collapsing two rows refuses
        dup_exp_1 = _team(2005, "Mt. St. Mary's Mountaineers", WNCAAB_SPORT_ID)
        dup_exp_2 = _team(2006, "Mount State Mary's Mountaineers", WNCAAB_SPORT_ID)
        exp_ambig = build_sport_team_index(WNCAAB_SPORT_ID, [dup_exp_1, dup_exp_2])
        assert (
            resolve_event_team(
                "Mount St. Mary's Mountaineers",
                exp_ambig,
                side="home",
                event_sport_id=WNCAAB_SPORT_ID,
                source="test",
            )
            is None
        )

    def test_contaminated_alternate_names_are_never_used(self):
        arkansas = _team(
            3001,
            "Arkansas Razorbacks",
            WNCAAB_SPORT_ID,
            alternate_names=["Central Arkansas Bears", "C Arkansas"],
        )
        index = build_sport_team_index(WNCAAB_SPORT_ID, [arkansas])
        assert (
            resolve_event_team(
                "Central Arkansas Bears",
                index,
                side="away",
                event_sport_id=WNCAAB_SPORT_ID,
                source="test",
            )
            is None
        )

    def test_existing_team_id_is_never_overwritten(self):
        sac = _team(1126, "Sacramento State Hornets", WNCAAB_SPORT_ID)
        mur = _team(1141, "Murray State Racers", WNCAAB_SPORT_ID)
        index = build_sport_team_index(WNCAAB_SPORT_ID, [sac, mur])
        evt = _event(
            9001,
            WNCAAB_SPORT_ID,
            "Sacramento St Hornets",
            "Murray St Racers",
            FIXED_NOW + timedelta(hours=3),
            home_team_id=99999,
            away_team_id=None,
        )
        links = link_event_sides_from_index(evt, index, source="test")
        assert evt.home_team_id == 99999
        assert evt.away_team_id == 1141
        assert len(links) == 1
        assert links[0]["side"] == "away"


class TestUpcomingFirstAndDryRun:
    @pytest.mark.asyncio
    async def test_historical_unlinked_rows_cannot_starve_upcoming_wncaab_slate(self):
        sac = _team(1126, "Sacramento State Hornets", WNCAAB_SPORT_ID)
        mur = _team(1141, "Murray State Racers", WNCAAB_SPORT_ID)

        # 350 historical unlinked events from 2024 that previously filled .limit(200)
        old_events = [
            _event(
                1000 + i,
                WNCAAB_SPORT_ID,
                "Sacramento St Hornets",
                "Murray St Racers",
                FIXED_NOW - timedelta(days=300 + i),
            )
            for i in range(350)
        ]
        upcoming = _event(
            5001,
            WNCAAB_SPORT_ID,
            "Sacramento St Hornets",
            "Murray St Racers",
            FIXED_NOW + timedelta(hours=6),
        )
        session = _InMemoryLinkingSession(
            teams=[sac, mur],
            events=old_events + [upcoming],
        )

        stats = await link_unlinked_events_for_sport(
            session,
            sport_id=WNCAAB_SPORT_ID,
            now=FIXED_NOW,
            lookback_days=1,
            limit=200,
            source="sports_poll",
            dry_run=False,
        )
        assert upcoming.home_team_id == 1126
        assert upcoming.away_team_id == 1141
        assert stats["events_scanned"] == 1
        assert stats["sides_linked"] == 2
        # Old 2024 rows were outside the lookback window and stayed untouched
        assert all(e.home_team_id is None for e in old_events)

    @pytest.mark.asyncio
    async def test_upcoming_linker_defaults_to_dry_run_and_writes_nothing(self):
        gremio = _team(4001, "Grêmio", SOCCER_SPORT_ID)
        crew = _team(4002, "Columbus Crew", MLS_SPORT_ID)
        ev_soccer = _event(
            6001,
            SOCCER_SPORT_ID,
            "Gremio",
            "Unknown Club FC",
            FIXED_NOW + timedelta(days=2),
        )
        ev_mls = _event(
            6002,
            MLS_SPORT_ID,
            "Columbus Crew 2",
            "Columbus Crew",
            FIXED_NOW + timedelta(days=3),
        )
        session = _InMemoryLinkingSession(
            teams=[gremio, crew],
            events=[ev_soccer, ev_mls],
        )

        summary = await link_unlinked_upcoming_events(session, now=FIXED_NOW)
        assert summary["dry_run"] is True
        assert summary["sides_linked"] == 2
        # Dry run must not mutate any event row
        assert ev_soccer.home_team_id is None
        assert ev_mls.away_team_id is None
        # Planned ledger links Gremio -> Grêmio and Columbus Crew -> Columbus Crew,
        # while refusing Columbus Crew 2 and Unknown Club FC.
        planned = {(p["event_id"], p["side"]): p["team_id"] for p in summary["planned_links"]}
        assert planned == {(6001, "home"): 4001, (6002, "away"): 4002}


class TestEventRegistryLinksOnCreate:
    @pytest.mark.asyncio
    async def test_find_or_create_event_sets_team_ids_for_exact_and_st_state_only(self):
        sac = _team(1126, "Sacramento State Hornets", WNCAAB_SPORT_ID)
        michigan_st = _team(1127, "Michigan State Spartans", WNCAAB_SPORT_ID)
        session = _FakeRegistrySession(
            sport_id=WNCAAB_SPORT_ID,
            teams=[sac, michigan_st],
        )
        _sport_id_cache.clear()
        ext_id = "wncaab-fixture-13144"
        event, created = await find_or_create_event(
            session,
            EventIdentity(
                sport_key="basketball_wncaab",
                home_team_name="Sacramento St Hornets",
                away_team_name="Michigan Wolverines",  # namesake -> must stay NULL
                commence_time=FIXED_NOW + timedelta(days=1),
                claim=EventClaim("odds_api", ext_id, schedule_derived=False),
                status="scheduled",
            ),
        )
        assert created is True
        assert event.home_team_id == 1126
        assert event.away_team_id is None


class TestAllLeaguesDiscoverPassAndReadById:
    @pytest.mark.asyncio
    async def test_discover_pass_links_zero_sportsbook_league_within_7d_horizon(self, caplog):
        import logging
        from app.tasks.sports import _link_upcoming_unlinked_events_pass

        grambling = _team(3046, "Grambling St Tigers", WNCAAB_SPORT_ID)
        alcorn = _team(6515, "Alcorn St Braves", WNCAAB_SPORT_ID)
        # Upcoming WBB game within 7d (Polymarket-only: zero sportsbook events in pass)
        ev_in_window = _event(
            7001,
            WNCAAB_SPORT_ID,
            "Grambling State Tigers",
            "Alcorn State Braves",
            FIXED_NOW + timedelta(days=2),
        )
        # Future game past the 7-day horizon -> must NOT be linked by the 7-day pass
        ev_past_horizon = _event(
            7002,
            WNCAAB_SPORT_ID,
            "Grambling State Tigers",
            "Alcorn State Braves",
            FIXED_NOW + timedelta(days=10),
        )
        session = _InMemoryLinkingSession(
            teams=[grambling, alcorn],
            events=[ev_in_window, ev_past_horizon],
        )

        with caplog.at_level(logging.INFO, logger="app.tasks.sports"):
            summary = await _link_upcoming_unlinked_events_pass(
                session,
                now=FIXED_NOW,
                sport_key_by_id={WNCAAB_SPORT_ID: "basketball_wncaab"},
            )

        assert summary["dry_run"] is False
        assert summary["sides_linked"] == 2
        assert ev_in_window.home_team_id == 3046
        assert ev_in_window.away_team_id == 6515
        assert ev_past_horizon.home_team_id is None
        assert ev_past_horizon.away_team_id is None
        assert any(
            "Linked 2 team IDs on upcoming events for basketball_wncaab" in rec.message
            for rec in caplog.records
        )

    def test_discover_events_runs_all_leagues_pass_outside_odds_api_loop(self):
        import inspect
        from app.tasks.sports import _discover_events

        src = inspect.getsource(_discover_events)
        assert "_link_upcoming_unlinked_events_pass" in src
        assert "link_unlinked_events_for_sport" not in src

    def test_team_for_event_resolves_linked_team_id_before_exact_name(self):
        from app.routes.events import TeamSnapshot, _dedupe_team_name_lookup, _team_for_event

        grambling = TeamSnapshot(
            id=3046,
            sport_id=WNCAAB_SPORT_ID,
            sport_key="basketball_wncaab",
            name="Grambling St Tigers",
            slug="grambling-st-tigers",
            abbreviation="GRAM",
            primary_color="#ee8601",
            secondary_color="#000000",
            logo_url_small="https://a.espncdn.com/i/teamlogos/ncaa/500/2755.png",
            logo_url_large="https://a.espncdn.com/i/teamlogos/ncaa/500/2755.png",
            current_record="10-12",
            alternate_names=(),
            standings_data=None,
            standings_updated_at=None,
            season_stats=None,
            espn_id="2755",
        )
        other_league = TeamSnapshot(
            id=9999,
            sport_id=999,
            sport_key="lacrosse_ncaa",
            name="Grambling Lacrosse",
            slug="grambling-lacrosse",
            abbreviation="GLAX",
            primary_color="#111111",
            secondary_color="#ffffff",
            logo_url_small="https://example.com/lax.png",
            logo_url_large="https://example.com/lax.png",
            current_record="5-2",
            alternate_names=(),
            standings_data=None,
            standings_updated_at=None,
            season_stats=None,
            espn_id="9999",
        )
        full = _dedupe_team_name_lookup([grambling, other_league])
        # Simulate _build_team_lookup returning a name-filtered subset for the
        # event's raw spelling ("Grambling State Tigers", not in `full` by name!).
        sub = full.subset({"Grambling State Tigers"})
        assert _team_for_event(sub, "Grambling State Tigers", "basketball_wncaab") is None
        resolved = _team_for_event(
            sub,
            "Grambling State Tigers",
            "basketball_wncaab",
            team_id=3046,
        )
        assert resolved is grambling
        assert resolved.abbreviation == "GRAM"

        # Nearest wrong neighbor: a team_id from another league must be refused.
        cross_league = _team_for_event(
            sub,
            "Grambling State Tigers",
            "basketball_wncaab",
            team_id=9999,
        )
        assert cross_league is None

    @pytest.mark.parametrize("reverse_order", [False, True])
    def test_name_lookup_runs_first_and_preserves_two_row_preference_for_ottawa(
        self, reverse_order
    ):
        """Fable review of #13210: linked team_id must never bypass #7132 two-row preference."""
        from app.routes.events import TeamSnapshot, _dedupe_team_name_lookup, _team_for_event

        stale_full = TeamSnapshot(
            id=56,
            sport_id=7,
            sport_key="icehockey_nhl",
            name="Ottawa Senators",
            slug="ottawa-senators",
            abbreviation="OTT",
            primary_color="#c8102e",
            secondary_color="#000000",
            logo_url_small="https://a.espncdn.com/i/teamlogos/nhl/500/ott.png",
            logo_url_large="https://a.espncdn.com/i/teamlogos/nhl/500/ott.png",
            current_record="44-27",
            alternate_names=(),
            standings_data={"points": 99, "division_rank": 3},
            standings_updated_at=FIXED_NOW - timedelta(days=180),
            season_stats=None,
            espn_id="14",
        )
        fresh_short = TeamSnapshot(
            id=13381,
            sport_id=7,
            sport_key="icehockey_nhl",
            name="Senators",
            slug="senators",
            abbreviation="OTT",
            primary_color="#c8102e",
            secondary_color="#000000",
            logo_url_small="https://a.espncdn.com/i/teamlogos/nhl/500/ott.png",
            logo_url_large="https://a.espncdn.com/i/teamlogos/nhl/500/ott.png",
            current_record="14-6",
            alternate_names=("Ottawa Senators",),
            standings_data={"points": 30, "division_rank": 2},
            standings_updated_at=FIXED_NOW - timedelta(hours=1),
            season_stats=None,
            espn_id="14",
        )
        rows = [fresh_short, stale_full] if reverse_order else [stale_full, fresh_short]
        full = _dedupe_team_name_lookup(rows)

        # 1. Event named "Ottawa Senators" linked to stale row 56: name path runs
        # first and picks fresh row 13381 (14-6, 30 pts), never row 56 (44-27, 99 pts).
        sub_exact = full.subset({"Ottawa Senators"})
        picked_exact = _team_for_event(
            sub_exact,
            "Ottawa Senators",
            "icehockey_nhl",
            team_id=56,
        )
        assert picked_exact is fresh_short
        assert picked_exact.id == 13381
        assert picked_exact.current_record == "14-6"

        # 2. Event with an unindexed variant spelling linked to stale row 56:
        # name path finds nothing, falls back to team_id=56, and STILL applies
        # the two-row preference to pick fresh row 13381 even after `.subset()`.
        sub_variant = full.subset({"Ottawa Senators NHL"})
        assert _team_for_event(sub_variant, "Ottawa Senators NHL", "icehockey_nhl") is None
        picked_fallback = _team_for_event(
            sub_variant,
            "Ottawa Senators NHL",
            "icehockey_nhl",
            team_id=56,
        )
        assert picked_fallback is fresh_short
        assert picked_fallback.id == 13381
        assert picked_fallback.current_record == "14-6"
