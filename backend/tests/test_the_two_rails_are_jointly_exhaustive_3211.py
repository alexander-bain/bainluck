"""EVERY ROW LANDS ON EXACTLY ONE RAIL — #3211, lane1/134.

═══ WHY THIS SUITE EXISTS ═══

A league page and a team page each render one PAIR of lists: what is on now or
still to come, and what has already happened. The pair is only correct if it is
**jointly exhaustive and mutually exclusive** over the states a row can be in —
every row the surface can reach satisfies exactly one side.

Nobody ever asserted that, and the pair has now been wrong three times, each
time for a different word, each time repaired by widening one literal and
leaving the structure that produced it:

    #1204     `closed` was in neither rail. A settled doubleheader vanished.
    live/056  `suspended` was in neither. A rain-delayed match vanished.
    #3211     `scheduled` past its own kickoff is in neither. **171 US Open
              matches** vanished — the whole fortnight, permanently.

The third one is the reason this file is named after the INVARIANT and not after
tennis. A suite called `test_tennis_matches_are_reachable` would have passed all
the way through #1204 and live/056 and would not catch the fourth word either.
What has to be true is a property of the two conditions, and it is checkable
over the whole vocabulary at once:

    for every status the ladder can write, at every position on the time axis:
        exactly one of {upcoming_rail_condition, recent_rail_condition} admits it

═══ WHAT IS DELIBERATELY OUTSIDE THE CLAIM ═══

Two exclusions, both principled, both asserted rather than assumed (see
`TestTheExclusionsAreDeliberate`) so that "exactly one" cannot be made true by
quietly widening what the sweep ignores:

  * `RETIRED_STATUSES` — `merged` and `voided` mean "stop showing this row"
    (lane1/132). Both rails are allowlists, so these are excluded by
    construction, and landing on NEITHER rail is the correct answer for them.
  * anything older than the recent rail's lookback. That is a HORIZON, not a
    gap: it applies to a Final exactly as it applies to everything else, and it
    is what keeps the recent rail from growing without bound.

═══ RED-FIRST ═══

`TestTheDefectReproduces` rebuilds the PRE-#3211 conditions — the literals that
were in `league_futures` and `teams` on master — and runs the same sweep over
the same corpus. It must find the gap. Without it every assertion below could be
passing over a matrix the old code also satisfied, and the suite would certify
nothing. It also pins the SIZE of the gap at the specimen row, so a future edit
that shrinks the fix cannot leave this file green.

Nothing here re-implements a condition and asserts on its re-implementation —
that is what let live/056 through, and the one hand-written copy in this file is
the pre-fix arm, where being a copy is the entire point.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import and_, create_engine, or_, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

# SQLite cannot render Postgres-native column types. DDL shims for the sqlite
# dialect ONLY — production is Postgres and never reaches them. Same shims, and
# the same reason, as `test_suspended_is_reachable_cert_786`: without them
# `events` cannot be created and this module degrades to shape-only coverage,
# which for an "exactly one rail" claim would be no coverage at all.


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models import Event, Sport  # noqa: E402
from app.models.models import Base  # noqa: E402
from app.utils.event_completion import (  # noqa: E402
    EVENT_SUSPENDED,
    RECENT_RAIL_STATUSES,
    RETIRED_STATUSES,
    UPCOMING_GRACE,
    started_without_result,
)
from app.utils.event_rails import (  # noqa: E402
    recent_rail_condition,
    upcoming_rail_condition,
)

NOW = datetime(2026, 9, 5, 13, 0, 0, tzinfo=timezone.utc)
LOOKBACK = timedelta(days=14)

S_TENNIS = 1

#: Every word `Event.status` can hold that a reader-facing surface may meet.
#: Derived from the vocabulary rather than re-listed, so a sixth state added to
#: `event_completion` arrives in this sweep without anybody remembering to add
#: it — which is the failure mode the whole file is about.
LIVE_LIKE = ["live", "scheduled"]
ALL_STATUSES = sorted({*LIVE_LIKE, *RECENT_RAIL_STATUSES})

#: Positions on the time axis, named for what they MEAN rather than by number,
#: and every one of them derived from a bound the production code actually
#: spends. A cell at "now - 90 minutes" would be testing a number this suite
#: invented; a cell at "just inside the grace" is testing the boundary the rails
#: split on. Offsets from a fixed anchor, never a branch on the clock
#: (gotcha #44).
TIME_CELLS = {
    "well in the future": timedelta(days=3),
    "an hour from now": timedelta(hours=1),
    "just inside the grace": -(UPCOMING_GRACE - timedelta(minutes=1)),
    "just outside the grace": -(UPCOMING_GRACE + timedelta(minutes=1)),
    "yesterday": timedelta(days=-1),
    "the far edge of the lookback": -(LOOKBACK - timedelta(hours=1)),
}

#: The specimen: Bucsa/Melichar-Martinez v Dart/Lumsden and 170 others. A US
#: Open row stamped at exactly midnight UTC by a Kalshi ticker (gotcha #14),
#: still `scheduled` days later because tennis has no ESPN anchor to settle it
#: (#2700), and therefore on no rail at all until this change.
SPECIMEN_ID = 15304868
SPECIMEN_COMMENCE = datetime(2026, 9, 2, 0, 0, 0, tzinfo=timezone.utc)


def _event(eid, commence_time, status):
    return Event(
        id=eid,
        sport_id=S_TENNIS,
        external_id=f"ext-{eid}",
        home_team_name="Dart / Lumsden",
        away_team_name="Bucsa / Melichar-Martinez",
        commence_time=commence_time,
        status=status,
    )


def _matrix_rows():
    """One row per (status, time) cell, plus the specimen and the two retired
    words. Ids encode the cell so a failure names the cell, not a number."""
    rows = []
    eid = 1
    index = {}
    for status in ALL_STATUSES:
        for cell, offset in TIME_CELLS.items():
            rows.append(_event(eid, NOW + offset, status))
            index[eid] = (status, cell)
            eid += 1
    for status in sorted(RETIRED_STATUSES):
        rows.append(_event(eid, NOW - timedelta(days=1), status))
        index[eid] = (status, "yesterday")
        eid += 1
    rows.append(_event(SPECIMEN_ID, SPECIMEN_COMMENCE, "scheduled"))
    index[SPECIMEN_ID] = ("scheduled", "the specimen")
    return rows, index


@pytest.fixture(scope="module")
def corpus():
    """A real engine executing the real conditions. A hand-evaluated predicate
    would be a re-implementation, and this suite exists because of one."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    rows, index = _matrix_rows()
    with Session(engine) as session:
        session.add(Sport(id=S_TENNIS, key="tennis_wta", name="WTA"))
        session.add_all(rows)
        session.commit()
        yield session, index


def _ids(session, condition):
    return set(session.execute(select(Event.id).where(condition)).scalars().all())


def _rails(session):
    return (
        _ids(session, upcoming_rail_condition(NOW)),
        _ids(session, recent_rail_condition(NOW, lookback=LOOKBACK)),
    )


def _in_horizon(status, offset_cell):
    """Is this cell one the pair is CLAIMING to cover?

    Everything except the two deliberate exclusions. Written as a function so
    the exclusions are one expression the tests below can also assert ON,
    rather than a set literal that could be widened to make a red sweep green.
    """
    if status in RETIRED_STATUSES:
        return False
    return offset_cell in TIME_CELLS


class TestTheInvariant:
    """Exactly one rail, for every cell inside the horizon."""

    def test_no_row_lands_on_neither_rail(self, corpus):
        session, index = corpus
        upcoming, recent = _rails(session)

        orphans = sorted(
            (eid, index[eid])
            for eid in index
            if _in_horizon(*index[eid]) and eid not in upcoming and eid not in recent
        )
        assert orphans == [], (
            "these (status, time) cells are on NO rail — the row is in the "
            "table, has teams and a market, and is unreachable from its own "
            f"league page permanently: {orphans}"
        )

    def test_no_row_lands_on_both_rails(self, corpus):
        """The other half of "exactly one". A row on both is a match that is
        simultaneously about to start and already over — and it is the failure
        mode a careless widening produces, so it is not a theoretical case."""
        session, index = corpus
        upcoming, recent = _rails(session)

        both = sorted((eid, index[eid]) for eid in upcoming & recent)
        assert both == [], f"these cells are on BOTH rails: {both}"

    def test_the_specimen_is_reachable(self, corpus):
        """The named row, not just the shape of it. 171 of these were invisible
        on 2026-09-05, and this is one of them."""
        session, _ = corpus
        upcoming, recent = _rails(session)

        assert SPECIMEN_ID in recent, (
            "the US Open specimen is not on the recent rail — this is the "
            "defect, and the matrix above should have caught it too"
        )
        assert SPECIMEN_ID not in upcoming, (
            "a match three days past its kickoff is not UPCOMING; putting it "
            "there is the false start time this repair exists to refuse"
        )


class TestTheDefectReproduces:
    """🔴 RED-FIRST. The pre-#3211 conditions, hand-written, over the same rows.

    This is the one place in the file where a copy is the artefact under test
    rather than a stand-in for the real thing.
    """

    @staticmethod
    def _pre_fix_upcoming():
        return and_(
            Event.status.in_(["live", "scheduled"]),
            Event.commence_time >= NOW - timedelta(hours=2),
        )

    @staticmethod
    def _pre_fix_recent():
        return and_(
            Event.status.in_(RECENT_RAIL_STATUSES),
            Event.commence_time >= NOW - LOOKBACK,
        )

    def test_the_old_pair_left_a_gap(self, corpus):
        session, index = corpus
        upcoming = _ids(session, self._pre_fix_upcoming())
        recent = _ids(session, self._pre_fix_recent())

        orphans = {
            index[eid]
            for eid in index
            if _in_horizon(*index[eid]) and eid not in upcoming and eid not in recent
        }
        assert orphans, (
            "the pre-fix conditions covered the whole matrix, so the corpus "
            "cannot demonstrate the defect and every green above is free"
        )
        # Named, not just counted: a gap of the wrong SHAPE would satisfy a
        # bare `assert orphans` while the real defect went unreproduced.
        assert ("scheduled", "just outside the grace") in orphans
        assert ("scheduled", "yesterday") in orphans
        assert ("live", "yesterday") in orphans

    def test_the_old_pair_lost_the_specimen(self, corpus):
        session, _ = corpus
        upcoming = _ids(session, self._pre_fix_upcoming())
        recent = _ids(session, self._pre_fix_recent())

        assert SPECIMEN_ID not in upcoming | recent, (
            "the specimen was reachable BEFORE the fix, so it is the wrong "
            "specimen and proves nothing about #3211"
        )


class TestTheHealthyDirectionIsUntouched:
    """Controls. Each routes only through behaviour that predates #3211, so a
    control going red means the change was too wide — not that it is absent."""

    def test_a_fixture_tomorrow_is_still_upcoming_and_only_upcoming(self, corpus):
        session, index = corpus
        upcoming, recent = _rails(session)

        cells = [
            eid
            for eid, (status, cell) in index.items()
            if status == "scheduled" and cell == "an hour from now"
        ]
        assert cells
        for eid in cells:
            assert eid in upcoming and eid not in recent

    def test_a_final_is_still_recent_and_only_recent(self, corpus):
        session, index = corpus
        upcoming, recent = _rails(session)

        cells = [
            eid
            for eid, (status, cell) in index.items()
            if status in ("completed", "closed") and cell == "yesterday"
        ]
        assert cells
        for eid in cells:
            assert eid in recent and eid not in upcoming

    def test_a_suspended_match_still_rides_the_recent_rail(self, corpus):
        """live/056's ship. It must not have been moved by this one."""
        session, index = corpus
        upcoming, recent = _rails(session)

        cells = [
            eid
            for eid, (status, cell) in index.items()
            if status == EVENT_SUSPENDED and cell == "yesterday"
        ]
        assert cells
        for eid in cells:
            assert eid in recent and eid not in upcoming


class TestTheExclusionsAreDeliberate:
    """ "Exactly one rail" is only meaningful if the set it ranges over cannot be
    quietly shrunk. These pin what is outside the claim and WHY."""

    def test_a_retired_row_is_on_neither_rail(self, corpus):
        """lane1/132: `merged` and `voided` mean stop showing this row. Both
        rails are allowlists, so neither admits them — by construction, which is
        the point. If one ever does, the retirement is not a retirement."""
        session, index = corpus
        upcoming, recent = _rails(session)

        retired = [
            eid for eid, (status, _) in index.items() if status in RETIRED_STATUSES
        ]
        assert retired, "the corpus holds no retired row, so this proves nothing"
        for eid in retired:
            assert eid not in upcoming and eid not in recent

    def test_beyond_the_lookback_is_a_horizon_not_a_gap(self, corpus):
        """A Final ages off; so does everything else, at the same bound. The
        distinction from the #3211 gap is that this one MOVES a row out of view
        as time passes rather than never showing it at all."""
        session, _ = corpus
        upcoming, recent = _rails(session)

        old = _event(990_001, NOW - LOOKBACK - timedelta(days=1), "completed")
        old_scheduled = _event(990_002, NOW - LOOKBACK - timedelta(days=1), "scheduled")
        session.add_all([old, old_scheduled])
        session.flush()
        try:
            upcoming, recent = _rails(session)
            assert 990_001 not in upcoming | recent
            assert 990_002 not in upcoming | recent
        finally:
            session.delete(old)
            session.delete(old_scheduled)
            session.flush()


class TestThePredicateAndTheSQLAgree:
    """The Python predicate and the emitted SQL are two expressions of one rule,
    and the frontend renders off the predicate's twin while the rails select off
    the SQL. If they disagree, a row reaches a card that then prints a start
    time for it — the exact fall-through this repair refuses.
    """

    @pytest.mark.parametrize("cell,offset", sorted(TIME_CELLS.items()))
    def test_started_without_result_matches_the_recent_rail_arm(
        self, corpus, cell, offset
    ):
        session, index = corpus
        _, recent = _rails(session)

        eid = next(
            e for e, (status, c) in index.items() if status == "scheduled" and c == cell
        )
        by_predicate = started_without_result("scheduled", NOW + offset, NOW)
        by_sql = eid in recent
        assert by_predicate == by_sql, (
            f"`started_without_result` and the recent rail disagree at {cell!r}: "
            f"predicate={by_predicate}, sql={by_sql}"
        )

    def test_the_predicate_refuses_every_other_status(self):
        """It answers a question about `scheduled` rows only. A `live` row hours
        past its start is handled by the upcoming rail keeping it, not by this
        predicate calling it result-less."""
        for status in ALL_STATUSES:
            if status == "scheduled":
                continue
            assert not started_without_result(
                status, NOW - timedelta(days=1), NOW
            ), f"{status} should not be reported as a result-less fixture"

    def test_an_unplaceable_row_is_left_alone(self):
        """A row we cannot place on the clock is one we have no standing to move
        off the schedule — the same rule `is_retired_event_status` applies to a
        word it does not recognise."""
        assert not started_without_result("scheduled", None, NOW)
        assert not started_without_result("scheduled", NOW - timedelta(days=1), None)


class TestBothSurfacesSpendOneDefinition:
    """The league page and the team page differ ONLY in their lookback. That is
    the difference each page is entitled to make; anything else diverging is how
    the pair got written twice in the first place.
    """

    def test_the_two_lookbacks_are_the_only_difference(self, corpus):
        session, _ = corpus

        league = _ids(session, recent_rail_condition(NOW, lookback=timedelta(days=14)))
        team = _ids(session, recent_rail_condition(NOW, lookback=timedelta(days=30)))

        assert league <= team, (
            "the 30-day team rail does not contain the 14-day league rail — the "
            "lookback has stopped being the only thing that differs"
        )

    def test_the_upcoming_rail_takes_no_lookback_at_all(self, corpus):
        """It is bounded by status, not by a window: a `live` row is live for as
        long as it is live, and a `scheduled` one is in the future or inside the
        grace. Passing it a horizon would be inventing a fourth boundary."""
        import inspect

        sig = inspect.signature(upcoming_rail_condition)
        assert list(sig.parameters) == ["now"]
