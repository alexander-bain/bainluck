"""#2077 residual — the guards must reach the code the way a reader does.

CERT-3311 granted #2077's token on direct code-path review and named ONE
nonblocking follow-up: ``2077-EXERCISE-THE-ACTUAL-GET-FUTURES-MARKET-ENDPOINT``.
This file is that follow-up, and it closes the third appearance of this ship's
single defect class.

═══ 🔴 THE CLASS, THREE TIMES, ONE LEVEL UP EACH TIME ═══

* ``d6936e281`` widened ``_format_market_detail`` to admit resolved boards and
  shipped **22 green guards on a sha that changed nothing a reader could see**.
  Every one of them injected ``fleet_newest_observation`` straight into the
  formatter, so none of them traversed the route seam — and the route was the
  half that was broken (``_fleet_newest_observation`` returned ``None`` without
  a query for every status but ``"open"``). CERT-3308 BLOCKed it.
* ``57ed72128`` repaired the route and added guards that compose
  ``_fleet_newest_observation`` + ``_format_market_detail`` **the way**
  ``get_futures_market`` **does** — but still not **through** it. CERT-3311
  granted the token and wrote the gap down rather than pretending it was shut.
* So the question was still open one layer out: *does any test reach this code
  the way production does, or do they all hand it an input the real caller never
  supplies?* Until this file, the answer was no.

A guard that hands the callee an input the caller never supplies cannot observe
a caller that never supplies it. Composing two helpers in the right order is a
claim ABOUT the route; calling the route is the only thing that is a claim BY
it. These tests issue ``GET /api/futures/{id}`` against the real FastAPI app on
a real Postgres and read the served payload.

═══ THE SPECIMEN ═══

``/futures/56916563`` — *Mia Ristic vs. Viola Turini: Total Sets O/U 2.5* —
resolved 2026-07-31 and on 2026-09-22, fifty-three days later, still served
``Under 0.5`` under a heading that reads "Final Results", with ``Over`` folded
into "More outcomes (1)". Board ``P`` below is that payload, leg for leg: the
half-withheld shape is ``stale_observation_keys`` doing its documented SELECTIVE
fail-open — it withholds the older legs and certifies the last-written one, so
the last gasp before the market died gets crowned as the result.

═══ THE CONTROLS, AND WHAT EACH CAN FAIL ON ═══

Every board carries the SAME healthy two-sided book (``bid 0.49 / ask 0.51``),
the shape #6757's ``C`` control proved is withheld by none of the four sibling
arms. Boards differ ONLY in ``status``, verdict, and stamps, so a difference in
served prices is attributable to the rule under test and to nothing else.

* ``L`` — the fleet's pulse: an open board observed *now*. It is what makes
  ``fleet_newest_observation`` recent, and therefore what makes every other
  board measurably behind the fleet. Its own prices must never move.
* ``R`` — resolved, ungraded, both legs sixty days behind the fleet.
  **🔴 RED ON BASE**: the route handed the formatter ``None``, the rule took its
  fail-open path, and both prices were served. After the fix both are withheld.
* ``P`` — the production shape (the specimen). Two legs, two *different* stamps.
  **🔴 RED ON BASE**: the older leg was already withheld and the newest leg was
  served as a live coin flip. After the fix neither is priced.
* ``G`` — resolved and GRADED (``api_settlement``, winner and loser), same dead
  stamps as ``R``. Prices KEPT. This is ``/futures/413``'s protection ("Jalen
  Brunson 99%", api_settlement on all 57 legs) and it fails if the widening
  over-reaches from "settled" to "settled without a verdict".
* ``F`` — resolved and ungraded but observed five days ago, inside
  ``BOARD_UNOBSERVED_DAYS``. Prices KEPT. Pins the residual the ship stated
  deliberately (a market that settled this morning is awaiting a grader, not
  dead) so the floor cannot widen silently. ``F`` is also the isolation control:
  if any OTHER withhold arm were firing on this leg shape, ``F`` would go
  priceless too.
* ``O`` — open, ungraded, sixty days dead: the original #8011 population.
  Prices WITHHELD. Pins that admitting ``"resolved"`` did not disturb ``"open"``.

═══ TWO INSTRUMENT CONTROLS, BECAUSE BOTH FAILURES LOOK LIKE A PASS ═══

``test_the_seeded_board_stamp_survived_onupdate`` and
``test_the_fleet_pulse_is_recent`` assert the rig itself. ``FuturesMarket``
``updated_at`` carries ``onupdate=func.now()``: if a seeded sixty-day-old stamp
were quietly reset to now, ``board_cannot_be_unobserved`` would short-circuit,
every board would keep its price, and the RED tests would fail for a reason that
has nothing to do with the route. Equally, if ``L`` failed to set a recent fleet
stamp, nothing would be behind the fleet and the withholds would vanish. Both
are dead-instrument modes that read exactly like a verdict about the code, so
both are asserted rather than assumed.

Gated exactly like ``test_futures_no_result_price_exemption_6757_pg.py``: set
``SEARCH_TEST_DATABASE_URL`` (CI's ``search-recall`` job provides one) or the
module skips, loudly.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #2077 route "
            "contract (CI job `search-recall` provides one)"
        ),
    ),
]

LABEL = "SYNTHETIC-2077"
SETTLEMENT = "api_settlement"

#: The one leg economics every board shares, so that only status/verdict/stamps
#: can explain a difference in what is served. A tight two-sided book — #6757's
#: `C` control proved this shape is withheld by none of the four sibling arms.
PRICE, BID, ASK = 0.50, 0.4900, 0.5100

#: Comfortably past `BOARD_UNOBSERVED_DAYS` (30), and close to the specimen's
#: real age (53 days settled) without sitting on the boundary.
DEAD_DAYS = 60

#: Comfortably inside the floor.
FRESH_DAYS = 5


def _now():
    return datetime.now(timezone.utc)


async def _seed(engine) -> dict[str, dict]:
    """Seed the six synthetic boards and return ``{key: {name: id}}``."""
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome

    ids: dict[str, dict] = {}
    # (key, title, status, leg specs) where a leg spec is
    # (name, age_days, resolution_source, is_winner).
    boards = (
        ("L", "the fleet's pulse", "open", (
            ("pulse yes", 0, None, False),
            ("pulse no", 0, None, False),
        )),
        ("R", "resolved, ungraded, dead", "resolved", (
            ("Under", DEAD_DAYS, None, False),
            ("Over", DEAD_DAYS, None, False),
        )),
        ("P", "the production shape (56916563)", "resolved", (
            # The older leg — already withheld on production by the per-leg rule.
            ("Over", DEAD_DAYS + 1, None, False),
            # The board's own newest stamp: the last write before it died, and
            # the number production crowned as "Final Results / Under LATEST 50%".
            ("Under", DEAD_DAYS, None, False),
        )),
        ("G", "resolved and graded", "resolved", (
            ("graded winner", DEAD_DAYS, SETTLEMENT, True),
            ("graded loser", DEAD_DAYS, SETTLEMENT, False),
        )),
        ("F", "resolved, ungraded, inside the floor", "resolved", (
            ("awaiting a grader yes", FRESH_DAYS, None, False),
            ("awaiting a grader no", FRESH_DAYS, None, False),
        )),
        ("O", "open and dead", "open", (
            ("open dead yes", DEAD_DAYS, None, False),
            ("open dead no", DEAD_DAYS, None, False),
        )),
    )

    async with AsyncSession(engine, expire_on_commit=False) as session:
        async with session.begin():
            handles = {}
            for key, title, status, legs in boards:
                m = FuturesMarket(
                    source="kalshi",
                    external_id=f"{LABEL}-{key}",
                    name=f"{LABEL} {title}",
                    description=f"{LABEL} synthetic fixture — not a real market",
                    category="championship",
                    market_tier=5,
                    mutually_exclusive=True,
                    status=status,
                    resolution_date=(
                        _now() - timedelta(days=53) if status == "resolved" else None
                    ),
                )
                session.add(m)
                leg_rows = {}
                for rank, (name, age_days, src, winner) in enumerate(legs, 1):
                    o = FuturesOutcome(
                        market=m,
                        external_id=f"{LABEL}-{key}-{rank}",
                        name=f"{LABEL} {name}",
                        current_probability=PRICE,
                        current_yes_bid=BID,
                        current_yes_ask=ASK,
                        rank=rank,
                        is_winner=winner,
                        resolution_source=src,
                        last_updated=_now() - timedelta(days=age_days),
                    )
                    session.add(o)
                    leg_rows[name] = o
                    # A real two-sided point so no book-shaped arm can claim this
                    # leg for a reason that is not the rule under test.
                    session.add(
                        FuturesOddsSnapshot(
                            outcome=o,
                            bookmaker="kalshi",
                            probability=PRICE,
                            yes_bid=BID,
                            yes_ask=ASK,
                            last_price=PRICE,
                            captured_at=_now() - timedelta(days=age_days),
                        )
                    )
                handles[key] = (m, leg_rows)

        for key, (m, leg_rows) in handles.items():
            ids[key] = {"market": m.id, **{n: o.id for n, o in leg_rows.items()}}

    # 🔴 `FuturesMarket.updated_at` carries `onupdate=func.now()`, and the board
    # rule reads it as the parent poller stamp. RAW SQL, because `onupdate` is
    # applied to ORM flushes and to Core `update()` alike — only a text statement
    # leaves the value alone. Asserted in `test_the_seeded_board_stamp_survived_onupdate`.
    async with AsyncSession(engine) as session:
        for key, _title, status, legs in boards:
            oldest = max(age for _n, age, _s, _w in legs)
            await session.execute(
                text(
                    "UPDATE futures_markets SET updated_at = :ts WHERE id = :id"
                ),
                {"ts": _now() - timedelta(days=oldest), "id": ids[key]["market"]},
            )
        await session.commit()
    return ids


@pytest.fixture
async def seeded(monkeypatch):
    """Real Postgres, real schema, the real route; session dependency pointed here."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.dependencies.auth import get_optional_user
    from app.main import app
    from app.services.database import Base, get_db, get_db_rw

    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    ids = await _seed(engine)

    async def _get_db():
        async with AsyncSession(engine, expire_on_commit=False) as session:
            yield session

    async def _anon():
        return None

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_db_rw] = _get_db
    app.dependency_overrides[get_optional_user] = _anon

    # The detail route caches its provenance half in Redis; make that half a
    # no-op so the assertions read the rows and never a cached prior run.
    import app.routes.futures as fr

    async def _no_sources(_db, _market_id, _outcome_ids):
        return [], []

    monkeypatch.setattr(fr, "_load_market_sources", _no_sources)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, ids, engine

    app.dependency_overrides.clear()
    await engine.dispose()


def _label(name: str) -> str:
    return f"{LABEL} {name}"


async def _detail(client, market_id):
    r = await client.get(f"/api/futures/{market_id}")
    assert r.status_code == 200, r.text
    return r.json()


def _prices(detail) -> dict[str, float | None]:
    """The served ladder, by leg name.

    🔴 The wire key is ``probability``. The DB column is ``current_probability``;
    reading THAT off the payload returns ``None`` for every leg of every board,
    which is indistinguishable from a fully-withheld board and would make every
    assertion below pass vacuously.
    """
    return {o["name"]: o["probability"] for o in detail["outcomes"]}


class TestTheInstrument:
    """Both of these failures look exactly like a verdict about the code."""

    async def test_the_seeded_board_stamp_survived_onupdate(self, seeded):
        _client, ids, engine = seeded
        from sqlalchemy.ext.asyncio import AsyncSession

        async with AsyncSession(engine) as session:
            row = (
                await session.execute(
                    text("SELECT updated_at FROM futures_markets WHERE id = :id"),
                    {"id": ids["R"]["market"]},
                )
            ).scalar_one()
        age_days = (_now() - row).total_seconds() / 86400
        assert age_days > 30, (
            f"board stamp is {age_days:.1f}d old — `onupdate=func.now()` reset the "
            "seeded value, so `board_cannot_be_unobserved` short-circuits and every "
            "withhold assertion below would pass for the wrong reason"
        )

    async def test_the_fleet_pulse_is_recent(self, seeded):
        _client, _ids, engine = seeded
        from sqlalchemy.ext.asyncio import AsyncSession

        async with AsyncSession(engine) as session:
            newest = (
                await session.execute(
                    text("SELECT max(last_updated) FROM futures_outcomes")
                )
            ).scalar_one()
        lag_days = (_now() - newest).total_seconds() / 86400
        assert lag_days < 1, (
            f"the fleet's newest observation is {lag_days:.1f}d old — board L did "
            "not set a recent pulse, so no board is measurably behind the fleet and "
            "nothing would be withheld regardless of the route"
        )


class TestR_ResolvedUngradedAndDead:
    async def test_the_route_withholds_both_prices(self, seeded):
        """🔴 RED ON BASE. The route handed the formatter None and both were served."""
        client, ids, _engine = seeded
        prices = _prices(await _detail(client, ids["R"]["market"]))
        assert prices == {_label("Under"): None, _label("Over"): None}, prices

    async def test_the_rows_keep_their_place(self, seeded):
        """Withheld, not dropped — the leg keeps its name, rank and opening."""
        client, ids, _engine = seeded
        detail = await _detail(client, ids["R"]["market"])
        assert len(detail["outcomes"]) == 2
        assert detail["prices_withheld"] == 2


class TestP_TheProductionShape:
    async def test_the_crowned_coin_flip_is_gone(self, seeded):
        """🔴 RED ON BASE. `/futures/56916563` served `Under 0.5` for 53 days.

        The older leg was already withheld by the per-leg rule; the board's own
        newest stamp — the last write before the market died — was served, and
        the page crowned it under a heading that reads "Final Results".
        """
        client, ids, _engine = seeded
        prices = _prices(await _detail(client, ids["P"]["market"]))
        assert prices[_label("Under")] is None, (
            "the last gasp before the board died is still being served as a live "
            "coin flip — this is the specimen, exactly as production served it"
        )
        assert prices[_label("Over")] is None
        assert (await _detail(client, ids["P"]["market"]))["prices_withheld"] == 2


class TestG_AVerdictIsAResult:
    async def test_a_graded_board_keeps_every_price(self, seeded):
        """`/futures/413`'s protection. Fails if the widening over-reaches."""
        client, ids, _engine = seeded
        detail = await _detail(client, ids["G"]["market"])
        prices = _prices(detail)
        assert prices == {
            _label("graded winner"): PRICE,
            _label("graded loser"): PRICE,
        }, prices
        assert detail["prices_withheld"] == 0


class TestF_TheFloorResidual:
    async def test_a_board_awaiting_a_grader_keeps_its_price(self, seeded):
        """The stated residual, pinned so it cannot widen silently.

        Doubles as the isolation control: if any OTHER withhold arm fired on this
        leg shape, this board would go priceless too and the RED tests above would
        prove nothing about the route.
        """
        client, ids, _engine = seeded
        detail = await _detail(client, ids["F"]["market"])
        assert _prices(detail) == {
            _label("awaiting a grader yes"): PRICE,
            _label("awaiting a grader no"): PRICE,
        }
        assert detail["prices_withheld"] == 0


class TestO_TheOriginalPopulation:
    async def test_an_open_dead_board_is_still_withheld(self, seeded):
        """#8011 unchanged. Pins that admitting "resolved" did not disturb "open"."""
        client, ids, _engine = seeded
        prices = _prices(await _detail(client, ids["O"]["market"]))
        assert prices == {
            _label("open dead yes"): None,
            _label("open dead no"): None,
        }, prices


class TestL_NothingMoves:
    async def test_the_fleet_pulse_keeps_its_prices(self, seeded):
        client, ids, _engine = seeded
        detail = await _detail(client, ids["L"]["market"])
        assert _prices(detail) == {
            _label("pulse yes"): PRICE,
            _label("pulse no"): PRICE,
        }
        assert detail["prices_withheld"] == 0
