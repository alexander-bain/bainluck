"""#5043 — an EMPTY served bank is not an UNDATED one, and must not be reported as one.

**The bug.** After a release changes the population fingerprint, the first beat of
the new generation clears the served bank. The builder is careful about this: for an
empty bank it writes ``staged:served_units = 0``, no ``staged:served_at``, and no
``staged:served_reason:unstamped`` — its docstring says ``served_at`` is "Absent, not
zero, when the bank is unstamped", and an empty bank is not an unstamped one.

``build_disclosure`` then collapsed the distinction. ``serving = served_units is not
None`` is ``True`` for ``0``, so an empty bank fell into the branch meaning "a serving
bank that lost its stamp" and returned ``unmeasured("served_at_absent")``. The whole
staged block went unmeasured — taking the rebuild-progress fields with it — for the
entire duration of every post-fingerprint rebuild. That is #5042's cause, and it is
what left the accuracy page's reader with nothing but ``age // interval_s`` to reason
from while the page sat frozen at 22:16:20Z — 7.6 hours and counting as of
2026-09-11T05:51Z, with the publish still ~100 units out.

**Why the one-line fix is forbidden.** ``serving = bool(served_units)`` makes an empty
bank fall through to ``staged_dt = staged_generated_at`` — the durable row's write
time, which advances every beat under the rolling re-stage. That puts a fresh
timestamp on a stale curve, which is exactly #2007 and exactly what CAL-P078's comment
block was written to forbid. So the repair gives the state its own name and keeps
refusing to date it.

**What this suite pins**, in the order it matters:

1. an empty bank is ``served_bank_empty``, never ``served_at_absent``;
2. it is still UNMEASURED and still carries no date — the #2007 hazard is untouched
   even when a fresh ``staged_generated_at`` is sitting right there;
3. the availability floor is unchanged, so nothing renders fresher than before;
4. a genuinely unstamped NON-empty bank still reports ``served_at_absent`` — the two
   reasons stay two facts (gotcha #53), which is the entire point of the repair.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.utils.calibration_staged_disclosure import (
    availability_floor,
    build_disclosure,
)

# A fresh write time, sitting right next to an undatable census. Every test below
# passes this in: if the repair ever starts dating the block from it, that is #2007
# and these assertions are the tripwire.
FRESH_WRITE = datetime(2026, 9, 11, 4, 37, 37, tzinfo=timezone.utc)


def _empty_bank(**over) -> dict:
    """The production shape measured on 2026-09-11: a rebuild 20/128 through.

    Taken from ``calibration:main:phase_ledger`` at the 04:37:37Z beat rather than
    invented, so the fixture cannot drift away from what the builder writes.
    """
    base = {
        "staged:served_units": 0,
        "staged:served_drifted": 0,
        "staged:served_drift_uncheckable": 0,
        "staged:units_banked": 20,
        "staged:units_this_beat": 7,
        "staged:units_drifted": 10,
        "staged:units_drift_checkable": 15,
        "staged:units_drift_uncheckable": 5,
        # No ``staged:served_at`` — the builder correctly omits it for an empty bank.
    }
    base.update(over)
    return base


class TestAnEmptyBankIsItsOwnState:
    def test_it_is_not_reported_as_an_undated_bank(self):
        block = build_disclosure(
            ledger_stages=_empty_bank(), staged_generated_at=FRESH_WRITE
        )

        assert block["measured"] is False
        assert block["reason"] == "served_bank_empty"
        assert block["reason"] != "served_at_absent"

    def test_it_still_refuses_to_date_the_census(self):
        """The #2007 hazard, asserted against the timestamp that would cause it."""
        block = build_disclosure(
            ledger_stages=_empty_bank(),
            staged_generated_at=FRESH_WRITE,
            now=datetime(2026, 9, 11, 5, 30, 0, tzinfo=timezone.utc),
        )

        # Two keys and nothing else: no date, no age, nothing derived from the
        # durable row's write time.
        assert set(block) == {"measured", "reason"}
        assert "staged_at" not in block
        assert "staged_age_s" not in block

    def test_the_availability_floor_does_not_move(self):
        """Naming the state must not let anything render fresher than it did."""
        block = build_disclosure(
            ledger_stages=_empty_bank(), staged_generated_at=FRESH_WRITE
        )

        assert availability_floor(block) == "stale"


class TestTheTwoReasonsStayTwoFacts:
    """An empty bank and an unstamped one are different failures (gotcha #53)."""

    def test_a_non_empty_bank_with_no_stamp_is_still_served_at_absent(self):
        block = build_disclosure(
            ledger_stages=_empty_bank(
                **{
                    "staged:served_units": 128,
                    "staged:served_drifted": 115,
                }
            ),
            staged_generated_at=FRESH_WRITE,
        )

        assert block["measured"] is False
        assert block["reason"] == "served_at_absent"

    def test_a_stamped_non_empty_bank_is_still_measured(self):
        """The healthy path is untouched — the repair is not a blanket refusal."""
        block = build_disclosure(
            ledger_stages=_empty_bank(
                **{
                    "staged:served_units": 128,
                    "staged:served_drifted": 0,
                    "staged:served_at": 1_788_981_761,
                }
            ),
            staged_generated_at=FRESH_WRITE,
            now=datetime.fromtimestamp(1_788_981_861, tz=timezone.utc),
        )

        assert block["measured"] is True
        # Dated from the SERVED census, not from the durable row's write time.
        assert block["staged_age_s"] == 100

    def test_an_absent_served_units_gauge_is_not_an_empty_bank(self):
        """A gauge the beat never wrote is not a bank with nothing in it.

        ``_int_gauge`` returns ``None`` for an absent key, which turns ``serving``
        off entirely and routes the read down the builder-bank path. Pinned so the
        ``== 0`` test added for #5043 is never loosened to a falsy check, which
        would swallow this case.
        """
        stages = _empty_bank()
        del stages["staged:served_units"]

        block = build_disclosure(
            ledger_stages=stages,
            staged_generated_at=FRESH_WRITE,
            now=datetime(2026, 9, 11, 5, 30, 0, tzinfo=timezone.utc),
        )

        assert block.get("reason") != "served_bank_empty"
