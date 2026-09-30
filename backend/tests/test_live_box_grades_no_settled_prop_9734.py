"""#9734: a live-pass box score never grades a settled prop.

Specimen: `/events/15320240`, Cubs @ Padres, final 8-0. Its box was the 02:11Z
live capture, eleven minutes after first pitch, every player at 0.0. The page
graded 203 props off it: "Michael King 2+ strikeouts … missed" for a pitcher
who struck out 8.

Every ship test below has a CONTROL that holds the box contents fixed and flips
only the ``live`` flag, so a pass proves the refusal is keyed on the flag and
not on the zeros.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.tasks.backfill_winners as bw
from app.routes.events import (
    _build_prop_grade_context,
    _build_props_script,
    _grade_settled_prop,
)
from app.utils.box_score_capture import BOX_SCORE_SOURCES, box_is_live_capture


# The specimen's first-inning box and its final box, one pitcher each.
_KING_FIRST_INNING = {"pitching strikeouts": 0.0, "innings pitched": 0.0}
_KING_FINAL = {"pitching strikeouts": 8.0, "innings pitched": 7.0}


def _event(king_line, *, live):
    box = {
        "source": "espn",
        "fetched_at": "2026-09-30T02:11:10+00:00",
        "players": {"Michael King": dict(king_line)},
    }
    if live:
        box["live"] = True
    return SimpleNamespace(box_score_data=box)


_MARKET = SimpleNamespace(
    name="Chicago Cubs vs San Diego: Strikeouts",
    external_id="KXMLBKS-26SEP29CHCSD-SDMKING15-2",
)


def _leg(source=None, won=False, price=1.0):
    return SimpleNamespace(
        name="Michael King: 2+",
        is_winner=won,
        resolution_source=source,
        current_probability=price,
    )


def _script_row(event, leg):
    ctx = _build_prop_grade_context(event)
    pp = {"market_name": _MARKET.name, "outcome_name": leg.name}
    pp.update(_grade_settled_prop(True, ctx, _MARKET, leg, 2, False))
    return pp, _build_props_script([pp])[0]


# ---------------------------------------------------------------------------
# The route: the specimen row.
# ---------------------------------------------------------------------------


def test_the_specimen_row_is_withheld_not_printed_as_0_miss():
    pp, row = _script_row(_event(_KING_FIRST_INNING, live=True), _leg())
    assert pp["hit"] is None and pp["actual"] is None
    assert row["graded_result"] is None
    assert row["graded_label"] is None
    assert row["settled"] is False


def test_control_the_same_zeros_without_the_live_flag_still_grade():
    """The unfixed tree's behaviour, kept for a box that says it is final.

    Mutant: key the refusal on anything but `live` and this or the ship fails.
    """
    _, row = _script_row(_event(_KING_FIRST_INNING, live=False), _leg())
    assert row["graded_label"] == "0 — miss"


def test_control_the_final_box_grades_the_ladder_the_reader_expects():
    _, row = _script_row(_event(_KING_FINAL, live=False), _leg())
    assert row["graded_label"] == "8 — hit"


# ---------------------------------------------------------------------------
# The route: verdicts the resolver STORED off the same live box.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("source", sorted(BOX_SCORE_SOURCES))
@pytest.mark.parametrize("won,price", [(False, 1.0), (False, 0.0), (True, 1.0)])
def test_a_stored_box_verdict_on_a_live_box_is_refused(source, won, price):
    """`_build_props_script` falls back on `is_winner` whenever a source is set,
    and `_venue_typed_hit` accepts tier 2 with an agreeing price. On a live box
    both would print the mid-game read, so both are shut: disagreeing price
    (1.0 vs False), agreeing price (0.0 vs False), and a stored winner.
    """
    pp, row = _script_row(
        _event(_KING_FIRST_INNING, live=True), _leg(source=source, won=won, price=price)
    )
    assert pp["hit"] is None
    assert pp["is_winner"] is None
    assert row["graded_result"] is None and row["settled"] is False


@pytest.mark.parametrize("source", sorted(BOX_SCORE_SOURCES))
def test_control_a_stored_box_verdict_on_a_final_box_is_unchanged(source):
    pp, row = _script_row(
        _event(_KING_FINAL, live=False), _leg(source=source, won=True, price=1.0)
    )
    assert pp["is_winner"] is True
    assert row["graded_label"] == "8 — hit"


def test_the_venues_own_settlement_still_grades_a_live_box_event():
    """The refusal is of the box, not of the row: an `api_settlement` its own
    settled price corroborates types the verdict, with no stat line."""
    pp, row = _script_row(
        _event(_KING_FIRST_INNING, live=True),
        _leg(source="api_settlement", won=True, price=1.0),
    )
    assert pp["hit"] is True and pp["actual"] is None
    assert row["graded_result"] == "hit"


def test_no_box_at_all_is_still_none():
    assert _build_prop_grade_context(SimpleNamespace(box_score_data=None)) is None


# ---------------------------------------------------------------------------
# The predicate.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [True, "true", 1, "yes"])
def test_any_live_value_reads_as_live(value):
    assert box_is_live_capture({"live": value}) is True


@pytest.mark.parametrize(
    "box", [{}, {"live": None}, {"live": False}, {"players": {}}, None, [], "live"]
)
def test_absent_or_false_reads_as_final(box):
    assert box_is_live_capture(box) is False


# ---------------------------------------------------------------------------
# The resolvers that STORE verdicts from box scores.
# ---------------------------------------------------------------------------


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


def _session(monkeypatch, *, outcomes, box_rows):
    writes = {"winner_ids": None, "loser_ids": None}
    session = AsyncMock()

    async def _execute(stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        if "SELECT id FROM events WHERE box_score_data IS NOT NULL" in sql:
            return _Result([(r.id,) for r in box_rows])
        if "box_score_data FROM events" in sql:
            return _Result(box_rows)
        if "FROM futures_outcomes" in sql:
            return _Result(outcomes)
        if "is_winner = true" in sql:
            writes["winner_ids"] = (params or {}).get("ids")
            return MagicMock(rowcount=len(writes["winner_ids"] or []))
        if "is_winner = false" in sql:
            writes["loser_ids"] = (params or {}).get("ids")
            return MagicMock(rowcount=len(writes["loser_ids"] or []))
        return MagicMock(rowcount=0)

    session.execute = AsyncMock(side_effect=_execute)
    session.commit = AsyncMock()

    class _CM:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(bw, "get_task_session", lambda: _CM())
    return writes


def _box(players, *, live):
    box = {"source": "espn", "players": players}
    if live:
        box["live"] = True
    return box


@pytest.mark.parametrize("live", [True, False])
async def test_player_prop_resolver_skips_a_live_box(monkeypatch, live):
    outcome = _row(
        outcome_id=15,
        outcome_name="Michael King: 2+",
        ticker="KXMLBKS-26SEP29CHCSD-SDMKING15-2",
        cur_winner=None,
        event_id=15320240,
    )
    bs = _row(id=15320240, box_score_data=_box({"Michael King": _KING_FIRST_INNING}, live=live))
    writes = _session(monkeypatch, outcomes=[outcome], box_rows=[bs])

    stats = await bw._resolve_kalshi_player_props_from_boxscore()

    if live:
        assert writes == {"winner_ids": None, "loser_ids": None}, stats
        assert stats["resolved"] == 0 and stats["live_box"] == 1
    else:
        # Control: the same zeros in a final box are written as the loser.
        assert writes["loser_ids"] == [15], stats
        assert stats.get("live_box", 0) == 0


@pytest.mark.parametrize("live", [True, False])
async def test_total_bases_resolver_skips_a_live_box(monkeypatch, live):
    """This pass writes only `is_winner IS NULL` rows and never revisits them,
    so a bound off a first-inning box (0 hits ⇒ "certain loser") is permanent."""
    outcome = _row(
        outcome_id=16,
        outcome_name="Manny Machado: 1+",
        box_score_data=_box({"Manny Machado": {"hits": 0, "home runs": 0}}, live=live),
    )
    writes = _session(monkeypatch, outcomes=[outcome], box_rows=[])

    stats = await bw._resolve_kalshi_total_bases_from_boxscore()

    if live:
        assert writes == {"winner_ids": None, "loser_ids": None}, stats
        assert stats["resolved"] == 0 and stats["live_box"] == 1
    else:
        assert writes["loser_ids"] == [16], stats
        assert stats.get("live_box", 0) == 0
