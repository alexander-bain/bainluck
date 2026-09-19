"""#4079 — executable acceptance for the ORIGINAL NUMERIC movement claims.

AMENDED COPY — see "AMENDMENTS" below. The delivered artifact is the handoff
package `artifacts/other-model-movement-numeric-acceptance/` (untracked, in the
shared checkout); its test file
`tests/integration/test_numeric_movement_fields_4079_pg.py`, sha256
`ef893b9263c241e0d12c1379f7ec00e6aaa247ecd71ab85ff4391b740c98ace3`, is IMMUTABLE
and is not edited by this lane — that sha is what a reader diffs this file
against to see exactly what changed. This file is latency's executable copy,
wired into CI's real-Postgres job; it is the only copy the CI gate runs, and
Discover does not edit it.

PILLAR: TRUTH. SHIP: the green movement arrow on the Discover card and the
"24h" value on the futures detail page use a real DATED comparison, or show
unavailable — while prices, cards and genuine moves survive.

#7176 (A8/A9) repaired the CAPTION: `top_mover_change` handed to the copy layer
is now `current - banked dated basis`. It did not touch the NUMBERS the phone
draws. On the pinned base `8cb3172e` those are still the per-write delta:

  * `GET /api/feed` -> `items[].data.top_outcomes[].movement`
        native `DiscoverView.swift` `MovementBadge(movement: leader.movement)`,
        web `FuturesCard.tsx` `leader?.movement`
  * `GET /api/feed` -> `items[].data.discover_card.distribution_outcomes[].movement`
        native `DistributionCardView.swift` `outcome.movement` — the arrow beside
        a row on the card that carries the grey "distribution" pill, i.e. the
        "+30.5 next to Grand Theft Auto" in the original phone clause
  * `GET /api/futures/{id}` -> `outcomes[].probability_change_24h`
        native `FuturesDetailView.swift` `outcome.probabilityChange24h`, drawn by
        `DeltaBadge(value: change * 100)` under the "24h" label, for EVERY row

All three are WIRE FRACTIONS that the client multiplies by 100 into points.

This file drives the REAL routes on a REAL PostgreSQL through the real FastAPI
dependencies, and — wherever a bank is involved in a "must be truthful" arm —
the bank is written by the REAL `update_max_movement` sweep (statement A8) from
`futures_odds_snapshots` rows, so the JSONB round trip is the producer's own.
A hand-written bank is used only for the isolated malformed/expired consumer
controls, where the point is a cell the real writer would never produce, and is
labelled SYNTHETIC BANK at each site.

EVERY ROW IN THIS FILE IS A LOCAL FIXTURE. The three original identities
(`58321581` Game Awards GOTY, `61122553`/`229745131` Meta training pause,
`59530987` US bank failure) are seeded from the saved 2026-09-19 12:05Z row
extract with their real ids and values, RE-DATED so the banked basis keeps the
age it had at the extract (22.2 h). They are timestamped evidence replayed
locally — not current production, and no claim is made that these ids appear on
any production page. Everything else is a SYNTHETIC VARIANT and says so.

── THE CONTRACT THESE TESTS HOLD THE OWNER TO ───────────────────────────────

For every numeric movement field named above, the served value is one of:

  (a) `raw current_probability - raw banked basis`, the owner's declared A8
      contract (#4079 comment 2026-09-19 11:12Z: "printed number equals raw
      current_probability − banked basis"), or the same subtraction with BOTH
      operands on the card's display scale (like with like); or
  (b) unavailable (`null`) — never `0`, never the per-write delta.

A dated move under the 2-point card floor may be served as itself or hidden as
`null`; both are truthful and neither is forced. A REAL ZERO must stay
distinguishable on the wire from MISSING evidence.

A mixed-scale subtraction (display-normalized current minus raw basis) is
rejected by name.

── AMENDMENTS (latency, 2026-09-19; nothing else in this file is changed) ───

The artifact left ONE thing open — "which scale does the arrow beside a
display-normalized percent use" — and accepted either answer in `test_7`. Codex
RULED it on 2026-09-19 16:00Z (Discover's 1600Z directive, "SCALE RULING"):

  * raw−raw is retained for the detail route and for feed rows whose VISIBLE
    probability is already on that same raw scale (display scale 1.0);
  * where the serving normalization puts the visible percent on a DIFFERENT
    scale and there is no supported historic display basis, the numeric
    movement is `null` on every affected feed reader — price, card and ranking
    untouched. Dividing a delta (or a historic price) by TODAY's denominator
    does not establish what the displayed probability was then, so neither
    +14.6 nor +7.1 may be published beside a 43%.

So two assertions change, and are the only ones that change:

  A1. `test_7` (renamed `test_7_display_normalized_card_*`) no longer accepts
      "raw or display". It PINS the ruling: on the normalized (÷1.40) fixture
      both feed readers serve `null`, and the raw detail route serves the dated
      `+0.10`. The detail arm is inside the same test on purpose — it is the
      discriminating control that makes a blanket "null everywhere" patch FAIL
      this test on its own, without appeal to any other test.
  A2. `test_7b_*` is NEW and applies the same pin to the adjacent `mode=sports`
      twin serializer on a normalized sports card, which the artifact never
      exercised (its `mode=sports` fixture sums to 1.00, i.e. scale 1.0).

Everything the ruling did not touch keeps the artifact's intent and its wording,
and three of those are what stop a blanket suppression passing:

  * `test_0a` / `test_1` / `test_2_5_6` — UNNORMALIZED dated moves must still be
    SERVED as numbers; `null` there is a failure ("A genuine move must survive").
  * `test_4` — a real zero must stay distinguishable from missing evidence.
  * `test_adjacent_sports_mode_twin_serializer_same_counterexample` — the
    UNNORMALIZED sports twin must still serve `+0.10`.

Count: the artifact's 24 tests become 25 (24 + `test_7b`). No test is deleted
and no assertion is loosened. Nobody may report "the untouched 24 passed".

── SAFETY ───────────────────────────────────────────────────────────────────

This module DROPS AND RECREATES THE WHOLE SCHEMA. It therefore refuses to touch
a database unless ALL of the following hold, and never infers safety from a
database's name:

  * `MOVEMENT_ACCEPTANCE_DATABASE_URL` is set (it deliberately does NOT read
    `DATABASE_URL` or `SEARCH_TEST_DATABASE_URL`), and `$DATABASE_URL`, if set at
    all, is that same scratch cluster;
  * the server is reached over a unix socket or loopback;
  * the database holds the sentinel table `movement_acceptance_disposable`
    whose single row equals `MOVEMENT_ACCEPTANCE_NONCE` — which only
    `APPLY-AND-TEST.sh` writes, into a cluster it `initdb`'d itself.

Without the URL the module SKIPS, loudly; `APPLY-AND-TEST.sh` treats any skip as
a failure. A skip is never green evidence.

If the owner moves the UI onto differently-named wire fields, point the tests at
them with `MOVEMENT_ACCEPTANCE_FEED_FIELD` / `MOVEMENT_ACCEPTANCE_DETAIL_FIELD`
and say so in the hand-back; the defaults are the fields the base clients read.
"""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

import pytest

DB_URL = os.environ.get("MOVEMENT_ACCEPTANCE_DATABASE_URL")
NONCE = os.environ.get("MOVEMENT_ACCEPTANCE_NONCE")
SENTINEL_TABLE = "movement_acceptance_disposable"

#: The wire fields the base clients read. Overridable ONLY so an owner who moves
#: the UI onto a new field can aim the same assertions at it.
FEED_FIELD = os.environ.get("MOVEMENT_ACCEPTANCE_FEED_FIELD", "movement")
DETAIL_FIELD = os.environ.get(
    "MOVEMENT_ACCEPTANCE_DETAIL_FIELD", "probability_change_24h"
)

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "NOT RUN — set MOVEMENT_ACCEPTANCE_DATABASE_URL + MOVEMENT_ACCEPTANCE_NONCE "
        "(APPLY-AND-TEST.sh does) to run the #4079 numeric-movement acceptance on a "
        "disposable Postgres. A skip here is NOT a pass."
    ),
)

TOL = 1e-6


# ---------------------------------------------------------------------------
# Disposable-database guard
# ---------------------------------------------------------------------------


def _refuse(msg: str):
    pytest.fail(f"REFUSING TO TOUCH THIS DATABASE: {msg}", pytrace=False)


def _host_of(url: str) -> str:
    parsed = urlparse(url.replace("postgresql+asyncpg", "postgresql", 1))
    q = parse_qs(parsed.query)
    return (q.get("host") or [parsed.hostname or ""])[0]


async def _assert_disposable():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    if not NONCE or len(NONCE) < 16:
        _refuse("MOVEMENT_ACCEPTANCE_NONCE is unset or short; only APPLY-AND-TEST.sh mints it")
    # The app builds its own engine from $DATABASE_URL at import. Nothing in this
    # file uses it, but it may not point anywhere except this same scratch cluster.
    app_url = os.environ.get("DATABASE_URL")
    if app_url and _host_of(app_url) != _host_of(DB_URL):
        _refuse("$DATABASE_URL is set and is not this scratch cluster; unset it or run APPLY-AND-TEST.sh")
    host = _host_of(DB_URL)
    if not (host.startswith("/") or host in ("localhost", "127.0.0.1", "::1")):
        _refuse(f"host {host!r} is neither a unix socket nor loopback")
    engine = create_async_engine(DB_URL)
    try:
        async with engine.connect() as conn:
            try:
                rows = (
                    await conn.execute(text(f"SELECT nonce FROM {SENTINEL_TABLE}"))
                ).fetchall()
            except Exception as exc:  # noqa: BLE001 — any failure is a refusal
                _refuse(f"sentinel table {SENTINEL_TABLE!r} is absent ({type(exc).__name__})")
            if [r[0] for r in rows] != [NONCE]:
                _refuse("sentinel nonce does not match MOVEMENT_ACCEPTANCE_NONCE")
    finally:
        await engine.dispose()


def _arun(coro):
    return asyncio.run(coro)


@pytest.fixture(scope="module", autouse=True)
def _schema():
    """Guard, then build the whole schema ONCE. Each test truncates its rows."""

    async def _build():
        from sqlalchemy.ext.asyncio import create_async_engine

        import app.models.models  # noqa: F401 — registers every table on Base
        from app.services.database import Base

        await _assert_disposable()
        engine = create_async_engine(DB_URL)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    _arun(_build())
    yield


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")

    async def _truncate():
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(DB_URL)
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "TRUNCATE futures_odds_snapshots, futures_outcomes, "
                    "futures_markets, sports RESTART IDENTITY CASCADE"
                )
            )
        await engine.dispose()

    _arun(_truncate())
    yield


# ---------------------------------------------------------------------------
# Seeding — every row a LOCAL FIXTURE
# ---------------------------------------------------------------------------


def O(name, p, delta=None, *, id=None, opening=None, opening_days=20.0, obs=(), rank=None):
    """One outcome. `obs` = [(hours_ago, probability[, bookmaker])] snapshots."""
    return {
        "name": name, "p": p, "delta": delta, "id": id, "opening": opening,
        "opening_days": opening_days, "obs": list(obs), "rank": rank,
    }


def M(key, name, category, outcomes, *, id=None, source="polymarket",
      exclusive=True, metadata=None, tier=2, volume=5000.0, sport=None):
    return {
        "key": key, "name": name, "category": category, "outcomes": outcomes,
        "id": id, "source": source, "exclusive": exclusive,
        "metadata": dict(metadata or {}), "tier": tier, "volume": volume,
        "sport": sport,
    }


class Seeded:
    def __init__(self):
        self.market: dict[str, int] = {}
        self.outcome: dict[tuple[str, str], int] = {}


async def _seed(markets) -> Seeded:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models as m

    engine = create_async_engine(DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    out = Seeded()
    async with maker() as s:
        sports: dict[str, int] = {}
        for spec in markets:
            if spec["sport"] and spec["sport"][0] not in sports:
                sp = m.Sport(key=spec["sport"][0], name=spec["sport"][1], active=True)
                s.add(sp)
                await s.flush()
                sports[spec["sport"][0]] = sp.id
            mk = m.FuturesMarket(
                sport_id=sports.get(spec["sport"][0]) if spec["sport"] else None,
                source=spec["source"],
                external_id=f"mvacc-{spec['key']}",
                name=spec["name"],
                category="futures",
                llm_sport_category=spec["category"],
                market_tier=spec["tier"],
                mutually_exclusive=spec["exclusive"],
                status="open",
                resolution_date=now + timedelta(days=60),
                volume_24h=spec["volume"],
                market_metadata=spec["metadata"],
                created_at=now - timedelta(days=30),
            )
            if spec["id"] is not None:
                mk.id = spec["id"]
            s.add(mk)
            await s.flush()
            out.market[spec["key"]] = mk.id
            ordered = sorted(spec["outcomes"], key=lambda o: -(o["p"] or 0))
            for position, o in enumerate(ordered, start=1):
                row = m.FuturesOutcome(
                    market_id=mk.id,
                    external_id=f"mvacc-{spec['key']}-{position}",
                    name=o["name"],
                    current_probability=o["p"],
                    opening_probability=o["opening"] if o["opening"] is not None else o["p"],
                    opening_captured_at=now - timedelta(days=o["opening_days"]),
                    probability_change_24h=o["delta"],
                    rank=o["rank"] or position,
                    rank_change_24h=0,
                    is_winner=False,
                    last_updated=now,
                )
                if o["id"] is not None:
                    row.id = o["id"]
                s.add(row)
                await s.flush()
                out.outcome[(spec["key"], o["name"])] = row.id
                for ob in o["obs"]:
                    hours_ago, prob = ob[:2]
                    s.add(
                        m.FuturesOddsSnapshot(
                            outcome_id=row.id,
                            bookmaker=ob[2] if len(ob) > 2 else spec["source"],
                            probability=prob,
                            captured_at=now - timedelta(hours=hours_ago),
                        )
                    )
        await s.commit()
    await engine.dispose()
    return out


async def _sql(stmt: str, params: dict | None = None, *, fetch=True):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(DB_URL)
    try:
        async with engine.begin() as conn:
            res = await conn.execute(text(stmt), params or {})
            return res.fetchall() if fetch and res.returns_rows else None
    finally:
        await engine.dispose()


def _poll_write(outcome_id: int, new_price: float):
    """SYNTHETIC STAND-IN FOR A POLL landing between two sweeps.

    Writes exactly what all four production writers write — `new - previous` at
    write time into `probability_change_24h`, the new price, `last_updated`, and
    one snapshot row — without calling a provider. It does NOT touch the bank:
    that is the point.
    """
    _arun(
        _sql(
            """
            WITH prev AS (
                SELECT id, current_probability AS was FROM futures_outcomes WHERE id = :id
            ), upd AS (
                UPDATE futures_outcomes fo
                SET probability_change_24h = CAST(:p AS numeric) - prev.was,
                    current_probability = CAST(:p AS numeric),
                    last_updated = now()
                FROM prev WHERE fo.id = prev.id
                RETURNING fo.id
            )
            INSERT INTO futures_odds_snapshots
                (outcome_id, bookmaker, probability, captured_at, reading_count)
            SELECT upd.id, 'polymarket', CAST(:p AS numeric), now(), 1 FROM upd
            """,
            {"id": outcome_id, "p": Decimal(str(new_price))},
            fetch=False,
        )
    )


def _run_real_sweep():
    """Drive the REAL `update_max_movement` (A..A9, C) against this database.

    Same harness as `tests/integration/test_movement_window_pg.py::_run_task`:
    the task calls `asyncio.run` itself, so this is called from sync test code.
    """
    import app.tasks.base as base_mod
    import app.tasks.futures_movers_warm as warm_mod
    from app.tasks import update_max_movement

    class _Ctx:
        async def __aenter__(self):
            from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

            self._engine = create_async_engine(DB_URL)
            self._session = async_sessionmaker(self._engine, expire_on_commit=False)()
            return self._session

        async def __aexit__(self, *exc):
            await self._session.close()
            await self._engine.dispose()
            return False

    async def _no_warm(_session):
        return {"terminal": "skipped", "completed": 0}

    real_session, real_warm = base_mod.get_task_session, warm_mod.warm_futures_movers
    base_mod.get_task_session = lambda: _Ctx()
    warm_mod.warm_futures_movers = _no_warm
    try:
        return update_max_movement.run()
    finally:
        base_mod.get_task_session = real_session
        warm_mod.warm_futures_movers = real_warm


def _bank(market_id: int) -> dict:
    rows = _arun(
        _sql(
            "SELECT market_metadata -> 'dated_movement_basis' FROM futures_markets WHERE id = :id",
            {"id": market_id},
        )
    )
    cell = rows[0][0]
    if isinstance(cell, str):
        cell = json.loads(cell)
    return cell or {}


def _require_real_bank(market_id: int, outcome_id: int, price: float) -> tuple[float, str]:
    """PRECONDITION, not the claim under test: the real A8 writer banked this.

    A failure here is a HARNESS/WRITER-COMPATIBILITY failure and is worded so it
    cannot be mistaken for the numeric-field defect.
    """
    cell = _bank(market_id).get(str(outcome_id))
    assert cell is not None, (
        "PRECONDITION (not the #4079 numeric claim): the real update_max_movement "
        f"sweep did not bank outcome {outcome_id}; bank={_bank(market_id)!r}"
    )
    assert abs(float(cell[0]) - price) < TOL, f"PRECONDITION: banked {cell!r}, seeded basis {price}"
    return float(cell[0]), cell[1]


def _stored(outcome_id: int):
    r = _arun(
        _sql(
            "SELECT fo.current_probability, fo.probability_change_24h, fm.max_movement_24h, "
            "fm.market_metadata -> 'dated_movement_basis' "
            "FROM futures_outcomes fo JOIN futures_markets fm ON fm.id = fo.market_id "
            "WHERE fo.id = :id",
            {"id": outcome_id},
        )
    )[0]
    return tuple(None if v is None else (float(v) if isinstance(v, Decimal) else v) for v in r)


# ---------------------------------------------------------------------------
# The app, on the real dependencies, against that database
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _client():
    from httpx import ASGITransport, AsyncClient
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
    # Redis is FAILED on purpose: every response is then a cold build from the
    # rows this file seeded, and no cache can serve one arm's page to another.
    # Neither route under test requires Redis to answer.
    boom = RuntimeError("redis disabled: #4079 numeric acceptance")
    try:
        with (
            patch("app.main.init_db", new_callable=AsyncMock),
            patch("app.tasks.redis_state.get_async_redis_client", side_effect=boom),
            patch("app.tasks.redis_state.get_redis_client", side_effect=boom),
            patch("app.utils.request_cache.get_shared_async_redis", side_effect=boom),
            patch("app.routes.feed._score_golf_tournaments", new=AsyncMock(return_value=[])),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                yield ac
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


def _forget_process_caches():
    from app.routes import events as _ev
    from app.utils import candidate_base as _cb
    from app.utils import request_cache as _rc
    from app.utils.principal_independent_cache import clear_shared_builds

    _rc._reset_last_good_for_tests()
    _rc._reset_inflight_for_tests()
    _cb._reset_l0_for_tests()
    clear_shared_builds()
    _ev._team_cache = {}
    _ev._team_cache_time = 0


def _get(path: str, **params):
    async def _go():
        _forget_process_caches()
        async with _client() as ac:
            resp = await ac.get(path, params=params)
        assert resp.status_code == 200, f"{path} {params} -> {resp.status_code} {resp.text[:400]}"
        return resp.json()

    return _arun(_go())


def _feed_card(market_id: int, **params) -> dict:
    """The served futures item for `market_id` — the CARD must exist.

    `category=` is the /categories/<slug> browse route, the route the owner named
    as the served surface for these markets; `mode=` reaches the other two
    serializers.
    """
    body = _get("/api/feed", limit=200, offset=0, **params)
    for item in body["items"]:
        if item.get("type") == "futures" and (item.get("data") or {}).get("id") == market_id:
            return item["data"]
    served = [(i.get("type"), (i.get("data") or {}).get("id")) for i in body["items"]]
    raise AssertionError(
        f"LOCAL FIXTURE market {market_id} was not served by /api/feed {params}; "
        f"the card must survive. served={served}"
    )


def _detail(market_id: int) -> dict:
    return _get(f"/api/futures/{market_id}")


def _row(rows, *, id=None, name=None):
    for r in rows or []:
        if id is not None and r.get("id") == id:
            return r
        if name is not None and (r.get("name") == name or r.get("label") == name):
            return r
    raise AssertionError(f"row id={id} name={name} not in {rows!r}")


# ---------------------------------------------------------------------------
# The oracle
# ---------------------------------------------------------------------------


def _assert_dated(value, *, current, basis, per_write, where, scale=1.0, floor_may_hide=False):
    """`value` is the dated subtraction (raw-raw, or display-display), never the
    per-write delta, never a mixed-scale number."""
    raw = current - basis
    like_display = raw / scale
    mixed = current / scale - basis
    if value is None:
        if floor_may_hide:
            return "hidden"
        raise AssertionError(
            f"{where}: served null, but a valid dated comparison exists "
            f"({basis} -> {current} = {raw:+.4f}). A genuine move must survive."
        )
    assert isinstance(value, (int, float)) and not isinstance(value, bool), f"{where}: {value!r}"
    if abs(value - raw) < TOL:
        return "raw"
    if scale != 1.0 and abs(value - like_display) < 1e-4:
        return "display"
    if per_write is not None and abs(value - per_write) < TOL:
        raise AssertionError(
            f"{where}: served {value:+.4f} = the PER-WRITE delta (new - previous write). "
            f"The dated comparison is {basis} -> {current} = {raw:+.4f}."
        )
    if scale != 1.0 and abs(value - mixed) < 1e-4:
        raise AssertionError(
            f"{where}: served {value:+.4f} = display-normalized current ({current}/{scale}) "
            f"minus RAW basis ({basis}). Mixed scales; like-with-like is {raw:+.4f} (raw) "
            f"or {like_display:+.4f} (display)."
        )
    raise AssertionError(
        f"{where}: served {value:+.4f}, which is neither the dated move {raw:+.4f} "
        f"nor unavailable (per-write delta was {per_write})."
    )


def _assert_unavailable(value, *, per_write, where):
    """No valid basis => `null`. Not 0, not the per-write delta."""
    if value is None:
        return
    if isinstance(value, (int, float)) and abs(value) < TOL:
        raise AssertionError(f"{where}: served 0 for MISSING evidence; unavailable must be null, not 0")
    raise AssertionError(
        f"{where}: served {value!r} with no valid dated basis "
        f"(per-write delta {per_write}). Must be unavailable (null)."
    )


def _reads(market_id: int, *, category: str, feed_params=None):
    """Every numeric reader of the original journey, for one market.

    Returns `{reader_name: rows}` where rows are the dicts the client decodes:
      feed.top_outcomes            -> `movement`     (keyed by id)
      feed.distribution_outcomes   -> `movement`     (keyed by label)
      detail.outcomes              -> `probability_change_24h` (keyed by id)
    """
    card = _feed_card(market_id, **(feed_params if feed_params is not None else {"category": category}))
    detail = _detail(market_id)
    return {
        "card": card,
        "detail": detail,
        "feed.top_outcomes": card.get("top_outcomes") or [],
        "feed.distribution_outcomes": (card.get("discover_card") or {}).get("distribution_outcomes") or [],
        "detail.outcomes": detail.get("outcomes") or [],
    }


def _field_of(reader: str) -> str:
    return DETAIL_FIELD if reader.startswith("detail") else FEED_FIELD


def _check_each(reads, *, outcome_id, name, check, readers=None, require_row=("feed.top_outcomes", "detail.outcomes")):
    """Run `check(value, row, where)` on every reader that draws this outcome,
    and COLLECT failures so one run names every defective numeric path."""
    failures, seen = [], []
    for reader in readers or ("feed.top_outcomes", "feed.distribution_outcomes", "detail.outcomes"):
        rows = reads[reader]
        try:
            row = _row(rows, id=outcome_id) if reader != "feed.distribution_outcomes" else _row(rows, name=name)
        except AssertionError:
            if reader in require_row:
                failures.append(f"{reader}: row for {name!r} is not served")
            continue
        seen.append(reader)
        field = _field_of(reader)
        if field not in row:
            failures.append(f"{reader}[{name}]: field {field!r} absent from the wire row {sorted(row)}")
            continue
        try:
            check(row[field], row, f"{reader}[{name}].{field}")
        except AssertionError as exc:
            failures.append(str(exc))
    assert not failures, "\n  - " + "\n  - ".join(failures)
    return seen


def _price_is_served(reads, *, outcome_id, name, raw_price):
    """The PRICE survives: every reader still prints this outcome's probability,
    raw or on the card's own display scale — never null because the move is."""
    for reader in ("feed.top_outcomes", "detail.outcomes"):
        row = _row(reads[reader], id=outcome_id)
        assert row.get("probability") is not None, f"{reader}[{name}]: price went null with the movement"
        assert 0 < row["probability"] <= raw_price + 1e-4, (
            f"{reader}[{name}]: price {row['probability']} vs raw {raw_price}"
        )


def _caption(card_or_item) -> str:
    return " | ".join(
        str(card_or_item.get(k) or "") for k in ("headline", "reason", "context", "hook")
    )


def _feed_item(market_id: int, **params) -> dict:
    body = _get("/api/feed", limit=200, offset=0, **params)
    for position, item in enumerate(body["items"]):
        if item.get("type") == "futures" and (item.get("data") or {}).get("id") == market_id:
            return {**item, "_position": position}
    raise AssertionError(f"market {market_id} not served for {params}")


# ---------------------------------------------------------------------------
# 0. THE ORIGINAL IDENTITIES — saved 2026-09-19 12:05Z rows, replayed locally
# ---------------------------------------------------------------------------

#: `inputs/saved-outcomes-1205Z.json`, market 58321581, verbatim:
#: (outcome_id, name, current_probability, probability_change_24h, opening_probability)
GOTY_ID = 58321581
GTA_ID = 216388319
GOTY_ROWS = [
    (216388319, "Grand Theft Auto VI", 0.660, -0.025, 0.645),
    (216388320, "Resident Evil Requiem", 0.110, 0.0, 0.105),
    (216388327, "Phantom Blade Zero", 0.0505, 0.0, 0.063),
    (216388325, "Control Resonant", 0.0305, 0.0, 0.0295),
    (216388333, "Pragmata", 0.0275, 0.0, 0.0225),
    (216388334, "Marvel's Wolverine", 0.020, 0.0, 0.0225),
    (216388318, "007 First Light", 0.020, 0.0, 0.020),
    (216388324, "The Duskbloods", 0.0165, -0.004, 0.0115),
    (216388337, "Slay the Spire 2", 0.015, 0.0, 0.405),
    (216388322, "Onimusha: Way of the Sword", 0.0105, 0.0, 0.0105),
    (216388323, "Saros", 0.0055, 0.0, 0.0055),
    (216388338, "Stranger Than Heaven", 0.005, 0.0, 0.005),
    (216388321, "Half-Life 3", 0.0045, 0.0, 0.0045),
    (216388336, "Crimson Desert", 0.004, 0.0, 0.004),
    (216388335, "Fable", 0.003, 0.0, 0.003),
    (216388328, "Esoteric Ebb", 0.003, 0.0, 0.003),
    (216388339, "Cairn", 0.0025, 0.0, 0.0025),
    (216388330, "Mouse: P.I. For Hire", 0.0025, 0.0, 0.0025),
    (216388326, "Marathon", 0.0015, 0.0, 0.0015),
    (216388329, "Nioh 3", 0.0015, 0.0, 0.0015),
    (216388340, "Forza Horizon 6", 0.0015, 0.0, 0.0015),
    (216388331, "Gears of War: E-Day", 0.0015, 0.0, 0.0015),
    (216388332, "Reanimal", 0.0015, 0.0, 0.0015),
    (216388341, "Exodus", 0.0015, 0.0, 0.0015),
]
#: `inputs/saved-markets-1205Z.json`: `{'216388319': [0.705, '2026-09-18T13:50:38Z']}`
#: — a cell the PRODUCTION A8 writer wrote. 22.24 h old at the 12:05Z extract.
GOTY_SAVED_BASIS = 0.705
GOTY_SAVED_BASIS_AGE_HOURS = 22.24

META_ID, META_YES, META_NO = 61122553, 229745131, 229745132
BANKFAIL_ID, BANKFAIL_YES = 59530987, 221539112


def _redated(age_hours: float) -> str:
    at = datetime.now(timezone.utc) - timedelta(hours=age_hours)
    return at.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_0a_game_awards_gta_arrow_and_24h_value_are_the_dated_move_not_the_per_write_delta():
    """ORIGINAL CLAUSE: "a green up arrow next to Grand Theft Auto that's +30.5 …
    what does that green number mean?" and "in the last 24 hours they've moved …
    an impossible amount".

    SAVED ROWS (12:05Z), real ids, RE-DATED bank cell. Stored per-write −0.025;
    dated 0.705 → 0.660 = −0.045 (the caption already says "down 4.5 points").
    Every numeric reader must agree with the caption's basis or go unavailable.
    """
    seeded = _arun(_seed([
        M("goty", "The Game Awards: Game of the Year", "entertainment",
          [O(n, p, d, id=i, opening=op, opening_days=1.3) for i, n, p, d, op in GOTY_ROWS],
          id=GOTY_ID, volume=1251.0,
          metadata={"neg_risk": True, "polymarket_event_id": "797729",
                    "dated_movement_basis": {str(GTA_ID): [GOTY_SAVED_BASIS, _redated(GOTY_SAVED_BASIS_AGE_HOURS)]}}),
    ]))
    assert seeded.market["goty"] == GOTY_ID
    reads = _reads(GOTY_ID, category="entertainment")

    # The accepted caption survives (#7176) — this is the basis the numbers must share.
    item = _feed_item(GOTY_ID, category="entertainment")
    assert "4.5 points today" in _caption(item), _caption(item)

    _check_each(
        reads, outcome_id=GTA_ID, name="Grand Theft Auto VI",
        check=lambda v, row, where: _assert_dated(
            v, current=0.660, basis=GOTY_SAVED_BASIS, per_write=-0.025, where=where),
    )
    _price_is_served(reads, outcome_id=GTA_ID, name="Grand Theft Auto VI", raw_price=0.660)


def test_0b_game_awards_non_leader_rows_never_serve_a_per_write_delta_as_24h():
    """The detail page draws the 24h badge for EVERY row. `The Duskbloods`
    (216388324) stores a per-write −0.004 and has NO banked basis (the A8 writer
    banks only deltas at or above the card floor) → unavailable, price kept."""
    _arun(_seed([
        M("goty", "The Game Awards: Game of the Year", "entertainment",
          [O(n, p, d, id=i, opening=op, opening_days=1.3) for i, n, p, d, op in GOTY_ROWS],
          id=GOTY_ID, volume=1251.0,
          metadata={"dated_movement_basis": {str(GTA_ID): [GOTY_SAVED_BASIS, _redated(GOTY_SAVED_BASIS_AGE_HOURS)]}}),
    ]))
    detail = _detail(GOTY_ID)
    dusk = _row(detail["outcomes"], id=216388324)
    assert dusk["probability"] is not None
    _assert_unavailable(dusk[DETAIL_FIELD], per_write=-0.004, where="detail.outcomes[The Duskbloods]")
    # Stored 0.000000 rows: no claim either way on the base (falsy → null) and none after.
    rer = _row(detail["outcomes"], id=216388320)
    assert rer[DETAIL_FIELD] is None or abs(rer[DETAIL_FIELD]) < TOL


def test_0c_meta_training_pause_and_us_bank_failure_stay_priced_with_no_daily_number():
    """SAVED ROWS. Both markets store NULL per-write deltas and no bank: there is
    no daily number to show, the price and the card stay, and the accepted
    dated-LIFETIME caption survives (Meta 0.835 → 0.050 "since <date>").

    GREEN on base by design — this is the control that an owner patch must not
    turn into a 0, a blank card, or a missing caption.
    """
    _arun(_seed([
        M("meta", "Meta announces a training pause by October 31?", "tech",
          [O("Yes", 0.050, None, id=META_YES, opening=0.835, opening_days=4.1),
           O("No", 0.950, None, id=META_NO, opening=0.165, opening_days=4.1)],
          id=META_ID, metadata={"polymarket_event_id": "1025713"}),
        M("bank", "US bank failure by December 31, 2026?", "economics",
          [O("Yes", 0.460, None, id=BANKFAIL_YES, opening=0.130, opening_days=25.4)],
          id=BANKFAIL_ID, volume=23.0, exclusive=False, metadata={"polymarket_event_id": "907020"}),
    ]))
    for market_id, category, oid, price in (
        (META_ID, "tech", META_YES, 0.050), (BANKFAIL_ID, "economics", BANKFAIL_YES, 0.460),
    ):
        detail = _detail(market_id)
        row = _row(detail["outcomes"], id=oid)
        assert row["probability"] is not None and abs(row["probability"] - price) < 1e-4
        assert row[DETAIL_FIELD] is None, f"{market_id}: {row[DETAIL_FIELD]!r}"
        card = _feed_card(market_id, category=category)
        for r in card.get("top_outcomes") or []:
            assert r.get(FEED_FIELD) is None, f"{market_id} top_outcomes: {r!r}"
        for r in (card.get("discover_card") or {}).get("distribution_outcomes") or []:
            assert r.get(FEED_FIELD) is None, f"{market_id} distribution: {r!r}"
    meta_item = _feed_item(META_ID, category="tech")
    assert "78.5 points since" in _caption(meta_item), _caption(meta_item)


# ---------------------------------------------------------------------------
# 1 + 2 + 5 + 6. Writer-backed counterexamples (SYNTHETIC VARIANTS)
# ---------------------------------------------------------------------------


def _award_market(key, title, leader_obs, leader_now, leader_delta, runner_obs, runner_now, runner_delta):
    return M(key, title, "entertainment", [
        O("Alpha Story", leader_now, leader_delta, obs=leader_obs),
        O("Beta Story", runner_now, runner_delta, obs=runner_obs),
        O("Gamma Story", 0.12, None),
        O("Delta Story", 0.05, None),
        O("Epsilon Story", 0.03, None),
    ])


def test_1_same_sign_wrong_amount_leader_and_non_leader():
    """SYNTHETIC VARIANT, REAL WRITER. dated 0.40 → 0.50 with the previous write
    at 0.45: per-write +0.05, dated +0.10. Runner-up: dated 0.36 → 0.28 with the
    previous write at 0.30: per-write −0.02, dated −0.08.

    The bank is produced by the real `update_max_movement` from snapshot rows,
    THEN a poll lands (no sweep after it)."""
    s = _arun(_seed([_award_market(
        "c1", "SYNTHETIC — Golden Reel Awards: Best Picture",
        [(20, 0.40), (3, 0.45)], 0.45, 0.05,
        [(20, 0.36), (3, 0.30)], 0.30, -0.06)]))
    mid, a, b = s.market["c1"], s.outcome[("c1", "Alpha Story")], s.outcome[("c1", "Beta Story")]
    _run_real_sweep()
    _require_real_bank(mid, a, 0.40)
    _require_real_bank(mid, b, 0.36)
    _poll_write(a, 0.50)
    _poll_write(b, 0.28)
    assert abs(_stored(a)[1] - 0.05) < TOL and abs(_stored(b)[1] + 0.02) < TOL  # the per-write deltas

    failures = []
    for params in ({"category": "entertainment"}, {}):
        reads = _reads(mid, category="entertainment", feed_params=params)
        for oid, name, current, basis, per_write in (
            (a, "Alpha Story", 0.50, 0.40, 0.05), (b, "Beta Story", 0.28, 0.36, -0.02),
        ):
            try:
                _check_each(reads, outcome_id=oid, name=name, check=lambda v, r, w: _assert_dated(
                    v, current=current, basis=basis, per_write=per_write,
                    where=f"/api/feed{params or '(discover)'} {w}"))
            except AssertionError as exc:
                failures.append(str(exc))
            _price_is_served(reads, outcome_id=oid, name=name, raw_price=current)
    assert not failures, "".join(failures)


def test_2_5_6_genuine_move_survives_then_a_write_between_sweeps_reverses_the_per_write_sign():
    """SYNTHETIC VARIANT, REAL WRITER. Three served states of ONE outcome, one bank:

      state A  0.40 → 0.60, written once      per-write +0.20 == dated +0.20
               → the GENUINE MOVE SURVIVES, on every reader          (control 6)
      state B  poll writes 0.50, no sweep     per-write −0.10,  dated +0.10
               → NO −0.10 daily arrow                                (control 2)
      state C  poll writes 0.53, no sweep     per-write +0.03,  dated +0.13
               → the number MOVES WITH THE WRITE against the same banked price;
                 an old banked/cached delta (+0.20 or +0.10) is not a result
                                                                     (control 5)
    """
    s = _arun(_seed([_award_market(
        "c2", "SYNTHETIC — Silver Lantern Awards: Best Director",
        [(20, 0.40), (3, 0.60)], 0.60, 0.20,
        [], 0.20, None)]))
    mid, a = s.market["c2"], s.outcome[("c2", "Alpha Story")]
    _run_real_sweep()
    _require_real_bank(mid, a, 0.40)

    states = [("A genuine", None, 0.60, 0.20), ("B sign-reversed write", 0.50, 0.50, -0.10),
              ("C second write", 0.53, 0.53, 0.03)]
    failures = []
    for label, write, current, per_write in states:
        if write is not None:
            _poll_write(a, write)
        assert abs(_stored(a)[1] - per_write) < TOL
        assert abs(_bank(mid)[str(a)][0] - 0.40) < TOL, "the bank is a PRICE and did not change"
        reads = _reads(mid, category="entertainment")
        try:
            _check_each(reads, outcome_id=a, name="Alpha Story", check=lambda v, r, w: _assert_dated(
                v, current=current, basis=0.40, per_write=per_write if write is not None else None,
                where=f"state {label}: {w}"))
        except AssertionError as exc:
            failures.append(str(exc))
        if label.startswith("A"):
            item = _feed_item(mid, category="entertainment")
            assert "20 points today" in _caption(item), _caption(item)
    assert not failures, "".join(failures)


# ---------------------------------------------------------------------------
# 3. No valid basis → unavailable, price and card kept
# ---------------------------------------------------------------------------

#: Cases the REAL WRITER refuses to bank. (label, snapshots for the leader)
WRITER_REFUSALS = [
    ("no-observation-at-all", []),
    ("basis-younger-than-12h", [(5, 0.40), (3, 0.45)]),
    ("expired-only-observation-older-than-24h", [(30, 0.40)]),
    ("incompatible-source-sportsbook-scale", [(20, 0.40, "draftkings"), (3, 0.45, "draftkings")]),
    ("two-sources-in-window", [(20, 0.40, "kalshi"), (3, 0.45, "polymarket")]),
]


@pytest.mark.parametrize("label,obs", WRITER_REFUSALS, ids=[c[0] for c in WRITER_REFUSALS])
def test_3a_real_writer_refuses_a_basis_so_the_number_is_unavailable(label, obs):
    """SYNTHETIC VARIANT, REAL WRITER. The stored per-write delta is +0.05 and is
    still stored after the sweep; the writer banks nothing; therefore there is no
    dated comparison and the numeric readers say unavailable — not 0, not +0.05."""
    s = _arun(_seed([_award_market(
        "c3", "SYNTHETIC — Copper Mask Awards: Best Ensemble", obs, 0.45, 0.05, [], 0.20, None)]))
    mid, a = s.market["c3"], s.outcome[("c3", "Alpha Story")]
    _run_real_sweep()
    assert _bank(mid).get(str(a)) is None, f"PRECONDITION: writer banked {label}: {_bank(mid)!r}"
    stored = _stored(a)[1]
    if stored is None:
        pytest.fail(
            f"PRECONDITION ({label}): the sweep retired the per-write delta, so this arm "
            "no longer exercises the serving path. Harness needs a new specimen.", pytrace=False)
    reads = _reads(mid, category="entertainment")
    _check_each(reads, outcome_id=a, name="Alpha Story",
                check=lambda v, r, w: _assert_unavailable(v, per_write=0.05, where=f"{label}: {w}"))
    _price_is_served(reads, outcome_id=a, name="Alpha Story", raw_price=0.45)


def _synthetic_bank_cells():
    ok_at, old_at, young_at = _redated(20), _redated(30), _redated(2)
    return [
        ("cell-too-short", [0.40]),
        ("cell-too-long", [0.40, ok_at, "x"]),
        ("price-not-a-number", ["abc", ok_at]),
        ("price-is-bool", [True, ok_at]),
        ("stamp-unparseable", [0.40, "yesterday"]),
        ("stamp-not-a-string", [0.40, 1758200000]),
        ("cell-is-a-bare-price", 0.40),
        ("cell-is-a-banked-DELTA-object", {"delta": 0.10, "at": ok_at}),
        ("expired-30h", [0.40, old_at]),
        ("younger-than-min-age-2h", [0.40, young_at]),
    ]


@pytest.mark.parametrize("index", range(10), ids=[
    "cell-too-short", "cell-too-long", "price-not-a-number", "price-is-bool", "stamp-unparseable",
    "stamp-not-a-string", "cell-is-a-bare-price", "cell-is-a-banked-DELTA-object", "expired-30h",
    "younger-than-min-age-2h"])
def test_3b_synthetic_bank_malformed_or_out_of_window_is_unavailable(index):
    """ISOLATED CONSUMER CONTROL — SYNTHETIC BANK, hand-written, cells the real
    writer never produces. Uses the EXISTING window (12–24 h, the reader's own
    `DATED_BASIS_*` constants); no new interval policy is asserted."""
    label, cell = _synthetic_bank_cells()[index]
    s = _arun(_seed([_award_market(
        "c3b", "SYNTHETIC — Copper Mask Awards: Best Ensemble", [], 0.45, 0.05, [], 0.20, None)]))
    mid, a = s.market["c3b"], s.outcome[("c3b", "Alpha Story")]
    _arun(_sql(
        "UPDATE futures_markets SET market_metadata = jsonb_build_object("
        "'dated_movement_basis', jsonb_build_object(CAST(:oid AS text), CAST(:cell AS jsonb))) WHERE id = :id",
        {"id": mid, "oid": str(a), "cell": json.dumps(cell)}, fetch=False))
    reads = _reads(mid, category="entertainment")
    _check_each(reads, outcome_id=a, name="Alpha Story",
                check=lambda v, r, w: _assert_unavailable(v, per_write=0.05, where=f"{label}: {w}"))
    _price_is_served(reads, outcome_id=a, name="Alpha Story", raw_price=0.45)


# ---------------------------------------------------------------------------
# 4. A real zero is not missing evidence
# ---------------------------------------------------------------------------

_MOVEMENT_KEY_HINTS = ("movement", "change", "basis", "dated", "delta")
#: `last_updated` contains "dated" and `rank_change_24h` contains "change";
#: neither says anything about a probability move.
_NOT_MOVEMENT_KEYS = ("updated", "rank")


def _movement_view(row: dict) -> dict:
    return {
        k: v for k, v in row.items()
        if any(h in k.lower() for h in _MOVEMENT_KEY_HINTS)
        and not any(x in k.lower() for x in _NOT_MOVEMENT_KEYS)
    }


def test_4_a_real_zero_dated_move_is_distinguishable_from_missing_evidence():
    """SYNTHETIC VARIANT, REAL WRITER. ZERO: 0.50 (20 h ago) → 0.47 → poll writes
    0.50 again: per-write +0.03, dated 0.00 exactly, WITH evidence. MISSING: same
    prices, per-write +0.03, no observation the writer will bank.

    Required: neither reader serves +0.03; and the two wire rows differ in some
    movement-bearing key (`0.0` vs `null` is the simplest; a sibling status key
    is equally acceptable). Whether a client DRAWS a zero is its own threshold
    (native hides < 1 pt) and is not asserted."""
    s = _arun(_seed([
        _award_market("zero", "SYNTHETIC — Amber Quill Awards: Best Screenplay",
                      [(20, 0.50), (3, 0.47)], 0.47, -0.03, [], 0.20, None),
        M("missing", "SYNTHETIC — Will the Halloran bridge reopen before December?", "economics",
          [O("Yes", 0.50, 0.03), O("No", 0.50, -0.03)]),
    ]))
    zmid, z = s.market["zero"], s.outcome[("zero", "Alpha Story")]
    mmid, m_ = s.market["missing"], s.outcome[("missing", "Yes")]
    _run_real_sweep()
    _require_real_bank(zmid, z, 0.50)
    _poll_write(z, 0.50)
    assert abs(_stored(z)[1] - 0.03) < TOL
    assert _bank(mmid).get(str(m_)) is None and abs(_stored(m_)[1] - 0.03) < TOL

    zr = _reads(zmid, category="entertainment")
    mr = _reads(mmid, category="economics")
    failures = []
    for reader in ("feed.top_outcomes", "detail.outcomes"):
        field = _field_of(reader)
        zrow, mrow = _row(zr[reader], id=z), _row(mr[reader], id=m_)
        zv, mv = zrow.get(field), mrow.get(field)
        if zv is not None and abs(zv - 0.03) < TOL:
            failures.append(f"{reader}: ZERO row serves the per-write +0.03; dated move is 0.00")
        elif zv is not None and abs(zv) > TOL:
            failures.append(f"{reader}: ZERO row serves {zv!r}; dated move is 0.00")
        if mv is not None:
            failures.append(f"{reader}: MISSING row serves {mv!r}; must be unavailable")
        if _movement_view(zrow) == _movement_view(mrow):
            failures.append(
                f"{reader}: a real zero and missing evidence are IDENTICAL on the wire "
                f"({_movement_view(zrow)!r}); they must stay distinguishable")
    assert not failures, "\n  - " + "\n  - ".join(failures)


# ---------------------------------------------------------------------------
# 7. Scale: like with like
#
# AMENDED (A1/A2 in the module docstring). The artifact left the scale question
# open and accepted raw OR display on the normalized card. Codex ruled it at
# 2026-09-19 16:00Z; these two tests PIN the ruling and nothing else in the file
# moves.
# ---------------------------------------------------------------------------


#: The scale ruling, in one place so both arms and the failure text agree.
_SCALE_RULING = (
    "SCALE RULING 2026-09-19 16:00Z: where serving normalization puts the visible "
    "percent on a scale the banked basis is NOT on, and no supported historic "
    "display basis exists, the numeric movement is null on every affected feed "
    "reader. raw-raw is retained where the visible probability is already raw "
    "(detail, and feed rows at display scale 1.0). A delta divided by TODAY's "
    "denominator is not the historic displayed change."
)


def test_7_display_normalized_card_serves_no_feed_number_while_raw_detail_serves_the_dated_move():
    """SYNTHETIC VARIANT, REAL WRITER. AMENDED — pins the 16:00Z scale ruling.

    Independent (non-exclusive) legs summing to 1.40, so `_feed_display_scale`
    divides every PRINTED percent on the CARD by 1.40. The detail route does not
    normalize, so its percent is raw.

      operand            scale      value
      current (stored)   RAW        0.60
      basis (banked)     RAW        0.50    ← the A8 writer banks raw snapshot prices
      current (printed)  DISPLAY    0.60/1.40 = 0.4286   (feed card only)
      per-write delta    RAW        +0.05   (previous write 0.55)

    What is pinned:

      feed.top_outcomes[].movement           -> null   (visible percent is 43%,
      feed.distribution_outcomes[].movement  -> null    the basis is on the raw
                                                        scale; unsupported)
      detail.outcomes[].probability_change_24h -> +0.10 (raw - raw; the visible
                                                        percent there IS raw)

    Every other answer is named and refused: the display-display +0.0714 and the
    raw +0.10 on the FEED (an unsupported claim about what was displayed then),
    the mixed-scale -0.0714 sign flip, the per-write +0.05, and a served 0.

    THIS TEST IS ITS OWN DISCRIMINATING CONTROL. The detail arm requires a real
    number in the same run in which the feed arms require null, so "return null
    everywhere" fails here without appeal to any other test; and "keep serving
    raw everywhere" fails on the feed arms. (test_0a/1/2_5_6/4 and the
    unnormalized sports twin are the wider anti-suppression controls.)
    """
    s = _arun(_seed([M(
        "scale", "SYNTHETIC — Which studios announce a release delay by October 31?", "entertainment",
        [O("Studio Aster", 0.55, 0.05, obs=[(20, 0.50), (3, 0.55)]),
         O("Studio Birch", 0.50, None), O("Studio Cedar", 0.30, None)],
        exclusive=False)]))
    mid, a = s.market["scale"], s.outcome[("scale", "Studio Aster")]
    _run_real_sweep()
    _require_real_bank(mid, a, 0.50)
    _poll_write(a, 0.60)
    reads = _reads(mid, category="entertainment")

    # PRECONDITIONS — the fixture must actually be normalized on the card and
    # raw on the detail route, or this test is measuring nothing.
    top = _row(reads["feed.top_outcomes"], id=a)
    assert top["probability"] is not None
    feed_scale = 0.60 / top["probability"]
    assert abs(feed_scale - 1.40) < 1e-3, (
        f"PRECONDITION: fixture expected the card's display scale to be 1.40, got {feed_scale:.4f}")
    det = _row(reads["detail.outcomes"], id=a)
    detail_scale = 0.60 / det["probability"]
    assert abs(detail_scale - 1.0) < 1e-3, (
        f"PRECONDITION: the detail route is expected to print the RAW 0.60, got "
        f"{det['probability']!r} (scale {detail_scale:.4f}). The ruling's raw-raw arm "
        f"only applies where the visible percent is raw.")

    failures = []

    # --- the two NORMALIZED feed readers: no number at all -------------------
    for reader in ("feed.top_outcomes", "feed.distribution_outcomes"):
        row = (_row(reads[reader], id=a) if reader != "feed.distribution_outcomes"
               else _row(reads[reader], name="Studio Aster"))
        where = f"{reader}[Studio Aster].{FEED_FIELD}"
        assert FEED_FIELD in row, f"{where}: field absent from the wire row {sorted(row)}"
        v = row[FEED_FIELD]
        if v is None:
            continue
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            named = {
                0.10: "the RAW dated move, beside a percent printed at 43% — an "
                      "unsupported claim about what was displayed 24h ago",
                0.0714: "display-display, derived by dividing the delta by TODAY's "
                        "denominator — not the historic displayed change",
                -0.0714: "display-normalized current minus RAW basis — a sign flip",
                0.05: "the PER-WRITE delta (new - previous write)",
            }
            hit = next((t for k, t in named.items() if abs(v - k) < 1e-4), None)
            if abs(v) < TOL:
                hit = "0 — unavailable must be null, never 0"
            failures.append(f"{where}: served {v:+.4f} = {hit or 'an unnamed value'}; must be null")
        else:
            failures.append(f"{where}: served {v!r}; must be null")

    # --- the RAW detail reader: the dated move, as a number ------------------
    where = f"detail.outcomes[Studio Aster].{DETAIL_FIELD}"
    assert DETAIL_FIELD in det, f"{where}: field absent from the wire row {sorted(det)}"
    dv = det[DETAIL_FIELD]
    if dv is None:
        failures.append(
            f"{where}: served null. The detail percent is RAW 0.60 and the banked basis "
            f"is RAW 0.50, so the dated +0.1000 is supported and must survive. "
            f"Suppression is only licensed where the scales differ.")
    elif not isinstance(dv, (int, float)) or isinstance(dv, bool):
        failures.append(f"{where}: served {dv!r}")
    elif abs(dv - 0.10) >= TOL:
        why = ("the PER-WRITE delta" if abs(dv - 0.05) < TOL else
               "display-display" if abs(dv - 0.0714) < 1e-4 else
               "0" if abs(dv) < TOL else "an unnamed value")
        failures.append(f"{where}: served {dv:+.4f} = {why}; the dated raw-raw move is +0.1000")

    assert not failures, _SCALE_RULING + "\n  - " + "\n  - ".join(failures)

    # The price and the card survive the suppression — that is the whole point
    # of suppressing the NUMBER rather than dropping the row.
    _price_is_served(reads, outcome_id=a, name="Studio Aster", raw_price=0.60)


def test_7b_display_normalized_sports_twin_serves_no_number():
    """SYNTHETIC VARIANT, REAL WRITER. NEW under the amendment (A2).

    `GET /api/feed?mode=sports` builds `top_outcomes[].movement` in
    `_score_sports_mode_futures`, which computes its own `_feed_display_scale`
    from the same helper. The artifact's `mode=sports` fixture sums to 1.00 —
    scale 1.0 — so it never reached the normalized branch of the twin, and a
    patch that suppressed only on the Discover scorer would pass it.

    Same fixture shape as `test_7` (0.60/0.50/0.30 = 1.40) on a sports market, so
    the card is normalized: the `mode=sports` movement must be null.

    Both of the twin's printed sites are pinned — `top_outcomes` AND the sports
    scorer's own `discover_card.distribution_outcomes`, which is a separate copy
    of the movement expression, not a view of the first.

    Its discriminating control is the artifact's own
    `test_adjacent_sports_mode_twin_serializer_same_counterexample`, which is
    UNCHANGED and requires the same twin to serve +0.10 on an UNNORMALIZED card.
    The pair cannot both pass under a blanket null or a blanket raw.
    """
    s = _arun(_seed([M(
        "wsn", "SYNTHETIC — Which Harbor League clubs sign a marquee free agent?", "basketball",
        [O("Harbor Gulls", 0.55, 0.05, obs=[(20, 0.50), (3, 0.55)]),
         O("Pier Rats", 0.50, None), O("Dock Owls", 0.30, None)],
        source="kalshi", tier=1, exclusive=False, sport=("basketball_nba", "NBA"))]))
    mid, a = s.market["wsn"], s.outcome[("wsn", "Harbor Gulls")]
    _run_real_sweep()
    _require_real_bank(mid, a, 0.50)
    _poll_write(a, 0.60)

    card = _feed_card(mid, mode="sports")
    row = _row(card["top_outcomes"], id=a)
    assert row.get("probability") is not None, "the price must survive the suppression"
    scale = 0.60 / row["probability"]
    assert abs(scale - 1.40) < 1e-3, (
        f"PRECONDITION: the mode=sports card was expected to be normalized by 1.40, "
        f"got {scale:.4f} — this fixture is not exercising the normalized branch")

    failures = []
    v = row.get(FEED_FIELD)
    if v is not None:
        failures.append(
            f"mode=sports feed.top_outcomes[Harbor Gulls].{FEED_FIELD}: served {v!r} beside a "
            f"percent printed at {row['probability']:.4f}; must be null. "
            f"(raw dated +0.1000, display-display +0.0714, mixed -0.0714, per-write +0.05.)")

    # The sports scorer builds its OWN `discover_card.distribution_outcomes`, a
    # fourth printed site with its own copy of the movement expression. A rule
    # wired into three of the four leaves this one shipping the number, so it is
    # pinned here rather than assumed to follow its twin.
    dist = (card.get("discover_card") or {}).get("distribution_outcomes") or []
    drow = next((r for r in dist if (r.get("label") or r.get("name")) == "Harbor Gulls"), None)
    if drow is None:
        # Not a pass by omission: say so, so nobody reads silence as coverage.
        print(
            "NOTE: the mode=sports card served no distribution row for Harbor Gulls "
            f"(archetype served {[r.get('label') or r.get('name') for r in dist]!r}); "
            "the distribution site of the sports scorer was NOT exercised by this run.")
    elif FEED_FIELD not in drow:
        failures.append(
            f"mode=sports feed.distribution_outcomes[Harbor Gulls]: field {FEED_FIELD!r} absent "
            f"from the wire row {sorted(drow)}")
    elif drow[FEED_FIELD] is not None:
        failures.append(
            f"mode=sports feed.distribution_outcomes[Harbor Gulls].{FEED_FIELD}: served "
            f"{drow[FEED_FIELD]!r} beside a percent printed at {drow.get('probability')!r}; "
            f"must be null. Its twin one line up is already silent, so this is the site a "
            f"rule wired into three of the four printed sites leaves behind.")

    assert not failures, _SCALE_RULING + "\n  - " + "\n  - ".join(failures)


# ---------------------------------------------------------------------------
# 8. Serving truth does not rewrite storage or re-rank
# ---------------------------------------------------------------------------


def test_8_serving_is_read_only_and_ranking_inputs_are_untouched():
    """SYNTHETIC VARIANT, REAL WRITER. GREEN on base by design.

      * serving the feed and the detail page leaves `probability_change_24h`,
        `current_probability`, `max_movement_24h` and the bank byte-identical;
      * `max_movement_24h` is still MAX(ABS(per-write delta)) after a sweep;
      * `/api/futures/movers` still ORDERS on the stored per-write delta (its
        printed values are out of this brief's scope and are not asserted);
      * a card's feed score and position do not depend on whether a bank exists
        — the bank decides what may be SAID, never what ranks.
    """
    s = _arun(_seed([
        _award_market("x", "SYNTHETIC — Golden Reel Awards: Best Picture",
                      [(20, 0.40), (3, 0.45)], 0.45, 0.05, [], 0.20, None),
        M("y", "SYNTHETIC — Will the Corvane tunnel open before 2027?", "economics",
          [O("Yes", 0.58, 0.08, obs=[(20, 0.50), (3, 0.58)]), O("No", 0.42, -0.08)]),
    ]))
    xm, xa = s.market["x"], s.outcome[("x", "Alpha Story")]
    ym, ya = s.market["y"], s.outcome[("y", "Yes")]
    _run_real_sweep()
    _require_real_bank(xm, xa, 0.40)
    _poll_write(xa, 0.50)  # per-write +0.05, dated +0.10 — smaller per-write than y's 0.08
    _run_real_sweep()      # recompute max_movement_24h over the post-write deltas

    before = (_stored(xa), _stored(ya))
    assert abs(before[0][2] - 0.05) < TOL, f"max_movement_24h must be MAX|per-write|: {before[0]}"
    assert abs(before[1][2] - 0.08) < TOL, before[1]

    with_bank = _feed_item(xm, category="entertainment")
    _reads(xm, category="entertainment"); _reads(xm, category="entertainment", feed_params={})
    _reads(ym, category="economics")
    movers = _get("/api/futures/movers", hours=24, limit=20)
    assert (_stored(xa), _stored(ya)) == before, "serving rewrote storage"

    rows = movers if isinstance(movers, list) else (movers.get("movers") or movers.get("items") or [])
    order = [r.get("market_id") or (r.get("market") or {}).get("id") for r in rows]
    assert ym in order and xm in order, f"PRECONDITION: movers payload shape changed: {str(movers)[:300]}"
    assert order.index(ym) < order.index(xm), (
        "movers must still ORDER on the stored per-write delta (y 0.08 before x 0.05); "
        f"got {order} — a dated re-rank is a new ranking policy")

    _arun(_sql("UPDATE futures_markets SET market_metadata = market_metadata - 'dated_movement_basis' "
               "WHERE id = :id", {"id": xm}, fetch=False))
    without_bank = _feed_item(xm, category="entertainment")
    assert with_bank["score"] == without_bank["score"], (with_bank["score"], without_bank["score"])
    assert with_bank["_position"] == without_bank["_position"]


# ---------------------------------------------------------------------------
# ADJACENT (same endpoint, twin serializer) — reported separately
# ---------------------------------------------------------------------------


def test_adjacent_sports_mode_twin_serializer_same_counterexample():
    """NOT part of the original phone journey's verdict. `GET /api/feed?mode=sports`
    builds `top_outcomes[].movement` in `_score_sports_mode_futures`, a line-for-
    line twin of the Discover serializer. Included so an owner patch to one twin
    cannot be accepted while the other still ships the per-write number."""
    s = _arun(_seed([M(
        "ws", "SYNTHETIC — Harbor League Championship Winner", "basketball",
        [O("Harbor Gulls", 0.45, 0.05, obs=[(20, 0.40), (3, 0.45)]),
         O("Pier Rats", 0.30, None), O("Dock Owls", 0.15, None), O("Quay Foxes", 0.10, None)],
        source="kalshi", tier=1, sport=("basketball_nba", "NBA"))]))
    mid, a = s.market["ws"], s.outcome[("ws", "Harbor Gulls")]
    _run_real_sweep()
    _require_real_bank(mid, a, 0.40)
    _poll_write(a, 0.50)
    card = _feed_card(mid, mode="sports")
    row = _row(card["top_outcomes"], id=a)
    _assert_dated(row.get(FEED_FIELD), current=0.50, basis=0.40, per_write=0.05,
                  where="mode=sports feed.top_outcomes[Harbor Gulls].movement")
