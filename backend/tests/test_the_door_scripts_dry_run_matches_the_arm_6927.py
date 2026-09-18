"""The door script's dry-run screen must be the arm's screen (#6927 after-check).

``scripts/unreachable_suspended_door.py`` is the ATTENDED CONTROL for the
unreachable-suspended arm: ``--dry-run`` is the only "change nothing, see what
it would touch" instrument an operator has before typing ``--open N``. It
carries its own copy of the arm's population as ``_SCOPE_SQL``, and a second
copy of a rule drifts — which is the same defect #6927 fixed inside the arm
itself (one rule, two copies, both hanging off the same hook).

MEASURED ON PRODUCTION 2026-09-18, immediately after #6927 went live at v4723,
with the door reopened at 13:35:47Z. The uncorrected script disagreed with the
arm in THREE places at once, in BOTH directions:

  * **floor 72h vs the arm's 96h.** ``_constants`` re-added
    ``SUSPENDED_RESUME_WINDOW + UNREACHABLE_SUSPENDED_MARGIN``; the arm calls
    ``unreachable_suspended_floor()``, which is ``max(SUSPENDED_RESUME_WINDOW,
    ODDS_SCORES_LOOKBACK) + UNREACHABLE_SUSPENDED_MARGIN``. #6347 added the
    second door to that ``max`` and the script never noticed. 494 rows clear
    72h; 177 clear 96h.
  * **no market question at all** — so the dry-run counted rows the arm
    refuses. At the true floor, 177 of 177 eligible rows carry a market, so the
    uncorrected instrument reported a backlog of which NONE was real.
  * **no ``odds_api`` arm** — so it also MISSED 147 rows the arm does act on.

The operator-visible cost: ``--dry-run`` said "eligible 347" on a morning when
the arm's honest answer was 0. An instrument that is wrong in both directions
cannot be sanity-checked by eye, which is why this file exists.

WHY AST AND NOT A BEHAVIOURAL DIFF. The right guard would build both screens and
compare the rows. ``_SCOPE_SQL`` is Postgres-only (``make_interval(hours => ...)``,
``<> ALL(...)``) and the suite's event fixtures are sqlite, so an equivalence run
is not available here; extracting the arm's SQLAlchemy screen into a shared
callable is the real repair and is an app-code change to a task that writes a
terminal status, which is not this script's class. Until then these tests hold
the two spellings together.

🔴 THE MAPPING IS CLOSED, DELIBERATELY. A column added to the arm's screen that
this file has never heard of FAILS rather than being skipped. An allowlist whose
default is "no opinion" is how the market clause went missing in the first
place: the drift that matters is always the clause nobody enumerated.
"""

import ast
import pathlib

import pytest

from app.tasks.espn_sync import unreachable_suspended_floor
from scripts.unreachable_suspended_door import _SCOPE_SQL, _constants

_ESPN_SYNC = (
    pathlib.Path(__file__).resolve().parents[1] / "app" / "tasks" / "espn_sync.py"
)

#: Every ``Event.<attr>`` the arm's screen may reference, mapped to the fragment
#: the script's SQL must contain for it. ``sport_id`` is the one that is spelled
#: differently on purpose — the arm excludes by resolved sport id, the script
#: joins `sports` and excludes by key — so it maps to the join's column, not to
#: `e.sport_id`.
_EXPECTED_FRAGMENT = {
    "status": "e.status",
    "external_id": "e.external_id",
    "commence_time_source": "e.commence_time_source",
    "espn_id": "e.espn_id",
    "statpal_fixture_id": "e.statpal_fixture_id",
    "home_score": "e.home_score",
    "away_score": "e.away_score",
    "completed_at": "e.completed_at",
    "commence_time": "e.commence_time",
    "sport_id": "s.key",
}


def _arm_screen_node():
    """The `.where(...)` call of the arm's `unreachable_result` SELECT."""
    tree = ast.parse(_ESPN_SYNC.read_text())
    for node in ast.walk(tree):
        targets = getattr(node, "targets", [])
        if not (
            isinstance(node, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "unreachable_result"
                for t in targets
            )
        ):
            continue
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Attribute)
                and inner.func.attr == "where"
            ):
                return inner
    pytest.fail(
        "Could not find the arm's `unreachable_result = ... .where(...)` screen "
        "in espn_sync.py. The arm was renamed or restructured — this guard is "
        "now blind and must be re-aimed, NOT deleted."
    )


def _screened_event_columns() -> set:
    where = _arm_screen_node()
    cols = set()
    for node in ast.walk(where):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "Event"
        ):
            cols.add(node.attr)
    return cols


class TestTheFloorIsTheArmsFloor:
    def test_the_script_calls_the_arms_floor_function(self):
        """72h vs 96h — the bug this catches, stated as a number."""
        assert _constants()["floor_hours"] == pytest.approx(
            unreachable_suspended_floor().total_seconds() / 3600.0
        )

    def test_the_floor_is_not_the_resume_window_alone(self):
        """A counter-example to the old derivation, so this is not a tautology.

        The broken spelling was `SUSPENDED_RESUME_WINDOW + MARGIN`. If that ever
        equals the real floor again the test above stops discriminating, so pin
        the fact that the `max` has a second, larger door in it.
        """
        from app.tasks.espn_sync import SUSPENDED_RESUME_WINDOW
        from app.utils.event_completion import UNREACHABLE_SUSPENDED_MARGIN

        broken = (
            SUSPENDED_RESUME_WINDOW + UNREACHABLE_SUSPENDED_MARGIN
        ).total_seconds() / 3600.0
        assert _constants()["floor_hours"] > broken


class TestTheScopeIsTheArmsScope:
    def test_the_scope_asks_the_market_question(self):
        """#6927's whole subject: a row carrying a market is never retired."""
        normalized = " ".join(_SCOPE_SQL.split()).lower()
        assert "not exists" in normalized
        assert "futures_markets" in normalized
        assert "f.event_id = e.id" in normalized

    def test_the_arm_itself_still_asks_it(self):
        """If the arm drops the clause, pinning the script to it proves nothing."""
        where = _arm_screen_node()
        names = {n.id for n in ast.walk(where) if isinstance(n, ast.Name)}
        assert "market_anchored_exists" in names

    def test_the_scope_admits_the_odds_api_arm(self):
        """#6347's second class — an `external_id` that is present but inert."""
        normalized = " ".join(_SCOPE_SQL.split()).lower()
        assert "e.commence_time_source = 'odds_api'" in normalized
        assert "e.external_id is null or" in normalized

    def test_every_column_the_arm_screens_on_is_in_the_script(self):
        """The forward-safe half: a clause added to the arm must reach here."""
        normalized = " ".join(_SCOPE_SQL.split()).lower()
        unknown = _screened_event_columns() - set(_EXPECTED_FRAGMENT)
        assert not unknown, (
            f"The arm's screen references Event columns this guard has never "
            f"heard of: {sorted(unknown)}. Add each to _EXPECTED_FRAGMENT with "
            f"the fragment the script's SQL must contain — and check the script "
            f"actually screens on it. Skipping the unknown case is how the "
            f"market clause went missing."
        )
        missing = {
            col: frag
            for col, frag in _EXPECTED_FRAGMENT.items()
            if col in _screened_event_columns() and frag.lower() not in normalized
        }
        assert not missing, (
            f"The arm screens on these, the door script's _SCOPE_SQL does not: "
            f"{missing}. --dry-run would report rows the arm will not touch."
        )
