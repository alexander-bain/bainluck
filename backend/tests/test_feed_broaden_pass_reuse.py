"""Queue 305 (#1475): the #1090 thin-pool broaden pass must not re-pay the cold
``futures.market_load`` it already paid in the primary pass.

Cold Discover builds in an off-season lull surface fewer than
``_THIN_FUTURES_POOL_FLOOR`` (100) futures, so the parent feed route runs
``_score_futures`` a SECOND time with relaxed staleness windows to avoid a
premature "all caught up" (#1090). The candidate base is config-independent, so
that second pass loads the IDENTICAL candidate markets — re-issuing the
~494ms three-round-trip ``market_load`` SELECT (parent + outcomes selectin +
sport selectin) for rows already hydrated in the primary pass. That reload is
uninstrumented (the broaden call passes no ``timing_records``), which is why it
hid in the 1369ms cold ``futures`` phase behind the named 494ms ``market_load``.

The fix threads the primary pass's already-ordered, already-hydrated markets
(plus its external-curator recall IDs, which drive the recall scoring bonus)
into the broaden pass via ``capture_base`` (primary out) → ``preloaded_base``
(broaden in). When a base is preloaded, ``_score_futures`` skips
``get_candidate_base`` AND ``market_load`` and re-scores the same rows under the
relaxed config. Membership, order, and per-market scoring are unchanged — the
relaxed pass still runs its scoring loop (that is the whole point of #1090); only
the redundant serial DB load is removed.

These fixtures pin:
1. A preloaded broaden pass issues ZERO market-load SQL and returns IDENTICAL
   scored IDs/order to a fresh reload under the same config (timing + equivalence).
2. The external-curator recall IDs survive the reuse (recall scoring identical).
3. An empty / missing preloaded base degrades safely to an empty result.
4. The per-item poison guard (gotcha #42) still holds on the reused rows.
5. The parent route actually wires capture → preloaded (source guard).
"""

import inspect
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.routes.feed as feed_mod
from app.routes.feed import _score_futures
from app.utils.personalization import PersonalizationContext

NOW = datetime(2026, 8, 3, 12, 0, 0, tzinfo=timezone.utc)


class _Outcome:
    def __init__(self, id, name, current_probability, *, change=0.0, opening=None):
        self.id = id
        self.name = name
        self.current_probability = current_probability
        self.probability_change_24h = change
        self.opening_probability = opening
        self.rank = None
        self.rank_change_24h = None
        self.team_id = None
        self.calibration_probability = None


class _Market:
    """A real object (not MagicMock) so ``__dict__.get(...)`` reads work."""

    _PROFILES = {
        1: ("Who will win the US Presidential election?", "politics"),
        2: ("Will the Fed cut rates in December?", "economics"),
        3: ("Who wins Best Picture at the Oscars?", "entertainment"),
        4: ("Who wins the Premier League?", "sports"),
    }

    def __init__(self, id, *, poison=False):
        name, category = self._PROFILES.get(id, (f"Test market {id}?", "politics"))
        self.id = id
        self.name = name
        self.source = "polymarket"
        self.external_id = f"poly-{id}"
        self.sport_id = None
        self.sport = None
        self.category = category
        self.llm_sport_category = category
        self.market_tier = 1
        # None short-circuits canonical source counts -> no extra SQL, so the only
        # SQL a fresh pass issues is the single market-load SELECT.
        self.canonical_market_key = None
        self.group_id = None
        self.group_type = None
        self.image_url = None
        self.hook_description = None
        self.hook_generated_at = None
        self.hook_leader_at_generation = None
        self.market_metadata = {}
        self.curation_score_adj = 0
        self.volume_24h = 250000
        self.updated_at = NOW
        self.commence_time = NOW - timedelta(days=1)
        self.resolution_date = NOW + timedelta(days=30)
        self.status = "open"
        self.created_at = NOW - timedelta(days=10)
        self.llm_league = None
        self.llm_gender = None
        self.llm_level = None
        top_prob = "not-a-number" if poison else 0.55
        self.outcomes = [
            _Outcome(10 + id, "Candidate A", top_prob, change=0.12, opening=0.43),
            _Outcome(20 + id, "Candidate B", 0.45, change=-0.12, opening=0.57),
        ]


class _CountingDB:
    """Session that hands back the given markets on the market-load SELECT and
    counts how many market-load SELECTs were issued."""

    def __init__(self, markets):
        self._markets = markets
        self.market_load_calls = 0
        self.executed: list = []

    async def execute(self, query):
        self.executed.append(query)
        compiled = str(query).lower()
        r = MagicMock()
        scalars = MagicMock()
        if "from futures_markets" in compiled and "count(" not in compiled:
            self.market_load_calls += 1
            unique = MagicMock()
            unique.all.return_value = self._markets
            scalars.unique.return_value = unique
            scalars.all.return_value = [m.id for m in self._markets]
        else:
            scalars.all.return_value = []
            scalars.unique.return_value = scalars
        r.scalars.return_value = scalars
        r.all.return_value = []
        return r

    async def rollback(self):
        return None


def _base_hit(monkeypatch, market_ids, curator_ids):
    """Force ``get_candidate_base`` to a fresh hit so ``_score_futures`` skips the
    candidate-pool SQL and goes straight to market_load."""
    from app.utils import candidate_base as cb_mod

    async def _fake_get_base(now, sport_filter, static_tag_filter, *, stages=None):
        return (list(market_ids), "fresh", list(curator_ids))

    monkeypatch.setattr(cb_mod, "get_candidate_base", _fake_get_base)


def _no_redis():
    """Interestingness blend degrades to no-blend without a Redis dependency."""
    return patch(
        "app.utils.request_cache.get_shared_async_redis",
        new=AsyncMock(side_effect=Exception("no redis in test")),
    )


def _ids(items):
    return [i["data"]["id"] for i in items if i["type"] == "futures"]


@pytest.mark.asyncio
async def test_preloaded_reuse_issues_zero_market_load_sql_and_identical_output(
    monkeypatch,
):
    """The core timing + equivalence guard.

    A fresh pass issues exactly one market-load SELECT; a preloaded broaden pass
    issues ZERO — while returning the identical scored IDs in the identical order.
    """
    markets = [_Market(i) for i in (1, 2, 3, 4)]
    curator_ids = {2, 4}
    ctx = PersonalizationContext()

    with _no_redis():
        # Fresh primary pass: fills capture_base, issues one market-load SELECT.
        _base_hit(monkeypatch, [m.id for m in markets], curator_ids)
        fresh_db = _CountingDB(markets)
        capture: dict = {}
        fresh_items = await _score_futures(
            fresh_db, NOW, None, ctx, capture_base=capture
        )
        fresh_ids = _ids(fresh_items)

        assert fresh_db.market_load_calls == 1, (
            "a fresh pass must issue exactly one market-load SELECT"
        )
        assert capture.get("markets"), "primary pass must capture its loaded markets"
        assert fresh_ids, "sanity: the fresh pass should score at least one market"

        # Broaden pass reusing the captured base: NO market-load SELECT, identical
        # scored output.
        reuse_db = _CountingDB(markets)
        reuse_items = await _score_futures(
            reuse_db, NOW, None, ctx, preloaded_base=capture
        )
        reuse_ids = _ids(reuse_items)

    assert reuse_db.market_load_calls == 0, (
        "a preloaded broaden pass must NOT re-issue the market-load SELECT — "
        f"issued {reuse_db.market_load_calls}"
    )
    assert reuse_ids == fresh_ids, (
        "reuse must produce byte-identical scored IDs/order to a fresh reload: "
        f"{reuse_ids} != {fresh_ids}"
    )


@pytest.mark.asyncio
async def test_preloaded_reuse_preserves_external_curator_recall_ids(monkeypatch):
    """The recall scoring bonus keys on external_curator_recall_ids; the reuse must
    carry them so scoring is identical to a fresh reload with the same base."""
    markets = [_Market(i) for i in (1, 2, 3, 4)]
    curator_ids = {2, 4}
    ctx = PersonalizationContext()

    with _no_redis():
        _base_hit(monkeypatch, [m.id for m in markets], curator_ids)
        fresh_db = _CountingDB(markets)
        capture: dict = {}
        fresh_items = await _score_futures(
            fresh_db, NOW, None, ctx, capture_base=capture
        )

        assert set(capture.get("curator_ids") or ()) == curator_ids, (
            "capture must record the external-curator recall IDs verbatim"
        )

        reuse_db = _CountingDB(markets)
        reuse_items = await _score_futures(
            reuse_db, NOW, None, ctx, preloaded_base=capture
        )

    # Same recall IDs -> same recall scoring -> identical scored set.
    assert _ids(reuse_items) == _ids(fresh_items)


@pytest.mark.asyncio
async def test_preloaded_empty_base_returns_empty(monkeypatch):
    """A preloaded base with no markets degrades to an empty result and issues no
    market-load SELECT (the broaden pass never fires on an empty primary, but the
    reuse path must be safe anyway)."""
    ctx = PersonalizationContext()
    with _no_redis():
        reuse_db = _CountingDB([])
        items = await _score_futures(
            reuse_db, NOW, None, ctx, preloaded_base={"markets": [], "curator_ids": []}
        )
    assert items == []
    assert reuse_db.market_load_calls == 0


@pytest.mark.asyncio
async def test_poison_market_in_preloaded_set_is_skipped(monkeypatch):
    """gotcha #42: the per-item guard must still hold on reused rows — one poison
    market cannot wipe the reused pass."""
    good = _Market(1)
    poison = _Market(2, poison=True)
    other = _Market(3)
    ctx = PersonalizationContext()
    with _no_redis():
        reuse_db = _CountingDB([poison, good, other])
        items = await _score_futures(
            reuse_db,
            NOW,
            None,
            ctx,
            preloaded_base={"markets": [poison, good, other], "curator_ids": []},
        )
    ids = set(_ids(items))
    assert 1 in ids and 3 in ids, f"healthy reused markets dropped by poison: {ids}"
    assert 2 not in ids, "poison market should be skipped, not scored"
    assert reuse_db.market_load_calls == 0


def test_broaden_pass_wiring_threads_capture_into_preloaded():
    """Source guard: the parent feed route must capture the primary pass's base and
    hand it to the broaden pass, or the reuse never happens in production."""
    src = inspect.getsource(feed_mod)
    # The primary futures call captures its base (``capture_base=`` only appears at
    # the primary call site; the signature uses ``capture_base:`` and the body uses
    # ``capture_base[``).
    assert "capture_base=" in src, "primary _score_futures call must pass capture_base="
    # The #1090 broaden re-score reuses it (``preloaded_base=`` only appears at the
    # broaden call site).
    assert "preloaded_base=" in src, "broaden _score_futures call must pass preloaded_base="
    # Ordering: the primary call (capture) must precede the broaden call (reuse).
    assert src.index("capture_base=") < src.index("preloaded_base="), (
        "the capturing primary call must precede the reusing broaden call"
    )
