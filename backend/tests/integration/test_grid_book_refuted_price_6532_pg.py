"""#6532's book-refutation arm, driven through the real grid on real PostgreSQL.

## what a reader saw

``/events/15312074`` — Valencia v Real Sociedad, a fixture four days from
kick-off — printed **"Relegated 99%"** for Real Sociedad under *Season context*,
directly beneath that club's own record on the same card, **2-1-3**, six games
into a twenty-club season. ``/events/15312073`` printed Villarreal at
``Relegated 44%`` beside ``Top 4 27%``. ``/sport/soccer/laliga`` showed the whole
column at once, summing to **8.24** in a league that relegates exactly three.

Real Sociedad's row carries ``current_probability 0.99`` beside
``current_yes_ask 0.4900``. You can buy the outcome at 49c while we print 99%.

## why this gate is at the GRID and not at the predicate

All three of those surfaces read ``routes/playoffs.get_playoff_grid`` through
``services/league_context``. None of them reads ``/api/futures/{id}``. A unit
test of :func:`price_refuted_by_live_book` — and this file has those too, one
level down in ``tests/test_futures_book_refuted_price_6532.py`` — would go on
passing on the day the grid stopped calling it, and every surface the reader
complained about would be unchanged. So the assertions below are taken off the
payload the page renders, with the route function executing its own SQL against
a server.

## what only a server can decide

The ingest loop the arm sits in is 50 lines inside a 1,000-line handler that
opens with a raw ``SET LOCAL statement_timeout``, loads overrides, resolves
每 market to a column, then bounds the outcome load (#1484). Whether a refused
leg is gone from the SERVED cell — rather than merely refused by a predicate
somebody called — is a fact about that whole chain, including the cross-source
merge below it, and only a real session evaluates it.

## the corpus is the production market

Market ``56775508`` / ``KXLALIGARELEGATION-27``, read on production
2026-09-16 ~10:5xZ. Its own rows supply both the defect and the controls: 15 of
its 19 priced legs carry ``resolution_source='api_settlement'`` on a contest that
resolves in July 2027, which is why the two shipped arms of
``futures_unsupported_price`` are disarmed on it before any price rule is
reached. Each control below fails EXACTLY ONE clause of the predicate, so a
mutant that drops that clause is isolated by the row named for it.
"""

import os

import pytest
from sqlalchemy import text

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the #6532 grid book-refutation gate "
        "against real PostgreSQL"
    ),
)

pytestmark.append(needs_postgres)

SPORT_ID = 965321
MARKET_KALSHI = 965321001
MARKET_POLY = 965321002
_MARKETS = (MARKET_KALSHI, MARKET_POLY)

#: ``(team, probability, bid, ask, resolution_source, is_winner, admitted)``.
#:
#: Every club here is on the production market and normalises to its own grid
#: row. The last field is the ship: True means the cell must still be served.
_KALSHI_LEGS = (
    # 🔴 THE SPECIMEN. Graded a LOSER on a contest ten months from resolving,
    # priced at 0.99, offered at 0.49. Refused.
    ("Real Sociedad", 0.99, 0.00, 0.49, "api_settlement", False, False),
    # Ungraded and refused on the same arm — one cent over its own ask is still
    # over it, because the page prints whole percents and the shared predicate's
    # half-cent tolerance is what "the same number to the reader" means.
    ("Valencia", 0.48, 0.00, 0.47, None, False, False),
    # CONTROL, fails the ask clause ALONE: graded the same way, priced the same
    # way, and its book offers it ABOVE what we print. Nothing refutes 0.60 when
    # you cannot buy it below 0.97.
    ("Levante", 0.60, 0.00, 0.97, "api_settlement", False, True),
    # CONTROL, fails the verdict clause ALONE: identical shape to the specimen
    # except the venue says this one WON. A settled winner beside a book nobody
    # refreshed keeps its price — withholding it would delete a result, which is
    # the harm the graded exemption exists to prevent.
    ("Barcelona", 0.99, 0.00, 0.07, "api_settlement", True, True),
    # CONTROL, fails the "graded rows get the ask arm only" clause ALONE: a
    # graded loser whose price sits BELOW a live bid. Its number is still the ~0
    # its grade implies, so the mirror arm must be off for it. The symmetric form
    # blanks this row; 110 production legs are in this shape.
    ("Espanyol", 0.02, 0.40, 0.62, "api_settlement", False, True),
    # The same shape UNGRADED is a quote, and a quote the live bid prices out is
    # refuted whichever side prices it out. This is the only row that proves the
    # mirror arm is reachable at all.
    ("Getafe", 0.10, 0.40, 0.62, None, False, False),
    # PIN, not a clause control: an ask of 1.00 cannot be exceeded by any price,
    # so #5121's predicate is inert on the empty book BY CONSTRUCTION rather than
    # by a special case, and `kalshi_resolution_sweep` depends on that shape
    # falling through. No single clause deletion reddens this row — what it
    # catches is somebody REPLACING the imported rule with a re-derived one
    # ("bid is 0 and the price is high"), which would eat a different ship's
    # defect along with this one.
    ("Alaves", 0.99, 0.00, 1.00, None, False, True),
    # CONTROL, fails the `yes_ask > 0` clause ALONE: no offer at all is not an
    # offer of zero. Drop that clause and every priced leg on a book with no ask
    # is refused, because any price exceeds nothing by more than half a cent.
    ("Celta Vigo", 0.47, 0.00, 0.00, None, False, True),
    # CONTROL, fails the tolerance ALONE: four ten-thousandths over its own ask,
    # which prints as the same whole percent the reader sees. Set the shared
    # epsilon to zero and this row is refused for a difference nobody can see.
    #
    # Priced at 0.70 and NOT near 0.50 on purpose. The grid's own pre-existing
    # noise filter drops any Kalshi leg within 0.02 of a coin flip that has no
    # bid, so the first draft of this control (0.5040 / 0.50) went missing for a
    # reason that had nothing to do with #6532 — a control removed by the wrong
    # clause isolates nothing.
    ("Rayo Vallecano", 0.7040, 0.00, 0.70, None, False, True),
)

#: The venue control. Byte-identical to the specimen but written by Polymarket,
#: whose rule for these columns is a different one (gotcha #19: a wide spread
#: falls back to ``lastTradePrice``, so a price legitimately sits above the ask
#: whenever the last trade did). 385 ungraded Polymarket legs are in this shape
#: and #5876's arm — not this one — is what answers for them.
_POLY_LEGS = (("Girona", 0.99, 0.00, 0.49, None, False, True),)

_REFUSED = {t for t, *_rest, admitted in _KALSHI_LEGS + _POLY_LEGS if not admitted}
_ADMITTED = {t for t, *_rest, admitted in _KALSHI_LEGS + _POLY_LEGS if admitted}


@pytest.fixture
async def pg_engine():
    """Real Postgres with the real schema.

    Function-scoped for the reason #6511's gate states: ``pytest.ini`` leaves
    ``asyncio_default_fixture_loop_scope`` unset, so a module-scoped async
    fixture would outlive the loop that made its engine. ``create_all`` only,
    never ``drop_all`` — the database is shared and this gate owns nothing but
    its own id block.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _clear(conn)
        await _seed(conn)

    yield engine

    async with engine.begin() as conn:
        await _clear(conn)
    await engine.dispose()


async def _clear(conn) -> None:
    await conn.execute(
        text("DELETE FROM futures_outcomes WHERE market_id = ANY(:ids)"),
        {"ids": list(_MARKETS)},
    )
    await conn.execute(
        text("DELETE FROM futures_markets WHERE id = ANY(:ids)"),
        {"ids": list(_MARKETS)},
    )
    await conn.execute(text("DELETE FROM sports WHERE id = :id"), {"id": SPORT_ID})


async def _seed(conn) -> None:
    """Insert the corpus.

    🔴 EVERY NOT NULL COLUMN IS SPELLED OUT, INCLUDING THE ONES THAT LOOK
    OPTIONAL. ``sports.active``, ``futures_markets.category`` /
    ``.mutually_exclusive`` / ``.status`` carry a **client-side** ``default=``
    the ORM applies and a raw INSERT does not, so omitting one raises
    ``NotNullViolation`` rather than taking the default.
    ``tests/test_pg_gate_seed_completeness.py`` parses these statements against
    live ORM metadata and this file is registered in its ``COVERED`` tuple.

    🔴 ``llm_sport_category`` IS WHAT PUTS THE MARKET ON THIS GRID AT ALL, and it
    is not decoration. la-liga configures NO Kalshi ticker prefix
    (``external_id_prefixes = []``), so ``KXLALIGARELEGATION-27`` reaches the
    grid through Path B.2 — category plus a league name pattern — exactly as it
    does on production. Seeded without it the whole corpus is invisible, every
    "the refused leg is gone" assertion passes for the wrong reason, and only
    ``test_the_column_is_not_emptied`` notices. It did.

    🔴 ``last_updated`` COMES FROM THE SERVER. The ingest loop drops any outcome
    older than seven days before it reaches the arm under test, so a hard-coded
    timestamp would be a correct seed on the day it was written and would later
    make every assertion below pass for the wrong reason — the rows would be
    absent because they were stale, not because they were refuted.
    """
    await conn.execute(
        text("INSERT INTO sports (id, key, name, active) VALUES (:id, :k, :n, true)"),
        {"id": SPORT_ID, "k": f"test_6532_{SPORT_ID}", "n": "Test 6532"},
    )
    for market_id, source, external_id in (
        (MARKET_KALSHI, "kalshi", "KXLALIGARELEGATION-27"),
        (MARKET_POLY, "polymarket", "la-liga-relegation-2026-27"),
    ):
        await conn.execute(
            text(
                "INSERT INTO futures_markets (id, source, external_id, name, "
                "category, mutually_exclusive, status, market_tier, "
                "llm_sport_category) VALUES "
                "(:id, :src, :ext, 'La Liga Relegation', 'championship', true, "
                "'open', 5, 'soccer')"
            ),
            {"id": market_id, "src": source, "ext": external_id},
        )

    for market_id, legs in ((MARKET_KALSHI, _KALSHI_LEGS), (MARKET_POLY, _POLY_LEGS)):
        for name, prob, bid, ask, resolution_source, is_winner, _admitted in legs:
            await conn.execute(
                text(
                    "INSERT INTO futures_outcomes (market_id, external_id, name, "
                    "current_probability, current_yes_bid, current_yes_ask, "
                    "resolution_source, is_winner, last_updated) VALUES "
                    "(:mid, :ext, :name, :p, :bid, :ask, :rs, :w, NOW())"
                ),
                {
                    "mid": market_id,
                    "ext": f"KXLALIGARELEGATION-27-{name[:3].upper()}-{market_id}",
                    "name": name,
                    "p": prob,
                    "bid": bid,
                    "ask": ask,
                    "rs": resolution_source,
                    "w": is_winner,
                },
            )


async def _relegation_cells(engine) -> dict[str, float]:
    """Drive the real route and read the column the reader complained about.

    Returns ``{team name: merged_probability}`` for the ``relegation`` column of
    ``/api/playoffs/la-liga`` — the same dict ``services/league_context`` turns
    into the event page's *Season context* card and ``/sport/soccer/laliga``
    prints as a list.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.routes.playoffs import get_playoff_grid

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        grid = await get_playoff_grid(
            league_slug="la-liga", hours=None, top=50, debug=False, db=session
        )

    teams = list(grid.get("teams") or [])
    for group in (grid.get("grouped_teams") or {}).values():
        teams.extend(group)

    # BOTH payload shapes, because the grid serves two and ``league_context``
    # reads two: ``cells`` keyed by column (what la-liga actually returns) and
    # ``stages`` as a list. Reading only one is how a passing assertion comes to
    # mean "the key I looked under was absent" rather than "the cell is gone" —
    # this reader was written against ``stages`` alone and every refusal
    # assertion passed vacuously until the strawman guard below caught it.
    cells: dict[str, float] = {}
    for team in teams:
        name = team.get("name") or ""
        cell = (team.get("cells") or {}).get("relegation")
        if isinstance(cell, dict) and cell.get("merged_probability") is not None:
            cells[name] = float(cell["merged_probability"])
        for stage in team.get("stages") or []:
            if stage.get("key") == "relegation" and stage.get("probability") is not None:
                cells[name] = float(stage["probability"])
    return cells


@needs_postgres
async def test_the_specimen_cell_is_gone_from_the_served_column(pg_engine):
    """The ship, stated as the reader's sentence: no "Relegated 99%"."""
    cells = await _relegation_cells(pg_engine)
    assert "Real Sociedad" not in cells, (
        "Real Sociedad still has a relegation cell at "
        f"{cells.get('Real Sociedad')}. Its row serves 0.99 against its own ask "
        "of 0.49 — you can buy the outcome at 49c — and it is what the reader "
        "saw printed beneath that club's own 2-1-3 record."
    )


@needs_postgres
async def test_every_refuted_leg_is_refused_and_every_control_survives(pg_engine):
    """One assertion over the whole corpus, so a mutant cannot pass by halves."""
    cells = await _relegation_cells(pg_engine)
    served = set(cells)
    assert served & _REFUSED == set(), (
        f"refuted legs still served: {sorted(served & _REFUSED)} (cells={cells})"
    )
    assert _ADMITTED <= served, (
        f"honest legs lost their cell: {sorted(_ADMITTED - served)} (cells={cells}). "
        "This arm withholds; it must never blank a row the book does not refute."
    )


@needs_postgres
async def test_the_column_is_not_emptied(pg_engine):
    """🔴 THE STRAWMAN GUARD.

    Every assertion above is satisfied by a grid that serves nothing at all —
    and "the page went blank" is the failure mode a withholding rule reaches
    for. The column must still be a column.
    """
    cells = await _relegation_cells(pg_engine)
    assert len(cells) >= len(_ADMITTED), (
        f"only {len(cells)} relegation cells survived, expected at least "
        f"{len(_ADMITTED)}: {cells}"
    )


@needs_postgres
async def test_the_sum_is_reduced_but_not_claimed_correct(pg_engine):
    """What this ship does and does NOT do, pinned so nobody overstates it later.

    The production column sums to 8.24 where exactly three clubs go down. This
    arm removes the legs whose own book refutes them and nothing else, so the
    sum FALLS and does not reach 3. The remaining over-sum is an illiquid book
    quoting half the league at ~0.5 — not row-decidable, not this ship, and not
    fixed by pretending otherwise.
    """
    cells = await _relegation_cells(pg_engine)
    total = sum(cells.values())
    seeded = sum(p for _n, p, *_r in _KALSHI_LEGS) + sum(p for _n, p, *_r in _POLY_LEGS)
    assert total < seeded, (
        f"the refused legs are still in the sum: served {total:.2f} of a seeded "
        f"{seeded:.2f}"
    )
