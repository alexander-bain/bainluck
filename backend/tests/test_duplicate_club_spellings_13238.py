"""Guards for #13238 (and #13142): EuroLeague, Bundesliga, and WBB club spellings
land on the existing row and fold into one blended card.

Measured production pairs (Nov 20, 2026):
- EuroLeague:
  * 15350440 ("KK Crvena zvezda @ FC Barcelona Bàsquet") / 15348467 ("KK Crvena Zvezda @ Barcelona")
  * 15349594 ("Beşiktaş J.K. @ KK Partizan NIS") / 15348468 ("Besiktas @ Partizan") / 15350188 ("KK Partizan Belgrade @ Besiktas JK")
  * 15349544 ("Real Madrid @ Olympiacos") / 15348466 ("Real Madrid @ Olympiacos B.C.") / 15350189 ("BC Olympiakos Piraeus @ Real Madrid")
- Bundesliga:
  * 15342140 ("1. FC Köln @ Bayern Munich") / 15351899 ("FC Cologne @ Bayern Munich")
- Women's college basketball (#13142):
  * 15351848 ("Arkansas-Little Rock Trojans @ Oklahoma St Cowgirls") / 15347844 ("Little Rock Trojans @ Oklahoma State Cowgirls")
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models import Event
from app.services.event_registry import EventClaim, _find_by_structured_match
from app.utils.event_twin_fold import fold_twin_events, twin_fold_key
from app.utils.name_normalization import names_match, token_overlap_score
from app.utils.prediction_market_matching import (
    _expand_team_search_terms,
    _fuzzy_team_match,
    extract_matchup,
    match_teams_to_event,
)
from app.utils.venue_club_spellings import venue_spellings_of
from scripts.audit_open_duplicate_events_13238 import (
    OpenEventRow,
    find_open_duplicate_pairs,
    format_report,
)
from tests.test_event_registry import _FakeRegistrySession

KICKOFF = datetime(2025, 2, 15, 19, 30, tzinfo=timezone.utc)


def _row(
    eid: int,
    sport_key: str,
    away: str,
    home: str,
    *,
    commence: datetime = KICKOFF,
    commence_time_source: str | None = None,
    external_id: str | None = None,
    espn_id: str | None = None,
    status: str = "live",
    home_score: int | None = None,
    away_score: int | None = None,
    sources: dict | None = None,
    opening_home_probability: float | None = None,
    opening_away_probability: float | None = None,
    sport_id: int = 99,
):
    return SimpleNamespace(
        id=eid,
        sport_id=sport_id,
        sport=SimpleNamespace(key=sport_key),
        away_team_name=away,
        home_team_name=home,
        commence_time=commence,
        commence_time_source=commence_time_source,
        external_id=external_id,
        espn_id=espn_id,
        statpal_fixture_id=None,
        status=status,
        home_score=home_score,
        away_score=away_score,
        event_tags=[],
        win_probability_sources=sources or {},
        opening_probability=None,
        opening_home_probability=opening_home_probability,
        opening_away_probability=opening_away_probability,
    )


class TestClubSpellingsAcrossAllMatchers:
    @pytest.mark.parametrize(
        "first,second",
        [
            ("FC Barcelona Bàsquet", "Barcelona"),
            ("Beşiktaş J.K.", "Besiktas"),
            ("Beşiktaş J.K.", "Besiktas JK"),
            ("KK Partizan NIS", "Partizan"),
            ("KK Partizan NIS", "KK Partizan Belgrade"),
            ("Olympiacos", "Olympiacos B.C."),
            ("Olympiacos", "BC Olympiakos Piraeus"),
            ("Fenerbahce SK", "Fenerbahce"),
            ("FC Bayern München", "Bayern Munich"),
            ("1. FC Köln", "FC Cologne"),
            ("Arkansas-Little Rock Trojans", "Little Rock Trojans"),
        ],
    )
    def test_names_match_and_pm_fuzzy_match_both_ways(self, first, second):
        assert names_match(first, second) is True
        assert names_match(second, first) is True
        assert _fuzzy_team_match(first, second) is True
        assert _fuzzy_team_match(second, first) is True

    @pytest.mark.parametrize(
        "a,b",
        [
            ("FC Cologne", "Bayern Munich"),
            ("Beşiktaş J.K.", "Fenerbahce SK"),
            ("KK Partizan NIS", "KK Crvena zvezda"),
            ("Olympiacos", "Panathinaikos"),
            ("Little Rock Trojans", "Arkansas Razorbacks"),
            ("Little Rock Trojans", "USC Trojans"),
        ],
    )
    def test_unrelated_clubs_do_not_match(self, a, b):
        assert names_match(a, b) is False
        assert _fuzzy_team_match(a, b) is False

    def test_euroleague_barcelona_alias_does_not_alter_la_liga_fold_key(self):
        la_liga_a = _row(1, "soccer_spain_la_liga", "Real Madrid", "FC Barcelona", sport_id=10)
        la_liga_b = _row(2, "soccer_spain_la_liga", "Real Madrid", "Barcelona", sport_id=10)
        euro_a = _row(3, "basketball_euroleague", "KK Crvena zvezda", "FC Barcelona Bàsquet", sport_id=20)
        euro_b = _row(4, "basketball_euroleague", "KK Crvena Zvezda", "Barcelona", sport_id=20)

        # La Liga keeps its normal distinct squashed keys (handled by soccer pass)
        assert twin_fold_key(la_liga_a)[2] == "fcbarcelona"
        assert twin_fold_key(la_liga_b)[2] == "barcelona"
        # EuroLeague lands both spellings on the exact same strict fold key
        assert twin_fold_key(euro_a) == twin_fold_key(euro_b)

    def test_venue_spellings_of_supports_euroleague_when_sport_key_supplied(self):
        assert "barcelona" in venue_spellings_of(
            "FC Barcelona Bàsquet", sport_key="basketball_euroleague"
        )
        assert "fc cologne" in venue_spellings_of("1. FC Köln")
        assert "barcelona" not in venue_spellings_of("FC Barcelona", sport_key="soccer_spain_la_liga")


class TestRegistryLandsSecondSpellingOnFirstRow:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "sport_id,existing_home,existing_away,incoming_home,incoming_away",
        [
            (1, "Bayern Munich", "1. FC Köln", "Bayern Munich", "FC Cologne"),
            (2, "FC Barcelona Bàsquet", "KK Crvena zvezda", "Barcelona", "KK Crvena Zvezda"),
            (2, "KK Partizan NIS", "Beşiktaş J.K.", "Partizan", "Besiktas"),
            (2, "Olympiacos", "Real Madrid", "BC Olympiakos Piraeus", "Real Madrid"),
            (3, "Oklahoma St Cowgirls", "Arkansas-Little Rock Trojans", "Oklahoma State Cowgirls", "Little Rock Trojans"),
        ],
    )
    async def test_anchored_second_spelling_matches_existing_sportsbook_row(
        self, sport_id, existing_home, existing_away, incoming_home, incoming_away
    ):
        existing = Event(
            id=15342140,
            sport_id=sport_id,
            home_team_name=existing_home,
            away_team_name=existing_away,
            commence_time=KICKOFF,
            status="scheduled",
            external_id="odds-ext-1",
        )
        session = _FakeRegistrySession(
            structured_candidates=[existing], sport_id=sport_id
        )
        claim = EventClaim("espn", "espn-fixture-1", schedule_derived=True)
        matched = await _find_by_structured_match(
            session,
            sport_id,
            incoming_home,
            incoming_away,
            KICKOFF,
            claim=claim,
        )
        assert matched is existing


class TestTwinFoldBlendsAllMeasuredPairs:
    def test_euroleague_barcelona_pair_folds_and_blends(self):
        sb = _row(
            15350440,
            "basketball_euroleague",
            "KK Crvena zvezda",
            "FC Barcelona Bàsquet",
            external_id="5549",
            sources={"betting": {"value": 0.56}},
        )
        pm = _row(
            15348467,
            "basketball_euroleague",
            "KK Crvena Zvezda",
            "Barcelona",
            sources={"kalshi": {"value": 0.50}, "polymarket": {"value": 0.50}},
        )
        res = fold_twin_events([sb, pm])
        assert [e.id for e in res.events] == [15350440]
        assert res.survivor_of == {15348467: 15350440}
        assert set(res.merged_sources[15350440].keys()) == {
            "betting",
            "kalshi",
            "polymarket",
        }

    def test_euroleague_partizan_pair_folds_and_blends(self):
        sb = _row(
            15349594,
            "basketball_euroleague",
            "Beşiktaş J.K.",
            "KK Partizan NIS",
            commence=KICKOFF + timedelta(minutes=15),
            external_id="4036",
            sources={"betting": {"value": 0.60}},
        )
        pm = _row(
            15348468,
            "basketball_euroleague",
            "Besiktas",
            "Partizan",
            commence=KICKOFF + timedelta(minutes=15),
            sources={"polymarket": {"value": 0.585}},
        )
        res = fold_twin_events([sb, pm])
        assert [e.id for e in res.events] == [15349594]
        assert res.survivor_of == {15348468: 15349594}
        assert set(res.merged_sources[15349594].keys()) == {"betting", "polymarket"}

    def test_bundesliga_cologne_pair_shares_strict_fold_key(self):
        sb = _row(
            15342140,
            "soccer_germany_bundesliga",
            "1. FC Köln",
            "Bayern Munich",
            external_id="cae4",
            sources={"betting": {"value": 0.1255}},
        )
        dup = _row(
            15351899,
            "soccer_germany_bundesliga",
            "FC Cologne",
            "Bayern Munich",
            sources={"polymarket": {"value": 0.0005}},
        )
        assert twin_fold_key(sb) == twin_fold_key(dup)
        res = fold_twin_events([sb, dup])
        assert [e.id for e in res.events] == [15342140]
        assert res.survivor_of == {15351899: 15342140}

    def test_wbb_little_rock_pair_shares_strict_fold_key(self):
        sb = _row(
            15351848,
            "basketball_wncaab",
            "Arkansas-Little Rock Trojans",
            "Oklahoma St Cowgirls",
            status="scheduled",
            external_id="683d",
            sources={"espn": {"value": 0.9947}},
        )
        pm = _row(
            15347844,
            "basketball_wncaab",
            "Little Rock Trojans",
            "Oklahoma State Cowgirls",
            status="scheduled",
            sources={"polymarket": {"value": 0.989}},
        )
        assert twin_fold_key(sb) == twin_fold_key(pm)
        res = fold_twin_events([sb, pm])
        assert [e.id for e in res.events] == [15351848]
        assert res.survivor_of == {15347844: 15351848}


class TestOpenDuplicateCensusScript13238:
    def _open_row(
        self,
        eid: int,
        sport_key: str,
        away: str,
        home: str,
        *,
        commence: datetime = KICKOFF,
        external_id: str | None = None,
        espn_id: str | None = None,
        status: str = "live",
        event_tags: tuple[str, ...] = (),
        sources: tuple[str, ...] = (),
        linked_markets: int = 0,
        odds_snapshots: int = 0,
    ) -> OpenEventRow:
        return OpenEventRow(
            event_id=eid,
            sport_id=1,
            sport_key=sport_key,
            status=status,
            commence_time=commence,
            commence_time_source=None,
            home_team_name=home,
            away_team_name=away,
            external_id=external_id,
            espn_id=espn_id,
            statpal_fixture_id=None,
            home_score=None,
            away_score=None,
            event_tags=event_tags,
            win_prob_sources=sources,
            linked_market_count=linked_markets,
            odds_snapshot_count=odds_snapshots,
        )

    def test_finds_all_three_13238_pairs_and_ranks_sportsbook_row_as_keeper(self):
        rows = [
            self._open_row(15350440, "basketball_euroleague", "KK Crvena zvezda", "FC Barcelona Bàsquet", external_id="5549", sources=("betting",), odds_snapshots=12),
            self._open_row(15348467, "basketball_euroleague", "KK Crvena Zvezda", "Barcelona", sources=("kalshi", "polymarket"), linked_markets=4),
            self._open_row(15349594, "basketball_euroleague", "Beşiktaş J.K.", "KK Partizan NIS", commence=KICKOFF + timedelta(minutes=15), external_id="4036", sources=("betting",)),
            self._open_row(15348468, "basketball_euroleague", "Besiktas", "Partizan", commence=KICKOFF + timedelta(minutes=15), sources=("polymarket",)),
            self._open_row(15342140, "soccer_germany_bundesliga", "1. FC Köln", "Bayern Munich", external_id="cae4", sources=("betting",)),
            self._open_row(15351899, "soccer_germany_bundesliga", "FC Cologne", "Bayern Munich", sources=("polymarket",)),
            # Already-tagged duplicate must be skipped
            self._open_row(15399999, "soccer_germany_bundesliga", "FC Cologne", "Bayern Munich", event_tags=("provenance:duplicate-of:15342140",)),
            # Separate fixture 24h later must NOT pair
            self._open_row(15399998, "basketball_euroleague", "Besiktas", "Partizan", commence=KICKOFF + timedelta(hours=24)),
        ]
        pairs = find_open_duplicate_pairs(rows)
        assert len(pairs) == 3
        keepers = {(p["keeper"]["id"], p["duplicate"]["id"]) for p in pairs}
        assert keepers == {
            (15350440, 15348467),
            (15349594, 15348468),
            (15342140, 15351899),
        }
        report = format_report(rows, pairs)
        assert "pairs=3" in report
        assert "basketball_euroleague: 2 pair(s)" in report
        assert "soccer_germany_bundesliga: 1 pair(s)" in report

    def test_refuses_to_pair_two_distinct_sportsbook_ids(self):
        rows = [
            self._open_row(1, "basketball_nba", "Boston Celtics", "New York Knicks", external_id="odds-1"),
            self._open_row(2, "basketball_nba", "Boston Celtics", "New York Knicks", external_id="odds-2"),
        ]
        assert find_open_duplicate_pairs(rows) == []

    def test_soccer_exonym_branch_catches_unlisted_soccer_spellings(self):
        rows = [
            self._open_row(10, "soccer_germany_bundesliga", "Borussia Monchengladbach", "Werder Bremen", external_id="odds-10"),
            self._open_row(11, "soccer_germany_bundesliga", "B. Monchengladbach", "Werder Bremen"),
        ]
        pairs = find_open_duplicate_pairs(rows)
        assert len(pairs) == 1
        assert pairs[0]["match_reason"] == "soccer_pair_matches"
        assert pairs[0]["keeper"]["id"] == 10
        assert pairs[0]["duplicate"]["id"] == 11


class TestFirstFcOrdinalCollisionFixed13238:
    @pytest.mark.parametrize(
        "a,b",
        [
            ("1. FC Köln", "1. FC Heidenheim"),
            ("1. FC Köln", "1. FC Nürnberg"),
            ("1. FC Heidenheim", "1. FC Nürnberg"),
        ],
    )
    def test_first_fc_clubs_must_stay_apart(self, a, b):
        assert token_overlap_score(a, b) == 0.0
        assert names_match(a, b) is False
        assert _fuzzy_team_match(a, b) is False

    @pytest.mark.parametrize(
        "a,b",
        [
            ("1. FC Köln", "FC Köln"),
            ("1. FC Köln", "FC Cologne"),
            ("1. FC Heidenheim", "FC Heidenheim"),
            ("San Francisco 49ers", "49ers"),
            ("Philadelphia 76ers", "76ers"),
        ],
    )
    def test_valid_first_fc_and_numeric_nicknames_still_match(self, a, b):
        assert names_match(a, b) is True
        assert _fuzzy_team_match(a, b) is True


class TestEuroLeagueNov23SwappedAndThreeHourTwins13238:
    @pytest.mark.parametrize(
        "first,second",
        [
            ("Pallacanestro Olimpia Milano", "Olimpia Milano"),
            ("Saski Baskonia", "Baskonia Vitoria-Gasteiz"),
            ("Anadolu Efes", "Anadolu Efes SK"),
            ("Maccabi Tel Aviv", "Maccabi Tel-Aviv"),
            ("Hapoel Tel Aviv", "Hapoel Tel-Aviv"),
            ("ASVEL Lyon Villeurbanne", "ASVEL Lyon-Villeurbanne"),
        ],
    )
    def test_new_euroleague_spellings_and_hyphens_match_in_pm_matcher(self, first, second):
        assert _fuzzy_team_match(first, second) is True
        assert _fuzzy_team_match(second, first) is True
        assert names_match(first, second) is True

    @pytest.mark.parametrize(
        "search_team,expected_term",
        [
            ("Bayern Munich", "FC Bayern München"),
            ("Olimpia Milano", "Pallacanestro Olimpia Milano"),
            ("BC Olympiakos Piraeus", "Olympiacos"),
            ("Baskonia Vitoria-Gasteiz", "Saski Baskonia"),
            ("Anadolu Efes SK", "Anadolu Efes"),
            ("Maccabi Tel-Aviv", "Maccabi Tel Aviv"),
            ("Hapoel Tel-Aviv", "Hapoel Tel Aviv"),
            ("ASVEL Lyon-Villeurbanne", "ASVEL Lyon Villeurbanne"),
        ],
    )
    def test_expand_team_search_terms_reaches_euroleague_partners(
        self, search_team, expected_term
    ):
        assert expected_term in _expand_team_search_terms(search_team)

    @pytest.mark.parametrize(
        "sb_away,sb_home,kalshi_away,kalshi_home",
        [
            (
                "Maccabi Tel Aviv",
                "FC Bayern München",
                "Bayern Munich",
                "Maccabi Tel-Aviv",
            ),
            (
                "Pallacanestro Olimpia Milano",
                "ASVEL Lyon Villeurbanne",
                "ASVEL Lyon-Villeurbanne",
                "Olimpia Milano",
            ),
            (
                "Hapoel Tel Aviv",
                "Olympiacos",
                "BC Olympiakos Piraeus",
                "Hapoel Tel-Aviv",
            ),
            (
                "Anadolu Efes",
                "Saski Baskonia",
                "Baskonia Vitoria-Gasteiz",
                "Anadolu Efes SK",
            ),
        ],
    )
    def test_kalshi_at_format_maps_to_correct_yes_is_home_even_when_swapped(
        self, sb_away, sb_home, kalshi_away, kalshi_home
    ):
        # Kalshi formats "Away at Home" where Yes = Away team listed first.
        # Because the Kalshi pair lists sb_home first, Yes corresponds to sb_home.
        matchup = extract_matchup(f"{kalshi_away} at {kalshi_home}")
        assert matchup is not None
        mapped = match_teams_to_event(
            matchup, sb_home, sb_away, external_id="KXEUROLEAGUEGAME-26NOV24"
        )
        assert mapped is not None
        assert mapped["yes_is_home"] is True  # Yes == kalshi_away == sb_home

    @pytest.mark.parametrize("status", ["scheduled", "live"])
    def test_all_four_nov23_live_euroleague_pairs_fold_recover_start_and_invert_kalshi(
        self, status
    ):
        base = datetime(2025, 11, 24, 19, 0, tzinfo=timezone.utc)
        live_clock = (
            {"live_state_changed_at": "2025-11-24T19:05:00+00:00"}
            if status == "live"
            else {}
        )
        rows = [
            _row(
                15351534,
                "basketball_euroleague",
                "Maccabi Tel Aviv",
                "FC Bayern München",
                commence=base,
                external_id="odds-1",
                status=status,
                home_score=44 if status == "live" else None,
                away_score=40 if status == "live" else None,
                sources={"betting": {"value": 0.5662}, "polymarket": {"value": 0.56}, **live_clock},
            ),
            _row(
                15352077,
                "basketball_euroleague",
                "Bayern Munich",
                "Maccabi Tel-Aviv",
                commence=base + timedelta(hours=3),
                commence_time_source="kalshi",
                status=status,
                sources={"kalshi": {"value": 0.425}, **live_clock},
                opening_home_probability=0.41,
                opening_away_probability=0.59,
            ),
            _row(
                15351540,
                "basketball_euroleague",
                "Pallacanestro Olimpia Milano",
                "ASVEL Lyon Villeurbanne",
                commence=base + timedelta(minutes=45),
                external_id="odds-2",
                status=status,
                home_score=38 if status == "live" else None,
                away_score=39 if status == "live" else None,
                sources={"betting": {"value": 0.4773}, **live_clock},
            ),
            _row(
                15352078,
                "basketball_euroleague",
                "ASVEL Lyon-Villeurbanne",
                "Olimpia Milano",
                commence=base + timedelta(hours=3, minutes=45),
                commence_time_source="kalshi",
                status=status,
                sources={"kalshi": {"value": 0.525}, **live_clock},
            ),
            _row(
                15351900,
                "basketball_euroleague",
                "Hapoel Tel Aviv",
                "Olympiacos",
                commence=base + timedelta(days=1, minutes=15),
                external_id="odds-3",
                status=status,
                home_score=50 if status == "live" else None,
                away_score=45 if status == "live" else None,
                sources={"betting": {"value": 0.6399}, "polymarket": {"value": 0.625}, **live_clock},
            ),
            _row(
                15352630,
                "basketball_euroleague",
                "BC Olympiakos Piraeus",
                "Hapoel Tel-Aviv",
                commence=base + timedelta(days=1, hours=3, minutes=15),
                commence_time_source="kalshi",
                status=status,
                sources={"kalshi": {"value": 0.35}, **live_clock},
            ),
            _row(
                15351920,
                "basketball_euroleague",
                "Anadolu Efes",
                "Saski Baskonia",
                commence=base + timedelta(days=1, minutes=30),
                external_id="odds-4",
                status=status,
                home_score=41 if status == "live" else None,
                away_score=42 if status == "live" else None,
                sources={"betting": {"value": 0.4824}, **live_clock},
            ),
            _row(
                15352631,
                "basketball_euroleague",
                "Baskonia Vitoria-Gasteiz",
                "Anadolu Efes SK",
                commence=base + timedelta(days=1, hours=3, minutes=30),
                commence_time_source="kalshi",
                status=status,
                sources={"kalshi": {"value": 0.515}, **live_clock},
            ),
        ]

        res = fold_twin_events(rows)
        assert [e.id for e in res.events] == [15351534, 15351540, 15351900, 15351920]
        assert res.survivor_of == {
            15352077: 15351534,
            15352078: 15351540,
            15352630: 15351900,
            15352631: 15351920,
        }
        assert res.merged_sources[15351534]["kalshi"]["value"] == pytest.approx(0.575)
        assert res.merged_sources[15351540]["kalshi"]["value"] == pytest.approx(0.475)
        assert res.merged_sources[15351900]["kalshi"]["value"] == pytest.approx(0.65)
        assert res.merged_sources[15351920]["kalshi"]["value"] == pytest.approx(0.485)
        # Opening line is swapped to match survivor's (away, home)
        assert res.merged_opening[15351534] == (0.59, 0.41)
        assert res.events[0].opening_home_probability == pytest.approx(0.59)
        assert res.events[0].opening_away_probability == pytest.approx(0.41)

    def test_refusal_guards_for_reversed_euroleague_fold(self):
        # 1) Two anchored reversed rows do NOT fold
        a1 = _row(1, "basketball_euroleague", "Maccabi Tel Aviv", "FC Bayern München", external_id="o1", status="scheduled")
        a2 = _row(2, "basketball_euroleague", "Bayern Munich", "Maccabi Tel-Aviv", external_id="o2", status="scheduled")
        assert len(fold_twin_events([a1, a2]).events) == 2

        # 2) Two id-less reversed rows do NOT fold
        c1 = _row(3, "basketball_euroleague", "Maccabi Tel Aviv", "FC Bayern München", status="scheduled")
        c2 = _row(4, "basketball_euroleague", "Bayern Munich", "Maccabi Tel-Aviv", status="scheduled")
        assert len(fold_twin_events([c1, c2]).events) == 2

        # 3) Live reversed claim carrying a score (wins election over scoreless anchor) does NOT fold
        sb_noscore = _row(5, "basketball_euroleague", "Maccabi Tel Aviv", "FC Bayern München", external_id="o5", status="live")
        claim_scored = _row(6, "basketball_euroleague", "Bayern Munich", "Maccabi Tel-Aviv", status="live", home_score=20, away_score=18, sources={"kalshi": {"value": 0.4}})
        assert len(fold_twin_events([sb_noscore, claim_scored]).events) == 2

        # 4) Unknown dict key in reversed reading fails closed (does NOT fold)
        sb = _row(7, "basketball_euroleague", "Maccabi Tel Aviv", "FC Bayern München", external_id="o7", status="scheduled")
        claim_bad = _row(8, "basketball_euroleague", "Bayern Munich", "Maccabi Tel-Aviv", status="scheduled", sources={"kalshi": {"value": 0.4, "unknown_field": 1}})
        assert len(fold_twin_events([sb, claim_bad]).events) == 2

        # 5) Non-allowlisted league (e.g. basketball_nba) reversed anchored/claim does NOT fold
        nba_sb = _row(9, "basketball_nba", "Boston Celtics", "Miami Heat", external_id="o9", status="scheduled")
        nba_cl = _row(10, "basketball_nba", "Miami Heat", "Boston Celtics", status="scheduled", sources={"kalshi": {"value": 0.4}})
        assert len(fold_twin_events([nba_sb, nba_cl]).events) == 2
