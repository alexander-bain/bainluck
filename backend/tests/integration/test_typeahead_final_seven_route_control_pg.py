"""THE SEVEN ROWS A READER ACTUALLY SEES, out of the REAL route, against a REAL
PostgreSQL. #4922.

## Why this file exists, in the words of the ships that wanted it

Three consecutive ships have now changed what `/api/events/typeahead` puts in
front of a reader, and not one of them could assert the finished list:

* **#4847** made a nickname resolve to a game at all (`niners` returned no game
  before it).
* **#4986** moved that game above the five markets derived from it. Its own
  guard file says so in as many words: *"nothing here proves the route SETS
  `_names_participant` correctly against a live pool, because that needs a
  populated database. That control is #4922, and this is the second ship on this
  cut to want it."*
* **#4914** dropped a played game's market out of the pool. Its real-Postgres
  oracle asserts the POOL predicate — which ids survive a `SELECT` — and stops
  there.

Every one of those is asserted one layer below the reader: on `rank_key`, on
`Evidence`, on a pool `SELECT`. The thing none of them touches is the
`reserve_headline_slot(_s_rank(...))[:7]` at the end of the route, which is the
only object a person ever sees. A change that leaves every existing guard green
and still ruins the dropdown — a reservation that promotes the wrong row, a
strip that drops a field the client needs, a pool that composes differently once
all four recall arms run against one another — has had no control over it.

## What it asserts, and why each is the ROUTE's job and not the scorer's

    1. the slice is at most seven                 the contract the client renders
    2. a played game's market is not in it        #4914, end to end
    3. the game outranks every prop derived       #4986, through the real pool
       from it                                    rather than through Evidence
    4. the live game's market is still in it      the anti-emptying control: 2
                                                  passes trivially if the route
                                                  returns nothing

## What it deliberately does NOT assert: the team card

`_build_team_lookup` is a PROCESS-GLOBAL cache. A team row seeded here is
invisible to it if any earlier test in the same worker warmed it, and visible if
none did — so an assertion on the team card would pass or fail on test ORDER,
which is worse than no assertion. The team card's position is already pinned by
`test_typeahead_a_nickname_leads_with_the_game_4986.py` against the real scorer.
What that file cannot do is run the pool, and that is all this one adds.

## 🔴 IT NEEDS BOTH SHIPS IN THE TREE, and its first run proved it

This file asserts #4914 and #4986 through one route call, so it is green only on
a tree carrying both. On this branch's first push it ran on a base that predates
the #4986 merge (`ae877d3b`) and reported, correctly:

    ['SF 49ers vs LA Rams: 2nd Quarter Winner',
     'SF 49ers vs LA Rams: 1st Half Total',
     'SF 49ers vs LA Rams: 1st Half Spread',
     'SF 49ers vs LA Rams: Team Total',
     'San Francisco 49ers at Los Angeles Rams']    <- the game, LAST

That is the #4986 screenshot, reproduced from a live pool by a guard whose whole
purpose is to notice it — the four other assertions passed, so the failure was
the specific one it was built to catch. **A red here is not automatically a
tooling problem: read the order it prints before touching the file.**

## Wiring

Opt-in on ``SEARCH_TEST_DATABASE_URL``; CI's ``search-recall`` job provides a
Postgres 15 service. Registered in ``tests/test_pg_gate_seed_completeness.py``'s
``COVERED`` tuple **and** given its own CI step — a file with only one of the two
never runs while the job stays green, which the repo's own
``test_every_real_postgres_gate_is_wired_into_ci`` exists to catch.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the final-seven route control "
            "(CI job `search-recall` provides one)"
        ),
    ),
    pytest.mark.asyncio,
]

#: The specimen, exactly as production named it at 2026-09-10 23:46Z.
_SF = "San Francisco 49ers"
_LAR = "Los Angeles Rams"
_GAME = f"{_SF} at {_LAR}"

#: The five markets that outranked it, verbatim.
_PROPS = (
    "SF 49ers vs LA Rams: 2nd Quarter Winner",
    "SF 49ers vs LA Rams: 1st Half Total",
    "SF 49ers vs LA Rams: 1st Half Spread",
    "SF 49ers vs LA Rams: Team Total",
)

#: The market on a game that has already been played (#4914's cut).
_PLAYED = "SF 49ers vs LA Rams: Final Margin (last week)"


class _FakeRedis:
    """Enough of the client for the trending vote and the response cache.

    The route reaches Redis for three things — the trending zset, the response
    cache and the head-warm marker — and none of them is what this file
    measures. A fake keeps the test about the seven rows; a real client would
    make it about whether CI has Redis.
    """

    def __init__(self):
        self.zsets: dict = {}
        self.kv: dict = {}

    # -- string ops ---------------------------------------------------------
    def get(self, key):
        return self.kv.get(key)

    def set(self, key, value, *a, **k):
        self.kv[key] = value
        return True

    def setex(self, key, seconds, value):
        self.kv[key] = value
        return True

    def delete(self, *keys):
        for k in keys:
            self.kv.pop(k, None)
        return True

    def exists(self, key):
        return 1 if key in self.kv else 0

    def expire(self, key, seconds):
        return True

    def ttl(self, key):
        return 60

    # -- zset ops -----------------------------------------------------------
    def zincrby(self, key, amount, member):
        z = self.zsets.setdefault(key, {})
        z[member] = z.get(member, 0.0) + float(amount)
        return z[member]

    def zrevrange(self, key, start, end, withscores=False):
        z = sorted((self.zsets.get(key) or {}).items(), key=lambda kv: -kv[1])
        rows = z[start : (end + 1 if end >= 0 else None)]
        return rows if withscores else [m for m, _ in rows]

    def pipeline(self, transaction=True):
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, rc):
        self._rc = rc
        self._queued: list = []

    def __getattr__(self, name):
        def _queue(*args, **kwargs):
            self._queued.append((name, args, kwargs))
            return self

        return _queue

    def execute(self):
        out = []
        for name, args, kwargs in self._queued:
            fn = getattr(self._rc, name, None)
            out.append(fn(*args, **kwargs) if fn else None)
        self._queued.clear()
        return out


@pytest.fixture
def _no_redis(monkeypatch):
    """Every Redis door the route knows, pointed at the fake."""
    client = _FakeRedis()
    monkeypatch.setattr(
        "app.tasks.redis_state.get_redis_client", lambda *a, **k: client
    )
    return client


@pytest.fixture
async def pg_session():
    """Real Postgres, real schema — the same contract as this directory's others.

    Function-scoped: ``pytest.ini`` leaves ``asyncio_default_fixture_loop_scope``
    unset, so a module-scoped async fixture would outlive the loop that made its
    engine.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session

    await engine.dispose()


async def _seed(session):
    """One upcoming NFL game, four markets derived from it, and one market on a
    game that finished last week.

    Raw ``text()`` INSERTs, the same way the other bind contracts here write
    theirs: what is being measured is what the route and the server do with
    these rows, not what the ORM does on the way in.
    """
    from sqlalchemy import text

    now = datetime.now(timezone.utc)

    sport_id = (
        await session.execute(
            text(
                """
                INSERT INTO sports (key, name, active)
                VALUES ('americanfootball_nfl', 'NFL', TRUE)
                RETURNING id
                """
            )
        )
    ).scalar()

    async def _event(status, commence, completed_at=None):
        return (
            await session.execute(
                text(
                    """
                    INSERT INTO events
                        (sport_id, home_team_name, away_team_name,
                         commence_time, status, completed_at)
                    VALUES (:sid, :home, :away, :ct, :st, :ca)
                    RETURNING id
                    """
                ),
                {
                    "sid": sport_id,
                    "home": _LAR,
                    "away": _SF,
                    "ct": commence,
                    "st": status,
                    "ca": completed_at,
                },
            )
        ).scalar()

    async def _market(name, event_id, external_id):
        return (
            await session.execute(
                text(
                    """
                    INSERT INTO futures_markets
                        (name, source, category, mutually_exclusive, status,
                         resolution_date, external_id, llm_sport_category,
                         event_id)
                    VALUES (:n, 'polymarket', 'prop', TRUE, 'open', :rd, :xid,
                            'football', :eid)
                    RETURNING id
                    """
                ),
                {
                    "n": name,
                    # FUTURE on every row, including the played game's, so the
                    # `resolution_date` filter that predates #4914 admits all of
                    # them and cannot be what suppresses anything below.
                    "rd": now + timedelta(days=3),
                    "xid": external_id,
                    "eid": event_id,
                },
            )
        ).scalar()

    upcoming = await _event("scheduled", now + timedelta(days=1))
    played = await _event(
        "completed", now - timedelta(days=7), now - timedelta(days=7)
    )

    ids = {"upcoming_event": upcoming, "played_event": played}
    for i, name in enumerate(_PROPS):
        ids[name] = await _market(name, upcoming, f"PGX-4922-P{i}")
    ids[_PLAYED] = await _market(_PLAYED, played, "PGX-4922-DEAD")

    await session.commit()
    return ids


async def _seven(session, q="niners"):
    """The finished list, exactly as the client receives it."""
    from app.routes.events import typeahead_search

    payload = await typeahead_search(
        q=q,
        debug_evidence=False,
        debug_timing=False,
        db=session,
        request=None,
    )
    return payload["suggestions"]


def _texts(rows):
    # Trap 11: the row label is `text`, never `label`/`name`/`title`.
    return [r.get("text") for r in rows]


class TestTheSevenRowsAReaderSees:

    async def test_the_seed_is_not_vacuous(self, pg_session, _no_redis):
        """The nickname arm resolves at all (#4847) and the game is in the list.

        If this fails, every assertion below is about an empty dropdown and none
        of them means anything.
        """
        await _seed(pg_session)
        rows = _texts(await _seven(pg_session))
        assert rows, "`niners` returned nothing — the pool never ran"
        assert any(_GAME in (t or "") for t in rows), (
            f"the game is not in the seven at all; got {rows}"
        )

    async def test_the_slice_is_at_most_seven(self, pg_session, _no_redis):
        """The contract the client renders against. The route's own `[:7]`."""
        await _seed(pg_session)
        rows = await _seven(pg_session)
        assert len(rows) <= 7, f"{len(rows)} rows would overflow the dropdown"

    async def test_a_played_games_market_is_not_in_the_seven(
        self, pg_session, _no_redis
    ):
        """#4914 END TO END. The pool oracle proves the id is not SELECTed; this
        proves nothing downstream puts it back."""
        await _seed(pg_session)
        rows = _texts(await _seven(pg_session))
        assert _PLAYED not in rows, (
            f"a market on a game finished a week ago is being offered: {rows}"
        )

    async def test_a_live_games_market_is_still_offered(
        self, pg_session, _no_redis
    ):
        """🔴 THE ANTI-EMPTYING CONTROL. Without it the assertion above passes on
        a route that returns nothing at all — which is a worse dropdown than the
        bug it was written for."""
        await _seed(pg_session)
        rows = _texts(await _seven(pg_session))
        assert any(p in rows for p in _PROPS), (
            f"no live market survived — the suppression is over-reaching: {rows}"
        )

    async def test_the_game_outranks_every_prop_derived_from_it(
        self, pg_session, _no_redis
    ):
        """#4986 THROUGH THE REAL POOL, which is the control its own guard file
        asked for by number. The scorer-level tests build `Evidence` by hand; the
        defect they cannot see is the route failing to SET `_names_participant`
        on rows a live session actually returned."""
        await _seed(pg_session)
        rows = _texts(await _seven(pg_session))
        game_at = next(
            (i for i, t in enumerate(rows) if _GAME in (t or "")), None
        )
        assert game_at is not None, f"the game is missing from {rows}"
        for prop in _PROPS:
            if prop in rows:
                assert rows.index(prop) > game_at, (
                    f"{prop!r} still outranks the game it is derived from: {rows}"
                )
