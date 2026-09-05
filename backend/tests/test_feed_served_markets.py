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
        self.strings: dict[str, str] = {}
        self.expires: list[int] = []
        self.setex_calls: list[tuple] = []
        self.set_calls: list[tuple] = []
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

    def get(self, key):
        if "get" in self.raise_on:
            raise RuntimeError("redis down")
        v = self.strings.get(key)
        return v.encode() if v is not None else None

    def setex(self, key, ttl, value):
        if "setex" in self.raise_on:
            raise RuntimeError("redis down")
        self.setex_calls.append((key, ttl, value))
        self.strings[key] = str(value)

    def set(self, key, value, nx=False, ex=None):
        if "set" in self.raise_on:
            raise RuntimeError("redis down")
        self.set_calls.append((key, value, nx, ex))
        if nx and key in self.strings:
            return None
        self.strings[key] = str(value)
        return True

    def delete(self, *keys):
        for k in keys:
            self.strings.pop(k, None)


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
    def test_every_entry_carries_its_own_write_time(self):
        """The stamp the per-shape age bound is built on. Key-wide TTL cannot
        retire one shape while its siblings keep the key alive."""
        rc = _FakeRedis()
        fsm.record_served_market_ids(rc, "discover", [1])
        entry = json.loads(rc.hash["discover"])
        assert isinstance(entry["at"], int) and entry["at"] > 0

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
        assert json.loads(rc.hash["discover"])["ids"] == [4]

    def test_shapes_do_not_overwrite_each_other(self):
        rc = _FakeRedis()
        fsm.record_served_market_ids(rc, "discover", [1])
        fsm.record_served_market_ids(rc, "sports", [2])
        assert json.loads(rc.hash["discover"])["ids"] == [1]
        assert json.loads(rc.hash["sports"])["ids"] == [2]

    def test_an_empty_payload_writes_an_empty_list_rather_than_skipping(self):
        """Otherwise a shape's last interesting answer stands for six hours."""
        rc = _FakeRedis()
        fsm.record_served_market_ids(rc, "sports", [7])
        fsm.record_served_market_ids(rc, "sports", [])
        assert json.loads(rc.hash["sports"])["ids"] == []

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
        stored = json.loads(rc.hash["big"])["ids"]
        assert len(stored) == fsm.MAX_SERVED_IDS_PER_SHAPE
        assert "capping" in caplog.text

    def test_a_redis_failure_costs_the_signal_and_never_the_warm(self):
        rc = _FakeRedis(raise_on={"hset"})
        fsm.record_served_market_ids(rc, "discover", [1])  # must not raise
        assert rc.hash == {}


_NOW = 1_788_600_000.0  # a fixed anchor; gotcha #44 — offset from it, never branch on it


class TestTheReaderReportsAStateAndNotJustAList:
    """🔴 CERT-1970's finding, and the reason this class replaced a simpler one.

    The first version returned `[]` for a missing key, a corrupt hash, a failed
    read AND a page with no futures cards. The first three mean the arm is not
    working; the fourth means it is working and idle. They are opposite, and the
    sweep's verdict has to be able to tell them apart or a dark front page reads
    `terminal: complete`.
    """

    def _signal(self, rc, monkeypatch, *, now=_NOW):
        monkeypatch.setattr(
            "app.tasks.redis_state.get_redis_client", lambda **kw: rc
        )
        return fsm.served_signal(now=now)

    def _write(self, rc, label, ids, *, age_s=0):
        rc.hash[label] = json.dumps({"at": int(_NOW - age_s), "ids": list(ids)})

    # --- the two healthy states ------------------------------------------------
    def test_a_page_with_cards_is_fresh_and_the_ids_are_unioned_and_sorted(
        self, monkeypatch
    ):
        rc = _FakeRedis()
        self._write(rc, "discover", [9, 3])
        self._write(rc, "sports", [3, 1])
        sig = self._signal(rc, monkeypatch)
        assert sig.state == fsm.SERVED_FRESH
        assert sig.ids == [1, 3, 9]
        assert sig.shapes == 2
        assert sig.green_allowed

    def test_a_page_with_no_futures_cards_is_EMPTY_and_stays_valid(
        self, monkeypatch
    ):
        """The one state that legitimately has no ids. It must not read as broken.

        The block's required control: a present-but-empty signal remains valid.
        """
        rc = _FakeRedis()
        self._write(rc, "discover", [])
        sig = self._signal(rc, monkeypatch)
        assert sig.state == fsm.SERVED_EMPTY
        assert sig.ids == []
        assert sig.green_allowed

    # --- the three unhealthy ones, which used to be indistinguishable ---------
    def test_a_redis_outage_is_UNAVAILABLE_and_never_never_seen(self, monkeypatch):
        """The conservative direction, and the whole of it.

        A read that raised cannot rule out that this arm was healthy, so calling
        it a cold start would restore the false green. `never_seen` is a claim
        about history; a failed read is the absence of one.
        """
        rc = _FakeRedis(raise_on={"hgetall"})
        sig = self._signal(rc, monkeypatch)
        assert sig.state == fsm.SERVED_UNAVAILABLE
        assert not sig.green_allowed

    def test_a_missing_key_with_a_stale_last_ok_marker_is_UNAVAILABLE(
        self, monkeypatch
    ):
        rc = _FakeRedis()
        rc.strings[fsm.SERVED_SIGNAL_LAST_OK_KEY] = str(
            int(_NOW - fsm.SERVED_SIGNAL_GRACE_S - 1)
        )
        sig = self._signal(rc, monkeypatch)
        assert sig.state == fsm.SERVED_UNAVAILABLE
        assert not sig.green_allowed

    def test_a_hash_of_only_corrupt_entries_is_UNAVAILABLE_not_empty(
        self, monkeypatch
    ):
        """Corrupt is not idle. This is the case the old `[]` hid most completely."""
        rc = _FakeRedis()
        rc.hash["discover"] = "{not json"
        rc.hash["sports"] = json.dumps({"ids": [1]})  # no `at` — cannot be aged
        rc.strings[fsm.SERVED_SIGNAL_LAST_OK_KEY] = str(
            int(_NOW - fsm.SERVED_SIGNAL_GRACE_S - 1)
        )
        sig = self._signal(rc, monkeypatch)
        assert sig.state == fsm.SERVED_UNAVAILABLE
        assert sig.unreadable_shapes == 2

    # --- and the two that are unhealthy but must not alarm --------------------
    def test_the_first_sighting_of_an_empty_store_is_NEVER_SEEN(self, monkeypatch):
        """A first deploy must not alarm on its own bootstrap — ONCE."""
        rc = _FakeRedis()
        sig = self._signal(rc, monkeypatch)
        assert sig.state == fsm.SERVED_NEVER_SEEN
        assert sig.green_allowed
        assert rc.strings[fsm.SERVED_SIGNAL_FIRST_MISSING_KEY] == str(int(_NOW))

    def test_a_recent_marker_is_WARMING_UP_and_permits_green(self, monkeypatch):
        """Inside the grace nothing has been demonstrated wrong yet.

        Its own state rather than a reuse of `never_seen`: a reader asking "has
        this ever worked" must not be told "no" about a signal that worked
        twenty minutes ago.
        """
        rc = _FakeRedis()
        rc.strings[fsm.SERVED_SIGNAL_LAST_OK_KEY] = str(int(_NOW - 20 * 60))
        sig = self._signal(rc, monkeypatch)
        assert sig.state == fsm.SERVED_WARMING_UP
        assert sig.green_allowed

    def test_the_grace_boundary_is_the_grace_constant(self, monkeypatch):
        """Both sides of it, offset from one anchor (gotcha #44)."""
        rc = _FakeRedis()
        for offset, expected in (
            (fsm.SERVED_SIGNAL_GRACE_S - 60, fsm.SERVED_WARMING_UP),
            (fsm.SERVED_SIGNAL_GRACE_S + 60, fsm.SERVED_UNAVAILABLE),
        ):
            rc.strings[fsm.SERVED_SIGNAL_LAST_OK_KEY] = str(int(_NOW - offset))
            assert self._signal(rc, monkeypatch).state == expected

    def test_an_unparseable_marker_still_counts_as_history(self, monkeypatch):
        """Something wrote it, so the arm has been healthy at least once."""
        rc = _FakeRedis()
        rc.strings[fsm.SERVED_SIGNAL_LAST_OK_KEY] = "not-a-number"
        assert self._signal(rc, monkeypatch).state == fsm.SERVED_UNAVAILABLE

    def test_a_marker_read_that_raises_is_UNAVAILABLE(self, monkeypatch):
        rc = _FakeRedis(raise_on={"get"})
        assert self._signal(rc, monkeypatch).state == fsm.SERVED_UNAVAILABLE

    # --- partial health --------------------------------------------------------
    def test_one_corrupt_shape_does_not_wipe_its_siblings(self, monkeypatch):
        """One bad item must never wipe the pass (gotcha #42)."""
        rc = _FakeRedis()
        self._write(rc, "discover", [5])
        rc.hash["sports"] = "{not json"
        sig = self._signal(rc, monkeypatch)
        assert sig.state == fsm.SERVED_FRESH
        assert sig.ids == [5]
        assert sig.unreadable_shapes == 1

    def test_a_non_integer_id_is_refused(self, monkeypatch):
        rc = _FakeRedis()
        rc.hash["discover"] = json.dumps(
            {"at": int(_NOW), "ids": [1, "2", None, True, -4, 0, 6]}
        )
        assert self._signal(rc, monkeypatch).ids == [1, 6]


class TestTheBootstrapExemptionHasAClock:
    """🔴 CERT-1974's finding. `never_seen` was an ABSORBING state.

    The first repair exempted a cold start — nothing can have regressed in an arm
    that has never run — and then gave the exemption no way to expire. On a
    HEALTHY Redis holding no served hash and no last-healthy marker, every read
    returned `never_seen`, permitted green, and deliberately wrote nothing. The
    grader probed the blocked sha at 0h, 4h, 24h and 744h and got
    `never_seen` / `is_green=True` every time.

    That is not a cold start, it is a rail that never started — a broken pre-warm
    hook, a beat its queue never reaches — and it would have kept the enforced
    task green forever while a page-one-only card sat outside every refresh arm.
    The exemption had swallowed the state it was written to survive.
    """

    def _signal(self, rc, monkeypatch, *, now):
        monkeypatch.setattr(
            "app.tasks.redis_state.get_redis_client", lambda **kw: rc
        )
        return fsm.served_signal(now=now)

    def test_an_empty_healthy_store_stops_permitting_green_after_the_grace(
        self, monkeypatch
    ):
        """THE REQUIRED REGRESSION: the same store, at t0 and t0 + grace + 1.

        One `_FakeRedis` across both reads, deliberately — the defect is only
        visible in a store that PERSISTS what the first read wrote. A fresh fake
        per call would pass against the blocked code.
        """
        rc = _FakeRedis()

        first = self._signal(rc, monkeypatch, now=_NOW)
        assert first.state == fsm.SERVED_NEVER_SEEN
        assert first.green_allowed

        later = self._signal(
            rc, monkeypatch, now=_NOW + fsm.SERVED_SIGNAL_GRACE_S + 1
        )
        assert later.state == fsm.SERVED_UNAVAILABLE
        assert not later.green_allowed

    def test_inside_the_grace_it_is_warming_up_and_still_green(self, monkeypatch):
        rc = _FakeRedis()
        self._signal(rc, monkeypatch, now=_NOW)
        mid = self._signal(
            rc, monkeypatch, now=_NOW + fsm.SERVED_SIGNAL_GRACE_S - 60
        )
        assert mid.state == fsm.SERVED_WARMING_UP
        assert mid.green_allowed

    def test_the_stamp_is_written_once_and_never_moved_forward(self, monkeypatch):
        """A clock whose hands are put back on every read is not a clock.

        This is the mutation that would restore the endless bootstrap while every
        other test in this class still passed, so it is asserted on the stored
        VALUE rather than on the state it produces.
        """
        rc = _FakeRedis()
        for offset in (0, 60, 3_600, 100_000):
            self._signal(rc, monkeypatch, now=_NOW + offset)
        assert rc.strings[fsm.SERVED_SIGNAL_FIRST_MISSING_KEY] == str(int(_NOW))

    def test_the_stamps_ttl_outlives_the_grace_by_orders_of_magnitude(self):
        """If the key expired the clock would restart and the bootstrap would

        come back one grace window at a time — the same endless green, merely
        slower. Its TTL is refreshed on read; its value is not, which is the
        distinction "non-renewing" actually forbids.
        """
        assert (
            fsm.SERVED_SIGNAL_FIRST_MISSING_TTL_S > 1000 * fsm.SERVED_SIGNAL_GRACE_S
        )

    def test_a_healthy_observation_clears_the_bootstrap_clock(self, monkeypatch):
        """Once the arm has worked, `last_ok` drives everything and a surviving

        first-missing stamp is residue. One clock at a time.
        """
        rc = _FakeRedis()
        monkeypatch.setattr(
            "app.tasks.redis_state.get_redis_client", lambda **kw: rc
        )
        fsm.served_signal(now=_NOW)
        assert fsm.SERVED_SIGNAL_FIRST_MISSING_KEY in rc.strings
        fsm.note_served_signal_healthy(now=_NOW + 10)
        assert fsm.SERVED_SIGNAL_FIRST_MISSING_KEY not in rc.strings

    def test_a_failure_writing_the_clock_reads_unavailable(self, monkeypatch):
        """Same conservative direction as every other branch: an arm we cannot

        ask about is not an arm we may claim coverage from.
        """
        rc = _FakeRedis(raise_on={"set"})
        assert (
            self._signal(rc, monkeypatch, now=_NOW).state == fsm.SERVED_UNAVAILABLE
        )

    def test_a_last_ok_marker_takes_precedence_over_the_bootstrap_clock(
        self, monkeypatch
    ):
        """The bootstrap branch must be unreachable once the arm has been healthy."""
        rc = _FakeRedis()
        rc.strings[fsm.SERVED_SIGNAL_LAST_OK_KEY] = str(int(_NOW - 60))
        assert self._signal(rc, monkeypatch, now=_NOW).state == fsm.SERVED_WARMING_UP
        assert fsm.SERVED_SIGNAL_FIRST_MISSING_KEY not in rc.strings


class TestARetiredShapeCannotStayPriorityWorkForever:
    """`L1B-051-PER-SHAPE-SERVED-SIGNAL-EXPIRY` — CERT-1970's follow-up.

    Redis expiry is key-wide. A shape that is retired, renamed or simply stops
    warming keeps its ids alive for as long as any SIBLING keeps refreshing the
    key's TTL, so without a per-entry stamp a dead label is priority work
    indefinitely — re-pricing markets nobody is being shown, at any tier and any
    volume, which is exactly the licence the served arm is not supposed to be.
    """

    def _signal(self, rc, monkeypatch):
        monkeypatch.setattr(
            "app.tasks.redis_state.get_redis_client", lambda **kw: rc
        )
        return fsm.served_signal(now=_NOW)

    def test_a_shape_past_the_age_bound_is_pruned_while_its_siblings_live(
        self, monkeypatch
    ):
        rc = _FakeRedis()
        rc.hash["discover"] = json.dumps({"at": int(_NOW - 60), "ids": [1]})
        rc.hash["retired"] = json.dumps(
            {"at": int(_NOW - fsm.SERVED_SHAPE_MAX_AGE_S - 60), "ids": [999]}
        )
        sig = self._signal(rc, monkeypatch)
        assert sig.ids == [1], "a shape that stopped warming is still priority work"
        assert sig.stale_shapes == 1
        assert sig.shapes == 1
        assert sig.state == fsm.SERVED_FRESH

    def test_a_hash_of_only_stale_shapes_is_not_read_as_a_working_arm(
        self, monkeypatch
    ):
        rc = _FakeRedis()
        rc.hash["discover"] = json.dumps(
            {"at": int(_NOW - fsm.SERVED_SHAPE_MAX_AGE_S - 1), "ids": [1]}
        )
        rc.strings[fsm.SERVED_SIGNAL_LAST_OK_KEY] = str(
            int(_NOW - fsm.SERVED_SIGNAL_GRACE_S - 1)
        )
        assert self._signal(rc, monkeypatch).state == fsm.SERVED_UNAVAILABLE

    def test_the_age_bound_can_actually_fire(self):
        """Above the key's own TTL it would be unreachable code."""
        assert fsm.SERVED_SHAPE_MAX_AGE_S < fsm.SERVED_MARKET_IDS_TTL_S
        # ...and above the warm rail's longest observed gap (2,511s), so a
        # struggling rail is not mistaken for a stopped one.
        assert fsm.SERVED_SHAPE_MAX_AGE_S > 2_511

    def test_an_entry_without_a_stamp_is_refused_rather_than_assumed_fresh(self):
        """Assuming fresh reinstates the immortal retired shape."""
        assert fsm._decode(json.dumps({"ids": [1]})) is None
        assert fsm._decode(json.dumps({"at": True, "ids": [1]})) is None
        assert fsm._decode(json.dumps({"at": 1, "ids": "nope"})) is None


class TestTheConsumerWritesTheHealthMarker:
    def test_it_records_a_timestamp_under_a_long_ttl(self, monkeypatch):
        rc = _FakeRedis()
        monkeypatch.setattr(
            "app.tasks.redis_state.get_redis_client", lambda **kw: rc
        )
        fsm.note_served_signal_healthy(now=_NOW)
        assert rc.setex_calls == [
            (fsm.SERVED_SIGNAL_LAST_OK_KEY, fsm.SERVED_SIGNAL_LAST_OK_TTL_S, str(int(_NOW)))
        ]

    def test_it_never_raises(self, monkeypatch):
        rc = _FakeRedis(raise_on={"setex"})
        monkeypatch.setattr(
            "app.tasks.redis_state.get_redis_client", lambda **kw: rc
        )
        fsm.note_served_signal_healthy(now=_NOW)

    def test_the_marker_outlives_the_grace_by_a_wide_margin(self):
        """Otherwise its own expiry reads as "this arm never worked"."""
        assert fsm.SERVED_SIGNAL_LAST_OK_TTL_S > 100 * fsm.SERVED_SIGNAL_GRACE_S


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
