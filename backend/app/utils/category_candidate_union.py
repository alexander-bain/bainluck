"""Single-CTE candidate-pool union for category-filtered Discover feeds (#11931).

When ``category_filter`` is set (e.g. ``/api/feed?category=politics``), running
the active candidate pools as 5 separate queries lets PostgreSQL walk the
global ``ix_fm_feed_open_volume``, ``ix_fm_feed_open_enriched``, and
``ix_fm_feed_open_timely`` indexes across all ~55,000 open markets five times
(measured ``2,205 ms`` on ``politics``).

Because every pool shares the exact same ``id_filters`` — including
``status = 'open'``, ``event_id IS NULL``, and ``llm_sport_category = :cat`` —
all active pools can read from ONE ``MATERIALIZED`` CTE over
``ix_fm_feed_open_sports`` (``(llm_sport_category, market_tier, resolution_date)
WHERE status = 'open' AND event_id IS NULL``) in a single round trip.

Single-source contract: every arm's extra ``WHERE`` criteria, ``ORDER BY``, and
``LIMIT`` are derived directly from the ``pool_specs`` returned by
``feed._discover_candidate_pool_specs`` via ``visitors.replacement_traverse``,
so pool definitions can never drift between Discover, category browse, and the
admin pool trace.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import Column, Integer, Select, func, literal, select, union_all
from sqlalchemy.sql import visitors

from app.models.models import FuturesMarket


def build_category_candidate_union_query(
    id_filters: Sequence[Any],
    active_pool_specs: Sequence[tuple[str, Select, int]],
) -> Select | None:
    """Fuse ``active_pool_specs`` into one ``MATERIALIZED``-CTE ``UNION ALL``.

    Returns a ``Select`` yielding ``(pool_idx, market_id)`` ordered by
    ``(pool_idx, rn)``, or ``None`` if ``active_pool_specs`` is empty or any
    pool spec cannot be safely rebound onto the ``cat_base`` CTE.
    """
    if not active_pool_specs:
        return None

    fm_table = FuturesMarket.__table__
    n_base = len(id_filters)
    needed_cols: set[str] = {"id"}

    for _name, query, _limit in active_pool_specs:
        where_criteria = tuple(getattr(query, "_where_criteria", ()))
        if len(where_criteria) < n_base:
            return None
        extra_where = where_criteria[n_base:]
        order_by = tuple(getattr(query, "_order_by_clauses", ()))
        for clause in (*extra_where, *order_by):
            for elem in visitors.iterate(clause):
                if isinstance(elem, Column):
                    if elem.table is not fm_table:
                        # Pool references another table — fall back to per-pool execution.
                        return None
                    needed_cols.add(elem.name)

    cat_base = (
        select(*(fm_table.c[col] for col in sorted(needed_cols)))
        .where(*id_filters)
        .cte("cat_base")
        .prefix_with("MATERIALIZED", dialect="postgresql")
    )

    def _rebind(expr: Any) -> Any:
        def _replace(elem: Any) -> Any:
            if isinstance(elem, Column) and elem.table is fm_table:
                return cat_base.c[elem.name]
            return None

        return visitors.replacement_traverse(expr, {}, _replace)

    arms: list[Select] = []
    for pool_idx, (_name, query, limit) in enumerate(active_pool_specs):
        extra_where = [_rebind(c) for c in query._where_criteria[n_base:]]
        order_by = [_rebind(c) for c in query._order_by_clauses]
        rn_expr = (
            func.row_number().over(order_by=order_by)
            if order_by
            else func.row_number().over()
        )
        arm_sub = (
            select(
                literal(pool_idx, Integer).label("pool_idx"),
                rn_expr.label("rn"),
                cat_base.c.id.label("id"),
            )
            .select_from(cat_base)
            .where(*extra_where)
            .order_by(*order_by)
            .limit(limit)
            .subquery(f"cat_pool_{pool_idx}")
        )
        arms.append(select(arm_sub.c.pool_idx, arm_sub.c.rn, arm_sub.c.id))

    if len(arms) == 1:
        combined = arms[0].subquery("cat_all_pools")
    else:
        combined = union_all(*arms).subquery("cat_all_pools")

    return select(combined.c.pool_idx, combined.c.id).order_by(
        combined.c.pool_idx, combined.c.rn
    )
