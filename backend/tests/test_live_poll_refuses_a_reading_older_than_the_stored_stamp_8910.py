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

## the other-writers repair (the clock domain)

The comparison is now made against the stored entry's OBSERVATION basis — when
the writer that stored it saw these same rows — and no longer against its
`updated_at`, which the WebSocket lane dates with its publication clock. So:

* clock domain: a stored entry PUBLISHED after this reading's rows were seen,
  but whose rows were seen EARLIER, is replaced (Codex's newer-B control);
* legacy: a stored entry with a stamp and no basis cannot be ordered and
  abstains — the transition state for the minutes after release.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.tasks import snapshots as _snapshots
from app.utils import aggregation as _aggregation
from app.utils.aggregation import (
    OBSERVED_BASIS_KEY,
    OBSERVED_VALUE_KEY,
    stamp_source_reading,
)

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
        _written.last_entry = real_stamp(existing, source, value, **kwargs)
        return _written.last_entry

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


#: The beat's one outcome row (`_beat`), as keyed in an observation basis.
ROW = "1001"


def _stored_at(when: datetime, value=0.035, *, published=None) -> dict:
    """The socket's stored entry: it SAW the row at ``when`` and published at
    ``published`` (default the same instant)."""
    return stamp_source_reading(
        None, "kalshi", value, now=published or when,
        observed_basis={ROW: when.timestamp()},
    )


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

    async def test_a_later_publication_of_an_earlier_observation_is_replaced(
        self, monkeypatch
    ):
        """Clock domain: the socket saw the row BEFORE this reading did but
        published after. Comparing with its publication clock refused the
        genuinely newer reading; the observation basis admits it."""
        now = _now()
        stamped, points, stats = await _written(
            monkeypatch,
            _beat(last_seen=now - timedelta(seconds=60)),
            _stored_at(
                now - timedelta(seconds=90), published=now - timedelta(seconds=15),
            ),
        )
        assert stamped == [0.155] and points == [0.155], (stamped, points)
        assert stats["stale_readings_refused"] == 0

    async def test_a_legacy_stamp_with_no_basis_abstains(self, monkeypatch):
        now = _now()
        stamped, points, _ = await _written(
            monkeypatch,
            _beat(last_seen=now - timedelta(seconds=150)),
            {"kalshi": {"value": 0.035,
                        "updated_at": (now - timedelta(seconds=15)).isoformat()}},
        )
        assert stamped == [0.155] and points == [0.155], (stamped, points)

    async def test_the_written_entry_carries_its_basis(self, monkeypatch):
        """What the next writer compares against is written here."""
        now = _now()
        seen = now - timedelta(seconds=60)
        stamped, _points, _ = await _written(
            monkeypatch, _beat(last_seen=seen), _stored_at(now - timedelta(seconds=200)),
        )
        assert stamped == [0.155]
        entry = _written.last_entry["kalshi"]
        assert entry[OBSERVED_BASIS_KEY] == {ROW: seen.timestamp()}, entry
        assert entry[OBSERVED_VALUE_KEY] == 0.155, entry

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
