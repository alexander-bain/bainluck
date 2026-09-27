"""The Canadiens' page prints the Canadiens' markets under either spelling (#9219).

## What a reader saw

Production 2026-09-27 ~22:20Z, `bainluck.com/sport/hockey/nhl/team/montral-canadiens`
at 390px: SEASON FUTURES listed three rows ("Montréal Canadiens · 3 markets
tracked") while the division table on the same page put the club at 14% for the
division. Every missing leg is NAMED "Montreal Canadiens":

    NHL Atlantic Division Winner                                  0.145
    NHL Playoffs: Eastern Conference Team to advance to Second Round 0.30
    NHL: 2027 Champion                                            0.057

and the club is two same-sport rows, tied on everything the collapse ranks by:

    568    Montreal Canadiens    icehockey_nhl  espn 10  3 identity mappings
    3706   Montréal Canadiens    icehockey_nhl  espn 10  3 identity mappings
    12651  Montreal              icehockey_nhl  espn 10  (holds the legs above)

## Two gaps, both closed here

1. `get_team` asked `_query_team_futures` for `[team.id]` only, although its
   games rails already use the club's row set (`_club_row_identity`, #7929).
2. `_query_team_futures` built its name patterns AFTER its identity collapse,
   from the one row that won it. With 568 and 3706 tied, the loser's spelling
   was never searched — so which markets printed depended on row order.

Real engine (SQLite with the #5491/#7929 DDL shims), real `select()`s; only the
price screen is stubbed to "nothing refused", because it is #8503's subject and
not this one's. Every name, id and price is the production specimen.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models.models import (  # noqa: E402
    Base,
    FuturesMarket,
    FuturesOutcome,
    Sport,
    Team,
    TeamIdentityMapping,
)
from app.routes import futures as futures_route  # noqa: E402
from app.routes import teams as teams_route  # noqa: E402
from app.routes.user import _query_team_futures  # noqa: E402

S_NHL = 70001
S_NHL_PRE = 70002

PLAIN_ROW = 568
ACCENTED_ROW = 3706
FRAGMENT_ROW = 12651
TORONTO = 115

PLAIN = "Montreal Canadiens"
ACCENTED = "Montréal Canadiens"

#: Legs named with the PLAIN spelling, bound to the fragment row (production).
ATLANTIC = 1001
SECOND_ROUND = 1002
#: The leg the page already printed — accented, bound to 3706.
STANLEY_CUP = 1003
#: CONTROL — another club's market in the same sport must stay off the page.
LEAFS_ONLY = 1004


#: Identity-mapping counts per spelling. Production is the tie (3, 3), and a
#: tie resolves by ROW ORDER: SQLite returns 568 first every time, Postgres
#: returns heap order. So the tie alone can never show the accented row
#: winning here; the two lopsided counts force each spelling to win outright.
TIE = {PLAIN_ROW: 3, ACCENTED_ROW: 3}
PLAIN_WINS = {PLAIN_ROW: 4, ACCENTED_ROW: 3}
ACCENTED_WINS = {PLAIN_ROW: 3, ACCENTED_ROW: 4}


def _world(team_order=(PLAIN_ROW, ACCENTED_ROW), mappings=TIE):
    teams = {
        PLAIN_ROW: Team(
            id=PLAIN_ROW, sport_id=S_NHL, name=PLAIN,
            slug="montreal-canadiens", espn_id="10",
        ),
        ACCENTED_ROW: Team(
            id=ACCENTED_ROW, sport_id=S_NHL, name=ACCENTED,
            slug="montral-canadiens", espn_id="10",
        ),
    }
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Sport(id=S_NHL, key="icehockey_nhl", name="NHL"))
        s.add(Sport(id=S_NHL_PRE, key="icehockey_nhl_preseason", name="NHL Preseason"))
        for tid in team_order:
            s.add(teams[tid])
        s.add(Team(id=FRAGMENT_ROW, sport_id=S_NHL, name="Montreal",
                   slug="montreal-nhl", espn_id="10"))
        s.add(Team(id=TORONTO, sport_id=S_NHL, name="Toronto Maple Leafs",
                   slug="toronto-maple-leafs", espn_id="21"))
        s.flush()
        # Identity mappings: the collapse's first tiebreak (name length, its
        # second, is equal for the two spellings).
        for tid in (PLAIN_ROW, ACCENTED_ROW):
            for n in range(mappings[tid]):
                s.add(TeamIdentityMapping(team_id=tid, source=f"src{n}",
                                          source_name="x", sport_key="icehockey_nhl"))
        for mid, name, tier, leg, team_id, prob in (
            (ATLANTIC, "NHL Atlantic Division Winner", 3, PLAIN, FRAGMENT_ROW, 0.145),
            (SECOND_ROUND,
             "NHL Playoffs: Eastern Conference Team to advance to Second Round",
             3, PLAIN, FRAGMENT_ROW, 0.30),
            (STANLEY_CUP, "2026-27 Stanley Cup Finals Winner", 1, ACCENTED,
             ACCENTED_ROW, 0.045),
            (LEAFS_ONLY, "NHL Norris Trophy", 4, "Toronto Maple Leafs", TORONTO, 0.2),
        ):
            s.add(FuturesMarket(
                id=mid, source="kalshi", external_id=f"K-{mid}", name=name,
                sport_id=S_NHL, status="open", llm_sport_category="hockey",
                market_tier=tier,
            ))
            s.add(FuturesOutcome(id=mid * 10, market_id=mid, name=leg, external_id=f"K-{mid}-o",
                                 team_id=team_id, current_probability=prob))
        s.commit()
    return eng


class _Savepoint:
    async def commit(self):
        pass

    async def rollback(self):
        pass


class _AsyncSession:
    """The route's `await db.execute(...)` over a real sync session."""

    def __init__(self, s):
        self._s = s

    async def execute(self, statement, *a, **k):
        return self._s.execute(statement, *a, **k)

    async def begin_nested(self):
        return _Savepoint()


async def _nothing_refused(_db, markets):
    return {m.id: set() for m in markets}


def _futures(eng, team_ids):
    with Session(eng) as s:
        with patch.object(futures_route, "withheld_price_outcome_ids_for_markets",
                          _nothing_refused):
            data = asyncio.run(_query_team_futures(team_ids, _AsyncSession(s), limit=30))
    return {i["market_id"] for i in data["items"]}


def _page(eng, slug):
    with Session(eng) as s:
        with patch.object(futures_route, "withheld_price_outcome_ids_for_markets",
                          _nothing_refused):
            page = asyncio.run(teams_route.get_team(slug, db=_AsyncSession(s)))
    return {i["market_id"] for i in page["futures"]}


CANADIENS_MARKETS = {ATLANTIC, SECOND_ROUND, STANLEY_CUP}


@pytest.mark.parametrize("mappings", [TIE, PLAIN_WINS, ACCENTED_WINS], ids=["tie", "plain-wins", "accented-wins"])
@pytest.mark.parametrize("team_order", [(PLAIN_ROW, ACCENTED_ROW), (ACCENTED_ROW, PLAIN_ROW)])
@pytest.mark.parametrize("ids", [[PLAIN_ROW, ACCENTED_ROW], [ACCENTED_ROW, PLAIN_ROW]])
def test_both_spellings_are_searched_whichever_row_wins_the_collapse(mappings, team_order, ids):
    """One answer whichever row wins. Before the fix the answer was the
    winner's spelling only: with the accented row winning, every leg named
    "Montreal Canadiens" was never searched."""
    assert _futures(_world(team_order, mappings), ids) == CANADIENS_MARKETS


@pytest.mark.parametrize("mappings", [TIE, ACCENTED_WINS], ids=["tie", "accented-wins"])
def test_the_accented_url_prints_the_plain_named_division_markets(mappings):
    """The ship: the page the Canadiens' URL resolves to (3706) prints the
    Atlantic Division and playoff-round legs, not just the Stanley Cup."""
    assert _page(_world(mappings=mappings), "montral-canadiens") == CANADIENS_MARKETS


def test_the_plain_url_prints_the_same_set():
    assert _page(_world(), "montreal-canadiens") == CANADIENS_MARKETS


def test_another_clubs_market_stays_off_the_page():
    """CONTROL: widening to the club's spellings does not reach a rival."""
    assert LEAFS_ONLY not in _page(_world(), "montral-canadiens")
    assert _page(_world(), "toronto-maple-leafs") == {LEAFS_ONLY}


def test_a_single_row_club_is_unchanged():
    """No dupe row, no collapse: the Leafs' query is exactly its own."""
    assert _futures(_world(), [TORONTO]) == {LEAFS_ONLY}


def test_strawman_the_accented_winner_hides_the_plain_legs_from_a_canonical_only_search():
    """STRAWMAN for the second gap — the fixture carries it. With the accented
    row winning the collapse, the plain-named legs are reachable ONLY through
    the loser's spelling: none of them is bound to 568 or 3706, so neither the
    FK branch nor the winner's own name can find them."""
    world = _world(mappings=ACCENTED_WINS)
    with Session(world) as s:
        bound = {
            o.market_id for o in s.query(FuturesOutcome)
            if o.team_id in (PLAIN_ROW, ACCENTED_ROW)
        }
        accented_named = {
            o.market_id for o in s.query(FuturesOutcome) if ACCENTED in o.name
        }
    assert (bound | accented_named) == {STANLEY_CUP}


def test_strawman_the_url_row_alone_misses_the_division_markets():
    """STRAWMAN — the fixture carries the defect. Asked for the URL's row only
    (the pre-fix call), the accented page reads the accented leg and nothing
    named "Montreal Canadiens"."""
    assert _futures(_world(), [ACCENTED_ROW]) == {STANLEY_CUP}
