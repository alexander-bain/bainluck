"""#10614 — a live probability the ESPN pass has already read is published
before the pass waits on the pre-game full-slate board.

## the ship

A genuine live ESPN/model update already read by the current pass reaches the
event page without waiting for an unrelated pre-game FBS board.

## what the source showed

`_sync_espn_live_events` read every featured board, then awaited
`_fetch_full_slate_boards` (NCAAF `groups=80`, #8682) BEFORE `_process_live_sport`
and its commit/publish (`_release_rows`, #9049). The full slate is read only by
the pre-game pass (`scheduled_board_for`, the #9143 dated prefetch), so a slow
FBS board held every live sport's already-read scores and probabilities.

## the rules these tests pin

* the live sport is processed, committed and its frames published while the
  full-slate request is still pending — driven through the real task with the
  request held on an `asyncio.Event` (RED on 285ce4d9da: nothing live had run);
* the pre-game pass still gets the FULL board, the live pass the FEATURED one,
  and the live pass the clock its board was read at;
* the provider sees exactly the calls it saw before — one featured read per
  mapped sport plus one full-slate read for NCAAF;
* a dark or raising full slate still falls back to the featured board;
* the full slate is asked with no savepoint open and no uncommitted write, on a
  service that is open, and every service is closed exactly once;
* no live games / no mapped sports still return before any board is asked.

WHAT IS NOT CLAIMED: the task does the same work in the same total time; this
moves one wait behind the live publication, it does not shorten the pass.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.asyncio

MLB, NCAAF = "baseball_mlb", "americanfootball_ncaaf"
FEATURED = {MLB: [SimpleNamespace(espn_id="mlb-1")], NCAAF: [SimpleNamespace(espn_id="fbs-1")]}
FULL = [SimpleNamespace(espn_id="fbs-1"), SimpleNamespace(espn_id="fbs-2")]


class _Espn:
    """One fake per `ESPNAPIService()`; all share the run's call log."""

    def __init__(self, rig, index):
        self.rig, self.index, self.closes = rig, index, 0

    async def get_scoreboard(self, sport_key, date=None, groups=None):
        assert self.closes == 0, f"service {self.index} asked after close"
        self.rig.calls.append((sport_key, date, groups))
        if groups:
            assert self.rig.depth == 0, "full slate asked inside a savepoint"
            assert not self.rig.dirty, "full slate asked with a write uncommitted"
            self.rig.log.append("full_slate:enter")
            self.rig.entered.set()
            await self.rig.gate.wait()
            self.rig.log.append("full_slate:return")
            if self.rig.full == "raise":
                raise RuntimeError("boom")
            return self.rig.full
        self.rig.read_at[sport_key] = datetime.now(timezone.utc)
        return FEATURED[sport_key]

    async def close(self):
        self.closes += 1


class _Rig:
    def __init__(self, full=FULL, live=(MLB,), scheduled=(NCAAF,)):
        self.full, self.live_keys, self.scheduled_keys = full, list(live), list(scheduled)
        self.calls: list = []
        self.log: list = []
        self.services: list = []
        self.read_at: dict = {}
        self.handed: dict = {"live": [], "scheduled": []}
        self.observed_at: dict = {}
        self.depth = 0
        self.dirty = False
        self.entered = asyncio.Event()
        self.gate = asyncio.Event()

    def wire(self, monkeypatch):
        import app.services.espn_api as espn_api
        import app.tasks.espn_sync as espn_sync
        import app.utils.espn_helpers as helpers
        import app.utils.nonvenue_live_push as push

        rig = self

        class _Nested:
            async def __aenter__(self):
                rig.depth += 1

            async def __aexit__(self, *exc):
                rig.depth -= 1
                return False

        async def _nothing(*a, **k):
            return None

        async def _no_rows(*a, **k):
            # #9143: the pre-game prefetch reads rows; none are scheduled here.
            return SimpleNamespace(all=lambda: [])

        async def _commit():
            assert rig.depth == 0, "commit inside a savepoint"
            rig.dirty = False
            rig.log.append("commit")

        session = SimpleNamespace(
            begin_nested=_Nested, flush=_nothing, execute=_no_rows,
            commit=_commit, info={},
        )

        class _Session:
            async def __aenter__(self):
                return session

            async def __aexit__(self, *exc):
                return False

        def _service():
            svc = _Espn(rig, len(rig.services))
            rig.services.append(svc)
            return svc

        async def _keys(_session):
            return list(rig.live_keys), list(rig.scheduled_keys)

        async def _decide(*a, **k):
            return {}

        async def _live(_session, sport_key, espn_events, stats, *a, observed_at=None, **k):
            rig.dirty = True
            rig.handed["live"].append((sport_key, espn_events))
            rig.observed_at[sport_key] = (observed_at, datetime.now(timezone.utc))
            rig.log.append(f"live:{sport_key}")

        async def _scheduled(_session, sport_key, espn_events, stats):
            rig.dirty = True
            rig.handed["scheduled"].append((sport_key, espn_events))
            rig.log.append(f"scheduled:{sport_key}")

        async def _publish(_session):
            rig.log.append("publish")

        monkeypatch.setattr(espn_sync, "get_task_session", lambda **k: _Session())
        monkeypatch.setattr(espn_api, "ESPNAPIService", _service)
        monkeypatch.setattr(espn_sync, "_find_sport_keys_to_sync", _keys)
        for name in (
            "_settle_authority_stragglers",
            "_settle_deep_authority_stragglers",
            "_recover_unstarted_authority_fixtures",
            "_act_on_failovers",
        ):
            monkeypatch.setattr(espn_sync, name, _nothing)
        monkeypatch.setattr(espn_sync, "_decide_failovers", _decide)
        monkeypatch.setattr(espn_sync, "_process_live_sport", _live)
        monkeypatch.setattr(helpers, "sync_scheduled_events", _scheduled)
        for name in (
            "fetch_completed_box_scores",
            "fetch_live_box_scores",
            "backfill_missing_scores",
        ):
            monkeypatch.setattr(helpers, name, _nothing)
        monkeypatch.setattr(push, "publish_committed_nonvenue_frames", _publish)

    async def run_held(self):
        """Run the task with the full-slate request held until the live pass
        has been looked at. Returns (log at the moment of the hold, stats)."""
        from app.tasks.espn_sync import _sync_espn_live_events

        task = asyncio.create_task(_sync_espn_live_events())
        try:
            await asyncio.wait_for(self.entered.wait(), timeout=5)
            held = list(self.log)
        finally:
            self.gate.set()
        return held, await asyncio.wait_for(task, timeout=5)


async def test_the_live_pass_publishes_while_the_full_slate_is_still_pending(monkeypatch):
    """THE SHIP. RED on 285ce4d9da: the hold came before `live:baseball_mlb`."""
    rig = _Rig()
    rig.wire(monkeypatch)

    held, stats = await rig.run_held()

    assert held[-4:] == [f"live:{MLB}", "commit", "publish", "full_slate:enter"], held
    assert not any(e.startswith("scheduled:") for e in held), held
    assert stats["errors"] == [], stats["errors"]


async def test_the_boards_each_pass_is_handed_are_unchanged(monkeypatch):
    """The pre-game pass still gets the full FBS week (#8682); the live pass
    keeps the featured board and the clock that board was read at (#4571)."""
    rig = _Rig()
    rig.wire(monkeypatch)

    _held, stats = await rig.run_held()

    assert rig.handed["scheduled"] == [(NCAAF, FULL)]
    assert rig.handed["live"] == [(MLB, FEATURED[MLB])]
    observed_at, processed_at = rig.observed_at[MLB]
    assert rig.read_at[MLB] <= observed_at <= processed_at
    assert stats["full_slate_events"] == {NCAAF: 2}
    assert rig.log.index("full_slate:return") < rig.log.index(f"scheduled:{NCAAF}")


async def test_the_provider_is_asked_exactly_what_it_was_asked_before(monkeypatch):
    """No new request and no lost one: a featured read per mapped sport, every
    one before the full slate, and one full-slate read for NCAAF."""
    rig = _Rig()
    rig.wire(monkeypatch)

    await rig.run_held()

    featured = [c for c in rig.calls if c[2] is None]
    full = [c for c in rig.calls if c[2] is not None]
    assert sorted(featured) == sorted([(MLB, None, None), (NCAAF, None, None)])
    assert full == [(NCAAF, None, "80")]
    assert len(rig.calls) == 3
    assert rig.calls[-1] == (NCAAF, None, "80")


async def test_every_service_is_closed_exactly_once(monkeypatch):
    rig = _Rig()
    rig.wire(monkeypatch)

    await rig.run_held()

    assert rig.services, "no service was opened"
    assert [s.closes for s in rig.services] == [1] * len(rig.services)


@pytest.mark.parametrize("full,counter", [(None, "full_slate_dark"), ("raise", None)])
async def test_a_dark_or_raising_full_slate_falls_back_and_live_still_publishes(
    monkeypatch, full, counter
):
    rig = _Rig(full=full)
    rig.wire(monkeypatch)

    held, stats = await rig.run_held()

    assert held[-3:] == ["commit", "publish", "full_slate:enter"], held
    assert f"live:{MLB}" in held
    assert rig.handed["scheduled"] == [(NCAAF, FEATURED[NCAAF])]
    if counter:
        assert stats[counter] == 1
        assert stats["errors"] == []
    else:
        assert stats["errors"] == [f"espn_full_slate_{NCAAF}: boom"]


@pytest.mark.parametrize(
    "live,scheduled,status",
    [((), (NCAAF,), "no_live_games"), (("cricket_test",), ("cricket_test",), "no_espn_mapped_sports")],
)
async def test_the_early_returns_ask_for_no_board(monkeypatch, live, scheduled, status):
    from app.tasks.espn_sync import _sync_espn_live_events

    rig = _Rig(live=live, scheduled=scheduled)
    rig.wire(monkeypatch)

    stats = await asyncio.wait_for(_sync_espn_live_events(), timeout=5)

    assert stats["status"] == status
    assert rig.calls == []
    assert [s.closes for s in rig.services] == [1] * len(rig.services)
