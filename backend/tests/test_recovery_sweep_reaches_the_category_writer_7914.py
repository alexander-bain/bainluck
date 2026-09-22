"""#7914 follow-up `7914-PIN-HEAVY-RECOVERY-TO-CATEGORY-WRITE` (CERT-3272, nonblocking).

#7914 shipped a category rule and claimed, in its PR body, its module comment and
one test docstring, that the live specimen it rests on (event 79905, market
113358) is reached by *the ordinary poll*. That was wrong. It is reached by the
hourly heavy ``recover_sunk_polymarket_events``. The mistake was cheap to make
and expensive to carry: ``poll_polymarket_markets`` is not in ``HEAVY_TASKS``, so
checking the RULE'S HOME said "no heavy release owed", while the task that
actually REWRITES THE ROW is heavy and notice 48 does bind.

Measured on production 2026-09-22 04:10Z: market 113358 (#7914's climate row) and
market 113129 (#7874's Nobel row) both carry ``volume_updated_at`` stamped
19:26:52Z / 19:27:03Z — the ``crontab(minute=26)`` sweep's signature — and both
match the recovery selector (polymarket, ``status='open'``, parent id, volume
older than ``SUNK_POLY_STALE_HOURS``).

WHAT EACH GUARD BELOW PINS, AND WHAT IT DOES NOT. None of these touch a database
or the venue; they pin the three links in the chain that made the claim wrong, so
that the claim cannot go stale silently:

  1. the sweep is SCHEDULED, and scheduled onto the heavy queue (so notice 48
     applies and a heavy release line is owed by anything it carries);
  2. the sweep's selector ADMITS the shape these rows have, and still refuses the
     shapes it exists to refuse;
  3. the sweep HANDS its events to the poll's own writer — the one function that
     carries the category rule — rather than to a bespoke writer of its own.

They do NOT prove the row moved; that is the after-check's job, and the after-check
has its own trap (below). They prove the reachability claim this ship rests on.

🪤 THE AFTER-CHECK TRAP THIS FILE EXISTS TO DOCUMENT. The sweep is hourly but a
given row is NOT reached hourly. Both specimens sit in the ROTATE arm (their
resolution dates are beyond the 14-day imminent horizon), which walks ~9,500
eligible rows 300 at a time behind a Redis cursor — a ~32-hour lap. They are
reached in the first pass after the cursor WRAPS, because only ~120 and ~223
eligible rows sort below them by id. So a row still reading its old category is
the EXPECTED state for most of a lap. Read ``volume_updated_at`` before reading
the category: if the stamp has not moved, the writer has not run and the row is
evidence about nothing.
"""

import ast
import inspect
from pathlib import Path

import pytest

from app.tasks import celery_app
from app.tasks import polymarket as poly

RECOVERY_TASK_NAME = "app.tasks.recover_sunk_polymarket_events"

#: The writer the ordinary poll uses. The whole point of the third guard is that
#: the recovery sweep uses THIS one and not a copy of it.
CATEGORY_WRITER = "_process_event_batch"


def _beat_entry():
    for entry in celery_app.conf.beat_schedule.values():
        if entry.get("task") == RECOVERY_TASK_NAME:
            return entry
    return None


# ---------------------------------------------------------------------------
# 1. The sweep is scheduled, and it is HEAVY.
# ---------------------------------------------------------------------------


def test_the_recovery_sweep_is_scheduled_at_all():
    """If this ever fails, the specimens have no writer and #7914 is inert."""
    assert _beat_entry() is not None, (
        f"{RECOVERY_TASK_NAME} has no beat entry: nothing rewrites the rows "
        "#7914's reach claim depends on"
    )


def test_the_recovery_sweep_is_queued_heavy_so_notice_48_binds():
    """The link that #7914 got wrong, stated as an assertion.

    A change routing this to the default queue would make "merged, heavy pending"
    false — and would do so silently, because the rule's own module is not heavy.
    """
    entry = _beat_entry()
    assert entry is not None
    assert entry.get("options", {}).get("queue") == "heavy", (
        "the recovery sweep is the writer for #7914's specimen; if it stops "
        "being heavy, the heavy-release line this ship owes stops being owed "
        "and every after-check built on it is timed against the wrong release"
    )


# ---------------------------------------------------------------------------
# 2. The selector admits this shape, and still refuses what it must.
#
# The WHERE clause is raw SQL, so these read its predicates rather than execute
# them. To keep that from degenerating into a spell-check, each assertion names
# the BEHAVIOUR it protects and the controls below fail if a predicate is
# dropped — which is the realistic regression, not a reworded one.
# ---------------------------------------------------------------------------


def test_the_recovery_selector_admits_the_open_parent_shape_both_specimens_have():
    where = poly._SUNK_POLY_WHERE
    # polymarket rows only, and only the ones we still serve as open — the two
    # properties that put 113358 and 113129 in the pool at all.
    assert "fm.source = 'polymarket'" in where
    assert "fm.status = 'open'" in where
    # Parents only: an id-addressed Gamma read takes the EVENT id, and both
    # specimens are parents. A child would be reached through its parent.
    assert "fm.external_id NOT LIKE '0x%'" in where
    # Staleness is what makes the pool finite and what makes a re-read cheap;
    # it is also the field an after-check must read before believing a category.
    assert "volume_updated_at" in where
    assert ":stale_hours" in where


def test_the_recovery_selector_keeps_the_floor_that_stops_it_eating_settled_rows():
    """Gotcha #41: a sweep over an expiring population needs BOTH bounds.

    Without the resolution floor the pass spends itself on rows settlement owns,
    and the live specimens — which are months out — are the first thing starved.
    """
    assert "fm.resolution_date" in poly._SUNK_POLY_WHERE
    assert ":refused" in poly._SUNK_POLY_WHERE


def test_the_two_arms_split_on_the_imminent_horizon_which_is_why_these_rows_rotate():
    """Both specimens resolve beyond the horizon, so both are ROTATE, not imminent.

    This is the fact that turns "hourly" into "~32-hourly" for them, and it is the
    single most misleading thing about timing an after-check on this path.
    """
    imminent = str(poly._SUNK_POLY_IMMINENT_SQL)
    rotate = str(poly._SUNK_POLY_ROTATE_SQL)
    assert ":horizon_days" in imminent and ":horizon_days" in rotate
    # The imminent arm takes what is close; the rotate arm takes the rest, behind
    # a cursor. If the cursor ever leaves the rotate arm, a far-dated row can be
    # skipped forever rather than merely slowly.
    assert ":cursor" in rotate
    assert ":cursor" not in imminent
    assert poly.SUNK_POLY_IMMINENT_DAYS > 0
    assert poly.SUNK_POLY_STALE_HOURS > 0


def test_the_venue_side_gate_admits_a_live_event_and_refuses_the_three_dead_shapes():
    """`sunk_event_is_open` is pure, so this one is behaviour, not text.

    Gamma keeps `active=true` on a CLOSED event, so the closed control is the
    load-bearing one: without it a settled market is re-opened and re-priced.
    """

    class E:
        def __init__(self, active=True, closed=False, archived=False):
            self.active, self.closed, self.archived = active, closed, archived

    assert poly.sunk_event_is_open(E()) is True
    assert poly.sunk_event_is_open(E(active=False)) is False
    assert poly.sunk_event_is_open(E(closed=True)) is False
    assert poly.sunk_event_is_open(E(archived=True)) is False


# ---------------------------------------------------------------------------
# 3. The sweep hands off to the POLL'S OWN writer.
#
# This is the guard that matters. The plausible-but-wrong implementation is a
# recovery path with its own inlined upsert: it would look correct, price rows
# correctly, stamp `volume_updated_at` correctly — and quietly not apply the
# category rule, making #7914 inert for exactly the rows it was written for.
# ---------------------------------------------------------------------------


def _calls_in(func) -> set[str]:
    """Every plain function name called in `func`'s body, via AST."""
    src = inspect.getsource(func)
    tree = ast.parse(inspect.cleandoc(src) if src.startswith(" ") else src)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name):
                names.add(f.id)
            elif isinstance(f, ast.Attribute):
                names.add(f.attr)
    return names


def test_the_recovery_sweep_hands_its_events_to_the_polls_category_writer():
    calls = _calls_in(poly._recover_sunk_polymarket_events)
    assert CATEGORY_WRITER in calls, (
        "the recovery sweep must write through the poll's own writer; a bespoke "
        "writer here would reprice the row without applying #7914's category "
        "rule, and the defect would be invisible on the page it was fixed for"
    )


def test_the_recovery_sweep_screens_events_through_the_open_gate_before_writing():
    """The census helpers are not decoration: they are why a half-written event
    is never reported as recovered, and why a closed event never reaches the
    writer at all."""
    calls = _calls_in(poly._recover_sunk_polymarket_events)
    assert "sunk_event_is_open" in calls
    assert "sunk_event_child_census" in calls


def test_the_category_writer_has_exactly_one_definition():
    """If a second writer ever appears, the category rule has two homes and one
    of them will drift.

    🪤 This pins ONE HOME, not the recovery sweep's use of it — measured: severing
    the sweep's handoff leaves this green, because the poll's three call sites
    keep the name alive. The handoff is
    `test_the_recovery_sweep_hands_its_events_to_the_polls_category_writer`'s job
    and only that test's; do not read this one as covering it.
    """
    src = Path(poly.__file__).read_text()
    assert src.count(f"async def {CATEGORY_WRITER}(") == 1


@pytest.mark.parametrize("name", ["_SUNK_POLY_WHERE", "_SUNK_POLY_IMMINENT_SQL", "_SUNK_POLY_ROTATE_SQL"])
def test_the_selector_pieces_this_file_reasons_about_still_exist(name):
    """A rename would make every text assertion above vacuously pass on absence
    if they were written defensively; they are not, but this makes the coupling
    explicit rather than implicit."""
    assert getattr(poly, name, None) is not None
