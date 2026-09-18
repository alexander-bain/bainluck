"""#5821 — folding two rows into one stops costing the reader the way in.

## The defect, measured on production 2026-09-18 15:5xZ

`not_a_proven_duplicate` is SCOPE, and the comment at its search call site says
exactly what it does: it *"can only ever REMOVE a row that the recall arms
already reached"*. That is true, and it is the bug. When the removed row was the
ONLY row the reader's text reached, suppressing the duplicate card does not
leave one card — it leaves NOTHING, which is strictly worse than the two-card
defect it is there to fix.

The Atlético–Real Madrid derby of 2026-09-20, three queries, one pass:

    q=Atletico Madrid       1 event    ONLY duplicate 15307707 · teams 0
    q=Atlético Madrid      10 events   canonical 15312071 first · teams 1
    q=Real Madrid          16 events   canonical 15312071 first · teams 1

The canonical is stored **accented** and search does no diacritic folding, so
the unaccented duplicate was a plain-keyboard reader's ONLY route to that derby.
Tagging it — which is right, the two rows are one game — takes that reader from
the wrong page to an empty one. The tag is correct and the fold is correct; what
was missing is the walk from the row we decline to print to the row we print
instead.

NEITHER EXISTING RESCUE COVERS IT, which is why the bridge is a third arm rather
than a tweak to one of them, and both exclusions were measured rather than
reasoned about:

* the resolved-team rescue needs the query to match `Team.name`, and the team row
  is accented too — the same pass returned `teams n=0`;
* the trigram "did you mean" fallback is `len(terms) == 1`, and this query is two.

## Why the bridge is allowed to be narrow

Only on the empty rail, for the reason the resolved-team arm states one screen
down: on every query whose rail is not empty the compiled SQL is unchanged and
no extra statement is issued. That matters more here, because
`is_a_proven_duplicate` is a prefix LIKE that `ix_events_event_tags` cannot
serve — it is affordable strictly because the reader's own recall arm leads it.

The KNOWN LIMIT is stated in the route and measured, not assumed: a non-empty
rail can still hide a bridged canonical. Of the 617 tagged rows on production
2026-09-18, 34 carry an ASCII duplicate against an accented canonical, of which
**3 rows / 1 canonical** are upcoming. The general repair is diacritic-insensitive
recall (#6977), which removes the asymmetry at its source instead of bridging
around it.

## What is pinned, and why in both directions

`TestThePredicatesPartition` is the durable one. The bridge's whole safety
argument is that `is_a_proven_duplicate` is the EXACT complement of its sibling —
if the pair ever both-admits or both-refuses a row, the surface either prints the
duplicate card again or loses a row entirely, and every behavioural test below
would still pass. So the partition is asserted over a table containing every
tag shape this codebase writes, not over the one tagged row.

The refusal direction is asserted as hard as the bridge (gotcha #43): a bridge
that fires on an UNTAGGED match would resurrect rows the surface deliberately
declined, which is the mirror-image defect.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models.models import Base, Event, Sport  # noqa: E402
from app.services.anchor_channel import DUPLICATE_TAG_PREFIX, duplicate_tag  # noqa: E402
from app.utils.proven_duplicates import (  # noqa: E402
    is_a_proven_duplicate,
    not_a_proven_duplicate,
)

# ── The production specimen, to the id ──────────────────────────────────────
#
# The ESPN-anchored canonical carries the accented club name and the crests; the
# Kalshi-minted duplicate carries the plain-ASCII spelling and, on the day, the
# only moneyline. Both served HTTP 200 under their own id — neither folded.
CANONICAL_ID = 15312071
GHOST_ID = 15307707
CANONICAL_HOME = "Atlético Madrid"
CANONICAL_AWAY = "Real Madrid"
GHOST_HOME = "Atletico"
GHOST_AWAY = "Real Madrid"
KICKOFF = datetime(2026, 9, 20, 14, 15, tzinfo=timezone.utc)

#: The two spellings the ship is about. The first is the one that regressed.
UNACCENTED_QUERY = "atletico madrid"
ACCENTED_QUERY = "atlético madrid"
PARTNER_QUERY = "real madrid"

S_SOCCER = 7

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

# Tag shapes that must NOT be read as a duplicate marker. `provenance:` is a
# shared prefix, so a predicate keyed on it rather than on the full
# `duplicate-of:` element would swallow all three.
INNOCENT_TAG_SHAPES = [
    None,
    [],
    ["provenance:source:odds_api"],
    ["provenance:unanchored", "provenance:source:statpal"],
    ["league:la_liga", "sport:soccer", "status:scheduled"],
]


def _row(event_id, *, home, away, event_tags=None, status="scheduled", offset_min=0):
    return Event(
        id=event_id,
        sport_id=S_SOCCER,
        home_team_name=home,
        away_team_name=away,
        commence_time=KICKOFF + timedelta(minutes=offset_min),
        status=status,
        event_tags=event_tags,
    )


# ════════════════════════════════════════════════════════════════════════════
# Part A — the partition. Executed, and it runs everywhere.
# ════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def engine():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Sport(id=S_SOCCER, key="soccer_spain_la_liga", name="La Liga"))
        s.add(_row(CANONICAL_ID, home=CANONICAL_HOME, away=CANONICAL_AWAY))
        s.add(
            _row(
                GHOST_ID,
                home=GHOST_HOME,
                away=GHOST_AWAY,
                event_tags=[duplicate_tag(CANONICAL_ID)],
                offset_min=1,
            )
        )
        for i, shape in enumerate(INNOCENT_TAG_SHAPES, start=1):
            s.add(_row(i, home=f"Club {i}", away=f"Rival {i}", event_tags=shape))
        s.commit()
    return eng


def _ids_where(eng, predicate):
    with Session(eng) as s:
        return sorted(s.execute(select(Event.id).where(predicate)).scalars().all())


class TestThePredicatesPartition:
    """The bridge's safety argument, and the one that must never silently rot.

    Every behavioural assertion below would still pass if these two predicates
    drifted into overlapping or leaving a gap — the surface would simply print
    the duplicate card again, or lose a row, with no test to say so.
    """

    def test_the_two_predicates_admit_every_row_exactly_once(self, engine):
        admitted = _ids_where(engine, not_a_proven_duplicate())
        duplicates = _ids_where(engine, is_a_proven_duplicate())

        with Session(engine) as s:
            everything = sorted(s.execute(select(Event.id)).scalars().all())

        assert sorted(admitted + duplicates) == everything, "the pair leaves a gap"
        assert set(admitted).isdisjoint(duplicates), "the pair double-counts a row"

    def test_the_duplicate_side_is_exactly_the_tagged_row(self, engine):
        assert _ids_where(engine, is_a_proven_duplicate()) == [GHOST_ID]

    def test_no_innocent_tag_shape_reads_as_a_duplicate(self, engine):
        """THE TRAP. `provenance:` is a shared prefix and `event_tags` is
        nullable — a predicate keyed on the wrong half would either claim every
        provenance-tagged row as a duplicate, or (the sibling's own scar) admit
        nothing at all because `NULL LIKE x` is NULL rather than TRUE."""
        duplicates = _ids_where(engine, is_a_proven_duplicate())
        innocents = list(range(1, len(INNOCENT_TAG_SHAPES) + 1))
        assert set(duplicates).isdisjoint(innocents)

    def test_the_duplicate_predicate_names_the_canonical_tag_prefix(self):
        """Read against the constant, so renaming the tag cannot disarm the
        bridge while leaving every row-level test above green."""
        compiled = str(
            select(Event.id)
            .where(is_a_proven_duplicate())
            .compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        assert DUPLICATE_TAG_PREFIX in compiled
        assert "IS NOT NULL" in compiled


# ════════════════════════════════════════════════════════════════════════════
# Part B — the walk itself, executed against a real engine.
#
# MOVED to `tests/integration/test_search_proven_duplicate_bridge_pg_5821.py`,
# and do not rebuild it here. As a `skipif`-gated class in this file it SKIPPED
# on every run — nothing in CI set `SEARCH_TEST_DATABASE_URL` for this path, and
# pytest exits 0 on a skip, so it read exactly like a passing gate. Armed by hand
# it could not even construct its fixture. It now runs as its own step in the
# `search-recall` job, which fails the build if the case skips.
# ════════════════════════════════════════════════════════════════════════════


# ════════════════════════════════════════════════════════════════════════════
# Part C — carriage. The walk is worthless if the route does not take it.
# ════════════════════════════════════════════════════════════════════════════


class TestTheRouteCarriesTheBridge:
    """Part A proves the walk is correct; this proves `/api/events/search` makes
    it, and makes it in the right ORDER. Both rescues below it are gated on the
    same empty rail, so a bridge placed after them would be dead on every query
    they happen to fill — including with a spelling neighbour, which is the
    outcome #4809 spent a ship avoiding."""

    @staticmethod
    def _source():
        import inspect

        from app.routes import events as events_module

        return inspect.getsource(events_module.search_events)

    def test_the_search_route_calls_the_bridge(self):
        assert "bridged_canonical_ids(" in self._source()

    def test_the_bridge_runs_before_both_rescues(self):
        src = self._source()
        bridge = src.index("bridged_canonical_ids(")
        fuzzy = src.index("Fuzzy fallback: re-query with trigram similarity")
        resolved_team = src.index("_resolved_teams: list[tuple[str, str]] = []")
        assert bridge < fuzzy, "a filled rail is never then 'corrected'"
        assert bridge < resolved_team, "the proven finding outranks the guess"

    def test_the_bridge_is_confined_to_the_empty_rail(self):
        """The latency contract of this arm. `is_a_proven_duplicate` is an
        unindexable prefix LIKE; off the empty rail it would be paid by every
        search that runs."""
        src = self._source()
        bridge = src.index("bridged_canonical_ids(")
        guard = src.rindex("if total_count == 0", 0, bridge)
        between = src[guard:bridge]
        assert "not degraded" in between
        assert "not sport_alias_keys" in between

    def test_the_bridged_rows_are_scoped_like_every_other_result(self):
        """The bridge may only offer a row search was already willing to print —
        so the canonical passes through `event_scope_conditions`, not around it."""
        src = self._source()
        bridge = src.index("bridged_canonical_ids(")
        tail = src[bridge : bridge + 2000]
        assert "_bridge_conditions" in tail
        assert "*event_scope_conditions" in tail
