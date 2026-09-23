"""#8166 — the men's NCAA grid's Champion column gets Kalshi's champion market.

The five round columns of `/playoffs/ncaa-basketball` were already fed by Kalshi's
2027 round markets, but the Champion column was served by `odds_api` alone, and the
page was titled "NCAA Tournament 2026". Both are the same stale-literal defect.

Kalshi's `KXMARMAD-27` ("Men's 2027 College Basketball Champion", open, 73/73 priced
on production 2026-09-23) was blocked by TWO independent gates:

  1. `external_id_prefixes=["KXMARMADROUND"]` — the champion ticker does not start
     with the round prefix, so it never reached the SQL candidate set.
  2. `season_pattern="2026"` — the name carries "2027", so `_is_future_season_market`
     dropped it. Already repaired this way on the women's config.

Neither gate alone was the cause and neither alone is the fix, which is why
`test_both_gates_were_necessary` exists.

The narrow prefix is the point. Measured over the real candidate population
(44 rows, `artifacts-authority-986/census_8166.json`), a bare `KXMARMAD` admits 33
further markets, four of which REACH A COLUMN. `KXMARMAD-2` gains 1 column-reaching
market and loses 0.

Two things this file pins that a reader of the diff would not guess:

* The four seed-count props a bare prefix lets into `final_four`/`round_of_32` are
  NOT the reason for the narrowing — all 33 of their outcomes are already caught by
  the stale cutoff or the numeric-outcome filter. The reason is their OPEN 2027
  siblings (`KXMARMADSEED-27T2/T3/T4/T5`, `KXMARMAD1SEED-27`): 293 fresh, team-named,
  fully-priced outcomes held out by the column matcher alone.
* The prefix ends in `2` rather than `-` because `external_id_prefix_range` refuses
  a prefix ending in punctuation, and a range-less prefix drops this league back to
  the 266K-row Kalshi scan LAT-P132 measured at 24,465 ms.
"""
import pytest

from app.config.league_configs import (
    NCAA_BASKETBALL_CONFIG as MENS,
    WNCAA_BASKETBALL_CONFIG as WOMENS,
)
from app.routes.playoffs import (
    _extract_season_max_year,
    _is_future_season_market,
    _is_past_season_market,
    _market_passes_league_filter,
    _match_market_to_column,
)

CHAMPION_TICKER = "KXMARMAD-27"
CHAMPION_PREFIX = "KXMARMAD-2"
CHAMPION_NAME = "Men's 2027 College Basketball Champion"

# Every one of these was admitted by a bare `KXMARMAD` in the census and is a
# seed-count / prop market, not a team market. The first four REACH A COLUMN,
# which is what makes the bare prefix a contamination rather than dead weight.
SEED_PROPS_THAT_REACHED_A_COLUMN = [
    ("KXMARMADSEEDROUND-26S1F4", "#1 seeds to reach the Semifinals"),
    ("KXMARMADSEEDROUND-26S2F4", "#2 seeds to reach the Semifinals"),
    ("KXMARMADSEED-26F4", "Highest numerical seed to qualify for the Semifinals"),
    ("KXMARMADSEED-26R32", "Highest numerical seed to qualify for the Round of 32"),
]
OTHER_BARE_PREFIX_SIBLINGS = [
    ("KXMARMADUPSET-26R64", "Number of upsets in the Round of 64"),
    ("KXMARMADPTS-26", "Men's College Basketball Tournament: Player Points"),
    ("KXMARMADCONFWIN-26", "Conference to win Men's College Basketball Championship"),
    ("KXMARMADSEED-27T2", "Men's College Basketball Tournament: Top 2 Seeds"),
    ("KXMARMAD1SEED-27", "Men's College Basketball Tournament: #1 Seeds"),
]


class Mkt:
    """The three fields `_match_market_to_column` reads."""

    def __init__(self, name, external_id, market_tier=None):
        self.name = name
        self.external_id = external_id
        self.market_tier = market_tier


def _in_ticker_arm(external_id, config):
    """The SQL id-space arm `_build_grid_market_filters` emits for Kalshi."""
    return any(external_id.startswith(p) for p in config.external_id_prefixes)


def _admitted(name, external_id, config, max_year):
    """The real gate chain: SQL prefix arm -> league filter -> season filter."""
    if not _in_ticker_arm(external_id, config):
        return False
    if not _market_passes_league_filter(name, external_id, config):
        return False
    return not _is_future_season_market(name, max_year) and not _is_past_season_market(
        name, max_year
    )


def _max_year():
    return _extract_season_max_year(MENS.season_pattern)


# ---------------------------------------------------------------------------
# The ship
# ---------------------------------------------------------------------------

def test_the_champion_market_reaches_the_champion_column():
    """THE LOAD-BEARING ASSERTION: the Champion column gains a Kalshi source."""
    assert _admitted(CHAMPION_NAME, CHAMPION_TICKER, MENS, _max_year()), (
        "Kalshi's men's champion market is not admitted — the Champion column "
        "falls back to odds_api alone, which is the #8166 defect"
    )
    assert (
        _match_market_to_column(Mkt(CHAMPION_NAME, CHAMPION_TICKER), MENS)
        == "championship"
    )


def test_both_gates_were_necessary():
    """Neither the prefix nor the season pattern alone admits the champion.

    This is what stops a later reader "simplifying" the fix back to one change:
    revert either field on its own and the market is excluded again.
    """
    round_only = _cfg(MENS, external_id_prefixes=["KXMARMADROUND"])
    assert not _admitted(CHAMPION_NAME, CHAMPION_TICKER, round_only, _max_year()), (
        "season pattern alone should not admit it — the ticker prefix is the other gate"
    )
    assert not _admitted(CHAMPION_NAME, CHAMPION_TICKER, MENS, 2026), (
        "the prefix alone should not admit it — max_year 2026 drops a 2027 name"
    )


def test_the_champion_ticker_gate_still_calls_it_a_champion_series():
    """`_is_champion_ticker` must read `KXMARMAD-27` as the genuine full-field
    series, or the #1059 gate silently empties the column it was widened for."""
    from app.routes.playoffs import _is_champion_ticker

    assert _is_champion_ticker(CHAMPION_TICKER, MENS) is True


# ---------------------------------------------------------------------------
# The narrowness — these are the mutations the hyphen exists to survive
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ticker,name", SEED_PROPS_THAT_REACHED_A_COLUMN)
def test_seed_count_props_that_a_bare_prefix_would_have_let_into_a_column(ticker, name):
    """Widen the prefix to a bare `KXMARMAD` and these four land in real columns.

    They are counts OF SEEDS, not teams. The census measured each one reaching
    `final_four` or `round_of_32` under the bare prefix.
    """
    assert not _in_ticker_arm(ticker, MENS), (
        f"{ticker} is in the candidate set — the prefix has been widened past "
        f"the champion series and this resolved seed-count prop now contends "
        f"for a grid column"
    )
    # The instrument is not vacuous: under the bare prefix these DO reach a column,
    # so the assertion above is the only thing keeping them out.
    bare = _cfg(MENS, external_id_prefixes=["KXMARMAD"])
    assert _in_ticker_arm(ticker, bare)
    assert _match_market_to_column(Mkt(name, ticker), bare) is not None


@pytest.mark.parametrize("ticker,name", OTHER_BARE_PREFIX_SIBLINGS)
def test_other_prop_siblings_stay_out_of_the_candidate_set(ticker, name):
    assert not _in_ticker_arm(ticker, MENS)


def test_the_round_markets_did_not_move():
    """The five columns that already worked keep working, and keep their columns."""
    for ticker, name, col in [
        ("KXMARMADROUND-27R32", "Men's Round of 32 Qualifiers", "round_of_32"),
        ("KXMARMADROUND-27R16", "Men's Round of 16 Qualifiers", "sweet_16"),
        ("KXMARMADROUND-27R8", "Men's Round of 8 Qualifiers", "elite_eight"),
        ("KXMARMADROUND-27F4", "Men's Semifinals Qualifiers", "final_four"),
        ("KXMARMADROUND-27T2", "Men's Championship Game Qualifiers", "title_game"),
    ]:
        assert _admitted(name, ticker, MENS, _max_year()), ticker
        assert _match_market_to_column(Mkt(name, ticker), MENS) == col, ticker


def test_the_womens_champion_ticker_is_not_admitted_to_the_mens_grid():
    """`KXWMARMAD-27` must not ride in on the widened prefix."""
    assert not _in_ticker_arm("KXWMARMAD-27", MENS)
    assert not _market_passes_league_filter(
        "Women's 2027 College Basketball Champion", "KXWMARMAD-27", MENS
    )


# ---------------------------------------------------------------------------
# The reader-visible contradiction #8166 was filed for
# ---------------------------------------------------------------------------

def test_the_two_ncaa_basketball_grids_name_the_same_year():
    """The men's and women's tournaments are played in one March; the two grid
    titles cannot disagree about which. This is the drift that produced #8166 and
    the one that produced #3571 before it, and nothing else asserts it."""
    import re

    def year(cfg):
        m = re.search(r"\b(20\d\d)\b", cfg.name)
        assert m, f"{cfg.slug} title carries no year: {cfg.name!r}"
        return m.group(1)

    assert year(MENS) == year(WOMENS), (
        f"{MENS.slug} says {MENS.name!r} and {WOMENS.slug} says {WOMENS.name!r} — "
        f"two sibling tournaments played in the same March, a year apart"
    )
    assert MENS.season_pattern == WOMENS.season_pattern


def test_the_title_year_matches_the_season_the_grid_actually_filters_on():
    """`name` and `season_pattern` are two literals that must not drift apart:
    the first is what a reader sees, the second decides which markets the grid
    admits. #8166 is what it looks like when only one of them is bumped."""
    assert MENS.season_pattern in MENS.name
    assert str(_extract_season_max_year(MENS.season_pattern)) in MENS.name


def _cfg(base, **overrides):
    """A shallow view over a real config with named fields overridden."""

    class _View:
        def __getattr__(self, k):
            if k in overrides:
                return overrides[k]
            return getattr(base, k)

    return _View()


def test_the_champion_prefix_is_index_served():
    """A prefix ending in `-` yields NO range and re-opens the 266K-row Kalshi scan.

    `external_id_prefix_range` refuses a prefix whose last character is not ASCII
    alphanumeric, because punctuation is ignorable at the primary level under
    en_US.UTF-8. The obvious spelling of this fix — `KXMARMAD-` — is exactly that
    refusal, and ncaa-basketball is the league LAT-P132 measured going from
    24,465 ms to 984 ms on the strength of this range.
    """
    from app.routes.playoffs import external_id_prefix_range

    assert external_id_prefix_range("KXMARMAD-") is None  # the trap, pinned
    rng = external_id_prefix_range(CHAMPION_PREFIX)
    assert rng is not None, (
        f"{CHAMPION_PREFIX!r} yields no index range — this league's candidate scan "
        f"falls back to the unindexable bare ILIKE"
    )
    low, high = rng
    assert low <= CHAMPION_TICKER < high
    for prefix in MENS.external_id_prefixes:
        assert external_id_prefix_range(prefix) is not None, prefix


def test_the_live_2027_seed_markets_are_the_reason_for_the_narrowing():
    """293 fresh, team-NAMED, fully-priced outcomes a bare prefix would admit.

    Unlike the resolved 2026 seed props, these are `open` with outcomes written
    within the hour, so neither the 7-day stale cutoff nor the numeric-outcome
    filter (their outcome names are schools — "Michigan St.", "FDU") would stop
    them. Today only `_match_market_to_column` does, by finding no pattern for
    "Top N Seeds" — one name-shaped defence. Keeping them out of the candidate
    set is the second, structural one.
    """
    live_siblings = [
        "KXMARMADSEED-27T2",
        "KXMARMADSEED-27T3",
        "KXMARMADSEED-27T4",
        "KXMARMADSEED-27T5",
        "KXMARMAD1SEED-27",
    ]
    bare = _cfg(MENS, external_id_prefixes=["KXMARMAD"])
    for ticker in live_siblings:
        assert not _in_ticker_arm(ticker, MENS), ticker
        assert _in_ticker_arm(ticker, bare), (
            f"{ticker} no longer rides a bare prefix — this test's premise has "
            f"moved and the narrowing argument needs re-measuring"
        )
