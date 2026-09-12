"""#5728 — a read that RAISED must not render as a confident, wrong page.

═══ THE TWO PRODUCTION EVENTS THIS FILE IS BUILT FROM ═══

Both captured on 2026-09-12, finals day, by the watch Fable directed at
`/api/tournaments/us-open` through the women's final. Both bodies are banked
under `artifacts-live-177/`.

**19:51:18Z — one request, catastrophic.** The page rebuilt into the
tournament's FIRST ROUND: 96 R128 rows all dated 2026-08-30, `results.count: 0`,
`scoreboard: "unavailable"`, `auto_linked_matchups: 0`. The samples seven
seconds either side were perfect. Four independent Redis reads had to miss at
once to produce it — the hub fragment cache (hence the fresh rebuild), the
results primary key, the results last-good key, and the link overlay. Four keys
with four TTLs and four writers cannot expire in the same millisecond and all be
back five seconds later; a dropped connection explains all four and key absence
explains none.

**20:21:05Z — one build, cached, milder.** Only the link overlay failed. The
slate and results were right; `blend_linked` read 0 and `incoherent` read 2 over
two rows both carrying `coherent: true`. The cache write SUCCEEDED, so five
consecutive requests over nineteen seconds were served the same bad body — all
five reporting `generated_at` 20:21:05.149645Z to the microsecond.

So the reach is not "one request in five". It is every reader for the life of
the TTL after any failed rebuild whose cache write then lands — and that is
MORE likely the less unwell Redis is, because a partial failure is exactly the
state in which a read fails and a write succeeds.

═══ THE DEFECT, AND WHY IT IS NOT IN ANY ACCESSOR ═══

Every accessor on this path swallows its own exception, and every one is
individually defensible: "cache is an optimisation, never a gate" is true of
each of them. `_espn_results` even quotes gotcha #53 in its own docstring while
committing it one level up — it distinguishes primary-hit / last-good-hit /
neither, and does not distinguish *neither because both keys are absent* (a real
quiet day, where rewinding the slate to the register is correct and #3304
settled it) from *neither because the read raised* (our infrastructure blinking,
where rewinding is a lie).

**No accessor is wrong; the composition is.** These tests are written against
the composition, not against any one except clause.
"""

import json
from typing import Any

import pytest

from app.routes import tournaments
from app.routes.tournaments import (
    SCOREBOARD_DEGRADED,
    _espn_results,
    _note_read_failure,
    _read_failure_ledger,
    _withheld_slate,
)

RESULTS_PREFIX = tournaments.RESULTS_PREFIX
LAST_GOOD_PREFIX = tournaments.RESULTS_LAST_GOOD_PREFIX


class _Redis:
    """Absent keys by default; `raises` is the state this file is about."""

    def __init__(self, contents=None, raises=None):
        self.contents = contents or {}
        self.raises = raises

    async def get(self, key):
        if self.raises:
            raise self.raises
        return self.contents.get(key)


@pytest.fixture
def redis(monkeypatch):
    import app.tasks.redis_state as redis_state

    client = _Redis()
    monkeypatch.setattr(redis_state, "get_async_redis_client", lambda: client)
    return client


# ─────────────────────────────────────────────────────────────────────────────
# 1. THE DISTINCTION ITSELF
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestARaiseIsNotAnAbsence:
    async def test_a_raised_read_is_degraded_not_unavailable(self, redis):
        redis.raises = RuntimeError("connection reset by peer")
        assert (await _espn_results("us-open"))["scoreboard"] == SCOREBOARD_DEGRADED

    async def test_genuinely_absent_keys_still_read_unavailable(self, redis):
        """The other direction, and it is not decoration.

        A quiet day must keep the #3304 behaviour: the register fallback is
        right when we know there is nothing on. Make every miss `degraded` and
        the card empties on a real day off.
        """
        assert (await _espn_results("us-open"))["scoreboard"] == "unavailable"

    async def test_a_live_scoreboard_is_untouched(self, redis):
        redis.contents[f"{RESULTS_PREFIX}us-open"] = json.dumps(
            {"order_of_play": {"1": {"state": "decided"}}}
        )
        assert (await _espn_results("us-open"))["scoreboard"] == "live"

    async def test_a_raise_on_the_primary_still_reaches_the_last_good_key(
        self, monkeypatch
    ):
        """Degradation is per-read, not per-request. A primary that raises must
        not skip the fallback #3304 added — that would turn this fix into a
        regression of the one before it."""

        class _FlakyOnce(_Redis):
            def __init__(self):
                super().__init__()
                self.seen = 0

            async def get(self, key):
                self.seen += 1
                if self.seen == 1:
                    raise RuntimeError("first read only")
                return json.dumps({"order_of_play": {"1": {"state": "decided"}}})

        import app.tasks.redis_state as redis_state

        flaky = _FlakyOnce()
        # Through monkeypatch, not a bare assignment: a module-global swap that
        # is never restored leaks a broken Redis into whatever runs next, and
        # the failure surfaces in someone else's file.
        monkeypatch.setattr(
            redis_state, "get_async_redis_client", lambda: flaky
        )
        payload = await _espn_results("us-open")

        assert payload["scoreboard"] == "last_good"
        assert flaky.seen == 2, "the last-good key was never tried"


# ─────────────────────────────────────────────────────────────────────────────
# 2. THE 19:51:18Z EVENT — NEVER THE OPENING ROUND BECAUSE WE COULD NOT LOOK
# ─────────────────────────────────────────────────────────────────────────────


class TestTheSlateIsWithheldRatherThanRewound:
    """`_withheld_slate` is what stands between a raised read and 96 R128 rows.

    Shaped on the real captured body: the production slate carried 96 matches,
    `incoherent: 8`, `in_progress: 0`, `blend_linked: 0`.
    """

    CAPTURED = {
        "matches": [{"round": "R128"}] * 96,
        "count": 96,
        "incoherent": 8,
        "in_progress": 0,
        "order_of_play_listed": 0,
        "order_of_play_complete": True,
        # A slate-level flag that is NOT one of the counts. Today the real
        # slate has exactly one bool and `_withheld_slate` overwrites it, so
        # the bool exclusion is unobservable on the live shape — defence in
        # depth, asserted here on the contract rather than left until the next
        # flag is added and silently ships as `0`.
        "draw_released": True,
        "blend_linked": 0,
        "books_priced": 0,
        "scoreboard_pairings": 0,
        "price_state": "live",
        "dark_after_hours": 48.0,
        "scoreboard": SCOREBOARD_DEGRADED,
    }

    def test_not_one_match_survives(self):
        assert _withheld_slate(self.CAPTURED)["matches"] == []

    def test_every_count_goes_to_zero(self):
        out = _withheld_slate(self.CAPTURED)
        assert out["count"] == 0 and out["incoherent"] == 0
        assert out["order_of_play_listed"] == 0

    def test_the_reason_survives_so_the_page_is_not_silently_empty(self):
        out = _withheld_slate(self.CAPTURED)
        assert out["scoreboard"] == SCOREBOARD_DEGRADED
        assert out["withheld_reason"] == "scoreboard_read_failed"

    def test_the_key_set_cannot_drift_from_build_slates(self):
        """Built by emptying the real slate, never by writing a literal.

        A client reading a field a hand-written literal forgot would get its
        KeyError on exactly the unlucky request — the last place anybody would
        think to look.
        """
        out = _withheld_slate(self.CAPTURED)
        assert set(self.CAPTURED) <= set(out)

    def test_a_float_is_not_mistaken_for_a_count(self):
        """`dark_after_hours` is configuration, not a measurement of the
        scoreboard we failed to read. Zeroing it would claim the window closed."""
        assert _withheld_slate(self.CAPTURED)["dark_after_hours"] == 48.0

    def test_a_bool_is_not_zeroed_into_an_int(self):
        """`True` is an `int` in Python. A naive numeric sweep turns a flag into
        `0` and changes its type under the client — `false` becomes `0` in the
        JSON, which a strict client reads as a different thing entirely."""
        out = _withheld_slate(self.CAPTURED)
        assert out["draw_released"] is True
        assert out["order_of_play_complete"] is False


# ─────────────────────────────────────────────────────────────────────────────
# 3. THE 20:21:05Z EVENT — A DEGRADED BUILD IS SERVED ONCE, NEVER PERSISTED
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestADegradedBuildIsNotCached:
    """The half that bounds the reach.

    One bad build reached five readers over nineteen seconds because it was
    written to the 60s fragment cache. These assert it is not.
    """

    @staticmethod
    def _wire(monkeypatch, fail: str | None):
        """`_hub_payload` over a cache we can inspect and a build we control."""
        written: dict[str, Any] = {}

        async def _get(slug, group=tournaments.SECTION_FIRST):
            return None

        async def _set(slug, payload, group=tournaments.SECTION_FIRST):
            written[f"{slug}:{group}"] = payload

        async def _build(slug, spec, db, *, groups):
            if fail:
                _note_read_failure(fail)
            return {g: {"slug": slug, "built": g} for g in groups}

        monkeypatch.setattr(tournaments, "_cache_get", _get)
        monkeypatch.setattr(tournaments, "_cache_set", _set)
        monkeypatch.setattr(tournaments, "_build_sections", _build)
        return written

    async def test_a_healthy_build_is_cached(self, monkeypatch):
        """The control. Without it every assertion below passes on a route that
        simply never caches anything."""
        written = self._wire(monkeypatch, fail=None)
        await tournaments._hub_payload("us-open", {"season": "2026"}, None)
        assert written, "a healthy build stopped being cached"

    async def test_a_build_with_a_failed_data_read_is_not_cached(self, monkeypatch):
        written = self._wire(monkeypatch, fail="links")
        payload = await tournaments._hub_payload("us-open", {"season": "2026"}, None)
        assert payload, "the degraded build must still be SERVED"
        assert not written, "a degraded build was written to the cache"

    async def test_a_failed_results_read_is_not_cached_either(self, monkeypatch):
        written = self._wire(monkeypatch, fail="results:live")
        await tournaments._hub_payload("us-open", {"season": "2026"}, None)
        assert not written

    async def test_a_failed_CACHE_read_alone_still_caches(self, monkeypatch):
        """The distinction that keeps this from over-firing.

        A cache read that failed only cost us a rebuild. If the DATA reads were
        healthy the rebuild is correct and worth keeping — refusing to cache it
        would turn one bad Redis moment into a cold page for as long as the
        trouble lasted, which is a self-inflicted version of the outage.
        """
        written = self._wire(monkeypatch, fail="cache:first")
        await tournaments._hub_payload("us-open", {"season": "2026"}, None)
        assert written, "a healthy rebuild after a cache miss must still cache"


class TestTheLedgerIsRequestScoped:
    """A ContextVar that leaks would make one bad request poison the next."""

    def test_a_failure_outside_a_ledger_is_a_no_op(self):
        _note_read_failure("links")  # must not raise, must not accumulate
        with _read_failure_ledger() as failures:
            assert failures == []

    def test_the_ledger_is_reset_on_the_way_out(self):
        with _read_failure_ledger() as first:
            _note_read_failure("links")
            assert first == ["links"]
        with _read_failure_ledger() as second:
            assert second == []

    def test_a_nested_ledger_hands_the_outer_one_back(self):
        """The reset, tested where it is observable.

        Two sequential ledgers pass whether or not the token is reset — each
        `set` installs a fresh list either way. Only NESTING can see it: drop
        the `reset` and the inner ledger stays installed after its block, so
        every later failure in the same request lands in a list nobody reads.
        On a route this is one request's failures leaking into the next.
        """
        with _read_failure_ledger() as outer:
            with _read_failure_ledger() as inner:
                _note_read_failure("results:live")
                assert inner == ["results:live"]
            _note_read_failure("links")
            assert outer == ["links"], (
                "the inner ledger was never uninstalled — this failure went "
                f"nowhere; outer saw {outer}"
            )

    def test_an_exception_does_not_strand_the_ledger(self):
        # `try/except` rather than `pytest.raises`: CodeQL cannot see that the
        # context manager swallows nothing and reads everything after a
        # `pytest.raises` block as unreachable (py/unreachable-statement).
        raised = False
        try:
            with _read_failure_ledger():
                _note_read_failure("links")
                raise ValueError("boom")
        except ValueError:
            raised = True

        assert raised
        with _read_failure_ledger() as clean:
            assert clean == []
