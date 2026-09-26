"""#8704: searching `united` stops spending seconds on a check that cannot apply.

The played gate's third arm (#6304) suppresses an UNATTACHED market whose venue
group sibling sits on a game already played. It used to state that scope as
two outer-only quals (`futures_markets.event_id IS NULL AND group_id IS NOT
NULL`). Postgres runs the NOT EXISTS as an anti-join, and an outer-only qual in
an anti-join cannot skip the inner side. So every candidate paid the sibling scan
and an `events` probe per sibling, attached or not. 1,160 of `united`'s 1,343
open name matches are attached. The emitted window took 9.2-9.5 s on production;
with the scope moved into the sibling key it took 1.0-1.1 s and returned the same
60 ids in order (the helper's docstring has the measurement and the whole-pool
set-identity census).

The rewrite is an equivalence, so what this file pins is that it STAYS one:

* an event-ATTACHED market in a played group, whose name names the played pair,
  is still offered (arm 1 reads its own event, which is not over). This is the
  row the rewrite could get wrong. Dropping the CASE, so the key is a bare
  `group_id`, suppresses it, and `test_an_attached_market_is_never_the_arms_business`
  fails.
* the unattached specimen is still suppressed, so the key did not go NULL for
  everyone.
* the Postgres spelling carries the scope in the key and no longer carries the
  outer-only quals whose placement was the cost.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, aliased


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models import Event, FuturesMarket, Sport  # noqa: E402
from app.models.models import Base  # noqa: E402
from app.routes.events import _futures_game_already_played  # noqa: E402

_T = datetime(2026, 9, 26, 3, 0, tzinfo=timezone.utc)

PLAYED = 15400001          # completed: Manchester United v Brentford
UPCOMING = 15400002        # scheduled: Manchester United v Brentford (the return leg)
GROUP = "polymarket:8704"

M_ATTACHED_SIBLING = 62000001   # on the played game: arm 1 suppresses it
M_UNATTACHED_NAMED = 62000002   # no event, names the pair: arm 3 suppresses it
M_ATTACHED_ELSEWHERE = 62000003  # on the UPCOMING game, same group, names the pair
M_UNATTACHED_OTHER = 62000004   # no event, names neither side: kept
M_UNGROUPED = 62000005          # no event, no group, names the pair: kept


def _market(market_id, event_id, name, group_id=GROUP):
    return FuturesMarket(
        id=market_id,
        source="polymarket",
        external_id=f"ext-{market_id}",
        event_id=event_id,
        name=name,
        category="game_prop",
        status="open",
        group_id=group_id,
    )


@pytest.fixture(scope="module")
def engine():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Sport(id=9, key="soccer_epl", name="EPL"))
        for event_id, status in ((PLAYED, "completed"), (UPCOMING, "scheduled")):
            s.add(
                Event(
                    id=event_id,
                    sport_id=9,
                    home_team_name="Manchester United",
                    away_team_name="Brentford",
                    commence_time=_T,
                    status=status,
                )
            )
        s.add(_market(M_ATTACHED_SIBLING, PLAYED, "Manchester United vs Brentford"))
        s.add(_market(M_UNATTACHED_NAMED, None, "Manchester United vs Brentford: BTTS"))
        s.add(
            _market(
                M_ATTACHED_ELSEWHERE, UPCOMING, "Manchester United vs Brentford (return)"
            )
        )
        s.add(_market(M_UNATTACHED_OTHER, None, "Premier League top scorer"))
        s.add(
            _market(M_UNGROUPED, None, "Manchester United vs Brentford", group_id=None)
        )
        s.commit()
    return eng


def _offered(eng, clause) -> set[int]:
    with Session(eng) as s:
        return set(s.execute(select(FuturesMarket.id).where(clause)).scalars().all())


def _sql(stmt) -> str:
    return str(
        stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    ).replace("%%", "%")


def _the_arm_keyed_on_a_bare_group_id():
    """The mutant: the CASE dropped, so the key no longer carries the scope."""
    sibling = aliased(FuturesMarket, name="grp_sibling")
    ghost = aliased(Event, name="grp_ghost")
    return ~(
        select(sibling.id)
        .select_from(sibling)
        .join(ghost, ghost.id == sibling.event_id)
        .where(
            sibling.group_id == FuturesMarket.group_id,
            ghost.status == "completed",
            FuturesMarket.name.ilike("%" + ghost.home_team_name + "%"),
            FuturesMarket.name.ilike("%" + ghost.away_team_name + "%"),
        )
        .correlate(FuturesMarket)
        .exists()
    )


class TestTheEquivalenceHolds:
    def test_an_attached_market_is_never_the_arms_business(self, engine):
        assert M_ATTACHED_ELSEWHERE in _offered(engine, _futures_game_already_played())

    def test_the_bare_key_mutant_would_have_suppressed_it(self, engine):
        """Strawman: proves the fixture discriminates. Without the scope in the
        key, the attached return-leg market is eaten by its group's played game."""
        assert M_ATTACHED_ELSEWHERE not in _offered(
            engine, _the_arm_keyed_on_a_bare_group_id()
        )

    def test_the_unattached_specimen_is_still_suppressed(self, engine):
        assert M_UNATTACHED_NAMED not in _offered(engine, _futures_game_already_played())

    def test_the_whole_answer(self, engine):
        assert _offered(engine, _futures_game_already_played()) == {
            M_ATTACHED_ELSEWHERE,
            M_UNATTACHED_OTHER,
            M_UNGROUPED,
        }


class TestTheCostShape:
    def test_the_scope_rides_the_sibling_key(self):
        sql = _sql(select(FuturesMarket.id).where(_futures_game_already_played()))
        assert (
            "grp_sibling.group_id = CASE WHEN (futures_markets.event_id IS NULL) "
            "THEN futures_markets.group_id END"
        ) in sql

    def test_the_outer_only_quals_are_gone(self):
        """These two placed as anti-join filters are what ran the sibling scan
        for all 1,343 `united` candidates. Either one back means that cost is back."""
        sql = _sql(select(FuturesMarket.id).where(_futures_game_already_played()))
        assert "futures_markets.group_id IS NOT NULL" not in sql
        assert "futures_markets.event_id IS NULL AND" not in sql

    def test_still_one_not_exists_and_no_top_level_or(self):
        sql = _sql(select(FuturesMarket.id).where(_futures_game_already_played()))
        assert sql.count("NOT (EXISTS (SELECT grp_sibling.id") == 1
        assert "futures_markets.event_id IS NOT NULL OR" not in sql


def test_the_mutant_helper_is_not_the_shipped_one():
    """The strawman compiles to the old key, so the pair above is a real A/B."""
    sql = _sql(select(FuturesMarket.id).where(_the_arm_keyed_on_a_bare_group_id()))
    assert "grp_sibling.group_id = futures_markets.group_id" in sql
    assert "CASE WHEN" not in sql
