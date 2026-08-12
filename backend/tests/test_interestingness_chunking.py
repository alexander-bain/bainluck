"""LAT-P042 (#1716): `precompute_interestingness` must stay memory-bounded.

WHAT THESE GUARD, AND WHY A REGRESSION HERE IS SILENT
------------------------------------------------------
The task was hard-killed on 6/6 production runs for months while the adherence
surface reported nothing useful, because a SIGKILLed worker runs no end handler:
zero successes, zero failures, zero durations. The measured cause was memory,
not time — 41,318 markets and 191,360 outcome ORM objects materialised at once
peaked at **515 MB RSS on a 512 MB dyno**, while the actual work takes ~15s
against a 300s limit.

Two properties fix that, and BOTH fail silently if undone:

1. **The pass is chunked.** Reverting to one unbounded query still passes every
   existing test — it just OOMs in production, where nothing records why.
2. **Each chunk flushes its own writes.** The old code buffered ~41K ``setex``
   calls into one pipeline executed on the last line, so a kill at 99% wrote
   NOTHING and looked exactly like a task that had never run. Restoring a
   single terminal flush is a one-line change with no local symptom.

So these assert the observable consequences — how many chunk queries are
issued, and that writes land per chunk rather than once at the end — not the
shape of the source.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.tasks.precompute_interestingness import (
    CHUNK_SIZE,
    SCORE_TTL_S,
    _precompute_interestingness,
    _score_chunk,
)


_NOW = datetime(2026, 8, 12, 19, 0, tzinfo=timezone.utc)


class FakeMarket:
    """Only the attributes the scorer actually reads."""

    def __init__(self, mid, *, outcomes=None, category=None, key=None, name="Market"):
        self.id = mid
        self.name = name
        self.llm_sport_category = category
        self.canonical_market_key = key
        self.volume_24h = 1000
        self.updated_at = None
        self.resolution_date = None
        self.market_metadata = {}
        self.status = "open"
        self.outcomes = outcomes if outcomes is not None else []


class FakeOutcome:
    def __init__(self, prob=None, change=None):
        self.current_probability = prob
        self.probability_change_24h = change


class FakePipeline:
    def __init__(self, recorder):
        self._recorder = recorder
        self._buffered = []

    def setex(self, key, ttl, value):
        self._buffered.append((key, ttl, value))

    def delete(self, key):
        self._buffered.append(("DEL", key, None))

    def execute(self):
        # Record the flush as a discrete event, with the writes it carried.
        self._recorder.flushes.append(list(self._buffered))
        self._recorder.written.extend(self._buffered)
        self._buffered = []


class FakeRedis:
    def __init__(self):
        self.flushes: list[list] = []
        self.written: list = []
        self.direct: dict = {}

    def get(self, key):
        # Title caches are pre-warmed so the task never takes its NETWORK
        # fallback inside a unit test.
        if key in ("tmdb:trending_titles", "music:charting_titles"):
            return json.dumps([])
        return self.direct.get(key)

    def setex(self, key, ttl, value):
        self.direct[key] = value

    def pipeline(self, transaction=False):
        return FakePipeline(self)


class _KeyRows:
    def __init__(self, keys):
        self._keys = keys

    def all(self):
        return [(k,) for k in self._keys]


class _CountRow:
    def __init__(self, key, cnt):
        self.canonical_market_key = key
        self.cnt = cnt


class _CountRows:
    def __init__(self, pairs):
        self._pairs = pairs

    def all(self):
        return [_CountRow(k, c) for k, c in self._pairs]


class _ScalarRows:
    def __init__(self, markets):
        self._markets = markets

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return self._markets


class FakeSession:
    """Replays a scripted sequence of results and counts expunges."""

    def __init__(self, script):
        self._script = list(script)
        self.executed = 0
        self.expunges = 0

    async def execute(self, _stmt):
        self.executed += 1
        if not self._script:
            raise AssertionError("more queries issued than the script provides")
        return self._script.pop(0)

    def expunge_all(self):
        self.expunges += 1


def _patch(monkeypatch, session, redis):
    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *exc):
            return False

    import app.tasks.base as base_mod
    import app.tasks.redis_state as redis_mod

    monkeypatch.setattr(base_mod, "get_task_session", lambda: _Ctx())
    monkeypatch.setattr(redis_mod, "get_redis_client", lambda *a, **k: redis)


class TestScoreChunkFlushesItsOwnWrites:
    def test_one_flush_per_chunk_carrying_every_market(self):
        r = FakeRedis()
        markets = [FakeMarket(i, outcomes=[FakeOutcome(0.6, 3.0)]) for i in range(5)]

        scored, errors = _score_chunk(
            markets, r=r, now=_NOW, source_counts={},
            trending_titles=set(), charting_titles=set(),
        )

        assert (scored, errors) == (5, 0)
        # Exactly one flush, and it happened before returning — that is what
        # makes a chunk's progress durable against a later SIGKILL.
        assert len(r.flushes) == 1
        assert len(r.flushes[0]) == 5
        assert {k for k, _, _ in r.written} == {f"interestingness:{i}" for i in range(5)}
        assert {ttl for _, ttl, _ in r.written} == {SCORE_TTL_S}

    def test_one_bad_market_does_not_wipe_its_chunk(self):
        """Gotcha #42: a throw inside a per-item loop must not empty the pass."""
        r = FakeRedis()
        good = [FakeMarket(1, outcomes=[FakeOutcome(0.5, 1.0)]),
                FakeMarket(2, outcomes=[FakeOutcome(0.5, 1.0)])]
        bad = FakeMarket(99)
        bad.outcomes = None  # iterating None raises inside the per-item try

        scored, errors = _score_chunk(
            [good[0], bad, good[1]], r=r, now=_NOW, source_counts={},
            trending_titles=set(), charting_titles=set(),
        )

        assert (scored, errors) == (2, 1)
        assert {k for k, _, _ in r.written} == {"interestingness:1", "interestingness:2"}


class TestPassIsChunked:
    @pytest.mark.asyncio
    async def test_walks_chunks_and_flushes_each_one(self, monkeypatch):
        r = FakeRedis()
        # Two full chunks then a partial one, so termination is exercised by a
        # short final page rather than only by an empty one.
        chunk_a = [FakeMarket(i, outcomes=[FakeOutcome(0.7, 2.0)]) for i in range(1, 4)]
        chunk_b = [FakeMarket(i, outcomes=[FakeOutcome(0.7, 2.0)]) for i in range(4, 7)]
        session = FakeSession([
            _KeyRows(["k1"]),
            _CountRows([("k1", 2)]),
            _ScalarRows(chunk_a),
            _ScalarRows(chunk_b),
            _ScalarRows([]),          # drained
        ])
        _patch(monkeypatch, session, r)

        out = await _precompute_interestingness()

        assert out["status"] == "ok"
        assert out["scored"] == 6
        assert out["errors"] == 0
        assert out["total_markets"] == 6
        assert out["chunks"] == 2
        # THE point of the fix: writes landed per chunk, not once at the end.
        assert len(r.flushes) == 2
        assert [len(f) for f in r.flushes] == [3, 3]
        # And each chunk's graph was released before the next was loaded.
        assert session.expunges == 2

    @pytest.mark.asyncio
    async def test_stops_without_scoring_when_nothing_is_eligible(self, monkeypatch):
        r = FakeRedis()
        session = FakeSession([_KeyRows([]), _ScalarRows([])])
        _patch(monkeypatch, session, r)

        out = await _precompute_interestingness()

        assert out["scored"] == 0
        assert out["chunks"] == 0
        # No canonical keys -> the count query is skipped entirely, so an empty
        # database costs two queries, not three.
        assert session.executed == 2
        assert r.flushes == []

    @pytest.mark.asyncio
    async def test_earlier_chunks_survive_a_later_failure(self, monkeypatch):
        """The property the old single-terminal-flush design could not have.

        A crash partway through must leave the completed chunks' scores in the
        cache. Under the old code the answer was zero keys — which is exactly
        why an empty cache and a never-run task were indistinguishable.
        """
        r = FakeRedis()
        chunk_a = [FakeMarket(i, outcomes=[FakeOutcome(0.7, 2.0)]) for i in range(1, 4)]
        session = FakeSession([
            _KeyRows([]),
            _ScalarRows(chunk_a),
            # next execute() raises: the script is exhausted
        ])
        _patch(monkeypatch, session, r)

        with pytest.raises(AssertionError):
            await _precompute_interestingness()

        assert len(r.flushes) == 1
        assert {k for k, _, _ in r.written} == {
            "interestingness:1", "interestingness:2", "interestingness:3"
        }


class TestChunkSizeIsBounded:
    def test_chunk_size_stays_inside_the_measured_safe_range(self):
        """Guards the one number the whole fix turns on.

        Sizes were measured end-to-end on a Standard-1X one-off — the same
        512 MB as `worker-background` — against production data:

            unbounded  515.0 MB peak, did not finish (swapping)
            2000       205.1 MB peak, 37.5s   <- OVER the ~195 MB child cap
            750        178.0 MB peak, 17.0s   <- chosen

        Deliberately asserted as a measured range rather than as
        `CHUNK_SIZE * bytes_per_market`, because that model is wrong: resident
        cost per market is ~44 KB at 750 but ~30 KB at 2000, so extrapolating
        linearly understates the peak at exactly the sizes that break. A future
        'tune' upward should re-measure, and should fail here first if it does
        not.
        """
        assert 0 < CHUNK_SIZE <= 1000, (
            "CHUNK_SIZE above 1000 is unmeasured; 2000 was measured at 205 MB, "
            "over the ~195 MB per-child cap. Re-measure before raising."
        )
