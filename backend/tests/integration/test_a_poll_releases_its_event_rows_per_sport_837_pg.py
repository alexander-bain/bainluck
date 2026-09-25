"""#837: an odds pass holds a live game's row only while it writes that sport.

THE DEFECT, AS PRODUCTION RECORDED IT
-------------------------------------
live/583's after-check (2026-09-25 02:38–03:12Z, release v5026) joined every
`live_blend_refresh ... row locked >500ms, re-queued` line for Padres @ Dodgers
(event 15317977) to the postgres chain behind it. Two holders show up:

* ``discover_events`` on worker-background. Its connection opened at 03:05:00,
  the task was received at 03:05:00.03, and it wrote the game's row
  (``_ingest_event_odds`` stamps ``betting`` on it since #5426). It then held
  that row until 03:06:35, because ``_discover_events`` commits ONCE, after all
  33 sports' Odds API and ESPN calls. The game's stamp re-queued every ~2 s for
  55 s (03:05:40–03:06:35). ``poll_all_odds[ecad4b0e]`` waited 44.7 s behind the
  same transaction on ``odds_snapshots`` rows, which is why that run took 56.4 s.
* ``poll_all_odds`` on worker-realtime. Its 30 s beat runs a ~7–10 s pass that
  also commits once, at the end. Most of the game's per-minute re-queues fall
  inside those passes (``:16–:25`` and ``:46–:55``).

Both have the same shape. A pass writes sport N's rows, then makes sport N+1's
network call (and every call after it) while the transaction is still open.
Each live game's row stays locked for the rest of the pass.

WHAT THIS FILE DRIVES
---------------------
The real ``_poll_all_odds`` and ``_discover_events`` over real Postgres rows.
They run with a fake Odds API that answers the FIRST of our two sports with a
real four-book payload and then parks inside the SECOND sport's ``get_odds``,
the point in the pass where production was making a network call. While the
pass is parked, a second connection tries the stamp's own lock
(``UPDATE events ... WHERE id = <first sport's game>``) under the stamp's
500 ms ``lock_timeout``. The row must be free.

Controls that keep this file from passing on nothing:

* ``test_the_probe_can_see_a_held_row``: the probe reports ``locked`` against a
  row another transaction is actually holding. A probe that always answered
  ``free`` would make every arm below vacuous.
* Each arm asserts the pass really wrote ``betting`` (four books) on the game
  it then probes. With no write there is no lock, and "free" would be true for
  the wrong reason.
* Each arm asserts the pass really parked on our second sport. If the gate is
  never reached, the probe runs after the pass and proves nothing.

Measured on unfixed ``origin/master`` 4d10671174 (PG14 + the one-index shim):
both pass arms read ``locked`` (55P03) with both controls green. With the
per-sport commits they read ``free``. Reverting either commit alone fails only
its own arm.
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #837 per-sport "
        "commit gate (CI job `search-recall` provides one)"
    ),
)

pytestmark = [needs_postgres, pytest.mark.asyncio]

#: The stamp's own bound (PR #8490). A probe that waits longer than production
#: does would call a row "free" that production's stamp gave up on.
STAMP_LOCK_TIMEOUT = "500ms"

#: Ids in a block nothing else uses, so cleanup is exact.
SPORTS = {
    "baseball_mlb": {"sport_id": 993701, "event_id": 993711,
                     "home": "San Diego Padres 837", "away": "Los Angeles Dodgers 837",
                     "team_ids": (993721, 993722)},
    "icehockey_nhl": {"sport_id": 993702, "event_id": 993712,
                      "home": "Boston Bruins 837", "away": "Toronto Maple Leafs 837",
                      "team_ids": (993723, 993724)},
}
EVENT_IDS = [s["event_id"] for s in SPORTS.values()]
TEAM_IDS = [t for s in SPORTS.values() for t in s["team_ids"]]
BOOKS = ("draftkings", "fanduel", "betmgm", "caesars")


def _external_id(event_id: int) -> str:
    return f"odds-837-pg-{event_id}"


@pytest.fixture
async def pg_engine():
    """Real Postgres, real schema, created with ``checkfirst`` and cleaned by id.

    Same discipline as ``test_completed_espn_final_is_not_repoisoned_7147_pg``:
    the CI database is shared across the whole ``search-recall`` job, so drop
    nothing and remove only this file's own rows.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    tables = [
        Base.metadata.tables[name]
        for name in (
            "sports", "teams", "venues", "events", "odds_snapshots",
            "event_provider_anchors", "team_identity_mapping",
        )
    ]
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables, checkfirst=True)
        await _clear(conn)
    yield engine
    async with engine.begin() as conn:
        await _clear(conn)
    await engine.dispose()


async def _clear(conn):
    await conn.execute(
        text("DELETE FROM odds_snapshots WHERE event_id = ANY(:ids)"), {"ids": EVENT_IDS}
    )
    await conn.execute(
        text("DELETE FROM event_provider_anchors WHERE event_id = ANY(:ids)"),
        {"ids": EVENT_IDS},
    )
    await conn.execute(text("DELETE FROM events WHERE id = ANY(:ids)"), {"ids": EVENT_IDS})
    await conn.execute(text("DELETE FROM teams WHERE id = ANY(:ids)"), {"ids": TEAM_IDS})
    await conn.execute(
        text("DELETE FROM sports WHERE id = ANY(:ids)"),
        {"ids": [s["sport_id"] for s in SPORTS.values()]},
    )


async def _seed(conn, anchor):
    """One live game per sport, with its two teams, started 30 minutes ago.

    ``sports`` is reused by key when a sibling step already created it, and
    otherwise inserted at a chosen id (the #7147 gate explains why the serial
    must not fire on the shared CI database).
    """
    for key, spec in SPORTS.items():
        sport_id = (
            await conn.execute(text("SELECT id FROM sports WHERE key = :k"), {"k": key})
        ).scalar_one_or_none()
        if sport_id is None:
            await conn.execute(
                text("INSERT INTO sports (id, key, name, active) VALUES (:i, :k, :k, true)"),
                {"i": spec["sport_id"], "k": key},
            )
            sport_id = spec["sport_id"]
        else:
            await conn.execute(
                text("UPDATE sports SET active = true WHERE id = :i"), {"i": sport_id}
            )
        home_id, away_id = spec["team_ids"]
        for team_id, name in ((home_id, spec["home"]), (away_id, spec["away"])):
            await conn.execute(
                text("INSERT INTO teams (id, sport_id, name) VALUES (:i, :s, :n)"),
                {"i": team_id, "s": sport_id, "n": name},
            )
        await conn.execute(
            text(
                "INSERT INTO events (id, sport_id, external_id, home_team_id, "
                "away_team_id, home_team_name, away_team_name, commence_time, "
                "status) VALUES (:i, :s, :x, :ht, :at, :h, :a, :c, 'live')"
            ),
            {
                "i": spec["event_id"],
                "s": sport_id,
                "x": _external_id(spec["event_id"]),
                "ht": home_id,
                "at": away_id,
                "h": spec["home"],
                "a": spec["away"],
                "c": anchor - timedelta(minutes=30),
            },
        )


def _odds_payload(sport_key, anchor):
    """The Odds API odds response for one sport: one live game, four books.

    Four books agreeing at -150/+130 clear BETTING_BOOK_FLOOR (3) and are no
    split market (#7523), so ``_ingest_event_odds`` really issues the
    ``UPDATE events SET win_probability_sources`` whose row lock is the subject.
    """
    spec = SPORTS[sport_key]
    return [
        {
            "id": _external_id(spec["event_id"]),
            "sport_key": sport_key,
            "commence_time": (anchor - timedelta(minutes=30)).isoformat().replace("+00:00", "Z"),
            "home_team": spec["home"],
            "away_team": spec["away"],
            "bookmakers": [
                {
                    "key": book,
                    "title": book,
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": spec["home"], "price": -150},
                                {"name": spec["away"], "price": 130},
                            ],
                        }
                    ],
                }
                for book in BOOKS
            ],
        }
    ]


class _GatedOddsService:
    """Answers the first of OUR sports and parks inside the second's ``get_odds``.

    Sports this file did not seed (a sibling step's leftovers on the shared CI
    database) are answered empty and never park. The order the pass visits
    sports in is the database's (``GROUP BY`` with no ``ORDER BY``), so the
    double does not assume which of ours comes first. It records which one did.
    """

    def __init__(self, anchor):
        self._anchor = anchor
        self.first = None
        self.parked_on = None
        self.parked = asyncio.Event()
        self.release = asyncio.Event()
        self.last_requests_used = 0
        self.last_requests_remaining = None  # skips record_odds_api_quota → Redis

    async def get_odds(self, sport_key, **kwargs):
        if sport_key not in SPORTS:
            return []
        if self.first is None:
            self.first = sport_key
            return _odds_payload(sport_key, self._anchor)
        self.parked_on = sport_key
        self.parked.set()
        await self.release.wait()
        return []

    async def get_scores(self, sport_key, **kwargs):
        return []

    async def close(self):
        return None


class _NoESPN:
    async def get_scoreboard(self, *args, **kwargs):
        return []

    async def close(self):
        return None


async def _probe(engine, event_id):
    """Try the stamp's lock on one row under the stamp's timeout; never write."""
    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            await conn.execute(text(f"SET LOCAL lock_timeout = '{STAMP_LOCK_TIMEOUT}'"))
            await conn.execute(
                text(
                    "UPDATE events SET win_probability_sources = win_probability_sources "
                    "WHERE id = :i"
                ),
                {"i": event_id},
            )
            return "free"
        except DBAPIError as exc:
            orig = getattr(exc, "orig", None)
            code = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
            if code == "55P03" or "LockNotAvailable" in repr(orig) or "lock timeout" in str(exc):
                return "locked"
            raise
        finally:
            await trans.rollback()


async def _betting(engine, event_id):
    async with engine.connect() as conn:
        return (
            await conn.execute(
                text(
                    "SELECT win_probability_sources->'betting', "
                    "win_probability_sources->>'betting_book_count' "
                    "FROM events WHERE id = :i"
                ),
                {"i": event_id},
            )
        ).one()


def _session_factory(engine):
    from contextlib import asynccontextmanager

    from sqlalchemy.ext.asyncio import async_sessionmaker

    maker = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def _session(**_kwargs):
        async with maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return _session


async def _drive_parked_pass(engine, run_pass):
    """Start the pass, probe while it is parked, then let it finish."""
    anchor = datetime.now(timezone.utc)
    async with engine.begin() as conn:
        await _seed(conn, anchor)
    service = _GatedOddsService(anchor)
    task = asyncio.create_task(run_pass(service))
    try:
        await asyncio.wait_for(service.parked.wait(), timeout=60)
    except asyncio.TimeoutError:
        service.release.set()
        await asyncio.wait_for(task, timeout=60)
        pytest.fail(
            "the pass never reached our second sport's get_odds, so there is no "
            f"'mid-pass' to probe (first={service.first!r}). NOT a pass."
        )
    held = SPORTS[service.first]["event_id"]
    verdict = await _probe(engine, held)
    service.release.set()
    result = await asyncio.wait_for(task, timeout=60)
    return service, held, verdict, result


async def test_the_probe_can_see_a_held_row(pg_engine):
    """Positive control: a row another transaction holds reads ``locked``."""
    anchor = datetime.now(timezone.utc)
    async with pg_engine.begin() as conn:
        await _seed(conn, anchor)
    event_id = SPORTS["baseball_mlb"]["event_id"]
    async with pg_engine.connect() as holder:
        trans = await holder.begin()
        await holder.execute(
            text("UPDATE events SET status = status WHERE id = :i"), {"i": event_id}
        )
        assert await _probe(pg_engine, event_id) == "locked"
        await trans.rollback()
    assert await _probe(pg_engine, event_id) == "free"


async def test_poll_all_odds_releases_a_sport_before_the_next_sports_call(
    pg_engine, monkeypatch
):
    from app.tasks import excitement_index, odds_polling

    async def _zero(*_a, **_k):
        return 0

    async def _no_stale_sweep(_session):
        return {"closed": 0, "suspended": 0}

    def _no_redis():
        raise RuntimeError("no redis in this gate")

    monkeypatch.setattr(odds_polling, "get_task_session", _session_factory(pg_engine))
    monkeypatch.setattr(odds_polling, "check_quota_guard", lambda *a, **k: (True, "ok_test"))
    monkeypatch.setattr(odds_polling, "get_redis_client", _no_redis)
    monkeypatch.setattr(odds_polling, "detect_and_close_stale_events", _no_stale_sweep)
    monkeypatch.setattr(odds_polling, "update_poll_state", lambda *a, **k: None)
    monkeypatch.setattr(excitement_index, "update_live_ei", _zero)

    async def run_pass(service):
        monkeypatch.setattr(odds_polling, "OddsAPIService", lambda: service)
        return await odds_polling._poll_all_odds()

    service, held, verdict, result = await _drive_parked_pass(pg_engine, run_pass)

    assert service.parked_on in SPORTS and service.parked_on != service.first
    betting, count = await _betting(pg_engine, held)
    assert betting is not None and count == "4", (
        f"the pass never wrote betting on event {held} ({betting!r}, {count!r}), "
        "so it never took the row lock this gate is about. A 'free' here would be vacuous."
    )
    assert result["snapshots"] == len(BOOKS), result
    assert verdict == "free", (
        f"event {held}'s row was still locked while the pass waited on "
        f"{service.parked_on}'s Odds API call. The live stamp gives up after "
        f"{STAMP_LOCK_TIMEOUT} and re-queues, so every other sport's network time "
        "becomes this game's price delay (#837)."
    )


async def test_discover_events_releases_a_sport_before_the_next_sports_call(
    pg_engine, monkeypatch
):
    from app.services import espn_api
    from app.tasks import sports

    def _no_redis():
        raise RuntimeError("no redis in this gate")

    monkeypatch.setattr(sports, "get_task_session", _session_factory(pg_engine))
    monkeypatch.setattr(sports, "check_quota_guard", lambda *a, **k: (True, "ok_test"))
    monkeypatch.setattr(sports, "get_redis_client", _no_redis)
    monkeypatch.setattr(espn_api, "ESPNAPIService", _NoESPN)

    async def run_pass(service):
        monkeypatch.setattr(sports, "OddsAPIService", lambda: service)
        return await sports._discover_events()

    service, held, verdict, result = await _drive_parked_pass(pg_engine, run_pass)

    assert service.parked_on in SPORTS and service.parked_on != service.first
    betting, count = await _betting(pg_engine, held)
    assert betting is not None and count == "4", (
        f"discovery never wrote betting on event {held} ({betting!r}, {count!r}), "
        "so it never took the row lock this gate is about. A 'free' here would be vacuous."
    )
    assert result["snapshots"] == len(BOOKS), result
    assert verdict == "free", (
        f"event {held}'s row was still locked while discovery waited on "
        f"{service.parked_on}'s Odds API call. Production measured this exact "
        "hold at 55 s on Padres @ Dodgers (#837)."
    )
