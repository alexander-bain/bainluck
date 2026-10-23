"""#1480 — the feed's candidate events read leaves the box score behind.

`_score_events` hydrates up to 500 candidate `Event` rows on every Sports and
Discover miss and on every My Teams build. The asyncpg dialect json-decodes
every JSONB value on every row at fetch time, on the event loop, and nothing on
this path reads `box_score_data` — the same finding #9047 made for the live
poll's population read (`test_live_poll_defers_heavy_event_columns_9047.py`).

Two groups:

1. the statement the session is handed: the box score is out of the SELECT
   list on both branches (Discover/Sports and My Teams), and every OTHER column
   is still in it, so nothing the cards read can start lazy-loading;
2. the path itself: scoring live, scheduled, settled and suspended rows never
   touches `box_score_data`, and the control proves the rows did become cards.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from sqlalchemy.dialects import postgresql

from app.models import Event
from app.routes.feed import _score_events
from app.utils.personalization import PersonalizationContext

NOW = datetime(2026, 10, 19, 23, 0, tzinfo=timezone.utc)


def _select_list(stmt) -> set[str]:
    """The selected column names, one per item — `win_probability_sources_rev`
    is a different column and must not satisfy a substring test."""
    flat = " ".join(str(stmt.compile(dialect=postgresql.dialect())).split())
    head = flat.split(" FROM ", 1)[0].lower().removeprefix("select ")
    return {item.strip().split(" as ")[0] for item in head.split(",")}


class _CapturingDb:
    """Answers the candidate read with `events` and keeps the statement."""

    def __init__(self, events=()):
        self.events = list(events)
        self.candidate_statements: list = []

    async def execute(self, stmt, params=None, *a, **k):
        result = MagicMock()
        result.all.return_value = []
        result.scalars.return_value.all.return_value = []
        if getattr(stmt, "column_descriptions", None) and any(
            d.get("entity") is Event for d in stmt.column_descriptions
        ):
            self.candidate_statements.append(stmt)
            result.scalars.return_value.all.return_value = list(self.events)
        return result


async def _score(db, ctx=None, **kwargs):
    with patch(
        "app.routes.feed._get_championship_probabilities",
        new=AsyncMock(return_value={}),
    ):
        return await _score_events(
            db, NOW, None, ctx or PersonalizationContext(), **kwargs
        )


ALL_EVENT_COLUMNS = {f"events.{c.name}" for c in Event.__table__.columns}


# ---------------------------------------------------------------------------
# 1. the statement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_discover_candidate_read_does_not_select_the_box_score():
    db = _CapturingDb()
    await _score(db, share_inputs=True)
    assert len(db.candidate_statements) == 1
    cols = _select_list(db.candidate_statements[0])
    assert "events.box_score_data" not in cols, cols


@pytest.mark.asyncio
async def test_the_my_teams_candidate_read_does_not_select_the_box_score():
    ctx = PersonalizationContext()
    ctx.team_relations = {101: "favorite"}
    db = _CapturingDb()
    await _score(db, ctx, my_teams_only=True)
    assert len(db.candidate_statements) == 1
    cols = _select_list(db.candidate_statements[0])
    assert "events.box_score_data" not in cols, cols


@pytest.mark.asyncio
async def test_every_other_event_column_is_still_selected():
    """The box score is the ONLY column left behind. A second deferral would be
    a second claim about the read surface, and has to be made here, by name."""
    db = _CapturingDb()
    await _score(db, share_inputs=True)
    cols = _select_list(db.candidate_statements[0])
    assert ALL_EVENT_COLUMNS - cols == {"events.box_score_data"}, (
        ALL_EVENT_COLUMNS - cols
    )


def test_the_deferral_raises_by_name_rather_than_lazy_loading():
    """`raiseload=True`: a future reader fails as InvalidRequestError naming the
    attribute, not as MissingGreenlet from a lazy load inside the async session."""
    import ast
    from pathlib import Path

    import app.routes.feed as feed_mod

    tree = ast.parse(Path(feed_mod.__file__).read_text())
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and getattr(n.func, "id", None) == "defer"
        and n.args
        and ast.unparse(n.args[0]) == "Event.box_score_data"
    ]
    assert len(calls) == 1
    kw = {k.arg: ast.unparse(k.value) for k in calls[0].keywords}
    assert kw.get("raiseload") == "True", kw


# ---------------------------------------------------------------------------
# 2. the path
# ---------------------------------------------------------------------------


def _sport():
    s = MagicMock()
    s.key = "americanfootball_nfl"
    s.name = "NFL"
    return s


def _event(event_id: int, status: str, *, start: datetime, box_reads: list):
    e = MagicMock()
    # Any read of the deferred column is recorded. `type(e)` is this mock's own
    # subclass, so the property is per instance.
    type(e).box_score_data = PropertyMock(
        side_effect=lambda: box_reads.append(event_id) or {"players": []}
    )
    e.id = event_id
    e.status = status
    e.commence_time = start
    e.home_team_id = event_id * 10 + 1
    e.away_team_id = event_id * 10 + 2
    e.home_team_name = f"Home {event_id}"
    e.away_team_name = f"Away {event_id}"
    e.opening_home_probability = 0.55
    e.opening_away_probability = 0.45
    e.win_probability_sources = {
        "betting": {"home": 0.6, "away": 0.4, "updated_at": NOW.isoformat()}
    }
    e.espn_win_prob_home = None
    e.opening_home_spread = -3.5
    e.opening_over_under = 44.5
    e.opening_favorite = "home"
    e.closing_home_probability = None
    e.llm_importance = "high"
    e.llm_gender = None
    e.llm_level = None
    e.llm_league = "NFL"
    e.sport = _sport()
    e.statpal_end_time = None
    e.completed_at = start + timedelta(hours=3) if status == "completed" else None
    e.period = "Q3" if status == "live" else None
    e.game_clock = "4:32" if status == "live" else None
    e.raw_ei = 80.0
    e.ei_metadata = None
    scored = status in ("live", "completed", "suspended")
    e.home_score = 21 if scored else None
    e.away_score = 17 if scored else None
    e.score_source = "espn" if scored else None
    e.score_observed_at = NOW - timedelta(minutes=1) if scored else None
    e.external_id = f"ext-{event_id}"
    e.espn_id = f"espn-{event_id}"
    e.broadcast_info = "CBS"
    e.event_tags = []
    return e


@pytest.mark.asyncio
async def test_scoring_every_status_never_reads_the_box_score():
    box_reads: list[int] = []
    events = [
        _event(1, "live", start=NOW - timedelta(hours=1), box_reads=box_reads),
        _event(2, "scheduled", start=NOW + timedelta(hours=2), box_reads=box_reads),
        _event(3, "completed", start=NOW - timedelta(hours=4), box_reads=box_reads),
        _event(4, "suspended", start=NOW - timedelta(hours=2), box_reads=box_reads),
    ]
    items = await _score(_CapturingDb(events), share_inputs=True)
    # The control: every row became a card, so the loop really ran over each
    # status. Without it the assertion below could pass on a path that dropped
    # every row before reading anything.
    assert sorted(i["data"]["id"] for i in items) == [1, 2, 3, 4]
    assert box_reads == []


@pytest.mark.asyncio
async def test_the_recorder_sees_a_read_when_one_happens():
    """The guard's own control: a read of the property IS recorded."""
    box_reads: list[int] = []
    e = _event(9, "live", start=NOW, box_reads=box_reads)
    _ = e.box_score_data
    assert box_reads == [9]
