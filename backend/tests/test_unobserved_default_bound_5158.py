"""#5158 — a never-observed row in a sport with no entry is no longer entitled
to its sport's full maximum.

THE DEFECT. `scheduled -> live` promotes on the clock alone, and the net that
should withdraw the claim — `wall_clock_bound_hours` — returned the sport's full
maximum for any sport absent from `UNOBSERVED_MAX_HOURS`. The table held exactly
`{tennis, soccer}`, so a cricket / esports / NPB row that nothing has ever
reported on rode `SPORT_MAX_DURATIONS["default"] = 4.0` and kept a lit LIVE badge,
with no score and no probability, for 4.5 hours (the net fires at `bound + 0.5`).

WHY A DEFAULT AND NOT MORE MEASUREMENT. The table's docstring demands a MEASURED
p99 before a sport may be added, and that bar cannot be met for the sports that
need it: cricket, esports and `icehockey_other` produced fewer than five completed
rows carrying a score in 21 days — the same fact that puts them in this cohort —
and where data existed it is contaminated by gotcha #22. Ruled in by the
orchestrator 2026-09-11 (live/149's question (a)).

The two directions this file has to hold down, because a clamp is exactly the
shape that over-reaches:

  * it must REACH the never-observed rows of any sport with no entry, and
  * it must NOT reach an observed row, a sport whose maximum is already shorter,
    or the three sports deliberately exempted.
"""

import inspect

import pytest

from app.tasks.config import SPORT_MAX_DURATIONS
from app.utils import event_completion as ec
from app.utils.event_completion import (
    UNOBSERVED_DEFAULT_EXEMPT_PREFIXES,
    UNOBSERVED_DEFAULT_KEY,
    UNOBSERVED_MAX_HOURS,
    wall_clock_bound_hours,
)


class TestTheDefaultReachesTheCohortItWasBuiltFor:
    """The rows that were actually stuck on the live board."""

    @pytest.mark.parametrize(
        "sport_key",
        [
            "esports",
            "esports_other",
            "cricket_international_t20",
            "aussierules_aflw",
            "icehockey_other",
        ],
    )
    def test_a_sport_with_no_entry_is_clamped_to_the_default(self, sport_key):
        # 4.0 is SPORT_MAX_DURATIONS["default"], which is what every one of these
        # rides today. Before #5158 this returned 4.0 and the net fired at 4.5h.
        assert wall_clock_bound_hours(sport_key, 4.0, True) == 2.5

    def test_the_production_specimen_baseball_milb_is_clamped(self):
        # MEASURED 2026-09-12: the worst row on the never-observed live board was
        # a `baseball_milb` row 4.5h past commence, entitled to 5.5h (5.0 + 0.5).
        # It rides `baseball`'s 5.0 maximum and is NOT MLB.
        assert wall_clock_bound_hours("baseball_milb", 5.0, True) == 2.5

    def test_npb_is_clamped_too(self):
        # 5 of the 7 never-observed baseball rows measured that night.
        assert wall_clock_bound_hours("baseball_npb", 5.0, True) == 2.5

    def test_the_clamp_actually_shortens_the_lit_badge(self):
        # The reader-facing statement, in the only units that matter: the net
        # fires at `bound + 0.5`, so this is 4.5h of a lit LIVE badge becoming 3.0h.
        before = 4.0 + 0.5
        after = wall_clock_bound_hours("esports", 4.0, True) + 0.5
        assert (before, after) == (4.5, 3.0)


class TestTheDefaultDoesNotOverReach:
    """Every direction the clamp must NOT travel."""

    def test_an_observed_row_is_untouched(self):
        # The whole clamp hangs off this flag. An esports row that something has
        # reported on keeps the full maximum.
        assert wall_clock_bound_hours("esports", 4.0, False) == 4.0

    def test_the_default_can_only_narrow_never_widen(self):
        # `min`, not substitution — a sport whose maximum is already shorter than
        # 2.5 must not be handed extra hours by the new fallback.
        assert wall_clock_bound_hours("darts_pdc", 1.5, True) == 1.5

    @pytest.mark.parametrize(
        "sport_key,sport_max",
        [("golf_pga", 8.0), ("americanfootball_ncaaf", 4.5), ("baseball_mlb", 5.0)],
    )
    def test_an_exempt_sport_keeps_its_full_maximum(self, sport_key, sport_max):
        # These three were reasoned exclusions before #5158 and a blanket default
        # would have silently reversed all of them.
        assert wall_clock_bound_hours(sport_key, sport_max, True) == sport_max

    def test_an_explicit_entry_still_beats_the_default(self):
        # tennis = 3.0 must not be dragged down to 2.5 by the fallback.
        assert wall_clock_bound_hours("tennis_atp", 6.0, True) == 3.0


class TestTheBaseballSplitIsTheWholePoint:
    """`baseball_mlb`, not `baseball` — the finding that shaped the exemption."""

    def test_mlb_is_exempt_but_its_siblings_are_not(self):
        # Same `baseball` prefix, same 5.0 maximum, opposite outcomes. Exempting
        # the whole prefix would have left #5158's worst row unfixed while the
        # fix read as though it were handled.
        assert wall_clock_bound_hours("baseball_mlb", 5.0, True) == 5.0
        assert wall_clock_bound_hours("baseball_npb", 5.0, True) == 2.5
        assert wall_clock_bound_hours("baseball_milb", 5.0, True) == 2.5

    def test_the_exemption_is_the_specific_key_not_the_bare_prefix(self):
        # A mutant that relaxes "baseball_mlb" to "baseball" passes every other
        # test in this file. This is the one that kills it.
        assert "baseball" not in UNOBSERVED_DEFAULT_EXEMPT_PREFIXES
        assert "baseball_mlb" in UNOBSERVED_DEFAULT_EXEMPT_PREFIXES


class TestTheTableItself:
    def test_the_default_is_pinned_from_both_sides(self):
        # A tuned constant needs pinning in both directions: 4.0 is the value
        # this ruling REJECTED (it is the status quo the defect rode on).
        assert UNOBSERVED_MAX_HOURS[UNOBSERVED_DEFAULT_KEY] == 2.5
        assert UNOBSERVED_MAX_HOURS[UNOBSERVED_DEFAULT_KEY] != 4.0
        assert (
            UNOBSERVED_MAX_HOURS[UNOBSERVED_DEFAULT_KEY]
            < SPORT_MAX_DURATIONS["default"]
        )

    def test_rugbyleague_is_pinned_independently_of_the_default(self):
        # MEASURED (rugbyleague_nrl n=22, p99 2.26) and numerically equal to the
        # default today, so it is inert on its own. It exists so that moving the
        # policy default later cannot silently move a measured bound — which
        # means its VALUE is the assertion, not its presence.
        assert UNOBSERVED_MAX_HOURS["rugbyleague"] == 2.5

    def test_the_default_key_is_not_prefix_matched_as_a_sport(self):
        # ⚠️ DOCUMENTARY, NOT A KILLING TEST — said plainly so nobody reads more
        # into it later. Dropping the `p != UNOBSERVED_DEFAULT_KEY` filter is an
        # EQUIVALENT mutant: a sport key beginning with "default" would then match
        # "default" as a prefix and be handed `UNOBSERVED_MAX_HOURS["default"]`,
        # which is the value the fallback returns anyway. Mutation-tested as M6 and
        # it survives all 90 tests, because no input can distinguish the two forms.
        #
        # The filter stays because it keeps the two ideas separate — "default" is a
        # fallback, not a sport — and because it is what makes the behaviour above
        # true by construction rather than by the coincidence that the fallback and
        # the entry share a value. If the default ever stops being a member of this
        # dict, the filter is what keeps the prefix scan honest.
        source = inspect.getsource(ec.wall_clock_bound_hours)
        assert "UNOBSERVED_DEFAULT_KEY" in source
        assert wall_clock_bound_hours("default_league", 4.0, True) == 2.5

    def test_no_prefix_is_both_an_entry_and_an_exemption(self):
        # The table would be expressing a contradiction. Cheap to assert, and it
        # is the invariant the tie-break in the function leans on.
        overlap = set(UNOBSERVED_MAX_HOURS) & set(UNOBSERVED_DEFAULT_EXEMPT_PREFIXES)
        assert overlap == set()

    def test_the_sweep_floor_still_reaches_every_clamped_row(self):
        # `_transition_event_statuses_impl` fetches on
        # `min(min(SPORT_MAX_DURATIONS.values()), min(UNOBSERVED_MAX_HOURS.values()))`.
        # Adding keys must not raise that floor, or the rule reads as correct
        # while fetching nothing to apply itself to (#3946's lesson, one function
        # over: a guard is not wired by being correct).
        assert min(UNOBSERVED_MAX_HOURS.values()) == 2.5
        assert min(UNOBSERVED_MAX_HOURS.values()) < min(SPORT_MAX_DURATIONS.values())
