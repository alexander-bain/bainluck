"""Single-source guard for the Discover candidate pool specs (Queue 286).

Queue 285 extracted the nine user-independent candidate-pool queries into
``feed._compute_ordered_candidate_ids`` so the request path and the precompute
beat build a byte-identical candidate base. Its report noted — but did not
verify — that the admin trace ``feed._discover_candidate_pool_trace`` still kept
a *private copy* of the pool specs, "in sync because the pools moved verbatim".

The Queue 286 audit measured that copy and found it had ALREADY drifted:

    pool                        production   stale admin trace
    sports                      limit 80     limit 50
    nonsports_volume            limit 120    limit 180
    nonsports_movement          limit 100    limit 160  + ordered by the retired
                                                          correlated
                                                          max(abs(probability_change_24h))
                                                          subquery instead of the
                                                          denormalized
                                                          max_movement_24h column
                                                          (and missing its
                                                          > 0 predicate)
    nonsports_enriched          limit 100    limit 160
    nonsports_editorial_recall  limit 80     limit 120
    nonsports_timely            limit 80     limit 120

i.e. the "why is this market not a candidate?" trace was answering against pools
the feed no longer runs. Both callers now execute the one
``_discover_candidate_pool_specs`` list; these tests keep it that way.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timezone

from sqlalchemy.dialects import postgresql

import app.routes.feed as feed_mod


NOW = datetime(2026, 7, 30, 12, 0, 0, tzinfo=timezone.utc)

# The ordered pool contract. Names double as the ``futures.pool_*`` timing stages
# and the ``pool_counts`` provenance keys, so a rename is a breaking change to
# both the stage evidence and the base envelope.
EXPECTED_POOLS = [
    ("sports", 80),
    ("sports_postseason", 80),
    ("sports_editorial_recall", 80),
    ("nonsports_volume", 120),
    ("nonsports_movement", 100),
    ("nonsports_enriched", 100),
    ("nonsports_editorial_recall", 80),
    ("nonsports_timely", 80),
]


def _compiled(query) -> str:
    return str(
        query.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()


def test_pool_specs_order_names_and_limits_are_the_contract():
    _id_filters, specs = feed_mod._discover_candidate_pool_specs(NOW)
    assert [(name, limit) for name, _query, limit in specs] == EXPECTED_POOLS


def test_declared_limit_matches_the_query_limit():
    """A spec whose declared limit lies would mislabel the admin trace."""
    _id_filters, specs = feed_mod._discover_candidate_pool_specs(NOW)
    for name, query, limit in specs:
        assert f"limit {limit}" in _compiled(query), (
            f"pool {name!r} declares limit {limit} but its SQL disagrees"
        )


def test_admin_trace_and_production_builder_share_one_spec_source():
    """Neither caller may keep a private copy of the pool specs.

    This is the drift guard: the trace drifted precisely because it had its own
    ``pool_specs`` literal. Both must go through the shared function.
    """
    trace_src = inspect.getsource(feed_mod._discover_candidate_pool_trace)
    builder_src = inspect.getsource(feed_mod._compute_ordered_candidate_ids)

    for name, src in (("trace", trace_src), ("builder", builder_src)):
        assert "_discover_candidate_pool_specs(" in src, (
            f"{name} must build its pools from the shared spec source"
        )
        assert "select(FuturesMarket.id)" not in src, (
            f"{name} reintroduced a private candidate-pool query — the exact "
            "shape that let the admin trace drift from production"
        )
        assert "_external_curator_recall_market_ids(" in src, (
            f"{name} must run the external-curator recall lane"
        )
        assert "row_limit=_EXTERNAL_CURATOR_RECALL_POOL_LIMIT" in src, (
            f"{name} must pull the curator recall lane at the shared depth"
        )


def test_movement_pool_uses_denormalized_column_not_correlated_subquery():
    """The stale trace copy ordered by a correlated max(abs(...)) subquery.

    That is the pre-denormalization shape whose replacement cut the pool from
    ~9s to <100ms; it must not survive anywhere in the spec source.
    """
    _id_filters, specs = feed_mod._discover_candidate_pool_specs(NOW)
    movement = next(query for name, query, _ in specs if name == "nonsports_movement")
    compiled = _compiled(movement)

    assert "max_movement_24h" in compiled
    assert "max(abs(" not in compiled
    assert "probability_change_24h" not in compiled

    spec_src = inspect.getsource(feed_mod._discover_candidate_pool_specs)
    assert "correlate(" not in spec_src


def test_specs_are_user_independent():
    """Only (now, sport_filter, static_tag_filter) may shape the pools.

    User/session/limit/offset independence is what makes the candidate base
    shareable across response-cache keys (Queue 285); a new request-scoped
    parameter here would silently poison every page that reuses the base.
    """
    params = list(
        inspect.signature(feed_mod._discover_candidate_pool_specs).parameters
    )
    assert params == ["now", "sport_filter", "static_tag_filter"]


def test_sport_and_static_tag_filters_reach_every_pool():
    """Both keyed inputs must apply to all pools, or a keyed base would leak
    unfiltered candidates into a filtered request."""
    _id_filters, specs = feed_mod._discover_candidate_pool_specs(
        NOW, "basketball", ["nba"]
    )
    for name, query, _limit in specs:
        # JSONB literals cannot render with literal_binds, so inspect the
        # compiled SQL structurally plus its bound parameter values.
        compiled = query.compile(dialect=postgresql.dialect())
        sql = str(compiled).lower()
        bound = {str(value) for value in compiled.params.values()}

        assert "ilike" in sql, f"pool {name!r} dropped the sport filter"
        assert "%basketball%" in bound, f"pool {name!r} dropped the sport filter"
        assert "market_tags" in sql, f"pool {name!r} dropped the static tag filter"
        assert '["nba"]' in bound, f"pool {name!r} dropped the static tag filter"
