"""#10320 — category-page cards are re-priced by id.

On 2026-10-03, /politics showed "Will the U.S. and China announce an AI safety
agreement?" at 25%, a week after Kalshi had finalized every leg YES. 9 of the
page's 58 Kalshi cards had not been written for over 72 hours. No Kalshi price
path for an existing row reached a low-volume tier-2 category card: the
discovery poll is starved, the sweep's value arm is tier-1, and its served arm
only knows Discover/Sports page one.

These tests pin the three links of the repair:
1. the producer: each category precompute records the ids it just cached;
2. the signal: its own Redis key, aged per page, never raising, and separate
   from page one's served hash so CERT-1970's state machine does not change;
3. the consumer: `_refresh_stale_futures_prices` selects those ids on their own
   statement and clock, attributes them to their own arm, and prices them.
"""

from __future__ import annotations

import json

import pytest

from app.tasks import futures_price_refresh as fpr
from app.utils import category_served_markets as csm
from app.utils import feed_served_markets as fsm


class _FakePipe:
    def __init__(self, store):
        self.store = store
        self.ops = []

    def hset(self, key, field, value):
        self.ops.append(("hset", key, field, value))
        return self

    def expire(self, key, ttl):
        self.ops.append(("expire", key, ttl))
        return self

    def execute(self):
        for op in self.ops:
            if op[0] == "hset":
                self.store.hashes.setdefault(op[1], {})[op[2]] = op[3]
            else:
                self.store.ttls[op[1]] = op[2]
        return [True] * len(self.ops)


class _FakeRedis:
    def __init__(self):
        self.hashes: dict = {}
        self.ttls: dict = {}
        self.strings: dict = {}

    def pipeline(self, transaction=True):
        return _FakePipe(self)

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def set(self, key, value, ex=None):
        self.strings[key] = value
        return True


class _BrokenRedis:
    def pipeline(self, transaction=True):
        raise ConnectionError("redis down")

    def hgetall(self, key):
        raise ConnectionError("redis down")


# A /politics-shaped payload: a theme card, a nested related market, a
# cross-source pair (one id per venue), and fields that must NOT be collected.
POLITICS_PAYLOAD = {
    "total_markets": 2877,
    "themes": {
        "policy": {
            "markets": [
                {"q": "AI safety agreement?", "market_id": 61461672, "prob": 24.5},
                {"q": "Mifepristone?", "market_id": 25926800, "prob": 12.0},
            ]
        },
        "presidential": {
            "races": [
                {
                    "market_id": 9547589,
                    "related": [{"market_id": 61461672}, {"market_id": 55601616}],
                }
            ]
        },
    },
    "cross_source": [
        {"kalshi_market_id": 59693618, "poly_market_id": 59317063, "id": 7}
    ],
    "economy": {"main_market_id": 113012, "external_id": "KXFOO-26", "event_id": 99},
    "flags": {"market_id": True},  # bool is an int subclass; must not read as 1
    "junk": {"market_id": "62000000"},  # a string is not an id
}


# --- 1. the payload walk -------------------------------------------------------


class TestIdsInACategoryPayload:
    def test_collects_every_named_key_at_any_depth_deduped_in_order(self):
        assert csm.market_ids_in_category_payload(POLITICS_PAYLOAD) == [
            61461672,
            25926800,
            9547589,
            55601616,
            59693618,
            59317063,
            113012,
        ]

    def test_event_and_venue_ids_bools_and_strings_are_not_market_ids(self):
        ids = set(csm.market_ids_in_category_payload(POLITICS_PAYLOAD))
        assert 7 not in ids  # a bare `id`
        assert 99 not in ids  # an event id
        assert 1 not in ids  # `True`
        assert 62000000 not in ids  # a string

    def test_several_payloads_are_one_list(self):
        # The weather page publishes seven sub-endpoints as one page.
        ids = csm.market_ids_in_category_payload(
            {"cities": [{"market_id": 1}]}, [{"market_id": 2}, {"market_id": 1}], None
        )
        assert ids == [1, 2]

    def test_garbage_yields_nothing(self):
        assert csm.market_ids_in_category_payload(None, "x", 3, [None]) == []


# --- 2. the signal -------------------------------------------------------------


class TestTheCategorySignal:
    def test_round_trip_and_replace_not_merge(self, monkeypatch):
        rc = _FakeRedis()
        csm.record_category_served_market_ids(rc, "politics", [3, 1, 2])
        csm.record_category_served_market_ids(rc, "politics", [5])
        csm.record_category_served_market_ids(rc, "economics", [1, 9])
        assert rc.ttls[csm.CATEGORY_SERVED_MARKET_IDS_KEY] == (
            csm.CATEGORY_SERVED_MARKET_IDS_TTL_S
        )
        monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda **kw: rc)
        got = csm.category_served_market_ids()
        # politics' second write REPLACED its first: 3 and 2 are gone.
        assert got.ids == [1, 5, 9]
        assert (got.pages, got.stale_pages, got.unreadable_pages) == (2, 0, 0)
        assert got.read_ok is True

    def test_a_page_past_the_age_bound_is_dropped_and_counted(self, monkeypatch):
        anchor = 1_791_000_000.0
        rc = _FakeRedis()
        rc.hashes[csm.CATEGORY_SERVED_MARKET_IDS_KEY] = {
            "politics": json.dumps({"at": anchor - 60, "ids": [1]}),
            "weather": json.dumps(
                {"at": anchor - csm.CATEGORY_SERVED_MAX_AGE_S - 1, "ids": [2]}
            ),
            "economics": "{not json",
            "entertainment": json.dumps({"ids": [3]}),  # no stamp: cannot age out
        }
        monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda **kw: rc)
        got = csm.category_served_market_ids(now=anchor)
        assert got.ids == [1]
        assert (got.pages, got.stale_pages, got.unreadable_pages) == (1, 1, 2)

    def test_the_age_bound_can_fire_before_the_key_expires(self):
        assert csm.CATEGORY_SERVED_MAX_AGE_S < csm.CATEGORY_SERVED_MARKET_IDS_TTL_S

    def test_a_failed_read_is_reported_not_silent(self, monkeypatch):
        monkeypatch.setattr(
            "app.tasks.redis_state.get_redis_client", lambda **kw: _BrokenRedis()
        )
        got = csm.category_served_market_ids()
        assert got.ids == [] and got.read_ok is False

    def test_a_failed_write_never_raises(self):
        csm.record_category_served_market_ids(_BrokenRedis(), "politics", [1])

    def test_a_runaway_page_is_capped(self):
        rc = _FakeRedis()
        n = csm.MAX_CATEGORY_SERVED_IDS_PER_PAGE + 25
        csm.record_category_served_market_ids(rc, "politics", list(range(1, n + 1)))
        stored = json.loads(rc.hashes[csm.CATEGORY_SERVED_MARKET_IDS_KEY]["politics"])
        assert len(stored["ids"]) == csm.MAX_CATEGORY_SERVED_IDS_PER_PAGE

    def test_page_one_served_hash_is_untouched(self, monkeypatch):
        """CERT-1970: a category entry in page one's hash would hold its state at
        `fresh` while every Discover shape had stopped warming."""
        assert csm.CATEGORY_SERVED_MARKET_IDS_KEY != fsm.SERVED_MARKET_IDS_KEY
        rc = _FakeRedis()
        csm.record_category_served_market_ids(rc, "politics", [1, 2])
        assert fsm.SERVED_MARKET_IDS_KEY not in rc.hashes
        # And page one's reader, over the same store, still sees no shape.
        monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda **kw: rc)
        rc.get = lambda key: None
        rc.expire = lambda *a, **kw: True
        real_set = rc.set

        def _set(key, value, ex=None, nx=False):
            return real_set(key, value, ex=ex)

        rc.set = _set
        sig = fsm.served_signal(now=1_791_000_000.0)
        assert sig.shapes == 0 and sig.ids == []


# --- 3. the producer -----------------------------------------------------------


def _pcp_module():
    # `from app.tasks import precompute_category_pages` resolves to the Celery
    # TASK of that name, which shadows the module on the package.
    import importlib

    return importlib.import_module("app.tasks.precompute_category_pages")


class TestThePrecomputeRecordsWhatItCached:
    @pytest.mark.asyncio
    async def test_politics_records_the_ids_of_the_payload_it_cached(self, monkeypatch):
        import contextlib

        pcp = _pcp_module()

        rc = _FakeRedis()

        @contextlib.asynccontextmanager
        async def _session(**_kw):
            yield object()

        async def _get_politics(db, stage_ms=None):
            return POLITICS_PAYLOAD

        monkeypatch.setattr("app.tasks.base.get_task_session", _session)
        monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda: rc)
        monkeypatch.setattr("app.routes.politics.get_politics", _get_politics)

        await pcp._precompute_politics()

        assert f"{pcp.CACHE_PREFIX}politics" in rc.strings
        entry = json.loads(rc.hashes[csm.CATEGORY_SERVED_MARKET_IDS_KEY]["politics"])
        assert entry["ids"] == csm.market_ids_in_category_payload(POLITICS_PAYLOAD)
        assert 61461672 in entry["ids"]

    @pytest.mark.asyncio
    async def test_a_failed_record_does_not_cost_the_page_its_cache(self, monkeypatch):
        import contextlib

        pcp = _pcp_module()

        rc = _FakeRedis()
        rc.pipeline = lambda transaction=True: (_ for _ in ()).throw(
            ConnectionError("pipeline down")
        )

        @contextlib.asynccontextmanager
        async def _session(**_kw):
            yield object()

        async def _get_economics(db):
            return {"total_markets": 3, "rows": [{"market_id": 113012}]}

        monkeypatch.setattr("app.tasks.base.get_task_session", _session)
        monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda: rc)
        monkeypatch.setattr("app.routes.economics.get_economics", _get_economics)

        assert await pcp._precompute_economics() == 3
        assert f"{pcp.CACHE_PREFIX}economics" in rc.strings
        assert f"{pcp.CACHE_PREFIX}economics:stale" in rc.strings

    def test_every_category_section_records(self):
        """All four category builders call the recorder, not just the one tested
        end to end above."""
        import inspect

        pcp = _pcp_module()

        for fn, page in (
            (pcp._precompute_politics, '"politics"'),
            (pcp._precompute_entertainment, '"entertainment"'),
            (pcp._precompute_economics, '"economics"'),
            (pcp._precompute_weather, '"weather"'),
        ):
            src = inspect.getsource(fn)
            assert "_record_rendered_market_ids(" in src, fn.__name__
            assert page in src, fn.__name__


# --- 4. the consumer -----------------------------------------------------------

from tests.test_futures_price_refresh import _RunHarness  # noqa: E402

#: A Polymarket row so the harness's existing price fake can price it. The arm is
#: venue-agnostic; the specimen that matters in production is Kalshi.
CATEGORY_ROW = (61461672, "polymarket", "0xabc", 3_456, "45915", None)


class _CategoryHarness(_RunHarness):
    def __init__(self, *, category_ids, served_ids=()):
        from app.utils.feed_served_markets import SERVED_FRESH, ServedSignal

        super().__init__(
            signal=ServedSignal(
                state=SERVED_FRESH, ids=list(served_ids), shapes=1 if served_ids else 0
            ),
            class_rows=[],
        )
        self.category_ids = list(category_ids)
        self.served_ids = list(served_ids)
        self.category_params: list[dict] = []

    def _category_served(self, now=None):
        return csm.CategoryServed(ids=self.category_ids, pages=1)

    class _Session(_RunHarness._Session):
        async def execute(self, statement, params=None):
            if statement is fpr._CATEGORY_PAGE_CANDIDATE_SQL:
                self.outer.category_params.append(dict(params))
                ids = set(params["market_ids"])
                return _RunHarness._Result([r for r in [CATEGORY_ROW] if r[0] in ids])
            if statement is fpr._SERVED_CANDIDATE_SQL:
                ids = set(params["market_ids"])
                return _RunHarness._Result([r for r in [CATEGORY_ROW] if r[0] in ids])
            return await super().execute(statement, params)


class TestTheSweepPricesCategoryCards:
    @pytest.mark.asyncio
    async def test_a_category_card_is_selected_attributed_and_priced(self, monkeypatch):
        harness = _CategoryHarness(category_ids=[61461672])
        stats = await harness.run(monkeypatch)

        assert stats["category_page_known"] == 1
        assert stats["category_page_read_ok"] is True
        assert stats["category_page_candidates"] == 1
        assert stats["category_page_attempted"] == 1
        assert stats["category_page_priced"] == 1
        assert stats["markets_priced"] == 1
        assert harness.snapshot_probabilities, "the card was selected but never priced"

    @pytest.mark.asyncio
    async def test_the_arm_runs_on_its_own_clock(self, monkeypatch):
        harness = _CategoryHarness(category_ids=[61461672])
        await harness.run(monkeypatch)
        assert harness.category_params == [
            {
                "market_ids": [61461672],
                "stale_minutes": fpr.CATEGORY_PAGE_REFRESH_MINUTES,
            }
        ]
        assert fpr.CATEGORY_PAGE_REFRESH_MINUTES != fpr.SERVED_REFRESH_MINUTES

    @pytest.mark.asyncio
    async def test_a_card_page_one_also_renders_stays_served(self, monkeypatch):
        harness = _CategoryHarness(category_ids=[61461672], served_ids=[61461672])
        stats = await harness.run(monkeypatch)
        assert stats["served_candidates"] == 1
        assert stats["category_page_candidates"] == 0
        assert stats["markets_attempted"] == 1  # priced once, not twice

    @pytest.mark.asyncio
    async def test_no_category_ids_is_no_statement_and_a_zero_arm(self, monkeypatch):
        harness = _CategoryHarness(category_ids=[])
        stats = await harness.run(monkeypatch)
        assert harness.category_params == []
        assert stats["category_page_known"] == 0
        assert stats["category_page_candidates"] == 0

    def test_the_arm_is_a_priority_arm(self):
        (market,) = fpr._rows_to_markets([CATEGORY_ROW], arm=fpr._ARM_CATEGORY_PAGE)
        assert market["priority"] is True
        assert market["served"] is False and market["registered"] is False

    def test_the_arm_uses_the_shared_by_id_statement(self):
        """Same liveness bounds as the other identity arms: a separate object, the
        same string, so the arms cannot drift on what 'reachable by id' means."""
        assert fpr._CATEGORY_PAGE_CANDIDATE_SQL is not fpr._SERVED_CANDIDATE_SQL
        assert str(fpr._CATEGORY_PAGE_CANDIDATE_SQL) == str(fpr._SERVED_CANDIDATE_SQL)
