"""#11296 — a final's pregame projected score: selection, refusals, order, provenance.

The specimen behind the issue is UX's 2026-10-19 22:24Z read of event 15328569:
kick-off 17:00Z, ``current_odds`` pair captured 20:25Z at 31.2 / 23.8 beside a
31–38 final. That pair is IN-PLAY. Every positive below is built from rows that
straddle the start, so a selector that read the newest row (as ``current_odds``
does) or dropped the boundary fails here rather than on a card.
"""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils import pregame_projection as pp
from app.utils.odds_math import project_scores, projection_contradicts_moneyline
from app.utils.start_placeholder import espn_start_placeholder_tag, start_placeholder_tag

# gotcha #44: a fixed anchor, offsets only.
KICK = datetime(2026, 10, 18, 17, 0, tzinfo=timezone.utc)
_ids = iter(range(1, 10_000))


def row(book, minutes, spread, total, home_p=0.6, away_p=None, *, event_id=1,
        pair=None, rid=None):
    """One stored `odds_snapshots` row, its projected pair solved from its own line."""
    home, away = project_scores(spread, total) if pair is None else pair
    return SimpleNamespace(
        id=next(_ids) if rid is None else rid,
        event_id=event_id,
        bookmaker=book,
        captured_at=KICK + timedelta(minutes=minutes),
        home_win_probability=home_p,
        away_win_probability=(round(1 - home_p, 4) if away_p is None else away_p),
        home_spread=spread,
        over_under=total,
        projected_home_score=home,
        projected_away_score=away,
    )


def event(eid=1, *, status="completed", source="odds_api", commence=KICK,
          sport="americanfootball_nfl", tags=None):
    return SimpleNamespace(
        id=eid, status=status, commence_time=commence,
        commence_time_source=source, event_tags=tags or [], sport_key=sport,
    )


def sport_of(e):
    return e.sport_key


def select(rows, boundary=KICK, unit="points", period="full_game"):
    return pp.select_pregame_projection(rows, boundary_at=boundary, unit=unit, period=period)


# ── positives ────────────────────────────────────────────────────────────────


def test_the_latest_pregame_row_per_book_is_read_and_the_in_play_rows_are_not():
    rows = [
        row("draftkings", -600, -3.0, 47.0),
        row("draftkings", -10, -3.5, 48.0),       # ← draftkings' answer: 25.8 / 22.2
        row("draftkings", 205, 7.5, 55.0),        # in-play (the 20:25Z shape)
        row("fanduel", -30, -2.5, 47.5),          # ← fanduel's answer: 25.0 / 22.5
        row("fanduel", 90, -10.5, 52.0),          # in-play
    ]
    projection, reason = select(rows)
    assert reason is None
    assert projection == {
        "projected_home_score": 25.4,
        "projected_away_score": 22.4,
        "kind": "last_before_scheduled_start",
        "earliest_captured_at": (KICK - timedelta(minutes=30)).isoformat(),
        "latest_captured_at": (KICK - timedelta(minutes=10)).isoformat(),
        "boundary": "scheduled_start",
        "boundary_at": KICK.isoformat(),
        "source": "sportsbooks",
        "basis": "consensus_spread_total",
        "bookmaker_count": 2,
        "unit": "points",
        "period": "full_game",
    }


def test_the_15328569_shape_only_in_play_rows_serves_no_projection():
    # Kick-off 17:00Z, every stored reading after it — the 20:25Z 31.2/23.8 pair.
    rows = [row("draftkings", 205, -7.4, 55.0, home_p=0.9)]
    assert rows[0].projected_home_score == 31.2 and rows[0].projected_away_score == 23.8
    assert select(rows) == (None, pp.REASON_NO_PREGAME_READING)


def test_the_boundary_is_strict_a_row_stamped_at_the_start_is_not_pregame():
    at_start = row("draftkings", 0, -3.0, 47.0)
    assert select([at_start]) == (None, pp.REASON_NO_PREGAME_READING)
    one_second_before = row("draftkings", 0, -3.0, 47.0)
    one_second_before.captured_at = KICK - timedelta(seconds=1)
    assert select([one_second_before])[0]["projected_home_score"] == 25.0


def test_latest_means_latest_a_book_whose_newest_row_has_no_pair_contributes_nothing():
    older = row("draftkings", -300, -3.0, 47.0)
    newest = row("draftkings", -5, -3.0, 47.0)
    newest.home_spread = None  # the book had pulled its spread
    newest.projected_home_score = newest.projected_away_score = None
    other = row("fanduel", -20, -6.0, 50.0)
    projection, _ = select([older, newest, other])
    # draftkings' older pair is NOT used — that would mix two times into "latest".
    assert projection["bookmaker_count"] == 1
    assert (projection["projected_home_score"], projection["projected_away_score"]) == (28.0, 22.0)


def test_equal_stamps_break_to_the_higher_id():
    low = row("draftkings", -5, -3.0, 47.0, rid=100)
    high = row("draftkings", -5, -7.0, 47.0, rid=101)
    projection, _ = select([low, high])
    assert projection["projected_home_score"] == 27.0  # high's pair
    projection, _ = select([high, low])  # input order is irrelevant
    assert projection["projected_home_score"] == 27.0


def test_home_away_order_is_the_rows_own():
    # Away favoured by 6.5: the away side must come out ahead, not "the favourite first".
    projection, _ = select([row("draftkings", -5, 6.5, 44.5, home_p=0.27)])
    assert (projection["projected_home_score"], projection["projected_away_score"]) == (19.0, 25.5)


@pytest.mark.parametrize(
    "sport, fmt",
    [
        ("americanfootball_nfl", ("points", "full_game")),
        ("americanfootball_ncaaf_fcs", ("points", "full_game")),
        ("basketball_nba", ("points", "full_game")),
        ("basketball_euroleague", ("points", "full_game")),
        ("soccer_epl", ("goals", "regulation")),
    ],
)
def test_supported_formats_are_named_with_their_unit_and_period(sport, fmt):
    # The web's PROJECTED_FINAL_FORMATS rows (frontend/lib/projectedFinalPair.ts).
    assert pp.projection_format(sport) == fmt


@pytest.mark.parametrize(
    "sport",
    [
        "baseball_mlb",                     # ±1.5 run line (#8617)
        "icehockey_nhl",                    # ±1.5 puck line — 15333056 / 15332424
        "icehockey_ahl",                    # 15327140: 1.5 / 1.5 → 0.0 – 1.5
        "tennis_atp_shanghai_masters",      # games under a sets scoreboard
        "mma_mixed_martial_arts",           # rounds (#9006)
        "boxing_boxing",
        "golf_masters_tournament_winner",
        "cricket_ipl",
        "esports_cs2",
        "rugbyleague_nrl",
        "aussierules_afl",
        "",
        None,
    ],
)
def test_the_same_sports_the_web_refuses_are_refused(sport):
    assert pp.projection_format(sport) is None


def test_a_soccer_favourite_under_fifty_on_a_three_way_board_is_not_refused():
    # 0.45 home / 0.29 away / ~0.26 draw: home leads its own moneyline.
    r = row("pinnacle", -15, -0.5, 2.5, home_p=0.45, away_p=0.29)
    assert (r.projected_home_score, r.projected_away_score) == (1.5, 1.0)
    # Control: the home-leg-only rule WOULD refuse this honest pair.
    assert projection_contradicts_moneyline(0.45, 1.5, 1.0) is True
    projection, reason = select([r], unit="goals", period="regulation")
    assert reason is None and projection["projected_home_score"] == 1.5
    assert (projection["unit"], projection["period"]) == ("goals", "regulation")


# ── refusals ─────────────────────────────────────────────────────────────────


def test_a_pair_that_crowns_its_own_moneyline_underdog_is_refused():
    r = row("betmgm", -5, -1.5, 7.5, home_p=0.095)  # #8231's mirror
    assert select([r]) == (None, pp.REASON_NO_PREGAME_READING)


def test_a_pair_that_does_not_solve_its_own_line_is_refused():
    r = row("draftkings", -5, -3.0, 47.0, pair=(30.0, 17.0))
    assert select([r]) == (None, pp.REASON_NO_PREGAME_READING)
    # Control: the same row with its own pair is admitted.
    assert select([row("draftkings", -5, -3.0, 47.0)])[0] is not None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: setattr(r, "projected_away_score", None),
        lambda r: setattr(r, "projected_home_score", math.nan),
        lambda r: setattr(r, "projected_away_score", math.inf),
        lambda r: setattr(r, "over_under", None),
        lambda r: setattr(r, "home_spread", None),
    ],
    ids=["unpaired", "nan", "inf", "no-total", "no-spread"],
)
def test_unpaired_nonfinite_or_lineless_rows_are_refused(mutate):
    r = row("draftkings", -5, -3.0, 47.0)
    mutate(r)
    assert select([r]) == (None, pp.REASON_NO_PREGAME_READING)


def test_a_negative_projection_is_refused():
    # #9006's fight shape, were it ever to reach a supported sport's rows.
    r = row("draftkings", -5, -7.5, 3.7, home_p=0.9)
    assert r.projected_away_score < 0
    assert select([r]) == (None, pp.REASON_NO_PREGAME_READING)


def test_a_reversed_book_is_excluded_by_the_existing_detector():
    rows = [
        row("a", -5, -7.0, 47.0, home_p=0.75),
        row("b", -5, -7.0, 47.0, home_p=0.76),
        row("c", -5, -7.0, 47.0, home_p=0.74),
        # home/away swapped: its own pair is coherent with its own (wrong) line.
        row("swapped", -5, 7.0, 47.0, home_p=0.25),
    ]
    projection, _ = select(rows)
    assert projection["bookmaker_count"] == 3
    assert projection["projected_home_score"] == 27.0


@pytest.mark.parametrize(
    "kwargs, reason",
    [
        ({"source": "kalshi"}, pp.REASON_START_NOT_FROM_SCHEDULE),
        ({"source": "polymarket"}, pp.REASON_START_NOT_FROM_SCHEDULE),
        ({"source": None}, pp.REASON_START_NOT_FROM_SCHEDULE),
        ({"commence": None}, pp.REASON_NO_START),
        ({"tags": [start_placeholder_tag(KICK)]}, pp.REASON_START_IS_PLACEHOLDER),
        ({"tags": [espn_start_placeholder_tag(KICK)]}, pp.REASON_START_IS_PLACEHOLDER),
        ({"sport": "tennis_atp_us_open"}, pp.REASON_FORMAT_UNSUPPORTED),
        ({"sport": "baseball_mlb"}, pp.REASON_FORMAT_UNSUPPORTED),
        ({"sport": "icehockey_nhl"}, pp.REASON_FORMAT_UNSUPPORTED),
        ({"sport": "mma_mixed_martial_arts"}, pp.REASON_FORMAT_UNSUPPORTED),
        ({"sport": "rugbyleague_nrl"}, pp.REASON_FORMAT_UNSUPPORTED),
        ({"sport": None}, pp.REASON_FORMAT_UNSUPPORTED),
    ],
)
def test_unproven_boundaries_and_unsupported_formats_are_refused_before_any_read(kwargs, reason):
    binds, answers = pp.plan_pregame_projections([event(**kwargs)], sport_of)
    assert binds is None
    assert answers == {1: {pp.UNAVAILABLE_KEY: reason}}


@pytest.mark.parametrize("source", ["espn", "statpal", "odds_api"])
def test_every_schedule_provider_admits_the_start(source):
    binds, answers = pp.plan_pregame_projections([event(source=source)], sport_of)
    assert answers == {} and binds["ids"] == [1] and binds["cutoffs"] == [KICK]


def test_a_placeholder_tag_for_another_instant_does_not_refuse():
    binds, _ = pp.plan_pregame_projections(
        [event(tags=[start_placeholder_tag(KICK - timedelta(hours=3))])], sport_of
    )
    assert binds is not None


@pytest.mark.parametrize("status", ["scheduled", "live", "suspended", None])
def test_unsettled_rows_are_not_asked(status):
    assert pp.plan_pregame_projections([event(status=status)], sport_of) == (None, {})


# ── reschedule and late arrival ──────────────────────────────────────────────


def test_a_rescheduled_start_moves_the_boundary_both_ways():
    rows = [row("draftkings", -60, -3.0, 47.0), row("draftkings", 60, -9.0, 47.0)]
    later = KICK + timedelta(hours=2)   # postponed: the +60 row is now pregame
    binds, _ = pp.plan_pregame_projections([event(commence=later)], sport_of)
    assert binds["cutoffs"] == [later]
    assert pp.answers_from_rows(binds, rows)[1][pp.PROJECTION_KEY]["projected_home_score"] == 28.0
    earlier = KICK - timedelta(hours=2)  # brought forward: neither row is pregame
    binds, _ = pp.plan_pregame_projections([event(commence=earlier)], sport_of)
    assert pp.answers_from_rows(binds, rows) == {1: {pp.UNAVAILABLE_KEY: pp.REASON_NO_PREGAME_READING}}


def test_a_late_arriving_in_play_row_cannot_displace_the_pregame_answer():
    # Highest id, newest stamp, after the start: the shape a selector ordered by
    # id or by arrival would take.
    pre = row("draftkings", -5, -3.0, 47.0, rid=10)
    late = row("draftkings", 1, -14.0, 47.0, rid=99_999)
    assert select([late, pre])[0]["projected_home_score"] == 25.0


# ── many events in one statement ─────────────────────────────────────────────


def test_answers_are_keyed_by_their_own_event_and_cutoff():
    e1, e2 = event(1), event(2, commence=KICK + timedelta(days=1))
    binds, _ = pp.plan_pregame_projections([e1, e2], sport_of)
    rows = [
        row("draftkings", -5, -3.0, 47.0, event_id=1),
        # e2's row sits after e1's start but before e2's: pregame for e2 only.
        row("draftkings", 60, -9.0, 41.0, event_id=2),
    ]
    answers = pp.answers_from_rows(binds, rows)
    assert answers[1][pp.PROJECTION_KEY]["projected_home_score"] == 25.0
    assert answers[2][pp.PROJECTION_KEY]["projected_home_score"] == 25.0
    assert answers[2][pp.PROJECTION_KEY]["boundary_at"] == e2.commence_time.isoformat()


class _FakeDb:
    def __init__(self, rows=(), fail=False):
        self.rows, self.fail, self.executed = list(rows), fail, []
        self.savepoint_ends: list[str] = []

    async def begin_nested(self):
        return SimpleNamespace(commit=self._commit, rollback=self._rollback)

    async def _commit(self):
        self.savepoint_ends.append("commit")

    async def _rollback(self):
        self.savepoint_ends.append("rollback")

    async def execute(self, statement, params=None):
        self.executed.append((str(statement), params))
        if self.fail and "statement_timeout" not in str(statement):
            raise RuntimeError("canceling statement due to statement timeout")
        return SimpleNamespace(all=lambda: self.rows)


def test_one_statement_serves_every_settled_row_on_the_page():
    events = [event(i) for i in range(1, 26)] + [event(99, status="scheduled")]
    db = _FakeDb([row("draftkings", -5, -3.0, 47.0, event_id=i) for i in range(1, 26)])
    answers = asyncio.run(pp.read_pregame_projections(db, events, sport_of))
    assert len(db.executed) == 1
    sql, params = db.executed[0]
    assert sql == pp.PREGAME_PROJECTION_SQL
    assert params["ids"] == list(range(1, 26)) and len(params["cutoffs"]) == 25
    assert set(answers) == set(range(1, 26))  # the scheduled row is not asked
    assert all(pp.PROJECTION_KEY in a for a in answers.values())


def test_no_statement_when_nothing_can_be_answered_by_a_read():
    db = _FakeDb()
    events = [event(1, source="kalshi"), event(2, status="live")]
    answers = asyncio.run(pp.read_pregame_projections(db, events, sport_of))
    assert db.executed == []
    assert answers == {1: {pp.UNAVAILABLE_KEY: pp.REASON_START_NOT_FROM_SCHEDULE}}


def test_a_failed_read_answers_read_failed_and_keeps_the_earlier_refusals():
    db = _FakeDb(fail=True)
    events = [event(1), event(2, sport="tennis_atp")]
    answers = asyncio.run(pp.read_pregame_projections(db, events, sport_of))
    assert answers == {
        1: {pp.UNAVAILABLE_KEY: pp.REASON_READ_FAILED},
        2: {pp.UNAVAILABLE_KEY: pp.REASON_FORMAT_UNSUPPORTED},
    }


# ── provenance ───────────────────────────────────────────────────────────────


def test_the_projection_is_a_sibling_and_never_inherits_the_priors_source():
    payload = {"prematch_odds": {"home_probability": 0.61, "source": "kalshi"}}
    projection, _ = select([row("draftkings", -5, -3.0, 47.0)])
    pp.attach_pregame_projection(payload, {pp.PROJECTION_KEY: projection})
    assert payload["prematch_odds"] == {"home_probability": 0.61, "source": "kalshi"}
    assert payload["pregame_projection"]["source"] == "sportsbooks"
    assert pp.UNAVAILABLE_KEY not in payload
    # A copy, so one surface cannot mutate another's object.
    payload["pregame_projection"]["source"] = "x"
    assert projection["source"] == "sportsbooks"


def test_a_refusal_serves_only_its_reason_and_an_unasked_row_serves_nothing():
    payload = {}
    pp.attach_pregame_projection(payload, {pp.UNAVAILABLE_KEY: pp.REASON_NO_PREGAME_READING})
    assert payload == {"pregame_projection_unavailable": "no_pregame_reading"}
    untouched = {}
    pp.attach_pregame_projection(untouched, None)
    assert untouched == {}


def test_the_statement_bounds_by_the_cutoff_strictly_and_walks_the_closing_index():
    sql = " ".join(pp.PREGAME_PROJECTION_SQL.split())
    assert "s.captured_at < k.cutoff" in sql
    assert "ORDER BY s.captured_at DESC, s.id DESC LIMIT 1" in sql
    assert "unnest(cast(:ids as integer[]), cast(:cutoffs as timestamptz[]))" in sql
    for column in ("projected_home_score", "projected_away_score", "home_spread",
                   "over_under", "home_win_probability", "away_win_probability"):
        assert f"x.{column}" in sql


def test_the_kind_names_the_scheduled_boundary_and_never_a_stronger_claim():
    # "latest_before_play" needs an observed start and "opening" an evidenced
    # opening; neither exists for this read, so neither may be produced.
    projection, _ = select([row("draftkings", -5, -3.0, 47.0)])
    assert projection["kind"] == pp.KIND_LAST_BEFORE_SCHEDULED_START
    assert projection["boundary"] == "scheduled_start"
    assert "captured_at" not in projection  # a range, never one stamp for the whole


def test_the_status_the_card_prints_decides_not_the_stored_column():
    # Discover's clearance condition 1: #11295 keys its current pair on the
    # SERVED status, so this keys on the same one and a card carries at most one.
    stored_final_served_live = event(1, status="completed")
    stored_live_served_final = event(2, status="live")
    served = {1: "live", 2: "completed"}
    binds, answers = pp.plan_pregame_projections(
        [stored_final_served_live, stored_live_served_final],
        sport_of,
        status_of=lambda e: served[e.id],
    )
    assert binds["ids"] == [2] and answers == {}
    # Without a served status the stored column is the fallback.
    binds, _ = pp.plan_pregame_projections([stored_final_served_live], sport_of)
    assert binds["ids"] == [1]


def test_a_bounded_read_sets_its_own_timeout_and_rolls_the_savepoint_back():
    # #11295's C1, applied to the feed's read: SET LOCAL inside the savepoint,
    # and a ROLLBACK (never a release) so the bound cannot outlive the read.
    db = _FakeDb([row("draftkings", -5, -3.0, 47.0)])
    answers = asyncio.run(pp.read_pregame_projections(db, [event()], sport_of, timeout_ms=1200))
    assert [sql for sql, _ in db.executed] == [
        "SET LOCAL statement_timeout = '1200ms'", pp.PREGAME_PROJECTION_SQL,
    ]
    assert db.savepoint_ends == ["rollback"]
    assert pp.PROJECTION_KEY in answers[1]


def test_no_budget_left_means_no_round_trip_and_read_failed():
    db = _FakeDb([row("draftkings", -5, -3.0, 47.0)])
    answers = asyncio.run(pp.read_pregame_projections(
        db, [event(1), event(2, sport="tennis_atp")], sport_of, timeout_ms=0
    ))
    assert db.executed == [] and db.savepoint_ends == []
    assert answers == {
        1: {pp.UNAVAILABLE_KEY: pp.REASON_READ_FAILED},
        2: {pp.UNAVAILABLE_KEY: pp.REASON_FORMAT_UNSUPPORTED},
    }


def test_a_timed_out_read_still_rolls_back_and_answers_read_failed():
    db = _FakeDb(fail=True)
    answers = asyncio.run(pp.read_pregame_projections(db, [event()], sport_of, timeout_ms=50))
    assert db.savepoint_ends == ["rollback"]
    assert answers == {1: {pp.UNAVAILABLE_KEY: pp.REASON_READ_FAILED}}


def test_a_cancellation_propagates_as_itself():
    class _Cancelled(_FakeDb):
        async def execute(self, statement, params=None):
            raise asyncio.CancelledError()

    db = _Cancelled()
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(pp.read_pregame_projections(db, [event()], sport_of))
    assert db.savepoint_ends == ["rollback"]
