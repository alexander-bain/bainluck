"""#8960 / CERT-3598 — a fixture ESPN postponed before kickoff is never badged live.

CERT-3598 BLOCKed the first cut, and it was right: the #3397 arm can only act
once kickoff has passed (the live pass selects `scheduled` rows with
`commence_time <= now`, and before kickoff a re-dated fixture must keep
`scheduled`), so at kickoff the 60-second promoter and the live pass raced and
the promoter could still flip RBNY v St. Louis (15314000) LIVE.

These drive the three REAL steps in production order over one row:

    1. `sync_scheduled_events` before kickoff — ESPN's board says POSTPONED,
       the row is matched by its own espn_id, the hold is stamped;
    2. `_transition_event_statuses_impl` just after kickoff — the hold keeps
       it `scheduled`;
    3. `update_event_fields_from_espn` (the live pass) — kickoff has passed,
       so the stoppage lands `suspended`.

The strawman runs step 2 without step 1 and gets the defect back.
"""

from __future__ import annotations

import asyncio
import copy
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.services.espn_api import ESPNAPIService
from app.tasks import espn_sync as espn_sync_mod
from app.utils import espn_helpers
from app.utils.espn_helpers import (
    ESPN_STOPPED_KEY,
    authority_stopped_holds,
    sync_scheduled_events,
    update_event_fields_from_espn,
)
from app.utils.event_completion import EVENT_SUSPENDED
from tests.test_authority_demotes_the_live_latch_5324 import _run_transition
from tests.test_espn_soccer_full_time_2908 import BRAGA_GIL_VICENTE_POSTPONED

UTC = timezone.utc
ESPN_ID = "761833"
#: Fixed, not the wall clock (gotcha #44). Every step is handed its own `now`.
KICKOFF = datetime(2026, 9, 26, 23, 30, tzinfo=UTC)
#: The scheduled pass runs on the 60s live beat, so the last stamp before
#: kickoff is under a minute old when the promoter first sees the row.
BEFORE = KICKOFF - timedelta(seconds=40)
JUST_AFTER = KICKOFF + timedelta(seconds=20)
SPORT_KEY = "soccer_usa_mls"


class _Sport:
    id = 1
    key = SPORT_KEY


class _Event:
    def __init__(self, **kw):
        self.id = 15314000
        self.sport = _Sport()
        self.sport_id = 1
        self.home_team_name = "Braga"
        self.away_team_name = "Gil Vicente"
        self.home_team_normalized = None
        self.away_team_normalized = None
        self.home_team_alt_names = None
        self.away_team_alt_names = None
        self.home_team_id = None
        self.away_team_id = None
        self.espn_id = ESPN_ID
        self.commence_time = KICKOFF
        self.commence_time_source = "espn"
        self.status = "scheduled"
        self.home_score = None
        self.away_score = None
        self.period = None
        self.game_clock = None
        self.broadcast_info = None
        self.completed_at = None
        self.llm_importance = None
        self.win_probability_sources = None
        for key, value in kw.items():
            setattr(self, key, value)


def _board(*, postponed=True):
    payload = copy.deepcopy(BRAGA_GIL_VICENTE_POSTPONED)
    payload["id"] = ESPN_ID
    payload["date"] = KICKOFF.strftime("%Y-%m-%dT%H:%MZ")
    if not postponed:
        payload["status"]["type"].update(
            name="STATUS_SCHEDULED", state="pre", completed=False,
            description="Scheduled", detail="Scheduled", shortDetail="Scheduled",
        )
    return ESPNAPIService()._parse_event(payload)


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _ScheduledSession:
    """Answers the scheduled pass: its row pool, then nothing."""

    def __init__(self, events):
        self.events = events
        self.updates = []

    async def execute(self, statement, *_a, **_kw):
        sql = str(statement)
        if sql.startswith("UPDATE"):
            self.updates.append(statement.compile().params)
            return None
        if "FROM events" in sql:
            return _Rows(self.events)
        return _Rows([])

    async def flush(self):
        pass


async def _no_team(*_a, **_kw):
    return None


def _scheduled_pass(event, ee, now):
    session = _ScheduledSession([event])
    stats: dict = {}

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    with patch.object(espn_helpers, "upsert_team", _no_team), patch.object(
        espn_helpers, "register_espn_team_identities", _no_team
    ), patch.object(espn_helpers, "datetime", _Frozen):
        asyncio.run(sync_scheduled_events(session, SPORT_KEY, [ee], stats))
    return stats, session


def _live_pass(event, ee):
    stats: dict = {}

    class _Result:
        rowcount = 1

    class _Session:
        def __init__(self):
            self.statements = []

        async def execute(self, statement, *_a, **_kw):
            self.statements.append(statement)
            return _Result()

        async def flush(self):
            pass

        def add(self, _obj):
            pass

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return JUST_AFTER

    with patch.object(espn_helpers, "datetime", _Frozen):
        asyncio.run(update_event_fields_from_espn(_Session(), event, ee, set(), stats))
    return stats


# ---------------------------------------------------------------------------
# The ship, through all three real steps
# ---------------------------------------------------------------------------


def test_a_postponed_fixture_is_never_promoted_and_lands_suspended():
    ours = _Event()
    board = _board()

    stamp_stats, session = _scheduled_pass(ours, board, BEFORE)
    assert ESPN_STOPPED_KEY in (ours.win_probability_sources or {}), (
        "the scheduled pass never recorded ESPN's postponement on the row"
    )
    assert stamp_stats["authority_stopped_stamped"] == 1
    assert any("win_probability_sources" in p for p in session.updates), (
        "the marker was mirrored in memory but never sent to Postgres (gotcha #4)"
    )
    assert ours.status == "scheduled", "before kickoff the row keeps its status"

    promote = _run_transition([ours], now=JUST_AFTER)
    assert ours.status == "scheduled", "the clock badged a postponed match LIVE"
    assert promote["held_authority_stopped"] == 1
    assert promote["scheduled_to_live"] == 0

    live = _live_pass(ours, board)
    assert ours.status == EVENT_SUSPENDED
    assert live["espn_stopped_without_result"] == 1


def test_THE_STRAWMAN_without_the_scheduled_pass_the_clock_promotes():
    """The defect CERT-3598 named: same row, same kickoff, no stamp ⇒ LIVE."""
    ours = _Event()

    promote = _run_transition([ours], now=JUST_AFTER)

    assert ours.status == "live"
    assert promote["scheduled_to_live"] == 1


def test_THE_CONTROL_an_ordinary_fixture_is_promoted_through_the_same_steps():
    """A hold that fired on everything would freeze every kickoff on the site."""
    ours = _Event()

    stats, session = _scheduled_pass(ours, _board(postponed=False), BEFORE)
    assert ESPN_STOPPED_KEY not in (ours.win_probability_sources or {})
    assert not session.updates, "an ordinary pass must not write the column"

    promote = _run_transition([ours], now=JUST_AFTER)
    assert ours.status == "live"
    assert promote["held_authority_stopped"] == 0


def test_a_fixture_espn_re_dates_is_released_by_the_next_anchored_pass():
    """Un-postponed (board back to `pre`): the marker is cleared, not left to hold."""
    ours = _Event(win_probability_sources={ESPN_STOPPED_KEY: BEFORE.isoformat()})

    stats, _ = _scheduled_pass(ours, _board(postponed=False), BEFORE + timedelta(minutes=1))

    assert ESPN_STOPPED_KEY not in (ours.win_probability_sources or {})
    assert stats["authority_stopped_cleared"] == 1


def test_a_name_matched_row_is_never_stamped():
    """A same-day NAME match is a matchup, not this fixture (#1947)."""
    ours = _Event(espn_id=None)

    stats, _ = _scheduled_pass(ours, _board(), BEFORE)

    assert ESPN_STOPPED_KEY not in (ours.win_probability_sources or {})
    assert "authority_stopped_stamped" not in stats


# ---------------------------------------------------------------------------
# The predicate
# ---------------------------------------------------------------------------


def test_the_hold_ignores_the_filler_period_and_clock_espn_publishes():
    """`play_evidence` with all four args counts `period='Postponed'` as play;
    this hold must not, or it is inert on the very rows it exists for."""
    sources = {ESPN_STOPPED_KEY: BEFORE.isoformat()}
    assert authority_stopped_holds(sources, BEFORE + timedelta(minutes=1))
    assert authority_stopped_holds(
        sources, BEFORE + timedelta(minutes=1), home_score=0, away_score=0
    )


def test_a_real_score_releases_the_hold():
    sources = {ESPN_STOPPED_KEY: BEFORE.isoformat()}
    assert not authority_stopped_holds(
        sources, BEFORE + timedelta(minutes=1), home_score=1, away_score=0
    )


def test_the_hold_expires_on_the_shared_ttl():
    sources = {ESPN_STOPPED_KEY: BEFORE.isoformat()}
    ttl = espn_helpers.AUTHORITY_NOT_STARTED_TTL
    assert authority_stopped_holds(sources, BEFORE + ttl)
    assert not authority_stopped_holds(sources, BEFORE + ttl + timedelta(seconds=1))


@pytest.mark.parametrize("junk", [None, 17, "not-a-time", {}])
def test_an_unreadable_marker_fails_open(junk):
    assert not authority_stopped_holds({ESPN_STOPPED_KEY: junk}, BEFORE)


def test_a_marker_from_the_future_is_a_clock_fault():
    sources = {ESPN_STOPPED_KEY: (BEFORE + timedelta(minutes=5)).isoformat()}
    assert not authority_stopped_holds(sources, BEFORE)


def test_the_promoter_asks_the_hold():
    """Wiring: the promotion loop names the predicate (a predicate returning the
    right answer into a loop that never asks it was #5324's first failure)."""
    import inspect

    source = inspect.getsource(espn_sync_mod._transition_event_statuses_impl)
    assert "authority_stopped_holds(" in source
