"""#5116: the #755 moneyline re-null must not fire on a team-abbreviation collision.

The re-null clears `is_winner`/`resolution_source` on Kalshi markets the moneyline
resolver mis-graded as game-winners. It identifies them by a token list. Seven of
those tokens are two or three letters (`tb`, `ks`, `stl`, `ast`, `reb`, `hit`,
`f5`), and a Kalshi ticker is `SERIES-EVENT[-STRIKE]` whose EVENT segment
concatenates the two team abbreviations — so the tokens appeared by accident
across the team boundary in plain full-game markets and those rows lost a correct
verdict every cycle (672 outcomes measured on production 2026-09-11).

The defect class this file guards: *a predicate that means "which market family is
this" must read the family segment, not the whole ticker.*

The Python mirror below is faithful to the SQL, not a re-implementation of the
rule: `~*` is a case-insensitive `re.search`, and Postgres `split_part(x, '-', 1)`
is `x.split("-")[0]` including for a string with no dash. Both token lists are
imported from the module, so a change to either is seen here.
"""

import importlib
import re

import pytest

#: NOT `from app.tasks import backfill_winners` — `app/tasks/__init__.py` re-exports
#: the celery task of the same name, so that binds the FUNCTION and every read
#: below silently answers about a two-line wrapper instead of the module.
bw = importlib.import_module("app.tasks.backfill_winners")


#: Verbatim, the alternation that shipped before #5116 — the red arm. Every
#: FALSE_POSITIVE below matches this, which is what made the bug invisible.
_PRE_5116_WHOLE_ID_RE = (
    "(teamtotal|spread|pts|reb|ast|3pt|blk|stl|hrr|hit|tb|ks"
    "|1hwinner|2hwinner|1htotal|2htotal|1hspread|mention|rfi|f5)"
)

#: Production tickers, from the measured 672-row loss set. Every one is a
#: full-game market (`*GAME` moneyline, `*TOTAL`, `*BTTS`) whose verdict was
#: verified correct against the linked event's final score.
FALSE_POSITIVES = [
    ("KXMLBTOTAL-26APR171915DETBOS", "DE|TB|OS — Detroit + Boston"),
    ("KXNHLTOTAL-26FEB25TORTB", "TOR + TB (Tampa Bay)"),
    ("KXNCAAMBTOTAL-26FEB19CARKSTET", "CA|RKS|TET"),
    ("KXNBATOTAL-26FEB25SASTOR", "S|AST|OR"),
    ("KXBRASILEIROTOTAL-26FEB25CTBSPA", "C|TB|SPA"),
    ("KXMLSTOTAL-26MAR01SDSTL", "SD + STL"),
    ("KXEPLTOTAL-26FEB21BREBRI", "B|REB|RI — Brentford-Brighton hitting an NBA token"),
    ("KXMLBGAME-26MAR261615TBSTL", "moneyline: TB + STL"),
    ("KXMLSBTTS-26MAR01SDSTL", "both-teams-to-score: SD + STL"),
    ("KXAFLGAME-26MAR150015SKSMEL", "S|KS|MEL"),
]

#: Markets the re-null genuinely exists to catch — it must still reach all of them.
TRUE_POSITIVES = [
    ("KXNBAPTS-26FEB25SASTOR", "player points prop, family segment"),
    ("KXMLBTEAMTOTAL-26APR011315NYMSTL", "team total, family segment"),
    ("KXNBASPREAD-26FEB25SASTOR", "spread, family segment"),
    ("KXMLBF5-26APR011315NYMSTL", "first five innings, family segment"),
    ("KXMLBRFI-26APR011315NYMSTL", "run first inning, family segment"),
    ("KXNCAAMB1HSPREAD-26FEB19CARKSTET", "first-half spread, family segment"),
    ("KXNCAAMBSGP-26APR04ILLCONNSPREAD", "same-game parlay: leg type AFTER the dash"),
]


def _matches(ticker: str) -> bool:
    """The Python mirror of `_ML_REPAIR_NON_MONEYLINE_SQL`."""
    family_segment = ticker.split("-")[0]
    return bool(
        re.search(bw._ML_REPAIR_TOKENS_FREE, ticker, re.IGNORECASE)
        or re.search(bw._ML_REPAIR_TOKENS_ANCHORED, family_segment, re.IGNORECASE)
    )


def _tokens(alternation: str) -> set:
    return set(alternation.strip("()").split("|"))


@pytest.mark.parametrize("ticker,why", FALSE_POSITIVES, ids=[t for t, _ in FALSE_POSITIVES])
def test_team_abbreviation_collision_is_not_re_nulled(ticker, why):
    # Red arm: the shipped-before form matched every one of these. If this
    # assertion ever fails the specimen is wrong, not the fix.
    assert re.search(_PRE_5116_WHOLE_ID_RE, ticker, re.IGNORECASE), (
        f"{ticker} is not a specimen of the #5116 bug ({why}) — it never matched "
        "the pre-fix regex, so it proves nothing"
    )
    assert not _matches(ticker), f"{ticker} still re-nulled via {why}"


@pytest.mark.parametrize("ticker,why", TRUE_POSITIVES, ids=[t for t, _ in TRUE_POSITIVES])
def test_real_non_moneyline_families_are_still_re_nulled(ticker, why):
    assert _matches(ticker), f"{ticker} lost coverage ({why})"


def test_anchoring_never_narrows_the_token_list():
    """The union of the two lists is exactly the twenty tokens that shipped before.

    #5116 is an anchoring change. Dropping a token would silently stop repairing a
    real family, which looks identical to the fix working.
    """
    assert _tokens(bw._ML_REPAIR_TOKENS_ANCHORED).isdisjoint(
        _tokens(bw._ML_REPAIR_TOKENS_FREE)
    ), "a token in both lists makes the anchored arm dead"
    assert _tokens(bw._ML_REPAIR_TOKENS_ANCHORED) | _tokens(
        bw._ML_REPAIR_TOKENS_FREE
    ) == _tokens(_PRE_5116_WHOLE_ID_RE)


def test_short_tokens_are_the_anchored_ones():
    """Any token short enough to fall out of two team abbreviations must be anchored.

    Four characters is the bound: the shortest real collision measured was three
    (`TB`, `KS`, `REB`, `AST`), and team abbreviations run two to four letters, so
    a token of four or fewer characters can be produced by a boundary.
    """
    too_short_to_be_free = [
        t for t in _tokens(bw._ML_REPAIR_TOKENS_FREE) if len(t) <= 4
    ]
    assert not too_short_to_be_free, (
        f"{too_short_to_be_free} can be spelled by a team-abbreviation boundary and "
        "must be anchored to the family segment"
    )


def test_both_call_sites_use_the_shared_predicate():
    """The two UPDATEs were byte-identical duplicates and drifting apart is the
    way this bug comes back on one path only."""
    import inspect

    source = inspect.getsource(bw)
    # The banned SHAPE, not the banned tokens — the token list itself is still in
    # the module (it has to be), so a substring test on the tokens fires on the
    # fix. What must never come back is an inline alternation matched against the
    # whole `external_id`, which is what put a team boundary in scope.
    assert "external_id ~* '(" not in source, (
        "an unanchored whole-id token alternation is back in backfill_winners"
    )
    assert source.count("_ML_REPAIR_NON_MONEYLINE_SQL") >= 3, (
        "expected the constant plus both re-null call sites"
    )
    assert source.count("_ML_REPAIR_PARAMS") >= 3
