"""#10090 — a game flush fenced by another call's held stamp wakes when that
stamp releases, and a fully fenced flush does not spend the socket budget.

Real-loop 250 ms cases on `paired(monkeypatch)` from
`tests/test_pm_same_flush_fresh_admission_10090.py` (no virtual scheduler).
Before this change (0094d11bb6) the peer waited ~210 ms, the released event's
newer quote ~193 ms after release and a fenced withdrawal ~209 ms, all for the
next periodic timer. One case is slower by design: when the event releases
inside the peer's budget window, its quote waits for that window's floor
(~45 ms later than the old periodic phase) — bounded below, never hidden.

Measures:
1. Healthy peer (Event 2) arriving after a 100%-fenced flush of Event 1,
   recording BOTH Peer Event 2's publication and Fenced Event 1's final
   publication when Event 1 releases after the second periodic probe (~0.565s)
   and when Event 1 releases inside Peer Event 2's 250 ms socket budget window
   (~0.340s).
2. Fenced wide-book withdrawal recovery after stamp release on the real loop.
3. Failed stamp backoff (`_failed_hold_until`) no-spin and recovery via
   `refresh_pending` on the real loop.
4. Cancellation / shutdown cleanup preserving pending debt and buffered quotes.
"""

import asyncio
import gc
import time

import pytest

from app.tasks import live_blend_refresh as blend
from app.tasks import polymarket_ws as pm
from tests.test_pm_same_flush_fresh_admission_10090 import paired
from tests.test_single_event_commit_10090 import settle_until

pytestmark = pytest.mark.asyncio

#: A wake-driven publication or withdrawal lands within this of its trigger.
#: Measured ~6-10 ms here; before this change the same paths waited 193-213 ms
#: for the periodic timer. The gap is runner headroom (a loaded runner measured
#: 54 ms once), never enough for a timer-paced path to pass.
WAKE_BOUND_S = 0.120
#: How far past the 250 ms floor a floor-paced publication may land.
FLOOR_MARGIN_S = 0.100


@pytest.fixture(autouse=True)
def full_collections():
    """Pay the process's owed full collection BEFORE a case starts its clock,
    and name any full collection that still lands inside the case.

    These bounds time the real loop. A gen-2 collection is a stop-the-world
    pause, and when one falls due is decided by everything the process
    allocated before this file, not by this file. On PR #11154 (CI shard 1, no
    #10090 file changed) two sibling #10090 files ran right before this one and
    the first case measured 158 and 163 ms on a path measured at 6-10 ms, its
    whole run ~150 ms longer than on master's split, where it passed. One
    collection here resets the generation counts, so the next full collection
    needs far more new survivors than one of these cases allocates. Collection
    stays ENABLED: a case still pays whatever its own work owes, and a bound
    that misses with no full collection in the case is the product, not this.
    """
    pass  # DIAG: no pre-case collection
    pauses_ms: list[float] = []
    started = [0.0]

    def observe(phase, info):
        if info["generation"] != 2:
            return
        if phase == "start":
            started[0] = time.perf_counter()
        else:
            pauses_ms.append(round((time.perf_counter() - started[0]) * 1000, 1))

    gc.callbacks.append(observe)
    try:
        yield pauses_ms
    finally:
        gc.callbacks.remove(observe)


def _buffer_game_cohort(
    p,
    cohort: dict[int, float],
    *,
    seq_base: int,
    t0: float,
) -> float:
    """Buffer a game price cohort and wake `catalog_boundary` as `handle_price` does."""
    now = time.monotonic()
    boundary = p.ns["catalog_boundary"]
    for idx, (oid, val) in enumerate(cohort.items(), start=seq_base):
        p.ns["price_buffer"][oid] = val
        p.ns["input_marks"][oid] = blend.InputMark(
            seq=idx,
            event_id=p.ns["event_id_by_outcome"][oid],
            outcome_id=oid,
            probability=val,
            kind="price",
            recv_wall=1000.0 + idx,
            recv_mono=now,
            venue_ts_ms=None,
            event_ordinal=idx,
        )
    wake_outcomes = getattr(boundary, "wake_for_outcomes", None)
    if wake_outcomes is not None:
        wake_outcomes(
            cohort.keys(),
            p.ns["open_outcome_ids"],
            p.ns["event_id_by_outcome"],
            p.ns["non_blend_outcome_ids"],
        )
    else:
        boundary.flush_wake.set()
    return round(now - t0, 4)


async def run_healthy_peer_after_fenced_flush_case(
    monkeypatch,
    *,
    release_ev1_at_s: float = 0.565,
    peer_tick_s: float | None = None,
    peer_until_s: float = 0.0,
) -> dict:
    """Run the real-loop 250 ms cadence comparison on `paired(monkeypatch)`:
    - Flush 1 (~0.005s): writes Event 1 ({1: 0.6, 2: 0.4}) and parks Event 1's
      first stamp at its SQL Update (`blocked=(1,)`).
    - t ~ 0.100s: newer quote for Event 1 ({1: 0.64, 2: 0.36}) buffers and sets
      `flush_wake`.
    - Flush 2 (~0.255s): runs while Event 1's first stamp is still held, fences
      Event 1 (`stamp_fenced == 2`), performs zero writes/stamps, and clears
      `flush_wake`.
    - t ~ 0.295s: healthy Peer Event 2 ({900: 0.7, 901: 0.3}) arrives and sets
      `flush_wake`.
    - t ~ `release_ev1_at_s`: Event 1's first stamp releases (`x.release.set()`).
    Returns exact relative timestamps (seconds since `t0`) for all flushes,
    writes, and publications of both Peer Event 2 and Fenced Event 1.
    """
    p, x = paired(monkeypatch, blocked=(1,))
    x.r.min_refresh_interval_s = 0.25
    boundary = p.ns["catalog_boundary"]

    # Hold back Event 2 ({900: 0.7, 901: 0.3}) until after Flush 2 fences Event 1.
    ev2_initial = {oid: p.ns["price_buffer"].pop(oid) for oid in (900, 901)}
    for oid in (900, 901):
        p.ns["input_marks"].pop(oid, None)

    t0 = time.monotonic()
    flush_starts: list[float] = []
    write_events: list[tuple[float, list[int], dict[int, float]]] = []
    pub_events: list[tuple[float, int]] = []
    latest_written_prob: dict[int, float] = {1: 0.60, 2: 0.70}
    peer_last = [0.70]
    ticker = None

    monkeypatch.setattr(
        "app.utils.live_blend.compute_source_home_probability",
        lambda group, home, away: type(
            "Reading",
            (),
            {
                "home_probability": latest_written_prob.get(
                    group[0].market.event_id, 0.9
                ),
                "away_probability": None,
                "draw_probability": None,
                "eligibility": None,
            },
        )(),
    )

    orig_write = p.ns["write_chunk"]

    async def timed_write(chunk, **kwargs):
        snap = dict(chunk)
        res = await orig_write(chunk, **kwargs)
        if res:
            if 1 in snap:
                latest_written_prob[1] = snap[1]
            if 900 in snap:
                latest_written_prob[2] = snap[900]
            write_events.append((round(time.monotonic() - t0, 4), sorted(snap), snap))
        return res

    p.ns["write_chunk"] = timed_write

    orig_publish = x.r._publish

    async def timed_publish(frames):
        await orig_publish(frames)
        now_rel = round(time.monotonic() - t0, 4)
        for frame in frames:
            pub_events.append((now_rel, int(frame["event_id"])))

    x.r._publish = timed_publish

    async def tracked_flush(started: float):
        flush_starts.append(round(started - t0, 4))
        return await p.ns["flush_prices"](flush_started=started)

    stop = asyncio.Event()
    boundary.flush_wake.set()
    cadence_task = asyncio.create_task(
        blend.run_flush_cadence(
            tracked_flush,
            0.25,
            stop=stop,
            failed_retry_interval_s=2.0,
            wake=boundary.flush_wake,
            work_count=lambda: boundary.flush_work,
            wake_coalesce_s=pm.PM_WAKE_COALESCE_SECONDS,
        )
    )
    try:
        # 1. Wait for Flush 1 to start Event 1's first stamp (parked on `x.release`).
        await settle_until(lambda: len(x.sessions) >= 1)

        # 2. At t ~ 0.100s, buffer newer quote B ({1: 0.64, 2: 0.36}) for Event 1.
        await asyncio.sleep(max(0.0, 0.100 - (time.monotonic() - t0)))
        t_ev1_quote2_buffered = _buffer_game_cohort(
            p, {1: 0.64, 2: 0.36}, seq_base=10, t0=t0
        )

        # 3. Wait for Flush 2 (~0.255s) to fence Event 1 while Stamp 1 is still held.
        await settle_until(
            lambda: len(flush_starts) >= 2
            and p.ns["stats"]["stamp_fenced"] >= 2
            and boundary.active == 0
        )
        flush_work_after_fenced_flush2 = boundary.flush_work

        # 4. At ~40ms after Flush 2 (~0.295s), healthy Peer Event 2 arrives.
        await asyncio.sleep(0.040)
        t_ev2_arrived = _buffer_game_cohort(p, ev2_initial, seq_base=20, t0=t0)
        if peer_tick_s is not None:
            # Sustained peer traffic: Event 2 moves every `peer_tick_s` through
            # Event 1's hold and release, so every peer flush is real work.
            async def tick_peer():
                k = 0
                while time.monotonic() - t0 < peer_until_s:
                    await asyncio.sleep(peer_tick_s)
                    k += 1
                    val = round(0.70 + 0.001 * k, 4)
                    _buffer_game_cohort(
                        p, {900: val, 901: round(1 - val, 4)},
                        seq_base=100 + 2 * k, t0=t0,
                    )
                    peer_last[0] = val

            ticker = asyncio.create_task(tick_peer())

        # 5. Release Event 1's first stamp at `release_ev1_at_s`.
        wait_to_release = release_ev1_at_s - (time.monotonic() - t0)
        if wait_to_release > 0:
            await asyncio.sleep(wait_to_release)
        ev2_published_before_ev1_release = 2 in x.published
        t_ev1_released = round(time.monotonic() - t0, 4)
        x.release.set()

        # 6. Wait for Peer Event 2 (1 publication) and Event 1 (2 publications:
        # initial 0.60 and newer 0.64) to finish publishing.
        async with asyncio.timeout(1.2):
            while x.published.count(2) < 1 or x.published.count(1) < 2:
                await asyncio.sleep(0.005)
        t_ev1_done = round(time.monotonic() - t0, 4)
        if ticker is not None:
            await ticker
            # Latest wins: the peer's last value is the one written.
            async with asyncio.timeout(1.0):
                while latest_written_prob[2] != peer_last[0]:
                    await asyncio.sleep(0.005)
    finally:
        x.release.set()
        if ticker is not None:
            ticker.cancel()
        stop.set()
        boundary.flush_wake.set()
        await asyncio.wait_for(cadence_task, timeout=2.0)
        await boundary.join_stamps()

    ev2_pubs = [t for t, eid in pub_events if eid == 2]
    ev1_pubs = [t for t, eid in pub_events if eid == 1]
    ev2_writes = [t for t, oids, _ in write_events if 900 in oids]
    ev1_writes = [t for t, oids, _ in write_events if 1 in oids]

    return {
        "release_ev1_target_s": release_ev1_at_s,
        "t_ev1_done": t_ev1_done,
        "t_done": round(time.monotonic() - t0, 4),
        "peer_last": peer_last[0],
        "peer_last_written": latest_written_prob[2],
        "t_ev1_quote2_buffered": t_ev1_quote2_buffered,
        "t_ev2_arrived": t_ev2_arrived,
        "t_ev1_released": t_ev1_released,
        "flush_work_after_fenced_flush2": flush_work_after_fenced_flush2,
        "ev2_published_before_ev1_release": ev2_published_before_ev1_release,
        "flush_starts": flush_starts,
        "ev2_writes": ev2_writes,
        "ev2_pubs": ev2_pubs,
        "ev2_latency_from_arrival_s": round(ev2_pubs[0] - t_ev2_arrived, 4),
        "ev1_writes": ev1_writes,
        "ev1_pubs": ev1_pubs,
        "ev1_final_latency_from_release_s": round(ev1_pubs[1] - t_ev1_released, 4),
        "stamp_fenced": p.ns["stats"]["stamp_fenced"],
        "total_flush_work": boundary.flush_work,
        "pending_after": sorted(x.r.pending_event_ids()),
        "errors": x.r.stats["errors"],
    }


async def test_healthy_peer_and_fenced_event_after_fully_fenced_flush_250ms_real_loop(
    monkeypatch, full_collections,
):
    """Prioritized real-loop comparison at 250 ms (`release_ev1_at_s=0.565`):
    - Flush 2 (~0.255s) is 100% fenced on Event 1.
    - Peer Event 2 arrives at ~0.295s.
    - Event 1 releases at ~0.565s (after the second 250 ms periodic window).
    Verifies both Peer Event 2's publication and Event 1's final publication.
    """
    out = await run_healthy_peer_after_fenced_flush_case(
        monkeypatch, release_ev1_at_s=0.565
    )
    assert out["errors"] == 0
    assert out["pending_after"] == []
    assert len(out["ev2_pubs"]) == 1
    assert len(out["ev1_pubs"]) == 2

    # On Candidate (where 100%-fenced Flush 2 does not charge `flush_work`),
    # `flush_work_after_fenced_flush2 == 1` and Peer Event 2 publishes within `WAKE_BOUND_S`
    # (~6-10ms) at ~0.302s while Event 1 is still held.
    # On Parent, `flush_work_after_fenced_flush2 == 2` and Peer Event 2 is held
    # for ~210ms until ~0.505s.
    assert out["flush_work_after_fenced_flush2"] == 1
    assert out["ev2_published_before_ev1_release"] is True
    assert out["ev2_latency_from_arrival_s"] < WAKE_BOUND_S, (
        f"full collections in case (ms): {full_collections}", out,
    )
    # The released event's newer quote rides the release wake, not the next
    # periodic timer (~193 ms after release before this change).
    assert out["ev1_final_latency_from_release_s"] < WAKE_BOUND_S, (
        f"full collections in case (ms): {full_collections}", out,
    )


async def test_healthy_peer_when_fenced_event_releases_inside_peer_budget_window_250ms_real_loop(
    monkeypatch,
):
    """Real-loop comparison when Event 1 releases at ~0.340s (45 ms after Peer
    Event 2 arrived at ~0.295s, inside the 250 ms socket budget window opened
    by Peer Event 2's ~0.300s flush):
    - Peer Event 2 still publishes within `WAKE_BOUND_S` (~0.302s vs ~0.506s on Parent).
    - Event 1's second quote flushes at the end of Peer Event 2's 250 ms socket
      budget window (~0.550s vs ~0.505s on Parent, i.e. the ~45ms socket budget
      phase shift from Event 2 flushing at ~0.300s, never the 145ms virtual
      clock artifact).
    """
    out = await run_healthy_peer_after_fenced_flush_case(
        monkeypatch, release_ev1_at_s=0.340
    )
    assert out["errors"] == 0
    assert out["pending_after"] == []
    assert out["flush_work_after_fenced_flush2"] == 1
    assert out["ev2_latency_from_arrival_s"] < WAKE_BOUND_S
    # The tradeoff, bounded: the released quote waits for the floor the peer's
    # flush set (its start + 250 ms), and no later than `FLOOR_MARGIN_S` past it.
    peer_flush = max(f for f in out["flush_starts"] if f <= out["ev2_writes"][0])
    floor = peer_flush + 0.25
    assert out["ev1_pubs"][1] >= floor - 0.010, out
    assert out["ev1_pubs"][1] - floor < FLOOR_MARGIN_S, out
    assert out["ev1_final_latency_from_release_s"] < 0.25 + FLOOR_MARGIN_S, out


async def test_fenced_withdrawal_recovery_after_stamp_release_250ms_real_loop(
    monkeypatch,
):
    """Repaired withdrawal control on the existing `paired(monkeypatch)` fixture
    at 250 ms cadence:
    - Flush 1 (~0.005s) writes Event 1 and parks Event 1's stamp on `x.release`.
    - At ~0.100s, a wide book for Event 1 (`{1: (0.1, 0.9), 2: (0.1, 0.9)}`)
      arrives and sets `flush_wake`.
    - At ~0.255s, Flush 2 fences the withdrawal via `join_stamp_reading`
      (`stamp_fenced == 2`, zero withdrawals while Event 1's stamp is held).
    - At ~0.300s, Event 1's stamp releases (`x.release.set()`), and the next
      flush withdraws `[1, 2]` (`held_prices_withdrawn == 2`, `p.books == {}`).
    """
    p, x = paired(monkeypatch, blocked=(1,))
    x.r.min_refresh_interval_s = 0.25
    boundary = p.ns["catalog_boundary"]
    for oid in (900, 901):
        p.ns["price_buffer"].pop(oid, None)
        p.ns["input_marks"].pop(oid, None)

    t0 = time.monotonic()
    flush_starts: list[float] = []
    withdraw_times: list[tuple[float, list[int]]] = []

    orig_withdraw = p.ns["withdraw_book_refuted_prices"]

    async def timed_withdraw(session, selected):
        rows = await orig_withdraw(session, selected)
        withdraw_times.append((round(time.monotonic() - t0, 4), sorted(selected)))
        return rows

    p.ns["withdraw_book_refuted_prices"] = timed_withdraw

    async def tracked_flush(started: float):
        flush_starts.append(round(started - t0, 4))
        return await p.ns["flush_prices"](flush_started=started)

    stop = asyncio.Event()
    boundary.flush_wake.set()
    cadence_task = asyncio.create_task(
        blend.run_flush_cadence(
            tracked_flush,
            0.25,
            stop=stop,
            failed_retry_interval_s=2.0,
            wake=boundary.flush_wake,
            work_count=lambda: boundary.flush_work,
            wake_coalesce_s=pm.PM_WAKE_COALESCE_SECONDS,
        )
    )
    try:
        await settle_until(lambda: len(x.sessions) >= 1)
        await asyncio.sleep(max(0.0, 0.100 - (time.monotonic() - t0)))
        p.books.update({1: (0.1, 0.9), 2: (0.1, 0.9)})
        boundary.flush_wake.set()

        await settle_until(
            lambda: len(flush_starts) >= 2
            and p.ns["stats"]["stamp_fenced"] >= 2
            and boundary.active == 0
        )
        assert withdraw_times == [], "withdrawal ran while Event 1's stamp was held"
        flush_work_after_fenced_withdraw = boundary.flush_work

        await asyncio.sleep(0.040)
        t_released = round(time.monotonic() - t0, 4)
        x.release.set()

        async with asyncio.timeout(1.0):
            while not withdraw_times:
                await asyncio.sleep(0.005)
    finally:
        x.release.set()
        stop.set()
        boundary.flush_wake.set()
        await asyncio.wait_for(cadence_task, timeout=2.0)
        await boundary.join_stamps()

    assert withdraw_times[0][1] == [1, 2]
    assert p.ns["stats"]["held_prices_withdrawn"] == 2
    assert not p.books
    assert flush_work_after_fenced_withdraw == 1
    # Withdrawn on the release wake (~209 ms after release before this change).
    assert withdraw_times[0][0] - t_released < WAKE_BOUND_S, (t_released, withdraw_times)


async def test_failed_stamp_hold_until_does_not_spin_on_wake_250ms_real_loop(
    monkeypatch,
):
    """Repaired failed-backoff control on the existing `paired(monkeypatch)`
    fixture at 250 ms cadence:
    - Event 2's first stamp commit fails (`failure='commit'`), setting
      `x.r._failed_hold_until[2] = clock + 0.45` and keeping Event 2 in
      `x.r.pending_event_ids()`.
    - During the 0.45s backoff window, `run_flush_cadence` does not spin on
      `flush_wake` (only the 250 ms periodic timer ticks run).
    - Once the transient failure clears and the 0.45s hold expires, the next
      250 ms periodic flush stamps and publishes Event 2 via `refresh_pending`.
    """
    p, x = paired(monkeypatch, blocked=())
    x.r.min_refresh_interval_s = 0.25
    x.r.failed_retry_interval_s = 0.45
    boundary = p.ns["catalog_boundary"]

    # Keep only Event 2 ({900: 0.7, 901: 0.3}) so Event 2 is the singleton stamp.
    for oid in (1, 2):
        p.ns["price_buffer"].pop(oid, None)
        p.ns["input_marks"].pop(oid, None)

    fail_commit = {"active": True}
    orig_factory = x.r._session_factory

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def flaky_factory():
        async with orig_factory() as session:
            yield session
            if fail_commit["active"] and 2 in session.event_ids:
                fail_commit["active"] = False
                raise RuntimeError("transient commit failure on event 2")

    x.r._session_factory = flaky_factory

    t0 = time.monotonic()
    flush_starts: list[float] = []

    async def tracked_flush(started: float):
        flush_starts.append(round(started - t0, 4))
        return await p.ns["flush_prices"](flush_started=started)

    stop = asyncio.Event()
    boundary.flush_wake.set()
    cadence_task = asyncio.create_task(
        blend.run_flush_cadence(
            tracked_flush,
            0.25,
            stop=stop,
            failed_retry_interval_s=2.0,
            wake=boundary.flush_wake,
            work_count=lambda: boundary.flush_work,
            wake_coalesce_s=pm.PM_WAKE_COALESCE_SECONDS,
        )
    )
    try:
        # Wait for Flush 1's stamp attempt on Event 2 to fail and enter backoff.
        await settle_until(lambda: 2 in x.r._failed_hold_until)
        assert x.r.stats["errors"] == 1
        assert 2 in x.r.pending_event_ids()
        assert 2 not in x.published

        # Wait until Event 2 recovers and publishes after the 0.45s hold expires
        # (on the ~0.505s periodic flush).
        async with asyncio.timeout(1.0):
            while 2 not in x.published:
                await asyncio.sleep(0.01)
    finally:
        stop.set()
        boundary.flush_wake.set()
        await asyncio.wait_for(cadence_task, timeout=2.0)
        await boundary.join_stamps()

    # Over ~0.52s, exactly 3 flushes ran (~0.005s, ~0.255s, ~0.505s) — no wake spin!
    assert len(flush_starts) == 3
    assert 2 in x.published
    assert not x.r.pending_event_ids()


async def test_cancellation_and_shutdown_preserve_pending_debt_real_loop(monkeypatch):
    """Cancelling `join_stamps(cancel=True)` while Event 1 is held and fenced
    clears `fenced` (when present), does not spuriously set `flush_wake`, and
    preserves both Event 1's pending debt and the buffered newer quote.
    """
    p, x = paired(monkeypatch, blocked=(1,))
    x.r.min_refresh_interval_s = 0.25
    boundary = p.ns["catalog_boundary"]
    for oid in (900, 901):
        p.ns["price_buffer"].pop(oid, None)
        p.ns["input_marks"].pop(oid, None)

    await p.ns["flush_prices"](flush_started=1000.0)
    await settle_until(lambda: len(x.sessions) >= 1)
    owner = boundary.stamp_owner(x.r)
    assert owner.task is not None and not owner.task.done()

    p.ns["price_buffer"].update({1: 0.64, 2: 0.36})
    boundary.flush_wake.clear()
    await p.ns["flush_prices"](flush_started=1000.25)
    assert p.ns["stats"]["stamp_fenced"] == 2

    await boundary.join_stamps(cancel=True)
    if hasattr(owner, "fenced"):
        assert owner.fenced == set()
    assert not boundary.flush_wake.is_set()
    assert 1 in x.r.pending_event_ids()
    assert p.ns["price_buffer"] == {1: 0.64, 2: 0.36}


async def test_released_event_bounded_under_sustained_peer_traffic_250ms_real_loop(
    monkeypatch,
):
    """Peer Event 2 moves every 50 ms from ~0.295 s to ~1.0 s while Event 1 is
    held and then released at ~0.565 s. Every peer flush is real work, so each
    sets the next 250 ms floor: the released quote may wait for that floor but
    never past it plus a margin, the work ceiling holds (no spin), and the
    peer's latest value is the one written.
    """
    out = await run_healthy_peer_after_fenced_flush_case(
        monkeypatch, release_ev1_at_s=0.565, peer_tick_s=0.050, peer_until_s=1.0,
    )
    assert out["errors"] == 0
    assert out["pending_after"] == []
    assert out["flush_work_after_fenced_flush2"] == 1
    assert out["ev2_latency_from_arrival_s"] < WAKE_BOUND_S
    assert out["ev1_final_latency_from_release_s"] < 0.25 + FLOOR_MARGIN_S, out
    # Ceiling: actual work starts at most once per 250 ms, so the run holds no
    # more flushes than its length allows (plus the first and a closing probe).
    starts = out["flush_starts"]
    assert len(starts) <= int(out["t_done"] / 0.25) + 3, out
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    assert all(g >= 0.25 - 0.010 for g in gaps[2:]), out
    assert out["peer_last_written"] == out["peer_last"], out


async def test_a_release_observer_set_on_the_window_never_replaces_the_release_wake():
    """The default-off stage trace (#11037) observes releases through the
    window's own `on_release`; the functional wake is a separate slot, so
    turning a trace on can never silence it."""
    woken: list[list[int]] = []
    observed: list[list[int]] = []
    window = blend._FreshAdmission(
        1000.0, 1000.0, {1, 2}, release_wake=lambda ids: woken.append(sorted(ids)),
    )
    window.on_release = lambda ids: observed.append(sorted(ids))
    window.release({1})
    assert woken == [[1]]
    assert window.release_wake is not window.on_release


async def test_the_pm_stamp_owner_installs_its_wake_on_the_refresher():
    """`_PMStampOwner` binds the refresher's `release_wake`; every window the
    refresher opens is handed it (`_FreshAdmission(..., release_wake=...)`)."""
    refresher = blend.LiveBlendRefresher("polymarket")
    boundary = pm._PMCatalogFlushBoundary()
    owner = boundary.stamp_owner(refresher)
    assert refresher.release_wake == owner._on_release
    assert owner.wake is boundary.flush_wake


def test_a_case_starts_with_no_full_collection_owed_and_names_one_inside_it(
    full_collections,
):
    """The fixture's two halves: no gen-1 collection has run since its full
    collection (so none is close to promoting into a full one), and a full
    collection that does land inside a case is named with its pause."""
    assert gc.isenabled()
    assert gc.get_count()[2] == 0
    assert full_collections == []
    gc.collect()
    assert len(full_collections) == 1 and full_collections[0] >= 0
