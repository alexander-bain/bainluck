"""#7548 — a ~$45 trade print is not Kyle Larson's championship probability.

PILLAR: TRUTH. SHIP: the NASCAR championship chart and hero sparkline show the
supported price journey without an unsupported spike, while a genuine near-100%
move still draws.

WHAT IS REPLAYED, AND WHAT KIND OF EVIDENCE EACH PIECE IS
----------------------------------------------------------
``tests/fixtures/nascar_trade_print_7548/`` — every file is a saved public
response, byte-for-byte except the one marked reduced (see PROVENANCE.md there):

* ``gamma-event-741506.json`` — Gamma ``/events/741506``, 2026-09-20T18:49:33Z.
  SOURCE BYTES. The healthy-field control and the identity map.
* ``dataapi-trades-larson.reduced.json`` — the venue's tape for Larson's
  condition. SOURCE BYTES (wallet/profile fields dropped). Holds the 0.989 print.
* ``clob-prices-history-larson-yes.json`` — the venue's own minute series for
  Larson's YES token across the day. SOURCE BYTES. Never above 0.586.
* ``bainluck-history-56947465.json`` / ``bainluck-detail-56947465.json`` — what
  production served at 18:49Z. SAVED EVIDENCE of the served 0.989.

THE ONE RECONSTRUCTION, stated once so nobody mistakes it for a capture: Gamma's
payload at our capture instant (2026-09-19T20:31:08Z) was not retained by anyone.
``_capture_instant_event`` rebuilds it from the real bytes by overriding four
fields on Larson's market only. ``lastTradePrice`` is the tape's. The midpoint is
the venue's own (0.3815, CLOB 20:31:15Z). The split of that midpoint into a bid
and an ask is NOT known — so the writer test is parametrized over every cent-grid
book that (a) has that midpoint and (b) could have produced a stored 0.989 at
all, and ``test_V2`` proves from arithmetic alone that none of them has an ask
within reach of the print. That is a SYNTHETIC REPLAY of a venue-evidenced state;
the stored row's own ``yes_bid``/``yes_ask`` (one bounded export, see REPORT.md)
is what upgrades it to a capture.

Real Postgres and real Redis, created by ``APPLY-AND-TEST.sh`` on loopback with a
minted nonce. The refusal guards are #7351's, restated: a skip is not a pass, and
this file will not touch a service it cannot prove is disposable.
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

DB_URL = os.environ.get("NASCAR_7548_DATABASE_URL")
REDIS_URL = os.environ.get("NASCAR_7548_REDIS_URL")
NONCE = os.environ.get("NASCAR_7548_NONCE")

pytestmark = pytest.mark.skipif(
    not (DB_URL and REDIS_URL),
    reason=(
        "set NASCAR_7548_DATABASE_URL / NASCAR_7548_REDIS_URL / NASCAR_7548_NONCE "
        "(APPLY-AND-TEST.sh provisions them and REFUSES a skip)"
    ),
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "nascar_trade_print_7548"
SENTINEL_TABLE = "nascar_7548_disposable_sentinel"
SENTINEL_KEY = "nascar7548:disposable-sentinel"

EVENT_ID = "741506"
MARKET_ID = 56947465
LARSON_OUTCOME_ID = 211437562
LARSON_CONDITION = "0xd8e4484971dc78f997f3ecb75c41f942f2b2f0d2f12ecc827770f42ade8a7c85"
LARSON_YES_TOKEN = (
    "80387649361663967783720414743451746455285579684363190637559405133484382266840"
)
BAD_STAMP = "2026-09-19T20:31:08.128201+00:00"
PRINT = 0.989
#: The venue's own midpoint nearest our capture instant (CLOB, 20:31:15Z).
VENUE_MID_AT_CAPTURE = 0.3815


def _fx(name: str):
    return json.loads((FIXTURES / name).read_text())


# ---------------------------------------------------------------------------
# Disposable-service guards (the #7351 pattern)
# ---------------------------------------------------------------------------


def _refuse(msg: str):
    pytest.fail(f"REFUSING TO TOUCH THESE SERVICES: {msg}", pytrace=False)


def _pg_host(url: str) -> str:
    parsed = urlparse(url.replace("postgresql+asyncpg", "postgresql", 1))
    q = parse_qs(parsed.query)
    return (q.get("host") or [parsed.hostname or ""])[0]


def _is_loopback(host: str) -> bool:
    return host.startswith("/") or host in ("localhost", "127.0.0.1", "::1")


def _arun(coro):
    return asyncio.run(coro)


def _redis():
    import redis

    return redis.Redis.from_url(REDIS_URL, socket_timeout=5, socket_connect_timeout=5)


async def _assert_disposable_pg():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    if not NONCE or len(NONCE) < 16:
        _refuse("NASCAR_7548_NONCE is unset or short; only the provisioning step mints it")
    if not _is_loopback(_pg_host(DB_URL)):
        _refuse(f"Postgres host {_pg_host(DB_URL)!r} is neither a unix socket nor loopback")
    app_url = os.environ.get("DATABASE_URL")
    if app_url and not _is_loopback(_pg_host(app_url)):
        _refuse("$DATABASE_URL is set and is not loopback")
    engine = create_async_engine(DB_URL)
    try:
        async with engine.connect() as conn:
            try:
                rows = (await conn.execute(text(f"SELECT nonce FROM {SENTINEL_TABLE}"))).fetchall()
            except Exception as exc:  # noqa: BLE001 — any failure is a refusal
                _refuse(f"sentinel table {SENTINEL_TABLE!r} is absent ({type(exc).__name__})")
            if [r[0] for r in rows] != [NONCE]:
                _refuse("Postgres sentinel nonce does not match NASCAR_7548_NONCE")
    finally:
        await engine.dispose()


def _assert_disposable_redis():
    host = urlparse(REDIS_URL).hostname or ""
    if not _is_loopback(host):
        _refuse(f"Redis host {host!r} is not loopback")
    if os.environ.get("REDIS_URL") != REDIS_URL:
        _refuse("$REDIS_URL must equal NASCAR_7548_REDIS_URL so the app's own clients "
                "land on the disposable Redis")
    value = _redis().get(SENTINEL_KEY)
    if (value or b"").decode() != NONCE:
        _refuse("Redis sentinel key does not carry NASCAR_7548_NONCE")


@pytest.fixture(scope="module", autouse=True)
def _schema():
    async def _build():
        from sqlalchemy.ext.asyncio import create_async_engine

        import app.models.models  # noqa: F401 — registers every table on Base
        from app.services.database import Base

        await _assert_disposable_pg()
        engine = create_async_engine(DB_URL)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    _assert_disposable_redis()
    _arun(_build())
    yield


@pytest.fixture(autouse=True)
def _world(monkeypatch):
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    import app.tasks.base as task_base

    monkeypatch.setattr(task_base, "DATABASE_URL", DB_URL)

    async def _truncate():
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(DB_URL)
        async with engine.begin() as conn:
            await conn.execute(text(
                "TRUNCATE futures_odds_snapshots, futures_outcomes, futures_markets, "
                "sports RESTART IDENTITY CASCADE"
            ))
        await engine.dispose()

    _arun(_truncate())
    _assert_disposable_redis()
    rc = _redis()
    rc.flushdb()
    rc.set(SENTINEL_KEY, NONCE)
    yield


# ---------------------------------------------------------------------------
# Payloads
# ---------------------------------------------------------------------------


def _real_event() -> dict:
    return _fx("gamma-event-741506.json")


def _with_larson(raw: dict, **fields) -> dict:
    out = copy.deepcopy(raw)
    hits = [m for m in out["markets"] if m["conditionId"] == LARSON_CONDITION]
    assert len(hits) == 1, "identity: exactly one Larson condition in the event"
    hits[0].update(fields)
    return out


def _capture_instant_event(bid: float, ask: float) -> dict:
    """The RECONSTRUCTION described in the module docstring. Larson's market only."""
    mid = round((bid + ask) / 2, 4)
    return _with_larson(
        _real_event(),
        outcomePrices=json.dumps([str(mid), str(round(1 - mid, 4))]),
        bestBid=bid,
        bestAsk=ask,
        lastTradePrice=PRINT,
        volume24hr=1528.0,
    )


def _books_that_could_have_stored_the_print() -> list[tuple[float, float]]:
    """Every cent-grid book with the venue's midpoint that routes to the last trade.

    A book narrower than the fabricated-midpoint spread returns ``outcome_prices``
    (0.38), which is not what was stored — so it is excluded by the stored value
    itself, not by preference.
    """
    from app.utils.feed_market_quality import is_fabricated_midpoint

    books = []
    for bid_c in range(1, 39):
        bid = bid_c / 100
        ask = round(2 * VENUE_MID_AT_CAPTURE - bid, 4)
        if ask <= bid or ask >= 1:
            continue
        if is_fabricated_midpoint(VENUE_MID_AT_CAPTURE, bid, ask):
            books.append((bid, ask))
    return books


def _parse(raw: dict):
    from app.services.polymarket_api import PolymarketAPIService

    event = PolymarketAPIService()._parse_event(raw)
    assert event is not None
    return event


async def _poll_write(raw: dict) -> dict:
    """The REAL discovery-poll writer, the one that wrote the 36-leg stamps."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome
    from app.tasks.polymarket import _process_event_batch
    from app.utils.market_label_normalization import compute_market_tier
    from app.utils.odds_math import probability_to_american

    stats: dict = {
        "markets_processed": 0, "outcomes_updated": 0, "snapshots_created": 0,
        "errors": [], "events_processed": 0,
    }

    class _Counting(dict):
        def __missing__(self, key):
            return 0

    stats = _Counting(stats)
    await _process_event_batch(
        [_parse(raw)], stats, FuturesMarket, FuturesOutcome, FuturesOddsSnapshot,
        pg_insert, probability_to_american, compute_market_tier,
    )
    assert not stats["errors"], stats["errors"]
    return stats


async def _rows(sql: str, **params):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(DB_URL)
    try:
        async with engine.connect() as conn:
            return (await conn.execute(text(sql), params)).fetchall()
    finally:
        await engine.dispose()


_LARSON_SNAPSHOTS = """
    SELECT s.probability::float, s.yes_bid::float, s.yes_ask::float, s.last_price::float
      FROM futures_odds_snapshots s
      JOIN futures_outcomes o ON o.id = s.outcome_id
      JOIN futures_markets m ON m.id = o.market_id
     WHERE m.source = 'polymarket' AND m.external_id = :eid AND o.external_id = :cond
     ORDER BY s.captured_at, s.id
"""

_STAMP_SHAPES = """
    SELECT s.captured_at, count(*), round(sum(s.probability)::numeric, 4)::float
      FROM futures_odds_snapshots s
      JOIN futures_outcomes o ON o.id = s.outcome_id
      JOIN futures_markets m ON m.id = o.market_id
     WHERE m.external_id = :eid
     GROUP BY 1 ORDER BY 1
"""


# ---------------------------------------------------------------------------
# V — what the VENUE's own bytes say (no code of ours under test)
# ---------------------------------------------------------------------------


def test_V1_identity_the_print_is_on_larsons_own_condition_and_yes_token():
    """Not a wrong question: one event, one Larson condition, the YES token."""
    event = _real_event()
    assert str(event["id"]) == EVENT_ID and event["negRisk"] is True
    larson = [m for m in event["markets"] if m["conditionId"] == LARSON_CONDITION]
    assert [m["groupItemTitle"] for m in larson] == ["Kyle Larson"]
    assert json.loads(larson[0]["clobTokenIds"])[0] == LARSON_YES_TOKEN
    assert _fx("bainluck-detail-56947465.json")["external_id"] == EVENT_ID

    prints = [
        t for t in _fx("dataapi-trades-larson.reduced.json")
        if t["conditionId"] == LARSON_CONDITION and t["outcome"] == "Yes"
        and abs(t["price"] - PRINT) < 1e-9
    ]
    assert len(prints) == 1
    assert prints[0]["asset"] == LARSON_YES_TOKEN
    at = datetime.fromtimestamp(prints[0]["timestamp"], tz=timezone.utc)
    assert at == datetime(2026, 9, 19, 20, 10, 35, tzinfo=timezone.utc)
    # ~$45: the size that moved a championship chart to 99%.
    assert 40 < prints[0]["size"] * prints[0]["price"] < 50


def test_V2_the_venues_own_series_never_reached_the_print_and_prices_it_out():
    history = _fx("clob-prices-history-larson-yes.json")["history"]
    day = [
        p for p in history
        if datetime(2026, 9, 19, 12, tzinfo=timezone.utc)
        <= datetime.fromtimestamp(p["t"], tz=timezone.utc)
        <= datetime(2026, 9, 20, 6, tzinfo=timezone.utc)
    ]
    assert len(day) > 500
    assert max(p["p"] for p in day) == 0.586
    # The 20 minutes before our capture stamp — a poll pass cannot predate these.
    window = [
        p["p"] for p in day
        if datetime(2026, 9, 19, 20, 20, tzinfo=timezone.utc)
        <= datetime.fromtimestamp(p["t"], tz=timezone.utc)
        <= datetime(2026, 9, 19, 20, 32, tzinfo=timezone.utc)
    ]
    assert window and max(window) <= 0.3935
    # ARITHMETIC, NOT A GUESS ABOUT THE BOOK: mid = (bid + ask) / 2 with bid >= 0
    # bounds the ask at 2 * mid. At 0.3935 that is 0.787 — two tenths under 0.989.
    from app.utils.kalshi_empty_book import BOOK_REFUTES_PRICE_EPSILON

    assert 2 * max(window) + BOOK_REFUTES_PRICE_EPSILON < PRINT
    # ...and the served history is the same number, on the same outcome.
    served = {
        o["outcome_id"]: {p["timestamp"]: p["probability"] for p in o["history"]}
        for o in _fx("bainluck-history-56947465.json")["outcomes"]
    }
    assert served[LARSON_OUTCOME_ID][BAD_STAMP] == PRINT


# ---------------------------------------------------------------------------
# W — the WRITER
# ---------------------------------------------------------------------------


def test_W0_the_reconstruction_space_is_not_empty_and_every_book_is_wide():
    books = _books_that_could_have_stored_the_print()
    assert len(books) >= 10
    assert all(ask < PRINT - 0.2 for _bid, ask in books)


@pytest.mark.parametrize("which", ["tightest", "widest", "middle"])
def test_W1_named_replay_the_poll_writer_does_not_store_the_print(which):
    """RED on the base: Larson gets a 0.989 snapshot and the stamp sums past 1.8."""
    books = _books_that_could_have_stored_the_print()
    bid, ask = {"tightest": books[-1], "widest": books[0], "middle": books[len(books) // 2]}[which]

    _arun(_poll_write(_real_event()))  # the ordinary pass before it
    before = _arun(_rows(_LARSON_SNAPSHOTS, eid=EVENT_ID, cond=LARSON_CONDITION))
    assert [r[0] for r in before] == [0.2505]

    _arun(_poll_write(_capture_instant_event(bid, ask)))
    after = _arun(_rows(_LARSON_SNAPSHOTS, eid=EVENT_ID, cond=LARSON_CONDITION))
    assert PRINT not in [r[0] for r in after], (
        f"the writer stored the {PRINT} trade print over a {bid}/{ask} book"
    )
    # A refusal is a SKIP: no row for the leg on that pass, and the number the
    # table prints is still the last supported one.
    assert [r[0] for r in after] == [0.2505]
    current = _arun(_rows(
        "SELECT current_probability::float FROM futures_outcomes WHERE external_id = :c",
        c=LARSON_CONDITION,
    ))
    assert current == [(0.2505,)]

    # HEALTHY FIELD CONTROL: every other leg was written on BOTH passes, so the
    # refusal cost one cell and not a stamp.
    shapes = _arun(_rows(_STAMP_SHAPES, eid=EVENT_ID))
    assert len(shapes) == 2
    (_, n1, sum1), (_, n2, sum2) = shapes
    assert n2 == n1 - 1
    assert abs((sum1 - 0.2505) - sum2) < 1e-6


@pytest.mark.parametrize(
    "fields, written",
    [
        # A leg that really ran to 0.989: the book is up there with it.
        (dict(outcomePrices='["0.989", "0.011"]', bestBid=0.985, bestAsk=0.992,
              lastTradePrice=0.989, volume24hr=90000.0), 0.989),
        # Gotcha #19's blowout: the ask side CLEARED, so Gamma's 0.85 is a phantom
        # midpoint and the last trade substitutes. SAME 0.989 print as the named
        # tick — kept, because no offer anywhere prices it out.
        (dict(outcomePrices='["0.85", "0.15"]', bestBid=0.70, bestAsk=1,
              lastTradePrice=0.989, volume24hr=90000.0), 0.989),
        # Wide book, recent trade INSIDE it: Q428's exception, untouched.
        (dict(outcomePrices='["0.6", "0.4"]', bestBid=0.30, bestAsk=0.90,
              lastTradePrice=0.62, volume24hr=500.0), 0.62),
    ],
    ids=["quoted-at-0.989", "cleared-ask-blowout-0.989", "trade-inside-wide-book"],
)
def test_W2_genuine_moves_are_still_written_by_the_same_writer(fields, written):
    _arun(_poll_write(_with_larson(_real_event(), **fields)))
    rows = _arun(_rows(_LARSON_SNAPSHOTS, eid=EVENT_ID, cond=LARSON_CONDITION))
    assert [r[0] for r in rows] == [written]


def test_W3_the_hourly_refresh_writer_shares_the_refusal():
    """`futures_price_refresh` is the 16-leg writer; it prices through the same resolver."""
    from app.tasks.futures_price_refresh import _fetch_polymarket_prices

    bid, ask = _books_that_could_have_stored_the_print()[0]
    raw = _capture_instant_event(bid, ask)

    class _Service:
        from app.services.polymarket_api import PolymarketAPIService as _S

        _parse_event = staticmethod(_S()._parse_event)

        async def get_events_by_ids(self, ids):
            return [raw]

    stats: dict = {}
    priced, _unpriced = _arun(_fetch_polymarket_prices(_Service(), [EVENT_ID], stats))
    by_condition = {item["external_id"]: item["probability"] for item in priced[EVENT_ID]}
    assert LARSON_CONDITION not in by_condition
    assert len(by_condition) >= 15  # the rest of the live field is still priced
    assert stats.get("polymarket_legs_declined_quoted", 0) >= 1  # and the refusal is COUNTED


# ---------------------------------------------------------------------------
# R — the READERS (chart + hero sparkline read /history; the concept page
#     reads /probability-timeline). Rows already stored.
# ---------------------------------------------------------------------------

NOW = datetime(2026, 9, 20, 18, 49, tzinfo=timezone.utc)
CONTROL_MARKET_ID = 7548001
CONTROL_OUTCOME_ID = 7548101
GENUINE_STAMP = "2026-09-19T20:31:08.128201+00:00"


class _FrozenMeta(type(datetime)):
    def __instancecheck__(cls, obj):
        return isinstance(obj, datetime)


class FrozenDatetime(datetime, metaclass=_FrozenMeta):
    @classmethod
    def now(cls, tz=None):
        return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)


async def _seed_served_history(*, bad_book):
    """Production's own served week, row for row, from the saved /history bytes.

    The book columns of every ORDINARY row are left NULL: they are not in the
    served payload and inventing them would let this test pass for the wrong
    reason. Only the named row carries a book — ``bad_book`` — and only the
    control row beside it.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models as m

    detail = _fx("bainluck-detail-56947465.json")
    history = _fx("bainluck-history-56947465.json")
    engine = create_async_engine(DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        s.add(m.FuturesMarket(
            id=MARKET_ID, source="polymarket", external_id=EVENT_ID, name=detail["name"],
            category="championship", llm_sport_category="motorsports", market_tier=2,
            mutually_exclusive=True, status="open", group_id=detail["group_id"],
            market_metadata={}, resolution_date=NOW + timedelta(days=49),
            created_at=NOW - timedelta(days=58),
        ))
        s.add(m.FuturesMarket(
            id=CONTROL_MARKET_ID, source="polymarket", external_id="7548-control",
            name="CONTROL: a leg that genuinely ran to 98.9%", category="championship",
            llm_sport_category="motorsports", market_tier=2, mutually_exclusive=True,
            status="open", market_metadata={}, resolution_date=NOW + timedelta(days=49),
            created_at=NOW - timedelta(days=58),
        ))
        await s.flush()
        for rank, o in enumerate(detail["outcomes"], start=1):
            s.add(m.FuturesOutcome(
                id=o["id"], market_id=MARKET_ID, external_id=f"cond-{o['id']}", name=o["name"],
                current_probability=o["probability"], rank=rank, is_winner=None,
                resolution_source=None, last_updated=NOW,
            ))
        s.add(m.FuturesOutcome(
            id=CONTROL_OUTCOME_ID, market_id=CONTROL_MARKET_ID, external_id="cond-control",
            name="Genuine Mover", current_probability=0.989, rank=1, is_winner=None,
            resolution_source=None, last_updated=NOW,
        ))
        await s.flush()
        for o in history["outcomes"]:
            for pt in o["history"]:
                named = o["outcome_id"] == LARSON_OUTCOME_ID and pt["timestamp"] == BAD_STAMP
                bid, ask, last = bad_book if named else (None, None, None)
                s.add(m.FuturesOddsSnapshot(
                    outcome_id=o["outcome_id"], bookmaker="polymarket",
                    probability=pt["probability"], yes_bid=bid, yes_ask=ask, last_price=last,
                    captured_at=datetime.fromisoformat(pt["timestamp"]),
                ))
        # The genuine-extreme control: SAME value, SAME stamp, SAME last trade —
        # the only difference is that its own book is up there with it.
        for stamp, p, bid, ask, last in [
            ("2026-09-19T15:50:34.140574+00:00", 0.62, 0.61, 0.63, 0.62),
            (GENUINE_STAMP, 0.989, 0.985, 0.992, 0.989),
            ("2026-09-20T02:54:04.380216+00:00", 0.991, 0.99, 0.995, 0.99),
        ]:
            s.add(m.FuturesOddsSnapshot(
                outcome_id=CONTROL_OUTCOME_ID, bookmaker="polymarket", probability=p,
                yes_bid=bid, yes_ask=ask, last_price=last,
                captured_at=datetime.fromisoformat(stamp),
            ))
        await s.commit()
    await engine.dispose()


@asynccontextmanager
async def _client():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.dependencies.auth import get_optional_user
    from app.main import app
    from app.services.database import get_db, get_db_rw

    engine = create_async_engine(DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _db():
        async with maker() as session:
            yield session

    async def _anon():
        return None

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_db_rw] = _db
    app.dependency_overrides[get_optional_user] = _anon
    try:
        with patch("app.main.init_db", new_callable=AsyncMock):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as ac:
                yield ac
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


def _get(path: str, monkeypatch) -> dict:
    import app.routes.futures as futures_routes

    monkeypatch.setattr(futures_routes, "datetime", FrozenDatetime)

    async def _go():
        async with _client() as ac:
            r = await ac.get(path)
        assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text[:400]}"
        return r.json()

    return _arun(_go())


def _series(body: dict) -> dict[int, dict[str, float]]:
    return {
        o["outcome_id"]: {p["timestamp"]: p["probability"] for p in o["history"]}
        for o in body["outcomes"]
    }


def test_R1_history_withholds_the_named_tick_and_nothing_else(monkeypatch):
    """The Probability Trend AND the hero sparkline both read this payload."""
    _arun(_seed_served_history(bad_book=(0.20, 0.563, PRINT)))
    saved = _series(_fx("bainluck-history-56947465.json"))
    served = _series(_get(f"/api/futures/{MARKET_ID}/history?hours=168&top_n=50", monkeypatch))

    assert BAD_STAMP not in served[LARSON_OUTCOME_ID], "the 98.9% print is still charted"
    assert max(served[LARSON_OUTCOME_ID].values()) < 0.30
    # Exact observation times preserved: Larson keeps his other 32 stamps, untouched.
    assert set(served[LARSON_OUTCOME_ID]) == set(saved[LARSON_OUTCOME_ID]) - {BAD_STAMP}
    # No other outcome lost a point, at that stamp or anywhere. The one point a
    # line may GAIN is #8296's carried endpoint: an unmoved leg closed at the
    # column's last instant (this rig seeds every leg ungraded, so it fires here).
    last_instant = max(t for points in saved.values() for t in points)
    for oid, points in saved.items():
        if oid != LARSON_OUTCOME_ID:
            assert set(points) <= set(served[oid]), oid
            assert set(served[oid]) - set(points) <= {last_instant}, oid
    # No smoothing, no rescale: every surviving value at the named stamp is the
    # stored one. (The stamp's column still sums past 1.6, so #23 leaves it raw.)
    for oid, points in served.items():
        if BAD_STAMP in points:
            assert points[BAD_STAMP] == saved[oid][BAD_STAMP]


def test_R2_a_genuine_move_to_the_same_value_is_still_drawn(monkeypatch):
    _arun(_seed_served_history(bad_book=(0.20, 0.563, PRINT)))
    served = _series(_get(f"/api/futures/{CONTROL_MARKET_ID}/history?hours=168", monkeypatch))
    assert served[CONTROL_OUTCOME_ID][GENUINE_STAMP] == 0.989
    assert len(served[CONTROL_OUTCOME_ID]) == 3


def test_R3_a_row_with_no_recorded_book_is_left_alone(monkeypatch):
    """EVIDENCE LIMIT, PINNED. If production's named row stored NULL book columns,
    the read arm is inert on it — absence is not evidence — and the stored-row
    correction in `repair/` is the remedy instead. This test is why REPORT.md asks
    for one export before anyone claims the chart is repaired."""
    _arun(_seed_served_history(bad_book=(None, None, PRINT)))
    served = _series(_get(f"/api/futures/{MARKET_ID}/history?hours=168&top_n=50", monkeypatch))
    assert served[LARSON_OUTCOME_ID][BAD_STAMP] == PRINT


def test_R4_the_timeline_reader_agrees_with_the_chart(monkeypatch):
    _arun(_seed_served_history(bad_book=(0.20, 0.563, PRINT)))
    body = _get(f"/api/futures/{MARKET_ID}/probability-timeline?hours=168&top=50", monkeypatch)
    larson = [b["outcomes"]["Kyle Larson"] for b in body["timeline"] if "Kyle Larson" in b["outcomes"]]
    assert larson, "the timeline serves no Larson series at all — the test would be vacuous"
    assert max(larson) < 0.5


def test_R5_a_settled_journey_is_not_edited():
    """Ungraded only: a graded row keeps every point, whatever its stale book says."""
    from app.utils.futures_unsupported_price import (
        snapshot_price_is_unsupported,
        trade_print_refuted_by_own_book,
    )

    assert trade_print_refuted_by_own_book("polymarket", None, PRINT, 0.20, 0.563, PRINT)
    assert not trade_print_refuted_by_own_book(
        "polymarket", "api_settlement", PRINT, 0.20, 0.563, PRINT
    )
    # Not its last trade -> a different instrument -> never asked.
    assert not trade_print_refuted_by_own_book("polymarket", None, PRINT, 0.20, 0.563, 0.41)
    # Kalshi has its own arm (#6532); this one does not double up on it.
    assert not trade_print_refuted_by_own_book("kalshi", None, PRINT, 0.20, 0.563, PRINT)
    assert snapshot_price_is_unsupported("polymarket", None, PRINT, 0.20, 0.563, PRINT)
