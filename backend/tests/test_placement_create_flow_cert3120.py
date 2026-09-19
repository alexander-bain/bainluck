"""CERT-3120 — the placement guard, driven through the REAL create/link flow.

WHY A SECOND FILE FOR ONE PREDICATE. `test_placement_tournament_guard_7086.py`
calls `league_is_running_at` directly, which is the right way to test a
predicate and is blind to the only thing that makes a wrong answer expensive.
`_create_event_from_prediction_market` does not defer a refused placement: it
creates the event under the `<sport>_other` catch-all and LINKS the market to
it, and every ordinary matching scan selects `FuturesMarket.event_id IS NULL`.
So nothing ever revisits a linked catch-all row — a wrong refusal strands a
valid fixture under "Other" permanently. The first draft of #7086 refused five
valid placements and called them self-healing on the strength of unit tests
exactly like that file's.

WHAT THIS FILE ASSERTS, therefore, is the sport key the create flow actually
reaches `find_or_create_event` with — the value that becomes the row's
competition and the reader's breadcrumb — for a fixture that must be placed and
for one that must not.

IT ALREADY EARNED ITS KEEP. The refusal branch interpolates the guard's
constants into its log line, and this repair renamed one of them. Every unit
test above stayed green because none of them executes that branch; this file's
refusal arm raised `NameError` on the first run. A predicate test cannot see a
caller, which is the whole argument for writing it.
"""
from datetime import datetime, timedelta, timezone

import pytest

import app.services.event_registry as event_registry
import app.tasks.prediction_market_matching as pmm
from tests.lib_placement_predicate import PredicateSession, ScheduleRow
from tests.test_placement_tournament_guard_7086 import (
    NBL_LAST_SEASON,
    NBL_THIS_SEASON,
    US_OPEN_DRAW,
)


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


class _Market:
    """A Polymarket game market, with the fields the create flow reads."""

    def __init__(self, name, commence_time):
        self.source = "polymarket"
        self.external_id = "0xcert3120"
        self.name = name
        self.commence_time = commence_time
        self.llm_sport_category = None
        self.market_metadata = {}
        self.event_id = None


class _Matchup:
    """The fields `MatchupInfo` carries, with "Yes" meaning the home side."""

    def __init__(self, team_a, team_b):
        self.team_a = team_a
        self.team_b = team_b
        self.yes_team = team_a
        self.format_type = "vs"


class _Created:
    """Captures what the registry was asked to create."""

    def __init__(self):
        self.identity = None

    async def __call__(self, session, identity, *args, **kwargs):
        self.identity = identity
        return type("E", (), {"id": 999, "sport_id": 1})(), True


async def _drive(monkeypatch, *, league, catch_all, fixtures, matchup, kickoff):
    """Run the real create flow, returning the sport key it tried to create on.

    Only the collaborators that answer a DIFFERENT question are replaced — the
    container-sibling lookup, the Odds-API coverage refusal and #5576's club
    resolver. The guard under test runs for real against a session that serves
    the competition's real fixtures, and the registry is captured rather than
    called, so what comes back is the key the row would have carried.
    """
    created = _Created()
    monkeypatch.setattr(
        pmm, "_polymarket_container_sibling_event_id",
        lambda session, market: _none(),
    )
    monkeypatch.setattr(
        pmm, "covered_league_for_matchup",
        lambda session, a, b: _none(),
    )
    monkeypatch.setattr(
        pmm, "placeable_league_for_matchup",
        lambda session, a, b, sport_key: _value(league),
    )
    monkeypatch.setattr(
        pmm, "auto_create_sport_key_from_category", lambda category: catch_all
    )
    monkeypatch.setattr(event_registry, "find_or_create_event", created)

    session = PredicateSession(
        [ScheduleRow(league, when, "odds_api") for when in fixtures]
    )
    await pmm._create_event_from_prediction_market(
        session, matchup, _Market("Cert 3120 market", kickoff), kickoff
    )
    assert created.identity is not None, (
        "the create flow returned before reaching the registry, so this test "
        "measured nothing — fix the harness rather than the assertion"
    )
    return created.identity.sport_key


async def _none():
    return None


async def _value(value):
    return value


class TestAValidFixtureReachesItsCompetition:
    """The five CERT-3120 named, at the only place the answer is spendable."""

    @pytest.mark.asyncio
    async def test_a_season_opening_behind_our_horizon_is_placed(self, monkeypatch):
        """NBL, 09-23: nothing after it, evidence is last season's 67-day block.

        This is the fixture the first draft stranded. It must come out of the
        create flow as `basketball_nbl` and not `basketball_other`.
        """
        placed = await _drive(
            monkeypatch,
            league="basketball_nbl",
            catch_all="basketball_other",
            fixtures=NBL_LAST_SEASON + NBL_THIS_SEASON,
            matchup=_Matchup("Cairns Taipans", "Tasmania JackJumpers"),
            kickoff=_utc("2026-09-23 09:30:00"),
        )
        assert placed == "basketball_nbl"

    @pytest.mark.asyncio
    async def test_a_competition_that_has_not_finished_is_placed(self, monkeypatch):
        """Nations League, 09-20: not season-shaped, but still playing."""
        windows = [
            _utc("2026-09-17 14:00:00"),
            _utc("2026-09-24 14:00:00"),
            _utc("2026-09-29 18:45:00"),
        ]
        placed = await _drive(
            monkeypatch,
            league="soccer_uefa_nations_league",
            catch_all="soccer_other",
            fixtures=windows,
            matchup=_Matchup("Finland", "Greece"),
            kickoff=_utc("2026-09-20 14:00:00"),
        )
        assert placed == "soccer_uefa_nations_league"


class TestAFinishedTournamentKeepsTheCatchAll:
    @pytest.mark.asyncio
    async def test_a_davis_cup_tie_does_not_reach_the_us_open(self, monkeypatch):
        """The ship's own defect, asserted where the reader would have seen it.

        `/events/15314722` headed its page "US Open 2026" six days after the
        final. The row must come out of the create flow on the catch-all.

        This arm is also the one that executes the refusal's logging branch,
        which is why it caught this repair renaming a constant the log reads.
        """
        placed = await _drive(
            monkeypatch,
            league="tennis_atp_us_open",
            catch_all="tennis_other",
            fixtures=US_OPEN_DRAW,
            matchup=_Matchup("Auger-Aliassime", "Rinderknech"),
            kickoff=_utc("2026-09-19 22:10:00"),
        )
        assert placed == "tennis_other"

    @pytest.mark.asyncio
    async def test_the_tournaments_own_later_round_still_reaches_it(
        self, monkeypatch
    ):
        """The control: refusing the tie may not cost the draw its own semi."""
        placed = await _drive(
            monkeypatch,
            league="tennis_atp_us_open",
            catch_all="tennis_other",
            fixtures=US_OPEN_DRAW,
            matchup=_Matchup("Zverev", "Shelton"),
            kickoff=US_OPEN_DRAW[-1] - timedelta(days=1.77),
        )
        assert placed == "tennis_atp_us_open"
