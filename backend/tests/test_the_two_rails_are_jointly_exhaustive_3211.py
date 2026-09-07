"""EVERY ROW LANDS ON EXACTLY ONE RAIL — #3211, lane1/134.

═══ WHY THIS SUITE EXISTS ═══

A league page and a team page each split their events into rails: what is on now
or still to come, and what has already happened. The split is only correct if it
is **jointly exhaustive and mutually exclusive** over the states a row can be in
— every row the surface can reach lands on exactly one rail.

Nobody ever asserted that, and the split has now been wrong three times, each
time for a different word, each time repaired by widening one literal and
leaving the structure that produced it:

    #1204     `closed` was on no rail. A settled doubleheader vanished.
    live/056  `suspended` was on no rail. A rain-delayed match vanished.
    #3211     `scheduled` past its own kickoff was on no rail. **171 US Open
              matches** vanished — the whole fortnight, permanently.

The third one is the reason this file is named after the INVARIANT and not after
tennis. A suite called `test_tennis_matches_are_reachable` would have passed all
the way through #1204 and live/056 and would not catch the fourth word either.
What has to be true is a property of the conditions, and it is checkable over
the whole vocabulary at once:

    for every status the ladder can write, at every position on the time axis:
        EXACTLY ONE rail admits it

⚠️ THE FILE NAME SAYS "TWO RAILS" AND THERE ARE NOW THREE. Kept deliberately:
the name is the ISSUE's name and the thing being asserted has not changed — a
rename would orphan every reference to #3211's guard in `event_rails`, both
routes and the ledger, to describe an implementation detail. The third rail
(`unreported`) is #3211's own repair: these rows could not simply join the
settled one, because they outnumber it and sort above it, so one shared cap
starved the Finals out of all eight visible slots. See
`unreported_rail_condition` for the measurement.

═══ WHAT IS DELIBERATELY OUTSIDE THE CLAIM ═══

Two exclusions, both principled, both asserted rather than assumed (see
`TestTheExclusionsAreDeliberate`) so that "exactly one" cannot be made true by
quietly widening what the sweep ignores:

  * `RETIRED_STATUSES` — `merged` and `voided` mean "stop showing this row"
    (lane1/132). Every rail is an allowlist, so these are excluded by
    construction, and landing on NO rail is the correct answer for them.
  * anything older than the lookback. That is a HORIZON, not a gap: it applies
    to a Final exactly as it applies to everything else, and it is what keeps
    the past rails from growing without bound.

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
    recent_or_unreported_condition,
    settled_rail_condition,
    unreported_rail_condition,
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


#: The THIRD axis, added by #3748 — and the invariant over it is a NEGATIVE:
#: no rail reads the scoreline, for any status. See
#: `test_no_rail_reads_the_scoreline_at_all`.
#:
#: The axis is here because a rail once nearly did. #3748's first attempt split
#: `suspended` on whether a score existed, keeping the scored ones under "Recent
#: Results"; CERT-2167 rejected it, because the shared card calls EVERY suspended
#: row result-less and those rows can still consume the capped result slots.
#: "The scored ones do have a result, surely they belong on the results rail" is
#: a natural thing for a future reader to propose, and sweeping this axis is what
#: makes the answer testable rather than remembered.
#:
#: The half-scored cell is not decoration: it is the shape any future
#: score-reading predicate is most likely to get wrong (an `or_` where it meant
#: an `and_`), and it must land on the same rail as both of its neighbours.
SCORE_CELLS = {
    "with a score": (3, 1),
    "with no score": (None, None),
    "with half a score": (3, None),
}


def _event(eid, commence_time, status, score=(None, None)):
    home_score, away_score = score
    return Event(
        id=eid,
        sport_id=S_TENNIS,
        external_id=f"ext-{eid}",
        home_team_name="Dart / Lumsden",
        away_team_name="Bucsa / Melichar-Martinez",
        commence_time=commence_time,
        status=status,
        home_score=home_score,
        away_score=away_score,
    )


def _matrix_rows():
    """One row per (status, time, score) cell, plus the specimen and the two
    retired words. Ids encode the cell so a failure names the cell, not a
    number."""
    rows = []
    eid = 1
    index = {}
    for status in ALL_STATUSES:
        for cell, offset in TIME_CELLS.items():
            for score_cell, score in SCORE_CELLS.items():
                rows.append(_event(eid, NOW + offset, status, score))
                index[eid] = (status, cell, score_cell)
                eid += 1
    for status in sorted(RETIRED_STATUSES):
        rows.append(_event(eid, NOW - timedelta(days=1), status))
        index[eid] = (status, "yesterday", "with no score")
        eid += 1
    rows.append(_event(SPECIMEN_ID, SPECIMEN_COMMENCE, "scheduled"))
    index[SPECIMEN_ID] = ("scheduled", "the specimen", "with no score")
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
    """The league page's THREE rails, by name.

    A dict rather than a tuple because the invariant is "exactly one of these",
    and a failure has to be able to say WHICH — with three rails, `(a, b, c)`
    unpacking at every call site is how a later fourth rail gets bolted on
    without the sweep noticing it.
    """
    return {
        "upcoming": _ids(session, upcoming_rail_condition(NOW)),
        "settled": _ids(session, settled_rail_condition(NOW, lookback=LOOKBACK)),
        "unreported": _ids(session, unreported_rail_condition(NOW, lookback=LOOKBACK)),
    }


def _rails_holding(session, eid):
    """The names of every rail that admits this row. Length 1 is the invariant."""
    return sorted(name for name, ids in _rails(session).items() if eid in ids)


def _in_horizon(status, offset_cell, score_cell="with no score"):
    """Is this cell one the pair is CLAIMING to cover?

    Everything except the two deliberate exclusions. Written as a function so
    the exclusions are one expression the tests below can also assert ON,
    rather than a set literal that could be widened to make a red sweep green.

    The score axis adds NO exclusion and takes the parameter only so the whole
    index entry can be splatted in: every score state of every in-horizon
    (status, time) cell is still claimed. #3748 changed WHICH rail a row lands
    on, never whether it lands on one.
    """
    if status in RETIRED_STATUSES:
        return False
    return offset_cell in TIME_CELLS and score_cell in SCORE_CELLS


class TestTheInvariant:
    """Exactly one rail, for every cell inside the horizon."""

    def test_no_row_lands_on_no_rail(self, corpus):
        session, index = corpus

        orphans = sorted(
            (eid, index[eid])
            for eid in index
            if _in_horizon(*index[eid]) and not _rails_holding(session, eid)
        )
        assert orphans == [], (
            "these (status, time) cells are on NO rail — the row is in the "
            "table, has teams and a market, and is unreachable from its own "
            f"league page permanently: {orphans}"
        )

    def test_no_row_lands_on_two_rails(self, corpus):
        """The other half of "exactly one". A row on two rails is a match that
        is simultaneously about to start and already over — and it is the
        failure mode a careless widening produces, so it is not theoretical."""
        session, index = corpus

        doubled = sorted(
            (eid, index[eid], _rails_holding(session, eid))
            for eid in index
            if len(_rails_holding(session, eid)) > 1
        )
        assert doubled == [], f"these cells are on more than one rail: {doubled}"

    def test_the_specimen_is_reachable_and_is_not_called_a_result(self, corpus):
        """The named row, not just the shape of it. 171 of these were invisible
        on 2026-09-05, and this is one of them.

        It must land on `unreported` SPECIFICALLY — not merely somewhere. On the
        `settled` rail it would be filed among the league's receipts, which is
        the false Final live/048 removed; on `upcoming` it would advertise a
        start time three days gone."""
        session, _ = corpus
        assert _rails_holding(session, SPECIMEN_ID) == ["unreported"]


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
        #
        # Compared on (status, time) only. #3748 gave the index a third axis,
        # but the PRE-FIX conditions being reproduced here never read a
        # scoreline, so the gap they leave cannot depend on one — naming a
        # score cell would assert something about the old code that the old
        # code does not say.
        by_status_and_time = {(status, cell) for status, cell, _ in orphans}
        assert ("scheduled", "just outside the grace") in by_status_and_time
        assert ("scheduled", "yesterday") in by_status_and_time
        assert ("live", "yesterday") in by_status_and_time

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

    def _cells(self, index, statuses, cell_name, score_cells=None):
        """Every id at these (status, time) cells, optionally narrowed to a
        score state. `score_cells=None` means "all of them", which is what a
        control for a status the score axis must not touch wants to say."""
        found = [
            eid
            for eid, (status, cell, score_cell) in index.items()
            if status in statuses
            and cell == cell_name
            and (score_cells is None or score_cell in score_cells)
        ]
        assert found, (
            f"the corpus holds no {statuses} row at {cell_name!r} "
            f"(score {score_cells or 'any'})"
        )
        return found

    def test_a_fixture_an_hour_out_is_still_upcoming_and_only_upcoming(self, corpus):
        session, index = corpus
        for eid in self._cells(index, {"scheduled"}, "an hour from now"):
            assert _rails_holding(session, eid) == ["upcoming"]

    def test_a_final_is_still_settled_and_only_settled(self, corpus):
        session, index = corpus
        for eid in self._cells(index, {"completed", "closed"}, "yesterday"):
            assert _rails_holding(session, eid) == ["settled"]

    def test_every_suspended_match_rides_the_unreported_rail(self, corpus):
        """#3748's ship, and the direction gotcha #43 demands: not merely "off
        the settled rail" but ON the named other rail. A row only asserted
        ABSENT from one rail can satisfy the assertion by vanishing, which is
        the failure this whole file exists to refuse.

        EVERY score state, which is CERT-2167's correction. This test first
        shipped split — scored rows asserted onto `settled`, scoreless onto
        `unreported` — on the reasoning that a scored row has something to show.
        The rail a row sits on has to agree with the words its own card prints,
        and `eventState.hasNoReportedResult` is true for every suspended row, so
        a scored one rendered "No result reported · last score 1-2" under a
        heading reading "Recent Results". Same contradiction the issue was filed
        about, and those rows could still consume capped result slots.

        This does NOT undo live/056, whose ship was that a suspended match is
        reachable AT ALL — it was on no rail and vanished, and the unreported
        rail did not yet exist. It is still on its league page, once, and it
        keeps its `· last score` label because both rails render the same card.
        What WOULD undo live/056 is the row disappearing, and
        `test_no_row_lands_on_no_rail` sweeps every score state for that.
        """
        session, index = corpus
        for score_cell in SCORE_CELLS:
            for eid in self._cells(index, {EVENT_SUSPENDED}, "yesterday", {score_cell}):
                assert _rails_holding(session, eid) == [
                    "unreported"
                ], f"a suspended row {score_cell} is not on the unreported rail"

    def test_no_rail_reads_the_scoreline_at_all(self, corpus):
        """🔴 A ROW'S RAIL IS A FUNCTION OF (status, time) AND NOTHING ELSE.

        The score axis exists in this matrix because a rail once DID read the
        scoreline: #3748's first attempt split `suspended` on it, and CERT-2167
        rejected that — the rail a row sits on has to agree with the words its
        own card prints, and the card calls every suspended row result-less.

        Keeping the axis and asserting the NEGATIVE is what makes that ruling
        durable. "Route the scored ones back to Recent Results" is a natural
        thing for a future reader to propose (they do have a score, after all),
        and it is exactly wrong; this is the test that says so. Swept over the
        whole vocabulary, so it also catches a scoreline predicate ANDed into
        `completed` or `scheduled`, where it would silently strand a Final
        nobody filled the score in for.
        """
        session, index = corpus

        for status in ALL_STATUSES:
            for cell in TIME_CELLS:
                rails = {
                    index[eid][2]: _rails_holding(session, eid)
                    for eid in self._cells(index, {status}, cell)
                }
                assert len(set(map(tuple, rails.values()))) == 1, (
                    f"{status!r} at {cell!r} lands on different rails depending "
                    f"on its scoreline, and no rail may read one: {rails}"
                )


class TestTheExclusionsAreDeliberate:
    """ "Exactly one rail" is only meaningful if the set it ranges over cannot be
    quietly shrunk. These pin what is outside the claim and WHY."""

    def test_a_retired_row_is_on_neither_rail(self, corpus):
        """lane1/132: `merged` and `voided` mean stop showing this row. Both
        rails are allowlists, so neither admits them — by construction, which is
        the point. If one ever does, the retirement is not a retirement."""
        session, index = corpus

        retired = [
            eid for eid, (status, _, _) in index.items() if status in RETIRED_STATUSES
        ]
        assert retired, "the corpus holds no retired row, so this proves nothing"
        for eid in retired:
            assert _rails_holding(session, eid) == []

    def test_beyond_the_lookback_is_a_horizon_not_a_gap(self, corpus):
        """A Final ages off; so does everything else, at the same bound. The
        distinction from the #3211 gap is that this one MOVES a row out of view
        as time passes rather than never showing it at all."""
        session, _ = corpus

        old = _event(990_001, NOW - LOOKBACK - timedelta(days=1), "completed")
        old_scheduled = _event(990_002, NOW - LOOKBACK - timedelta(days=1), "scheduled")
        session.add_all([old, old_scheduled])
        session.flush()
        try:
            assert _rails_holding(session, 990_001) == []
            assert _rails_holding(session, 990_002) == []
        finally:
            session.delete(old)
            session.delete(old_scheduled)
            session.flush()


class TestThePredicateAndTheSQLAgree:
    """The Python predicate and the emitted SQL are two expressions of one rule,
    and the frontend renders off the predicate's twin while the rails select off
    the SQL. If they disagree, a row reaches a card that then prints a start
    time for it — the exact fall-through this repair refuses.

    🔴 SCOPE, after #3748. `started_without_result` answers a question about
    `scheduled` rows and ONLY about them (the test at the foot of this class is
    what says so), so it is the twin of the unreported rail's `scheduled` ARM,
    not of the whole rail. The rail's second arm — a scoreless `suspended`
    row — has no Python twin here because it needs none: the frontend's
    `eventState.hasNoReportedResult` is already true for every `suspended` row,
    score or no score, so no suspended row can reach a card that prints a start
    time for it. The two expressions cannot drift on that arm because only one
    of them exists.
    """

    @pytest.mark.parametrize("cell,offset", sorted(TIME_CELLS.items()))
    def test_started_without_result_matches_the_unreported_rail(
        self, corpus, cell, offset
    ):
        session, index = corpus
        unreported = _rails(session)["unreported"]

        eid = next(
            e
            for e, (status, c, score_cell) in index.items()
            if status == "scheduled" and c == cell and score_cell == "with no score"
        )
        by_predicate = started_without_result("scheduled", NOW + offset, NOW)
        by_sql = eid in unreported
        assert by_predicate == by_sql, (
            f"`started_without_result` and the unreported rail disagree at "
            f"{cell!r}: predicate={by_predicate}, sql={by_sql}"
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
    """The league page and the team page differ in their lookback and in whether
    they SPLIT the past into two rails. Both differences are decisions the pages
    are entitled to make; anything else diverging is how the rails got written
    twice in the first place.
    """

    def test_the_lookback_is_the_only_thing_the_horizon_changes(self, corpus):
        session, _ = corpus

        league = _ids(session, settled_rail_condition(NOW, lookback=timedelta(days=14)))
        team = _ids(session, settled_rail_condition(NOW, lookback=timedelta(days=30)))

        assert league <= team, (
            "the 30-day team rail does not contain the 14-day league rail — the "
            "lookback has stopped being the only thing that differs"
        )

    def test_the_team_page_sees_exactly_what_the_league_page_sees_split(self, corpus):
        """🔴 THE ASYMMETRY IS A LAYOUT DECISION, NOT A COVERAGE ONE.

        The league page renders the past as two rails because one shared cap
        starved the Finals out of all eight slots; the team page renders it as
        one because its cap spans a single team's own schedule, where the two
        populations are comparable and nothing starves.

        That difference must be about PRESENTATION only. If the combined
        condition ever admitted a different set of rows than the two split ones
        together, one of the two pages would be hiding something — which is the
        defect this whole file is about, re-created by the repair for it."""
        session, _ = corpus

        combined = _ids(session, recent_or_unreported_condition(NOW, lookback=LOOKBACK))
        split = _ids(session, settled_rail_condition(NOW, lookback=LOOKBACK)) | _ids(
            session, unreported_rail_condition(NOW, lookback=LOOKBACK)
        )

        assert combined == split
        assert combined, "the corpus admits nothing at all, so this proves nothing"

    def test_the_two_split_rails_do_not_overlap(self, corpus):
        """Otherwise the team page's single list would render a row twice."""
        session, _ = corpus

        settled = _ids(session, settled_rail_condition(NOW, lookback=LOOKBACK))
        unreported = _ids(session, unreported_rail_condition(NOW, lookback=LOOKBACK))
        assert settled & unreported == set()

    def test_the_upcoming_rail_takes_no_lookback_at_all(self, corpus):
        """It is bounded by status, not by a window: a `live` row is live for as
        long as it is live, and a `scheduled` one is in the future or inside the
        grace. Passing it a horizon would be inventing a fourth boundary."""
        import inspect

        sig = inspect.signature(upcoming_rail_condition)
        assert list(sig.parameters) == ["now"]
