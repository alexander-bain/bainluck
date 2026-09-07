"""#3728 — the "Right now" row stops saying "Live" about a game that has not started.

WHAT A USER SAW (production, 2026-09-06, filed by lane1). Event 14969919, one row,
read twice in the same minute:

    GET /api/events/14969919            ->  "status": "scheduled"
    GET /api/events/search-suggestions  ->  "Live — tight game vs ..."   (chip 1)

`_build_search_suggestions` selected `Event.status == "live"` off the RAW column.
Every other public event path in this codebase — six call sites in
`routes/events.py`, two in `routes/league_futures.py` — first runs
`app.utils.lifecycle.served_event_status()`, which rewrites a row claiming `live`
while its own `commence_time` is still in the future back to `scheduled`. The
suggestions builder was the one exception, so the first thing a person saw on
`/search` was a "Live" claim about a match that was weeks away.

The population was 1 when it was filed and 0 by the time it was, because the row
itself was repaired. The PRODUCER is not repaired and is not this lane's: a row
goes `live` legitimately and then has its `commence_time` overwritten forward by
an ESPN reschedule, and neither arm of `tasks/espn_sync.py` can reach that state
(the settled arm covers `completed`/`closed` only; the staleness arm requires
`commence_time <= now - min_max_hours`, which a future-dated row can never
satisfy). The row lane1 found had been in it since at least 2026-08-29 and is
named verbatim in `flow_sentinel.live_before_commence_events`' docstring. So this
guards the SERVING side, which is the half that reaches a person.

TWO HALVES, and the second is why this is a ship and not a deletion:

  1. section 1 (live close games) refuses the row, and
  2. section 2 (starting soon) accepts it, so the game keeps its chip and the
     chip says when it starts.

Delete either half and a test here fails.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routes import events as events_routes
from app.utils import search_suggestions_cache as ssc
from app.utils.lifecycle import EVENT_NOT_STARTED, served_event_status

pytestmark = pytest.mark.asyncio


#: The row lane1 found, by number, so a reader can go and look at it.
_PRODUCTION_ROW_ID = 14969919


class _Rows:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _RecordingDB:
    """Hands each section its rows in order and keeps the statements."""

    def __init__(self, results):
        self._results = list(results)
        self.executed = []

    async def execute(self, stmt):
        self.executed.append(stmt)
        if not self._results:
            raise AssertionError(
                "the build issued more statements than the fixture queued — a "
                "section would have been swallowed as dead"
            )
        return self._results.pop(0)


def _empty(n=5):
    return [_Rows([]) for _ in range(n)]


def _event(*, status, starts_in, event_id=_PRODUCTION_ROW_ID, blend=0.5):
    """One tennis-shaped row. `starts_in` is a timedelta from now, or None."""
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=event_id,
        status=status,
        commence_time=None if starts_in is None else now + starts_in,
        home_team_name="Anna Kalinskaya",
        away_team_name="Emma Navarro",
        win_probability_sources={"betting": blend},
        opening_home_probability=None,
        espn_win_prob_home=None,
    )


@pytest.fixture
def no_redis(monkeypatch):
    import app.tasks.redis_state as redis_state

    monkeypatch.setattr(redis_state, "get_redis_client", lambda: None)


def _live_chips(resp):
    return [s for s in resp["suggestions"] if s["label"].startswith("Live")]


# ---------------------------------------------------------------------------
# 1. The rule itself, so the surface and the shared function cannot drift
# ---------------------------------------------------------------------------


class TestTheRuleThisSurfaceWasMissing:
    async def test_the_function_calls_the_production_row_scheduled(self):
        """Fixture drift catch: if this ever returns `live`, the tests below
        are asserting nothing and the bug is in `lifecycle`, not here."""
        now = datetime.now(timezone.utc)
        assert (
            served_event_status("live", now + timedelta(days=14), now)
            == EVENT_NOT_STARTED
        )
        assert served_event_status("live", now - timedelta(minutes=40), now) == "live"
        assert served_event_status("live", None, now) == EVENT_NOT_STARTED


# ---------------------------------------------------------------------------
# 2. Section 1 refuses it — in the statement AND after the read
# ---------------------------------------------------------------------------


class TestSectionOneRefusesARowThatHasNotStarted:
    async def test_the_statement_carries_a_clock_floor(self):
        """The floor is IN the statement for the reason the tier gate is
        (`test_search_suggestions_tier_and_budget_3685.py`): `.limit(50)` has no
        ordering, so a row filtered only after the read has already spent one of
        the fifty slots the section gets."""
        db = _RecordingDB(_empty())
        await events_routes._build_search_suggestions(db)

        live_sql = str(db.executed[0]).lower()
        assert "status" in live_sql, "fixture drift: statement 1 is not section 1"
        assert "commence_time <=" in live_sql, (
            "section 1's live statement has no clock floor — a premature-live "
            f"row is a candidate again:\n{live_sql}"
        )

    async def test_a_future_dated_live_row_gets_no_chip_even_if_the_read_returns_it(
        self, no_redis
    ):
        """🔴 THE SHIP. The statement is an optimisation of the budget; the rule
        is `served_event_status`, and it runs on every row that survives. This
        drives the section with a row the floor would have excluded, which is
        exactly what a stale plan, a clock skew or a future edit to that
        statement would hand it."""
        weeks_away = _event(status="live", starts_in=timedelta(days=14))
        resp = await events_routes._build_search_suggestions(
            _RecordingDB([_Rows([weeks_away])] + _empty(4))
        )

        assert _live_chips(resp) == [], (
            "a match 14 days away is on the row as \"Live\" — this is #3728 "
            f"exactly:\n{resp['suggestions']}"
        )
        assert not any(
            s.get("event_id") == _PRODUCTION_ROW_ID for s in resp["suggestions"]
        )

    async def test_a_live_row_with_no_start_time_at_all_gets_no_chip(self, no_redis):
        """`live_start_satisfied` fails CLOSED on a missing start authority, and
        so must this. The SQL floor drops it too — `NULL <= now` is NULL — but
        that is three-valued logic agreeing with the rule by luck, not the rule."""
        no_start = _event(status="live", starts_in=None)
        resp = await events_routes._build_search_suggestions(
            _RecordingDB([_Rows([no_start])] + _empty(4))
        )

        assert _live_chips(resp) == [], (
            "a row with no start time is being called Live: " f"{resp['suggestions']}"
        )

    async def test_a_game_actually_in_progress_still_gets_its_chip(self, no_redis):
        """The half that makes this a repair rather than a deletion. #3685 spent
        a whole ship getting real live games onto this row; a fix that emptied
        section 1 would pass every assertion above."""
        in_progress = _event(status="live", starts_in=-timedelta(minutes=40))
        resp = await events_routes._build_search_suggestions(
            _RecordingDB([_Rows([in_progress])] + _empty(4))
        )

        chips = _live_chips(resp)
        assert len(chips) == 1, (
            "a match that started 40 minutes ago lost its chip — the repair ate "
            f"the section it was meant to correct:\n{resp['suggestions']}"
        )
        assert chips[0]["event_id"] == _PRODUCTION_ROW_ID
        assert "tight game" in chips[0]["label"]


# ---------------------------------------------------------------------------
# 3. Section 2 accepts it, so the game keeps a chip and the chip is true
# ---------------------------------------------------------------------------


class TestSectionTwoPicksUpWhatSectionOneRefused:
    async def test_the_statement_admits_a_live_row_whose_start_is_still_ahead(self):
        db = _RecordingDB(_empty())
        await events_routes._build_search_suggestions(db)

        soon_sql = str(db.executed[1]).lower()
        assert "commence_time between" in soon_sql, (
            "fixture drift: statement 2 is not section 2"
        )
        assert "commence_time >" in soon_sql, (
            "section 2 still asks for the RAW `scheduled` only, so a "
            "premature-live game now falls out of the row entirely — #3728's "
            f"repair deleted the chip instead of correcting it:\n{soon_sql}"
        )

    async def test_the_refused_row_comes_back_as_a_countdown(self, no_redis):
        """One row, both sections, one run: section 1 declines it and section 2
        renders the truth about it."""
        starts_soon = _event(status="live", starts_in=timedelta(minutes=40))
        resp = await events_routes._build_search_suggestions(
            _RecordingDB(
                [
                    _Rows([starts_soon]),
                    _Rows([(starts_soon, "tennis_wta_us_open")]),
                    *_empty(3),
                ]
            )
        )

        assert _live_chips(resp) == []
        mine = [s for s in resp["suggestions"] if s.get("event_id") == _PRODUCTION_ROW_ID]
        assert len(mine) == 1, (
            "the game vanished from the row instead of moving to 'starting "
            f"soon':\n{resp['suggestions']}"
        )
        assert ssc.COUNTDOWN_FIELD in mine[0], (
            "the chip carries no deadline, so the serving clock cannot re-render "
            f"it (LAT-P139): {mine[0]}"
        )
        assert "live" not in mine[0]["label"].lower(), mine[0]["label"]


# ---------------------------------------------------------------------------
# 4. The two sections must not both claim the same row
# ---------------------------------------------------------------------------


class TestTheBoundaryBetweenThem:
    async def test_the_two_statements_partition_the_live_rows(self):
        """Section 1 takes `commence_time <= now`, section 2 takes `> now`. The
        instant they overlap is the instant one game is two chips — and the
        instant they leave a gap is the instant it is none. Written as SQL text
        because the halves are in two statements a single query cannot compare.
        """
        db = _RecordingDB(_empty())
        await events_routes._build_search_suggestions(db)

        live_sql = str(db.executed[0]).lower()
        soon_sql = str(db.executed[1]).lower()

        assert "commence_time <=" in live_sql and "commence_time >=" not in live_sql
        assert "commence_time >" in soon_sql
        assert "commence_time >=" not in soon_sql.split("between")[0], (
            "section 2's live arm uses `>=`, which claims the exact-`now` row "
            f"section 1 has already taken:\n{soon_sql}"
        )
