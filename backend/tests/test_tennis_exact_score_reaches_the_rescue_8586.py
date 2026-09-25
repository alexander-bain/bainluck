"""#8586 — a tennis exact-score question stays open until the match ends.

The #8586 fix made the poller keep Kalshi's close pad as ``resolution_date`` for
a single contest, instead of the venue's estimate (which, for a match, is the
scheduled START). That fix only reaches a row the poller actually rewrites.

Measured 2026-09-25 20:40Z, one beat after heavy v93 carried the fix: every open
``KXATPMATCH`` / ``KXWTAMATCH`` row carried the pad, and all 5 open
``KXATPEXACTMATCH`` rows still carried the start, last poll write 06:54Z. The
match series are on the guaranteed rescue floor (Q426); the exact-score series
were reachable only through the deadline-bounded main scan, which reached them
once. The resolution sweep cannot repair them either — it selects
``resolution_date >= expiration_time`` and a start date sits below that — so
``mark_resolved_futures`` closed three exact-score books on their start date
(MEDROY, HALSAF, CINMUL) while Kalshi still listed every leg ``active``.

The guard is the same shape as #1898's: membership in the floor AND in the
always-fetch set (one exact-score event per match, so daily turnover), plus the
two facts that make the rescued row come back right — it is fetched WITH its
nested legs (no heavy token), and its ticker is a dated fixture, so the window
derivation keeps the pad.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.services.kalshi_api import (
    _ALWAYS_FETCH_SERIES,
    _HEAVY_TOKENS,
    _RESCUE_SERIES_TICKERS,
    _SPORTS_SERIES_TICKERS,
)
from app.tasks.kalshi import _is_dated_fixture_ticker, _is_kalshi_game_ticker
from app.utils.kalshi_resolution_window import derive_resolution_window

_EXACT_SCORE_SERIES = ("KXATPEXACTMATCH", "KXWTAEXACTMATCH")


@pytest.mark.parametrize("series", _EXACT_SCORE_SERIES)
def test_an_exact_score_series_is_on_the_guaranteed_floor(series):
    assert series in _SPORTS_SERIES_TICKERS, (
        f"{series} is not on the rescue floor, so only the main scan can rewrite "
        f"its rows — and a row the poller never rewrites keeps the pre-#8586 "
        f"start date and is closed by `mark_resolved_futures` mid-match."
    )
    assert series in _RESCUE_SERIES_TICKERS


@pytest.mark.parametrize("series", _EXACT_SCORE_SERIES)
def test_an_exact_score_series_is_fetched_even_when_one_event_is_present(series):
    """One stale exact-score event in the main scan must not skip the slate."""
    assert series in _ALWAYS_FETCH_SERIES


@pytest.mark.parametrize("series", _EXACT_SCORE_SERIES)
def test_an_exact_score_series_is_fetched_with_its_legs(series):
    """The window derivation reads the legs; a stripped fetch would not carry them."""
    assert not any(tok in series for tok in _HEAVY_TOKENS)


def test_a_rescued_exact_score_row_keeps_the_close_pad():
    """The rescued row must come back with the pad, not the start (venue shape 9/25)."""
    ticker = "KXATPEXACTMATCH-26SEP26YUNMAJ"
    start = datetime(2026, 9, 26, 8, 30, tzinfo=timezone.utc)
    pad = datetime(2026, 10, 10, 5, 30, tzinfo=timezone.utc)
    legs = [
        SimpleNamespace(
            close_time=pad, expiration_time=pad, expected_expiration_time=start
        )
        for _ in range(4)
    ]

    single_contest = bool(_is_kalshi_game_ticker(ticker)) or _is_dated_fixture_ticker(
        ticker
    )
    assert single_contest, "an exact-score ticker must read as one dated contest"

    window = derive_resolution_window(legs, single_contest=single_contest)
    assert window.resolution_date == pad
    # Strawman: the same legs read as a future take the start — the defect.
    assert derive_resolution_window(legs).resolution_date == start
