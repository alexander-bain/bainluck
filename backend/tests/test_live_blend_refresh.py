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
