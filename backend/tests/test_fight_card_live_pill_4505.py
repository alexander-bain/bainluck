"""#4505 — a fight card wears the live pill while people are fighting, and not otherwise.

`combat_status` opened the live window a fixed EIGHT HOURS before a card's LATEST
bout. That is an approximation of "the prelims must have started by now", and it is
only ever as good as the spread between the card's first bout and its last.

The specimen is `event:ufc:26sep10` (Renato Moicano vs Brian Ortega). Its ten bouts
are all stamped `2026-09-10 00:00:00+00` — the spread is ZERO — so `latest - 8h` put
the pulsing red `● LIVE` pill on the card at 16:00Z on 09-09. #4505 photographed it
badged Live at 21:57Z on 09-09, two hours before its own served `start_date`.

Third member of the class fixed in F1 by #4433 and in cycling by #4449, and it is the
same fix: the window is the event, not a proximity band around it.

Census behind the numbers below (production db-query, 2026-09-10, every combat card
commencing in [now-10d, now+30d], grouped by card day):

    2026-09-10  mma  10 bouts  00:00 -> 00:00  spread  0.00h   <- the specimen
    2026-09-09  mma   8 bouts  00:12 -> 05:20  spread  5.13h
    2026-09-05  mma  33 bouts  16:00 -> 23:20  spread  7.33h

The 09-05 row is why the old rule survived as long as it did: an 8h lead on 23:20
lands at 15:20, 40 minutes before the real first bout. The rule was never right, it
was just close on the cards with a full-length spread.

Gotcha #44: every clock in this file is an OFFSET from a fixed `NOW`. Nothing here
reads the wall clock, so no assertion can swing with the time of day it runs at.
"""

import inspect
from datetime import datetime, timedelta, timezone

from app.utils.event_combat import combat_status

# The specimen's own served start: ten bouts, all at midnight UTC.
CARD_26SEP10 = datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc)


class TestTheSpecimenStopsWearingThePillEarly:
    """`event:ufc:26sep10`, the card #4505 was filed from."""

    def test_the_photographed_moment_is_no_longer_live(self):
        """21:57Z on 09-09 — the exact clock in the issue. Under the old rule this
        returned "live" because 00:00Z minus eight hours is 16:00Z."""
        now = datetime(2026, 9, 9, 21, 57, tzinfo=timezone.utc)
        assert (
            combat_status(CARD_26SEP10, now, CARD_26SEP10) == "upcoming"
        ), "the card is two hours from its first bout and nobody is fighting"

    def test_the_whole_eight_hour_band_is_gone_not_narrowed(self):
        """Every hour the old rule called live before the card starts."""
        for hours_early in (8, 6, 4, 2, 1):
            now = CARD_26SEP10 - timedelta(hours=hours_early)
            assert (
                combat_status(CARD_26SEP10, now, CARD_26SEP10) == "upcoming"
            ), f"{hours_early}h before the first bout"

    def test_it_goes_live_when_the_fighting_starts(self):
        assert combat_status(CARD_26SEP10, CARD_26SEP10, CARD_26SEP10) == "live"
        for hours_in in (0.5, 2, 5):
            now = CARD_26SEP10 + timedelta(hours=hours_in)
            assert (
                combat_status(CARD_26SEP10, now, CARD_26SEP10) == "live"
            ), f"{hours_in}h into the card"


class TestACardWithARealSpreadIsLiveForItsWholeRun:
    """The 09-09 card: first bout 00:12, main event 05:20. The prelims ARE the card,
    so the pill belongs on it from 00:12 — and it must not wait for the main event,
    which is the failure mode the conservative default deliberately accepts only when
    the first bout is unknown."""

    FIRST = datetime(2026, 9, 9, 0, 12, tzinfo=timezone.utc)
    LAST = datetime(2026, 9, 9, 5, 20, tzinfo=timezone.utc)

    def test_the_prelims_light_the_pill(self):
        for minutes_in in (1, 30, 180):
            now = self.FIRST + timedelta(minutes=minutes_in)
            assert (
                combat_status(self.LAST, now, self.FIRST) == "live"
            ), f"{minutes_in} minutes after the first bout, before the main event"

    def test_the_fifty_two_minutes_the_old_rule_stole(self):
        """`latest - 8h` = 21:20 on 09-08, 52 minutes before the first bout."""
        now = datetime(2026, 9, 8, 23, 50, tzinfo=timezone.utc)
        assert combat_status(self.LAST, now, self.FIRST) == "upcoming"

    def test_the_trailing_arm_is_unchanged(self):
        """A card is not dropped as finished the moment its main event starts — the
        arm that was never wrong, asserted so a later change cannot quietly take it."""
        assert (
            combat_status(self.LAST, self.LAST + timedelta(hours=5), self.FIRST)
            == "live"
        )
        assert (
            combat_status(self.LAST, self.LAST + timedelta(hours=7), self.FIRST)
            == "settled"
        )


class TestTheDefaultUnderClaims:
    """With no first bout known the function falls back to the main event. That is a
    deliberate direction: it waits, rather than claiming a fight that has not happened.
    Same direction as this function's standing "no time -> upcoming"."""

    NOW = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)

    def test_no_earliest_never_lights_the_pill_early(self):
        assert combat_status(self.NOW + timedelta(hours=2), self.NOW) == "upcoming"
        assert combat_status(self.NOW + timedelta(hours=7), self.NOW) == "upcoming"

    def test_no_earliest_still_goes_live_at_the_main_event(self):
        assert combat_status(self.NOW, self.NOW) == "live"
        assert combat_status(self.NOW - timedelta(hours=2), self.NOW) == "live"

    def test_no_time_at_all_is_still_upcoming(self):
        assert combat_status(None, self.NOW) == "upcoming"
        assert combat_status(None, self.NOW, self.NOW) == "upcoming"

    def test_a_naive_datetime_does_not_raise(self):
        """The `TypeError` arm: a tz-naive commence cannot be subtracted from `now`."""
        assert combat_status(datetime(2026, 9, 10, 0, 0), self.NOW) == "upcoming"
        assert (
            combat_status(self.NOW, self.NOW, datetime(2026, 9, 10, 0, 0)) == "upcoming"
        )


class TestBadDataCannotOpenAWindowThatWillNotClose:
    """A first bout LATER than the last is not a schedule, it is a data defect. It must
    not produce a card that stays upcoming while its own last bout is hours past."""

    NOW = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)

    def test_first_after_last_falls_back_to_the_last(self):
        last = self.NOW - timedelta(hours=1)
        impossible_first = self.NOW + timedelta(hours=3)
        assert combat_status(last, self.NOW, impossible_first) == "live"

    def test_first_after_last_still_settles(self):
        last = self.NOW - timedelta(hours=9)
        impossible_first = self.NOW + timedelta(hours=3)
        assert combat_status(last, self.NOW, impossible_first) == "settled"


class TestEveryCallSitePassesTheFirstBout:
    """A fix in `combat_status` that four call sites do not use is inert. Each site is
    asserted by name, because the defect the reader saw was produced by the CALL, not
    by the function — see #4505's payload, served by `list_card_concepts`."""

    def test_the_concept_lister_passes_it(self):
        from app.utils import event_combat

        src = inspect.getsource(event_combat.list_card_concepts)
        assert "earliest = bouts[0].commence_time" in src
        assert 'earliest = kalshi["fights"][0]["commence"]' in src
        # #5603 put a filter between the bout list and the call: the pair is still
        # (first, last) of this card's own bouts, minus the ones that have been
        # called off. CERT-2727 then moved the whole decision behind
        # `card_status_from_bouts`, so what this scan follows is that call and the
        # first-bout term it is handed. The Kalshi-only arm has no statuses to
        # read, so it still hands over the raw `earliest`/`latest` pair — as the
        # FALLBACK, which is the only arm that may reach `combat_status` directly.
        assert "card_status_from_bouts(" in src
        assert "fallback_first=earliest" in src
        assert "fallback_last=latest" in src

    def test_the_adapter_passes_it_at_all_three_of_its_sites(self):
        from app.utils import event_combat

        src = inspect.getsource(event_combat.CombatEventAdapter)
        # Both adapter sites go through the shared entry point, and #1803's
        # authority reads what they produced rather than recomputing it.
        # CERT-2727: `combat_status` must NOT be reachable from this class any
        # other way — an adapter that calls it directly is an adapter that can
        # put the live pill back on a card that is off, which is the exact defect
        # the block was about.
        assert src.count("card_status_from_bouts(") == 2
        assert "combat_status(" not in src
        # And it is the FIRST bout, not the last wearing the name. Passing the
        # first-bout term is not the fix if the value handed over is `bouts[-1]` —
        # that is a mutant the asserts above do not kill, so the fallback arms are
        # named here.
        assert (
            "first_commence = bouts[0].commence_time if bouts else fights[0].commence_time"
            in src
        )
        assert "first_commence = bouts[0].commence_time if bouts else None" in src
        # Per SITE, not as a bare substring: both sites spell the fallback pair
        # `fallback_first=first_commence`, so `... in src` stays true when ONE of
        # them is switched to the last bout. (Measured: that mutant survived this
        # test until the asserts were made site-exact.)
        assert (
            src.count(
                "fallback_first=first_commence,\n"
                "            fallback_last=authoritative_commence,"
            )
            == 1
        )
        assert (
            src.count(
                "bouts, now, fallback_first=first_commence, "
                "fallback_last=latest_commence"
            )
            == 1
        )

    def test_the_first_bout_rule_survives_the_shared_entry_point(self):
        """#4505's property, asserted on VALUES through what the sites actually call.

        Every other test in this class either reads source text or calls
        `combat_status` directly. CERT-2727 put `card_status_from_bouts` between
        the two, so a wrapper that quietly stopped forwarding the first bout —
        `combat_status(last, now, None)` — passed all of them while restoring
        #4505's defect exactly. The live window must open at the FIRST bout, and
        this is the only test in the file that would notice if it did not.
        """
        from datetime import datetime, timezone
        from types import SimpleNamespace

        from app.utils.event_combat import card_status_from_bouts

        def b(hour):
            return SimpleNamespace(
                commence_time=datetime(2026, 9, 12, hour, tzinfo=timezone.utc),
                status="scheduled",
            )

        card = [b(16), b(20), b(23)]
        # An hour after the first bout, seven hours before the main event.
        now = datetime(2026, 9, 12, 17, tzinfo=timezone.utc)
        assert card_status_from_bouts(card, now) == "live"
        # And still closed before the first bout — the other half of #4505.
        early = datetime(2026, 9, 12, 15, tzinfo=timezone.utc)
        assert card_status_from_bouts(card, early) == "upcoming"

    def test_the_span_helper_returns_first_then_last(self):
        """The order the call sites unpack it in.

        Every site above spells `status_first, status_last = card_status_span(...)`
        and then calls `combat_status(status_last, now, status_first)`. A helper
        that returned `(last, first)` would satisfy every string assert in this
        class and invert the live window — so the contract is asserted on values,
        not on source text.
        """
        from datetime import datetime, timezone
        from types import SimpleNamespace

        from app.utils.event_combat import card_status_span

        def b(hour):
            return SimpleNamespace(
                commence_time=datetime(2026, 9, 12, hour, tzinfo=timezone.utc),
                status="scheduled",
            )

        first, last = card_status_span([b(16), b(23)])
        assert first < last

    def test_the_first_bout_is_read_off_an_ascending_sort(self):
        """`bouts[0]` is only the first bout because `_list_event_bouts` sorts each
        group by `bout_order_key`. If that sort goes, this fix inverts."""
        from app.utils import event_combat

        src = inspect.getsource(event_combat)
        assert "group.sort(key=bout_order_key)" in src
