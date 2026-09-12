"""Discovery advances the betting consensus instead of only writing snapshots (#5426).

MEASURED on production, 2026-09-12 03:00-03:15Z:

    upcoming events with a `betting` key, sampled n=150
      newest odds_snapshots row NEWER than betting.updated_at by >6h :  42
      ... by >24h                                                    :  14
      worst                                                          : 130.5h

    the split is by LEAGUE, all-or-nothing, and the cause is a population gap:

      soccer_epl              2 events inside +/-6h -> polled -> 0 of 7 stale
      soccer_england_league1  0 events inside +/-6h -> frozen -> 11 of 11 stale

`poll_all_odds` selects SPORTS having an event within +/-6h of now, then refreshes
every event that sport returns. A league with no fixture in that window is never
polled, so its `betting` value AND `updated_at` freeze. Meanwhile `_discover_events`
kept fetching that league's odds on its tier gate (:05/:35, 2-4h for the long tail)
and wrote `odds_snapshots` rows while discarding the consensus.

Specimen from the issue: event 15297691 (Aston Villa v Nottingham Forest) sat at
betting 0.6339 stamped 2026-09-06T17:27Z while nine books quoted a devigged
0.5741-0.5872 five days later — 5.3 points wrong. It self-healed only once an EPL
fixture entered the +/-6h window.

Two hazards make the naive "just call the shared writer" fix WRONG, and both are
guarded below. Discovery fetches `regions="us", markets="h2h"` to save 5/6 of the
Odds API quota, so it is a PARTIAL-COVERAGE caller:

  1. `_maybe_set_opening_odds` writes spread and total unconditionally once it has
     a home probability. An h2h-only caller has neither, so it would NULL an
     opening spread/total captured earlier by a full-markets poll.
  2. Ruling 051 drops `betting` under BETTING_BOOK_FLOOR because books PULL the
     moneyline when a game goes out of reach. A narrow fetch sees few books
     because of what it ASKED FOR — dropping on that deletes a good consensus.
"""

import inspect
from datetime import datetime, timezone

import pytest

from app.tasks.odds_polling import BETTING_BOOK_FLOOR, _ingest_event_odds

# Always pre-kickoff, so `_maybe_set_opening_odds` cannot decline for a reason
# unrelated to what these tests are asserting.
FUTURE = datetime(2099, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fakes. `_ingest_event_odds` needs a session that records Core update() calls,
# a snapshot factory, and an event row.
# ---------------------------------------------------------------------------


class _FakeSnapshot:
    def __init__(self, home_prob, spread=None, over_under=None):
        self.home_win_probability = home_prob
        self.away_win_probability = (1 - home_prob) if home_prob else None
        self.home_spread = spread
        self.over_under = over_under


class _FakeEvent:
    def __init__(self, sources=None, status="scheduled"):
        self.id = 15297691
        self.win_probability_sources = sources
        self.status = status


class _RecordingSession:
    """Captures every Core update() the writer executes, by target column."""

    def __init__(self, status="scheduled"):
        self.sources_writes: list[dict] = []
        self.opening_writes: list[dict] = []
        self._status = status

    async def execute(self, stmt):
        params = getattr(stmt, "_values", None) or {}
        rendered = {str(k).split(".")[-1]: v for k, v in params.items()}
        vals = {
            k: (getattr(v, "value", v)) for k, v in rendered.items()
        }
        if "win_probability_sources" in vals:
            self.sources_writes.append(vals["win_probability_sources"])
        elif any(k.startswith("opening_") for k in vals):
            self.opening_writes.append(vals)
        return _ScalarResult(self._status)

    def add(self, _obj):
        pass


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalar(self):
        return self._value


@pytest.fixture
def patched_snapshots(monkeypatch):
    """Make `_create_or_update_snapshot` return a book's quote, in order."""

    def _install(probs, spread=None, over_under=None):
        queue = list(probs)

        async def _fake(session, event_id, bookmaker, event_data, snapshot_cache=None):
            return _FakeSnapshot(queue.pop(0), spread, over_under), True

        monkeypatch.setattr(
            "app.tasks.odds_polling._create_or_update_snapshot", _fake
        )
        return {"bookmakers": [{"key": f"b{i}"} for i in range(len(probs))]}

    return _install


# ---------------------------------------------------------------------------
# 1. The ship: discovery advances value AND stamp.
# ---------------------------------------------------------------------------


class TestDiscoveryAdvancesTheConsensus:
    @pytest.mark.asyncio
    async def test_partial_caller_writes_value_and_stamp_when_books_suffice(
        self, patched_snapshots
    ):
        """The frozen-league case, fixed: three books is a consensus.

        This is the whole ship. Before #5426 discovery wrote the snapshots and
        returned, leaving the stale value and the stale stamp in place.
        """
        event_data = patched_snapshots([0.57, 0.58, 0.59])
        event = _FakeEvent(
            {"betting": {"value": 0.6339, "updated_at": "2026-09-06T17:27:22Z"}}
        )
        session = _RecordingSession()

        await _ingest_event_odds(
            session, event, event_data, FUTURE, {},
            update_opening=False, drop_below_floor=False,
        )

        assert len(session.sources_writes) == 1
        written = session.sources_writes[0]
        # The median of the three books, not the five-day-old 0.6339.
        assert written["betting"]["value"] == pytest.approx(0.58)
        # And the stamp MOVED — this is what un-poisons the recency decay.
        assert written["betting"]["updated_at"] != "2026-09-06T17:27:22Z"
        assert written["betting_book_count"] == 3

    @pytest.mark.asyncio
    async def test_the_stamp_is_what_the_recency_decay_reads(
        self, patched_snapshots
    ):
        """#4028: `updated_at` is an OBSERVATION time.

        The observation happened here — books were read — so recording it is the
        honest act. Leaving it unstamped is what made a bookkeeping gap read as
        "the sportsbooks have gone quiet" and floored betting's weight (#1999).
        """
        event_data = patched_snapshots([0.40, 0.41, 0.42])
        event = _FakeEvent({"betting": {"value": 0.9, "updated_at": "2020-01-01T00:00:00Z"}})
        session = _RecordingSession()

        await _ingest_event_odds(
            session, event, event_data, FUTURE, {},
            update_opening=False, drop_below_floor=False,
        )

        stamp = session.sources_writes[0]["betting"]["updated_at"]
        assert stamp.startswith("20")
        assert "2020" not in stamp


# ---------------------------------------------------------------------------
# 2. Hazard one: the partial caller must not DROP a good consensus.
# ---------------------------------------------------------------------------


class TestPartialCallerDoesNotDropBelowTheFloor:
    @pytest.mark.asyncio
    async def test_narrow_fetch_under_the_floor_leaves_the_entry_alone(
        self, patched_snapshots
    ):
        """The regression the naive fix would have shipped.

        Discovery asking one region for one market can see 2 books on an event a
        full poll covers with 8. Under ruling 051's drop that deletes a healthy
        consensus on every discovery pass — the value would vanish and reappear.
        """
        event_data = patched_snapshots([0.55, 0.56])  # 2 < floor of 3
        event = _FakeEvent(
            {"betting": {"value": 0.61, "updated_at": "2026-09-11T12:00:00Z"},
             "betting_book_count": 8}
        )
        session = _RecordingSession()

        await _ingest_event_odds(
            session, event, event_data, FUTURE, {},
            update_opening=False, drop_below_floor=False,
        )

        # Nothing written at all: not the value, not the count.
        assert session.sources_writes == []

    @pytest.mark.asyncio
    async def test_the_narrower_count_does_not_overwrite_the_stored_one(
        self, patched_snapshots
    ):
        """The count describes the measurement the VALUE came from.

        Writing count=2 beside a value eight books stand behind would make the
        count describe a measurement the value never came from — and
        `betting_book_count` is exactly what a reader consults to judge the
        value's weight.
        """
        event_data = patched_snapshots([0.55, 0.56])
        event = _FakeEvent(
            {"betting": {"value": 0.61, "updated_at": "2026-09-11T12:00:00Z"},
             "betting_book_count": 8}
        )
        session = _RecordingSession()

        await _ingest_event_odds(
            session, event, event_data, FUTURE, {},
            update_opening=False, drop_below_floor=False,
        )

        assert all(
            w.get("betting_book_count") != 2 for w in session.sources_writes
        )

    @pytest.mark.asyncio
    async def test_a_full_coverage_caller_still_drops_ruling_051(
        self, patched_snapshots
    ):
        """The other direction (gotcha #43) — the default must not move.

        Ruling 051 is untouched for `poll_all_odds`: below the floor the key is
        REMOVED, not frozen, because there a thin book count really is the
        market thinning. If this goes red the ship has widened into the ruling.
        """
        event_data = patched_snapshots([0.1347])  # the #1841 specimen, 1 book
        event = _FakeEvent({"betting": {"value": 0.1347, "updated_at": "x"}})
        session = _RecordingSession()

        await _ingest_event_odds(session, event, event_data, FUTURE, {})

        assert len(session.sources_writes) == 1
        written = session.sources_writes[0]
        assert "betting" not in written
        assert written["betting_book_count"] == 1


# ---------------------------------------------------------------------------
# 3. Hazard two: the partial caller must not WIPE the opening spread/total.
# ---------------------------------------------------------------------------


class TestPartialCallerDoesNotWipeOpeningOdds:
    @pytest.mark.asyncio
    async def test_h2h_only_caller_writes_no_opening_odds_at_all(
        self, patched_snapshots
    ):
        """`_maybe_set_opening_odds` sets spread and total UNCONDITIONALLY.

        It returns early only when the home probability is None. An h2h-only
        fetch HAS a home probability and has neither spread nor total, so
        calling it would write NULL over both — a silent paired-field wipe on
        every discovery pass (opening lines are ~93% populated today).
        """
        event_data = patched_snapshots([0.57, 0.58, 0.59], spread=None, over_under=None)
        event = _FakeEvent({})
        session = _RecordingSession()

        await _ingest_event_odds(
            session, event, event_data, FUTURE, {},
            update_opening=False, drop_below_floor=False,
        )

        assert session.opening_writes == []

    @pytest.mark.asyncio
    async def test_a_full_coverage_caller_still_writes_opening_odds(
        self, patched_snapshots
    ):
        """The other direction: the poller's behaviour is unchanged."""
        event_data = patched_snapshots(
            [0.57, 0.58, 0.59], spread=-1.5, over_under=2.5
        )
        event = _FakeEvent({})
        session = _RecordingSession()

        await _ingest_event_odds(session, event, event_data, FUTURE, {})

        assert len(session.opening_writes) == 1
        assert session.opening_writes[0]["opening_home_spread"] == -1.5
        assert session.opening_writes[0]["opening_over_under"] == 2.5


# ---------------------------------------------------------------------------
# 4. Wiring — the population gap this closes is a property of the CALL SITE,
#    and a behavioural test above cannot see the call site being removed.
# ---------------------------------------------------------------------------


class TestDiscoveryIsWiredToTheSharedWriter:
    @property
    def src(self):
        from app.tasks import sports

        return inspect.getsource(sports._discover_events)

    def test_discovery_calls_the_shared_writer(self):
        """If this goes red, discovery has gone back to snapshots-only and the
        whole frozen-league class is live again."""
        assert "_ingest_event_odds(" in self.src

    def test_discovery_declares_itself_a_partial_caller(self):
        """Both flags, explicitly — a default here would trip a hazard above."""
        src = self.src
        assert "update_opening=False" in src
        assert "drop_below_floor=False" in src

    def test_the_floor_is_still_three(self):
        assert BETTING_BOOK_FLOOR == 3

    def test_defaults_preserve_full_coverage_behaviour(self):
        """The two existing callers pass neither flag, so the defaults ARE the
        poller's contract. Pinned from the other side (a default flipped to
        False would silently disable ruling 051 fleet-wide)."""
        sig = inspect.signature(_ingest_event_odds)
        assert sig.parameters["update_opening"].default is True
        assert sig.parameters["drop_below_floor"].default is True
