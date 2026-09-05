"""Guards for widening Kalshi series discovery to a SECOND tag (lane1b/040, #2927).

The ship: Football matches and props the venue lists and we do not carry stop
being missing — 2,744 open events across 256 series the hand list never names.

The trap this file exists for is that **the obvious widening un-ships the last
one.** Measured at the venue 2026-09-05 (tag catalog + one exhausted
open-listing census, 70 pages / 13,946 open events / 4,073 series, 22s):

    tag              listed  live  openEv  UNCARRIED  selectable(openEv)
    Football            552   264    2874       2744         40 / 958
    Soccer             1403   580    3243       3243         40 / 390
    Baseball            214    98     883        794         40 / 351
    Basketball          534   138     321        315         40 / 199
    Tennis (shipped)    140    39     329        300         27 / 179
    Hockey               72    21      78         75         16 /  54
    Golf                118    19      22         21         18 /  21
    Olympics             46     0       0          0          0 /   0
    Winter Olympics       0     0       0          0          0 /   0

Football is the darkest in-season tag. Soccer holds more raw open events but
2,526 of its 3,243 are `heavy_payload_shape` — the #995 monster-payload
population — so it yields 390 selectable against Football's 958.

Now the trap. Tennis selects 27 series today and Football has 214 selectable.
Ranked TOGETHER on one shared cap of 40 by open-event count, tennis drops from
**27 series to 3**: `KXWTADOUBLES`, `KXITFDOUBLES` and `KXHONEYDEUCE` are among
the 24 evicted — precisely the US Open doubles coverage that shipped four beats
earlier. Raising the cap does not rescue it (at 80 tennis still loses 17),
because Football's long tail out-ranks tennis's small futures on raw open-event
count forever. One cap over two populations of very different size caps the
smaller one out of existence.

So the cap is SPLIT per tag (`_fair_shares`) rather than shared, and the fetch
order INTERLEAVES the tags so a truncated beat costs every tag its tail rather
than one tag its whole draw — gotcha #41 ("ask what the ordering starts on")
applied across tags instead of within one.

`test_adding_football_evicts_no_tennis_series` is the catching test: it is red
on a shared cap and green on a split one. Every count below is measured, not
invented.
"""

import asyncio

import pytest

from app.services import kalshi_api as ka
from app.utils.kalshi_series_selection import (
    _fair_shares,
    select_discovered_series,
    summarize_discovery_receipt,
)

# ---------------------------------------------------------------------------
# The fixtures are the venue's own shape on 2026-09-05, captured from the
# catalog + census walk, not invented tickers.
#
# TENNIS is COMPLETE: all 39 series the venue had carrying open events, with
# their real counts. 27 of them are selectable (the rest are hand-listed or
# heavy), which is the production number.
#
# FOOTBALL is TRUNCATED to the top 70 of its 264 live series — enough that the
# cap binds, which is what the guards need, and short of a 264-entry literal
# nobody will maintain. It contains the heavy series naturally, in the
# proportion the venue has them (34 of the 70), so the decline path is
# exercised on real tickers rather than a hand-picked few.
#
# Where a number below is a PRODUCTION count rather than the fixture's own, it
# is said so: a reduced fixture can back a shape or a count, not both.
# ---------------------------------------------------------------------------
from tests.test_kalshi_series_discovery import (  # noqa: E402
    VENUE_DORMANT,
)

TENNIS_OPEN_COUNTS = {
    "KXATPSETWINNER": 36, "KXITFWMATCH": 28, "KXITFMATCH": 26,
    "KXWTASETWINNER": 24, "KXATPDOUBLES": 23, "KXWTADOUBLES": 16,
    "KXITFDOUBLES": 14, "KXATPEXACTMATCH": 12, "KXATPGSPREAD": 12,
    "KXATPGTOTAL": 12, "KXATPMATCH": 12, "KXATPSSPREAD": 12,
    "KXATPTOTALSETS": 12, "KXWTAEXACTMATCH": 12, "KXWTAGTOTAL": 12,
    "KXWTAMATCH": 12, "KXITFWDOUBLES": 11, "KXATPCHALLENGERMATCH": 8,
    "KXATPCHALLENGERDOUBLES": 5, "KXATPADVANCE": 3, "KXATPNATSTAGE": 3,
    "KXWTAADVANCE": 3, "KXATPRETIRE": 2, "KXWTANATSTAGE": 2,
    "KXATP": 1, "KXATP1RANK": 1, "KXATPFINALSQUAL": 1, "KXATPGRANDSLAM": 1,
    "KXATPNATWINNER": 1, "KXATPNOVAK25": 1, "KXATPWTA": 1, "KXGRANDSLAM": 1,
    "KXHONEYDEUCE": 1, "KXPLAYERDEAL": 1, "KXSINNERFINISH": 1, "KXWTA": 1,
    "KXWTAFINALSQUAL": 1, "KXWTAGRANDSLAM": 1, "KXWTATOURNWIN": 1,
}
TENNIS_DORMANT = [
    "KXATPRETURN", "KXMOMEN", "KXATPMEN", "KXFOMEN", "KXATPCOMPETE",
    "KXATPWDDF",
] + VENUE_DORMANT
TENNIS = list(TENNIS_OPEN_COUNTS) + TENNIS_DORMANT

FOOTBALL_OPEN_COUNTS = {
    "KXNCAAFGAME": 243, "KXNCAAF1H": 233, "KXNCAAFSPREAD": 104,
    "KXNCAAFTOTAL": 104, "KXNFLRACE": 80, "KXNCAAFWINS": 73, "KXNCAAFOT": 57,
    "KXNCAAF1HSPREAD": 51, "KXNCAAF1HTOTAL": 51, "KXNCAAFFIRSTTDTEAM": 51,
    "KXNCAAFTEAMTOTAL": 51, "KXNCAAFTOPAPRANK": 33, "KXNFLWINS": 33,
    "KXNFLGAME": 32, "KXNFLSTAGEOFELIM": 32, "KXNFLTSPEC": 32,
    "KXNCAAF1Q": 26, "KXNCAAF1QSPREAD": 26, "KXNCAAF1QTOTAL": 26,
    "KXNCAAF2H": 26, "KXNCAAF2HSPREAD": 26, "KXNCAAF2HTOTAL": 26,
    "KXNCAAF2Q": 26, "KXNCAAF2QSPREAD": 26, "KXNCAAF2QTOTAL": 26,
    "KXNCAAF3Q": 26, "KXNCAAF3QSPREAD": 26, "KXNCAAF3QTOTAL": 26,
    "KXNCAAF4Q": 26, "KXNCAAF4QSPREAD": 26, "KXNCAAF4QTOTAL": 26,
    "KXNCAAFDSTTD": 26, "KXNCAAFTEAMTD": 26, "KXNCAAFAWARD": 18,
    "KXNCAAFTOPCFPPOLL": 16, "KXNFL1H": 16, "KXNFL1HSPREAD": 16,
    "KXNFL1HTOTAL": 16, "KXNFL1Q": 16, "KXNFL1QBTTS": 16,
    "KXNFL1QSPREAD": 16, "KXNFL1QTOTAL": 16, "KXNFL2H": 16,
    "KXNFL2HSPREAD": 16, "KXNFL2HTOTAL": 16, "KXNFL2Q": 16,
    "KXNFL2QBTTS": 16, "KXNFL2QSPREAD": 16, "KXNFL2QTOTAL": 16,
    "KXNFL3Q": 16, "KXNFL3QBTTS": 16, "KXNFL3QSPREAD": 16,
    "KXNFL3QTOTAL": 16, "KXNFL4Q": 16, "KXNFL4QBTTS": 16,
    "KXNFL4QSPREAD": 16, "KXNFL4QTOTAL": 16, "KXNFLBOTH": 16,
    "KXNFLDSTTD": 16, "KXNFLEQBTTS": 16, "KXNFLFFLEADERTOP": 16,
    "KXNFLFIRSTTD": 16, "KXNFLFIRSTTDTEAM": 16, "KXNFLPASSTDS": 16,
    "KXNFLPASSYDS": 16, "KXNFLREC": 16, "KXNFLRECYDS": 16,
    "KXNFLRSHYDS": 16, "KXNFLSPREAD": 16, "KXNFLTD": 16,
}
#: The four biggest series in the whole tag, all `_HEAVY_TOKENS`. They must
#: never be selected: 243 open KXNCAAFGAME events is the #995 population.
FOOTBALL_HEAVY_HEADLINE = ("KXNCAAFGAME", "KXNCAAF1H", "KXNCAAFSPREAD",
                           "KXNCAAFTOTAL")
FOOTBALL_DORMANT = [
    "KXNEXTEAMTYREEK", "KXNFLVIEWERSHIP", "KXNFLWINS-GB", "KXLSUCOACH",
    "KXNFLEXACTWINSGB", "KXNFLTEAMFIRSTTD",
]
FOOTBALL = list(FOOTBALL_OPEN_COUNTS) + FOOTBALL_DORMANT

ALL_COUNTS = {**TENNIS_OPEN_COUNTS, **FOOTBALL_OPEN_COUNTS}
BY_TAG = {"Tennis": TENNIS, "Football": FOOTBALL}

#: Production counts, from the live measurement — NOT derived from the reduced
#: Football fixture above. Cited where a test needs the real-world magnitude.
PROD_TENNIS_SELECTABLE = 27
PROD_FOOTBALL_SELECTABLE = 214


def _select(discovered, *, max_series=None, **over):
    kwargs = dict(
        discovered=discovered,
        open_counts=ALL_COUNTS,
        guaranteed=ka._SPORTS_SERIES_TICKERS,
        heavy_tokens=ka._HEAVY_TOKENS,
        max_series=ka._DISCOVERY_MAX_SERIES if max_series is None else max_series,
        max_open_events=ka._DISCOVERY_MAX_OPEN_EVENTS,
        page_limit=ka._DISCOVERY_PAGE_LIMIT,
        max_pages=ka._DISCOVERY_MAX_PAGES,
    )
    kwargs.update(over)
    return select_discovered_series(**kwargs)


def _tennis_only():
    """What the shipped tennis-only path selects — the thing not to regress."""
    return {t for t, _ in _select(TENNIS, max_series=40)[0]}


class TestTheShip:
    """Football's live series become fetchable."""

    def test_football_series_are_selected(self):
        picked = {t for t, _ in _select(BY_TAG)[0]}
        for series in (
            "KXNFLRACE", "KXNCAAFWINS", "KXNCAAFOT", "KXNCAAFFIRSTTDTEAM",
        ):
            assert series in picked, f"{series} must be discovered"

    def test_the_hand_list_names_none_of_them(self):
        """The premise of the ship, asserted rather than asserted-about.

        Scoped to the series discovery actually SELECTS. The hand list does name
        four football tickers (`KXNFLGAME`, `KXNFLSPREAD`…) and they are in the
        fixture on purpose — they are the heavy game-level series the guaranteed
        floor already fetches stripped. The claim is about the props and futures
        beside them, which nothing has ever fetched.
        """
        guaranteed = {s.upper() for s in ka._SPORTS_SERIES_TICKERS}
        selected = {t for t, _ in _select(BY_TAG)[0]}
        football_selected = selected & set(FOOTBALL_OPEN_COUNTS)
        assert football_selected, "the ship selects nothing"
        assert not (guaranteed & football_selected)

    def test_the_biggest_football_series_are_declined_as_heavy(self):
        """243 open events of KXNCAAFGAME is the #995 population, not a prize."""
        selected, receipt = _select(BY_TAG)
        picked = {t for t, _ in selected}
        assert not (picked & set(FOOTBALL_HEAVY_HEADLINE))
        assert receipt["skipped"]["heavy_payload_shape"] >= len(FOOTBALL_HEAVY_HEADLINE)


class TestNoTennisRegression:
    """The catching tests. A shared cap un-ships the doubles; a split one does not."""

    def test_adding_football_evicts_no_tennis_series(self):
        """RED on a shared cap, GREEN on a split one.

        This is the whole reason `_fair_shares` exists. With one global ranking
        the 27 tennis series become 3 and `KXWTADOUBLES` / `KXITFDOUBLES` /
        `KXHONEYDEUCE` — shipped four beats before this change — go dark again.
        """
        before = _tennis_only()
        after = {t for t, _ in _select(BY_TAG)[0]}
        lost = sorted(before - after)
        assert lost == [], f"widening to Football evicted tennis series: {lost}"

    def test_the_doubles_draw_survives_by_name(self):
        """Named individually so a failure says which ship broke."""
        picked = {t for t, _ in _select(BY_TAG)[0]}
        for series in ("KXATPDOUBLES", "KXWTADOUBLES", "KXHONEYDEUCE"):
            assert series in picked, f"{series} regressed out of the selection"

    def test_a_shared_cap_is_what_would_have_broken_it(self):
        """The defect, reproduced — so the guard above is known to be load-bearing.

        Flattening the tags into one list is exactly the naive widening. It must
        produce the eviction; if it ever stops doing so, the test above has
        stopped proving anything.
        """
        flat = list(TENNIS) + [t for t in FOOTBALL if t not in set(TENNIS)]
        shared = {t for t, _ in _select(flat)[0]}
        lost = _tennis_only() - shared
        assert lost, "the shared-cap defect no longer reproduces; re-check the guard"
        # Every one evicted is a small tennis future, which is the signature:
        # the shared ranking is on raw open-event count, so the tag with the
        # longer tail wins every tie-break forever.
        assert all(TENNIS_OPEN_COUNTS[t] <= 2 for t in lost), lost
        # MAGNITUDE IS PRODUCTION'S, NOT THE FIXTURE'S. Football is truncated to
        # 70 of its 264 live series here, so the fixture evicts a handful; the
        # live catalog evicts 24 of 27 at cap 40 and 17 at cap 80. The fixture
        # proves the shape, the census proved the size.
        assert len(lost) >= 1

    def test_tennis_keeps_its_share_even_against_a_far_bigger_tag(self):
        """Football's catalog could be ten times larger and tennis is unmoved."""
        huge = dict(ALL_COUNTS)
        big_tag = []
        for i in range(300):
            ticker = f"KXFAKE{i:03d}"
            huge[ticker] = 90
            big_tag.append(ticker)
        after = {
            t for t, _ in _select(
                {"Tennis": TENNIS, "Football": big_tag}, open_counts=huge,
            )[0]
        }
        assert not (_tennis_only() - after)


class TestFairShares:
    """The split itself, as a unit."""

    def test_an_equal_split_when_both_tags_want_more(self):
        assert _fair_shares({"a": 100, "b": 100}, 60) == {"a": 30, "b": 30}

    def test_a_tag_that_wants_less_releases_the_remainder(self):
        # Tennis (27) under a 30 share releases 3, which Football takes.
        assert _fair_shares({"Tennis": 27, "Football": 214}, 60) == {
            "Tennis": 27, "Football": 33,
        }

    def test_a_dormant_tag_costs_the_others_nothing(self):
        """Adding an out-of-season tag must not shrink a live one."""
        assert _fair_shares({"a": 40, "b": 0}, 60) == {"a": 40, "b": 0}

    def test_nobody_gets_more_than_they_want(self):
        assert _fair_shares({"a": 3, "b": 4}, 60) == {"a": 3, "b": 4}

    def test_a_cap_smaller_than_the_tag_count_is_handed_out_one_apiece(self):
        shares = _fair_shares({"a": 5, "b": 5, "c": 5}, 2)
        assert sum(shares.values()) == 2
        assert shares == {"a": 1, "b": 1, "c": 0}

    def test_a_zero_cap_selects_nothing_rather_than_raising(self):
        assert _fair_shares({"a": 5}, 0) == {"a": 0}

    def test_no_tags_at_all_is_not_a_crash(self):
        assert _fair_shares({}, 60) == {}

    def test_the_split_is_deterministic(self):
        wants = {"Tennis": 27, "Football": 214, "Soccer": 190}
        assert _fair_shares(wants, 60) == _fair_shares(wants, 60)

    def test_the_cap_is_never_exceeded(self):
        for cap in (1, 7, 40, 60, 999):
            shares = _fair_shares({"a": 500, "b": 500, "c": 500}, cap)
            assert sum(shares.values()) <= cap


class TestFetchOrder:
    """The order IS the behaviour when a deadline truncates the loop."""

    def test_the_tags_are_interleaved(self):
        selected, _ = _select(BY_TAG)
        tags = [
            "Tennis" if t in TENNIS_OPEN_COUNTS else "Football"
            for t, _ in selected[:8]
        ]
        assert len(set(tags)) == 2, f"expected both tags near the head: {tags}"

    def test_each_tag_is_still_biggest_first_within_itself(self):
        selected, _ = _select(BY_TAG)
        for source in (TENNIS_OPEN_COUNTS, FOOTBALL_OPEN_COUNTS):
            counts = [source[t] for t, _ in selected if t in source]
            assert counts == sorted(counts, reverse=True)

    def test_a_truncated_beat_costs_every_tag_its_tail_not_one_tag_everything(self):
        """The interleave's whole point, asserted on the failure it prevents."""
        selected, _ = _select(BY_TAG)
        # The reserve runs out halfway: the loop breaks where it stands.
        fetched = [t for t, _ in selected[: len(selected) // 2]]
        assert any(t in TENNIS_OPEN_COUNTS for t in fetched)
        assert any(t in FOOTBALL_OPEN_COUNTS for t in fetched)

    def test_one_tag_still_orders_plainly_by_size(self):
        """The shipped tennis-only behaviour, unchanged."""
        selected, _ = _select({"Tennis": TENNIS})
        counts = [TENNIS_OPEN_COUNTS[t] for t, _ in selected]
        assert counts == sorted(counts, reverse=True)

    def test_a_flat_list_behaves_exactly_like_one_tag(self):
        """Backwards compatibility is the contract every existing caller relies on."""
        assert _select(TENNIS)[0] == _select({"Tennis": TENNIS})[0]


class TestTheReceipt:
    """A reader can see the split, which is the only way to spot a squeeze."""

    def test_the_split_is_reported_per_tag(self):
        _, receipt = _select(BY_TAG)
        assert receipt["selected_per_tag"] == {"Football": 33, "Tennis": 27}

    def test_the_split_survives_into_the_persisted_receipt(self):
        """Bounded telemetry drops a lot; this must not be among it."""
        _, receipt = _select(BY_TAG)
        receipt["source"] = "live"
        kept = summarize_discovery_receipt(receipt)
        assert kept["selected_per_tag"] == {"Football": 33, "Tennis": 27}

    def test_an_untagged_selection_reports_no_split(self):
        """A flat caller has no tags, so it must not invent a `_` tag."""
        _, receipt = _select(TENNIS)
        assert receipt["selected_per_tag"] == {}
        assert "_" not in summarize_discovery_receipt(
            dict(receipt, source="live")
        ).get("selected_per_tag", {})

    def test_every_series_is_still_either_fetched_or_explained(self):
        selected, receipt = _select(BY_TAG)
        assert receipt["discovered"] == len(set(TENNIS) | set(FOOTBALL))
        assert len(selected) + sum(receipt["skipped"].values()) == receipt["discovered"]

    def test_the_expected_counts_still_cover_every_selected_series(self):
        """CERT-953's per-series alarm reads this; the widening must not thin it."""
        selected, receipt = _select(BY_TAG)
        assert set(receipt["selected_expected"]) == {t for t, _ in selected}


class _TwoTagService(ka.KalshiAPIService):
    """A service whose venue answers each tag DIFFERENTLY, like the real one.

    The existing `_FakeService` returns the same catalog for every tag, which
    cannot tell a split selection from a shared one. This one can.
    """

    def __init__(self):
        super().__init__()
        self.tags_asked = []

    async def get_series(self, category=None, tags=None, limit=200, cursor=None):
        self.tags_asked.append(tags)
        catalog = {"Tennis": TENNIS, "Football": FOOTBALL}.get(tags, [])
        return [{"ticker": t} for t in catalog], None

    async def get_events(self, status=None, series_ticker=None, **kw):
        if series_ticker is not None:
            return [], None
        return [
            {"event_ticker": f"{s}-26SEP05AAABBB{i}"}
            for s, n in ALL_COUNTS.items()
            for i in range(n)
        ], None


class TestTheChain:
    """The catalog's tags must reach the selection, not just exist at both ends.

    lane1b/037 and lane1b/039 were both two green ends around a chain that did
    not connect. `by_tag` is a new link, so it gets a test that drives the whole
    thing rather than the producer and the consumer separately.
    """

    def test_the_service_asks_the_venue_for_every_discovery_tag(self):
        svc = _TwoTagService()
        asyncio.run(svc.resolve_discovered_series())
        assert svc.tags_asked == list(ka._DISCOVERY_TAGS)

    def test_the_tag_split_survives_the_whole_resolve(self):
        """End to end: two catalogs in, a per-tag split out."""
        svc = _TwoTagService()
        selected, receipt = asyncio.run(svc.resolve_discovered_series())
        assert receipt["source"] == "live"
        assert receipt["selected_per_tag"] == {"Football": 33, "Tennis": 27}
        picked = {t for t, _ in selected}
        # Both tags reached the fetch list, and tennis's ship is intact.
        assert "KXNFLRACE" in picked and "KXATPDOUBLES" in picked
        assert "KXHONEYDEUCE" in picked

    def test_a_catalog_without_tags_still_selects(self):
        """A degraded catalog falls back to the flat list rather than nothing."""
        svc = _TwoTagService()

        async def _no_tags(tags, deadline=None, progress_cb=None):
            return list(TENNIS), {"tags": list(tags), "requests": 1}

        svc.discover_series_for_tags = _no_tags
        selected, receipt = asyncio.run(svc.resolve_discovered_series())
        assert selected, "a catalog with no by_tag must still select something"
        assert receipt["selected_per_tag"] == {}


class TestTheBudget:
    """The reserve is 25s and the cap is sized against a measured fetch."""

    def test_the_planned_pages_fit_the_discovery_reserve(self):
        """The irreducible floor: 0.2s of deliberate sleep per page.

        Timed against the live venue on 2026-09-05, the full 60-series selection
        was 64 pages costing a median 16.7s and a worst-of-ten 22.3s — so the
        fixed sleep is 12.8s of it and the actual work is ~4-9.5s.

        The bound is set from that measurement, not from taste: 16.0s of sleep
        is ~80 pages, a quarter more than the shipped selection. Crossing it
        means the cap or `_DISCOVERY_MAX_PAGES` grew enough that the measured
        headroom no longer applies, and the loop needs re-timing before it can
        be trusted to finish inside the reserve.
        """
        selected, _ = _select(BY_TAG)
        sleep_floor = sum(pages for _, pages in selected) * 0.2
        assert sleep_floor <= 16.0, (
            f"{sleep_floor:.1f}s of fixed sleep out of a 25.0s reserve is past "
            "the point the fetch was timed at; re-time before raising the cap"
        )

    def test_the_reserve_the_cap_was_sized_against_has_not_moved(self):
        import inspect
        src = inspect.getsource(ka.KalshiAPIService._fetch_all_events_unfiltered)
        assert "_DISCOVERY_RESERVE_S = 25.0" in src


@pytest.mark.parametrize("tag", ka._DISCOVERY_TAGS)
def test_every_discovery_tag_is_a_real_kalshi_sports_tag(tag):
    assert tag in ka.KalshiAPIService.SPORTS_TAGS


def test_the_dormant_football_series_are_counted_not_named(self=None):
    """288 dormant Football series must not bury the refusals a reader can act on."""
    _, receipt = _select(BY_TAG)
    assert receipt["skipped"]["no_open_events"] >= len(FOOTBALL_DORMANT)
    assert len(receipt["dormant_sample"]) <= 8
    for ticker in FOOTBALL_DORMANT + VENUE_DORMANT:
        assert ticker not in receipt["skipped_detail"]
