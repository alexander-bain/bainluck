"""Guard for the WC concept adapter's stale-projected-final dedup (#209 Item 3).

Live 2026-07-19 the World Cup final slot carried three scheduled rows — the real
Spain vs Argentina beside a stale Spain vs England and France vs England (England
& France already knocked out). An eliminated nation cannot play a future match
(#210: elimination is a bracket fact), so slot-conflicting rows with an
eliminated side are dropped when a both-alive alternative exists. These tests pin
that the dedup (a) kills the phantom finals, (b) never drops a unique real
fixture, and (c) never touches completed history.
"""
from datetime import datetime, timezone

from app.utils.event_soccer import (
    _drop_slot_duplicate_phantoms,
    _match_is_real,
    _norm,
)


class _G:
    def __init__(self, gid, home, away, status, commence,
                 external_id="odds-hex", win_probability_sources=None,
                 home_score=None, away_score=None):
        self.id = gid
        self.home_team_name = home
        self.away_team_name = away
        self.status = status
        self.commence_time = commence
        self.external_id = external_id
        self.win_probability_sources = (
            win_probability_sources if win_probability_sources is not None else {"espn": 0.5}
        )
        self.home_score = home_score
        self.away_score = away_score


def test_match_is_real_drops_placeholder_events():
    """A matching-created placeholder — no schedule-source id AND no win-prob —
    is a phantom regardless of status (teamless closed rows; the 07-29 phantom)."""
    teamless = _G(1, None, None, "closed", FINAL,
                  external_id=None, win_probability_sources={})
    phantom_future = _G(2, "England", "Argentina", "scheduled",
                        datetime(2026, 7, 29, 19, 0, tzinfo=timezone.utc),
                        external_id=None, win_probability_sources={})
    assert _match_is_real(teamless) is False
    assert _match_is_real(phantom_future) is False


def test_match_is_real_keeps_real_source_fixtures():
    """Real fixtures (odds-api external_id + win-prob) always count."""
    real_final = _G(3, "Spain", "Argentina", "scheduled", FINAL)
    played = _G(4, "England", "Argentina", "completed", FINAL,
                home_score=1, away_score=2)
    assert _match_is_real(real_final) is True
    assert _match_is_real(played) is True


FINAL = datetime(2026, 7, 19, 19, 0, tzinfo=timezone.utc)


def _elim(*nations):
    return {_norm(n): {"eliminated": True} for n in nations}


def test_drops_phantom_finals_keeps_real():
    real = _G(1, "Spain", "Argentina", "scheduled", FINAL)
    phantom_a = _G(2, "Spain", "England", "scheduled", FINAL)
    phantom_b = _G(3, "France", "England", "scheduled", FINAL)
    games = [real, phantom_a, phantom_b]
    kept = _drop_slot_duplicate_phantoms(games, _elim("England", "France"))
    assert [g.id for g in kept] == [1]


def test_unique_slot_never_dropped():
    """A lone scheduled match with an 'eliminated' team (e.g. a group-stage
    mislabel) at its own slot is kept — no false drop."""
    lone = _G(9, "England", "Argentina", "scheduled",
              datetime(2026, 7, 29, 19, 0, tzinfo=timezone.utc))
    kept = _drop_slot_duplicate_phantoms([lone], _elim("England"))
    assert [g.id for g in kept] == [9]


def test_fail_open_when_no_alive_alternative():
    """If every row in a slot has an eliminated side, keep them all (something's
    off with the elimination data — don't empty the slot)."""
    a = _G(1, "Spain", "England", "scheduled", FINAL)
    b = _G(2, "France", "England", "scheduled", FINAL)
    kept = _drop_slot_duplicate_phantoms([a, b], _elim("England", "France"))
    assert {g.id for g in kept} == {1, 2}


def test_completed_history_untouched():
    """Completed matches (the bracket's history) are never dropped, even if they
    share a slot with a scheduled row and involve an eliminated team."""
    played = _G(1, "England", "Argentina", "completed", FINAL)
    live_real = _G(2, "Spain", "Argentina", "scheduled", FINAL)
    kept = _drop_slot_duplicate_phantoms([played, live_real], _elim("England"))
    assert {g.id for g in kept} == {1, 2}


def test_no_eliminations_noop():
    a = _G(1, "Spain", "Argentina", "scheduled", FINAL)
    b = _G(2, "Portugal", "Brazil", "scheduled", FINAL)
    kept = _drop_slot_duplicate_phantoms([a, b], {})
    assert {g.id for g in kept} == {1, 2}
