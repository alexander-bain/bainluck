"""#8220's untaken-offer arm, driven through the real grid on real PostgreSQL.

## what a reader saw

``/playoffs/ncaa-basketball`` at 390px. **South Dakota St read 13% to reach the
Title Game and <0.1% to win it** — a factor of 260 on one row. Florida (19.5% →
9.53%) and Duke (20.5% → 8.81%) are the two rows that land where a coin-flip
final puts them, and they are the two rows with real two-sided books.

The Title Game column offered **4.58 probability for 2 places**.

## why this gate is at the GRID and not at the predicate

🔴 **#8220 EXISTS BECAUSE A CORRECT RULE WAS UNWIRED AT THIS ROUTE.**
``is_lone_ask_in_exclusive_field`` was written for exactly this book shape in
#6846 and returns True on the specimen. It reached no reader because
``routes/playoffs.py`` imported one member of ``futures_unsupported_price`` and
not the other. A unit test of the predicate — and
``tests/test_grid_untaken_offer_8220.py`` is that, one level down — would have
gone on passing through the entire life of the defect.

So the assertions below are taken off the payload the page renders, with the
route function executing its own SQL against a server. A mutant that deletes the
call site in ``get_playoff_grid`` is caught here and nowhere else.

## the frame, and why it is declared rather than read

``market_is_proved_exclusive_field`` refuses all five round markets, and not
because its winner-count term reads ``== "1"``: measured on production
2026-09-23 they store ``exhaustive: None / expected_winners: None /
outcome_relation: 'unknown'`` at ``confidence: 'low'``. The classifier declined
them, so the frame fails three clauses and no winner count exists upstream at
all. ``routes/playoffs`` supplies it instead, because it built the column.

## the corpus is the production market

``KXMARMADROUND-27T2`` / "Men's Championship Game Qualifiers", read 2026-09-23
~11:5xZ. Of its 112 legs, 94 are ask-only and 91 of those have never traded
(``last_price 0 / volume 0 / open interest 0``). The specimen's and the two
controls' books are their real stored values.
"""

import os

import pytest
from sqlalchemy import text

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the #8220 grid untaken-offer gate "
        "against real PostgreSQL"
    ),
)

pytestmark.append(needs_postgres)

SPORT_ID = 965322
MARKET_T2 = 965322001
MARKET_CHAMP = 965322002
_MARKETS = (MARKET_T2, MARKET_CHAMP)

#: ``(team, probability, bid, ask, resolution_source, admitted)`` on the
#: ``title_game`` column. The last field is the ship: True means the cell must
#: still be served. Every control fails EXACTLY ONE clause, so a mutant that
#: drops that clause is isolated by the row named for it.
#:
#: 🔴 EVERY NAME IS IN ``NCAA_2026_BRACKET``, AND THAT IS LOAD-BEARING RATHER
#: THAN TIDY. Step 4d drops any team not in that static list, so a refused
#: specimen that is not in it would be absent from the payload because it was
#: FILTERED, and every "the cell is gone" assertion below would pass without the
#: rule under test running at all. The first draft of this file used Syracuse,
#: Creighton, Marquette and Xavier; none is in the list, and three of them
#: vanished for that reason. ``test_no_corpus_team_was_dropped_by_the_bracket
#: _filter`` holds this shut.
_T2_LEGS = (
    # 🔴 THE SPECIMEN. Nobody bidding, one untaken offer at 15c, no trade since
    # 2026-04-28. We served 0.13 — the ask, to the cent — beside a <0.1% to win
    # the whole thing, a factor of 260 on one row.
    ("South Dakota St Jackrabbits", 0.13, 0.00, 0.15, None, False),
    # 🔴 The same shape at the HEAD of the column, not only in the tail. Houston
    # is served 0.22 off a zero bid. A fix reaching only the longshots would
    # leave the reader's ranking inverted at the top, which is the half of the
    # defect a "13% vs <0.1%" framing hides.
    ("Houston Cougars", 0.22, 0.00, 0.22, None, False),
    # 🔴 NOT A CONTROL — THE OPPOSITE, and the row that separates #6876 from a
    # naive "resolution_source IS NOT NULL". `ungradeable_result` RETRACTS a
    # verdict: it asserts no winner, so the number beside it is still a quote and
    # is still refused.
    ("Alabama Crimson Tide", 0.14, 0.00, 0.14, "ungradeable_result", False),
    # CONTROL, fails the BOOK clause alone: Duke's real two-sided book, the row
    # whose 20.5% -> 8.81% ratio was already right. Must keep its number.
    ("Duke Blue Devils", 0.205, 0.11, 0.29, None, True),
    # CONTROL, fails the BOOK clause alone: Florida, the other honest row.
    ("Florida Gators", 0.195, 0.16, 0.22, None, True),
    # CONTROL, fails the VERDICT clause alone (#7387/#6876): the venue graded it,
    # so its number is a settlement value and withholding it would delete a
    # result.
    #
    # 🔴 PRICED BELOW ITS OWN ASK ON PURPOSE. The first draft graded this row at
    # 0.99 against an ask of 0.15, and #6532's arm — which runs immediately
    # above this one and refuses a price its own book prices out — ate it before
    # the graded exemption was ever reached. A control removed by the wrong
    # clause isolates nothing.
    ("Michigan St Spartans", 0.14, 0.00, 0.15, "api_settlement", True),
    # CONTROL, fails the BOOK clause alone: a MISSING bid is not a zero bid. NULL
    # means the poller never recorded a book, and the rule must not claim to know
    # anything about those rows.
    ("Villanova Wildcats", 0.12, None, 0.14, None, True),
    # CONTROL, fails the BOOK clause alone: no offer at all is not an offer of
    # zero. Drop `yes_ask > 0` and every leg on a book with no ask is refused.
    ("Purdue Boilermakers", 0.09, 0.00, 0.00, None, True),
    # CONTROL, fails the BOOK clause alone: one cent of bid is somebody paying
    # something, which is the evidence the entire rule turns on.
    ("Kansas Jayhawks", 0.11, 0.01, 0.15, None, True),
)

#: Championship legs. EVERY corpus team gets one, and that mirrors production:
#: all 68 cells in that column are populated, so no team's row depends on its
#: bracket cell existing. It is what makes a withheld Title Game cell mean "this
#: row kept its name and lost its number" rather than "this row vanished", and
#: it is what makes the refusal assertions non-vacuous — the team is still on the
#: page to be checked.
#:
#: South Dakota St's is the FRAME control and carries the specimen's own book
#: shape: a zero bid and a lone 1c offer, which is the `<0.1%` the reader saw. It
#: must SURVIVE, because `championship` is deliberately outside
#: `_ADVANCEMENT_COLUMNS` — every one of its production cells carries a
#: non-Kalshi source, so withholding a contributor there is a blending change
#: (reviewed class under 49(d)) and not this ship. A mutant that drops the column
#: gate refuses this row, and no assertion on the Title Game column can see it.
_CHAMP_LEGS = (
    ("South Dakota St Jackrabbits", 0.0005, 0.00, 0.01, None, True),
) + tuple(
    (name, 0.05, 0.04, 0.06, None, True)
    for name, *_rest in _T2_LEGS
    if name != "South Dakota St Jackrabbits"
)

_T2_REFUSED = {n for n, *_r, admitted in _T2_LEGS if not admitted}
_T2_ADMITTED = {n for n, *_r, admitted in _T2_LEGS if admitted}
_ALL_TEAMS = {n for n, *_r in _T2_LEGS}


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

    🔴 THE MARKET NAME IS WHAT PUTS EACH ROW IN ITS COLUMN, and the two are not
    interchangeable. "Men's Championship Game Qualifiers" matches the
    ``Championship\\s+Game`` rule and lands on ``title_game``; "Men's College
    Basketball Champion" matches ``College\\s+Basketball\\s+Champion\\b`` and
    lands on ``championship``. Swap them and the frame control moves into the
    very column it exists to sit outside of, and it passes for the wrong reason.

    🔴 ``external_id`` MUST CARRY THE CONFIGURED PREFIX. ncaa-basketball reaches
    these markets through ``external_id_prefixes = ["KXMARMADROUND", "KXMARMAD-2"]``
    (Path A), so a market seeded under any other id is invisible and every
    "the refused leg is gone" assertion passes because nothing was ever there.

    🔴 ``last_updated`` COMES FROM THE SERVER. The ingest loop drops any outcome
    older than seven days before it reaches the arm under test, so a hard-coded
    timestamp would be a correct seed today and would later make every assertion
    pass for the wrong reason — the rows absent because they were stale, not
    because they were refused.
    """
    await conn.execute(
        text("INSERT INTO sports (id, key, name, active) VALUES (:id, :k, :n, true)"),
        {"id": SPORT_ID, "k": f"test_8220_{SPORT_ID}", "n": "Test 8220"},
    )
    for market_id, source, external_id, name in (
        (MARKET_T2, "kalshi", "KXMARMADROUND-27T2", "Men's Championship Game Qualifiers"),
        (MARKET_CHAMP, "kalshi", "KXMARMAD-27", "Men's College Basketball Champion"),
    ):
        await conn.execute(
            text(
                "INSERT INTO futures_markets (id, source, external_id, name, "
                "category, mutually_exclusive, status, market_tier, "
                "llm_sport_category) VALUES "
                "(:id, :src, :ext, :name, 'championship', true, "
                "'open', 5, 'basketball')"
            ),
            {"id": market_id, "src": source, "ext": external_id, "name": name},
        )

    for market_id, legs in ((MARKET_T2, _T2_LEGS), (MARKET_CHAMP, _CHAMP_LEGS)):
        for name, prob, bid, ask, resolution_source, _admitted in legs:
            await conn.execute(
                text(
                    "INSERT INTO futures_outcomes (market_id, external_id, name, "
                    "current_probability, current_yes_bid, current_yes_ask, "
                    "resolution_source, is_winner, last_updated) VALUES "
                    "(:mid, :ext, :name, :p, :bid, :ask, :rs, false, NOW())"
                ),
                {
                    "mid": market_id,
                    "ext": f"{market_id}-{name.replace(' ', '')[:12].upper()}",
                    "name": name,
                    "p": prob,
                    "bid": bid,
                    "ask": ask,
                    "rs": resolution_source,
                },
            )


async def _cells(engine, column: str) -> dict[str, float]:
    """Drive the real route and read one column of the served payload."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.routes.playoffs import get_playoff_grid

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        grid = await get_playoff_grid(
            league_slug="ncaa-basketball", hours=None, top=50, debug=False, db=session
        )

    teams = list(grid.get("teams") or [])
    for group in (grid.get("grouped_teams") or {}).values():
        teams.extend(group)

    # BOTH payload shapes, because the grid serves two: ``cells`` keyed by column
    # and ``stages`` as a list. Reading only one is how a passing assertion comes
    # to mean "the key I looked under was absent" rather than "the cell is gone".
    out: dict[str, float] = {}
    for team in teams:
        name = team.get("name") or ""
        cell = (team.get("cells") or {}).get(column)
        if isinstance(cell, dict) and cell.get("merged_probability") is not None:
            out[name] = float(cell["merged_probability"])
        for stage in team.get("stages") or []:
            if stage.get("key") == column and stage.get("probability") is not None:
                out[name] = float(stage["probability"])
    return out


def _match(served: dict[str, float], wanted: str) -> bool:
    """Grid rows carry full club names ("South Dakota St Jackrabbits")."""
    w = wanted.lower().replace(".", "").replace(" ", "")
    return any(w in k.lower().replace(".", "").replace(" ", "") for k in served)


@needs_postgres
async def test_no_corpus_team_was_dropped_by_the_bracket_filter(pg_engine):
    """🔴 THE ANTI-VACUITY GUARD, and it must run before any refusal is believed.

    Step 4d filters this grid to ``NCAA_2026_BRACKET``. A refused specimen that
    is not in that list is absent from the payload for a reason that has nothing
    to do with the rule under test, and every assertion below would pass with the
    fix reverted. Every corpus team also carries a championship leg, so its ROW
    exists whatever happens to its bracket cell — which is production's shape,
    where all 68 teams have a champion number.

    So: each team must be ON the page. What varies is whether it has a Title Game
    NUMBER.
    """
    rows = await _cells(pg_engine, "championship")
    missing = sorted(n for n in _ALL_TEAMS if not _match(rows, n))
    assert missing == [], (
        f"these corpus teams never reached the payload at all: {missing}. "
        "Their absence from the Title Game column would prove nothing — check "
        "they are in NCAA_2026_BRACKET and that their championship leg seeded."
    )


@needs_postgres
async def test_the_specimen_cell_is_gone_from_the_served_column(pg_engine):
    """The ship, as the reader's sentence: no 13% to reach a final."""
    served = await _cells(pg_engine, "title_game")
    assert not _match(served, "South Dakota St Jackrabbits"), (
        "South Dakota St still has a Title Game cell "
        f"({served}). Its book is a zero bid and one untaken 15c offer with no "
        "trade in five months, and the page printed 13% to reach the final "
        "beside <0.1% to win it."
    )


@needs_postgres
async def test_every_untaken_offer_is_refused_and_every_real_book_survives(pg_engine):
    """One assertion over the whole corpus, so a mutant cannot pass by halves."""
    served = await _cells(pg_engine, "title_game")
    still = sorted(n for n in _T2_REFUSED if _match(served, n))
    assert still == [], f"untaken offers still served: {still} (cells={served})"
    lost = sorted(n for n in _T2_ADMITTED if not _match(served, n))
    assert lost == [], (
        f"honest legs lost their cell: {lost} (cells={served}). This arm "
        "withholds; it must never blank a row whose book supports its number."
    )


@needs_postgres
async def test_the_column_is_not_emptied(pg_engine):
    """🔴 THE STRAWMAN GUARD.

    Every assertion above is satisfied by a grid that serves nothing at all, and
    "the page went blank" is the failure mode a withholding rule reaches for.
    The column must still be a column.
    """
    served = await _cells(pg_engine, "title_game")
    assert len(served) >= len(_T2_ADMITTED), (
        f"only {len(served)} Title Game cells survived, expected at least "
        f"{len(_T2_ADMITTED)}: {served}"
    )


@needs_postgres
async def test_the_refused_row_keeps_its_name(pg_engine):
    """Withholding, never deleting (gotcha #21).

    The reader must still see South Dakota St on the page — with its champion
    number and without a Title Game one. A rule that removed the row would also
    satisfy every "the cell is gone" assertion above, and it is the wrong
    treatment: the leg keeps its name and loses its number.
    """
    rows = await _cells(pg_engine, "championship")
    assert _match(rows, "South Dakota St Jackrabbits"), (
        f"the specimen's whole row disappeared: {rows}"
    )


@needs_postgres
async def test_the_frame_holds_the_championship_column_out(pg_engine):
    """The column gate is real at the ROUTE, not only in the helper.

    Byte-identical book to the specimen, one column over. A mutant that drops
    ``col_key in _ADVANCEMENT_COLUMNS`` refuses this row, and every assertion on
    the Title Game column stays green while it does.
    """
    served = await _cells(pg_engine, "championship")
    assert _match(served, "South Dakota St Jackrabbits"), (
        "the championship cell was withheld too "
        f"({served}). That column is blended — 38 of 68 production cells carry "
        "Kalshi beside odds_api — so withholding a contributor there is a "
        "blending change and is deliberately not this ship."
    )


@needs_postgres
async def test_the_column_sum_falls_toward_the_number_of_places(pg_engine):
    """What the ship does, in the units that make it a defect.

    A bracket column is summed and read as a distribution. On production the
    Title Game column offered 4.58 for 2 places; withholding the untaken offers
    takes it to 2.08. Asserted as a fall against the seeded total rather than a
    fixed figure, because the corpus is a sample of the column and the exact sum
    is not the claim.
    """
    served = await _cells(pg_engine, "title_game")
    total = sum(served.values())
    seeded = sum(p for _n, p, *_r in _T2_LEGS)
    assert total < seeded, (
        f"the untaken offers are still in the sum: served {total:.3f} of a "
        f"seeded {seeded:.3f}"
    )
