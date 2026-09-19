"""#4646 arm (a), backend half — the fixture's own result leaves Bigger Picture.

WHAT A READER SAW. `/events/15314530` (Ito v Lansere, WTA), 390px, 2026-09-19
05:53Z. The hero reads **Ito 72% – Lansere 28%**. Three hundred pixels below,
under "Bigger Picture · Season context":

    GAME PROPS
      OTHER (1)    [Aoi Ito        72%]
    GAME PROPS
      OTHER (1)    [Sofya Lansere  29%]
    2 related futures from multiple sources

72 + 29 = 101. It is one Kalshi market (`61373787` "Ito vs Lansere") published as
two independent binary legs: the hero takes one leg and complements it, the rail
prints both raw, overround and all, and the page answers one question twice with
two different numbers. `/game-markets` serves that same market as ONE labelled
card. #4646 is the p1, open since 2026-09-09; this is the backend half of its
arm (a), the decision site its own routing correction named.

THE PREDICATE IS NOT NEW AND THAT IS THE POINT. #4646 asked for "a careful test
for 'this game_prop is this event's moneyline' that holds across sports". #6799
shipped exactly that afterwards as `_market_is_event_match_winner`, and
`/game-markets` folds duplicate winner cards with it one door up the same file.
Reusing it is what keeps the two doors from drifting into disagreeing about what
the fixture's own result market IS — which is how one market came to be drawn
two ways in the first place. No name rule is written here.

TWO CONTROLS CARRY THIS FILE, because a fold's characteristic failure is taking
something it was never meant to take:

  * `test_unlinked_market_naming_both_clubs_is_kept` — the bound that makes this
    a de-duplication rather than a deletion. Only a market door one owns
    (`event_id == event_id`) is a candidate; a series market or another meeting
    of the same two clubs is not this fixture's result, whatever its legs say.
    Measured on production: 12 markets folded across 21 events, and folds with
    no door-one copy = 0.
  * `test_spanning_both_lists_is_required` — the one that fails against the
    obvious implementation. This door splits a three-way's legs by side, so the
    home list reads {draw, home} and the away list {away}. Judged per list, the
    predicate's two-sides test folds the home pair and leaves the lone away chip
    behind — a worse page than the unfixed one. The rows must be grouped across
    both lists and the market judged once.

`test_an_unrecognised_leg_keeps_the_whole_market` pins the refusal that is
deliberately NOT worked around: `names_match("Brighton", "Brighton and Hove
Albion")` is False, so Brighton v Arsenal keeps its duplicate. That is #6799's
rule (one unrecognised leg keeps the market) and widening a predicate shared
with door one is a separate, measured change — the test exists so the limit is
recorded rather than discovered later as a surprise.
"""

from types import SimpleNamespace

from app.routes.events import _fold_event_match_winner_futures

EVENT_ID = 15314530
OTHER_EVENT_ID = 99999


def _market(market_id, event_id=EVENT_ID):
    return SimpleNamespace(id=market_id, event_id=event_id)


def _row(market_id, market_name, outcome_name):
    return {
        "market_id": market_id,
        "market_name": market_name,
        "outcome_name": outcome_name,
    }


# The photographed specimen: one market, two legs, one per side.
ITO = "Ito vs Lansere"


def test_the_photographed_duplicate_leaves_both_lists():
    home = [_row(61373787, ITO, "Aoi Ito")]
    away = [_row(61373787, ITO, "Sofya Lansere")]

    kept_home, kept_away = _fold_event_match_winner_futures(
        home, away, {61373787: _market(61373787)}, EVENT_ID, "Ito", "Lansere"
    )

    assert kept_home == []
    assert kept_away == []


def test_spanning_both_lists_is_required():
    """A three-way's legs are split by side; judged per list the fold cannot fire.

    ⚠️ THE SPLIT HERE IS CHOSEN TO ISOLATE THE PROPERTY, NOT COPIED FROM THE ROW.
    Production put {home, draw} in the home list and {away} in the away list for
    this market, and that split does NOT test spanning: the home list alone
    already carries two sides, so a per-list implementation folds it and the test
    passes against the bug. Measured — a "home list only" mutant survives that
    arrangement. So the draw is placed on the away side, leaving the home list
    with ONE side: `_market_is_event_match_winner` needs two, so a per-list
    implementation folds nothing at all and both assertions below fail.

    A test whose fixture is the specimen is not automatically a test of the
    specimen's defect.
    """
    name = "Borneo Samarinda vs. Bali United"
    home = [_row(61360690, name, "Borneo Samarinda")]
    away = [
        _row(61360690, name, "Draw (Borneo Samarinda vs. Bali United)"),
        _row(61360690, name, "Bali United"),
    ]

    kept_home, kept_away = _fold_event_match_winner_futures(
        home,
        away,
        {61360690: _market(61360690)},
        EVENT_ID,
        "Borneo Samarinda",
        "Bali United",
    )

    assert kept_home == []
    assert kept_away == [], "the away leg must go with its market, not be stranded"


def test_unlinked_market_naming_both_clubs_is_kept():
    """Only a market door one owns is a candidate — otherwise a fold is a deletion."""
    home = [_row(61373787, ITO, "Aoi Ito")]
    away = [_row(61373787, ITO, "Sofya Lansere")]

    kept_home, kept_away = _fold_event_match_winner_futures(
        home,
        away,
        {61373787: _market(61373787, event_id=OTHER_EVENT_ID)},
        EVENT_ID,
        "Ito",
        "Lansere",
    )

    assert kept_home == home
    assert kept_away == away


def test_a_market_absent_from_row_markets_is_kept():
    """No market record is no evidence of ownership, so it is not a candidate."""
    home = [_row(61373787, ITO, "Aoi Ito")]
    away = [_row(61373787, ITO, "Sofya Lansere")]

    kept_home, kept_away = _fold_event_match_winner_futures(
        home, away, {}, EVENT_ID, "Ito", "Lansere"
    )

    assert kept_home == home
    assert kept_away == away


def test_season_and_prop_rows_are_untouched():
    """The fold takes the fixture's result and nothing else on the page."""
    home = [
        _row(61373787, ITO, "Aoi Ito"),
        _row(55674162, "2028 UEFA Euros Champion", "Germany"),
        _row(61461852, "Boston vs Tampa Bay: Total Runs", "Over 7.5 runs scored"),
    ]
    away = [
        _row(61373787, ITO, "Sofya Lansere"),
        _row(31834301, "English Premier League Champion", "Arsenal"),
    ]
    row_markets = {
        61373787: _market(61373787),
        55674162: _market(55674162),
        61461852: _market(61461852),
        31834301: _market(31834301),
    }

    kept_home, kept_away = _fold_event_match_winner_futures(
        home, away, row_markets, EVENT_ID, "Ito", "Lansere"
    )

    assert [r["market_id"] for r in kept_home] == [55674162, 61461852]
    assert [r["market_id"] for r in kept_away] == [31834301]


def test_a_tail_colon_market_named_for_the_fixture_is_kept():
    """"… : Total Runs" is a prop of the fixture, not the fixture's result."""
    name = "Boston vs Tampa Bay: Total Runs"
    home = [_row(61461852, name, "Boston")]
    away = [_row(61461852, name, "Tampa Bay")]

    kept_home, kept_away = _fold_event_match_winner_futures(
        home, away, {61461852: _market(61461852)}, EVENT_ID, "Boston", "Tampa Bay"
    )

    assert kept_home == home
    assert kept_away == away


def test_an_unrecognised_leg_keeps_the_whole_market():
    """The recorded LIMIT: a short-form club name refuses, so Brighton keeps its duplicate.

    `names_match("Brighton", "Brighton and Hove Albion")` is False (token overlap
    1-of-4, under the 0.5 bar), so that leg answers no side and #6799's rule keeps
    the market. Pinned rather than worked around — widening a predicate shared
    with `/game-markets` is its own measured change.
    """
    home = [
        _row(60481697, "Brighton vs Arsenal", "Tie"),
        _row(60481697, "Brighton vs Arsenal", "Brighton"),
    ]
    away = [_row(60481697, "Brighton vs Arsenal", "Arsenal")]

    kept_home, kept_away = _fold_event_match_winner_futures(
        home,
        away,
        {60481697: _market(60481697)},
        EVENT_ID,
        "Brighton and Hove Albion",
        "Arsenal",
    )

    assert kept_home == home
    assert kept_away == away


def test_empty_lists_are_returned_unchanged():
    assert _fold_event_match_winner_futures([], [], {}, EVENT_ID, "A", "B") == ([], [])


def test_the_fold_is_wired_in_before_the_merges():
    """The mutant the tests above CANNOT see: the call site deleted or moved.

    Every other test in this file calls the helper directly, so all eight pass
    against a `_build_related_futures` that never calls it — a guard suite that
    cannot see whether its own decision is applied. ORDER is load-bearing too:
    after `dedup_by_merge_group` a leg can speak for a market it did not come
    from, so a fold keyed on `market_id` must run while the attribution is still
    each row's own — the same fact `_snapshot_row_market_ids` exists for.
    """
    import inspect

    from app.routes import events as events_module

    src = inspect.getsource(events_module._build_related_futures)
    fold_at = src.find("_fold_event_match_winner_futures(")
    snapshot_at = src.find("_snapshot_row_market_ids(")

    assert fold_at != -1, "_build_related_futures no longer folds the fixture's own result"
    assert snapshot_at != -1, "the pre-merge snapshot moved; re-derive the ordering below"
    assert fold_at < snapshot_at, "the fold must run BEFORE the merges, on un-merged attribution"
