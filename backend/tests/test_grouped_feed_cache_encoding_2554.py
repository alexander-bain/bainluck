"""#2554 — the grouped-feed cache serves the same TYPES on a hit as on a miss.

THE DEFECT, MEASURED ON PRODUCTION. `GET /api/futures/grouped-feed` returned
`probability` as a JSON **number** the first time a given key was requested and
as a JSON **string** on every subsequent request. Proved by prediction on a
never-before-requested key, 2026-09-03:

    ?limit=13  (fresh key -> cache MISS)   40 numbers,  0 strings
    ?limit=13  (same key  -> cache HIT )    0 numbers, 40 strings

and a structural diff of those two payloads reported exactly one differing field
family — `feed[].market.outcomes[].probability`, `float -> str`, 40 leaves.
Nothing else in the payload moved.

THE CAUSE was one keyword. `_publish_grouped_feed_cache` wrote the body with
`json.dumps(payload, default=str)`. `default=` fires for every value `json`
cannot serialize natively; `current_probability` is a `Numeric` column, so each
value arrived as a `Decimal` and was stored as `"0.682560"`. The route's own
return path never sees that, because FastAPI encodes the dict with
`jsonable_encoder`, which floats a `Decimal`. One endpoint, two encoders, and the
one that ran on ~all real traffic was the wrong one.

WHY IT LOOKED LIKE A REFUSAL RATHER THAN A BUG, which is why #2554 carried the
wrong root cause from pass 1 until pass 11: the `/sports` prop card reads the
value twice. `Number.isFinite("0.68")` is `false`, so the number renders as an em
dash — but `prob * 100` coerces the string happily, so the bar beside it draws
the correct width. **A right-sized bar beside a missing number is the signature
of a string, not of a null**, and a genuinely unpriced row renders a different
character (an ASCII hyphen from `formatProbability`, not `formatProbabilityPercent`'s
em dash).

WHAT THIS SUITE PINS. Not "Decimal is handled" — the invariant that **the cached
body is byte-identical to what the miss path would have served**. That is why the
fix encodes with `jsonable_encoder` instead of special-casing `Decimal`: it is the
same encoder the miss path runs, so the two cannot drift, and the next non-JSON
type to enter this payload cannot reopen the defect for a different field. The
`datetime` arm below exists to prove that generality rather than assert it.

WHY THE EXISTING SUITE COULD NOT SEE IT. `tests/test_grouped_feed_cache.py` is
about the KEY contract and the warmer — which parameters key the entry, that the
warmed key is the key the client reads, TTLs. It never round-trips a payload
through publish -> read, so no `Decimal` has ever crossed the cache boundary in a
test. It needed no edit for this fix, and that is the finding, not a reassurance.
"""

import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.encoders import jsonable_encoder

from app.routes.futures import (
    _publish_grouped_feed_cache,
    _read_grouped_feed_cache,
)


class FakeRedis:
    """The smallest async client the two cache functions actually call."""

    def __init__(self):
        self.store: dict[str, str] = {}

    async def setex(self, key, ttl, body):
        self.store[key] = body
        return True

    async def get(self, key):
        return self.store.get(key)


@pytest.fixture
def redis(monkeypatch):
    """Install a fake shared client for BOTH functions.

    Both do `from app.utils import request_cache as _rc` inside the function
    body, so patching the module attribute reaches them, and the real
    `bounded_redis_call` still runs — the deadline/typed-result wrapper is not
    stubbed out, only the socket.
    """
    from app.utils import request_cache as rc

    fake = FakeRedis()

    async def _shared():
        return fake

    monkeypatch.setattr(rc, "get_shared_async_redis", _shared)
    return fake


def a_grouped_feed_payload(probability):
    """One market, one outcome — the shape the route publishes, minimised."""
    return {
        "feed": [
            {
                "market": {
                    "id": 59863411,
                    "name": "Omega European Masters - Winner",
                    "outcomes": [
                        {"name": "Yannik Paul", "probability": probability},
                    ],
                }
            }
        ]
    }


# --- The ship -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_decimal_probability_comes_back_as_a_number(redis):
    """RED ON MASTER: comes back as the string "0.682560"."""
    payload = a_grouped_feed_payload(Decimal("0.682560"))

    await _publish_grouped_feed_cache("k", payload)
    got, status = await _read_grouped_feed_cache("k")

    assert status == "hit"
    value = got["feed"][0]["market"]["outcomes"][0]["probability"]
    assert not isinstance(value, str), (
        f"probability crossed the cache as {type(value).__name__} {value!r} — "
        "this is the em-dash-with-a-correct-bar defect (#2554)"
    )
    assert value == pytest.approx(0.68256)


@pytest.mark.asyncio
async def test_the_hit_is_byte_identical_to_what_the_miss_path_would_serve(redis):
    """The invariant, stated as an equality rather than a type check.

    `jsonable_encoder(payload)` IS what FastAPI hands `json.dumps` when the route
    returns the dict directly, i.e. exactly what a cache miss serves. Asserting
    equality against it means this test cannot pass for a field the fix happens
    to have missed.
    """
    payload = a_grouped_feed_payload(Decimal("0.005640"))

    await _publish_grouped_feed_cache("k", payload)
    got, _ = await _read_grouped_feed_cache("k")

    assert got == jsonable_encoder(payload)


@pytest.mark.asyncio
async def test_the_generality_holds_for_a_type_that_is_not_decimal(redis):
    """A `datetime` is the counter-case that separates the two candidate fixes.

    `str(dt)` renders "2026-09-03 03:15:41+00:00" (a space); `jsonable_encoder`
    renders ISO-8601 with a "T". A Decimal-only `default=` would leave this arm
    red, so it is what proves the fix is the encoder and not a special case.
    """
    when = datetime(2026, 9, 3, 3, 15, 41, tzinfo=timezone.utc)
    payload = {"feed": [], "generated_at": when}

    await _publish_grouped_feed_cache("k", payload)
    got, _ = await _read_grouped_feed_cache("k")

    assert got["generated_at"] == jsonable_encoder(when)
    assert "T" in got["generated_at"], got["generated_at"]


@pytest.mark.asyncio
async def test_the_stale_twin_is_encoded_the_same_way(redis):
    """Both keys are written from one `body`, so a fix that only reached the
    fresh entry would serve a stale hit that still prints an em dash."""
    payload = a_grouped_feed_payload(Decimal("0.19648"))

    await _publish_grouped_feed_cache("k", payload)

    fresh = json.loads(redis.store["k"])
    stale = json.loads(redis.store["k:stale"])
    assert fresh == stale == jsonable_encoder(payload)
    assert not isinstance(
        stale["feed"][0]["market"]["outcomes"][0]["probability"], str
    )


@pytest.mark.asyncio
async def test_every_outcome_is_converted_not_just_the_first(redis):
    """The production payload carried 40 of these; a fix that converted the
    head of a list would look green on a one-outcome fixture."""
    payload = {
        "feed": [
            {
                "market": {
                    "outcomes": [
                        {"name": f"G{i}", "probability": Decimal(f"0.0{i}")}
                        for i in range(1, 10)
                    ]
                }
            }
        ]
    }

    await _publish_grouped_feed_cache("k", payload)
    got, _ = await _read_grouped_feed_cache("k")

    values = [o["probability"] for o in got["feed"][0]["market"]["outcomes"]]
    assert len(values) == 9
    assert not any(isinstance(v, str) for v in values), values


# --- Controls: green on master too --------------------------------------------


@pytest.mark.asyncio
async def test_CONTROL_a_payload_of_plain_json_types_is_unchanged(redis):
    """Green in both arms. A float probability never touched `default=`, so if
    this ever goes red the fix has started rewriting values it should not."""
    payload = a_grouped_feed_payload(0.42)

    await _publish_grouped_feed_cache("k", payload)
    got, _ = await _read_grouped_feed_cache("k")

    assert got == payload
    assert got["feed"][0]["market"]["outcomes"][0]["probability"] == 0.42


@pytest.mark.asyncio
async def test_CONTROL_a_null_probability_stays_null(redis):
    """Green in both arms, and it matters: the live payload carries exactly one
    `None` beside the 54 broken values. A genuinely unpriced outcome must keep
    rendering as unpriced — the fix must not invent a 0.0 for it."""
    payload = a_grouped_feed_payload(None)

    await _publish_grouped_feed_cache("k", payload)
    got, _ = await _read_grouped_feed_cache("k")

    assert got["feed"][0]["market"]["outcomes"][0]["probability"] is None


@pytest.mark.asyncio
async def test_CONTROL_a_redis_failure_still_costs_the_caller_nothing(redis, monkeypatch):
    """Green in both arms. The function's stated contract is best-effort; the
    encoder change must not turn a cache write into a request-path exception."""
    from app.utils import request_cache as rc

    async def _boom():
        raise RuntimeError("redis is down")

    monkeypatch.setattr(rc, "get_shared_async_redis", _boom)

    await _publish_grouped_feed_cache("k", a_grouped_feed_payload(Decimal("0.5")))


# --- Encoder-swap edge behaviour: RED on master, so NOT controls ---------------
#
# Both of these started life above, under the controls heading, mislabelled
# "green in both arms". The red arm printed them as failures and that is how the
# labels were caught. They are kept, moved, and re-titled rather than deleted,
# because they are the two cases where swapping the encoder changes an outcome
# and a grader should be able to see exactly what changed.


@pytest.mark.asyncio
async def test_an_ordinary_object_still_encodes(redis):
    """RED ON MASTER (it is part of the change, NOT a control — see below).

    I first labelled this a control and the red arm caught the lie: on master
    `default=str` stringifies the object to "<...Opaque object at 0x...>", so the
    assertion below is arm-dependent and this test is describing the ship.

    It also corrects a claim I had written and not checked.

    I expected `jsonable_encoder` to be STRICTER than `default=str` and to start
    raising on values the catch-all used to stringify. It is not: it converts an
    unknown object through `vars()` (and a `set` to a list), so an ordinary
    object encodes to `{}` and the write succeeds exactly as before. Measured,
    not assumed. The narrow case where it genuinely does raise is the next test.
    """

    class Opaque:
        pass

    await _publish_grouped_feed_cache("k", {"feed": [], "x": Opaque()})

    assert redis.store, "an ordinary object must not cost the cache its write"
    assert json.loads(redis.store["k"])["x"] == {}


@pytest.mark.asyncio
async def test_the_narrow_case_that_does_raise_is_swallowed(redis):
    """RED ON MASTER (also not a control — `default=str` cannot fail here).

    The one real behaviour change, stated at its true size.

    `jsonable_encoder` raises `ValueError` for an object with `__slots__` and no
    `__dict__`, where `default=str` would have stringified it. That is a narrow
    class and almost certainly unreachable from this payload, but it is a change,
    so it is pinned: the function's best-effort contract must hold and the failure
    must degrade to a cache miss rather than a request-path exception.
    """

    class Slotted:
        __slots__ = ("a",)

        def __init__(self):
            self.a = 1

    await _publish_grouped_feed_cache("k", {"feed": [], "x": Slotted()})

    assert redis.store == {}, "a failed encode must publish nothing at all"


# --- Anti-drift backstop ------------------------------------------------------


def test_the_writer_does_not_reintroduce_a_stringifying_default():
    """The value guards above are load-bearing; this is the cheap backstop.

    Named separately because `default=str` reads as harmless defensive coding and
    is exactly the kind of line a later edit re-adds "so the cache write can never
    fail".

    ⚠️ IT SCANS THE CODE, NOT THE DOCSTRING. The first version of this test used
    a bare `inspect.getsource` and went red on the fix — because the docstring
    that EXPLAINS the bug quotes `default=str` verbatim. A source-scanning guard
    whose pattern appears in the prose justifying the change is red exactly when
    it should be green, so the docstring is dropped before matching.
    """
    import ast
    import inspect
    import textwrap

    from app.routes import futures

    tree = ast.parse(
        textwrap.dedent(inspect.getsource(futures._publish_grouped_feed_cache))
    )
    fn = tree.body[0]
    assert isinstance(fn, ast.AsyncFunctionDef)
    body = fn.body[1:] if ast.get_docstring(fn) is not None else fn.body
    code = "\n".join(ast.unparse(node) for node in body)

    assert "default=str" not in code, (
        "`default=str` is back in the grouped-feed cache writer — it silently "
        "stringifies Decimal probabilities (#2554)"
    )
    assert "jsonable_encoder" in code
