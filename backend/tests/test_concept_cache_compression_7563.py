"""Guard tests for #7563: the concept tier stores compressed, and reads both codecs.

WHY THIS TIER AND NOT A REDIS PLAN BUMP. Production Redis on 2026-09-20 was
86.3% of a 100 MB `maxmemory` under **`allkeys-lru`**, with 646,869
`evicted_keys`. On `allkeys-lru` a declared TTL is not a residency guarantee —
the evictor takes the least-recently-*used* key no matter how long its TTL had
left. The venue-history bank of #7351 declares 36 h, measured under 4 h, and is
the perfect LRU victim: small (0.33 MB) and read only when one reader opens one
chart. It was not evicted for being big. It was evicted because this tier is
big: `bainluck:related_futures` (7.23 MB / 22 keys) and `bainluck:game_markets`
(7.14 MB / 28 keys) were the two largest classes in the census, and every class
routed through `encode_payload` summed to ~24 MB of the ~53 MB accounted for.

So the fix is this tier's footprint, and the reader-visible ship is #7563's:
a cold reader stops getting the mostly-dashed chart.

MEASURED, NOT ASSUMED (five real production payloads, `/api/events/{id}/
game-markets` and `/related-futures`, 3.7 KB .. 1.24 MB, 3.58 MB total):

    level 1   9.2x    compress 2.5 ms worst    decompress 0.45 ms worst
    level 6  12.3x    compress 5.5 ms worst

Level 1: the extra 1.3x costs 2.2x the CPU on the read path of the event page.
The read path is faster on net — 0.45 ms of inflate against ~1.1 MB of Heroku
Redis transfer it no longer does.

These tests assert the CODEC CONTRACT, not the ratio on any one payload. The
ratio is a production measurement and belongs in the issue; what a test can
own is that both shapes read, that neither arm can hand the compare-and-set a
type it cannot compare, and that a rollback degrades to a miss.
"""

import json
import zlib
from datetime import datetime, timezone

from app.utils import event_concept_cache as cache_mod


def _big(n: int = 400) -> dict:
    """A payload above the floor that is realistically compressible.

    Repetitive like the real thing — the production payloads are arrays of
    market rows sharing keys and team names — but NOT degenerate: a dict of one
    repeated character would compress ~1000x and prove nothing about JSON.
    """
    return {
        "children": [
            {
                "market_id": i,
                "question": f"Will the New York Jets beat the Green Bay Packers in week {i}?",
                "outcomes": [{"name": "Yes", "probability": 0.5}, {"name": "No", "probability": 0.5}],
                "status": "open",
            }
            for i in range(n)
        ]
    }


# ---------------------------------------------------------------------------
# The two arms
# ---------------------------------------------------------------------------


def test_large_payload_is_stored_compressed_and_round_trips_exactly():
    payload = _big()
    encoded = cache_mod.encode_payload(payload)

    assert encoded.startswith(cache_mod._COMPRESS_PREFIX)
    assert cache_mod.decode_payload(encoded) == payload

    plain = json.dumps(payload, default=str).encode()
    assert len(encoded) < len(plain), "the compressed arm must actually be smaller"


def test_small_payload_stays_plain_json_and_is_byte_identical_to_the_old_codec():
    """Below the floor nothing changes — including the exact bytes stored.

    This is what makes the deploy a non-event for every small tenant of the
    tier: the value it writes after this change is the value it wrote before,
    so a reader on either build sees the same thing.
    """
    payload = {"a": 1, "b": "two"}
    encoded = cache_mod.encode_payload(payload)

    assert not encoded.startswith(cache_mod._COMPRESS_PREFIX)
    assert encoded == json.dumps(payload, default=str).encode()
    assert cache_mod.decode_payload(encoded) == payload


def test_the_floor_is_the_thing_that_decides_which_arm():
    """Pin the boundary, so a future edit to the floor has to come here first."""
    under = cache_mod.encode_payload({"k": "x" * (cache_mod._COMPRESS_MIN_BYTES // 2)})
    over = cache_mod.encode_payload({"k": "x" * (cache_mod._COMPRESS_MIN_BYTES * 2)})

    assert not under.startswith(cache_mod._COMPRESS_PREFIX)
    assert over.startswith(cache_mod._COMPRESS_PREFIX)


# ---------------------------------------------------------------------------
# Both shapes are live at once — neither direction is a migration
# ---------------------------------------------------------------------------


def test_legacy_plain_values_written_by_the_previous_build_still_read():
    """Deploy day: every stored value is plain JSON and must keep serving.

    Both types, because `decode_payload` has always accepted `str` as well as
    `bytes` and the tier's existing totality test pins that.
    """
    payload = _big(50)
    legacy = json.dumps(payload, default=str)

    assert cache_mod.decode_payload(legacy.encode()) == payload
    assert cache_mod.decode_payload(legacy) == payload


def test_a_compressed_value_read_by_an_older_build_is_a_miss_not_an_exception():
    """Rollback: the old `decode_payload` json.loads the deflate bytes and fails.

    It cannot raise — that is the whole point of the function being total — so
    the cost of a rollback is one rebuild per key, not a 500. Reproduced here
    with the OLD decoder rather than asserted about it.
    """
    encoded = cache_mod.encode_payload(_big())

    def _old_decode(raw):
        try:
            text = raw.decode() if isinstance(raw, (bytes, bytearray)) else raw
            value = json.loads(text)
        except Exception:
            return None
        return value if isinstance(value, dict) else None

    assert _old_decode(encoded) is None


def test_decode_stays_total_on_a_corrupt_compressed_value():
    """A truncated or damaged deflate body is a miss, like any other bad value."""
    assert cache_mod.decode_payload(cache_mod._COMPRESS_PREFIX + b"\x78\x01nonsense") is None
    assert cache_mod.decode_payload(cache_mod._COMPRESS_PREFIX) is None
    # And a compressed body that inflates to something that is not a dict.
    not_a_dict = cache_mod._COMPRESS_PREFIX + zlib.compress(b"[1,2,3]", 1)
    assert cache_mod.decode_payload(not_a_dict) is None


def test_the_prefix_cannot_collide_with_a_json_payload():
    """`json.dumps` of a dict always begins `{`, so the two spaces are disjoint."""
    assert not cache_mod._COMPRESS_PREFIX.startswith(b"{")
    for payload in ({}, {"z1:": 1}, _big(5)):
        assert json.dumps(payload, default=str).encode().startswith(b"{")


# ---------------------------------------------------------------------------
# The type invariant the compare-and-set depends on
# ---------------------------------------------------------------------------


def test_encode_returns_bytes_on_both_arms():
    """One type, so `setex_if_unchanged` never compares `str` to `rc.get` bytes.

    A union return is the defect this pins: the CAS compares the value it is
    about to write against the bytes a `read_slot_raw` took, and redis-py hands
    back `bytes`. A `str` on the small arm would make the mirror publish decline
    silently for exactly the payloads that are cheap enough to be common.
    """
    assert isinstance(cache_mod.encode_payload({"a": 1}), bytes)
    assert isinstance(cache_mod.encode_payload(_big()), bytes)


def test_compare_and_set_publishes_a_compressed_mirror_and_declines_on_drift():
    """The CAS is byte-exact over compressed bytes, in both directions."""

    class _Rc:
        def __init__(self, seed=None):
            self.store = {"k": seed} if seed is not None else {}

        def eval(self, script, numkeys, key, absent_flag, expected, ttl, value):
            current = self.store.get(key)
            if absent_flag == "1":
                if current is not None:
                    return 0
            elif current != expected:
                return 0
            self.store[key] = value
            return 1

    encoded = cache_mod.encode_payload(_big())
    assert encoded.startswith(cache_mod._COMPRESS_PREFIX)

    # Still absent -> writes.
    rc = _Rc()
    assert cache_mod.setex_if_unchanged(rc, "k", None, 60, encoded) is True
    assert cache_mod.decode_payload(rc.store["k"]) == _big()

    # Holds exactly what we judged -> writes.
    rc = _Rc(seed=encoded)
    newer = cache_mod.encode_payload(_big(401))
    assert cache_mod.setex_if_unchanged(rc, "k", encoded, 60, newer) is True

    # Somebody moved it -> declines, and leaves the stored value alone.
    other = cache_mod.encode_payload(_big(402))
    rc = _Rc(seed=other)
    assert cache_mod.setex_if_unchanged(rc, "k", encoded, 60, newer) is False
    assert rc.store["k"] == other


# ---------------------------------------------------------------------------
# What Redis is actually given
# ---------------------------------------------------------------------------


def test_the_shared_client_does_not_decode_responses():
    """`decode_responses=True` would make every compressed read a permanent miss.

    redis-py would utf-8 decode the deflate bytes on the way out of `get`, which
    raises, which `read_slot_raw` turns into a miss — so the tier would rebuild
    on every single request while every unit test here stayed green. This module
    already carries that lesson for the `ex` argument (gotcha #39's neighbour);
    this is the same test for the response codec, and it is the reason the
    compressed arm is safe to ship at all.
    """
    from unittest.mock import patch

    import app.tasks.redis_state as rs

    seen = {}

    def _factory(url, **kwargs):
        seen.update(kwargs)
        return object()

    with patch.object(rs, "_CLIENT_CACHE", {}), patch.object(rs.redis, "from_url", _factory):
        rs.get_redis_client()

    assert seen, "the factory was never called — the guard proved nothing"
    assert seen.get("decode_responses") in (None, False)


# ---------------------------------------------------------------------------
# End to end through the tier's own read/write seam
# ---------------------------------------------------------------------------


def test_write_then_read_a_large_payload_through_the_tier():
    """The compressed value survives the envelope validation `read_slot` applies.

    Encoding is only half the contract: a payload that round-trips through
    `json` but not through `stamp_envelope` -> `write_payload` -> `read_slot`
    would still serve nothing.
    """

    class _FakeRedis:
        def __init__(self):
            self.store = {}
            self.ttls = {}

        def get(self, k):
            return self.store.get(k)

        def setex(self, k, ttl, v):
            self.ttls[k] = ttl
            self.store[k] = v.encode() if isinstance(v, str) else v

        def delete(self, k):
            self.ttls.pop(k, None)
            return int(self.store.pop(k, None) is not None)

    rc = _FakeRedis()
    keys = cache_mod.cache_keys("event:nfl:jets-packers")
    stamped = cache_mod.stamp_envelope(
        _big(), created_at=datetime.now(timezone.utc), lifecycle_watermark=None
    )

    cache_mod.write_payload(rc, keys, stamped)

    assert rc.store[keys.primary].startswith(cache_mod._COMPRESS_PREFIX)
    assert rc.store[keys.stale] == rc.store[keys.primary]

    read_back = cache_mod.read_slot(rc, keys.primary)
    assert read_back is not None
    assert read_back["children"] == _big()["children"]
