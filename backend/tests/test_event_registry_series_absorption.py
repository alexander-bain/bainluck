"""#1779 — consecutive-day series games must not be absorbed by the ±28h structured match.

THE DEFECT

``_find_by_structured_match`` accepts any same-sport candidate whose commence_time
is within ±28h and whose two team names match. For a sport where the same two
clubs play on consecutive days, **24h < 28h** — so the second game of a series
name-matched the first and was folded into it instead of being created. Nine MLB
games vanished and three rows were overwritten with the wrong day's score over
2026-08-10 → 08-12; the owner went looking for a live Red Sox game and it did not
exist on any surface, because it did not exist in the database.

THE FIX UNDER TEST (Alex ruling 2026-08-12)

The window is deliberately NOT narrowed — it exists for genuine cross-source date
disagreement (Kalshi settlement dates 24h off the start, UTC boundary crossings),
and narrowing it re-opens those. Instead a candidate is disqualified when it
already carries a **different game id from the incoming claim's own provider**.
The provider has already said these are two different games; names and times
cannot outvote that.

WHAT THE FIXTURES ARE

The seven absorption pairs are the real ones, not invented: absorbing-event ids,
their real ``espn_id`` / ``statpal_fixture_id`` and commence_times are the values
measured in production on 2026-08-12, and the incoming ESPN ids are the real ids
ESPN assigned the games that went missing. A synthetic fixture would prove the
branch runs; these prove the incident does not recur.
"""

import pytest
from datetime import datetime, timezone

from app.models import Event
from app.services.event_registry import (
    EventClaim,
    EventIdentity,
    _find_by_structured_match,
    _holds_distinct_provider_game_id,
    find_or_create_event,
)

from tests.test_event_registry import _FakeRegistrySession

MLB_SPORT_ID = 53232


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def _event(*, event_id, away, home, commence, espn_id=None, statpal_id=None,
           external_id=None, status="completed") -> Event:
    return Event(
        id=event_id,
        sport_id=MLB_SPORT_ID,
        away_team_name=away,
        home_team_name=home,
        commence_time=_utc(commence),
        status=status,
        espn_id=espn_id,
        statpal_fixture_id=statpal_id,
        external_id=external_id,
        completed_at=None,
    )


# (label, away, home, absorbing event id, its espn_id, its statpal id, its
#  commence_time, the missing game's commence_time, the missing game's real ESPN id)
#
# Measured 2026-08-12: production `events` rows + ESPN scoreboard for 08-10..08-12.
# Every delta below is inside the ±28h window, which is precisely the problem.
ABSORPTION_PAIRS = [
    ("BOS@TOR", "Boston Red Sox", "Toronto Blue Jays",
     15187583, "401816469", "355179", "2026-08-10T23:07:00", "2026-08-11T23:07:00", "401816479"),
    ("NYM@ATL", "New York Mets", "Atlanta Braves",
     15187584, "401816470", "355172", "2026-08-10T23:15:00", "2026-08-11T23:15:00", "401816482"),
    ("KC@LAD", "Kansas City Royals", "Los Angeles Dodgers",
     15187853, "401816475", "355174", "2026-08-11T02:10:00", "2026-08-12T02:10:00", "401816490"),
    ("COL@ARI", "Colorado Rockies", "Arizona Diamondbacks",
     15193365, "401816503", "355180", "2026-08-12T19:40:00", "2026-08-12T01:40:00", "401816488"),
    ("TB@ATH", "Tampa Bay Rays", "Athletics",
     15193123, "401816492", "355181", "2026-08-12T19:05:00", "2026-08-12T01:40:00", "401816507"),
    ("MIL@SD", "Milwaukee Brewers", "San Diego Padres",
     15193257, "401816491", "355190", "2026-08-12T20:10:00", "2026-08-12T01:40:00", "401816506"),
    ("HOU@SF", "Houston Astros", "San Francisco Giants",
     15193124, "401816489", "355191", "2026-08-12T19:45:00", "2026-08-12T01:45:00", "401816504"),
]

_IDS = [p[0] for p in ABSORPTION_PAIRS]


class TestTheSevenAbsorptions:
    """The 7/7 repro. Each pair must FALL INSIDE the window and STILL not match."""

    @pytest.mark.parametrize("pair", ABSORPTION_PAIRS, ids=_IDS)
    @pytest.mark.asyncio
    async def test_incoming_espn_game_is_not_absorbed(self, pair):
        (_label, away, home, ev_id, espn_id, statpal_id,
         absorber_time, missing_time, missing_espn) = pair

        absorber = _event(
            event_id=ev_id, away=away, home=home, commence=absorber_time,
            espn_id=espn_id, statpal_id=statpal_id,
        )
        session = _FakeRegistrySession(
            structured_candidates=[absorber], sport_id=MLB_SPORT_ID,
        )

        match = await _find_by_structured_match(
            session, MLB_SPORT_ID, home, away, _utc(missing_time),
            EventClaim("espn", missing_espn),
        )

        assert match is None, (
            f"{away} @ {home} on {missing_time} was absorbed into event {ev_id} "
            f"({absorber_time}) — that row already holds ESPN id {espn_id}, so ESPN "
            f"itself says {missing_espn} is a different game"
        )

    @pytest.mark.parametrize("pair", ABSORPTION_PAIRS, ids=_IDS)
    @pytest.mark.asyncio
    async def test_each_pair_really_is_inside_the_window(self, pair):
        """Guards the test itself.

        If a fixture's two times ever drifted outside ±28h the absorption test
        above would pass for the wrong reason — the candidate would be filtered
        out by the SQL window and the disqualification would never be exercised.
        """
        (_label, _away, _home, _ev, _espn, _statpal,
         absorber_time, missing_time, _missing_espn) = pair
        delta = abs((_utc(missing_time) - _utc(absorber_time)).total_seconds()) / 3600.0
        assert 0 < delta < 28, f"fixture drifted out of the ±28h window: {delta:.1f}h"

    @pytest.mark.parametrize("pair", ABSORPTION_PAIRS, ids=_IDS)
    @pytest.mark.asyncio
    async def test_absorption_still_happens_without_a_provider_id(self, pair):
        """The window itself is untouched — proof the fix is the id, not a narrowing.

        Same geometry, but the incoming claim comes from a source that carries no
        per-game id column (Kalshi). Nothing can be disqualified, so the candidate
        still matches. If this ever returns None, someone narrowed the window.
        """
        (_label, away, home, ev_id, espn_id, statpal_id,
         absorber_time, missing_time, _missing_espn) = pair

        absorber = _event(
            event_id=ev_id, away=away, home=home, commence=absorber_time,
            espn_id=espn_id, statpal_id=statpal_id,
        )
        session = _FakeRegistrySession(
            structured_candidates=[absorber], sport_id=MLB_SPORT_ID,
        )

        match = await _find_by_structured_match(
            session, MLB_SPORT_ID, home, away, _utc(missing_time),
            EventClaim("kalshi", "KXMLBGAME-26AUG11BOSTOR"),
        )
        assert match is absorber


class TestDisqualificationPredicate:
    """``_holds_distinct_provider_game_id`` — the whole decision, in isolation."""

    def test_distinct_id_same_provider_disqualifies(self):
        candidate = _event(event_id=1, away="A", home="B",
                           commence="2026-08-10T23:07:00", espn_id="401816469")
        assert _holds_distinct_provider_game_id(candidate, EventClaim("espn", "401816479"))

    def test_same_id_does_not_disqualify(self):
        """Idempotence. A re-poll of the same game must still find its own row."""
        candidate = _event(event_id=1, away="A", home="B",
                           commence="2026-08-10T23:07:00", espn_id="401816469")
        assert not _holds_distinct_provider_game_id(candidate, EventClaim("espn", "401816469"))

    def test_int_vs_str_id_is_not_a_difference(self):
        """ESPN ids arrive as both; a type difference must not read as a new game."""
        candidate = _event(event_id=1, away="A", home="B",
                           commence="2026-08-10T23:07:00", espn_id="401816469")
        candidate.espn_id = 401816469
        assert not _holds_distinct_provider_game_id(candidate, EventClaim("espn", "401816469"))

    def test_candidate_without_that_provider_id_is_kept(self):
        """The normal cross-source join: ESPN arriving at an odds_api-created row."""
        candidate = _event(event_id=1, away="A", home="B",
                           commence="2026-08-10T23:07:00", external_id="abc123")
        assert not _holds_distinct_provider_game_id(candidate, EventClaim("espn", "401816479"))

    def test_other_providers_id_never_disqualifies(self):
        """Two providers' id spaces are unrelated — comparing them is meaningless."""
        candidate = _event(event_id=1, away="A", home="B",
                           commence="2026-08-10T23:07:00", external_id="abc123")
        assert not _holds_distinct_provider_game_id(candidate, EventClaim("statpal", "355179"))

    def test_idless_provider_never_disqualifies(self):
        candidate = _event(event_id=1, away="A", home="B",
                           commence="2026-08-10T23:07:00", espn_id="401816469")
        assert not _holds_distinct_provider_game_id(candidate, EventClaim("kalshi", "KX-1"))
        assert not _holds_distinct_provider_game_id(candidate, EventClaim("polymarket", "0xdead"))

    def test_empty_incoming_id_never_disqualifies(self):
        candidate = _event(event_id=1, away="A", home="B",
                           commence="2026-08-10T23:07:00", espn_id="401816469")
        assert not _holds_distinct_provider_game_id(candidate, EventClaim("espn", ""))

    def test_statpal_uses_its_own_column(self):
        candidate = _event(event_id=1, away="A", home="B",
                           commence="2026-08-10T23:07:00", statpal_id="355179")
        assert _holds_distinct_provider_game_id(candidate, EventClaim("statpal", "355193"))
        assert not _holds_distinct_provider_game_id(candidate, EventClaim("statpal", "355179"))

    def test_odds_api_uses_its_own_column(self):
        candidate = _event(event_id=1, away="A", home="B",
                           commence="2026-08-10T23:07:00", external_id="abc123")
        assert _holds_distinct_provider_game_id(candidate, EventClaim("odds_api", "def456"))
        assert not _holds_distinct_provider_game_id(candidate, EventClaim("odds_api", "abc123"))


class TestDoubleheadersStillCollapseCorrectly:
    """The ±28h window's original job must survive — ruling 2026-08-12 names this.

    Doubleheaders carry distinct provider ids too, so the id disqualification
    covers the case the window was built for. Where no ids exist yet, the window
    and its closest-by-time tiebreaker still decide.
    """

    @pytest.mark.asyncio
    async def test_distinct_ids_separate_the_two_games_of_a_doubleheader(self):
        game1 = _event(event_id=1, away="Boston Red Sox", home="Toronto Blue Jays",
                       commence="2026-08-10T17:07:00", espn_id="401816469")
        session = _FakeRegistrySession(structured_candidates=[game1], sport_id=MLB_SPORT_ID)

        match = await _find_by_structured_match(
            session, MLB_SPORT_ID, "Toronto Blue Jays", "Boston Red Sox",
            _utc("2026-08-10T23:07:00"), EventClaim("espn", "401816470"),
        )
        assert match is None, "game 2 of a doubleheader must not fold into game 1"

    @pytest.mark.asyncio
    async def test_idless_doubleheader_still_picks_the_closest_in_time(self):
        game1 = _event(event_id=1, away="Boston Red Sox", home="Toronto Blue Jays",
                       commence="2026-08-10T17:07:00")
        game2 = _event(event_id=2, away="Boston Red Sox", home="Toronto Blue Jays",
                       commence="2026-08-10T23:07:00")
        session = _FakeRegistrySession(
            structured_candidates=[game1, game2], sport_id=MLB_SPORT_ID,
        )

        match = await _find_by_structured_match(
            session, MLB_SPORT_ID, "Toronto Blue Jays", "Boston Red Sox",
            _utc("2026-08-10T23:05:00"), EventClaim("kalshi", "KX-1"),
        )
        assert match is game2

    @pytest.mark.asyncio
    async def test_swapped_orientation_still_matches_when_no_id_conflict(self):
        existing = _event(event_id=1, away="Boston Red Sox", home="Toronto Blue Jays",
                          commence="2026-08-10T23:07:00", external_id="abc123")
        session = _FakeRegistrySession(structured_candidates=[existing], sport_id=MLB_SPORT_ID)

        match = await _find_by_structured_match(
            session, MLB_SPORT_ID, "Toronto Blue Jays", "Boston Red Sox",
            _utc("2026-08-10T23:07:00"), EventClaim("espn", "401816469"),
        )
        assert match is existing


class TestEndToEndThroughFindOrCreate:
    """The absorption is only really fixed if the top-level entry point creates."""

    @pytest.mark.asyncio
    async def test_missing_series_game_is_created_not_absorbed(self):
        absorber = _event(
            event_id=15187583, away="Boston Red Sox", home="Toronto Blue Jays",
            commence="2026-08-10T23:07:00", espn_id="401816469", statpal_id="355179",
        )
        session = _FakeRegistrySession(
            structured_candidates=[absorber], sport_id=MLB_SPORT_ID,
        )

        event, created = await find_or_create_event(
            session,
            EventIdentity(
                sport_key="baseball_mlb",
                home_team_name="Toronto Blue Jays",
                away_team_name="Boston Red Sox",
                commence_time=_utc("2026-08-11T23:07:00"),
                claim=EventClaim("espn", "401816479"),
                status="scheduled",
            ),
        )

        assert created is True, "the Aug 11 Red Sox game must be CREATED, not absorbed"
        assert event is not absorber
        assert event.espn_id == "401816479"
        assert event.commence_time == _utc("2026-08-11T23:07:00")
        # And the Aug 10 row is left completely alone.
        assert absorber.espn_id == "401816469"
        assert absorber.commence_time == _utc("2026-08-10T23:07:00")

    @pytest.mark.asyncio
    async def test_same_game_re_poll_still_finds_its_own_row(self):
        """Regression guard on the fix: it must not turn re-polls into duplicates."""
        existing = _event(
            event_id=15187583, away="Boston Red Sox", home="Toronto Blue Jays",
            commence="2026-08-10T23:07:00", espn_id="401816469",
        )
        session = _FakeRegistrySession(
            source_matches={"401816469": existing},
            structured_candidates=[existing],
            sport_id=MLB_SPORT_ID,
        )

        event, created = await find_or_create_event(
            session,
            EventIdentity(
                sport_key="baseball_mlb",
                home_team_name="Toronto Blue Jays",
                away_team_name="Boston Red Sox",
                commence_time=_utc("2026-08-10T23:07:00"),
                claim=EventClaim("espn", "401816469"),
            ),
        )
        assert created is False
        assert event is existing

    @pytest.mark.asyncio
    async def test_cross_source_join_still_works(self):
        """ESPN arriving at a row odds_api created must still MERGE, not duplicate."""
        existing = _event(
            event_id=15187583, away="Boston Red Sox", home="Toronto Blue Jays",
            commence="2026-08-10T23:07:00", external_id="abc123",
        )
        session = _FakeRegistrySession(
            structured_candidates=[existing], sport_id=MLB_SPORT_ID,
        )

        event, created = await find_or_create_event(
            session,
            EventIdentity(
                sport_key="baseball_mlb",
                home_team_name="Toronto Blue Jays",
                away_team_name="Boston Red Sox",
                commence_time=_utc("2026-08-10T23:07:00"),
                claim=EventClaim("espn", "401816469"),
            ),
        )
        assert created is False
        assert event is existing
        assert event.espn_id == "401816469"
