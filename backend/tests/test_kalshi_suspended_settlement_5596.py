"""#5596 — a played game whose event is stuck at `suspended` stops pricing itself.

THE DATED SPECIMEN, our own row and the venue read in the same pass (standing
notice 26/27). `Machida Z vs Marinos`, J-League, market 60489099, filed by
ux/1213 off the live page:

    leg          current_probability     yes_bid / yes_ask     book mid
    Tie                     0.99            0.15 / 0.16          0.155
    Marinos                 0.01            0.69 / 0.70          0.695
    Machida Z               0.01            0.10 / 0.13          0.115

The book is COHERENT — 0.155 + 0.695 + 0.115 = 0.965, and it names Marinos the
~70% favourite. The served vector is `0.99 / 0.01 / 0.01`: a draw at 99% with
both teams at 1%, three numbers summing to 101%, on a match that had already
been played. The 0.99 sits on the leg the book puts at 15.5%, so it is not a
mis-derivation from the book and not "the winner written early" either — it is
the settlement tail frozen beside a two-sided quote that stopped updating.

WHICH HALF IS LYING, because the obvious reading is the wrong one. `99% against
a 15.5% book` invites withdrawing the 99%. Asked at the venue,
`KXJLEAGUEGAME-26SEP12MACMAR-TIE` settled **`result='yes'`** — the match really
did end a draw — and the Sunderland specimen's 0.99 leg (`Arsenal wins 2-0`)
settled `result='yes'` too. **The probability is the honest half in both; the
frozen two-sided quote is the relic.** So the defect is not a wrong number, it
is a finished market presented as a live one, and the fix must not suppress a
price: `UPDATE_SQL` leaves every price exactly where it is
(`test_the_write_carries_no_grade`).

WHY NO EXISTING ARM REACHES IT, measured over #5596's WHOLE Kalshi population on
production 2026-09-14 05:16Z — 51 markets / 114 legs, and **114/114 `finalized`
at Kalshi**, asked by ticker through `GET /trade-api/v2/markets?tickers=…`:

* the linked events read `suspended` (44) or `scheduled` (7), `completed_at`
  NULL on all 51;
* run against those same ids: the completed arm selects **0**, the live arm
  selects **0**, and PR #5913's pre-kick-off scope (`e.status='scheduled' AND
  e.commence_time > NOW()`) selects **0**.

Not late — unreachable. Both existing arms key on our own event reaching
`completed` or `live`, and a `suspended` event reaches neither (#5881: 59
finished MLB games have been frozen there since Sep 2).

WHY THE SCREEN IS `suspended` AND NOT WIDER. Precision measured the same minute,
30 markets per bucket carrying the frozen signature, asked at the venue:
`suspended` **26/30 finalized (87%)**, `scheduled` 7/28 (25%), NO linked event
**1/26 (4%)** — and that last bucket is 485 markets, nearly all genuinely
trading. A row that is never settled never leaves the selection, so widening
past `suspended` would buy a venue read every 10 minutes, forever, on healthy
markets. The unlinked rows are a real gap (`JOIN events` cannot see them) and
are deliberately NOT this ship.

WHAT THIS SHIP DOES NOT DO. It writes no grade — never `is_winner`, never a
price (CAL-P061 / #1852, inherited unchanged through `UPDATE_SQL`). It makes the
market stop claiming to be open. It also does not repair the event status: an
event frozen at `suspended` is the event graph's defect (#5881 / #5747) and this
arm is built to work correctly WITHOUT waiting for it.

ON THE TESTS. `TestTheStatement` asserts binds and text the way #5024's suite
does. `TestThePredicateOnRealRows` goes further and is the reason this file is
worth reading: it EXECUTES `RECENT_FINAL_SELECT_SQL` against real tables holding
the specimen's own numbers, so "the predicate matches the specimen" is proved
here rather than deferred to a production read. Both directions are asserted
(gotcha #43): the frozen row is selected AND a normally-trading one is not.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import sqlite3
import textwrap
from datetime import datetime, timedelta, timezone

import pytest

from app.tasks import kalshi_resolution_sweep as sweep

#: Fixed, offset-first, so nothing below can branch on the wall clock
#: (gotcha #44). The specimen's game was played 2026-09-12.
NOW = datetime(2026, 9, 14, 5, 16, 0, tzinfo=timezone.utc)

#: The specimen's own event ticker and the backstop the venue returns.
SPECIMEN_TICKER = "KXJLEAGUEGAME-26SEP12MACMAR"
BACKSTOP = datetime(2026, 9, 12, 12, 34, 57, tzinfo=timezone.utc)

#: A selected row as the statement returns it:
#: (id, external_id, resolution_date, commence_time, market_tier).
SPECIMEN_ROW = (
    60489099,
    SPECIMEN_TICKER,
    BACKSTOP,
    datetime(2026, 9, 12, 10, 0, 0, tzinfo=timezone.utc),
    3,
)


# --------------------------------------------------------------------------
# The statement: binds and text.
# --------------------------------------------------------------------------


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _Session:
    TOTALS = (1, 0, 0, 1)

    def __init__(self, recorder, rows):
        self._recorder = recorder
        self._rows = rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        self._recorder.append((sql, params))
        if sql.strip().upper().startswith("UPDATE"):
            return _Result([])
        if "count(*)" in sql:
            return _Result([self.TOTALS])
        return _Result(self._rows)

    async def commit(self):
        return None


class _Venue:
    """Kalshi, answering with the specimen's real leg statuses.

    It must be able to REFUSE — `statuses` is a parameter — or "reached the
    venue" and "wrote the row" become indistinguishable.
    """

    def __init__(self, statuses):
        self._statuses = list(statuses)
        self.asked: list[str] = []

    async def get_event(self, ticker, with_nested_markets=True):
        self.asked.append(ticker)
        iso = BACKSTOP.isoformat().replace("+00:00", "Z")
        return {
            "markets": [
                {
                    "ticker": f"{ticker}-{i}",
                    "status": s,
                    "close_time": iso,
                    "expiration_time": iso,
                    # The grade rides the same payload. This rail reads it and
                    # must never write it (CAL-P061 / #1852).
                    "result": "yes" if s == "finalized" else "",
                }
                for i, s in enumerate(self._statuses)
            ]
        }

    async def close(self):
        return None


def _drive(*, rows=(SPECIMEN_ROW,), statuses=("finalized",) * 3, apply=True):
    recorder: list = []
    venue = _Venue(statuses)

    def maker():
        return _Session(recorder, list(rows))

    report = asyncio.run(
        sweep.run_recent_finals(
            limit=200,
            apply=apply,
            session_maker=maker,
            client_factory=lambda: venue,
            now=NOW,
        )
    )
    selects = [(s, p) for s, p in recorder if not s.strip().upper().startswith("UPDATE")]
    updates = [p for s, p in recorder if s.strip().upper().startswith("UPDATE")]
    return report, selects, updates, venue


def _params_the_runner_supplies() -> set[str]:
    """The keys of the dict `run_recent_finals` hands to `session.execute`.

    Read from the source rather than by driving the task, because the driver
    above records the parameters the runner BUILT, which is the same side of the
    question. This reads the call site itself, so the bind-set test compares two
    independent halves.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(sweep.run_recent_finals)))
    dicts = [
        node.args[1]
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "execute"
        and len(node.args) == 2
        and isinstance(node.args[1], ast.Dict)
    ]
    assert len(dicts) == 1, (
        f"expected exactly one parameterised `session.execute` in "
        f"`run_recent_finals`, found {len(dicts)}; this helper cannot tell you "
        f"which one the bind-set test means"
    )
    keys = [k.value for k in dicts[0].keys if isinstance(k, ast.Constant)]
    assert len(keys) == len(dicts[0].keys), (
        "a non-literal key (a `**spread`, a variable) is in the parameter dict; "
        "the bind-set test cannot read it statically"
    )
    return set(keys)


class TestTheStatement:
    """The suspended branch exists, binds its own parameters, and is additive."""

    def test_it_binds_a_suspended_floor_and_a_frozen_gap(self):
        """RED before #5596: neither parameter was bound, because the statement
        had no suspended branch to bind them for."""
        _, selects, _, _ = _drive()
        _, params = selects[0]

        assert params["suspended_floor"] == NOW - timedelta(
            hours=sweep.SUSPENDED_EVENT_WINDOW_HOURS
        )
        assert params["frozen_gap"] == sweep.FROZEN_BOOK_GAP
        # The specimen commenced 2026-09-12 10:00Z, two days before the read. A
        # band tightened below that would drop the row this arm exists for.
        assert params["suspended_floor"] < SPECIMEN_ROW[3], (
            "the specimen's kickoff must be inside the band this arm asks for"
        )

    def test_the_statement_admits_a_suspended_event_on_both_freeze_signatures(self):
        sql = _drive()[1][0][0]

        assert "e.status = 'suspended'" in sql
        assert "e.commence_time >= :suspended_floor" in sql
        # #5024's signature — both sides of the book gone.
        assert "fo.current_yes_bid = 0" in sql
        assert "fo.current_yes_ask = 1" in sql
        # #5596's — a two-sided book contradicting its own probability.
        assert "fo.current_yes_bid > 0" in sql
        assert "fo.current_yes_ask < 1" in sql
        assert ":frozen_gap" in sql

    def test_the_two_existing_arms_are_untouched(self):
        """The suspended branch is additive. If this fails, #4655 or #5024
        regressed."""
        sql, params = _drive()[1][0]

        assert "e.status = 'completed'" in sql
        assert "e.completed_at >= :final_floor" in sql
        assert "e.status = 'live'" in sql
        assert "e.commence_time >= :live_floor" in sql
        assert params["final_floor"] == NOW - timedelta(
            hours=sweep.RECENT_FINAL_WINDOW_HOURS
        )
        assert params["live_floor"] == NOW - timedelta(
            hours=sweep.LIVE_EVENT_WINDOW_HOURS
        )

    def test_a_finished_game_still_takes_the_batch_first(self):
        """#4655's 30-minute bar is unchanged. A suspended event carries
        `completed_at` NULL, so `NULLS LAST` keeps every one of these behind
        every genuine final."""
        sql = _drive()[1][0][0]
        order = sql.split("ORDER BY", 1)[1]

        assert "e.completed_at DESC NULLS LAST" in order
        assert order.index("e.completed_at DESC") < order.index("e.commence_time DESC")

    def test_the_statement_parses_as_postgres(self):
        """A syntax error here is otherwise found by a beat nobody is reading."""
        sqlglot = pytest.importorskip("sqlglot")
        sqlglot.parse_one(sweep.RECENT_FINAL_SELECT_SQL, dialect="postgres")

    def test_the_measured_constants_are_pinned_to_what_was_measured(self):
        """The behaviour tests below derive their inputs FROM these constants, so
        they move with a change instead of catching it. This one does not.

        Both numbers carry a production measurement in their docstrings — 0.10 is
        the gap at which 26/30 sampled suspended markets were `finalized` at the
        venue (87%), and 336h covers the oldest suspended open KX market
        (2026-09-03 18:50Z) as read on 2026-09-14. Changing either is allowed;
        changing it without re-taking the measurement is what this refuses.
        """
        assert sweep.FROZEN_BOOK_GAP == 0.10
        assert sweep.SUSPENDED_EVENT_WINDOW_HOURS == 336

    def test_the_window_is_leashed_rather_than_unbounded(self):
        """A suspended event never reaches a terminal status on its own, so the
        floor is the ONLY thing that retires a stuck row from this band."""
        assert sweep.SUSPENDED_EVENT_WINDOW_HOURS > 0
        assert "e.commence_time IS NOT NULL" in sweep.RECENT_FINAL_SELECT_SQL

    def test_the_statement_binds_exactly_the_parameters_the_runner_supplies(self):
        """#5596 gave this statement its first SQL comments, and `text()` scans
        for `:word` ANYWHERE in the string — comments included.

        So a sentence like "see :frozen_gap" mints a SIXTH bind that nothing
        supplies, and `StatementError: A value is required for bind parameter`
        is raised at EXECUTE time, on a 10-minute beat, in production. Nothing
        else in this file can see it: every test above drives a fake session
        that records the statement and never binds it, and the sqlite tests
        below pass their own parameter dict.

        Both sides are read from the code, so the assertion moves with a
        legitimate change — but a bind that appears on ONE side only (which is
        exactly what a comment does) breaks the equality. The literal set is
        pinned too, so deleting both sides cannot pass.
        """
        sqlalchemy_text = pytest.importorskip("sqlalchemy").text
        bound = set(sqlalchemy_text(sweep.RECENT_FINAL_SELECT_SQL)._bindparams)
        supplied = _params_the_runner_supplies()

        assert supplied == {
            "final_floor",
            "live_floor",
            "suspended_floor",
            "frozen_gap",
            "limit",
        }
        assert bound == supplied, (
            f"the statement binds {sorted(bound)} and `run_recent_finals` supplies "
            f"{sorted(supplied)}; a `:word` in a COMMENT is the usual cause"
        )

    def test_that_guard_can_actually_see_a_bind_hidden_in_a_comment(self):
        """The positive control for the test above, which would otherwise be
        unfalsifiable: if `text()` ignored comments, it would pass forever."""
        sqlalchemy_text = pytest.importorskip("sqlalchemy").text
        marker = "-- #5024's signature: both sides gone."
        assert marker in sweep.RECENT_FINAL_SELECT_SQL, (
            "the comment this control poisons has been reworded; repoint it"
        )
        poisoned = sweep.RECENT_FINAL_SELECT_SQL.replace(
            marker, "-- #5024's signature: both sides of :oops gone."
        )

        assert "oops" in set(sqlalchemy_text(poisoned)._bindparams)


# --------------------------------------------------------------------------
# The predicate, executed against real rows holding the specimen's numbers.
# --------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE events (
    id INTEGER PRIMARY KEY,
    status TEXT,
    completed_at TEXT,
    commence_time TEXT
);
CREATE TABLE futures_markets (
    id INTEGER PRIMARY KEY,
    source TEXT,
    external_id TEXT,
    status TEXT,
    event_id INTEGER,
    resolution_date TEXT,
    commence_time TEXT,
    market_tier INTEGER,
    updated_at TEXT
);
CREATE TABLE futures_outcomes (
    id INTEGER PRIMARY KEY,
    market_id INTEGER,
    current_yes_bid REAL,
    current_yes_ask REAL,
    current_probability REAL
);
"""

#: ISO-8601 UTC, so a lexicographic comparison in SQLite orders the same way a
#: TIMESTAMPTZ comparison does in Postgres.
def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _select(markets, events, outcomes, *, now=NOW):
    """Run the REAL statement over real rows and return the selected ids.

    The one substitution is `CAST(:frozen_gap AS numeric)` -> `CAST(... AS REAL)`:
    SQLite has no `numeric`, and the cast exists in the Postgres text so the bind
    cannot be compared as a float against a `numeric(7,6)` column. Nothing else
    about the predicate is rewritten — every branch, floor and screen below is
    the shipped text.
    """
    con = sqlite3.connect(":memory:")
    con.executescript(_SCHEMA)
    con.executemany(
        "INSERT INTO events (id,status,completed_at,commence_time) VALUES (?,?,?,?)",
        events,
    )
    con.executemany(
        "INSERT INTO futures_markets "
        "(id,source,external_id,status,event_id,resolution_date,commence_time,"
        "market_tier,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        markets,
    )
    con.executemany(
        "INSERT INTO futures_outcomes "
        "(id,market_id,current_yes_bid,current_yes_ask,current_probability) "
        "VALUES (?,?,?,?,?)",
        outcomes,
    )
    sql = sweep.RECENT_FINAL_SELECT_SQL.replace(
        "CAST(:frozen_gap AS numeric)", "CAST(:frozen_gap AS REAL)"
    )
    rows = con.execute(
        sql,
        {
            "final_floor": _iso(now - timedelta(hours=sweep.RECENT_FINAL_WINDOW_HOURS)),
            "live_floor": _iso(now - timedelta(hours=sweep.LIVE_EVENT_WINDOW_HOURS)),
            "suspended_floor": _iso(
                now - timedelta(hours=sweep.SUSPENDED_EVENT_WINDOW_HOURS)
            ),
            "frozen_gap": sweep.FROZEN_BOOK_GAP,
            "limit": 200,
        },
    ).fetchall()
    con.close()
    return {r[0] for r in rows}


def _suspended_event(eid=1, *, commence=datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)):
    return (eid, "suspended", None, _iso(commence))


def _market(mid, eid, *, status="open", external_id=SPECIMEN_TICKER):
    return (
        mid,
        "kalshi",
        external_id,
        status,
        eid,
        None,
        _iso(datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)),
        3,
        _iso(NOW),
    )


class TestThePredicateOnRealRows:
    """#5024's suite could not prove the predicate matches its specimen. This
    one executes the shipped statement over the specimen's own numbers."""

    def test_the_jleague_specimen_is_selected(self):
        """`Tie` at 0.99 over its own 0.15/0.16 book, on a suspended event.

        RED before #5596: no branch of the statement admits a suspended event,
        so this returns the empty set."""
        selected = _select(
            markets=[_market(60489099, 1)],
            events=[_suspended_event(1)],
            outcomes=[
                # The venue settled TIE `result='yes'`: the 0.99 is the honest
                # half and the 0.15/0.16 quote beside it is the frozen relic.
                (1, 60489099, 0.15, 0.16, 0.99),   # Tie      — the real result
                (2, 60489099, 0.69, 0.70, 0.01),   # Marinos  — the stale favourite
                (3, 60489099, 0.10, 0.13, 0.01),   # Machida Z
            ],
        )
        assert selected == {60489099}

    def test_the_other_direction_is_selected_too(self):
        """gotcha #43. `Over 0.5 goals` served at 0.01 against an 0.85 book is
        the same defect inverted, and a one-sided rule would ship half a fix."""
        selected = _select(
            markets=[_market(2, 1)],
            events=[_suspended_event(1)],
            outcomes=[(1, 2, 0.84, 0.86, 0.01)],
        )
        assert selected == {2}

    def test_a_normally_trading_suspended_market_is_not_selected(self):
        """The 13% the screen admits at the venue cost one question and no
        write — but a market whose probability AGREES with its own book is not
        even asked about. Without this the arm would re-ask 198 rows every 10
        minutes forever."""
        selected = _select(
            markets=[_market(3, 1)],
            events=[_suspended_event(1)],
            outcomes=[
                (1, 3, 0.15, 0.16, 0.155),
                (2, 3, 0.69, 0.70, 0.695),
            ],
        )
        assert selected == set()

    def test_an_empty_book_on_a_suspended_event_is_selected(self):
        """#5024's signature reaches suspended events too. Nothing covered it
        there: its own arm requires `e.status = 'live'`."""
        selected = _select(
            markets=[_market(4, 1)],
            events=[_suspended_event(1)],
            outcomes=[(1, 4, 0.0, 1.0, 0.99)],
        )
        assert selected == {4}

    def test_a_scheduled_event_is_not_selected(self):
        """Precision scoping, measured: `scheduled` was 7/28 (25%) finalized at
        the venue against `suspended`'s 26/30. Widening to it would spend three
        venue reads in four on markets that are fine."""
        selected = _select(
            markets=[_market(5, 2)],
            events=[(2, "scheduled", None, _iso(datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)))],
            outcomes=[(1, 5, 0.15, 0.16, 0.99)],
        )
        assert selected == set()

    def test_a_suspended_event_older_than_the_floor_is_not_selected(self):
        """The leash. Nothing else retires a permanently-stuck event."""
        stale = NOW - timedelta(hours=sweep.SUSPENDED_EVENT_WINDOW_HOURS + 24)
        selected = _select(
            markets=[_market(6, 3)],
            events=[_suspended_event(3, commence=stale)],
            outcomes=[(1, 6, 0.15, 0.16, 0.99)],
        )
        assert selected == set()

    def test_a_resolved_market_is_not_reselected(self):
        """Self-draining: the write is what removes a row from the population.
        If this fails the arm re-asks the venue about its own finished work."""
        selected = _select(
            markets=[_market(7, 1, status="resolved")],
            events=[_suspended_event(1)],
            outcomes=[(1, 7, 0.15, 0.16, 0.99)],
        )
        assert selected == set()

    def test_a_non_kalshi_ticker_is_not_selected(self):
        """`LIKE 'KX%'` — the derivation downstream reads Kalshi event tickers
        and nothing else."""
        selected = _select(
            markets=[_market(8, 1, external_id="SOMETHING-ELSE")],
            events=[_suspended_event(1)],
            outcomes=[(1, 8, 0.15, 0.16, 0.99)],
        )
        assert selected == set()

    def test_a_gap_well_inside_the_threshold_does_not_select(self):
        """The constant is a real bound, not decoration: a book that disagrees
        by HALF of it is left alone.

        Both this and its sibling below are computed FROM `FROZEN_BOOK_GAP`
        rather than transcribing 0.10, so widening the constant moves the guard
        with it instead of silently passing. They deliberately do NOT probe the
        exact boundary: `0.25 - (0.14 + 0.16)/2` is `0.09999999999999998` in
        binary float, so an "exactly at the threshold" case is decided by the
        representation rather than by the comparison, and it survives flipping
        `>` to `>=` — a test that cannot tell those apart should not claim to.
        """
        gap = sweep.FROZEN_BOOK_GAP / 2
        selected = _select(
            markets=[_market(9, 1)],
            events=[_suspended_event(1)],
            outcomes=[(1, 9, 0.14, 0.16, 0.15 + gap)],
        )
        assert selected == set()

    def test_a_gap_well_past_the_threshold_selects(self):
        """The other side of the same bound."""
        gap = sweep.FROZEN_BOOK_GAP * 2
        selected = _select(
            markets=[_market(10, 1)],
            events=[_suspended_event(1)],
            outcomes=[(1, 10, 0.14, 0.16, 0.15 + gap)],
        )
        assert selected == {10}


class TestTheSpecimenReachesTheWrite:
    """End to end on the specimen's row: asked, derived, written — no grade."""

    def test_the_specimen_is_written_resolved(self):
        report, _, updates, venue = _drive()

        assert venue.asked == [SPECIMEN_TICKER]
        assert updates and updates[0]["venue_settled"] is True
        assert report.get("terminal") != "failed"

    def test_the_write_carries_no_grade(self):
        """CAL-P061 / #1852. Widening WHICH rows reach the shared write must not
        widen WHAT it writes."""
        _, _, updates, _ = _drive()

        assert updates
        for params in updates:
            assert "is_winner" not in params
            assert "current_probability" not in params
            assert "result" not in params
        assert "is_winner" not in sweep.UPDATE_SQL
        assert "current_probability" not in sweep.UPDATE_SQL

    def test_a_market_the_venue_still_lists_open_is_asked_and_not_written(self):
        """The screen is not a verdict. The 4 in 30 the venue still calls
        `active` come out of `UPDATE_SQL` byte-identical on `status`."""
        _, _, updates, venue = _drive(statuses=("active", "active", "active"))

        assert venue.asked == [SPECIMEN_TICKER]
        assert updates and updates[0]["venue_settled"] is False

    def test_the_report_names_the_new_band(self):
        """A count handed over without the window that makes it a rate is not a
        measurement (LAT-P024)."""
        report = _drive()[0]

        assert report["suspended_window_hours"] == sweep.SUSPENDED_EVENT_WINDOW_HOURS
        assert report["frozen_gap"] == sweep.FROZEN_BOOK_GAP
        assert report["suspended_floor"].startswith("2026-")
