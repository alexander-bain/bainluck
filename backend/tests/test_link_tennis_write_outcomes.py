"""A link is both shapes or neither. CERT-871 FOLLOW-UP `AUTHORITY-006-LINK-WRITE-OUTCOMES`.

`link_tennis_statpal_fixtures` writes two things per link — `events.statpal_fixture_id`
and the `('statpal', 'tennis:<id>', 'game')` anchor — and the column goes first.
Whether the anchor write is allowed to stand decides whether the pair survives.

## the defect this replaces

The commit branch named the ONE outcome it refused:

    if outcome == COLLISION:   rollback
    if outcome == LOST_RACE:   rollback
    commit                     # ...everything else

That is a whitelist written as a blacklist, and `anchor_channel.record_anchor` has
four outcomes, not two. `STALE_INCUMBENT` and `NO_KEY` both fell through to the
commit, and the row they left is worse than an unlinked one:

* `events.statpal_fixture_id` says the match is linked;
* `event_provider_anchors` holds nothing, so ruling 048's drain clause never sees it;
* the D51 restore cannot undo it — the restore only knows rows the one-time apply
  wrote, and this one was written by the recurring task.

Nothing raises and nothing is counted. The run reports a successful link.

## why the guard is written against `anchor_channel`'s own vocabulary

Listing today's four outcomes here would pass forever and say nothing the moment a
fifth is added — which is exactly how this defect arrived. So the guard ENUMERATES
the outcome constants out of `anchor_channel` and requires each one to be
classified: committable, or explicitly refused. A new outcome fails this file until
somebody decides what it means.
"""

from __future__ import annotations

import pytest

from app.services import anchor_channel
from app.tasks.link_tennis_statpal_fixtures import (
    COMMITTABLE_OUTCOMES,
    LOST_RACE,
)

#: The outcomes `record_anchor` can return, read off the module rather than
#: retyped. `WROTE`/`CONFIRMED`/`COLLISION`/`NO_KEY`/`STALE_INCUMBENT` today.
ANCHOR_OUTCOMES = {
    name: getattr(anchor_channel, name)
    for name in (
        "WROTE",
        "CONFIRMED",
        "COLLISION",
        "NO_KEY",
        "STALE_INCUMBENT",
    )
}


class TestOnlyAnAnchoredLinkIsCommitted:
    def test_wrote_and_confirmed_are_the_only_committable_outcomes(self):
        assert COMMITTABLE_OUTCOMES == {
            anchor_channel.WROTE,
            anchor_channel.CONFIRMED,
        }

    @pytest.mark.parametrize(
        "name", ["COLLISION", "NO_KEY", "STALE_INCUMBENT"]
    )
    def test_every_other_outcome_refuses_the_link(self, name):
        """`NO_KEY` and `STALE_INCUMBENT` are the two that used to slip through."""
        assert ANCHOR_OUTCOMES[name] not in COMMITTABLE_OUTCOMES

    def test_lost_race_is_ours_and_is_not_an_anchor_outcome(self):
        """It means the column was claimed between the query and the write.

        Kept distinct from the anchor vocabulary on purpose: it is not a refusal
        by the channel, it is a refusal by the `IS NULL` guard, and it is counted
        as `already_linked` rather than as a failure.
        """
        assert LOST_RACE not in ANCHOR_OUTCOMES.values()
        assert LOST_RACE not in COMMITTABLE_OUTCOMES

    def test_a_new_anchor_outcome_cannot_arrive_unclassified(self):
        """The guard that would have caught the original defect.

        Every public outcome constant in `anchor_channel` must be either
        committable or one this task has decided to refuse. Add a sixth outcome
        there and this fails here, where the decision belongs — rather than
        silently committing a scalar-only link in production.
        """
        declared = {
            name: value
            for name, value in vars(anchor_channel).items()
            if name.isupper()
            and isinstance(value, str)
            and value == name  # the outcome constants are self-named
        }
        # Sanity: the discovery actually found the vocabulary, so a rename
        # upstream fails loudly instead of emptying this test.
        assert set(ANCHOR_OUTCOMES.values()) <= set(declared.values()), (
            f"the outcome constants moved or were renamed; found {sorted(declared)}"
        )
        refused = set(declared.values()) - COMMITTABLE_OUTCOMES
        assert refused == {
            anchor_channel.COLLISION,
            anchor_channel.NO_KEY,
            anchor_channel.STALE_INCUMBENT,
        }, (
            "an outcome in `anchor_channel` is neither committable nor one of the "
            f"three this task refuses on purpose: {sorted(refused)}. Decide what it "
            "means for a link before it reaches production."
        )


class TestTheRunReportsWhatItRefused:
    def test_a_write_refusal_has_its_own_bucket(self):
        """A refused write is not an unmatched fixture and not a doubles skip.

        It is the one case where we found the match, wanted to link it, and could
        not — which needs a different fix from all three of the others, so it is
        counted and receipted separately.
        """
        from app.tasks.link_tennis_statpal_fixtures import LinkRun

        run = LinkRun()
        assert "write_refusals" in vars(run)
        assert run.summary()["write_refusals"] == 0

        run.write_refusals.append({"statpal_id": "2631673", "outcome": "NO_KEY"})
        summary = run.summary()
        assert summary["write_refusals"] == 1
        assert summary["unmatched"] == 0, "a refusal must not inflate the misses"
        assert summary["linked"] == 0, "and must not read as a success"
