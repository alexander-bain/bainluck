"""#901: _precompute_grids must warm the golf playoff grid.

`/playoffs/golf` reads `bainluck:category:playoffs:golf`; if the hourly warm
loop skips golf, every load cold-rebuilds via ~15 sequential DataGolf calls
(~12s) and the skeleton often never resolves. This guards the warm list so a
future refactor can't silently drop golf again.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import app.tasks.precompute_category_pages as pcp


class _FakeCM:
    async def __aenter__(self):
        return MagicMock()

    async def __aexit__(self, *a):
        return False


async def test_precompute_grids_warms_golf():
    grid_mock = AsyncMock(return_value={"teams": [], "columns": []})
    redis_mock = MagicMock()

    with patch("app.tasks.redis_state.get_redis_client", return_value=redis_mock), \
            patch("app.tasks.base.get_task_session", return_value=_FakeCM()), \
            patch("app.routes.playoffs.get_playoff_grid", grid_mock):
        warmed = await pcp._precompute_grids()

    # golf must be in the warmed set (alongside the existing leagues)
    assert "golf" in warmed, warmed
    assert {"mlb", "nba", "nhl", "golf"}.issubset(set(warmed))

    # get_playoff_grid was actually invoked for golf
    called_slugs = {c.args[0] for c in grid_mock.call_args_list}
    assert "golf" in called_slugs, called_slugs

    # the golf cache key was written to Redis (setex), proving the warm path
    written_keys = {c.args[0] for c in redis_mock.setex.call_args_list}
    assert "bainluck:category:playoffs:golf" in written_keys, written_keys


def test_precompute_grids_source_lists_golf():
    """Belt-and-suspenders assert: the warm list still includes golf.

    #1484 lifted the literal out of the loop body into the module-level
    ``GRID_WARM_LEAGUES`` so the observability report can pre-seed one entry per
    league. Assert the constant directly — it is the thing a future refactor
    could actually drop, and it is stronger than a substring match on source
    text (which "golf" would satisfy from a docstring alone).
    """
    assert "golf" in pcp.GRID_WARM_LEAGUES
    assert {"mlb", "nba", "nhl", "golf"}.issubset(set(pcp.GRID_WARM_LEAGUES))
