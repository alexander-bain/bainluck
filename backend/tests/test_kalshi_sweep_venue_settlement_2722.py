"""#2722 — a market Kalshi has already settled stops claiming to be open.

WHAT WAS WRONG, MEASURED AT THE VENUE. 179 Kalshi events sampled by
``md5(external_id)`` from the 10,187 rows we hold as ``status='open'`` with a
future date, live public API, 2026-09-02:

    cohort                          n     close_time in the past
    ---------------------------------------------------------------
    settled at venue               49     39  (80%)
    ...finalized EARLY             10      0   (0%)

CAL-P989 shipped the 80%: a date predicate (``status <> 'resolved' AND
resolution_date < now()``) reaches every row whose ``close_time`` has gone past.
**It can never reach the other 20%.** A market Kalshi finalises before its
scheduled close keeps a future ``close_time``, so no date field moves and no date
predicate selects it. Only the venue's own ``status`` says what happened — and
the sweep was reading that status off every leg of every candidate it fetched and
throwing it away, deriving dates from the same payload.

The user-visible cost is #2660's card: the row stays ``open``, so the site goes on
rendering a dead last-trade price as a live probability for a market that is over.

WHAT THIS FILE HOLDS.

1. :func:`derive_venue_settlement` — the pure read. All legs terminal or it is not
   a settlement; an absent status is not a settlement; ``closed`` is not a
   settlement.
2. The composed path: a row whose stored date is a MONTH IN THE FUTURE and whose
   venue payload moves no date at all still reaches the write, with the settlement
   bind on. That is the acceptance line — "a guard that fails if the settlement
   path can only be entered via a date predicate" — stated as a run rather than as
   prose.
3. The statement itself, executed against a real seeded table: ``status`` becomes
   ``resolved``, ``settled_at`` is stamped, the date columns we already hold are
   NOT blanked, and the controls (venue open, venue partially settled) come out
   byte-identical.

CLOCK DISCIPLINE (gotcha #44). ``run_backfill`` takes ``now`` as a parameter and
every fixture here pins it to a literal, so no assertion can flip with the
calendar.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text

from app.tasks import kalshi_resolution_sweep as sweep
from app.utils.kalshi_resolution_window import (
    VENUE_SETTLED_STATUSES,
    derive_venue_settlement,
)

#: The instant every assertion here is measured from. A literal, never `utcnow()`.
NOW = datetime(2026, 9, 5, 19, 30, tzinfo=timezone.utc)

#: A month out. This is the whole point of the cohort: the row's stored date says
#: nothing has happened yet, and the venue says the market is over.
FUTURE = NOW + timedelta(days=30)


# ---------------------------------------------------------------------------
# 1. The pure read
# ---------------------------------------------------------------------------


class TestTheVenueSettlementRead:
    def test_every_leg_terminal_is_a_settlement(self):
        out = derive_venue_settlement(["finalized", "settled", "finalized"])
        assert out.settled is True
        assert (out.legs_total, out.legs_settled) == (3, 3)
        assert out.reason == "settled"

    def test_one_live_leg_is_not_a_settlement(self):
        """A Kalshi event settles leg by leg; our row is the whole event.

        A tennis set-winner event finalises its first-set leg while the match is
        still being played. Flipping the row on the first terminal leg is #2351's
        defect read from the other direction — one leg's answer written to every
        sibling.
        """
        out = derive_venue_settlement(["finalized", "active"])
        assert out.settled is False
        assert out.reason == "partially_settled"
        assert (out.legs_total, out.legs_settled) == (2, 1)

    def test_closed_is_not_settled(self):
        """Trading stopped is not "we know what happened".

        `status='resolved'` is the gate a dozen grading and calibration queries
        read, so a market whose result is still pending must not open them.
        """
        out = derive_venue_settlement(["closed", "closed"])
        assert out.settled is False
        assert out.reason == "open_at_venue"
        assert "closed" not in VENUE_SETTLED_STATUSES

    def test_an_absent_status_is_not_a_settlement(self):
        assert derive_venue_settlement(["finalized", None]).reason == "status_absent"
        assert derive_venue_settlement(["finalized", ""]).settled is False

    def test_no_legs_is_not_a_settlement(self):
        """Gotcha #53: an empty list is a response shape, not a fact."""
        out = derive_venue_settlement([])
        assert out.settled is False
        assert out.reason == "no_legs"

    def test_the_venues_own_casing_and_padding_are_read(self):
        assert derive_venue_settlement([" Finalized ", "SETTLED"]).settled is True


# ---------------------------------------------------------------------------
# 2. The composed path — entered without a date predicate
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, recorder, rows, totals):
        self._recorder = recorder
        self._rows = rows
        self._totals = totals
        self.committed = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        self._recorder.append((sql, params))
        if sql.strip().upper().startswith("UPDATE"):
            return _FakeResult([])
        if "count(*)" in sql:
            return _FakeResult([self._totals])
        return _FakeResult(self._rows)

    async def commit(self):
        self.committed += 1


class _Venue:
    """One event, whose legs carry exactly the fields the real payload carries.

    Shape taken from the live public API, 2026-09-05
    (``/events?status=settled&with_nested_markets=true``), e.g.
    ``KXG7LEADEROUT-45JAN01-MCAR``: ``status`` "finalized", ``close_time`` and
    ``expiration_time`` both present, ``result`` "no" — which this rail reads and
    must never write.
    """

    def __init__(self, legs):
        self._legs = legs
        self.asked: list[str] = []
        self.closed = False

    async def get_event(self, ticker, with_nested_markets=True):
        self.asked.append(ticker)
        return {"markets": list(self._legs)}

    async def close(self):
        self.closed = True


#: The #2722 row: we hold a date a month out, the venue holds the same date, and
#: the venue says the market is over. NOTHING about the dates changes, so every
#: date-shaped path is a no-op on it.
EARLY_FINALIZED_ROW = (
    77001,
    "KXATPEXACTMATCH-26AUG30BERTAB",
    FUTURE,  # stored resolution_date, in the FUTURE
    NOW - timedelta(days=6),  # commence_time
    5,  # market_tier
)

_FUTURE_ISO = FUTURE.isoformat().replace("+00:00", "Z")


def _legs(status, *, close=_FUTURE_ISO, expiry=_FUTURE_ISO):
    leg = {"ticker": "KXATPEXACTMATCH-26AUG30BERTAB-BER31", "status": status}
    if close is not None:
        leg["close_time"] = close
    if expiry is not None:
        leg["expiration_time"] = expiry
    if status in VENUE_SETTLED_STATUSES:
        # The venue sends the grade on the same payload. It must be visible to
        # this test and invisible to the write (#1852 / #2722's own line).
        leg["result"] = "yes"
    return [leg, dict(leg)]


def _drive(legs, *, apply=True, rows=(EARLY_FINALIZED_ROW,)):
    recorder: list = []
    venue = _Venue(legs)

    def maker():
        return _FakeSession(recorder, list(rows), (len(rows), 0, 0, len(rows)))

    report = asyncio.run(
        sweep.run_backfill(
            session_maker=maker,
            client_factory=lambda: venue,
            limit=500,
            apply=apply,
            now=NOW,
        )
    )
    updates = [p for s, p in recorder if s.strip().upper().startswith("UPDATE")]
    return report, updates, venue


class TestSettlementIsNotReachedThroughADate:
    """#2722's acceptance line, as a run."""

    def test_a_future_dated_row_the_venue_has_finalized_still_reaches_the_write(self):
        report, updates, venue = _drive(_legs("finalized"))

        assert venue.asked == ["KXATPEXACTMATCH-26AUG30BERTAB"]
        stats = report["stats"]
        assert stats["moved_earlier"] == 0 and stats["newly_past"] == 0, (
            "RED-FIRST ANCHOR: no date moves on this row — that is what makes it "
            "the 20% cohort. If a date moved, the fixture is no longer the case "
            "#2722 reports and this whole class proves nothing."
        )
        assert stats["unchanged"] == 1
        assert stats["venue_settled"] == 1
        assert len(updates) == 1
        assert updates[0]["venue_settled"] is True
        assert updates[0]["id"] == 77001

    def test_the_write_carries_no_grade(self):
        """The venue sent `result: yes` on the same payload. It stops here."""
        _report, updates, _venue = _drive(_legs("finalized"))

        assert set(updates[0]) == {
            "id",
            "resolution_date",
            "expiration_time",
            "venue_settled",
            "updated_at",
        }
        for forbidden in ("is_winner", "result", "probability", "price"):
            assert forbidden not in updates[0]

    def test_a_live_market_is_not_flipped(self):
        report, updates, _venue = _drive(_legs("active"))

        assert report["stats"]["venue_settled"] == 0
        assert updates[0]["venue_settled"] is False, (
            "the venue still lists this market; the settlement bind must be OFF "
            "or every swept row is marked over whether Kalshi says so or not"
        )

    def test_a_half_settled_event_is_not_flipped(self):
        legs = _legs("finalized")
        legs[1]["status"] = "active"
        report, updates, _venue = _drive(legs)

        assert updates[0]["venue_settled"] is False
        assert report["stats"]["venue_partially_settled"] == 1
        assert report["stats"]["venue_settled"] == 0

    def test_a_settled_row_with_no_derivable_date_is_still_written(self):
        """The settlement fact does not depend on our date columns.

        Before this ship a payload with no usable timestamps returned early and
        wrote nothing at all, so an event the venue had finalised but sent no
        dates for was unreachable twice over.
        """
        report, updates, _venue = _drive(_legs("settled", close=None, expiry=None))

        stats = report["stats"]
        assert stats["settled_without_date"] == 1
        assert stats["unresolvable_at_venue"] == 1
        assert len(updates) == 1
        assert updates[0]["venue_settled"] is True
        assert updates[0]["resolution_date"] is None
        assert "batch_fully_unresolvable" not in report, (
            "every row was date-unresolvable, but one WAS written — the batch "
            "note claims nothing could be, and an operator reading it would "
            "advance the offset past a row that just moved"
        )

    def test_an_unresolvable_open_row_still_writes_nothing(self):
        """The control for the case above: no date AND no settlement is a skip."""
        report, updates, _venue = _drive(_legs("active", close=None, expiry=None))

        assert updates == []
        assert report["stats"]["settled_without_date"] == 0
        assert report["stats"]["unresolvable_at_venue"] == 1
        assert "batch_fully_unresolvable" in report


# ---------------------------------------------------------------------------
# 3. The statement, executed
# ---------------------------------------------------------------------------

CREATE_TABLE = """
    CREATE TABLE futures_markets (
        id INTEGER PRIMARY KEY,
        external_id TEXT,
        source TEXT,
        status TEXT,
        market_tier INTEGER,
        commence_time TEXT,
        resolution_date TEXT,
        expiration_time TEXT,
        settled_at TEXT,
        updated_at TEXT
    )
"""

INSERT = """
    INSERT INTO futures_markets
        (id, external_id, source, status, market_tier, commence_time,
         resolution_date, expiration_time, settled_at, updated_at)
    VALUES (:id, 'KXATPEXACTMATCH-26AUG30BERTAB', 'kalshi', 'open', 5,
            :commence_time, :resolution_date, :expiration_time, :settled_at,
            :updated_at)
"""


@pytest.fixture
def seeded_row():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(CREATE_TABLE))
        conn.execute(
            text(INSERT),
            {
                "id": 77001,
                "commence_time": (NOW - timedelta(days=6)).isoformat(),
                "resolution_date": FUTURE.isoformat(),
                "expiration_time": FUTURE.isoformat(),
                "settled_at": None,
                "updated_at": (NOW - timedelta(days=4)).isoformat(),
            },
        )
    return engine


def _apply(engine, params):
    with engine.begin() as conn:
        conn.execute(text(sweep.UPDATE_SQL), params)
        return conn.execute(
            text(
                "SELECT status, settled_at, resolution_date, expiration_time, "
                "updated_at FROM futures_markets WHERE id = 77001"
            )
        ).first()


class TestTheStatementItself:
    """Executed against a seeded table, not asserted against its own text."""

    def test_the_settled_row_stops_being_open_and_is_stamped(self, seeded_row):
        row = _apply(
            seeded_row,
            {
                "id": 77001,
                "resolution_date": FUTURE.isoformat(),
                "expiration_time": FUTURE.isoformat(),
                "venue_settled": True,
                "updated_at": NOW.isoformat(),
            },
        )
        assert row[0] == "resolved"
        assert row[1] == NOW.isoformat(), (
            "settled_at is stamped from the run's bound instant, so the column "
            "records one clock the caller controls (gotcha #44)"
        )

    def test_an_existing_settled_at_is_not_overwritten(self, seeded_row):
        with seeded_row.begin() as conn:
            conn.execute(
                text("UPDATE futures_markets SET settled_at = :t WHERE id = 77001"),
                {"t": (NOW - timedelta(days=3)).isoformat()},
            )
        row = _apply(
            seeded_row,
            {
                "id": 77001,
                "resolution_date": FUTURE.isoformat(),
                "expiration_time": FUTURE.isoformat(),
                "venue_settled": True,
                "updated_at": NOW.isoformat(),
            },
        )
        assert row[1] == (NOW - timedelta(days=3)).isoformat(), (
            "the earlier observation is the better one; re-stamping it every "
            "sweep would make settled_at mean 'when we last looked'"
        )

    def test_a_settlement_with_no_date_does_not_blank_the_dates(self, seeded_row):
        row = _apply(
            seeded_row,
            {
                "id": 77001,
                "resolution_date": None,
                "expiration_time": None,
                "venue_settled": True,
                "updated_at": NOW.isoformat(),
            },
        )
        assert row[0] == "resolved"
        assert row[2] == FUTURE.isoformat(), (
            "RED-FIRST ANCHOR: a plain assignment here blanks a date we already "
            "hold in order to record a status — the COALESCE is what makes the "
            "no-date settlement safe to write"
        )
        assert row[3] == FUTURE.isoformat()

    def test_an_unsettled_write_leaves_status_and_settled_at_alone(self, seeded_row):
        earlier = (NOW - timedelta(days=1)).isoformat()
        row = _apply(
            seeded_row,
            {
                "id": 77001,
                "resolution_date": earlier,
                "expiration_time": FUTURE.isoformat(),
                "venue_settled": False,
                "updated_at": NOW.isoformat(),
            },
        )
        assert row[0] == "open", (
            "the same statement runs for every candidate; a row the venue still "
            "lists must come out of it exactly as it went in, apart from dates"
        )
        assert row[1] is None
        assert row[2] == earlier, "the date half is unchanged by this ship"
