"""#5621 — the basketball page stops serving NFL games.

## The ship

`GET /api/leagues/basketball_other`, read on production Sat 2026-09-12 13:28Z,
the day before NFL Week 1 Sunday. Its LIVE & UPCOMING rail, all eight slots:

    1  Toronto Argonauts @ Ottawa Redblacks          CFL
    2  Winnipeg Blue Bombers @ Saskatchewan Rough..  CFL
    3  Houston @ Buffalo                             NFL
    4  Minnesota @ Green Bay                         NFL
    5  British Columbia Lions @ Montreal Alouettes   CFL
    6  Tennessee @ New York J                        NFL
    7  Cincinnati @ Tampa Bay                        NFL
    8  Jacksonville @ Cleveland                      NFL

Not one of the eight upcoming "basketball" games was basketball.

## One unmapped series, and the scatter that names it

All five NFL rows — 16 in total — were minted by ONE Kalshi series,
`KXNFLFFPTS` (NFL Fantasy Points), which was absent from
`KALSHI_TICKER_TO_SPORT_KEY`. Step 1 of `_categorize_kalshi_market` calls the
ticker "AUTHORITATIVE — ticker never lies", but an unmapped prefix resolves to
nothing and the row falls through to the NAME rules, which read
"Buffalo vs Houston: Fantasy **Points**…" as basketball.

The tell is the scatter — one series wearing four league tags:

    NFL 13 · NBA 1 · NCAAF 1 · WNBA 1

The WNBA row was New York Giants vs Dallas.

## Why a wrong sport MINTS A ROW rather than merely mislabelling one

This is the half that made it reader-visible, and it is what
`test_a_mislabelled_nfl_prop_can_no_longer_mint_an_event` pins:
`LLM_CATEGORIES_THAT_MAY_NOT_CREATE_EVENTS` contains `"football"`, so a market
the ticker proves is American football may NOT invent a fixture — Q453 put it
there because that category's errors are systematic. Mislabelled `basketball`,
the same market sails past that refusal and
`auto_create_sport_key_from_category` hands back `basketball_other`, so the
prop mints its own id-less game with the Kalshi close time standing in for
kickoff (gotcha #14) and the orientation reversed.

So correcting the ticker map closes the defect twice over, by two independent
routes: the row is labelled football, AND it can no longer create an event.

## This is the THIRD instance of one hole

`sport_keys.py` already carries the Q453 block for `kxnfl1q`/`kxnflrace`
("one NFL series scattered across FIVE sports"), and #2321 / #3340 are the same
family on other pages. Each repair added the missing literals. The literals
below are this ship; `test_every_league_token_prefix_maps_to_its_own_sport` is
the part that makes the NEXT mis-mapping loud instead of silent.

A series that is simply ABSENT from both maps still falls through to the name
rules — that is the residual hole, and it needs a league-token fallback in the
categoriser rather than another literal. Filed separately; it is a change to
the classifier, not to this config.
"""

import pytest

from app.tasks.kalshi import _categorize_kalshi_market
from app.utils.prediction_market_matching import (
    LLM_CATEGORIES_THAT_MAY_NOT_CREATE_EVENTS,
    auto_create_sport_key_from_category,
)
from app.utils.sport_keys import (
    KALSHI_FUTURES_TICKER_TO_SPORT_KEY,
    KALSHI_GAME_TICKER_PREFIXES,
    KALSHI_TICKER_TO_SPORT_KEY,
)

#: The production specimens, verbatim from `futures_markets.external_id` /
#: `.name` on 2026-09-12. Every one minted an id-less `basketball_other` event.
FANTASY_POINTS_SPECIMENS = [
    ("KXNFLFFPTS-26SEP13BUFHOU", "Buffalo vs Houston: Fantasy Points Leader"),
    ("KXNFLFFPTS-26SEP13CLEJAC", "Cleveland vs Jacksonville: Fantasy Points Leader"),
    ("KXNFLFFPTS-26SEP13GBMIN", "Green Bay vs Minnesota: Fantasy Points Leader"),
    ("KXNFLFFPTS-26SEP13NYJTEN", "New York J vs Tennessee: Fantasy Points Leader"),
    ("KXNFLFFPTS-26SEP13TBCIN", "Tampa Bay vs Cincinnati: Fantasy Points Leader"),
    ("KXNFLFFPTS-26SEP13ATLPIT", "Atlanta vs Pittsburgh: Fantasy Points Leader"),
]

#: Ticker token → the `sport_key` family every prefix carrying it must land in.
#: Deliberately the families whose tokens are unambiguous league names; a token
#: that names a SPORT rather than a league ("kxsoccer") is not in scope, because
#: several leagues legitimately share it.
LEAGUE_TOKEN_TO_SPORT_FAMILY = {
    "kxnfl": "americanfootball",
    "kxncaaf": "americanfootball",
    "kxnba": "basketball",
    "kxwnba": "basketball",
    "kxmlb": "baseball",
    "kxnhl": "icehockey",
}


@pytest.mark.parametrize("ticker,name", FANTASY_POINTS_SPECIMENS)
def test_a_fantasy_points_prop_is_football(ticker, name):
    """THE SHIP, asserted through the function ingest actually calls.

    Not through the maps: a test that reads `KALSHI_TICKER_TO_SPORT_KEY` and
    `SPORT_PREFIX_TO_LLM_CATEGORY` and composes them itself proves the two dicts
    compose, which was never in doubt — it would pass with step 1 of
    `_categorize_kalshi_market` deleted.
    """
    assert _categorize_kalshi_market(name, "Sports", ticker) == "football"


@pytest.mark.parametrize("ticker,name", FANTASY_POINTS_SPECIMENS)
def test_the_name_alone_still_gets_it_wrong(ticker, name):
    """The negative control, and the bug itself.

    With no ticker the name rules have only "Fantasy Points" to read, and they
    reach for basketball. This is what makes the case above meaningful: if the
    name could already classify these, the ticker would not be load-bearing and
    step 1 could regress with nothing failing.
    """
    assert _categorize_kalshi_market(name, "Sports", None) != "football"


@pytest.mark.parametrize("ticker,name", FANTASY_POINTS_SPECIMENS)
def test_a_mislabelled_nfl_prop_can_no_longer_mint_an_event(ticker, name):
    """The reader-visible half: no category, no invented fixture.

    `auto_create_sport_key_from_category` is the writer that turned this
    mislabelling into sixteen rows on a league page. Asserting on the composed
    pair rather than on the category alone is the point — the harm was never the
    word "basketball", it was the `basketball_other` event that word bought.
    """
    category = _categorize_kalshi_market(name, "Sports", ticker)
    assert category in LLM_CATEGORIES_THAT_MAY_NOT_CREATE_EVENTS
    assert auto_create_sport_key_from_category(category) is None


def test_the_name_alone_would_have_minted_one():
    """The same negative control, pointed at the writer.

    Without the ticker the specimen still buys an `_other` event — which is
    exactly the row a reader found on the basketball page. If this ever stops
    being true the test above has quietly become vacuous.
    """
    category = _categorize_kalshi_market(
        "Buffalo vs Houston: Fantasy Points Leader", "Sports", None
    )
    assert auto_create_sport_key_from_category(category) == "basketball_other"


def test_every_league_token_prefix_maps_to_its_own_sport():
    """THE GUARD. A prefix whose token names a league cannot map elsewhere.

    The ticker is the authority precisely because it is unambiguous: a prefix
    beginning `kxnfl` is American football whatever its suffix does. This sweeps
    both maps rather than listing the prefixes that exist today, so a new
    `kxnfl…`/`kxnba…` entry typed into the wrong sport trips here instead of
    reaching production as a wrong-sport page.
    """
    wrong = {}
    for source, mapping in (
        ("KALSHI_TICKER_TO_SPORT_KEY", KALSHI_TICKER_TO_SPORT_KEY),
        ("KALSHI_FUTURES_TICKER_TO_SPORT_KEY", KALSHI_FUTURES_TICKER_TO_SPORT_KEY),
    ):
        for prefix, sport_key in mapping.items():
            for token, family in LEAGUE_TOKEN_TO_SPORT_FAMILY.items():
                if prefix.startswith(token) and not sport_key.startswith(family):
                    wrong[f"{source}[{prefix}]"] = f"{sport_key} (expected {family}_*)"

    assert not wrong, (
        "A Kalshi ticker prefix naming a league maps to another sport. The "
        "ticker is step 1 of _categorize_kalshi_market and is documented there "
        "as authoritative, so a wrong value here is served, not guessed: "
        f"{wrong}"
    )


def test_the_fantasy_points_series_is_game_level():
    """It resolves per game, so Pass 1 may LINK it to the real fixture.

    The corollary of the mint refusal above: refusing to CREATE is only the
    right answer because the prop can still find the real NFL game once that
    game exists.
    """
    assert "kxnflffpts" in KALSHI_GAME_TICKER_PREFIXES


def test_the_head_to_head_win_total_series_is_futures_not_game_level():
    """`KXNFLH2HWINS` is season-long, so it must never acquire a game.

    All eleven live markets resolve 2027-02-01 and carry `event_id IS NULL`.
    Unmapped it scattered to `baseball_other` (9), `baseball_mlb` (1) and
    `soccer_other` (1); mapped into the GAME map instead it would become
    game-level and could attach a February season bet to a September fixture,
    which is the Q440 failure this file must not reintroduce.
    """
    assert "kxnflh2hwins" in KALSHI_FUTURES_TICKER_TO_SPORT_KEY
    assert "kxnflh2hwins" not in KALSHI_GAME_TICKER_PREFIXES
    assert "kxnflh2hwins" not in KALSHI_TICKER_TO_SPORT_KEY
