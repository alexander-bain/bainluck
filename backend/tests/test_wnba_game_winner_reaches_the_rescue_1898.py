"""#1898 — a WNBA game page shows its winner market.

The capture sentinel filed `basketball_wnba/moneyline starved_class` five times
between CAL-P063 and 2026-09-14 (0.80 → 0.96 winner markets per game). Two
hypotheses sat on the issue and measurement rejected both: the classifier reads
every WNBA name we hold as `moneyline`, and there are no leaked
`basketball_other` siblings — there are no Polymarket WNBA rows at all. What the
production read actually found was 28 WNBA fixtures holding ZERO linked markets
of any class, every `KXWNBA*` series dead at the same instant
(2026-09-19T18:49:29Z) while the rest of Kalshi ingest wrote normally, and the
venue carrying 24 open `KXWNBAGAME` markets we held none of.

The cause is a membership omission in `_SPORTS_SERIES_TICKERS`, which is the
same cause as golf (#163), combat (#173) and tennis (Q426). What makes this
class worth a guard rather than a fourth one-line patch is the second assertion
below: a `_HEAVY_TOKENS` series is declined by series DISCOVERY *by
construction*, so the hand list is not a safety net over a scan that mostly
works — for these series it is the only channel there is. An omission is
therefore total, permanent and silent, not intermittent.

These tests assert the promise for the five leagues we actually make it for.
They deliberately do NOT assert it for every core team sport: `KALSHI_TICKER_TO_
SPORT_KEY` maps thirteen further game series (NCAAB, NCAAF, EPL, MLS, La Liga…)
onto `CORE_TEAM_SPORTS`, and adding those to the guaranteed floor is a fetch-
budget decision that has to be measured, not an assertion a test may force.
"""

from __future__ import annotations

import pytest

from app.services.kalshi_api import (
    _ALWAYS_FETCH_SERIES,
    _HEAVY_TOKENS,
    _RESCUE_SERIES_TICKERS,
    _SPORTS_SERIES_TICKERS,
)
from app.utils.kalshi_series_selection import select_discovered_series
from app.utils.sport_keys import KALSHI_TICKER_TO_SPORT_KEY

#: The leagues whose nightly game-winner slate we promise a guaranteed floor
#: for. WNBA is the fourth occurrence of the omission class and the reason this
#: file exists; the other four are the promise it was measured against.
_FLOORED_GAME_SERIES = (
    "KXNBAGAME",
    "KXNHLGAME",
    "KXMLBGAME",
    "KXNFLGAME",
    "KXWNBAGAME",
)


@pytest.mark.parametrize("series", _FLOORED_GAME_SERIES)
def test_a_nightly_game_winner_series_is_on_the_guaranteed_floor(series):
    """Without this membership the series has no channel at all (see below)."""
    assert series in _SPORTS_SERIES_TICKERS, (
        f"{series} is not in the guaranteed rescue floor. It carries a heavy "
        f"token, so discovery refuses it and the deadline-bounded main scan is "
        f"the only thing left — the walk whose own report reads "
        f"`wrapped: false` on every beat. This is how WNBA went dark (#1898)."
    )
    assert series in _RESCUE_SERIES_TICKERS


@pytest.mark.parametrize("series", _FLOORED_GAME_SERIES)
def test_a_nightly_game_winner_series_is_fetched_even_when_one_event_is_present(series):
    """The `any(startswith)` short-circuit skips a whole slate on one stale row.

    These series turn over daily, so "the main scan already found one of these"
    is never a reason to skip the fetch — the difference between some and all
    is every other game page that night.
    """
    assert series in _ALWAYS_FETCH_SERIES


def test_the_wnba_winner_series_maps_to_the_wnba_sport_key():
    """A rescued row that lands on the wrong sport key starves the cohort anyway."""
    assert KALSHI_TICKER_TO_SPORT_KEY["kxwnbagame"] == "basketball_wnba"


@pytest.mark.parametrize("series", _FLOORED_GAME_SERIES)
def test_discovery_cannot_rescue_a_game_winner_series(series):
    """THE REASON THE LIST ABOVE IS LOAD-BEARING.

    Delete this and the first test reads as belt-and-braces over a discovery
    pass that would have caught the omission. It would not: `select_discovered_
    series` declines every `_HEAVY_TOKENS` ticker by construction, so a series
    missing from the hand list is missing permanently and silently.

    Asserted against the real selector with the real token list, and with the
    series handed to it as freshly discovered and richly populated — i.e. under
    the most favourable input discovery could possibly have.
    """
    selected, receipt = select_discovered_series(
        discovered=[series],
        open_counts={series: 12},
        guaranteed=[],          # not already floored — discovery's best case
        heavy_tokens=_HEAVY_TOKENS,
        max_series=60,
        max_open_events=500,
        page_limit=200,
        max_pages=5,
    )

    assert selected == [], (
        f"{series} was selected by discovery, which would mean the guaranteed "
        f"floor is no longer this series' only channel. Re-read #1898 before "
        f"relaxing the floor: the whole argument for the hand list rests on "
        f"this refusal."
    )
    declined = str(receipt)
    assert "heavy_payload_shape" in declined, (
        f"discovery declined {series} for some reason other than its payload "
        f"shape; the refusal this guard depends on may have moved. Receipt: "
        f"{declined[:400]}"
    )
