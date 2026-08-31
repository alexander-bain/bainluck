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
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
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


# ── The adjacent tiers: golf and event concepts (Q472 / CERT-542) ────────────
#
# CERT-542 blocked the ship above, and it was right. The exact category filter
# reached every futures pool and both cache keys — and the SAME request still
# invoked the golf tier with `sport=None` and the concept tier with
# `sport_filter=None`, then appended both DIRECTLY to `feed_items`. Nothing
# downstream filters by category, so `/categories/economics` served golf
# tournaments and UFC cards under an economics heading. The ship replaced empty
# category pages with pages whose heading no longer described their content.
#
# Reproduced through the real route before fixing: `category=economics` carried
# BOTH stubs below.
#
# These are ENDPOINT guards, not source guards. Every one drives a real HTTP
# request through the ASGI app, and every one is paired with a control that
# proves the stub CAN reach the response — an absence assertion whose stub was
# never reachable is the vacuous guard this board has paid for repeatedly.


@pytest.fixture(autouse=True)
def _clean_shared_concept_cache():
    """The concept artifact cache is process-global.

    A leaked entry produces the most misleading failure available here: an
    absence that holds because a previous test warmed something, or a control
    that passes on a neighbour's artifact instead of its own build."""
    from app.utils.principal_independent_cache import clear_shared_builds

    clear_shared_builds()
    yield
    clear_shared_builds()


GOLF_STUB_NAME = "Q472 PROBE GOLF TOURNAMENT"
CONCEPT_STUB_NAME = "Q472 PROBE UFC CARD"


def _golf_stub() -> dict:
    """One golf card, shaped as `_score_golf_tournaments` emits and scored high
    enough that no ranking cap can be mistaken for the filter."""
    return {
        "type": "tournament",
        "id": "q472-probe-golf",
        "name": GOLF_STUB_NAME,
        "score": 999.0,
        "sport_category": "golf",
    }


def _concept_stub() -> dict:
    return {
        "type": "event_concept",
        "id": "q472-probe-concept",
        "name": CONCEPT_STUB_NAME,
        "score": 998.0,
        "sport_category": "mma",
    }


@pytest.fixture
def adjacent_tier_probe(monkeypatch):
    """Stub the two adjacent tiers non-empty and record the filter each is
    handed. Both halves matter: the NAMES prove what reached the user, and the
    recorded filters prove which tier ran at all."""
    calls: dict[str, list] = {"golf": [], "concepts": []}

    async def _golf(db, now, sport_filter, ctx=None, stages=None, provenance_sink=None):
        calls["golf"].append(sport_filter)
        return [_golf_stub()]

    async def _concepts(db, now, sport_filter, ctx=None):
        calls["concepts"].append(sport_filter)
        return [_concept_stub()]

    async def _no_events(*a, **kw):
        return []

    monkeypatch.setattr(feed_mod, "_score_golf_tournaments", _golf)
    monkeypatch.setattr(feed_mod, "_score_event_concepts", _concepts)
    monkeypatch.setattr(feed_mod, "_score_events", _no_events)
    return calls


@pytest.fixture
async def feed_client(monkeypatch):
    """A feed client over a mocked DB, so the route can be driven end to end
    without Postgres."""
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")

    from app.main import app
    from app.dependencies.auth import get_optional_user
    from app.services.database import get_db, get_db_rw

    session = AsyncMock()

    def _empty_result():
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        result.scalars.return_value.first.return_value = None
        result.scalar_one_or_none.return_value = None
        result.scalar.return_value = None
        result.fetchall.return_value = []
        result.all.return_value = []
        result.first.return_value = None
        return result

    session.execute.return_value = _empty_result()

    async def _mock_get_db():
        yield session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user

    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac

    app.dependency_overrides.clear()


async def _feed_names(client, **params) -> list[str]:
    resp = await client.get(
        "/api/feed",
        params={"include_futures": "false", **params},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body["items"] if isinstance(body, dict) else body
    return [i.get("name") for i in items if isinstance(i, dict)]


@pytest.mark.asyncio
async def test_an_unrelated_category_page_serves_no_golf_tournament(
    feed_client, adjacent_tier_probe
):
    """CERT-542's finding, on the tier it named first."""
    names = await _feed_names(feed_client, category="economics")
    assert GOLF_STUB_NAME not in names, (
        "the golf tier reached an economics page — CERT-542's exact defect: "
        f"{names}"
    )


@pytest.mark.asyncio
async def test_an_unrelated_category_page_serves_no_event_concept(
    feed_client, adjacent_tier_probe
):
    """CERT-542's finding, on the second tier. Separate from the golf test on
    purpose: one gate fixed and the other left is the half-repair this program
    has shipped before."""
    names = await _feed_names(feed_client, category="economics")
    assert CONCEPT_STUB_NAME not in names, (
        f"the concept tier reached an economics page: {names}"
    )


@pytest.mark.asyncio
async def test_an_unrelated_category_page_does_not_even_run_the_two_tiers(
    feed_client, adjacent_tier_probe
):
    """Skipped, not built-and-discarded.

    Filtering the output would also satisfy the two tests above while still
    paying for a golf base read and a ~1s concept build on every category page.
    The gate is the fix; this is what says so."""
    await _feed_names(feed_client, category="economics")
    assert adjacent_tier_probe["golf"] == [], (
        f"golf tier ran on an economics page with filter {adjacent_tier_probe['golf']}"
    )
    assert adjacent_tier_probe["concepts"] == [], (
        "concept tier ran on an economics page with filter "
        f"{adjacent_tier_probe['concepts']}"
    )


@pytest.mark.asyncio
async def test_the_stubs_do_reach_discover__so_the_absences_above_are_real(
    feed_client, adjacent_tier_probe
):
    """THE CONTROL FOR ALL THREE ABSENCES.

    Without it every test above is satisfied by a route that returns nothing at
    all, and the suite would stay green through a total feed outage. A request
    with no category must carry BOTH stubs and hand BOTH tiers no filter —
    Discover is exactly unchanged."""
    names = await _feed_names(feed_client)
    assert GOLF_STUB_NAME in names, f"golf stub unreachable even on Discover: {names}"
    assert CONCEPT_STUB_NAME in names, f"concept stub unreachable: {names}"
    assert adjacent_tier_probe["golf"] == [None]
    assert adjacent_tier_probe["concepts"] == [None]


@pytest.mark.asyncio
async def test_the_golf_category_page_still_gets_its_tournaments(
    feed_client, adjacent_tier_probe
):
    """The other direction, and the one a too-wide gate breaks.

    Skipping golf whenever a category is present would pass every absence test
    above and empty `/categories/golf` — which is the defect this whole queue
    exists to fix, reintroduced on one page."""
    names = await _feed_names(feed_client, category="golf")
    assert GOLF_STUB_NAME in names, f"/categories/golf lost its tournaments: {names}"
    assert CONCEPT_STUB_NAME not in names, (
        f"concepts leaked onto the golf page: {names}"
    )
    assert adjacent_tier_probe["golf"] == ["golf"], (
        "the golf tier must be handed the category, so its own refusal agrees "
        f"with the route gate: {adjacent_tier_probe['golf']}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("category", ["mma", "motorsports", "cycling"])
async def test_a_concept_category_page_gets_exactly_its_own_source(
    feed_client, adjacent_tier_probe, category
):
    """Each of the three live concept categories, by name.

    `cycling` is parametrized deliberately: it is the alias the hand-written
    copy of this vocabulary in `feed.py` had already lost once (UX-P177), and a
    test naming only `mma` would not have noticed."""
    names = await _feed_names(feed_client, category=category)
    assert CONCEPT_STUB_NAME in names, f"/categories/{category} lost concepts: {names}"
    assert GOLF_STUB_NAME not in names, f"golf leaked onto /categories/{category}"
    assert adjacent_tier_probe["concepts"] == [(category,)], (
        "the concept tier must be narrowed to this category's own source, not "
        f"merely run: {adjacent_tier_probe['concepts']}"
    )


@pytest.mark.asyncio
async def test_the_tag_derived_filter_still_reaches_the_builder_through_the_route(
    feed_client, adjacent_tier_probe
):
    """Not this queue's path, and guarded here because this queue moved it.

    Q472 lifted the builder's argument into a named local
    (`_concept_build_filter`), one line above the call. UX-P177's guard on that
    wiring is `assert "sport or _concept_sport_filter" in src` — a source
    substring, which my rename keeps TRUE while no longer proving the value is
    used. The behavioural tests in `test_feed_concept_tag_filter.py` all call
    `list_all_concepts` directly and never enter the route, so the route half
    had no witness at all. It has one now."""
    await _feed_names(feed_client, tags='["sport:mma"]')
    assert adjacent_tier_probe["concepts"] == [("mma",)], (
        "a `sport:mma` tag no longer narrows the concept build through the "
        f"route: {adjacent_tier_probe['concepts']}"
    )


@pytest.mark.asyncio
async def test_a_category_browse_never_shares_the_concept_artifact_with_discover(
    feed_client, adjacent_tier_probe
):
    """The second defect, found while repairing the first.

    The shared concept key stood in for the builder's real argument with the
    two things that argument was derived FROM. Once a THIRD source can shape it,
    `?category=mma` and plain Discover carry the same sport and the same (empty)
    tags — so they would have shared one entry and whichever arrived first
    would publish its answer to the other.

    Two requests, two DIFFERENT builder arguments: the count is the proof."""
    await _feed_names(feed_client, category="mma")
    await _feed_names(feed_client)
    assert adjacent_tier_probe["concepts"] == [("mma",), None], (
        "the category build and the Discover build must not share a cache "
        f"entry: {adjacent_tier_probe['concepts']}"
    )


@pytest.mark.asyncio
async def test_two_identical_discover_requests_still_share_one_concept_build(
    feed_client, adjacent_tier_probe
):
    """The control for the test above: the key was made MORE precise, not
    unshareable. Re-keying is only free if identical requests still hit."""
    await _feed_names(feed_client)
    await _feed_names(feed_client, offset=1)
    assert adjacent_tier_probe["concepts"] == [None], (
        "the re-keyed concept cache stopped sharing between identical builds: "
        f"{adjacent_tier_probe['concepts']}"
    )


# ── The concept vocabulary stays derived, not copied ─────────────────────────


def test_the_category_concept_filter_is_derived_from_the_registered_sources():
    """A fourth source registered tomorrow is covered the same day.

    The sibling assertion in `test_feed_concept_tag_filter.py` for the tag
    caller. Both exist because `feed.py` grew a hand-written copy of this list
    once and lost `cycling` out of it."""
    from app.utils.event_concept_population import (
        CONCEPT_SOURCES,
        concept_filter_for_category,
    )

    for source in CONCEPT_SOURCES:
        skip, filt = concept_filter_for_category(source.category)
        assert skip is False and filt == (source.category,), (
            f"registered source {source.category!r} is not reachable by its own "
            "category"
        )


def test_a_category_naming_no_concept_source_is_skipped_not_run_unfiltered():
    from app.utils.event_concept_population import concept_filter_for_category

    for category in ("economics", "table_tennis", "politics", "weather"):
        assert concept_filter_for_category(category) == (True, None), (
            f"{category!r} must skip the concept tier, not run it with no filter"
        )


def test_no_category_leaves_the_concept_tier_exactly_as_it_was():
    """The Discover control on the helper itself."""
    from app.utils.event_concept_population import concept_filter_for_category

    assert concept_filter_for_category(None) == (False, None)
    assert concept_filter_for_category("") == (False, None)


def test_the_golf_vocabulary_is_one_constant_read_by_both_layers():
    """The route gate and the scorer's own refusal must not hold two copies.

    Anchored on the AST call/compare nodes rather than on the constant's name
    appearing in the file: a `GOLF_TIER_SPORTS` mentioned only in a comment
    would satisfy a substring check while the literal lived on."""
    import ast

    src = inspect.getsource(feed_mod)
    tree = ast.parse(src)
    literals = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Tuple)
        and [getattr(e, "value", None) for e in node.elts] == ["golf", "all"]
    ]
    assert not literals, (
        "the ('golf', 'all') literal is back; the gate and the scorer must read "
        "GOLF_TIER_SPORTS or they will disagree"
    )

    gate_src = inspect.getsource(feed_mod.get_feed)
    assert "GOLF_TIER_SPORTS" in gate_src, (
        "the route-level category gate must read the shared golf vocabulary"
    )
    assert "GOLF_TIER_SPORTS" in inspect.getsource(feed_mod._score_golf_tournaments)


# ── A category and a tag naming ONE source must not cancel (Q474 / CERT-561) ──
#
# CERT-561 blocked the repair above, and it was right. `CONCEPT_SOURCES`
# deliberately registers TWO names for the same source — UFC is reached by both
# `mma` and `ufc`, F1 by both `motorsports` and `f1` — and Q472's new narrowing
# intersected the two helpers' LITERAL STRINGS. `category=mma` yields
# `("mma",)`, `tags=["sport:ufc"]` yields `("ufc",)`, their string intersection
# is empty, and the tier was skipped for a request whose two halves name one
# registered source. The narrowing is correct in intent and wrong in currency:
# an alias is a way of SAYING a source, never the source itself.
#
# The whole reason `event_concept_population.py` exists is that a second copy of
# this vocabulary loses an entry (UX-P177 lost `cycling`). Comparing aliases as
# if they were identities is the same mistake one level down — not a second list
# that can drift, but a single list read as though its rows had one name each.
#
# Reproduced through the real route on `b0e0da41`'s own bytes before fixing:
# both pairs below served no concept card and made ZERO concept-builder calls.


def _alias_pairs_for_one_source() -> list[tuple[str, str, str]]:
    """Every (label, alias_a, alias_b) where one source answers to two names.

    Derived from the registry rather than typed out, for the reason the module
    docstring gives: a fourth source registered tomorrow with two aliases is
    covered by these tests the same day, and a hand-written `[("mma","ufc"), …]`
    here would be the third copy of the vocabulary this program has paid for.
    """
    from app.utils.event_concept_population import CONCEPT_SOURCES

    pairs = []
    for source in CONCEPT_SOURCES:
        names = [a for a in source.aliases if a != "all"]
        for i, first in enumerate(names):
            for second in names[i + 1 :]:
                pairs.append((source.label, first, second))
    return pairs


ALIAS_PAIRS = _alias_pairs_for_one_source()


def test_the_registry_really_does_give_some_source_two_names():
    """The premise of every test below.

    If `CONCEPT_SOURCES` ever collapsed to one alias per source these would
    parametrize to nothing and pass vacuously — the empty-parametrize trap. This
    fails loudly instead."""
    assert ALIAS_PAIRS, (
        "no registered concept source has two non-wildcard aliases; the "
        "alias/identity tests below would be vacuous"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("label,cat_alias,tag_alias", ALIAS_PAIRS)
async def test_a_category_and_a_tag_naming_ONE_source_keep_that_source(
    feed_client, adjacent_tier_probe, label, cat_alias, tag_alias
):
    """CERT-561's finding, through the real route, both orderings.

    Both directions are driven because the intersection is written with the tag
    filter on one side and the category filter on the other, and a fix that
    canonicalises only one side passes half of this.

    The shared concept artifact is cleared BETWEEN the two orderings, not just
    at the top: they canonicalise to one filter, so the second would otherwise
    be served the first's cached build and record zero builder calls — an
    absence that looks exactly like the defect. (That sharing is itself correct,
    and is pinned as its own guard below.)"""
    from app.utils.principal_independent_cache import clear_shared_builds

    for category, tag in ((cat_alias, tag_alias), (tag_alias, cat_alias)):
        clear_shared_builds()
        adjacent_tier_probe["concepts"].clear()
        names = await _feed_names(
            feed_client, category=category, tags=f'["sport:{tag}"]'
        )
        assert CONCEPT_STUB_NAME in names, (
            f"category={category!r} + sport:{tag} both name the {label!r} source, "
            f"yet the page carries no concept card: {names}"
        )
        assert adjacent_tier_probe["concepts"], (
            f"category={category!r} + sport:{tag} skipped the concept tier "
            f"entirely though both name {label!r}"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("label,cat_alias,tag_alias", ALIAS_PAIRS)
async def test_that_narrowed_build_is_still_narrowed_to_the_one_source(
    feed_client, adjacent_tier_probe, label, cat_alias, tag_alias
):
    """Running the tier is half the answer; running it UNFILTERED is CERT-542
    again. The filter handed to the builder must select this source and no
    other."""
    from app.utils.event_concept_population import (
        CONCEPT_SOURCES,
        _source_applies,
    )

    await _feed_names(
        feed_client, category=cat_alias, tags=f'["sport:{tag_alias}"]'
    )
    assert len(adjacent_tier_probe["concepts"]) == 1
    handed = adjacent_tier_probe["concepts"][0]
    assert handed, "the tier ran with NO filter — every source would be built"
    selected = {s.label for s in CONCEPT_SOURCES if _source_applies(s.aliases, handed)}
    assert selected == {label}, (
        f"category={cat_alias!r} + sport:{tag_alias} must build exactly "
        f"{{{label!r}}}; the filter {handed!r} selects {selected}"
    )


@pytest.mark.asyncio
async def test_a_category_and_a_tag_naming_DIFFERENT_sources_still_cancel(
    feed_client, adjacent_tier_probe
):
    """The control that stops the fix from becoming a union.

    `mma` and `cycling` are two different registered sources. A page asked for
    both narrows to nothing, and nothing is a skipped tier — never the union,
    which is the failure mode a canonicalising fix reaches for first."""
    names = await _feed_names(feed_client, category="mma", tags='["sport:cycling"]')
    assert CONCEPT_STUB_NAME not in names, (
        f"a genuinely disjoint category/tag pair served concepts anyway: {names}"
    )
    assert adjacent_tier_probe["concepts"] == [], (
        "a genuinely disjoint pair must SKIP the tier, not build and discard: "
        f"{adjacent_tier_probe['concepts']}"
    )


@pytest.mark.asyncio
async def test_the_same_alias_on_both_sides_still_serves_that_one_source(
    feed_client, adjacent_tier_probe
):
    """The case Q472 already got right, pinned so the repair cannot lose it.

    Asserted by what the filter SELECTS, not by the string it is spelled with.
    The narrowed filter is now canonical — `("mma", "ufc")`, every non-wildcard
    alias of the one shared source — which is the whole point of the repair, so
    a test pinning the literal `("mma",)` here would forbid the fix rather than
    guard the behaviour."""
    from app.utils.event_concept_population import CONCEPT_SOURCES, _source_applies

    names = await _feed_names(feed_client, category="mma", tags='["sport:mma"]')
    assert CONCEPT_STUB_NAME in names, f"category=mma + sport:mma lost concepts: {names}"
    assert len(adjacent_tier_probe["concepts"]) == 1
    handed = adjacent_tier_probe["concepts"][0]
    selected = {s.label for s in CONCEPT_SOURCES if _source_applies(s.aliases, handed)}
    assert selected == {"ufc"}, (
        f"category=mma + sport:mma must build exactly the UFC source; the "
        f"filter {handed!r} selects {selected}"
    )


@pytest.mark.asyncio
async def test_two_spellings_of_one_source_share_a_single_concept_build(
    feed_client, adjacent_tier_probe
):
    """The payoff of canonicalising rather than string-matching, made a guard.

    `category=mma&tags=["sport:ufc"]` and `category=ufc&tags=["sport:mma"]` are
    the same request said two ways. Before the repair they built nothing at all;
    a fix that merely preserved each side's own spelling would build the same
    artifact twice under two keys. They now narrow to one canonical filter, so
    the second is served the first's build — the ~1s concept stage is paid once.

    This is also the trap that made the ordering test above look like the defect
    it was written to catch."""
    await _feed_names(feed_client, category="mma", tags='["sport:ufc"]')
    assert len(adjacent_tier_probe["concepts"]) == 1, (
        f"the first spelling did not build: {adjacent_tier_probe['concepts']}"
    )
    await _feed_names(feed_client, category="ufc", tags='["sport:mma"]')
    assert len(adjacent_tier_probe["concepts"]) == 1, (
        "two spellings of one source rebuilt the concept tier instead of "
        f"sharing it: {adjacent_tier_probe['concepts']}"
    )


# ── The canonicalisation's own properties (Q474 / CERT-561) ──────────────────


def test_a_filter_and_the_sources_it_names_round_trip_for_every_subset():
    """`concept_filter_for_sources` is the inverse of `concept_sources_named`.

    The load-bearing property of the repair, and the one that stops the narrowed
    filter from being *nearly* right. Checked over every subset of the registry
    rather than the two pairs CERT-561 named, because a filter that selects one
    source too many is the CERT-542 foreign-card defect and one too few is the
    CERT-561 empty-page defect — both reachable from a plausible mis-derivation.
    """
    from itertools import combinations

    from app.utils.event_concept_population import (
        CONCEPT_SOURCES,
        concept_filter_for_sources,
        concept_sources_named,
    )

    labels = [s.label for s in CONCEPT_SOURCES]
    for size in range(1, len(labels) + 1):
        for subset in combinations(labels, size):
            filt = concept_filter_for_sources(subset)
            assert concept_sources_named(filt) == frozenset(subset), (
                f"filter {filt!r} for sources {subset} selects "
                f"{set(concept_sources_named(filt))}"
            )


def test_the_canonical_filter_never_emits_the_wildcard_alias():
    """`all` is every source's alias, so one leaking in turns the narrowing the
    repair adds into no narrowing at all — a silent return to CERT-542."""
    from itertools import combinations

    from app.utils.event_concept_population import (
        CONCEPT_SOURCES,
        concept_filter_for_sources,
    )

    labels = [s.label for s in CONCEPT_SOURCES]
    assert any("all" in s.aliases for s in CONCEPT_SOURCES), (
        "no source registers `all`; this guard would be vacuous"
    )
    for size in range(1, len(labels) + 1):
        for subset in combinations(labels, size):
            assert "all" not in concept_filter_for_sources(subset)


def test_every_alias_of_a_shared_source_narrows_to_that_source():
    """CERT-561's finding at the helper, over the whole registry.

    Any two aliases of one source must narrow to that source — never to nothing,
    which is the defect, and never to a second source, which would be a union.
    """
    from app.utils.event_concept_population import (
        CONCEPT_SOURCES,
        concept_sources_named,
        narrow_concept_filters,
    )

    for source in CONCEPT_SOURCES:
        names = [a for a in source.aliases if a != "all"]
        for first in names:
            for second in names:
                skip, filt = narrow_concept_filters((first,), (second,))
                assert skip is False, (
                    f"{first!r} and {second!r} both name {source.label!r} and "
                    "narrowed to nothing"
                )
                assert concept_sources_named(filt) == {source.label}, (
                    f"{first!r} + {second!r} narrowed to "
                    f"{set(concept_sources_named(filt))}, not {source.label!r}"
                )


def test_narrowing_disjoint_sources_skips_rather_than_unions():
    from app.utils.event_concept_population import narrow_concept_filters

    assert narrow_concept_filters(("mma",), ("cycling",)) == (True, None)
    assert narrow_concept_filters(("ufc",), ("cycling",)) == (True, None)
    assert narrow_concept_filters(("f1",), ("mma",)) == (True, None)


def test_a_silent_side_passes_the_other_through_byte_for_byte():
    """No churn on the single-filter paths.

    Re-expanding a filter that is already correct would change the shared
    concept cache key for every plain `?tags=` and `?category=` request without
    changing one card that gets built."""
    from app.utils.event_concept_population import narrow_concept_filters

    assert narrow_concept_filters(None, ("mma",)) == (False, ("mma",))
    assert narrow_concept_filters(("mma",), None) == (False, ("mma",))
    assert narrow_concept_filters((), ("cycling",)) == (False, ("cycling",))
    assert narrow_concept_filters(None, None) == (False, None)


def test_the_canonicaliser_answers_with_the_same_predicate_the_builder_uses():
    """`concept_sources_named` must not re-implement source selection.

    Two copies of "does this filter name this source" is the drift this module
    exists to prevent; anchored on the AST call node rather than the name
    appearing anywhere in the file."""
    import ast

    from app.utils import event_concept_population as ecp

    fn = ast.parse(inspect.getsource(ecp.concept_sources_named))
    called = {
        node.func.id
        for node in ast.walk(fn)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "_source_applies" in called, (
        "concept_sources_named resolves membership itself instead of asking the "
        "predicate list_all_concepts builds with"
    )


def test_the_canonical_filter_holds_for_a_source_whose_label_is_not_an_alias():
    """The coincidence the repair refuses to rest on, made a real case.

    All three sources registered today answer to their own label, so deriving
    the narrowed filter from `source.label` instead of `source.aliases` passes
    every other test in this file. It is still wrong: nothing in `ConceptSource`
    requires the label to be an alias — the label is the log line and the aliases
    are the selectors. A fourth source registered that way would narrow to a
    filter selecting nothing, and its category page would go empty exactly the
    way CERT-561's did.

    So one is registered here, and the round-trip has to survive it."""
    from app.utils import event_concept_population as ecp

    synthetic = ecp.ConceptSource(
        "darts-label-only",
        ("darts", "oche"),
        4,
        "app.utils.event_darts",
        "list_darts_concepts",
        "darts",
        ("name",),
    )
    assert synthetic.label not in synthetic.aliases, "the premise of this test"

    original = ecp.CONCEPT_SOURCES
    try:
        ecp.CONCEPT_SOURCES = original + (synthetic,)
        filt = ecp.concept_filter_for_sources({synthetic.label})
        assert filt, (
            "a source whose label is not one of its aliases narrowed to an "
            "EMPTY filter — the label/alias coincidence is load-bearing"
        )
        assert ecp.concept_sources_named(filt) == {synthetic.label}, (
            f"filter {filt!r} selects {set(ecp.concept_sources_named(filt))}"
        )
        skip, narrowed = ecp.narrow_concept_filters(("darts",), ("oche",))
        assert skip is False and ecp.concept_sources_named(narrowed) == {
            synthetic.label
        }, "two aliases of the synthetic source did not narrow to it"
    finally:
        ecp.CONCEPT_SOURCES = original

    assert ecp.CONCEPT_SOURCES is original, "the registry was not restored"
