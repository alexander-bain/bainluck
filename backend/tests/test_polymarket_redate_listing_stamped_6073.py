"""#6073, the third half: re-date the fixtures ALREADY minted from the listing stamp.

The other two halves are PREVENTION and only reach a mint. This one reaches the
standing population, and `tasks/polymarket.py`'s block above
`REDATE_LISTING_STAMPED_SQL` carries the production census these tests are built
from (2026-09-14, the whole band):

    band (commence_time_source='polymarket', live|suspended, still linked)   827
      venue start LATER than ours                                     820 (100%)
      venue start EARLIER than ours                                     0
      venue start still in the FUTURE                                 566
      of those 566: carrying a score / period / clock / completed_at    0 each
    groups linking to more than one event                            21 of 895
    groups carrying two different venue_game_start values              0 of 895

Two things are asserted here that a census cannot assert: that each refusal is
REAL (drive the predicate at it), and that the function WRITES what the ship
claims (drive it with a recording session and read the statements back). A rail
that selects correctly and writes the wrong column reads identical from a count.
"""

import ast
import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.tasks import polymarket as poly
from app.tasks.polymarket import (
    REDATE_LISTING_STAMPED_SQL,
    redate_polymarket_listing_stamped_events,
    redate_target,
)
from app.utils.event_completion import (
    POLYMARKET_VENUE_COMMENCE_SOURCE,
    commence_time_is_a_reported_start,
)


NOW = datetime(2026, 9, 14, 6, 0, tzinfo=timezone.utc)


def _utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


# ── The four production specimens of #6073 ───────────────────────────────────
#
# IMPORTED, never re-typed. The ingest half's suite already records these as read
# from the venue (notice 26) and they are the same four rows; two suites in one
# repo quoting different production readings for event 15312412 is exactly the
# drift that makes a later reader trust neither. One definition, so a correction
# to it reaches both halves at once.
#
# Shape: (event_id, our listing stamp, the venue's own start, skew hours). All
# four are ITF tennis; all four rendered "No result reported" for a match nobody
# had played.
from tests.test_polymarket_child_venue_stamp_6073 import SPECIMENS  # noqa: E402


class TestTheDateMoves:
    """The venue's instant replaces the listing stamp, forward only."""

    @pytest.mark.parametrize("event_id,listed,venue,skew", SPECIMENS)
    def test_each_specimen_takes_the_venue_instant(self, event_id, listed, venue, skew):
        decision = redate_target(
            venue_game_start=venue.isoformat(), event_commence=listed, now=NOW,
        )
        assert decision is not None, f"{event_id} was refused"
        target, _status = decision
        assert target == venue

    @pytest.mark.parametrize("event_id,listed,venue,skew", SPECIMENS)
    def test_the_measured_skew_is_what_the_move_closes(
        self, event_id, listed, venue, skew
    ):
        # Guards the specimens themselves: if a later edit mistypes one of these
        # instants, the recorded skew stops matching and this fails rather than
        # silently testing a fixture that never existed.
        measured = (venue - listed).total_seconds() / 3600
        assert round(measured, 1) == skew

    def test_a_backward_move_is_refused(self):
        # Measured 0/820 today. It is refused because moving a start BACKWARD can
        # only make a match that has not happened read as one that has — #6073's
        # own defect, arriving from the other side.
        assert redate_target(
            venue_game_start=_utc(2026, 9, 14, 6, 0).isoformat(),
            event_commence=_utc(2026, 9, 14, 13, 0),
            now=NOW,
        ) is None

    def test_agreement_is_not_a_write(self):
        instant = _utc(2026, 9, 14, 13, 0)
        assert redate_target(
            venue_game_start=instant.isoformat(), event_commence=instant, now=NOW,
        ) is None

    def test_a_naive_column_does_not_raise_and_is_read_as_utc(self):
        # The driver can hand back a naive column; the arithmetic must not blow up
        # on it, and it must not be read as local time.
        decision = redate_target(
            venue_game_start="2026-09-14T13:00:00",
            event_commence=datetime(2026, 9, 13, 19, 12),
            now=NOW,
        )
        assert decision is not None
        assert decision[0] == _utc(2026, 9, 14, 13, 0)

    @pytest.mark.parametrize("bad", [None, "", "not-a-timestamp", "2026-13-45"])
    def test_an_unusable_stamp_writes_nothing(self, bad):
        assert redate_target(
            venue_game_start=bad,
            event_commence=_utc(2026, 9, 13, 19, 12),
            now=NOW,
        ) is None

    def test_a_z_suffixed_stamp_parses(self):
        # What `sub_market_metadata` and the parent row both write.
        decision = redate_target(
            venue_game_start="2026-09-14T13:00:00Z",
            event_commence=_utc(2026, 9, 13, 19, 12),
            now=NOW,
        )
        assert decision is not None
        assert decision[0] == _utc(2026, 9, 14, 13, 0)


class TestEvidenceOfPlayRefusesTheRow:
    """0 of 566 carry any of these today. The guard is for the day one does."""

    @pytest.mark.parametrize(
        "field,value",
        [
            ("home_score", 0),
            ("home_score", 3),
            ("away_score", 0),
            ("away_score", 2),
            ("period", 1),
            ("game_clock", "12:00"),
        ],
    )
    def test_any_reported_play_signal_refuses(self, field, value):
        kwargs = {
            "venue_game_start": _utc(2026, 9, 14, 13, 0).isoformat(),
            "event_commence": _utc(2026, 9, 13, 19, 12),
            "now": NOW,
            field: value,
        }
        assert redate_target(**kwargs) is None

    def test_a_zero_score_is_evidence_too(self):
        # 0-0 is a REPORTED score, not an absent one: something watched this game
        # and said nobody had scored. The measured population carries NULL, not 0.
        assert redate_target(
            venue_game_start=_utc(2026, 9, 14, 13, 0).isoformat(),
            event_commence=_utc(2026, 9, 13, 19, 12),
            now=NOW,
            home_score=0,
            away_score=0,
        ) is None

    def test_with_no_signals_at_all_the_row_moves(self):
        # The complement of the six above — proves they are refusing on the signal
        # and not on something the fixture shares with them.
        assert redate_target(
            venue_game_start=_utc(2026, 9, 14, 13, 0).isoformat(),
            event_commence=_utc(2026, 9, 13, 19, 12),
            now=NOW,
            home_score=None,
            away_score=None,
            period=None,
            game_clock=None,
        ) is not None


class TestGotcha46IsNeverInverted:
    """`completed_at >= commence_time` is an invariant; violating it means a
    cross-event data merge. Refused, never clamped."""

    def test_a_target_past_completed_at_is_refused(self):
        assert redate_target(
            venue_game_start=_utc(2026, 9, 14, 13, 0).isoformat(),
            event_commence=_utc(2026, 9, 13, 19, 12),
            now=NOW,
            completed_at=_utc(2026, 9, 14, 10, 0),
        ) is None

    def test_a_target_before_completed_at_is_allowed(self):
        decision = redate_target(
            venue_game_start=_utc(2026, 9, 14, 8, 0).isoformat(),
            event_commence=_utc(2026, 9, 13, 19, 12),
            now=NOW,
            completed_at=_utc(2026, 9, 14, 10, 0),
        )
        assert decision is not None
        assert decision[0] == _utc(2026, 9, 14, 8, 0)

    def test_completed_at_exactly_at_the_target_is_allowed(self):
        instant = _utc(2026, 9, 14, 10, 0)
        decision = redate_target(
            venue_game_start=instant.isoformat(),
            event_commence=_utc(2026, 9, 13, 19, 12),
            now=NOW,
            completed_at=instant,
        )
        assert decision is not None


class TestTheStatusRidesOnlyWhenTheStartIsStillAhead:

    def test_a_future_start_goes_back_to_scheduled(self):
        # The ship: 566 rows rendering "No result reported" for matches that have
        # not begun.
        decision = redate_target(
            venue_game_start=_utc(2026, 9, 14, 13, 0).isoformat(),
            event_commence=_utc(2026, 9, 13, 19, 12),
            now=NOW,
        )
        assert decision == (_utc(2026, 9, 14, 13, 0), "scheduled")

    def test_a_past_start_moves_the_date_and_leaves_the_status(self):
        # 261 of the 827. The date was still wrong; whether the row is live,
        # finished or stale is not something this rail can know.
        decision = redate_target(
            venue_game_start=_utc(2026, 9, 14, 5, 0).isoformat(),
            event_commence=_utc(2026, 9, 13, 19, 12),
            now=NOW,
        )
        assert decision == (_utc(2026, 9, 14, 5, 0), None)

    def test_the_status_boundary_is_now(self):
        assert redate_target(
            venue_game_start=NOW.isoformat(),
            event_commence=NOW - timedelta(hours=5),
            now=NOW,
        )[1] is None
        assert redate_target(
            venue_game_start=(NOW + timedelta(seconds=1)).isoformat(),
            event_commence=NOW - timedelta(hours=5),
            now=NOW,
        )[1] == "scheduled"

    def test_the_source_it_writes_is_a_reported_start(self):
        # The whole point of moving the row back to `scheduled`: the ordinary
        # promotion gate must be willing to take it live at the real hour. If
        # `polymarket_venue` were a derived source, the rescheduled rows would
        # never go live again and this ship would trade one defect for another.
        assert commence_time_is_a_reported_start(POLYMARKET_VENUE_COMMENCE_SOURCE)


# ── Driving the rail itself ──────────────────────────────────────────────────


class _RecordingResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _RecordingSession:
    """Returns canned SELECT rows, then records every statement written."""

    def __init__(self, rows):
        self._rows = rows
        self.selected_params = None
        self.writes = []
        self.commits = 0

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "UPDATE events" in sql:
            self.writes.append((sql, params))
            return _RecordingResult([])
        self.selected_params = params
        return _RecordingResult(self._rows)

    async def commit(self):
        self.commits += 1


class _Ctx:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False


def _row(**kw):
    base = dict(
        event_id=1,
        event_commence=_utc(2026, 9, 13, 19, 12),
        completed_at=None,
        home_score=None,
        away_score=None,
        period=None,
        game_clock=None,
        status="suspended",
        venue_game_start=_utc(2026, 9, 14, 13, 0).isoformat(),
        n_stamps=1,
        n_events=1,
    )
    base.update(kw)
    return SimpleNamespace(**base)


async def _run(monkeypatch, rows):
    session = _RecordingSession(rows)
    monkeypatch.setattr(poly, "get_task_session", lambda: _Ctx(session))
    stats = await redate_polymarket_listing_stamped_events()
    return stats, session


class TestTheRailWritesWhatTheShipClaims:

    @pytest.mark.asyncio
    async def test_a_future_start_writes_all_three_columns_in_one_statement(
        self, monkeypatch
    ):
        stats, session = await _run(monkeypatch, [_row()])
        assert stats["moved"] == 1
        assert stats["rescheduled"] == 1
        assert len(session.writes) == 1, "two statements would let one land alone"
        sql, params = session.writes[0]
        assert "commence_time = :dt" in sql
        assert "commence_time_source = :src" in sql
        assert "status = :status" in sql
        assert params["dt"] == _utc(2026, 9, 14, 13, 0)
        assert params["src"] == POLYMARKET_VENUE_COMMENCE_SOURCE
        assert params["status"] == "scheduled"
        assert params["id"] == 1
        assert session.commits == 1

    @pytest.mark.asyncio
    async def test_a_past_start_writes_the_date_and_never_the_status(
        self, monkeypatch
    ):
        stats, session = await _run(
            monkeypatch,
            [_row(venue_game_start=_utc(2026, 9, 14, 5, 0).isoformat())],
        )
        assert stats["moved"] == 1
        assert stats["rescheduled"] == 0
        sql, params = session.writes[0]
        assert "status" not in sql
        assert "status" not in params

    @pytest.mark.asyncio
    async def test_it_selects_on_the_listing_stamp_and_nothing_else(
        self, monkeypatch
    ):
        # An odds_api / ESPN / StatPal-dated row must never be reachable: those
        # are real schedules and outrank the venue's own listing.
        _stats, session = await _run(monkeypatch, [_row()])
        assert session.selected_params == {"listing_src": "polymarket"}

    @pytest.mark.asyncio
    async def test_a_multi_event_group_is_skipped_and_counted(self, monkeypatch):
        # 21 of 895 groups. One instant cannot date three fixtures; that is the
        # twins class (#2693), not a dating defect.
        stats, session = await _run(monkeypatch, [_row(n_events=3)])
        assert stats["moved"] == 0
        assert stats["skipped_multi_event_group"] == 1
        assert session.writes == []
        assert session.commits == 0

    @pytest.mark.asyncio
    async def test_a_group_disagreeing_with_itself_is_skipped_and_counted(
        self, monkeypatch
    ):
        stats, session = await _run(monkeypatch, [_row(n_stamps=2)])
        assert stats["moved"] == 0
        assert stats["skipped_ambiguous_stamp"] == 1
        assert session.writes == []

    @pytest.mark.asyncio
    async def test_a_row_with_a_score_is_skipped_through_the_rail_too(
        self, monkeypatch
    ):
        # The predicate refuses it; this proves the rail asks the predicate rather
        # than only the SQL.
        stats, session = await _run(monkeypatch, [_row(home_score=6)])
        assert stats["moved"] == 0
        assert stats["skipped_no_change"] == 1
        assert session.writes == []

    @pytest.mark.asyncio
    async def test_nothing_to_do_commits_nothing_and_says_so(self, monkeypatch):
        stats, session = await _run(monkeypatch, [])
        assert stats == {
            "scanned": 0,
            "moved": 0,
            "rescheduled": 0,
            "skipped_multi_event_group": 0,
            "skipped_ambiguous_stamp": 0,
            "skipped_no_change": 0,
        }
        assert session.commits == 0

    @pytest.mark.asyncio
    async def test_the_whole_specimen_slate_moves_in_one_pass(self, monkeypatch):
        rows = [
            _row(event_id=eid, event_commence=listed, venue_game_start=venue.isoformat())
            for eid, listed, venue, _skew in SPECIMENS
        ]
        stats, session = await _run(monkeypatch, rows)
        assert stats["scanned"] == 4
        assert stats["moved"] == 4
        assert stats["rescheduled"] == 4
        assert {p["id"] for _s, p in session.writes} == {e for e, *_ in SPECIMENS}
        assert session.commits == 1

    @pytest.mark.asyncio
    async def test_one_bad_row_does_not_cost_the_healthy_siblings(self, monkeypatch):
        rows = [_row(event_id=1, n_events=4), _row(event_id=2)]
        stats, session = await _run(monkeypatch, rows)
        assert stats["moved"] == 1
        assert [p["id"] for _s, p in session.writes] == [2]


class TestItIsWiredAndTheGatesAreInTheQuery:

    def test_the_poll_actually_calls_it(self):
        # The class this repo keeps re-learning: a fix behind a helper no caller
        # runs. Read from the AST of the poll body, not from a grep of the module.
        tree = ast.parse(inspect.getsource(poly._poll_polymarket_markets))
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "redate_polymarket_listing_stamped_events" in called

    def test_it_runs_after_the_link_sweep(self):
        # It reads `event_id` on child rows that sweep has just written.
        src = inspect.getsource(poly._poll_polymarket_markets)
        assert src.index("link_polymarket_sub_markets()") < src.index(
            "redate_polymarket_listing_stamped_events()"
        )

    def test_the_query_carries_both_group_gates(self):
        assert "n_stamps = 1" in REDATE_LISTING_STAMPED_SQL
        assert "n_events = 1" in REDATE_LISTING_STAMPED_SQL

    def test_the_query_never_reaches_a_finished_row(self):
        # 17,633 closed + 6,261 voided rows carry this provenance. Re-dating a
        # finished game is worth nothing and risks the #46 inversion.
        assert "IN ('live', 'suspended')" in REDATE_LISTING_STAMPED_SQL
        assert "closed" not in REDATE_LISTING_STAMPED_SQL
        assert "voided" not in REDATE_LISTING_STAMPED_SQL

    def test_the_listing_source_is_a_bind_not_a_literal(self):
        assert ":listing_src" in REDATE_LISTING_STAMPED_SQL
