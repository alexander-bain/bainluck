"""#9049 — the ESPN live pass lets go of each game's row before its next ESPN call.

## the ship

A new live price and a new live score reach the page without queueing behind
the ESPN live sync.

## what production showed (2026-09-27 04:14–04:21Z, 21 samples)

12 lock waits of up to 17.6 s on `events`. Every blocker was this pass, idle in
transaction for 11.9–22.8 s: `_sync_espn_live_events` ran every step in ONE
transaction, and a `_step_savepoint` (#8796) does not release a row lock. So a
game's row stayed locked from its score write in the live loop until the last
box-score fetch had come back from ESPN. Queued behind it: the socket's price
write (10.65 s), the live poll's locked read (8.25 s), a score write (8.21 s).

## the rules these tests pin

* the task commits — and publishes the frames that commit confirmed — after
  every live sport and after every later pass, never inside a savepoint;
* `fetch_live_box_scores` asks ESPN for every game FIRST and writes after, so no
  game's row is written (locked) while another game's fetch is in flight;
* inside one sport, the dated board (#5697 widening) is asked for BEFORE the
  first game is written (CERT-3611: game A written, then game B waited on
  ESPN with A's row locked).

Real-Postgres arms (the lock itself, not the call order):
`tests/integration/test_espn_pass_releases_rows_pg_9049.py`.
"""

from __future__ import annotations

import contextlib
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio

MLB, NHL = "baseball_mlb", "icehockey_nhl"


# ── fetch_live_box_scores: every fetch before any write ──────────────────────


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _LoggingSession:
    """Answers the SELECT with `events`; logs each write into the shared log."""

    def __init__(self, events, log, fail_write_for=None):
        self._events = events
        self._log = log
        self._fail = fail_write_for

    async def execute(self, statement, params=None):
        if params is None:
            return _Result(self._events)
        if params["eid"] == self._fail:
            raise RuntimeError("write failed")
        self._log.append(("write", params["eid"]))
        return _Result([])

    def begin_nested(self):
        # #8913: each game's write runs in its own SAVEPOINT. The fake has no
        # transaction to abort; the real-Postgres half is
        # tests/integration/test_live_box_pass_survives_one_failed_write_pg_8913.py.
        return contextlib.nullcontext()


def _live_event(event_id):
    event = MagicMock()
    event.id = event_id
    event.espn_id = f"espn-{event_id}"
    event.status = "live"
    event.box_score_data = None
    event.sport = MagicMock()
    event.sport.key = MLB
    return event


class _Espn:
    def __init__(self, log, dark=()):
        self._log = log
        self._dark = set(dark)

    async def get_event_context(self, sport_key, espn_id):
        event_id = int(espn_id.split("-")[1])
        self._log.append(("fetch", event_id))
        if event_id in self._dark:
            raise RuntimeError("ESPN timed out")
        return {"box_score": {"P": {"h": 1}}, "scoring_plays": [], "scores": {}}

    async def close(self):
        pass


async def _run_box_pass(events, log, *, dark=(), fail_write_for=None):
    from app.utils import espn_helpers

    stats: dict = {}
    session = _LoggingSession(events, log, fail_write_for)
    with patch("app.services.espn_api.ESPNAPIService", return_value=_Espn(log, dark)):
        await espn_helpers.fetch_live_box_scores(session, stats)
    return stats


async def test_no_game_is_written_while_another_games_fetch_is_in_flight():
    """THE SHIP (call order). RED before #9049: fetch 1, write 1, fetch 2 … —
    game 1's row locked through the other fetches."""
    log: list = []
    await _run_box_pass([_live_event(1), _live_event(2), _live_event(3)], log)

    kinds = [kind for kind, _ in log]
    assert kinds == ["fetch"] * 3 + ["write"] * 3, log
    # Same games, same order: only the network moved out from between them.
    assert [e for k, e in log if k == "write"] == [e for k, e in log if k == "fetch"]


async def test_every_game_still_gets_its_box_score():
    """KILL CONTROL. A pass that fetched and never wrote satisfies the order
    test vacuously; each fetched game must land its write and its count."""
    log: list = []
    stats = await _run_box_pass([_live_event(1), _live_event(2)], log)

    assert sorted(e for k, e in log if k == "write") == [1, 2]
    assert stats["live_box_scores_fetched"] == 2


async def test_one_games_failed_fetch_or_write_costs_only_that_game():
    """The per-game try/except survives the split: a dark fetch (2) and a failed
    write (3) each cost their own game here. That is the Python half only — on
    Postgres a failed UPDATE aborts the transaction, which the per-game
    savepoint (#8913) contains; that half is proved on a real server in
    tests/integration/test_live_box_pass_survives_one_failed_write_pg_8913.py."""
    log: list = []
    stats = await _run_box_pass(
        [_live_event(1), _live_event(2), _live_event(3), _live_event(4)],
        log,
        dark={2},
        fail_write_for=3,
    )

    assert sorted(e for k, e in log if k == "write") == [1, 4]
    assert stats["live_box_scores_fetched"] == 2


# ── the task: a commit (and its frames) after every sport and every pass ─────


def _wire(monkeypatch, log):
    import app.services.espn_api as espn_api
    import app.tasks.espn_sync as espn_sync
    import app.utils.espn_helpers as helpers
    import app.utils.nonvenue_live_push as push

    class _Nested:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *exc):
            return False

    async def _flush():
        return None

    async def _execute(*a, **k):
        # #9143: the pre-game prefetch reads rows; an empty result, as a real
        # session with nothing scheduled would return.
        return SimpleNamespace(all=lambda: [])

    async def _commit():
        log.append("commit")

    session = SimpleNamespace(
        begin_nested=_Nested, flush=_flush, execute=_execute, commit=_commit, info={}
    )

    class _Session:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *exc):
            log.append("final")
            return False

    class _Board:
        async def get_scoreboard(self, *a, **k):
            return [object()]

        async def close(self):
            pass

    async def _noop(*a, **k):
        return None

    async def _keys(_session):
        return [MLB, NHL], [MLB]

    async def _decide(*a, **k):
        return {}

    async def _live(_session, sport_key, *a, **k):
        log.append(f"live:{sport_key}")

    def _step(name):
        async def _run(*a, **k):
            log.append(name)

        return _run

    async def _publish(_session):
        log.append("publish")

    monkeypatch.setattr(espn_sync, "get_task_session", lambda **k: _Session())
    monkeypatch.setattr(espn_api, "ESPNAPIService", lambda: _Board())
    monkeypatch.setattr(espn_sync, "_find_sport_keys_to_sync", _keys)
    for name in (
        "_settle_authority_stragglers",
        "_settle_deep_authority_stragglers",
        "_act_on_failovers",
    ):
        monkeypatch.setattr(espn_sync, name, _noop)
    monkeypatch.setattr(
        espn_sync, "_recover_unstarted_authority_fixtures", _step("stragglers")
    )
    monkeypatch.setattr(espn_sync, "_decide_failovers", _decide)
    monkeypatch.setattr(espn_sync, "_fetch_full_slate_boards", _decide)
    monkeypatch.setattr(espn_sync, "_process_live_sport", _live)
    monkeypatch.setattr(espn_sync, "scheduled_board_for", lambda k, b, f: b)
    monkeypatch.setattr(helpers, "sync_scheduled_events", _step("scheduled"))
    monkeypatch.setattr(helpers, "fetch_completed_box_scores", _step("completed_box"))
    monkeypatch.setattr(helpers, "fetch_live_box_scores", _step("live_box"))
    monkeypatch.setattr(helpers, "backfill_missing_scores", _step("backfill"))
    monkeypatch.setattr(push, "publish_committed_nonvenue_frames", _publish)


def _released_between(log, before, after):
    i, j = log.index(before), log.index(after)
    return "commit" in log[i + 1 : j]


async def test_the_pass_commits_between_every_sport_and_every_pass(monkeypatch):
    """THE SHIP (task shape). RED before #9049: one commit, at `final`."""
    from app.tasks.espn_sync import _sync_espn_live_events

    log: list = []
    _wire(monkeypatch, log)
    stats = await _sync_espn_live_events()

    assert stats["errors"] == [], stats["errors"]
    for before, after in (
        ("stragglers", f"live:{MLB}"),  # before the scoreboard fetches
        (f"live:{MLB}", f"live:{NHL}"),  # one sport's rows free before the next
        (f"live:{NHL}", "completed_box"),  # before any box-score network call
        ("scheduled", "completed_box"),
        ("completed_box", "live_box"),
        ("live_box", "backfill"),
    ):
        assert _released_between(log, before, after), (before, after, log)


async def test_every_commit_publishes_the_frames_it_confirmed(monkeypatch):
    """A score push a mid-pass commit confirmed goes out then, not after the
    whole pass (and not before its commit: fanout cannot undo a write)."""
    from app.tasks.espn_sync import _sync_espn_live_events

    log: list = []
    _wire(monkeypatch, log)
    await _sync_espn_live_events()

    commits = [i for i, entry in enumerate(log) if entry == "commit"]
    assert commits, log
    for i in commits:
        assert log[i + 1] == "publish", log
    assert log.count("publish") == len(commits)


async def test_a_failed_sport_still_releases_before_the_next(monkeypatch):
    """The release sits OUTSIDE the sport's savepoint: a sport that raised has
    been rolled back to its savepoint, and the next sport still starts on a
    released row set."""
    import app.tasks.espn_sync as espn_sync
    from app.tasks.espn_sync import _sync_espn_live_events

    log: list = []
    _wire(monkeypatch, log)

    async def _live(_session, sport_key, *a, **k):
        log.append(f"live:{sport_key}")
        if sport_key == MLB:
            raise RuntimeError("deadlock detected")

    monkeypatch.setattr(espn_sync, "_process_live_sport", _live)
    stats = await _sync_espn_live_events()

    assert [e.split(":")[0] for e in stats["errors"]] == [MLB]
    assert _released_between(log, f"live:{MLB}", f"live:{NHL}"), log


# ── inside one sport: the dated board is asked before the first write ────────


async def test_the_dated_board_is_fetched_before_any_game_in_the_sport_is_written():
    """CERT-3611's path. Game A (on the undated board) is written, then game B
    (only on the dated board) waits on ESPN — A's row locked across the wait.
    RED at 0fd0bd5ea3: `write A` came before `fetch`."""
    from app.tasks.espn_sync import _process_live_sport, espn_team_matches
    from app.utils.espn_helpers import match_event_to_espn
    from tests.test_undated_board_is_a_slice_5697 import (
        DATED_BOARD,
        NOW,
        SPORT,
        UNDATED_BOARD,
        _FakeEvent,
        _FakeSession,
        _Recorder,
    )

    log: list = []
    a = _FakeEvent("Michigan Wolverines", "Oklahoma Sooners")
    b = _FakeEvent("Purdue Boilermakers", "Wake Forest Demon Deacons")

    class _Logging(_Recorder):
        async def update_fields(self, session, event, ee, claimed, stats):
            log.append(("write", event.id))
            return await super().update_fields(session, event, ee, claimed, stats)

    async def _fetch(sport_key, board_day):
        log.append(("fetch", board_day))
        return DATED_BOARD

    rec = _Logging()
    stats = {"events_synced": 0, "events_updated": 0, "errors": []}
    await _process_live_sport(
        _FakeSession([a, b]), SPORT, UNDATED_BOARD, stats,
        NOW - timedelta(hours=6), NOW - timedelta(hours=5),
        espn_team_matches, rec.upsert_team, rec.register_identities,
        match_event_to_espn, rec.update_fields, rec.write_win_prob,
        rec.compute_stat_model, rec.create_unmatched,
        dated_board_fetcher=_fetch,
    )

    assert [kind for kind, _ in log] == ["fetch", "write", "write"], log
    # WIDENING CONTROL: moving the fetch did not cost B its dated-board match.
    assert rec.updated == [(a.id, "401856679"), (b.id, "401858224")]
    assert stats["events_matched_on_dated_board"] == 1
    assert stats["dated_board_fetches"] == 1


async def test_a_sport_the_undated_board_fully_covers_asks_for_no_dated_board():
    """The dry run must not turn into a fetch per sport: every game matched on
    the undated board ⇒ no ESPN call, as before."""
    from app.tasks.espn_sync import _process_live_sport, espn_team_matches
    from app.utils.espn_helpers import match_event_to_espn
    from tests.test_undated_board_is_a_slice_5697 import (
        NOW,
        SPORT,
        UNDATED_BOARD,
        _FakeEvent,
        _FakeSession,
        _Recorder,
    )

    fetched: list = []

    async def _fetch(sport_key, board_day):
        fetched.append(board_day)
        return []

    rec = _Recorder()
    stats = {"events_synced": 0, "events_updated": 0, "errors": []}
    await _process_live_sport(
        _FakeSession([_FakeEvent("Michigan Wolverines", "Oklahoma Sooners")]),
        SPORT, UNDATED_BOARD, stats,
        NOW - timedelta(hours=6), NOW - timedelta(hours=5),
        espn_team_matches, rec.upsert_team, rec.register_identities,
        match_event_to_espn, rec.update_fields, rec.write_win_prob,
        rec.compute_stat_model, rec.create_unmatched,
        dated_board_fetcher=_fetch,
    )

    assert fetched == []
    assert stats["events_synced"] == 1


async def test_a_doubleheaders_second_game_still_reaches_the_dated_board():
    """CERT-3617's case. Two id-less rows, same teams, same day, inside the
    3 h name window; the undated board carries only game 1. Both rows name-match
    game 1 unless the first one's claim is counted — and it is the LOOP's claim
    that sends row 2 to the dated board, where game 2 is. RED at 12f612b5fa
    (the dry run claimed nothing: no board fetched, row 2 lost its score)."""
    from app.tasks.espn_sync import _process_live_sport, espn_team_matches
    from app.utils.espn_helpers import match_event_to_espn
    from tests.test_undated_board_is_a_slice_5697 import (
        KICKOFF,
        NOW,
        SPORT,
        _espn_event,
        _FakeEvent,
        _FakeSession,
        _Recorder,
    )

    game_1 = _espn_event(
        "9049001", "Purdue Boilermakers", "Purdue",
        "Wake Forest Demon Deacons", "Wake Forest", 7, 3,
    )
    game_2 = _espn_event(
        "9049002", "Purdue Boilermakers", "Purdue",
        "Wake Forest Demon Deacons", "Wake Forest", 0, 14,
        when=KICKOFF + timedelta(hours=2, minutes=30),
    )
    row_1 = _FakeEvent("Purdue Boilermakers", "Wake Forest Demon Deacons")
    row_2 = _FakeEvent(
        "Purdue Boilermakers", "Wake Forest Demon Deacons",
        commence=KICKOFF + timedelta(hours=2, minutes=30),
    )

    class _Claiming(_Recorder):
        async def update_fields(self, session, event, ee, claimed, stats):
            # What the real writers do with a matched game's id
            # (`write_espn_win_probability`, `espn_id_stamp`).
            claimed.add(ee.espn_id)
            return await super().update_fields(session, event, ee, claimed, stats)

    fetched: list = []

    async def _fetch(sport_key, board_day):
        fetched.append(board_day)
        return [game_1, game_2]

    rec = _Claiming()
    stats = {"events_synced": 0, "events_updated": 0, "errors": []}
    await _process_live_sport(
        _FakeSession([row_1, row_2]), SPORT, [game_1], stats,
        NOW - timedelta(hours=6), NOW - timedelta(hours=5),
        espn_team_matches, rec.upsert_team, rec.register_identities,
        match_event_to_espn, rec.update_fields, rec.write_win_prob,
        rec.compute_stat_model, rec.create_unmatched,
        dated_board_fetcher=_fetch,
    )

    assert len(fetched) == 1, fetched
    assert rec.updated == [(row_1.id, "9049001"), (row_2.id, "9049002")], rec.updated
    assert (row_2.home_score, row_2.away_score) == (0, 14)
    assert stats["events_matched_on_dated_board"] == 1


# ── CERT-3620: the assignment does not depend on the order the rows arrive ──


def _doubleheader():
    from tests.test_undated_board_is_a_slice_5697 import KICKOFF, _espn_event

    game_1 = _espn_event(
        "9049001", "Purdue Boilermakers", "Purdue",
        "Wake Forest Demon Deacons", "Wake Forest", 7, 3,
    )
    game_2 = _espn_event(
        "9049002", "Purdue Boilermakers", "Purdue",
        "Wake Forest Demon Deacons", "Wake Forest", 0, 14,
        when=KICKOFF + timedelta(hours=2, minutes=30),
    )
    return game_1, game_2


async def _run_live_sport(rows, undated, fetch):
    from app.tasks.espn_sync import _process_live_sport, espn_team_matches
    from app.utils.espn_helpers import match_event_to_espn
    from tests.test_undated_board_is_a_slice_5697 import (
        NOW,
        SPORT,
        _FakeSession,
        _Recorder,
    )

    class _Claiming(_Recorder):
        async def update_fields(self, session, event, ee, claimed, stats):
            claimed.add(ee.espn_id)
            return await super().update_fields(session, event, ee, claimed, stats)

    rec = _Claiming()
    stats = {"events_synced": 0, "events_updated": 0, "errors": []}
    await _process_live_sport(
        _FakeSession(rows), SPORT, undated, stats,
        NOW - timedelta(hours=6), NOW - timedelta(hours=5),
        espn_team_matches, rec.upsert_team, rec.register_identities,
        match_event_to_espn, rec.update_fields, rec.write_win_prob,
        rec.compute_stat_model, rec.create_unmatched,
        dated_board_fetcher=fetch,
    )
    return dict(rec.updated), stats


@pytest.mark.parametrize("order", ["as-listed", "reversed"])
async def test_a_doubleheader_keeps_each_game_on_its_own_row_in_either_order(order):
    """CERT-3620's case. The live query has no ORDER BY; when the LATER row came
    back first it claimed game 1 off the undated board and the earlier row then
    took game 2 off the dated one: two swapped live scores. RED `reversed` at
    942e466df3 (row 2 got 9049001, row 1 got 9049002)."""
    from tests.test_undated_board_is_a_slice_5697 import KICKOFF, _FakeEvent

    game_1, game_2 = _doubleheader()
    row_1 = _FakeEvent("Purdue Boilermakers", "Wake Forest Demon Deacons")
    row_2 = _FakeEvent(
        "Purdue Boilermakers", "Wake Forest Demon Deacons",
        commence=KICKOFF + timedelta(hours=2, minutes=30),
    )
    rows = [row_1, row_2] if order == "as-listed" else [row_2, row_1]

    async def _fetch(sport_key, board_day):
        return [game_1, game_2]

    assigned, _ = await _run_live_sport(rows, [game_1], _fetch)
    assert assigned == {row_1.id: "9049001", row_2.id: "9049002"}, assigned
    assert (row_2.home_score, row_2.away_score) == (0, 14)
    assert (row_1.home_score, row_1.away_score) == (7, 3)


async def test_a_row_is_matched_on_its_own_days_board_when_that_board_was_fetched():
    """The pool arm alone, which chronological order cannot supply. Game 1's row
    is not ours; another game on the same day sends the pass to the dated board.
    Against the undated board, row 2's nearest name match is game 1 (2.5 h
    away, inside the window) and it would print game 1's score. Against its own
    day's board, game 2 is nearer. RED with the dated pool asked only after an
    undated miss."""
    from tests.test_undated_board_is_a_slice_5697 import (
        KICKOFF,
        _espn_event,
        _FakeEvent,
    )

    game_1, game_2 = _doubleheader()
    other = _espn_event(
        "9049003", "Iowa Hawkeyes", "Iowa",
        "Ohio State Buckeyes", "Ohio State", 21, 17,
    )
    row_2 = _FakeEvent(
        "Purdue Boilermakers", "Wake Forest Demon Deacons",
        commence=KICKOFF + timedelta(hours=2, minutes=30),
    )
    row_other = _FakeEvent("Iowa Hawkeyes", "Ohio State Buckeyes")

    async def _fetch(sport_key, board_day):
        return [game_1, game_2, other]

    assigned, stats = await _run_live_sport([row_other, row_2], [game_1], _fetch)
    assert assigned == {row_other.id: "9049003", row_2.id: "9049002"}, assigned
    assert (row_2.home_score, row_2.away_score) == (0, 14)
    assert stats["events_matched_on_dated_board"] == 2


async def test_with_no_dated_board_the_later_row_cannot_take_the_earlier_game():
    """The order arm alone, which the pool cannot supply: the dated board is
    dark, so only the undated board (game 1) exists. In chronological order row
    1 takes game 1 and row 2 honestly has no game. Asked later-row-first, row 2
    took game 1 and printed the other game's score. RED without the sort."""
    from tests.test_undated_board_is_a_slice_5697 import KICKOFF, _FakeEvent

    game_1, _game_2 = _doubleheader()
    row_1 = _FakeEvent("Purdue Boilermakers", "Wake Forest Demon Deacons")
    row_2 = _FakeEvent(
        "Purdue Boilermakers", "Wake Forest Demon Deacons",
        commence=KICKOFF + timedelta(hours=2, minutes=30),
    )

    async def _dark(sport_key, board_day):
        return None

    assigned, _ = await _run_live_sport([row_2, row_1], [game_1], _dark)
    assert assigned == {row_1.id: "9049001"}, assigned
    assert (row_2.home_score, row_2.away_score) == (None, None)
