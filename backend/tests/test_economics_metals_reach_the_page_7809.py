"""#7809: /economics stops heading a section "Energy & Commodities" and serving no commodity.

Read at 390px on production 2026-09-21 12:5xZ. The section rendered:

    ENERGY & COMMODITIES
    Gas, oil, and the price at the pump
    21 active

    NATURAL GAS PRICE  $3.145 · modal bracket 18% · 6 brackets
    CRUDE OIL          New Mexico YoY 96% · WTI vs. Brent 75% · WTI $109.99 2%

Not one metal. The only two strings containing "Gold" in `GET /api/economics`
were `Goldman Sachs` and `Annual Return: S&P 500 Total Return Vs. Gold?` — and
that one is admitted by the `s&p` name regex, not because it is a metal.
`Silver`, `Copper`, `Platinum` and `Palladium` appeared nowhere in the payload.

Meanwhile Kalshi was listing them (`/trade-api/v2/markets?series_ticker=KXGOLDD
&status=open` → 5 active, e.g. `KXGOLDD-26SEP2217-T4545`) and we had already
INGESTED twelve of them: 7 filed `other`, 3 `crypto`, 1 `economics`, 1
`politics`. So this was never an ingest gap. The page dropped what we held.

TWO INDEPENDENT GATES, and a fix to either one alone leaves the section empty:

  * the WHERE clause admits `llm_sport_category IN (economics, finance, crypto)`
    OR a `_THEME_BY_TICKER` prefix, and that table's "Energy / commodities"
    block was only `kxgasprice`/`kxwti`/`kxbrent`/`kxoil`. The 7 rows filed
    `other` failed both arms and were never selected. `commodities` is not in
    `econ_categories` either, so fixing the CATEGORISER alone would not have
    fixed this;

  * `_classify_theme` returns `"other"` for anything matching no prefix and no
    name regex, markets are bucketed into a defaultdict, and only the named
    themes are ever read back out. `themed["other"]` is never read and the
    response has no `other` key, so the 4 rows that DID pass the WHERE were
    admitted and then silently discarded. `"Gold price on September 21, 2026 at
    5:00 PM EDT?"` matches no `_THEME_BY_NAME` pattern — the energy regex is
    `gas price|oil price|crude|wti|brent|petrol|gasoline`.

The second gate is the general bug and the reason for this file's last test:
ANY market that passes the category filter but matches no theme vanishes with
no counter and no log. Metals are only the family that made it visible.

WHY METALS ARE THEIR OWN THEME rather than more `energy` prefixes. Measured on
the served payload before the fix was written: `energy` was
`count 21 | gas 1 | oil 4 | side_markets 7`, and `side_markets` is
`[... for m in energy_markets ...][:8]`. Seven of eight slots were already
crude oil, so folding metals into `energy` would have surfaced at most ONE of
them — and which one is arbitrary, because the query has no ORDER BY.

WHY THE PREFIXES ARE SPELLED OUT rather than a bare `kxgold`/`kxcopper`:

  * novelty collisions. `KXGOLDCARDS` is "How many Gold Cards will Trump issue
    before May?" and `KXCOPPERCABLE` is Section 232 cable restrictions. Both
    match a bare metal name and neither is a commodity price;
  * flood. The `*15M` families are ~8,700 fifteen-minute scalping ladders
    (KXGOLD15M 3,566, KXSILVER15M 3,503, KXCOPPER15M 1,638, plus platinum and
    palladium) and would bury every other row on the page.

What this file pins:
  1. every metal PRICE-SERIES ticker reaches the `metals` theme;
  2. the two novelty collisions and the 15M flood do NOT;
  3. the existing energy tickers are untouched;
  4. THE CLASS: no `_THEME_BY_TICKER` entry may map to a theme the response
     does not serve, because such a row is admitted by the WHERE clause and
     then dropped without trace.
"""

import pytest

from app.routes.economics import _THEME_BY_TICKER, _classify_theme


class _Market:
    """The two fields `_classify_theme` reads."""

    def __init__(self, external_id: str, name: str = ""):
        self.external_id = external_id
        self.name = name


# The themes the response actually builds a key for. Kept as a literal so that
# adding a prefix for a theme nobody serves fails test 4 loudly instead of
# silently dropping every row that matches it.
SERVED_THEMES = {
    "fed",
    "inflation",
    "jobs",
    "recession",
    "markets",
    "energy",
    "metals",
    "housing",
    "trade",
    "government",
}


# The twelve rows that were open and unreachable on 2026-09-21, plus the two
# longer-dated series that only exist as hourly markets.
METAL_PRICE_SPECIMENS = [
    ("KXGOLDD-26SEP2117", "Gold price on September 21, 2026 at 5:00 PM EDT?"),
    ("KXGOLDW-26SEP2517", "Gold price on September 25, 2026 at 5:00 PM EDT?"),
    ("KXGOLDMON-26SEP3017", "Gold price on September 30, 2026 at 5:00 PM EDT?"),
    ("KXGOLDH-26AUG0222", "Gold price on August 02, 2026 at 10:00 PM ET"),
    ("KXGOLDDIRY-26DEC31H1700", "Gold price at year end?"),
    ("KXGOLDVSSILVER-26DEC31", "Annual Return: Gold vs. Silver"),
    ("KXSILVERD-26SEP2117", "Silver price on September 21, 2026 at 5:00 PM EDT?"),
    ("KXSILVERW-26SEP2517", "Silver price on September 25, 2026 at 5:00 PM EDT?"),
    ("KXSILVERMON-26SEP3017", "Silver price on September 30, 2026 at 5:00 PM EDT?"),
    ("KXSILVERH-26AUG0222", "Silver price on August 02, 2026 at 10:00 PM ET"),
    ("KXCOPPERD-26SEP2117", "Copper price on September 21, 2026 at 5:00 PM EDT?"),
    ("KXCOPPERW-26SEP2517", "Copper price on September 25, 2026 at 5:00 PM EDT?"),
    ("KXCOPPERMON-26SEP3017", "Copper price on September 30, 2026 at 5:00 PM EDT?"),
    ("KXPLATINUMH-26AUG2412", "Platinum price on August 24, 2026 at 12:00 PM ET"),
    ("KXPALLADIUMH-26AUG0322", "Palladium price on August 03, 2026 at 10:00 PM ET"),
]


@pytest.mark.parametrize("ticker,name", METAL_PRICE_SPECIMENS)
def test_metal_price_series_reaches_the_metals_theme(ticker, name):
    """A metal price market is themed, so the WHERE clause admits it and the
    response reads it back out. Before #7809 every one of these was "other"."""
    assert _classify_theme(_Market(ticker, name)) == "metals"


# A bare `kxgold`/`kxcopper` prefix would swallow all of these.
NOT_A_METAL_PRICE = [
    ("KXGOLDCARDS-26MAY", "How many Gold Cards will Trump issue before May?"),
    (
        "KXCOPPERCABLE-28",
        "When will insulated copper cable face Section 232 restrictions?",
    ),
    ("KXGOLD15M-26SEP2113", "Gold 15 min · $4,030.53 target"),
    ("KXSILVER15M-26SEP2113", "Silver 15 min · $56.700 target"),
    ("KXCOPPER15M-26SEP2113", "Copper 15 min · $6.43324 target"),
    ("KXPLATINUM15M-26SEP2113", "Platinum Up or Down - 15 minutes"),
    ("KXPALLADIUM15M-26SEP2113", "Palladium 15 min · $1,288.572 target"),
]


@pytest.mark.parametrize("ticker,name", NOT_A_METAL_PRICE)
def test_novelty_and_fifteen_minute_families_are_not_metals(ticker, name):
    """The collisions and the ~8,700-row scalping flood stay out of the
    section. A bare `kxgold` prefix passes test 1 and fails this one."""
    assert _classify_theme(_Market(ticker, name)) != "metals"


ENERGY_SPECIMENS = [
    ("KXGASPRICE-26SEP", "Natural gas price"),
    ("KXWTI-26SEP21", "WTI Crude Oil (WTI) Up or Down on September 21?"),
    ("KXBRENT-26SEP", "Annual Return: WTI vs. Brent?"),
    ("KXOILNM-26", "Will New Mexico crude oil production rise YoY?"),
]


@pytest.mark.parametrize("ticker,name", ENERGY_SPECIMENS)
def test_energy_tickers_are_untouched(ticker, name):
    """Metals took their own theme precisely so the energy card's path stays
    byte-identical. If a metal prefix ever shadows an energy one, this fails."""
    assert _classify_theme(_Market(ticker, name)) == "energy"


def test_every_ticker_prefix_maps_to_a_theme_the_response_serves():
    """THE CLASS GUARD.

    A `_THEME_BY_TICKER` entry does two jobs: it admits a market through the
    WHERE clause, and it names the bucket the response reads back out. When
    those disagree — a prefix pointing at a theme with no key in the response —
    the market is selected from the database and then discarded with no
    counter, no log and no `other` bucket to catch it. That is exactly how
    twelve open metal markets were invisible while we held every one of them.
    """
    themes = {theme for _, theme in _THEME_BY_TICKER}
    unserved = themes - SERVED_THEMES
    assert not unserved, (
        f"_THEME_BY_TICKER routes markets to {sorted(unserved)}, which the "
        f"/economics response has no key for. Every market matching those "
        f"prefixes is admitted by the WHERE clause and then silently dropped. "
        f"Add the section to the response (and to SERVED_THEMES), or point the "
        f"prefix at a theme that is served."
    )


def test_the_metals_theme_is_actually_populated_by_some_prefix():
    """Guards the other direction: `SERVED_THEMES` gaining "metals" while the
    prefix table lost its metal entries would leave the section permanently
    empty and every test above still green on classification alone."""
    metal_prefixes = [p for p, theme in _THEME_BY_TICKER if theme == "metals"]
    assert len(metal_prefixes) >= 14, (
        f"expected the metal price-series prefixes, found {metal_prefixes}"
    )
    # The families that were open and unreachable on the day this was filed.
    for stem in ("kxgoldd", "kxsilverd", "kxcopperd", "kxplatinumh", "kxpalladiumh"):
        assert stem in metal_prefixes, f"{stem} is missing from _THEME_BY_TICKER"
