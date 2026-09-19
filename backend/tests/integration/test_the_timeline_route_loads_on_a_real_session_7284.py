"""#7284 — the chart route answers on a REAL session, and it answers the board.

PILLAR: TRUTH. SHIP: the phone timeline and the detail page agree, without the
chart endpoint crashing on a sports market.

═══ WHY THIS FILE EXISTS AND WHY IT IS NOT A MOCK ═══════════════════════════

#7284 pointed `/api/futures/{id}/probability-timeline` at the detail route's
formatter so the participant table could stop re-deriving the board. live/429's
review found that the timeline did not match the detail route's EAGER LOADS:
`_format_market_detail` dereferences `market.sport.key`, `FuturesMarket.sport`
is a plain lazy `relationship()` (models.py:866), and on an async session an
un-eager-loaded read raises `MissingGreenlet` — a 500, not a fallback.

Every gate the change passed was green against the one input shape that
structurally cannot show it. Discover's companion guard
`tests/test_the_chart_table_reads_the_board_7284.py` builds its markets as
`SimpleNamespace(sport=None, ...)`, and a NULL FK short-circuits on
`if market.sport` with no IO at all. A mock session never lazy-loads, so the
fixture behaves identically with and without the option. That file's answer is
an AST guard on the query, which is the right shape for a mock harness; this
file is the behavioural half it cannot have, and neither replaces the other.

So: a PERSISTED market, a REAL non-null `Sport` FK, the real routes over a real
PostgreSQL through the real FastAPI dependencies. Nothing here calls a provider
or production.

    THE MUTANT THIS FILE EXISTS TO KILL — delete `selectinload(FuturesMarket.sport)`
    from the timeline route's query (`futures.py`, inside `get_probability_timeline`;
    mutate BY LINE — the identical loader string also appears in an unrelated
    route further up the file, so a first-occurrence replace hits the wrong one)
    and `test_1_the_chart_route_answers_on_a_market_that_has_a_sport` raises
    `MissingGreenlet` / serves a 500.

MUTATION RUN, composed candidate + current master, real Postgres (latency,
2026-09-19). Baseline 9 passed. Every mutant is a one-line edit to
`app/routes/futures.py` inside `get_probability_timeline`:

  A  delete `selectinload(FuturesMarket.sport)`     → 9 failed (MissingGreenlet)
  B  delete `selectinload(FuturesMarket.outcomes)
       .selectinload(FuturesOutcome.team)`          → 9 failed (live/431's arm)
  C  serve `o.probability_change_24h` (the stored
       per-write column) instead of the board's     → test_4, test_6 failed
  D  divide the plotted point by today's field sum  → test_8 failed, ONLY
  E  serve `o.current_probability` (the raw price)
       instead of the board's                       → test_7 failed, ONLY

C, D and E each fail exactly the arm that names them and nothing else, which is
what says the agreement tests are not all restating the crash test. No mutant
survived.

The widening live/431 measured is carried here rather than in discover's file:
the collector on the mock side counts two-step `market.X.Y` walks, but a
ONE-step lazy read raises the same `MissingGreenlet` and the formatter already
has one (`market.outcomes`). This guard is on the ROUTE'S OUTPUT, so it does not
have to enumerate relationships at all — dropping EITHER load fails it.

═══ SESSION ORDER IS PART OF THE GUARD ══════════════════════════════════════

Every test calls the TIMELINE FIRST, in its own fresh async session, and the
detail route SECOND, in a separate fresh session. `_timeline_then_detail` is
the only way this file reaches the two routes, and it builds a new engine,
sessionmaker, client and session per call.

The hazard the order defends against is real but belongs to a SHARED session:
reach the detail route first on the same session and `Sport` is already
persistent in its identity map, the lazy load issues no IO, and the defect
disappears. MEASURED HERE, so the comment does not overstate what this harness
proves: with the eager load deleted, calling detail first still leaves the
timeline raising `MissingGreenlet` (detail 200 / timeline MissingGreenlet),
because a per-call session cannot carry an identity map across. The order is
kept anyway — it is the order the defect was found in, and it is the one that
still bites if a later edit makes these two calls share a session.

═══ WHAT IS PINNED BESIDES "IT DOES NOT CRASH" ══════════════════════════════

The ship is that the two surfaces AGREE, so the crash test alone is not the
guard. Compared BY OUTCOME ID, never by position or label:

  * `timeline.outcomes[].current_probability` == `detail.outcomes[].probability`
  * `timeline.outcomes[].probability_change_24h`
        == `detail.outcomes[].probability_change_24h`, nulls included

and the two conditions that make that comparison worth making:

  * A SUPPORTED DATED CLAIM (#4079). One outcome carries a bank basis the REAL
    `update_max_movement` sweep wrote from real snapshot rows, aged inside
    `DATED_BASIS_MIN_AGE_HOURS..DATED_BASIS_WINDOW_HOURS`, so the served number
    is a real dated subtraction. A guard where every value is null passes
    trivially and proves nothing.
  * THE REFUSAL / NORMALIZATION CONDITION (#4079's scale ruling, codex
    2026-09-19). On a board whose raw prices sum past the #23 threshold the
    detail serializer squeezes every printed probability and then withholds
    every `probability_change_24h`, because the dated move is raw−raw and the
    printed number is not. The chart table must arrive at the same refusal —
    and, crucially, must NOT re-derive a movement off the stored column.

  * THE HISTORICAL CONTROL. The PLOTTED series is deliberately NOT rescaled by
    that squeeze (codex's ruling: the points are real observations at real
    instants, and dividing them by today's field sum would assert a historic
    displayed percent nobody observed). So on the squeezed board the line stays
    RAW while the table is squeezed, and the bucket keeps the instant it was
    observed at. This is the control that fails a well-meant "just normalize the
    chart too" patch.

═══ EVERY ROW IS A LOCAL FIXTURE ════════════════════════════════════════════

Two synthetic boards, invented here, seeded here. The team names are real teams
because the display pipeline drops placeholder-shaped names; no claim is made
that these markets, ids or prices exist in production.

═══ SAFETY ══════════════════════════════════════════════════════════════════

This module DROPS AND RECREATES THE WHOLE SCHEMA, so it refuses to touch a
database unless all of the following hold, and it never infers safety from a
database's name:

  * `TIMELINE_ROUTE_DATABASE_URL` is set — it deliberately does NOT fall back to
    `DATABASE_URL` or `SEARCH_TEST_DATABASE_URL` — and `$DATABASE_URL`, if set,
    is on that same cluster;
  * the server is reached over a unix socket or loopback;
  * the database holds the sentinel table `timeline_route_disposable` whose
    single row equals `TIMELINE_ROUTE_NONCE`, minted in the same run by whoever
    created the scratch database.

Without the URL the module SKIPS, loudly. The CI step that owns this file
refuses a skip, a zero-collection and a short count: a skipped acceptance reads
exactly like a passing one.

The guard, schema and sweep harness are the ones latency already runs in
`test_numeric_movement_fields_4079_amended_real_postgres.py` (same lane, same
CI job); they are duplicated rather than imported because a test module that
imports another test module breaks on collection order.
"""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

import pytest

DB_URL = os.environ.get("TIMELINE_ROUTE_DATABASE_URL")
NONCE = os.environ.get("TIMELINE_ROUTE_NONCE")
SENTINEL_TABLE = "timeline_route_disposable"

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "NOT RUN — set TIMELINE_ROUTE_DATABASE_URL + TIMELINE_ROUTE_NONCE to run "
        "the #7284 real-session route guard on a disposable Postgres. A skip here "
        "is NOT a pass."
    ),
)

TOL = 1e-9

#: The seeded basis observation's age. Inside `DATED_BASIS_MIN_AGE_HOURS` (12)
#: .. `DATED_BASIS_WINDOW_HOURS` (24), so the bank the real sweep writes from it
#: is a usable dated basis rather than one that has aged out.
BASIS_AGE_HOURS = 22.0


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
        _refuse("TIMELINE_ROUTE_NONCE is unset or short; only the provisioning step mints it")
    app_url = os.environ.get("DATABASE_URL")
    if app_url and _host_of(app_url) != _host_of(DB_URL):
        _refuse("$DATABASE_URL is set and is not this scratch cluster")
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
                _refuse("sentinel nonce does not match TIMELINE_ROUTE_NONCE")
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
# The fixtures — two synthetic boards, both carrying a REAL Sport FK
# ---------------------------------------------------------------------------


class Board:
    """What a seeded board hands the tests: ids, and the instants it was seeded at."""

    def __init__(self):
        self.market_id: int = 0
        self.outcome: dict[str, int] = {}
        self.seeded_probability: dict[str, float] = {}
        self.basis_observed_at: datetime | None = None


async def _seed_board(
    *,
    sport_key: str,
    sport_name: str,
    market_name: str,
    outcomes: list[tuple[str, float, float | None, float]],
    source: str = "polymarket",
) -> Board:
    """Persist one market with a NON-NULL `sport_id` and its outcomes.

    `outcomes` is `(name, current_probability, stored_change_24h, basis_price)`.
    Each outcome gets TWO snapshot rows — one at `BASIS_AGE_HOURS` ago carrying
    `basis_price` (what the real sweep banks) and one a few minutes ago carrying
    the current price — so the bank is written from real observation rows rather
    than by hand.

    `sport_id` is the whole point of the file: a NULL FK short-circuits
    `if market.sport` with no IO and is immune to the defect.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models as m

    engine = create_async_engine(DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    basis_at = now - timedelta(hours=BASIS_AGE_HOURS)
    board = Board()
    board.basis_observed_at = basis_at

    async with maker() as s:
        sport = m.Sport(key=sport_key, name=sport_name, group="Sports", active=True)
        s.add(sport)
        await s.flush()

        market = m.FuturesMarket(
            sport_id=sport.id,  # ← REAL, NON-NULL. The defect needs it.
            source=source,
            external_id=f"tl7284-{sport_key}",
            name=market_name,
            category="futures",
            llm_sport_category=sport_key.split("_")[-1],
            market_tier=2,
            mutually_exclusive=True,
            status="open",
            resolution_date=now + timedelta(days=60),
            volume_24h=25000.0,
            market_metadata={},
            created_at=now - timedelta(days=30),
        )
        s.add(market)
        await s.flush()
        board.market_id = market.id

        for position, (name, prob, stored_change, basis_price) in enumerate(
            sorted(outcomes, key=lambda o: -o[1]), start=1
        ):
            row = m.FuturesOutcome(
                market_id=market.id,
                external_id=f"tl7284-{sport_key}-{position}",
                name=name,
                current_probability=prob,
                opening_probability=basis_price,
                opening_captured_at=now - timedelta(days=20),
                probability_change_24h=stored_change,
                rank=position,
                rank_change_24h=0,
                is_winner=False,
                last_updated=now,
            )
            s.add(row)
            await s.flush()
            board.outcome[name] = row.id
            board.seeded_probability[name] = basis_price
            for captured_at, price in (
                (basis_at, basis_price),
                (now - timedelta(minutes=5), prob),
            ):
                s.add(
                    m.FuturesOddsSnapshot(
                        outcome_id=row.id,
                        bookmaker=source,
                        probability=price,
                        captured_at=captured_at,
                    )
                )
        await s.commit()
    await engine.dispose()
    return board


#: A COHERENT sports board: the raw prices sum to 1.00, so the #23 squeeze does
#: not fire and the dated movement column survives to be compared.
def _seed_coherent_sports_board() -> Board:
    return _arun(
        _seed_board(
            sport_key="americanfootball_nfl",
            sport_name="NFL",
            market_name="Super Bowl LXI Winner (local fixture)",
            outcomes=[
                # name,                  current, stored change, basis price
                ("Kansas City Chiefs", 0.42, 0.03, 0.36),
                ("Buffalo Bills", 0.31, -0.02, 0.33),
                # A NULL stored change is the #4079 refusal that is NOT the
                # squeeze: the writers never claimed a move, so the board stays
                # silent even though the bank could date one.
                ("Philadelphia Eagles", 0.17, None, 0.17),
                ("Detroit Lions", 0.10, 0.01, 0.09),
            ],
        )
    )


#: A SQUEEZED board: raw prices sum to 1.20, inside the #23 normalization band
#: (> 1.05, <= `_FIELD_SUM_MAX` 1.60), so the serializer rescales every printed
#: probability and then withholds every dated movement.
def _seed_squeezed_sports_board() -> Board:
    return _arun(
        _seed_board(
            sport_key="basketball_nba",
            sport_name="NBA",
            market_name="NBA Championship 2027 (local fixture)",
            outcomes=[
                ("Boston Celtics", 0.50, 0.04, 0.44),
                ("Denver Nuggets", 0.40, 0.02, 0.38),
                ("Milwaukee Bucks", 0.30, -0.01, 0.31),
            ],
        )
    )


# ---------------------------------------------------------------------------
# The real A8 sweep — the bank is written by the producer, not by this file
# ---------------------------------------------------------------------------


def _run_real_sweep():
    """Drive the REAL `update_max_movement` against this database.

    Same harness as `tests/integration/test_movement_window_pg.py::_run_task`
    and latency's #4079 acceptance: the task calls `asyncio.run` itself, so this
    is called from sync test code. Writing the bank with the producer is what
    makes the dated claim below a real one rather than a shape this file
    invented.
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
    async def _go():
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(DB_URL)
        try:
            async with engine.begin() as conn:
                row = (
                    await conn.execute(
                        text(
                            "SELECT market_metadata -> 'dated_movement_basis' "
                            "FROM futures_markets WHERE id = :id"
                        ),
                        {"id": market_id},
                    )
                ).fetchone()
        finally:
            await engine.dispose()
        cell = row[0] if row else None
        return json.loads(cell) if isinstance(cell, str) else (cell or {})

    return _arun(_go())


def _require_banked(board: Board, name: str) -> float:
    """PRECONDITION, not the claim under test: the real sweep banked this row.

    Worded so a failure here cannot be mistaken for the #7284 agreement defect.
    """
    outcome_id = board.outcome[name]
    cell = _bank(board.market_id).get(str(outcome_id))
    assert cell is not None, (
        "PRECONDITION (not the #7284 claim): the real update_max_movement sweep "
        f"did not bank outcome {outcome_id} ({name!r}); "
        f"bank={_bank(board.market_id)!r}"
    )
    return float(cell[0])


# ---------------------------------------------------------------------------
# The app, on the real dependencies, against that database
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _client():
    """One request's worth of app, on a FRESH engine, sessionmaker and session.

    Redis is FAILED on purpose so every response is a cold build off the rows
    this file seeded and no cache can serve one route's answer to the other —
    which would make the two surfaces agree for the wrong reason.
    """
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
    boom = RuntimeError("redis disabled: #7284 real-session route guard")
    try:
        with (
            patch("app.main.init_db", new_callable=AsyncMock),
            patch("app.tasks.redis_state.get_async_redis_client", side_effect=boom),
            patch("app.tasks.redis_state.get_redis_client", side_effect=boom),
            patch("app.utils.request_cache.get_shared_async_redis", side_effect=boom),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
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


class Served:
    """One route's answer, or the exception it died of."""

    def __init__(self, path: str, status: int | None, body, raised: BaseException | None):
        self.path, self.status, self.body, self.raised = path, status, body, raised

    def ok(self) -> dict:
        assert self.raised is None, (
            f"{self.path} RAISED {type(self.raised).__name__}: {self.raised}"
        )
        assert self.status == 200, f"{self.path} -> {self.status}: {str(self.body)[:500]}"
        return self.body


def _serve(path: str, **params) -> Served:
    async def _go():
        _forget_process_caches()
        try:
            async with _client() as ac:
                resp = await ac.get(path, params=params)
        except BaseException as exc:  # noqa: BLE001 — a 500 is the thing under test
            return Served(path, None, None, exc)
        try:
            body = resp.json()
        except Exception:  # noqa: BLE001
            body = resp.text
        return Served(path, resp.status_code, body, None)

    return _arun(_go())


def _timeline_then_detail(market_id: int) -> tuple[Served, Served]:
    """THE ORDER IS THE GUARD. Timeline first, in its own fresh session.

    Detail second, in a separate fresh session. Reversing these hydrates
    `Sport` into the identity map before the formatter walks it, the lazy load
    issues no IO, and the defect this file exists for becomes invisible.
    """
    timeline = _serve(f"/api/futures/{market_id}/probability-timeline")
    detail = _serve(f"/api/futures/{market_id}")
    return timeline, detail


def _by_id(rows, outcome_id: int) -> dict:
    for row in rows or []:
        if row.get("id") == outcome_id:
            return row
    raise AssertionError(f"outcome id {outcome_id} not in {rows!r}")


# ---------------------------------------------------------------------------
# 1 — the crash
# ---------------------------------------------------------------------------


class TestTheChartRouteSurvivesARealSession:
    def test_1_the_chart_route_answers_on_a_market_that_has_a_sport(self):
        """A PERSISTED market with a real non-null `Sport` FK, timeline first.

        This is the whole mutant: `_format_market_detail` walks `market.sport.key`,
        `FuturesMarket.sport` is lazy, and without the eager load the first
        access on this async session raises `MissingGreenlet`. Drop
        `selectinload(FuturesMarket.sport)` from the timeline query and this
        fails; every mock fixture in the companion file passes either way.
        """
        board = _seed_coherent_sports_board()
        timeline, detail = _timeline_then_detail(board.market_id)

        body = timeline.ok()
        assert body["market_id"] == board.market_id
        # The formatter ran to completion: `outcomes` is what it returned.
        assert len(body["outcomes"]) == len(board.outcome), body["outcomes"]
        # And the detail route, which has always carried the load, agrees it is
        # the same market — so a failure above is about the LOAD, not the row.
        assert detail.ok()["id"] == board.market_id

    def test_2_the_sport_relationship_is_what_makes_this_specimen_bite(self):
        """The fixture's own precondition: `sport_id` is really non-null.

        Without this, a later edit that quietly drops the FK turns every test in
        this file back into the blind mock specimen, green and meaningless.
        """
        board = _seed_coherent_sports_board()

        async def _go():
            from sqlalchemy import text
            from sqlalchemy.ext.asyncio import create_async_engine

            engine = create_async_engine(DB_URL)
            try:
                async with engine.begin() as conn:
                    return (
                        await conn.execute(
                            text(
                                "SELECT s.key FROM futures_markets fm "
                                "JOIN sports s ON s.id = fm.sport_id WHERE fm.id = :id"
                            ),
                            {"id": board.market_id},
                        )
                    ).fetchone()
            finally:
                await engine.dispose()

        row = _arun(_go())
        assert row is not None and row[0] == "americanfootball_nfl", (
            "PRECONDITION: the seeded market must carry a real non-null Sport FK; "
            "a NULL one short-circuits `if market.sport` with no IO and cannot "
            "show the defect."
        )
        # And the routes serve it, which is the value the lazy read produces.
        # BOTH answers are unwrapped: an earlier cut took only `[1]`, so the
        # timeline's exception sat unexamined inside its `Served` and this test
        # was the one survivor of its own file's mutation run.
        timeline, detail = _timeline_then_detail(board.market_id)
        timeline.ok()
        assert detail.ok()["sport"] == "americanfootball_nfl"


# ---------------------------------------------------------------------------
# 2 — the agreement, by outcome id
# ---------------------------------------------------------------------------


class TestTheTwoSurfacesAgreeByOutcomeId:
    def test_3_participant_current_probability_equals_the_board(self):
        board = _seed_coherent_sports_board()
        timeline, detail = _timeline_then_detail(board.market_id)
        table, ladder = timeline.ok()["outcomes"], detail.ok()["outcomes"]

        compared = 0
        for name, outcome_id in board.outcome.items():
            served = _by_id(table, outcome_id)
            rung = _by_id(ladder, outcome_id)
            assert served["current_probability"] == rung["probability"], (
                f"{name!r} (id {outcome_id}): the chart's participant table says "
                f"{served['current_probability']!r} and the ladder below it says "
                f"{rung['probability']!r} — one screen, two answers."
            )
            assert served["name"] == rung["name"], (
                f"id {outcome_id}: table label {served['name']!r} vs ladder "
                f"{rung['name']!r}; the series key is the label, so they must match."
            )
            compared += 1
        assert compared == len(board.outcome), "every seeded row must be compared"

    def test_4_a_supported_dated_claim_reaches_both_surfaces_identically(self):
        """The #4079 dated move, banked by the REAL sweep, served by both routes."""
        board = _seed_coherent_sports_board()
        _run_real_sweep()
        basis = _require_banked(board, "Kansas City Chiefs")

        timeline, detail = _timeline_then_detail(board.market_id)
        table, ladder = timeline.ok()["outcomes"], detail.ok()["outcomes"]
        outcome_id = board.outcome["Kansas City Chiefs"]

        served = _by_id(table, outcome_id)["probability_change_24h"]
        rung = _by_id(ladder, outcome_id)["probability_change_24h"]

        assert served is not None, (
            "the chart table withheld a movement the ladder can support: the real "
            f"sweep banked {basis} at ~{BASIS_AGE_HOURS}h and the current price is "
            "0.42. A genuine dated move must survive."
        )
        assert rung is not None, (
            "PRECONDITION (not the #7284 claim): the DETAIL route withheld the "
            f"dated move too, so this arm compares two refusals. bank basis={basis}"
        )
        assert abs(served - rung) < TOL, (
            f"id {outcome_id}: chart table {served!r} vs ladder {rung!r}"
        )
        # And it is the dated subtraction, not the stored per-write delta (0.03).
        assert abs(served - (0.42 - basis)) < 1e-6, (
            f"served {served!r} is neither `current - banked basis` "
            f"({0.42 - basis:+.4f}) nor the ladder's value"
        )

    def test_5_a_row_the_writers_never_claimed_is_silent_on_both(self):
        """`stored_change IS NULL` is the refusal that is not the squeeze."""
        board = _seed_coherent_sports_board()
        _run_real_sweep()
        timeline, detail = _timeline_then_detail(board.market_id)
        outcome_id = board.outcome["Philadelphia Eagles"]

        served = _by_id(timeline.ok()["outcomes"], outcome_id)["probability_change_24h"]
        rung = _by_id(detail.ok()["outcomes"], outcome_id)["probability_change_24h"]
        assert rung is None, (
            "PRECONDITION (not the #7284 claim): the detail route was expected to "
            f"refuse this row (stored change NULL) and served {rung!r}"
        )
        assert served is None, (
            f"id {outcome_id}: the ladder refuses to date this row and the chart "
            f"table served {served!r} — the table re-derived a claim the board withheld."
        )
        # A refusal is null, never 0.0 — 0.0 is reserved for a measured flat day.
        assert served is not False and served != 0


# ---------------------------------------------------------------------------
# 3 — the refusal / normalization condition
# ---------------------------------------------------------------------------


class TestTheSqueezeRefusalReachesTheChartTable:
    def test_6_a_squeezed_board_withholds_movement_on_both_surfaces(self):
        """Raw sum 1.20 → #23 squeeze → every dated move withheld (#4079 ruling).

        The discriminating arm: the stored `probability_change_24h` column is
        non-null on two of these rows and the bank can date both, so a table that
        reads the column — or re-runs the subtraction — serves a number here. The
        board serves null, and the table must too.
        """
        board = _seed_squeezed_sports_board()
        _run_real_sweep()
        _require_banked(board, "Boston Celtics")

        timeline, detail = _timeline_then_detail(board.market_id)
        table, ladder = timeline.ok()["outcomes"], detail.ok()["outcomes"]

        for name, outcome_id in board.outcome.items():
            rung = _by_id(ladder, outcome_id)
            assert rung["probability_change_24h"] is None, (
                "PRECONDITION (not the #7284 claim): the squeeze was expected to "
                f"withhold the dated move on {name!r} and the ladder served "
                f"{rung['probability_change_24h']!r}. Raw sum is 1.20; if the #23 "
                "band moved, this fixture needs re-aiming, not the route."
            )
            served = _by_id(table, outcome_id)["probability_change_24h"]
            assert served is None, (
                f"{name!r} (id {outcome_id}): the ladder withholds the dated move on "
                f"a squeezed board and the chart table served {served!r} — the two "
                "numbers are on two scales and the reader is invited to read one as "
                "the change in the other."
            )

    def test_7_the_squeezed_probability_is_the_one_both_surfaces_print(self):
        board = _seed_squeezed_sports_board()
        timeline, detail = _timeline_then_detail(board.market_id)
        table, ladder = timeline.ok()["outcomes"], detail.ok()["outcomes"]

        celtics = board.outcome["Boston Celtics"]
        printed = _by_id(ladder, celtics)["probability"]
        assert printed is not None and abs(printed - 0.50) > 1e-4, (
            "PRECONDITION (not the #7284 claim): the #23 squeeze did not fire — the "
            f"ladder printed the raw 0.50 as {printed!r}. Re-aim the fixture."
        )
        for name, outcome_id in board.outcome.items():
            assert (
                _by_id(table, outcome_id)["current_probability"]
                == _by_id(ladder, outcome_id)["probability"]
            ), f"{name!r} (id {outcome_id}): table and ladder print different percents"


# ---------------------------------------------------------------------------
# 4 — the historical control
# ---------------------------------------------------------------------------


class TestWhatMustNotMove:
    def test_8_the_plotted_history_keeps_its_raw_value_and_its_instant(self):
        """The series is observations at instants; the squeeze must not touch it.

        Codex's 2026-09-19 ruling, and the control that fails a well-meant "make
        the chart match the table" patch: dividing a historic price by TODAY's
        field sum asserts a displayed percent nobody observed. So on the squeezed
        board the TABLE is squeezed (test_7) and the LINE is raw — here.
        """
        board = _seed_squeezed_sports_board()
        timeline, detail = _timeline_then_detail(board.market_id)
        body = timeline.ok()

        assert body["bucket_seconds"] == 3600, body["bucket_seconds"]
        bucket_at = datetime.fromtimestamp(
            (int(board.basis_observed_at.timestamp()) // 3600) * 3600, tz=timezone.utc
        )
        points = [p for p in body["timeline"] if p["timestamp"] == bucket_at.isoformat()]
        assert len(points) == 1, (
            f"the {BASIS_AGE_HOURS}h observation should sit in exactly one "
            f"{bucket_at.isoformat()} bucket; got {[p['timestamp'] for p in body['timeline']]}"
        )

        # The series is keyed by the BOARD's label, which is what the phone joins on.
        label = _by_id(detail.ok()["outcomes"], board.outcome["Boston Celtics"])["name"]
        plotted = points[0]["outcomes"][label]
        raw = board.seeded_probability["Boston Celtics"]
        assert abs(plotted - raw) < 1e-6, (
            f"the plotted point is {plotted!r}; the observation was {raw!r}. A "
            f"rescaled series would read ~{raw / 1.20:.4f} (today's field sum), "
            "which asserts a historic displayed percent nobody observed."
        )

    def test_9_an_unsqueezed_boards_line_and_table_are_on_the_same_scale(self):
        """The control's control: where nothing is squeezed, nothing diverges.

        Without this, test_8 is satisfied by a route that never rescales anything
        under any condition — true today, and exactly what we want pinned, but
        only meaningful next to a board where the two columns DO agree.
        """
        board = _seed_coherent_sports_board()
        timeline, detail = _timeline_then_detail(board.market_id)
        body = timeline.ok()

        chiefs = board.outcome["Kansas City Chiefs"]
        label = _by_id(detail.ok()["outcomes"], chiefs)["name"]
        bucket_at = datetime.fromtimestamp(
            (int(board.basis_observed_at.timestamp()) // 3600) * 3600, tz=timezone.utc
        )
        point = next(p for p in body["timeline"] if p["timestamp"] == bucket_at.isoformat())
        assert abs(point["outcomes"][label] - 0.36) < 1e-6, point["outcomes"]
        # Raw table, raw line, one scale.
        assert _by_id(body["outcomes"], chiefs)["current_probability"] == 0.42
