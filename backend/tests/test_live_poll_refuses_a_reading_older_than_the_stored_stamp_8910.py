"""#8910 — after a goal, the two-minute poll stops putting the pre-goal price back.

## the ship, as the reader sees it

Czechia v Croatia, 2026-09-26 (event 15311809). Croatia scored; the WebSocket
lane stamped Kalshi at 0.035 at 19:51:23Z. At 19:52:05Z the two-minute poll
stamped Kalshi 0.155 — byte-equal to the socket's 19:50:14Z value, the price
from BEFORE the goal — and the held page's headline went 4% -> 10% for 12.6 s.
At the equalizer the same beat did it again the other way: 0.035 stored over
0.135-0.155 socket rows, 80 s of "Czechia 9%" instead of 15%.

## the mechanism

The poll derives its blend from the outcome rows it loaded (or re-priced from
REST) when the pass BEGAN, then runs its stamp stage up to minutes later over
those in-memory rows. Its stamp is an observation time (#4028/#5661), so the
stale reading carries an OLDER stamp than the one the socket already stored —
the ordering signal was on the row the whole time; nothing compared it.

## the arms

* ship: a reading whose rows were last seen before the stored stamp is refused
  — no hero stamp, no chart point;
* ship, fetched variant: the pass re-priced the leg from REST before the socket
  wrote (the pass's task-entry clock is its observation time);
* control: the same beat with the stored stamp OLDER than the reading still
  writes both — the refusal is a refusal, not a harness that writes nothing;
* abstain: a stored bare float (no stamp) and an outcome that cannot say when
  it was seen both write as before. Unknown is not stale;
* atomic (independent review, 2026-09-26): the read the comparison is made on
  takes the event row's lock and holds it to the write's commit. Unlocked, a
  socket stamp landing between read and write is never compared, and the
  whole-column write erases it and any sibling stamped in the gap;
* release: a REFUSED reading lets go of that lock at once (commit before the
  next statement), so the socket is never held behind a reading we dropped.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.tasks import snapshots as _snapshots
from app.utils import aggregation as _aggregation
from app.utils.aggregation import reading_predates_stored_entry

from tests.test_live_poll_commit_boundary_5682 import (  # noqa: E402
    _Event,
    _KalshiService,
    _Outcome,
    _Population,
    _Result,
    _Session,
    _leg,
    _now,
    _run,
)
from tests.test_live_poll_settled_speaker_call_site_6608 import (  # noqa: E402
    TICKER,
    _Market,
    _disable_inversion,
)


class _StoredSession(_Session):
    """The 5682 session, plus the event's stored `win_probability_sources`."""

    def __init__(self, generations, stored):
        super().__init__(generations)
        self._stored = stored
        self.stored_reads = []

    async def execute(self, stmt, params=None):
        result = await super().execute(stmt, params)
        if self.journal[-1] == ("execute", "select:win_probability_sources"):
            self.stored_reads.append(stmt)
            return _Result(scalar_value=self._stored)
        return result


def _beat(*, last_seen) -> _Population:
    market = _Market(1, status="open")
    event = _Event(101)
    outcome = _Outcome(1001, 1, f"{TICKER}-LAR", "Los Angeles R")
    # The pre-goal price the pass is holding.
    outcome.current_probability = 0.155
    outcome.last_updated = last_seen
    return _Population([(market, event)], [outcome])


async def _written(monkeypatch, population, stored, *, venue_legs=()):
    """Run the REAL beat; return (hero values stamped, chart points written)."""
    stamped: list[float] = []
    points: list[float] = []
    real_stamp = _aggregation.stamp_source_reading

    def _record_stamp(existing, source, value, **kwargs):
        stamped.append(value)
        return real_stamp(existing, source, value, **kwargs)

    async def _record_point(session, event_id, source, home_win_probability, *a, **kw):
        points.append(home_win_probability)
        return object(), False

    monkeypatch.setattr(_aggregation, "stamp_source_reading", _record_stamp)
    monkeypatch.setattr(
        _snapshots, "_create_or_update_win_prob_snapshot", _record_point
    )
    _disable_inversion(monkeypatch)

    session = _StoredSession([population, population], stored)
    service = _KalshiService({TICKER: list(venue_legs)}, [])
    stats = await _run(monkeypatch, session, kalshi=service, blend={})
    _written.last_session = session
    return stamped, points, stats


def _stored_at(when: datetime, value=0.035) -> dict:
    return {"kalshi": {"value": value, "updated_at": when.isoformat()}}


class TestTheBeatRefusesAReadingOlderThanTheStoredStamp:
    async def test_rows_seen_before_the_socket_stamp_are_not_written(
        self, monkeypatch
    ):
        """The ship: the second occurrence's shape (rows ~2.5 min old)."""
        now = _now()
        stamped, points, stats = await _written(
            monkeypatch,
            _beat(last_seen=now - timedelta(seconds=150)),
            _stored_at(now - timedelta(seconds=15)),
        )
        assert stamped == [], f"the pre-goal price was re-stamped: {stamped}"
        assert points == [], f"the pre-goal price got a chart point: {points}"
        assert stats["stale_readings_refused"] == 1

    async def test_a_leg_repriced_before_the_socket_wrote_is_not_written(
        self, monkeypatch
    ):
        """The pass DID fetch, but before the socket's later write.

        The fetch stamps `last_updated` with the pass's entry clock, so a
        socket stamp after entry is a later observation. Production spaces
        these by the pass's run time; here the stored stamp sits just past
        entry to stand in for it.
        """
        stamped, points, stats = await _written(
            monkeypatch,
            _beat(last_seen=None),
            _stored_at(_now() + timedelta(seconds=30)),
            venue_legs=[_leg(f"{TICKER}-LAR", TICKER, bid=0.15, ask=0.16)],
        )
        assert stats["kalshi_outcomes_updated"] == 1, "the fetch arm never fetched"
        assert stamped == [] and points == [], (stamped, points)
        assert stats["stale_readings_refused"] == 1

    async def test_a_stored_stamp_older_than_the_reading_is_replaced(
        self, monkeypatch
    ):
        """Control: same beat, stored stamp BEFORE the rows were seen."""
        now = _now()
        stamped, points, stats = await _written(
            monkeypatch,
            _beat(last_seen=now - timedelta(seconds=60)),
            _stored_at(now - timedelta(seconds=200)),
        )
        assert stamped == [0.155] and points == [0.155], (stamped, points)
        assert stats["stale_readings_refused"] == 0

    async def test_a_stored_bare_float_abstains(self, monkeypatch):
        now = _now()
        stamped, points, _ = await _written(
            monkeypatch,
            _beat(last_seen=now - timedelta(seconds=150)),
            {"kalshi": 0.035},
        )
        assert stamped == [0.155] and points == [0.155], (stamped, points)

    async def test_rows_that_cannot_say_when_seen_abstain(self, monkeypatch):
        stamped, points, _ = await _written(
            monkeypatch,
            _beat(last_seen=None),
            _stored_at(_now() - timedelta(seconds=15)),
        )
        assert stamped == [0.155] and points == [0.155], (stamped, points)


class TestTheComparisonHoldsAtTheCommit:
    async def test_the_compared_read_locks_the_row_until_the_write_commits(
        self, monkeypatch
    ):
        now = _now()
        stamped, _points, _ = await _written(
            monkeypatch,
            _beat(last_seen=now - timedelta(seconds=60)),
            _stored_at(now - timedelta(seconds=200)),
        )
        assert stamped == [0.155], "control: the beat never reached the write"
        session = _written.last_session
        assert len(session.stored_reads) == 1, session.stored_reads
        assert session.stored_reads[0]._for_update_arg is not None, (
            "the stamp is compared on an unlocked read: a socket write between "
            "it and the whole-column write is erased uncompared"
        )
        journal = session.journal
        read_at = journal.index(("execute", "select:win_probability_sources"))
        write_at = journal.index(("execute", "update"), read_at)
        assert ("commit", None) not in journal[read_at:write_at], (
            "the lock is released between the comparison and the write",
            journal[read_at : write_at + 1],
        )

    async def test_a_refusal_lets_go_of_the_lock_before_anything_else(
        self, monkeypatch
    ):
        """Codex review of 104d7bd4: the refused branch kept the row lock."""
        now = _now()
        stamped, _points, stats = await _written(
            monkeypatch,
            _beat(last_seen=now - timedelta(seconds=150)),
            _stored_at(now - timedelta(seconds=15)),
        )
        assert stats["stale_readings_refused"] == 1 and stamped == [], (
            "control: the beat never refused"
        )
        journal = _written.last_session.journal
        read_at = journal.index(("execute", "select:win_probability_sources"))
        assert journal[read_at + 1] == ("commit", None), (
            "the refused reading's row lock is carried into the next statement",
            journal[read_at : read_at + 3],
        )


class TestTheHelper:
    T = datetime(2026, 9, 26, 19, 51, 23, 817530, tzinfo=timezone.utc)

    def test_the_specimen(self):
        # 19:52:05's reading was last seen no later than 19:51:08, the Kalshi
        # row's price change; the socket had stored 19:51:23.
        stored = {"kalshi": {"value": 0.035, "updated_at": self.T.isoformat()}}
        seen = datetime(2026, 9, 26, 19, 51, 8, tzinfo=timezone.utc)
        assert reading_predates_stored_entry(stored, "kalshi", seen) is True

    def test_equal_and_later_are_admitted(self):
        stored = {"kalshi": {"value": 0.035, "updated_at": self.T.isoformat()}}
        assert reading_predates_stored_entry(stored, "kalshi", self.T) is False
        later = self.T + timedelta(seconds=1)
        assert reading_predates_stored_entry(stored, "kalshi", later) is False

    def test_it_reads_only_its_own_source(self):
        stored = {"polymarket": {"value": 0.04, "updated_at": self.T.isoformat()}}
        early = self.T - timedelta(minutes=5)
        assert reading_predates_stored_entry(stored, "kalshi", early) is False

    def test_abstentions(self):
        early = self.T - timedelta(minutes=5)
        assert reading_predates_stored_entry(None, "kalshi", early) is False
        assert reading_predates_stored_entry({"kalshi": 0.03}, "kalshi", early) is False
        assert reading_predates_stored_entry(
            {"kalshi": {"value": 0.03, "updated_at": "garbage"}}, "kalshi", early
        ) is False
        stored = {"kalshi": {"value": 0.035, "updated_at": self.T.isoformat()}}
        assert reading_predates_stored_entry(stored, "kalshi", None) is False

    def test_a_naive_observation_is_read_as_utc(self):
        stored = {"kalshi": {"value": 0.035, "updated_at": self.T.isoformat()}}
        naive = (self.T - timedelta(seconds=10)).replace(tzinfo=None)
        assert reading_predates_stored_entry(stored, "kalshi", naive) is True
