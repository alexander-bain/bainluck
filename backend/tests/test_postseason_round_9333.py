"""#9333 — the round-name resolver and its collation-safe ticker bound.

No database: these must run where the real-Postgres gate skips. The bound
rule matters because production's collation ignores punctuation — a range
ending in `-`/`.` matched ZERO rows there and every row on a C-collated
(macOS) test database, so only a static check sees it everywhere.
"""

from sqlalchemy.dialects import postgresql

from app.models.models import FuturesMarket
from app.routes.events import (
    _POSTSEASON_ROUND_ALIASES,
    _postseason_round_futures_arms,
    _resolve_postseason_round,
    _ticker_range,
)


def _bounds(prefix: str) -> tuple[str, str, str]:
    clause = _ticker_range(FuturesMarket.external_id, prefix)
    params = clause.compile(dialect=postgresql.dialect()).params
    return tuple(params.values())


def test_the_phrase_and_the_one_word_spelling_resolve():
    for terms in (["wild", "card"], ["Wild", "Card"], ["wildcard"], ["yankees", "wild", "card"]):
        rnd, consumed = _resolve_postseason_round(terms)
        assert rnd is not None and rnd[0] == "baseball_mlb", terms
        assert consumed <= {"wild", "card", "wildcard"}, consumed


def test_the_words_apart_are_not_the_round():
    for terms in (["wild"], ["card"], ["card", "wild"], ["minnesota", "wild"], ["cardinals"]):
        assert _resolve_postseason_round(terms) == (None, set()), terms
        assert _postseason_round_futures_arms(terms) == []


def test_every_ticker_range_is_bounded_on_an_alphanumeric_stem():
    prefixes = {p for rnd in _POSTSEASON_ROUND_ALIASES.values() for p in rnd[1:4]}
    assert prefixes, "the round map is empty"
    for prefix in prefixes:
        lower, upper, like = _bounds(prefix)
        assert lower[-1].isalnum() and upper[-1].isalnum(), (prefix, lower, upper)
        assert like == f"{prefix}%", like
        assert lower < upper and upper.startswith(lower[:-1]), (lower, upper)


def test_the_bound_for_a_hyphenated_prefix_drops_the_hyphen():
    """Strawman: the shape that returned zero rows on production."""
    lower, upper, like = _bounds("KXMLBSERIES-")
    assert (lower, upper) == ("KXMLBSERIES", "KXMLBSERIET")
    assert (lower, upper) != ("KXMLBSERIES-", "KXMLBSERIES.")
