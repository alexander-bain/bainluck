"""Guards for #13238 (and #13142): EuroLeague, Bundesliga, and WBB club spellings
land on the existing row and fold into one blended card.

Measured production pairs (2026-11-20):
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
from app.utils.name_normalization import names_match
from app.utils.prediction_market_matching import _fuzzy_team_match
from app.utils.venue_club_spellings import venue_spellings_of
from scripts.audit_open_duplicate_events_13238 import (
    OpenEventRow,
    find_open_duplicate_pairs,
    format_report,
)
from tests.test_event_registry import _FakeRegistrySession

KICKOFF = datetime(2026, 11, 20, 19, 30, tzinfo=timezone.utc)


def _row(
    eid: int,
    sport_key: str,
    away: str,
    home: str,
    *,
    commence: datetime = KICKOFF,
    external_id: str | None = None,
    espn_id: str | None = None,
    status: str = "live",
    sources: dict | None = None,
    sport_id: int = 99,
):
    return SimpleNamespace(
        id=eid,
        sport_id=sport_id,
        sport=SimpleNamespace(key=sport_key),
        away_team_name=away,
        home_team_name=home,
        commence_time=commence,
        commence_time_source=None,
        external_id=external_id,
        espn_id=espn_id,
        statpal_fixture_id=None,
        status=status,
        home_score=None,
        away_score=None,
        event_tags=[],
        win_probability_sources=sources or {},
        opening_probability=None,
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
