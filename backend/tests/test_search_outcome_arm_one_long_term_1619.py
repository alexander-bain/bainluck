"""#1619 — a multi-term outcome arm with ONE long term is the anchored subquery alone.

`_multi_term_outcome_match` (#9646) builds, for `f1 champion`:

    id = ANY(ARRAY(outcomes WHERE %champion% OR %winner%))                 -- (a)
    AND id = ANY(ARRAY(outcomes WHERE (%champion% OR %winner%) AND %f1%))  -- (b)

(b) needs ONE outcome matching the long term AND the short one, so it already
needs an outcome matching the long term: (a) is implied and costs a full trigram
scan plus an ARRAY of 31,531 market ids probed per row. Production row-path
2026-10-01, three interleaved pairs, same count: 894-1,389 ms with (a),
609-797 ms without, against the arm's 1,000 ms bound.

With TWO long terms the anchor ORs them, so it implies neither alone and each
keeps its own subquery — that is the half a careless "drop the long arms" would
break (`zelenskyy putin us` must still need both names somewhere).

The recall half on real Postgres is `tests/integration/test_search_recall_contract.py`
(#9646 rows); these guards need no server.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.models.models import FuturesMarket
from app.routes import events as events_route

SUBQUERY = "SELECT futures_outcomes.market_id"


def _sql(expanded) -> str:
    return str(
        select(FuturesMarket.id)
        .where(events_route._multi_term_outcome_match(expanded))
        .compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )


def _subqueries(sql: str) -> list[str]:
    parts = sql.split(SUBQUERY)[1:]
    return [p.split("))")[0] for p in parts]


def test_f1_champion_is_one_subquery_carrying_both_terms():
    subs = _subqueries(_sql([("f1", None), ("champion", "winner")]))
    assert len(subs) == 1, subs
    (only,) = subs
    # The anchor: long term (with its expansion) AND the short term, one outcome.
    assert "%%champion%%" in only and "%%winner%%" in only and "%%f1%%" in only, only


def test_two_long_terms_each_keep_their_own_subquery():
    subs = _subqueries(_sql([("us", None), ("zelenskyy", None), ("putin", None)]))
    assert len(subs) == 3, subs
    alone = [s for s in subs if "%%us%%" not in s]
    assert sorted("zelenskyy" in s for s in alone) == [False, True], alone
    assert sorted("putin" in s for s in alone) == [False, True], alone


def test_the_short_term_still_filters():
    """LAT-P006: `us recession` must not admit a board whose outcomes lack `us`."""
    subs = _subqueries(_sql([("us", None), ("recession", None)]))
    assert len(subs) == 1 and "%%us%%" in subs[0] and "%%recession%%" in subs[0], subs


def test_unmixed_queries_are_unchanged():
    # Every term long, every term short: one subquery per term, as before #1619.
    assert len(_subqueries(_sql([("zelenskyy", None), ("putin", None)]))) == 2
    assert len(_subqueries(_sql([("f1", None), ("us", None)]))) == 2
