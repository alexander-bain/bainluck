"""Guard tests for LAT-P026: the hub tier's miss must not cost a rebuild (#1651).

These pin the defect measured in production on 2026-08-10 against deployed
`259536f8`, one request at a time, cold pass then warm pass inside the 180s TTL:

    golf      2.745s cold   0.285s warm   9.6x
    tennis    1.622s cold   0.353s warm   4.6x
    esports   1.101s cold   0.451s warm   2.4x
    mma       0.874s cold   0.287s warm   3.0x
    boxing    0.870s cold   0.242s warm   3.6x
    politics  (control, precomputed)      0.30s

Every 180 seconds the first reader of each hub paid that cold column with a
healthy 24h mirror sitting one Redis `GET` away, because the mirror was read only
when the build came back EMPTY — it rescued a failed build and did nothing at all
for a cold one.

Everything here asserts SHAPE and CALL COUNT, never wall-clock, so it is
deterministic in CI. The numbers above are why the shape matters, not the test.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.routes import hub as hub_route
from app.utils import event_concept_cache as cache_mod


class _FakeRedis:
    """In-memory Redis: get / set(nx,ex) / setex / delete / eval over a dict.

    Deliberately a local double rather than an import from the concept tier's
    test module: coupling two test files makes collection order load-bearing, and
    a forty-line double is cheaper than that.
    """

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

    def eval(self, script, numkeys, *args):
        key, token = args[0], args[1]
        expected = token.encode() if isinstance(token, str) else token
        if self.store.get(key) == expected:
            self.store.pop(key, None)
            self.ttls.pop(key, None)
            return 1
        return 0


SLUG = "mma"


def _hub_payload(*, marker="stored", sections=None, upcoming=None):
    """A hub body shaped like `build_hub`'s return value."""
    return {
        "competition": SLUG,
        "label": "MMA",
        "title": "MMA",
        "emoji": "🥊",
        "blurb": "",
        "sport_key": "mma_mixed_martial_arts",
        "upcoming": upcoming if upcoming is not None else [{"key": marker}],
        "sections": sections if sections is not None else {"futures": [{"id": 1}]},
        "total_markets": 1,
        "marker": marker,
    }


def _enveloped(**kwargs):
    """A stored payload that `read_slot` will accept: current generation, all five
    contract fields present and well-formed."""
    return cache_mod.stamp_envelope(
        _hub_payload(**kwargs),
        created_at=datetime.now(timezone.utc),
        lifecycle_watermark=None,
    )


def _seed(rc, slot: str, **kwargs) -> dict:
    keys = hub_route.hub_cache_keys(SLUG)
    payload = _enveloped(**kwargs)
    rc.setex(getattr(keys, slot), 999, cache_mod.encode_payload(payload))
    return payload


class _BuildSpy:
    """Stands in for `build_hub`, counting how many rebuilds actually happened."""

    def __init__(self, *, result=None, raises=False, delay=0.0):
        self.calls = 0
        self._result = result
        self._raises = raises
        self._delay = delay

    async def __call__(self, cfg, db):
        self.calls += 1
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._raises:
            raise RuntimeError("upstream exploded")
        return self._result if self._result is not None else _hub_payload(marker="rebuilt")


async def _call(rc, spy, dispatch=None):
    """Invoke the route with the cache client and builder stubbed out."""
    sender = dispatch if dispatch is not None else (lambda *a, **k: None)

    class _Celery:
        @staticmethod
        def send_task(*args, **kwargs):
            return sender(*args, **kwargs)

    with patch.object(hub_route, "get_client", return_value=rc), \
         patch.object(hub_route, "build_hub", spy), \
         patch.dict("sys.modules", {}), \
         patch("app.tasks.celery_app", _Celery):
        return await hub_route.get_competition_hub(competition=SLUG, db=None)


# ---------------------------------------------------------------------------
# The fix
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_miss_with_healthy_mirror_serves_stale_without_rebuilding():
    """THE defect. Primary expired, mirror healthy: serve the mirror, do not build.

    Before #1651 this walked past the mirror into a full rebuild — the golf
    2.745s column above.
    """
    rc = _FakeRedis()
    _seed(rc, "stale", marker="mirror")
    spy = _BuildSpy()

    out = await _call(rc, spy)

    assert spy.calls == 0, "a cache miss rebuilt while a healthy mirror was one GET away"
    assert out["marker"] == "mirror"
    assert out["cache"]["availability"] == cache_mod.AVAILABILITY_STALE_OK


@pytest.mark.asyncio
async def test_miss_with_mirror_schedules_exactly_one_refresh():
    rc = _FakeRedis()
    _seed(rc, "stale", marker="mirror")
    dispatched = []

    await _call(rc, _BuildSpy(), dispatch=lambda *a, **k: dispatched.append((a, k)))

    assert len(dispatched) == 1
    args, kwargs = dispatched[0]
    assert args[0] == "app.tasks.refresh_hub"
    slug, token = kwargs["args"]
    assert slug == SLUG
    # The owner token must TRAVEL with the dispatch: the route acquires the lock
    # and the worker releases it, so the worker has to be able to prove ownership
    # (#1678 finding 1). A dispatch without it releases whatever it finds.
    assert token, "refresh dispatched without the refresh-lock owner token"


@pytest.mark.asyncio
async def test_concurrent_burst_behind_one_expiry_produces_one_rebuild():
    """Single-flight: N readers arriving behind one TTL expiry, not N rebuilds."""
    rc = _FakeRedis()
    _seed(rc, "stale", marker="mirror")
    dispatched = []

    outs = await asyncio.gather(*[
        _call(rc, _BuildSpy(), dispatch=lambda *a, **k: dispatched.append(a))
        for _ in range(12)
    ])

    assert len(dispatched) == 1, f"stampede: {len(dispatched)} refreshes for one expiry"
    assert all(o["cache"]["availability"] == cache_mod.AVAILABILITY_STALE_OK for o in outs)
    assert all(o["marker"] == "mirror" for o in outs)


# ---------------------------------------------------------------------------
# What must NOT change
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_warm_primary_hit_serves_live_and_never_builds():
    rc = _FakeRedis()
    stored = _seed(rc, "primary", marker="warm")
    spy = _BuildSpy()

    out = await _call(rc, spy)

    assert spy.calls == 0
    assert out["cache"]["availability"] == cache_mod.AVAILABILITY_LIVE
    # UX-P061 (#1742): the route now ALSO stamps ruling 025's conforming
    # `availability` at the top level (spec §7). The legacy `cache.availability` is
    # untouched above — this is additive, not a migration of the cache tier — but
    # the conforming field is a real second envelope key and must be excluded from
    # the byte-identity check rather than silently tolerated.
    assert out["availability"] == "fresh"
    envelope_keys = {"cache", "availability"}
    # Additive only: every non-envelope key is byte-identical to what was stored.
    assert {k: v for k, v in out.items() if k not in envelope_keys} == {
        k: v for k, v in stored.items() if k not in envelope_keys
    }


@pytest.mark.asyncio
async def test_cold_with_nothing_cached_builds_inline_and_caches_both_slots():
    rc = _FakeRedis()
    spy = _BuildSpy()

    out = await _call(rc, spy)

    assert spy.calls == 1
    assert out["marker"] == "rebuilt"
    assert out["cache"]["availability"] == cache_mod.AVAILABILITY_LIVE
    keys = hub_route.hub_cache_keys(SLUG)
    assert rc.store.get(keys.primary) is not None
    assert rc.store.get(keys.stale) is not None
    # The primary TTL is this tier's own, not the concept tier's 60s. Asserted as
    # a LITERAL on purpose: `== hub_route.HUB_PRIMARY_TTL` reads the same constant
    # it is checking, so it passes for any value and pins nothing. Mutation M5
    # (180 -> 60) walked straight through that version of this line.
    assert rc.ttls[keys.primary] == 180
    assert rc.ttls[keys.stale] == 86400


@pytest.mark.asyncio
async def test_failed_build_is_rescued_by_the_mirror():
    rc = _FakeRedis()
    _seed(rc, "stale", marker="mirror")
    keys = hub_route.hub_cache_keys(SLUG)
    # Force step 3 (not step 2) by making the mirror invisible to the first read.
    with patch.object(hub_route, "read_slot", side_effect=[None, None, cache_mod.decode_payload(rc.store[keys.stale])]):
        out = await _call(rc, _BuildSpy(raises=True))
    assert out["marker"] == "mirror"
    assert out["cache"]["availability"] == cache_mod.AVAILABILITY_STALE_OK


@pytest.mark.asyncio
async def test_empty_build_never_overwrites_a_good_mirror():
    """The rescue must have something to rescue.

    Writing before the emptiness check would clobber the 24h snapshot with the
    blank page and then 'rescue' by reading back the blank we just stored. The
    pre-#1651 route got this ordering for free; moving the write into a shared
    helper is exactly where it is easy to lose.
    """
    rc = _FakeRedis()
    _seed(rc, "stale", marker="mirror")
    keys = hub_route.hub_cache_keys(SLUG)
    before = rc.store[keys.stale]
    empty = _hub_payload(marker="blank", sections={}, upcoming=[])

    # Primary is absent; make step 2 miss so the empty build actually runs, then
    # let the post-build rescue see the real mirror.
    real_read = hub_route.read_slot
    calls = {"n": 0}

    def _read(rc_, key):
        calls["n"] += 1
        if calls["n"] == 2:  # step 2's mirror probe
            return None
        return real_read(rc_, key)

    with patch.object(hub_route, "read_slot", _read):
        out = await _call(rc, _BuildSpy(result=empty))

    assert rc.store[keys.stale] == before, "an empty build clobbered the mirror"
    assert out["marker"] == "mirror"
    assert out["cache"]["availability"] == cache_mod.AVAILABILITY_STALE_OK


# ---------------------------------------------------------------------------
# Honest quality (the module's typed-loss vocabulary, adopted here)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lost_sections_publish_degraded_not_full():
    cfg = hub_route.HUB_CONFIGS[SLUG]
    with patch.object(hub_route, "get_league_futures", side_effect=RuntimeError("boom")):
        built = await hub_route.build_hub(cfg, db=None)
    quality, reasons = cache_mod.take_build_quality(built)
    assert quality == cache_mod.QUALITY_DEGRADED
    assert "hub_league_futures_failed" in reasons
    assert cache_mod.BUILD_LOSS_FIELD not in built, "private loss field reached the wire"


@pytest.mark.asyncio
async def test_healthy_build_publishes_full_with_no_reasons():
    cfg = hub_route.HUB_CONFIGS[SLUG]
    with patch.object(hub_route, "get_league_futures", return_value={"sections": {"futures": []}}), \
         patch.dict(hub_route._UPCOMING_LISTERS, {}, clear=True):
        built = await hub_route.build_hub(cfg, db=None)
    quality, reasons = cache_mod.take_build_quality(built)
    assert quality == cache_mod.QUALITY_FULL
    assert reasons == []


@pytest.mark.asyncio
async def test_served_payload_carries_all_five_envelope_fields():
    rc = _FakeRedis()
    out = await _call(rc, _BuildSpy())
    for field in cache_mod.ENVELOPE_FIELDS:
        assert field in out["cache"], f"envelope missing contract field {field}"
    assert out["cache"]["generation"] == cache_mod.GENERATION


# ---------------------------------------------------------------------------
# The keys did not move
# ---------------------------------------------------------------------------


def test_hub_keys_are_unchanged_from_the_pre_adoption_layout():
    """Adoption, not migration: production keys stay where they are."""
    keys = hub_route.hub_cache_keys("golf")
    assert keys.primary == "bainluck:hub:golf"
    assert keys.stale == "bainluck:hub:golf:stale"


def test_cache_keys_default_prefix_is_unchanged_for_the_concept_tier():
    assert cache_mod.cache_keys("event:golf:x").primary == (
        f"{cache_mod.CACHE_PREFIX}event:golf:x"
    )


# ---------------------------------------------------------------------------
# The refresh task
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_task_releases_only_its_own_token():
    from app.tasks.hub_refresh import _refresh_hub

    rc = _FakeRedis()
    keys = hub_route.hub_cache_keys(SLUG)
    rc.set(keys.refresh_lock, "someone-elses-token", nx=True, ex=120)

    with patch.object(cache_mod, "get_client", return_value=rc), \
         patch.object(hub_route, "build_hub", _BuildSpy()), \
         patch("app.tasks.base.get_task_session"):
        await _refresh_hub(SLUG, token="my-token")

    assert rc.store.get(keys.refresh_lock) == b"someone-elses-token", (
        "the worker deleted a lock it could not prove it owned"
    )


@pytest.mark.asyncio
async def test_refresh_task_reports_unknown_slug_distinctly():
    from app.tasks.hub_refresh import _refresh_hub

    rc = _FakeRedis()
    with patch.object(cache_mod, "get_client", return_value=rc):
        out = await _refresh_hub("not-a-hub", token=None)
    assert out["reason"] == "unknown_slug"
    assert out["completed"] == 0
