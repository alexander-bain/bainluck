"""#7594 — the revival screen is asked once; this is the arm that asks it again.

WHAT A READER SEES WITHOUT IT. `/search?q=hurricanes` on production, 2026-09-21
04:1xZ, two adjacent cards for one game:

    15302884  OTHER HOCKEY  Hurricanes / Panthers   "No result reported"
    15312312  NHL           Panthers / Hurricanes   "Sep 20 FINAL 6-3"

The same game contradicting itself about whether it has been played.

The rule is EVIDENCE, not time, and that is the whole of what these tests pin:
the keeper is the row holding a result or an authority id, and a row holding
either is never taken back. The four refusals are each their own case, because a
predicate whose refusals are only tested in aggregate is a predicate whose
refusals can be deleted one at a time.

The two-session proof that the write cannot empty a fixture lives in
`tests/integration/test_7594_canonical_ownership_pg.py`, where real Postgres
can execute the locking it is about. sqlite serialises writers and ignores
`FOR UPDATE`, so nothing in this file could tell a lock from no lock.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timezone

import pytest

from app.utils.event_completion import (
    revived_twin_may_be_taken_back,
    row_carries_a_result,
    row_carries_an_authority_id,
)


def _code(fn) -> str:
    """The function's EXECUTABLE source — no docstring, no comments.

    🪤 Every source scan in this file reads this and not `getsource`. The
    docstrings below explain the very rules they pin, by name, at length: a
    scan for "the recall must not say `scheduled`" run over the whole source is
    a guard its own explanation defeats, and a scan for a name that is PRESENT
    passes on a comment that merely mentions it. Both failure modes are silent.
    """
    src = inspect.getsource(fn)
    chunks = src.split('"""')
    if len(chunks) >= 3:
        src = chunks[0] + '"""'.join(chunks[2:])
    return "\n".join(
        line for line in src.splitlines() if not line.strip().startswith("#")
    )


def _permitted(**overrides):
    """The arguments of a take-back that IS allowed, before any override.

    Spelled once so each case below changes exactly one thing. A case that
    built its own full argument set could pass while the permit it is the
    negative of had quietly stopped being reachable.
    """
    args = {
        "retired_by_the_arm": True,
        "has_surviving_counterpart": True,
        "subject_carries_result": False,
        "subject_carries_authority_id": False,
        "a_survivor_carries_evidence": True,
    }
    args.update(overrides)
    return args


class TestTheKeeperIsTheRowWithTheEvidence:
    def test_the_resultless_twin_beside_a_finished_canonical_is_taken_back(self):
        """THE SHIP, as a rule. `15302884` beside `15312312` FINAL 6-3."""
        assert revived_twin_may_be_taken_back(**_permitted()) is True

    def test_a_row_carrying_a_result_is_never_taken_back(self):
        """The test that makes this arm unable to destroy a result.

        By construction, not by the caller's care: whichever row the screen
        pairs it with, and whatever that row holds, a score or a `completed_at`
        on the SUBJECT ends the question.
        """
        assert (
            revived_twin_may_be_taken_back(**_permitted(subject_carries_result=True))
            is False
        )

    def test_an_anchored_row_is_left_to_the_anchor_channel(self):
        """D39's line. An `espn_id`/`statpal_fixture_id` row is #2693's."""
        assert (
            revived_twin_may_be_taken_back(
                **_permitted(subject_carries_authority_id=True)
            )
            is False
        )

    def test_an_orphan_is_kept_because_voiding_it_deletes_the_game(self):
        """The #7260 harm, arrived at from the other side."""
        assert (
            revived_twin_may_be_taken_back(
                **_permitted(has_surviving_counterpart=False)
            )
            is False
        )

    def test_two_evidenceless_rows_are_a_pair_this_arm_cannot_rank(self):
        """"We cannot tell" is never spent as "go ahead".

        Both past kickoff, neither holding anything: #7617's shape, not this
        arm's. Guessing here would void a card on a coin flip.
        """
        assert (
            revived_twin_may_be_taken_back(
                **_permitted(a_survivor_carries_evidence=False)
            )
            is False
        )

    def test_the_arms_own_ledger_is_the_scope(self):
        """2,544 rows are `voided` for unrelated reasons and match the rule.

        The same fence the revival predicate carries, for the same reason: a
        take-back keyed on anything but membership of the #7260 arm's own
        backup table reaches rows this ship never touched.
        """
        assert (
            revived_twin_may_be_taken_back(**_permitted(retired_by_the_arm=False))
            is False
        )

    def test_every_input_must_be_answered(self):
        """Keyword-only with no defaults, so a stale caller cannot be permissive.

        A default here would let a call site written before a refusal existed
        keep compiling and keep getting the permissive answer — which is how a
        guard is deleted without anybody editing it.
        """
        sig = inspect.signature(revived_twin_may_be_taken_back)
        assert [p.name for p in sig.parameters.values() if p.default is not p.empty] == []
        assert all(
            p.kind is inspect.Parameter.KEYWORD_ONLY
            for p in sig.parameters.values()
        )
        with pytest.raises(TypeError):
            revived_twin_may_be_taken_back(  # type: ignore[call-arg]
                retired_by_the_arm=True,
                has_surviving_counterpart=True,
                subject_carries_result=False,
            )


class TestWhatCountsAsEvidence:
    @pytest.mark.parametrize(
        "home,away,completed",
        [
            (6, 3, None),
            (0, 0, None),
            (None, 3, None),
            (None, None, datetime(2026, 9, 21, 1, 41, tzinfo=timezone.utc)),
        ],
    )
    def test_a_score_or_a_completed_at_is_a_result(self, home, away, completed):
        """`0-0` is a result too — the scoreless draw is the case that proves it."""
        assert row_carries_a_result(home, away, completed) is True

    def test_nothing_present_is_no_result(self):
        assert row_carries_a_result(None, None, None) is False

    @pytest.mark.parametrize(
        "espn,statpal", [("401879932", None), (None, "649046"), ("1", "2")]
    )
    def test_either_provider_id_is_an_anchor(self, espn, statpal):
        assert row_carries_an_authority_id(espn, statpal) is True

    @pytest.mark.parametrize(
        "espn,statpal", [(None, None), ("", ""), ("  ", None), (None, " ")]
    )
    def test_an_empty_string_is_not_an_id(self, espn, statpal):
        """A provider that wrote an empty string has told us nothing."""
        assert row_carries_an_authority_id(espn, statpal) is False


class TestTheArmIsBoundedAndUndoable:
    def test_it_shares_one_bank_and_therefore_one_undo_with_the_one_shot(self):
        """Two tables with one undo pointed at whichever was written first is the
        failure this import exists to prevent."""
        import importlib

        from app.tasks.espn_sync import REVIVED_TWIN_TAKEBACK_BANK_TABLE

        repair = importlib.import_module(
            "scripts.repair_7594_revoid_published_reversed_twins"
        )
        assert repair.BANK_TABLE == REVIVED_TWIN_TAKEBACK_BANK_TABLE

    def test_the_restore_rail_is_a_gate_not_a_log(self):
        """No bank, no writes — the #5532 arm's rule, and this arm writes a
        terminal too, so it may not write one it could not give back."""
        from app.tasks import espn_sync

        src = _code(espn_sync._take_back_revived_twins_impl)
        assert "REVIVED_TWIN_TAKEBACK_BANK_TABLE" in src
        assert "to_regclass" in src
        # The gate returns rather than logging on: a `logger.warning` followed
        # by the loop would be the same sentence with none of the protection.
        gate, _, rest = src.partition("to_regclass")
        assert "return stats" in rest.split("candidate_ids")[0], (
            "the missing-table branch must RETURN before the recall"
        )
        assert "candidate_ids" not in gate

    def test_the_pass_is_capped(self):
        """A blast-radius bound, and the only one: this arm has no attended door."""
        from app.tasks import espn_sync

        assert espn_sync.REVIVED_TWIN_TAKEBACK_MAX_PER_PASS == 25
        assert "LIMIT :cap" in _code(espn_sync._take_back_revived_twins_impl)

    def test_the_scope_is_the_ledger_join(self):
        """A source scan because the JOIN is what establishes
        `retired_by_the_arm=True`; a bare status test would hand the predicate a
        `True` it had not earned."""
        from app.tasks import espn_sync

        src = _code(espn_sync._take_back_revived_twins_impl)
        assert "UNREACHABLE_SUSPENDED_BACKUP_TABLE" in src
        assert "JOIN" in src

    def test_the_recall_cannot_starve_the_end_where_the_harm_is(self):
        """Ordered by distance from now, from BOTH directions.

        This population does not expire and does not fully drain — a row the
        screen refuses stays in it forever — so a plain oldest-first or
        newest-first eventually fills the head with permanent refusals and never
        reaches tonight's twins (gotcha #41).
        """
        from app.tasks import espn_sync

        src = _code(espn_sync._take_back_revived_twins_impl)
        assert "abs(extract(epoch FROM (e.commence_time - now())))" in src

    def test_the_recall_does_not_key_on_scheduled(self):
        """The production specimen is `suspended`, not `scheduled`.

        `15302884` was revived `voided → scheduled` and drifted to `suspended`
        when its kickoff passed with no data. The one-shot repair's selector
        with its clock bound flipped would select none of the four rows this arm
        exists for, so a later edit that "tidies" this recall into that one is a
        silent regression to zero.

        Asserted on the RECALL, not on the function's source: the docstring
        explaining all of the above says the word "scheduled" five times, and a
        scan of the whole source would be a guard its own explanation defeats.
        """
        from app.tasks import espn_sync

        recall = _code(espn_sync._take_back_revived_twins_impl).split("candidate_ids")[1]
        assert "e.status <> :terminal" in recall
        assert ":scheduled" not in recall

    def test_the_pass_runs_on_the_existing_beat(self):
        """No new beat entry: the take-back is the other half of the revival's
        pass, so it inherits that task's queue, cadence and non-heavy status."""
        from app.tasks import espn_sync

        assert "_take_back_revived_twins_impl()" in _code(
            espn_sync._revive_retired_future_starts_impl
        )

    def test_the_unscreenable_sentinel_is_read_as_a_refusal(self):
        """`None` means the screen could not be run, and for a take-back that is
        the opposite of a survivor.

        `_counterpart_screen_refuses` folds `None` in with "a survivor exists"
        because for the REVIVAL both answers mean "do not publish". Spending
        that boolean here would read "we could not tell" as a licence to write.
        """
        from app.tasks import espn_sync

        src = _code(espn_sync._take_back_revived_twins_impl)
        assert "_counterpart_screen_refuses" not in src
        assert "survivors is None" in src
