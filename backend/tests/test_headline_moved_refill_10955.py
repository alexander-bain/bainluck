"""#10955 / #7547 — a stored price that moved after the chart's last word re-asks the venue.

PILLARS: TRUTH / FORMATTING. SHIP: a tennis reader sees genuine recent
probability changes for the same named outcome, with honest timestamps and gaps
between headline and chart.

The retained specimen (authority's public reads, 2026-10-21 23:17Z):
`/futures/66891390` "Rinaldo Persson vs Mercier" (KXITFWMATCH-26OCT21RINMER).
`/history` served three discovery-poll captures per player (15:05:10, 17:24:45,
19:03:13Z), the last one Persson 0.895 / Mercier 0.11. The detail served
Persson 0.545 / Mercier 0.455, both `price_changed_at` 23:16:56Z, written by
the Kalshi socket's open-contract arm, which writes no snapshot row. Outcome
251242709 is Mercier in both payloads, so the sides agree. The defect is the
four-hour hole between them.

These tests pin the rule that lets the chart's bank re-ask Kalshi inside its
three-hour negative cache, and the fences that keep it from drawing the stored
price, inventing samples, triggering on a settlement, or spending more than
the hour's existing coarse budget.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from app.tasks import generic_market_history_fill as fill
from app.utils import generic_market_history as gmh

APP = Path(__file__).resolve().parents[1] / "app"


def _z(hh: int, mm: int, ss: int = 0) -> datetime:
    return datetime(2026, 10, 21, hh, mm, ss, tzinfo=timezone.utc)


MERCIER, PERSSON = 251242709, 251242708
CAPTURES = {
    MERCIER: [(_z(15, 5, 10), 0.115), (_z(17, 24, 45), 0.115), (_z(19, 3, 13), 0.11)],
    PERSSON: [(_z(15, 5, 10), 0.88), (_z(17, 24, 45), 0.88), (_z(19, 3, 13), 0.895)],
}
SOCKET_WRITE = _z(23, 16, 56)
STORED = {MERCIER: (0.455, SOCKET_WRITE), PERSSON: (0.545, SOCKET_WRITE)}


# ── the pure rule, on the specimen's own retained values ─────────────────────


def test_the_specimen_reads_as_a_move_nothing_on_the_chart_draws():
    assert gmh.headline_moved_past_history(CAPTURES, STORED, bank_attempted_at=None) is True
    # A bank asked BEFORE the socket write has not seen the move either.
    assert gmh.headline_moved_past_history(
        CAPTURES, STORED, bank_attempted_at=_z(21, 0)
    ) is True


def test_a_bank_asked_after_the_move_is_left_to_draw_it():
    assert gmh.headline_moved_past_history(
        CAPTURES, STORED, bank_attempted_at=_z(23, 17)
    ) is False


def test_a_capture_after_the_move_already_draws_it():
    later = {k: v + [(_z(23, 20), STORED[k][0])] for k, v in CAPTURES.items()}
    assert gmh.headline_moved_past_history(later, STORED, bank_attempted_at=None) is False


def test_the_polls_own_clock_lag_is_not_a_move():
    """The 19:03:13Z capture's row was written at 19:06:18Z with the SAME price."""
    stored = {MERCIER: (0.11, _z(19, 6, 18)), PERSSON: (0.895, _z(19, 6, 18))}
    assert gmh.headline_moved_past_history(CAPTURES, stored, bank_attempted_at=None) is False


def test_quiet_and_unpriced_lines_never_ask():
    assert gmh.headline_moved_past_history(
        CAPTURES, {MERCIER: (None, SOCKET_WRITE), PERSSON: (0.545, None)},
        bank_attempted_at=None,
    ) is False
    # A stamp older than the newest capture is a quiet line, whatever its price.
    assert gmh.headline_moved_past_history(
        CAPTURES, {MERCIER: (0.2, _z(16, 0))}, bank_attempted_at=None
    ) is False


def test_a_new_market_with_no_capture_but_a_moved_price_asks():
    assert gmh.headline_moved_past_history(
        {}, {MERCIER: (0.455, SOCKET_WRITE)}, bank_attempted_at=_z(22, 0)
    ) is True


def test_naive_database_stamps_are_read_as_utc():
    naive_caps = {MERCIER: [(ts.replace(tzinfo=None), p) for ts, p in CAPTURES[MERCIER]]}
    naive_stored = {MERCIER: (0.455, SOCKET_WRITE.replace(tzinfo=None))}
    assert gmh.headline_moved_past_history(
        naive_caps, naive_stored, bank_attempted_at=_z(23, 17)
    ) is False
    assert gmh.headline_moved_past_history(
        naive_caps, naive_stored, bank_attempted_at=_z(21, 0)
    ) is True


# ── the planner: one bounded exception to the three-hour cache ───────────────


class _Redis:
    def __init__(self):
        self.kv, self.ttl = {}, {}

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.kv:
            return False
        self.kv[key] = value
        self.ttl[key] = ex
        return True

    def get(self, key):
        return self.kv.get(key)

    def incr(self, key):
        self.kv[key] = int(self.kv.get(key, 0)) + 1
        return self.kv[key]

    def decr(self, key):
        self.kv[key] = int(self.kv.get(key, 0)) - 1
        return self.kv[key]

    def expire(self, key, seconds):
        self.ttl[key] = seconds

    def delete(self, key):
        self.kv.pop(key, None)


ATTEMPT = _z(22, 0)
MARKET = SimpleNamespace(id=66891390, source="kalshi",
                         external_id="KXITFWMATCH-26OCT21RINMER", status="open")
OUTCOMES = [SimpleNamespace(id=MERCIER, external_id="KXITFWMATCH-26OCT21RINMER-MER"),
            SimpleNamespace(id=PERSSON, external_id="KXITFWMATCH-26OCT21RINMER-RIN")]


def _bank(**over):
    body = {"attempted_at": ATTEMPT.isoformat(), "built_at": ATTEMPT.isoformat(),
            "status": "ok", "outcomes": {str(MERCIER): {"points": [[ATTEMPT.isoformat(), 0.11]]}},
            "stats": {"fetched_points": 1}}
    body.update(over)
    return body


def _plan(payload, *, moved, after, market=MARKET, rc=None, thin=False):
    return fill.plan_on_demand_fill(
        market, OUTCOMES, payload, chart_is_thin=thin, chart_is_coarse=moved,
        headline_moved=moved, now=ATTEMPT + after, rc=rc or _Redis(),
    )


def test_without_a_move_the_three_hour_cache_is_unchanged():
    assert _plan(_bank(), moved=False, after=timedelta(hours=1))["reason"] == "answered_recently"


def test_a_move_after_the_bank_re_asks_inside_the_three_hours():
    assert fill.HEADLINE_MOVED_REFRESH_SECONDS < fill.REFRESH_AFTER_SECONDS
    assert _plan(_bank(), moved=True, after=timedelta(hours=1)) == {
        "enqueue": True, "reason": "claimed"}


def test_the_re_ask_waits_out_its_own_floor():
    just_under = timedelta(seconds=fill.HEADLINE_MOVED_REFRESH_SECONDS - 1)
    assert _plan(_bank(), moved=True, after=just_under)["reason"] == "answered_recently"
    at_floor = timedelta(seconds=fill.HEADLINE_MOVED_REFRESH_SECONDS)
    assert _plan(_bank(), moved=True, after=at_floor)["enqueue"] is True


def test_the_re_ask_spends_the_coarse_share_and_keeps_the_claim():
    rc = _Redis()
    hour = (ATTEMPT + timedelta(hours=1)).strftime("%Y%m%d%H")
    rc.kv[gmh.coarse_budget_key(hour)] = fill.COARSE_FILL_CAP
    assert _plan(_bank(), moved=True, after=timedelta(hours=1), rc=rc)["reason"] == "coarse_hourly_cap"
    rc = _Redis()
    assert _plan(_bank(), moved=True, after=timedelta(hours=1), rc=rc)["enqueue"] is True
    assert _plan(_bank(), moved=True, after=timedelta(hours=1), rc=rc)["reason"] == "already_claimed"


def test_a_settled_answer_is_never_re_asked_for_a_move():
    settled = SimpleNamespace(**{**vars(MARKET), "status": "settled"})
    answered = _bank(market_settled=True)
    assert _plan(answered, moved=True, after=timedelta(hours=1),
                 market=settled)["reason"] == "settled_and_already_answered"


# ── the route half: both readers ask, and it never widens a first fill ───────


def _venue(payload=None, applicable=True, state="warm"):
    return SimpleNamespace(applicable=applicable, state=state, payload=payload)


def _outcome_row(oid, ext, price, changed, is_winner=None, name="Player"):
    return SimpleNamespace(id=oid, external_id=ext, name=name, current_probability=price,
                           price_changed_at=changed, is_winner=is_winner)


def _market_row(status="open", winner=None):
    return SimpleNamespace(
        id=66891390, source="kalshi", status=status,
        outcomes=[
            _outcome_row(MERCIER, "KXITFWMATCH-26OCT21RINMER-MER", 0.455, SOCKET_WRITE,
                         winner, "Clemence Mercier"),
            _outcome_row(PERSSON, "KXITFWMATCH-26OCT21RINMER-RIN", 0.545, SOCKET_WRITE,
                         None if winner is None else (not winner), "Kajsa Rinaldo Persson"),
        ],
    )


def _capture_rows(extra=()):
    rows = [SimpleNamespace(outcome_id=oid, captured_at=ts, probability=p, bookmaker="kalshi")
            for oid, caps in CAPTURES.items() for ts, p in caps]
    return rows + list(extra)


def test_route_rule_fires_on_the_specimen_and_respects_its_fences():
    from app.routes.futures import _headline_moved_past_history as moved

    bank = _bank()
    assert moved(_venue(bank), _market_row(), _capture_rows()) is True
    # No bank attempt: the thin/coarse gates own the first fill, unchanged.
    assert moved(_venue(None), _market_row(), _capture_rows()) is False
    assert moved(_venue(bank, applicable=False), _market_row(), _capture_rows()) is False
    assert moved(_venue(bank, state="unavailable"), _market_row(), _capture_rows()) is False
    # A settled market and graded lines: a result's stamp is not a trade.
    assert moved(_venue(bank), _market_row(status="settled"), _capture_rows()) is False
    assert moved(_venue(bank), _market_row(winner=True), _capture_rows()) is False


def test_route_rule_ignores_settlement_markers_as_captures():
    from app.routes.futures import _headline_moved_past_history as moved

    marker = [SimpleNamespace(outcome_id=oid, captured_at=_z(23, 30), probability=p,
                              bookmaker="settlement")
              for oid, (p, _) in STORED.items()]
    assert moved(_venue(_bank()), _market_row(), _capture_rows(marker)) is True
    real = [SimpleNamespace(outcome_id=oid, captured_at=_z(23, 30), probability=p,
                            bookmaker="kalshi")
            for oid, (p, _) in STORED.items()]
    assert moved(_venue(_bank()), _market_row(), _capture_rows(real)) is False


def test_both_chart_readers_pass_the_move_to_the_planner():
    """`/history` (web) and `/probability-timeline` (iPhone) must not disagree."""
    src = (APP / "routes" / "futures.py").read_text()
    timeline = _route_body(src, "get_probability_timeline")
    history = _route_body(src, "get_futures_history")
    # Each reader hands the rule its WHOLE field's captures: the timeline's
    # `snapshots` span the field; `/history`'s are the drawn subset, so it hands
    # in `_supported_field` instead (lane1 F1 on 334edae8ce).
    assert "_moved = _headline_moved_past_history(venue, market, snapshots)" in timeline
    assert "_moved = _headline_moved_past_history(venue, market, _supported_field)" in history
    assert "_headline_moved_past_history(venue, market, snapshots)" not in history
    assert len(re.findall(r"headline_moved=_moved,", src)) == 2
    assert len(re.findall(r"or _leg_absent or _moved", src)) == 2


def _route_body(src: str, name: str) -> str:
    return src.split(f"async def {name}(", 1)[1].split("\n@router.", 1)[0]


def _poll_priced_board():
    """A poll-priced 3-leg board: the 19:03 poll moved every leg AND captured it."""
    def leg(oid, p):
        return SimpleNamespace(id=oid, external_id=f"KXNBA-27-T{oid}", name=f"Team {oid}",
                               current_probability=p, price_changed_at=_z(19, 3), is_winner=None)

    market = SimpleNamespace(id=1, source="kalshi", status="open",
                             outcomes=[leg(1, 0.40), leg(2, 0.35), leg(3, 0.25)])
    rows = [SimpleNamespace(outcome_id=o.id, captured_at=_z(19, 3, 1),
                            probability=o.current_probability, bookmaker="kalshi")
            for o in market.outcomes]
    return market, rows


def test_history_narrowed_to_one_drawn_leg_does_not_ask_for_undrawn_legs_moves():
    """`/history?outcome_id=<leader>` (team pages) and `top_n` below the fillable
    twelve (golf, winner evolution) draw a subset. The undrawn legs' captures at
    their stored prices after the move still answer "the captures cover it"."""
    from app.routes.futures import _headline_moved_past_history as moved

    market, rows = _poll_priced_board()
    venue = _venue(_bank(attempted_at=_z(18, 0).isoformat()))
    drawn = [r for r in rows if r.outcome_id == 1]  # what `snapshots` holds on /history?outcome_id=1
    # The defect lane1 probed: handed only the drawn leg, the rule fires.
    assert moved(venue, market, drawn) is True
    # The call site now hands in the field: no ask.
    assert moved(venue, market, rows) is False
    # A move on an UNDRAWN leg with no capture after it still stales the bank,
    # so narrowing the lines to the drawn ids would be the wrong repair.
    market.outcomes[2].current_probability = 0.31
    market.outcomes[2].price_changed_at = _z(20, 0)
    assert moved(venue, market, rows) is True


def test_the_rule_reads_stored_prices_and_writes_no_chart_point():
    """It decides whether to ask. It never turns a stored price into a sample."""
    src = (APP / "utils" / "generic_market_history.py").read_text()
    body = src.split("def headline_moved_past_history(", 1)[1].split("\ndef ", 1)[0]
    assert "VenuePoint(" not in body and "append(" not in body
