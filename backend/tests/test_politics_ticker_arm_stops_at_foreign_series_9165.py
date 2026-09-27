"""#9165 — the politics page stops pulling golf, music charts and budget data
through a bare Kalshi ticker prefix.

THE READER'S VIEW (native, iPhone on the production API, 2026-09-27 ~15:12Z):
under the 2028 presidential race on /politics, among the related markets, a card
reading "Presidents Cup: Hole-in-One" (1+ / 2+ / 3+ holes-in-one). The served
payload carried it at `themes.presidential.side_markets[7]`
(`artifacts/9165/BEFORE-api-politics.json`), so the web page was served it too.

THE CAUSE: `get_politics` spreads `_THEME_BY_TICKER` into its pool query as
`external_id LIKE '<PREFIX>%'`, and three of those prefixes were shorter than
the series they meant:

    KXPRES%  also matches KXPRESCUP*   (Presidents Cup, golf)
    KXBILL%  also matches KXBILLBOARD* (Billboard charts, entertainment)
    KXGOV%   also matches KXGOVBAL / KXGOVTSPEND (budget balance, spending — economics)

Measured on production 2026-09-27: every open row those three arms fetched that
the `llm_sport_category IN ('politics','geopolitics')` arm did not was one of
these — 22 golf, 4 Billboard, 7 economics, 1 culture. The real presidential,
governor and bills series are all tagged `politics`, so the arms bought nothing
else. The fix moves the three prefixes to `_THEME_BY_TICKER_CLASSIFY_ONLY`: they
still LABEL the rows the category arm fetches, and they no longer FETCH.

WHAT WOULD MAKE THIS FILE VACUOUS: a table with no ticker prefixes at all passes
every "does not fetch" assertion. `TestRealPoliticsSeriesKeepTheirTheme` is the
control that answers it — it fails on any fix that deletes the prefixes instead
of moving them. `test_the_old_table_admits_the_specimens` re-runs the specimens
against the retired table and requires them to be admitted; if it ever fails,
the "does not fetch" tests below are measuring nothing.
"""

import inspect
from types import SimpleNamespace

import pytest

from app.routes import politics as politics_route
from app.routes.politics import (
    _THEME_BY_TICKER,
    _THEME_BY_TICKER_CLASSIFY_ONLY,
    _classify_theme,
)

# Real open tickers read from production on 2026-09-27, one or two per family.
_FOREIGN_SERIES = [
    "KXPRESCUPHOLEINONE-26",          # Presidents Cup: Hole-in-One (golf) — the specimen
    "KXPRESCUPMATCH-27SEP26R5M1",     # Singles: Cameron Young vs Ryo Hisatsune (golf)
    "KXPRESCUPPTSLEAD-26",            # Presidents Cup: Overall Points Leader (golf)
    "KXBILLBOARDRUNNERUPSONG-26OCT10",  # #2 on the Billboard Hot 100 (entertainment)
    "KXGOVBAL-26-FRA",                # France's government budget balance (economics)
    "KXGOVTSPEND-26",                 # Government spending increase (economics)
]

_RETIRED_QUERY_PREFIXES = ("kxpres", "kxgov", "kxbill")


def _query_arm_admits(external_id: str, table) -> bool:
    """What the pool query's LIKE arm does with this ticker: a byte-prefix compare
    of the uppercased prefix, exactly as `get_politics` spreads it."""
    return any(external_id.startswith(prefix.upper()) for prefix, _ in table)


def _market(external_id: str, name: str = "Some market"):
    """Only what `_classify_theme` reads. The default name matches no
    `_THEME_BY_NAME` pattern, so a theme below comes from the TICKER."""
    return SimpleNamespace(external_id=external_id, name=name)


class TestTheQueryArmsNoLongerFetchForeignSeries:
    @pytest.mark.parametrize("external_id", _FOREIGN_SERIES)
    def test_no_query_arm_admits_the_series(self, external_id):
        assert not _query_arm_admits(external_id, _THEME_BY_TICKER), (
            f"{external_id} is not politics, and a LIKE arm in the /politics pool "
            "query would fetch it past the category filter (#9165)"
        )

    def test_the_old_table_admits_the_specimens(self):
        """Strawman: the retired arms DID fetch every specimen above."""
        old_table = [*_THEME_BY_TICKER, *((p, "x") for p in _RETIRED_QUERY_PREFIXES)]
        for external_id in _FOREIGN_SERIES:
            assert _query_arm_admits(external_id, old_table), external_id

    def test_the_route_spreads_the_query_table_and_not_the_classify_table(self):
        """The fix is only real while `get_politics` builds its LIKE arms from
        `_THEME_BY_TICKER`. Spreading the classify-only table (or both) into the
        query would put the three bare prefixes straight back."""
        source = inspect.getsource(politics_route.get_politics)
        assert "for prefix, _ in _THEME_BY_TICKER]" in source
        assert "_THEME_BY_TICKER_CLASSIFY_ONLY" not in source


class TestRealPoliticsSeriesKeepTheirTheme:
    """The control: the moved prefixes still label the politics rows the
    category arm fetches, with the theme they had before."""

    @pytest.mark.parametrize("external_id, theme", [
        ("KXPRESPERSON-28", "presidential"),
        ("KXPRESNOMD-28", "presidential"),
        ("KXPRESPARTY-2028", "presidential"),
        ("KXGOVCA-26", "gubernatorial"),
        ("KXGOVOHNOMR-26", "gubernatorial"),
        ("KXBILLS-26", "policy"),
        ("KXBILLSCOUNT-26SEP", "policy"),
    ])
    def test_theme_is_unchanged(self, external_id, theme):
        assert _classify_theme(_market(external_id)) == theme

    def test_the_moved_prefixes_are_classify_only(self):
        classify = {p for p, _ in _THEME_BY_TICKER_CLASSIFY_ONLY}
        query = {p for p, _ in _THEME_BY_TICKER}
        for prefix in _RETIRED_QUERY_PREFIXES:
            assert prefix in classify and prefix not in query, prefix
