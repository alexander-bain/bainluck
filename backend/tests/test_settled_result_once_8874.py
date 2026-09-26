"""#8874 — a settled tennis page says its result once, in the hero.

WHAT A READER SAW (production, 2026-09-26 17:08Z, release v5100).

`/events/15319072` (M25 Setubal, Deckers v Henning), `suspended`, graded by the
venue: the hero read **Settled · Deckers wins**, and Additional Markets repeated
it twice — the match winner `62392768` ("Alec Deckers, last quote 100%") and
Polymarket's `62526438` ("Completed Match: Yes, last quote 100%").

The live doubles page `/events/15318843` never drew its match winner `62358022`:
the page's `findWinProbMarkets` hides two priced legs summing to one. A settled
market serves its loser's 0 as `None`, so that fold stopped exactly on the pages
whose hero already names the winner.

THE CONTROLS. Every fold test has a neighbour the fold must leave: the Set 1 /
Set 2 Winner and Set Handicap markets #8829 brought back, a Completed Match
leaning `No` (#8288's void signal), and every page whose hero does NOT name the
winner — live, scheduled, suspended with no venue grade, finished with no score.
"""

import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import app.routes.events as events_module
from app.routes.events import (
    _build_game_markets,
    _completed_match_says_played,
    _markets_the_settled_hero_answers,
    _names_completed_match,
    _settled_hero_names_the_result,
)

HOME = "Deckers"
AWAY = "Henning"
HEAD = 62392768
COMPLETED = 62526438
SET1 = 62422520
SET2 = 62526440
HANDICAP = 62422524
STAMP = "2026-09-26T16:10:46.707330+00:00"
NOW = datetime(2026, 9, 26, 17, 8, tzinfo=timezone.utc)


def _row(market_id, name, leg, prob, is_winner=None):
    return {
        "market_name": name,
        "outcome_name": leg,
        "observed_at": STAMP,
        "probability": prob,
        "source": "polymarket",
        "is_winner": is_winner,
        "resolution_source": "api_settlement" if is_winner is not None else None,
        "_market_id": market_id,
    }


def _specimen_other():
    """`/api/events/15319072/game-markets` `other[]`, as served 2026-09-26 17:08Z."""
    return [
        _row(SET2, "Set 2 Winner: Alec Deckers vs Philip Henning", "Alec Deckers", 1.0),
        _row(SET2, "Set 2 Winner: Alec Deckers vs Philip Henning", "Philip Henning", None),
        _row(SET1, "Set 1 Winner: Alec Deckers vs Philip Henning", "Alec Deckers", 1.0),
        _row(SET1, "Set 1 Winner: Alec Deckers vs Philip Henning", "Philip Henning", None),
        _row(HEAD, "M25 Setubal: Alec Deckers vs Philip Henning", "Alec Deckers", 1.0),
        _row(HEAD, "M25 Setubal: Alec Deckers vs Philip Henning", "Philip Henning", None),
        _row(COMPLETED, "M25 Setubal, Main Draw: Completed Match: Alec Deckers vs Philip Henning", "Yes", 1.0),
        _row(COMPLETED, "M25 Setubal, Main Draw: Completed Match: Alec Deckers vs Philip Henning", "No", None),
        _row(HANDICAP, "Set Handicap: Philip Henning (-1.5) vs Alec Deckers (+1.5)", "Alec Deckers", 1.0, True),
    ]


class TestTheSpecimenFoldsToItsSetMarkets:
    def test_the_match_winner_and_completed_match_are_the_answered_pair(self):
        assert _markets_the_settled_hero_answers(_specimen_other(), HOME, AWAY) == {HEAD, COMPLETED}

    def test_the_set_markets_and_the_handicap_are_not_answered(self):
        answered = _markets_the_settled_hero_answers(_specimen_other(), HOME, AWAY)
        assert not answered & {SET1, SET2, HANDICAP}

    def test_the_doubles_headline_is_a_match_winner_too(self):
        rows = [
            _row(62358022, "Hangzhou Open (Doubles): Reynolds/Watt vs King/Stevens", "King/Stevens", 1.0),
            _row(62358022, "Hangzhou Open (Doubles): Reynolds/Watt vs King/Stevens", "Reynolds/Watt", None),
            _row(62358024, "Set 1 Winner: Reynolds/Watt vs King/Stevens", "King/Stevens", 1.0),
            _row(62358024, "Set 1 Winner: Reynolds/Watt vs King/Stevens", "Reynolds/Watt", None),
        ]
        assert _markets_the_settled_hero_answers(rows, "Reynolds / Watt", "King / Stevens") == {62358022}

    def test_a_row_without_a_market_id_is_never_answered(self):
        rows = [dict(r, _market_id=None) for r in _specimen_other()]
        assert _markets_the_settled_hero_answers(rows, HOME, AWAY) == set()


class TestCompletedMatch:
    NAME = "M25 Setubal, Main Draw: Completed Match: Alec Deckers vs Philip Henning"

    def test_the_name_is_a_whole_segment(self):
        assert _names_completed_match(self.NAME)
        assert _names_completed_match("Korea Open: Completed Match: A vs B")

    def test_a_substring_is_not_the_segment(self):
        assert not _names_completed_match("Completed Matches Tonight: A vs B")
        assert not _names_completed_match("A vs B")
        assert not _names_completed_match(None)

    def test_yes_at_one_says_played(self):
        assert _completed_match_says_played([_row(1, self.NAME, "Yes", 1.0), _row(1, self.NAME, "No", None)])

    def test_yes_graded_says_played_whatever_its_price(self):
        assert _completed_match_says_played([_row(1, self.NAME, "Yes", 0.5, True)])

    def test_a_void_keeps_its_card(self):
        """#8288: "Completed Match: No" is the void signal — it is not folded."""
        rows = [_row(COMPLETED, self.NAME, "Yes", None), _row(COMPLETED, self.NAME, "No", 1.0)]
        assert not _completed_match_says_played(rows)
        assert _markets_the_settled_hero_answers(rows, HOME, AWAY) == set()

    def test_a_graded_no_beats_a_stale_yes_price(self):
        rows = [_row(1, self.NAME, "Yes", 1.0), _row(1, self.NAME, "No", 0.0, True)]
        assert not _completed_match_says_played(rows)

    def test_an_undecided_market_has_said_nothing(self):
        rows = [_row(1, self.NAME, "Yes", 0.9), _row(1, self.NAME, "No", 0.1)]
        assert not _completed_match_says_played(rows)


def _event(status, home_score=None, away_score=None, start=NOW - timedelta(hours=3)):
    return SimpleNamespace(
        id=15319072,
        status=status,
        home_score=home_score,
        away_score=away_score,
        commence_time=start,
        home_team_name=HOME,
        away_team_name=AWAY,
    )


@pytest.fixture
def venue(monkeypatch):
    """Stand in for `_venue_settlement`; records whether it was asked."""
    calls = []
    state = {"answer": {"venue_settled": True, "venue_settled_result": "Deckers wins"}}

    async def fake(db, event):
        calls.append(event.id)
        return state["answer"]

    monkeypatch.setattr(events_module, "_venue_settlement", fake)
    return SimpleNamespace(calls=calls, state=state)


class TestTheHeroNamesTheResult:
    @pytest.mark.asyncio
    async def test_suspended_and_venue_graded_is_the_specimen(self, venue):
        assert await _settled_hero_names_the_result(None, _event("suspended"), NOW)
        assert venue.calls == [15319072]

    @pytest.mark.asyncio
    async def test_suspended_without_a_venue_grade_does_not(self, venue):
        venue.state["answer"] = {"venue_settled": False, "venue_settled_result": None}
        assert not await _settled_hero_names_the_result(None, _event("suspended"), NOW)

    @pytest.mark.asyncio
    async def test_a_failed_venue_read_does_not(self, venue):
        venue.state["answer"] = None
        assert not await _settled_hero_names_the_result(None, _event("suspended"), NOW)

    @pytest.mark.asyncio
    async def test_a_graded_venue_that_names_no_result_does_not(self, venue):
        venue.state["answer"] = {"venue_settled": True, "venue_settled_result": None}
        assert not await _settled_hero_names_the_result(None, _event("suspended"), NOW)

    @pytest.mark.asyncio
    async def test_a_live_page_never_asks_the_venue(self, venue):
        assert not await _settled_hero_names_the_result(None, _event("live"), NOW)
        assert venue.calls == []

    @pytest.mark.asyncio
    async def test_a_future_fixture_never_asks_the_venue(self, venue):
        assert not await _settled_hero_names_the_result(
            None, _event("scheduled", start=NOW + timedelta(hours=2)), NOW
        )
        assert venue.calls == []

    @pytest.mark.asyncio
    async def test_a_finished_event_with_its_score(self, venue):
        assert await _settled_hero_names_the_result(None, _event("completed", 2, 0), NOW)
        assert venue.calls == []

    @pytest.mark.asyncio
    async def test_a_finished_event_without_a_score_does_not(self, venue):
        assert not await _settled_hero_names_the_result(None, _event("completed"), NOW)

    @pytest.mark.asyncio
    async def test_a_completed_row_starting_in_the_future_is_not_finished(self, venue):
        """#46 shape: `_event_is_really_finished` refuses it, and it has a score, so no venue ask."""
        assert not await _settled_hero_names_the_result(
            None, _event("completed", 2, 0, start=NOW + timedelta(hours=5)), NOW
        )


class TestTheBuildCallsTheFold:
    def test_the_fold_runs_after_the_6799_fold_and_before_the_field_withhold(self):
        src = inspect.getsource(_build_game_markets)
        fold_6799 = src.index("_fold_duplicate_match_winner_markets(")
        answered = src.index("_markets_the_settled_hero_answers(")
        gate = src.index("_settled_hero_names_the_result(")
        withhold = src.index("_withhold_partial_field_markets(")
        assert fold_6799 < answered < gate < withhold
        assert 'r.get("_market_id") not in _answered' in src
