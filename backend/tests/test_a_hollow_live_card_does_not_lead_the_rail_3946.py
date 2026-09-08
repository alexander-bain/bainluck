"""#3946, the DISPLAY half — a card with nothing to show does not lead the page.

THE SPECIMEN, `GET /api/leagues/tennis_atp` read from production 2026-09-08 at
17:40Z, `upcoming_games` in exactly the order it was served:

    1  live       Petkovic v Pellegrino          14:20Z   no score, no anchor
    2  live       Dellien v Meligeni Alves       14:20Z   no score, no anchor
    3  live       Varillas v Arnaboldi           14:20Z   no score, no anchor
    4  live       Scaglia v Bertrand             14:30Z   no score, no anchor
    5  scheduled  Frances Tiafoe v Alex Michelsen        17:30Z
    6  scheduled  Miedler/Polmans v Arevalo/Pavic        18:00Z
    7  scheduled  Heliovaara/Patten v Cabral/Tracy       18:00Z
    8  scheduled  Ben Shelton v Carlos Alcaraz           00:30Z

Four challenger matches that nothing has ever reported on hold the top four slots
of the ATP page, and the US Open semi-final is slot 8.

🔴 THIS IS NOT THE WALL CLOCK AND A SHORTER ONE DOES NOT FIX IT. #3946's other
half shipped first (`5c32e053`) and narrowed the bound a never-reported tennis
row may claim `live` under from 6.0h to 3.0h. It was photographed on production:
the three cards the issue named went away and three younger ones took their
place, at 3.4h, inside the new bound and correctly so. Measured either side of
that deploy, `live AND commence < now()-3.5h` went 58 → 14. **Halving how long a
bad card lasts does not change what the page looks like**, because there is
always a fresher cohort. Every one of the four rows above is inside the new
bound. The ordering has to be the fix, and it needs no clock at all.

SIZED against production the same day. 79 rows were `live` and started; 73 had
every column signal silent — `tennis_atp` 16 of 16, `soccer_other` 20 of 20,
`tennis_other` 18 of 18, `baseball_other` 8 of 8 — while every genuinely-reported
league in the same read was fully observed: Champions League 2 of 2,
`tennis_wta_us_open` 1 of 1, Eredivisie, Veikkausliiga and the Saudi Pro League
1 of 1 each. The demotion lands on the hollow population and on nothing else.

The clauses are executed as real SQL rather than asserted on their source, for
the reason `test_live_before_kickoff_q438.py` gives: the whole class of bug here
is an expression that looks right and sorts wrong.
"""

from datetime import datetime, timezone
from itertools import product

import pytest

from app.utils.event_completion import event_has_never_been_observed
from app.utils.event_rails import (
    live_first_order,
    live_scheduled_settled_order,
    never_observed_columns,
)

#: The test's own anchor, not the time the page above was read (17:40Z). It sits
#: past every `commence_time` in the fixtures except the premature ones, so the
#: time half of `started_live` is exercised rather than assumed. Fixed, never
#: derived from the clock (gotcha #44).
NOW = datetime(2026, 9, 8, 20, 0, tzinfo=timezone.utc)

#: The five columns of the canonical predicate, in its own argument order.
SIGNAL_COLUMNS = (
    "home_score",
    "away_score",
    "period",
    "espn_id",
    "statpal_fixture_id",
)

#: A value that counts as "this source has spoken", per column. `0-0` is a
#: REPORTED scoreline and has to rescue a row: a goalless first half is the
#: ordinary case, and demoting it would take a real match off the top of a real
#: league page. `None` is the only silence.
A_SIGNAL = {
    "home_score": 0,
    "away_score": 0,
    "period": "Set 2",
    "espn_id": "401778777",
    "statpal_fixture_id": "9912345",
}


def _order_under(clause, rows):
    """Execute `clause` against a real `events` table and return the ids.

    `rows` are dicts, because this clause reads eight columns and positional
    tuples of eight are unreadable. The models' JSONB columns cannot be created
    under SQLite, so the table is only what the ORDER BY touches; the EXPRESSION
    is the shipping one, rendering `events.<column>` by name, so it binds here
    unchanged.
    """
    from sqlalchemy import (
        Column,
        DateTime,
        Integer,
        MetaData,
        String,
        Table,
        create_engine,
        insert,
        select,
    )

    from app.models.models import Event

    md = MetaData()
    events = Table(
        "events",
        md,
        Column("id", Integer, primary_key=True),
        Column("status", String),
        Column("commence_time", DateTime(timezone=True)),
        Column("home_score", Integer),
        Column("away_score", Integer),
        Column("period", String),
        Column("espn_id", String),
        Column("statpal_fixture_id", String),
    )
    engine = create_engine("sqlite://")
    md.create_all(engine)
    with engine.begin() as conn:
        conn.execute(insert(events), list(rows))
        stmt = select(Event.id).order_by(clause, Event.commence_time.asc())
        return [row[0] for row in conn.execute(stmt)]


def _row(event_id, status, commence, **signals):
    row = {
        "id": event_id,
        "status": status,
        "commence_time": datetime.fromisoformat(commence).replace(tzinfo=timezone.utc),
    }
    row.update({c: None for c in SIGNAL_COLUMNS})
    row.update(signals)
    return row


#: The ATP page as it was served, ids in served order. The four hollow rows
#: carry no signal at all; the Slam matches are `scheduled`.
ATP_PAGE = (
    _row(1, "live", "2026-09-08 14:20:00"),  # Petkovic v Pellegrino
    _row(2, "live", "2026-09-08 14:20:00"),  # Dellien v Meligeni Alves
    _row(3, "live", "2026-09-08 14:20:00"),  # Varillas v Arnaboldi
    _row(4, "live", "2026-09-08 14:30:00"),  # Scaglia v Bertrand
    _row(5, "scheduled", "2026-09-08 17:30:00"),  # Tiafoe v Michelsen
    _row(6, "scheduled", "2026-09-08 18:00:00"),  # Miedler/Polmans
    _row(7, "scheduled", "2026-09-08 18:00:00"),  # Heliovaara/Patten
    _row(8, "scheduled", "2026-09-09 00:30:00"),  # Shelton v Alcaraz
)


class TestTheProductionSpecimen:
    """§1 — the eight rows of the ATP page, ordered by the shipping clause."""

    def test_the_four_hollow_cards_no_longer_hold_the_top_of_the_rail(self):
        # 5-8 are the US Open, in date order; 1-4 are the challenger matches
        # nothing has ever reported on, below them.
        assert _order_under(live_first_order(NOW), ATP_PAGE) == [5, 6, 7, 8, 1, 2, 3, 4]

    def test_the_clause_this_replaced_led_with_them(self):
        """RED, executed rather than described: the two-way clause put all four
        hollow rows above the semi-final."""
        from sqlalchemy import case

        from app.utils.event_rails import started_live

        two_way = case((started_live(NOW), 0), else_=1)
        assert _order_under(two_way, ATP_PAGE)[:4] == [1, 2, 3, 4]

    def test_levelling_them_with_the_scheduled_games_would_have_been_a_no_op(self):
        """RED for the OTHER tempting shape — the one that reads as a fix and
        changes nothing.

        Every caller pairs this clause with `commence_time ASC`, so a row that
        started at 14:20 outranks a 17:30 fixture inside any group they share.
        Demoting a hollow row only as far as group 1 leaves the page byte-for-
        byte where it was, which is why the shipping clause sends it to group 2.
        """
        from sqlalchemy import case

        from app.utils.event_rails import started_live_and_observed

        levelled = case((started_live_and_observed(NOW), 0), else_=1)
        assert _order_under(levelled, ATP_PAGE) == [1, 2, 3, 4, 5, 6, 7, 8]


class TestAMatchWithSomethingToShowKeepsTheTop:
    """§2 — the direction that costs something if it is wrong.

    The live-first sort exists so that what is being played leads the page. A
    demotion that also caught real matches would be a worse bug than the one it
    repairs, so each of the five signals is tested on its own: ANY one of them
    is a source having spoken, and any one of them alone must rescue the row.
    """

    @pytest.mark.parametrize("column", SIGNAL_COLUMNS)
    def test_one_signal_alone_puts_the_live_row_back_on_top(self, column):
        rows = [
            _row(90, "live", "2026-09-08 14:20:00", **{column: A_SIGNAL[column]}),
            *ATP_PAGE,
        ]
        assert _order_under(live_first_order(NOW), rows)[0] == 90

    def test_a_goalless_first_half_is_a_reported_scoreline(self):
        """`0-0` is not silence. Demoting it would take a real soccer match off
        the top of a real league page for the first forty-five minutes."""
        rows = [
            _row(91, "live", "2026-09-08 19:30:00", home_score=0, away_score=0),
            *ATP_PAGE,
        ]
        assert _order_under(live_first_order(NOW), rows)[0] == 91


class TestQ438IsNotUndone:
    """§3 — a PREMATURE-live row keeps the position Q438 ruled it into.

    A fixture a month out has no score either, and the temptation is to key the
    demotion on the columns alone. Q438's whole finding is that such a row
    belongs in DATE ORDER among the scheduled games — not at the bottom of the
    rail beside rows whose start time has actually passed. It fails the time
    half of `started_live`, so it never reaches the hollow arm.
    """

    ROWS = (
        _row(20, "live", "2026-10-06 18:00:00"),  # 14969919, a month out
        _row(21, "scheduled", "2026-09-08 23:30:00"),  # kicks off tonight
        _row(22, "live", "2026-09-08 17:00:00", home_score=1),  # being played
        _row(23, "live", "2026-09-08 14:20:00"),  # hollow, started
    )

    def test_the_premature_row_sits_among_the_scheduled_games_not_below_them(self):
        order = _order_under(live_first_order(NOW), self.ROWS)
        assert order == [22, 21, 20, 23]
        assert order.index(20) < order.index(23)

    def test_the_three_way_clause_keeps_it_there_too(self):
        rows = (*self.ROWS, _row(24, "completed", "2026-09-07 23:30:00"))
        assert _order_under(live_scheduled_settled_order(NOW), rows) == [
            22,  # live and reported on
            21,
            20,  # upcoming, in date order — the premature row among them
            23,  # started, and nothing has ever said so
            24,  # finished
        ]


class TestTheSqlAgreesWithThePythonPredicate:
    """§4 — the two readings of "never observed" cannot drift apart.

    `never_observed_columns()` is the column half of
    `event_completion.event_has_never_been_observed`, written a second time in a
    second language, which is the shape this repo's rails module exists to warn
    about. So the whole column vocabulary is swept: all 2^5 combinations of
    silence and signal, executed as SQL and compared against the Python
    predicate. A column added to one and not the other fails here.
    """

    @pytest.mark.parametrize(
        "signals", list(product((None, "SIGNAL"), repeat=len(SIGNAL_COLUMNS)))
    )
    def test_every_combination_of_silence_and_signal_agrees(self, signals):
        values = {
            column: (A_SIGNAL[column] if flag else None)
            for column, flag in zip(SIGNAL_COLUMNS, signals)
        }
        expected = event_has_never_been_observed(
            *(values[c] for c in SIGNAL_COLUMNS), None
        )

        from sqlalchemy import case

        demoted = _order_under(
            case((never_observed_columns(), 1), else_=0),
            [_row(1, "live", "2026-09-08 14:20:00", **values)],
        )
        # One row, so the order proves nothing; run the predicate as a value.
        assert demoted == [1]
        assert self._never_observed_in_sql(values) is expected

    @staticmethod
    def _never_observed_in_sql(values) -> bool:
        from sqlalchemy import (
            Column,
            DateTime,
            Integer,
            MetaData,
            String,
            Table,
            create_engine,
            insert,
            select,
        )

        md = MetaData()
        events = Table(
            "events",
            md,
            Column("id", Integer, primary_key=True),
            Column("status", String),
            Column("commence_time", DateTime(timezone=True)),
            *(
                Column(c, Integer if c.endswith("_score") else String)
                for c in SIGNAL_COLUMNS
            ),
        )
        engine = create_engine("sqlite://")
        md.create_all(engine)
        with engine.begin() as conn:
            conn.execute(
                insert(events), [_row(1, "live", "2026-09-08 14:20:00", **values)]
            )
            return bool(conn.execute(select(never_observed_columns())).scalar_one())

    def test_the_argument_order_still_matches_the_python_signature(self):
        """The sweep above would pass on two predicates that disagree about
        WHICH column is which, as long as both read all five. This pins the
        order, so `SIGNAL_COLUMNS` cannot quietly stop describing the function
        it is a transcription of.
        """
        import inspect

        params = list(inspect.signature(event_has_never_been_observed).parameters)
        assert params == [*SIGNAL_COLUMNS, "last_snapshot"]
