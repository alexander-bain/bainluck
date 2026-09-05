"""#3315 — the page-one signal that lets the price sweep reach what a reader sees.

## The class this file exists to catch

Not "the walker has a bug". The one that produced #3315: **the only rail that can
re-price a market the discovery polls cannot reach selected on a proxy for
importance instead of on importance itself.** Measured on production 2026-09-05,
all seven Polymarket cards on Discover page one were `market_tier = 2` and
therefore outside the sweep's predicate permanently — "Brazil Presidential
Election" rendered Flávio Bolsonaro at 26.2% against Polymarket's own 39.9%, off
rows last written 1,109 hours earlier, on $114M of volume. Nothing was red. A
coverage gap cannot be seen by a scheduling instrument.

So the properties pinned here are the ones that decide whether the signal
*arrives*, because every one of them fails silently:

1. The walker finds ids in all three places a card hides them. Six of twenty
   page-one cards were bundles; a top-level-only walk misses most of the page.
2. The writer REPLACES a shape's list. A merge would turn "what page one is
   showing" into "what page one has ever shown", which is the volume floor with
   extra steps.
3. The reader is total: a Redis outage, a corrupt value or a missing key costs
   the sweep its page-one arm and never the run.
4. The pre-warmer actually calls it, for every shape, and only for `offset = 0`
   shapes — so "page one" stays a true description of the set.
"""

import json

import pytest

from app.utils import feed_served_markets as fsm


class _FakeRedis:
    """Just enough Redis, and it records what it was asked to do."""

    def __init__(self, *, raise_on=None):
        self.hash: dict[str, str] = {}
        self.expires: list[int] = []
        self.raise_on = raise_on or set()

    def pipeline(self, transaction=False):
        self.transaction = transaction
        return self

    def hset(self, key, field, value):
        if "hset" in self.raise_on:
            raise RuntimeError("redis down")
        self.hash[field] = value
        return self

    def expire(self, key, ttl):
        self.expires.append(ttl)
        return self

    def execute(self):
        return []

    def hgetall(self, key):
        if "hgetall" in self.raise_on:
            raise RuntimeError("redis down")
        return {k.encode(): v.encode() for k, v in self.hash.items()}


def _futures(mid, name="card"):
    return {"type": "futures", "data": {"id": mid, "name": name}}


class TestTheWalkerFindsEveryCard:
    def test_it_reads_top_level_bundle_members_and_bundle_children(self):
        """Three hiding places, and missing one loses a whole card type.

        Shaped from the real Discover page-one payload of 2026-09-05: 20 items,
        11 top-level `futures` cards and 6 bundles, one of which carried
        `member_ids: [109435, 113503]` AND nested items of its own.
        """
        payload = {
            "items": [
                _futures(108326, "2028 U.S. Presidential Election winner?"),
                {
                    "type": "bundle",
                    "data": {
                        "id": "theme:story:aliens_disclosure",
                        "member_ids": [109435, 113503],
                        "items": [_futures(109435), _futures(113503)],
                    },
                },
                {
                    "type": "bundle",
                    "data": {"items": [_futures(112996, "Brazil Presidential")]},
                },
            ]
        }
        got = fsm.market_ids_in_feed_payload(payload)
        assert set(got) == {108326, 109435, 113503, 112996}
        # Deduped, and the first sighting keeps its position.
        assert got.count(109435) == 1
        assert got[0] == 108326

    def test_event_and_concept_cards_contribute_nothing(self):
        """Their ids are EVENT ids. Passing one to the price sweep selects the

        wrong row or no row, and no row is the failure that looks like success —
        the served arm would report a candidate it never had.
        """
        payload = {
            "items": [
                {"type": "event", "data": {"id": 555}},
                {"type": "concept", "data": {"id": 556, "key": "event:cycling:x"}},
                {"type": "tournament", "data": {"id": 557}},
                _futures(558),
            ]
        }
        assert fsm.market_ids_in_feed_payload(payload) == [558]

    def test_true_is_not_collected_as_market_one(self):
        """`bool` is an `int` subclass — the same trap the tournament register hit."""
        payload = {"items": [{"type": "futures", "data": {"id": True}}]}
        assert fsm.market_ids_in_feed_payload(payload) == []

    @pytest.mark.parametrize(
        "payload",
        [None, {}, {"items": None}, {"items": "nope"}, {"items": [None, 3, "x"]}],
    )
    def test_a_shape_it_does_not_understand_yields_nothing_and_never_raises(
        self, payload
    ):
        """This runs inside the pre-warm publish path, which must never fail here."""
        assert fsm.market_ids_in_feed_payload(payload) == []


class TestTheWriterReplacesRatherThanAccumulates:
    def test_a_second_warm_replaces_the_shapes_list(self):
        """A merge would make this "ever shown", which is not a page-one signal.

        The whole value of the arm is that it tracks rotation: a card that leaves
        page one must stop being re-priced on its account, or within a day the
        set is every market the ranker has ever surfaced and the sweep is back to
        guessing.
        """
        rc = _FakeRedis()
        fsm.record_served_market_ids(rc, "discover", [1, 2, 3])
        fsm.record_served_market_ids(rc, "discover", [4])
        assert json.loads(rc.hash["discover"]) == [4]

    def test_shapes_do_not_overwrite_each_other(self):
        rc = _FakeRedis()
        fsm.record_served_market_ids(rc, "discover", [1])
        fsm.record_served_market_ids(rc, "sports", [2])
        assert json.loads(rc.hash["discover"]) == [1]
        assert json.loads(rc.hash["sports"]) == [2]

    def test_an_empty_payload_writes_an_empty_list_rather_than_skipping(self):
        """Otherwise a shape's last interesting answer stands for six hours."""
        rc = _FakeRedis()
        fsm.record_served_market_ids(rc, "sports", [7])
        fsm.record_served_market_ids(rc, "sports", [])
        assert json.loads(rc.hash["sports"]) == []

    def test_the_ttl_is_refreshed_on_every_write_including_the_empty_one(self):
        """The expiry tracks the RAIL's liveness, not the last interesting payload."""
        rc = _FakeRedis()
        fsm.record_served_market_ids(rc, "sports", [])
        assert rc.expires == [fsm.SERVED_MARKET_IDS_TTL_S]

    def test_the_ttl_outlives_the_consumers_period_not_the_producers(self):
        """Sized against the hourly sweep, not the 40-120s warm.

        A TTL near the producer's period expires under any bad half hour and the
        sweep silently reverts to pre-#3315 coverage — the failure this arm
        exists to end, arriving through its own plumbing.
        """
        assert fsm.SERVED_MARKET_IDS_TTL_S >= 6 * 3600

    def test_a_runaway_payload_is_capped_and_the_cap_is_not_silent(self, caplog):
        rc = _FakeRedis()
        with caplog.at_level("WARNING"):
            fsm.record_served_market_ids(rc, "big", list(range(1, 2000)))
        stored = json.loads(rc.hash["big"])
        assert len(stored) == fsm.MAX_SERVED_IDS_PER_SHAPE
        assert "capping" in caplog.text

    def test_a_redis_failure_costs_the_signal_and_never_the_warm(self):
        rc = _FakeRedis(raise_on={"hset"})
        fsm.record_served_market_ids(rc, "discover", [1])  # must not raise
        assert rc.hash == {}


class TestTheReaderIsTotal:
    def _reader_over(self, rc, monkeypatch):
        monkeypatch.setattr(
            "app.tasks.redis_state.get_redis_client", lambda **kw: rc
        )
        return fsm.served_market_ids()

    def test_it_unions_every_shape_and_sorts(self, monkeypatch):
        rc = _FakeRedis()
        fsm.record_served_market_ids(rc, "discover", [9, 3])
        fsm.record_served_market_ids(rc, "sports", [3, 1])
        assert self._reader_over(rc, monkeypatch) == [1, 3, 9]

    def test_a_redis_outage_reads_empty_rather_than_raising(self, monkeypatch):
        rc = _FakeRedis(raise_on={"hgetall"})
        assert self._reader_over(rc, monkeypatch) == []

    def test_a_corrupt_value_drops_that_shape_and_keeps_the_others(
        self, monkeypatch
    ):
        """One bad item must never wipe the pass (gotcha #42)."""
        rc = _FakeRedis()
        fsm.record_served_market_ids(rc, "discover", [5])
        rc.hash["sports"] = "{not json"
        rc.hash["native"] = json.dumps({"nope": 1})
        assert self._reader_over(rc, monkeypatch) == [5]

    def test_a_non_integer_id_is_refused(self, monkeypatch):
        rc = _FakeRedis()
        rc.hash["discover"] = json.dumps([1, "2", None, True, -4, 0, 6])
        assert self._reader_over(rc, monkeypatch) == [1, 6]


class TestThePreWarmerPublishesWhatItRendered:
    """The producer half. Without this call the arm is an empty set forever."""

    def test_the_warmer_records_the_ids_of_the_payload_it_published(self):
        # Read off disk, not via `inspect`: `app.tasks.precompute_category_pages`
        # is reached through a Celery module proxy that does not expose module
        # attributes, and the proxy's AttributeError would read as "the call is
        # missing" rather than "the test cannot see it".
        from pathlib import Path

        import app.tasks.futures_price_refresh as _fpr

        whole = (
            Path(_fpr.__file__).parent / "precompute_category_pages.py"
        ).read_text()
        src = whole[whole.index("async def _prewarm_feed_shape") :]
        src = src[: src.index("\nasync def ", 1)]
        call = (
            "record_served_market_ids(rc, label, market_ids_in_feed_payload(payload))"
        )
        assert call in src
        # AFTER the publish, so a shape whose build was degraded, empty or
        # keyless — all three return early above — never contributes ids. A set
        # written before the quality gates would name markets no reader was
        # served. Indexed on the whole CALL, not on the bare name: the import at
        # the top of the function carries the name too, and comparing against
        # that would make this assertion pass wherever the call sits.
        assert src.index("rc.setex(cache_key") < src.index(call)

    def test_every_warmed_shape_is_page_one(self):
        """"Page one" has to stay a true description of this set.

        The arm re-prices its members at any tier and any volume, so enrolling a
        deep-offset shape would quietly widen an unbounded-by-value population.
        """
        from app.tasks.precompute_category_pages import FEED_PREWARM_SHAPES

        assert FEED_PREWARM_SHAPES
        assert all(s["offset"] == 0 for s in FEED_PREWARM_SHAPES)

    def test_the_sweep_reads_the_same_key_the_warmer_writes(self):
        """One key, named once. Two spellings is a signal that publishes to nobody."""
        rc = _FakeRedis()
        fsm.record_served_market_ids(rc, "discover", [11])
        assert set(rc.hash) == {"discover"}
        assert fsm.SERVED_MARKET_IDS_KEY.startswith("bainluck:")
