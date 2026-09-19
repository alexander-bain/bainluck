"""LAT-P332 / #7124 — a resolved ticker row is a candidate only at a usable tier.

``get_playoff_grid``'s phase-1 candidate scan admits ``resolved`` markets on the
ticker (Kalshi / Odds API) arm because division winners settle and the grid still
has to show them. Unbounded, that also admits an in-season league's entire
settled per-game inventory: measured on production 2026-09-19, the MLB arm
carried 232 open rows against **42,714 resolved ones, 39,504 of them tier 5** —
innings, first-run, spreads, totals, strikeouts, player props. The scan selects
full ``FuturesMarket`` entities, so at the query plan's 1,538-byte row width the
hourly MLB grid warm pulled ~66 MB across the wire and built 43K ORM objects to
produce a 30-row grid, and failed at 24.3 s on this route's own
``SET LOCAL statement_timeout = '20s'``.

**Why these guards assert the SHAPE and not just a row count.** The defect is
invisible on the page — the grid rendered correctly the whole time, just slowly
and then not at all — and it is invisible in a result set, because the rows the
bound removes were always discarded a moment later by ``_match_market_to_column``.
So a test that only checked "the grid still shows 30 teams" would stay green
through a full revert. These evaluate the REAL clause object the route hands to
SQLAlchemy, against fixture rows, so a revert fails a test rather than getting
slower.

The losslessness of the bound is NOT asserted here — it is a claim about
production rows, and it was measured there: all 57,218 rows the bound drops
across the 14 league configs were paged out and run through the real
``_market_passes_league_filter`` + ``_match_market_to_column``; zero reach a
column, while the same instrument finds 23 column-reaching rows among the rows
the bound KEEPS. See ``_resolved_tier_bound``'s docstring for the table.
"""

import pytest

from app.config.league_configs import get_all_league_slugs, get_league_config
from app.routes.playoffs import (
    GRID_COLUMN_TIERS,
    _build_grid_market_filters,
)

from tests.test_playoff_grid_source_scoped_candidates_lat_p129 import (
    _matches,
    _walk,
)

# Leagues whose config actually HAS a ticker arm. The bound lives on that arm,
# so parametrising over every slug would run the interesting assertions against
# `None` for the nine name-matched leagues and report a green that means
# "nothing was checked".
TICKER_SLUGS = sorted(
    slug
    for slug in get_all_league_slugs()
    if (getattr(get_league_config(slug), "external_id_prefixes", None)
        or getattr(get_league_config(slug), "sport_keys", None))
)


def _with_status(slug):
    return _build_grid_market_filters(get_league_config(slug))[0]


def _ticker_row(slug, *, status, market_tier):
    """A row that reaches the league's ticker arm through its Odds API id space."""
    config = get_league_config(slug)
    return {
        "source": "odds_api",
        "external_id": f"{config.sport_keys[0]}_winner",
        "name": "Some Market",
        "llm_sport_category": None,
        "status": status,
        "market_tier": market_tier,
    }


@pytest.mark.parametrize("slug", TICKER_SLUGS)
@pytest.mark.parametrize("tier", GRID_COLUMN_TIERS)
def test_resolved_ticker_row_at_a_column_tier_is_still_a_candidate(slug, tier):
    """The reason ``resolved`` is on this arm at all: settled division winners.

    Measured on production 2026-09-19, 23 resolved rows at these tiers reach a
    grid column today (nba 8, nhl 5, ncaa-basketball 5, ncaa-women-basketball 3,
    wnba 2). Dropping ``resolved`` outright instead of bounding it would empty
    those columns.
    """
    assert _matches(_with_status(slug), _ticker_row(slug, status="resolved", market_tier=tier))


@pytest.mark.parametrize("slug", TICKER_SLUGS)
def test_resolved_ticker_row_below_the_column_tiers_is_not_a_candidate(slug):
    """The ship. Tier 5 is the per-game/prop tier; no column can be built from it."""
    assert not _matches(
        _with_status(slug), _ticker_row(slug, status="resolved", market_tier=5)
    )


@pytest.mark.parametrize("slug", TICKER_SLUGS)
@pytest.mark.parametrize("status", ["open", "closed"])
def test_the_bound_applies_to_resolved_only(slug, status):
    """An OPEN tier-5 row is still a candidate.

    The bound is a statement about settled inventory, not about tier 5. An open
    market's tier can still be wrong or late, and the open population is three
    orders of magnitude smaller than the resolved one (232 vs 42,714 for MLB),
    so there is nothing to buy by narrowing it and a live column to lose.
    """
    assert _matches(_with_status(slug), _ticker_row(slug, status=status, market_tier=5))


@pytest.mark.parametrize("slug", TICKER_SLUGS)
def test_an_untiered_resolved_row_fails_open(slug):
    """``market_tier IS NULL`` is unclassified, not classified-as-junk.

    There are none in any ticker arm today, so keeping them costs nothing — and
    if a source ever starts minting untiered rows, the grid must not lose a
    column silently while every counter stays green.
    """
    assert _matches(
        _with_status(slug), _ticker_row(slug, status="resolved", market_tier=None)
    )


@pytest.mark.parametrize("slug", TICKER_SLUGS)
def test_the_category_arm_carries_no_tier_term(slug):
    """Polymarket's arm is already ``open|closed``; a tier term there would be
    a second narrowing nobody measured, hiding inside this one."""
    config = get_league_config(slug)
    row = {
        "source": "polymarket",
        "external_id": "0xdeadbeef",
        "name": "Some Market",
        "llm_sport_category": config.sport_category,
        "status": "open",
        "market_tier": 5,
    }
    clause = _with_status(slug)
    # Tier 5 must not be what decides the category arm either way: the row is
    # judged on category + name, exactly as before.
    assert _matches(clause, row) == _matches(clause, {**row, "market_tier": 1})


@pytest.mark.parametrize("slug", sorted(get_all_league_slugs()))
def test_the_bare_filter_gains_no_tier_term(slug):
    """The bare filter feeds the resolved backfill, which applies
    ``GRID_COLUMN_TIERS`` itself. A tier term here would be applied twice — a
    silent no-op today and a trap the day the two sets differ."""
    _, bare = _build_grid_market_filters(get_league_config(slug))
    if bare is None:
        pytest.skip(f"{slug} builds no bare filter")
    for node, _ in _walk(bare):
        left = getattr(node, "left", None)
        assert getattr(left, "key", None) != "market_tier", (
            f"{slug}: bare market_filter must not constrain market_tier"
        )


def test_the_backfill_and_the_scan_share_one_tier_set():
    """The resolved backfill used to spell ``[1, 2, 3, 4]`` inline. Two copies of
    one rule drift; the constant is what makes a future tier a one-line change."""
    import inspect

    from app.routes import playoffs

    source = inspect.getsource(playoffs.get_playoff_grid)
    assert "market_tier.in_(GRID_COLUMN_TIERS)" in source, (
        "the resolved backfill must read the shared constant, not a literal list"
    )
    assert "market_tier.in_([1, 2, 3, 4])" not in source
    assert GRID_COLUMN_TIERS == (1, 2, 3, 4)
