"""#6057 — the payload said a match kicked off 129 minutes ago AND that it was scheduled.

THE STATE HALF OF #6031.  `27b426e65` fixed which RAIL a started row lands on and
ux's `81b0c9936` stopped the badge printing the word "Pregame".  Neither touched
the served ``status``, so every consumer reading the field rather than the badge
was still told a match in progress had not begun.

Measured on production 2026-09-14 03:24:09Z, ``/api/events/15308949``::

    served status         scheduled
    served commence_time  2026-09-14T01:15:00+00:00     <- 129 MINUTES EARLIER
    completed_at          null

The row refutes itself with no ground truth needed.  #5905's recovery reaches the
serializer — that 01:15Z IS the recovered kickoff — while the state derivation
kept the raw column's answer.

WHY THIS IS AN ADDITIVE KEY AND NOT A NEW VALUE FOR ``status``.  The three
obvious mutations were ruled out against measured consumers:

* ``live`` re-asserts exactly the unbacked liveness ``enforce_live_requires_start``
  was written to refuse.
* ``suspended`` blanks the probability on web (``EventCard`` gates every
  probability branch on ``!isSuspended``) and feeds the stuck-``suspended``
  population of #4901.
* a new word is unparsed by ``EventState.swift``, whose ``upcoming`` is
  ``status == "scheduled" || status == nil``, so the row would be neither
  upcoming nor live nor finished on iOS.

So ``status`` is asserted UNCHANGED in the same breath as the new key, in
:func:`test_the_started_row_still_serves_scheduled_beside_the_flag`.  That arm is
the design decision, and a later session that "simplifies" this by mutating the
status word reddens it.

``started_without_result`` is this repo's own predicate for the question and had
ZERO executable callers before this ship — the same "a rule with no consumer is a
document" that ``served_event_status`` records about ``enforce_live_requires_start``.
Its SQL half already decides rail membership, so publishing the Python half is
what stops a card's label and its rail's position coming from two definitions.
"""

import ast
import inspect
from datetime import datetime, timedelta, timezone

from app.models import Event, Sport
from app.routes import events as events_module
from app.routes.events import _format_event
from app.utils.event_completion import UPCOMING_GRACE, started_without_result

# The production specimen, to the minute.  129 minutes is the measured gap; the
# grace is two hours, so this row is past it by nine minutes and no more — a
# margin a widened grace would swallow.
SPECIMEN_MINUTES_PAST_KICKOFF = 129


def _event(status: str, minutes_past_kickoff: float) -> Event:
    """An event whose kickoff is `minutes_past_kickoff` behind the real clock.

    Gotcha #44: the offset is applied FIRST and the anchor contains no `if`, so
    this fixture cannot branch on what time the suite happens to run.  The
    formatter reads the wall clock itself, so the row is positioned relative to
    that clock rather than to a frozen constant.
    """
    return Event(
        id=15308949,
        sport_id=1,
        sport=Sport(id=1, key="soccer_other", name="Other Soccer"),
        home_team_name="Cucuta",
        away_team_name="Millonarios",
        commence_time=datetime.now(timezone.utc)
        - timedelta(minutes=minutes_past_kickoff),
        status=status,
        home_score=None,
        away_score=None,
    )


# ── THE PRODUCTION SPECIMEN ────────────────────────────────────────────────


def test_the_specimen_stops_claiming_it_has_not_started():
    """15308949, 129 minutes past its own served kickoff."""
    data = _format_event(_event("scheduled", SPECIMEN_MINUTES_PAST_KICKOFF))

    assert data["started_without_result"] is True


def test_the_started_row_still_serves_scheduled_beside_the_flag():
    """THE DESIGN DECISION, PINNED.

    The fix is additive.  A later change that "closes #6057 properly" by making
    the status word itself say the match began breaks web probabilities
    (`suspended`), reasserts unbacked liveness (`live`) or falls off every iOS
    branch (a new word) — see this module's docstring.  All three redden here.
    """
    data = _format_event(_event("scheduled", SPECIMEN_MINUTES_PAST_KICKOFF))

    assert data["status"] == "scheduled"
    assert data["started_without_result"] is True


def test_the_payload_no_longer_refutes_itself():
    """The whole defect, expressed as the relationship between two served keys.

    Reads the payload the way the production probe did — compute the age from
    the SERVED `commence_time`, not from the fixture's input — so this arm fails
    if the formatter ever serves a kickoff that disagrees with the flag beside it.
    """
    data = _format_event(_event("scheduled", SPECIMEN_MINUTES_PAST_KICKOFF))

    served_kickoff = datetime.fromisoformat(data["commence_time"])
    age = datetime.now(timezone.utc) - served_kickoff

    assert age > UPCOMING_GRACE
    assert data["started_without_result"] is True


# ── THE CONTROLS.  Each is a row the flag must NOT fire on ─────────────────


def test_a_row_inside_the_grace_is_not_yet_started_without_result():
    """The other side of the boundary.

    60 minutes past kickoff is a match in its first half, and the rail question
    is deliberately not asked yet — `startedWithoutResult` on the client has the
    same floor, which is why ux's badge fix had to say "Started" separately.
    """
    data = _format_event(_event("scheduled", 60))

    assert data["started_without_result"] is False


def test_a_fixture_that_has_not_kicked_off_is_untouched():
    data = _format_event(_event("scheduled", -90))

    assert data["started_without_result"] is False
    assert data["status"] == "scheduled"


def test_a_live_row_is_not_started_without_result():
    """`live` means something DID report.  The predicate is `scheduled`-only, and
    a live row three hours in is #6031's other arm, not this one."""
    data = _format_event(_event("live", 180))

    assert data["started_without_result"] is False


def test_a_finished_row_is_not_started_without_result():
    data = _format_event(_event("completed", 300))

    assert data["started_without_result"] is False


def test_a_suspended_row_is_not_relabelled_by_this_key():
    """`suspended` already says "no result reported" in its own right.  Folding
    it in here would double-count it and, worse, make the key mean two things."""
    data = _format_event(_event("suspended", 300))

    assert data["started_without_result"] is False
    assert data["status"] == "suspended"


# ── THE BOUNDARY, ON THE PURE PREDICATE ────────────────────────────────────
#
# The exact edge is tested here rather than through the formatter because the
# formatter reads the wall clock, so "exactly at the grace" is unrepresentable
# there: microseconds elapse between building the row and serving it.  Asserting
# it against a real clock would be a flake, and padding it to make it pass would
# test the pad.


def test_the_boundary_is_strict():
    now = datetime(2026, 9, 14, 3, 24, 9, tzinfo=timezone.utc)
    exactly_at_grace = now - UPCOMING_GRACE

    assert started_without_result("scheduled", exactly_at_grace, now) is False
    assert (
        started_without_result(
            "scheduled", exactly_at_grace - timedelta(seconds=1), now
        )
        is True
    )


def test_a_missing_kickoff_cannot_fire_the_flag():
    now = datetime(2026, 9, 14, 3, 24, 9, tzinfo=timezone.utc)

    assert started_without_result("scheduled", None, now) is False


def test_a_naive_kickoff_fails_closed_instead_of_raising():
    """FOUND BY GIVING THE PREDICATE ITS FIRST CALLER.

    A tz-naive `commence_time` against a tz-aware `now` RAISES rather than
    compares.  Nothing could discover that while `started_without_result` had
    zero consumers — every input it had ever seen was one a test chose.  Serving
    it from `_format_event` put real rows through it and two fixtures in
    `test_events_list_blank_cards_3016` went straight to TypeError, which on the
    wire is a 500 on the event payload, not a wrong flag.

    False, not a coerced UTC reading: an uncomparable time cannot prove the
    clock ran out, and inventing an offset the row never stated could move a
    card by hours.  Same rule, same reason, as `lifecycle.live_start_satisfied`.
    """
    now = datetime(2026, 9, 14, 3, 24, 9, tzinfo=timezone.utc)
    naive_kickoff = datetime(2026, 9, 14, 1, 15, 0)

    assert started_without_result("scheduled", naive_kickoff, now) is False


def test_a_naive_kickoff_does_not_break_the_payload():
    """The same defect at the surface it actually reached."""
    row = _event("scheduled", SPECIMEN_MINUTES_PAST_KICKOFF)
    row.commence_time = row.commence_time.replace(tzinfo=None)

    data = _format_event(row)

    assert data["started_without_result"] is False
    assert data["status"] == "scheduled"


# ── THE ONE-CLOCK INVARIANT ────────────────────────────────────────────────


def test_the_formatter_reads_the_clock_exactly_once():
    """`status` and `started_without_result` come from ONE instant.

    Both keys are time-derived and they disagree at the boundary, so two
    `datetime.now()` calls straddling it could serve `scheduled` beside
    `started_without_result: false` from clocks microseconds apart — the exact
    contradiction this ship exists to end.  Counted on the parsed function
    rather than by patching the clock, because the property is "how many times
    is it read", which a patched clock cannot observe without changing it.
    """
    tree = ast.parse(inspect.getsource(_format_event))

    reads = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "now"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "datetime"
    ]

    assert len(reads) == 1, (
        f"_format_event reads the wall clock {len(reads)} times; "
        "every time-derived key in one payload must share one instant"
    )


# ── SURVIVAL: the key is ADDITIVE ──────────────────────────────────────────


def test_the_existing_payload_is_unchanged_around_the_new_key():
    """A formatter that served the new key by dropping or renaming an old one
    would pass every arm above and break every existing client."""
    data = _format_event(_event("scheduled", SPECIMEN_MINUTES_PAST_KICKOFF))

    for key in (
        "id",
        "status",
        "commence_time",
        "completed_at",
        "home_team",
        "away_team",
        "home_score",
        "away_score",
        "sport",
        "sport_name",
    ):
        assert key in data, f"_format_event stopped serving {key!r}"


def test_every_surface_behind_the_shared_formatter_gets_the_key():
    """REACH.  The key is added once, in the formatter the detail route, search,
    My Stuff, team rails and the league pages all share — not at one call site.

    This asserts the mechanism rather than the count: `_format_event` is the
    single definition, so a later change that special-cased one caller would
    have to fork the formatter to break this.
    """
    source = inspect.getsource(events_module)

    assert source.count('"started_without_result":') == 1
