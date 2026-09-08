"""#3559 — a darts match stops being filed as baseball.

## The ship

Kalshi's per-match series for darts, squash and chess name a market with two human
names and nothing else:

    KXDARTSMATCH-26SEP07SMINUI   "Jack Smith vs Jurgen Nuijten"

There is no sport word in that string, so the name rules cannot do better than
chance — and they don't. Measured on production 2026-09-07, across the five
name-only `*MATCH` series:

| series             | rows | correct | wrong |
|--------------------|------|---------|-------|
| KXDARTSMATCH       |  285 |     115 |   170 |
| KXSQUASHMATCH      |  170 |       0 |   170 |
| KXCHESSMATCH       |   13 |       0 |    13 |
| KXWRESTLINGMATCH   |    1 |       0 |     1 |
| KXPICKLEBALLMATCH  |    1 |       0 |     1 |

`KXSQUASHMATCH` was 145 `baseball` + 25 `football` — not one row in 170 said
squash. The ticker prefix has been unambiguous the whole time.

## Why the guard below is not hypothetical

`kxchess` has mapped to the `chess` sport key since #207, whose comment says in so
many words that KXCHESSMATCH "was LLM-mis-tagged baseball". That fix has been
INERT ever since, and `_categorize_kalshi_market` returned `'other'` for
KXCHESSMATCH on the commit before this one. Step 1 resolved the key to `chess`
and then fell straight through, because `chess` was missing from
`SPORT_PREFIX_TO_LLM_CATEGORY` and a miss there is silent — it just proceeds to
the name rules.

So the class is: **a sport key that step 1 can reach, with no category to hand
back.** `test_every_ticker_reachable_sport_key_has_a_category` is what makes the
next one loud instead of silent. It is the reason this file exists; the literal
cases below are the ship.

## Two series are deliberately NOT mapped

The same venue read (notice 26 — Kalshi's own `/series?category=Sports` listing,
not our mirror) reports `tags: ["MMA"]` for KXWRESTLINGMATCH and
`tags: ["Tennis"]` for KXPICKLEBALLMATCH. Mapping those is a product judgement
about whether a pickleball match belongs on our tennis surface, not the
deterministic lookup this change is, so they are left alone and
`test_the_two_venue_ambiguous_series_stay_unmapped` records that as a decision
rather than an oversight.

Expectations are written literally on purpose. Deriving them from
`KALSHI_FUTURES_TICKER_TO_SPORT_KEY` would make this file agree with the maps by
construction and assert nothing (the #3446 precedent says the same).
"""

import pytest

from app.tasks.kalshi import _categorize_kalshi_market
from app.utils.sport_keys import (
    KALSHI_FUTURES_TICKER_TO_SPORT_KEY,
    KALSHI_TICKER_TO_SPORT_KEY,
    SPORT_PREFIX_TO_LLM_CATEGORY,
    get_sport_key_from_ticker,
)

# (ticker, market name as Kalshi writes it, the category a reader would expect).
# Real tickers and real player pairings from the measured population.
NAME_ONLY_MATCHES = [
    ("KXDARTSMATCH-26SEP07SMINUI", "Jack Smith vs Jurgen Nuijten", "darts"),
    ("KXDARTSMATCH-26SEP07HUMGER", "Luke Humphries vs Michael van Gerwen", "darts"),
    ("KXSQUASHMATCH-26SEP07ASAFAR", "Mostafa Asal vs Ali Farag", "squash"),
    ("KXCHESSMATCH-26SEP07FIRGUK", "Firouzja vs Gukesh", "chess"),
    ("KXCHESSMATCH-26SEP07CARNAK", "Magnus Carlsen vs Hikaru Nakamura", "chess"),
]


@pytest.mark.parametrize("ticker,name,expected", NAME_ONLY_MATCHES)
def test_a_name_only_match_is_classified_by_its_ticker(ticker, name, expected):
    """The ship, asserted through the function the ingest actually calls.

    Not through the maps: a test that reads `KALSHI_FUTURES_TICKER_TO_SPORT_KEY`
    and `SPORT_PREFIX_TO_LLM_CATEGORY` and composes them itself proves the two
    dicts compose, which was never in doubt. It would pass with step 1 of
    `_categorize_kalshi_market` deleted.
    """
    assert _categorize_kalshi_market(name, "Sports", ticker) == expected


@pytest.mark.parametrize("ticker,name,expected", NAME_ONLY_MATCHES)
def test_the_name_alone_cannot_reach_that_answer(ticker, name, expected):
    """The negative control: with no ticker, the name genuinely has nothing to read.

    This is what makes the parametrised case above meaningful. If the name rules
    could already classify "Firouzja vs Gukesh", the ticker would not be
    load-bearing and step 1 could regress without any test noticing.
    """
    assert _categorize_kalshi_market(name, "Sports", None) != expected


def test_every_ticker_reachable_sport_key_has_a_category():
    """THE GUARD. A key step 1 can reach must have a category to hand back.

    `_categorize_kalshi_market` calls this "AUTHORITATIVE — ticker never lies",
    but the authority is conditional on a hand-maintained dict: miss it and the
    market silently drops through to the name rules. #207 shipped `kxchess` into
    the ticker map and stopped one line short of the category map, and nothing
    failed for it.

    Anyone adding a ticker prefix for a new sport trips this instead.
    """
    uncovered = {}
    for source, mapping in (
        ("KALSHI_TICKER_TO_SPORT_KEY", KALSHI_TICKER_TO_SPORT_KEY),
        ("KALSHI_FUTURES_TICKER_TO_SPORT_KEY", KALSHI_FUTURES_TICKER_TO_SPORT_KEY),
    ):
        for ticker_prefix, sport_key in mapping.items():
            prefix = sport_key.split("_")[0]
            if prefix not in SPORT_PREFIX_TO_LLM_CATEGORY:
                uncovered.setdefault(prefix, []).append(f"{source}:{ticker_prefix}")

    assert not uncovered, (
        "These sport keys are reachable from a Kalshi ticker but have no entry in "
        "SPORT_PREFIX_TO_LLM_CATEGORY, so step 1 of _categorize_kalshi_market "
        "resolves them and then silently falls through to the name rules — the "
        "#3559 / #207 failure. Add the prefix to SPORT_PREFIX_TO_LLM_CATEGORY: "
        f"{uncovered}"
    )


def test_the_two_venue_ambiguous_series_stay_unmapped():
    """A decision, recorded — not an oversight.

    Kalshi tags KXWRESTLINGMATCH `MMA` and KXPICKLEBALLMATCH `Tennis`. Following
    the venue would put a pickleball match on our tennis surface, which is a
    product call and not this change's to make. Two rows between them, both
    resolved, so nothing is waiting on it.

    If a later lane maps them deliberately, it edits this test and the docstring
    tells it which question it is answering.
    """
    for ticker in ("KXWRESTLINGMATCH-26SEP07ABC", "KXPICKLEBALLMATCH-26SEP07ABC"):
        assert get_sport_key_from_ticker(ticker) is None


def test_the_families_that_already_worked_still_do():
    """Blast radius. Two new futures prefixes must not move anything else.

    `KXNFLDRAFT` is here for the `\\bdarts?\\b` trap that
    `futures_categorization` carries a war story about: "Will Jaxson Dart be the
    first overall pick?" must stay football, not become darts.
    """
    unchanged = [
        ("KXMLBGAME-26SEP07NYYBOS", "Will the Yankees win?", "baseball"),
        ("KXATPMATCH-26SEP07ZVEDAR", "Zverev vs Darderi", "tennis"),
        ("KXEFLCUPBTTS-26X", "Ajax vs Sion: Regulation Time BTTS", "soccer"),
        ("KXNFLDRAFT-26X", "Will Jaxson Dart be the first overall pick?", "football"),
        ("KXCHESSTOURNAMENT-26EWC", "Chess Tournament Winner", "chess"),
    ]
    for ticker, name, expected in unchanged:
        assert _categorize_kalshi_market(name, "Sports", ticker) == expected


def test_the_new_prefixes_are_futures_not_game_level():
    """Darts and squash have no events table, so they must never become a
    matcher sport key — the same reason #207 put chess in the futures map.

    Measured before the change: no game prefix collides with `kxdarts` or
    `kxsquash`, and both tickers read `is_kalshi_game_level_ticker() is False`.
    """
    from app.utils.sport_keys import is_kalshi_game_level_ticker

    for ticker in ("KXDARTSMATCH-26SEP07SMINUI", "KXSQUASHMATCH-26SEP07ASAFAR"):
        assert is_kalshi_game_level_ticker(ticker) is False
