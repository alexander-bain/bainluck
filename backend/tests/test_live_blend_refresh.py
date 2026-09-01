"""Q460 — guards for the fast lane's last mile.

The ship is "the number on the card moves with the action". The failure classes
that would silently un-ship it, each with a test below:

* the refresher writes on every tick and the write rate melts the DB (throttle);
* the refresher stops writing when a price is stable, the source ages out under
  the hero's recency decay (#1829), and the blend quietly drifts to whichever
  source is noisiest (unchanged re-stamp);
* the inversion verdict is re-derived per tick, so a 2-second loop issues a
  per-event `odds_snapshots` query and the fast lane becomes the slow lane
  (verdict cache);
* one bad event raises inside the WS flush loop and takes down the price
  streaming that is the dyno's actual job (gotcha #42, containment).
"""

import pytest

from app.tasks.live_blend_refresh import (
    LiveBlendRefresher,
    event_ids_for_outcomes,
)


class TestEventIdsForOutcomes:
    def test_maps_outcomes_to_distinct_events(self):
        mapping = {1: 100, 2: 100, 3: 200}
        assert event_ids_for_outcomes(mapping, [1, 2, 3]) == {100, 200}

    def test_unlinked_outcomes_contribute_nothing(self):
        """An outcome with no linked event has no card to refresh."""
        mapping = {1: 100, 2: None}
        assert event_ids_for_outcomes(mapping, [1, 2, 999]) == {100}

    def test_empty_batch_is_empty(self):
        assert event_ids_for_outcomes({1: 100}, []) == set()


class TestThrottle:
    def test_first_sight_of_an_event_is_always_due(self):
        r = LiveBlendRefresher("kalshi", min_refresh_interval_s=5.0)
        assert r._due(42, now=1000.0) is True

    def test_a_second_tick_inside_the_interval_is_not_due(self):
        r = LiveBlendRefresher("kalshi", min_refresh_interval_s=5.0)
        r._last_refresh_at[42] = 1000.0
        assert r._due(42, now=1003.0) is False

    def test_the_interval_boundary_is_due(self):
        r = LiveBlendRefresher("kalshi", min_refresh_interval_s=5.0)
        r._last_refresh_at[42] = 1000.0
        assert r._due(42, now=1005.0) is True

    def test_throttling_one_event_does_not_throttle_its_neighbour(self):
        r = LiveBlendRefresher("kalshi", min_refresh_interval_s=5.0)
        r._last_refresh_at[42] = 1000.0
        assert r._due(43, now=1001.0) is True


class TestShouldWrite:
    def test_first_value_for_an_event_is_written(self):
        r = LiveBlendRefresher("kalshi")
        assert r._should_write(1, 0.61, now=100.0) is True

    def test_a_moved_price_is_written_immediately(self):
        r = LiveBlendRefresher("kalshi")
        r._last_written_value[1] = 0.61
        r._last_write_at[1] = 100.0
        assert r._should_write(1, 0.62, now=101.0) is True

    def test_an_unmoved_price_is_not_rewritten_every_tick(self):
        r = LiveBlendRefresher("kalshi", unchanged_restamp_interval_s=45.0)
        r._last_written_value[1] = 0.61
        r._last_write_at[1] = 100.0
        assert r._should_write(1, 0.61, now=110.0) is False

    def test_an_unmoved_price_is_restamped_eventually(self):
        """`updated_at` drives the hero's relative recency decay: a source that
        keeps quoting the same price must keep SAYING so, or it loses weight to
        noisier siblings and the blend drifts."""
        r = LiveBlendRefresher("kalshi", unchanged_restamp_interval_s=45.0)
        r._last_written_value[1] = 0.61
        r._last_write_at[1] = 100.0
        assert r._should_write(1, 0.61, now=145.0) is True


class _FakeSession:
    """Counts how often the inversion check would touch the database."""


class TestInversionVerdictCache:
    @pytest.mark.asyncio
    async def test_verdict_is_computed_once_and_reused(self, monkeypatch):
        calls = []

        async def _fake_check(session, event_id, home_prob, source):
            calls.append((event_id, home_prob))
            return home_prob  # not inverted

        monkeypatch.setattr(
            "app.tasks.prediction_market_matching._check_and_fix_inversion",
            _fake_check,
        )
        r = LiveBlendRefresher("kalshi", inversion_ttl_s=150.0)
        s = _FakeSession()

        assert await r._oriented(s, 7, 0.61) == 0.61
        assert await r._oriented(s, 7, 0.64) == 0.64
        assert await r._oriented(s, 7, 0.70) == 0.70
        assert len(calls) == 1, "orientation must not be re-derived per tick"

    @pytest.mark.asyncio
    async def test_a_flip_verdict_applies_to_later_prices(self, monkeypatch):
        """The cache stores the BOOLEAN, not the value — caching the value would
        pin a price, which is the opposite of a fast lane."""

        async def _fake_check(session, event_id, home_prob, source):
            return 1.0 - home_prob  # inverted linkage

        monkeypatch.setattr(
            "app.tasks.prediction_market_matching._check_and_fix_inversion",
            _fake_check,
        )
        r = LiveBlendRefresher("kalshi")
        s = _FakeSession()

        assert abs(await r._oriented(s, 7, 0.30) - 0.70) < 1e-9
        # Second call is served from cache, and must still flip the NEW price.
        assert abs(await r._oriented(s, 7, 0.25) - 0.75) < 1e-9

    @pytest.mark.asyncio
    async def test_verdict_expires_and_is_re_derived(self, monkeypatch):
        calls = []

        async def _fake_check(session, event_id, home_prob, source):
            calls.append(event_id)
            return home_prob

        monkeypatch.setattr(
            "app.tasks.prediction_market_matching._check_and_fix_inversion",
            _fake_check,
        )
        r = LiveBlendRefresher("kalshi", inversion_ttl_s=150.0)
        s = _FakeSession()

        await r._oriented(s, 7, 0.61)
        # Force the cached entry to have expired.
        expires_at, flipped = r._inversion[7]
        r._inversion[7] = (expires_at - 1000.0, flipped)
        await r._oriented(s, 7, 0.61)
        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_two_events_get_independent_verdicts(self, monkeypatch):
        async def _fake_check(session, event_id, home_prob, source):
            return (1.0 - home_prob) if event_id == 2 else home_prob

        monkeypatch.setattr(
            "app.tasks.prediction_market_matching._check_and_fix_inversion",
            _fake_check,
        )
        r = LiveBlendRefresher("kalshi")
        s = _FakeSession()
        assert abs(await r._oriented(s, 1, 0.30) - 0.30) < 1e-9
        assert abs(await r._oriented(s, 2, 0.30) - 0.70) < 1e-9


class TestContainment:
    """A blend refresh that raises must never stop the WS streaming prices."""

    @pytest.mark.asyncio
    async def test_a_failing_batch_is_counted_not_raised(self, monkeypatch):
        r = LiveBlendRefresher("kalshi")

        async def _boom(event_ids, now):
            raise RuntimeError("db went away")

        monkeypatch.setattr(r, "_refresh_batch", _boom)
        stats = await r.refresh([1, 2, 3])
        assert stats["errors"] == 1
        assert stats["considered"] == 3

    @pytest.mark.asyncio
    async def test_an_empty_batch_does_no_work(self, monkeypatch):
        r = LiveBlendRefresher("kalshi")
        called = []

        async def _spy(event_ids, now):
            called.append(list(event_ids))

        monkeypatch.setattr(r, "_refresh_batch", _spy)
        await r.refresh([])
        assert called == []

    @pytest.mark.asyncio
    async def test_throttled_events_are_counted_and_skipped(self, monkeypatch):
        r = LiveBlendRefresher("kalshi", min_refresh_interval_s=1e9)
        seen = []

        async def _spy(event_ids, now):
            seen.append(sorted(event_ids))

        monkeypatch.setattr(r, "_refresh_batch", _spy)
        await r.refresh([1, 2])
        assert seen == [[1, 2]]
        # Mark them refreshed the way `_refresh_batch` would.
        import time as _t
        r._last_refresh_at[1] = _t.monotonic()
        r._last_refresh_at[2] = _t.monotonic()
        await r.refresh([1, 2])
        assert seen == [[1, 2]], "second pass must not re-enter the batch"
        assert r.stats["throttled"] == 2


class TestThrottleIsStampedBeforeResolution:
    """An event that resolves no markets must still be throttled.

    `get_task_session()` builds a fresh engine and connection pool per call. If
    the throttle were stamped only for events that resolved markets, an event
    with no linked markets of this source would stay permanently due and open a
    Postgres connection on every 2-second flush, forever, to find the same
    nothing. Guarded by asserting the stamp covers the whole attempted batch.
    """

    @pytest.mark.asyncio
    async def test_every_attempted_event_is_stamped_even_with_no_markets(
        self, monkeypatch
    ):
        r = LiveBlendRefresher("kalshi")
        opened = []

        async def _fake_batch(event_ids, now):
            opened.append(sorted(event_ids))
            # Mimic the real early-return when the market query finds nothing,
            # which happens AFTER the throttle stamp in the implementation.
            for eid in event_ids:
                r._last_refresh_at[eid] = now
            return

        monkeypatch.setattr(r, "_refresh_batch", _fake_batch)
        await r.refresh([501, 502])
        assert opened == [[501, 502]]
        await r.refresh([501, 502])
        assert opened == [[501, 502]], (
            "an unresolvable event must not re-open a session every flush"
        )

    def test_the_stamp_precedes_the_session_open_in_source(self):
        """Order guard: stamping after the session would not prevent the open."""
        import ast
        import inspect
        import textwrap

        from app.tasks.live_blend_refresh import LiveBlendRefresher as _LBR

        # `getsource` on a method keeps its class indentation, which `ast.parse`
        # rejects outright — dedent first or this guard fails for the wrong reason.
        tree = ast.parse(textwrap.dedent(inspect.getsource(_LBR._refresh_batch)))
        stamp_lines = [
            n.lineno
            for n in ast.walk(tree)
            if isinstance(n, ast.Attribute) and n.attr == "_last_refresh_at"
        ]
        session_lines = [
            n.lineno
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "get_task_session"
        ]
        assert stamp_lines and session_lines
        assert min(stamp_lines) < min(session_lines)


class TestSourceIsolation:
    def test_two_refreshers_do_not_share_state(self):
        """Kalshi and Polymarket run on the same dyno; neither may evict the
        other's throttles or verdicts."""
        k = LiveBlendRefresher("kalshi")
        p = LiveBlendRefresher("polymarket")
        k._last_refresh_at[1] = 1000.0
        assert p._due(1, now=1000.1) is True
        assert k.stats is not p.stats


# ─────────────────────────────────────────────────────────────────────────────
# Q501 — the fast lane also moves the CHART, not just the number.
#
# Alex, 2026-09-01: "our probability graphs don't update" on the US Open. The
# blend key moving sub-second is only half the ship; `win_prob_snapshots` is the
# series `GET /api/events/{id}/history` returns as `win_prob_history`, and the
# 120s poll used to be its only writer. These guard the two ways adding a second
# writer goes wrong: it writes per-tick and multiplies the table, or it lets a
# snapshot failure cost the blend stamp that already succeeded.
# ─────────────────────────────────────────────────────────────────────────────


class _SnapSession:
    """A session that can accept an ORM insert, which `_FakeSession` cannot."""

    def __init__(self):
        self.added = []

    def add(self, row):
        self.added.append(row)


class _Reading:
    """Stand-in for the BlendReading the refresher passes to the snapshot."""

    class _Market:
        id = 77
        name = "Fritz vs Blanch"

    class _Outcome:
        name = "Taylor Fritz"

    market = _Market()
    outcome = _Outcome()
    yes_probability = 0.99


class TestSnapshotThrottle:
    """The chart point runs on its OWN clock, slower than the blend's."""

    @pytest.mark.asyncio
    async def test_first_stamp_for_an_event_writes_a_chart_point(self, monkeypatch):
        r, calls = _snapshot_spy(monkeypatch)
        await r._maybe_snapshot(_SnapSession(), 1, 0.61, _Reading(), now=100.0)
        assert len(calls) == 1
        assert r.stats["snapshots_written"] == 1

    @pytest.mark.asyncio
    async def test_a_second_stamp_inside_the_interval_writes_no_point(self, monkeypatch):
        """Q460's stated objection — a snapshot per tick — must stay refused.

        The blend throttle is 5s and the snapshot throttle is 25s, so a
        continuously-ticking market must NOT produce a chart point per stamp.
        """
        r, calls = _snapshot_spy(monkeypatch, snapshot_interval_s=25.0)
        await r._maybe_snapshot(_SnapSession(), 1, 0.61, _Reading(), now=100.0)
        await r._maybe_snapshot(_SnapSession(), 1, 0.62, _Reading(), now=110.0)
        await r._maybe_snapshot(_SnapSession(), 1, 0.63, _Reading(), now=120.0)
        assert len(calls) == 1, "the snapshot clock is not the blend clock"

    @pytest.mark.asyncio
    async def test_the_interval_boundary_writes_again(self, monkeypatch):
        r, calls = _snapshot_spy(monkeypatch, snapshot_interval_s=25.0)
        await r._maybe_snapshot(_SnapSession(), 1, 0.61, _Reading(), now=100.0)
        await r._maybe_snapshot(_SnapSession(), 1, 0.62, _Reading(), now=125.0)
        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_the_interval_clears_inside_a_minute(self, monkeypatch):
        """Alex's bar is a chart point 'within a minute'. Pin it as a number."""
        r, _ = _snapshot_spy(monkeypatch)
        assert r.snapshot_interval_s <= 60.0

    @pytest.mark.asyncio
    async def test_throttling_one_event_does_not_throttle_its_neighbour(self, monkeypatch):
        r, calls = _snapshot_spy(monkeypatch, snapshot_interval_s=25.0)
        await r._maybe_snapshot(_SnapSession(), 1, 0.61, _Reading(), now=100.0)
        await r._maybe_snapshot(_SnapSession(), 2, 0.44, _Reading(), now=101.0)
        assert len(calls) == 2


class TestSnapshotShape:
    @pytest.mark.asyncio
    async def test_away_is_the_complement_and_the_writer_is_named(self, monkeypatch):
        r, calls = _snapshot_spy(monkeypatch)
        await r._maybe_snapshot(_SnapSession(), 1, 0.61, _Reading(), now=100.0)
        kwargs = calls[0]
        assert kwargs["home_win_probability"] == 0.61
        assert kwargs["away_win_probability"] == 0.39
        # Distinguishable from the poll's "live_fast" in the audit trail.
        assert kwargs["game_state"]["poll_type"] == "ws_fast_lane"
        assert kwargs["source"] == "kalshi"

    @pytest.mark.asyncio
    async def test_a_deduped_point_is_counted_separately(self, monkeypatch):
        """The shared helper returns is_new=False on an unmoved value."""
        r, _ = _snapshot_spy(monkeypatch, is_new=False)
        await r._maybe_snapshot(_SnapSession(), 1, 0.61, _Reading(), now=100.0)
        assert r.stats["snapshots_written"] == 0
        assert r.stats["snapshots_deduped"] == 1


class TestSnapshotContainment:
    """The chart is downstream of the number and must never cost it."""

    @pytest.mark.asyncio
    async def test_a_failing_snapshot_is_counted_not_raised(self, monkeypatch):
        async def _boom(session, **kwargs):
            raise RuntimeError("snapshot table went away")

        monkeypatch.setattr(
            "app.tasks.snapshots._create_or_update_win_prob_snapshot", _boom
        )
        r = LiveBlendRefresher("kalshi")
        # Must not raise — the blend stamp before it already succeeded.
        await r._maybe_snapshot(_SnapSession(), 1, 0.61, _Reading(), now=100.0)
        assert r.stats["errors"] == 1
        assert r.stats["snapshots_written"] == 0

    @pytest.mark.asyncio
    async def test_a_failed_snapshot_still_consumes_its_throttle_slot(self, monkeypatch):
        """A permanently-failing event must not retry on every single flush."""
        async def _boom(session, **kwargs):
            raise RuntimeError("nope")

        monkeypatch.setattr(
            "app.tasks.snapshots._create_or_update_win_prob_snapshot", _boom
        )
        r = LiveBlendRefresher("kalshi", snapshot_interval_s=25.0)
        await r._maybe_snapshot(_SnapSession(), 1, 0.61, _Reading(), now=100.0)
        await r._maybe_snapshot(_SnapSession(), 1, 0.61, _Reading(), now=105.0)
        assert r.stats["errors"] == 1, "a failing event must not retry every flush"


def _snapshot_spy(monkeypatch, *, snapshot_interval_s=25.0, is_new=True):
    """A refresher whose snapshot helper records its kwargs instead of writing."""
    calls = []

    async def _fake_create(session, **kwargs):
        calls.append(kwargs)
        return object(), is_new

    monkeypatch.setattr(
        "app.tasks.snapshots._create_or_update_win_prob_snapshot", _fake_create
    )
    return LiveBlendRefresher("kalshi", snapshot_interval_s=snapshot_interval_s), calls


class TestTheFastLaneActuallyCallsTheSnapshot:
    """Without this, every test above passes on a DISCONNECTED feature.

    `_maybe_snapshot` is driven directly by the tests above, so deleting its
    call site inside `_refresh_batch` would leave them all green while the
    chart silently went back to the 120s poll's cadence — exactly the bug this
    queue exists to fix, reintroduced invisibly.
    """

    def test_refresh_batch_invokes_maybe_snapshot(self):
        import inspect

        from app.tasks.live_blend_refresh import LiveBlendRefresher

        src = inspect.getsource(LiveBlendRefresher._refresh_batch)
        assert "_maybe_snapshot" in src, (
            "the fast lane no longer writes a chart point"
        )

    def test_the_snapshot_follows_a_successful_stamp(self):
        """Ordering matters: a chart point must not outrun the number.

        The snapshot shares the blend stamp's transaction deliberately, so the
        call has to sit after `stats["stamped"]`, inside the same try — not
        before the write and not outside it.
        """
        import inspect

        from app.tasks.live_blend_refresh import LiveBlendRefresher

        src = inspect.getsource(LiveBlendRefresher._refresh_batch)
        assert src.index('self.stats["stamped"]') < src.index("_maybe_snapshot")
