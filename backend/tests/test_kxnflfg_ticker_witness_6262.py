"""#6262 follow-up — an NFL game stops rendering a second time as soccer.

## The ship

`KXNFLFG` ("Pro Football Field Goals") was in neither Kalshi ticker map. One
literal in `KALSHI_TICKER_TO_SPORT_KEY` closes it, and that literal pays twice:

* **Cleanup.** It is the second witness `resolve_market_born_duplicates` needs
  to fold ghost event **15311150** — `soccer_other`, "Denver vs Kansas City",
  scheduled 2026-09-14 00:00Z, 0 markets — onto canonical **14638896**, the real
  Broncos-at-Chiefs game that finished 31-10. Gap B (`614e20b05`) folded three
  rows of this exact shape and named this one, in its commit message and in a
  test asserting `is None`, as the one it could not reach.
* **Prevention.** `americanfootball_nfl` is in `ODDS_API_COVERED_PREFIXES`, and
  `football` is in `LLM_CATEGORIES_THAT_MAY_NOT_CREATE_EVENTS`, so the mint
  cannot recur by either route.

## Why an NFL prop minted a SOCCER row, run rather than reasoned about

Step 1 of `_categorize_kalshi_market` is documented "AUTHORITATIVE — ticker
never lies", but an unmapped prefix resolves to nothing and the row falls
through to the NAME rules. The name is `"Denver vs Kansas City: Team Field
Goals"`, and **"Goals" reads as soccer**:

    _categorize_kalshi_market("Denver vs Kansas City: Team Field Goals",
                              "Sports", "KXNFLFG-26SEP14DENKC", None)
      -> "soccer"

`auto_create_sport_key_from_category` turned that into `soccer_other` and the
prop minted its own id-less fixture, with the Kalshi close time standing in for
kickoff (gotcha #14). That is the Q453 / #5621 scatter signature for the fourth
time, and #5621's own docstring predicted it: *"A series that is simply ABSENT
from both maps still falls through to the name rules — that is the residual
hole."*

## The fix DID NOT reach the row, which is the interesting half

The series-tag repair already re-categorised the MARKETS: all 16 `KXNFLFG`
markets on production sit on real `americanfootball_nfl` events, and the
specimen's own market moved onto 14638896. The ghost EVENT stayed, holding zero
markets. Fixing the label orphaned the row rather than draining it — the same
shape Q050 records for `_reconcile_kalshi_match_segments`. So a census of
MARKETS reads clean while the reader-visible defect is an EVENT.

## Blast radius, measured over production rather than argued

`get_sport_key_from_ticker` is longest-prefix within each map, so adding key `K`
can only change a ticker that STARTS WITH `K`. That reduces "what does this
touch" to one exhaustive query per table, and both came back with one row:

    futures_markets   WHERE lower(external_id) LIKE 'kxnflfg%'
      -> 1 prefix, 16 markets, 16 distinct events, ALL americanfootball_nfl
    event_provider_anchors WHERE lower(source_id) LIKE 'kxnflfg%'
      -> 1 anchor: event 15311150, soccer_other, kalshi_ticker, holds no
         markets, single target 14638896

In the other direction `kxnflfg` is a prefix of no registered key in either map;
the near neighbours differ at character 7 (`kxnflffpts`, `kxnflfirsttd`,
`kxnflfirsttdtime`, `kxnflfantasymost`, `kxnflfirstpick`). So the literal moves
exactly one row, and it is the row the ship names.

## What was deliberately NOT done

`KALSHI_TICKER_TO_DISPLAY_LABEL` is not a label map — `_is_kalshi_game_ticker`
reads it, and a truthy answer arms `_build_game_market_name` (which RENAMES the
row as a matchup) and the `occurrence_datetime` preference in
`_kalshi_commence_time`. Adding `kxnflfg` there is a different change with a
different argument. 176 of the 394 sport-map keys carry no display label,
including Q453's own `kxnfl1q` and `kxnflrace`, so this is the established
shape and not an omission.
"""

from __future__ import annotations

from app.tasks.kalshi import _categorize_kalshi_market, _is_kalshi_game_ticker
from app.tasks.prediction_market_matching import (
    ODDS_API_COVERED_PREFIXES,
    _sport_key_is_odds_api_covered,
)
from app.utils.prediction_market_matching import (
    _SPORT_ABBREV_SUFFIX,
    feeds_win_prob_blend,
)
from app.utils.sport_keys import (
    KALSHI_FUTURES_TICKER_TO_SPORT_KEY,
    KALSHI_GAME_TICKER_PREFIXES,
    KALSHI_TICKER_TO_DISPLAY_LABEL,
    KALSHI_TICKER_TO_SPORT_KEY,
    get_sport_key_from_ticker,
    is_kalshi_game_level_ticker,
)
from tests.test_market_born_duplicate_reads_as_canonical_q050 import (
    MAPPED_NFL_PROP_TICKER,
)

#: The production specimen, ticker for ticker.
TICKER = "KXNFLFG-26SEP14DENKC"
PREFIX = "kxnflfg"
NFL = "americanfootball_nfl"

#: The venue's own name for the market that minted ghost 15311150.
SPECIMEN_NAME = "Denver vs Kansas City: Team Field Goals"


# =============================================================================
# The ship.
# =============================================================================


def test_the_series_resolves_to_the_nfl_6262():
    """The literal. A revert lands here first."""
    assert KALSHI_TICKER_TO_SPORT_KEY[PREFIX] == NFL
    assert get_sport_key_from_ticker(TICKER) == NFL


def test_the_shared_fold_constant_still_names_this_ships_ticker_6262():
    """🔴 CAUGHT BY THE MUTATION SWEEP (M7), AND IT IS NOT A PEDANTIC TIE.

    The fold assertion in the gap B suite steers with
    `MAPPED_NFL_PROP_TICKER`, which lives in the Q050 module. Point that
    constant at any ticker that was ALREADY mapped — `KXNFLGAME-…` is one
    character-class away — and the whole suite stays green while the fold test
    quietly re-proves gap B's ship instead of this one. Nothing in the map
    records WHEN a key was added, so no property can distinguish the two; the
    only honest guard is to name it across the file boundary, here.
    """
    assert MAPPED_NFL_PROP_TICKER == TICKER
    assert MAPPED_NFL_PROP_TICKER.lower().split("-", 1)[0] == PREFIX


def test_the_name_rules_still_read_this_market_as_soccer_6262():
    """🔴 THE DEFECT ITSELF, PINNED — and the reason the ticker must win.

    This is not a test of the fix; it is a test of what the fix is protecting
    against. The categoriser is asked with the series tag ABSENT, which is the
    state at mint time, and the ONLY thing standing between "Team Field Goals"
    and a soccer row is step 1 reading the ticker.

    If someone ever teaches the name rules that "Field Goals" is football, this
    test goes red and should be DELETED rather than inverted — at that point the
    ticker map is belt and braces, and the comment in `sport_keys.py` saying
    "the name rules read Goals as soccer" has become false and must go too.
    """
    assert (
        _categorize_kalshi_market(SPECIMEN_NAME, "Sports", TICKER, None)
        == "football"
    ), "the ticker is no longer outvoting the name"

    # And the counterfactual that makes the sentence above meaningful: strip the
    # ticker and the same name still reads as soccer.
    assert (
        _categorize_kalshi_market(SPECIMEN_NAME, "Sports", None, None)
        == "soccer"
    ), (
        "the name rules no longer read 'Team Field Goals' as soccer — the "
        "premise this ship rests on has moved; see the docstring"
    )


def test_the_mint_cannot_recur_by_either_route_6262():
    """Prevention, not only cleanup (the standing ask on #3813's class).

    Two independent refusals now cover this series, and BOTH are asserted
    because either one alone would leave a route open if the other moved.
    """
    # Route 1: the auto-create boundary refuses a covered league outright.
    assert _sport_key_is_odds_api_covered(get_sport_key_from_ticker(TICKER))
    assert NFL in ODDS_API_COVERED_PREFIXES

    # Route 2: the category the ticker now yields may not create events at all.
    from app.utils.prediction_market_matching import (
        LLM_CATEGORIES_THAT_MAY_NOT_CREATE_EVENTS,
        auto_create_sport_key_from_category,
    )

    category = _categorize_kalshi_market(SPECIMEN_NAME, "Sports", TICKER, None)
    assert category in LLM_CATEGORIES_THAT_MAY_NOT_CREATE_EVENTS
    assert auto_create_sport_key_from_category(category) is None


# =============================================================================
# Blast radius. The point of this ship was that it HAS one, so it is measured
# here rather than asserted in prose.
# =============================================================================


def test_the_new_key_moves_no_other_registered_ticker_6262():
    """Longest-prefix means the reach is exactly "tickers starting with the key".

    Both directions, because they fail differently: a key that SWALLOWS a longer
    registered series silently re-sports it, and a key that IS swallowed never
    fires at all.
    """
    # Nothing registered is a prefix of ours, in either map...
    for mapping in (KALSHI_TICKER_TO_SPORT_KEY, KALSHI_FUTURES_TICKER_TO_SPORT_KEY):
        swallowing = [k for k in mapping if PREFIX.startswith(k) and k != PREFIX]
        assert swallowing == [], swallowing

    # ...and ours is a prefix of nothing registered, in either map.
    for mapping in (KALSHI_TICKER_TO_SPORT_KEY, KALSHI_FUTURES_TICKER_TO_SPORT_KEY):
        swallowed = [k for k in mapping if k.startswith(PREFIX) and k != PREFIX]
        assert swallowed == [], swallowed

    # The near neighbours that make the two assertions above non-trivial: they
    # share six characters and diverge at the seventh. Without these the test
    # would pass just as well on a map with no NFL prop series at all.
    neighbours = {"kxnflffpts", "kxnflfirsttd", "kxnflfirsttdtime"}
    assert neighbours <= set(KALSHI_TICKER_TO_SPORT_KEY)
    for near in neighbours:
        assert near.startswith("kxnflf") and not near.startswith(PREFIX)
        assert get_sport_key_from_ticker(f"{near}-26SEP14DENKC") == NFL


def test_every_registered_prefix_still_resolves_to_its_own_sport_6262():
    """The property the map's own docstring claims, re-run after the insert.

    Longest-prefix-wins is only a no-op while no registered prefix shadows
    another into a DIFFERENT sport. Asked of every key in both maps rather than
    of the one being added, because a new key can break a pair it is not part
    of only by being longer than one of them — and that is cheap to just check.
    """
    for prefix, sport in KALSHI_TICKER_TO_SPORT_KEY.items():
        assert get_sport_key_from_ticker(f"{prefix}-26SEP14DENKC") == sport, prefix
    for prefix, sport in KALSHI_FUTURES_TICKER_TO_SPORT_KEY.items():
        if prefix in KALSHI_TICKER_TO_SPORT_KEY:
            continue  # the game map wins by design; that tie is its own test
        assert get_sport_key_from_ticker(f"{prefix}-26SEP14DENKC") == sport, prefix


def test_a_field_goals_prop_still_cannot_write_the_win_prob_blend_6262():
    """The one thing being in the game map must NOT buy it.

    `feeds_win_prob_blend` admits prefixes ending in `game`, combat bouts and
    racquet matches. `kxnflfg` is none of those, and a field-goals prop writing
    into a game's win probability would be a truth defect, not a coverage win.
    """
    assert feeds_win_prob_blend(TICKER) is False
    # The control: the real game line for the same fixture DOES feed it, so the
    # assertion above is about this series and not about a dead predicate.
    assert feeds_win_prob_blend("KXNFLGAME-26SEP14DENKC") is True


def test_the_team_codes_now_read_in_the_nfl_namespace_6262():
    """`DEN` is the Broncos here, not the Nuggets.

    Q453's specimen was exactly this: an unmapped NFL series whose `DEN`
    resolved to the Denver Nuggets because the prefix had no abbreviation
    namespace. The namespace is derived from the sport map, so the literal
    closes this too — asserted because "derived" is a claim about code that can
    stop being true.
    """
    assert _SPORT_ABBREV_SUFFIX[PREFIX] == "_nfl"


def test_the_display_label_map_was_deliberately_not_touched_6262():
    """🔴 A NON-CHANGE, PINNED, because the tempting edit is one line away.

    `KALSHI_TICKER_TO_DISPLAY_LABEL` looks like a label map and is not:
    `_is_kalshi_game_ticker` reads it, and a truthy answer arms
    `_build_game_market_name` (which renames the row as a matchup) and the
    `occurrence_datetime` preference in `_kalshi_commence_time`. Whoever adds
    `kxnflfg` there is making a second, larger change and should have to delete
    this test to do it.
    """
    assert PREFIX not in KALSHI_TICKER_TO_DISPLAY_LABEL
    assert _is_kalshi_game_ticker(TICKER) is None

    # Not an oddity: 176 of the sport map's keys carry no display label,
    # including Q453's own additions. Asserted as a floor so the claim in the
    # `sport_keys.py` comment cannot quietly become false.
    label_less = set(KALSHI_TICKER_TO_SPORT_KEY) - set(KALSHI_TICKER_TO_DISPLAY_LABEL)
    assert {"kxnfl1q", "kxnflrace"} <= label_less
    assert len(label_less) >= 100


def test_the_prefix_joined_the_matcher_key_set_6262():
    """It is in the derived game-prefix tuple, i.e. Pass 1 can see it.

    `KALSHI_GAME_TICKER_PREFIXES` subtracts the classification-only prefixes, so
    "is in the map" and "is in the matcher's key set" are two facts, and the
    ship needs the second one.
    """
    assert PREFIX in KALSHI_GAME_TICKER_PREFIXES
    assert is_kalshi_game_level_ticker(TICKER) is True
