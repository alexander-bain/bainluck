"""#10090 — the ESPN pass's straggler arms let go of a row before their next ESPN read.

## the ship

A live game's price stops freezing behind the ESPN pass's straggler arms after
ESPN's board rolls at Eastern midnight.

## what production showed (2026-10-29 04:38:57–04:39:03Z, lock watch 4)

One backend on a realtime worker, started 04:38:56.88, was `idle in
transaction` for 3.8 and then 6.2 s, its last statement 0.2-0.4 s old each
time and always `UPDATE events SET win_probability_sources=$1::JSONB WHERE
events.id = $2`; the socket's stamps waited on it. That is the pass's FIRST
transaction (it begins 0.17 s after connect, at `_find_sport_keys_to_sync`).
In it, three straggler arms each asked ESPN, wrote, asked ESPN again — and the
only commit was after all three. The shallow arm's rows are `live` games whose
board day has rolled (a late game still going after 04:00Z), and its door
writes their score and clock.

## the rules these tests pin

* `_ask_boards_by_espn_id` asks for every board before it writes any row; the
  groups, their order, the writes, the stamps and each board's own observation
  clock (#4571) are unchanged;
* `_recover_unstarted_authority_fixtures` asks every anchor before it writes;
* the task commits (and publishes) after the shallow arm and after the deep
  arm, as it already did after the third.

Real-Postgres arms (the lock itself):
`tests/integration/test_straggler_arms_release_rows_pg_10090.py`.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.asyncio


# ── _ask_boards_by_espn_id: every board before any write ────────────────────


class _Espn:
    def __init__(self, log, *, broken=(), dark=()):
        self._log = log
        self._broken = set(broken)
        self._dark = set(dark)
        self.read_at = {}

    async def get_scoreboard(self, sport_key, date=None):
        # A real read takes time; it also separates the boards' clocks.
        await asyncio.sleep(0.005)
        self._log.append(("fetch", date))
        self.read_at[date] = datetime.now(timezone.utc)
        if date in self._broken:
            raise RuntimeError("ESPN timed out")
        if date in self._dark:
            return None
        return [SimpleNamespace(espn_id=f"{date}-{n}") for n in (1, 2)]


def _event(event_id, espn_id):
    return SimpleNamespace(
        id=event_id, espn_id=espn_id, status="live",
        home_team_name="H", away_team_name="A",
    )


def _groups():
    return [
        (("basketball_nba", "20261028"), [_event(1, "20261028-1"), _event(2, "20261028-2")]),
        (("icehockey_nhl", "20261027"), [_event(3, "20261027-1")]),
        (("baseball_mlb", "20261026"), [_event(4, "20261026-1")]),
        (("soccer_usa_mls", "20261025"), [_event(5, "20261025-1")]),
    ]


async def _run_ask(log, *, broken=(), dark=()):
    from app.tasks.espn_sync import _ask_boards_by_espn_id

    espn = _Espn(log, broken=broken, dark=dark)
    observed = {}

    async def _door(session, event, matched, claimed, stats, *, allow_unstarted, observed_at):
        log.append(("write", event.id))
        observed[event.id] = observed_at
        event.status = "completed"

    async def _on_asked(events):
        log.append(("stamp", tuple(e.id for e in events)))

    stats = {
        "errors": [], "authority_dark_sports": 0,
        "straggler_boards_fetched": 0, "straggler_settled": 0,
    }
    await _ask_boards_by_espn_id(
        object(), espn, _groups(), stats, _door,
        stat_prefix="straggler", log_tag="%s %s %s %s %s %s %s",
        on_asked=_on_asked,
    )
    return espn, observed, stats


async def test_no_row_is_written_while_another_board_is_being_asked_for():
    """THE SHIP (call order). RED before #10090: fetch, write 1, write 2, stamp,
    fetch … — the NBA game's live row locked through the later ESPN reads."""
    log: list = []
    await _run_ask(log)

    kinds = [kind for kind, _ in log]
    assert kinds == ["fetch"] * 4 + ["write", "write", "stamp", "write", "stamp",
                                     "write", "stamp", "write", "stamp"], log


async def test_same_writes_same_order_same_stamps():
    """KILL CONTROL. A version that fetched and dropped the writes, or reordered
    them, passes the order test vacuously."""
    log: list = []
    _espn, _observed, stats = await _run_ask(log)

    after_fetches = [entry for entry in log if entry[0] != "fetch"]
    assert after_fetches == [
        ("write", 1), ("write", 2), ("stamp", (1, 2)),
        ("write", 3), ("stamp", (3,)),
        ("write", 4), ("stamp", (4,)),
        ("write", 5), ("stamp", (5,)),
    ]
    assert stats["straggler_boards_fetched"] == 4
    assert stats["straggler_settled"] == 5


async def test_each_board_keeps_the_clock_it_was_read_at():
    """#4571 survives the split: a score is stamped with ITS board's read time,
    not the time the write finally ran (which is now after every read)."""
    log: list = []
    espn, observed, _stats = await _run_ask(log)

    read = espn.read_at
    # Taken as its own board returned: before the NEXT board was even read.
    assert read["20261028"] <= observed[1] == observed[2] < read["20261027"]
    assert read["20261027"] <= observed[3] < read["20261026"]
    assert read["20261026"] <= observed[4] < read["20261025"]
    assert read["20261025"] <= observed[5]


async def test_a_broken_or_dark_board_still_costs_only_its_own_group():
    """gotcha #42 and the dark-path stamp (the livelock guard) are unchanged:
    a broken board and a dark board each settle nothing, are each stamped, and
    are recorded in the same order and words as before."""
    log: list = []
    _espn, _observed, stats = await _run_ask(log, broken={"20261027"}, dark={"20261026"})

    after_fetches = [entry for entry in log if entry[0] != "fetch"]
    assert after_fetches == [
        ("write", 1), ("write", 2), ("stamp", (1, 2)),
        ("stamp", (3,)),
        ("stamp", (4,)),
        ("write", 5), ("stamp", (5,)),
    ]
    assert stats["errors"] == ["straggler_fetch_icehockey_nhl_20261027: ESPN timed out"]
    assert stats["authority_dark_sports"] == 1
    assert stats["straggler_boards_fetched"] == 2


# ── _recover_unstarted_authority_fixtures: every anchor before any write ─────


async def test_the_unstarted_arm_asks_every_anchor_before_it_writes_a_row():
    """RED before #10090: ask 1, write 1, ask 2, … — row 1 locked across the
    later anchors. Same writes after the split: two recoveries, one stamp."""
    from app.tasks.espn_sync import _recover_unstarted_authority_fixtures
    from tests.test_the_misdated_fixture_that_never_kicked_off_6280 import (
        AUBURN_AT_GEORGIA,
        DC_AT_CINCINNATI,
        MSU_AT_MICHIGAN,
        NOW,
        _answer,
        _FakeESPN,
        _FakeSession,
        _row,
    )

    log: list = []

    class _Session(_FakeSession):
        async def execute(self, stmt, *args, **kwargs):
            if not str(stmt).lstrip().upper().startswith("SELECT"):
                log.append("write")
            return await super().execute(stmt, *args, **kwargs)

    class _Anchor(_FakeESPN):
        async def get_event(self, sport_key, espn_id):
            log.append("ask")
            return await super().get_event(sport_key, espn_id)

    answers = {**_answer(MSU_AT_MICHIGAN), **_answer(AUBURN_AT_GEORGIA)}
    session = _Session([_row(MSU_AT_MICHIGAN), _row(AUBURN_AT_GEORGIA), _row(DC_AT_CINCINNATI)])
    stats = {"errors": []}
    await _recover_unstarted_authority_fixtures(session, _Anchor(answers), NOW, stats)

    assert log.index("write") == 3, log
    assert log[:3] == ["ask"] * 3
    assert len(session.recoveries()) == 2
    assert len(session.stamps()) == 1  # DC: no answer, queue advanced
    assert stats["unstarted_recovery_recovered"] == 2
    assert stats["unstarted_recovery_no_answer"] == 1


async def test_a_failed_anchor_read_is_still_recorded_and_writes_nothing():
    from app.tasks.espn_sync import _recover_unstarted_authority_fixtures
    from tests.test_the_misdated_fixture_that_never_kicked_off_6280 import (
        MSU_AT_MICHIGAN,
        NOW,
        _FakeESPN,
        _FakeSession,
        _row,
    )

    session = _FakeSession([_row(MSU_AT_MICHIGAN)])
    stats = {"errors": []}
    await _recover_unstarted_authority_fixtures(
        session, _FakeESPN({}, raises=True), NOW, stats
    )

    assert session.updates == []
    assert stats["errors"] == [f"unstarted_recovery_{MSU_AT_MICHIGAN[0]}: ESPN blew up"]


# ── the task: a commit after each straggler arm ─────────────────────────────


async def test_the_pass_commits_after_every_straggler_arm(monkeypatch):
    """THE SHIP (task shape). RED before #10090: shallow, deep and unstarted
    arms ran in one transaction — the shallow arm's live rows were held across
    the deep arm's and the unstarted arm's ESPN reads."""
    import app.tasks.espn_sync as espn_sync
    from tests.test_espn_pass_releases_rows_9049 import (
        MLB,
        _released_between,
        _wire,
    )

    log: list = []
    _wire(monkeypatch, log)

    def _arm(name):
        async def _run(*a, **k):
            log.append(name)

        return _run

    monkeypatch.setattr(espn_sync, "_settle_authority_stragglers", _arm("shallow"))
    monkeypatch.setattr(espn_sync, "_settle_deep_authority_stragglers", _arm("deep"))
    stats = await espn_sync._sync_espn_live_events()

    assert stats["errors"] == [], stats["errors"]
    for before, after in (
        ("shallow", "deep"),
        ("deep", "stragglers"),  # `_wire`'s name for the unstarted arm
        ("stragglers", f"live:{MLB}"),
    ):
        assert _released_between(log, before, after), (before, after, log)
    commits = [i for i, entry in enumerate(log) if entry == "commit"]
    assert all(log[i + 1] == "publish" for i in commits), log


async def test_a_failed_shallow_arm_still_releases_before_the_deep_arm(monkeypatch):
    """The release sits OUTSIDE the arm's savepoint (#8796): an arm that raised
    has been rolled back to it, and the next arm starts on a released set."""
    import app.tasks.espn_sync as espn_sync
    from tests.test_espn_pass_releases_rows_9049 import _released_between, _wire

    log: list = []
    _wire(monkeypatch, log)

    async def _shallow(*a, **k):
        log.append("shallow")
        raise RuntimeError("deadlock detected")

    async def _deep(*a, **k):
        log.append("deep")

    monkeypatch.setattr(espn_sync, "_settle_authority_stragglers", _shallow)
    monkeypatch.setattr(espn_sync, "_settle_deep_authority_stragglers", _deep)
    stats = await espn_sync._sync_espn_live_events()

    assert stats["errors"] == ["authority_stragglers: deadlock detected"]
    assert _released_between(log, "shallow", "deep"), log
