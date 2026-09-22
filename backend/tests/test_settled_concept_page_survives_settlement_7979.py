"""#7979 — a settled marquee event's concept page must not 404.

Two adapters deleted their own page at the moment the event became a result:

  * `AwardsEventAdapter` selected `status == "open"`, and the 2026 Emmys are 55
    markets of which ZERO are open (measured on production 2026-09-22), so the
    query came back empty and `build_event` returned None.
  * `CyclingEventAdapter` already had a graded rescue for exactly this case
    (#1177), but an early `if not markets: return None` on the OPEN-only list
    ran first, so the rescue was unreachable for a fully-settled race. The
    Vuelta and the Tour de France 2026 are 53 resolved / 0 open.

Both 404s reached readers as an HTTP **200** page reading "Event not found",
which is why no health counter saw them (gotcha #53).

Both tests below are written to FAIL on the pre-fix code:

  * the cycling test feeds the OPEN query an empty result and the GRADED query
    the settled GC market, so the early return is the only thing that can make
    it fail;
  * the awards test inspects the COMPILED statement, because the `mock_db` rig
    ignores the WHERE clause entirely — a behavioural test there would pass
    before and after and prove nothing.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


class _Result:
    """Mimics the slice of the SQLAlchemy Result the adapters actually call:
    `.scalars().unique().all()`."""

    def __init__(self, items):
        self._items = list(items)

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return list(self._items)


def _outcome(name, prob, won=False):
    return SimpleNamespace(
        name=name,
        current_probability=prob,
        is_winner=won,
        current_yes_bid=None,
        current_yes_ask=None,
        resolution_source="api_settlement" if won else None,
        last_updated=datetime(2026, 9, 13, tzinfo=timezone.utc),
    )


def _settled_vuelta_gc_market():
    """The Vuelta's GC winner market as it exists AFTER the race: flipped off
    `open`, carrying the graded crown. `resolution_date` year must equal the
    slug year or the edition guard drops it."""
    return SimpleNamespace(
        id=884401,
        name="Vuelta a Espana Winner",
        status="resolved",
        llm_sport_category="cycling",
        source="kalshi",
        group_id=None,
        external_id="KXVUELTA-26",
        resolution_date=datetime(2026, 9, 13, tzinfo=timezone.utc),
        outcomes=[
            _outcome("Jonas Vingegaard", 1.0, won=True),
            _outcome("Joao Almeida", 0.0),
            _outcome("Tom Pidcock", 0.0),
        ],
    )


class TestASettledGrandTourStillHasAPage:
    """The reader specimen: /event/cycling/vuelta-2026 nine days after the race."""

    async def test_a_fully_settled_race_still_builds_its_concept(self):
        from app.utils.event_cycling import CyclingEventAdapter

        db = AsyncMock()
        # First execute = the OPEN-only scan: a finished race has nothing there.
        # Second execute = the #1177 graded rescue, which holds the crown.
        # Anything after that is the children scan (stages/props), which a settled
        # race has none of — answered empty rather than left to StopIteration.
        calls = {"n": 0}

        async def _execute(stmt, *a, **kw):
            calls["n"] += 1
            if calls["n"] == 2:
                return _Result([_settled_vuelta_gc_market()])
            return _Result([])

        db.execute.side_effect = _execute

        built = await CyclingEventAdapter().build_event("vuelta-2026", db)

        # Pre-fix this is None — the early `if not markets: return None` fired on
        # the empty OPEN list and the graded rescue never ran.
        assert built is not None, "a settled Grand Tour must still render a page"
        assert built["event"]["domain"] == "cycling"
        names = [c["name"] for c in built["primary"]["competitors"]]
        assert "Jonas Vingegaard" in names
        # The rescue query was actually issued — if the open-only scan is ever
        # allowed to short-circuit again this drops to 1 and the test says so.
        assert db.execute.await_count >= 2

    async def test_a_race_with_no_gc_field_at_all_still_404s(self):
        """The control. Removing the early bail must not turn "this race does not
        exist" into an empty page — `winner is None` is the real guard."""
        from app.utils.event_cycling import CyclingEventAdapter

        db = AsyncMock()
        db.execute.side_effect = [_Result([]), _Result([])]

        assert await CyclingEventAdapter().build_event("vuelta-2026", db) is None


class TestTheAwardsQueryAdmitsASettledEdition:
    """The awards adapter runs ONE query and the mock rig ignores its WHERE
    clause, so the only honest assertion is against the statement itself."""

    @staticmethod
    async def _captured_statement(slug):
        from app.utils.event_awards import AwardsEventAdapter

        seen = []

        async def _execute(stmt, *a, **kw):
            seen.append(stmt)
            return _Result([])

        db = AsyncMock()
        db.execute.side_effect = _execute
        await AwardsEventAdapter().build_event(slug, db)
        assert seen, "build_event issued no query"
        return str(seen[0].compile(compile_kwargs={"literal_binds": True}))

    async def test_settled_editions_are_selected(self):
        sql = await self._captured_statement("emmys-2026")
        # The whole defect: 55 resolved Emmy markets and no open ones.
        assert "'resolved'" in sql, (
            "a settled ceremony's markets are `resolved`; excluding them 404s the page"
        )

    async def test_open_editions_are_still_selected(self):
        """A ceremony that has not happened yet must be unaffected — Grammys 2027
        and Oscars 2027 serve today and must keep serving."""
        sql = await self._captured_statement("oscars-2027")
        assert "'open'" in sql

    @pytest.mark.parametrize("state", ["closed", "settled"])
    async def test_the_other_terminal_states_come_too(self, state):
        """Parity with `SoccerEventAdapter`, whose settled World Cup 2026 concept
        is the in-repo proof that this predicate is the right one."""
        sql = await self._captured_statement("emmys-2026")
        assert f"'{state}'" in sql
