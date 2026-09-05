"""ux/1082 (#3250 + #3143): the Monthly rainfall card stops saying there is nothing.

`/weather`'s "Monthly rainfall" card — subtitled *"'Above 1 inch of rain', city
by city"* — read **"No live rainfall markets right now"** at every width while
Kalshi quoted monthly rain in TEN cities. The empty state was honest; the
absence was not. Measured at the venue on 2026-09-05 by series discovery
(notice 26a, `/series?category=Climate and Weather`, 369 series → 11 monthly
city-rain series), one `/events?series_ticker=…&status=open&
with_nested_markets=true` per series:

    KXRAINNYCM 10 markets   KXRAINMIAM 16   KXRAINCHIM  7   KXRAINDALM  7
    KXRAINHOUM  7           KXRAINSFOM  7   KXRAINSEAM  7   KXRAINLAXM  7
    KXRAINAUSM  7           KXRAINDENM  7   KXRAINSTPM  0 (dormant)

82 nested markets, every one priced. We held FOUR rows, all of them NYC
(`KXRAINNYCM-26SEP/OCT/NOV/DEC`), and every one carried ZERO outcomes.

There are two independent defects in that, and fixing either alone still ships
a broken card. This file guards both, plus the display bug the pair un-latents.

**1. Coverage.** Ten of eleven series were never fetched. `_ALWAYS_FETCH_SERIES`
   is keyed on the series STRING, not the prefix, so "KXRAIN" being a member did
   nothing for "KXRAINNYCM" — and a monthly series keeps its settled events in
   the listing forever (36 KXRAINNYCM events at the venue), so the
   `any(startswith)` short-circuit was satisfied by a dead row on every beat.

**2. The shell.** The one city we DID hold was held market-less, and the rescue
   could not repair it: both merges read `if ticker not in all_events`, so the
   re-fetch that carried the ten priced markets was DISCARDED in favour of the
   empty incumbent. Widening the series list alone would have fixed the nine
   cities we had never seen and left the one visible on the card untouched —
   the fix would have looked like it worked.

**3. The month (#3143).** The card kept the LATEST resolution date per city, so
   the moment prices arrived it would have answered for December. Filed latent;
   the ingest halves above are exactly what un-latents it.
"""

import asyncio
import time
from datetime import datetime, timedelta, timezone

import pytest

from app.services import kalshi_api as ka
from app.services.kalshi_api import (
    MERGE_ADDED,
    MERGE_KEPT,
    MERGE_UPGRADED,
    KalshiAPIService,
    KalshiEvent,
    KalshiMarket,
    merge_fetched_event,
)


@pytest.fixture
def client():
    return KalshiAPIService()


async def _no_sleep(*_a, **_k):
    return None


def _raw_threshold_market(event_ticker: str, inches: int, prob: float) -> dict:
    """One priced threshold market, in the shape the venue actually sends.

    `*_dollars` strings, not integer cents: verified against Kalshi on
    2026-09-05, where `/markets?series_ticker=KXRAINNYCM` no longer carries the
    `yes_bid`/`last_price` integer keys AT ALL. Reading the absent ones is what
    made the first pass of this diagnosis report "unpriced" for a market
    quoting 0.96/0.99 — the parser already prefers `_dollars`, and the fixture
    has to speak the same dialect or it proves nothing about production.
    """
    return {
        "ticker": f"{event_ticker}-{inches}",
        "event_ticker": event_ticker,
        "title": "Rain in NYC in Sep 2026?",
        "yes_sub_title": f"Above {inches} inch{'es' if inches > 1 else ''}",
        "status": "active",
        "yes_bid_dollars": f"{prob - 0.01:.4f}",
        "yes_ask_dollars": f"{prob + 0.01:.4f}",
        "last_price_dollars": f"{prob:.4f}",
    }


def _raw_nyc_september(markets: bool) -> dict:
    """`KXRAINNYCM-26SEP` as the LISTING returns it — shell, or fully nested.

    The fetch parses raw payloads (`_parse_event`), so a fixture that hands it
    ready-made `KalshiEvent`s is silently dropped by the parser's try/except
    and every assertion downstream becomes vacuous. See
    `test_the_fixture_actually_reaches_the_accumulator`.
    """
    return {
        "event_ticker": "KXRAINNYCM-26SEP",
        "title": "Rain in NYC in Sep 2026?",
        "category": "Climate and Weather",
        "markets": (
            [_raw_threshold_market("KXRAINNYCM-26SEP", i, 0.97 - 0.09 * i)
             for i in range(1, 11)]
            if markets else []
        ),
    }


def _nyc_september(markets: bool) -> KalshiEvent:
    """The same event already PARSED — what `merge_fetched_event` operates on."""
    return KalshiEvent(
        event_ticker="KXRAINNYCM-26SEP",
        title="Rain in NYC in Sep 2026?",
        category="Climate and Weather",
        markets=(
            [
                KalshiMarket(
                    ticker=f"KXRAINNYCM-26SEP-{i}",
                    event_ticker="KXRAINNYCM-26SEP",
                    title="Rain in NYC in Sep 2026?",
                    yes_sub_title=f"Above {i} inch{'es' if i > 1 else ''}",
                    status="active",
                    last_price=0.97 - 0.09 * i,
                )
                for i in range(1, 11)
            ]
            if markets else []
        ),
    )


async def _run_fetch(client, monkeypatch, main_scan_events=(), series_events=None):
    """Drive the real fetch.

    ``main_scan_events`` and ``series_events`` carry RAW event payloads;
    ``series_events`` maps a series ticker to what its supplementary fetch
    returns, so a test can make the rescue answer with the nested markets the
    venue really has.
    """
    supplementary: list[str] = []
    nested_by_series: dict[str, bool] = {}
    series_events = series_events or {}
    consumed: list[int] = []
    tel: dict = {}

    async def fake_get_events(**kw):
        st = kw.get("series_ticker")
        if st is None:
            consumed.append(1)
            return (list(main_scan_events) if len(consumed) == 1 else [], None)
        supplementary.append(st)
        nested_by_series[st] = kw.get("with_nested_markets")
        return (list(series_events.get(st, [])), None)

    monkeypatch.setattr(client, "get_events", fake_get_events)
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    events = await client._fetch_all_events_unfiltered(
        deadline=time.monotonic() + 1000, telemetry=tel
    )
    return supplementary, nested_by_series, events, tel


# ---------------------------------------------------------------------------
# 1. Coverage — ten cities the rescue never asked for
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestEveryMonthlyCityReachesTheRescue:
    async def test_all_eleven_monthly_series_are_fetched(self, client, monkeypatch):
        supp, _, _, _ = await _run_fetch(client, monkeypatch)
        missing = [s for s in ka._WEATHER_MONTHLY_SERIES_TICKERS if s not in supp]
        assert not missing, (
            f"monthly city-rain series never fetched: {missing} — the card "
            "promises 'city by city' and only NYC was ever ingested"
        )

    async def test_a_settled_monthly_event_does_not_seal_its_series_shut(
        self, client, monkeypatch
    ):
        """THE COVERAGE DEFECT. Red before the monthly series joined
        `_ALWAYS_FETCH_SERIES`.

        A monthly series never drops its settled events — `KXRAINNYCM-26AUG` is
        finalized and still listed. `any(startswith)` therefore matches on every
        beat, forever, and the rescue is skipped 100% of the time. That is a
        stronger failure than the daily case this file's ux/1076 sibling guards:
        a daily series at least fails intermittently.
        """
        settled = {
            "event_ticker": "KXRAINNYCM-26AUG",
            "title": "Rain in NYC in Aug 2026?",
            "category": "Climate and Weather",
            "markets": [],
        }
        supp, _, events, _ = await _run_fetch(
            client, monkeypatch, main_scan_events=[settled]
        )
        # The short-circuit reads `all_events`, so this assertion is only worth
        # anything if the stale event actually GOT there. Without it the test
        # passes just as happily on a fixture the parser threw away.
        assert any(e.event_ticker == "KXRAINNYCM-26AUG" for e in events), (
            "fixture never reached the accumulator — the short-circuit this "
            "test exists to defeat was never exercised"
        )
        assert "KXRAINNYCM" in supp, (
            "a finalized KXRAINNYCM-26AUG must not stand in for September — "
            "'we have this series' is not 'we have its open month'"
        )

    async def test_the_short_circuit_is_keyed_on_the_series_not_the_prefix(self):
        """Why every monthly ticker needs its OWN membership.

        The loop tests `st not in _ALWAYS_FETCH_SERIES`. "KXRAIN" is a prefix of
        "KXRAINNYCM" but is not equal to it, so prefix membership buys the
        monthly series nothing. Asserting the mechanism, not just the outcome.
        """
        assert "KXRAIN" in ka._ALWAYS_FETCH_SERIES
        for st in ka._WEATHER_MONTHLY_SERIES_TICKERS:
            assert st in ka._ALWAYS_FETCH_SERIES, (
                f"{st} must be a member in its own right — it startswith "
                "'KXRAIN' and that is not what the loop tests"
            )

    async def test_monthly_rain_is_fetched_with_its_nested_markets(
        self, client, monkeypatch
    ):
        """The threshold markets ARE the card. Fetched stripped they arrive
        empty and wait on the per-event backfill, which is the shell state
        #3250 is about."""
        _, nested, _, _ = await _run_fetch(client, monkeypatch)
        for st in ka._WEATHER_MONTHLY_SERIES_TICKERS:
            assert nested.get(st) is True, f"{st} must fetch WITH nested markets"


class TestTheMonthlySetIsShapedRight:
    def test_no_monthly_series_carries_a_heavy_token(self):
        """A heavy token would strip the nested markets and route these through
        the per-event backfill — reintroducing the shell by another door."""
        for st in ka._WEATHER_MONTHLY_SERIES_TICKERS:
            assert not any(tok in st.upper() for tok in ka._HEAVY_TOKENS)

    def test_the_dormant_series_is_still_carried(self):
        """KXRAINSTPM had 0 open events when measured. The set is "the series
        the venue lists", a rule; dropping the dormant one makes it a snapshot
        of one afternoon that rots the month St Petersburg opens."""
        assert "KXRAINSTPM" in ka._WEATHER_MONTHLY_SERIES_TICKERS

    def test_monthly_series_are_in_the_one_rescue_net(self):
        """The fetch, the discovery hand-off and the empty-event backfill all
        read the concatenation, so they cannot disagree about coverage."""
        for st in ka._WEATHER_MONTHLY_SERIES_TICKERS:
            assert st in ka._RESCUE_SERIES_TICKERS
            assert st not in ka._SPORTS_SERIES_TICKERS


# ---------------------------------------------------------------------------
# 2. The shell — a rescue that could not repair the row it exists for
# ---------------------------------------------------------------------------

class TestAShellNeverWinsOverMarkets:
    def test_absent_event_is_added(self):
        acc: dict = {}
        assert merge_fetched_event(acc, _nyc_september(markets=True)) == MERGE_ADDED
        assert len(acc["KXRAINNYCM-26SEP"].markets) == 10

    def test_a_market_less_incumbent_is_upgraded(self):
        """THE MERGE DEFECT. Red before `merge_fetched_event` existed.

        The main scan puts the shell in first; the rescue then fetches the same
        event properly and gets its ten priced markets. Under `if ticker not in
        all_events` that good parse was dropped on the floor and the upsert's
        `if not event.markets: continue` turned the whole city into nothing.
        """
        acc = {"KXRAINNYCM-26SEP": _nyc_september(markets=False)}
        assert merge_fetched_event(acc, _nyc_september(markets=True)) == MERGE_UPGRADED
        assert len(acc["KXRAINNYCM-26SEP"].markets) == 10, (
            "the parse carrying markets must win over the shell"
        )

    def test_markets_are_never_replaced_by_a_shell(self):
        """The same bug pointed the other way: a later market-less parse must
        not undo a good one."""
        acc = {"KXRAINNYCM-26SEP": _nyc_september(markets=True)}
        assert merge_fetched_event(acc, _nyc_september(markets=False)) == MERGE_KEPT
        assert len(acc["KXRAINNYCM-26SEP"].markets) == 10

    def test_a_redundant_good_parse_changes_nothing(self):
        acc = {"KXRAINNYCM-26SEP": _nyc_september(markets=True)}
        assert merge_fetched_event(acc, _nyc_september(markets=True)) == MERGE_KEPT

    def test_two_shells_stay_one_shell(self):
        acc = {"KXRAINNYCM-26SEP": _nyc_september(markets=False)}
        assert merge_fetched_event(acc, _nyc_september(markets=False)) == MERGE_KEPT
        assert len(acc) == 1


@pytest.mark.asyncio
class TestTheRescueRepairsTheShellEndToEnd:
    async def test_the_fetch_returns_september_with_its_markets(
        self, client, monkeypatch
    ):
        """The whole ship, through the real fetch: the main scan yields the
        shell we actually hold, the rescue answers with what the venue actually
        lists, and the event handed to the upsert carries its ten markets."""
        _, _, events, _ = await _run_fetch(
            client,
            monkeypatch,
            main_scan_events=[_raw_nyc_september(markets=False)],
            series_events={"KXRAINNYCM": [_raw_nyc_september(markets=True)]},
        )
        by_ticker = {e.event_ticker: e for e in events}
        assert "KXRAINNYCM-26SEP" in by_ticker
        assert len(by_ticker["KXRAINNYCM-26SEP"].markets) == 10, (
            "the upsert's first statement is `if not event.markets: continue` — "
            "a shell here is the card's empty state"
        )

    async def test_an_upgrade_is_reported_and_is_not_counted_as_an_addition(
        self, client, monkeypatch
    ):
        """`supplementary_events` is one half of an identity the fetch report
        checks every beat (main_scan + supplementary == events_fetched, Queue
        355 / #1845). An upgrade REPLACES a key rather than adding one, so
        counting it there would break that identity on exactly the beats where
        the repair worked — and not reporting it at all makes a repair that
        never ran indistinguishable from one that did.
        """
        _, _, events, tel = await _run_fetch(
            client,
            monkeypatch,
            main_scan_events=[_raw_nyc_september(markets=False)],
            series_events={"KXRAINNYCM": [_raw_nyc_september(markets=True)]},
        )
        assert tel["shells_upgraded"] == 1
        assert tel["events_fetched"] == len(events)
        assert tel["main_scan_events"] + tel["supplementary_events"] == (
            tel["events_fetched"]
        ), "the upgrade must not move either term of the reconciliation identity"


# ---------------------------------------------------------------------------
# 3. The month (#3143) — un-latented by the two above
# ---------------------------------------------------------------------------

class _FakeOutcome:
    def __init__(self, name, prob, delta=None):
        self.name = name
        self.current_probability = prob
        self.probability_change_24h = delta


class _FakeMarket:
    def __init__(self, name, res_date, prob, external_id="KXRAINNYCM-26SEP"):
        self.name = name
        self.resolution_date = res_date
        self.external_id = external_id
        self.source = "kalshi"
        self.outcomes = [_FakeOutcome("Above 1 inch", prob)]


def _pick_city_best(markets):
    """The route's own dedup, exercised directly.

    `get_rain` is one async function over a live session; the month choice
    inside it is pure. Re-running the same expression here would be a guard
    that only accidentally tests production (the lesson `stripped_market_
    series` was extracted for), so this drives the route's real helper.
    """
    from app.routes.weather import _monthly_city_best

    return _monthly_city_best(markets)


class TestTheCardAnswersForTheMonthInPlay:
    def test_the_nearest_unresolved_month_wins(self):
        """THE DISPLAY DEFECT. Red while the dedup kept the LATEST date.

        NYC carries Sep, Oct, Nov and Dec 2026 open at once. A card titled
        "Monthly rainfall" answering for December is answering for the month
        furthest from the reader.
        """
        now = datetime.now(timezone.utc)
        months = [
            _FakeMarket("Rain in NYC in Dec 2026?", now + timedelta(days=120), 0.55),
            _FakeMarket("Rain in NYC in Sep 2026?", now + timedelta(days=20), 0.97),
            _FakeMarket("Rain in NYC in Nov 2026?", now + timedelta(days=90), 0.60),
            _FakeMarket("Rain in NYC in Oct 2026?", now + timedelta(days=55), 0.70),
        ]
        best = _pick_city_best(months)
        assert set(best) == {"NYC"}
        _res, _market, period = best["NYC"]
        assert period == "Sep 2026", (
            f"the month in play must win, got {period!r} — keeping the latest "
            "date put December on a card about this month's rain"
        )

    def test_each_city_is_judged_on_its_own_months(self):
        """Ten cities now reach this dedup where one did before, so the choice
        has to be per city rather than a single global minimum."""
        now = datetime.now(timezone.utc)
        markets = [
            _FakeMarket("Rain in NYC in Dec 2026?", now + timedelta(days=120), 0.55),
            _FakeMarket("Rain in NYC in Sep 2026?", now + timedelta(days=20), 0.97),
            _FakeMarket("Rain in Miami in Oct 2026?", now + timedelta(days=55), 0.80),
            _FakeMarket("Rain in Miami in Dec 2026?", now + timedelta(days=120), 0.50),
            _FakeMarket(
                "Rain in Los Angeles in Nov 2026?", now + timedelta(days=90), 0.30
            ),
        ]
        best = _pick_city_best(markets)
        assert best["NYC"][2] == "Sep 2026"
        assert best["Miami"][2] == "Oct 2026"
        assert best["Los Angeles"][2] == "Nov 2026", (
            "a multi-word city name must survive the non-greedy city parse"
        )

    def test_a_dated_month_beats_an_undated_one(self):
        """A row we cannot date cannot be compared. It only wins if the city
        has nothing else — the same rule the old code used at the far end of
        the ordering, kept when the ordering flipped."""
        now = datetime.now(timezone.utc)
        undated = _FakeMarket("Rain in NYC in Sep 2026?", None, 0.97)
        dated = _FakeMarket("Rain in NYC in Oct 2026?", now + timedelta(days=55), 0.70)

        assert _pick_city_best([undated, dated])["NYC"][2] == "Oct 2026"
        # …and order of arrival must not decide it.
        assert _pick_city_best([dated, undated])["NYC"][2] == "Oct 2026"

    def test_an_undated_row_is_still_shown_when_it_is_all_the_city_has(self):
        best = _pick_city_best([_FakeMarket("Rain in NYC in Sep 2026?", None, 0.97)])
        assert best["NYC"][2] == "Sep 2026"
