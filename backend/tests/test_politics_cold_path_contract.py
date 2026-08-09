"""LAT-P016/#1607 — the politics cold path.

#1607 reported `/api/politics` "serves 5.0s warm — sustained, not cold-cache".
Measured on 2026-08-09 against deployed `11f75a2f`, the warm path is **294ms p50 /
304ms p95** over 21 paired samples with zero non-200s, and the served payload's
`updated_at` matched the hourly warmer's `started_at` to the millisecond — so it
was a cache HIT, not a fast query.

The 5.0s was real, but it was the **cold** path being taken on every request. Those
two are indistinguishable from outside: a permanently-lapsed cache is both slow AND
sustained across repeated hits, which is exactly the reading that produced the
"not cold-cache" conclusion. The same shape as gotcha #53 — one observation, two
different facts, and the emptier reading was inferred as a fact.

What made the lapse expensive: politics was the ONLY page in the category-page
family whose warmer wrote no `:stale` mirror, so there was nothing behind the 2h
primary key. The warmer's own rail measured that rebuild at **10.4s** — twice
what #1607 reported and 35x the cache hit.

These pin the fix in both directions.
"""

import ast
import importlib
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes import politics as politics_route

POLITICS_SRC = inspect.getsource(politics_route)


def _fake_async_redis(primary=None, stale=None, raises=False):
    """An async redis stub recording every set() it is asked to perform."""
    rc = MagicMock()
    store = {
        "bainluck:category:politics": primary,
        "bainluck:category:politics:stale": stale,
    }
    rc.writes = []

    async def _get(key):
        if raises:
            raise ConnectionError("redis is down")
        return store.get(key)

    async def _set(key, value, ex=None):
        rc.writes.append((key, ex))
        return True

    rc.get = _get
    rc.set = _set
    rc.aclose = AsyncMock()
    return rc


# ---------------------------------------------------------------------------
# The three cache tiers, in order.
# ---------------------------------------------------------------------------
class TestTheRouteHasAMiddleTier:
    @pytest.mark.asyncio
    async def test_primary_hit_never_touches_stale_or_the_database(self):
        rc = _fake_async_redis(primary='{"total_markets": 7}')
        rebuild = AsyncMock()

        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc), \
             patch.object(politics_route, "get_politics", rebuild):
            out = await politics_route.get_politics_cached(db=MagicMock())

        assert out == {"total_markets": 7}
        rebuild.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_primary_miss_serves_the_stale_mirror_instead_of_rebuilding(self):
        """The whole point. Before this, a lapsed primary key went straight to a
        10.4s rebuild on the request path."""
        rc = _fake_async_redis(primary=None, stale='{"total_markets": 5166}')
        rebuild = AsyncMock()

        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc), \
             patch.object(politics_route, "get_politics", rebuild):
            out = await politics_route.get_politics_cached(db=MagicMock())

        assert out == {"total_markets": 5166}
        rebuild.assert_not_awaited(), (
            "a stale mirror was available and the route rebuilt anyway — this is "
            "the 10.4s path #1607 was actually measuring"
        )

    @pytest.mark.asyncio
    async def test_both_tiers_empty_rebuilds_and_then_populates_the_mirror(self):
        """The first cold request still pays. The SECOND one must not."""
        rc = _fake_async_redis(primary=None, stale=None)
        rebuild = AsyncMock(return_value={"total_markets": 1})

        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc), \
             patch.object(politics_route, "get_politics", rebuild):
            out = await politics_route.get_politics_cached(db=MagicMock())

        assert out == {"total_markets": 1}
        rebuild.assert_awaited_once()
        assert ("bainluck:category:politics:stale", 86400) in rc.writes, (
            "a live rebuild did not seed the mirror, so every subsequent cold "
            "request pays the full rebuild again"
        )

    @pytest.mark.asyncio
    async def test_redis_down_still_answers_and_is_not_recorded_as_a_miss(self):
        """Gotcha #53: "no such key" and "Redis did not answer" are different
        facts. Both fall through, but they must not be the same log line."""
        rc = _fake_async_redis(raises=True)
        rebuild = AsyncMock(return_value={"total_markets": 2})

        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc), \
             patch.object(politics_route, "get_politics", rebuild), \
             patch.object(politics_route.logger, "warning") as warn:
            out = await politics_route.get_politics_cached(db=MagicMock())

        assert out == {"total_markets": 2}
        states = [c.args[1] for c in warn.call_args_list
                  if c.args and "cache %s" in str(c.args[0])]
        assert "unavailable" in states, (
            "a Redis outage was logged as an ordinary cache miss"
        )


# ---------------------------------------------------------------------------
# The warmer.
# ---------------------------------------------------------------------------
class TestTheWarmerWritesBothKeys:
    @pytest.mark.asyncio
    async def test_politics_warmer_writes_primary_and_stale(self):
        pcp = importlib.import_module("app.tasks.precompute_category_pages")
        rc = MagicMock()

        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value=MagicMock())
        session.__aexit__ = AsyncMock(return_value=False)

        with patch.object(pcp, "get_task_session", return_value=session, create=True), \
             patch("app.tasks.base.get_task_session", return_value=session), \
             patch("app.tasks.redis_state.get_redis_client", return_value=rc), \
             patch("app.routes.politics.get_politics",
                   AsyncMock(return_value={"total_markets": 5166})):
            out = await pcp._precompute_politics()

        keys = {c.args[0]: c.kwargs.get("ex") for c in rc.set.call_args_list}
        assert keys.get("bainluck:category:politics") == pcp.CACHE_TTL
        assert keys.get("bainluck:category:politics:stale") == pcp.STALE_CACHE_TTL, (
            "politics still writes no stale mirror — the exact asymmetry that made "
            "a lapsed cache cost 10.4s a request (#1607)"
        )
        assert out["total_markets"] == 5166

    def test_every_category_warmer_writes_a_stale_mirror(self):
        """The class guard, not the instance.

        Politics was missing the mirror for as long as the mirror has existed, and
        nothing failed — because no test ever compared the siblings to each other.
        This asserts the family is symmetric, so the next page added cannot quietly
        ship without one.
        """
        pcp = importlib.import_module("app.tasks.precompute_category_pages")

        for name in ("politics", "entertainment", "economics"):
            src = inspect.getsource(getattr(pcp, f"_precompute_{name}"))
            assert f'{name}:stale' in src, (
                f"_precompute_{name} writes no :stale mirror, so a lapsed primary "
                f"key drops every request onto a live rebuild"
            )
            assert "STALE_CACHE_TTL" in src, (
                f"_precompute_{name}'s mirror does not use the shared 24h TTL"
            )


# ---------------------------------------------------------------------------
# Stage attribution.
# ---------------------------------------------------------------------------
class TestTheColdBuildIsAttributable:
    def test_get_politics_accepts_a_stage_ms_out_parameter(self):
        sig = inspect.signature(politics_route.get_politics)
        assert "stage_ms" in sig.parameters
        assert sig.parameters["stage_ms"].default is None, (
            "stage timing must be opt-in so the request path pays nothing"
        )

    def test_each_named_stage_is_timed_separately(self):
        """LAT-P013's lesson one level down: a bundled mark attributed 16.5s to the
        wrong thing. Every stage that issues a query or a full-corpus pass gets its
        own label, or the 10.4s stays unattributed."""
        for stage in ("market_query", "group_by_group_id", "theme_classify",
                      "presidential", "presidential_history", "congressional",
                      "cross_source", "sections"):
            assert f'_mark("{stage}"' in POLITICS_SRC, f"stage {stage} is not timed"

    def test_the_warmer_passes_a_dict_so_the_rail_can_show_it(self):
        pcp = importlib.import_module("app.tasks.precompute_category_pages")
        src = inspect.getsource(pcp._precompute_politics)
        assert "stage_ms=stage_ms" in src
        assert '"stage_ms": stage_ms' in src, (
            "stage times are measured but never surfaced in the run report, so the "
            "admin rail still cannot name the dominant stage"
        )


# ---------------------------------------------------------------------------
# The LAT-P002 revert lesson.
# ---------------------------------------------------------------------------
def test_no_request_deadline_was_added_to_the_politics_path():
    """LAT-P002 shipped a 4s bound on `/search`, it fired on HEALTHY builds, 3 of 8
    production queries came back 200-with-nothing, and master reverted the whole
    queue (f98d8104).

    The sibling economics route wraps its rebuild in `asyncio.wait_for(..., 25)` and
    returns `{"themes": {}}` when it trips. Politics deliberately does NOT copy that
    half of the pattern: on a page whose rebuild is already the family's slowest at
    10.4s and grows with market count, a bound is a promise to eventually serve an
    empty politics page instead of a slow one. Slow is a worse answer than fast;
    empty is a worse answer than slow.
    """
    # Parsed call nodes, not raw text: this file and the route both *discuss*
    # wait_for in prose, and a substring check cannot tell an explanation of the
    # trap from the trap.
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for node in ast.walk(ast.parse(POLITICS_SRC))
        if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Attribute, ast.Name))
    }
    assert "wait_for" not in called, (
        "a request deadline is back on the politics path — when it trips it will "
        "serve an empty page, which is what got LAT-P002 reverted"
    )
    assert "timeout_at" not in called and "timeout" not in called, (
        "an asyncio timeout context is back on the politics path"
    )
