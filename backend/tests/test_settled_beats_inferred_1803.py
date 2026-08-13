"""#1803 — an event's ASSIGNED settled status is the authority, in every adapter.

`docs/rulings/036-...` states the rule; this suite pins its two non-golf legs.
The golf leg lives with its own neighbours in `test_golf_tournament_render.py`
(`TestTerminalRoundCeiling1803`).

WHY THIS FILE EXISTS AS A CLASS SUITE RATHER THAN A GOLF FIX
------------------------------------------------------------
#1803 was filed scoped to golf, because golf is where it was measured. Cycle
68's census (ruling 030) asked the question the ticket did not — *do the other
concept adapters infer stage completion the same way?* — and found a SECOND
reachable production specimen in a completely different mechanism:

    golf    round ceiling inferred from graded sibling leaders, no terminal case
    combat  settledness inferred from PRICE convergence (>=0.97 / <=0.03)
    cycling settledness inferred from the stage's own grade

Three different inferences, one shared defect: none of them ever consulted the
event's own assigned status, so each had states it could never escape.

THE SHARED INVARIANT, and every test below is a face of it: the assigned status
is OR-ed in, never substituted, so consulting it can only make a child MORE
settled and never less. Suppressing a genuinely-live market is the direction
that costs a reader real information, and monotonicity makes that direction
structurally impossible rather than merely unintended.
"""

import inspect

import pytest

from app.utils.event_combat import combat_status, fight_child_settled


class TestCombatFightChildSettled:
    """MEASURED specimen, production v3790/v3792: `event:ufc:26aug08` — "Fight
    Night: Gamrot vs Salkilld", fought 2026-08-09, card `status: settled`. Two of
    its fourteen children still rendered live ladders."""

    def test_the_measured_specimen_johns_vs_rosas(self):
        # The exact numbers read off production. A finished fight at a coin-flip.
        assert fight_child_settled(0.54, card_settled=False) is False   # the bug
        assert fight_child_settled(0.54, card_settled=True) is True     # the fix

    def test_the_measured_specimen_ko_prop(self):
        assert fight_child_settled(0.505, card_settled=False) is False
        assert fight_child_settled(0.505, card_settled=True) is True

    def test_price_inference_still_decides_a_card_in_play(self):
        # Unchanged behaviour for a live card: converged → settled, else not.
        assert fight_child_settled(0.98, card_settled=False) is True
        assert fight_child_settled(0.02, card_settled=False) is True
        assert fight_child_settled(0.97, card_settled=False) is True   # boundary
        assert fight_child_settled(0.03, card_settled=False) is True   # boundary
        assert fight_child_settled(0.96, card_settled=False) is False
        assert fight_child_settled(0.50, card_settled=False) is False

    def test_no_price_is_not_settled_on_a_live_card(self):
        assert fight_child_settled(None, card_settled=False) is False

    def test_no_price_IS_settled_on_a_finished_card(self):
        # An unpriced child on a card that already fought is still over. Before
        # the fix `lead_prob is None` was permanently "live".
        assert fight_child_settled(None, card_settled=True) is True

    @pytest.mark.parametrize(
        "lead_prob", [None, 0.0, 0.03, 0.04, 0.44, 0.5, 0.54, 0.96, 0.97, 1.0]
    )
    def test_monotone_assigned_status_only_ever_ADDS_settledness(self, lead_prob):
        live = fight_child_settled(lead_prob, card_settled=False)
        done = fight_child_settled(lead_prob, card_settled=True)
        assert done or not live, "a settled card made a child LESS settled"
        assert done is True

    def test_a_live_card_is_bit_identical_to_the_old_price_test(self):
        # The pre-#1803 expression, transcribed. A card in play must be
        # unreachable by the new term.
        for lead_prob in (None, 0.0, 0.02, 0.03, 0.5, 0.54, 0.96, 0.97, 1.0):
            old = lead_prob is not None and (lead_prob >= 0.97 or lead_prob <= 0.03)
            assert fight_child_settled(lead_prob, card_settled=False) is old


class TestCombatStatusIsTheAuthorityFeeding_It:
    """The `card_settled` argument above is not a new opinion about when a card
    is over — it is the SAME `combat_status` that already decides the banner the
    reader sees. One authority, consulted twice (#1620)."""

    def test_the_builder_feeds_child_settledness_from_combat_status(self):
        from app.utils import event_combat

        src = inspect.getsource(event_combat.CombatEventAdapter)
        assert 'card_settled = combat_status(authoritative_commence, now) == "settled"' in src
        assert "fight_child_settled(lead_prob, card_settled)" in src

    def test_combat_status_still_classifies_the_specimen_as_settled(self):
        from datetime import datetime, timedelta, timezone

        # No wall clock (gotcha #44): `now` is an argument, so the offset IS the
        # fact under test and cannot swing with the time of day it runs at.
        now = datetime(2026, 8, 12, 20, 0, tzinfo=timezone.utc)
        fought = now - timedelta(hours=90)          # the 08-09 card, 3+ days back
        assert combat_status(fought, now) == "settled"

        in_window = now - timedelta(hours=2)
        assert combat_status(in_window, now) == "live"
        assert combat_status(now + timedelta(days=3), now) == "upcoming"


class TestCyclingStageSettled1803:
    """The cycling leg, and it is honestly labelled: LATENT, not measured.

    Every settled cycling concept 404s in production today (`tour-de-france-2026`
    and `giro-2026` both 404 on v3792), so unlike golf and combat this leg has no
    production specimen and is proven here only. It was fixed rather than filed
    because the Vuelta concludes 2026-09-13 and makes it reachable — a dated fuse
    on a one-line guard is not worth a ticket.
    """

    def test_the_source_ORs_the_event_status_in(self):
        """UX-P069: re-pointed from the LITERAL to the CALL, and that is the fix.

        This assertion used to match the transcribed expression
        `"settled": event_status == "settled" or graded is not None`. UX-P068
        recorded the limitation honestly — the sibling grid test below
        re-implements the expression, so this string match was the ONLY thing
        binding the source. Alex's item 4c asked whether cycling rides the same
        fixed code path; it did not, it rode a copy. It now calls
        `settled_under_assigned_state`, so this asserts the CALL and the argument
        that carries the assigned term.
        """
        from app.utils import event_cycling

        src = inspect.getsource(event_cycling.CyclingEventAdapter)
        assert "settled_under_assigned_state(" in src, (
            "the cycling stage child no longer calls the settledness authority — "
            "if the policy was re-inlined here, the next change to it reaches only "
            "one of six adapters"
        )
        assert 'assigned_settled=event_status == "settled"' in src, (
            "the cycling stage child must pass the race's ASSIGNED status as the "
            "assigned term, not replace the per-stage grade with it"
        )

    @pytest.mark.parametrize("graded", [None, "Tadej Pogacar"])
    @pytest.mark.parametrize("event_status", ["upcoming", "live", "settled"])
    def test_monotone_and_correct_over_the_whole_grid(self, graded, event_status):
        # UX-P069: was a transcription of the adapter's expression; now it drives
        # the REAL authority the adapter calls, so this grid and the source
        # assertion above bind the same code.
        from app.utils.settledness import settled_under_assigned_state

        settled = settled_under_assigned_state(
            inferred=graded is not None, assigned_settled=event_status == "settled"
        )
        old = graded is not None

        # Never LESS settled than the old rule.
        assert settled or not old

        # An ungraded stage on a CONCLUDED race is the bug, and it settles now.
        if event_status == "settled":
            assert settled is True
        else:
            # Mid-race, an ungraded stage stays live — the sharp edge.
            assert settled is old
