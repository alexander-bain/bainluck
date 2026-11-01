"""#10090 headline clock: a waiting input whose game a read now sees finished.

Alex 2026-10-31: "If there's no valid price to show, I won't count that as a
miss. It's a miss if we have unnecessary delays." A venue tick received after
the game's recorded end has no live headline to move (the page shows the
result), so it leaves the clock and is counted as ``settled=``. A tick received
before the end was a real wait: it ends at the read that saw the end, at its
full age. Specimen: 07:06Z 11/01, a J-League Kalshi tick 28 s after full time
sat 91 s and was reported as ``late:mutate_read_required``.

The same rule for a receipt the live book cannot price: a bundled Challenger
home leg whose every socket has no primary price, no midpoint and no selected
input (a one-sided book at 0.99/0.01) has no valid price to show, so the input
leaves the clock (``nobook=``) and the next input starts its own. 07:05Z: a
0.01 tick on a one-sided Delaney-Wang book was charged 1.99 s.
"""

import time
from datetime import datetime, timezone
from types import SimpleNamespace

from app.tasks import live_blend_refresh as module
from app.tasks.live_blend_refresh import LiveBlendRefresher

MONO = 1000.0


def _refresher(monkeypatch):
    monkeypatch.setattr(module, "_mono", lambda: MONO)
    return LiveBlendRefresher("kalshi")


def _read(eid, *, status="completed", ended_ago=None):
    """What `_read_groups` hands on: the event row as the read saw it."""
    ended = (None if ended_ago is None
             else datetime.fromtimestamp(time.time() - ended_ago, timezone.utc))
    return {eid: (SimpleNamespace(id=eid, status=status, completed_at=ended), [])}


def test_an_input_received_after_full_time_leaves_the_clock(monkeypatch):
    r = _refresher(monkeypatch)
    r._hl_pending[1] = [MONO - 3.0, "mutate_read_required", None, 1]

    r._hl_settle_finished(_read(1, ended_ago=31.0))

    assert r._hl_pending == {}
    assert r._hl_summary() == "n=0 late=0 settled=1 nobook=0"


def test_an_input_received_before_full_time_is_a_wait_ended_at_the_read(monkeypatch):
    r = _refresher(monkeypatch)
    r._hl_pending[1] = [MONO - 40.0, "mutate_read_required", None, 1]

    r._hl_settle_finished(_read(1, ended_ago=10.0))

    assert r._hl_pending == {}
    line = r._hl_summary()
    assert "max_ms=40000 worst=1:40000:mutate_read_required>stamp_settled[f-,a1]" in line
    assert line.endswith("late=0 settled=0 nobook=0")


def test_a_finished_status_without_an_end_time_is_counted(monkeypatch):
    """No recorded end, nothing to compare: the wait counts at its age."""
    r = _refresher(monkeypatch)
    r._hl_pending[1] = [MONO - 2.0, "na_proof", None, 2]

    r._hl_settle_finished(_read(1, status="final"))

    assert "worst=1:2000:na_proof>stamp_settled[f-,a2]" in r._hl_summary()


def test_a_live_event_is_untouched(monkeypatch):
    r = _refresher(monkeypatch)
    entry = [MONO - 3.0, "receipt", None, 1]
    r._hl_pending[1] = entry

    r._hl_settle_finished(_read(1, status="live"))

    assert r._hl_pending == {1: entry}
    assert r._hl_summary() == "n=0 late=0 settled=0 nobook=0"


def test_the_read_path_settles_before_it_returns():
    """Wired into `_read_groups` (every read, not only preview-ticket reads)."""
    import inspect

    source = inspect.getsource(LiveBlendRefresher._read_groups)
    assert "settle(grouped)" in source
    assert source.index("settle(grouped)") < source.index("if preview_ticket is not None:")


# ── no valid price: the live book offers the home leg nothing ────────────────

TICKER = "KXATPCHALLENGERMATCH-26NOV01DELWAN"


def _challenger(source="kalshi", ticker=TICKER):
    from app.utils.live_blend import MarketOutcomes

    market = SimpleNamespace(id=5, source=source, external_id=ticker, event_id=1,
                             name="Delaney vs Wang", status="open", market_metadata={})
    rows = [SimpleNamespace(id=51, market_id=5, name="Delaney", external_id=ticker + "-DEL",
                            current_probability=0.99),
            SimpleNamespace(id=52, market_id=5, name="Wang", external_id=ticker + "-WAN",
                            current_probability=0.01)]
    return [MarketOutcomes(market, rows, None, False)]


EVENT = SimpleNamespace(id=1, home_team_name="Delaney", away_team_name="Wang")


def _books(**by_leg):
    """`current_book_signature`: per leg suffix, the socks' (pp, mid, input)."""
    def read(ticker):
        socks = by_leg.get(ticker.rsplit("-", 1)[-1], [(None, None, None)])
        return (False, tuple((i, *s) for i, s in enumerate(socks)), None, None, None, None)
    return read


def test_a_one_sided_home_book_is_no_price(monkeypatch):
    r = _refresher(monkeypatch)
    r.current_book_signature = _books(WAN=[(0.01, None, None)])
    assert r._home_book_empty(EVENT, _challenger())


def test_any_price_on_the_home_leg_is_a_price(monkeypatch):
    r = _refresher(monkeypatch)
    for book in ((0.99, None, None), (None, 0.985, None), (None, None, ("id", 0.99))):
        r.current_book_signature = _books(DEL=[(None, None, None), book])
        assert not r._home_book_empty(EVENT, _challenger()), book


def test_no_subscribed_socket_is_a_gap_not_a_missing_price(monkeypatch):
    r = _refresher(monkeypatch)
    r.current_book_signature = _books(DEL=[])
    assert not r._home_book_empty(EVENT, _challenger())


def test_only_the_bundled_challenger_market_is_read(monkeypatch):
    r = _refresher(monkeypatch)
    r.current_book_signature = _books()
    assert not r._home_book_empty(EVENT, _challenger(ticker="KXATPMATCH-26NOV01DELWAN"))


def test_an_unpriceable_receipt_leaves_the_clock(monkeypatch):
    r = _refresher(monkeypatch)
    r._hl_pending[1] = [MONO - 0.008, "receipt", None, 1]

    r._hl_no_price(1)

    assert r._hl_pending == {}
    assert r._hl_summary() == "n=0 late=0 settled=0 nobook=1"


def test_an_input_an_earlier_refusal_holds_is_a_wait(monkeypatch):
    """It waited while the book still priced it: counted, at its age."""
    r = _refresher(monkeypatch)
    r._hl_pending[1] = [MONO - 1.5, "na_proof", None, 2]

    r._hl_no_price(1)

    assert "worst=1:1500:na_proof>stamp_nobook[f-,a2]" in r._hl_summary()


def test_the_receipt_plan_routes_an_unpriceable_book_before_marking_na_proof():
    import inspect

    source = inspect.getsource(LiveBlendRefresher._receipt_preview_plan)
    nobook = source.index("self._home_book_empty(event, patched)")
    assert nobook < source.index('self._hl_mark(event_id, "na_proof" if proof_kwargs')


def test_an_unoriented_receipt_names_its_legs(monkeypatch, caplog):
    """07:49Z 11/01: a three-way moneyline waited 14.3 s as `na_orientation` with
    no line saying why; each such composition now names its legs (bounded)."""
    import logging

    r = _refresher(monkeypatch)
    patched = _challenger()
    with caplog.at_level(logging.INFO, logger="app.tasks.live_blend_refresh"):
        r._log_na_orientation(1, patched, {51}, None)
        r._log_na_orientation(1, "not a graph", set(), None)  # never raises
    lines = [rec.getMessage() for rec in caplog.records if "na_orientation event=" in rec.getMessage()]
    assert lines[0] == ("live_blend_refresh[kalshi]: na_orientation event=1 reading=none "
                        "m5[Delaney=0.99/rNone/ov,Wang=0.01/rNone]")


def test_both_refusal_kinds_share_the_attribution_bound():
    import inspect

    source = inspect.getsource(LiveBlendRefresher._receipt_preview_plan)
    assert "self._log_na_orientation(event_id, patched, overlaid, reading)" in source
    assert "if self._na_proof_logged < 6:" in source
