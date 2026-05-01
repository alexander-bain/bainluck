"""Smoke tests — verify the app boots without import errors.

These catch the #1 class of production crashes: broken imports in
route files, missing modules, or syntax errors that prevent uvicorn
from starting. Run before every push.
"""


def test_app_imports():
    """The FastAPI app loads and has routes registered."""
    from app.main import app
    assert len(app.routes) > 100, f"Expected >100 routes, got {len(app.routes)}"


def test_all_route_modules_import():
    """Every route module listed in main.py can be imported."""
    from app.routes import (
        events, sports, health, futures, admin, auth, user, feed,
        market_moves, oscars, oscars_pool, golf, march_madness,
        playoffs, weather, economics, league_futures, predictions,
        og_image,
    )


def test_key_task_modules_import():
    """Key task modules load without errors."""
    import app.tasks.espn_sync
    import app.tasks.odds_polling
    import app.tasks.polymarket
    import app.tasks.prediction_market_matching


def test_key_util_modules_import():
    """Key utility modules load without errors."""
    from app.utils.futures_highlights import compute_futures_highlight
    from app.utils.feed_scoring import compute_base_score
    from app.utils.aggregation import compute_aggregate_probability
