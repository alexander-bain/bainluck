"""#762: published-calibration void filter (did_not_play / withdrew non-participants).

DataGolf "Make the Cut" markets generate ~49% did_not_play outcomes — players who
never teed off, all graded is_winner=False. They are VOIDs, not losses, and were
dragging DataGolf's MCE to ~13.7pp. The main calibration query drops them from the
denominator; this covers the canonical predicate, that the production SQL embeds
the exclusion + transparency count, and that the route fallback keeps the response
shape consistent (void_filter key present).
"""

from types import SimpleNamespace

import pytest

from app.routes import calibration
from app.tasks import precompute_calibration
from app.tasks.precompute_calibration import (
    VOID_FILTER_RULE_TEXT,
    VOID_RESOLUTION_SOURCES,
    outcome_is_calibration_void,
)


class TestVoidPredicate:
    """Canonical definition: void iff the player never participated."""

    def test_non_participants_excluded(self):
        assert outcome_is_calibration_void("did_not_play") is True
        assert outcome_is_calibration_void("withdrew") is True

    def test_real_outcomes_included(self):
        # Played/graded outcomes count toward calibration.
        assert outcome_is_calibration_void("leaderboard") is False
        assert outcome_is_calibration_void("all_losers") is False
        assert outcome_is_calibration_void("api_settlement") is False

    def test_none_is_not_void(self):
        # NULL resolution_source is a real (legacy) grading, not a void.
        assert outcome_is_calibration_void(None) is False

    def test_constant_lists_both_sources(self):
        assert "did_not_play" in VOID_RESOLUTION_SOURCES
        assert "withdrew" in VOID_RESOLUTION_SOURCES


class TestVoidSQL:
    def test_rule_text_describes_the_filter(self):
        t = VOID_FILTER_RULE_TEXT.lower()
        assert "did_not_play" in t
        assert "withdrew" in t
        assert "void" in t

    def test_main_precompute_query_embeds_exclusion_and_count(self):
        import inspect

        src = inspect.getsource(precompute_calibration._precompute_calibration_main)
        # The exclusion is applied in the main bucket query's WHERE clause.
        assert "'did_not_play', 'withdrew'" in src
        # The transparency count query + payload surface.
        assert "void_excluded" in src
        assert '"void_filter"' in src


class _FakeResult:
    def __init__(self, *, rows=None, scalar_value=None, one_value=None):
        self._rows = rows or []
        self._scalar_value = scalar_value
        self._one_value = one_value

    def all(self):
        return self._rows

    def scalar(self):
        return self._scalar_value

    def one(self):
        return self._one_value


class _FakeDB:
    """Mirrors the route's cold-cache inline computation (6 queries)."""

    def __init__(self):
        self._results = [
            _FakeResult(rows=[]),  # main futures
            _FakeResult(rows=[]),  # events
            _FakeResult(rows=[]),  # spreads
            _FakeResult(rows=[]),  # totals
            _FakeResult(scalar_value=0),  # total markets
            _FakeResult(
                one_value=SimpleNamespace(
                    has_closing=0, needs_closing=0, total_completed=0
                )
            ),
        ]

    async def execute(self, statement):
        return self._results.pop(0)


@pytest.mark.asyncio
async def test_route_fallback_includes_void_filter_key():
    # Cold-cache fallback serves void_filter=None for shape consistency; the
    # authoritative count comes from the precompute->Redis path.
    calibration._cache = {"data": None, "timestamp": 0}
    resp = await calibration.public_calibration(db=_FakeDB(), bust=1)
    assert "void_filter" in resp
    assert resp["void_filter"] is None
