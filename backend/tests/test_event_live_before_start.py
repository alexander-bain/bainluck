"""#1779 family — an event may not render LIVE before its own commence_time.

THE SPECIMEN, from production on 2026-08-17 (queue 364). Four MLB events served
``status: "live"``, with live scores, while their own ``commence_time`` sat 40–51
hours in the FUTURE:

    15199901  Detroit @ Pittsburgh    commence 2026-08-19 16:35Z   live  0–5
    15199882  San Diego @ NY Mets     commence 2026-08-19 17:10Z   live  2–1
    15200229  Arizona @ Boston        commence 2026-08-19 20:10Z   live  4–0
    15199886  Miami @ Philadelphia    commence 2026-08-19 22:05Z   live  4–1

Each is a duplicate: the same game also exists at its correct Aug-17 time with the
same ``espn_id`` and the same score. So there are two defects stacked, and they need
separating, because only one of them is safely fixable today.

WHY THE DUPLICATE IS NOT FIXED HERE
-----------------------------------

``_merge_duplicate_events_impl`` cannot see these pairs: its candidate SQL requires
``ABS(a.commence_time - b.commence_time) < 21600`` (6h) before the shared-id check
ever runs, and these are 45–51h apart. The tempting fix — drop the window when the
rows share a provider id, since ruling 048 calls a shared id identity — is
**measurably unsafe**. Production holds ``espn_id`` values shared by genuinely
DIFFERENT games:

    401816142  Dodgers @ Yankees  ...and...  Dodgers @ **Mets**
    401882919  Real Sociedad @ Real Madrid  ...and...  Real **Betis** @ Real Sociedad
    401856667  Ohio State @ Texas  ...and...  **Texas State** @ Texas

and same-name pairs 42–44h apart (Blue Jays @ Red Sox Jul 24 / Jul 26; White Sox @
Orioles Jun 29 / Jul 1) are the ordinary SERIES shape — two real games — which is
the exact specimen ``event_merge_invariant``'s own docstring cites as the thing a
window-widening deletes. Widening the window would trade a display bug for a
destroyed game. That finding goes to Alex; it is a ruling-048 arm-A question.

WHAT IS FIXED HERE
------------------

The single-row contradiction, which needs no pairing to detect and no delete to
repair: **a row claiming ``live`` before its own start time is not live.** The
invariant was already written and already correct in ``app/utils/lifecycle`` —
"one canonical rule for every surface that labels a card/event/concept live" —
and ``enforce_live_requires_start`` had **zero callers**. A rule with no consumer
is a document, which is the same shape as q363's #1924/#1933 finding two windows
running.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.lifecycle import (
    EVENT_NOT_STARTED,
    enforce_live_requires_start,
    served_event_status,
)

NOW = datetime(2026, 8, 18, 0, 41, tzinfo=timezone.utc)


class TestTheProductionSpecimen:
    """The four rows, by their measured values."""

    @pytest.mark.parametrize(
        "event_id,commence,score",
        [
            (15199901, datetime(2026, 8, 19, 16, 35, tzinfo=timezone.utc), (0, 5)),
            (15199882, datetime(2026, 8, 19, 17, 10, tzinfo=timezone.utc), (2, 1)),
            (15200229, datetime(2026, 8, 19, 20, 10, tzinfo=timezone.utc), (4, 0)),
            (15199886, datetime(2026, 8, 19, 22, 5, tzinfo=timezone.utc), (4, 1)),
        ],
    )
    def test_none_of_them_may_be_served_as_live(self, event_id, commence, score):
        assert served_event_status("live", commence, NOW) == EVENT_NOT_STARTED

    def test_the_gap_really_is_the_40_to_51_hour_band(self):
        """Guard the specimen's own premise, so a typo cannot make it vacuous."""
        gaps = [
            (datetime(2026, 8, 19, 16, 35, tzinfo=timezone.utc) - NOW),
            (datetime(2026, 8, 19, 22, 5, tzinfo=timezone.utc) - NOW),
        ]
        assert 39 < gaps[0] / timedelta(hours=1) < 40
        assert 45 < gaps[1] / timedelta(hours=1) < 46

    def test_the_correctly_dated_twin_is_untouched(self):
        """The same game at its real Aug-17 time IS live and must stay live.

        A guard that fixes the false positive by suppressing the true one has
        moved the bug, not removed it (gotcha #43's both-directions rule).
        """
        real = datetime(2026, 8, 17, 19, 0, tzinfo=timezone.utc)
        assert served_event_status("live", real, NOW) == "live"


class TestTheVocabularyIsTheEventsOne:
    def test_the_downgrade_is_scheduled_not_upcoming(self):
        """``upcoming`` is the CARD vocabulary; an events row has no such state.

        Emitting it would hand every client a status it does not parse — a
        different bug wearing the fix's clothes.
        """
        future = NOW + timedelta(hours=40)
        assert served_event_status("live", future, NOW) == "scheduled"
        assert enforce_live_requires_start("live", future, NOW) == "upcoming"

    @pytest.mark.parametrize("status", ["scheduled", "completed", "closed", None, ""])
    def test_every_other_status_passes_through_verbatim(self, status):
        """Only ``live`` is ever rewritten. This must not become a classifier."""
        future = NOW + timedelta(hours=40)
        assert served_event_status(status, future, NOW) == status

    def test_an_unknown_start_time_is_not_live(self):
        """Unknown time authority never establishes live — the module's own rule."""
        assert served_event_status("live", None, NOW) == EVENT_NOT_STARTED

    def test_a_naive_commence_time_does_not_raise(self):
        """A tz-naive DB value must fail closed, not 500 the event page."""
        naive = datetime(2026, 8, 19, 16, 35)
        assert served_event_status("live", naive, NOW) == EVENT_NOT_STARTED


class TestThePredicateHasConsumers:
    """The whole failure was a correct rule nobody called.

    So the guard is not "does the function work" — it did — but "is it wired".
    Asserted against the shipping module source, because an import that gets
    dropped in a refactor restores the exact silence this repairs.
    """

    PUBLIC_SURFACES = ("app/routes/events.py", "app/routes/teams.py")

    def test_the_public_event_serializers_route_through_it(self):
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[1]
        for rel in self.PUBLIC_SURFACES:
            source = (root / rel).read_text()
            assert "served_event_status" in source, f"{rel} does not consume the invariant"

    def test_admin_surfaces_deliberately_do_not(self):
        """An operator debugging a contradictory row must SEE the contradiction.

        Repairing it on the admin read would hide the very rows this queue found.
        """
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[1]
        source = (root / "app/routes/admin_events.py").read_text()
        assert "served_event_status" not in source
