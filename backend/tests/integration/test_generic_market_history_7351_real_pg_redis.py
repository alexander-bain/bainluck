"""#7351 — an ordinary market's chart serves the venue history our polls missed.

PILLAR: TRUTH. SHIP: opening a generic Discover market shows its supported
historical observations on the phone and the web, including history missed by
our periodic polls.

═══ WHAT IS REAL HERE AND WHAT IS CONTROLLED ════════════════════════════════

REAL: both chart route handlers through the real FastAPI app
(`/api/futures/{id}/probability-timeline` — the phone; `/api/futures/{id}/history`
— the web futures page), a real PostgreSQL, a real Redis, the real Celery task
FUNCTION (`app.tasks.fill_generic_market_history`), `get_task_session`, the real
`KalshiAPIService` / `PolymarketAPIService` and their own response parsing, the
real tier planner, candle price rule, layering, compaction, claim, cache and
identity validation.

CONTROLLED, AND ONLY THESE:
  * the two venues' HTTP TRANSPORT — `httpx.MockTransport` answers with saved
    provider bytes (Kalshi: three REAL responses for the named ticker, fetched
    2026-09-20T03:42Z; see `tests/fixtures/generic_market_history_7351/
    PROVENANCE.md`) or with bytes labelled SYNTHETIC (every Polymarket body);
  * the BROKER — `apply_async` is recorded instead of published, and the test
    then executes the recorded call through the task's real `.run()`;
  * the CLOCK of the three modules that ask it, frozen at the instant the Kalshi
    bytes were fetched, so every timestamp asserted below is the literal
    timestamp in the saved bytes and the fill replays the EXACT requests that
    produced them.

THE NAMED FAILURE. Market 59165099 / outcome 219751686 / Kalshi ticker
KXCAPGAINDOWN-26AUG-27JAN01. Production served ONE observation in seven days
(`59165099-timeline.json`, `59165099-history.json`); Kalshi's own candles for the
exact ticker hold more. `test_A1` is RED on the pinned base
3fa9d18c484a030e735a1491c235d950f3ad1d90 — "MISSING ELIGIBLE VENUE TIMESTAMPS" —
and green on the candidate.

A SKIP IS NOT A PASS. This file skips when it cannot see its disposable services;
`APPLY-AND-TEST.sh` and the CI step both refuse a skip, a zero collection and a
short count.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

DB_URL = os.environ.get("GENERIC_HISTORY_DATABASE_URL")
REDIS_URL = os.environ.get("GENERIC_HISTORY_REDIS_URL")
NONCE = os.environ.get("GENERIC_HISTORY_NONCE")
SENTINEL_TABLE = "generic_history_disposable"
SENTINEL_KEY = "generic_history_disposable"

pytestmark = pytest.mark.skipif(
    not (DB_URL and REDIS_URL and NONCE),
    reason=(
        "NOT RUN — set GENERIC_HISTORY_DATABASE_URL + GENERIC_HISTORY_REDIS_URL + "
        "GENERIC_HISTORY_NONCE to run the #7351 acceptance on disposable Postgres "
        "and Redis. A skip here is NOT a pass."
    ),
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "generic_market_history_7351"

# ── the specimen ────────────────────────────────────────────────────────────
MARKET_ID = 59165099
OUTCOME_ID = 219751686
EVENT_TICKER = "KXCAPGAINDOWN-26AUG"
TICKER = "KXCAPGAINDOWN-26AUG-27JAN01"

#: The instant the three Kalshi fixture responses were fetched — their requests'
#: own `end_ts`. The clock is frozen HERE, so the fill's windows are those
#: requests exactly (asserted in `test_B1`).
FROZEN_NOW = datetime.fromtimestamp(1789875752, tz=timezone.utc)  # 2026-09-20T03:42:32Z

from app.utils.futures_chart_series import (  # noqa: E402 — after the skip gate
    FINE_TIER_HOURS as _FINE_TIER_HOURS,
    KALSHI_MAX_CANDLES_PER_REQUEST as _KALSHI_BUDGET,
)

#: The three requests that produced the Kalshi fixture bytes, verbatim — except
#: the fine tier's `start_ts`, which #7547 moved and which is therefore DERIVED.
#:
#: ⚠️ THE FINE BYTES ANSWER A NARROWER ASK THAN THE ONE NOW MADE, AND THAT IS
#: STATED RATHER THAN HIDDEN. `kalshi-1m-24h.json` is Kalshi's real answer for
#: `start_ts = end_ts − 24h`, fetched 2026-09-20T03:42:32Z. #7547 widened the fine
#: tier to `FINE_TIER_HOURS` (144h) because a reader scrubbing 1W was being served
#: a week drawn from hours, so the fill now asks for six days of minutes and the
#: saved bytes answer one day of them. Replaying them against the wider ask is
#: CONSERVATIVE in the only direction that matters — a sub-window of the venue's
#: real answer can under-serve this file's assertions, never invent a candle — so
#: every admitted/rejected timestamp below still comes from bytes Kalshi sent.
#: What it does NOT do is prove the venue serves the extra five days; that is
#: proved against the venue itself and recorded on #7547, not here.
#:
#: Derived from `FINE_TIER_HOURS` rather than written as 1789357352 so the day the
#: tier moves again this constant moves with it instead of reddening as a literal
#: nobody can date.
RECORDED_KALSHI_REQUESTS = [
    {"period_interval": 1, "start_ts": 1789875752 - int(_FINE_TIER_HOURS * 3600),
     "end_ts": 1789875752, "file": "kalshi-1m-24h.json"},
    {"period_interval": 60, "start_ts": 1787197352, "end_ts": 1789875752, "file": "kalshi-60m-31d.json"},
    {"period_interval": 1440, "start_ts": 1787093355, "end_ts": 1789875752, "file": "kalshi-1440m-life.json"},
]

#: sha256 of every fixture byte this file replays. The first five are the brief's
#: own saved inputs and equal `inputs/SHA256SUMS`.
FIXTURE_SHA256 = {
    "59165099-detail.json": "97f482735068306c8cfd6ecd702ff85b67027f213fe5b39adfb2b55c3e10ae17",
    "59165099-history.json": "c012218da10debce8745b24d3f0903e6f5d9b2acbf75f09190420fdd7d277f5e",
    "59165099-kalshi-7d-hourly.json": "b024602da97522893fe2434912b1feb76ffcd8367ffbff415c8c274cece93a45",
    "59165099-kalshi-event.json": "9b1bfddad3448e8ef4521f74eb7785c9f59514f4de71542e4b9319718e812e69",
    "59165099-timeline.json": "6a9b2d4d86b7a03f1797563aaa9d202e74667bb4e2e21e5b2dbb8274e0557622",
}


def _fx(name: str):
    return json.loads((FIXTURES / name).read_text())


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


# ── what the candidate must serve for the specimen, and WHY ─────────────────
#
# Inside the phone's seven-day window (frozen now − 168h = 2026-09-13T03:42:32Z).
# Every candle the three real responses hold in that window is accounted for:
# ADMITTED with the value `normalize_candle` gives its closing book, or REJECTED
# with the one rule that rejected it. Nothing is asserted by count.
#
#   tier   candle end (UTC)        bid/ask close   value    verdict
ADMITTED_IN_WEEK = [
    #                                                        tight book → mid
    ("2026-09-16T03:00:00+00:00", 0.085),   # 60m   0.08/0.09
    ("2026-09-16T04:00:00+00:00", 0.085),   # 1440m 0.08/0.09 (60 min from the 03:00 hourly: outside its claim)
    ("2026-09-16T17:00:00+00:00", 0.085),   # 60m   0.08/0.09
    ("2026-09-17T04:00:00+00:00", 0.085),   # 1440m 0.08/0.09
    ("2026-09-17T08:00:00+00:00", 0.06),    # 60m   0.03/0.09
    ("2026-09-17T10:00:00+00:00", 0.085),   # 60m   0.08/0.09
    ("2026-09-17T16:00:00+00:00", 0.07),    # 60m   0.05/0.09
    ("2026-09-17T17:00:00+00:00", 0.07),    # 60m   0.05/0.09
    ("2026-09-18T04:00:00+00:00", 0.07),    # 1440m 0.05/0.09
    ("2026-09-18T10:00:00+00:00", 0.065),   # 60m   0.05/0.08
    ("2026-09-18T14:00:00+00:00", 0.055),   # 60m   0.03/0.08
    ("2026-09-19T04:00:00+00:00", 0.055),   # 1440m 0.03/0.08
    ("2026-09-19T08:01:00+00:00", 0.06),    # 1m    0.03/0.09
    ("2026-09-19T09:00:00+00:00", 0.06),    # 60m   0.03/0.09 (41 min from the 09:41 minute candle: outside its claim)
    ("2026-09-19T09:41:00+00:00", 0.055),   # 1m    0.03/0.08
]
REJECTED_IN_WEEK = {
    # The hourly candle 19 minutes after the 09:41 one-minute candle is the same
    # stretch of book at a coarser grain: `layer_tiers` keeps the finer tier
    # (claim radius: half the tier's median spacing, capped at 30 minutes).
    "2026-09-19T10:00:00+00:00": "claimed_by_finer_tier",
}
#: Our own capture in the week, from `59165099-history.json`. It is a CAPTURE and
#: is never displaced: it stays exactly where and what it was.
CAPTURE_IN_WEEK = ("2026-09-19T10:47:36.879693+00:00", 0.055)


# ---------------------------------------------------------------------------
# Disposable-service guards
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
        _refuse("GENERIC_HISTORY_NONCE is unset or short; only the provisioning step mints it")
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
                _refuse("Postgres sentinel nonce does not match GENERIC_HISTORY_NONCE")
    finally:
        await engine.dispose()


def _assert_disposable_redis():
    host = urlparse(REDIS_URL).hostname or ""
    if not _is_loopback(host):
        _refuse(f"Redis host {host!r} is not loopback")
    if os.environ.get("REDIS_URL") != REDIS_URL:
        _refuse("$REDIS_URL must equal GENERIC_HISTORY_REDIS_URL so the APP's own clients "
                "(claim, cache, task tracking) land on the disposable Redis")
    import app.tasks.redis_state as rs

    if rs.REDIS_URL != REDIS_URL:
        _refuse("app.tasks.redis_state was imported under a different REDIS_URL")
    value = _redis().get(SENTINEL_KEY)
    if (value or b"").decode() != NONCE:
        _refuse("Redis sentinel key does not carry GENERIC_HISTORY_NONCE")


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


# ---------------------------------------------------------------------------
# The clock
# ---------------------------------------------------------------------------

_REAL_DATETIME = datetime


class _FrozenMeta(type(datetime)):
    def __instancecheck__(cls, obj):  # `isinstance(x, datetime)` keeps meaning datetime
        return isinstance(obj, _REAL_DATETIME)


class FrozenDatetime(datetime, metaclass=_FrozenMeta):
    current = FROZEN_NOW

    @classmethod
    def now(cls, tz=None):
        return cls.current.astimezone(tz) if tz else cls.current.replace(tzinfo=None)


#: Every module on the path under test that asks what time it is.
_CLOCKED_MODULES = (
    "app.routes.futures",
    "app.tasks.generic_market_history_fill",
    "app.tasks.futures_chart_series_fill",
)


@pytest.fixture(autouse=True)
def _world(monkeypatch):
    """Frozen clock, clean rows, clean Redis, the app pointed at the scratch DB.

    🔴 `durable_state_snapshots` IS PART OF THE WORLD (#7807), and it was the one
    piece the reset used to miss. Flushing Redis stopped clearing the bank the
    moment the bank stopped being Redis-only — that is the whole point of the
    tier — and a leaked row does not merely make a cold test warm. It interacts
    with THIS FIXTURE'S OWN CLOCK RESET, in both directions:

      * a test that advances `FrozenDatetime.current` (B9/B10/B13 go to +20h)
        leaves a row stamped in the FUTURE relative to the next test. The next
        test reads it as `STALE` — `decode_envelope` rejects `age_s < 0` rather
        than clamping it, deliberately — so an evicted bank reads COLD;
      * and `publish_snapshot`'s `stored.generation <= EXCLUDED.generation` guard
        then REFUSES that test's own honest write, because its generation is
        smaller. The future row sticks, and a later test that advances its clock
        finds it inside the age bound again and reads WARM where it wants cold.

    So a missing line here does not fail loudly in one place; it produces two
    opposite wrong answers in two different tests. Both are real behaviour, both
    are correct outside a rig that rewinds time, and neither is reachable in
    production, where clocks go forwards.
    """
    import importlib

    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    FrozenDatetime.current = FROZEN_NOW
    for name in _CLOCKED_MODULES:
        try:
            module = importlib.import_module(name)
        except ModuleNotFoundError:
            continue  # the pinned BASE has no generic fill module; A1 must still RUN there
        monkeypatch.setattr(module, "datetime", FrozenDatetime)
    import app.tasks.base as task_base

    monkeypatch.setattr(task_base, "DATABASE_URL", DB_URL)

    async def _truncate():
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(DB_URL)
        async with engine.begin() as conn:
            await conn.execute(text(
                "TRUNCATE futures_odds_snapshots, futures_outcomes, futures_markets, "
                "sports, durable_state_snapshots RESTART IDENTITY CASCADE"
            ))
        await engine.dispose()

    _arun(_truncate())
    _assert_disposable_redis()
    rc = _redis()
    rc.flushdb()
    rc.set(SENTINEL_KEY, NONCE)
    yield


# ---------------------------------------------------------------------------
# The venues — saved bytes behind the services' REAL clients
# ---------------------------------------------------------------------------


class Venue:
    """Both venues' HTTP surface. Records every request it is ever sent."""

    def __init__(self):
        self.requests: list[dict] = []
        self.kalshi_mode = "recorded"       # recorded | empty | http_500 | http_429 | fail_60m | custom
        self.kalshi_custom: dict[int, dict] = {}
        self.gamma_events: dict[str, dict] = {}
        self.clob: dict[tuple[str, str, int], object] = {}
        self.clob_default: object = []

    # -- Kalshi -----------------------------------------------------------
    def _kalshi(self, request: httpx.Request) -> httpx.Response:
        q = parse_qs(request.url.query.decode())
        interval = int(q["period_interval"][0])
        start_ts, end_ts = int(q["start_ts"][0]), int(q["end_ts"][0])
        tickers = q["market_tickers"][0].split(",")
        self.requests.append({"venue": "kalshi", "period_interval": interval,
                              "start_ts": start_ts, "end_ts": end_ts, "tickers": tickers})
        if self.kalshi_mode == "http_500" or (self.kalshi_mode == "fail_60m" and interval == 60):
            return httpx.Response(500, json={"error": "synthetic upstream failure"})
        if self.kalshi_mode == "http_429":
            return httpx.Response(429, json={"error": "synthetic rate limit"})
        if self.kalshi_mode == "empty":
            return httpx.Response(200, json={"markets": []})
        if self.kalshi_mode == "custom":
            body = self.kalshi_custom.get(interval, {"markets": []})
        else:
            recorded = next(r for r in RECORDED_KALSHI_REQUESTS if r["period_interval"] == interval)
            body = _fx(recorded["file"])
        # The venue answers only for the tickers and the window it was asked for.
        markets = []
        for entry in body.get("markets", []):
            if entry.get("market_ticker") not in tickers:
                continue
            candles = [c for c in entry.get("candlesticks", [])
                       if c.get("end_period_ts") is None or start_ts <= c["end_period_ts"] <= end_ts]
            markets.append({**entry, "candlesticks": candles})
        return httpx.Response(200, json={"markets": markets})

    # -- Polymarket (every body SYNTHETIC) --------------------------------
    def _gamma(self, request: httpx.Request) -> httpx.Response:
        event_id = request.url.path.rsplit("/", 1)[-1]
        self.requests.append({"venue": "polymarket-gamma", "event_id": event_id})
        body = self.gamma_events.get(event_id)
        return httpx.Response(200, json=body) if body is not None else httpx.Response(404, json={})

    def _clob(self, request: httpx.Request) -> httpx.Response:
        q = parse_qs(request.url.query.decode())
        key = (q["market"][0], q["interval"][0], int(q["fidelity"][0]))
        self.requests.append({"venue": "polymarket-clob", "token": key[0],
                              "interval": key[1], "fidelity": key[2]})
        answer = self.clob.get(key, self.clob_default)
        if answer == "http_500":
            return httpx.Response(500, json={"error": "synthetic"})
        return httpx.Response(200, json={"history": answer})

    def handler(self, request: httpx.Request) -> httpx.Response:
        host, path = request.url.host, request.url.path
        if "kalshi" in host and path.endswith("/markets/candlesticks"):
            return self._kalshi(request)
        if "gamma" in host and "/events/" in path:
            return self._gamma(request)
        if "clob" in host and path.endswith("/prices-history"):
            return self._clob(request)
        self.requests.append({"venue": "UNEXPECTED", "url": str(request.url)})
        return httpx.Response(599, json={"error": "unexpected request in a sealed test"})

    def provider_requests(self) -> list[dict]:
        return list(self.requests)


class _HttpxProxy:
    """`httpx`, except every AsyncClient the SERVICE builds rides the fake venue."""

    def __init__(self, venue: Venue):
        self._venue = venue

    def AsyncClient(self, **kwargs):
        kwargs["transport"] = httpx.MockTransport(self._venue.handler)
        return httpx.AsyncClient(**kwargs)

    def __getattr__(self, name):
        return getattr(httpx, name)


@pytest.fixture
def venue(monkeypatch):
    from app.services import base_api, polymarket_api

    v = Venue()
    proxy = _HttpxProxy(v)
    monkeypatch.setattr(base_api, "httpx", proxy)
    monkeypatch.setattr(polymarket_api, "httpx", proxy)
    # The fill paces real venues at 0.25 s a request. There is no venue here.
    from app.tasks import futures_chart_series_fill as concept_fill

    monkeypatch.setattr(concept_fill, "REQUEST_PAUSE_SECONDS", 0)
    return v


# ---------------------------------------------------------------------------
# The broker — recorded, then executed through the task's REAL function
# ---------------------------------------------------------------------------


class Broker:
    def __init__(self):
        self.calls: list[dict] = []
        self.fail_next_dispatch = False
        self.task_registered = False

    def apply_async(self, args=None, kwargs=None, **options):
        if self.fail_next_dispatch:
            self.fail_next_dispatch = False
            raise ConnectionError("synthetic broker outage")
        self.calls.append({"kwargs": dict(kwargs or {}), "options": options})

    def run_enqueued(self) -> list[dict]:
        """Execute every recorded dispatch through the REAL task entry point."""
        from app import tasks

        results = []
        pending, self.calls = self.calls, []
        for call in pending:
            assert call["options"].get("queue") == "background", call
            results.append(tasks.fill_generic_market_history.run(**call["kwargs"]))
        return results


@pytest.fixture
def broker(monkeypatch):
    from app import tasks

    b = Broker()
    task = getattr(tasks, "fill_generic_market_history", None)
    if task is not None:  # absent on the pinned base — A1 must still RUN there, and fail
        b.task_registered = True
        monkeypatch.setattr(task, "apply_async", b.apply_async)
    return b


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------


async def _seed(markets: list[dict]):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models as m

    engine = create_async_engine(DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        for spec in markets:
            s.add(m.FuturesMarket(
                id=spec["id"], source=spec["source"], external_id=spec["external_id"],
                name=spec["name"], category=spec.get("category", "politics"),
                llm_sport_category=spec.get("category", "politics"), market_tier=2,
                mutually_exclusive=spec.get("mutually_exclusive", False), status="open",
                group_id=spec.get("group_id"), market_metadata=spec.get("metadata", {}),
                resolution_date=FROZEN_NOW + timedelta(days=100),
                created_at=spec.get("created_at", FROZEN_NOW - timedelta(days=32)),
            ))
            await s.flush()
            for rank, o in enumerate(spec["outcomes"], start=1):
                s.add(m.FuturesOutcome(
                    id=o["id"], market_id=spec["id"], external_id=o["external_id"], name=o["name"],
                    current_probability=o["p"], opening_probability=o.get("open", o["p"]),
                    rank=rank, is_winner=False, last_updated=FROZEN_NOW,
                ))
                await s.flush()
                for captured_at, price in o.get("captures", []):
                    s.add(m.FuturesOddsSnapshot(
                        outcome_id=o["id"], bookmaker=spec["source"],
                        probability=price, captured_at=captured_at,
                    ))
        await s.commit()
    await engine.dispose()


def _seed_specimen():
    """The named market, from the brief's own saved responses. Nothing invented:
    ids, names and prices are `59165099-detail.json`; the nine captures are the
    nine observations `59165099-history.json` served."""
    detail, history = _fx("59165099-detail.json"), _fx("59165099-history.json")
    outcome = detail["outcomes"][0]
    assert (detail["id"], outcome["id"]) == (MARKET_ID, OUTCOME_ID)
    captures = [
        (datetime.fromisoformat(pt["timestamp"]), pt["probability"])
        for pt in history["outcomes"][0]["history"]
    ]
    assert len(captures) == 9
    _arun(_seed([{
        "id": MARKET_ID, "source": "kalshi", "external_id": detail["external_id"],
        "name": detail["name"], "mutually_exclusive": detail["mutually_exclusive"],
        "group_id": detail["group_id"],
        "created_at": datetime.fromisoformat(detail["created_at"]),
        "outcomes": [{
            "id": OUTCOME_ID, "external_id": TICKER, "name": outcome["name"],
            "p": outcome["probability"], "open": outcome["opening_probability"],
            "captures": captures,
        }],
    }]))


# ---------------------------------------------------------------------------
# Serving
# ---------------------------------------------------------------------------


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


def _forget_process_caches():
    from app.utils import candidate_base as _cb
    from app.utils import request_cache as _rc
    from app.utils.principal_independent_cache import clear_shared_builds

    _rc._reset_last_good_for_tests()
    _rc._reset_inflight_for_tests()
    _cb._reset_l0_for_tests()
    clear_shared_builds()


def _get(*paths: str, concurrent: int = 1) -> list[dict]:
    """ORDINARY reads. No bypass parameter exists, so none is passed."""

    async def _go():
        _forget_process_caches()
        async with _client() as ac:
            jobs = [ac.get(p) for p in paths for _ in range(concurrent)]
            responses = await asyncio.gather(*jobs)
        bodies = []
        for r in responses:
            assert r.status_code == 200, f"{r.request.url} -> {r.status_code}: {r.text[:400]}"
            bodies.append(r.json())
        return bodies

    return _arun(_go())


def _timeline(market_id=MARKET_ID, hours=168, top=50) -> dict:
    return _get(f"/api/futures/{market_id}/probability-timeline?hours={hours}&top={top}")[0]


def _history(market_id=MARKET_ID, hours=168) -> dict:
    return _get(f"/api/futures/{market_id}/history?hours={hours}")[0]


def _detail(market_id=MARKET_ID) -> dict:
    return _get(f"/api/futures/{market_id}")[0]


WEEK_START = FROZEN_NOW - timedelta(hours=168)


def _timeline_points(body: dict, name="Yes") -> list[tuple[str, float]]:
    return [(b["timestamp"], b["outcomes"][name]) for b in body["timeline"] if name in b["outcomes"]]


def _history_points(body: dict, outcome_id=OUTCOME_ID) -> list[tuple[str, float]]:
    for entry in body["outcomes"]:
        if entry["outcome_id"] == outcome_id:
            return [(pt["timestamp"], pt["probability"]) for pt in entry["history"]]
    return []


def _in_week(points):
    return [(ts, v) for ts, v in points if datetime.fromisoformat(ts) >= WEEK_START]


def _hour_bucket(iso: str) -> str:
    stamp = datetime.fromisoformat(iso)
    return stamp.replace(minute=0, second=0, microsecond=0).isoformat()


def _cold_then_warm(broker) -> tuple[dict, dict, dict, dict]:
    cold_t, cold_h = _timeline(), _history()
    broker.run_enqueued()
    return cold_t, cold_h, _timeline(), _history()


# ═══ A — THE NAMED REPLAY (red first) ═══════════════════════════════════════


def _assert_named_contract(timeline: dict, history: dict):
    """The contract #7351 names. Raises AssertionError — reused by the mutant in D."""
    served_h = _in_week(_history_points(history))
    expected_h = sorted(ADMITTED_IN_WEEK + [CAPTURE_IN_WEEK])
    missing = [ts for ts, _ in ADMITTED_IN_WEEK if ts not in {t for t, _ in served_h}]
    assert not missing, f"MISSING ELIGIBLE VENUE TIMESTAMPS on /history: {missing}"
    assert served_h == expected_h, (
        "/history must serve EXACTLY the admitted venue observations plus our own "
        f"capture, at their real instants and raw values.\n got  {served_h}\n want {expected_h}"
    )
    for ts, reason in REJECTED_IN_WEEK.items():
        assert ts not in {t for t, _ in served_h}, f"{ts} must be rejected ({reason})"

    # The phone's reader buckets to the hour to DEDUPLICATE — one venue point per
    # (outcome, hour), the LAST one in the hour (a real quote, never a median),
    # and an hour our capture reached keeps the capture.
    #
    # 🔴 BUT IT SERVES THAT OBSERVATION AT THE INSTANT THE VENUE RECORDED IT. The
    # bucket decides WHICH observation is served, never WHEN it happened. Two of
    # the specimen's own candles close off the hour — 08:01 and 09:41 — and the
    # first presentation published them as 08:00 and 09:00: times nobody observed,
    # on the one series whose whole claim is that these are real observations at
    # real instants. `/history` served the true minute all along, so the two
    # readers disagreed about when the same Kalshi candle closed.
    last_in_hour: dict[str, tuple[str, float]] = {}
    for ts, value in ADMITTED_IN_WEEK:
        last_in_hour[_hour_bucket(ts)] = (ts, value)
    # An hour our own capture reached is the capture's, and a capture is still
    # served at its bucket start — nothing about our own rows moved.
    last_in_hour.pop(_hour_bucket(CAPTURE_IN_WEEK[0]), None)
    cells = dict(last_in_hour.values())
    cells[_hour_bucket(CAPTURE_IN_WEEK[0])] = CAPTURE_IN_WEEK[1]
    served_t = _in_week(_timeline_points(timeline))
    missing_t = [b for b in cells if b not in {t for t, _ in served_t}]
    assert not missing_t, f"MISSING ELIGIBLE VENUE TIMESTAMPS on /probability-timeline: {missing_t}"
    assert served_t == sorted(cells.items()), (
        f"/probability-timeline observations.\n got  {served_t}\n want {sorted(cells.items())}"
    )
    # Stated as itself, so the mutant that re-floors these cannot pass by
    # agreeing with a table that was floored the same way.
    off_the_hour = {"2026-09-19T08:01:00+00:00", "2026-09-19T09:41:00+00:00"}
    assert off_the_hour <= {t for t, _ in served_t}, (
        "a venue observation was relabelled with its bucket start: "
        f"{sorted(off_the_hour - {t for t, _ in served_t})}"
    )
    # …and BOTH readers say the same instant for the same candle.
    assert off_the_hour <= {t for t, _ in served_h}


def test_A1_named_replay_both_readers_serve_the_venue_history_our_polls_missed(venue, broker):
    _seed_specimen()

    # COLD — and it is the named production failure, reproduced from the saved
    # responses: nine observations found only by stretching to 90 days, ONE of
    # them inside the week the phone shows.
    cold_t, cold_h = _timeline(), _history()
    saved_t = _fx("59165099-timeline.json")
    assert cold_t["timeline"] == saved_t["timeline"]
    assert (cold_t["hours"], cold_t["actual_hours"]) == (168, 2160)
    assert _history_points(cold_h) == [
        (pt["timestamp"], pt["probability"])
        for pt in _fx("59165099-history.json")["outcomes"][0]["history"]
    ]
    assert len(_in_week(_timeline_points(cold_t))) == 1
    assert venue.provider_requests() == [], "a page handler called a provider"

    broker.run_enqueued()          # the enqueued task, through its real function
    warm_t, warm_h = _timeline(), _history()   # a later ORDINARY read

    _assert_named_contract(warm_t, warm_h)

    # The metadata describes what is served — no more, no less.
    for body, points in ((warm_t, _timeline_points(warm_t)), (warm_h, _history_points(warm_h))):
        stamps = sorted(datetime.fromisoformat(ts) for ts, _ in points)
        assert body["coverage_start"] == stamps[0].isoformat()
        assert body["coverage_end"] == stamps[-1].isoformat()
        assert body["observation_times"] == len(set(stamps))
        assert body["coverage_hours"] == round((stamps[-1] - stamps[0]).total_seconds() / 3600, 2)
        assert all(datetime.fromisoformat(ts) >= FROZEN_NOW - timedelta(hours=body["actual_hours"])
                   for ts, _ in points), "a point outside the window the reader says it searched"
        assert all(datetime.fromisoformat(ts) <= FROZEN_NOW for ts, _ in points), "a synthetic 'now' endpoint"
    assert warm_h["total_data_points"] == len(_history_points(warm_h))
    # Sixteen real observations in the week no longer need 90 days to find nine.
    assert (warm_t["actual_hours"], warm_h["actual_hours"]) == (720, 720)
    vh = warm_h["venue_history"]
    assert vh["state"] == "warm" and vh["scale"] == "venue_yes_probability_raw"
    assert vh["points_served"] == len([p for p in warm_h["outcomes"][0]["history"]
                                       if p.get("provenance") == "venue_history"])
    # Provenance: a venue sample never passes as one of our captures.
    by_ts = {p["timestamp"]: p for p in warm_h["outcomes"][0]["history"]}
    assert by_ts[CAPTURE_IN_WEEK[0]]["bookmaker"] == "consensus"
    assert "provenance" not in by_ts[CAPTURE_IN_WEEK[0]]
    assert by_ts["2026-09-16T03:00:00+00:00"]["bookmaker"] == "kalshi"


def test_A2_the_saved_input_is_the_same_venue_record_the_replay_serves():
    """The brief's ten-candle 7d response ⊂ the 31d response the fill replays —
    record for record — and every saved input is byte-identical to its SHA."""
    for name, digest in FIXTURE_SHA256.items():
        assert hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest() == digest, name
    saved = _fx("59165099-kalshi-7d-hourly.json")["markets"][0]
    replay = _fx("kalshi-60m-31d.json")["markets"][0]
    assert saved["market_ticker"] == replay["market_ticker"] == TICKER
    by_end = {c["end_period_ts"]: c for c in replay["candlesticks"]}
    assert len(saved["candlesticks"]) == 10
    for candle in saved["candlesticks"]:
        assert by_end[candle["end_period_ts"]] == candle
    event = _fx("59165099-kalshi-event.json")["event"]
    assert event["event_ticker"] == EVENT_TICKER and event["markets"][0]["ticker"] == TICKER


def test_A3_every_candle_in_the_week_is_admitted_or_rejected_for_a_named_reason(venue, broker):
    """No candle is unaccounted for, and each verdict is the rule's own."""
    from app.tasks.event_chart_backfill import normalize_candle

    _seed_specimen()
    _cold_then_warm(broker)
    seen: dict[str, float] = {}
    for recorded in RECORDED_KALSHI_REQUESTS:          # finest tier first
        for candle in _fx(recorded["file"])["markets"][0]["candlesticks"]:
            stamp = datetime.fromtimestamp(candle["end_period_ts"], tz=timezone.utc)
            if stamp >= WEEK_START:
                price = normalize_candle(candle)
                assert price is not None, "a candle with no supported price would need its own reason"
                seen.setdefault(stamp.isoformat(), round(price, 6))
    admitted = dict(ADMITTED_IN_WEEK)
    assert set(seen) == set(admitted) | set(REJECTED_IN_WEEK), "a candle in the week is unaccounted for"
    for ts, value in admitted.items():
        assert seen[ts] == pytest.approx(value, abs=1e-9), ts
    # The rejected candle really is inside a finer candle's 30-minute claim.
    minute = [datetime.fromtimestamp(c["end_period_ts"], tz=timezone.utc)
              for c in _fx("kalshi-1m-24h.json")["markets"][0]["candlesticks"]]
    for ts in REJECTED_IN_WEEK:
        assert min(abs((datetime.fromisoformat(ts) - m).total_seconds()) for m in minute) <= 1800


# ═══ B — LIFECYCLE ══════════════════════════════════════════════════════════


def test_B1_cold_read_asks_once_the_fill_replays_the_recorded_requests_warm_read_uses_it(venue, broker):
    _seed_specimen()
    cold = _timeline()
    assert cold["venue_history"]["state"] == "cold"
    assert cold["venue_history"]["fill"] == "requested"
    assert broker.calls == [{"kwargs": {"market_ids": [MARKET_ID]}, "options": {"queue": "background"}}]
    assert venue.provider_requests() == [], "no provider HTTP on the page request"

    again = _history()      # a second cold reader, before the fill has run
    assert again["venue_history"]["fill"] == "already_claimed"
    assert len(broker.calls) == 1

    results = broker.run_enqueued()
    assert results[0]["results"][0]["status"] == "ok"
    # The fill asked the venue EXACTLY what the saved bytes answered.
    assert [
        {k: r[k] for k in ("period_interval", "start_ts", "end_ts")} for r in venue.provider_requests()
    ] == [{k: r[k] for k in ("period_interval", "start_ts", "end_ts")} for r in RECORDED_KALSHI_REQUESTS]
    assert all(r["tickers"] == [TICKER] for r in venue.provider_requests())

    before = len(venue.provider_requests())
    warm = _timeline()
    assert warm["venue_history"]["state"] == "warm"
    assert warm["venue_history"]["fill"] == "answered_recently"
    assert broker.calls == [] and len(venue.provider_requests()) == before


def test_B2_concurrent_cold_readers_buy_one_fill(venue, broker):
    _seed_specimen()
    bodies = _get(
        f"/api/futures/{MARKET_ID}/probability-timeline?hours=168&top=50",
        f"/api/futures/{MARKET_ID}/history?hours=168",
        concurrent=6,
    )
    fills = sorted(b["venue_history"]["fill"] for b in bodies)
    assert fills == ["already_claimed"] * 11 + ["requested"], fills
    assert len(broker.calls) == 1
    assert venue.provider_requests() == []
    broker.run_enqueued()
    assert len(venue.provider_requests()) == 3, "twelve readers, one market, three venue requests"


def test_B3_a_stale_cache_keeps_a_fresher_capture_and_asks_again_once(venue, broker):
    _seed_specimen()
    _cold_then_warm(broker)

    # Four hours on: our poller has written a capture AFTER the cache was built.
    FrozenDatetime.current = FROZEN_NOW + timedelta(hours=4)
    fresh_at = FROZEN_NOW + timedelta(hours=3, minutes=5)

    async def _add():
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        import app.models.models as m

        engine = create_async_engine(DB_URL)
        async with async_sessionmaker(engine)() as s:
            s.add(m.FuturesOddsSnapshot(outcome_id=OUTCOME_ID, bookmaker="kalshi",
                                        probability=0.045, captured_at=fresh_at))
            await s.commit()
        await engine.dispose()

    _arun(_add())
    body = _history()
    points = _history_points(body)
    assert points[-1] == (fresh_at.isoformat(), 0.045), "the fresher capture must be the last point"
    assert ("2026-09-16T03:00:00+00:00", 0.085) in points, "the stale cache is still layered in"
    assert body["venue_history"]["fill"] == "requested", "stale → one refresh"
    assert len(broker.calls) == 1
    assert _history()["venue_history"]["fill"] == "already_claimed"


def test_B4_partial_provider_failure_serves_what_was_fetched_and_says_degraded(venue, broker):
    _seed_specimen()
    venue.kalshi_mode = "fail_60m"
    _timeline()
    result = broker.run_enqueued()[0]["results"][0]
    assert result["status"] == "degraded" and result["stats"]["window_errors"] >= 1
    served = dict(_in_week(_history_points(_history())))
    # The minute and daily tiers answered; the hourly tier is simply absent.
    assert served["2026-09-19T08:01:00+00:00"] == 0.06
    assert served["2026-09-18T04:00:00+00:00"] == 0.07
    assert "2026-09-16T03:00:00+00:00" not in served, "an hourly point was fabricated for a failed tier"


@pytest.mark.parametrize("mode", ["http_500", "http_429", "empty"])
def test_B5_a_failed_or_empty_fill_never_costs_the_last_good_history(venue, broker, mode):
    _seed_specimen()
    _, _, good_t, good_h = _cold_then_warm(broker)

    FrozenDatetime.current = FROZEN_NOW + timedelta(hours=4)      # stale → refresh
    venue.kalshi_mode = mode
    assert _timeline()["venue_history"]["fill"] == "requested"
    result = broker.run_enqueued()[0]["results"][0]
    assert result["status"] == ("ok" if mode == "empty" else "degraded")
    after_t, after_h = _timeline(), _history()
    assert _in_week(_history_points(after_h)) == _in_week(_history_points(good_h))
    assert _in_week(_timeline_points(after_t)) == _in_week(_timeline_points(good_t))
    # …and the bad answer is itself cached as an ATTEMPT: no retry storm.
    assert after_t["venue_history"]["fill"] == "answered_recently"
    assert broker.calls == []


@pytest.mark.parametrize("mode", ["http_500", "http_429", "empty"])
def test_B6_a_venue_with_nothing_to_say_adds_nothing_and_is_not_asked_again(venue, broker, mode):
    _seed_specimen()
    cold = _timeline()
    venue.kalshi_mode = mode
    broker.run_enqueued()
    after = _timeline()
    assert after["timeline"] == cold["timeline"], "observations appeared from a venue that gave none"
    assert after["venue_history"]["points_served"] == 0
    assert after["venue_history"]["fill"] == "answered_recently", "negative cache: no poisoned-cold loop"
    assert broker.calls == []
    # Not permanently cold either: once the attempt ages out, a healthy venue fills it.
    FrozenDatetime.current = FROZEN_NOW + timedelta(hours=4)
    venue.kalshi_mode = "recorded"
    assert _timeline()["venue_history"]["fill"] == "requested"


def test_B7_dispatch_failure_hands_the_claim_back_and_a_dead_task_cannot_hold_it(venue, broker):
    from app.tasks.generic_market_history_fill import CLAIM_TTL_SECONDS
    from app.utils.generic_market_history import claim_key

    _seed_specimen()
    broker.fail_next_dispatch = True
    assert _timeline()["venue_history"]["fill"] == "dispatch_failed"
    assert _redis().get(claim_key(MARKET_ID)) is None, "a failed dispatch kept the claim"
    assert _timeline()["venue_history"]["fill"] == "requested", "the next reader could not retry"

    # The task is now 'running' and dies without writing. Nothing releases the
    # claim — and nothing has to: it carries its own expiry.
    broker.calls.clear()
    ttl = _redis().ttl(claim_key(MARKET_ID))
    assert 0 < ttl <= CLAIM_TTL_SECONDS, f"claim TTL {ttl}: a permanent claim"
    assert _timeline()["venue_history"]["fill"] == "already_claimed"
    _redis().delete(claim_key(MARKET_ID))        # == the TTL elapsing
    assert _timeline()["venue_history"]["fill"] == "requested"


def test_B8_the_hourly_budget_bounds_a_crawler(venue, broker):
    from app.tasks.generic_market_history_fill import HOURLY_FILL_CAP
    from app.utils.generic_market_history import budget_key, claim_key

    _seed_specimen()
    _redis().set(budget_key(FROZEN_NOW.strftime("%Y%m%d%H")), HOURLY_FILL_CAP)
    assert _timeline()["venue_history"]["fill"] == "hourly_cap"
    assert broker.calls == [] and _redis().get(claim_key(MARKET_ID)) is None


def _set_market_status(status: str, market_id=MARKET_ID):
    """Settle (or re-open) a seeded market, the way the poller eventually does."""

    async def _go():
        from sqlalchemy import update
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        import app.models.models as m

        engine = create_async_engine(DB_URL)
        async with async_sessionmaker(engine)() as s:
            await s.execute(
                update(m.FuturesMarket)
                .where(m.FuturesMarket.id == market_id)
                .values(status=status)
            )
            await s.commit()
        await engine.dispose()

    _arun(_go())


@pytest.mark.parametrize("mode", ["http_500", "http_429", "empty"])
def test_B9_a_settled_markets_failed_fill_recovers_instead_of_freezing_for_a_week(venue, broker, mode):
    """A settled payload is kept for SEVEN DAYS, so what is in it had better be an answer.

    The first presentation short-circuited a settled market on any DATED attempt,
    whatever it contained. A venue that was rate-limited for thirty seconds
    therefore froze that chart for a week, and the failure is silent by
    construction: the reader sees a thin chart and a warm cache, and nothing ever
    asks again. This walks the real seam — claim, fill, read — and requires the
    recovery to happen on the ordinary bounded retry.
    """
    _seed_specimen()
    _set_market_status("settled")
    venue.kalshi_mode = mode
    assert _timeline()["venue_history"]["fill"] == "requested"
    broker.run_enqueued()

    failed = _timeline()
    assert failed["venue_history"]["points_served"] == 0
    # Bounded, not a storm: inside the refresh age the bad attempt stands.
    assert failed["venue_history"]["fill"] == "answered_recently"
    assert broker.calls == []

    # …but it is NOT the week's answer. Once the attempt ages out the venue is
    # asked again, and a healthy one fills the chart.
    FrozenDatetime.current = FROZEN_NOW + timedelta(hours=4)
    venue.kalshi_mode = "recorded"
    assert _timeline()["venue_history"]["fill"] == "requested", (
        "a settled market's failed fill was treated as its answer"
    )
    broker.run_enqueued()
    warm = _timeline()
    assert warm["venue_history"]["state"] == "warm"
    assert len(_in_week(_timeline_points(warm))) > 1
    assert _payload()["market_settled"] is True

    # And NOW the retries stop: a successful post-settlement fill is the answer,
    # even though it is older than the refresh age.
    FrozenDatetime.current = FROZEN_NOW + timedelta(hours=8)
    assert _timeline()["venue_history"]["fill"] == "settled_and_already_answered"
    assert broker.calls == []


def test_B10_a_fill_taken_before_settlement_is_not_a_settled_markets_answer(venue, broker):
    """It cannot be: it does not contain the hours that decided the question."""
    _seed_specimen()
    _cold_then_warm(broker)                      # a healthy fill while still OPEN
    assert _payload()["market_settled"] is False

    _set_market_status("settled")
    FrozenDatetime.current = FROZEN_NOW + timedelta(hours=4)
    assert _timeline()["venue_history"]["fill"] == "requested", (
        "a pre-settlement fill was frozen in as the settled answer"
    )
    broker.run_enqueued()
    assert _payload()["market_settled"] is True

    FrozenDatetime.current = FROZEN_NOW + timedelta(hours=8)
    assert _timeline()["venue_history"]["fill"] == "settled_and_already_answered"


def test_B11_an_empty_post_settlement_fill_is_not_answered_by_the_series_it_carried(
    venue, broker
):
    """open fill → settle → EMPTY fill → bounded retry → healthy fill. CERT-3152.

    B9 walks a settled market whose fills fail with nothing in the cache, and
    B10 walks a healthy fill taken before settlement. The gap between them is the
    state a real market actually passes through, and it is the one that looks
    fine:

      a healthy series fetched while the market was OPEN, then settlement, then
      one attempt that fetches NOTHING.

    Last-good carries the old series forward — correctly; that is what B5 pins —
    and `build_payload` calls a payload with points `ok`, and the fill that ran
    stamps `market_settled`. Every clause of the settled short-circuit is then
    satisfied by a payload whose attempt asked the venue and came back with
    nothing, so the chart froze for the seven-day settled TTL WITHOUT the hours
    that decided the question — the only hours a settled chart is missing. The
    reader sees a full-looking chart that stops before the end, a warm cache, and
    no retry for a week.

    The distinction this arm holds the code to is between the payload's DISPLAY
    series and THIS ATTEMPT's yield (`stats.fetched_points`, counted before the
    last-good merge).
    """
    _seed_specimen()
    _, _, open_t, _ = _cold_then_warm(broker)         # a healthy fill while OPEN
    healthy = _in_week(_timeline_points(open_t))
    assert len(healthy) > 1
    assert _payload()["market_settled"] is False

    _set_market_status("settled")
    venue.kalshi_mode = "empty"
    FrozenDatetime.current = FROZEN_NOW + timedelta(hours=4)
    assert _timeline()["venue_history"]["fill"] == "requested"
    broker.run_enqueued()

    carried = _payload()
    assert carried["market_settled"] is True
    assert carried["status"] == "ok", "last-good still carries the series (B5)"
    assert carried["stats"]["fetched_points"] == 0, "and the attempt fetched none of it"
    assert _in_week(_timeline_points(_timeline())) == healthy, "the chart kept its history"

    # 🔴 THE FINDING: a full payload is not an answered attempt.
    FrozenDatetime.current = FROZEN_NOW + timedelta(hours=8)
    assert _timeline()["venue_history"]["fill"] == "requested", (
        "an empty post-settlement fill was frozen in as the week's answer "
        "because the series it carried made the payload look complete"
    )
    broker.run_enqueued()                              # second empty attempt

    # …and the retry is what recovers the terminal history the moment the venue
    # publishes it, which is the whole point of not freezing.
    FrozenDatetime.current = FROZEN_NOW + timedelta(hours=12)
    venue.kalshi_mode = "recorded"
    assert _timeline()["venue_history"]["fill"] == "requested"
    broker.run_enqueued()
    answered = _payload()
    assert answered["stats"]["fetched_points"] > 0
    assert answered["settled_empty_attempts"] == 0, "a venue that answered is not silent"
    assert len(_in_week(_timeline_points(_timeline()))) >= len(healthy)

    # NOW the retries stop, older than the refresh age and never asked again.
    FrozenDatetime.current = FROZEN_NOW + timedelta(hours=16)
    assert _timeline()["venue_history"]["fill"] == "settled_and_already_answered"
    assert broker.calls == []


def test_B12_a_venue_that_purged_a_settled_market_is_asked_a_bounded_number_of_times(
    venue, broker
):
    """The ceiling. Kalshi purges a settled market's candles (gotcha #35).

    B11's repair says "an empty attempt is not the answer", and taken alone that
    is an unbounded three-hourly request per settled chart for the whole seven-
    day TTL — the same defect, paid to the venue instead of the reader. So the
    venue is asked `MAX_SETTLED_EMPTY_ATTEMPTS` times, and then the series it
    already has is accepted as all there is.
    """
    from app.tasks.generic_market_history_fill import MAX_SETTLED_EMPTY_ATTEMPTS

    _seed_specimen()
    _, _, open_t, _ = _cold_then_warm(broker)
    healthy = _in_week(_timeline_points(open_t))

    _set_market_status("settled")
    venue.kalshi_mode = "empty"
    for attempt in range(1, MAX_SETTLED_EMPTY_ATTEMPTS + 1):
        FrozenDatetime.current = FROZEN_NOW + timedelta(hours=4 * attempt)
        assert _timeline()["venue_history"]["fill"] == "requested", (
            f"attempt {attempt} is inside the ceiling of "
            f"{MAX_SETTLED_EMPTY_ATTEMPTS} and the venue must still be asked"
        )
        broker.run_enqueued()
        assert _payload()["settled_empty_attempts"] == attempt

    FrozenDatetime.current = FROZEN_NOW + timedelta(
        hours=4 * (MAX_SETTLED_EMPTY_ATTEMPTS + 1)
    )
    assert _timeline()["venue_history"]["fill"] == "settled_and_already_answered"
    assert broker.calls == []
    # Spending the ceiling costs the reader nothing: the chart still draws every
    # observation it had.
    assert _in_week(_timeline_points(_timeline())) == healthy


@pytest.mark.parametrize("mode", ["http_500", "http_429"])
def test_B13_failed_settled_attempts_do_not_exhaust_the_silence_ceiling(
    venue, broker, mode
):
    """Three failures in a row, then a healthy answer. CERT-3156.

    B12's ceiling is about a venue that ANSWERS and has nothing to give —
    Kalshi's purge. A 429 is not that: it is the venue declining to answer, and
    counting it spends a bounded budget on a fact nobody established. The first
    cut counted both, so three rate-limited attempts inside nine hours froze the
    chart for the seven-day settled TTL on a `degraded` payload — the very
    failure this ship exists to remove, rebuilt out of the repair for it.

    So: `MAX_SETTLED_EMPTY_ATTEMPTS` failures must leave the counter at zero and
    the market still askable, the carried chart must survive every one of them,
    and the healthy answer that follows must land and end the retries.
    """
    from app.tasks.generic_market_history_fill import MAX_SETTLED_EMPTY_ATTEMPTS

    _seed_specimen()
    _, _, open_t, _ = _cold_then_warm(broker)
    healthy = _in_week(_timeline_points(open_t))
    assert len(healthy) > 1

    _set_market_status("settled")
    venue.kalshi_mode = mode
    for attempt in range(1, MAX_SETTLED_EMPTY_ATTEMPTS + 1):
        FrozenDatetime.current = FROZEN_NOW + timedelta(hours=4 * attempt)
        assert _timeline()["venue_history"]["fill"] == "requested", (
            f"failure {attempt} of {MAX_SETTLED_EMPTY_ATTEMPTS} exhausted a "
            "ceiling that is about SILENCE, not about errors"
        )
        broker.run_enqueued()
        after = _payload()
        assert after["status"] == "degraded"
        assert after["settled_empty_attempts"] == 0, (
            "a failed attempt advanced the silence counter"
        )
        # The reader keeps the chart through every failure (B5, under settlement).
        assert _in_week(_timeline_points(_timeline())) == healthy

    # One past the ceiling, still asking.
    FrozenDatetime.current = FROZEN_NOW + timedelta(
        hours=4 * (MAX_SETTLED_EMPTY_ATTEMPTS + 1)
    )
    assert _timeline()["venue_history"]["fill"] == "requested"

    # …and the healthy answer lands and ends them.
    venue.kalshi_mode = "recorded"
    broker.run_enqueued()
    answered = _payload()
    assert answered["stats"]["fetched_points"] > 0
    assert answered["settled_empty_attempts"] == 0
    FrozenDatetime.current = FROZEN_NOW + timedelta(
        hours=4 * (MAX_SETTLED_EMPTY_ATTEMPTS + 2)
    )
    assert _timeline()["venue_history"]["fill"] == "settled_and_already_answered"
    assert broker.calls == []


def test_B14_an_evicted_bank_is_served_from_the_durable_tier_without_asking_the_venue(
    venue, broker
):
    """#7807 — the eviction #7563 measured, staged for real, costs the reader nothing.

    THE DEFECT. The bank lives only in `futures:generic-history:v1:{id}` on a
    100 MB `allkeys-lru` instance. A ~35 KB value nobody reads is the ideal
    eviction victim, so the declared 36 h bought under four hours on 3 of 3
    markets: three charts proven warm at 13:05Z read `cold` at 17:17Z with the
    pre-#7351 numbers back. `DEL` is exactly what LRU does to that key, and it is
    the only thing this test does differently from B1.

    Everything asserted below is the same chart, from the same payload, through
    the same three identity bindings — the tier that held it is the only change.
    """
    from app.tasks.generic_market_history_fill import CACHE_TTL_SECONDS
    from app.utils.generic_market_history import cache_key

    _seed_specimen()
    _, _, warm_t, warm_h = _cold_then_warm(broker)
    assert warm_t["venue_history"]["state"] == "warm"
    assert warm_t["venue_history"]["tier"] == "cache", "Redis is still the fast tier"
    _assert_named_contract(warm_t, warm_h)
    served = _in_week(_timeline_points(warm_t))
    asked = len(venue.provider_requests())

    # ── the eviction, and nothing else ──────────────────────────────────────
    # The DELETE is the staged eviction, so it may not live inside an `assert`:
    # under `python -O` the assert vanishes and with it the only thing this test
    # does differently from B1 — it would pass having evicted nothing
    # (`py/side-effect-in-assert`, and here the side effect IS the experiment).
    evicted = _redis().delete(cache_key(MARKET_ID))
    assert evicted == 1, "the bank was not in Redis to begin with"
    assert _payload() is None, "the bank is gone from Redis"

    after_t, after_h = _timeline(), _history()

    assert after_t["venue_history"]["state"] == "warm", (
        "an evicted bank read as `cold` — the durable tier did not answer, and "
        "this is #7563's defect exactly"
    )
    assert after_t["venue_history"]["tier"] == "durable"
    assert _in_week(_timeline_points(after_t)) == served, "a different chart"
    _assert_named_contract(after_t, after_h)
    assert len(venue.provider_requests()) == asked, (
        "recovering an evicted bank must cost NO outbound venue request"
    )
    assert broker.calls == [], "nor a fill"

    # ── and the next reader is back on the fast tier, not on the database ───
    ttl = _redis().ttl(cache_key(MARKET_ID))
    assert 0 < ttl <= CACHE_TTL_SECONDS, (
        f"rehydrated with ttl={ttl}: a restored bank must get what is LEFT of "
        "its declared life, never a fresh one"
    )
    assert _timeline()["venue_history"]["tier"] == "cache"


def test_B15_a_durable_bank_past_its_declared_life_is_not_served(venue, broker):
    """#7807 makes the declared 36 h REAL — it does not make it longer.

    The durable row has no TTL of its own, so without this bound the tier would
    quietly convert an expiring cache into a permanent one and hand a reader a
    price line the cache policy had already retired. Past the declared life the
    market is cold and the planner gets its chance to refill, which is the same
    answer the reader would have had before this ship.
    """
    from app.tasks.generic_market_history_fill import CACHE_TTL_SECONDS
    from app.utils.generic_market_history import cache_key

    _seed_specimen()
    _cold_then_warm(broker)
    _redis().delete(cache_key(MARKET_ID))

    FrozenDatetime.current = FROZEN_NOW + timedelta(seconds=CACHE_TTL_SECONDS + 60)
    body = _timeline()

    assert body["venue_history"]["state"] == "cold"
    assert body["venue_history"]["fill"] == "requested", "the planner still asks"


# ═══ C — IDENTITY AND SHAPE ═════════════════════════════════════════════════

OTHER_MARKET_ID, OTHER_OUTCOME_ID, OTHER_TICKER = 59165100, 219751700, "KXOTHERQUESTION-26-YES1"


def _candle(end_ts: int, bid: str | None, ask: str | None, *, trade: str | None = None,
            previous: str | None = None) -> dict:
    """SYNTHETIC Kalshi candle in the venue's real shape."""
    price = {}
    if trade is not None:
        price["close_dollars"] = trade
    if previous is not None:
        price["previous_dollars"] = previous
    return {
        "end_period_ts": end_ts, "price": price, "volume_fp": "0.00", "open_interest_fp": "0.00",
        "yes_bid": {"close_dollars": bid} if bid is not None else {},
        "yes_ask": {"close_dollars": ask} if ask is not None else {},
    }


def _hours_ago(hours: float) -> int:
    return int((FROZEN_NOW - timedelta(hours=hours)).timestamp()) // 3600 * 3600


def _payload(market_id=MARKET_ID) -> dict:
    from app.utils.generic_market_history import cache_key

    raw = _redis().get(cache_key(market_id))
    return json.loads(raw) if raw else None


def _put_payload(payload: dict, market_id=MARKET_ID):
    from app.utils.generic_market_history import cache_key

    _redis().setex(cache_key(market_id), 3600, json.dumps(payload))


def test_C1_another_markets_yes_cannot_reach_this_chart(venue, broker):
    """Two binaries, two outcomes named "Yes". The name is never the key."""
    _seed_specimen()
    _arun(_seed([{
        "id": OTHER_MARKET_ID, "source": "kalshi", "external_id": "KXOTHERQUESTION-26",
        "name": "Will something entirely different happen?",
        "outcomes": [{"id": OTHER_OUTCOME_ID, "external_id": OTHER_TICKER, "name": "Yes", "p": 0.91,
                      "captures": [(FROZEN_NOW - timedelta(hours=2), 0.91)]}],
    }]))
    venue.kalshi_mode = "custom"
    venue.kalshi_custom = {60: {"markets": [{"market_ticker": OTHER_TICKER, "candlesticks": [
        _candle(_hours_ago(h), "0.90", "0.92") for h in (30, 20, 10)]}]}}
    _timeline(OTHER_MARKET_ID)
    broker.run_enqueued()
    other = _payload(OTHER_MARKET_ID)
    assert other["outcomes"][str(OTHER_OUTCOME_ID)]["contract"]["ticker"] == OTHER_TICKER
    assert _payload(MARKET_ID) is None, "one market's fill wrote another market's key"
    cold = _timeline()

    # 1. The other market's payload, filed under THIS market's key.
    _put_payload(other)
    body = _timeline()
    assert body["timeline"] == cold["timeline"]
    assert {r["reason"] for r in body["venue_history"]["refusals"]} == {"market_id_mismatch"}

    # 2. Right market envelope, the other market's OUTCOME.
    forged = {**other, "market_id": MARKET_ID, "market_external_id": EVENT_TICKER}
    _put_payload(forged)
    body = _timeline()
    assert body["timeline"] == cold["timeline"]
    assert [r["reason"] for r in body["venue_history"]["refusals"]] == ["not_a_charted_outcome_of_this_market"]

    # 3. Right market, right outcome id — the other market's CONTRACT.
    entry = dict(other["outcomes"][str(OTHER_OUTCOME_ID)], outcome_id=OUTCOME_ID)
    _put_payload({**forged, "outcomes": {str(OUTCOME_ID): entry}})
    body, hist = _timeline(), _history()
    assert body["timeline"] == cold["timeline"]
    assert [r["reason"] for r in body["venue_history"]["refusals"]] == ["contract_outcome_external_id_mismatch"]
    assert all(v != 0.91 for _, v in _history_points(hist)), "the other question's price reached this chart"


@pytest.mark.parametrize("corruption, reason", [
    ("reversed", "timestamps_not_strictly_ascending"),
    ("future", "timestamp_after_build"),
    ("naive", "timestamp_unparseable_or_naive"),
    ("out_of_range", "probability_out_of_range"),
    ("scale", "scale_mismatch"),
    ("version", "schema_or_version_mismatch"),
])
def test_C2_a_corrupted_cache_is_refused_whole_not_repaired(venue, broker, corruption, reason):
    _seed_specimen()
    cold_t, cold_h, warm_t, _ = _cold_then_warm(broker)
    assert warm_t["timeline"] != cold_t["timeline"]
    payload = _payload()
    points = payload["outcomes"][str(OUTCOME_ID)]["points"]
    if corruption == "reversed":
        points.reverse()
    elif corruption == "future":
        points[-1][0] = (FROZEN_NOW + timedelta(days=2)).isoformat()
    elif corruption == "naive":
        points[3][0] = points[3][0].replace("+00:00", "")
    elif corruption == "out_of_range":
        points[3][1] = 1.7
    elif corruption == "scale":
        payload["scale"] = "renormalised_to_todays_field"
    elif corruption == "version":
        payload["version"] = "v0"
    _put_payload(payload)
    body, hist = _timeline(), _history()
    assert body["timeline"] == cold_t["timeline"], "a corrupted series was partly served"
    assert _history_points(hist) == _history_points(cold_h)
    assert reason in {r["reason"] for r in body["venue_history"]["refusals"]}


FIELD_MARKET_ID = 59165200
FIELD = [  # (outcome id, ticker suffix, name, current p)
    (219752001, "A", "Alder", 0.40), (219752002, "B", "Birch", 0.30),
    (219752003, "C", "Cedar", 0.20), (219752004, "D", "Dogwood", 0.10),
]


def _seed_field(*, mutually_exclusive: bool, capture_scale: float = 1.0):
    captured = [FROZEN_NOW - timedelta(hours=h) for h in (50, 26, 2)]
    _arun(_seed([{
        "id": FIELD_MARKET_ID, "source": "kalshi", "external_id": "KXFIELD-26",
        "name": "Which tree wins?", "mutually_exclusive": mutually_exclusive,
        "outcomes": [{"id": oid, "external_id": f"KXFIELD-26-{sfx}", "name": name, "p": p,
                      "captures": [(ts, round(p * capture_scale, 4)) for ts in captured]}
                     for oid, sfx, name, p in FIELD],
    }]))


def _field_venue(venue: Venue):
    """SYNTHETIC hourly candles: each ticker its OWN prices, tight books."""
    venue.kalshi_mode = "custom"
    venue.kalshi_custom = {60: {"markets": [
        {"market_ticker": f"KXFIELD-26-{sfx}", "candlesticks": [
            _candle(_hours_ago(h), f"{p - 0.01 + i * 0.01:.2f}", f"{p + 0.01 + i * 0.01:.2f}")
            for i, h in enumerate((40, 30, 12))]}
        for _oid, sfx, _name, p in FIELD]}}


def test_C3_independent_binaries_stay_independent_and_a_field_is_never_renormalised(venue, broker):
    _seed_field(mutually_exclusive=False, capture_scale=1.6)     # sums to 1.6: independent binaries
    _field_venue(venue)
    _timeline(FIELD_MARKET_ID)
    broker.run_enqueued()
    tl = _timeline(FIELD_MARKET_ID, top=2)
    hist = _history(FIELD_MARKET_ID)
    for i, h in enumerate((40, 30, 12)):
        bucket = next(b for b in tl["timeline"] if b["timestamp"] == _iso(_hours_ago(h)))
        # Each line is its OWN ticker's raw mid. Not divided by a field sum, not
        # squeezed to 100, and no "Field" invented for a bucket no capture read.
        assert bucket["outcomes"] == {"Alder": round(0.40 + i * 0.01, 6), "Birch": round(0.30 + i * 0.01, 6)}
    capture_bucket = next(b for b in tl["timeline"] if "Field" in b["outcomes"])
    assert capture_bucket["outcomes"]["Field"] == pytest.approx((0.20 + 0.10) * 1.6, abs=1e-6)
    served = {e["name"]: {p["timestamp"]: p["probability"] for p in e["history"]} for e in hist["outcomes"]}
    assert served["Dogwood"][_iso(_hours_ago(40))] == 0.10
    assert hist["venue_history"]["state"] == "warm"


def _field_venue_coherent(venue: Venue, *, omit: tuple[str, int] | None = None):
    """Candles whose field sums to exactly 1.00 at every instant it is complete.

    `_field_venue` drifts each ticker up by a cent per tier, so its field sums
    1.00 / 1.04 / 1.08 and the squeeze is NOT the identity at two of its three
    instants. That is the right fixture for "the venue's own scale moved"; it
    cannot isolate a missing companion, because the scale already fails. Here the
    mids are exactly .40/.30/.20/.10 at every hour, so the ONLY thing `omit` can
    change is whether one instant has a whole field.
    """
    venue.kalshi_mode = "custom"
    venue.kalshi_custom = {60: {"markets": [
        {"market_ticker": f"KXFIELD-26-{sfx}", "candlesticks": [
            _candle(_hours_ago(h), f"{p - 0.01:.2f}", f"{p + 0.01:.2f}")
            for h in (40, 30, 12) if omit != (sfx, h)]}
        for _oid, sfx, _name, p in FIELD]}}


@pytest.mark.parametrize("capture_scale, what", [
    (1.12, "captures at 112%, so the squeeze visibly fires on our own rows too"),
    (1.00, "captures at 100%, so the squeeze is the identity at every instant we "
           "CAN measure — and the venue instants still have to answer for themselves"),
])
def test_C4_an_exclusive_fields_venue_instants_must_answer_for_themselves(venue, broker, capture_scale, what):
    """`/history` prints the #23-squeezed scale; a raw venue point is not on it.

    🔴 THE SECOND PARAMETER IS THE CONTROL. The squeeze is a WHOLE-FIELD operation:
    what it does to one outcome is a function of the other outcomes' values at the
    SAME instant. The first presentation admitted the whole market whenever every
    CAPTURED instant happened to come through unchanged — which is exactly what a
    field sitting at 100% does for as long as it sits there — and then served venue
    points at instants no capture reached. That is an inference from one instant to
    a different one. Here the captures need no squeeze at all and the series is
    still refused, because this venue's own field sums to 1.04 and 1.08 at two of
    its three instants: measured where the point is, not where the captures are.
    """
    _seed_field(mutually_exclusive=True, capture_scale=capture_scale)
    _field_venue(venue)
    _timeline(FIELD_MARKET_ID)
    broker.run_enqueued()
    hist = _history(FIELD_MARKET_ID)
    assert hist["venue_history"]["state"] == "refused", what
    assert hist["venue_history"]["refusals"][-1]["reason"] == (
        "printed_scale_is_not_the_venue_raw_scale"
    ), what
    assert all("provenance" not in p for e in hist["outcomes"] for p in e["history"])
    # The phone's reader plots the RAW scale by ruling (#7284) and may serve them.
    tl = _timeline(FIELD_MARKET_ID)
    assert tl["venue_history"]["points_served"] == 12

    # 🔴 WHAT THE WIDENED FINE TIER COSTS AT THE VENUE, DERIVED AND STATED.
    # Four tickers used to ride ONE batched request per tier — three requests for
    # the market. Kalshi's candlestick budget is `tickers × periods ≤ 9,000`, and
    # #7547 took the fine tier from 24h to 144h, so ONE ticker's minute window is
    # now 8,640 periods and no second ticker fits beside it. The fine tier is
    # therefore one request per ticker while the hourly and daily tiers still
    # batch, and a four-outcome field costs six requests instead of three.
    #
    # That is the venue's arithmetic, not a regression in the batcher, so it is
    # asserted as arithmetic: `ticker_batches` is asked how it splits this field,
    # and the number of requests must equal the number of batches it names. A
    # literal 6 here would go stale the moment either constant moves, and — worse
    # — would read as a number someone chose.
    from collections import Counter

    from app.utils.futures_chart_series import ticker_batches

    fine_periods = int(_FINE_TIER_HOURS * 60)
    fine_batches = len(ticker_batches(["a", "b", "c", "d"], periods=fine_periods,
                                      max_candles=_KALSHI_BUDGET))
    by_interval = Counter(r["period_interval"] for r in venue.provider_requests())
    assert by_interval == Counter({1: fine_batches, 60: 1, 1440: 1}), (
        f"{what}: the fine tier splits into {fine_batches} request(s) at "
        f"{fine_periods} periods per ticker; the coarser tiers still batch"
    )


def test_C4b_an_exclusive_field_with_a_hole_at_the_venue_instant_is_refused(venue, broker):
    """The control codex named: captures that need no squeeze, a venue point with
    no companion evidence.

    Every mid here is exactly its outcome's price, so the field sums to 1.00
    wherever it is whole and the scale objection of C4 cannot fire. The single
    difference is that Dogwood has no candle at one of the three hours. A field
    with a hole has no denominator at that instant, so there is nothing to
    establish that the squeeze would have left the other three alone — and the
    honest answer is a refusal, not three quarters of a field.
    """
    _seed_field(mutually_exclusive=True, capture_scale=1.0)
    _field_venue_coherent(venue, omit=("D", 30))
    _timeline(FIELD_MARKET_ID)
    broker.run_enqueued()
    hist = _history(FIELD_MARKET_ID)
    assert hist["venue_history"]["state"] == "refused"
    assert hist["venue_history"]["refusals"][-1]["reason"] == (
        "exclusive_field_incomplete_at_venue_instant"
    )
    assert all("provenance" not in p for e in hist["outcomes"] for p in e["history"])
    assert _timeline(FIELD_MARKET_ID)["venue_history"]["points_served"] == 11


def test_C4c_an_exclusive_field_whose_venue_instants_carry_the_whole_field_is_served(venue, broker):
    """And the refusal is not a blanket one, which is the whole point of measuring.

    Same exclusive market, same captures, same tickers as C4b — the one change is
    that no candle is missing. Every venue instant carries all four outcomes and
    they sum to 1.00, so the squeeze is measured to be the identity AT THE POINT
    BEING SERVED and the series is admitted. Without this control, C4 and C4b are
    equally satisfied by a route that simply refuses every exclusive field, which
    would quietly drop a capability the delivered candidate had.
    """
    _seed_field(mutually_exclusive=True, capture_scale=1.0)
    _field_venue_coherent(venue)
    _timeline(FIELD_MARKET_ID)
    broker.run_enqueued()
    hist = _history(FIELD_MARKET_ID)
    assert hist["venue_history"]["state"] == "warm"
    assert hist["venue_history"]["points_served"] == 12
    served = {e["name"]: {p["timestamp"]: p["probability"] for p in e["history"]} for e in hist["outcomes"]}
    for _oid, _sfx, name, p in FIELD:
        assert served[name][_iso(_hours_ago(30))] == pytest.approx(p), (
            "an admitted venue point must be served at its RAW value, unsqueezed"
        )


def _field_venue_at_distinct_minutes(venue: Venue):
    """The same synthetic candles, each ticker closing at its OWN minute."""
    venue.kalshi_mode = "custom"
    venue.kalshi_custom = {60: {"markets": [
        {"market_ticker": f"KXFIELD-26-{sfx}", "candlesticks": [
            _candle(_hours_ago(h) + FIELD_MINUTES[sfx] * 60,
                    f"{p - 0.01 + i * 0.01:.2f}", f"{p + 0.01 + i * 0.01:.2f}")
            for i, h in enumerate((40, 30, 12))]}
        for _oid, sfx, _name, p in FIELD]}}


FIELD_MINUTES = {"A": 7, "B": 41, "C": 23, "D": 55}


def test_C5_two_outcomes_observed_at_different_minutes_are_not_collapsed(venue, broker):
    """One hour, four tickers, four different closing minutes — four instants.

    The timeline's entry used to BE the bucket, so every outcome observed inside
    one hour shared a single reading stamped at the hour mark: four separate
    observations published as one simultaneous quote of the whole field. Nothing
    in the specimen could catch that (it has one outcome), and nothing that
    asserts a bucket's contents can catch it either, because the collapsed answer
    is what such an assertion describes.

    Non-exclusive so `/history` serves them too (C4 owns the exclusive refusal),
    and the two readers are then asked the same question: WHEN was this observed.
    """
    _seed_field(mutually_exclusive=False, capture_scale=1.6)
    _field_venue_at_distinct_minutes(venue)
    _timeline(FIELD_MARKET_ID)
    broker.run_enqueued()
    tl = _timeline(FIELD_MARKET_ID)
    hist = _history(FIELD_MARKET_ID)

    hour = _hours_ago(30)
    entries = {b["timestamp"]: b["outcomes"] for b in tl["timeline"]}
    assert _iso(hour) not in entries, (
        "an entry was published at an hour mark no outcome was observed at"
    )
    for i, (_oid, sfx, name, p) in enumerate(FIELD):
        at = _iso(hour + FIELD_MINUTES[sfx] * 60)
        assert at in entries, f"{name} was not served at the minute it was observed"
        assert list(entries[at]) == [name], (
            f"{at} carries {sorted(entries[at])} — observations of different "
            "outcomes at different instants were merged into one reading"
        )
        assert entries[at][name] == pytest.approx(round(p + 0.01, 6))

    # Both readers, the same instants, for the same candles.
    served_h = {e["name"]: {pt["timestamp"] for pt in e["history"]} for e in hist["outcomes"]}
    for _oid, sfx, name, _p in FIELD:
        assert _iso(hour + FIELD_MINUTES[sfx] * 60) in served_h[name]
    assert hist["venue_history"]["state"] == "warm"


# ── Polymarket: every provider byte below is SYNTHETIC ──────────────────────
PM_MARKET_ID, PM_YES_ID, PM_NO_ID = 59165300, 219753001, 219753002
PM_CONDITION = "0x" + "ab" * 32
PM_YES_TOKEN, PM_NO_TOKEN = "71321045679252212594626385532706912750332728571942532289631379312455583992563", \
    "52114319501245915516055106046884209969926127482827954674443846427813813222426"
PM_EVENT_ID = "990001"


def _seed_polymarket():
    captured = [FROZEN_NOW - timedelta(hours=h) for h in (60, 3)]
    _arun(_seed([{
        "id": PM_MARKET_ID, "source": "polymarket", "external_id": PM_EVENT_ID,
        "name": "Will the synthetic thing happen?", "mutually_exclusive": True,
        "group_id": f"polymarket:{PM_EVENT_ID}", "metadata": {"polymarket_event_id": PM_EVENT_ID},
        "outcomes": [
            {"id": PM_YES_ID, "external_id": f"{PM_CONDITION}_yes", "name": "Yes", "p": 0.30,
             "captures": [(ts, 0.30) for ts in captured]},
            {"id": PM_NO_ID, "external_id": f"{PM_CONDITION}_no", "name": "No", "p": 0.70,
             "captures": [(ts, 0.70) for ts in captured]},
        ],
    }]))


def _polymarket_venue(venue: Venue, *, yes_first: bool = True):
    names, tokens = ["Yes", "No"], [PM_YES_TOKEN, PM_NO_TOKEN]
    if not yes_first:                       # the venue may list the legs either way round
        names, tokens = names[::-1], tokens[::-1]
    venue.gamma_events[PM_EVENT_ID] = {"id": PM_EVENT_ID, "markets": [
        {"conditionId": "0x" + "cd" * 32, "outcomes": json.dumps(["Yes", "No"]),
         "clobTokenIds": json.dumps(["1111", "2222"])},                 # a SIBLING condition
        {"conditionId": PM_CONDITION, "outcomes": json.dumps(names), "clobTokenIds": json.dumps(tokens)},
    ]}
    t = [_hours_ago(h) for h in (48, 36, 24, 12)]
    venue.clob[(PM_YES_TOKEN, "1m", 60)] = [
        {"t": t[0], "p": 0.25}, {"t": t[1], "p": 0}, {"t": t[2], "p": 0.28},
        {"t": t[3], "p": None}, {"t": None, "p": 0.9}, {"t": t[3] + 60, "p": 1.7},   # malformed ×3
    ]
    venue.clob[(PM_NO_TOKEN, "1m", 60)] = [{"t": t[0], "p": 0.75}, {"t": t[1], "p": 1}, {"t": t[2], "p": 0.72}]
    venue.clob[("1111", "1m", 60)] = [{"t": t[0], "p": 0.99}]          # must never be asked for


@pytest.mark.parametrize("yes_first", [True, False])
def test_C6_polymarket_exact_token_by_name_both_readers_supported_zero_malformed_dropped(venue, broker, yes_first):
    _seed_polymarket()
    _polymarket_venue(venue, yes_first=yes_first)
    _timeline(PM_MARKET_ID)
    broker.run_enqueued()

    contracts = {k: v["contract"] for k, v in _payload(PM_MARKET_ID)["outcomes"].items()}
    assert contracts[str(PM_YES_ID)]["token_id"] == PM_YES_TOKEN
    assert contracts[str(PM_NO_ID)]["token_id"] == PM_NO_TOKEN, "the No row was handed the Yes book (Q489 inversion)"
    assert contracts[str(PM_YES_ID)]["condition_id"] == PM_CONDITION
    asked = {r["token"] for r in venue.provider_requests() if r["venue"] == "polymarket-clob"}
    assert asked == {PM_YES_TOKEN, PM_NO_TOKEN}, "a sibling condition's token was queried"

    t = [_iso(_hours_ago(h)) for h in (48, 36, 24)]
    hist = _history(PM_MARKET_ID)
    yes = dict(_history_points(hist, PM_YES_ID))
    no = dict(_history_points(hist, PM_NO_ID))
    assert (yes[t[0]], yes[t[1]], yes[t[2]]) == (0.25, 0.0, 0.28), "a supported ZERO must survive as 0.0"
    assert (no[t[0]], no[t[1]], no[t[2]]) == (0.75, 1.0, 0.72)
    assert len(yes) == 3 + 2, "three venue points + two captures; the three malformed points are gone"
    tl = _timeline(PM_MARKET_ID)
    assert dict(_timeline_points(tl, "Yes"))[t[1]] == 0.0
    assert dict(_timeline_points(tl, "No"))[t[1]] == 1.0


def test_C7_duplicate_legs_are_neither_fetched_nor_resurrected_from_cache(venue, broker):
    """#6641's shape: a bare rung AND the same condition's `_yes`/`_no` legs."""
    bare_id, yes_id, no_id = 219754001, 219754002, 219754003
    captured = [FROZEN_NOW - timedelta(hours=h) for h in (60, 3)]
    _arun(_seed([{
        "id": 59165400, "source": "polymarket", "external_id": PM_EVENT_ID,
        "name": "Synthetic rung market", "mutually_exclusive": False,
        "metadata": {"polymarket_event_id": PM_EVENT_ID},
        "outcomes": [
            {"id": bare_id, "external_id": PM_CONDITION, "name": "March 31, 2026", "p": 0.30,
             "captures": [(ts, 0.30) for ts in captured]},
            {"id": yes_id, "external_id": f"{PM_CONDITION}_yes", "name": "Yes", "p": 0.30,
             "captures": [(ts, 0.30) for ts in captured]},
            {"id": no_id, "external_id": f"{PM_CONDITION}_no", "name": "No", "p": 0.70,
             "captures": [(ts, 0.70) for ts in captured]},
        ],
    }]))
    _polymarket_venue(venue)
    _timeline(59165400)
    broker.run_enqueued()
    payload = _payload(59165400)
    assert set(payload["outcomes"]) == {str(bare_id)}, "a duplicate leg was fetched"
    assert payload["outcomes"][str(bare_id)]["contract"]["token_id"] == PM_YES_TOKEN

    # Even a cache that DOES hold a leg cannot bring it back.
    leg = dict(payload["outcomes"][str(bare_id)], outcome_id=no_id)
    leg["contract"] = dict(leg["contract"], outcome_external_id=f"{PM_CONDITION}_no")
    payload["outcomes"][str(no_id)] = leg
    _put_payload(payload, 59165400)
    names = {e["name"] for e in _history(59165400)["outcomes"]}
    assert names == {"March 31, 2026"}, names


def test_C8_one_point_stays_one_point_and_an_empty_book_midpoint_is_withheld(venue, broker):
    _seed_specimen()
    venue.kalshi_mode = "custom"
    venue.kalshi_custom = {60: {"markets": [{"market_ticker": TICKER, "candlesticks": [
        _candle(_hours_ago(30), "0.05", "0.07"),                 # ONE supported observation
        _candle(_hours_ago(20), "0.01", "0.99"),                 # the midpoint of a book with nothing in it
        _candle(_hours_ago(15), None, None),                     # no book, no trade: no price at all
    ]}]}}
    cold = _history()
    broker.run_enqueued()
    body = _history()
    gained = sorted(set(_history_points(body)) - set(_history_points(cold)))
    assert gained == [(_iso(_hours_ago(30)), 0.06)], gained
    assert body["venue_history"]["unsupported_points_withheld"] == 1
    assert all(v != 0.5 for _, v in _history_points(body)), "an empty-book 50% reached the chart"
    assert body["total_data_points"] == len(_history_points(body))
    unpriced = _payload()["stats"]["candles_unpriced"]
    assert [u["reason"] for u in unpriced] == ["no_supported_price_in_candle"]


def test_C9_a_finely_captured_market_spends_nothing_and_every_cell_it_served_is_unchanged(venue, broker):
    """The fence: a chart our own polls already draw FINELY asks the venue nothing.

    ⚠️ THIS TEST'S FIXTURE MOVED, AND THE REASON IS THE POINT (#7547 / CERT-3252).
    It used to seed 100 captures NINETY MINUTES apart and call that dense. Dense
    it is — five times the thin gate's threshold — but ninety minutes is sixty
    times the venue's fine interval, so those hundred points cannot carry a
    market that moves by the minute. Counting rows could not tell the two states
    apart, and the fill this test asserts we do not spend is exactly the fill
    such a chart SHOULD spend. That original fixture is not deleted: it is now
    the specimen of `test_C9b`, where it is the positive case.

    What this fence is really about is the cadence our live poll actually writes
    — two minutes — so that is what it seeds now. The claim is unchanged and is
    now true for the right reason: a market we already observe at the venue's own
    resolution never converts a page view into an outbound venue request.
    """
    dense_id, oid = 59165500, 219755001
    captures = [(FROZEN_NOW - timedelta(minutes=2 * i + 17), round(0.40 + 0.001 * (i % 7), 4))
                for i in range(500)]
    _arun(_seed([{"id": dense_id, "source": "kalshi", "external_id": "KXDENSE-26", "name": "Dense market",
                  "outcomes": [{"id": oid, "external_id": "KXDENSE-26-Y", "name": "Yes", "p": 0.40,
                                "captures": captures}]}]))
    cold_t, cold_h = _timeline(dense_id), _history(dense_id)
    assert cold_t["venue_history"]["fill"] == "chart_not_thin" and broker.calls == []
    assert (cold_t["actual_hours"], cold_h["actual_hours"]) == (168, 168)

    # Were a payload to exist anyway, it may only ADD cells — never move one.
    from app.utils.generic_market_history import CACHE_VERSION, SCALE, SCHEMA

    venue_points = [[_iso(_hours_ago(h)), 0.77, 0.76, 0.78, None, "kalshi_candle_60m"] for h in (100, 50, 10)]
    _put_payload({"schema": SCHEMA, "version": CACHE_VERSION, "scale": SCALE, "market_id": dense_id,
                  "market_source": "kalshi", "market_external_id": "KXDENSE-26",
                  "attempted_at": FROZEN_NOW.isoformat(), "built_at": FROZEN_NOW.isoformat(), "status": "ok",
                  "outcomes": {str(oid): {"outcome_id": oid, "points": venue_points, "contract": {
                      "venue": "kalshi", "ticker": "KXDENSE-26-Y", "outcome_external_id": "KXDENSE-26-Y"}}},
                  "stats": {}}, dense_id)
    warm_t, warm_h = _timeline(dense_id), _history(dense_id)
    warm_cells = dict(_timeline_points(warm_t))
    assert all(warm_cells[ts] == v for ts, v in _timeline_points(cold_t)), "a captured cell moved"
    assert set(_history_points(cold_h)) <= set(_history_points(warm_h)), "a captured point was displaced"


def test_C9b_a_dense_but_coarse_chart_asks_for_fine_history_and_serves_what_comes_back(venue, broker):
    """#7547 — the state the density fence cannot see, through both real routes.

    C9's original fixture, unchanged: 100 captures ninety minutes apart. That is
    five times the thin gate's threshold, so `chart_is_thin` is False and the old
    planner answered `chart_not_thin` — which is why widening the fine retrieval
    tier from 24h to 144h changed nothing a reader could see. CERT-3252 measured
    the same shape on production: `/api/futures/40533/history?hours=168` served
    960 points at `state=cold`, `points_served=0`, `fill=chart_not_thin`, on ten
    lines whose median capture gap was 3,607 s.

    The assertion is not that a fill was PLANNED. It is that the minute candles
    the venue answers with reach the served payload — the composition CERT-3252
    found broken, end to end, through the route a reader actually calls.
    """
    coarse_id, oid = 59165501, 219755002
    ticker = "KXCOARSE-26-Y"
    captures = [(FROZEN_NOW - timedelta(minutes=90 * i + 17), round(0.40 + 0.001 * (i % 7), 4))
                for i in range(100)]
    _arun(_seed([{"id": coarse_id, "source": "kalshi", "external_id": "KXCOARSE-26",
                  "name": "Coarsely captured market",
                  "outcomes": [{"id": oid, "external_id": ticker, "name": "Yes", "p": 0.40,
                                "captures": captures}]}]))

    # Minute candles INSIDE the widened fine tier and outside the old 24h one —
    # the six-day band this ship exists to reach. Truncated to the minute, which
    # is the grain the venue's fine tier answers on.
    def _minutes_ago(minutes: float) -> int:
        return int((FROZEN_NOW - timedelta(minutes=minutes)).timestamp()) // 60 * 60

    fine_ts = [_minutes_ago(m) for m in (4000, 4001, 4002)]
    venue.kalshi_mode = "custom"
    venue.kalshi_custom = {1: {"markets": [{"market_ticker": ticker, "candlesticks": [
        _candle(ts, "0.30", "0.32") for ts in fine_ts]}]}}

    cold_t, cold_h = _timeline(coarse_id), _history(coarse_id)
    assert cold_t["venue_history"]["fill"] == "requested", cold_t["venue_history"]
    assert broker.calls, "a coarse chart planned no fill"

    broker.run_enqueued()
    warm_h = _history(coarse_id)
    gained = sorted(set(_history_points(warm_h, oid)) - set(_history_points(cold_h, oid)))
    assert gained == sorted((_iso(ts), 0.31) for ts in fine_ts), gained

    # The venue was asked at the FINE interval, over a window wider than the 24h
    # the tier used to stop at — the retrieval half of this ship, stated on the
    # recorded request rather than inferred from the points that came back.
    fine_calls = [r for r in venue.requests if r["venue"] == "kalshi" and r["period_interval"] == 1]
    assert fine_calls, "the fine tier was never requested"
    assert max(c["end_ts"] - c["start_ts"] for c in fine_calls) > 24 * 3600

    # And the fence still holds for the market next door: captures are never
    # displaced by the venue points that arrive.
    assert set(_history_points(cold_h, oid)) <= set(_history_points(warm_h, oid))


def test_C9d_a_quiet_minute_tier_survives_our_captures_and_a_restatement_does_not(venue, broker):
    """🔴 CERT-3258's finding, replayed through the real routes.

    C9b's candles are three CONSECUTIVE minutes, so the layering could measure
    the venue's grain off its own gaps and get the right answer by luck. This is
    the case where measuring cannot: **Kalshi emits a candle only for a minute
    with something to say**, so a quiet market's 1-minute tier reports 124-minute
    spacing, a measured claim radius comes back capped at the full 30 minutes,
    and our 62-minute captures — the production median, `p25` 60.1 / `p75` 120.2
    over 150 sampled open legs — tile straight over every one of them. Two real
    observations in, zero served, off a bank the reader already paid to build.

    The fetch DECLARED its grain (`period_interval=1`), so the grain is known and
    is not inferred. What this file adds over the unit guards in
    `tests/test_generic_market_history_7351.py` is the seam they cannot reach:
    that the tier label survives the fill, the compaction and the bank, and is
    still on the point when the reader lays the tiers over each other. Bind the
    cap to the declared resolution and forget to carry the label, and every unit
    guard stays green while the reader is served exactly nothing.

    The third candle restates a capture to the second, and must NOT be served:
    "narrower" is the claim, not "switched off".
    """
    quiet_id, oid = 59165502, 219755003
    ticker = "KXQUIET-26-Y"
    # :32 in `FROZEN_NOW`, so the captures land on an exact minute boundary and
    # the restating candle below can be a true zero-second duplicate rather than
    # one that merely rounds to within the claim.
    captures = [
        (FROZEN_NOW - timedelta(minutes=62 * i, seconds=32), round(0.40 + 0.001 * (i % 7), 4))
        for i in range(40)
    ]
    _arun(_seed([{"id": quiet_id, "source": "kalshi", "external_id": "KXQUIET-26",
                  "name": "Quietly traded market",
                  "outcomes": [{"id": oid, "external_id": ticker, "name": "Yes", "p": 0.40,
                                "captures": captures}]}]))

    def _at(capture_index: int, *, plus_minutes: int) -> int:
        stamp = captures[capture_index][0] + timedelta(minutes=plus_minutes)
        return int(stamp.timestamp()) // 60 * 60

    # Two genuine observations 124 minutes apart, each 20 minutes from one of our
    # captures: far inside the measured 30-minute claim, nowhere near restating.
    genuine = [_at(32, plus_minutes=20), _at(30, plus_minutes=20)]
    assert genuine[1] - genuine[0] == 124 * 60
    # And one that IS a restatement — the same instant as a capture.
    restating = _at(20, plus_minutes=0)

    venue.kalshi_mode = "custom"
    venue.kalshi_custom = {1: {"markets": [{"market_ticker": ticker, "candlesticks": [
        _candle(ts, "0.30", "0.32") for ts in sorted(genuine + [restating])]}]}}

    cold_h = _history(quiet_id)
    assert _history(quiet_id) and broker.calls, "a coarse chart planned no fill"

    broker.run_enqueued()
    warm_h = _history(quiet_id)
    gained = sorted(set(_history_points(warm_h, oid)) - set(_history_points(cold_h, oid)))

    assert gained == sorted((_iso(ts), 0.31) for ts in genuine), gained
    assert (_iso(restating), 0.31) not in set(_history_points(warm_h, oid))
    # A capture is never displaced, whatever the grain of what arrives.
    assert set(_history_points(cold_h, oid)) <= set(_history_points(warm_h, oid))


def test_C9c_refused_coarse_reads_cannot_spend_the_thin_reserve_on_one_real_redis(venue, broker):
    """🔴 CERT-3255's finding, replayed on a REAL Redis through the real routes.

    The reserve was two caps over one counter, advanced before the cap was
    consulted, so a coarse read that was REFUSED — no claim kept, no dispatch, no
    venue request — had still spent a unit of the hour finding that out. The
    graded sequence: the coarse share is gone, twenty more coarse readers arrive
    and are turned away, and then an EMPTY chart asks. It was answered
    `hourly_cap` at a counter of 61, having been starved entirely by refusals.

    It takes a shared Redis across requests to see: every counter here is read
    from the same instance the app writes, and the twenty refusals are twenty
    real HTTP reads of the same route a crawler would walk. A per-assertion
    double cannot express the depletion, because the depletion IS the crossing.
    """
    from app.tasks.generic_market_history_fill import COARSE_FILL_CAP
    from app.utils.generic_market_history import budget_key, coarse_budget_key

    hour = FROZEN_NOW.strftime("%Y%m%d%H")
    bkey, ckey = budget_key(hour), coarse_budget_key(hour)

    coarse_id, oid = 59165502, 219755003
    captures = [(FROZEN_NOW - timedelta(minutes=90 * i + 17), round(0.40 + 0.001 * (i % 7), 4))
                for i in range(100)]
    _seed_specimen()
    _arun(_seed([{"id": coarse_id, "source": "kalshi", "external_id": "KXCOARSE2-26",
                  "name": "Coarsely captured market, budget", "outcomes": [
                      {"id": oid, "external_id": "KXCOARSE2-26-Y", "name": "Yes", "p": 0.40,
                       "captures": captures}]}]))

    # The hour as it stands after forty coarse fills really ran: forty against
    # coarseness's share, and the same forty against the hour.
    _redis().set(bkey, COARSE_FILL_CAP)
    _redis().set(ckey, COARSE_FILL_CAP)

    refusals = [_timeline(coarse_id)["venue_history"]["fill"] for _ in range(20)]
    assert refusals == ["coarse_hourly_cap"] * 20, refusals
    assert broker.calls == [], "a refused coarse read dispatched a fill"
    assert int(_redis().get(bkey)) == COARSE_FILL_CAP, (
        "twenty refusals did no work and must have cost the hour nothing"
    )
    assert int(_redis().get(ckey)) == COARSE_FILL_CAP, "the coarse counter drifted"

    # The empty chart this ship's reserve exists for. It was refused here.
    assert _timeline()["venue_history"]["fill"] == "requested"
    assert int(_redis().get(bkey)) == COARSE_FILL_CAP + 1


def test_C10_the_concept_envelope_and_its_cache_are_untouched(venue, broker):
    from app.tasks.futures_chart_series_fill import cache_key as concept_cache_key
    from app.utils.event_concept import apply_venue_history

    _seed_specimen()
    _cold_then_warm(broker)
    assert _redis().get(concept_cache_key(MARKET_ID)) is None, "the generic fill wrote the CONCEPT cache"
    competitors = [{"name": "Yes", "outcome_id": OUTCOME_ID,
                    "history": [{"timestamp": CAPTURE_IN_WEEK[0], "probability": 0.055}]}]
    before = json.dumps(competitors, sort_keys=True)
    with patch("app.utils.event_concept._request_venue_history_fill"):
        assert apply_venue_history(MARKET_ID, competitors) == 0
    assert json.dumps(competitors, sort_keys=True) == before, "the concept reader consumed the generic cache"


# ═══ D — NON-VACUITY ════════════════════════════════════════════════════════


def test_D1_history_alone_changed_price_rank_movement_and_detail_are_byte_equal(venue, broker):
    _seed_specimen()
    cold_detail = _detail()
    cold_t, cold_h, warm_t, warm_h = _cold_then_warm(broker)
    assert warm_t["timeline"] != cold_t["timeline"]
    assert json.dumps(warm_t["outcomes"], sort_keys=True) == json.dumps(cold_t["outcomes"], sort_keys=True)
    assert json.dumps(_detail(), sort_keys=True) == json.dumps(cold_detail, sort_keys=True)
    unchanged = ("market_id", "market_name", "sport_category", "source", "hours", "top", "bucket_seconds")
    assert {k: warm_t[k] for k in unchanged} == {k: cold_t[k] for k in unchanged}
    for key in ("round_boundaries", "leaderboard", "market_name", "hours"):
        assert warm_h[key] == cold_h[key]
    # TestFlight 16's decoder: every key it requires is still there, same type.
    assert isinstance(warm_t["bucket_seconds"], int) and isinstance(warm_t["timeline"], list)
    assert all(set(b) == {"timestamp", "outcomes"} for b in warm_t["timeline"])


def test_D2_the_whole_lifecycle_writes_no_shared_table(venue, broker):
    # 🔴 THE ONE ALLOWED WRITE, AND WHY THE ASSERTION STAYS STRONG (#7736). This
    # test was written when the fill wrote NOTHING to Postgres. #7736 added a
    # single bookkeeping key — `market_metadata->'venue_history_bank'`, at most
    # once per market — because the bank is Redis-only under `allkeys-lru` and an
    # eviction otherwise takes the only evidence the bank ever existed. So the
    # `futures_markets` digest STRIPS exactly that one key and nothing else: every
    # other column of every row, `updated_at` INCLUDED, must still be byte-equal,
    # and the marker is asserted positively below so stripping it cannot hide a
    # fill that silently stopped writing it. `updated_at` is load-bearing here —
    # it is `onupdate=func.now()` and 58 call sites read it as "the market's data
    # changed" (CERT-949), so the write pins it to itself.
    _MARKER = "venue_history_bank"
    tables = ("futures_odds_snapshots", "futures_outcomes", "futures_markets")
    _row_text = {
        "futures_markets": (
            "jsonb_set(to_jsonb(t), '{market_metadata}', "
            f"coalesce(t.market_metadata, '{{}}'::jsonb) - '{_MARKER}')::text"
        ),
    }

    async def _digest():
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(DB_URL)
        out = {}
        async with engine.connect() as conn:
            for table in tables:
                row = _row_text.get(table, "t::text")
                out[table] = tuple((await conn.execute(text(
                    f"SELECT count(*), md5(coalesce(string_agg({row}, '|' ORDER BY t.id), '')) FROM {table} t"
                ))).one())
        await engine.dispose()
        return out

    async def _marker_rows():
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(DB_URL)
        async with engine.connect() as conn:
            # `jsonb_exists(...)`, never the `?` operator: a bare `?` in a
            # `text()` is a paramstyle marker to some drivers (gotcha #45).
            rows = (await conn.execute(text(
                f"SELECT id FROM futures_markets "
                f"WHERE jsonb_exists(market_metadata, '{_MARKER}') ORDER BY id"
            ))).scalars().all()
        await engine.dispose()
        return [int(r) for r in rows]

    _seed_specimen()
    before = _arun(_digest())
    _cold_then_warm(broker)
    venue.kalshi_mode = "http_500"
    FrozenDatetime.current = FROZEN_NOW + timedelta(hours=4)
    _timeline(), broker.run_enqueued(), _history()
    assert _arun(_digest()) == before, "a shared table was written (snapshots / outcomes / markets)"
    assert before["futures_odds_snapshots"][0] == 9
    # Non-vacuity: the stripped key is really there, on the one market that was
    # filled — so the strip above is narrowing a real write, not papering a no-op.
    assert _arun(_marker_rows()) == [MARKET_ID]


def test_D3_reverting_the_reader_integration_makes_the_named_contract_fail_again(venue, broker, monkeypatch):
    """The cache is warm and correct; ONLY the readers' seam is reverted."""
    import app.routes.futures as routes

    _seed_specimen()
    _, _, warm_t, warm_h = _cold_then_warm(broker)
    _assert_named_contract(warm_t, warm_h)                      # green with the seam

    async def _base_reader(market, charted_outcomes, exclusive_field_ids, db=None):
        # `db` mirrors the real signature since #7807 gave the reader its durable
        # second tier. Reverting the seam has to revert BOTH tiers — a stub that
        # took only the first three would raise TypeError, which `pytest.raises
        # (AssertionError)` below would not catch as the contract failing.
        return routes._GenericVenueHistory()                    # what base does: nothing

    monkeypatch.setattr(routes, "_load_generic_venue_history", _base_reader)
    reverted_t, reverted_h = _timeline(), _history()
    with pytest.raises(AssertionError, match="MISSING ELIGIBLE VENUE TIMESTAMPS"):
        _assert_named_contract(reverted_t, reverted_h)
    assert reverted_t["timeline"] == _fx("59165099-timeline.json")["timeline"], "reverted == production today"
