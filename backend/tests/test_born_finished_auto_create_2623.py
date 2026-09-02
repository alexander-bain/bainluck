"""#2623, the PRODUCER half — a row born finished was never a fixture.

Searching `Sabalenka` returned nine matches listed twice: a rich `odds_api` row
with the score beside a surname-only Kalshi ghost with none. **UX-P258
(PR #2631, `app/utils/search_fixture_dedup.py`) fixes the RENDERER half** — it
stops the page showing both — and says so plainly: *"This subject is the
renderer half only and claims nothing about the drain."*

This file guards the other end: the thing that keeps minting the ghosts.

The specimen names the mechanism. Event 15300722, `Sabalenka vs Bejlek`,
**created 2026-09-01 22:05 for a fixture that started 2026-08-20 04:14** —
twelve days after the match was played. Kalshi's settled markets stay
`status='open'` in our table (gotcha #33), so `_try_link_market` keeps finding
them and each pass auto-creates an event for a game long over. It is born past,
the staleness net closes it, and it renders as a FINAL with no score. That is
D26's class arriving by a second door.

RED-FIRST: every test here fails on master, where
`auto_create_is_stale_fixture` does not exist. The symbol is resolved lazily so
the failure is a COUNT of assertions rather than a collection error.
"""

from datetime import datetime, timedelta, timezone
from importlib import import_module

import pytest


def _sym(name):
    module = import_module("app.tasks.prediction_market_matching")
    sym = getattr(module, name, None)
    assert sym is not None, (
        f"app.tasks.prediction_market_matching.{name} does not exist on this "
        "tree — #2623's born-finished refusal is not applied"
    )
    return sym


def auto_create_is_stale_fixture(commence_time, now):
    return _sym("auto_create_is_stale_fixture")(commence_time, now)


NOW = datetime(2026, 9, 1, 22, 5, tzinfo=timezone.utc)


class TestTheBoundItself:
    def test_the_specimen_is_refused(self):
        played = datetime(2026, 8, 20, 4, 14, tzinfo=timezone.utc)
        assert auto_create_is_stale_fixture(played, NOW) is True

    def test_a_match_that_may_still_be_running_is_allowed(self):
        assert auto_create_is_stale_fixture(NOW - timedelta(hours=1), NOW) is False
        assert auto_create_is_stale_fixture(NOW - timedelta(hours=11), NOW) is False

    def test_a_midnight_ticker_stand_in_still_clears_the_bound(self):
        # `auto_create_commence_time` stamps a ticker DATE, which has no
        # time-of-day and resolves to midnight UTC, so a match played at 23:00
        # local on the ticker's own day sits ~30h after its own stand-in.
        # Refusing that would delete a fixture that really happened.
        assert auto_create_is_stale_fixture(NOW - timedelta(hours=30), NOW) is False

    def test_a_future_fixture_is_never_stale(self):
        assert auto_create_is_stale_fixture(NOW + timedelta(days=3), NOW) is False

    def test_absence_is_not_age(self):
        # gotcha #53. A missing time is not an old one, and the caller has
        # already replaced a missing time with `now` before reaching here.
        assert auto_create_is_stale_fixture(None, NOW) is False
        assert auto_create_is_stale_fixture(NOW, None) is False

    @pytest.mark.parametrize("hours,expected", [(35, False), (37, True)])
    def test_the_bound_is_where_it_says_it_is(self, hours, expected):
        assert _sym("AUTO_CREATE_MAX_PAST_AGE") == timedelta(hours=36)
        assert auto_create_is_stale_fixture(
            NOW - timedelta(hours=hours), NOW
        ) is expected


class TestItIsActuallyConsulted:
    """A refusal nobody calls is a comment.

    Scanned as an AST so a mention inside this module's own prose — which names
    the function repeatedly while explaining it — cannot satisfy the guard.
    """

    def test_the_auto_create_path_calls_it(self):
        import ast
        import inspect

        import app.tasks.prediction_market_matching as pmm

        tree = ast.parse(inspect.getsource(pmm))
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "auto_create_is_stale_fixture" in called, (
            "the born-finished refusal is defined and never consulted"
        )

    def test_it_sits_beside_the_other_termination_check_not_instead_of_it(self):
        # #2020's `auto_create_self_refutes` closes a different loop. Replacing
        # it would reopen a generator that produced 297 events for one market.
        import ast
        import inspect

        import app.tasks.prediction_market_matching as pmm

        tree = ast.parse(inspect.getsource(pmm))
        called = [
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        assert "auto_create_self_refutes" in called
        assert "auto_create_is_stale_fixture" in called


class TestNothingElseMoved:
    """Controls — green on master AND on this branch."""

    def test_the_status_a_row_is_born_in_is_unchanged(self):
        from app.tasks.prediction_market_matching import auto_create_status

        # A reported start in the past is still born live…
        assert auto_create_status(NOW - timedelta(hours=1), "odds_api", NOW) == "live"
        # …a future one is still born scheduled…
        assert auto_create_status(NOW + timedelta(hours=1), "odds_api", NOW) == "scheduled"
        # …and a ticker-derived stand-in is still never born live (q076).
        assert auto_create_status(
            NOW - timedelta(hours=1), "kalshi_ticker", NOW
        ) == "scheduled"

    def test_the_ticker_commence_selection_is_unchanged(self):
        from app.tasks.prediction_market_matching import auto_create_commence_time

        class _M:
            source = "polymarket"
            external_id = "no-ticker-here"

        fallback = NOW
        assert auto_create_commence_time(_M(), fallback) == (fallback, None)
