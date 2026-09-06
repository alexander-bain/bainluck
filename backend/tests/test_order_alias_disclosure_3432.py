"""The tennis row discloses every order tolerance it applied, not the oldest one.

#3432. `ORDER_ALIASES` — the set `resolve_tennis_name` obeys — grew from 9
classes to 164 when the authority-proven layer landed (D69, CERT-2019). The
disclosure did not move with it: `pair_tennis_sides` went on enumerating
`REVIEWED_ALIASES`, so production published

    "allowances": {"order_aliases_reviewed": {"count": 2, "receipts": [...]}}

for a pass that had applied 164. An allowance is the inverse of a refusal — it
lets rows JOIN, moves the governing number upward, and leaves no count anywhere
to notice it by — so the published receipt is the ONLY place the tolerance is
visible, and an operator comparing 2 against the tolerance he believed was in
force would have been reassured by a number describing a different set.

The old test could not catch it. `test_reviewed_alias_evidence_3287` asserts
`count == 2` by restating `REVIEWED_ALIASES`, which is the defect's own premise:
it agrees by construction and would keep agreeing at 164, at 1,640, and at
whatever the next capture proves.

So the guard here is a COVER, taken against the live set:

    every class in `ORDER_ALIASES` is disclosed by exactly one allowance key,
    and every class an allowance key discloses is in `ORDER_ALIASES`

which has no count in it to go stale, and which a fourth provenance fails
before it can ship silently. `test_a_fourth_provenance_cannot_ship_undisclosed`
is that claim made executable; `test_the_pre_fix_disclosure_fails_the_cover` is
the same guard shown dying on the exact shape production served.

**What this file does not claim.** Not that the tolerance is CORRECT — that is
`test_tennis_order_aliases_are_proven_2907`, which refuses a class the authority
record does not prove. This file only claims the row says what the join did.
"""

from __future__ import annotations

import json

import pytest

from app.utils.authority_agreement import (
    RECEIPT_CAP,
    Join,
    Side,
    build_agreement_row,
)
from app.utils.authority_tennis_agreement import (
    DOUBLES,
    MEASURED_ALIAS_ALLOWANCE,
    ORDER_ALIAS_ALLOWANCE,
    PROVEN_ALIAS_ALLOWANCE,
    SINGLES,
    TENNIS_ALLOWANCE_NAMES,
    TENNIS_UNCAPPED_ALLOWANCES,
    build_tennis_agreements,
    singles_order_allowances,
)
from app.utils.authority_tennis_names import (
    ORDER_ALIASES,
    REVIEWED_ALIASES,
    SLOT_PROVEN_ALIASES,
    _ORDER_ALIASES_MEASURED,
    _ORDER_ALIASES_REVIEWED,
    _ORDER_ALIASES_SLOT_PROVEN,
)


def _classes(receipts) -> set[tuple[str, ...]]:
    """The permutation classes a list of receipts discloses."""
    return {tuple(r["tokens"]) for r in receipts}


def _disclosed(allowances) -> set[tuple[str, ...]]:
    """Every class disclosed across every allowance key."""
    return set().union(*(_classes(v) for v in allowances.values()))


class TestTheRowDisclosesEveryToleranceItApplied:
    def test_the_disclosure_covers_the_set_the_join_obeys(self):
        """The #3432 guard. No count, no restated set — the two sides are the
        live `ORDER_ALIASES` and what the strategy publishes about it."""
        disclosed = _disclosed(singles_order_allowances())

        undisclosed = ORDER_ALIASES - disclosed
        assert not undisclosed, (
            f"{len(undisclosed)} classes fold the join and appear on no "
            f"allowance receipt, e.g. {sorted(undisclosed)[:5]}"
        )

        # The other direction, which is not symmetric decoration: a receipt for
        # a class the join does NOT fold is a tolerance disclosed but never
        # granted, and an operator auditing it would be reading fiction.
        invented = disclosed - ORDER_ALIASES
        assert not invented, f"disclosed but not in the set: {sorted(invented)}"

    def test_the_pre_fix_disclosure_fails_the_cover(self):
        """The guard dies on the exact shape production served at 05:44Z on
        2026-09-06 — the reviewed receipts alone."""
        pre_fix = {ORDER_ALIAS_ALLOWANCE: [a.receipt() for a in REVIEWED_ALIASES]}

        missing = ORDER_ALIASES - _disclosed(pre_fix)
        assert len(missing) == len(ORDER_ALIASES) - len(_ORDER_ALIASES_REVIEWED)
        assert missing, "the guard would be vacuous if the old shape passed it"

    def test_a_fourth_provenance_cannot_ship_undisclosed(self, monkeypatch):
        """The durable half. Widening `ORDER_ALIASES` without routing the new
        classes to an allowance key fails here, which is the whole mechanism —
        the next person to grow the tolerance cannot leave the row describing
        the old one."""
        import app.utils.authority_tennis_agreement as agreement
        import app.utils.authority_tennis_names as names

        widened = ORDER_ALIASES | {("fourth", "provenance")}
        monkeypatch.setattr(names, "ORDER_ALIASES", widened)
        monkeypatch.setattr(agreement, "ORDER_ALIASES", widened)

        assert agreement.ORDER_ALIASES - _disclosed(singles_order_allowances()) == {
            ("fourth", "provenance")
        }

    def test_each_key_discloses_its_own_provenance_and_no_other(self):
        """A cover made of one key holding everything would pass the test above
        and tell an operator nothing about what backs what."""
        published = singles_order_allowances()

        assert _classes(published[ORDER_ALIAS_ALLOWANCE]) == _ORDER_ALIASES_REVIEWED
        assert _classes(published[PROVEN_ALIAS_ALLOWANCE]) == _ORDER_ALIASES_SLOT_PROVEN
        assert _classes(published[MEASURED_ALIAS_ALLOWANCE]) == _ORDER_ALIASES_MEASURED
        assert set(published) == set(TENNIS_ALLOWANCE_NAMES)

    def test_the_keys_overlap_because_the_evidence_does(self):
        """Not a partition, and the difference is the finding D69 bought: the
        reviewed classes are a SUBSET of the proven ones bar `Juncheng Shang`,
        whom the authority record served only in doubles. The counts therefore
        sum to MORE than the set — asserting otherwise would force a future
        editor to drop a real provenance to make arithmetic work."""
        published = singles_order_allowances()
        total = sum(len(v) for v in published.values())

        assert total > len(ORDER_ALIASES)
        overlap = _ORDER_ALIASES_REVIEWED & _ORDER_ALIASES_SLOT_PROVEN
        assert total - len(overlap) == len(ORDER_ALIASES)


class TestThePublishedRowSaysIt:
    """Through `build_tennis_agreements`, because a builder and a row can agree
    while the wiring between them is dead."""

    @pytest.fixture
    def rows(self):
        return build_tennis_agreements(fixtures=[], rows=[])

    def test_the_singles_row_counts_the_whole_set_under_each_key(self, rows):
        allowances = rows[SINGLES]["allowances"]

        assert allowances[ORDER_ALIAS_ALLOWANCE]["count"] == len(REVIEWED_ALIASES)
        assert allowances[PROVEN_ALIAS_ALLOWANCE]["count"] == len(SLOT_PROVEN_ALIASES)
        assert allowances[MEASURED_ALIAS_ALLOWANCE]["count"] == len(
            _ORDER_ALIASES_MEASURED
        )

    def test_a_count_is_never_the_length_of_a_truncated_list(self, rows):
        """The reason the cap is safe. Truncation may change the examples under
        a number and may never change the number — read the other way, a reader
        who compares `count` against the tolerance is comparing whole sets."""
        proven = rows[SINGLES]["allowances"][PROVEN_ALIAS_ALLOWANCE]

        assert proven["count"] == len(SLOT_PROVEN_ALIASES) > RECEIPT_CAP
        assert len(proven["receipts"]) == RECEIPT_CAP
        assert proven["receipts_truncated"] is True
        assert proven["receipts_shown"] == RECEIPT_CAP
        assert str(proven["count"]) in proven["receipts_note"]

    def test_the_unbacked_allowance_is_published_in_full(self, rows):
        """#3287's rule survives the cap: nothing re-runs a reviewed attestation,
        so a sample of them audits nothing and the full list is owed."""
        reviewed = rows[SINGLES]["allowances"][ORDER_ALIAS_ALLOWANCE]

        assert ORDER_ALIAS_ALLOWANCE in TENNIS_UNCAPPED_ALLOWANCES
        assert len(reviewed["receipts"]) == reviewed["count"]
        assert "receipts_truncated" not in reviewed
        assert all(r["ratified_by_alex"] is False for r in reviewed["receipts"])

    def test_every_receipt_names_what_backs_it(self, rows):
        """A receipt an operator cannot act on is a count with decoration."""
        allowances = rows[SINGLES]["allowances"]

        for receipt in allowances[ORDER_ALIAS_ALLOWANCE]["receipts"]:
            assert receipt["reviewer"] and receipt["attestation"]
        for receipt in allowances[PROVEN_ALIAS_ALLOWANCE]["receipts"]:
            # The id is the proof, per D69 — a surname proves a word, a slot
            # carrying one stable player id proves a person (CERT-2019).
            assert receipt["authority_ids"]
            assert receipt["slots"]
            assert all(s["authority_id"] for s in receipt["slots"])
        for receipt in allowances[MEASURED_ALIAS_ALLOWANCE]["receipts"]:
            assert "_orders_by_multiset" in receipt["basis"]

    def test_the_doubles_row_still_discloses_nothing(self, rows):
        """CERT-1948 survives three keys. The doubles join reads an unordered
        pair of surnames, so no re-ordering tolerance can move its number, and
        claiming one would be the same lie in the other direction."""
        assert rows[DOUBLES]["allowances"] == {}
        for name in TENNIS_ALLOWANCE_NAMES:
            assert name not in rows[DOUBLES]["allowances"]

    def test_the_row_stays_small_enough_to_read(self, rows):
        """The cap's own reason. A row a bus window cannot hold is not
        disclosure either, and 156 full slot receipts are 77kB."""
        assert len(json.dumps(rows[SINGLES]["allowances"])) < 30_000

    def test_the_order_is_stable_between_passes(self):
        """An allowance list that reshuffled itself would show as a diff on a
        row whose tolerance had not moved, and the operator this exists for
        would learn to skip it."""
        first = build_tennis_agreements(fixtures=[], rows=[])[SINGLES]["allowances"]
        second = build_tennis_agreements(fixtures=[], rows=[])[SINGLES]["allowances"]

        assert json.dumps(first) == json.dumps(second)


class TestTheSharedRowCapsReceiptsAndNeverCounts:
    """The mechanism, on a synthetic strategy — so it is pinned for the next
    sport that publishes an allowance, not only for tennis."""

    @staticmethod
    def _row(allowances, uncapped=frozenset()):
        join = Join(
            fixtures=[],
            rows=[],
            paired=[],
            statpal_only=[],
            ours_only=[],
            unusable_fixtures=[],
            unusable_rows=[],
            allowances=allowances,
            uncapped_allowances=uncapped,
        )
        return build_agreement_row(
            sport_key="tennis_singles",
            fixtures=[],
            rows=[],
            normalize=str,
            pair_sides=lambda fixtures, rows, normalize: join,
        )

    def test_a_capped_key_truncates_examples_and_keeps_its_count(self):
        many = [{"tokens": [f"n{i}"]} for i in range(RECEIPT_CAP + 7)]

        published = self._row({"backed": many})["allowances"]["backed"]

        assert published["count"] == RECEIPT_CAP + 7
        assert len(published["receipts"]) == RECEIPT_CAP
        assert published["receipts_truncated"] is True

    def test_an_uncapped_key_publishes_the_same_list_whole(self):
        """Same input, one word of configuration different — so the test cannot
        pass because the list was short."""
        many = [{"tokens": [f"n{i}"]} for i in range(RECEIPT_CAP + 7)]

        published = self._row({"unbacked": many}, uncapped=frozenset({"unbacked"}))[
            "allowances"
        ]["unbacked"]

        assert published["count"] == RECEIPT_CAP + 7
        assert len(published["receipts"]) == RECEIPT_CAP + 7
        assert "receipts_truncated" not in published

    def test_a_short_capped_list_is_not_marked_truncated(self):
        """The flag says something happened; a permanent `False`-shaped marker
        on every allowance would train a reader to ignore it."""
        published = self._row({"backed": [{"tokens": ["one"]}]})["allowances"]["backed"]

        assert published["count"] == 1
        assert "receipts_truncated" not in published

    def test_a_strategy_that_names_no_allowance_publishes_none(self):
        """Fail closed, and the expected reading for every sport but tennis."""
        assert self._row({})["allowances"] == {}
