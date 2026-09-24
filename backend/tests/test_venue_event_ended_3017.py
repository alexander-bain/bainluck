"""#3017: Polymarket's event record says an anchor-less match ended → off the live board.

The payloads below are the venue's own records for shopper pass 0039's
specimens, read from Gamma 2026-09-24 14:2xZ and trimmed to the fields the rule
reads. `CAN` is the case that matters most: a cancelled match whose page read
"LIVE 71%", with a finish time eleven hours BEFORE its kickoff.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils.venue_event_ended import (
    FINISH_CLOCK_SKEW,
    START_AGREEMENT_WINDOW,
    SUSPEND_ON_VENUE_EVENT_ENDED_SQL,
    VENUE_EVENT_ENDED_CANDIDATES_SQL,
    gamma_event_id_from_group,
    gamma_record_says_ended,
    row_carries_no_authority_id,
    row_verdict,
)

KICKOFF = datetime(2026, 9, 24, 11, 35, tzinfo=timezone.utc)
NOW = datetime(2026, 9, 24, 14, 20, tzinfo=timezone.utc)

# 1004368 China PR vs. Palestine — cancelled before kickoff.
CANCELLED = {
    "id": "1004368",
    "gameId": 90123064,
    "live": False,
    "ended": True,
    "period": "CAN",
    "score": "0-0",
    "startTime": "2026-09-24T11:35:00Z",
    "finishedTimestamp": "2026-09-24T00:00:06.122331Z",
}
# 1006074 — the same fixture's "More Markets" event: same gameId, same story.
CANCELLED_MORE = dict(CANCELLED, id="1006074")
# 1069107 China PR vs. Maldives — full time after extra (VFT), 3-0.
FINISHED = {
    "id": "1069107",
    "gameId": 90123244,
    "live": False,
    "ended": True,
    "period": "VFT",
    "score": "3-0",
    "startTime": "2026-09-24T11:35:00Z",
    "finishedTimestamp": "2026-09-24T13:31:50.381284Z",
}
# 1024559 Uzbekistan vs. IR Iran - More Markets, read in play at 14:2xZ.
IN_PLAY = {
    "id": "1024559",
    "gameId": 90123999,
    "live": True,
    "ended": False,
    "period": "1H",
    "score": "1-0",
    "startTime": "2026-09-24T14:00:00Z",
}
# 1071440 Counter-Strike: ended per MAP, no finish time — must not end a match.
ESPORTS_MAP = {
    "id": "1071440",
    "gameId": 5550001,
    "live": False,
    "ended": True,
    "period": "2/3",
    "score": "000-000|2-0|Bo3",
    "startTime": "2026-09-24T11:35:00Z",
}
# 1069911-shaped: a derivative market's event with no sports block at all.
NO_SPORTS_BLOCK = {"id": "1069911", "startTime": "2026-09-24T11:35:00Z"}


def _ended(p, commence=KICKOFF, now=NOW):
    return gamma_record_says_ended(p, commence_time=commence, now=now)


# ── the specimens ──────────────────────────────────────────────────────────


def test_the_cancelled_specimen_leaves_the_live_board():
    assert (
        row_verdict([CANCELLED, CANCELLED_MORE], commence_time=KICKOFF, now=NOW)
        == "CAN"
    )


def test_the_finished_specimen_leaves_the_live_board():
    assert row_verdict([FINISHED], commence_time=KICKOFF, now=NOW) == "VFT"


def test_a_cancellation_finishing_before_kickoff_is_still_a_ruling():
    # The finish precedes kickoff by 11.5h; the rule reads the record's
    # startTime for fixture agreement, never the finish time.
    assert _parse(CANCELLED["finishedTimestamp"]) < KICKOFF
    assert _ended(CANCELLED)


def test_a_match_in_play_is_held():
    in_play_kickoff = datetime(2026, 9, 24, 14, 0, tzinfo=timezone.utc)
    assert row_verdict([IN_PLAY], commence_time=in_play_kickoff, now=NOW) is None


# ── each refusal, one at a time, from a record that otherwise passes ────────


def test_the_control_record_passes():
    # Every refusal below mutates THIS record; if it did not pass, each
    # refusal test would pass vacuously.
    assert _ended(FINISHED)


@pytest.mark.parametrize("value", [None, False, "true", 1, "True"])
def test_ended_must_be_the_literal_true(value):
    assert not _ended(dict(FINISHED, ended=value))


def test_a_record_that_says_live_is_held_even_if_it_says_ended():
    assert not _ended(dict(FINISHED, live=True))


@pytest.mark.parametrize("value", [None, "", 0])
def test_no_game_id_means_no_sports_feed(value):
    assert not _ended(dict(FINISHED, gameId=value))


def test_ended_per_map_with_no_finish_time_is_held():
    assert not _ended(ESPORTS_MAP)
    assert not _ended(dict(FINISHED, finishedTimestamp=None))
    assert not _ended(dict(FINISHED, finishedTimestamp="not a time"))


def test_a_finish_time_in_the_future_is_held():
    ahead = NOW + FINISH_CLOCK_SKEW + timedelta(minutes=1)
    assert not _ended(dict(FINISHED, finishedTimestamp=ahead.isoformat()))
    within_skew = NOW + FINISH_CLOCK_SKEW - timedelta(minutes=1)
    assert _ended(dict(FINISHED, finishedTimestamp=within_skew.isoformat()))


def test_a_record_for_a_different_fixture_is_held():
    far = KICKOFF + START_AGREEMENT_WINDOW + timedelta(minutes=1)
    near = KICKOFF + START_AGREEMENT_WINDOW - timedelta(minutes=1)
    assert not _ended(dict(FINISHED, startTime=far.isoformat()))
    assert _ended(dict(FINISHED, startTime=near.isoformat()))
    assert not _ended(dict(FINISHED, startTime=None))


def test_a_naive_commence_time_is_read_as_utc():
    assert _ended(FINISHED, commence=KICKOFF.replace(tzinfo=None))


# ── the row: every sports record must tell one story ────────────────────────


def test_a_row_with_no_sports_record_is_held():
    assert row_verdict([NO_SPORTS_BLOCK], commence_time=KICKOFF, now=NOW) is None
    assert row_verdict([], commence_time=KICKOFF, now=NOW) is None


def test_a_non_sports_sibling_neither_rules_nor_blocks():
    assert (
        row_verdict([FINISHED, NO_SPORTS_BLOCK], commence_time=KICKOFF, now=NOW)
        == "VFT"
    )


def test_a_sibling_record_still_live_holds_the_row():
    lagging = dict(FINISHED, id="1070761", live=True, ended=False, period="2H")
    assert row_verdict([FINISHED, lagging], commence_time=KICKOFF, now=NOW) is None
    assert row_verdict([lagging, FINISHED], commence_time=KICKOFF, now=NOW) is None


def test_records_naming_two_game_ids_hold_the_row():
    other_fixture = dict(CANCELLED, startTime=FINISHED["startTime"])
    assert _ended(other_fixture) and _ended(FINISHED)
    assert (
        row_verdict([FINISHED, other_fixture], commence_time=KICKOFF, now=NOW) is None
    )


def test_a_blank_period_still_rules_and_says_so():
    assert (
        row_verdict([dict(FINISHED, period="")], commence_time=KICKOFF, now=NOW)
        == "ended"
    )


# ── ids ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "group_id, expected",
    [
        ("polymarket:1004368", "1004368"),
        ("polymarket: 1004368 ", "1004368"),
        ("polymarket:0xabc", None),
        ("polymarket:", None),
        ("kalshi:KXWTA-26SEP24", None),
        (None, None),
        (1004368, None),
    ],
)
def test_group_id_to_gamma_event_id(group_id, expected):
    assert gamma_event_id_from_group(group_id) == expected


@pytest.mark.parametrize(
    "espn_id, statpal_id, expected",
    [(None, None, True), ("", "  ", True), ("401", None, False), (None, "sp1", False)],
)
def test_an_anchored_row_is_not_this_rails(espn_id, statpal_id, expected):
    assert row_carries_no_authority_id(espn_id, statpal_id) is expected


# ── the SQL ─────────────────────────────────────────────────────────────────


def _norm(sql):
    return " ".join(sql.split())


def test_the_write_is_a_compare_and_set_that_yields_to_an_authority():
    sql = _norm(SUSPEND_ON_VENUE_EVENT_ENDED_SQL)
    assert sql.startswith("UPDATE events")
    assert "SET status = 'suspended' WHERE" in sql
    for clause in (
        "status = 'live'",
        "completed_at IS NULL",
        "NULLIF(btrim(espn_id), '') IS NULL",
        "NULLIF(btrim(statpal_fixture_id), '') IS NULL",
    ):
        assert clause in sql, clause


def test_the_write_sets_nothing_but_status():
    set_clause = (
        _norm(SUSPEND_ON_VENUE_EVENT_ENDED_SQL)
        .split(" SET ", 1)[1]
        .split(" WHERE ", 1)[0]
    )
    assert set_clause == "status = 'suspended'"


def test_the_candidate_read_binds_its_prefix():
    # gotcha #45: a colon inside a text() literal parses as a bind parameter.
    sql = _norm(VENUE_EVENT_ENDED_CANDIDATES_SQL)
    assert "starts_with(fm.group_id, :group_prefix)" in sql
    assert "'polymarket:" not in sql
    for clause in (
        "e.status = 'live'",
        "e.commence_time <= :now",
        "e.completed_at IS NULL",
        "fm.source = 'polymarket'",
    ):
        assert clause in sql, clause


# ── the pass ────────────────────────────────────────────────────────────────


class _Result:
    def __init__(self, rows, rowcount=0):
        self._rows = rows
        self.rowcount = rowcount

    def all(self):
        return list(self._rows)


class _Session:
    def __init__(self, rows, write_rowcount=None):
        self._rows = rows
        self.write_rowcount = write_rowcount
        self.selects = []
        self.writes = []
        self.commits = 0

    async def execute(self, stmt, params=None):
        if str(stmt).startswith("UPDATE"):
            self.writes.append(params)
            n = (
                len(params["event_ids"])
                if self.write_rowcount is None
                else self.write_rowcount
            )
            return _Result([], rowcount=n)
        self.selects.append(params)
        return _Result(self._rows)

    async def commit(self):
        self.commits += 1


class _Ctx:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False


class _Service:
    def __init__(self, payloads, fail=False):
        self._payloads = {p["id"]: p for p in payloads}
        self.fail = fail
        self.calls = []

    async def get_events_by_ids(self, ids):
        self.calls.append(list(ids))
        if self.fail:
            raise RuntimeError("gamma 503")
        return [self._payloads[i] for i in ids if i in self._payloads]


def _row(event_id, groups, espn_id=None, statpal=None, commence=KICKOFF):
    return SimpleNamespace(
        event_id=event_id,
        home_team_name="China PR",
        away_team_name="Palestine",
        commence_time=commence,
        espn_id=espn_id,
        statpal_fixture_id=statpal,
        group_ids=groups,
    )


async def _run(monkeypatch, rows, service, write_rowcount=None):
    import app.tasks.venue_event_ended as mod

    session = _Session(rows, write_rowcount)
    monkeypatch.setattr(mod, "get_task_session", lambda: _Ctx(session))
    stats = await mod._suspend_venue_ended_events(service=service, now=NOW)
    return stats, session


@pytest.mark.asyncio
async def test_the_pass_suspends_the_specimens_and_holds_the_live_match(monkeypatch):
    rows = [
        _row(15310213, ["polymarket:1004368", "polymarket:1006074"]),
        _row(15317878, ["polymarket:1069107"]),
        _row(
            15318999,
            ["polymarket:1024559"],
            commence=datetime(2026, 9, 24, 14, 0, tzinfo=timezone.utc),
        ),
    ]
    service = _Service([CANCELLED, CANCELLED_MORE, FINISHED, IN_PLAY])
    stats, session = await _run(monkeypatch, rows, service)

    assert session.selects[0]["group_prefix"] == "polymarket:"
    assert session.writes == [{"event_ids": [15310213, 15317878]}]
    assert session.commits == 1
    assert stats["ruled"] == 2 and stats["suspended"] == 2
    assert stats["held_not_ended"] == 1
    assert service.calls == [["1004368", "1006074", "1024559", "1069107"]]


@pytest.mark.asyncio
async def test_a_record_gamma_did_not_return_holds_the_row(monkeypatch):
    rows = [_row(15310213, ["polymarket:1004368", "polymarket:1006074"])]
    stats, session = await _run(monkeypatch, rows, _Service([CANCELLED]))
    assert session.writes == []
    assert stats["held_unreadable"] == 1 and stats["ruled"] == 0
    # Held by the absence test itself, not by the per-row exception net
    # catching the KeyError a skipped absence test would raise.
    assert stats["errors"] == []


@pytest.mark.asyncio
async def test_an_unreadable_batch_holds_every_row_and_is_counted(monkeypatch):
    rows = [_row(15317878, ["polymarket:1069107"])]
    stats, session = await _run(monkeypatch, rows, _Service([FINISHED], fail=True))
    assert session.writes == []
    assert stats["batches_unreadable"] == 1 and stats["held_unreadable"] == 1
    assert stats["errors"]


@pytest.mark.asyncio
async def test_an_anchored_row_is_never_read_or_written(monkeypatch):
    rows = [_row(15317878, ["polymarket:1069107"], statpal="sp-1")]
    service = _Service([FINISHED])
    stats, session = await _run(monkeypatch, rows, service)
    assert service.calls == [] and session.writes == []
    assert stats["terminal"] == "no_anchorless_polymarket_rows_live"


@pytest.mark.asyncio
async def test_non_numeric_groups_are_not_addressed(monkeypatch):
    rows = [_row(15317878, ["polymarket:0xdeadbeef"])]
    service = _Service([])
    stats, session = await _run(monkeypatch, rows, service)
    assert service.calls == [] and stats["candidates"] == 0


@pytest.mark.asyncio
async def test_the_counter_is_the_compare_and_sets_rowcount(monkeypatch):
    rows = [_row(15317878, ["polymarket:1069107"])]
    stats, _ = await _run(monkeypatch, rows, _Service([FINISHED]), write_rowcount=0)
    assert stats["ruled"] == 1 and stats["suspended"] == 0


@pytest.mark.asyncio
async def test_batches_never_exceed_gammas_limit(monkeypatch):
    from app.utils.polymarket_settlement_scan import GAMMA_MAX_IDS_PER_REQUEST

    rows = [
        _row(1000 + i, [f"polymarket:{5000 + i}"])
        for i in range(GAMMA_MAX_IDS_PER_REQUEST + 3)
    ]
    service = _Service([])
    stats, _ = await _run(monkeypatch, rows, service)
    assert [len(c) for c in service.calls] == [GAMMA_MAX_IDS_PER_REQUEST, 3]
    assert stats["held_unreadable"] == GAMMA_MAX_IDS_PER_REQUEST + 3


def test_the_beat_runs_every_five_minutes_on_heavy():
    from app.tasks import celery_app

    entry = celery_app.conf.beat_schedule["suspend-venue-ended-events"]
    assert entry["task"] == "app.tasks.suspend_venue_ended_events"
    assert entry["options"]["queue"] == "heavy"
    assert entry["schedule"].minute == set(range(0, 60, 5))
    assert "app.tasks.suspend_venue_ended_events" in celery_app.tasks


def _parse(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
