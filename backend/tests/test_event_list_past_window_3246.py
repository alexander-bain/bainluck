"""#3246 — `/api/events` can be asked for more than yesterday's results.

PILLAR: TRUTH. SHIP: `/sports/americanfootball_nfl` stops dropping Sunday's
scores at Monday teatime while we still hold them.

THE DEFECT, MEASURED
====================

`list_events` builds ONE floor — `yesterday_start`, i.e. `(now - 1 day)`
truncated to midnight UTC — and spends it on both the scheduled arm and the
finished arm. That floor **breathes between 24h and 48h** across the UTC day
(it truncates *after* subtracting), so it steps at `00:00Z` = **17:00 PDT**.

The consequence is not a dormant-league curiosity. Measured by ux/1283 on
production 2026-09-15, `/api/events?days=14` against `/api/leagues/{key}` in
the same minute, with the floor 46.2h back:

    americanfootball_ncaaf    0 completed of 78 rows   vs   8 held with scores
    americanfootball_nfl      2 completed of 34 rows   vs   8 held with scores
    tennis_atp                0 of 37                  vs   8
    soccer_uefa_champs_league 0                        vs   8
    aussierules_afl           0 of 3                   vs   6

Sorting the kickoffs against the floor reproduces every count with nothing left
over, so it is the floor and not absent data: we hold `Chicago 59 @ Carolina 37`
and decline to serve it to the page that exists to show it. A reader opening
`/sports/americanfootball_nfl` on Monday evening Pacific sees Sunday Night and
Monday Night and an arbitrary two-game subset of the afternoon slate — the rest
drop mid-evening while the reader is looking at them.

`days` cannot reach them: it bounds the FUTURE only. ux measured `days=14` and
`days=90` returning byte-identical payloads on AFL (3 scheduled / 0 completed).
No value of `days` reaches a finished game, which is why this needs its own
parameter rather than a bigger number.

WHAT THIS CHANGES, AND THE ONE ARM IT DELIBERATELY DOES NOT WIDEN
=================================================================

`event_list_window_condition` grows an optional `finished_start`. Omitted, it
falls back to `recent_start` — so every existing caller is byte-identical and
this is purely additive (the CERT-786 suite pins that and must keep passing).

**The scheduled arm keeps `recent_start` even when `finished_start` widens**,
and that is a decision rather than an oversight. #3211 gave the scheduled arm a
backwards floor so a row still marked `scheduled` after its own kickoff stays
reachable — "its clock ran out and nothing reported an ending". Those rows carry
no score. Widening the RESULTS window must not drag three days of stale
kickoff-passed rows onto the page beside the finals; a reader asking for more
results is not asking for more ghosts.

Suspended keeps riding the finished arm, unchanged: a suspended row "is as
recent as the Final it replaced, and should age off exactly where that Final
would have" (the function's own docstring), so it ages off with the widened
Finals, not with the scheduled ghosts.

THE CONSUMER HALF
=================

`fetchEvents` has exactly one caller — `frontend/app/sports/[key]/page.tsx` —
and ux/1283 owns it (notice 41: layout is ux's, server-side is lane1's) and has
taken it on #3246. This file grades the producer half on its own merits under
notice 46: the pair is named here, and #3246 is the linked open issue.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import and_, create_engine, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

# SQLite cannot render Postgres-native column types. DDL shims for the sqlite
# dialect ONLY — production is Postgres and never reaches them. Same shims as
# `test_suspended_is_reachable_cert_786`, and for the same reason: without them
# `events` cannot be created and this module degrades to shape-only coverage.


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models import Event, Sport  # noqa: E402
from app.models.models import Base  # noqa: E402
from app.routes.events import (  # noqa: E402
    EVENT_LIST_DEFAULT_STATUSES,
    event_list_window_condition,
)
from app.utils.event_completion import EVENT_SUSPENDED  # noqa: E402

#: Tuesday 00:30Z — five PM Pacific on Monday, thirty minutes after the floor
#: steps. This is the exact instant the reader loses Sunday's slate, so it is
#: the instant the suite is anchored on. Fixed, never derived from the clock
#: (gotcha #44): the anchor is offset from a literal, so there is no branch.
NOW = datetime(2026, 9, 15, 0, 30, 0, tzinfo=timezone.utc)

#: `(now - 1 day)` truncated — what `list_events` spends today.
YESTERDAY_START = (NOW - timedelta(days=1)).replace(
    hour=0, minute=0, second=0, microsecond=0
)

S_NFL = 1
S_NCAAF = 2

#: Sunday afternoon, 2026-09-13 17:00Z. Held with a score, 31.5h behind NOW —
#: and 7h behind the floor, which is the whole defect.
NFL_SUNDAY_ID = 930_001
NFL_SUNDAY_COMMENCE = datetime(2026, 9, 13, 17, 0, 0, tzinfo=timezone.utc)

#: Sunday Night — the one the reader DOES still see, because it kicked off
#: after the floor. Its presence beside the missing afternoon games is what
#: makes the page read as an arbitrary subset rather than an empty section.
NFL_SNF_ID = 930_002
NFL_SNF_COMMENCE = datetime(2026, 9, 14, 0, 20, 0, tzinfo=timezone.utc)

#: Saturday, 2026-09-12 19:00Z. NCAAF plays its whole slate here, so the league
#: loses ALL of it — the 0-of-78 row in the measurement above.
NCAAF_SATURDAY_ID = 930_003
NCAAF_SATURDAY_COMMENCE = datetime(2026, 9, 12, 19, 0, 0, tzinfo=timezone.utc)

#: A row that still says `scheduled` three days after its kickoff — #3211's
#: population. It has no score and must NOT ride the widened results window.
STALE_SCHEDULED_ID = 930_004
STALE_SCHEDULED_COMMENCE = datetime(2026, 9, 12, 19, 0, 0, tzinfo=timezone.utc)

#: Suspended on Saturday. Rides the finished arm, so it widens WITH the Finals.
SATURDAY_SUSPENDED_ID = 930_005

#: Beyond `end_date` (NOW + 7d), to prove the upper bound is untouched. Twelve
#: days out on purpose: a specimen inside the requested range would be served
#: by the scheduled arm correctly and the assertion would be testing nothing.
NFL_NEXT_WEEK_ID = 930_006
NFL_NEXT_WEEK_COMMENCE = datetime(2026, 9, 27, 17, 0, 0, tzinfo=timezone.utc)

#: Live, kicked off before the floor. The live arm has no floor at all and must
#: keep not having one.
NFL_LIVE_ID = 930_007


def _event(eid, sport_id, commence_time, status, *, home_score=None, away_score=None):
    return Event(
        id=eid,
        sport_id=sport_id,
        external_id=f"ext-{eid}",
        home_team_name=f"H{eid}",
        away_team_name=f"A{eid}",
        commence_time=commence_time,
        status=status,
        home_score=home_score,
        away_score=away_score,
    )


def _slate_rows():
    return [
        _event(
            NFL_SUNDAY_ID,
            S_NFL,
            NFL_SUNDAY_COMMENCE,
            "completed",
            home_score=37,
            away_score=59,
        ),
        _event(
            NFL_SNF_ID, S_NFL, NFL_SNF_COMMENCE, "completed", home_score=21, away_score=17
        ),
        _event(
            NCAAF_SATURDAY_ID,
            S_NCAAF,
            NCAAF_SATURDAY_COMMENCE,
            "completed",
            home_score=28,
            away_score=24,
        ),
        _event(STALE_SCHEDULED_ID, S_NFL, STALE_SCHEDULED_COMMENCE, "scheduled"),
        _event(SATURDAY_SUSPENDED_ID, S_NCAAF, NCAAF_SATURDAY_COMMENCE, EVENT_SUSPENDED),
        _event(NFL_NEXT_WEEK_ID, S_NFL, NFL_NEXT_WEEK_COMMENCE, "scheduled"),
        _event(NFL_LIVE_ID, S_NFL, NFL_SUNDAY_COMMENCE, "live"),
    ]


@pytest.fixture()
def slate():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[Sport.__table__, Event.__table__])
    with Session(engine) as s:
        s.add(Sport(id=S_NFL, key="americanfootball_nfl", name="NFL"))
        s.add(Sport(id=S_NCAAF, key="americanfootball_ncaaf", name="NCAAF"))
        s.add_all(_slate_rows())
        s.commit()
        yield s


def _matching(session, condition):
    return {r[0] for r in session.execute(select(Event.id).where(condition)).all()}


def _served(session, **kwargs):
    """Both gates the route ANDs together — the status set and the window.

    Asserting the window alone would let a change pass that the status filter
    then hides, which is the trap CERT-786 named on this very route.
    """
    window = event_list_window_condition(
        now=NOW, end_date=NOW + timedelta(days=7), **kwargs
    )
    return _matching(
        session, and_(Event.status.in_(EVENT_LIST_DEFAULT_STATUSES), window)
    )


# ---------------------------------------------------------------------------
# 0 — the defect reproduces on today's floor
# ---------------------------------------------------------------------------


class TestTheDefectReproduces:
    def test_todays_floor_loses_sundays_slate(self, slate):
        """The whole issue in one assertion: we hold the score and do not serve it."""
        served = _served(slate, recent_start=YESTERDAY_START)
        assert NFL_SUNDAY_ID not in served
        assert NCAAF_SATURDAY_ID not in served

    def test_and_keeps_the_night_game_so_the_reader_sees_a_subset(self, slate):
        """Not an empty section — an arbitrary two-game remainder, which is
        worse: an empty section reads as "nothing yet", a partial one reads as
        "this is the slate"."""
        served = _served(slate, recent_start=YESTERDAY_START)
        assert NFL_SNF_ID in served

    def test_the_floor_breathes_between_24h_and_48h(self):
        """It truncates AFTER subtracting, so its width depends on the hour —
        which is why the drop lands mid-evening Pacific rather than at a fixed
        age. Pinned so a later "simplification" to a rolling window is a
        deliberate change and not an accident."""
        just_after_step = datetime(2026, 9, 15, 0, 30, tzinfo=timezone.utc)
        just_before_step = datetime(2026, 9, 15, 23, 30, tzinfo=timezone.utc)
        width_after = just_after_step - (
            just_after_step - timedelta(days=1)
        ).replace(hour=0, minute=0, second=0, microsecond=0)
        width_before = just_before_step - (
            just_before_step - timedelta(days=1)
        ).replace(hour=0, minute=0, second=0, microsecond=0)
        assert width_after == timedelta(hours=24, minutes=30)
        assert width_before == timedelta(hours=47, minutes=30)


# ---------------------------------------------------------------------------
# 1 — the fix: a widened results floor reaches them
# ---------------------------------------------------------------------------


class TestAWidenedFinishedFloorReachesTheSlate:
    def test_three_days_back_serves_sunday_and_saturday(self, slate):
        served = _served(
            slate,
            recent_start=YESTERDAY_START,
            finished_start=(NOW - timedelta(days=3)).replace(
                hour=0, minute=0, second=0, microsecond=0
            ),
        )
        assert NFL_SUNDAY_ID in served
        assert NCAAF_SATURDAY_ID in served
        assert NFL_SNF_ID in served

    def test_suspended_widens_with_the_finals_it_replaced(self, slate):
        served = _served(
            slate,
            recent_start=YESTERDAY_START,
            finished_start=(NOW - timedelta(days=3)).replace(
                hour=0, minute=0, second=0, microsecond=0
            ),
        )
        assert SATURDAY_SUSPENDED_ID in served


# ---------------------------------------------------------------------------
# 2 — what must NOT widen
# ---------------------------------------------------------------------------


class TestTheScheduledArmDoesNotWiden:
    def test_a_stale_scheduled_row_stays_out_of_a_widened_results_window(self, slate):
        """#3211's population has no score. A reader asking for more RESULTS is
        not asking for three days of kickoff-passed ghosts."""
        served = _served(
            slate,
            recent_start=YESTERDAY_START,
            finished_start=(NOW - timedelta(days=7)).replace(
                hour=0, minute=0, second=0, microsecond=0
            ),
        )
        assert STALE_SCHEDULED_ID not in served

    def test_3211_still_holds_inside_its_own_floor(self, slate):
        """…while the arm itself is untouched: a kickoff-passed row inside
        `recent_start` is still reachable, which is the whole of #3211."""
        recent_stale = _event(
            930_008, S_NFL, NOW - timedelta(hours=6), "scheduled"
        )
        slate.add(recent_stale)
        slate.commit()
        served = _served(slate, recent_start=YESTERDAY_START)
        assert 930_008 in served

    def test_the_future_bound_is_untouched(self, slate):
        served = _served(
            slate,
            recent_start=YESTERDAY_START,
            finished_start=(NOW - timedelta(days=7)).replace(
                hour=0, minute=0, second=0, microsecond=0
            ),
        )
        assert NFL_NEXT_WEEK_ID not in served, (
            "widening backwards must not widen forwards"
        )

    def test_the_live_arm_keeps_having_no_floor(self, slate):
        assert NFL_LIVE_ID in _served(slate, recent_start=YESTERDAY_START)


# ---------------------------------------------------------------------------
# 3 — the default is byte-identical, so this is purely additive
# ---------------------------------------------------------------------------


class TestOmittingTheParameterChangesNothing:
    def test_omitted_equals_finished_start_set_to_recent_start(self, slate):
        """Every existing caller passes three kwargs. Both spellings must serve
        the same ids, or this change is a silent behaviour change to CERT-786's
        route rather than an addition."""
        omitted = _served(slate, recent_start=YESTERDAY_START)
        explicit = _served(
            slate, recent_start=YESTERDAY_START, finished_start=YESTERDAY_START
        )
        assert omitted == explicit

    def test_past_days_of_one_reproduces_todays_floor_exactly(self, slate):
        """The route's default. `past_days=1` must compute `yesterday_start`
        to the microsecond — a default that is merely *close* is a regression
        nobody would attribute to this change."""
        derived = (NOW - timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        assert derived == YESTERDAY_START
        assert _served(slate, recent_start=YESTERDAY_START, finished_start=derived) == (
            _served(slate, recent_start=YESTERDAY_START)
        )

    def test_a_narrower_request_is_honoured(self, slate):
        """`past_days=0` means today only. It is a legitimate ask and it must
        actually narrow, or the parameter is one-directional."""
        today_only = NOW.replace(hour=0, minute=0, second=0, microsecond=0)
        served = _served(
            slate, recent_start=YESTERDAY_START, finished_start=today_only
        )
        assert NFL_SNF_ID not in served
        assert NFL_SUNDAY_ID not in served
        # …and the arms that do not read this floor are unaffected by it.
        assert NFL_LIVE_ID in served


# ---------------------------------------------------------------------------
# 4 — the route is actually wired to it
# ---------------------------------------------------------------------------


class TestTheRouteIsWired:
    def test_list_events_declares_past_days(self):
        """FastAPI drops an unknown query param SILENTLY, so a consumer passing
        `past_days` to a route that does not declare it gets page-one forever
        while looking busy — the exact failure Q496 paid for on
        `after_commence`. Assert the dispatcher can receive the name."""
        import inspect

        from app.routes.events import list_events

        assert "past_days" in inspect.signature(list_events).parameters

    def test_the_default_is_a_real_int_not_a_query_object(self):
        """Four suites call `list_events` DIRECTLY as a plain function, so a
        parameter they do not pass keeps its Python default. Spelled
        `past_days: int = Query(1, ...)` that default is the `Query` OBJECT,
        and `timedelta(days=<Query>)` raises TypeError for 35 tests that never
        mentioned this parameter. `Annotated` is what keeps the default a real
        int; this pins it, because the `= Query(...)` spelling is what the rest
        of the file uses and is the obvious thing for a later hand to "tidy" it
        back to.
        """
        import inspect

        from app.routes.events import list_events

        default = inspect.signature(list_events).parameters["past_days"].default
        assert default == 1
        assert isinstance(default, int), (
            f"past_days default is {type(default).__name__}, not int — every "
            "direct caller that omits it will raise TypeError"
        )

    def test_list_events_hands_a_finished_start_to_the_predicate(self):
        """An AST walk, not a grep: this file and that route are both full of
        prose naming the parameter, and a substring search is satisfied by a
        comment describing the fix that was reverted."""
        import ast
        import inspect

        from app.routes import events as events_module

        tree = ast.parse(inspect.getsource(events_module.list_events))
        wired = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "event_list_window_condition"
            and any(kw.arg == "finished_start" for kw in node.keywords)
        ]
        assert wired, (
            "list_events no longer passes `finished_start` to "
            "event_list_window_condition — the parameter is declared but inert, "
            "so `past_days` is accepted and silently ignored."
        )
