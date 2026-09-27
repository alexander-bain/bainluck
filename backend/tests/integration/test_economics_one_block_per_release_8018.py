"""#8018: the /economics inflation card stops answering one release twice.

Production `GET /api/economics`, 2026-09-27 06:50Z: `cpi_releases` opened with
Polymarket "Argentina Monthly Inflation - September" (60760395) and directly
under it Kalshi "Argentina inflation rate MoM for September" (60775221) — one
release, two ladders, two answers. The US September print has the same shape
three venues deep: for each of headline MoM, headline YoY, core MoM and core
YoY there is a Kalshi headline-series ladder, a Kalshi EconStats ladder and a
Polymarket ladder. Only the Argentina pair was inside the six on the day, but
folding it alone would have promoted "CPI core month-over-month in Sep 2026?"
into slot six beside "CPI core in September", its own twin.

Names, ids, resolution dates and volumes below are the production rows read by
`db-query` in the same minute. Brackets are plausible, not stored — this ship
moves no number.
"""

from datetime import datetime, timezone

import pytest

from app.routes import economics as econ
from app.utils.inflation_release_identity import (
    ReleaseIdentity,
    fold_same_release,
    inflation_release_identity,
)

from .test_route_economics import _market, _outcome, _query_result


def _at(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc)


# (market_id, source, name, resolution_date, volume) as stored.
ARG_POLY = (60760395, "polymarket", "Argentina Monthly Inflation - September", "2026-10-13T15:59", 12680)
ARG_KALSHI = (60775221, "kalshi", "Argentina inflation rate MoM for September", "2026-10-13T18:59", 7855)

US_SEP = {
    ("headline", "mom"): [
        (364212, "kalshi", "CPI in September", "2026-10-14T12:25", 349303),
        (109971, "kalshi", "CPI month-over-month in Sep 2026?", "2026-10-14T12:29", 41203),
        (60760502, "polymarket", "September Inflation US - Monthly", "2026-10-15T03:59", 39998),
    ],
    ("headline", "yoy"): [
        (55686483, "kalshi", "Inflation in September 2026 (CPI YoY)", "2026-10-14T12:29", 541933),
        (109969, "kalshi", "CPI year-over-year in Sep 2026?", "2026-10-14T12:29", 48663),
        (60760504, "polymarket", "September Inflation US - Annual", "2026-10-15T03:59", 76731),
    ],
    ("core", "mom"): [
        (55686485, "kalshi", "CPI core in September", "2026-10-14T12:25", 137961),
        (109970, "kalshi", "CPI core month-over-month in Sep 2026?", "2026-10-14T12:29", 9351),
        (60760497, "polymarket", "Core CPI MoM - September 2026", "2026-10-15T03:59", 17216),
    ],
    ("core", "yoy"): [
        (55686484, "kalshi", "Core inflation in September 2026 (Core CPI YoY)", "2026-10-14T12:25", 98174),
        (109972, "kalshi", "CPI core year-over-year in Sep 2026?", "2026-10-14T12:29", 3918),
        (60760463, "polymarket", "Core CPI YoY - September 2026", "2026-10-15T03:59", 27460),
    ],
}
COMBO = (61484986, "kalshi", "September 2026 CPI MoM Combo · Headline & Core", "2026-10-14T12:25", 125860)

#: Production titles in the same theme that are NOT one of the releases above
#: and must never be keyed — each carries a word the closed vocabulary does not
#: know, or lacks a month or a measure. A key on any of them could fold a
#: question the reader wanted.
NEVER_KEYED = [
    "September 2026 CPI MoM Combo · Headline & Core",
    "Will core CPI be above headline CPI in September (MoM)?",
    "Will core CPI be above headline CPI in September (YoY)?",
    "Core goods CPI MoM in September",
    "Electricity inflation YoY in September",
    "US gasoline CPI for September",
    "CPI-U index in September",
    "US shelter CPI in September",
    "Will UK inflation be above Euro Area inflation in September?",
    "Will US core inflation be above UK core inflation in September?",
    "South Africa inflation rate MoM for September",
    "Brazil inflation rate in September",
    "Headline PCE inflation in Aug 2026",
    "US headline CPI inflation in December 2030",
    "Argentina Annual Inflation 2026",
    "South Korea Annual Inflation 2026",
    "Will inflation reach more than 5% in 2026?",
    "How high will CPI get this year?",
    # Synthetic: no country and no "CPI". Only a CPI title defaults to the US;
    # a bare "inflation" could be any country's with the country dropped.
    "Monthly Inflation - September",
    "",
    None,
]


def _cpi_market(spec):
    market_id, source, name, resolves, volume = spec
    m = _market(
        market_id=market_id,
        name=name,
        external_id=f"ext-{market_id}",
        source=source,
        resolution_date=_at(resolves),
        outcomes=[
            _outcome("0.1%", 0.30, outcome_id=market_id * 10, rank=1),
            _outcome("0.2%", 0.45, outcome_id=market_id * 10 + 1, rank=2),
            _outcome("0.3%", 0.25, outcome_id=market_id * 10 + 2, rank=3),
        ],
    )
    m.volume = volume
    return m


ALL_SPECS = [ARG_POLY, ARG_KALSHI, COMBO] + [s for group in US_SEP.values() for s in group]


async def _blocks(client, mock_db, specs=ALL_SPECS):
    mock_db.execute.return_value = _query_result([_cpi_market(s) for s in specs])
    body = (await client.get("/api/economics")).json()
    return body["themes"]["inflation"]["cpi_releases"]


class TestIdentity:
    def test_the_argentina_pair_is_one_release(self):
        a = inflation_release_identity(ARG_POLY[2])
        b = inflation_release_identity(ARG_KALSHI[2])
        assert a == b == ReleaseIdentity("argentina", 9, None, "mom", "headline")

    @pytest.mark.parametrize("series_measure", list(US_SEP))
    def test_each_us_trio_is_one_release(self, series_measure):
        series, measure = series_measure
        keys = {inflation_release_identity(s[2])._replace(year=None) for s in US_SEP[series_measure]}
        assert keys == {ReleaseIdentity("us", 9, None, measure, series)}

    def test_the_four_us_measures_are_four_releases(self):
        keys = {
            inflation_release_identity(group[0][2])._replace(year=None)
            for group in US_SEP.values()
        }
        assert len(keys) == 4

    @pytest.mark.parametrize("title", NEVER_KEYED)
    def test_an_unreadable_title_is_never_keyed(self, title):
        assert inflation_release_identity(title) is None

    def test_above_is_not_the_over_of_month_over_month(self):
        # The tokenizer aliases `above` onto `over`; read as the joint of
        # "month-over-month" it would key a comparison as core MoM. Synthetic
        # on purpose: the production comparisons also say "headline", which the
        # next test refuses on its own, so only this title isolates the rule.
        assert inflation_release_identity("Core CPI above September (MoM)") is None
        assert inflation_release_identity("CPI core month-over-month in Sep 2026?") is not None

    def test_a_title_naming_both_series_is_not_either_series(self):
        assert inflation_release_identity("Core and headline CPI MoM in September") is None
        assert inflation_release_identity("Headline CPI MoM in September") is not None

    def test_different_countries_months_years_are_different_keys(self):
        assert inflation_release_identity("Argentina Monthly Inflation - September") != (
            inflation_release_identity("Argentina Monthly Inflation - October")
        )
        assert inflation_release_identity("September Inflation UK - Annual") != (
            inflation_release_identity("September Inflation US - Annual")
        )
        assert inflation_release_identity("CPI month-over-month in Sep 2026?") != (
            inflation_release_identity("CPI month-over-month in Sep 2027?")
        )


def _row(spec):
    market_id, _source, name, resolves, volume = spec
    return {"id": market_id, "q": name, "v": volume, "r": _at(resolves)}


def _fold(rows):
    return fold_same_release(
        rows, name=lambda r: r["q"], volume=lambda r: r["v"],
        resolves=lambda r: r["r"], key=lambda r: r["id"],
    )


class TestFold:
    def test_the_most_traded_ladder_survives(self):
        assert [r["id"] for r in _fold([_row(ARG_KALSHI), _row(ARG_POLY)])] == [ARG_POLY[0]]
        trio = US_SEP[("headline", "yoy")]
        assert [r["id"] for r in _fold([_row(s) for s in trio])] == [55686483]

    def test_the_survivor_does_not_depend_on_input_order(self):
        rows = [_row(s) for s in ALL_SPECS]
        forward = {r["id"] for r in _fold(rows)}
        backward = {r["id"] for r in _fold(list(reversed(rows)))}
        assert forward == backward

    def test_input_order_is_kept_for_survivors(self):
        rows = [_row(COMBO), _row(ARG_KALSHI), _row(ARG_POLY)]
        assert [r["id"] for r in _fold(rows)] == [COMBO[0], ARG_POLY[0]]

    def test_one_key_a_month_apart_is_two_releases(self):
        # A year-less "September" priced a year later is a different release;
        # the release dates, not the title, separate them.
        next_year = (1, "polymarket", ARG_POLY[2], "2027-10-13T15:59", 1)
        assert len(_fold([_row(ARG_POLY), _row(next_year)])) == 2

    def test_a_yearless_title_without_a_release_date_is_never_folded(self):
        rows = [_row(ARG_POLY), _row(ARG_KALSHI)]
        rows[1]["r"] = None
        assert len(_fold(rows)) == 2

    def test_unkeyed_rows_always_survive(self):
        rows = [_row(COMBO), _row(COMBO)]
        assert len(_fold(rows)) == 2


class TestTheServedCard:
    async def test_argentina_is_served_once_from_the_more_traded_venue(self, client, mock_db):
        ids = [b["market_id"] for b in await _blocks(client, mock_db)]
        assert ARG_POLY[0] in ids
        assert ARG_KALSHI[0] not in ids

    async def test_no_two_blocks_price_one_release(self, client, mock_db):
        blocks = await _blocks(client, mock_db)
        keys = [inflation_release_identity(b["q"]) for b in blocks]
        keyed = [k._replace(year=None) for k in keys if k is not None]
        assert len(keyed) == len(set(keyed)), [b["q"] for b in blocks]

    async def test_the_six_slots_go_to_six_different_releases(self, client, mock_db):
        # Argentina, the combo, and one ladder for each US measure — the
        # most-traded one. Without the fold three of these slots went to twins.
        ids = {b["market_id"] for b in await _blocks(client, mock_db)}
        assert ids == {ARG_POLY[0], COMBO[0], 364212, 55686485, 55686484, 55686483}

    async def test_the_fold_bookkeeping_does_not_reach_the_payload(self, client, mock_db):
        for block in await _blocks(client, mock_db):
            assert not any(k.startswith("_") for k in block), block

    async def test_control_without_the_fold_the_card_serves_the_twins(
        self, client, mock_db, monkeypatch
    ):
        # The red half: the same rows through the route with the fold removed
        # reproduce the production card — both Argentina ladders, first and
        # second. If this ever passes with the fold in place, the tests above
        # are not reading the route.
        monkeypatch.setattr(econ, "fold_same_release", lambda items, **_: list(items))
        ids = [b["market_id"] for b in await _blocks(client, mock_db)]
        assert ids[:2] == [ARG_POLY[0], ARG_KALSHI[0]]
