"""#9333 dropdown half — the round's series markets lead a round-name query.

No database. Production 2026-09-28 (`7cb0bae4`): the dropdown for `wild card`
led with "Curitiba: Thiago Seyboth Wild vs Pedro Boscardin Dias" and "Wildcard
Gaming vs. M80", whose names hold both typed words, above "Series Winner:
Boston vs New York Y", whose name holds neither.
"""

from types import SimpleNamespace

from app.routes.events import (
    _futures_postseason_round_order_key,
    _postseason_round_series_first,
    _rerank_search_futures,
)


def _m(name, source, ext, volume=0):
    return SimpleNamespace(
        name=name, source=source, external_id=ext, volume=volume, volume_24h=0,
        outcomes=[], resolution_date=None, llm_sport_category=None, sport_id=None,
        status="open", market_tier=1, id=hash(ext),
    )


SEYBOTH = _m("Curitiba: Thiago Seyboth Wild vs Pedro Boscardin Dias", "polymarket", "pm-1", 90_000)
WILDCARD_GAMING = _m("Wildcard Gaming vs. M80", "polymarket", "pm-2", 40_000)
SERIES = _m("Series Winner: Boston vs New York Y", "kalshi", "KXMLBSERIES-26BOSNYYWC", 500)
SERIES_GAMES = _m("Series Total Games: Boston vs New York Y", "kalshi", "KXMLBSERIESGAMES-26BOSNYYWC", 100)
# Same family, no round code: a regular-season series is not the round.
OTHER_SERIES = _m("Series Winner: Detroit vs Seattle", "kalshi", "KXMLBSERIES-25DETSEA", 900)


def test_the_round_series_move_ahead_in_their_own_order():
    markets = [SEYBOTH, WILDCARD_GAMING, OTHER_SERIES, SERIES, SERIES_GAMES]
    out = _postseason_round_series_first(markets, ["wild", "card"])
    assert out == [SERIES, SERIES_GAMES, SEYBOTH, WILDCARD_GAMING, OTHER_SERIES]


def test_a_query_without_a_round_is_untouched():
    markets = [SEYBOTH, SERIES, WILDCARD_GAMING]
    for terms in (
        ["wild"], ["card"], ["boston"], [],
        # The round word beside something else the reader named.
        ["wildcard", "gaming"], ["yankees", "wild", "card"],
    ):
        assert _postseason_round_series_first(markets, terms) is markets, terms
        assert _futures_postseason_round_order_key(terms) is None, terms


def test_the_sql_key_exists_only_for_a_round():
    assert _futures_postseason_round_order_key(["wild", "card"]) is not None
    assert _futures_postseason_round_order_key(["wildcard"]) is not None
    assert _futures_postseason_round_order_key(["mlb", "wild", "card"]) is not None


def test_the_reranker_ends_with_the_series_first():
    """The name/volume sort puts the collisions first; the partition must win."""
    out = _rerank_search_futures(
        [SERIES, SEYBOTH, WILDCARD_GAMING, SERIES_GAMES],
        [("wild", None), ("card", None)],
    )
    assert out[:2] == [SERIES, SERIES_GAMES], [m.name for m in out]
