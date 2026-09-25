"""#5051 — the search row's "Upset brewing" chip asks the scoreboard, like the capsule.

#4580 ruled that "Upset brewing" names the SCOREBOARD, so the scoreboard has to
agree, and fixed it in `highlights.get_highlight_label` and the footer badge. The
live chip in `_build_search_suggestions` (section 1) was a second implementation of
the same sentence with no scoreboard read at all: an opening favourite whose price
flipped got the chip at 0-0, or with the favourite ahead.

Four arms, and each deletion reddens one:

  1. 0-0 with a flipped price           -> no chip  (the defect)
  2. favourite ahead, flipped price     -> no chip
  3. no score on the row                -> no chip  (None is "cannot say")
  4. underdog ahead, flipped price      -> "Upset brewing" on the underdog
     ... and the market certain         -> "Upset underway" (#5047's tense)
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.routes import events as events_routes

pytestmark = pytest.mark.asyncio

_EVENT_ID = 505100


class _Rows:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _DB:
    def __init__(self, results):
        self._results = list(results)

    async def execute(self, stmt):
        if not self._results:
            return _Rows([])
        return self._results.pop(0)


@pytest.fixture(autouse=True)
def no_redis(monkeypatch):
    import app.tasks.redis_state as redis_state

    monkeypatch.setattr(redis_state, "get_redis_client", lambda: None)


def _game(*, home_score, away_score, now_home=0.30):
    """NFL-opener shape from #4580: home opened 62%, the blend now has it at 30%
    (outside section 1's 35-65% tight band, so only the upset arm can speak)."""
    return SimpleNamespace(
        id=_EVENT_ID,
        status="live",
        commence_time=datetime.now(timezone.utc) - timedelta(minutes=50),
        home_team_name="Philadelphia Eagles",
        away_team_name="Dallas Cowboys",
        home_score=home_score,
        away_score=away_score,
        # Numeric columns arrive as Decimal off the real row.
        opening_home_probability=Decimal("0.6200"),
        opening_away_probability=Decimal("0.3800"),
        win_probability_sources={"betting": now_home},
        espn_win_prob_home=None,
    )


async def _chips(game):
    resp = await events_routes._build_search_suggestions(_DB([_Rows([game])]))
    return [s for s in resp["suggestions"] if s.get("event_id") == _EVENT_ID]


async def test_nil_nil_with_a_flipped_price_gets_no_upset_chip():
    """🔴 THE DEFECT: nothing has happened on the field."""
    assert await _chips(_game(home_score=0, away_score=0)) == []


async def test_the_favourite_ahead_gets_no_upset_chip():
    assert await _chips(_game(home_score=14, away_score=3)) == []


async def test_a_row_with_no_score_gets_no_upset_chip():
    assert await _chips(_game(home_score=None, away_score=None)) == []


async def test_the_underdog_ahead_keeps_its_chip():
    """The half that makes this a repair and not a deletion of the arm."""
    chips = await _chips(_game(home_score=3, away_score=10))
    assert len(chips) == 1, chips
    assert chips[0]["label"] == "Upset brewing"
    assert chips[0]["query"] == "Dallas Cowboys"


async def test_a_decided_upset_says_underway_not_brewing():
    chips = await _chips(_game(home_score=7, away_score=24, now_home=0.05))
    assert [c["label"] for c in chips] == ["Upset underway"]
