"""#899: the box_score player-prop resolver must be memory-bounded.

It used to join e.box_score_data onto EVERY outcome row and result.all() held
every (re-deserialized) copy at once → OOM on the 200MB worker child, which
forced the #937 re-grade to stay scoped to kxnhlpts. The fix: fetch small
outcome rows (no JSONB), group by event, and load each event's box score ONCE
in bounded batches. These tests guard (a) the memory-bounded structure and
(b) that resolution semantics are preserved end-to-end.
"""

import inspect
from unittest.mock import AsyncMock, MagicMock

from app.tasks.backfill_winners import _resolve_kalshi_player_props_from_boxscore


def test_memory_bounded_structure():
    src = inspect.getsource(_resolve_kalshi_player_props_from_boxscore)
    # the main outcomes query's SELECT list must NOT pull the box_score JSONB per
    # outcome row (a WHERE `e.box_score_data IS NOT NULL` filter is fine — it's a
    # cheap NULL check, not a per-row JSONB transfer). Check the SELECT...FROM span.
    outcomes_select = src.split("FROM futures_outcomes", 1)[0].rsplit("SELECT", 1)[1]
    assert "box_score_data" not in outcomes_select, (
        "outcomes query SELECT still pulls box_score_data per row — the #899 OOM"
    )
    # it must carry event_id so rows can be grouped by event
    assert "e.id AS event_id" in outcomes_select
    # box scores are loaded in bounded batches, once per event
    assert "SELECT id, box_score_data FROM events WHERE id = ANY" in src
    assert "_BS_BATCH" in src
    # still extracts the players key (gotcha #37) and stays idempotent (gotcha #21)
    assert 'raw_bs.get("players", raw_bs)' in src
    assert "if row.cur_winner is not None and bool(row.cur_winner) == verdict:" in src


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


def _row(**kw):
    m = MagicMock()
    for k, v in kw.items():
        setattr(m, k, v)
    return m


async def test_resolution_semantics_preserved_through_batched_load(monkeypatch):
    """A kxnhlpts (goals+assists) outcome grades correctly via the per-event
    box-score batch load: McDavid with 1 goal + 2 assists = 3 >= 2 → winner."""
    import app.tasks.backfill_winners as bw

    outcome = _row(
        outcome_id=42,
        outcome_name="Connor McDavid: 2+",
        ticker="KXNHLPTS-26JAN01EDM",
        cur_winner=None,
        event_id=7,
    )
    bs = _row(
        id=7,
        box_score_data={
            "source": "espn",
            "players": {"connor mcdavid": {"goals": 1, "assists": 2}},
        },
    )

    captured = {"winner_ids": None, "loser_ids": None}

    session = AsyncMock()

    async def _execute(stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        if "FROM futures_outcomes" in sql:
            return _Result([outcome])
        if "box_score_data FROM events" in sql:
            return _Result([bs])
        if "is_winner = true" in sql:
            captured["winner_ids"] = (params or {}).get("ids")
            return MagicMock(rowcount=len(captured["winner_ids"] or []))
        if "is_winner = false" in sql:
            captured["loser_ids"] = (params or {}).get("ids")
            return MagicMock(rowcount=len(captured["loser_ids"] or []))
        return MagicMock(rowcount=0)

    session.execute = AsyncMock(side_effect=_execute)
    session.commit = AsyncMock()

    class _CM:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(bw, "get_task_session", lambda: _CM())

    stats = await _resolve_kalshi_player_props_from_boxscore()

    assert captured["winner_ids"] == [42], stats   # graded a winner from the batch-loaded box score
    assert not captured["loser_ids"]
    assert stats["resolved"] == 1


def test_regrade_broadened_beyond_kxnhlpts():
    """#937: the box_score re-grade branch must no longer be scoped to kxnhlpts —
    it re-processes ALL box_score-resolved props (now memory-safe via #899)."""
    src = inspect.getsource(_resolve_kalshi_player_props_from_boxscore)
    # the re-grade branch is now an unrestricted box_score clause
    assert "OR fo.resolution_source = 'box_score')" in src
    # and the old kxnhlpts-only restriction on that branch is gone
    regrade_clause = src.split("resolution_source = 'box_score'", 1)[1].split(")", 1)[0]
    assert "kxnhlpts" not in regrade_clause, (
        "box_score re-grade is still scoped to kxnhlpts — #937 broadening missing"
    )


async def test_regrade_flips_mismarked_mlb_strikeouts_prop(monkeypatch):
    """#937: an already-box_score-resolved MLB strikeouts prop that was wrongly
    graded a loser flips to winner when re-graded (8 K >= 6), proving the
    broadening fixes non-NHL props with the verified ESPN stat-key mapping."""
    import app.tasks.backfill_winners as bw

    outcome = _row(
        outcome_id=99,
        outcome_name="Gerrit Cole: 6+",
        ticker="KXMLBKS-26JUL04NYY",   # strikeouts -> 'strikeouts'
        cur_winner=False,              # mis-graded loser
        event_id=3,
    )
    bs = _row(
        id=3,
        box_score_data={"source": "espn", "players": {"gerrit cole": {"strikeouts": 8}}},
    )
    captured = {"winner_ids": None, "loser_ids": None}
    session = AsyncMock()

    async def _execute(stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        if "FROM futures_outcomes" in sql and "box_score_data FROM events" not in sql:
            return _Result([outcome])
        if "box_score_data FROM events" in sql:
            return _Result([bs])
        if "is_winner = true" in sql:
            captured["winner_ids"] = (params or {}).get("ids")
            return MagicMock(rowcount=len(captured["winner_ids"] or []))
        if "is_winner = false" in sql:
            captured["loser_ids"] = (params or {}).get("ids")
            return MagicMock(rowcount=len(captured["loser_ids"] or []))
        return MagicMock(rowcount=0)

    session.execute = AsyncMock(side_effect=_execute)
    session.commit = AsyncMock()

    class _CM:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(bw, "get_task_session", lambda: _CM())
    stats = await _resolve_kalshi_player_props_from_boxscore()

    assert captured["winner_ids"] == [99], stats   # flipped the mis-graded loser to winner
    assert not captured["loser_ids"]
