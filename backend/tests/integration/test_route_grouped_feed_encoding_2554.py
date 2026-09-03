"""#2554 — route-level proof that a cache HIT serves numbers, not strings.

`tests/test_grouped_feed_cache_encoding_2554.py` proves the two cache functions
round-trip a `Decimal` as a number. That is the defect site, but it stops one
step short of the thing a reader sees: a guard that exercises the helpers stays
green if the route stops calling them, or re-encodes on the way out.

So this file drives the real ASGI route and asserts on the RESPONSE BODY. The
seeding is done by the real `_publish_grouped_feed_cache` rather than by
hand-writing JSON into the fake, because hand-written JSON would encode the
payload the way *this file* thinks it should be encoded — which is the one
assumption under test.

The production signature this reproduces, measured 2026-09-03 on a
never-before-requested key:

    ?limit=13  (fresh key -> MISS)   40 numbers,  0 strings
    ?limit=13  (same key  -> HIT )    0 numbers, 40 strings
"""

import json
from decimal import Decimal

from app.routes.futures import _publish_grouped_feed_cache
from app.utils import request_cache as _rc
from app.utils.grouped_feed_cache import (
    GROUPED_FEED_CACHE_HEADER,
    grouped_feed_cache_key,
)

KEY = grouped_feed_cache_key(category=None, sport=None, sports_only=False, limit=20)


class _Redis:
    def __init__(self):
        self._store: dict[str, str] = {}

    async def get(self, key):
        return self._store.get(key)

    async def setex(self, key, ttl, body):
        self._store[key] = body
        return True


async def _async(value):
    return value


def _install(monkeypatch, fake):
    _rc._reset_last_good_for_tests()
    _rc._reset_inflight_for_tests()
    _rc._reset_shared_client_for_tests()
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(fake))


def _payload(probability):
    return {
        "feed": [
            {
                "type": "market",
                "market": {
                    "id": 59863411,
                    "name": "Omega European Masters - Winner",
                    "outcomes": [{"name": "Yannik Paul", "probability": probability}],
                },
            }
        ],
        "total_grouped": 0,
        "total_ungrouped": 1,
        "group_counts": {
            "stat_prop": 0,
            "playoff_progression": 0,
            "threshold": 0,
        },
    }


def _served_probability(body):
    return body["feed"][0]["market"]["outcomes"][0]["probability"]


async def test_a_cache_hit_serves_a_numeric_probability(client, mock_db, monkeypatch):
    """RED ON MASTER: the response carries the string "0.682560".

    Asserted on `resp.json()` — the bytes the browser parses — not on the value
    the helper returned, so a later re-encode between the cache read and the
    response cannot reopen this quietly.
    """
    fake = _Redis()
    _install(monkeypatch, fake)
    await _publish_grouped_feed_cache(KEY, _payload(Decimal("0.682560")))

    resp = await client.get("/api/futures/grouped-feed?limit=20")

    assert resp.status_code == 200
    assert resp.headers[GROUPED_FEED_CACHE_HEADER] == "hit"

    value = _served_probability(resp.json())
    assert not isinstance(value, str), (
        f"the route served probability as {type(value).__name__} {value!r}; "
        "/sports renders that as an em dash beside a correctly-sized bar (#2554)"
    )
    assert value == 0.68256


async def test_the_raw_bytes_carry_a_json_number_not_a_quoted_string(
    client, mock_db, monkeypatch
):
    """The type check above passes if something re-parses the string to a float.

    This one reads the serialized text, so it pins that the wire format itself is
    a JSON number — `"probability": 0.68256` and never `"probability": "0.682560"`.
    That is what `Number.isFinite` on the client actually consumes.
    """
    fake = _Redis()
    _install(monkeypatch, fake)
    await _publish_grouped_feed_cache(KEY, _payload(Decimal("0.682560")))

    resp = await client.get("/api/futures/grouped-feed?limit=20")

    text = resp.text
    assert '"probability": "' not in text.replace(", ", ", ")
    assert '"probability":"' not in text
    assert json.loads(text)["feed"][0]["market"]["outcomes"][0]["probability"] == 0.68256


async def test_the_hit_and_the_stale_hit_agree(client, mock_db, monkeypatch):
    """Both entries are written from one body; a fix reaching only the fresh key
    would still print an em dash for anyone served the stale twin."""
    fake = _Redis()
    _install(monkeypatch, fake)
    await _publish_grouped_feed_cache(KEY, _payload(Decimal("0.19648")))

    # Drop the fresh entry so the route must fall through to `:stale`.
    fake._store.pop(KEY)

    resp = await client.get("/api/futures/grouped-feed?limit=20")

    assert resp.status_code == 200
    assert resp.headers[GROUPED_FEED_CACHE_HEADER] == "stale_hit"
    assert not isinstance(_served_probability(resp.json()), str)


async def test_CONTROL_a_float_payload_is_served_unchanged(
    client, mock_db, monkeypatch
):
    """Green on master too. Pins that the fix did not start rewriting values that
    were already correct — the miss path's own output must survive a round trip."""
    fake = _Redis()
    _install(monkeypatch, fake)
    await _publish_grouped_feed_cache(KEY, _payload(0.42))

    resp = await client.get("/api/futures/grouped-feed?limit=20")

    assert resp.status_code == 200
    assert _served_probability(resp.json()) == 0.42


async def test_CONTROL_a_null_probability_is_still_served_as_null(
    client, mock_db, monkeypatch
):
    """Green on master too, and load-bearing: the live payload carries exactly one
    `None` beside the 54 broken values, and an unpriced outcome must keep saying
    so rather than acquiring a 0.0."""
    fake = _Redis()
    _install(monkeypatch, fake)
    await _publish_grouped_feed_cache(KEY, _payload(None))

    resp = await client.get("/api/futures/grouped-feed?limit=20")

    assert resp.status_code == 200
    assert _served_probability(resp.json()) is None
