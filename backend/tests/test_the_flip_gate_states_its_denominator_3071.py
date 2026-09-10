"""A permitted flip says what its seven days were counted on. #3071.

Pillar: TRUTH. Rides the authority lane's ship (*every game exists on the site
before any market lists it; nothing goes blank when ESPN does*) — it is the
substrate of program steps 6/7, not a ship of its own.

## what this is NOT

**It is not #3071's ruling and it does not narrow the gate by one game.** The
minimum denominator for a flip is unruled; `alex-inbox/authority-016` puts it to
Alex as question A with a stated default (A1 — a floor below which a day scores
`NO-SCORE` and the streak pauses) and it has been unanswered since 2026-09-04.
Nothing here compares a coverage figure to a threshold, because choosing the
threshold is the ruling. `TestTheBooleanIsUntouched` asserts that in both
directions, so this file cannot become the ruling by accident later.

#3071's own stated catching test is *"a row with a 1-game denominator must not
report `identity.governing.gate == MEETS`"*. **That test cannot be written until
the ruling lands, and pretending otherwise would be writing the ruling.** Its
honest cousin is here instead: a 1-game denominator's `True` must SAY it is a
1-game denominator.

## why a `True` has to carry this

`flip_permitted`'s docstring spends fifteen lines arguing that a bare `False` is
a failure — six different "no"s prescribe six different pieces of work, and a
reader needs to know which one they are in. A `True` that will not say what it
was counted on is that same failure with the sign flipped, and it is the more
expensive one.

Measured in production on 2026-09-09 (`GET /api/admin/statpal/authority-agreement`,
pass 08:04:01Z), five days after #3071 was filed and unmoved:

| sport | both | ours_only | `ours_covered_pct` | statpal_only inside our span | gate |
|---|---:|---:|---:|---:|---|
| `americanfootball_nfl` | 321 | 0 | 100.0 | 0 | MEETS |
| `basketball_nba` | 41 | 0 | 100.0 | **386** | MEETS |
| `icehockey_nhl` | 32 | 0 | 100.0 | **106** | MEETS |

Both thin sports reach seven consecutive days on **2026-09-11**, two days after
this file was written, on 3.4% and 2.3% of seasons that have not started. The
sentence they would have returned was *"D50's measured half is met"*, full stop.
True, and silent about the only fact a person deciding needs. Since #3473 that
sentence is also read by a machine: `espn_sync._decide_failovers` calls this gate
to decide the automatic ESPN-outage failover.
"""

from __future__ import annotations

import pytest

from app.config.authority_by_sport import _counted_on, flip_permitted
from app.utils.authority_streak import REQUIRED_STREAK_DAYS
from tests.authority_specimens import register_specimen

#: A CONSTRUCTED sport with a shadow stamper, a scheduled discovery pass and a
#: governing number — i.e. one that can actually reach the `True` branch.
#:
#: It is no longer a real sport, and that is the point (#4588). It was
#: `basketball_nba` until the NBA shipped as the second ruled release (#4493),
#: then `icehockey_nhl`, and the NHL is the third release under #2867 — after
#: which no real sport reaches this branch at all. The warning that used to sit
#: here said this file "cannot be fixed by moving a line again" and told whoever
#: hit it "do not discover this at merge time". This is that migration, made
#: before the release rather than during it.
THIN = "flipgate_clock_specimen"
#: `COMPLETE` was `americanfootball_nfl` until D104 = A4 (2026-09-09, #4417) put
#: football in `FLIP_RULED_WITHOUT_STREAK`, where it returns before the seven-day
#: branch and can no longer be the specimen for what that branch's sentence says.
COMPLETE = THIN

#: THE TWO NAMES HOLD THE SAME SPORT, AND THAT IS NOT AN OVERSIGHT.
#:
#: What they distinguish is the FIXTURE, not the sport — `both` and `denominator`
#: come from `_days`, so "thin" means a 41-of-1,208 day and "complete" a
#: 321-of-321 one, and every assertion here is about the sentence those numbers
#: produce. Keeping both names keeps the intent legible; one specimen serves both
#: because the branch, not the sport, is what is under test.


@pytest.fixture(autouse=True)
def _clock_specimen(monkeypatch):
    """Register the constructed sport for every test in this file.

    Autouse because every test here calls `flip_permitted` on the specimen, so
    naming it in eleven signatures would be noise. The sibling files register
    per-test instead, purely so a test that consults the specimen says so — not
    because autouse is unsafe there; a mutant proved it is not (#4588).

    Safe in any case: `register_specimen` only rebinds modules named `app.*`,
    and a census reading this test module's own import would never see it.
    """
    register_specimen(monkeypatch, THIN)


def _days(both, denominator, *, n=REQUIRED_STREAK_DAYS, state="MEETS", fields=True):
    """`n` consecutive ledger days, newest last, as `fold_day` writes them.

    `both` may be an int (steady) or a sequence of length `n` (varying).
    """
    boths = [both] * n if isinstance(both, int) else list(both)
    assert len(boths) == n
    out = []
    for i, b in enumerate(boths):
        day = {"day": f"2026-09-{5 + i:02d}", "state": state}
        if fields:
            day["both"] = b
            day["denominator"] = denominator
        out.append(day)
    return out


class TestThePermissionStatesWhatItWasCountedOn:
    """The 2026-09-11 sentence, for the two sports that will produce it."""

    def test_the_thin_sport_names_its_denominator(self):
        ok, why = flip_permitted(THIN, _days(41, 1208))
        assert ok is True
        assert "counted over 41 of the 1,208 fixtures" in why
        assert "(3.4%)" in why

    def test_the_complete_sport_names_its_denominator_too(self):
        """Unconditional, not triggered by a threshold.

        Disclosure that only appears when a number looks bad is a threshold
        wearing a different hat — and the reader who most needs the figure is the
        one about to flip a sport they believe is complete.
        """
        ok, why = flip_permitted(COMPLETE, _days(321, 321))
        assert ok is True
        assert "counted over 321 of the 321 fixtures" in why
        assert "(100.0%)" in why

    def test_it_names_the_open_ruling_every_time(self):
        for sport, days in ((THIN, _days(41, 1208)), (COMPLETE, _days(321, 321))):
            _, why = flip_permitted(sport, days)
            assert "UNRULED (#3071)" in why
            assert "this gate applies no floor" in why

    def test_the_one_game_denominator_says_it_is_one_game(self):
        """#3071's catching test, in the only form available before the ruling.

        The issue asks that a 1-game denominator not report `MEETS`. Making that
        true is the ruling. Making it UNMISSABLE is not, and is this file.
        """
        ok, why = flip_permitted(THIN, _days(1, 1206))
        assert ok is True
        assert "counted over 1 of the 1,206 fixtures" in why
        assert "(0.1%)" in why


class TestItReadsTheStreaksOwnDays:
    """Not the whole retained ledger, and not only the last day."""

    def test_a_denominator_that_grew_is_reported_as_a_range(self):
        """The third candidate option in #3071 turns on exactly this difference.

        A streak banked while the denominator climbed from 3 to 41 is not the
        same evidence as seven days at 41, and collapsing both to "41" would hide
        the distinction the ruling may end up resting on.
        """
        _, why = flip_permitted(THIN, _days([3, 7, 12, 20, 30, 38, 41], 1208))
        assert "counted over 3–41 of the 1,208 fixtures" in why
        assert "(0.2–3.4%)" in why
        assert "varying across its 7 recorded days" in why

    def test_a_steady_denominator_says_so_rather_than_printing_a_range(self):
        _, why = flip_permitted(THIN, _days(41, 1208))
        assert "on every day of the streak" in why
        assert "–" not in why.split("The minimum denominator")[0]

    def test_days_before_the_streak_began_are_not_counted_in(self):
        """A retained day that did not clear was not part of what was permitted.

        The ledger keeps more days than the streak spans. A `BELOW` day sitting
        before the streak restarts it, so its denominator describes a different
        measurement than the one being permitted, and including it would report a
        range that never happened.
        """
        older = _days(2, 1208, n=3, state="BELOW")
        older[-1]["day"] = "2026-09-04"
        older[0]["day"], older[1]["day"] = "2026-09-02", "2026-09-03"
        _, why = flip_permitted(THIN, older + _days(41, 1208))
        assert "counted over 41 of the 1,208 fixtures" in why
        assert "on every day of the streak" in why
        assert "2" not in why.split("counted over ")[1].split(" of the")[0]


class TestItRefusesToInventANumberItDoesNotHave:
    def test_a_ledger_day_without_the_fields_says_so(self):
        """Absent is not zero (gotcha #53).

        A day written before `day_entry` carried these fields cannot be
        described, and reporting it as "0 of 0" would be a measurement nobody
        took. The permission still stands — this is disclosure, not a gate.
        """
        ok, why = flip_permitted(THIN, _days(41, 1208, fields=False))
        assert ok is True
        assert "do not record what they were counted on" in why
        assert "counted over" not in why

    def test_a_generator_is_not_consumed_out_from_under_the_disclosure(self):
        """`compute_streak` reads the iterable first; this used to be the bug.

        The parameter is annotated `Iterable`. Handed a generator, a second read
        sees an empty sequence and the gate would report "its days do not record
        what they were counted on" about a ledger that records it perfectly well
        — a false statement produced by the reading, not by the data.
        """
        days = _days(41, 1208)
        _, from_list = flip_permitted(THIN, days)
        _, from_generator = flip_permitted(THIN, (d for d in days))
        assert from_generator == from_list
        assert "counted over 41 of the 1,208 fixtures" in from_generator


class TestTheBooleanIsUntouched:
    """This file must never become the ruling. Both directions asserted."""

    @pytest.mark.parametrize(
        "both,denominator",
        [(1, 1206), (41, 1208), (321, 321), (1206, 1206)],
    )
    def test_no_coverage_figure_changes_the_verdict(self, both, denominator):
        """The table from #3071's body: one game and a whole season both pass.

        That is the defect the issue reports and it is still true here, on
        purpose. If a later change makes one of these `False`, the ruling has
        landed and this test should be rewritten to match it — not deleted.
        """
        ok, _ = flip_permitted(THIN, _days(both, denominator))
        assert ok is True

    def test_a_short_streak_is_still_refused_and_says_nothing_about_coverage(self):
        """The disclosure belongs to the `True` branch alone.

        A five-day streak's problem is that it is five days. Telling that reader
        about a denominator would bury the reason they were refused under a
        number that did not refuse them.
        """
        ok, why = flip_permitted(THIN, _days(41, 1208, n=5))
        assert ok is False
        assert "5/7" in why
        assert "counted over" not in why
        assert "#3071" not in why

    def test_a_sport_refused_before_the_streak_is_read_is_unchanged(self):
        ok, why = flip_permitted("tennis_singles", _days(41, 1208))
        assert ok is False
        assert "MEASUREMENT POPULATION" in why
        assert "#3071" not in why


class TestTheHelperOnItsOwn:
    """`_counted_on` is pure, so the awkward shapes are cheap to pin here."""

    def test_an_empty_streak_window_reports_the_absence(self):
        assert "do not record" in _counted_on([], {"since": None, "through": None})

    def test_the_upper_bound_holds_even_though_no_caller_can_reach_it(self):
        """`through` is unreachable-as-a-limit through `flip_permitted` today.

        `compute_streak` sets `as_of` to the LAST day in the ledger, so no day
        can ever sit after `through` and the `<= through` clause never excludes
        anything — a mutant that deletes it survives the whole end-to-end band,
        which is how it was found. The clause is not redundant, it is unreached:
        `_counted_on` takes the streak as a parameter and owes its contract to
        any caller, not only to the one that exists. Pinned here rather than
        deleted, because deleting it would make a future streak that ends before
        the ledger does silently report days it never cleared.
        """
        days = [
            {"day": "2026-09-05", "both": 41, "denominator": 1208},
            {"day": "2026-09-06", "both": 41, "denominator": 1208},
            {"day": "2026-09-07", "both": 900, "denominator": 1208},
        ]
        out = _counted_on(days, {"since": "2026-09-05", "through": "2026-09-06"})
        assert "counted over 41 of the 1,208 fixtures" in out
        assert "900" not in out

    def test_a_zero_denominator_does_not_divide(self):
        """A denominator of zero is not a crash and not a percentage.

        `both` and `denominator` come off a stored row; nothing guarantees the
        row is sane, and a `ZeroDivisionError` inside the flip gate would take
        out the ESPN-outage failover that calls it (#3473).
        """
        out = _counted_on(
            [{"day": "2026-09-05", "both": 0, "denominator": 0}],
            {"since": "2026-09-05", "through": "2026-09-05"},
        )
        assert "counted over 0 of the 0 fixtures" in out
        assert "%" not in out
