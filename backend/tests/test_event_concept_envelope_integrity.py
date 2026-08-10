"""Guards for #1678 (Codex C243): three P1s in the event-concept cache + warmer.

One test per finding, asserted against CALL and PAYLOAD SHAPE rather than a wall
clock, so they are deterministic in CI:

1. The refresh lock had no owner token. `_build_one` never acquired and released
   unconditionally in its `finally`, so the 5-minute scheduled warmer deleted the
   live lock of a route-dispatched refresh and admitted a second concurrent
   builder. A single-flight primitive that admits a third builder is not one.

2. `read_slot` validated ONE of the envelope's five fields. `{"cache":
   {"generation": N}}` — a single field — passed as a complete envelope, and every
   consumer then read `created_at`/`quality`/`availability` as null with no way to
   tell a malformed payload from an honestly-unknown one.

3. Every build was stamped `quality: "full"`, including builds whose live fusion
   had failed inside a bare `except Exception: pass`. A golf page that could not
   fuse its leaderboard published a complete-looking envelope, and the 24h mirror
   went on republishing that claim.

Finding 3 is deliberately tested THROUGH THE STORED AND SERVED envelope, not
through the build's return value. That is C243's explicit ask, and it is the
difference between testing what the producer computed and testing what a consumer
actually receives — the whole defect lived in the gap between those two.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.routes import event as event_route
from app.utils import event_concept as concept_mod
from app.utils import event_concept_cache as cache_mod


class _FakeRedis:
    """In-memory Redis: get / set(nx,ex) / setex / delete / eval."""

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
        """delete KEYS[1] only if it equals ARGV[1].

        The double implements the SEMANTICS; real Redis provides the ATOMICITY.
        Deliberate split: the defect here was never a torn compare-and-delete, it
        was a caller releasing a lock it had never acquired — a caller-contract
        bug, which is exactly what these tests can catch.
        """
        key, token = args[0], args[1]
        expected = token.encode() if isinstance(token, str) else token
        if self.store.get(key) == expected:
            self.store.pop(key, None)
            self.ttls.pop(key, None)
            return 1
        return 0


class _LossyAdapter:
    """An adapter that builds successfully but records losses on the way."""

    def __init__(self, *losses):
        self._losses = losses
        self.calls = 0

    async def build_event(self, slug, db):
        self.calls += 1
        envelope = {"event": {"name": "The Open"}, "primary": {"competitors": []}}
        for reason, severity in self._losses:
            cache_mod.note_build_loss(envelope, reason, severity)
        return envelope


KEY = "event:golf:the-open-championship"
KEYS = cache_mod.cache_keys(KEY)


async def _serve(adapter, rc):
    with patch.object(event_route, "get_adapter", return_value=adapter), \
         patch("app.tasks.redis_state.get_redis_client", return_value=rc), \
         patch("app.tasks.celery_app.send_task"):
        return await event_route.get_event_concept(KEY, db=None)


def _stored_envelope(rc, slot):
    return json.loads(rc.store[slot].decode())[cache_mod.ENVELOPE_FIELD]


# ---------------------------------------------------------------------------
# Finding 1 — the refresh lock needs an owner
# ---------------------------------------------------------------------------


def test_only_the_holders_token_can_release_the_lock():
    """THE guard for finding 1. A producer that did not acquire cannot release."""
    rc = _FakeRedis()
    mine = cache_mod.acquire_refresh_lock(rc, KEYS)
    assert mine, "precondition: the lock should have been acquired"

    # A second producer cannot even get one.
    assert cache_mod.acquire_refresh_lock(rc, KEYS) is None

    # ...and cannot release the first producer's lock with a token of its own
    # invention, nor by declining to name one at all.
    assert cache_mod.release_refresh_lock(rc, KEYS, "some-other-token") is False
    assert cache_mod.release_refresh_lock(rc, KEYS, None) is False
    assert KEYS.refresh_lock in rc.store, (
        "a non-owner released the single-flight lock — this is #1678 finding 1, "
        "and it admits a second concurrent builder"
    )

    # The owner can.
    assert cache_mod.release_refresh_lock(rc, KEYS, mine) is True
    assert KEYS.refresh_lock not in rc.store


def test_release_fails_closed_when_the_compare_and_delete_cannot_run():
    """A broken Redis must leave the lock to expire, never delete it blind.

    Failing OPEN here would reintroduce the defect on exactly the unhappy path
    where concurrency is most likely.
    """

    class _NoEval(_FakeRedis):
        def eval(self, *a, **k):
            raise RuntimeError("NOSCRIPT")

    rc = _NoEval()
    token = cache_mod.acquire_refresh_lock(rc, KEYS)
    assert cache_mod.release_refresh_lock(rc, KEYS, token) is False
    assert KEYS.refresh_lock in rc.store, (
        "the lock was dropped when its compare-and-delete failed — fail-closed "
        "costs one delayed refresh, fail-open costs a stampede"
    )


@pytest.mark.asyncio
async def test_the_scheduled_warmer_skips_a_key_another_producer_is_building():
    """The exact collision from finding 1, end to end.

    The route acquires and dispatches; the 5-minute warmer wakes mid-rebuild. It
    must leave that key alone — and above all must not delete the lock, which is
    what let a second builder in.
    """
    from app.tasks import event_concept_warmer as warmer

    rc = _FakeRedis()
    route_token = cache_mod.acquire_refresh_lock(rc, KEYS)

    built = []

    async def _spy_build(key, db, rc=None, adapter=None):
        built.append(key)
        return {"event": {}}

    with patch("app.utils.event_concept_cache.get_client", return_value=rc), \
         patch("app.utils.event_concept_cache.build_and_cache", _spy_build):
        summary = await warmer._warm_event_concepts((KEY,))

    assert built == [], "the warmer rebuilt a key that was already being rebuilt"
    assert rc.store.get(KEYS.refresh_lock) == route_token.encode(), (
        "the scheduled warmer deleted the route's live refresh lock — #1678 "
        "finding 1, and the next reader now dispatches a SECOND parallel build"
    )
    assert summary["locked"] == [KEY]
    assert summary["errors"] == []


@pytest.mark.asyncio
async def test_the_scheduled_warmer_acquires_and_then_releases_its_own_lock():
    """The other direction: an uncontended key is built and the lock handed back."""
    from app.tasks import event_concept_warmer as warmer

    rc = _FakeRedis()
    built = []

    async def _spy_build(key, db, rc=None, adapter=None):
        built.append(key)
        # While the build runs, the warmer must be holding the lock.
        assert KEYS.refresh_lock in rc.store if rc else True
        return {"event": {}}

    with patch("app.utils.event_concept_cache.get_client", return_value=rc), \
         patch("app.utils.event_concept_cache.build_and_cache", _spy_build), \
         patch("app.tasks.base.get_task_session"):
        summary = await warmer._warm_event_concepts((KEY,))

    assert built == [KEY]
    assert KEYS.refresh_lock not in rc.store, "the warmer kept its own lock"
    assert summary["built"] == 1
    assert summary["locked"] == []


# ---------------------------------------------------------------------------
# Finding 2 — one field is not an envelope
# ---------------------------------------------------------------------------


def _valid_envelope() -> dict:
    from datetime import datetime, timezone

    return cache_mod.stamp_envelope(
        {"event": {"name": "The Open"}},
        created_at=datetime.now(timezone.utc),
        lifecycle_watermark=None,
    )


@pytest.mark.parametrize(
    "mutate, expected",
    [
        (lambda e: e.clear(), "missing_fields"),
        (lambda e: e.pop("created_at"), "missing_fields"),
        (lambda e: e.pop("quality"), "missing_fields"),
        (lambda e: e.pop("availability"), "missing_fields"),
        (lambda e: e.pop("lifecycle_watermark"), "missing_fields"),
        (lambda e: e.update(created_at=None), "created_at_unparseable"),
        (lambda e: e.update(created_at="not-a-date"), "created_at_unparseable"),
        (lambda e: e.update(quality="excellent"), "quality_invalid"),
        (lambda e: e.update(quality=None), "quality_invalid"),
        (lambda e: e.update(availability="probably"), "availability_invalid"),
        (lambda e: e.update(lifecycle_watermark="soon"), "lifecycle_watermark_unparseable"),
    ],
)
def test_a_malformed_current_generation_payload_is_refused(mutate, expected):
    """Each field is load-bearing. A payload that claims to be this generation and
    is not shaped like one is a MISS, never a serve — we cannot know what a
    missing `quality` should have been, and guessing `full` is the fabrication
    finding 3 is about."""
    payload = _valid_envelope()
    mutate(payload[cache_mod.ENVELOPE_FIELD])

    defect = cache_mod.envelope_defect(payload)
    assert defect is not None and defect.startswith(expected), defect

    rc = _FakeRedis()
    rc.setex(KEYS.primary, 60, json.dumps(payload))
    assert cache_mod.read_slot(rc, KEYS.primary) is None


def test_the_one_field_payload_from_the_audit_is_refused():
    """The literal payload C243 reported as passing."""
    payload = {cache_mod.ENVELOPE_FIELD: {"generation": cache_mod.GENERATION}}
    assert cache_mod.is_current_generation(payload), (
        "precondition: the generation check alone still accepts it — that is why "
        "it was not enough"
    )
    assert not cache_mod.is_servable_envelope(payload)


def test_a_null_watermark_is_an_allowed_unknown():
    """The one deliberate asymmetry: `lifecycle_watermark` may be null, because
    "we do not know how far into reality this payload got" is a real, publishable
    answer and `compute_watermark` returns None by design for a payload that
    references no markets. `availability` may also be null AT REST — it is stamped
    on the way out by `with_availability`."""
    payload = _valid_envelope()
    assert payload[cache_mod.ENVELOPE_FIELD]["lifecycle_watermark"] is None
    assert payload[cache_mod.ENVELOPE_FIELD]["availability"] is None
    assert cache_mod.envelope_defect(payload) is None


@pytest.mark.asyncio
async def test_the_route_rebuilds_rather_than_serving_a_malformed_payload():
    """Through the route, which is where it mattered."""
    adapter = _LossyAdapter()
    rc = _FakeRedis()
    rc.setex(
        KEYS.primary,
        60,
        json.dumps({cache_mod.ENVELOPE_FIELD: {"generation": cache_mod.GENERATION}}),
    )

    out = await _serve(adapter, rc)

    assert adapter.calls == 1, "a one-field payload was served as a complete envelope"
    assert out["event"]["name"] == "The Open"


# ---------------------------------------------------------------------------
# Finding 3 — through the STORED and SERVED envelope, not the build return
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_degraded_build_is_served_and_stored_as_degraded():
    """THE guard for finding 3, and C243's explicit ask.

    Asserting on `build_and_cache`'s return value would have passed against the
    old code too, because the lie was introduced at the stamp and then persisted.
    What matters is what a consumer receives and what the 24h mirror will keep
    repeating, so this checks the response AND both stored slots.
    """
    adapter = _LossyAdapter(("golf_live_fusion_failed", cache_mod.LOSS_DEGRADED))
    rc = _FakeRedis()

    out = await _serve(adapter, rc)

    served = out[cache_mod.ENVELOPE_FIELD]
    assert served["quality"] == cache_mod.QUALITY_DEGRADED, (
        "a build whose live fusion failed was served as a complete one"
    )
    assert served["quality_reasons"] == ["golf_live_fusion_failed"]
    assert served["availability"] == cache_mod.AVAILABILITY_LIVE

    for slot in (KEYS.primary, KEYS.stale):
        stored = _stored_envelope(rc, slot)
        assert stored["quality"] == cache_mod.QUALITY_DEGRADED, (
            f"{slot} will keep republishing quality=full for up to 24h"
        )

    # The private marker is build-scoped and must never reach the wire or Redis.
    assert cache_mod.BUILD_LOSS_FIELD not in out
    assert cache_mod.BUILD_LOSS_FIELD not in json.loads(rc.store[KEYS.stale].decode())


@pytest.mark.asyncio
async def test_the_mirror_still_reports_degraded_when_it_is_served_stale():
    """The quality is baked into the stored bytes, so it survives the mirror path
    — a stale serve reports `stale_ok` availability AND the original build's
    quality, rather than quietly upgrading itself."""
    adapter = _LossyAdapter(("golf_live_fusion_failed", cache_mod.LOSS_DEGRADED))
    rc = _FakeRedis()
    await _serve(adapter, rc)
    rc.store.pop(KEYS.primary)  # the 60s boundary

    out = await _serve(adapter, rc)

    assert out[cache_mod.ENVELOPE_FIELD]["availability"] == cache_mod.AVAILABILITY_STALE_OK
    assert out[cache_mod.ENVELOPE_FIELD]["quality"] == cache_mod.QUALITY_DEGRADED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "severity, expected_quality, expect_reason",
    [
        (cache_mod.LOSS_DEGRADED, cache_mod.QUALITY_DEGRADED, True),
        (cache_mod.LOSS_PARTIAL, cache_mod.QUALITY_PARTIAL, True),
        (cache_mod.LOSS_COSMETIC, cache_mod.QUALITY_FULL, False),
    ],
)
async def test_severity_maps_to_quality(severity, expected_quality, expect_reason):
    """Cosmetic losses stay `full` on purpose: the commentary box is Open-only and
    live-only, so its absence is the NORMAL state for nearly every cached key, and
    grading that `partial` would drain the word of meaning."""
    adapter = _LossyAdapter(("a_loss", severity))
    rc = _FakeRedis()

    out = await _serve(adapter, rc)
    served = out[cache_mod.ENVELOPE_FIELD]

    assert served["quality"] == expected_quality
    assert served["quality_reasons"] == (["a_loss"] if expect_reason else [])


def test_the_worst_severity_wins():
    result = {}
    cache_mod.note_build_loss(result, "cosmetic_thing", cache_mod.LOSS_COSMETIC)
    cache_mod.note_build_loss(result, "partial_thing", cache_mod.LOSS_PARTIAL)
    cache_mod.note_build_loss(result, "degraded_thing", cache_mod.LOSS_DEGRADED)

    quality, reasons = cache_mod.take_build_quality(result)

    assert quality == cache_mod.QUALITY_DEGRADED
    assert reasons == ["partial_thing", "degraded_thing"]
    assert cache_mod.BUILD_LOSS_FIELD not in result, "take_ must POP, or it ships"


def test_a_clean_build_is_full_with_no_reasons():
    quality, reasons = cache_mod.take_build_quality({"event": {}})
    assert quality == cache_mod.QUALITY_FULL
    assert reasons == []


@pytest.mark.asyncio
async def test_the_golf_adapter_marks_a_failed_live_fusion_degraded():
    """The real adapter, not a stub: drive its live-fusion block into its own
    `except` and prove the swallow point now records the loss.

    This is the handler whose comment already claimed "honest degrade" while
    recording nothing at all.
    """

    class _RaisingDB:
        async def execute(self, *a, **k):
            raise RuntimeError("db unavailable")

    data = {"tournament": {"name": "The Open"}, "evolution_market_id": 42}
    envelope = {
        "event": {"status": "upcoming", "name": "The Open"},
        "primary": {"competitors": []},
    }

    with patch(
        "app.routes.golf.get_golf_tournament", new=AsyncMock(return_value=data)
    ), patch.object(concept_mod, "golf_detail_to_envelope", return_value=envelope):
        built = await concept_mod.GolfEventAdapter().build_event("the-open", _RaisingDB())

    quality, reasons = cache_mod.take_build_quality(built)
    assert quality == cache_mod.QUALITY_DEGRADED
    assert "golf_live_fusion_failed" in reasons
