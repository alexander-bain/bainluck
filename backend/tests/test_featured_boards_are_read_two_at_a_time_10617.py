"""#10617 — the featured scoreboards are read two at a time, so one slow board
no longer adds its whole wait to every other board's.

## the ship

Readers see genuine live probability changes sooner when several sports'
boards are fetched: two independent network waits overlap before the existing
serial commits and publications.

## what the source showed

`_sync_espn_live_events` awaited `espn.get_scoreboard(key)` for every mapped
sport one after another, then processed, committed and published. Nothing in
that loop touches the database, so the waits were serial for no reason; the
writes that follow are serial on purpose and stay so.

## the rules these tests pin

* while one board is held, a second one is asked; a third is NOT asked until
  one of the two returns (RED on 841163945d: the second never entered) — and
  nothing is processed, committed or published while reads are outstanding;
* a new board is admitted at least the service's `rate_limit_delay` after the
  previous one started — concurrency goes 1 → 2, start spacing stays bounded;
* each board's clock is taken when THAT board returned, never at the join;
* every mapped sport is asked exactly once, and the full-slate read still
  comes after the live pass has committed and published (#10614);
* dark (`None`) stays ABSENT, empty (`[]`) stays present, a raise is the same
  `espn_fetch_<key>` error, and none of them costs a healthy sibling;
* cancelled mid-read, both in-flight reads are cancelled and drained BEFORE
  the shared service is closed, the queued third is never asked, and no task
  is left behind.

WHAT IS NOT CLAIMED: production speedup. One slow board still holds the join
(every live write waits for the slowest read); this removes the SUM of waits,
not the max. Driven with a fake clock, not timed against ESPN.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.asyncio

MLB, NFL, NHL, NBA, NCAAF = (
    "baseball_mlb",
    "americanfootball_nfl",
    "icehockey_nhl",
    "basketball_nba",
    "americanfootball_ncaaf",
)
FULL = [SimpleNamespace(espn_id="fbs-1"), SimpleNamespace(espn_id="fbs-2")]


def _board(key):
    return [SimpleNamespace(espn_id=f"{key}-1")]


class _Clock:
    """The admission clock. `sleep` advances it instead of the wall."""

    def __init__(self):
        self.now = 1000.0
        self.slept: list = []

    def monotonic(self):
        return self.now

    async def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds
        await asyncio.sleep(0)


class _Espn:
    """One fake per `ESPNAPIService()`; all share the run's logs."""

    def __init__(self, rig, index):
        self.rig, self.index, self.closes = rig, index, 0
        self.rate_limit_delay = rig.rate_limit_delay

    async def get_scoreboard(self, sport_key, date=None, groups=None):
        rig = self.rig
        assert self.closes == 0, f"service {self.index} asked after close"
        rig.calls.append((sport_key, date, groups))
        if groups:
            rig.log.append("full_slate:enter")
            return FULL
        rig.entered.append(sport_key)
        rig.started_at[sport_key] = rig.clock.monotonic()
        rig.in_flight += 1
        rig.max_in_flight = max(rig.max_in_flight, rig.in_flight)
        rig.log.append(f"read:{sport_key}")
        try:
            if rig.hold:
                await rig.gate(sport_key).wait()
        except asyncio.CancelledError:
            rig.log.append(f"cancelled:{sport_key}")
            raise
        finally:
            rig.in_flight -= 1
        answer = rig.answers.get(sport_key, "board")
        rig.returned_at[sport_key] = datetime.now(timezone.utc)
        rig.log.append(f"return:{sport_key}")
        if answer == "raise":
            raise RuntimeError("boom")
        if answer == "abort":
            raise _Abort()
        if answer == "dark":
            return None
        if answer == "empty":
            return []
        return _board(sport_key)

    async def close(self):
        self.closes += 1
        self.rig.log.append(f"close:{self.index}")


class _Rig:
    def __init__(self, live=(MLB, NFL, NHL), scheduled=(), *, hold=True,
                 answers=None, rate_limit_delay=0.5):
        self.live_keys, self.scheduled_keys = list(live), list(scheduled)
        self.hold, self.answers = hold, dict(answers or {})
        self.rate_limit_delay = rate_limit_delay
        self.clock = _Clock()
        self.calls: list = []
        self.log: list = []
        self.services: list = []
        self.entered: list = []
        self.started_at: dict = {}
        self.returned_at: dict = {}
        self.observed_at: dict = {}
        self.decided: list = []
        self.in_flight = 0
        self.max_in_flight = 0
        self._gates: dict = {}

    def gate(self, key):
        return self._gates.setdefault(key, asyncio.Event())

    def release(self, key):
        self.gate(key).set()

    def wire(self, monkeypatch):
        import app.services.espn_api as espn_api
        import app.tasks.espn_sync as espn_sync
        import app.utils.espn_helpers as helpers
        import app.utils.nonvenue_live_push as push

        rig = self

        class _Nested:
            async def __aenter__(self):
                return None

            async def __aexit__(self, *exc):
                return False

        async def _nothing(*a, **k):
            return None

        async def _no_rows(*a, **k):
            return SimpleNamespace(all=lambda: [])

        async def _commit():
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

        async def _decide(espn_data, fetch_keys, stats):
            rig.decided.append((dict(espn_data), set(fetch_keys)))
            return {}

        async def _live(_session, sport_key, espn_events, stats, *a, observed_at=None, **k):
            rig.observed_at[sport_key] = observed_at
            rig.log.append(f"live:{sport_key}")

        async def _scheduled(_session, sport_key, espn_events, stats):
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
        # raising=False so the RED run on the sequential base reaches the
        # assertion that names the defect instead of an AttributeError.
        monkeypatch.setattr(espn_sync, "_board_admission_clock", rig.clock.monotonic, raising=False)
        monkeypatch.setattr(espn_sync, "_board_admission_sleep", rig.clock.sleep, raising=False)
        monkeypatch.setattr(helpers, "sync_scheduled_events", _scheduled)
        for name in (
            "fetch_completed_box_scores",
            "fetch_live_box_scores",
            "backfill_missing_scores",
        ):
            monkeypatch.setattr(helpers, name, _nothing)
        monkeypatch.setattr(push, "publish_committed_nonvenue_frames", _publish)

    def start(self):
        from app.tasks.espn_sync import _sync_espn_live_events

        return asyncio.create_task(_sync_espn_live_events())

    async def until(self, predicate, what):
        async def _poll():
            while not predicate():
                await asyncio.sleep(0.001)

        try:
            await asyncio.wait_for(_poll(), timeout=2)
        except asyncio.TimeoutError:
            pytest.fail(f"never happened: {what}; log={self.log}")

    @staticmethod
    async def turns(n=50):
        for _ in range(n):
            await asyncio.sleep(0)


def _featured_reads(rig):
    return [c for c in rig.calls if c[2] is None]


def _since_first_read(rig):
    """The log from the first featured read on. The #9049 commit/publish that
    frees the recovery passes' rows runs BEFORE the reads and is not theirs."""
    first = min(i for i, e in enumerate(rig.log) if e.startswith("read:"))
    return rig.log[first:]


async def test_a_second_board_is_asked_while_the_first_is_held_and_a_third_waits(monkeypatch):
    """THE SHIP. RED on 841163945d: the second board never entered."""
    rig = _Rig()
    rig.wire(monkeypatch)
    task = rig.start()
    try:
        await rig.until(lambda: len(rig.entered) >= 2, "a second board asked while the first is held")
        await rig.turns()
        first, second = rig.entered
        assert len(rig.entered) == 2, f"a third board entered with two in flight: {rig.entered}"
        assert rig.max_in_flight == 2
        assert not any(e.startswith(("live:", "commit", "publish")) for e in _since_first_read(rig)), rig.log

        rig.release(second)
        await rig.until(lambda: len(rig.entered) == 3, "the third board once a slot freed")
        assert rig.log.index(f"return:{second}") < rig.log.index(f"read:{rig.entered[2]}")
        assert rig.max_in_flight == 2
        assert not any(e.startswith("live:") for e in rig.log), rig.log

        for key in rig.entered:
            rig.release(key)
        stats = await asyncio.wait_for(task, timeout=2)
    finally:
        for key in (MLB, NFL, NHL):
            rig.release(key)
    assert stats["errors"] == [], stats["errors"]
    assert rig.max_in_flight == 2
    # The join stands: every read returned before the first live write.
    first_live = min(i for i, e in enumerate(rig.log) if e.startswith("live:"))
    assert all(rig.log.index(f"return:{k}") < first_live for k in (MLB, NFL, NHL)), rig.log


@pytest.mark.parametrize("delay", [0.5, 0.75])
async def test_each_new_board_starts_at_least_rate_limit_delay_after_the_last(monkeypatch, delay):
    """Two may be in flight, but they never start in the same instant: the
    service's own `rate_limit_delay` (0.5 s by default) spaces admissions."""
    rig = _Rig(live=(MLB, NFL, NHL, NBA), hold=False, rate_limit_delay=delay)
    rig.wire(monkeypatch)

    await asyncio.wait_for(rig.start(), timeout=2)

    starts = sorted(rig.started_at.values())
    assert len(starts) == 4
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    assert all(g >= delay for g in gaps), gaps


async def test_each_board_keeps_the_clock_it_was_read_at_not_the_join(monkeypatch):
    """#4571 survives the overlap: a board that returned early is stamped when
    it returned, not when the slowest sibling finally did."""
    rig = _Rig(live=(MLB, NFL))
    rig.wire(monkeypatch)
    task = rig.start()
    try:
        await rig.until(lambda: len(rig.entered) == 2, "both boards in flight")
        early, late = rig.entered[1], rig.entered[0]
        rig.release(early)
        await rig.until(lambda: early in rig.returned_at, "the early board returned")
        await asyncio.sleep(0.02)
        rig.release(late)
        await asyncio.wait_for(task, timeout=2)
    finally:
        rig.release(MLB)
        rig.release(NFL)
    assert rig.returned_at[early] <= rig.observed_at[early] < rig.returned_at[late]
    assert rig.returned_at[late] <= rig.observed_at[late]


async def test_every_board_is_asked_exactly_once_and_the_full_slate_still_waits_for_the_live_publish(
    monkeypatch,
):
    rig = _Rig(live=(MLB, NFL, NHL), scheduled=(NCAAF,), hold=False)
    rig.wire(monkeypatch)

    stats = await asyncio.wait_for(rig.start(), timeout=2)

    assert sorted(_featured_reads(rig)) == sorted(
        (k, None, None) for k in (MLB, NFL, NHL, NCAAF)
    )
    assert [c for c in rig.calls if c[2] is not None] == [(NCAAF, None, "80")]
    assert len(rig.calls) == 5
    enter = rig.log.index("full_slate:enter")
    for key in (MLB, NFL, NHL):
        live = rig.log.index(f"live:{key}")
        assert rig.log[live + 1 : live + 3] == ["commit", "publish"], rig.log
        assert live < enter
    assert rig.log.index(f"scheduled:{NCAAF}") > enter
    assert stats["errors"] == []
    assert [s.closes for s in rig.services] == [1] * len(rig.services)


async def test_dark_empty_and_raising_boards_keep_their_meaning_and_spare_the_healthy_one(monkeypatch):
    rig = _Rig(
        live=(MLB, NFL, NHL, NBA),
        hold=False,
        answers={MLB: "dark", NFL: "empty", NHL: "raise"},
    )
    rig.wire(monkeypatch)

    stats = await asyncio.wait_for(rig.start(), timeout=2)

    [(espn_data, fetch_keys)] = rig.decided
    assert espn_data == {NFL: [], NBA: _board(NBA)}
    assert fetch_keys == {MLB, NFL, NHL, NBA}
    assert stats["authority_dark_sports"] == 1
    assert stats["errors"] == [f"espn_fetch_{NHL}: boom"]
    assert [e for e in rig.log if e.startswith("live:")] == [f"live:{NBA}"]
    assert rig.returned_at[NBA] <= rig.observed_at[NBA]
    assert len(_featured_reads(rig)) == 4


async def test_cancelled_mid_read_drains_both_reads_before_close_and_never_asks_the_third(monkeypatch):
    rig = _Rig()
    rig.wire(monkeypatch)
    before = {t for t in asyncio.all_tasks() if not t.done()}
    task = rig.start()
    try:
        await rig.until(lambda: len(rig.entered) == 2, "two boards in flight")
        await rig.turns()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=2)
    finally:
        for key in (MLB, NFL, NHL):
            rig.release(key)
    await rig.turns()

    first, second = rig.entered
    assert len(rig.entered) == 2, f"a third board was asked after cancellation: {rig.entered}"
    featured_close = f"close:{len(rig.services) - 1}"
    assert rig.log.index(f"cancelled:{first}") < rig.log.index(featured_close), rig.log
    assert rig.log.index(f"cancelled:{second}") < rig.log.index(featured_close), rig.log
    assert not any(
        e.startswith(("return:", "live:", "commit", "publish")) for e in _since_first_read(rig)
    ), rig.log
    assert [s.closes for s in rig.services] == [1] * len(rig.services)
    leaked = {t for t in asyncio.all_tasks() if not t.done()} - before - {asyncio.current_task()}
    assert not leaked, leaked


class _Abort(BaseException):
    """Not an `Exception`: the read's own handler does not catch it."""


async def test_a_read_dying_on_a_non_exception_drains_its_sibling_before_close(monkeypatch):
    """`gather` alone would re-raise at once and leave the held sibling reading
    on a service the caller's `finally` is about to close."""
    rig = _Rig(live=(MLB, NFL))
    rig.wire(monkeypatch)
    task = rig.start()
    try:
        await rig.until(lambda: len(rig.entered) == 2, "both boards in flight")
        dying, held = rig.entered
        rig.answers[dying] = "abort"
        rig.release(dying)
        with pytest.raises(_Abort):
            await asyncio.wait_for(task, timeout=2)
    finally:
        rig.release(MLB)
        rig.release(NFL)
    await rig.turns()

    featured_close = f"close:{len(rig.services) - 1}"
    assert rig.log.index(f"cancelled:{held}") < rig.log.index(featured_close), rig.log
    assert f"return:{held}" not in rig.log, rig.log
    assert [s.closes for s in rig.services] == [1] * len(rig.services)
