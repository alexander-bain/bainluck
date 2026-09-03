"""#2693 step 2 — the authority-id channel that un-dead-ends the Finished list.

`resolve_matchup_events` starts at a REGISTER MATCHUP, and `build_slate` retires
a matchup the moment its match starts. So the one list made entirely of started
matches is the one that channel structurally cannot serve: measured on
production 2026-09-02, 118 of the 235 finished rows carried no matchup at all.

`resolve_espn_competition_events` is the second channel — the authority's own
competition id dereferenced through `events.espn_id`. Two things have to hold,
and the second is the one with teeth:

  1. an id carried by exactly one event resolves;
  2. an id carried by TWO resolves to NEITHER.

(2) is not defensive coding. When this shipped, 196 `espn_id`s were worn by 430
rows and there was no unique constraint to stop it — a link that guesses between
two rows is wrong half the time and looks right every time.

THE SQL IS RUN, NOT READ. The predicate is compiled to sqlite and executed over
planted rows, because the two bounds that matter — the `IN (...)` on the ids and
the join-bound on `sports.key` — are properties of the statement and an assertion
about a dict the function returns cannot see either of them.
"""

from __future__ import annotations

import asyncio
import sqlite3

import pytest
from sqlalchemy.dialects import sqlite as sqlite_dialect

from app.utils.tournament_event_link import (
    ESPN_UNRESOLVED_REASONS,
    resolve_espn_competition_events,
)

US_OPEN_KEYS = ("tennis_atp_us_open", "tennis_wta_us_open")


class _CapturingSession:
    """Records the statement, replies with whatever the test planted."""

    def __init__(self, rows):
        self._rows = rows
        self.statements = []

    async def execute(self, statement, *args, **kwargs):
        self.statements.append(statement)
        return _Result(self._rows)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


def resolve(rows, competition_ids, sport_keys=US_OPEN_KEYS):
    session = _CapturingSession(rows)
    out = asyncio.run(
        resolve_espn_competition_events(session, competition_ids, sport_keys)
    )
    return out, session


# ---------------------------------------------------------------------------
# The resolution, and the refusal that is the point of it.
# ---------------------------------------------------------------------------


class TestResolution:
    def test_one_event_per_id_resolves(self):
        out, _ = resolve([("182565", 15301137)], ["182565"])
        assert out["by_espn"] == {"182565": 15301137}
        assert out["unresolved"] == {}
        assert out["reason_counts"] == {}

    def test_two_events_on_one_id_resolve_to_NEITHER(self):
        """The load-bearing refusal. `espn_id` was not unique when this shipped."""
        out, _ = resolve(
            [("182565", 15301137), ("182565", 15399999)], ["182565"]
        )
        assert out["by_espn"] == {}
        assert out["unresolved"] == {"182565": "ESPN_ID_AMBIGUOUS"}
        assert out["reason_counts"] == {"ESPN_ID_AMBIGUOUS": 1}

    def test_the_same_event_returned_twice_is_not_an_ambiguity(self):
        """A duplicate ROW is not two events. Counting rows instead of distinct
        events would turn a harmless repeat into a refused link."""
        out, _ = resolve(
            [("182565", 15301137), ("182565", 15301137)], ["182565"]
        )
        assert out["by_espn"] == {"182565": 15301137}

    def test_an_id_no_event_carries_is_a_NAMED_gap(self):
        """71 of the 118 espn-keyed rows are qualifying matches we never
        created. That is coverage, and it must be counted, not silent."""
        out, _ = resolve([], ["184657"])
        assert out["by_espn"] == {}
        assert out["unresolved"] == {"184657": "NO_EVENT_FOR_ESPN_ID"}

    def test_every_refusal_is_in_the_declared_set(self):
        out, _ = resolve(
            [("1", 10), ("2", 20), ("2", 21)], ["1", "2", "3"]
        )
        assert set(out["unresolved"].values()) <= set(ESPN_UNRESOLVED_REASONS)
        assert out["by_espn"] == {"1": 10}

    def test_mixed_ids_each_get_their_own_answer(self):
        out, _ = resolve(
            [("a", 1), ("b", 2), ("b", 3)], ["a", "b", "c"]
        )
        assert out["by_espn"] == {"a": 1}
        assert out["reason_counts"] == {
            "ESPN_ID_AMBIGUOUS": 1,
            "NO_EVENT_FOR_ESPN_ID": 1,
        }


class TestBounds:
    def test_no_ids_issues_no_query_at_all(self):
        out, session = resolve([], [])
        assert out == {"by_espn": {}, "unresolved": {}, "reason_counts": {}}
        assert session.statements == []

    def test_no_sport_keys_issues_no_query_at_all(self):
        """An unbounded read of `events` is the one thing this must never be."""
        out, session = resolve([], ["182565"], sport_keys=())
        assert out["by_espn"] == {}
        assert session.statements == []

    def test_a_blank_or_none_id_is_dropped_before_the_query(self):
        _, session = resolve([], ["182565", "", None])
        sql = _compiled(session)
        assert "182565" in sql
        # A blank would be a bind that matches an `espn_id` of '' — the same
        # wildcard-by-another-route the decider's name test refuses.
        assert "''" not in sql.split("IN (")[-1].split(")")[0]

    def test_a_repeated_id_is_asked_for_once(self):
        _, session = resolve([], ["182565", "182565", "182545"])
        sql = _compiled(session)
        assert sql.count("'182565'") == 1


def _compiled(session) -> str:
    assert session.statements, "the resolver issued no query"
    return (
        session.statements[0]
        .compile(dialect=sqlite_dialect.dialect(), compile_kwargs={"literal_binds": True})
        .string
    )


# ---------------------------------------------------------------------------
# THE SQL IS RUN. Both bounds are properties of the statement.
# ---------------------------------------------------------------------------


#: (event_id, espn_id, sport_key, selected, why)
PLANTED = [
    (15301137, "182565", "tennis_wta_us_open", True,
     "the ordinary case — a US Open match ESPN named"),
    (15301156, "182687", "tennis_atp_us_open", True,
     "the other US Open sport key; the bound is a list, not one key"),
    (15399001, "182565", "tennis_atp", False,
     "SAME competition id, a DIFFERENT tournament. The sport bound is what "
     "stops a Cincinnati row from answering for a US Open one"),
    (14683176, "182565", "baseball_ncaa", False,
     "SAME id again, in another sport entirely. ESPN's id spaces are not "
     "guaranteed disjoint across sports and this row must not be reachable"),
    (15301138, "999999", "tennis_wta_us_open", False,
     "in scope, id not asked for — the IN(...) bound"),
    (15301139, None, "tennis_wta_us_open", False,
     "no espn_id at all; 4 of the 200 US Open rows are these"),
]


@pytest.fixture()
def planted_db():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE sports (id INTEGER PRIMARY KEY, key TEXT)")
    db.execute(
        "CREATE TABLE events (id INTEGER PRIMARY KEY, espn_id TEXT, sport_id INTEGER)"
    )
    keys = {}
    for _, _, sport_key, _, _ in PLANTED:
        keys.setdefault(sport_key, len(keys) + 1)
    for sport_key, sport_id in keys.items():
        db.execute("INSERT INTO sports VALUES (?, ?)", (sport_id, sport_key))
    for event_id, espn_id, sport_key, _, _ in PLANTED:
        db.execute(
            "INSERT INTO events VALUES (?, ?, ?)", (event_id, espn_id, keys[sport_key])
        )
    db.commit()
    yield db
    db.close()


def test_the_real_predicate_selects_exactly_the_rows_it_should(planted_db):
    """Compiled from the resolver's own statement, run over planted rows.

    An assertion on the returned dict cannot see either bound — the function
    would return the same shape if the `sports.key` join vanished. This runs it.
    """
    _, session = resolve([], ["182565", "182687"])
    sql = _compiled(session)

    selected = {row[1] for row in planted_db.execute(sql).fetchall()}
    expected = {
        event_id for event_id, espn_id, sport_key, want, _ in PLANTED
        if want and espn_id in ("182565", "182687")
    }
    assert selected == expected, "\n".join(
        f"  {event_id} {espn_id} {sport_key}: {why}"
        for event_id, espn_id, sport_key, _, why in PLANTED
    )


def test_the_out_of_sport_twin_would_otherwise_be_an_ambiguity(planted_db):
    """The sport bound is not an optimisation.

    Three rows carry `182565`. Two are out of scope. Without the join-bound the
    resolver would see three events for one id, call it ESPN_ID_AMBIGUOUS, and
    the US Open link that ought to work would go dead — a failure that looks
    exactly like the collision it is meant to detect.
    """
    _, session = resolve([], ["182565"])
    bounded = planted_db.execute(_compiled(session)).fetchall()
    assert len({row[1] for row in bounded}) == 1

    # The control: the same id, asked WITHOUT the sport bound. Written out
    # rather than derived from the statement by string surgery — a control
    # built by cutting up the treatment can break in a way that reads as a
    # result.
    unbounded = planted_db.execute(
        "SELECT events.espn_id, events.id FROM events WHERE events.espn_id IN ('182565')"
    ).fetchall()
    assert len({row[1] for row in unbounded}) == 3
