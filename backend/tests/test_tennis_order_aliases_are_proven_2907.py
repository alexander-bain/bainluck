"""D69 = A — a re-ordering aliases because the AUTHORITY RECORD proves it.

Alex, 2026-09-05 7:16pm PT: *"you don't want human in the loop on this, because
it's not the last time this'll happen with names. Sort it out in a scalable
way."* And, at 7:25pm, on how a machine could possibly know: *"not from Fable's
knowledge of Chinese naming — from the authority record… The lane proves it that
way, or does not alias."*

WHAT THESE TESTS ARE FOR. Before this change `Juncheng Shang` and `Qinwen Zheng`
folded because a `ReviewedAlias` record said an agent had read them and believed
it — two entries carrying `ratified_by_alex: false`. After it they fold because
StatPal, in slots with dates and opponents, named the surname; the reviewed
records are still in the file. CERT-2017 is why the claim is split rather than
sweeping: `Qinwen Zheng` IS proven by the record and his human entry is now
redundant; `Juncheng Shang` is NOT — StatPal served him only in doubles, and a
team's surname proves a word, not a person — so his entry is still the only
thing folding that class, and `TestTheHumanIsRetired` says so out loud.

THE COUNTER-CASE IS THE POINT. A rule that folds every re-ordering it can reach
is not a rule, it is a sort — and it fuses `Garcia Perez` with `Perez-Garcia`,
two Spanish families our own register held in the field together on 2026-07-13.
Every guard below is shown to refuse it, one at a time, and a mutant that drops
any one of them admits it.
"""
from dataclasses import replace

import pytest

from app.utils import authority_tennis_capture as capture
from app.utils.authority_tennis_names import (
    CAPTURED_SLOTS,
    ORDER_ALIASES,
    PROOF_SLOT,
    REVIEWED_ALIASES,
    SLOT_PROVEN_ALIASES,
    ProvenSlot,
    _ORDER_ALIASES_MEASURED,
    _ORDER_ALIASES_REVIEWED,
    _ORDER_ALIASES_SLOT_PROVEN,
    _tokens,
    fold_tennis_name,
    is_doubles_name,
    slot_proven_order_aliases,
)

ZHENG = ("qinwen", "zheng")
SHANG = ("juncheng", "shang")
#: The class this module refuses, and the reason the guards exist.
GARCIA_PEREZ = ("garcia", "perez")


def _alias(tokens):
    for alias in SLOT_PROVEN_ALIASES:
        if alias.tokens == tokens:
            return alias
    return None


# =============================================================================
# 1. The capture is a measurement, and the alias set is derived from it
# =============================================================================

class TestTheAnswerIsDerivedAndNotWritten:
    """A hand-written list of proven classes would be the reviewed set wearing a
    new name. The set the matcher obeys has to come out of the prover."""

    def test_the_published_set_is_what_the_prover_returns_on_the_capture(self):
        rerun = slot_proven_order_aliases(
            CAPTURED_SLOTS, capture.AUTHORITY_SURNAMES, capture.OUR_SPELLINGS
        )
        assert {a.tokens for a in rerun} == {a.tokens for a in SLOT_PROVEN_ALIASES}
        assert _ORDER_ALIASES_SLOT_PROVEN == {a.tokens for a in rerun}

    def test_the_capture_is_the_venues_own_record_and_says_when(self):
        assert capture.CAPTURED_AT.endswith("Z")
        assert capture.CAPTURE_WINDOW[0] < capture.CAPTURE_WINDOW[1]
        assert len(capture.PROVEN_SIDES) > 300, "a thin capture proves thin things"
        assert len(capture.AUTHORITY_SURNAMES) > 300
        # The contradiction guard reads a YEAR of our register, not the venue's
        # fifteen days — `Perez-Garcia` last appeared eight weeks outside it.
        assert len(capture.OUR_SPELLINGS) > 5000

    def test_every_captured_side_survives_the_definition_of_a_slot(self):
        """`ProvenSlot.__post_init__` is the definition; the capture must satisfy
        it. A capture that lost rows here would be proving less than it claims."""
        assert len(CAPTURED_SLOTS) == len(capture.PROVEN_SIDES)

    def test_our_spellings_carry_no_doubles_pairs(self):
        """Folding replaces `/` with a space, so `Bagaric/Moratelli` becomes a
        two-token string indistinguishable from a singles name — and the prover
        would have been offered 1,674 teams as if they were people."""
        assert not [s for s in capture.OUR_SPELLINGS if "/" in s]
        pairs = [s for s in capture.OUR_SPELLINGS if is_doubles_name(s)]
        assert pairs == []


# =============================================================================
# 2. The two classes D69 names, proven from slots rather than from naming lore
# =============================================================================

class TestTheTwoNamesAlexWasAskedAbout:

    def test_zheng_folds_on_a_slot_with_an_id_behind_it(self):
        alias = _alias(ZHENG)
        assert alias is not None, "the class D69 = A ratified is not proven"
        assert alias.kind == PROOF_SLOT
        assert alias.confidence == 1.0
        assert alias.surname == "zheng"
        # Identity is the id: one player, one StatPal id, across every slot.
        assert alias.authority_ids == ("43122",)
        # Two independent slots on different days against different opponents.
        # Not more, because our register carries a bare-surname twin of each
        # tennis row (`Zheng` in `tennis_wta` beside `Qinwen Zheng` in
        # `tennis_wta_us_open`), and a one-token spelling has no order to prove —
        # the pairing consumes the fixture on whichever twin it reaches first.
        assert len(alias.slots) >= 2, "one slot is an anecdote"
        assert {s.slot_date for s in alias.slots} == {"2026-09-03", "2026-09-07"}
        assert len({s.our_opponent for s in alias.slots}) == len(alias.slots)
        assert {s.tour for s in alias.slots} == {"tennis_wta_us_open"}
        # 2026-09-07 is Swiatek–Zheng, the match standing notice 27 was written
        # about — the same slot the Polymarket attach was reported to have missed.
        assert "Iga Swiatek" in {s.our_opponent for s in alias.slots}
        # The opponent is what makes it a slot rather than a name coincidence.
        assert all(s.our_opponent.strip() for s in alias.slots)

    def test_the_other_zheng_is_a_different_person_and_the_id_says_so(self):
        """`Q. Zheng` and `M. Zheng` share a surname and nothing else. A
        name-keyed identity would have to guess; an id-keyed one does not."""
        ids = {s.authority_id for s in CAPTURED_SLOTS
               if fold_tennis_name(s.authority_name).endswith("zheng")}
        assert {"43122", "126416"} <= ids
        michael = [s for s in CAPTURED_SLOTS if s.authority_id == "126416"]
        assert michael, "the capture lost the second Zheng"
        assert all(fold_tennis_name(s.our_name) != "qinwen zheng" for s in michael)

    def test_shang_is_not_proven_and_the_module_declines_to_pretend(self):
        """CERT-2017, and it was right.

        The first cut folded Shang because a doubles TEAM elsewhere carried the
        surname — no slot, no player id, and the same path independently
        authorised `Alice Shang`, a different human. StatPal served Shang only
        in doubles in the captured window, so the honest answer is that his
        re-ordering is NOT proven, and D69's own words are "proves it that way,
        or does not alias".

        He still folds, on the unratified `ReviewedAlias` record alone — which is
        exactly what `TestTheHumanIsRetired` now has to disclose rather than
        claim away.
        """
        assert _alias(SHANG) is None, "a doubles surname is not a proof of a person"
        assert SHANG not in _ORDER_ALIASES_SLOT_PROVEN
        assert SHANG in _ORDER_ALIASES_REVIEWED

    def test_a_receipt_names_evidence_and_never_a_reviewer(self):
        receipt = _alias(ZHENG).receipt()
        assert receipt["authority_ids"] == ["43122"]
        assert receipt["slots"] and receipt["slots"][0]["authority"] == "statpal"
        assert {"reviewer", "attestation", "ratified_by_alex"}.isdisjoint(receipt)


class TestTheHumanIsRetired:

    def test_exactly_one_reviewed_class_is_now_proven_and_the_other_is_not(self):
        """What D69 actually bought, stated without rounding up.

        `Qinwen Zheng` no longer rests on an agent's reading — the authority
        record proves it, so the human record under it is redundant. `Juncheng
        Shang` is NOT proven and still rests on that reading alone. Claiming the
        containment for both is what CERT-2017 blocked, so this test asserts the
        split and will start failing the day StatPal serves Shang in singles —
        which is the moment to delete his record too.
        """
        assert ZHENG in _ORDER_ALIASES_SLOT_PROVEN
        assert SHANG not in _ORDER_ALIASES_SLOT_PROVEN
        assert not _ORDER_ALIASES_REVIEWED <= _ORDER_ALIASES_SLOT_PROVEN

        # Dropping the reviewed source today would drop Shang with it. That is a
        # real consequence and the reason his record stays for now.
        without_the_humans = _ORDER_ALIASES_MEASURED | _ORDER_ALIASES_SLOT_PROVEN
        assert ORDER_ALIASES - without_the_humans == {SHANG}

    def test_every_proven_alias_has_an_id_backed_slot(self):
        """CERT-2017's first named test. Nothing in the proven set may rest on a
        surname that appeared somewhere; every class carries at least one slot,
        and every slot carries a stable authority player id."""
        assert SLOT_PROVEN_ALIASES, "an empty set would pass this vacuously"
        for alias in SLOT_PROVEN_ALIASES:
            assert alias.kind == PROOF_SLOT, alias.tokens
            assert alias.confidence == 1.0, alias.tokens
            assert alias.slots, f"{alias.tokens} folds on no slot at all"
            assert alias.authority_ids, f"{alias.tokens} folds with no authority id"
            assert all(s.authority_id.strip() for s in alias.slots), alias.tokens
            # One class, one person: the id is the identity, not the spelling.
            assert len(set(alias.authority_ids)) == 1, alias.tokens

    def test_a_doubles_team_surname_cannot_authorize_an_unrelated_singles_identity(self):
        """CERT-2017's second named test, driven on the exact shape it found.

        `Bublik/ Shang` is a doubles TEAM. Its surnames must not authorise ANY
        singles re-ordering — not Shang's own, and least of all a different
        human who merely shares the surname.
        """
        doubles = ProvenSlot(
            authority="statpal", authority_id="352267",
            authority_name="Bublik/ Shang", our_name="Bublik / Shang",
            slot_date="2026-09-05", tour="tennis_atp",
            authority_opponent="Baez/ Marozsan", our_opponent="Baez / Marozsan",
            doubles=True,
        )
        spellings = {"juncheng shang", "alice shang", "bublik shang"}
        produced = slot_proven_order_aliases([doubles], {"shang", "bublik"}, spellings)
        assert produced == (), "a team surname authorised a person"

        # And the capture agrees: neither singles class is in the shipped set,
        # though the doubles slot that tempted the first cut really is captured.
        assert ("juncheng", "shang") not in _ORDER_ALIASES_SLOT_PROVEN
        assert ("alice", "shang") not in _ORDER_ALIASES_SLOT_PROVEN
        assert any(s.doubles and "shang" in s.proven_surnames for s in CAPTURED_SLOTS)

    def test_the_reviewed_records_are_still_unratified_and_no_longer_load_bearing(self):
        """They are left in place for one change only — removing them is purely
        subtractive and touches the agreement row's `allowances` payload."""
        assert [a.ratified_by_alex for a in REVIEWED_ALIASES] == [False, False]
        assert {a.tokens for a in REVIEWED_ALIASES} == {ZHENG, SHANG}


# =============================================================================
# 3. The counter-case, and each guard refusing it on its own
# =============================================================================

class TestTheClassThatMustNotFold:

    def test_garcia_perez_is_refused(self):
        assert GARCIA_PEREZ not in ORDER_ALIASES
        assert _alias(GARCIA_PEREZ) is None

    def test_both_orders_really_are_in_our_register(self):
        """Guard 3 is not hypothetical — this is the evidence it reads."""
        assert "garcia perez" in capture.OUR_SPELLINGS
        assert "perez garcia" in capture.OUR_SPELLINGS

    @staticmethod
    def _garcia_slot():
        return ProvenSlot(
            authority="statpal", authority_id="99999", authority_name="G. Perez",
            our_name="Garcia Perez", slot_date="2026-07-13", tour="tennis_wta",
            authority_opponent="A. Nobody", our_opponent="Anna Nobody",
        )

    def test_guard_three_refuses_it_even_with_a_slot(self):
        """Give it the strongest proof it could ever have and it still declines,
        because our own field holds the reversed order."""
        aliases = slot_proven_order_aliases(
            [self._garcia_slot()], {"perez"}, {"garcia perez", "perez garcia"}
        )
        assert [a.tokens for a in aliases] == []

    def test_guard_two_refuses_it_when_both_tokens_are_family_names(self):
        """Drop guard 3's evidence — pretend the reversed order never arrived —
        and guard 2 still refuses, because `garcia` is a surname somewhere."""
        aliases = slot_proven_order_aliases(
            [self._garcia_slot()], {"perez", "garcia"}, {"garcia perez"}
        )
        assert [a.tokens for a in aliases] == []

    def test_guard_one_refuses_a_class_with_no_proof_at_all(self):
        aliases = slot_proven_order_aliases([], {"perez"}, {"garcia perez"})
        assert [a.tokens for a in aliases] == []

    def test_with_every_guard_satisfied_it_would_fold(self):
        """The control that keeps the three tests above from passing vacuously:
        the same call with the contradictions removed DOES produce the alias, so
        each refusal above is the guard and not a missing input."""
        aliases = slot_proven_order_aliases(
            [self._garcia_slot()], {"perez"}, {"garcia perez"}
        )
        assert [a.tokens for a in aliases] == [GARCIA_PEREZ]

    def test_two_ids_under_one_spelling_are_two_people(self):
        """The id clause, driven directly: same tokens, two authority ids."""
        one = self._garcia_slot()
        two = replace(one, authority_id="88888", slot_date="2026-07-14")
        assert slot_proven_order_aliases([one, two], {"perez"}, {"garcia perez"}) == ()


# =============================================================================
# 4. A slot is both sides, or it is a coincidence
# =============================================================================

class TestWhatMakesItASlot:

    @staticmethod
    def _valid(**over):
        base = dict(
            authority="statpal", authority_id="43122", authority_name="Q. Zheng",
            our_name="Qinwen Zheng", slot_date="2026-09-05",
            tour="tennis_wta_us_open", authority_opponent="M. Keys",
            our_opponent="Madison Keys",
        )
        base.update(over)
        return base

    def test_the_real_slot_builds(self):
        slot = ProvenSlot(**self._valid())
        assert slot.proven_key == ("zheng", "q")
        assert slot.proven_surnames == {"zheng"}
        assert slot.tokens == ZHENG

    def test_an_opponent_that_does_not_agree_is_not_a_slot(self):
        with pytest.raises(ValueError, match="OPPONENTS"):
            ProvenSlot(**self._valid(our_opponent="Iga Swiatek"))

    def test_a_side_that_does_not_agree_proves_nothing(self):
        with pytest.raises(ValueError, match="do not agree"):
            ProvenSlot(**self._valid(our_name="Carlos Alcaraz"))

    @pytest.mark.parametrize("field", ["authority_id", "authority_name",
                                       "our_name", "tour", "our_opponent"])
    def test_a_blank_field_is_refused(self, field):
        with pytest.raises(ValueError, match="blank"):
            ProvenSlot(**self._valid(**{field: "  "}))

    def test_a_date_that_is_not_a_date_is_refused(self):
        with pytest.raises(ValueError, match="ISO date"):
            ProvenSlot(**self._valid(slot_date="yesterday"))


# =============================================================================
# 5. The blast radius, measured over the whole register
# =============================================================================

class TestTheWideningChangesNothingToday:
    """156 proven classes is a large tolerance next to nine reviewed ones, and
    the honest question is what it fuses. Answer, over a year of the real field:
    nothing. Guard 3 makes every proven class one our register spells exactly one
    way, so the fold cannot change an identity — it can only pre-authorise the
    spelling that has not arrived yet, which is the whole point of D69."""

    @staticmethod
    def _identity(name, aliases):
        tokens = tuple(_tokens(name))
        multiset = tuple(sorted(tokens))
        return multiset if multiset in aliases else tokens

    def _partition(self, aliases):
        groups: dict[tuple, set] = {}
        for name in capture.OUR_SPELLINGS:
            groups.setdefault(self._identity(name, aliases), set()).add(name)
        return groups

    def test_no_two_spellings_are_fused_that_were_apart_before(self):
        before = self._partition(_ORDER_ALIASES_MEASURED | _ORDER_ALIASES_REVIEWED)
        after = self._partition(ORDER_ALIASES)
        fused = {k: sorted(v) for k, v in after.items()
                 if len(v) > 1 and k not in before}
        assert fused == {}, f"the widening fused {len(fused)} classes"
        assert len(after) == len(before)

    def test_the_widening_is_real_and_not_an_empty_set(self):
        """The control for the test above: it would also pass if the prover
        returned nothing at all."""
        assert len(_ORDER_ALIASES_SLOT_PROVEN) > 100
        assert not _ORDER_ALIASES_SLOT_PROVEN <= _ORDER_ALIASES_MEASURED
