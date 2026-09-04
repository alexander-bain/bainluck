"""Guards for Kalshi series DISCOVERY (#2927 container principle, lane1b/024).

The class these guard is the one the hand list kept re-learning: a series the
venue carries and our list does not name, so we hold none of it. Golf before
#163, combat before #173, tennis singles before Q426 — and, measured
2026-09-04 against the venue's own `/series?category=Sports&tags=Tennis`, the
US Open doubles draw: 32 open `KXATPDOUBLES` + 22 `KXWTADOUBLES` events at
Kalshi, 0 open rows on our side, newest doubles row five days cold.

The fixtures below are that production shape, not invented tickers.
"""

import asyncio

import pytest

from app.services import kalshi_api as ka
from app.utils.kalshi_series_selection import (
    fetch_stage_deadlines,
    select_discovered_series,
)


# The 39 tennis series the venue had carrying open events on 2026-09-04, with
# their measured open-event counts. Trimmed to the ones that exercise a
# distinct branch; the counts are real.
VENUE_OPEN_COUNTS = {
    "KXATPSETWINNER": 48,
    "KXWTASETWINNER": 32,
    "KXATPDOUBLES": 32,
    "KXITFMATCH": 29,
    "KXITFWMATCH": 24,
    "KXWTADOUBLES": 22,
    "KXITFWDOUBLES": 21,
    "KXITFDOUBLES": 20,
    "KXWTAMATCH": 16,
    "KXATPMATCH": 16,
    "KXATPGTOTAL": 16,
    "KXATPGSPREAD": 16,
    "KXATPEXACTMATCH": 16,
    "KXATPCHALLENGERMATCH": 12,
    "KXATPCHALLENGERDOUBLES": 6,
    "KXATPNATSTAGE": 3,
    "KXWTANATSTAGE": 2,
    "KXHONEYDEUCE": 1,
}
# Series the venue lists but which carried nothing open that day.
VENUE_DORMANT = [
    "KXMIXEDDOUBLES", "KXMIXEDDOUBLESMATCH", "KXWIMMEN", "KXFOMEN",
    "KXAOMEN", "KXLAVERCUP", "KXDAVISCUP", "KXUNITEDCUP", "KXBATTLEOFSEXES",
]
VENUE_TENNIS = list(VENUE_OPEN_COUNTS) + VENUE_DORMANT


def _select(**over):
    kwargs = dict(
        discovered=VENUE_TENNIS,
        open_counts=VENUE_OPEN_COUNTS,
        guaranteed=ka._SPORTS_SERIES_TICKERS,
        heavy_tokens=ka._HEAVY_TOKENS,
        max_series=ka._DISCOVERY_MAX_SERIES,
        max_open_events=ka._DISCOVERY_MAX_OPEN_EVENTS,
        page_limit=ka._DISCOVERY_PAGE_LIMIT,
        max_pages=ka._DISCOVERY_MAX_PAGES,
    )
    kwargs.update(over)
    return select_discovered_series(**kwargs)


class TestTheShip:
    """The doubles draw becomes fetchable. This is the user-visible claim."""

    def test_us_open_doubles_series_are_selected(self):
        selected, receipt = _select()
        picked = {t for t, _ in selected}
        # The five doubles series the venue carried live that day. Before this
        # ship not one of them was reachable: none is in the hand list, and the
        # main scan has never once walked to them.
        for series in (
            "KXATPDOUBLES", "KXWTADOUBLES",
            "KXITFDOUBLES", "KXITFWDOUBLES", "KXATPCHALLENGERDOUBLES",
        ):
            assert series in picked, f"{series} must be discovered: {receipt}"

    def test_honey_deuce_is_selected(self):
        """The US Open's own side question — 1 event, 7 markets, never held."""
        picked = {t for t, _ in _select()[0]}
        assert "KXHONEYDEUCE" in picked

    def test_hand_list_alone_would_have_missed_every_one_of_them(self):
        """The red arm's premise, asserted rather than asserted-about.

        If someone ever adds the doubles series to `_SPORTS_SERIES_TICKERS` by
        hand, this test still passes on the discovery path — but the day it
        starts failing is the day the hand list grew again by incident, which
        is the habit the ship exists to break.
        """
        guaranteed = {s.upper() for s in ka._SPORTS_SERIES_TICKERS}
        assert not (guaranteed & {"KXATPDOUBLES", "KXWTADOUBLES", "KXHONEYDEUCE"})


class TestTheReceipt:
    """Every series the venue lists is either fetched or explained."""

    def test_every_discovered_series_is_accounted_for(self):
        selected, receipt = _select()
        accounted = receipt["selected_count"] + sum(receipt["skipped"].values())
        assert accounted == receipt["discovered"] == len(VENUE_TENNIS)

    def test_dormant_series_are_counted_not_named_in_full(self):
        _, receipt = _select()
        assert receipt["skipped"]["no_open_events"] == len(VENUE_DORMANT)
        # Bounded: a receipt that names 101 dormant series every beat buries
        # the handful a reader can act on.
        assert len(receipt["dormant_sample"]) <= 8

    def test_a_declined_live_series_says_why_by_name(self):
        _, receipt = _select()
        # 48 open events we are NOT taking today; the reader must be able to
        # find out that it was the payload shape, not an oversight.
        assert receipt["skipped_detail"]["KXATPSETWINNER"] == "heavy_payload_shape"
        assert receipt["skipped_detail"]["KXATPGSPREAD"] == "heavy_payload_shape"

    def test_hand_listed_series_are_skipped_as_already_covered(self):
        _, receipt = _select()
        for s in ("KXATPMATCH", "KXWTAMATCH", "KXATPNATSTAGE", "KXWTANATSTAGE"):
            assert receipt["skipped_detail"][s] == "already_guaranteed"


class TestTheBounds:
    """The refusals are the reason discovery is affordable at all."""

    def test_heavy_payload_series_are_never_selected(self):
        """#995's monster pages must not reach the poll by a new door."""
        selected, _ = _select()
        for ticker, _pages in selected:
            assert not any(tok in ticker for tok in ka._HEAVY_TOKENS), ticker

    def test_a_series_too_big_for_one_beat_is_refused(self):
        counts = dict(VENUE_OPEN_COUNTS, KXATPDOUBLES=5000)
        _, receipt = _select(open_counts=counts)
        assert receipt["skipped_detail"]["KXATPDOUBLES"] == "too_many_open_events"

    def test_pages_come_from_the_census_not_a_uniform_guess(self):
        selected, _ = _select()
        pages = dict(selected)
        # 32 open events at 50/page is one page. The old loop asked for 5.
        assert pages["KXATPDOUBLES"] == 1
        assert pages["KXHONEYDEUCE"] == 1

    def test_pages_scale_up_but_stay_capped(self):
        counts = dict(VENUE_OPEN_COUNTS, KXATPDOUBLES=90)
        pages = dict(_select(open_counts=counts)[0])
        assert pages["KXATPDOUBLES"] == 2
        counts["KXATPDOUBLES"] = 100
        assert dict(_select(open_counts=counts)[0])["KXATPDOUBLES"] == 2

    def test_max_series_caps_the_beat_and_says_it_did(self):
        selected, receipt = _select(max_series=3)
        assert len(selected) == 3
        assert receipt["skipped"]["over_budget"] >= 1

    def test_biggest_gap_is_fetched_first(self):
        """The order IS the behaviour when a deadline truncates the loop."""
        selected, _ = _select()
        counts = [VENUE_OPEN_COUNTS[t] for t, _ in selected]
        assert counts == sorted(counts, reverse=True)

    def test_selection_is_deterministic(self):
        assert _select()[0] == _select()[0]

    def test_ties_break_on_ticker_so_the_order_is_stable(self):
        counts = {"KXBBB": 5, "KXAAA": 5, "KXCCC": 5}
        selected, _ = _select(discovered=list(counts), open_counts=counts)
        assert [t for t, _ in selected] == ["KXAAA", "KXBBB", "KXCCC"]


class TestTotality:
    """A fetch must never fail on a bookkeeping concern."""

    def test_junk_tickers_are_skipped_not_raised(self):
        selected, receipt = _select(discovered=["", None, "  ", "KXATPDOUBLES"])
        assert [t for t, _ in selected] == ["KXATPDOUBLES"]
        assert receipt["discovered"] == 1

    def test_duplicates_are_collapsed(self):
        _, receipt = _select(discovered=["KXATPDOUBLES", "kxatpdoubles"])
        assert receipt["discovered"] == 1

    def test_empty_catalog_selects_nothing_and_still_reports(self):
        selected, receipt = _select(discovered=[])
        assert selected == []
        assert receipt["discovered"] == 0


class _FakeService(ka.KalshiAPIService):
    """A KalshiAPIService with the network replaced, nothing else."""

    def __init__(self, series=None, census=None, raise_on=None):
        # Real base init: it only builds an (unused) httpx client and opens no
        # socket, and skipping it would leave a half-constructed service — the
        # every-method-is-overridden assumption is exactly the kind that rots.
        super().__init__()
        self._series = series if series is not None else [
            {"ticker": t} for t in VENUE_TENNIS
        ]
        self._census = census
        self._raise_on = raise_on or set()
        self.calls = []

    async def get_series(self, category=None, tags=None, limit=200, cursor=None):
        self.calls.append(("series", tags))
        if "series" in self._raise_on:
            raise RuntimeError("venue down")
        return self._series, None

    async def get_events(self, status=None, series_ticker=None, **kw):
        self.calls.append(("events", series_ticker, status))
        if "events" in self._raise_on:
            raise RuntimeError("venue down")
        if series_ticker is None:
            # The census walk: one page of the open listing.
            counts = self._census if self._census is not None else VENUE_OPEN_COUNTS
            evs = [
                {"event_ticker": f"{s}-26SEP04AAABBB{i}"}
                for s, n in counts.items()
                for i in range(n)
            ]
            return evs, None
        return [], None


class TestResolveDiscoveredSeries:
    """The service half: measure, select, cache — and never break the fetch."""

    def test_live_resolve_selects_the_doubles(self):
        svc = _FakeService()
        selected, receipt = asyncio.run(svc.resolve_discovered_series())
        assert "KXATPDOUBLES" in {t for t, _ in selected}
        assert receipt["source"] == "live"
        assert receipt["census"]["exhausted"] is True

    def test_a_cache_hit_costs_no_venue_calls(self):
        svc = _FakeService()
        cached = {"selected": [["KXATPDOUBLES", 1]], "receipt": {"discovered": 140}}
        selected, receipt = asyncio.run(
            svc.resolve_discovered_series(cached=cached)
        )
        assert selected == [("KXATPDOUBLES", 1)]
        assert receipt["source"] == "cache"
        assert svc.calls == []

    def test_a_malformed_cache_re_measures_rather_than_failing(self):
        svc = _FakeService()
        selected, receipt = asyncio.run(
            svc.resolve_discovered_series(cached={"selected": "not-a-list"})
        )
        assert receipt["source"] == "live"
        assert selected

    def test_an_exhausted_census_is_saved(self):
        svc = _FakeService()
        saved = []
        asyncio.run(svc.resolve_discovered_series(save=saved.append))
        assert saved and saved[0]["selected"]

    def test_a_partial_census_is_used_but_never_saved(self):
        """Caching a truncated walk would freeze the exact gap for the TTL."""
        svc = _FakeService()

        async def _partial(deadline=None, progress_cb=None):
            return {"KXATPDOUBLES": 32}, {"pages": 3, "exhausted": False}

        svc.census_open_series = _partial
        saved = []
        selected, receipt = asyncio.run(
            svc.resolve_discovered_series(save=saved.append)
        )
        assert selected, "a partial census must still be USED"
        assert saved == [], "a partial census must not be cached"
        assert receipt["not_cached"] == "census_partial"

    def test_a_dead_venue_degrades_to_nothing_rather_than_raising(self):
        svc = _FakeService(raise_on={"series"})
        selected, receipt = asyncio.run(svc.resolve_discovered_series())
        assert selected == []
        assert receipt["discovered"] == 0

    def test_census_survives_a_failing_listing(self):
        svc = _FakeService(raise_on={"events"})
        counts, receipt = asyncio.run(svc.census_open_series())
        assert counts == {}
        assert receipt["exhausted"] is False
        assert "error" in receipt

    def test_discovery_asks_the_venue_not_our_tables(self):
        """Notice 26: the question 'does the venue list X' is asked of the venue."""
        svc = _FakeService()
        asyncio.run(svc.discover_series_for_tags(("Tennis",)))
        assert ("series", "Tennis") in svc.calls


class TestStageDeadlines:
    """#999 and #2214 were the same mistake. Discovery is the third stage."""

    RESCUE, DISC, BACKFILL = 60.0, 25.0, 45.0

    def _carve(self, has_discovered, deadline=1000.0):
        return fetch_stage_deadlines(
            deadline, has_discovered, self.RESCUE, self.DISC, self.BACKFILL,
        )

    def test_the_stages_stop_in_order(self):
        d = self._carve(True)
        assert d.main_scan < d.guaranteed < d.discovered < 1000.0

    def test_discovery_gets_a_reserve_the_floor_cannot_touch(self):
        """The failure this prevents: the floor fills the rescue window, and
        discovery's first check fires immediately — zero series, every beat."""
        d = self._carve(True)
        assert d.discovered - d.guaranteed == pytest.approx(self.DISC)

    def test_the_backfill_keeps_its_own_floor_behind_discovery(self):
        d = self._carve(True)
        assert 1000.0 - d.discovered == pytest.approx(self.BACKFILL)

    def test_an_empty_tag_costs_the_guaranteed_floor_nothing(self):
        d = self._carve(False)
        assert d.guaranteed == d.discovered
        assert 1000.0 - d.main_scan == pytest.approx(self.RESCUE + self.BACKFILL)

    def test_the_main_scan_is_what_pays_for_discovery(self):
        """It can afford to: its cursor is resumable, so the seconds are
        deferred to the next beat rather than lost."""
        with_disc = self._carve(True).main_scan
        without = self._carve(False).main_scan
        assert without - with_disc == pytest.approx(self.DISC)

    def test_no_deadline_means_no_stage_stops_early(self):
        assert fetch_stage_deadlines(None, True, 60.0, 25.0, 45.0) == (
            None, None, None,
        )

    def test_the_service_uses_reserves_that_fit_the_fetch_budget(self):
        """The three reserves plus a working main scan must fit in 240s."""
        import inspect
        src = inspect.getsource(
            ka.KalshiAPIService._fetch_all_events_unfiltered
        )
        assert "_DISCOVERY_RESERVE_S = 25.0" in src
        assert "_DISCOVERY_MEASURE_CAP_S = 35.0" in src
        # poll_kalshi's budget. 60 + 25 + 45 + 35 leaves the main scan 75s on a
        # cache miss and 110s on a hit — truncated, but its cursor resumes.
        assert 60.0 + 25.0 + 45.0 + 35.0 < 240.0


class _FetchService(ka.KalshiAPIService):
    """`_fetch_all_events_unfiltered` with only the network faked.

    Distinguishes the three callers of ``get_events`` the way the venue does:
    no series + no status is the main scan, no series + ``open`` is the census,
    a series ticker is a rescue or discovered fetch.
    """

    def __init__(self, main_scan=(), census=None, per_series=None):
        super().__init__()
        self._main = list(main_scan)
        self._census = census if census is not None else VENUE_OPEN_COUNTS
        self._per_series = per_series or {}
        self.fetched_series = []

    async def get_series(self, category=None, tags=None, limit=200, cursor=None):
        return [{"ticker": t} for t in VENUE_TENNIS], None

    async def get_events(
        self, status=None, series_ticker=None, with_nested_markets=True,
        limit=200, cursor=None, deadline=None, progress_cb=None,
    ):
        def _ev(ticker):
            return {
                "event_ticker": ticker, "title": ticker, "category": "Sports",
                "markets": [{"ticker": ticker + "-YES", "title": "y"}],
            }

        if series_ticker is None and status == "open":
            return (
                [
                    _ev(f"{s}-26SEP04X{i}")
                    for s, n in self._census.items()
                    for i in range(n)
                ],
                None,
            )
        if series_ticker is None:
            return [_ev(t) for t in self._main], None
        self.fetched_series.append(series_ticker)
        return [_ev(t) for t in self._per_series.get(series_ticker, [])], None

    async def get_markets(self, **kw):
        return [], None


@pytest.fixture
def no_pacing(monkeypatch):
    """Drop the inter-page politeness sleeps.

    The fetch paces itself against the venue's rate limit — ~60 rescue series at
    0.3s apiece plus the discovered loop is 20s of real sleeping per call, which
    made this file a 112s CI item that measured nothing but `asyncio.sleep`. The
    pacing is the venue's concern; the ordering and the counters are ours.
    """
    real_sleep = asyncio.sleep

    async def _instant(delay, *a, **kw):
        return await real_sleep(0, *a, **kw)

    monkeypatch.setattr(asyncio, "sleep", _instant)


@pytest.mark.usefixtures("no_pacing")
class TestFetchIntegration:
    """The discovered half inside the real fetch, budgets and counters and all."""

    def _run(self, svc, tel, saved=None):
        # Discovery is opt-in on the caller's cache handles, so a test that
        # wants it wires them exactly as `poll_kalshi` does.
        return asyncio.run(
            svc._fetch_all_events_unfiltered(
                deadline=None,
                telemetry=tel,
                save_discovery=(saved.append if saved is not None else lambda _p: None),
            )
        )

    def test_reconciliation_identity_holds_when_discovery_adds_events(self):
        """#1845's invariant is CHECKED every beat by the scan report.

        A third source of additions that did not roll into
        ``supplementary_events`` would break the identity on exactly the beats
        that worked — the fetch would report itself broken for succeeding.
        """
        svc = _FetchService(
            main_scan=["KXMLBGAME-26SEP04BOSNYY"],
            per_series={"KXATPDOUBLES": ["KXATPDOUBLES-26SEP04KRAPUTFARWAL"]},
        )
        tel = {}
        events = self._run(svc, tel)
        assert tel["main_scan_events"] + tel["supplementary_events"] == (
            tel["events_fetched"]
        )
        assert tel["events_fetched"] == len(events)

    def test_the_doubles_event_reaches_the_returned_list(self):
        """End to end: the venue lists it, so the fetch returns it."""
        svc = _FetchService(
            per_series={
                "KXATPDOUBLES": ["KXATPDOUBLES-26SEP04KRAPUTFARWAL"],
                "KXWTADOUBLES": ["KXWTADOUBLES-26SEP03BAROSOKICKIC"],
            },
        )
        tickers = {e.event_ticker for e in self._run(svc, {})}
        assert "KXATPDOUBLES-26SEP04KRAPUTFARWAL" in tickers
        assert "KXWTADOUBLES-26SEP03BAROSOKICKIC" in tickers

    def test_the_receipt_reaches_telemetry(self):
        tel = {}
        self._run(_FetchService(), tel)
        receipt = tel["series_discovery"]
        assert receipt["source"] == "live"
        assert receipt["skipped_detail"]["KXATPSETWINNER"] == "heavy_payload_shape"
        assert "series_fetched" in receipt

    def test_discovered_series_are_fetched_open_only(self):
        """Unfiltered, `KXATPDOUBLES` pages expiry-DESC through 255 settled rows.

        Its page budget comes from the count of OPEN events, so a `status=None`
        fetch would spend that budget on August and return none of today's draw.
        """
        svc = _FetchService(per_series={"KXATPDOUBLES": []})
        captured = []
        orig = svc.get_events

        async def _spy(**kw):
            if kw.get("series_ticker") == "KXATPDOUBLES":
                captured.append(kw.get("status"))
            return await orig(**kw)

        svc.get_events = _spy
        self._run(svc, {})
        assert captured and set(captured) == {"open"}

    def test_an_unwired_caller_pays_no_venue_calls_for_discovery(self):
        """The stage is additive: without cache handles the fetch is unchanged.

        Discovery costs a catalog read plus a census walk. A caller with nowhere
        to persist the answer would pay them every beat and discard it, and
        every existing caller and test would silently acquire a new call
        sequence — which is how a new stage breaks six unrelated guards.
        """
        svc = _FetchService(main_scan=["KXMLBGAME-26SEP04BOSNYY"])
        tel = {}
        asyncio.run(
            svc._fetch_all_events_unfiltered(deadline=None, telemetry=tel)
        )
        assert tel["series_discovery"]["source"] == "not_wired"
        assert tel["series_discovery"]["events_added"] == 0
        assert "KXATPDOUBLES" not in svc.fetched_series

    def test_a_cache_alone_is_enough_to_enable_it(self):
        svc = _FetchService()
        tel = {}
        asyncio.run(
            svc._fetch_all_events_unfiltered(
                deadline=None,
                telemetry=tel,
                discovery_cache={"selected": [["KXATPDOUBLES", 1]]},
            )
        )
        assert tel["series_discovery"]["source"] == "cache"
        assert "KXATPDOUBLES" in svc.fetched_series

    def test_a_dead_discovery_leaves_the_rest_of_the_fetch_intact(self):
        svc = _FetchService(main_scan=["KXMLBGAME-26SEP04BOSNYY"])

        async def _boom(*a, **k):
            raise RuntimeError("venue down")

        svc.resolve_discovered_series = _boom
        tel = {}
        events = self._run(svc, tel)
        assert {e.event_ticker for e in events} >= {"KXMLBGAME-26SEP04BOSNYY"}
        assert tel["series_discovery"]["source"] == "failed"


class TestWiring:
    """The constants are policy, so a guard reaches them by name (Q426)."""

    def test_discovery_tags_are_measured_before_they_are_added(self):
        # Widening this is the whole knob. It is asserted so that adding a tag
        # is a deliberate act with a test to update, not a one-word edit.
        assert ka._DISCOVERY_TAGS == ("Tennis",)

    def test_discovered_series_fetch_with_nested_markets_page_size(self):
        # 50, and for #995's reason: discovered series are fetched WITH nested
        # markets, so they take the page size measured safe for nested pages.
        assert ka._DISCOVERY_PAGE_LIMIT == ka.KalshiAPIService._MAIN_SCAN_PAGE_LIMIT

    def test_fetch_accepts_the_discovery_cache_handles(self):
        import inspect
        for fn in (
            ka.KalshiAPIService.get_all_events,
            ka.KalshiAPIService._fetch_all_events_unfiltered,
        ):
            params = inspect.signature(fn).parameters
            assert "discovery_cache" in params
            assert "save_discovery" in params

    def test_poll_kalshi_persists_the_discovery_measurement(self):
        """The caller owns Redis, as it already does for the main-scan cursor."""
        import inspect
        from app.tasks import kalshi as kt
        src = inspect.getsource(kt._poll_kalshi_markets)
        assert "bainluck:kalshi:rescue_series:v1" in src
        assert "discovery_cache=" in src and "save_discovery=" in src


@pytest.mark.parametrize("tag", ka._DISCOVERY_TAGS)
def test_every_discovery_tag_is_a_real_kalshi_sports_tag(tag):
    assert tag in ka.KalshiAPIService.SPORTS_TAGS
