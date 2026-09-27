"""#9037: poll and socket must not revive a pre-kickoff PM quote.

Exercise both actual writers with their real admission, selection, observation
and stamping helpers. The session doubles record executed Event UPDATE values;
the socket's RETURNING row is derived from that UPDATE, never a canned expected
price. Snapshot and socket payload assertions therefore also expose a wrong
speaker. Database locking/atomicity remains covered by the existing PG gates.
"""

from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import timedelta
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import Select, Update

from app.tasks import live_blend_refresh as ws
from app.utils.aggregation import observation_basis, stamp_source_reading
from tests.test_live_blend_refresh import _RecordingSession, _Result as _WSResult
from tests.test_live_poll_commit_boundary_5682 import (
    _Event,
    _KalshiService,
    _Outcome,
    _Population,
    _PolyService,
    _Result,
    _Session,
    _now,
    _run,
)
from tests.test_live_poll_settled_speaker_call_site_6608 import _disable_inversion


def _population(*, third=True, case="stale", source="polymarket"):
    now = _now()
    kickoff = now - timedelta(minutes=40)
    if case == "grace":
        kickoff = now - timedelta(minutes=6)
    elif case == "outside_window":
        kickoff = now - timedelta(hours=13)
    event = _Event(101, commence=kickoff)
    event.win_probability_sources = {}
    event.opening_home_probability = None
    event.espn_win_prob_home = None
    if case == "unknown_kickoff":
        event.commence_time = None
    elif case == "completed":
        event.completed_at = now
    elif case == "nonlive":
        event.status = "scheduled"
    fresh = now - timedelta(seconds=20)
    old = kickoff - timedelta(minutes=30)
    low_seen = fresh if case in {"postkickoff", "reversal"} else old
    low_price = 0.85 if case == "reversal" else 0.77
    rows, outcomes = [], []
    for mid, prob, seen in [(9, low_price, low_seen), (12, 0.035, fresh)]:
        if case == "all_stale":
            seen = old
        market = SimpleNamespace(
            id=mid,
            event_id=event.id,
            source=source,
            external_id=(
                f"pm-{mid}" if source == "polymarket" else f"KXNFLGAME-EVT{mid}"
            ),
            name="New York G vs. Los Angeles R",
            status="open",
            market_type="game_winner",
            market_metadata={"pregame_mark": {}},
        )
        rows.append((market, event))
        for oid, name, value in [
            (mid * 10, event.home_team_name, prob),
            (mid * 10 + 1, event.away_team_name, 1 - prob),
        ]:
            outcome = _Outcome(oid, mid, f"tok-{oid}", name)
            outcome.current_probability = value
            outcome.last_updated = seen
            outcomes.append(outcome)
    if third:
        market = SimpleNamespace(
            id=13,
            event_id=event.id,
            source=source,
            external_id="pm-13",
            name="New York G vs. Los Angeles R: Both Teams to Score",
            status="open",
            market_type=None,
            market_metadata={"pregame_mark": {}},
        )
        rows.append((market, event))
        for oid, name in [(130, "Yes"), (131, "No")]:
            outcome = _Outcome(oid, 13, f"tok-{oid}", name)
            outcome.current_probability = 0.5
            outcome.last_updated = fresh
            outcomes.append(outcome)
    return _Population(rows, outcomes)


class _PollSession(_Session):
    def __init__(self, population):
        super().__init__([population])
        self.stored = deepcopy(population.rows[0][1].win_probability_sources)
        self.writes = []

    async def execute(self, stmt, params=None):
        if isinstance(stmt, Select):
            names = [column.get("name") for column in stmt.column_descriptions]
            if names == ["win_probability_sources"]:
                return _Result(scalar_value=self.stored)
        if isinstance(stmt, Update) and stmt.table.name == "events":
            values = stmt.compile().params
            if "win_probability_sources" in values:
                self.stored = values["win_probability_sources"]
                self.writes.append(self.stored)
        return await super().execute(stmt, params)


class _SocketSession(_RecordingSession):
    def __init__(self, population, source):
        super().__init__(population.rows, population.outcomes, None)
        self.source = source
        self.stored = deepcopy(population.rows[0][1].win_probability_sources)
        self.writes = []

    async def execute(self, stmt, *args, **kwargs):
        if isinstance(stmt, Update) and stmt.table.name == "events":
            # Read the actual JSON entry bound into atomic_stamp_expression.
            entries = []
            for value in stmt.compile().params.values():
                if isinstance(value, str) and value.startswith("{"):
                    parsed = json.loads(value)
                    if "value" in parsed:
                        entries.append(parsed)
            assert len(entries) == 1
            entry = entries[0]
            entry["updated_at"] = _now().isoformat()
            self.stored = {**self.stored, self.source: entry}
            self.writes.append(self.stored)
            self.updates.append(stmt)
            return _WSResult(scalar=self.stored)
        return await super().execute(stmt, *args, **kwargs)


async def _writer(monkeypatch, writer, population, source="polymarket"):
    _disable_inversion(monkeypatch)
    snapshots, frames = [], []

    async def snapshot(session, **kwargs):
        snapshots.append(kwargs)
        return object(), True

    monkeypatch.setattr(
        "app.tasks.snapshots._create_or_update_win_prob_snapshot", snapshot
    )
    if writer == "poll":
        session = _PollSession(population)
        stats = await _run(
            monkeypatch,
            session,
            kalshi=_KalshiService({}, []),
            poly=_PolyService({}, []),
            blend={},
        )
        assert not stats["errors"], stats
        assert ("commit", None) in session.journal
    else:
        session = _SocketSession(population, source)

        @asynccontextmanager
        async def get_session():
            yield session

        async def publish(batch):
            frames.extend(batch)

        monkeypatch.setattr("app.tasks.base.get_task_session", get_session)
        refresher = ws.LiveBlendRefresher(source)
        monkeypatch.setattr(refresher, "_publish", publish)
        await refresher.refresh([101])
        assert refresher.stats["errors"] == 0, refresher.stats
    return session, snapshots, frames


@pytest.mark.parametrize("writer", ["poll", "socket"])
@pytest.mark.parametrize("third", [False, True], ids=["two_books", "derivative_third"])
async def test_fresh_sibling_is_the_stored_and_emitted_speaker(
    monkeypatch, writer, third
):
    session, snapshots, frames = await _writer(
        monkeypatch, writer, _population(third=third)
    )
    assert len(session.writes) == len(snapshots) == 1
    entry = session.stored["polymarket"]
    assert entry["value"] == pytest.approx(0.035)
    assert set(entry["observed_basis"]) == {"120"}
    assert snapshots[0]["home_win_probability"] == pytest.approx(0.035)
    if writer == "socket":
        assert len(frames) == 1
        assert frames[0]["source_value"] == pytest.approx(0.035)
        assert frames[0]["p"] == pytest.approx(0.035)


@pytest.mark.parametrize("writer", ["poll", "socket"])
@pytest.mark.parametrize(
    "case,expected",
    [
        ("postkickoff", 0.77),
        ("reversal", 0.85),
        ("grace", 0.77),
        ("unknown_kickoff", 0.77),
        ("completed", 0.77),
        ("nonlive", 0.77),
        ("outside_window", 0.77),
    ],
)
async def test_existing_admission_controls_keep_their_quote(
    monkeypatch, writer, case, expected
):
    population = _population(case=case)
    if case == "reversal":
        observed = population.outcomes[0].last_updated - timedelta(seconds=10)
        population.rows[0][1].win_probability_sources = stamp_source_reading(
            {},
            "polymarket",
            0.035,
            now=observed,
            observed_basis={"90": observed.timestamp()},
        )
    session, snapshots, frames = await _writer(monkeypatch, writer, population)
    assert len(session.writes) == len(snapshots) == 1
    assert session.stored["polymarket"]["value"] == pytest.approx(expected)
    assert snapshots[0]["home_win_probability"] == pytest.approx(expected)
    if writer == "socket":
        assert frames[0]["source_value"] == pytest.approx(expected)


@pytest.mark.parametrize("writer", ["poll", "socket"])
async def test_all_stale_means_no_readdition_not_a_withdrawal(monkeypatch, writer):
    population = _population(case="all_stale")
    existing = {"polymarket": {"value": 0.42, "updated_at": _now().isoformat()}}
    population.rows[0][1].win_probability_sources = existing
    session, snapshots, frames = await _writer(monkeypatch, writer, population)
    assert session.writes == snapshots == frames == []
    assert session.stored == existing  # Withdrawal belongs to the matcher.


@pytest.mark.parametrize("writer", ["poll", "socket"])
@pytest.mark.parametrize("third", [False, True], ids=["two_books", "derivative_third"])
async def test_existing_fresh_quote_cannot_be_replaced_by_stale_alternative(
    monkeypatch, writer, third
):
    population = _population(third=third)
    fresh = next(outcome for outcome in population.outcomes if outcome.id == 120)
    population.rows[0][1].win_probability_sources = stamp_source_reading(
        {},
        "polymarket",
        0.035,
        now=fresh.last_updated,
        observed_basis=observation_basis([fresh]),
    )
    session, snapshots, frames = await _writer(monkeypatch, writer, population)
    assert session.stored["polymarket"]["value"] == pytest.approx(0.035)
    assert set(session.stored["polymarket"]["observed_basis"]) == {"120"}
    # Poll may restamp; socket intentionally suppresses an unchanged observation.
    assert all(
        point["home_win_probability"] == pytest.approx(0.035) for point in snapshots
    )
    assert all(frame["source_value"] == pytest.approx(0.035) for frame in frames)
    if writer == "socket":
        assert session.writes == snapshots == frames == []


@pytest.mark.parametrize("writer", ["poll", "socket"])
async def test_two_fresh_books_still_use_existing_composite(monkeypatch, writer):
    session, snapshots, frames = await _writer(
        monkeypatch, writer, _population(third=False, case="postkickoff")
    )
    assert session.stored["polymarket"]["value"] == pytest.approx(0.4025)
    assert set(session.stored["polymarket"]["observed_basis"]) == {"90", "120"}
    assert snapshots[0]["home_win_probability"] == pytest.approx(0.4025)
    if writer == "socket":
        assert frames[0]["source_value"] == pytest.approx(0.4025)


@pytest.mark.parametrize("writer", ["poll", "socket"])
async def test_kalshi_primary_stays_exempt(monkeypatch, writer):
    population = _population(source="kalshi", third=False)
    population.rows = population.rows[:1]
    population.outcomes = population.outcomes[:1]
    session, snapshots, frames = await _writer(
        monkeypatch, writer, population, "kalshi"
    )
    assert len(session.writes) == len(snapshots) == 1
    assert session.stored["kalshi"]["value"] == pytest.approx(0.77)
    assert snapshots[0]["home_win_probability"] == pytest.approx(0.77)
    if writer == "socket":
        assert frames[0]["source_value"] == pytest.approx(0.77)
