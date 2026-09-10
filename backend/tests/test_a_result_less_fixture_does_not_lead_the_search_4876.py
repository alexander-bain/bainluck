"""#4876 — search leads with a game that never happened. D107, ship 7 (#4461).

THE SPECIMENS, `GET /api/events/search` read from production 2026-09-10 at
19:15Z, `results` in exactly the order they were served:

    q=red sox   1  scheduled  Toronto Blue Jays v Boston Red Sox    2026-08-11
                2  scheduled  Toronto Blue Jays v Boston Red Sox    2026-08-12
                3  scheduled  Pittsburgh Pirates v Boston Red Sox   2026-08-15
                4  scheduled  Lehigh Valley IronPigs v Worcester    2026-09-10
                5  scheduled  Boston Red Sox v Kansas City Royals   2026-09-11

    q=alcaraz  10  scheduled  Wu v Alcaraz                          2026-09-04
               11  completed  Ben Shelton v Carlos Alcaraz          2026-09-09
               12  completed  Tommy Paul v Carlos Alcaraz           2026-09-06
               13  completed  Wu Yibing v Carlos Alcaraz            2026-09-04
               14  completed  Jaime Faria v Carlos Alcaraz          2026-09-03
               15  closed     Roman Safiullin v Carlos Alcaraz      2026-08-30

`red sox` spends its top three slots on August. `alcaraz` leads with a Sep-4 row
that no source ever reported an ending for, above the Sep-9 match that is
genuinely the last one played. D107 asks for the entity, then its NEXT-or-LAST
game — next before last when one exists — and neither query delivers it.

🔴 IT IS NOT A NEAR-MISS AND IT IS NOT RELEVANCE. Every row above is the right
entity; `_search_rank` did its job. The clause that failed is the STATUS tier:
`live_scheduled_settled_order` scored a `scheduled` row into the upcoming tier
with no time bound, and every caller pairs that tier with `commence_time ASC`,
so the staler the row the higher it sorted. The oldest wreck in the table led.

🔴 THE CARD ALREADY DISAGREED WITH THE POSITION. `EventCard.tsx:272` renders
this exact class through `eventState.hasNoReportedResult`, so all three August
rows print "No result reported" — at the top of a list whose first slot means
"next". This is the position agreeing with the label; no label moves.

The clauses are executed as real SQL rather than asserted on their source, for
the reason `test_live_before_kickoff_q438.py` gives: the whole class of bug here
is an expression that looks right and sorts wrong.
"""

from datetime import datetime, timedelta, timezone
from itertools import product

import pytest
from sqlalchemy import case

from app.models.models import Event
from app.utils.event_completion import (
    EVENT_SUSPENDED,
    UPCOMING_GRACE,
    started_without_result,
)
from app.utils.event_rails import (
    live_scheduled_settled_order,
    started_without_result_rows,
)

#: The moment the two specimens above were read. Fixed, never derived from the
#: clock (gotcha #44) — every fixture time is written as a literal beside it, so
#: the grace boundary is exercised rather than assumed.
NOW = datetime(2026, 9, 10, 19, 15, tzinfo=timezone.utc)

#: Both specimens are tennis/baseball rows on a LIT sport, so the StatPal anchor
#: would count as an observation (#4075). Nothing here carries one; the column
#: exists because `never_observed_columns()` reads it.
LIT_SPORT_ID = 1
SPORT_KEYS = {LIT_SPORT_ID: "tennis_atp"}


def _create_schema(md):
    """Only what this ORDER BY touches. The models' JSONB columns cannot be
    created under SQLite; the EXPRESSION under test is the shipping one and
    renders `events.<column>` by name, so it binds here unchanged."""
    from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table

    assert isinstance(md, MetaData)
    events = Table(
        "events",
        md,
        Column("id", Integer, primary_key=True),
        Column("status", String),
        Column("commence_time", DateTime(timezone=True)),
        Column("sport_id", Integer),
        Column("home_score", Integer),
        Column("away_score", Integer),
        Column("period", String),
        Column("espn_id", String),
        Column("statpal_fixture_id", String),
    )
    sports = Table(
        "sports",
        md,
        Column("id", Integer, primary_key=True),
        Column("key", String),
    )
    return events, sports


def _search_secondary_terms():
    """The two commence terms `search_events` pairs its status tier with, from
    `routes/events.py` (the `case(...).asc()` / `case(...).desc()` pair under
    the ORDER BY).

    They are REPLICATED rather than imported because they are written inline in
    the route body. That is load-bearing for the `alcaraz` claim and not a
    detail: the settled tier sorts DESC, so "the last real match leads" is only
    true under this pair. `TestTheTierValuesDirectly` states the same ship
    without them, so a future extraction that changes these cannot make the
    guard vacuous.
    """
    return (
        case(
            (Event.status.in_(["live", "scheduled"]), Event.commence_time),
            else_=None,
        )
        .asc()
        .nulls_last(),
        case(
            (
                Event.status.in_(["completed", "closed", EVENT_SUSPENDED]),
                Event.commence_time,
            ),
            else_=None,
        )
        .desc()
        .nulls_last(),
    )


def _order_under(clause, rows):
    """Execute `clause` against a real `events` table, under search's own
    secondary ordering, and return the ids in served order."""
    from sqlalchemy import MetaData, create_engine, insert, select

    md = MetaData()
    events, sports = _create_schema(md)
    engine = create_engine("sqlite://")
    md.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            insert(sports),
            [{"id": sid, "key": key} for sid, key in SPORT_KEYS.items()],
        )
        conn.execute(insert(events), list(rows))
        stmt = select(Event.id).order_by(clause, *_search_secondary_terms())
        return [row[0] for row in conn.execute(stmt)]


def _tier_of(clause, row):
    """The tier value `clause` assigns to one row — the claim without the
    secondary ordering in front of it."""
    from sqlalchemy import MetaData, create_engine, insert, select

    md = MetaData()
    events, sports = _create_schema(md)
    engine = create_engine("sqlite://")
    md.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            insert(sports),
            [{"id": sid, "key": key} for sid, key in SPORT_KEYS.items()],
        )
        conn.execute(insert(events), [row])
        return conn.execute(select(clause)).scalar()


def _row(event_id, status, commence, **signals):
    row = {
        "id": event_id,
        "status": status,
        "commence_time": datetime.fromisoformat(commence).replace(tzinfo=timezone.utc),
        "sport_id": LIT_SPORT_ID,
        "home_score": None,
        "away_score": None,
        "period": None,
        "espn_id": None,
        "statpal_fixture_id": None,
    }
    row.update(signals)
    return row


#: `q=red sox`, ids in served order. A next game EXISTS, so D107 wants it first.
RED_SOX = (
    _row(1, "scheduled", "2026-08-11 23:07:00"),  # a month past its kickoff
    _row(2, "scheduled", "2026-08-12 23:07:00"),
    _row(3, "scheduled", "2026-08-15 23:15:00"),
    _row(4, "scheduled", "2026-09-10 22:45:00"),  # tonight, Worcester
    _row(5, "scheduled", "2026-09-11 23:10:00"),  # Boston's next game
)

#: `q=alcaraz`, ids in served order. NO next match exists, so D107 falls through
#: to the last one — which has to be the Sep-9 result, not the Sep-4 wreck.
ALCARAZ = (
    _row(10, "scheduled", "2026-09-04 00:00:00"),  # no result, ever
    _row(11, "completed", "2026-09-09 03:00:23"),  # the last match played
    _row(12, "completed", "2026-09-06 18:07:03"),
    _row(13, "completed", "2026-09-04 18:16:44"),
    _row(14, "completed", "2026-09-03 00:30:18"),
    _row(15, "closed", "2026-08-30 15:00:00"),
)


class TestTheProductionSpecimens:
    """§1 — the two served lists, ordered by the shipping clause."""

    def test_the_next_game_leads_for_red_sox(self):
        # 4 and 5 are the fixtures still to come, in date order; the three
        # August wrecks are below them instead of on top of them.
        assert _order_under(live_scheduled_settled_order(NOW), RED_SOX) == [
            4,
            5,
            1,
            2,
            3,
        ]

    def test_the_last_real_match_leads_for_alcaraz(self):
        # No next match exists, so D107 falls through to the last one: Shelton
        # on Sep 9, then the rest most-recent-first, then the wreck.
        assert _order_under(live_scheduled_settled_order(NOW), ALCARAZ) == [
            11,
            12,
            13,
            14,
            15,
            10,
        ]

    def test_a_reader_never_opens_on_a_row_that_reported_nothing(self):
        """The ship in one sentence, over both specimens: whatever leads, it is
        not a row whose own card prints 'No result reported'."""
        for rows in (RED_SOX, ALCARAZ):
            leader = _order_under(live_scheduled_settled_order(NOW), rows)[0]
            row = next(r for r in rows if r["id"] == leader)
            assert not started_without_result(
                row["status"], row["commence_time"], NOW
            ), f"row {leader} leads and has no reported result"


class TestTheClauseThisReplaced:
    """§2 — RED, executed rather than described."""

    def _two_tier(self):
        """The shipping clause with the #3211 arm removed — i.e. what it was."""
        from app.utils.event_rails import (
            started_live_and_observed,
            started_live_but_unobserved,
        )

        return case(
            (started_live_and_observed(NOW), 0),
            (started_live_but_unobserved(NOW), 2),
            (Event.status.in_(("live", "scheduled")), 1),
            else_=3,
        )

    def test_it_put_three_august_games_above_the_next_one(self):
        assert _order_under(self._two_tier(), RED_SOX) == [1, 2, 3, 4, 5]

    def test_it_put_the_wreck_above_every_real_alcaraz_result(self):
        assert _order_under(self._two_tier(), ALCARAZ)[0] == 10

    def test_the_staler_the_row_the_higher_it_sorted(self):
        """The mechanism, not just the symptom: under the old clause the order
        of the wrecks is their age, oldest first."""
        assert _order_under(self._two_tier(), RED_SOX)[:3] == [1, 2, 3]


class TestTheTemptingPlacementThatDoesNotWork:
    """§3 — RED for the shape that reads as the fix.

    "Started and nothing reported an ending" is branch two's own sentence, so
    the obvious home for these rows is beside the hollow-live ones. Branch two
    sits ABOVE the finished games, and that is the whole problem.
    """

    def _as_group_two(self):
        from app.utils.event_rails import (
            started_live_and_observed,
            started_live_but_unobserved,
        )

        return case(
            (started_live_and_observed(NOW), 0),
            (started_live_but_unobserved(NOW), 2),
            (started_without_result_rows(NOW), 2),
            (Event.status.in_(("live", "scheduled")), 1),
            else_=3,
        )

    def test_grouping_it_with_the_hollow_live_rows_leaves_alcaraz_broken(self):
        # The wreck still outranks the Sep-9 result — the defect with one fewer
        # row in front of it, which is why the arm scores 4 and not 2.
        assert _order_under(self._as_group_two(), ALCARAZ)[0] == 10

    def test_joining_the_settled_rows_is_the_3211_starvation(self):
        """The OTHER tempting shape, and `unreported_rail_condition` already
        measured what it does: these rows carry the midnight-UTC stamp
        (gotcha #14), so folding them into the settled tier sorts them above
        every real Final."""
        from app.utils.event_rails import (
            started_live_and_observed,
            started_live_but_unobserved,
        )

        as_settled = case(
            (started_live_and_observed(NOW), 0),
            (started_live_but_unobserved(NOW), 2),
            (started_without_result_rows(NOW), 3),
            (Event.status.in_(("live", "scheduled")), 1),
            else_=3,
        )
        midnight_stamped = (
            _row(20, "scheduled", "2026-09-10 00:00:00"),  # today, no result
            _row(21, "completed", "2026-09-09 03:00:23"),  # a real Final
        )
        assert _order_under(as_settled, midnight_stamped)[0] == 20


class TestTheTierValuesDirectly:
    """§4 — the ship stated without the secondary ordering in front of it, so a
    change to search's commence terms cannot quietly make §1 vacuous."""

    @pytest.mark.parametrize(
        "status,commence,expected",
        [
            ("scheduled", "2026-08-11 23:07:00", 4),  # #3211's class, LAST
            ("scheduled", "2026-09-11 23:10:00", 1),  # upcoming
            ("completed", "2026-09-09 03:00:23", 3),  # settled
            ("closed", "2026-08-30 15:00:00", 3),
            ("live", "2026-09-10 18:00:00", 2),  # started, nothing reported
        ],
    )
    def test_each_class_scores_its_own_tier(self, status, commence, expected):
        assert (
            _tier_of(live_scheduled_settled_order(NOW), _row(99, status, commence))
            == expected
        )

    def test_the_result_less_tier_is_below_every_other_tier(self):
        """The one relation the ship depends on, asserted as a relation rather
        than as the literal 4."""
        wreck = _tier_of(
            live_scheduled_settled_order(NOW),
            _row(99, "scheduled", "2026-08-11 23:07:00"),
        )
        others = [
            _tier_of(live_scheduled_settled_order(NOW), _row(99, status, commence))
            for status, commence in (
                ("scheduled", "2026-09-11 23:10:00"),
                ("completed", "2026-09-09 03:00:23"),
                ("closed", "2026-08-30 15:00:00"),
                ("live", "2026-09-10 18:00:00"),
                ("live", "2026-09-10 18:00:00"),
            )
        ]
        assert all(wreck > other for other in others)

    def test_a_started_live_row_still_outranks_it(self):
        """The #3946 placement is untouched: a hollow LIVE row is being played
        as far as the clock knows, and still sits above a fixture whose clock
        ran out days ago."""
        hollow_live = _tier_of(
            live_scheduled_settled_order(NOW), _row(99, "live", "2026-09-10 18:00:00")
        )
        wreck = _tier_of(
            live_scheduled_settled_order(NOW),
            _row(99, "scheduled", "2026-08-11 23:07:00"),
        )
        assert hollow_live < wreck


class TestTheTwoReadingsCannotDriftApart:
    """§5 — the SQL predicate and the Python one are the same sentence.

    `started_without_result_rows` was extracted from `unreported_rail_condition`
    so the ORDER BY could spend it. A second reading of "has this row's clock
    run out?" is exactly the drift `started_live` refuses in its own docstring,
    so the two are swept against each other rather than trusted.
    """

    STATUSES = ("scheduled", "live", "completed", "closed", EVENT_SUSPENDED)
    OFFSETS = (
        -timedelta(days=30),
        -timedelta(days=1),
        -UPCOMING_GRACE - timedelta(minutes=1),  # just past the boundary
        -UPCOMING_GRACE,  # exactly on it — NOT past, `<` is strict
        -UPCOMING_GRACE + timedelta(minutes=1),
        timedelta(0),
        timedelta(hours=5),
        timedelta(days=30),
    )

    @pytest.mark.parametrize("status,offset", list(product(STATUSES, OFFSETS)))
    def test_the_sql_agrees_with_the_python_predicate(self, status, offset):
        commence = NOW + offset
        sql = bool(
            _tier_of(
                started_without_result_rows(NOW),
                {
                    "id": 99,
                    "status": status,
                    "commence_time": commence,
                    "sport_id": LIT_SPORT_ID,
                    "home_score": None,
                    "away_score": None,
                    "period": None,
                    "espn_id": None,
                    "statpal_fixture_id": None,
                },
            )
        )
        assert sql == started_without_result(status, commence, NOW)

    def test_the_grace_is_the_boundary_and_it_is_strict(self):
        """A fixture that has not quite kicked off keeps its slot; one two hours
        and a minute past it does not. The number is `UPCOMING_GRACE`, spent and
        not copied."""
        on_the_line = _tier_of(
            live_scheduled_settled_order(NOW),
            _row(99, "scheduled", (NOW - UPCOMING_GRACE).isoformat()),
        )
        just_past = _tier_of(
            live_scheduled_settled_order(NOW),
            _row(
                99,
                "scheduled",
                (NOW - UPCOMING_GRACE - timedelta(minutes=1)).isoformat(),
            ),
        )
        assert on_the_line == 1
        assert just_past == 4
