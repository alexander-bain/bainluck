"""#5324, team-sport half — an MLB/NHL game stops reading LIVE before its first pitch.

WHAT A READER SAW, production 2026-09-25:

* NHL 15314743 Bruins @ Capitals, `/events/15314743` at 23:02Z: `live · 11s ago`,
  hero clock `0:00`, score `0 – 0`, while ESPN 401879360 read `state: pre`.
* MLB 15318355 Pirates @ Tigers: `status: live` on the stream from 22:42:43Z;
  MLB's first play (statsapi 824220) was 23:08:16Z.

── THE MECHANISM, observed live (artifacts-live-618/poll.log) ─────────────────

    23:30:17Z  15314764 NHL  ours: live  period None       clock '0:00'  0-0
                             ESPN 401879649: pre, displayClock '0:00', period 0
    23:30:17Z  15318665 MLB  ours: live  period 'Scheduled' clock '0:00'  0-0
                             ESPN 401817073: STATUS_SCHEDULED, detail 'Scheduled'

ESPN's pre-game board publishes FILLER — `displayClock "0:00"` on every scheduled
NHL and MLB game, detail `"Scheduled"` on MLB (which `_sanitize_period` keeps),
and score `"0"`. The live pass copied all of it onto the row, and
`play_evidence` reads any clock or period as play. So the authority demotion
shipped for this issue (`66ce552da`) refused on EVERY anchored team-sport row:
its own wiring tests fed boards with `clock=None`, a shape ESPN never serves.

The repair is two halves, both driven through the REAL writer below:

1. `update_event_fields_from_espn` takes no live state from a board that says
   `scheduled` with no score (the same refusal #8247 applies to the straggler
   arm, keyed on the board's word instead of the caller's flag).
2. A row that ALREADY carries the board's filler has it discounted as evidence
   and — when the authority says not started — withdrawn, because the
   promoter's hold reads the row one beat later.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.services.espn_api import ESPNEvent
from app.tasks.espn_sync import _process_live_sport, espn_team_matches
from app.utils.espn_helpers import (
    ESPN_NOT_STARTED_KEY,
    espn_pregame_filler,
    match_event_to_espn,
    play_evidence,
    update_event_fields_from_espn,
)
from app.utils.game_state import _sanitize_period

from tests.test_authority_demotes_the_live_latch_5324 import (
    NOW,
    KICKOFF,
    SPORT,
    _FakeEvent,
    _FakeSession,
    _Recorder,
    _run_transition,
    _team,
)

import app.tasks.espn_sync as espn_sync_mod
from unittest.mock import patch

_LIVE_STATE = ("period", "game_clock", "home_score", "away_score")
_MIRRORED = _LIVE_STATE + ("status", "win_probability_sources")


def _board(status, *, detail, clock, period, hs, aws, espn_id="401860883"):
    """One ESPN board entry, with the values ESPN actually serves."""
    return ESPNEvent(
        espn_id=espn_id,
        name="Fresno State Bulldogs at Nevada Wolf Pack",
        short_name="FRES @ NEV",
        date=KICKOFF,
        status=status,
        status_detail=detail,
        period=period,
        clock=clock,
        home_team=_team("Nevada Wolf Pack", "Nevada"),
        away_team=_team("Fresno State Bulldogs", "Fresno State"),
        home_score=hs,
        away_score=aws,
        venue=None,
        broadcasts=[],
        home_win_probability=None,
    )


def _mlb_pregame():
    """ESPN 401817073 / 401817092 as served 2026-09-25 23:29Z (notice 26):
    STATUS_SCHEDULED, detail 'Scheduled', period 1, displayClock '0:00', score 0."""
    return _board("scheduled", detail="Scheduled", clock="0:00", period=1, hs=0, aws=0)


def _nhl_pregame():
    """ESPN 401879649 / 401879360 as served 2026-09-25: state pre, period 0,
    displayClock '0:00', detail a date, score 0."""
    return _board(
        "scheduled", detail="Fri, September 25th at 7:30 PM EDT",
        clock="0:00", period=0, hs=0, aws=0,
    )


class _RowSession(_FakeSession):
    """The rig's session, answering UPDATEs the way Postgres + SQLAlchemy do.

    `write_row_if_unmoved` reads `rowcount` and relies on the ORM-enabled
    UPDATE's session sync to mirror values onto the loaded row, so this applies
    the SET values to the (single) row and reports one row matched — unless
    `refuse_live_writes` is set, which stands in for another writer having
    moved the row between the decision and the compare-and-write.
    """

    def __init__(self, events, *, refuse_live_writes=False):
        super().__init__(events)
        self.row = events[0]
        self.updates = []
        self.refuse_live_writes = refuse_live_writes

    async def execute(self, stmt, *a, **k):
        if str(stmt).lstrip().upper().startswith("UPDATE"):
            params = stmt.compile().params
            self.updates.append(params)
            writes_live_state = any(column in params for column in _LIVE_STATE)
            if self.refuse_live_writes and writes_live_state:
                return type("R", (), {"rowcount": 0})()
            for column in _MIRRORED:
                if column in params:
                    setattr(self.row, column, params[column])
            return type("R", (), {"rowcount": 1})()
        return await super().execute(stmt, *a, **k)


def _live_pass(row, board, *, refuse_live_writes=False, update_fields=None):
    """One `_process_live_sport` pass through the REAL ESPN field writer."""
    rec = _Recorder()
    stats = {"events_synced": 0, "events_updated": 0, "errors": []}

    class _FrozenNow(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    session = _RowSession([row], refuse_live_writes=refuse_live_writes)
    with patch.object(espn_sync_mod, "datetime", _FrozenNow):
        asyncio.run(
            _process_live_sport(
                session, SPORT, [board], stats,
                NOW - timedelta(hours=6), NOW - timedelta(hours=5),
                espn_team_matches, rec.upsert_team, rec.register_identities,
                match_event_to_espn,
                update_fields or update_event_fields_from_espn,
                rec.write_win_prob, rec.compute_stat_model, rec.create_unmatched,
            )
        )
    return stats, session


def _started_row(**kw):
    """An anchored row the clock has just promoted to `live` at its listed start."""
    row = _FakeEvent(espn_id="401860883", status="live", **kw)
    row.win_probability_sources = {}
    return row


# ═══════════════════════════════════════════════════════════════════════════
# THE SHIP, through both real tasks
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("board", [_mlb_pregame, _nhl_pregame], ids=["mlb", "nhl"])
def test_a_game_the_authority_has_not_started_stops_reading_live(board):
    """The 23:30:17Z shape: promoted at its listed start, ESPN still pre-game.
    The live pass demotes it and the promoter one beat later holds it."""
    row = _started_row()

    stats, _ = _live_pass(row, board())

    assert row.status == "scheduled"
    assert stats["live_demoted_by_authority"] == 1
    assert ESPN_NOT_STARTED_KEY in row.win_probability_sources
    for column in _LIVE_STATE:
        assert getattr(row, column) is None, (
            f"{column} took the pre-game board's filler "
            f"({getattr(row, column)!r}); a scheduled game has no live state"
        )

    promote = _run_transition([row], now=NOW + timedelta(seconds=60))
    assert row.status == "scheduled", "the clock re-promoted a game nobody has started"
    assert promote["held_authority_not_started"] == 1


@pytest.mark.parametrize(
    "filler",
    [
        {"period": "Scheduled", "game_clock": "0:00", "home_score": 0, "away_score": 0},
        {"period": None, "game_clock": "0:00", "home_score": 0, "away_score": 0},
    ],
    ids=["mlb-15318665", "nhl-15314764"],
)
def test_a_row_already_carrying_the_filler_is_demoted_and_cleaned(filler):
    """The rows live on production at the release: the filler is already stored.
    It must not refuse the demotion, and it must leave the row, or the
    promoter's hold (which reads the row) is superseded by it one beat later."""
    row = _started_row(**filler)
    board = _mlb_pregame() if filler["period"] else _nhl_pregame()

    stats, _ = _live_pass(row, board)

    assert row.status == "scheduled"
    assert stats["pregame_filler_withdrawn"] == 1
    for column in _LIVE_STATE:
        assert getattr(row, column) is None
    promote = _run_transition([row], now=NOW + timedelta(seconds=60))
    assert row.status == "scheduled"
    assert promote["held_authority_not_started"] == 1


def test_a_second_scheduled_pass_keeps_the_hold():
    """The refresh arm, on the real writer: the second pass writes no filler
    back, so the row stays clean and the marker is refreshed."""
    row = _started_row()
    _live_pass(row, _mlb_pregame())
    stats, _ = _live_pass(row, _mlb_pregame())

    assert row.status == "scheduled"
    assert stats["authority_not_started_refreshed"] == 1
    assert row.period is None and row.game_clock is None


# ═══════════════════════════════════════════════════════════════════════════
# CONTROLS — the same harness must leave real play alone
# ═══════════════════════════════════════════════════════════════════════════


def test_THE_CONTROL_first_pitch_writes_the_scoreboard_and_stays_live():
    """ESPN flips to in-progress with the same '0:00' and a real inning: every
    column lands and the row is not touched."""
    row = _started_row()
    board = _board("in", detail="Top 1st", clock="0:00", period=1, hs=0, aws=0)

    stats, _ = _live_pass(row, board)

    assert row.status == "live"
    assert row.period == "Top 1st"
    assert row.game_clock == "0:00"
    assert (row.home_score, row.away_score) == (0, 0)
    assert stats.get("live_demoted_by_authority", 0) == 0


def test_THE_CONTROL_another_writers_inning_outranks_a_lagging_board():
    """`mlb_sync` routinely says 'Top 1st' while ESPN still says pre-game. That
    period is not the board's filler, so it stays evidence and nothing moves."""
    row = _started_row(period="Top 1st", game_clock="0:00", home_score=0, away_score=0)

    stats, _ = _live_pass(row, _mlb_pregame())

    assert row.status == "live"
    assert row.period == "Top 1st"
    assert stats.get("live_demoted_by_authority", 0) == 0
    assert stats.get("pregame_filler_withdrawn", 0) == 0


def test_THE_CONTROL_a_race_lost_on_the_withdrawal_demotes_nothing():
    """If another writer moved the row between the read and the withdrawal,
    something real may have landed — this pass neither withdraws nor demotes."""
    row = _started_row(period="Scheduled", game_clock="0:00", home_score=0, away_score=0)

    stats, _ = _live_pass(row, _mlb_pregame(), refuse_live_writes=True)

    assert row.status == "live"
    assert stats.get("live_demoted_by_authority", 0) == 0
    assert ESPN_NOT_STARTED_KEY not in row.win_probability_sources


def test_THE_STRAWMAN_the_old_fixture_hid_the_defect():
    """Why `66ce552da` shipped inert: the filler IS play evidence to the shared
    definition. If this ever goes False the discount above is dead weight."""
    assert play_evidence(0, 0, None, "0:00") is True
    assert play_evidence(0, 0, "Scheduled", None) is True
    assert _sanitize_period("Scheduled") == "Scheduled"


def test_THE_STRAWMAN_copying_the_board_refuses_the_demotion():
    """A writer that copies the board verbatim (the pre-fix behaviour, which the
    old rig's recorder also modelled) plus a row without the discount: the pass
    must still demote, because the discount recognises the board's own values."""
    row = _started_row()
    stats, _ = _live_pass(row, _mlb_pregame(), update_fields=_copy_everything)

    assert row.status == "scheduled"
    assert stats["pregame_filler_withdrawn"] == 1


async def _copy_everything(session, event, ee, claimed, stats):
    event.period = _sanitize_period(ee.status_detail)
    event.game_clock = ee.clock
    event.home_score = ee.home_score
    event.away_score = ee.away_score
    return True


# ═══════════════════════════════════════════════════════════════════════════
# THE WRITER, on the UPDATE's own params
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("board", [_mlb_pregame, _nhl_pregame], ids=["mlb", "nhl"])
def test_the_writer_takes_no_live_state_from_a_pregame_board(board):
    row = _started_row()
    session = _RowSession([row])
    stats = {"errors": []}

    asyncio.run(update_event_fields_from_espn(session, row, board(), set(), stats))

    for params in session.updates:
        for column in _LIVE_STATE:
            assert column not in params, f"wrote {column}={params[column]!r}"
    assert stats["pregame_board_live_writes_refused"] == 1


def test_a_nonzero_board_score_still_lands_on_a_scheduled_board():
    """The safety valve #8247 kept: a score is not a value a board invents."""
    row = _started_row()
    session = _RowSession([row])
    board = _board("scheduled", detail="Scheduled", clock="0:00", period=1, hs=2, aws=0)

    asyncio.run(update_event_fields_from_espn(session, row, board, set(), {"errors": []}))

    assert row.home_score == 2


# ═══════════════════════════════════════════════════════════════════════════
# THE DISCOUNT, pure
# ═══════════════════════════════════════════════════════════════════════════


def test_the_filler_is_recognised_only_on_a_scheduled_board():
    assert espn_pregame_filler(
        "in", "Top 1st", "0:00", 0, 0,
        period="Top 1st", game_clock="0:00", home_score=0, away_score=0,
    ) == {}


def test_a_board_with_a_score_has_no_filler():
    assert espn_pregame_filler(
        "scheduled", "Scheduled", "0:00", 1, 0,
        period="Scheduled", game_clock="0:00", home_score=1, away_score=0,
    ) == {}


def test_only_exact_matches_are_filler():
    assert espn_pregame_filler(
        "scheduled", "Scheduled", "0:00", 0, 0,
        period="Top 1st", game_clock="12:00", home_score=None, away_score=None,
    ) == {}


def test_a_real_score_on_the_row_is_never_withdrawn():
    assert espn_pregame_filler(
        "scheduled", "Scheduled", "0:00", 0, 0,
        period="Scheduled", game_clock="0:00", home_score=3, away_score=1,
    ) == {"period": None, "game_clock": None}


def test_a_boolean_is_not_a_zero_score():
    out = espn_pregame_filler(
        "scheduled", None, "0:00", 0, 0,
        period=None, game_clock=None, home_score=False, away_score=0,
    )
    assert "home_score" not in out and out.get("away_score", "x") is None
