"""Guards for the ``/categories/<slug>`` browse filter (Q467).

**The defect.** Every one of the 48 category tiles on ``/categories`` quotes a
count, and 29 of the 48 pages behind them rendered "No … items right now".
Measured on production 2026-08-31: **20,492 of 46,181 counted items were
unreachable**, ``table_tennis`` — the largest category on the site at 13,433 —
among them. Two independent causes, and fixing either alone leaves the biggest
page empty:

1. **The tag vocabulary is a fixed allowlist the classifier outgrew.** The tile
   counts come from ``llm_sport_category`` verbatim (48 distinct values), but
   ``compute_market_tags`` emits ``sport:<x>`` only when ``x`` is one of the 22
   values in ``ALLOWED_TAGS["sport"]``. So 26 categories carry NO sport tag at
   all and ``tags=["sport:table_tennis"]`` matched nothing that existed —
   13,510 rows, 0 tagged.
2. **The page reused Discover's curated pool, which excludes game lines.** The
   ``% vs %`` predicate keeps head-to-head matchups out of *Discover*. On a
   *browse* surface the matchups ARE the content: 13,431 of 13,431 open
   table-tennis markets are ``% vs %`` named, and 757 of 758 cricket — which is
   exactly why ``/categories/cricket`` served precisely one card.

The fix is a ``category`` filter that matches ``llm_sport_category`` exactly and
keeps the matchups. It must not be confused with ``sport``, which is a substring
``ILIKE``: ``sport=tennis`` also selects ``table_tennis``, which was harmless
only while the matchup exclusion hid every table-tennis row anyway.

Every test naming Discover below is a **must-not-regress control** — it passes
on both trees, and its job is to prove the browse filter bought its recall
without moving the flagship feed.
"""

from __future__ import annotations

import hashlib
import inspect
from datetime import datetime, timezone

from sqlalchemy.dialects import postgresql

import app.routes.feed as feed_mod
from app.utils.feed_cache import (
    FEED_PAGE_BASE_CACHE_PREFIX,
    FEED_RESPONSE_CACHE_PREFIX,
    feed_page_base_cache_key,
    feed_response_cache_key,
)


NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)

# The two literal predicates that make Discover a curated feed rather than a
# listing. Spelled here so a rename in the route cannot quietly pass these.
# The ``%%`` is not a typo: ``literal_binds`` escapes ``%`` for the DBAPI
# paramstyle, so the compiled SQL reads ``not like '%% vs %%'``. Asserting the
# single-``%`` form would make every one of these tests vacuously green.
MATCHUP_EXCLUSIONS = ("not like '%% vs %%'", "not like '%% vs. %%'")


def _compiled(query) -> str:
    return str(
        query.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()


def _pool(specs, name: str):
    return next(query for pool_name, query, _ in specs if pool_name == name)


# ── The browse filter ────────────────────────────────────────────────────────


def test_category_browse_matches_the_category_exactly_not_as_a_substring():
    """``category=tennis`` must not drag in ``table_tennis``.

    ``sport`` is an ``ILIKE '%…%'``. Reusing it for browse would put table
    tennis on the tennis page the moment the matchup exclusion stopped hiding
    it — i.e. the moment the rest of this fix landed.
    """
    _id_filters, specs = feed_mod._discover_candidate_pool_specs(
        NOW, None, None, "tennis"
    )
    compiled = _compiled(_pool(specs, "nonsports_volume"))

    assert "llm_sport_category = 'tennis'" in compiled
    assert "llm_sport_category ilike '%%tennis%%'" not in compiled


def test_category_browse_keeps_head_to_head_matchup_markets():
    """The whole of table tennis and all but one cricket market are ``% vs %``."""
    _id_filters, specs = feed_mod._discover_candidate_pool_specs(
        NOW, None, None, "table_tennis"
    )
    for pool_name, query, _limit in specs:
        compiled = _compiled(query)
        for exclusion in MATCHUP_EXCLUSIONS:
            assert exclusion not in compiled, (
                f"pool {pool_name!r} still excludes matchups under a category "
                "browse — table_tennis is 13,431/13,431 matchup-named, so this "
                "is the empty page"
            )


def test_every_pool_carries_the_category_filter():
    """A pool that forgets it would leak another category onto the page."""
    _id_filters, specs = feed_mod._discover_candidate_pool_specs(
        NOW, None, None, "economics"
    )
    for pool_name, query, _limit in specs:
        assert "llm_sport_category = 'economics'" in _compiled(query), (
            f"pool {pool_name!r} is unfiltered under a category browse"
        )


# ── Discover controls: these must pass on BOTH trees ─────────────────────────


def test_discover_still_excludes_matchups_when_no_category_is_given():
    """CONTROL. Discover is a curated feed; game lines stay out of it."""
    _id_filters, specs = feed_mod._discover_candidate_pool_specs(NOW)
    for pool_name, query, _limit in specs:
        compiled = _compiled(query)
        for exclusion in MATCHUP_EXCLUSIONS:
            assert exclusion in compiled, (
                f"pool {pool_name!r} stopped excluding matchups on the "
                "UNFILTERED Discover path — the browse fix leaked"
            )


def test_discover_pool_sql_is_byte_identical_without_a_category():
    """CONTROL. The strongest form: same SQL, character for character."""
    _before, specs = feed_mod._discover_candidate_pool_specs(NOW, None, None)
    _after, specs_explicit_none = feed_mod._discover_candidate_pool_specs(
        NOW, None, None, None
    )
    assert [_compiled(q) for _n, q, _l in specs] == [
        _compiled(q) for _n, q, _l in specs_explicit_none
    ]


def test_sport_filter_is_still_a_substring_match():
    """CONTROL. ``sport`` keeps its old loose semantics; browse got a new param
    rather than a redefinition of an existing one."""
    _id_filters, specs = feed_mod._discover_candidate_pool_specs(NOW, "tennis")
    compiled = _compiled(_pool(specs, "sports"))
    assert "llm_sport_category ilike '%%tennis%%'" in compiled


# ── The candidate base must never be shared with a category browse ───────────


def test_category_browse_never_reads_or_publishes_the_shared_candidate_base():
    """The base identity is ``(sport_filter, static_tag_filter)`` — no category
    segment. Reading it would serve Discover's candidates to a category page;
    publishing under it would serve one category's candidates to Discover.
    """
    src = inspect.getsource(feed_mod._score_futures)
    assert "if category_filter:" in src, (
        "_score_futures must branch on category_filter before touching the "
        "shared candidate base"
    )
    # The base identity function still takes only the two shareable inputs.
    from app.utils import candidate_base as cb

    params = list(inspect.signature(cb.base_identity).parameters)
    assert params == ["sport_filter", "static_tag_filter"], (
        "base_identity grew an input; if a category can now key the shared "
        "base, this guard and the bypass in _score_futures must be revisited"
    )


# ── Cache keys ───────────────────────────────────────────────────────────────


def test_two_categories_get_two_response_cache_keys():
    a = feed_response_cache_key(limit=50, offset=0, category="tennis")
    b = feed_response_cache_key(limit=50, offset=0, category="table_tennis")
    none = feed_response_cache_key(limit=50, offset=0)
    assert a != b != none and a != none


def test_two_categories_get_two_page_base_cache_keys():
    """The page-base key is offset-independent, so omitting the category here
    would serve page 2 of another category's list."""
    a = feed_page_base_cache_key(limit=50, category="tennis")
    b = feed_page_base_cache_key(limit=50, category="table_tennis")
    none = feed_page_base_cache_key(limit=50)
    assert a != b != none and a != none


def test_a_request_without_a_category_hashes_the_legacy_string_unchanged():
    """Shipping this must not cold-start the whole feed response cache.

    The literals below are the pre-existing key strings; the category segment is
    PREPENDED so a no-category request hashes exactly what it always did.
    """
    legacy_response = "feed:anon:all:20:0:True:True:::False:discover"
    assert feed_response_cache_key(limit=20, offset=0) == (
        f"{FEED_RESPONSE_CACHE_PREFIX}:"
        f"{hashlib.md5(legacy_response.encode()).hexdigest()}"
    )

    legacy_page_base = "pagebase:all:20:True:True:::False:discover"
    assert feed_page_base_cache_key(limit=20) == (
        f"{FEED_PAGE_BASE_CACHE_PREFIX}:"
        f"{hashlib.md5(legacy_page_base.encode()).hexdigest()}"
    )


def test_category_cache_segment_is_length_delimited():
    """A bare ``cat:<value>|`` separator is forgeable; this is the forgery.

    ``sport`` is a free-form string that lands in the key, so the boundary
    between the category and the rest of the shape can be moved across the
    separator. These two DIFFERENT requests concatenate to the identical
    ``cat:a|feed:anon:b|feed:anon:c:50:0:…`` under a bare separator and would
    therefore share one cache entry — each serving the other's feed:

        A: category="a",              sport="b|feed:anon:c"
        B: category="a|feed:anon:b",  sport="c"

    The explicit length (``cat=1:`` vs ``cat=13:``) is what keeps them apart.
    An earlier version of this test compared two requests that also differed in
    `parts`, so it passed under the bare form too — vacuously. It was caught by
    a mutant that removed the delimiter and survived.
    """
    a = feed_response_cache_key(limit=50, offset=0, category="a", sport="b|feed:anon:c")
    b = feed_response_cache_key(limit=50, offset=0, category="a|feed:anon:b", sport="c")
    assert a != b

    a_pb = feed_page_base_cache_key(limit=50, category="a", sport="b|pagebase:c")
    b_pb = feed_page_base_cache_key(limit=50, category="a|pagebase:b", sport="c")
    assert a_pb != b_pb


# ── Route wiring ─────────────────────────────────────────────────────────────


def test_category_is_refused_rather_than_silently_ignored():
    """Two ways `category` could answer wrongly with a 200, both refused.

    `mode=sports` takes a different futures path that has no category filter,
    so honouring the request would serve the whole sports feed under one
    category's heading. And the category is a cache-key input, so an unbounded
    one is unbounded key cardinality on a Redis shared with the Celery broker.
    """
    src = inspect.getsource(feed_mod.get_feed)
    assert 'detail="category is not supported with mode=sports"' in src
    assert "len(category) > _cb_limits.MAX_TAG_LENGTH" in src

    # Both refusals must precede the cache read, or a refused request still
    # mints an entry.
    guard_at = src.index("if category is not None:")
    cache_at = src.index('_cache_status = "miss"')
    assert guard_at < cache_at, (
        "the category guards must run BEFORE the response-cache block"
    )


def test_get_feed_declares_category_and_threads_it_everywhere():
    params = inspect.signature(feed_mod.get_feed).parameters
    assert "category" in params, "GET /api/feed must accept ?category="

    src = inspect.getsource(feed_mod.get_feed)
    assert "category=category," in src, (
        "category must reach the response-cache shape; omitting it serves one "
        "category's page to another"
    )
    assert "category_filter=category," in src, (
        "category must reach _score_futures"
    )
    assert "sport or category," in src, (
        "the events half must narrow too, or /categories/table-tennis lists "
        "every live game on the site"
    )
