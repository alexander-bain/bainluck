"""#5603 liveness half — a fight card stops wearing the LIVE pill ten hours early.

═══ THE DEFECT ═══

Read on production 2026-09-12 13:48Z, `GET /api/feed` served this concept card:

    name       "Fight Night: Silva vs Delgado"
    status     live                 ← the pulsing red ● LIVE pill
    headline   "Live"
    start_date 2026-09-12T23:45:00Z ← its own main event, TEN HOURS away

The card contradicts itself inside one payload, so it needs no screenshot to
grade. The control in the same feed is the Vuelta concept, correctly live since
08-22.

Cause. A card's token is a DATE (`event_commence_token` → `YYMONDD`), so every
bout on one UTC calendar day is one card, and `combat_status` opens the live
window at the card's first bout (#4505). The callers spelled that first bout
``bouts[0]`` — the earliest row in the token, in whatever state it is in. The
2026-09-12 MMA token held, ahead of the UFC card proper (16:00Z → 23:45Z):

    suspended  01:25Z  Neemias Santana vs Shawn Marcos Da Silva   (15308196)
    suspended  02:30Z  Vincius Pires vs Rafael Pereira            (15308197)
    suspended  10:00Z  Kennedy Rayomba vs Andrej Kalasnik         (15308904)

`earliest` came out 01:25Z, so the pill lit at 01:25Z for a card whose first
fight is at 16:00Z. Production carried ZERO live combat bouts at the time of the
read (36 scheduled, 6 suspended across MMA and boxing). Boxing's 26SEP12 token
had the same shape — three suspended bouts (01:30Z/02:25Z/03:00Z) in front of a
18:00Z card — so this was two cards, not one specimen.

═══ WHY THE OBVIOUS FILTER IS WRONG ═══

`_list_event_bouts` documents itself as returning "scheduled/live bouts" while
its query filters on nothing but `commence_time` — so the tempting repair is to
make the code match its own docstring and keep only `scheduled`/`live`.

That trades a false positive for a false negative. Once the prelims FINISH they
are `completed`, and the earliest surviving bout is in the future — the card
would drop to `upcoming` while the main card is on air. A card's window is the
span of the fights that actually happen, which includes the ones already fought.
So the rule here is a DENY-list of called-off statuses, and
`test_a_card_mid_run_with_finished_prelims_is_still_live` is the guard that
fails if anyone later "simplifies" it into an allow-list.

═══ SCOPE ═══

This fixes a window set by a bout that will not be fought. It does NOT fix
same-day cross-promotion grouping — a *completed* early bout from another
promotion still shares the date token and still drags the window back. That is
the key itself (#5602, lane1 under D35) and is deliberately untouched.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils.event_combat import card_status_span, combat_status


def bout(hour, status="scheduled", *, day=12, minute=0):
    """One bout on the 2026-09-12 token, as the callers hand them over."""
    return SimpleNamespace(
        commence_time=datetime(2026, 9, day, hour, minute, tzinfo=timezone.utc),
        status=status,
    )


# The production card, in the order `bout_order_key` sorts it.
SPECIMEN = [
    bout(1, "suspended", minute=25),
    bout(2, "suspended", minute=30),
    bout(10, "suspended"),
    bout(16),  # the UFC card proper
    bout(18),
    bout(23, minute=45),  # main event
]


class TestTheSpecimen:
    def test_the_span_skips_the_three_suspended_bouts(self):
        first, last = card_status_span(SPECIMEN)
        assert first == datetime(2026, 9, 12, 16, tzinfo=timezone.utc)
        assert last == datetime(2026, 9, 12, 23, 45, tzinfo=timezone.utc)

    def test_the_card_reads_upcoming_at_the_hour_it_served_live(self):
        """13:48Z, the minute of the production read."""
        now = datetime(2026, 9, 12, 13, 48, tzinfo=timezone.utc)
        first, last = card_status_span(SPECIMEN)
        assert combat_status(last, now, first) == "upcoming"

    def test_and_it_really_did_say_live_before_this(self):
        """The un-filtered pair is the defect: this is what shipped."""
        now = datetime(2026, 9, 12, 13, 48, tzinfo=timezone.utc)
        unfiltered_first = SPECIMEN[0].commence_time
        unfiltered_last = SPECIMEN[-1].commence_time
        assert combat_status(unfiltered_last, now, unfiltered_first) == "live"

    def test_the_pill_still_lights_when_the_card_actually_starts(self):
        now = datetime(2026, 9, 12, 16, 1, tzinfo=timezone.utc)
        first, last = card_status_span(SPECIMEN)
        assert combat_status(last, now, first) == "live"


class TestTheFalseNegativeGuard:
    def test_a_card_mid_run_with_finished_prelims_is_still_live(self):
        """The reason this is a deny-list and not an allow-list.

        Filtering to `scheduled`/`live` — the spelling `_list_event_bouts`'
        docstring suggests — makes this test fail: at 21:00Z the only
        non-completed bouts are at 22:00Z and 23:45Z, both future, so the card
        would go dark with the main card on air.
        """
        card = [
            bout(18, "completed"),
            bout(19, "completed"),
            bout(20, "live"),
            bout(22),
            bout(23, minute=45),
        ]
        now = datetime(2026, 9, 12, 21, tzinfo=timezone.utc)
        first, last = card_status_span(card)
        assert first == datetime(2026, 9, 12, 18, tzinfo=timezone.utc)
        assert combat_status(last, now, first) == "live"

    @pytest.mark.parametrize("status", ["completed", "closed", "live", "scheduled"])
    def test_a_bout_that_happens_is_never_dropped_from_the_span(self, status):
        card = [bout(18, status), bout(23, minute=45)]
        first, _ = card_status_span(card)
        assert first == datetime(2026, 9, 12, 18, tzinfo=timezone.utc)


class TestTheVocabularyIsOpen:
    @pytest.mark.parametrize(
        "status", ["suspended", "SUSPENDED", " Suspended ", "postponed", "cancelled"]
    )
    def test_called_off_spellings_leave_the_span(self, status):
        card = [bout(1, status), bout(16), bout(23, minute=45)]
        first, _ = card_status_span(card)
        assert first == datetime(2026, 9, 12, 16, tzinfo=timezone.utc)

    @pytest.mark.parametrize("status", ["in_progress", "delayed", "", None, "weird"])
    def test_an_unknown_status_counts_as_a_real_bout(self, status):
        """`events.status` is written by several providers and is an open set.

        An unknown value must keep today's behaviour — count as a bout — rather
        than silently vanish from the card's window. An allow-list would drop it.
        """
        card = [bout(1, status), bout(16), bout(23, minute=45)]
        first, _ = card_status_span(card)
        assert first == datetime(2026, 9, 12, 1, tzinfo=timezone.utc)


class TestDegenerateInput:
    def test_every_bout_called_off_keeps_the_full_span(self):
        """Rather than invent a window from nothing.

        Boxing's 26SEP11 token on production was exactly this — two suspended
        bouts and nothing else. It is past its main event, so `combat_status`'
        trailing arm settles it either way; what matters is that the pair is not
        `(None, None)`.
        """
        card = [bout(22, "suspended", day=11), bout(23, "suspended", day=11)]
        first, last = card_status_span(card)
        assert first == datetime(2026, 9, 11, 22, tzinfo=timezone.utc)
        assert last == datetime(2026, 9, 11, 23, tzinfo=timezone.utc)
        now = datetime(2026, 9, 12, 13, 48, tzinfo=timezone.utc)
        assert combat_status(last, now, first) == "settled"

    def test_no_bouts_at_all(self):
        assert card_status_span([]) == (None, None)

    def test_bouts_without_a_commence_are_not_a_span(self):
        assert card_status_span(
            [SimpleNamespace(commence_time=None, status="scheduled")]
        ) == (
            None,
            None,
        )

    def test_a_stampless_bout_does_not_poison_a_real_span(self):
        card = [
            SimpleNamespace(commence_time=None, status="scheduled"),
            bout(16),
            bout(20),
        ]
        first, last = card_status_span(card)
        assert first == datetime(2026, 9, 12, 16, tzinfo=timezone.utc)
        assert last == datetime(2026, 9, 12, 20, tzinfo=timezone.utc)

    def test_the_pair_does_not_depend_on_the_callers_sort(self):
        """min/max, not `[0]`/`[-1]`.

        The callers sort the FULL list by `bout_order_key`; dropping rows out of
        the middle must not make the answer depend on which ones went.
        """
        assert card_status_span(list(reversed(SPECIMEN))) == card_status_span(SPECIMEN)


class TestTheClockIsNotBranchedOn:
    def test_the_specimen_verdict_holds_at_every_minute_before_the_first_bout(self):
        first, last = card_status_span(SPECIMEN)
        start = datetime(2026, 9, 12, tzinfo=timezone.utc)
        for minutes in range(0, 16 * 60, 17):
            now = start + timedelta(minutes=minutes)
            assert combat_status(last, now, first) == "upcoming"
