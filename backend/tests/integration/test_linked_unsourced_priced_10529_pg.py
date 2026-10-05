"""#10529 — `linked_unsourced` accuses a writer only when it had a price to write.

## What was wrong, measured on production

On 2026-10-05 the matching-drift rail held `linked_unsourced` RED on ONE pair:
CS2 event 15323417 (XI Esport v struggletony, 19:00Z) with ONE open Kalshi market,
`KXCS2GAME-26OCT051500XISTR`. Both of its outcomes were stored with
`current_probability` NULL. The retained raw venue book read both legs active at
0.12/0.80 and 0.08/0.80 with a last trade of 0.00 — spreads the Kalshi
probability policy correctly declines — so there was no price to write and no
curve to draw. The alert was accusing the curve writer of skipping nothing.

## Why this gate is real PostgreSQL and not a session double

The fix is one SQL predicate — an `EXISTS` on a priced outcome inside the WHERE,
before `GROUP BY` and `LIMIT 200`. Every way it can be wrong is invisible to a
double that hands back precomputed rows:

* written as a `JOIN futures_outcomes`, the per-pair market count multiplies by
  the outcome count;
* placed after the `LIMIT` (or in a HAVING over the grouped rows), unpriced
  pairs with more markets still crowd a priced pair out of the 200;
* written as `> 0`, an honestly priced 0% outcome stops counting.

And it must narrow nothing else: a priced market whose identity the writer would
refuse (a non-game ticker, outcome names matching no team) is EXACTLY the failure
the alert exists to catch, so it stays RED here.

The check reads the whole table and compares against `NOW()`, so every row here
is seeded relative to the database clock and every assertion is scoped to this
file's own event ids — `search-recall` shares one database across its gates.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #10529 "
            "linked_unsourced priced-precondition gate (CI job `search-recall` "
            "provides one)"
        ),
    ),
    pytest.mark.asyncio,
]

#: The only sport this file creates, deletes or asserts over.
SPORT_KEY = "esports_cs2_gate_10529"

#: More unpriced pairs than the check's LIMIT, each carrying more markets than
#: the priced pair, so ordering by market count would put every one of them
#: ahead of it if the price test ran after the LIMIT.
CROWD = 201


def _closure(*roots):
    """The tables this query needs, and nothing else (see #5779's gate)."""
    seen: dict = {}
    pending = list(roots)
    while pending:
        table = pending.pop()
        if table.key in seen:
            continue
        seen[table.key] = table
        for fk in table.foreign_keys:
            pending.append(fk.column.table)
    return list(seen.values())


SEQUENCED = (
    "sports", "events", "futures_markets", "futures_outcomes", "win_prob_snapshots",
)


@pytest.fixture
async def pg_session():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.models.models import FuturesOutcome, WinProbSnapshot
    from app.services.database import Base

    tables = _closure(FuturesOutcome.__table__, WinProbSnapshot.__table__)
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync: Base.metadata.create_all(sync, tables=tables, checkfirst=True)
        )
        await _clear(conn)
        # Sibling gates seed explicit ids without advancing sequences; resync so
        # a sequence-assigned id here cannot collide with one of theirs.
        for table in SEQUENCED:
            await conn.execute(
                text(
                    "SELECT setval("
                    "  pg_get_serial_sequence(:t, 'id'),"
                    f"  COALESCE((SELECT MAX(id) FROM {table}), 0) + 1,"
                    "  false)"
                ),
                {"t": table},
            )

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session

    async with engine.begin() as conn:
        await _clear(conn)
    await engine.dispose()


async def _clear(conn):
    from sqlalchemy import text

    mine = "SELECT e.id FROM events e JOIN sports s ON s.id = e.sport_id WHERE s.key = :k"
    await conn.execute(
        text(f"DELETE FROM win_prob_snapshots WHERE event_id IN ({mine})"),
        {"k": SPORT_KEY},
    )
    await conn.execute(
        text(
            "DELETE FROM futures_outcomes WHERE market_id IN "
            f"(SELECT id FROM futures_markets WHERE event_id IN ({mine}))"
        ),
        {"k": SPORT_KEY},
    )
    await conn.execute(
        text(f"DELETE FROM futures_markets WHERE event_id IN ({mine})"),
        {"k": SPORT_KEY},
    )
    await conn.execute(text(f"DELETE FROM events WHERE id IN ({mine})"), {"k": SPORT_KEY})
    await conn.execute(text("DELETE FROM sports WHERE key = :k"), {"k": SPORT_KEY})


class _Seed:
    def __init__(self, session, sport_id: int, now: datetime):
        self.session = session
        self.sport_id = sport_id
        self.now = now
        self.n = 0

    async def event(self, *, offset_h: float = 1.0, status: str = "scheduled") -> int:
        from sqlalchemy import text

        self.n += 1
        return (
            await self.session.execute(
                text(
                    "INSERT INTO events "
                    "(sport_id, home_team_name, away_team_name, commence_time, status) "
                    "VALUES (:sid, :home, :away, :ct, :status) RETURNING id"
                ),
                {
                    "sid": self.sport_id,
                    "home": f"XI Esport {self.n}",
                    "away": f"struggletony {self.n}",
                    "ct": self.now + timedelta(hours=offset_h),
                    "status": status,
                },
            )
        ).scalar()

    async def market(
        self,
        event_id: int,
        *,
        prices,
        source: str = "kalshi",
        ticker: str | None = None,
        status: str = "open",
        age_min: float = 180,
        names=("XI Esport", "struggletony"),
    ) -> int:
        """One market with one outcome per entry in ``prices`` (None = unpriced)."""
        from sqlalchemy import text

        self.n += 1
        ext = ticker or f"KXCS2GAME-26OCT05GATE{self.n}"
        market_id = (
            await self.session.execute(
                text(
                    "INSERT INTO futures_markets "
                    "(source, external_id, name, category, mutually_exclusive, "
                    " status, event_id, sport_id, created_at, updated_at) "
                    "VALUES (:src, :ext, :name, 'game', TRUE, :status, :eid, :sid, "
                    "        :created, :created) RETURNING id"
                ),
                {
                    "src": source,
                    "ext": ext,
                    "name": f"Gate market {self.n}",
                    "status": status,
                    "eid": event_id,
                    "sid": self.sport_id,
                    "created": self.now - timedelta(minutes=age_min),
                },
            )
        ).scalar()
        for i, price in enumerate(prices):
            await self.session.execute(
                text(
                    "INSERT INTO futures_outcomes "
                    "(market_id, external_id, name, current_probability) "
                    "VALUES (:mid, :ext, :name, :p)"
                ),
                {
                    "mid": market_id,
                    "ext": f"{ext}-{i}",
                    "name": names[i % len(names)],
                    "p": price,
                },
            )
        return market_id

    async def snapshot(self, event_id: int, source: str) -> None:
        from sqlalchemy import text

        await self.session.execute(
            text(
                "INSERT INTO win_prob_snapshots "
                "(event_id, source, home_win_probability, reading_count) "
                "VALUES (:eid, :src, 0.5, 1)"
            ),
            {"eid": event_id, "src": source},
        )


async def _seed(session) -> _Seed:
    from sqlalchemy import text

    now = (await session.execute(text("SELECT NOW()"))).scalar()
    sport_id = (
        await session.execute(
            text(
                "INSERT INTO sports (key, name, active) VALUES (:k, :k, TRUE) "
                "RETURNING id"
            ),
            {"k": SPORT_KEY},
        )
    ).scalar()
    return _Seed(session, sport_id, now)


async def _red_pairs(session) -> tuple[dict, dict]:
    import app.tasks.matching_reconciliation as mrec

    out = await mrec.check_linked_unsourced(session)
    pairs = {(r["event_id"], r["source"]): r for r in out["rows"]}
    return out, pairs


async def test_the_cs2_specimen_all_legs_unpriced_is_not_accused(pg_session):
    """15323417's shape: one open Kalshi market, both legs stored NULL."""
    seed = await _seed(pg_session)
    cs2 = await seed.event()
    await seed.market(cs2, prices=(None, None), ticker="KXCS2GAME-26OCT051500XISTR")
    control = await seed.event()
    await seed.market(control, prices=(0.6, 0.4))
    await pg_session.commit()

    _, pairs = await _red_pairs(pg_session)
    assert (control, "kalshi") in pairs  # the refusal below is not vacuous
    assert (cs2, "kalshi") not in pairs


async def test_a_genuinely_priced_pair_with_no_snapshot_stays_red(pg_session):
    seed = await _seed(pg_session)
    ev = await seed.event()
    await seed.market(ev, prices=(0.62, 0.38))
    await pg_session.commit()

    out, pairs = await _red_pairs(pg_session)
    assert out["red"] is True
    assert pairs[(ev, "kalshi")]["priced_linked_markets"] == 1


async def test_one_priced_market_among_unpriced_keeps_the_pair_and_counts_only_it(
    pg_session,
):
    """Mixed pair: eligible through its priced member. Two priced outcomes on
    that one market must still count ONE market — EXISTS, not a JOIN."""
    seed = await _seed(pg_session)
    ev = await seed.event()
    await seed.market(ev, prices=(None, None))
    await seed.market(ev, prices=(None, None))
    await seed.market(ev, prices=(0.55, 0.45))
    await pg_session.commit()

    _, pairs = await _red_pairs(pg_session)
    assert pairs[(ev, "kalshi")]["priced_linked_markets"] == 1


async def test_a_priced_market_with_an_identity_the_writer_refuses_stays_red(
    pg_session,
):
    """A non-game ticker whose outcomes name no team: the writer would decline
    it, and a priced market the writer declines is what this alert is for."""
    seed = await _seed(pg_session)
    ev = await seed.event()
    await seed.market(
        ev,
        prices=(0.7, 0.3),
        ticker="KXCS2MAPTOTAL-26OCT051500XISTR-2",
        names=("Over 2.5 maps", "Under 2.5 maps"),
    )
    await pg_session.commit()

    _, pairs = await _red_pairs(pg_session)
    assert (ev, "kalshi") in pairs


async def test_a_zero_probability_is_a_price(pg_session):
    seed = await _seed(pg_session)
    ev = await seed.event()
    await seed.market(ev, prices=(0.0, None))
    await pg_session.commit()

    _, pairs = await _red_pairs(pg_session)
    assert (ev, "kalshi") in pairs


async def test_a_snapshot_excludes_only_its_own_event_and_source(pg_session):
    seed = await _seed(pg_session)
    ev = await seed.event()
    other = await seed.event()
    await seed.market(ev, prices=(0.6, 0.4), source="kalshi")
    await seed.market(ev, prices=(0.6, 0.4), source="polymarket")
    await seed.market(other, prices=(0.6, 0.4), source="kalshi")
    await seed.snapshot(ev, "kalshi")
    await pg_session.commit()

    _, pairs = await _red_pairs(pg_session)
    assert (ev, "kalshi") not in pairs
    assert (ev, "polymarket") in pairs
    assert (other, "kalshi") in pairs


async def test_the_temporal_and_status_guards_still_hold_for_priced_markets(
    pg_session,
):
    seed = await _seed(pg_session)
    control = await seed.event()
    far = await seed.event(offset_h=30)
    done = await seed.event(status="completed")
    young = await seed.event()
    closed = await seed.event()
    await seed.market(control, prices=(0.6, 0.4))
    await seed.market(far, prices=(0.6, 0.4))
    await seed.market(done, prices=(0.6, 0.4))
    await seed.market(young, prices=(0.6, 0.4), age_min=5)
    await seed.market(closed, prices=(0.6, 0.4), status="closed")
    await pg_session.commit()

    _, pairs = await _red_pairs(pg_session)
    assert (control, "kalshi") in pairs  # the arms below are not vacuous
    for ev in (far, done, young, closed):
        assert (ev, "kalshi") not in pairs


async def test_unpriced_pairs_cannot_crowd_a_priced_pair_out_of_the_limit(
    pg_session,
):
    """201 unpriced pairs of two markets each would all outrank a one-market
    priced pair under `ORDER BY markets DESC LIMIT 200` if the price test ran
    after the cut. It must run before it."""
    seed = await _seed(pg_session)
    for _ in range(CROWD):
        crowd_ev = await seed.event()
        await seed.market(crowd_ev, prices=(None, None))
        await seed.market(crowd_ev, prices=(None, None))
    priced = await seed.event()
    await seed.market(priced, prices=(0.51, 0.49))
    await pg_session.commit()

    out, pairs = await _red_pairs(pg_session)
    assert (priced, "kalshi") in pairs
    assert len(out["rows"]) < 200  # the crowd is not in the result at all
