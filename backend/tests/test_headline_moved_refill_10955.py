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

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

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


# ── #10955 Kalshi 2-leg binary paired compaction & overlap reproducer ────────
#
# Retained runtime evidence vs constructed reproducer inputs:
#   * RETAINED (`artifacts/live/10955-unadmitted-capture-20261025T0720Z/R3-public-history-67318590.json`,
#     sha256 `adb9c91d6dab7b9aafa0944d510e90f1c118e0176aab2ac0daf543334750cebb`):
#     market_id=67318590, market_name="Henning vs Nagel", total_data_points=13,
#     observation_times=7, outcome 252747654 ("Arthur Nagel", 7 points starting at
#     2026-10-24T18:52:13.233004+00:00 prob 0.11 and ending at
#     2026-10-25T06:53:54.025606+00:00 prob 0.39) and outcome 252747653
#     ("Philip Henning", 6 points starting at 2026-10-24T21:01:57.708338+00:00
#     prob 0.65 and ending at 2026-10-25T06:53:54.025606+00:00 prob 0.605;
#     no capture at 18:52:13.233004+00:00), with `venue_history.state == "cold"`.
#   * CONSTRUCTED (labeled `CONSTRUCTED_*` below):
#     the Kalshi event/outcome tickers (`KXITFMATCH-26OCT25HENNAG` / `-NAG` / `-HEN`),
#     `market_metadata` (`market_count=2`), and the 1-minute Kalshi candlestick
#     series passed through `build_generic_history`, `_compact_entries`, and
#     `get_futures_history`. The original production cause of the missing bank on
#     67318590 remains unproved; these tests prove the producer-to-reader
#     compaction and single-leg capture-overlap refusal path on pinned source.

R3_MARKET_ID = 67318590
R3_NAGEL_ID = 252747654
R3_HENNING_ID = 252747653
CONSTRUCTED_EVENT_TICKER = "KXITFMATCH-26OCT25HENNAG"
CONSTRUCTED_NAGEL_TICKER = "KXITFMATCH-26OCT25HENNAG-NAG"
CONSTRUCTED_HENNING_TICKER = "KXITFMATCH-26OCT25HENNAG-HEN"

#: Exact retained public `/history` points from `R3-public-history-67318590.json`.
RETAINED_R3_NAGEL_POINTS = [
    ("2026-10-24T18:52:13.233004+00:00", 0.11),
    ("2026-10-24T21:01:57.708338+00:00", 0.305),
    ("2026-10-24T22:50:40.288387+00:00", 0.345),
    ("2026-10-25T00:52:56.502124+00:00", 0.355),
    ("2026-10-25T02:58:11.226290+00:00", 0.375),
    ("2026-10-25T04:51:45.344661+00:00", 0.385),
    ("2026-10-25T06:53:54.025606+00:00", 0.39),
]
RETAINED_R3_HENNING_POINTS = [
    ("2026-10-24T21:01:57.708338+00:00", 0.65),
    ("2026-10-24T22:50:40.288387+00:00", 0.63),
    ("2026-10-25T00:52:56.502124+00:00", 0.63),
    ("2026-10-25T02:58:11.226290+00:00", 0.615),
    ("2026-10-25T04:51:45.344661+00:00", 0.61),
    ("2026-10-25T06:53:54.025606+00:00", 0.605),
]

#: Wall-clock anchor for `get_futures_history` (which windows from `datetime.now`).
R3_NOW = datetime.now(timezone.utc).replace(microsecond=0)
R3_CAPTURED_END = datetime.fromisoformat("2026-10-25T06:53:54.025606+00:00")
R3_SHIFT = (R3_NOW - timedelta(hours=30)) - R3_CAPTURED_END.replace(microsecond=0)


class _FakeKalshiCandleService:
    """Offline Kalshi candlestick double returning constructed 1-minute candles."""

    def __init__(self, candles_by_ticker: dict[str, list[dict]]) -> None:
        self._candles = candles_by_ticker

    async def get_markets_candlesticks_raw(
        self,
        *,
        tickers: list[str],
        period_interval: int,
        start_ts: int,
        end_ts: int,
    ) -> dict[str, list[dict]]:
        if period_interval != 1:
            return {t: [] for t in tickers}
        out: dict[str, list[dict]] = {}
        for ticker in tickers:
            out[ticker] = [
                c
                for c in self._candles.get(ticker, ())
                if start_ts <= int(c["end_period_ts"]) <= end_ts
            ]
        return out

    async def close(self) -> None:
        return None


def _constructed_candle(ts: datetime, prob: float) -> dict:
    bid = round(max(0.01, prob - 0.01), 4)
    ask = round(min(0.99, prob + 0.01), 4)
    return {
        "end_period_ts": int(ts.timestamp()),
        "yes_bid": {"close_dollars": f"{bid:.4f}"},
        "yes_ask": {"close_dollars": f"{ask:.4f}"},
        "price": {"close_dollars": f"{prob:.4f}"},
    }


def _constructed_kalshi_match_market(
    *,
    mutually_exclusive: bool | None = True,
    market_count: object = 2,
    event_ticker: str = CONSTRUCTED_EVENT_TICKER,
    nagel_ticker: str = CONSTRUCTED_NAGEL_TICKER,
    henning_ticker: str = CONSTRUCTED_HENNING_TICKER,
    nagel_name: str = "Arthur Nagel",
    henning_name: str = "Philip Henning",
    source: str = "kalshi",
    extra_outcomes: tuple = (),
    meta_overrides: dict | None = None,
) -> SimpleNamespace:
    nagel = SimpleNamespace(
        id=R3_NAGEL_ID,
        market_id=R3_MARKET_ID,
        name=nagel_name,
        external_id=nagel_ticker,
        current_probability=0.39,
        current_american_odds=None,
        opening_probability=0.11,
        opening_american_odds=None,
        probability_change_24h=0.28,
        price_changed_at=R3_NOW - timedelta(hours=30),
        current_yes_bid=0.38,
        current_yes_ask=0.40,
        current_last_price=0.39,
        volume_24h=1200.0,
        volume_24h_at=R3_NOW - timedelta(minutes=10),
        open_interest=2500.0,
        open_interest_at=R3_NOW - timedelta(minutes=10),
        last_updated=R3_NOW - timedelta(minutes=5),
        rank=2,
        team_id=None,
        team=None,
        is_winner=None,
        resolution_source=None,
    )
    henning = SimpleNamespace(
        id=R3_HENNING_ID,
        market_id=R3_MARKET_ID,
        name=henning_name,
        external_id=henning_ticker,
        current_probability=0.605,
        current_american_odds=None,
        opening_probability=0.65,
        opening_american_odds=None,
        probability_change_24h=-0.045,
        price_changed_at=R3_NOW - timedelta(hours=30),
        current_yes_bid=0.59,
        current_yes_ask=0.62,
        current_last_price=0.605,
        volume_24h=1200.0,
        volume_24h_at=R3_NOW - timedelta(minutes=10),
        open_interest=2500.0,
        open_interest_at=R3_NOW - timedelta(minutes=10),
        last_updated=R3_NOW - timedelta(minutes=5),
        rank=1,
        team_id=None,
        team=None,
        is_winner=None,
        resolution_source=None,
    )
    metadata: dict[str, object] = {
        "kalshi_event_ticker": event_ticker,
        "event_title": "Henning vs Nagel",
        "market_count": market_count,
    }
    if meta_overrides:
        metadata.update(meta_overrides)
    outcomes = [nagel, henning, *extra_outcomes]
    market = SimpleNamespace(
        id=R3_MARKET_ID,
        name="Henning vs Nagel",
        source=source,
        external_id=event_ticker,
        group_id=None,
        status="open",
        market_type="head_to_head",
        mutually_exclusive=mutually_exclusive,
        llm_sport_category="tennis",
        sport_id=None,
        sport=None,
        created_at=R3_NOW - timedelta(days=3),
        updated_at=R3_NOW - timedelta(minutes=5),
        settled_at=None,
        closes_at=R3_NOW + timedelta(days=1),
        market_metadata=metadata,
        outcomes=outcomes,
    )
    for o in outcomes:
        o.market = market
    return market


def _constructed_asymmetric_kalshi_minute_series(
    base: datetime, *, minutes: int = 150
) -> tuple[list[tuple[datetime, float]], list[tuple[datetime, float]]]:
    """Constructed 1-minute Kalshi series in the 1W band (90-point budget per leg).

    Nagel moves on even minutes 0..60 (0.11 -> 0.39) and stays flat thereafter;
    Henning moves on odd minutes 1..61 (0.89 -> 0.61) and ticks by 0.001 at
    minute 110. Every minute sums within 0.01 of 1.00, yet independent
    per-leg `compact_by_band` keeps different instants on each leg.
    """
    nagel_pts: list[tuple[datetime, float]] = []
    henning_pts: list[tuple[datetime, float]] = []
    for m in range(minutes):
        ts = base + timedelta(minutes=m)
        step_n = min(m // 2, 30)
        step_h = min((m + 1) // 2, 30)
        p_nagel = round(0.11 + step_n * (0.28 / 30.0), 4)
        p_henning = round(0.89 - step_h * (0.28 / 30.0), 4)
        if m == 110:
            p_henning = round(p_henning - 0.001, 4)
        nagel_pts.append((ts, p_nagel))
        henning_pts.append((ts, p_henning))
    return nagel_pts, henning_pts


def test_compact_entries_retains_shared_kalshi_instants_with_real_venue_points():
    """Direct `_compact_entries(outcomes, entries, now)` reproducer with real `VenuePoint`s."""
    from app.utils import futures_chart_series as series

    market = _constructed_kalshi_match_market()
    nagel_o, henning_o = market.outcomes
    base = (R3_NOW - timedelta(hours=36)).replace(second=0)
    raw_nagel, raw_henning = _constructed_asymmetric_kalshi_minute_series(base)

    # Sanity check: independent band compaction drops different instants on each leg.
    alone_nagel = {ts for ts, _ in series.compact_by_band(raw_nagel, R3_NOW)}
    alone_henning = {ts for ts, _ in series.compact_by_band(raw_henning, R3_NOW)}
    assert alone_nagel != alone_henning

    entries = {
        R3_NAGEL_ID: {
            "contract": gmh.kalshi_contract(nagel_o),
            "points": [
                gmh.VenuePoint(ts, p, round(p - 0.01, 4), round(p + 0.01, 4), p, "kalshi_candle_1m")
                for ts, p in raw_nagel
            ],
        },
        R3_HENNING_ID: {
            "contract": gmh.kalshi_contract(henning_o),
            "points": [
                gmh.VenuePoint(ts, p, round(p - 0.01, 4), round(p + 0.01, 4), p, "kalshi_candle_1m")
                for ts, p in raw_henning
            ],
        },
    }
    fill._compact_entries([nagel_o, henning_o], entries, R3_NOW)

    kept_nagel = [pt.observed_at for pt in entries[R3_NAGEL_ID]["points"]]
    kept_henning = [pt.observed_at for pt in entries[R3_HENNING_ID]["points"]]
    assert kept_nagel == kept_henning
    assert set(kept_nagel) == alone_nagel | alone_henning
    for oid, raw in ((R3_NAGEL_ID, dict(raw_nagel)), (R3_HENNING_ID, dict(raw_henning))):
        for pt in entries[oid]["points"]:
            assert isinstance(pt, gmh.VenuePoint)
            assert pt.observed_at in raw
            assert pt.probability == raw[pt.observed_at]
            assert pt.pair_at == pt.observed_at and pt.peer_at == pt.observed_at


def test_retained_r3_henning_nagel_captures_with_constructed_kalshi_candles_survive_compaction_and_single_leg_claim():
    """End-to-end fill + `/history` reproducer combining retained R3 captures with constructed Kalshi candles.

    Proves two things on actual `build_generic_history` and `get_futures_history`:
      1. Compaction retains both halves of every paired Kalshi candle in the 1W band
         so `/history` serves the genuine move warm instead of refusing the whole bank
         with `exclusive_field_incomplete_at_venue_instant`.
      2. At `2026-10-24T18:52:13.233004+00:00` (retained R3 single-leg capture on Nagel
         with no Henning capture), the overlapping 18:52:00Z candle is claimed on Nagel
         only; Henning's widowed 18:52:00Z venue candle is withheld (`unpaired_points_withheld == 1`)
         without fabricating an 18:52 peer point on Henning, and all later paired candles survive.
    """
    import asyncio
    import json
    from unittest.mock import patch

    from app.routes import futures as futures_route
    from tests.test_generic_history_paired_compaction_11157 import _Redis, _Result, _Session

    market = _constructed_kalshi_match_market()

    # Exact 13 retained R3 snapshot points (7 Nagel, 6 Henning), shifted into the wall-clock window.
    snapshots = [
        SimpleNamespace(
            outcome_id=oid,
            captured_at=datetime.fromisoformat(ts_iso) + R3_SHIFT,
            probability=prob,
            american_odds=None,
            bookmaker="kalshi",
            yes_bid=round(max(0.01, prob - 0.01), 4),
            yes_ask=round(min(0.99, prob + 0.01), 4),
            last_price=prob,
        )
        for oid, rows in (
            (R3_NAGEL_ID, RETAINED_R3_NAGEL_POINTS),
            (R3_HENNING_ID, RETAINED_R3_HENNING_POINTS),
        )
        for ts_iso, prob in rows
    ]
    assert len(snapshots) == 13

    # Constructed 1-minute candles:
    # (a) one candle at 18:52:00Z + R3_SHIFT (13.23s before Nagel's lone capture at 18:52:13.233004Z + R3_SHIFT),
    # (b) 150 synchronous 1-minute candles starting at 19:00:00Z + R3_SHIFT across the 0.11 -> 0.39 move.
    single_leg_claim_minute = (
        datetime.fromisoformat("2026-10-24T18:52:00+00:00") + R3_SHIFT
    )
    series_base = datetime.fromisoformat("2026-10-24T19:00:00+00:00") + R3_SHIFT
    raw_nagel, raw_henning = _constructed_asymmetric_kalshi_minute_series(series_base, minutes=150)
    raw_nagel = [(single_leg_claim_minute, 0.11), *raw_nagel]
    raw_henning = [(single_leg_claim_minute, 0.89), *raw_henning]

    venue = _FakeKalshiCandleService(
        {
            CONSTRUCTED_NAGEL_TICKER: [_constructed_candle(ts, p) for ts, p in raw_nagel],
            CONSTRUCTED_HENNING_TICKER: [_constructed_candle(ts, p) for ts, p in raw_henning],
        }
    )
    payload = asyncio.run(
        fill.build_generic_history(None, market, kalshi_service=venue, now=R3_NOW)
    )
    nagel_bank_ts = [r[0] for r in payload["outcomes"][str(R3_NAGEL_ID)]["points"]]
    henning_bank_ts = [r[0] for r in payload["outcomes"][str(R3_HENNING_ID)]["points"]]

    rc = _Redis({gmh.cache_key(market.id): json.dumps(payload)})
    db = _Session(_Result(value=market), _Result(rows=snapshots), _Result(rows=snapshots))
    with (
        patch.object(futures_route, "_request_path_redis", return_value=rc),
        patch.object(futures_route, "_refuted_midpoint_outcome_ids", return_value=set()),
    ):
        res = asyncio.run(
            futures_route.get_futures_history(
                market.id,
                outcome_id=None,
                hours=168,
                top_n=10,
                champion=None,
                db=db,
                history_range=None,
            )
        )

    vh = res["venue_history"]
    assert vh["state"] == "warm", {
        "venue_history": vh,
        "nagel_bank_points": len(nagel_bank_ts),
        "henning_bank_points": len(henning_bank_ts),
        "unshared_bank_instants": len(set(nagel_bank_ts) ^ set(henning_bank_ts)),
    }
    assert nagel_bank_ts == henning_bank_ts
    assert "exclusive_field_incomplete_at_venue_instant" not in json.dumps(vh.get("refusals") or [])
    # (1) Nagel's lone 18:52:13.233004 capture claims Nagel's 18:52:00 candle; Henning's
    #     widowed 18:52:00 candle is withheld as 1 unpaired point.
    # (2) Both legs' 21:01:57.708338 captures claim both legs' 21:02:00 candles (2.29s away).
    # All remaining 149 banked candle pairs (298 points) survive and are served warm.
    paired_claim_minute = (
        datetime.fromisoformat("2026-10-24T21:02:00+00:00") + R3_SHIFT
    )
    assert vh["unpaired_points_withheld"] == 1
    assert vh["points_served"] == 2 * (len(nagel_bank_ts) - 2) == 298

    by_name = {o["name"]: o["history"] for o in res["outcomes"]}
    nagel_venue_ts = [
        pt["timestamp"] for pt in by_name["Arthur Nagel"] if pt.get("provenance") == "venue_history"
    ]
    henning_venue_ts = [
        pt["timestamp"] for pt in by_name["Philip Henning"] if pt.get("provenance") == "venue_history"
    ]
    expected_venue_ts = [
        ts
        for ts in nagel_bank_ts
        if ts not in {single_leg_claim_minute.isoformat(), paired_claim_minute.isoformat()}
    ]
    assert nagel_venue_ts == henning_venue_ts == expected_venue_ts
    assert single_leg_claim_minute.isoformat() not in nagel_venue_ts
    assert single_leg_claim_minute.isoformat() not in henning_venue_ts
    # And no synthetic complement was fabricated on Henning at Nagel's 18:52:13.233004 capture timestamp.
    henning_all_ts = {pt["timestamp"] for pt in by_name["Philip Henning"]}
    nagel_lone_capture_iso = (
        datetime.fromisoformat("2026-10-24T18:52:13.233004+00:00") + R3_SHIFT
    ).isoformat()
    assert nagel_lone_capture_iso not in henning_all_ts


def test_kalshi_semantic_identity_requires_full_field_exclusivity_and_preserves_all_refusals():
    """Positive and negative semantic-admission controls for `paired_binary_leg_ids` and `_verify_pair_bank`."""
    from app.routes import futures as futures_route
    from app.utils.async_binary_pair import paired_binary_leg_ids

    ts = (R3_NOW - timedelta(hours=2)).replace(second=0)

    def make_entries(market_obj, *, c_a_over=None, c_b_over=None, extra_entries=None):
        o_a, o_b = market_obj.outcomes[0], market_obj.outcomes[1]
        c_a = gmh.kalshi_contract(o_a) or {}
        c_b = gmh.kalshi_contract(o_b) or {}
        if c_a_over:
            c_a = {**c_a, **c_a_over}
        if c_b_over:
            c_b = {**c_b, **c_b_over}
        out = {
            int(o_a.id): {
                "contract": c_a,
                "points": [gmh.VenuePoint(ts, 0.39, 0.38, 0.40, 0.39, "kalshi_candle_1m")],
            },
            int(o_b.id): {
                "contract": c_b,
                "points": [gmh.VenuePoint(ts, 0.61, 0.60, 0.62, 0.61, "kalshi_candle_1m")],
            },
        }
        if extra_entries:
            out.update(extra_entries)
        return out

    # 1. Valid 2-leg mutually-exclusive Kalshi match is admitted.
    valid_market = _constructed_kalshi_match_market()
    valid_entries = make_entries(valid_market)
    assert paired_binary_leg_ids(valid_market.outcomes, valid_entries) == (
        R3_NAGEL_ID,
        R3_HENNING_ID,
    )

    # 2. Existing Polymarket predicate is preserved byte-for-byte (positive + refusals).
    cond = "0x" + "ab" * 32
    pm_outcomes = [SimpleNamespace(id=11), SimpleNamespace(id=12)]
    pm_entries = {
        11: {
            "contract": {
                "venue": "polymarket",
                "condition_id": cond,
                "token_id": "tok_yes",
                "outcome_external_id": f"{cond}_yes",
            }
        },
        12: {
            "contract": {
                "venue": "polymarket",
                "condition_id": cond,
                "token_id": "tok_no",
                "outcome_external_id": f"{cond}_no",
            }
        },
    }
    assert paired_binary_leg_ids(pm_outcomes, pm_entries) == (11, 12)
    assert (
        paired_binary_leg_ids(
            pm_outcomes,
            {
                11: pm_entries[11],
                12: {
                    "contract": {
                        **pm_entries[12]["contract"],
                        "outcome_external_id": f"{cond}_yes",
                    }
                },
            },
        )
        is None
    )

    # 3. `wrong-event` refusals:
    #    - leg ticker has a different event prefix
    #    - `market.external_id` disagrees with leg event prefix
    #    - `market_metadata["kalshi_event_ticker"]` disagrees with `market.external_id`
    wrong_leg_event = _constructed_kalshi_match_market(
        henning_ticker="KXITFMATCH-26OCT25OTHER-HEN"
    )
    assert paired_binary_leg_ids(wrong_leg_event.outcomes, make_entries(wrong_leg_event)) is None

    wrong_market_ext = _constructed_kalshi_match_market(event_ticker="KXITFMATCH-26OCT25OTHER")
    assert paired_binary_leg_ids(wrong_market_ext.outcomes, make_entries(wrong_market_ext)) is None

    wrong_meta_ticker = _constructed_kalshi_match_market(
        meta_overrides={"kalshi_event_ticker": "KXITFMATCH-26OCT25OTHER"}
    )
    assert (
        paired_binary_leg_ids(wrong_meta_ticker.outcomes, make_entries(wrong_meta_ticker)) is None
    )

    # 4. `subset` refusals (even though probabilities 0.39 + 0.61 sum to 1.00):
    #    - `market` is missing (unattached outcomes)
    unattached = [
        SimpleNamespace(id=R3_NAGEL_ID, name="Arthur Nagel", external_id=CONSTRUCTED_NAGEL_TICKER),
        SimpleNamespace(
            id=R3_HENNING_ID, name="Philip Henning", external_id=CONSTRUCTED_HENNING_TICKER
        ),
    ]
    assert paired_binary_leg_ids(unattached, valid_entries) is None

    #    - `market_count` is 3 (e.g., 3-way event with 1 withdrawn/unlisted leg), 1, None, or bool/str
    for bad_count in (3, 1, None, "2", True):
        m_bad_count = _constructed_kalshi_match_market(market_count=bad_count)
        assert (
            paired_binary_leg_ids(m_bad_count.outcomes, make_entries(m_bad_count)) is None
        ), f"market_count={bad_count!r} must be refused"

    #    - 2-outcome subset of a 3-outcome `FuturesMarket`
    third_leg = SimpleNamespace(
        id=252747655,
        market_id=R3_MARKET_ID,
        name="Third Player",
        external_id="KXITFMATCH-26OCT25HENNAG-THD",
    )
    three_way = _constructed_kalshi_match_market(extra_outcomes=(third_leg,))
    assert (
        paired_binary_leg_ids(three_way.outcomes[:2], make_entries(three_way)) is None
    )

    #    - `entries` contains a third leg
    assert (
        paired_binary_leg_ids(
            valid_market.outcomes,
            make_entries(valid_market, extra_entries={252747655: valid_entries[R3_NAGEL_ID]}),
        )
        is None
    )

    #    - `_verify_pair_bank` refuses when cached `payload["outcomes"]` holds 3 legs
    paired_pt_a = gmh.VenuePoint(
        ts, 0.39, 0.38, 0.40, 0.39, "kalshi_candle_1m", pair_at=ts, peer_at=ts
    )
    paired_pt_b = gmh.VenuePoint(
        ts, 0.61, 0.60, 0.62, 0.61, "kalshi_candle_1m", pair_at=ts, peer_at=ts
    )
    three_leg_payload = gmh.build_payload(
        valid_market,
        {
            R3_NAGEL_ID: {"contract": valid_entries[R3_NAGEL_ID]["contract"], "points": [paired_pt_a]},
            R3_HENNING_ID: {
                "contract": valid_entries[R3_HENNING_ID]["contract"],
                "points": [paired_pt_b],
            },
            252747655: {"contract": gmh.kalshi_contract(third_leg), "points": [paired_pt_a]},
        },
        now=R3_NOW,
        stats={},
        degraded=False,
    )
    assert (
        futures_route._verify_pair_bank(
            {R3_NAGEL_ID: [paired_pt_a], R3_HENNING_ID: [paired_pt_b]},
            three_leg_payload,
            valid_market.outcomes,
        )
        == (None, None)
    )

    #    - catch-all `Field` / `Other` outcome or `Draw` / `Tie` slice
    for bad_name in ("Field", "Other", "All Others", "Draw", "Tie"):
        m_slice = _constructed_kalshi_match_market(henning_name=bad_name)
        assert (
            paired_binary_leg_ids(m_slice.outcomes, make_entries(m_slice)) is None
        ), f"outcome={bad_name!r} must be refused"

    # 5. `independent-market` refusals:
    #    - `mutually_exclusive` is False or None
    for me_val in (False, None):
        m_non_excl = _constructed_kalshi_match_market(mutually_exclusive=me_val)
        assert (
            paired_binary_leg_ids(m_non_excl.outcomes, make_entries(m_non_excl)) is None
        ), f"mutually_exclusive={me_val!r} must be refused"

    #    - cumulative threshold ladder (gotcha #17)
    m_ladder = _constructed_kalshi_match_market(nagel_name="Above 250", henning_name="Above 300")
    assert paired_binary_leg_ids(m_ladder.outcomes, make_entries(m_ladder)) is None

    #    - numeric range bins
    m_bins = _constructed_kalshi_match_market(
        nagel_name="200 to 249", henning_name="250 to 299"
    )
    assert paired_binary_leg_ids(m_bins.outcomes, make_entries(m_bins)) is None

    #    - quantity ticker (`_QUANTITY_TICKER_PREFIXES`)
    m_qty = _constructed_kalshi_match_market(
        event_ticker="KXBOXOFFICE-26OCT",
        nagel_ticker="KXBOXOFFICE-26OCT-A",
        henning_ticker="KXBOXOFFICE-26OCT-B",
    )
    assert paired_binary_leg_ids(m_qty.outcomes, make_entries(m_qty)) is None

    #    - multi-winner / participation kind or persisted non-exhaustive shape
    for bad_meta in (
        {"source_market_kind": "top_finish"},
        {"shape": {"exhaustive": False, "expected_winners": 1, "outcome_relation": "competitors"}},
        {"shape": {"exhaustive": True, "expected_winners": 2, "outcome_relation": "competitors"}},
        {"shape": {"exhaustive": True, "expected_winners": 1, "outcome_relation": "independent"}},
    ):
        m_ind = _constructed_kalshi_match_market(meta_overrides=bad_meta)
        assert paired_binary_leg_ids(m_ind.outcomes, make_entries(m_ind)) is None, bad_meta

    # 6. `mismatched-ID` refusals:
    assert (
        paired_binary_leg_ids(
            valid_market.outcomes,
            make_entries(valid_market, c_b_over={"outcome_external_id": CONSTRUCTED_NAGEL_TICKER}),
        )
        is None
    )
    assert (
        paired_binary_leg_ids(
            valid_market.outcomes,
            make_entries(valid_market, c_b_over={"ticker": "KXITFMATCH-26OCT25HENNAG-OTHER"}),
        )
        is None
    )

    # 7. `duplicate-ID` refusals:
    assert (
        paired_binary_leg_ids(
            [valid_market.outcomes[0], valid_market.outcomes[0]], valid_entries
        )
        is None
    )
    dup_ticker = _constructed_kalshi_match_market(henning_ticker=CONSTRUCTED_NAGEL_TICKER)
    assert paired_binary_leg_ids(dup_ticker.outcomes, make_entries(dup_ticker)) is None

    # 8. `mixed-venue` refusals:
    assert (
        paired_binary_leg_ids(
            valid_market.outcomes, make_entries(valid_market, c_b_over={"venue": "polymarket"})
        )
        is None
    )
    wrong_source = _constructed_kalshi_match_market(source="polymarket")
    assert paired_binary_leg_ids(wrong_source.outcomes, make_entries(wrong_source)) is None


# ── #10955 R1 (lane1b's review of rev2 e61fef59): a Kalshi pair is two books ─────
#
# The 1% coherence guard in `_venue_pair_admission` was set for the Yes/No tokens
# of ONE Polymarket condition. A Kalshi pair is two tickers, each priced from its
# own book, paired only at an exact shared candle instant, so its legs routinely
# sum to 0.98 or 1.03. Base served those complete instants through the field rule
# (the squeeze is a no-op up to 1.05); rev2 withheld every one as "incoherent"
# and left the state "warm" over an empty chart. These pin base's behaviour back.


def _serve_kalshi_bank(raw_nagel, raw_henning, snapshots=()):
    """Fill a constructed Kalshi bank and read it back through `/history`."""
    import asyncio
    import json
    from unittest.mock import patch

    from app.routes import futures as futures_route
    from tests.test_generic_history_paired_compaction_11157 import _Redis, _Result, _Session

    market = _constructed_kalshi_match_market()
    venue = _FakeKalshiCandleService(
        {
            CONSTRUCTED_NAGEL_TICKER: [_constructed_candle(ts, p) for ts, p in raw_nagel],
            CONSTRUCTED_HENNING_TICKER: [_constructed_candle(ts, p) for ts, p in raw_henning],
        }
    )
    payload = asyncio.run(fill.build_generic_history(None, market, kalshi_service=venue, now=R3_NOW))
    rows = list(snapshots)
    rc = _Redis({gmh.cache_key(market.id): json.dumps(payload)})
    db = _Session(_Result(value=market), _Result(rows=rows), _Result(rows=rows))
    with (
        patch.object(futures_route, "_request_path_redis", return_value=rc),
        patch.object(futures_route, "_refuted_midpoint_outcome_ids", return_value=set()),
    ):
        res = asyncio.run(
            futures_route.get_futures_history(
                market.id, outcome_id=None, hours=168, top_n=10, champion=None,
                db=db, history_range=None,
            )
        )
    return payload, res


def _served_venue_points(res, name):
    return {
        datetime.fromisoformat(pt["timestamp"]): pt["probability"]
        for o in res["outcomes"] if o["name"] == name
        for pt in o["history"] if pt.get("provenance") == "venue_history"
    }


def _assert_every_raw_point_served(res, raw_nagel, raw_henning):
    """Each leg's served venue points are exactly its raw candles: own clock, own value."""
    for name, raw in (("Arthur Nagel", raw_nagel), ("Philip Henning", raw_henning)):
        served = _served_venue_points(res, name)
        assert sorted(served) == sorted(ts for ts, _ in raw), name
        for ts, p in raw:
            assert served[ts] == pytest.approx(p, abs=1e-9), (name, ts)


def _complete_synchronous_bank(book_sum):
    base = datetime.fromisoformat("2026-10-24T19:00:00+00:00") + R3_SHIFT
    nagel = [(base + timedelta(minutes=m), round(0.30 + 0.005 * m, 4)) for m in range(30)]
    henning = [(ts, round(book_sum - p, 4)) for ts, p in nagel]
    return nagel, henning


@pytest.mark.parametrize("book_sum", [1.00, 0.98, 1.02, 1.03])
def test_R1_a_complete_synchronous_kalshi_bank_off_one_dollar_is_served_whole(book_sum):
    """lane1b control A: 30 shared minutes, two books summing to `book_sum`, no
    asymmetry, no capture. Base served all 60; rev2 served 0 (incoherent 60)."""
    nagel, henning = _complete_synchronous_bank(book_sum)
    _, res = _serve_kalshi_bank(nagel, henning)
    vh = res["venue_history"]
    assert vh["state"] == "warm", vh
    assert vh["points_served"] == 60, vh
    assert vh.get("incoherent_pair_points_withheld", 0) == 0, vh
    assert vh.get("unpaired_points_withheld", 0) == 0, vh
    assert not vh.get("refusals"), vh
    _assert_every_raw_point_served(res, nagel, henning)


def test_R1_a_kalshi_bank_the_squeeze_would_move_is_still_refused_whole():
    """The printed-scale contract is unchanged: at 1.06 the squeeze would print a
    number the venue never quoted, so the WHOLE series is refused, as on base."""
    nagel, henning = _complete_synchronous_bank(1.06)
    _, res = _serve_kalshi_bank(nagel, henning)
    vh = res["venue_history"]
    assert vh["points_served"] == 0, vh
    assert vh.get("incoherent_pair_points_withheld", 0) == 0, vh
    assert "printed_scale_is_not_the_venue_raw_scale" in json.dumps(vh.get("refusals") or []), vh
    assert not _served_venue_points(res, "Arthur Nagel")
    assert not _served_venue_points(res, "Philip Henning")


def test_R1_the_retained_r3_pairs_off_one_dollar_survive_at_their_own_clocks_and_values():
    """Fable's F1 specimen: the retained R3 pairs (Nagel 0.305 / Henning 0.65 = 0.955,
    then 0.975 and 0.985) banked as Kalshi candles at their own instants. Every
    paired point is served with its raw value; Nagel's lone 18:52 point has no
    peer and is withheld, and nothing is invented on Henning there."""
    def at_second(iso):
        return datetime.fromisoformat(iso).replace(microsecond=0) + R3_SHIFT

    raw_nagel = [(at_second(ts), p) for ts, p in RETAINED_R3_NAGEL_POINTS]
    raw_henning = [(at_second(ts), p) for ts, p in RETAINED_R3_HENNING_POINTS]
    shared = dict(raw_henning)
    sums = sorted(round(p + shared[ts], 4) for ts, p in raw_nagel if ts in shared)
    assert sums[:3] == [0.955, 0.975, 0.985]  # the three rev2 called "incoherent"

    _, res = _serve_kalshi_bank(raw_nagel, raw_henning)
    vh = res["venue_history"]
    assert vh.get("incoherent_pair_points_withheld", 0) == 0, vh
    assert vh["unpaired_points_withheld"] == 1, vh
    assert vh["points_served"] == 12, vh
    lone = raw_nagel[0]
    _assert_every_raw_point_served(res, raw_nagel[1:], raw_henning)
    assert lone[0] not in _served_venue_points(res, "Philip Henning")


@pytest.mark.parametrize("henning_offset", [-0.025, 0.02])
def test_R1_the_asymmetric_overlap_fixture_off_one_dollar_serves_its_genuine_points(henning_offset):
    """The rev2 repair itself, on books that do not sum to 1.00: the asymmetric
    1-minute fixture with Henning's book shifted (sums 0.975-0.984 / 1.02-1.029).
    Union retention keeps both halves of every kept instant, and every retained
    raw point is SERVED at its own clock and value — not merely a warm state."""
    base = (R3_NOW - timedelta(hours=36)).replace(second=0)
    raw_nagel, raw_henning = _constructed_asymmetric_kalshi_minute_series(base)
    raw_henning = [(ts, round(p + henning_offset, 4)) for ts, p in raw_henning]

    payload, res = _serve_kalshi_bank(raw_nagel, raw_henning)
    nagel_bank = [r[0] for r in payload["outcomes"][str(R3_NAGEL_ID)]["points"]]
    henning_bank = [r[0] for r in payload["outcomes"][str(R3_HENNING_ID)]["points"]]
    assert nagel_bank == henning_bank and len(nagel_bank) > 60

    vh = res["venue_history"]
    assert vh["state"] == "warm", vh
    assert vh.get("incoherent_pair_points_withheld", 0) == 0, vh
    assert vh["points_served"] == 2 * len(nagel_bank), vh
    kept = {datetime.fromisoformat(ts) for ts in nagel_bank}
    _assert_every_raw_point_served(
        res,
        [(ts, p) for ts, p in raw_nagel if ts in kept],
        [(ts, p) for ts, p in raw_henning if ts in kept],
    )
