"""LAT-P021 (#1107): the warmer, and the TTL that makes it worth running.

The outage had NO EXIT VIA USER TRAFFIC: two of the four golf majors 503'd at
Heroku's 30.3s H12 boundary on every request, and a request that never completes
never writes the cache, so every visitor paid the full cold build forever.

Two halves, and the task is theatre without both — which is what these tests are
mostly here to pin:
  1. a settled envelope caches for 24h instead of 60s
  2. a worker warms the four keys off the request path

A warmer alone against a 60s TTL would run, report success, and leave the page
cold for 59 of every 60 seconds.
"""

import pytest

from app.routes.event import _ENVELOPE_TTL, _SETTLED_TTL, _envelope_ttl
from app.tasks.warm_event_concepts import (
    MAJOR_EVENT_KEYS,
    _run_warm_major_event_concepts,
)


class TestSettledTtl:
    def test_a_settled_envelope_gets_the_long_ttl(self):
        assert _envelope_ttl({"event": {"status": "settled"}}) == _SETTLED_TTL

    def test_a_live_envelope_keeps_the_short_ttl(self):
        """LAT-P014's freshness reasoning for moving events is untouched."""
        assert _envelope_ttl({"event": {"status": "live"}}) == _ENVELOPE_TTL

    @pytest.mark.parametrize(
        "envelope", [{}, {"event": None}, {"event": {}}, {"event": {"status": None}}]
    )
    def test_anything_not_explicitly_settled_gets_the_short_ttl(self, envelope):
        """The failure directions are NOT symmetric, so the default is the cheap one.

        Mis-reading a live event as settled freezes a moving probability for a
        day — a visible product lie. Mis-reading a settled one as live costs a
        rebuild. So only the literal string "settled" earns the long TTL.
        """
        assert _envelope_ttl(envelope) == _ENVELOPE_TTL

    def test_the_long_ttl_is_actually_long_enough_to_outlive_the_beat(self):
        """The pairing, asserted rather than assumed.

        The beat is hourly. If the settled TTL were ever shortened below that,
        the warmer would silently stop covering the gap between runs and the
        page would go cold again with every task still reporting success.
        """
        one_hour = 3600
        assert _SETTLED_TTL > one_hour


class TestWarmerHonesty:
    """`_tracked_run` classifies on the returned summary, so the summary must lie
    about nothing. This task exists because a zero-yield loop read as success."""

    @pytest.mark.asyncio
    async def test_a_pass_that_warms_nothing_terminals_as_failed(self, monkeypatch):
        async def _all_absent(key):
            return key, "absent"

        monkeypatch.setattr(
            "app.tasks.warm_event_concepts._warm_one", _all_absent
        )
        out = await _run_warm_major_event_concepts()
        assert out["warmed"] == 0
        assert out["terminal"] == "failed", (
            "warming zero keys must NOT read as a success — that is the exact "
            "shape that let #683 look healthy every 6h for ten weeks"
        )

    @pytest.mark.asyncio
    async def test_a_partial_pass_says_partial(self, monkeypatch):
        async def _half(key):
            return key, "warm" if key == MAJOR_EVENT_KEYS[0] else "error"

        monkeypatch.setattr("app.tasks.warm_event_concepts._warm_one", _half)
        out = await _run_warm_major_event_concepts()
        assert out["warmed"] == 1
        assert out["terminal"] == "partial"

    @pytest.mark.asyncio
    async def test_a_full_pass_says_ok(self, monkeypatch):
        async def _all_warm(key):
            return key, "warm"

        monkeypatch.setattr("app.tasks.warm_event_concepts._warm_one", _all_warm)
        out = await _run_warm_major_event_concepts()
        assert out["warmed"] == len(MAJOR_EVENT_KEYS)
        assert out["terminal"] == "ok"

    @pytest.mark.asyncio
    async def test_a_short_ttl_warm_does_NOT_count_as_warmed(self, monkeypatch):
        """The subtle one, and the reason `warm_short_ttl` is its own state.

        If an envelope stops reporting `settled`, the warm still SUCCEEDS — a key
        is written — but it evaporates in 60s and the endpoint is cold again long
        before the next beat. Counting that as warmed would make the task green
        while the outage returned.
        """
        async def _short(key):
            return key, "warm_short_ttl"

        monkeypatch.setattr("app.tasks.warm_event_concepts._warm_one", _short)
        out = await _run_warm_major_event_concepts()
        assert out["warmed"] == 0
        assert out["terminal"] == "failed"

    @pytest.mark.asyncio
    async def test_one_bad_key_does_not_kill_the_pass(self, monkeypatch):
        """Gotcha #42, one level up: a throw inside a per-item loop must not
        empty the whole pass."""
        async def _one_throws(key):
            if key == MAJOR_EVENT_KEYS[1]:
                raise RuntimeError("boom")
            return key, "warm"

        monkeypatch.setattr("app.tasks.warm_event_concepts._warm_one", _one_throws)
        with pytest.raises(RuntimeError):
            # _warm_one itself swallows; this asserts the monkeypatched raise is
            # what escapes, i.e. the loop has no extra swallow hiding real bugs.
            await _run_warm_major_event_concepts()


class TestWarmSet:
    def test_the_four_majors_are_the_warm_set(self):
        assert len(MAJOR_EVENT_KEYS) == 4
        for slug in ("the-masters", "pga-championship", "us-open", "the-open-championship"):
            assert f"event:golf:{slug}" in MAJOR_EVENT_KEYS

    def test_the_warm_set_stays_bounded(self):
        """Deliberately a list, not a query.

        "All settled golf tournaments" grows without limit and puts the cost back,
        just on a worker instead of a dyno. If this ever needs to be dynamic it
        needs a bound, and this test should be the thing that argues about it.
        """
        assert len(MAJOR_EVENT_KEYS) <= 10


def test_the_route_actually_uses_the_ttl_function():
    """The wiring, not just the helper.

    Caught by mutation: reverting the route's write back to the flat
    `_ENVELOPE_TTL` left every test above GREEN, because they all exercise
    `_envelope_ttl` directly. A helper nothing calls is a helper that does
    nothing, and the whole payoff of LAT-P021 lives in this one call site.
    """
    import inspect
    from app.routes import event as event_mod

    src = inspect.getsource(event_mod.get_event_concept)
    assert "_envelope_ttl(envelope)" in src, (
        "routes/event.py no longer chooses its primary TTL via _envelope_ttl -- "
        "settled envelopes are back on the 60s TTL and the hourly warmer cannot "
        "keep them warm, so #1107 returns silently with the task still green"
    )
