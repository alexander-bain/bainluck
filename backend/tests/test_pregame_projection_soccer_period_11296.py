"""#11296 soccer slice — a settled soccer row says when its actual score is the 90-minute score.

Soccer's pregame forecast settles on ``regulation``. The web compares a final
with it only when the caller can pass ``actualPeriod: "regulation"`` from real
evidence, and until now no payload said whether a soccer final went to extra
time or penalties, so every soccer final was withheld. The producer now serves
``final_score_period: "regulation"`` from the row's own stored ``period``, under
the contract the three-way accuracy curve already grades on
(``soccer_three_way.regulation_finish_proven``, CERT-4066), and nothing else.

THE DECIDING CASE IS A SAVED SERVED READING, NOT A FIXTURE. VfB Stuttgart v
Atlético Madrid, event 15330334, as `/api/events/15330334` served it at
2026-10-20T20:54:12Z (``state_read_not_before``), saved at
``artifacts/sports-bug-report-20261020/event-15330334-final.json``
(sha256 b5a5334ba52afe208e8a04793bc2b3a6c950ac99c44cd0dac5d4503101f256bf).
The values below are copied from those bytes; the file itself is not read here
(it is not in the repo).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils import pregame_projection as pp
from app.utils.game_state import normalize_live_game_state
from app.utils.odds_math import project_scores
from app.utils.soccer_three_way import regulation_finish_proven

SOCCER = "soccer_uefa_champs_league"

# ── the saved served reading of 15330334 (copied verbatim) ──────────────────
S_ID = 15330334
S_COMMENCE = datetime(2026, 10, 20, 19, 0, tzinfo=timezone.utc)
S_SERVED = {
    "id": S_ID,
    "sport": SOCCER,
    "home_team": "VfB Stuttgart",
    "away_team": "Atlético Madrid",
    "commence_time": "2026-10-20T19:00:00+00:00",
    "start_is_from_schedule": True,
    "status": "completed",
    "home_score": 1,
    "away_score": 1,
    "espn": {"espn_id": "401915392", "game_clock": "90'+4'", "period": "FT"},
    "pregame_projection": {
        "projected_home_score": 1.5,
        "projected_away_score": 1.9,
        "kind": "last_before_scheduled_start",
        "earliest_captured_at": "2026-10-20T18:37:57.209904+00:00",
        "latest_captured_at": "2026-10-20T18:56:23.853083+00:00",
        "boundary": "scheduled_start",
        "boundary_at": "2026-10-20T19:00:00+00:00",
        "source": "sportsbooks",
        "basis": "consensus_spread_total",
        "bookmaker_count": 4,
        "unit": "goals",
        "period": "regulation",
    },
    "hero_settled_result": "draw",
}


def _row(eid=S_ID, *, status="completed", period="FT", sport=SOCCER, commence=S_COMMENCE,
         source="espn"):
    return SimpleNamespace(
        id=eid, status=status, period=period, sport_key=sport, commence_time=commence,
        commence_time_source=source, event_tags=[],
    )


def _sport_of(e):
    return e.sport_key


def _snap(book, minutes, spread, total, home_p, away_p, *, eid=S_ID, start=S_COMMENCE, rid):
    home, away = project_scores(spread, total)
    return SimpleNamespace(
        id=rid, event_id=eid, bookmaker=book,
        captured_at=start + timedelta(minutes=minutes),
        home_win_probability=home_p, away_win_probability=away_p,
        home_spread=spread, over_under=total,
        projected_home_score=home, projected_away_score=away,
    )


class _FakeDb:
    def __init__(self, rows=(), fail=False):
        self.rows, self.fail, self.executed = list(rows), fail, []

    async def begin_nested(self):
        async def _end():
            return None
        return SimpleNamespace(commit=_end, rollback=_end)

    async def execute(self, statement, params=None):
        self.executed.append((str(statement), params))
        if self.fail and "statement_timeout" not in str(statement):
            raise RuntimeError("canceling statement due to statement timeout")
        ids = (params or {}).get("ids") or []
        return SimpleNamespace(all=lambda: [r for r in self.rows if r.event_id in ids])


def _read(events, rows=(), **kwargs):
    db = _FakeDb(rows, fail=kwargs.pop("fail", False))
    return asyncio.run(pp.read_pregame_projections(db, events, _sport_of, **kwargs)), db


# ── the deciding positive ────────────────────────────────────────────────────


def test_the_served_ft_on_15330334_is_its_stored_period_verbatim():
    # The page serves `espn.period` through `normalize_live_game_state`, which
    # rewrites only baseball. So the served "FT" IS the stored `events.period`.
    assert normalize_live_game_state(SOCCER, "FT", "90'+4'") == ("FT", "90'+4'")
    assert regulation_finish_proven(S_SERVED["espn"]["period"])


def test_15330334_serves_regulation_beside_its_own_regulation_forecast():
    stored = _row(period=S_SERVED["espn"]["period"], status=S_SERVED["status"])
    payload = {k: v for k, v in S_SERVED.items() if k != "pregame_projection"}
    answers, _ = _read([stored], status_of=lambda e: payload["status"])
    assert answers[S_ID][pp.SCORE_PERIOD_KEY] == "regulation"
    # Attach the served forecast exactly as served, with the producer's period.
    pp.attach_pregame_projection(
        payload,
        {pp.PROJECTION_KEY: S_SERVED["pregame_projection"],
         pp.SCORE_PERIOD_KEY: answers[S_ID][pp.SCORE_PERIOD_KEY]},
    )
    forecast = payload["pregame_projection"]
    # The pairing the card and the page compare on: same game, same unit, same
    # period, forecast read strictly before the row's own published start.
    assert payload["final_score_period"] == forecast["period"] == "regulation"
    assert forecast["unit"] == "goals"
    assert forecast["boundary_at"] == payload["commence_time"] == S_COMMENCE.isoformat()
    assert forecast["latest_captured_at"] < forecast["boundary_at"]
    # The ultimate result is untouched: a 1–1 draw, served as it was.
    assert (payload["home_score"], payload["away_score"]) == (1, 1)
    assert payload["hero_settled_result"] == "draw"


def test_a_read_with_rows_serves_the_period_beside_the_projection():
    # Constructed rows (not served): the producer path end to end on one soccer
    # final. Three-way legs, home the moneyline underdog, as on 15330334.
    rows = [
        _snap("draftkings", -10, 0.5, 3.5, 0.30, 0.44, rid=1),
        _snap("fanduel", -20, 0.5, 3.5, 0.31, 0.43, rid=2),
        _snap("fanduel", 30, 1.5, 2.5, 0.10, 0.70, rid=3),  # in-play, excluded
    ]
    answers, db = _read([_row()], rows)
    assert len(db.executed) == 1
    projection = answers[S_ID][pp.PROJECTION_KEY]
    assert (projection["unit"], projection["period"]) == ("goals", "regulation")
    assert answers[S_ID][pp.SCORE_PERIOD_KEY] == "regulation"
    payload = {}
    pp.attach_pregame_projection(payload, answers[S_ID])
    assert payload["final_score_period"] == "regulation"
    assert payload["pregame_projection"]["bookmaker_count"] == 2


# ── refusals: the period is not established ─────────────────────────────────


@pytest.mark.parametrize(
    "period",
    [
        None,          # no provider finished the row with a status
        "",
        "90'+4'",      # a live token left behind
        "2H",
        "HT",
        "AET",         # after extra time: the score is the 120-minute score
        "FT-Pens",     # a shootout finish: the tally is not goals
        "Pens",
        "FT (AET)",
        "ft",          # exact equality: a new spelling refuses, never admits
        "Final",
        " FT",
    ],
)
def test_a_soccer_final_without_a_full_time_finish_serves_no_period(period):
    answers, _ = _read([_row(period=period)])
    assert pp.SCORE_PERIOD_KEY not in answers.get(S_ID, {})
    payload = {}
    pp.attach_pregame_projection(payload, answers.get(S_ID))
    assert "final_score_period" not in payload


def test_an_extra_time_final_keeps_its_result_and_serves_no_period():
    # An extra-time 3–2 cannot be paired with a 90-minute forecast. Its result
    # still serves (nothing here touches it); only the comparison key is absent.
    rows = [_snap("draftkings", -10, 0.5, 3.5, 0.30, 0.44, rid=1)]
    answers, _ = _read([_row(period="AET")], rows)
    payload = {"home_score": 3, "away_score": 2, "status": "completed"}
    pp.attach_pregame_projection(payload, answers[S_ID])
    assert "final_score_period" not in payload
    assert payload["pregame_projection"]["period"] == "regulation"  # the forecast's own
    assert (payload["home_score"], payload["away_score"]) == (3, 2)


def test_only_the_status_the_card_prints_can_settle_the_period():
    # Stored FT, card prints live: not settled, no key. Stored completed on a
    # scheduled card: no key.
    answers, _ = _read([_row(status="completed")], status_of=lambda e: "live")
    assert answers == {}
    answers, _ = _read([_row(status="scheduled")])
    assert answers == {}


@pytest.mark.parametrize(
    "sport,period",
    [
        ("americanfootball_nfl", "Final"),
        ("americanfootball_nfl", "FT"),
        ("basketball_nba", "Final/OT"),
        ("basketball_nba", "FT"),
        ("icehockey_nhl", "FT"),
        ("tennis_atp_paris", "FT"),
    ],
)
def test_no_other_sport_gains_the_key(sport, period):
    # Football and basketball callers keep passing `full_game`; their payloads
    # are unchanged. Every other sport stays unsupported.
    answers, _ = _read([_row(sport=sport, period=period)])
    assert pp.SCORE_PERIOD_KEY not in answers.get(S_ID, {})


# ── the period never manufactures a comparison ──────────────────────────────


def test_missing_baseline_serves_the_period_and_no_forecast():
    answers, _ = _read([_row()], rows=[])
    assert answers[S_ID] == {
        pp.UNAVAILABLE_KEY: pp.REASON_NO_PREGAME_READING,
        pp.SCORE_PERIOD_KEY: "regulation",
    }
    payload = {}
    pp.attach_pregame_projection(payload, answers[S_ID])
    assert "pregame_projection" not in payload


def test_a_last_live_pair_is_not_a_pregame_forecast_even_with_the_period_proven():
    rows = [
        _snap("draftkings", 0, 0.5, 3.5, 0.30, 0.44, rid=1),    # at the start
        _snap("fanduel", 88, -1.5, 1.5, 0.95, 0.01, rid=2),     # last live
    ]
    answers, _ = _read([_row()], rows)
    assert answers[S_ID] == {
        pp.UNAVAILABLE_KEY: pp.REASON_NO_PREGAME_READING,
        pp.SCORE_PERIOD_KEY: "regulation",
    }


def test_a_start_not_from_a_schedule_refuses_the_forecast_but_not_the_period():
    answers, db = _read([_row(source="kalshi")])
    assert db.executed == []
    assert answers[S_ID] == {
        pp.UNAVAILABLE_KEY: pp.REASON_START_NOT_FROM_SCHEDULE,
        pp.SCORE_PERIOD_KEY: "regulation",
    }


@pytest.mark.parametrize("kwargs", [{"fail": True}, {"timeout_ms": 0}])
def test_a_failed_read_still_serves_the_period(kwargs):
    answers, _ = _read([_row()], **kwargs)
    assert answers[S_ID] == {
        pp.UNAVAILABLE_KEY: pp.REASON_READ_FAILED,
        pp.SCORE_PERIOD_KEY: "regulation",
    }


def test_attach_serves_only_the_one_value():
    payload = {}
    pp.attach_pregame_projection(payload, {pp.SCORE_PERIOD_KEY: "full_game"})
    assert payload == {}
    pp.attach_pregame_projection(payload, {pp.SCORE_PERIOD_KEY: "regulation"})
    assert payload == {"final_score_period": "regulation"}


def test_a_row_that_did_not_load_period_refuses_and_never_lazy_loads():
    class _Deferred:
        id = S_ID
        status = "completed"

        def __init__(self):
            self.__dict__.update(id=S_ID, status="completed")

        @property
        def period(self):  # a deferred column: touching it is a lazy load
            raise AssertionError("lazy load of period")

    assert pp.final_score_period(_Deferred(), SOCCER, "completed") is None


# ── the list surfaces carry it through their own attaches ──────────────────


def _soccer_card(eid, status="completed"):
    return {"id": eid, "status": status, "sport": SOCCER, "home_score": 1, "away_score": 1}


def test_feed_cards_carry_the_period_on_a_full_time_final_only():
    from app.routes.feed import _attach_pregame_projections

    ft, aet, live = 1, 2, 3
    events = [_row(ft), _row(aet, period="AET"), _row(live, status="live", period="62'")]
    items = [
        {"type": "event", "data": _soccer_card(ft)},
        {"type": "event", "data": _soccer_card(aet)},
        {"type": "event", "data": _soccer_card(live, "live")},
    ]
    rows = [_snap("draftkings", -10, 0.5, 3.5, 0.30, 0.44, eid=ft, rid=1)]
    db = _FakeDb(rows)
    asyncio.run(_attach_pregame_projections(db, items, events))
    by_id = {i["data"]["id"]: i["data"] for i in items}
    assert by_id[ft]["final_score_period"] == "regulation"
    assert by_id[ft]["pregame_projection"]["period"] == "regulation"
    assert "final_score_period" not in by_id[aet]
    assert "final_score_period" not in by_id[live]


def test_league_results_rail_carries_the_period_on_a_full_time_final_only():
    from app.routes.league_futures import _attach_pregame_projections

    ft, pens = 1, 2
    events = [_row(ft), _row(pens, period="FT-Pens")]
    briefs = [_soccer_card(ft), _soccer_card(pens)]
    asyncio.run(_attach_pregame_projections(_FakeDb(), events, briefs))
    assert briefs[0]["final_score_period"] == "regulation"
    assert "final_score_period" not in briefs[1]
