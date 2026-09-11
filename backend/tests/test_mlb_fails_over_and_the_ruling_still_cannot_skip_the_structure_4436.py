"""D113 = A: baseball fails over like football, and the guard that makes it safe. #4436.

Ship parent #2867 (pillar: MATCHING) — *every game exists on the site before any
market lists it; nothing goes blank when ESPN does*. This is the third of the
per-sport releases Alex asked for after D104 ("then the rest in one release
each"): football #4417, the NBA #4493, baseball here.

Alex, 2026-09-10 10:35am PT, relayed by Fable-5:

    "move the check below the ruling so baseball fails over like football, with
     the guard that a sport with no backup data can never slip through"

WHY THIS RELEASE NEEDED A CODE CHANGE AND THE OTHER TWO DID NOT
════════════════════════════════════════════════════════════════
Football and the NBA joined `FLIP_RULED_WITHOUT_STREAK` by adding one string
each. **Adding `baseball_mlb` to that set changes nothing on its own** — measured
on this branch before the reorder, `flip_permitted("baseball_mlb", …)` still
returned `False`, one branch earlier, on D63's governing-number question. The
ship is the REORDER; the set membership only becomes reachable because of it.

The reorder is legitimate because the governing number was never a capability:

  * MLB has a shadow stamper and a working hourly discovery pass, so it is
    structurally able to fail over — it is not missing backup data;
  * `GOVERNING_IDENTITY_NUMBERS` decides which published percentage advances a
    STREAK. `authority_failover.decide` and `_act_on_failovers` never read it;
  * after D104 no streak gates a ruled sport at all.

So above the ruling it refused a ruled sport on a fact that decided nothing
about the flip. Below the ruling it still refuses every UNRULED sport that lacks
one, which is the only thing it ever meant.

WHAT THE GUARD IS, AND WHY IT IS BUILT RATHER THAN BORROWED
════════════════════════════════════════════════════════════
Alex's condition is a claim about BACKUP DATA, which is branches 2 and 3 — no
shadow stamper (nothing to flip onto) and no working discovery pass (nothing
that could find a game we missed). Both stay ABOVE the ruling, so a ruled key
lacking either is refused. `TestARulingCannotBuyBackupDataThatDoesNotExist` is
that guard.

It uses constructed sports (`tests/authority_specimens.py`), not real ones,
because **after this ship no real sport is left in the states it needs to
demonstrate**. Every shadow-stamped, discovery-scheduled sport is now either
governed (NFL/NBA/NHL) or ruled (MLB). #4493 already paid for this lesson once:
it turned four tests red and left one green for the wrong reason, passing on the
D104 branch while claiming to prove something about seven days. A borrowed
specimen asserts today's config; a constructed one asserts the branch.

WHAT THIS SHIP IS NOT
═════════════════════
It is not a flip. `baseball_mlb` still holds ESPN in `AUTHORITY_BY_SPORT` and
must: that map is the STANDING source of record, and `authority_failover.decide`
reads a `STATPAL` value there as "this sport has already flipped, ESPN's silence
is not an outage for it". This ship only permits a FALLBACK, on a pass where
ESPN has gone dark. `TestTheSwitchItselfDidNotMove` keeps the two apart.

The reader-visible effect, when it fires: on a pass where ESPN answers nothing
for baseball, today's MLB games keep appearing and keep advancing instead of
freezing on last-known state. On every other pass, nothing changes.
"""

import pytest

from app.config.authority_by_sport import (
    AUTHORITY_BY_SPORT,
    DISCOVERY_SCHEDULED_SPORTS,
    ESPN,
    FLIP_EVIDENCE,
    FLIP_RULED_WITHOUT_STREAK,
    GOVERNING_IDENTITY_NUMBERS,
    SHADOW_STAMPERS,
    authority_for,
    discovery_state,
    flip_permitted,
)
from app.utils.authority_streak import REQUIRED_STREAK_DAYS
from tests.authority_specimens import register_specimen

NFL = "americanfootball_nfl"
NBA = "basketball_nba"
NHL = "icehockey_nhl"
MLB = "baseball_mlb"


def _days(n, state="MEETS"):
    """`n` CONSECUTIVE ledger days ending 2026-09-30, all in one state.

    A third copy of this helper rather than an import, for the reason #4493
    wrote down: these files pin three different releases, and a shared fixture
    retuned for one would silently move the others' controls.

    The key is `day`, not `date` — #4493's first cut used `date`, every ledger it
    built read as ABSENT, and its controls refused with "has no agreement ledger
    yet" while still being `False` and still green. Hence: every control in this
    file asserts the refusal REASON, never merely the verdict.
    """
    from datetime import date, timedelta

    end = date(2026, 9, 30)
    return [
        {"day": (end - timedelta(days=n - 1 - i)).isoformat(), "state": state}
        for i in range(n)
    ]


class TestBaseballFailsOverLikeFootball:
    """The ship itself — Alex's sentence, asserted."""

    def test_mlb_is_in_the_ruled_set(self):
        assert MLB in FLIP_RULED_WITHOUT_STREAK

    def test_mlb_is_permitted_on_an_empty_ledger(self):
        """The state `_decide_failovers` actually hands the gate.

        #4443's case: when the durable ledger read fails, the caller passes `[]`.
        A ruled sport must be permitted anyway, or the failover is still gated on
        the MONITOR being readable — which is the hole #4443 closed for football
        and this release inherits.
        """
        permitted, why = flip_permitted(MLB, [])
        assert permitted is True, why

    def test_mlb_is_permitted_on_a_short_streak(self):
        permitted, why = flip_permitted(MLB, _days(3))
        assert permitted is True, why

    def test_mlb_is_permitted_on_a_broken_streak(self):
        """The arm a "ruled means skip the wait" reading could still get wrong.

        A run of BELOW days is not a short streak, it is a broken one — a
        different refusal branch with different wording. D104 retires both for a
        ruled sport, so this must permit too.
        """
        permitted, why = flip_permitted(MLB, _days(9, state="BELOW"))
        assert permitted is True, why

    def test_the_reason_names_d104_and_discloses_the_unruled_number(self):
        """#4436's acceptance criterion, verbatim.

        A `True` that will not say which open question it walked past is the
        silent-`True` failure `flip_permitted`'s own docstring argues against. So
        MLB's permission has to name the ruling that granted it AND say that the
        governing number is still unruled and now applies to the monitor only.
        """
        permitted, why = flip_permitted(MLB, [])
        assert permitted is True, why
        assert "D104" in why, why
        assert "D113" in why, why
        assert "D63" in why, why
        assert "MONITOR" in why, why

    def test_a_governed_sport_does_not_carry_the_disclosure(self):
        """The other arm — the clause is conditional, not boilerplate.

        Without this, the assertion above would pass against a `why` that
        recited D63 at every ruled sport, which would make the disclosure noise
        rather than information.
        """
        for governed in (NFL, NBA):
            why = flip_permitted(governed, [])[1]
            assert GOVERNING_IDENTITY_NUMBERS.get(governed), governed
            assert "WHAT IS STILL UNRULED" not in why, f"{governed}: {why}"


class TestARulingCannotBuyBackupDataThatDoesNotExist:
    """Alex's guard on D113, and the reason the reorder was safe to make.

    *"with the guard that a sport with no backup data can never slip through"*.

    Backup data is branches 2 and 3. Both are asked ABOVE the ruling, so being
    ruled cannot answer either. Each arm asserts the refusal REASON, because a
    specimen that refused for some third reason would pass a verdict-only
    assertion while proving nothing about the branch it names.
    """

    def test_a_ruled_sport_with_no_shadow_stamper_still_refuses(self, monkeypatch):
        """Nothing to flip ONTO. No ruling reaches this."""
        key = register_specimen(
            monkeypatch, "unittest_ruled_no_stamper", stamper=False, ruled=True
        )
        permitted, why = flip_permitted(key, _days(30))
        assert permitted is False, why
        assert "no shadow stamper" in why, why

    def test_a_ruled_sport_with_no_discovery_pass_still_refuses(self, monkeypatch):
        """Nothing that could FIND a game we missed, which is the point of it.

        A sport with no discovery pass is scored only over games we already
        have, so its agreement can never show StatPal finding one we lack. Its
        own branch comment says "fix the path, do not wait for days" — a build
        step, and a ruling about proof days does not perform it.
        """
        key = register_specimen(
            monkeypatch, "unittest_ruled_no_discovery", discovery=False, ruled=True
        )
        permitted, why = flip_permitted(key, _days(30))
        assert permitted is False, why
        assert "no working StatPal discovery pass" in why, why

    def test_a_ruled_measurement_population_still_refuses(self, monkeypatch):
        """The wrong-question branch, which a ruling must also not answer.

        A population key names no `sports.key`, so flipping it would flip
        nothing while reporting success — worse than a refusal.
        """
        from app.utils.authority_agreement import MEASUREMENT_POPULATION_SCOPES

        key = register_specimen(
            monkeypatch,
            "unittest_ruled_population",
            ruled=True,
            population=MEASUREMENT_POPULATION_SCOPES["soccer"],
        )
        permitted, why = flip_permitted(key, _days(30))
        assert permitted is False, why
        assert "MEASUREMENT POPULATION" in why, why

    def test_the_positive_control_the_same_specimen_ruled_and_whole_is_permitted(
        self, monkeypatch
    ):
        """Without this, all three arms above could pass on a broken harness.

        `register_specimen` patches six module globals across every loaded
        binding. If it silently patched none of them, the three refusals above
        would still be `False` — measuring the real config's answer for an
        unknown key ("no shadow stamper") and reading as green. A specimen that
        is ruled and structurally complete MUST be permitted, and that is the
        assertion which proves the harness is actually wired to the gate.
        """
        key = register_specimen(monkeypatch, "unittest_ruled_and_whole", ruled=True)
        permitted, why = flip_permitted(key, [])
        assert permitted is True, why
        assert "D104" in why, why

    def test_every_really_ruled_sport_really_has_its_backup_data(self):
        """The guard applied to the live config, not to a specimen.

        The tests above prove the gate refuses a ruled sport without backup
        data. This one proves no sport is currently in that state — so the
        refusal is a guard we hold, not one we are relying on.
        """
        for key in FLIP_RULED_WITHOUT_STREAK:
            assert key in SHADOW_STAMPERS, key
            assert key in DISCOVERY_SCHEDULED_SPORTS, key
            assert discovery_state(key)[0] == "SCHEDULED", key


class TestTheD63BranchIsMovedNotRetired:
    """The half of D113 that is easy to over-deliver.

    Alex moved the check. He did not delete it, and a reorder that quietly made
    it unreachable would be a different ruling than the one he gave.
    """

    def test_an_unruled_sport_with_no_governing_number_still_refuses(self, monkeypatch):
        key = register_specimen(
            monkeypatch, "unittest_unruled_no_governing", governing=None, ruled=False
        )
        permitted, why = flip_permitted(key, _days(30))
        assert permitted is False, why
        assert "governing identity number" in why, why
        assert "D63" in why, why

    def test_it_refuses_even_on_a_streak_that_would_otherwise_pass(self, monkeypatch):
        """D63 outranks a complete streak, exactly as it did before the move.

        The branch sits ABOVE the streak questions in its new home too. Handed
        enough MEETS days to clear the bar, an ungoverned unruled sport must
        still refuse on D63 rather than being permitted on its days — otherwise
        the "move" was a demotion below the thing it is supposed to gate.
        """
        key = register_specimen(
            monkeypatch, "unittest_ungoverned_long_streak", governing=None, ruled=False
        )
        permitted, why = flip_permitted(key, _days(REQUIRED_STREAK_DAYS + 5))
        assert permitted is False, why
        assert "D63" in why, why

    def test_no_real_sport_can_still_exercise_this_branch(self):
        """Why the two tests above have to be built rather than borrowed.

        Asserted rather than left as a comment, so that if a future release adds
        a real ungoverned sport, this fails and tells the next lane that the
        branch has a live specimen again — instead of the specimen-only coverage
        quietly becoming redundant and nobody noticing either way.
        """
        reachable = {
            key
            for key in SHADOW_STAMPERS
            if key in DISCOVERY_SCHEDULED_SPORTS
            and not GOVERNING_IDENTITY_NUMBERS.get(key)
            and key not in FLIP_RULED_WITHOUT_STREAK
        }
        assert reachable == set(), (
            "a real sport can reach the D63 branch again: "
            f"{sorted(reachable)}. That is not a failure — it means this "
            "branch has a live specimen once more, and these tests may borrow "
            "it instead of constructing one"
        )


class TestOnlyBaseballShipsOnThisIssue:
    """Alex: "then the rest in one release each" — so the set grows by one."""

    def test_the_ruled_set_is_exactly_what_has_been_graded(self):
        assert FLIP_RULED_WITHOUT_STREAK == frozenset({NFL, NBA, MLB}), (
            "football #4417, the NBA #4493, MLB #4436. NHL is its own release "
            "under #2867; adding it here lands two flips under a cert that "
            "graded one"
        )

    def test_the_nhl_still_waits(self):
        """The control that proves this ship is one sport wide.

        The NHL is the last real sport that reaches the CLOCK, so it is also the
        only remaining real proof that the streak branch still binds anything.
        """
        permitted, why = flip_permitted(NHL, _days(5))
        assert permitted is False, why
        assert f"5/{REQUIRED_STREAK_DAYS}" in why, why

    def test_an_empty_ledger_permits_only_ruled_sports(self):
        """#4443's property, re-proved now that the ruled set has three members.

        `flip_permitted(key, [])` may permit a RULED sport and nothing else —
        every other route to `True` runs through `compute_streak`, which refuses
        on an empty ledger. Asserted over every shadow-stamped sport, so a fourth
        release re-checks it automatically.
        """
        permitted_on_empty = {
            key for key in SHADOW_STAMPERS if flip_permitted(key, [])[0]
        }
        assert permitted_on_empty == set(FLIP_RULED_WITHOUT_STREAK) & set(
            SHADOW_STAMPERS
        ), (
            "an empty ledger permitted a sport that is not ruled, so something "
            "other than the D104 branch is answering yes without a streak: "
            f"permitted={sorted(permitted_on_empty)} "
            f"ruled={sorted(FLIP_RULED_WITHOUT_STREAK)}"
        )


class TestTheSwitchItselfDidNotMove:
    """A gate exemption, not a flip. #4434's distinction, held for a third sport.

    MLB joined the RULED SET here and not the standing switch. #4954 flipped
    NFL on 2026-09-11 by a ship of its own, so the claim is no longer "every
    value is ESPN" — it is that no sport arrives in the switch by MEMBERSHIP of
    the ruled set, only by an evidenced edit of its own.
    """

    def test_mlb_is_still_espn_standing(self):
        assert authority_for(MLB) == ESPN
        assert MLB not in FLIP_EVIDENCE

    def test_no_ruled_sport_was_written_into_the_standing_switch(self):
        unflipped = sorted(k for k in FLIP_RULED_WITHOUT_STREAK if k not in FLIP_EVIDENCE)
        assert MLB in unflipped, (
            "MLB is this file's subject and it has been flipped by some later "
            "ship — re-read that ship before touching this test"
        )
        for key in unflipped:
            assert AUTHORITY_BY_SPORT.get(key) == ESPN, (
                f"{key} was written into the standing switch as well as the "
                "gate, with no FLIP_EVIDENCE; that is the STANDING-STATPAL "
                "path arriving by membership, which is not a fallback and is "
                "not what D104 or D113 asked for"
            )


class TestTheServedNoteFollowsTheRuledSet:
    """The admin note is derived from the set, so it cannot go stale per sport.

    #4493 shipped this derivation precisely so a new member needs no edit here.
    This is the assertion that proves the third member inherited it.
    """

    @pytest.mark.parametrize("sport", sorted(FLIP_RULED_WITHOUT_STREAK))
    def test_a_ruled_sports_note_says_the_wait_is_retired(self, sport):
        from app.routes.admin_providers import _authority_note

        note = _authority_note(sport)
        assert "D104" in note, note
        assert (
            "seven consecutive daily gate states" not in note
        ), f"{sport} is ruled; its note still describes the retired wait: {note}"

    def test_an_unruled_sports_note_still_describes_the_gate(self):
        from app.routes.admin_providers import _authority_note

        assert NHL not in FLIP_RULED_WITHOUT_STREAK
        assert "seven consecutive daily gate states" in _authority_note(NHL)
