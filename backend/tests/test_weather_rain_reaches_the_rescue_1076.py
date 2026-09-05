"""ux/1076: /weather answers its own headline question — tomorrow's rain.

The page opens with "What are the odds it rains tomorrow?" and its Rain &
rainfall section said "No live rainfall markets right now". Kalshi carried 44
open KXRAIN markets (22 cities on 26SEP05, 22 on 26SEP06) and 22 KXRAINWKND at
the time, and our database held zero September rain events of either series.

The 40 KXRAIN rows we DID hold carry the fingerprint of the failure this file
guards: `KXRAIN-26AUG20` was created 2026-08-29, seven days AFTER it resolved
on 08-22, and every sibling is the same shape. Daily rain was not un-ingested,
it was ingested a week late — which for "will it rain tomorrow" is the same as
never — because the deadline-bounded main scan is a slow rotation over the full
open-events listing and a one-day event expires long before the cursor comes
round.

That is the golf (#163) / combat (#173) / tennis (Q426) class, fifth
occurrence. The guard is behavioural, not a membership assertion: a list can be
present and still never fetched, which is exactly what the `startswith`
short-circuit did to tennis.
"""

import asyncio
import time

import pytest

from app.services import kalshi_api as ka
from app.services.kalshi_api import KalshiAPIService, KalshiEvent


@pytest.fixture
def client():
    return KalshiAPIService()


async def _no_sleep(*_a, **_k):
    return None


def _stale_rain_event():
    """One long-settled rain event, the shape our listing was actually in.

    Every KXRAIN row we held was resolved. `startswith` cannot tell that from
    "we have today's rain".
    """
    return KalshiEvent(
        event_ticker="KXRAIN-26AUG20",
        title="Where will it rain on Aug 20, 2026?",
        category="Climate and Weather",
        markets=[],
    )


async def _run_fetch(client, monkeypatch, main_scan_events=()):
    """Drive the real fetch, recording which series the rescue asked for."""
    supplementary: list[str] = []
    nested_by_series: dict[str, bool] = {}

    async def fake_get_events(**kw):
        st = kw.get("series_ticker")
        if st is None:
            # The main scan. Hand back whatever the test seeded, once.
            events = list(main_scan_events)
            main_scan_events_consumed.append(1)
            return (events if len(main_scan_events_consumed) == 1 else [], None)
        supplementary.append(st)
        nested_by_series[st] = kw.get("with_nested_markets")
        return ([], None)

    main_scan_events_consumed: list[int] = []
    monkeypatch.setattr(client, "get_events", fake_get_events)
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    await client._fetch_all_events_unfiltered(deadline=time.monotonic() + 1000)
    return supplementary, nested_by_series


@pytest.mark.asyncio
class TestRainReachesTheGuaranteedRescue:
    async def test_daily_rain_is_fetched_when_we_hold_nothing(
        self, client, monkeypatch
    ):
        supp, _ = await _run_fetch(client, monkeypatch)
        assert "KXRAIN" in supp, (
            "the daily 'Where will it rain' series must be on the guaranteed "
            "rescue — the main scan's rotation reaches it a week after each "
            "event resolves"
        )
        assert "KXRAINWKND" in supp

    async def test_a_stale_rain_event_does_not_seal_the_rescue_shut(
        self, client, monkeypatch
    ):
        """THE DEFECT. Red before `_ALWAYS_FETCH_SERIES` learned about rain.

        The supplementary loop skips a series when the main scan already
        produced any event whose ticker `startswith` it. One settled August
        event is enough to satisfy that for every one of today's 22 cities —
        and settled August events are precisely what our listing was full of.
        """
        supp, _ = await _run_fetch(
            client, monkeypatch, main_scan_events=[_stale_rain_event()]
        )
        assert "KXRAIN" in supp, (
            "a resolved KXRAIN-26AUG20 in the listing must not stand in for "
            "tomorrow's slate — 'we have rain' is not 'we have today's rain', "
            "and for a daily series it is the reverse"
        )

    async def test_a_stale_weekend_event_does_not_seal_the_daily_series_shut(
        self, client, monkeypatch
    ):
        """`KXRAIN` is a PREFIX of `KXRAINWKND` and of the monthly KXRAIN*M
        series, so the short-circuit could be satisfied by a sibling series
        entirely — a stale weekend event suppressing the daily slate."""
        weekend = KalshiEvent(
            event_ticker="KXRAINWKND-26AUG22",
            title="Where will it rain this weekend (Aug 22 - Aug 23)?",
            category="Climate and Weather",
            markets=[],
        )
        monthly = KalshiEvent(
            event_ticker="KXRAINNYCM-26APR",
            title="Rain in NYC in Apr 2026?",
            category="Climate and Weather",
            markets=[],
        )
        supp, _ = await _run_fetch(
            client, monkeypatch, main_scan_events=[weekend, monthly]
        )
        assert "KXRAIN" in supp
        assert "KXRAINWKND" in supp

    async def test_rain_is_fetched_with_its_nested_markets(
        self, client, monkeypatch
    ):
        """A rain event's 22 city markets ARE the card. Fetched without nested
        markets it arrives empty and waits on the backfill — which is the
        stripped-game-series path, and rain carries no `_HEAVY_TOKEN` precisely
        so it does not need it."""
        _, nested = await _run_fetch(client, monkeypatch)
        assert nested.get("KXRAIN") is True
        assert nested.get("KXRAINWKND") is True

    async def test_rain_outruns_the_non_perishable_sports_tail(
        self, client, monkeypatch
    ):
        """Ordering is the difference between a fix that reads right and one
        that works. Appended to `_RESCUE_SERIES_TICKERS`, rain sits at the tail
        of a ~60-series walk — the position #999 records the deadline eating —
        and a rain event is worth nothing the day after. Championship series
        are still there in two hours; tomorrow's rain is not.
        """
        supp, _ = await _run_fetch(client, monkeypatch)
        rain = [i for i, s in enumerate(supp) if s.upper().startswith("KXRAIN")]
        plain_sports = [
            i for i, s in enumerate(supp)
            if not s.upper().startswith(ka._PRIORITY_RESCUE_PREFIXES)
        ]
        assert rain and plain_sports, "expected both rain and ordinary sports fetches"
        assert max(rain) < min(plain_sports), (
            "rain must be fetched before the non-priority sports tail"
        )

    async def test_golf_keeps_its_first_claim(self, client, monkeypatch):
        """Rain joins the priority group; it does not displace the series the
        group was created for. `sorted` is stable and sport is concatenated
        first, so golf still goes first — what rain jumps is the tail."""
        supp, _ = await _run_fetch(client, monkeypatch)
        golf = [
            i for i, s in enumerate(supp)
            if s.upper().startswith(("KXPGA", "KXLPGA", "KXLIV", "KXDPWORLD"))
        ]
        rain = [i for i, s in enumerate(supp) if s.upper().startswith("KXRAIN")]
        assert golf and rain
        assert max(golf) < min(rain), "golf keeps first claim on the reserve"


class TestTheRescueNetStaysOneNet:
    """The three consumers read one concatenation, so the fetch, the discovery
    hand-off and the empty-event backfill cannot disagree about which series
    the net covers."""

    def test_weather_is_in_the_rescue_list(self):
        assert "KXRAIN" in ka._RESCUE_SERIES_TICKERS
        assert "KXRAINWKND" in ka._RESCUE_SERIES_TICKERS

    def test_the_sports_list_is_still_only_sport(self):
        """`_SPORTS_SERIES_TICKERS` keeps its name honest — the discovery
        selection tests read it directly."""
        assert "KXRAIN" not in ka._SPORTS_SERIES_TICKERS
        assert ka._RESCUE_SERIES_TICKERS[: len(ka._SPORTS_SERIES_TICKERS)] == (
            ka._SPORTS_SERIES_TICKERS
        )

    def test_rain_carries_no_heavy_token(self):
        """A heavy token would strip the nested markets and route rain through
        the per-event backfill. None of the tokens appear in either ticker."""
        for st in ("KXRAIN", "KXRAINWKND"):
            assert not any(tok in st for tok in ka._HEAVY_TOKENS)
