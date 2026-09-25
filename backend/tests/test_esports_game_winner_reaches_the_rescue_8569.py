"""#8569 — esports match pages get back the Kalshi prices the venue still lists.

Every esports match-winner series stopped arriving after 2026-09-20 08:47Z while
the rest of Kalshi ingest kept writing. Measured at the venue 2026-09-25
(`/events?series_ticker=…&status=open`): KXCS2GAME 78 open events, KXLOLGAME 27,
KXDOTA2GAME 9, KXVALORANTGAME 6 — and we held 0 open rows in any of them.

Nothing broke on 9/20. Our creation history is BURSTS (9/5, 9/8–13, 9/19–20,
dark in between), which is the signature of the resumable main-scan cursor
passing over those pages now and then: esports never had a channel of its own.
Same membership omission as golf (#163), combat (#173), tennis (Q426) and WNBA
(#1898), and for #1898's reason it is total rather than intermittent: the four
winner series carry the `GAME` heavy token, so discovery refuses them by
construction — and `_DISCOVERY_TAGS` does not name Esports anyway.
"""

from __future__ import annotations

import pytest

from app.services.kalshi_api import (
    _ALWAYS_FETCH_SERIES,
    _DISCOVERY_TAGS,
    _HEAVY_TOKENS,
    _RESCUE_SERIES_TICKERS,
    _SPORTS_SERIES_TICKERS,
)
from app.tasks.kalshi import _categorize_kalshi_market
from app.utils.kalshi_series_selection import select_discovered_series

_ESPORTS_WINNER_SERIES = ("KXCS2GAME", "KXLOLGAME", "KXDOTA2GAME", "KXVALORANTGAME")


@pytest.mark.parametrize("series", _ESPORTS_WINNER_SERIES)
def test_an_esports_winner_series_is_on_the_guaranteed_floor(series):
    assert series in _SPORTS_SERIES_TICKERS, (
        f"{series} is not in the guaranteed rescue floor, so the deadline-bounded "
        f"main scan is its only channel — which is how esports went dark (#8569)."
    )
    assert series in _RESCUE_SERIES_TICKERS


@pytest.mark.parametrize("series", _ESPORTS_WINNER_SERIES)
def test_an_esports_winner_series_is_fetched_even_when_one_event_is_present(series):
    """Daily turnover: one stale match in the main scan must not skip the slate."""
    assert series in _ALWAYS_FETCH_SERIES


@pytest.mark.parametrize("series", _ESPORTS_WINNER_SERIES)
def test_it_is_fetched_stripped_and_backfilled_not_nested(series):
    """The #995 shape: a GAME series goes through the stripped fetch + backfill."""
    assert any(tok in series for tok in _HEAVY_TOKENS)


@pytest.mark.parametrize("series", _ESPORTS_WINNER_SERIES)
def test_a_rescued_row_lands_on_the_esports_category(series):
    """A rescued row that lands on the wrong sport never reaches an esports page."""
    ticker = f"{series}-26SEP261300QUASIN"
    assert _categorize_kalshi_market("QUAZAR vs. Sinners", "Sports", ticker) == "esports"


@pytest.mark.parametrize("series", _ESPORTS_WINNER_SERIES)
def test_discovery_cannot_rescue_an_esports_winner_series(series):
    """THE REASON THE FLOOR IS LOAD-BEARING (#1898's argument, for esports).

    Asked of the real selector with the real token list, under discovery's best
    case — freshly discovered, populated, not already floored.
    """
    selected, receipt = select_discovered_series(
        discovered=[series],
        open_counts={series: 78},
        guaranteed=[],
        heavy_tokens=_HEAVY_TOKENS,
        max_series=60,
        max_open_events=500,
        page_limit=200,
        max_pages=5,
    )
    assert selected == []
    assert "heavy_payload_shape" in str(receipt)


def test_discovery_does_not_ask_for_esports_at_all():
    """Second, independent reason discovery is no channel today. If Esports is
    ever added to the discovery tags this reds so the floor can be re-read, not
    so it can be dropped: the GAME refusal above still stands."""
    assert "Esports" not in _DISCOVERY_TAGS
