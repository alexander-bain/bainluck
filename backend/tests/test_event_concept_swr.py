"""Guard tests for LAT-P021: the concept tier's miss must not cost a rebuild (#1107).

These pin the defect measured in production on 2026-08-09, against deployed
`faae7a48`, one request at a time and outside the post-deploy window:

    21:07:33  event:golf:pga-championship   200  10.977s   cold build (writes primary+stale)
    21:08:09  event:golf:pga-championship   200   0.437s   t+36s, inside the 60s TTL
    21:09:18  event:golf:pga-championship   200  18.537s   t+105s, TTL expired

The third read is the bug. The primary had expired; a 96-second-old, complete,
healthy 24h mirror sat one Redis key away; the request walked past it into a full
rebuild. `event:golf:the-open-championship` did the same thing and crossed
Heroku's 30s H12 boundary into a **503** — while its dyno finished the build ~35s
in and warmed the cache for the *next* reader.

Everything here asserts SHAPE and CALL COUNT, never wall-clock, so it is
deterministic in CI. The numbers above are why the shape matters, not the test.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.routes import event as event_route
from app.utils import event_concept_cache as cache_mod


class _FakeRedis:
    """In-memory Redis: get / set(nx,ex) / setex / delete over a dict."""

    def __init__(self):
        self.store: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}

    def get(self, k):
        return self.store.get(k)

    def set(self, k, v, nx=False, ex=None):
        if nx and k in self.store:
            return None
        self.store[k] = v.encode() if isinstance(v, str) else v
        if ex is not None:
            self.ttls[k] = ex
        return True

    def setex(self, k, ttl, v):
        self.ttls[k] = ttl
        self.store[k] = v.encode() if isinstance(v, str) else v

    def delete(self, k):
        self.ttls.pop(k, None)
        return int(self.store.pop(k, None) is not None)


class _StubAdapter:
    def __init__(self, envelope=None, *, raises=False):
        self._envelope = envelope or {"event": {"name": "The Open"}, "primary": {"competitors": []}}
        self._raises = raises
        self.calls = 0

    async def build_event(self, slug, db):
        self.calls += 1
        if self._raises:
            raise RuntimeError("boom")
        return {**self._envelope, "_build_n": self.calls}


KEY = "event:golf:the-open-championship"
KEYS = cache_mod.cache_keys(KEY)


async def _get(key=KEY, *, adapter, rc, db=None):
    with patch.object(event_route, "get_adapter", return_value=adapter), \
         patch("app.tasks.redis_state.get_redis_client", return_value=rc):
        return await event_route.get_event_concept(key, db=db)


def _expire_primary(rc):
    """What Redis does at the 60s boundary: the primary goes, the mirror stays."""
    rc.store.pop(KEYS.primary, None)


# ---------------------------------------------------------------------------
# The measured defect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_ttl_miss_serves_the_mirror_instead_of_rebuilding():
    """THE regression guard. A primary expiry must cost a mirror read, not a build."""
    adapter = _StubAdapter()
    rc = _FakeRedis()

    with patch("app.tasks.celery_app.send_task"):
        await _get(adapter=adapter, rc=rc)          # cold build
        assert adapter.calls == 1
        _expire_primary(rc)                          # the 60s boundary
        out = await _get(adapter=adapter, rc=rc)     # the read that used to cost 18.5s

    assert adapter.calls == 1, (
        f"the adapter ran {adapter.calls} times — a TTL expiry rebuilt instead of "
        "serving the healthy 24h mirror sitting next to it. This is the 18.5s "
        "(and, for The Open, the 30s H12 503) measured in production."
    )
    assert out["_build_n"] == 1
    assert out[cache_mod.ENVELOPE_FIELD]["availability"] == cache_mod.AVAILABILITY_STALE_OK


@pytest.mark.asyncio
async def test_the_mirror_serve_schedules_exactly_one_revalidation():
    """Single-flight: a burst behind one expiry produces one rebuild, not N."""
    adapter = _StubAdapter()
    rc = _FakeRedis()

    with patch("app.tasks.celery_app.send_task") as send:
        await _get(adapter=adapter, rc=rc)
        _expire_primary(rc)
        for _ in range(5):
            await _get(adapter=adapter, rc=rc)

    assert send.call_count == 1, (
        f"{send.call_count} revalidations dispatched for one expiry — that is the "
        "cold-build stampede Codex C224 found, moved to the background rather than fixed"
    )
    assert send.call_args.args[0] == "app.tasks.refresh_event_concept"
    assert send.call_args.kwargs["args"] == [KEY]


@pytest.mark.asyncio
async def test_a_failed_dispatch_releases_the_lock_so_the_next_reader_retries():
    """A dead broker must cost one retry, not wedge the key for the lock's TTL."""
    adapter = _StubAdapter()
    rc = _FakeRedis()

    with patch("app.tasks.celery_app.send_task", side_effect=RuntimeError("no broker")):
        await _get(adapter=adapter, rc=rc)
        _expire_primary(rc)
        await _get(adapter=adapter, rc=rc)

    assert KEYS.refresh_lock not in rc.store, (
        "the single-flight lock survived a failed dispatch — nothing will "
        "revalidate this key until the lock's own TTL expires"
    )


# ---------------------------------------------------------------------------
# Codex C224: a malformed primary must not disarm the whole request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_malformed_primary_falls_through_to_the_mirror():
    adapter = _StubAdapter()
    rc = _FakeRedis()

    with patch("app.tasks.celery_app.send_task"):
        await _get(adapter=adapter, rc=rc)
        rc.store[KEYS.primary] = b"{not json"      # corruption
        out = await _get(adapter=adapter, rc=rc)

    assert adapter.calls == 1, (
        "a corrupt primary sent the request to a full rebuild past a healthy "
        "mirror — the old `except Exception: _rc = None` disabled Redis wholesale"
    )
    assert out["_build_n"] == 1


@pytest.mark.asyncio
async def test_a_malformed_primary_does_not_disarm_the_write_back():
    """The other half of C224: the rebuild's result must still be cached."""
    adapter = _StubAdapter()
    rc = _FakeRedis()
    rc.store[KEYS.primary] = b"\x00\x01 not json"   # corrupt, and no mirror exists

    with patch("app.tasks.celery_app.send_task"):
        await _get(adapter=adapter, rc=rc)

    assert adapter.calls == 1
    assert cache_mod.read_slot(rc, KEYS.primary) is not None, (
        "the rebuild after a corrupt read was never written back, so every "
        "subsequent request rebuilds too"
    )
    assert cache_mod.read_slot(rc, KEYS.stale) is not None


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_pre_envelope_payload_is_refused_and_rebuilt():
    """What makes the first deploy of this module self-healing.

    Every payload already in Redis was written without an envelope. Serving one
    would be serving possibly-24h-old content with no age disclosure, which is
    the exact defect the contract names.
    """
    adapter = _StubAdapter()
    rc = _FakeRedis()
    legacy = b'{"event": {"name": "Legacy"}, "primary": {"competitors": []}}'
    rc.store[KEYS.primary] = legacy
    rc.store[KEYS.stale] = legacy

    with patch("app.tasks.celery_app.send_task"):
        out = await _get(adapter=adapter, rc=rc)

    assert adapter.calls == 1, "a pre-envelope payload was served without disclosure"
    assert out["event"]["name"] == "The Open"


def test_generation_mismatch_reads_as_a_miss():
    payload = cache_mod.stamp_envelope(
        {"event": {}}, created_at=datetime.now(timezone.utc), lifecycle_watermark=None
    )
    assert cache_mod.is_current_generation(payload)
    payload[cache_mod.ENVELOPE_FIELD]["generation"] = cache_mod.GENERATION + 1
    assert not cache_mod.is_current_generation(payload)
    assert not cache_mod.is_current_generation({"event": {}})
    assert not cache_mod.is_current_generation(None)


# ---------------------------------------------------------------------------
# The envelope (docs/contracts/cache-envelope.md, ruling 005)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_envelope_publishes_all_five_fields():
    adapter = _StubAdapter()
    rc = _FakeRedis()
    out = await _get(adapter=adapter, rc=rc)

    envelope = out[cache_mod.ENVELOPE_FIELD]
    for field in ("generation", "created_at", "quality", "availability", "lifecycle_watermark"):
        assert field in envelope, (
            f"envelope field '{field}' is absent. An absent field and a null field "
            "read identically to a consumer — that ambiguity is what the contract exists to remove."
        )
    assert envelope["generation"] == cache_mod.GENERATION
    assert envelope["quality"] == cache_mod.QUALITY_FULL
    assert envelope["availability"] == cache_mod.AVAILABILITY_LIVE


@pytest.mark.asyncio
async def test_availability_distinguishes_a_live_answer_from_a_stale_one():
    """The whole reason the envelope is mandatory once the mirror is served on purpose:
    a 0.44s live answer and a 0.44s four-minute-old one are otherwise identical."""
    adapter = _StubAdapter()
    rc = _FakeRedis()

    with patch("app.tasks.celery_app.send_task"):
        live = await _get(adapter=adapter, rc=rc)
        warm = await _get(adapter=adapter, rc=rc)
        _expire_primary(rc)
        stale = await _get(adapter=adapter, rc=rc)

    assert live[cache_mod.ENVELOPE_FIELD]["availability"] == cache_mod.AVAILABILITY_LIVE
    assert warm[cache_mod.ENVELOPE_FIELD]["availability"] == cache_mod.AVAILABILITY_LIVE
    assert stale[cache_mod.ENVELOPE_FIELD]["availability"] == cache_mod.AVAILABILITY_STALE_OK


@pytest.mark.asyncio
async def test_created_at_is_content_time_and_survives_a_mirror_serve():
    """Contract: `created_at` is when the CONTENT was computed, not when it was
    written or fetched. Reporting the read time would make a day-old payload
    look fresh — which is the failure the field exists to prevent."""
    adapter = _StubAdapter()
    rc = _FakeRedis()

    with patch("app.tasks.celery_app.send_task"):
        built = await _get(adapter=adapter, rc=rc)
        _expire_primary(rc)
        served = await _get(adapter=adapter, rc=rc)

    assert (
        served[cache_mod.ENVELOPE_FIELD]["created_at"]
        == built[cache_mod.ENVELOPE_FIELD]["created_at"]
    ), "the mirror serve restamped created_at, so old content reports as fresh"


@pytest.mark.asyncio
async def test_the_envelope_is_purely_additive():
    """No existing key changes name, type, or meaning."""
    original = {
        "event": {"name": "The Open", "as_of": None},
        "primary": {"kind": "winner", "competitors": []},
        "sections": [],
        "children": [],
        "props_script": [],
        "movers": [],
    }
    adapter = _StubAdapter(original)
    rc = _FakeRedis()
    out = await _get(adapter=adapter, rc=rc)

    for key, value in original.items():
        assert key in out and out[key] == value, f"the envelope mutated '{key}'"
    assert set(out) - set(original) == {cache_mod.ENVELOPE_FIELD, "_build_n"}


# ---------------------------------------------------------------------------
# Ordering and the cold path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_known_absent_key_404s_rather_than_serving_a_day_old_mirror():
    """The negative is read BEFORE the mirror on purpose: a tournament that has
    stopped resolving must 404, not keep serving yesterday's payload for 24h."""
    from fastapi import HTTPException

    adapter = _StubAdapter()
    rc = _FakeRedis()

    with patch("app.tasks.celery_app.send_task"):
        await _get(adapter=adapter, rc=rc)       # mirror now exists
    _expire_primary(rc)
    cache_mod.write_negative(rc, KEYS)            # the key has since stopped resolving

    with pytest.raises(HTTPException) as exc:
        await _get(adapter=adapter, rc=rc)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_the_cold_path_still_serves_with_the_warmer_disabled():
    """Queue acceptance 3, asserted rather than assumed.

    The warmer must never be load-bearing. With nothing cached and nothing
    scheduled, a cold miss still builds inline and returns a page — slow is the
    failure mode, not broken.
    """
    adapter = _StubAdapter()
    rc = _FakeRedis()

    out = await _get(adapter=adapter, rc=rc)

    assert adapter.calls == 1
    assert out["event"]["name"] == "The Open"
    assert out[cache_mod.ENVELOPE_FIELD]["availability"] == cache_mod.AVAILABILITY_LIVE


@pytest.mark.asyncio
async def test_a_dead_redis_still_serves_the_page():
    adapter = _StubAdapter()
    with patch.object(event_route, "get_adapter", return_value=adapter), \
         patch("app.tasks.redis_state.get_redis_client", side_effect=RuntimeError("down")):
        out = await event_route.get_event_concept(KEY, db=None)
    assert out["_build_n"] == 1
    assert out[cache_mod.ENVELOPE_FIELD]["availability"] == cache_mod.AVAILABILITY_LIVE


# ---------------------------------------------------------------------------
# Watermark (contract field 5)
# ---------------------------------------------------------------------------


def test_collect_market_ids_reads_every_place_a_market_id_hides():
    result = {
        "children": [{"market_id": 3}, {"market_id": "7"}, {"no_id": True}, "junk"],
        "sections": [{"market_ids": [3, 11]}, {"market_ids": None}, "junk"],
        "primary": {"evolution_market_id": 42},
    }
    assert cache_mod.collect_market_ids(result) == [3, 7, 11, 42]


def test_collect_market_ids_is_total_on_a_junk_payload():
    assert cache_mod.collect_market_ids({}) == []
    assert cache_mod.collect_market_ids({"children": None, "sections": 5, "primary": "x"}) == []
    # bool is an int subclass — a True must never become market id 1.
    assert cache_mod.collect_market_ids({"children": [{"market_id": True}]}) == []


@pytest.mark.asyncio
async def test_the_watermark_is_the_newest_upstream_fact_not_the_build_time():
    """`created_at` says when we computed; the watermark says how far into
    reality we had got when we did. A payload rebuilt every 5 minutes from a
    source that stopped updating yesterday has a fresh created_at and a
    day-old watermark — only the watermark makes that visible."""
    newest_market = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)
    live_as_of = datetime(2026, 8, 9, 18, 30, tzinfo=timezone.utc)

    class _DB:
        async def scalar(self, *_a, **_k):
            return newest_market

    result = {"event": {"as_of": live_as_of.isoformat()}, "children": [{"market_id": 1}]}
    assert await cache_mod.compute_watermark(_DB(), result) == live_as_of

    result_no_live = {"event": {"as_of": None}, "children": [{"market_id": 1}]}
    assert await cache_mod.compute_watermark(_DB(), result_no_live) == newest_market


@pytest.mark.asyncio
async def test_a_watermark_we_cannot_compute_never_costs_the_user_the_page():
    class _BrokenDB:
        async def scalar(self, *_a, **_k):
            raise RuntimeError("db down")

    result = {"event": {"as_of": None}, "children": [{"market_id": 1}]}
    assert await cache_mod.compute_watermark(_BrokenDB(), result) is None


@pytest.mark.asyncio
async def test_a_non_datetime_from_the_db_publishes_null_rather_than_a_fabricated_claim():
    """Found by the integration suite, kept because the class is real.

    A value that is not a datetime is not a watermark. Coercing whatever came
    back would stamp a fabricated freshness claim onto the payload — the exact
    failure `lifecycle_watermark` exists to prevent — and the stamping happens on
    the response path of a page that is already the subject of a p0, so it must
    not raise either.
    """

    class _WeirdDB:
        def __init__(self, value):
            self._value = value

        async def scalar(self, *_a, **_k):
            return self._value

    result = {"event": {"as_of": None}, "children": [{"market_id": 1}]}
    for junk in ("2026-08-09", 1754784000, object()):
        assert await cache_mod.compute_watermark(_WeirdDB(junk), result) is None

    # And the stamper itself is total on the same class of value.
    stamped = cache_mod.stamp_envelope({}, created_at=datetime.now(timezone.utc), lifecycle_watermark="nope")
    assert stamped[cache_mod.ENVELOPE_FIELD]["lifecycle_watermark"] is None


def test_payload_age_is_read_from_the_stored_content_time():
    created = datetime.now(timezone.utc) - timedelta(minutes=7)
    payload = cache_mod.stamp_envelope({}, created_at=created, lifecycle_watermark=None)
    age = cache_mod.payload_age_seconds(payload)
    assert age is not None and 400 < age < 440


# ---------------------------------------------------------------------------
# Codec
# ---------------------------------------------------------------------------


def test_decode_payload_is_total():
    assert cache_mod.decode_payload(None) is None
    assert cache_mod.decode_payload(b"{not json") is None
    assert cache_mod.decode_payload(b"[1,2,3]") is None      # not a dict
    assert cache_mod.decode_payload(b'{"a":1}') == {"a": 1}
    assert cache_mod.decode_payload('{"a":1}') == {"a": 1}
