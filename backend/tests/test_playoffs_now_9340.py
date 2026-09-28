"""#9340: a bare `playoffs` puts the postseason in progress first — the pure halves.

The route-level proof (the twenty-row window, the refill, both screens) is
`tests/integration/test_search_playoffs_now_pg.py`. This file pins the gate:
which queries arm the key at all, and the Python partition's rule.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from app.routes.events import (
    _futures_postseason_now_order_key,
    _is_bare_postseason_query,
    _postseason_now_first,
    _rerank_search_futures,
)

NOW = datetime(2026, 9, 28, 10, 30, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "terms",
    [["playoffs"], ["Playoffs"], ["playoff"], ["postseason"], ["PLAYOFFS", "postseason"]],
)
def test_a_bare_postseason_word_arms_the_key(terms):
    assert _is_bare_postseason_query(terms)
    key = _futures_postseason_now_order_key(terms, NOW)
    assert key is not None
    sql = str(key.compile(dialect=postgresql.dialect()))
    assert "resolution_date" in sql and "llm_sport_category" in sql


@pytest.mark.parametrize(
    "terms",
    [[], ["mlb", "playoffs"], ["patriots", "playoffs"], ["stanley", "cup", "playoffs"],
     ["playoffs", "2027"], ["play"], ["wild", "card"]],
)
def test_anything_more_than_the_postseason_compiles_no_key(terms):
    """Byte-identical SQL for every other query: the key is None."""
    assert not _is_bare_postseason_query(terms)
    assert _futures_postseason_now_order_key(terms, NOW) is None


def _m(name, days, cat, volume=None):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        name=name, resolution_date=now + timedelta(days=days),
        llm_sport_category=cat, volume=volume,
    )


def test_the_partition_puts_in_progress_team_sport_rows_first_stably():
    valorant = _m("VALORANT … Playoffs?", 51, "esports", 536.0)
    bruins = _m("Bruins … 2027 Stanley Cup Playoffs?", 219, "hockey")
    r6 = _m("Rainbow Six … Playoffs", 1, "esports")
    alds = _m("MLB Playoffs: Team to advance to ALDS", 7, "baseball", 7118.0)
    opp = _m("Boston: First Playoff Opponent", 34, "baseball", 213.0)
    past = _m("Last week's playoff board", -1, "baseball")
    naive = SimpleNamespace(
        name="naive tz", resolution_date=(datetime.now(timezone.utc) + timedelta(days=3)).replace(tzinfo=None),
        llm_sport_category="basketball", volume=None,
    )
    rows = [valorant, bruins, r6, alds, past, opp, naive]
    assert _postseason_now_first(rows, ["playoffs"]) == [
        alds, opp, naive, valorant, bruins, r6, past,
    ]


def test_the_partition_is_a_no_op_for_any_other_query():
    rows = [_m("a", 219, "hockey"), _m("b", 7, "baseball")]
    assert _postseason_now_first(rows, ["mlb", "playoffs"]) == rows
    assert _postseason_now_first(rows, []) == rows


def test_the_reranker_applies_it_after_the_name_and_volume_sort():
    """Without the partition the VALORANT name match (536 volume) leads the
    Kalshi board whose name says `Playoff`, not `playoffs`."""
    valorant = _m("Will the VALORANT Champions 2026 champion go undefeated on maps in the Playoffs?", 51, "esports", 536.0)
    opp = _m("Boston: First Playoff Opponent", 34, "baseball", 213.0)
    for m in (valorant, opp):
        m.status = "open"
        m.outcomes = []
        m.market_tier = 1
        m.source = "polymarket"
        m.external_id = m.name
        m.group_id = None
        m.market_metadata = {}
    ranked = _rerank_search_futures([valorant, opp], [("playoffs", None)])
    assert ranked[0] is opp, [m.name for m in ranked]
