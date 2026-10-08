"""#10719 (+ #10256) — MLB postseason and WNBA playoff game pages get Kalshi's
spreads, totals and player questions back.

Read 2026-10-07: Kalshi listed ~200 questions on LAD@ATL and 95 on the WNBA
semifinal NY@ATL game 2; we held the winner only. Every MLB/WNBA spread, total
and player series stopped writing 09-28/09-29, and the NHL player series had
written nothing since 07-17.

The scan report names the mechanism: the main scan walks `status=None` (all of
Kalshi's history, expiry-DESC) on a resumable cursor, never wrapped in 24 of 24
beats, and once it passed the present it only sees settled history. Series it
alone reached went dark. KXMLBSPREAD/TOTAL were on the floor and went dark too,
because the floor skips a series the main scan already holds an event of, and
the main scan was paging through the regular season's settled spreads.

Three guards, one per link of that chain:

1. the open pass fetches every listed series as OPEN events with markets, and a
   settled history event in the main scan cannot stop it;
2. the floor's skip is keyed on the series, so the open pass holding tonight's
   KXMLBHIT cannot switch off the World Series rescue (`KXMLB` is a prefix of
   every MLB series);
3. the upsert loop writes tonight's events with the floor, ahead of the new
   history events that used up its deadline.
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

from app.services import kalshi_api as ka
from app.services.kalshi_api import KalshiAPIService
from app.tasks.kalshi import _floor_series_first

#: The series shopper read at the venue on 2026-10-07 (and #10256's NHL list).
#: The ship is these questions on these pages; dropping one is a regression.
_MEASURED = (
    "KXMLBSPREAD", "KXMLBTOTAL", "KXMLBHIT", "KXMLBHR", "KXMLBTB", "KXMLBKS",
    "KXMLBF5", "KXMLBRFI",
    "KXWNBASPREAD", "KXWNBATOTAL", "KXWNBAPTS", "KXWNBAREB", "KXWNBAAST",
    "KXWNBA3PT",
    "KXNHLPTS", "KXNHLGOAL", "KXNHLAST",
)


@pytest.fixture
def client():
    return KalshiAPIService()


async def _no_sleep(*_a, **_k):
    return None


def _raw_market(event_ticker: str, leg: str, status: str = "active") -> dict:
    return {
        "ticker": f"{event_ticker}-{leg}",
        "event_ticker": event_ticker,
        "title": "Over 8.5 runs?",
        "yes_sub_title": leg,
        "status": status,
        "yes_bid_dollars": "0.4900",
        "yes_ask_dollars": "0.5100",
        "last_price_dollars": "0.5000",
    }


def _raw_event(event_ticker: str, markets: bool = True, status: str = "active") -> dict:
    return {
        "event_ticker": event_ticker,
        "title": event_ticker,
        "category": "Sports",
        "markets": (
            [_raw_market(event_ticker, f"L{i}", status) for i in range(3)]
            if markets else []
        ),
    }


async def _run_fetch(client, monkeypatch, main_scan_events=(), open_events=None,
                     floor_events=None):
    """Drive the real fetch. Records every series call as (series, status, nested)."""
    calls: list[tuple[str, object, object]] = []
    open_events = open_events or {}
    floor_events = floor_events or {}
    consumed: list[int] = []

    async def fake_get_events(**kw):
        st = kw.get("series_ticker")
        if st is None:
            consumed.append(1)
            return (list(main_scan_events) if len(consumed) == 1 else [], None)
        calls.append((st, kw.get("status"), kw.get("with_nested_markets")))
        source = open_events if kw.get("status") == "open" else floor_events
        return (list(source.get(st, [])), None)

    async def fake_get_markets(**kw):
        return ([], None)

    monkeypatch.setattr(client, "get_events", fake_get_events)
    monkeypatch.setattr(client, "get_markets", fake_get_markets)
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    tel: dict = {}
    events = await client._fetch_all_events_unfiltered(
        deadline=time.monotonic() + 1000, telemetry=tel
    )
    return calls, events, tel


@pytest.mark.parametrize("series", _MEASURED)
def test_every_measured_series_is_in_the_open_pass(series):
    assert series in ka._OPEN_DERIVATIVE_SERIES_TICKERS, (
        f"{series} is not in the open pass. Discovery doesn't cover it and the "
        f"main scan no longer reaches today's events (#10719)."
    )


@pytest.mark.asyncio
class TestTheOpenPass:
    async def test_every_series_is_fetched_open_with_its_markets(self, client, monkeypatch):
        calls, _, tel = await _run_fetch(client, monkeypatch)
        open_calls = {st: nested for st, status, nested in calls if status == "open"}
        missing = [s for s in ka._OPEN_DERIVATIVE_SERIES_TICKERS if s not in open_calls]
        assert not missing, f"never fetched open: {missing}"
        stripped = [s for s, nested in open_calls.items() if nested is not True]
        assert not stripped, (
            f"fetched without markets: {stripped}. A stripped event waits on the "
            f"bounded backfill, which is truncated on most beats."
        )
        assert tel["open_derivative_series_fetched"] == len(
            ka._OPEN_DERIVATIVE_SERIES_TICKERS
        )
        assert tel["open_derivative_truncated_after"] is None

    async def test_a_settled_history_event_cannot_stand_in_for_tonight(
        self, client, monkeypatch
    ):
        """THE SPREAD/TOTAL DEFECT. Without the open pass, a regular-season
        KXMLBSPREAD event in the main scan made the floor skip the series, and
        the postseason's spreads were never asked for."""
        history = _raw_event("KXMLBSPREAD-26SEP201610SFLAD", status="finalized")
        tonight = _raw_event("KXMLBSPREAD-26OCT071800LADATL")
        _, events, _ = await _run_fetch(
            client, monkeypatch,
            main_scan_events=[history],
            open_events={"KXMLBSPREAD": [tonight]},
        )
        by_ticker = {e.event_ticker: e for e in events}
        # The skip reads the accumulator, so the history row must actually be in it.
        assert "KXMLBSPREAD-26SEP201610SFLAD" in by_ticker
        assert "KXMLBSPREAD-26OCT071800LADATL" in by_ticker, (
            "tonight's spread event was never fetched"
        )
        assert len(by_ticker["KXMLBSPREAD-26OCT071800LADATL"].markets) == 3

    async def test_a_player_series_off_the_floor_is_fetched(self, client, monkeypatch):
        """The player series were never on any list; only the main scan reached them."""
        tonight = _raw_event("KXWNBAPTS-26OCT07NYATL")
        _, events, tel = await _run_fetch(
            client, monkeypatch, open_events={"KXWNBAPTS": [tonight]}
        )
        assert any(e.event_ticker == "KXWNBAPTS-26OCT07NYATL" and e.markets for e in events)
        assert tel["open_derivative_events_added"] == 1

    async def test_the_pass_stops_at_its_reserve_and_the_floor_still_runs(
        self, client, monkeypatch
    ):
        """It is carved from the main scan, never from the floor's 60s."""
        monkeypatch.setattr(ka, "_OPEN_DERIVATIVE_RESERVE_S", 0.0)
        calls, _, tel = await _run_fetch(client, monkeypatch)
        assert not [c for c in calls if c[1] == "open"]
        assert tel["open_derivative_truncated_after"] == 0
        assert ("KXMLBGAME", None, False) in calls, "the floor did not run"

    async def test_one_failed_series_does_not_end_the_pass(self, client, monkeypatch):
        calls: list[str] = []

        async def fake_get_events(**kw):
            st = kw.get("series_ticker")
            if st is None:
                return ([], None)
            if kw.get("status") == "open":
                calls.append(st)
                if st == ka._OPEN_DERIVATIVE_SERIES_TICKERS[0]:
                    raise RuntimeError("429")
            return ([], None)

        monkeypatch.setattr(client, "get_events", fake_get_events)
        monkeypatch.setattr(asyncio, "sleep", _no_sleep)
        tel: dict = {}
        await client._fetch_all_events_unfiltered(
            deadline=time.monotonic() + 1000, telemetry=tel
        )
        assert calls == list(ka._OPEN_DERIVATIVE_SERIES_TICKERS)
        assert tel["open_derivative_series_fetched"] == len(calls) - 1


@pytest.mark.asyncio
class TestTheFloorSkipIsKeyedOnTheSeries:
    async def test_tonights_player_events_do_not_skip_the_world_series(
        self, client, monkeypatch
    ):
        """`KXMLB` is a prefix of `KXMLBHIT`. With a prefix test, the open pass
        would switch off the championship rescue on every MLB game day."""
        calls, events, _ = await _run_fetch(
            client, monkeypatch,
            open_events={"KXMLBHIT": [_raw_event("KXMLBHIT-26OCT071800LADATL")]},
        )
        assert any(e.event_ticker.startswith("KXMLBHIT-") for e in events)
        floor_series = [st for st, status, _ in calls if status is None]
        for champ in ("KXMLB", "KXNHL"):
            assert champ in floor_series, f"{champ} championship rescue was skipped"

    async def test_the_same_series_still_short_circuits(self, client, monkeypatch):
        """The skip itself still works: an exact-series hit skips the floor fetch."""
        calls, _, _ = await _run_fetch(
            client, monkeypatch,
            open_events={"KXMLBSPREAD": [_raw_event("KXMLBSPREAD-26OCT071800LADATL")]},
        )
        assert "KXMLBSPREAD" not in [st for st, status, _ in calls if status is None]


def _ev(ticker: str, statuses=("active",)):
    return SimpleNamespace(
        event_ticker=ticker,
        markets=[SimpleNamespace(status=s) for s in statuses],
    )


class TestTheUpsertWritesTonightFirst:
    def test_an_open_derivative_event_is_written_with_the_floor(self):
        history_new = _ev("KXMIDTERMCOUNTY-26NOV03X")
        tonight = _ev("KXWNBAPTS-26OCT07NYATL")
        winner = _ev("KXWNBAGAME-26OCT07NYATL")
        ordered = _floor_series_first([history_new, tonight, winner])
        assert [e.event_ticker for e in ordered] == [
            "KXWNBAPTS-26OCT07NYATL",
            "KXWNBAGAME-26OCT07NYATL",
            "KXMIDTERMCOUNTY-26NOV03X",
        ]

    def test_a_settled_derivative_event_keeps_its_place(self):
        """The floor series' history must not ride along to the front."""
        history_new = _ev("KXMIDTERMCOUNTY-26NOV03X")
        settled = _ev("KXMLBHIT-26SEP201610SFLAD", statuses=("finalized", "finalized"))
        ordered = _floor_series_first([history_new, settled])
        assert [e.event_ticker for e in ordered] == [
            "KXMIDTERMCOUNTY-26NOV03X",
            "KXMLBHIT-26SEP201610SFLAD",
        ]

    def test_a_market_less_derivative_event_keeps_its_place(self):
        history_new = _ev("KXMIDTERMCOUNTY-26NOV03X")
        shell = _ev("KXMLBHIT-26OCT081700CLECWS", statuses=())
        ordered = _floor_series_first([history_new, shell])
        assert ordered[0].event_ticker == "KXMIDTERMCOUNTY-26NOV03X"
