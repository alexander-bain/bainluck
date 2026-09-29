"""#9597 — the sunk-slot outcome arm's gate and its session discipline.

The route behaviour is pinned on a real database in
`tests/integration/test_search_sunk_slot_outcome_arm_9597_pg.py`; this file pins
the two things that do not need one: WHEN the arm may run (every other page must
pay nothing), and that its shed path never rolls the session back while
`deduped_futures` is live (gotcha #6, LAT-P255/#3731).
"""

from __future__ import annotations

import inspect

import pytest

from app.routes import events as events_route
from app.routes.events import _SEARCH_FUTURES_PAGE, _needs_sunk_slot_outcome_arm


@pytest.mark.parametrize(
    "arm_state, answer_rows, over_cap, expected",
    [
        ("skipped", 4, {1}, True),  # the specimen: `red sox`
        ("skipped", _SEARCH_FUTURES_PAGE - 1, {1}, True),
        ("skipped", _SEARCH_FUTURES_PAGE, {1}, False),  # sunk rows never ship
        ("skipped", 4, set(), False),  # nothing was sunk
        ("merged", 4, {1}, False),  # the arm already ran
        ("absent", 4, {1}, False),
        ("shed", 4, {1}, False),
        ("budget_exceeded", 4, {1}, False),
        ("not_reached", 4, {1}, False),
    ],
)
def test_the_gate(arm_state, answer_rows, over_cap, expected):
    assert _needs_sunk_slot_outcome_arm(arm_state, answer_rows, over_cap) is expected


def test_the_fetch_uses_a_savepoint_and_never_a_session_rollback():
    src = inspect.getsource(events_route._fetch_sunk_slot_outcome_rows)
    code = "\n".join(
        line for line in src.splitlines() if not line.lstrip().startswith("#")
    )
    assert "await db.begin_nested()" in code
    assert "_recover_search_session" not in code
    assert "db.rollback(" not in code


def test_the_fetch_excludes_the_name_arms():
    """Without the exclusion the window's name-tier-first order returns the
    props whose OUTCOMES name the club, and no outcome-only row (the pg mutant)."""
    src = inspect.getsource(events_route._fetch_sunk_slot_outcome_rows)
    assert "~candidates_in(tier1_arms)" in src


def test_the_route_reports_the_arm_state():
    src = inspect.getsource(events_route.search_events)
    assert '"futures_sunk_slot_arm": _futures_sunk_slot_arm' in src
    # The gate is counted fresh: an over-cap row is not an answer here.
    start = src.index("if _needs_sunk_slot_outcome_arm(")
    gate = src[start:src.index("_fetch_sunk_slot_outcome_rows(", start)]
    assert "m.id not in _over_match_cap_ids" in gate
