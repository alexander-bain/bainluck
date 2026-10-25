"""#11315 — a finished golf board keeps its final journey; the hourly poll stops
handing it the pre-tournament field again after the tournament ends.

WHAT WAS WRONG. `_poll_datagolf_markets` picks `current_event` as the first
schedule row that is not "completed" or whose end date is today or later.
DataGolf's status string lags (the reason #1076 and #144 exist), so on the
final day — and for as long as the status trails the result — the poll still
selects a tournament that is over, and writes `get_pre_tournament()` onto its
markets with no look at whether they are resolved. #7935's deferral does not
stand it down: it reads the in-play beat's owner key, and that key expires with
the live phase. So a settled board took, every hour: a new pre-tournament
`current_probability`, a fresh `last_updated` / `price_changed_at` /
`probability_change_24h`, a snapshot drawn onto the finished chart (or the
dedup arm stretching an old one's `valid_until`), the withdrawal null-out
taking graded legs off the board, and — for a player first seen now — a new leg
born on the finished board with a pre-tournament price.

This is PREVENTION ONLY. Nothing here cleans stored history, grades a market,
or claims which execution produced any particular stored reset.

THE RIG. The real `_poll_datagolf_markets`, the real payload models, the #7935
fake session (which keeps every write), and one addition: a session that
APPLIES the #1076 restore, so the future-dated control proves the guard reads
the row's status after the restore rather than before it. Every refusal arm
runs beside a control that differs in one input and must still write.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.sql.dml import Update

import app.services.datagolf_api as datagolf_api
import app.tasks.base as task_base
import app.tasks.datagolf as datagolf
import app.tasks.redis_state as redis_state
from app.models.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome

from tests.test_datagolf_one_price_writer_per_phase_7935 import (  # noqa: E402
    EURO_EVENT_ID,
    PGA_EVENT_ID,
    _FakeRedis,
    _FakeResult,
    _FakeService,
    _FakeSession,
    _player,
)

DataGolfTournament = datagolf_api.DataGolfTournament

#: The graded value on the finished board (the winner's leg).
GRADED = 1.0
#: What `get_pre_tournament` still returns for that player after the result.
PRE_TOURNAMENT = 0.083
#: A pre-tournament price the euro sibling (not yet started) should receive.
EURO_PRE_TOURNAMENT = 0.31

WINNER_ID = 18417
VANISHED_ID = 77777
NEWCOMER_ID = 99999
EURO_PLAYER_ID = 12345

OLD = datetime(2026, 1, 1, tzinfo=timezone.utc)
OLD_CHANGE = 0.42

#: A snapshot whose `valid_until` the dedup arm would stretch.
SNAP_VALID_UNTIL = datetime(2026, 1, 2, tzinfo=timezone.utc)


# --------------------------------------------------------------- fixtures --


def _tournament(tour, event_id, name, *, start_offset, length=3, status=None):
    """Offset FIRST, then truncate (gotcha #44)."""
    now = datetime.now(timezone.utc)
    start = now + timedelta(days=start_offset)
    end = start + timedelta(days=length)
    return DataGolfTournament(
        event_id=event_id,
        event_name=name,
        course="Baycurrent",
        start_date=start.strftime("%Y-%m-%d"),
        end_date=end.strftime("%Y-%m-%d"),
        status=status,
        tour=tour,
    )


#: How the poll comes to name a finished tournament "current". Both are the
#: schedule's own fields; neither involves the in-play owner key.
FINISHED_BUT_CURRENT = {
    # Final day: end date is today, status not yet "completed" (absent).
    "final_day": dict(start_offset=-3, length=3, status=None),
    # Days later, the status string still trailing the result.
    "status_lags": dict(start_offset=-6, length=3, status="in_progress"),
}


class _RestoringSession(_FakeSession):
    """The #7935 session, plus the #1076 restore actually applied.

    The parent answers every UPDATE with rowcount 0 and changes nothing, which
    would leave a future-dated resolved market resolved and make the #1076
    control below test nothing. This applies the restore's own predicate to the
    seeded markets: resolved datagolf rows with a future `resolution_date` go
    back to open with `settled_at` cleared.
    """

    async def execute(self, stmt):
        if isinstance(stmt, Update) and stmt.table.name == "futures_markets":
            params = stmt.compile().params
            values = {
                c.key if hasattr(c, "key") else str(c): v
                for c, v in stmt._values.items()
            }
            if "resolved" in params.values() and "status" in values:
                status_value = values["status"]
                status_value = getattr(status_value, "value", status_value)
                if status_value == "open":
                    now = datetime.now(timezone.utc)
                    flipped = 0
                    for market in self.markets.values():
                        if (
                            market.status == "resolved"
                            and market.resolution_date is not None
                            and market.resolution_date > now
                        ):
                            market.status = "open"
                            market.settled_at = None
                            flipped += 1
                    return _FakeResult(rowcount=flipped)
        return await super().execute(stmt)


def _world(*, pga_status, euro_status="open", pga_resolution_date=None):
    markets: dict[str, FuturesMarket] = {}
    outcomes: dict[tuple[int, str], FuturesOutcome] = {}
    snapshots: dict[int, FuturesOddsSnapshot] = {}

    market_id = 10
    for tour, event_id, status in (
        ("pga", PGA_EVENT_ID, pga_status),
        ("euro", EURO_EVENT_ID, euro_status),
    ):
        for market_type, _category in datagolf.MARKET_TYPES:
            ext = datagolf._external_id(tour, event_id, market_type)
            market = FuturesMarket(
                source="datagolf",
                external_id=ext,
                name=f"{tour} - {market_type}",
                status=status,
            )
            market.id = market_id
            market.market_metadata = {}
            if tour == "pga":
                market.resolution_date = pga_resolution_date
                market.settled_at = OLD if status == "resolved" else None
            markets[ext] = market
            market_id += 1

    def _leg(mid, dg_id, name, probability, oid):
        outcome = FuturesOutcome(
            market_id=mid,
            external_id=f"dg_{dg_id}",
            name=name,
            current_probability=probability,
        )
        outcome.id = oid
        outcome.last_updated = OLD
        outcome.price_changed_at = OLD
        outcome.probability_change_24h = OLD_CHANGE
        outcomes[(mid, f"dg_{dg_id}")] = outcome
        snap = FuturesOddsSnapshot(
            outcome_id=oid,
            bookmaker="datagolf_model",
            probability=probability,
            reading_count=3,
        )
        snap.valid_until = SNAP_VALID_UNTIL
        snapshots[oid] = snap
        return outcome

    pga_cut = markets[datagolf._external_id("pga", PGA_EVENT_ID, "make_cut")].id
    euro_cut = markets[datagolf._external_id("euro", EURO_EVENT_ID, "make_cut")].id
    _leg(pga_cut, WINNER_ID, "Tournament Winner", GRADED, 101)
    _leg(pga_cut, VANISHED_ID, "Dropped From Field", 0.0, 102)
    _leg(euro_cut, EURO_PLAYER_ID, "Euro Control", 0.55, 201)
    return markets, outcomes, snapshots


def _run(
    monkeypatch,
    *,
    pga_status,
    shape="final_day",
    tours=("pga",),
    pga_players_price=PRE_TOURNAMENT,
    newcomer=False,
    owner_pga=False,
    pga_schedule=None,
    pga_resolution_date=None,
):
    markets, outcomes, snapshots = _world(
        pga_status=pga_status, pga_resolution_date=pga_resolution_date
    )
    session = _RestoringSession(markets, outcomes, snapshots)

    pga_players = [_player(WINNER_ID, "Tournament Winner", pga_players_price)]
    if newcomer:
        pga_players.append(_player(NEWCOMER_ID, "Next Week Entrant", 0.41))

    schedules: dict[str, list] = {}
    players: dict[str, list] = {}
    if "pga" in tours:
        schedules["pga"] = [
            pga_schedule
            or _tournament(
                "pga", PGA_EVENT_ID, "Baycurrent Classic",
                **FINISHED_BUT_CURRENT[shape],
            )
        ]
        players["pga"] = pga_players
    if "euro" in tours:
        schedules["euro"] = [
            _tournament("euro", EURO_EVENT_ID, "Open de France", start_offset=7)
        ]
        players["euro"] = [_player(EURO_PLAYER_ID, "Euro Control", EURO_PRE_TOURNAMENT)]

    service = _FakeService(schedules, players)
    present: dict[str, object] = {}
    if owner_pga:
        present[f"{datagolf.LIVE_KEY_PREFIX}:pga"] = "1"
        present[f"{datagolf.INPLAY_OWNER_KEY_PREFIX}:pga"] = PGA_EVENT_ID.encode()
    redis = _FakeRedis(present)

    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setattr(datagolf, "get_task_session", lambda: _Ctx())
    monkeypatch.setattr(task_base, "get_task_session", lambda: _Ctx())
    monkeypatch.setattr(datagolf_api, "DataGolfAPIService", lambda *a, **kw: service)
    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **kw: redis)

    stats = asyncio.run(datagolf._poll_datagolf_markets())
    return stats, session, markets, outcomes, snapshots


def _cut_id(markets, tour, event_id):
    return markets[datagolf._external_id(tour, event_id, "make_cut")].id


def _snapshots_added(session):
    return [o for o in session.added if isinstance(o, FuturesOddsSnapshot)]


def _legs_added(session, market_id):
    return [
        o for o in session.added
        if isinstance(o, FuturesOutcome) and o.market_id == market_id
    ]


def _reranked_ids(session):
    ids = set()
    for stmt in session.reranked:
        for value in stmt.compile().params.values():
            if isinstance(value, (list, tuple)):
                ids.update(v for v in value if isinstance(v, int))
            elif isinstance(value, int):
                ids.add(value)
    return ids


# ------------------------------------------------------------- refusals --


@pytest.mark.parametrize("shape", sorted(FINISHED_BUT_CURRENT))
class TestAResolvedBoardTakesNoPreTournamentPrice:
    def test_the_graded_leg_keeps_its_price_and_every_stamp(self, monkeypatch, shape):
        stats, _session, markets, outcomes, _snaps = _run(
            monkeypatch, pga_status="resolved", shape=shape
        )
        leg = outcomes[(_cut_id(markets, "pga", PGA_EVENT_ID), f"dg_{WINNER_ID}")]
        assert leg.current_probability == GRADED, (
            "the hourly poll wrote a pre-tournament price "
            f"({leg.current_probability}) onto a resolved board"
        )
        assert leg.last_updated == OLD
        assert leg.price_changed_at == OLD
        assert leg.probability_change_24h == OLD_CHANGE
        # All five market types of the finished event, nothing else.
        assert stats["resolved_market_price_writes_refused"] == len(datagolf.MARKET_TYPES)
        assert stats["outcomes_upserted"] == 0

    def test_no_snapshot_is_drawn_onto_the_finished_chart(self, monkeypatch, shape):
        stats, session, _markets, _outcomes, snaps = _run(
            monkeypatch, pga_status="resolved", shape=shape
        )
        assert _snapshots_added(session) == []
        assert stats["snapshots_written"] == 0
        assert snaps[101].valid_until == SNAP_VALID_UNTIL, (
            "the poll closed the graded snapshot's valid_until on its way past"
        )

    def test_an_identical_price_does_not_stretch_the_last_snapshot(self, monkeypatch, shape):
        """The dedup arm is a write too: equal price => `reading_count += 1`
        and `valid_until = now`, extending the last point past the result."""
        _stats, session, _markets, _outcomes, snaps = _run(
            monkeypatch, pga_status="resolved", shape=shape, pga_players_price=GRADED
        )
        assert snaps[101].reading_count == 3
        assert snaps[101].valid_until == SNAP_VALID_UNTIL
        assert _snapshots_added(session) == []

    def test_a_player_missing_from_the_field_keeps_the_graded_row(self, monkeypatch, shape):
        _stats, _session, markets, outcomes, _snaps = _run(
            monkeypatch, pga_status="resolved", shape=shape
        )
        gone = outcomes[(_cut_id(markets, "pga", PGA_EVENT_ID), f"dg_{VANISHED_ID}")]
        assert gone.current_probability == 0.0, (
            "the withdrawal null-out took a graded leg off a resolved board"
        )
        assert gone.last_updated == OLD
        assert gone.price_changed_at == OLD
        assert gone.probability_change_24h == OLD_CHANGE

    def test_no_new_leg_is_born_on_the_finished_board(self, monkeypatch, shape):
        """The alternate write path: leg creation prices the row at birth,
        regardless of the in-play owner. A guard on updates alone leaves it."""
        _stats, session, markets, _outcomes, _snaps = _run(
            monkeypatch, pga_status="resolved", shape=shape, newcomer=True
        )
        assert _legs_added(session, _cut_id(markets, "pga", PGA_EVENT_ID)) == [], (
            "a player first seen after the result was created on the resolved "
            "board with a pre-tournament price"
        )

    def test_the_settled_board_is_not_renumbered(self, monkeypatch, shape):
        _stats, session, markets, _outcomes, _snaps = _run(
            monkeypatch, pga_status="resolved", shape=shape
        )
        pga_ids = {
            m.id for ext, m in markets.items() if ext.startswith("datagolf:pga:")
        }
        assert not (_reranked_ids(session) & pga_ids), (
            "#6325: a finished field's rank is the record of how it finished"
        )


def test_the_resolved_guard_does_not_depend_on_the_inplay_owner(monkeypatch):
    """Owner key PRESENT for the finished event: still refused, and refused by
    THIS guard (the deferral never runs, so it counts nothing)."""
    stats, session, markets, outcomes, _snaps = _run(
        monkeypatch, pga_status="resolved", owner_pga=True, newcomer=True
    )
    leg = outcomes[(_cut_id(markets, "pga", PGA_EVENT_ID), f"dg_{WINNER_ID}")]
    assert leg.current_probability == GRADED
    assert _snapshots_added(session) == []
    assert _legs_added(session, _cut_id(markets, "pga", PGA_EVENT_ID)) == []
    assert stats["resolved_market_price_writes_refused"] == len(datagolf.MARKET_TYPES)
    assert stats["inplay_price_writes_deferred"] == 0


# -------------------------------------------------------------- controls --


@pytest.mark.parametrize("shape", sorted(FINISHED_BUT_CURRENT))
class TestTheSameBoardOpenIsStillWritten:
    """One input changed — the market's status — and every write comes back.
    Without this, a guard that refused all writes would pass the class above."""

    def test_price_stamps_snapshot_nullout_birth_and_rank(self, monkeypatch, shape):
        stats, session, markets, outcomes, snaps = _run(
            monkeypatch, pga_status="open", shape=shape, newcomer=True
        )
        cut = _cut_id(markets, "pga", PGA_EVENT_ID)
        leg = outcomes[(cut, f"dg_{WINNER_ID}")]
        assert leg.current_probability == PRE_TOURNAMENT
        assert leg.last_updated != OLD
        assert leg.probability_change_24h == pytest.approx(PRE_TOURNAMENT - GRADED)
        assert sorted(float(s.probability) for s in _snapshots_added(session)) == [
            PRE_TOURNAMENT, 0.41,
        ]
        assert snaps[101].valid_until != SNAP_VALID_UNTIL
        assert outcomes[(cut, f"dg_{VANISHED_ID}")].current_probability is None
        assert [o.external_id for o in _legs_added(session, cut)] == [f"dg_{NEWCOMER_ID}"]
        assert cut in _reranked_ids(session)
        assert stats["resolved_market_price_writes_refused"] == 0


def test_the_inplay_deferral_on_an_open_board_is_unchanged(monkeypatch):
    """#7935 isolation: open board, owner key naming this event, inside its
    window — deferred by the beat's ownership, not by this guard."""
    stats, session, markets, outcomes, _snaps = _run(
        monkeypatch,
        pga_status="open",
        owner_pga=True,
        pga_schedule=_tournament(
            "pga", PGA_EVENT_ID, "Baycurrent Classic", start_offset=-1
        ),
    )
    leg = outcomes[(_cut_id(markets, "pga", PGA_EVENT_ID), f"dg_{WINNER_ID}")]
    assert leg.current_probability == GRADED
    assert _snapshots_added(session) == []
    assert stats["inplay_price_writes_deferred"] == 1
    assert stats["resolved_market_price_writes_refused"] == 0


def test_another_tours_open_event_is_written_beside_a_resolved_one(monkeypatch):
    """Per market, not per poll: pga is polled first and refused; euro, which
    has not teed off, still gets its pre-tournament field."""
    stats, session, markets, outcomes, _snaps = _run(
        monkeypatch, pga_status="resolved", tours=("pga", "euro")
    )
    pga_leg = outcomes[(_cut_id(markets, "pga", PGA_EVENT_ID), f"dg_{WINNER_ID}")]
    euro_leg = outcomes[(_cut_id(markets, "euro", EURO_EVENT_ID), f"dg_{EURO_PLAYER_ID}")]
    assert pga_leg.current_probability == GRADED
    assert euro_leg.current_probability == EURO_PRE_TOURNAMENT
    assert [float(s.probability) for s in _snapshots_added(session)] == [EURO_PRE_TOURNAMENT]
    assert stats["resolved_market_price_writes_refused"] == len(datagolf.MARKET_TYPES)


def test_a_future_dated_market_resolved_by_mistake_is_restored_and_written(monkeypatch):
    """#1076: the restore at the top flips it back to open BEFORE the loop, so
    the guard (which reads the row's status) lets the poll write it."""
    future = datetime.now(timezone.utc) + timedelta(days=4)
    stats, session, markets, outcomes, _snaps = _run(
        monkeypatch,
        pga_status="resolved",
        pga_resolution_date=future,
        pga_schedule=_tournament(
            "pga", PGA_EVENT_ID, "Baycurrent Classic", start_offset=2
        ),
    )
    cut = markets[datagolf._external_id("pga", PGA_EVENT_ID, "make_cut")]
    assert cut.status == "open" and cut.settled_at is None
    assert stats.get("markets_restored") == len(datagolf.MARKET_TYPES)
    leg = outcomes[(cut.id, f"dg_{WINNER_ID}")]
    assert leg.current_probability == PRE_TOURNAMENT
    assert [float(s.probability) for s in _snapshots_added(session)] == [PRE_TOURNAMENT]
    assert stats["resolved_market_price_writes_refused"] == 0


def test_a_past_dated_resolved_market_is_not_restored(monkeypatch):
    """Rig control for the restoring session: it applies #1076's predicate,
    not a blanket reopen — a resolution date already passed stays resolved."""
    past = datetime.now(timezone.utc) - timedelta(days=1)
    stats, _session, markets, _outcomes, _snaps = _run(
        monkeypatch, pga_status="resolved", pga_resolution_date=past
    )
    cut = markets[datagolf._external_id("pga", PGA_EVENT_ID, "make_cut")]
    assert cut.status == "resolved"
    assert "markets_restored" not in stats
    assert stats["resolved_market_price_writes_refused"] == len(datagolf.MARKET_TYPES)


def test_name_and_metadata_still_update_on_a_resolved_board(monkeypatch):
    """The guard sits after these on purpose: they are not prices."""
    _stats, _session, markets, _outcomes, _snaps = _run(
        monkeypatch, pga_status="resolved"
    )
    cut = markets[datagolf._external_id("pga", PGA_EVENT_ID, "make_cut")]
    assert cut.market_metadata.get("datagolf_event_id") == PGA_EVENT_ID
    assert cut.name == "Baycurrent Classic - Make the Cut"


def test_the_rig_serves_the_seeded_legs(monkeypatch):
    """Rig control: on the open control the poll UPDATED the seeded leg rather
    than creating a duplicate, so the refusal arms read the row it found."""
    _stats, session, markets, _outcomes, _snaps = _run(
        monkeypatch, pga_status="open"
    )
    cut = _cut_id(markets, "pga", PGA_EVENT_ID)
    assert [o for o in _legs_added(session, cut) if o.external_id == f"dg_{WINNER_ID}"] == []
