"""LAT-P221 (#2971) — the feed's most expensive artifact must FIT the wire.

WHAT WENT WRONG, AND WHY NOTHING CAUGHT IT.

`futures.market_load` — the hydrated Discover candidate base — is the single
biggest stage of a cold `/api/feed`. LAT-P174 made it a principal-independent
shared artifact precisely because every principal rebuilds the identical rows.
Then it silently stopped being shared, and stayed that way for weeks.

It did not break. It ROTTED. LAT-P174 sized the artifact at ~1.2 MB against a
2 MB cap, for 700 markets and 2,223 outcomes. The outcome population is now
6,904 — 3.1x — so the envelope is 2.79 MB, `_publish_cross_worker` refuses it on
every build, and the artifact never leaves the worker that made it. Measured in
production 2026-09-04: `x-feed-shared` listed `canonical_counts,concepts` and
never `market_load`, and the only reuse ever observed for it was
`x-feed-shared-tier: local`.

The cost was the whole cold feed. `futures.market_load` was 692-775 ms of a
1,537-1,982 ms miss; on the requests that happened to reuse it from the building
worker's own L1 the same stage cost 68-71 ms and the whole request 735-774 ms.
47% of production feed requests miss.

**Every guard in the suite tested that the cache WORKS. None tested that the
artifact FITS.** So the size guards passed on toy fixtures forever while the one
artifact they existed for was refused in production on every single build. That
is the class this file closes: a bound that is only ever exercised against
fixtures smaller than the thing it bounds is not a bound, it is a decoration.

HOW TO RE-MEASURE THE SHAPE BELOW (it is a population, so it moves):

    POST /api/admin/db-query
    SELECT count(*) FROM futures_markets
     WHERE status='open' AND event_id IS NULL
       AND (resolution_date IS NULL OR resolution_date >= now())
       AND name NOT LIKE '%% vs %%' AND name NOT LIKE '%% vs. %%'
    -- and the outcome count / mean text widths for the top 700 of those,
    -- ordered by market_tier ASC NULLS LAST, resolution_date ASC NULLS LAST.

When this file goes red, the answer is NOT to raise a cap. It is that the
artifact outgrew its wire and needs a narrower one (drop a column, compact the
row form, or chunk the publish).
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.models.models import FuturesMarket, FuturesOutcome
from app.utils import futures_market_snapshot as fs
from app.utils import principal_independent_cache as pic

#: Tz-aware and microsecond-bearing, because that is what the columns hold and
#: the isoformat length is what the codec pays for.
_A_TIMESTAMP = datetime(2026, 9, 4, 4, 47, 12, 123456, tzinfo=timezone.utc)

# --- the measured production shape, 2026-09-04 ------------------------------
#: Candidate-base size. The eight Discover pools are capped at 80/80/80/120/100/
#: 100/80/80 = 720 ids before dedup, so 700 is the population's real ceiling and
#: not an estimate.
PROD_MARKETS = 700
#: Measured, not derived: 6,904 outcomes across those 700 markets.
PROD_OUTCOMES = 6_904
#: Mean bytes of the variable-width text a row actually carries (names, external
#: ids, urls, hooks, and `market_metadata`, which dominates the market row).
PROD_MARKET_TEXT_BYTES = 955
PROD_OUTCOME_TEXT_BYTES = 68

#: The measured envelope of the REAL artifact, encoded by this module's own
#: codec over 40 real production rows and extrapolated to the shape above. It is
#: what `test_the_fixture_reproduces_the_measured_artifact` holds the fixture to.
MEASURED_ENVELOPE_BYTES = 2_928_973
#: Fraction of nullable columns left `None`. CALIBRATED, not chosen: it is the
#: one free parameter, and it is set to whatever reproduces
#: `MEASURED_ENVELOPE_BYTES`. Re-calibrate it when the shape constants move.
NULL_RATE = 0.25

#: The alarm fires BEFORE breakage, not at it. A guard that goes red at the
#: moment the share stops working has told us nothing the latency would not
#: have; the point is to be red while there is still room to fix it. 1.5 puts
#: the alarm at a 4.0 MB envelope against a 6 MB bound — today's artifact is
#: 2.79 MB, so ~1.4x growth trips this file and ~2.1x actually breaks the share.
HEADROOM_FACTOR = 1.5

#: Plausibility band for the fixture's own compression ratio. The storage
#: assertion below runs the fixture through the REAL `wire_encode`, which makes
#: it sensitive to how compressible this file's filler happens to be — so the
#: band is what stops a future edit buying a green with easier text. Measured:
#: 4.2x on the real artifact, 3.8x on the fixture, both at zlib level 1.
COMPRESSION_RATIO_BAND = (3.0, 6.0)


def _texty(rng: random.Random, n_bytes: int) -> str:
    """`n_bytes` of text with prose-like — not degenerate, not random — entropy.

    Both failure modes matter. Repeated filler compresses ~50x and would make
    every storage assertion below vacuously true; `os.urandom` compresses not at
    all and would make them unmeetable. Neither would be measuring the artifact.
    """
    out: list[str] = []
    size = 0
    while size < n_bytes:
        word = rng.choice(_WORDS) + str(rng.randrange(1000))
        out.append(word)
        size += len(word) + 1
    return " ".join(out)[:n_bytes]


_WORDS = (
    "winner championship market open close outright tournament round leader "
    "polymarket kalshi series playoff conference division award nominee "
    "election primary candidate senate governor forecast landfall category"
).split()


def _column_kinds(model, columns: tuple[str, ...]) -> list[str]:
    """One kind per column position, READ OFF THE MODEL rather than listed here.

    🔴 This is the load-bearing half of the fixture, and the reason it is
    introspected instead of transcribed. Most of the artifact's bytes are not
    its text — they are the wire codec's per-value tags, and only `Decimal` and
    `datetime` carry one (`{"__pic__":"dec","v":"0.155000"}` is 31 bytes to
    express six characters). A fixture that leaves those columns `None` encodes
    to 58% of the real artifact, sails under the cap the real one is breaching,
    and reports green on the exact defect it was written for. Measured: it did.

    Reading the types off `FuturesMarket` / `FuturesOutcome` also means a column
    added to `MARKET_COLUMNS` grows this fixture on the same commit, instead of
    quietly shrinking it relative to production.
    """
    from sqlalchemy import DateTime, Integer, Numeric

    kinds = []
    for name in columns:
        col_type = model.__table__.columns[name].type
        if isinstance(col_type, DateTime):
            kinds.append("dt")
        elif isinstance(col_type, Numeric) and not isinstance(col_type, Integer):
            # `Numeric` is the Decimal one; SQLAlchemy's `Float` subclasses it
            # and is NOT (a float needs no tag), so check the python type.
            kinds.append("dec" if col_type.python_type is Decimal else "num")
        elif isinstance(col_type, Integer):
            kinds.append("int")
        elif name == "market_metadata":
            kinds.append("json")
        else:
            kinds.append("str")
    return kinds


def _row_at_kinds(
    rng: random.Random, kinds: list[str], nullable: list[bool], text_budget: int
) -> list:
    """One positional row whose values have production's TYPES and text width."""
    text_cols = [i for i, k in enumerate(kinds) if k in ("str", "json")] or [0]
    per_text = max(1, text_budget // len(text_cols))
    row: list = []
    for i, kind in enumerate(kinds):
        if nullable[i] and rng.random() < NULL_RATE:
            # A `None` is four bytes and no tag. Production rows are full of
            # them (no image, no hook, no closing line), so a fixture that
            # fills every nullable column is not a heavier version of the real
            # artifact — it is a different one.
            row.append(None)
        elif kind == "dt":
            row.append(_A_TIMESTAMP)
        elif kind == "dec":
            row.append(Decimal(f"0.{rng.randrange(100000, 999999)}"))
        elif kind == "num":
            row.append(rng.random())
        elif kind == "int":
            row.append(rng.randrange(1, 900_000))
        elif kind == "json":
            row.append({"shape": _texty(rng, per_text), "v": 2, "confidence": "low"})
        else:
            row.append(_texty(rng, per_text))
    return row


#: The kinds of `DERIVED_MARKET_COLUMNS`, declared BY NAME because they are not
#: on `FuturesMarket` and `_column_kinds` therefore cannot introspect them. A
#: derived column added without a line here is a `KeyError` in this fixture, not
#: a silently-cheap `str` that shrinks the artifact relative to production —
#: which is the whole reason the loaded kinds are introspected in the first
#: place. `price_polled_at` is a `datetime`, and a datetime is a TAGGED value on
#: this wire (~31 bytes of codec around it), so it must be measured as one.
_DERIVED_KINDS = {"price_polled_at": "dt"}


def _production_scale_payload() -> dict:
    """A `to_plain`-shaped artifact at the measured production shape."""
    rng = random.Random(20260904)
    market_kinds = _column_kinds(FuturesMarket, fs.MARKET_COLUMNS) + [
        _DERIVED_KINDS[name] for name in fs.DERIVED_MARKET_COLUMNS
    ]
    outcome_kinds = _column_kinds(FuturesOutcome, fs.OUTCOME_COLUMNS)
    # Derived values are nullable by construction: `to_plain` writes `None` for
    # a market the caller's map does not cover (a market with no outcome rows).
    market_null = _nullable(FuturesMarket, fs.MARKET_COLUMNS) + [True] * len(
        fs.DERIVED_MARKET_COLUMNS
    )
    outcome_null = _nullable(FuturesOutcome, fs.OUTCOME_COLUMNS)
    per_market = PROD_OUTCOMES // PROD_MARKETS
    remainder = PROD_OUTCOMES - per_market * PROD_MARKETS
    rows = []
    for i in range(PROD_MARKETS):
        n = per_market + (1 if i < remainder else 0)
        rows.append(
            [
                _row_at_kinds(rng, market_kinds, market_null, PROD_MARKET_TEXT_BYTES),
                [
                    _row_at_kinds(
                        rng, outcome_kinds, outcome_null, PROD_OUTCOME_TEXT_BYTES
                    )
                    for _ in range(n)
                ],
                None,
            ]
        )
    return {"v": fs.SNAPSHOT_SCHEMA_VERSION, "rows": rows}


def _nullable(model, columns: tuple[str, ...]) -> list[bool]:
    return [
        bool(model.__table__.columns[name].nullable) and name != "id"
        for name in columns
    ]


@pytest.fixture(name="payload", scope="module")
def _payload():
    return _production_scale_payload()


def test_the_fixture_is_the_measured_production_shape(payload):
    """A control. If this fixture drifts off the population it is standing in
    for, every assertion below is about a different artifact."""
    assert len(payload["rows"]) == PROD_MARKETS
    assert sum(len(r[1]) for r in payload["rows"]) == PROD_OUTCOMES
    pic.assert_plain_data(payload)  # must not raise, or it is not shareable


def test_the_fixture_reproduces_the_measured_artifact(payload):
    """The control that makes every size assertion below mean something.

    The first version of this fixture left the nullable `Decimal` and `datetime`
    columns empty and encoded to 58% of the real artifact — green under the very
    cap production was breaching. A synthetic fixture standing in for a measured
    population has to be held to the measurement, or it is only testing itself.
    """
    envelope = _envelope_bytes(payload)
    ratio = envelope / MEASURED_ENVELOPE_BYTES

    assert 0.9 <= ratio <= 1.1, (
        f"the fixture encodes to {envelope:,} B against a measured "
        f"{MEASURED_ENVELOPE_BYTES:,} B ({ratio:.0%}). Re-calibrate NULL_RATE, "
        f"or re-measure MEASURED_ENVELOPE_BYTES if the population moved."
    )


def test_the_fixture_compresses_like_real_data(payload):
    """And the other way a synthetic fixture can buy a green: filler that
    compresses better than prose. The storage assertion runs the real
    `wire_encode`, so its verdict is only as honest as this band."""
    envelope = json.dumps(_envelope(payload), separators=(",", ":"), ensure_ascii=False)
    ratio = len(envelope.encode()) / len(pic.wire_encode(envelope))

    low, high = COMPRESSION_RATIO_BAND
    assert low <= ratio <= high, (
        f"the fixture compresses {ratio:.1f}x, outside the {low}-{high}x band "
        f"real market_load rows sit in — the storage assertion is measuring "
        f"this file's filler, not the artifact."
    )


def test_a_production_scale_market_load_fits_the_decode_budget(payload):
    """The bound that was actually being violated. 2.79 MB against 2 MB."""
    envelope = _envelope_bytes(payload)

    assert envelope <= pic.MAX_ENVELOPE_BYTES / HEADROOM_FACTOR, (
        f"market_load encodes to {envelope:,} B; the decode budget is "
        f"{pic.MAX_ENVELOPE_BYTES:,} B and this guard wants {HEADROOM_FACTOR}x "
        f"headroom. The artifact outgrew its wire — narrow the wire, do not "
        f"raise the cap (gotcha #38: the parse holds the GIL)."
    )


def test_a_production_scale_market_load_fits_the_storage_budget(payload):
    """The other bound: what Redis has to hold, through the real wire."""
    envelope = json.dumps(_envelope(payload), separators=(",", ":"), ensure_ascii=False)
    stored = len(pic.wire_encode(envelope))

    assert stored <= pic.MAX_STORED_BYTES / HEADROOM_FACTOR, (
        f"market_load stores {stored:,} B; the storage budget is "
        f"{pic.MAX_STORED_BYTES:,} B and Redis is a shared 100 MB LRU that "
        f"Celery's state lives in too."
    )


@pytest.mark.asyncio
async def test_a_production_scale_market_load_is_published_not_refused(
    payload, monkeypatch
):
    """End to end through the real publish path — the assertion whose absence
    is the whole reason this file exists.

    The two size tests above are arithmetic on the same numbers; this one proves
    the arithmetic is about the code that runs.
    """
    stored: dict[str, object] = {}

    class _Redis:
        async def set(self, key, value, ex=None):
            stored[key] = value
            return True

    monkeypatch.setattr(pic, "_shared_redis_client", _fake_client(_Redis()))
    pic.clear_shared_builds()

    await pic._publish_cross_worker("market_load", ("market_load", 2, "d"), payload, 60)

    assert stored, (
        "a production-scale market_load was REFUSED by _publish_cross_worker — "
        "it will only ever be reused by the worker that built it, which is the "
        "692-775 ms defect LAT-P221 fixed"
    )
    assert pic.shared_build_stats()["cross_worker_publish_refused"] == 0
    blob = next(iter(stored.values()))
    assert isinstance(blob, bytes)
    assert json.loads(pic.wire_decode(blob))["ns"] == "market_load"


@pytest.mark.asyncio
async def test_the_published_artifact_round_trips_byte_for_byte(payload, monkeypatch):
    """Fitting is not enough — the reader has to get the same rows back.

    `market_load` rows are what the scoring loop reads. A wire that fits and
    lies is worse than one that refuses (the module docstring's own argument for
    the tagged codec), so the compression layer gets the same standard.
    """
    stored: dict[str, object] = {}

    class _Redis:
        async def set(self, key, value, ex=None):
            stored[key] = value
            return True

        async def get(self, key):
            return stored.get(key)

    monkeypatch.setattr(pic, "_shared_redis_client", _fake_client(_Redis()))
    pic.clear_shared_builds()
    key = ("market_load", 2, "roundtrip")

    await pic._publish_cross_worker("market_load", key, payload, 60)
    ok, value = await pic._read_cross_worker("market_load", key, 60)

    assert ok, "the artifact we just published did not read back"
    assert value == payload
    assert fs.is_snapshot_payload(value), "it read back in an unusable shape"


def test_the_shared_redis_client_hands_back_bytes_not_str():
    """The wire is BINARY now, and that is a dependency worth a guard.

    `wire_encode` returns a zlib stream. If the shared async client were ever
    built with `decode_responses=True`, redis-py would UTF-8-decode that stream
    on the way out and the value would arrive unrecoverable — `wire_decode`
    would return `None` for every read, every reader would rebuild, and the feed
    would go straight back to 692-775 ms with nothing failing and nothing
    logged. That is the same silence LAT-P221 is about, so it gets a test rather
    than a comment.
    """
    from app.tasks.redis_state import get_async_redis_client

    client = get_async_redis_client()  # constructing does not connect
    kwargs = client.connection_pool.connection_kwargs

    assert not kwargs.get("decode_responses"), (
        "the shared Redis client decodes responses, which corrupts the "
        "compressed shared-artifact wire into an unrecoverable str"
    )


def _envelope(payload: dict) -> dict:
    """The envelope `_publish_cross_worker` builds, built the same way."""
    return {
        "v": 1,
        "ns": "market_load",
        "k": "('market_load', 2, 'digest')",
        "stored_wall": 1_788_000_000.0,
        "payload": pic.encode_shared_payload(payload),
    }


def _envelope_bytes(payload: dict) -> int:
    envelope = json.dumps(_envelope(payload), separators=(",", ":"), ensure_ascii=False)
    return len(envelope.encode("utf-8", "replace"))


def _fake_client(redis):
    async def _get_client():
        return redis

    return _get_client
