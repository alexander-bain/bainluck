"""#7829 part 1 — two schools the venue spells ``Miami (FL)`` and ``Miami (OH)``
reach the NCAAF grid as TWO identities, driven through the real route on real
PostgreSQL.

## what a reader saw

``/api/playoffs/ncaa-football``, read 2026-09-21 15:26Z: **Miami Hurricanes
with no `make_playoffs` and no `semifinal` cell** — championship only. Kalshi
prices both a Miami (FL) leg and a Miami (OH) leg on the playoff markets, and
the grid could not say which school either belonged to, so the Hurricanes'
own numbers landed on a row the page does not serve.

## the mechanism, measured

``normalize_team_name`` strips a *trailing* parenthetical, so the venue's
``Miami (FL)`` and ``Miami (OH)`` both key the grid as ``miami``. One key then
collects both ticker suffixes (``MIA`` and ``MOH``), both candidates hit, and
the #7821 anchor **correctly** fails closed on two hits. The identity is lost
*before* any resolver runs: the pool is the defect, the resolver is not.

## why this gate is at the GRID and not at a helper

A unit test of a new key function passes whether or not the route calls it.
The claim here is about what the payload serves, so every assertion is taken
off the grid the page renders, with ``get_playoff_grid`` executing its own SQL
against a server.

## the three seeds, and why there are three

* ``forward`` — the production face. Miami (OH) is graded OUT of the playoff
  (0.0, ``api_settlement``): **the valid zero**, served as the verdict
  ``eliminated`` with no number. On base the pooled key binds to Miami (OH),
  its verdict swallows the Hurricanes' 0.71, and the Hurricanes are blank.
* ``permuted`` — the same corpus with outcome rows reversed and the two kalshi
  markets' ids swapped, so a fix that works because of insertion or source
  order fails here. The schools may not swap.
* ``oh_live`` — Miami (OH) priced LIVE at 0.79 instead of graded. Now the
  pool has no verdict to hide behind: on base the reader sees **0.71 on Miami
  (OH)** — the Hurricanes' number on the wrong school, the #7821 defect's
  publishing face — and the Hurricanes blank. Every Miami assertion is red on
  base under this seed.

## controls, and what each one holds shut

* **Texas A&M Aggies** (``TXAM``) — #7829 part 2's already-paid half.
* **North Carolina Tar Heels** (``UNC``) vs North Carolina A&T — the two-
  candidate family the rejected "fewest remaining words" rule regressed.
* **Dirty abbreviations, as measured on production**: California Golden Bears
  carries ``MIA``, Ohio State ``PSU``, Michigan State ``WMU``, Florida A&M
  ``MSU``. None may start claiming another team's legs — California's bogus
  ``MIA`` may not pull a Miami leg onto California, and Florida A&M's bogus
  ``MSU`` may not pull Michigan State's ``MSU`` leg onto the Rattlers.
* **Miami (OH) absent from one market** — the semifinal market prices only
  Miami (FL). The RedHawks' semifinal cell must be absent, not borrowed.
* **A qualified name with no ticker** (the ``anchorless`` seed) — every
  ``Miami (FL)`` leg arrives with an ``external_id`` that is not a ticker, so
  the key has no suffix at all. With nothing to anchor on, the legs may NOT be
  bound to Miami (OH) by string length; they stay unbound (a blank, the benign
  face). Red on base, where the lone ``MOH`` hit binds the pool to Miami (OH).
"""

import os
from dataclasses import dataclass

import pytest
from sqlalchemy import text

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the #7829 Miami identity grid gate "
        "against real PostgreSQL"
    ),
)

pytestmark.append(needs_postgres)

SPORT_ID = 978291
MARKET_CHAMP = 978291001     # odds_api, championship column
MARKET_PLAYOFF = 978291002   # kalshi, make_playoffs column
MARKET_SEMI = 978291003      # kalshi, semifinal column
_MARKETS = (MARKET_CHAMP, MARKET_PLAYOFF, MARKET_SEMI)
_TEAM_ID_BASE = 978291100

#: ``teams`` rows: (name, abbreviation). Abbreviations are the REAL production
#: values as measured 2026-09-21 — including the four dirty ones.
TEAMS = (
    ("Miami Hurricanes", "MIA"),
    ("Miami (OH) RedHawks", "M-OH"),
    ("Texas A&M Aggies", "TA&M"),
    ("North Carolina Tar Heels", "UNC"),
    ("North Carolina A&T Aggies", "NCAT"),
    ("California Golden Bears", "MIA"),      # dirty — really MIA on production
    ("Ohio State Buckeyes", "PSU"),           # dirty
    ("Michigan State Spartans", "WMU"),       # dirty
    ("Florida A&M Rattlers", "MSU"),          # dirty
)
KNOWN = {name for name, _ab in TEAMS}

#: odds_api championship legs: full club names, one per team, so every row is
#: on the page whatever happens to its bracket cells (production's shape).
CHAMP_LEGS = tuple((name, 0.02 + 0.005 * i) for i, (name, _ab) in enumerate(TEAMS))

#: kalshi make_playoffs legs: (outcome name as the venue spells it, ticker
#: suffix, probability, bid, ask, resolution_source). Miami (OH)'s leg is set
#: per seed (see ``OH_GRADED`` / ``OH_LIVE``).
#:
#: Miami (FL) is priced OUTSIDE the 0.45-0.65 single-source-Kalshi noise band
#: on purpose: a cell in that band with no corroborating source is removed by a
#: filter that has nothing to do with this ship.
PLAYOFF_LEGS = (
    ("Miami (FL)", "MIA", 0.71, 0.70, 0.72, None),
    ("Texas A&M", "TXAM", 0.44, 0.43, 0.45, None),
    ("North Carolina", "UNC", 0.12, 0.11, 0.13, None),
    ("California", "CAL", 0.07, 0.06, 0.08, None),
    ("Ohio State", "OSU", 0.83, 0.82, 0.84, None),
    ("Michigan State", "MSU", 0.21, 0.20, 0.22, None),
    ("Florida A&M", "FAMU", 0.03, 0.02, 0.04, None),
)

#: Miami (OH)'s make_playoffs leg. THE VALID ZERO is a graded-out leg
#: (``api_settlement``, 0.0): an ungraded 0.0 never reaches the merge — the
#: #7387 rail drops it — so the only zero the grid can serve is a verdict, and
#: it renders as ``state: "eliminated"`` with no number. ``oh_live`` prices the
#: same leg at 0.79, ABOVE Miami (FL)'s 0.71, so the pooled per-source dedup
#: (keep lowest) on base visibly puts 0.71 on the RedHawks.
OH_GRADED = ("Miami (OH)", "MOH", 0.00, 0.00, 0.00, "api_settlement")
OH_LIVE = ("Miami (OH)", "MOH", 0.79, 0.78, 0.80, None)

#: kalshi semifinal legs — Miami (OH) is deliberately ABSENT here.
SEMI_LEGS = (
    ("Miami (FL)", "MIA", 0.27, 0.26, 0.28),
    ("Texas A&M", "TXAM", 0.19, 0.18, 0.20),
    ("North Carolina", "UNC", 0.05, 0.04, 0.06),
    ("Ohio State", "OSU", 0.48, 0.47, 0.49),
)

CONTROL_PLAYOFF = {
    "Texas A&M Aggies": 0.44,
    "North Carolina Tar Heels": 0.12,
    "California Golden Bears": 0.07,
    "Ohio State Buckeyes": 0.83,
    "Michigan State Spartans": 0.21,
    "Florida A&M Rattlers": 0.03,
}
CONTROL_SEMI = {
    "Texas A&M Aggies": 0.19,
    "North Carolina Tar Heels": 0.05,
    "Ohio State Buckeyes": 0.48,
}


@dataclass
class Seeded:
    engine: object
    variant: str

    @property
    def oh_live(self) -> bool:
        return self.variant == "oh_live"

    def expected_playoff(self) -> dict[str, float]:
        out = dict(CONTROL_PLAYOFF)
        out["Miami Hurricanes"] = 0.71
        if self.oh_live:
            out["Miami (OH) RedHawks"] = 0.79
        return out

    def expected_semi(self) -> dict[str, float]:
        return {**CONTROL_SEMI, "Miami Hurricanes": 0.27}


async def _engine(**seed_kwargs):
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _clear(conn)
        await _seed(conn, **seed_kwargs)
    return engine


async def _dispose(engine):
    async with engine.begin() as conn:
        await _clear(conn)
    await engine.dispose()


@pytest.fixture(params=["forward", "permuted", "oh_live"])
async def seeded(request):
    """Real Postgres with the real schema, seeded three ways (module docstring).

    Function-scoped for the reason #6511's gate states; ``create_all`` only,
    never ``drop_all`` — the database is shared and this gate owns nothing
    but its own id block.
    """
    engine = await _engine(
        permuted=(request.param == "permuted"),
        oh_live=(request.param == "oh_live"),
    )
    yield Seeded(engine, request.param)
    await _dispose(engine)


@pytest.fixture
async def seeded_anchorless():
    """The ``oh_live`` corpus, except every Miami (FL) leg has NO ticker suffix."""
    engine = await _engine(permuted=False, oh_live=True, anchorless=True)
    yield Seeded(engine, "anchorless")
    await _dispose(engine)


async def _clear(conn) -> None:
    await conn.execute(
        text("DELETE FROM futures_outcomes WHERE market_id = ANY(:ids)"),
        {"ids": list(_MARKETS)},
    )
    await conn.execute(
        text("DELETE FROM futures_markets WHERE id = ANY(:ids)"),
        {"ids": list(_MARKETS)},
    )
    await conn.execute(
        text("DELETE FROM teams WHERE id >= :lo AND id < :hi"),
        {"lo": _TEAM_ID_BASE, "hi": _TEAM_ID_BASE + 100},
    )
    await conn.execute(text("DELETE FROM sports WHERE id = :id"), {"id": SPORT_ID})


async def _seed(conn, *, permuted: bool, oh_live: bool, anchorless: bool = False) -> None:
    """Insert the corpus.

    🔴 EVERY NOT NULL COLUMN IS SPELLED OUT, INCLUDING THE ONES THAT LOOK
    OPTIONAL. ``sports.active``, ``futures_markets.category`` /
    ``.mutually_exclusive`` / ``.status`` carry a **client-side** ``default=``
    the ORM applies and a raw INSERT does not, so omitting one raises
    ``NotNullViolation`` rather than taking the default.
    ``tests/test_pg_gate_seed_completeness.py`` parses these statements against
    live ORM metadata and this file is registered in its ``COVERED`` tuple.

    🔴 THE MARKET NAME IS WHAT PUTS EACH ROW IN ITS COLUMN. "College Football
    Playoff" satisfies the league name pattern (Path B.2, ``llm_sport_category
    = 'football'``); "Make the College Football Playoff" lands on
    ``make_playoffs`` and "...Playoff Semifinal" on ``semifinal``. The
    championship market reaches the grid through Path A on its odds_api
    ``external_id`` prefix ``americanfootball_ncaaf``. No year appears in any
    name, so the season filter has nothing to act on.

    🔴 ``last_updated`` COMES FROM THE SERVER. The ingest loop drops any outcome
    older than seven days before it reaches the merge under test.
    """
    await conn.execute(
        text("INSERT INTO sports (id, key, name, active) VALUES (:id, :k, :n, true)"),
        {"id": SPORT_ID, "k": f"test_7829_{SPORT_ID}", "n": "Test 7829"},
    )
    for i, (name, abbreviation) in enumerate(TEAMS):
        await conn.execute(
            text(
                "INSERT INTO teams (id, sport_id, name, abbreviation) "
                "VALUES (:id, :sid, :name, :ab)"
            ),
            {"id": _TEAM_ID_BASE + i, "sid": SPORT_ID, "name": name, "ab": abbreviation},
        )

    playoff_id, semi_id = (MARKET_PLAYOFF, MARKET_SEMI)
    if permuted:
        playoff_id, semi_id = (MARKET_SEMI, MARKET_PLAYOFF)

    markets = [
        (MARKET_CHAMP, "odds_api", "americanfootball_ncaaf_championship_winner_t7829",
         "NCAAF Championship Winner"),
        (playoff_id, "kalshi", "KXCFPMAKE-T7829",
         "Will a team Make the College Football Playoff"),
        (semi_id, "kalshi", "KXCFPSEMI-T7829",
         "College Football Playoff Semifinal Qualifiers"),
    ]
    if permuted:
        markets.reverse()
    for market_id, source, external_id, name in markets:
        await conn.execute(
            text(
                "INSERT INTO futures_markets (id, source, external_id, name, "
                "category, mutually_exclusive, status, market_tier, "
                "llm_sport_category) VALUES "
                "(:id, :src, :ext, :name, 'championship', false, "
                "'open', 5, 'football')"
            ),
            {"id": market_id, "src": source, "ext": external_id, "name": name},
        )

    async def _leg(market_id, ext, name, p, bid, ask, rs=None):
        await conn.execute(
            text(
                "INSERT INTO futures_outcomes (market_id, external_id, name, "
                "current_probability, current_yes_bid, current_yes_ask, "
                "resolution_source, is_winner, last_updated) VALUES "
                "(:mid, :ext, :name, :p, :bid, :ask, :rs, false, NOW())"
            ),
            {"mid": market_id, "ext": ext, "name": name, "p": p, "bid": bid,
             "ask": ask, "rs": rs},
        )

    order = (lambda rows: list(reversed(rows))) if permuted else list

    def _ext(market_ext: str, name: str, suffix: str) -> str:
        # `anchorless`: Miami (FL)'s legs carry an id that is NOT a ticker under
        # the market's own ticker, so `_ticker_suffix` yields None for them.
        if anchorless and name == "Miami (FL)":
            return f"legacy-{name}"
        return f"{market_ext}-{suffix}"

    playoff_legs = PLAYOFF_LEGS[:1] + ((OH_LIVE if oh_live else OH_GRADED),) + PLAYOFF_LEGS[1:]

    for name, p in order(CHAMP_LEGS):
        await _leg(MARKET_CHAMP, name, name, p, p - 0.005, p + 0.005)
    for name, suffix, p, bid, ask, rs in order(playoff_legs):
        await _leg(playoff_id, _ext("KXCFPMAKE-T7829", name, suffix), name, p, bid, ask, rs)
    for name, suffix, p, bid, ask in order(SEMI_LEGS):
        await _leg(semi_id, _ext("KXCFPSEMI-T7829", name, suffix), name, p, bid, ask)


async def _grid(seeded: Seeded) -> dict:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.routes.playoffs import get_playoff_grid

    maker = async_sessionmaker(seeded.engine, expire_on_commit=False)
    async with maker() as session:
        return await get_playoff_grid(
            league_slug="ncaa-football", hours=None, top=50, debug=False, db=session
        )


def _rows(grid: dict) -> dict[str, dict]:
    teams = list(grid.get("teams") or [])
    for group in (grid.get("grouped_teams") or {}).values():
        teams.extend(group)
    return {t.get("name") or "": t for t in teams}


def _cell(team: dict, column: str):
    """A served number for one column, from either payload shape, or None."""
    cell = (team.get("cells") or {}).get(column)
    if isinstance(cell, dict) and cell.get("merged_probability") is not None:
        return float(cell["merged_probability"])
    for stage in team.get("stages") or []:
        if stage.get("key") == column and stage.get("probability") is not None:
            return float(stage["probability"])
    return None


def _column(grid: dict, column: str) -> dict[str, float]:
    """Served NUMBERS in one column, on KNOWN teams. A terminal cell has none."""
    out = {}
    for name, team in _rows(grid).items():
        v = _cell(team, column)
        if v is not None and name in KNOWN:
            out[name] = round(v, 4)
    return out


def _state(grid: dict, column: str) -> dict[str, str]:
    """Served cell STATE in one column ("live" / "eliminated" / "won"...)."""
    out = {}
    for name, team in _rows(grid).items():
        cell = (team.get("cells") or {}).get(column)
        if isinstance(cell, dict) and cell.get("state"):
            out[name] = cell["state"]
    return out


# ---------------------------------------------------------------------------
# anti-vacuity
# ---------------------------------------------------------------------------

@needs_postgres
async def test_every_corpus_team_is_on_the_page(seeded):
    """Every team carries a championship leg, so every ROW must exist. A row
    absent from the payload proves nothing about its bracket cells."""
    rows = _rows(await _grid(seeded))
    missing = sorted(n for n in KNOWN if n not in rows)
    assert missing == [], f"corpus teams never reached the payload: {missing}"


# ---------------------------------------------------------------------------
# the ship
# ---------------------------------------------------------------------------

@needs_postgres
async def test_miami_hurricanes_receive_their_own_playoff_and_semifinal_cells(seeded):
    """The reader's sentence: the Hurricanes stop being championship-only."""
    grid = await _grid(seeded)
    playoff = _column(grid, "make_playoffs")
    semi = _column(grid, "semifinal")
    assert playoff.get("Miami Hurricanes") == 0.71, (
        f"Miami Hurricanes make_playoffs = {playoff.get('Miami Hurricanes')!r}; "
        f"the venue's Miami (FL) leg is 0.71. Column: {playoff}"
    )
    assert _state(grid, "make_playoffs").get("Miami Hurricanes") == "live", (
        "the Hurricanes' make_playoffs cell is not a live number: "
        f"{_state(grid, 'make_playoffs')}. A terminal state here is Miami (OH)'s "
        "graded-out verdict published on the wrong school."
    )
    assert semi.get("Miami Hurricanes") == 0.27, (
        f"Miami Hurricanes semifinal = {semi.get('Miami Hurricanes')!r}; "
        f"the venue's Miami (FL) leg is 0.27. Column: {semi}"
    )


@needs_postgres
async def test_miami_oh_keeps_its_own_identity_and_inherits_nothing(seeded):
    """Miami (OH) serves exactly its own make_playoffs leg — the graded-out
    verdict (``eliminated``, no number) or, under ``oh_live``, 0.79 — and NO
    semifinal cell, because the semifinal market never priced it.

    Under ``oh_live`` this is red on base: the pool binds to the RedHawks and
    the per-source dedup keeps the LOWER of the two legs, so the reader sees
    the Hurricanes' 0.71 on Miami (OH). Under the graded seeds the verdict
    masks that number on base; there the assertion is the guard against a
    candidate that moves the verdict onto the Hurricanes.
    """
    grid = await _grid(seeded)
    playoff = _column(grid, "make_playoffs")
    semi = _column(grid, "semifinal")
    states = _state(grid, "make_playoffs")
    if seeded.oh_live:
        assert playoff.get("Miami (OH) RedHawks") == 0.79, (
            f"Miami (OH) make_playoffs = {playoff.get('Miami (OH) RedHawks')!r}; "
            f"its own leg is 0.79. 0.71 here is the Hurricanes' number. Column: {playoff}"
        )
        assert states.get("Miami (OH) RedHawks") == "live"
    else:
        assert states.get("Miami (OH) RedHawks") == "eliminated", (
            f"Miami (OH) make_playoffs state = {states.get('Miami (OH) RedHawks')!r}; "
            f"its own leg is a graded-out 0.0. States: {states}; numbers: {playoff}"
        )
        assert "Miami (OH) RedHawks" not in playoff, (
            f"Miami (OH) serves a make_playoffs NUMBER ({playoff.get('Miami (OH) RedHawks')}); "
            "its only leg is a verdict, so that number is another school's."
        )
    assert "Miami (OH) RedHawks" not in semi, (
        f"Miami (OH) has a semifinal cell ({semi.get('Miami (OH) RedHawks')}) "
        "but the semifinal market never priced it — that number is the Hurricanes'."
    )


@needs_postgres
async def test_the_whole_make_playoffs_column_is_exactly_the_venue_legs(seeded):
    """One assertion over the column: every served number is the number the
    venue put on THAT school, and nothing else is served. Holds the schools
    from swapping under any seed order."""
    grid = await _grid(seeded)
    assert _column(grid, "make_playoffs") == seeded.expected_playoff()


@needs_postgres
async def test_the_whole_semifinal_column_is_exactly_the_venue_legs(seeded):
    grid = await _grid(seeded)
    assert _column(grid, "semifinal") == seeded.expected_semi()


# ---------------------------------------------------------------------------
# controls
# ---------------------------------------------------------------------------

@needs_postgres
async def test_texas_am_and_north_carolina_controls_hold(seeded):
    """#7829 part 2 (TXAM→TA&M) and #7821's UNC family are untouched."""
    grid = await _grid(seeded)
    playoff = _column(grid, "make_playoffs")
    assert playoff.get("Texas A&M Aggies") == 0.44
    assert playoff.get("North Carolina Tar Heels") == 0.12
    assert "North Carolina A&T Aggies" not in playoff


@needs_postgres
async def test_dirty_abbreviations_claim_nothing(seeded):
    """California really carries ``MIA`` on production; Florida A&M carries
    ``MSU`` while Michigan State's ticker IS ``MSU``. Neither may pull another
    school's leg onto its own row, and Miami's ``MIA`` leg may not leak to
    California."""
    grid = await _grid(seeded)
    playoff = _column(grid, "make_playoffs")
    for name, expected in CONTROL_PLAYOFF.items():
        assert playoff.get(name) == expected, (name, playoff)
    assert playoff.get("Miami Hurricanes") == 0.71


@needs_postgres
async def test_a_qualified_name_with_no_ticker_is_not_bound_by_length(seeded_anchorless):
    """Every ``Miami (FL)`` leg arrives without a ticker; Miami (OH) keeps ``MOH``
    and is priced live at 0.79.

    With nothing to anchor on, binding the Hurricanes' legs by string length
    puts 0.71 and 0.27 on Miami (OH) — which is exactly what base does here,
    because the pooled key's lone ``MOH`` hit binds it to the RedHawks. The
    candidate leaves them unbound: no served TEAM carries them, the Hurricanes
    are (honestly) blank, and Miami (OH) serves exactly its own 0.79.
    """
    grid = await _grid(seeded_anchorless)
    playoff = _column(grid, "make_playoffs")
    semi = _column(grid, "semifinal")
    assert 0.71 not in playoff.values(), (
        f"the un-anchored Miami (FL) playoff leg was bound to a team: {playoff}"
    )
    assert 0.27 not in semi.values(), (
        f"the un-anchored Miami (FL) semifinal leg was bound to a team: {semi}"
    )
    assert playoff.get("Miami (OH) RedHawks") == 0.79, playoff
    assert "Miami (OH) RedHawks" not in semi
    assert "Miami Hurricanes" not in playoff and "Miami Hurricanes" not in semi
    # The controls do not move with the anchor: they never depended on it.
    for name, expected in CONTROL_PLAYOFF.items():
        assert playoff.get(name) == expected, (name, playoff)
