"""`--only` lets the #5821 undo clear SOME banked rows without clearing all.

SHIP: an operator repairing a handful of wrongly-tagged fixtures clears exactly
those, and the fixtures that were folded correctly keep their fold. Before this
the script was all-or-nothing — the only way to free four bad rows was to undo
the repair for all 226, putting every correct fold back to the defect.

WHAT THESE TESTS ARE GUARDING, AND WHY EACH ONE EXISTS
──────────────────────────────────────────────────────
1. **An id that is not banked aborts.** The failure mode a scoping flag invites
   is the quiet one: a typo narrows the plan to nothing, the script prints
   "nothing to undo" and exits 0, and the operator reads that as "the rows I
   named are clear" when not one of them was examined. Same shape as the
   failed-read-is-not-an-absence defect #6786 caught in this file's sibling.

2. **A scoped run verifies over its SCOPE.** The post-write re-read re-reads the
   whole backup table. Unscoped, every banked row the operator deliberately did
   not name still carries its tag — correctly — so a *successful* `--only` run
   would count those as "still folded", print UNDO INCOMPLETE and exit 1. The
   run would have worked and the operator would be told it failed.

3. **Parsing refuses what it cannot read.** `--only 1,2x` must not run over one
   id while the operator believes they named two.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts.restore_5821_container_twin_tags import parse_only, select_requested


def _row(event_id: int, canonical_id: int = 999):
    """One banked row, shaped like the `_PLAN_SQL` result the script reads."""
    return SimpleNamespace(
        event_id=event_id,
        canonical_id=canonical_id,
        old_tags="[]",
        current_tags=f'["provenance:duplicate-of:{canonical_id}"]',
    )


class TestParsingTheFlag:
    def test_absent_is_none_not_empty(self):
        """🔴 None and [] must not collapse.

        `None` means "no scope was asked for" and runs the whole table; an empty
        scope would mean "clear nothing". Folding them together would make a
        malformed `--only` silently undo all 226 rows.
        """
        assert parse_only(None) is None
        assert parse_only([]) is None

    def test_comma_separated(self):
        assert parse_only(["1,2,3"]) == [1, 2, 3]

    def test_repeatable_and_mixed(self):
        assert parse_only(["1,2", "3"]) == [1, 2, 3]

    def test_whitespace_is_tolerated(self):
        assert parse_only([" 1 , 2 "]) == [1, 2]

    def test_order_is_kept_and_duplicates_collapse(self):
        assert parse_only(["9,3,9,3,1"]) == [9, 3, 1]

    @pytest.mark.parametrize("bad", ["1,2x", "abc", "1;2", "15313072.0", "1 2"])
    def test_a_non_integer_raises_rather_than_being_skipped(self, bad):
        """A skipped token is a narrowed scope nobody asked for."""
        with pytest.raises(ValueError):
            parse_only([bad])

    def test_all_separators_and_no_ids_raises(self):
        """`--only ,,,` named nothing; running the full table would be a rout."""
        with pytest.raises(ValueError):
            parse_only([",,,"])


class TestSelectingTheScope:
    def test_no_scope_is_the_whole_plan(self):
        plan = [_row(1), _row(2)]
        selected, unknown = select_requested(plan, None)
        assert [r.event_id for r in selected] == [1, 2]
        assert unknown == []

    def test_a_subset_leaves_the_rest_alone(self):
        plan = [_row(1), _row(2), _row(3)]
        selected, unknown = select_requested(plan, [1, 3])
        assert [r.event_id for r in selected] == [1, 3]
        assert unknown == []

    def test_an_unbanked_id_is_reported_not_dropped(self):
        """🔴 THE DEFECT A SCOPING FLAG INVITES.

        If 77 just vanished from the plan, the run would clear id 1, report
        success, and the operator would believe 77 was cleared too.
        """
        plan = [_row(1), _row(2)]
        selected, unknown = select_requested(plan, [1, 77])
        assert unknown == [77]
        assert [r.event_id for r in selected] == [1]

    def test_every_id_unknown_is_still_unknown_not_an_empty_no_op(self):
        """The narrowest version of the same trap: scope collapses to nothing.

        Were this to return `([], [])` the caller would take the
        "nothing to undo" branch and exit 0 — the cheerful lie.
        """
        plan = [_row(1)]
        selected, unknown = select_requested(plan, [55, 66])
        assert selected == []
        assert unknown == [55, 66]

    def test_an_empty_backup_table_makes_every_named_id_unknown(self):
        assert select_requested([], [1, 2]) == ([], [1, 2])


class TestTheScopedVerificationReadsTheScope:
    """Guard 2, at the level the bug actually lives: the post-write re-read.

    `run()` re-reads `_PLAN_SQL` after writing and passes it back through
    `select_requested(..., only)`. This pins that narrowing: over a table where
    the out-of-scope rows still carry their tags (which is the CORRECT state
    after a scoped undo), the verification set must be empty.
    """

    def test_out_of_scope_rows_are_not_counted_as_remaining(self):
        from scripts.restore_5821_container_twin_tags import duplicate_tag

        cleared = SimpleNamespace(
            event_id=1, canonical_id=999, old_tags="[]", current_tags='["audience:us"]'
        )
        still_folded_on_purpose = _row(2)
        after_the_write = [cleared, still_folded_on_purpose]

        scoped, _ = select_requested(after_the_write, [1])
        remaining = [
            r.event_id
            for r in scoped
            if duplicate_tag(r.canonical_id) in (r.current_tags or "")
        ]
        assert remaining == [], (
            "row 2 was deliberately left out of --only and correctly still "
            "carries its tag; counting it would make a successful scoped undo "
            "print UNDO INCOMPLETE and exit 1"
        )

        unscoped, _ = select_requested(after_the_write, None)
        unscoped_remaining = [
            r.event_id
            for r in unscoped
            if duplicate_tag(r.canonical_id) in (r.current_tags or "")
        ]
        assert unscoped_remaining == [2], (
            "and the unscoped read is what would have produced the false "
            "failure — this is the mutant the assertion above kills"
        )

    def test_a_scoped_row_that_kept_its_tag_IS_still_remaining(self):
        """The other direction: scoping must not swallow a genuine failure.

        A row the operator NAMED that still carries its tag after the write is a
        real incomplete undo and must survive the narrowing.
        """
        from scripts.restore_5821_container_twin_tags import duplicate_tag

        scoped, _ = select_requested([_row(1), _row(2)], [1])
        remaining = [
            r.event_id
            for r in scoped
            if duplicate_tag(r.canonical_id) in (r.current_tags or "")
        ]
        assert remaining == [1]
