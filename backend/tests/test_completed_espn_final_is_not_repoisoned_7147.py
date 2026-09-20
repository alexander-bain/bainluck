"""#7147 / CERT-3145 — a repaired final stays repaired.

WHY THIS FILE EXISTS
--------------------
The #7147 cleanup deletes post-full-time score snapshots and restores the
ESPN-authoritative final onto the event row. Applied to production on
2026-09-19 at 22:37Z, it worked — and by **23:15:07Z event 15313146 was serving
7-2 again**, with a freshly stamped `score_history` row to match, against ESPN's
7-3. CERT-3145 BLOCKED the cleanup for exactly that: the branch swept residue
and never touched the writer that produces it, so the repair was a deletion with
a half-life of under an hour.

The writer is `odds_polling`'s Odds API scores feed. It carries no clock and no
period, and its only deferral — `clockless_write_defers_to_authority` — is
`status == "live" and bool(espn_id)`, which is False for a completed row. That
exclusion is deliberate and its docstring says why: *"the write that lands a
FINAL score must never be withheld."*

🔴 **THE DISTINCTION THE OLD GUARD COULD NOT MAKE.** Landing a final on a row
that holds none, and overwriting a final an ESPN-anchored row already holds, are
two different writes. The single word `completed` was covering both, so keeping
the first meant permitting the second. `clockless_write_repoisons_a_settled_final`
splits them: the carve-out survives intact (a settled row with a NULL half still
takes the write) and only a CONFLICTING write onto a complete stored pair is
refused.

WHAT IS NOT CLAIMED HERE
------------------------
That the Odds API is wrong and ESPN is right in general. The rule is a
PRECEDENCE, identical in shape to #6056's: the feed that cannot say where the
game is does not get to move a number an authority feed already banked. A
genuine correction from ESPN still lands, because ESPN does not write through
this path.
"""

from __future__ import annotations

import ast
import inspect
import textwrap

import pytest

from app.utils.espn_tennis_anchor import SETTLED_STATUSES
from app.utils.game_pairing import (
    SETTLED_STATUSES_CLAIMING_A_RESULT,
    clockless_write_defers_to_authority,
    clockless_write_repoisons_a_settled_final,
)

#: The specimen CERT-3145 measured, and the one the ship is named for.
#: Rangers–Red Sox, ESPN 401816966, repaired to 7-3 at 22:37Z and serving 7-2
#: again at 23:15:07Z.
SPECIMEN_ESPN_ID = "401816966"
AUTHORITATIVE = (7, 3)
STALE = (7, 2)


def _repoisons(**kw):
    """The predicate with the specimen's shape as the default background."""
    return clockless_write_repoisons_a_settled_final(
        **{
            "event_status": "completed",
            "espn_id": SPECIMEN_ESPN_ID,
            "home_score": STALE[0],
            "away_score": STALE[1],
            "stored_home_score": AUTHORITATIVE[0],
            "stored_away_score": AUTHORITATIVE[1],
            **kw,
        }
    )


class TestTheSpecimenThatCERT3145Measured:
    """The named acceptance: the repaired row survives the next poll."""

    def test_completed_espn_final_survives_clockless_writer_and_writes_no_snapshot(
        self,
    ):
        """🔴 THE SHIP, IN ONE ASSERTION.

        Event 15313146 holds ESPN's 7-3 with an `espn_id`. The Odds API pass
        arrives five minutes later still carrying 7-2. Before this repair the
        write landed and a `score_history` row was stamped; now it is refused,
        and because the refusal is carried on `_skip_score_write` (asserted
        structurally below) the snapshot is declined with it.
        """
        assert _repoisons() is True

    def test_the_old_guard_alone_lets_that_write_straight_through(self):
        """The falsification that makes this file non-redundant. If
        `clockless_write_defers_to_authority` already covered the specimen,
        every assertion here would be decoration on a fixed defect."""
        assert (
            clockless_write_defers_to_authority("completed", SPECIMEN_ESPN_ID)
            is False
        ), (
            "the #6056 deferral now covers completed rows, so this whole file "
            "is testing a rule something else already enforces — re-read both"
        )

    def test_the_agreeing_poll_that_follows_is_not_refused(self):
        """Once the venue catches up, the write agrees and must not be counted
        as a refusal — otherwise the counter reads as a guard firing forever on
        a row nobody is fighting over."""
        assert (
            _repoisons(home_score=AUTHORITATIVE[0], away_score=AUTHORITATIVE[1])
            is False
        )


class TestTheCarveOutTheSiblingGuardWasProtecting:
    """`completed` was excluded for a REASON, and the reason still holds."""

    def test_a_settled_row_holding_no_score_still_takes_the_final(self):
        """The write that LANDS a final is never withheld — that is the whole
        of the sibling's carve-out, and narrowing it must not eat it."""
        assert (
            _repoisons(stored_home_score=None, stored_away_score=None) is False
        )

    @pytest.mark.parametrize("missing", ["home", "away"])
    def test_a_half_filled_settled_row_still_takes_the_final(self, missing):
        """A row with one NULL half is not STATING a result, so there is no
        authoritative pair to protect and this write is still the landing one."""
        assert (
            _repoisons(
                **{
                    f"stored_{missing}_score": None,
                }
            )
            is False
        )

    def test_a_row_espn_does_not_cover_is_left_alone(self):
        """Identical to the sibling's reasoning: most college football, handball
        and the smaller soccer leagues have no other score writer at all, so
        deferring there would be deferring to nobody."""
        assert _repoisons(espn_id=None) is False
        assert _repoisons(espn_id="") is False

    @pytest.mark.parametrize("status", ["live", "scheduled", "suspended", None])
    def test_an_unsettled_row_is_not_this_guards_business(self, status):
        """`live` belongs to the #6056 deferral and `scheduled` to nobody. A
        guard that reached them would be a second, unargued opinion on a
        population another rule already orders."""
        assert _repoisons(event_status=status) is False

    def test_a_write_carrying_neither_side_is_not_a_write(self):
        """Refused first, so a pass that touched nothing can never increment the
        counter — the counter is the only way to tell this guard holding from
        the population being empty."""
        assert _repoisons(home_score=None, away_score=None) is False


class TestItJudgesThePairTheRowWillHold:
    """CERT-2963's correction, inherited rather than re-learned.

    `odds_polling` writes the two halves in INDEPENDENT statements, so a payload
    carrying one side lands on top of whatever the row already holds. A
    predicate that judged the PAYLOAD would be answering about a score that
    never exists.
    """

    def test_a_one_sided_payload_that_would_change_the_pair_is_refused(self):
        """Stored 7-3, incoming `away=2` alone → the row will HOLD 7-2. This is
        the exact shape the specimen arrived in and the one a payload-only
        reading calls 'one side missing, not a claim'."""
        assert _repoisons(home_score=None, away_score=2) is True

    def test_a_one_sided_payload_that_agrees_is_allowed(self):
        """Stored 7-3, incoming `home=7` alone → the row will still HOLD 7-3.
        Nothing moves, so nothing is refused."""
        assert _repoisons(home_score=7, away_score=None) is False

    def test_the_other_side_of_the_same_coin(self):
        assert _repoisons(home_score=None, away_score=3) is False
        assert _repoisons(home_score=6, away_score=None) is True

    @pytest.mark.parametrize("status", sorted(SETTLED_STATUSES_CLAIMING_A_RESULT))
    def test_both_settled_statuses_are_reached(self, status):
        """`closed` is as much a claim to a reader as `completed`; a rule that
        read only the latter would leave half the settled population open."""
        assert _repoisons(event_status=status) is True


class TestTheVocabularyCannotDriftFromTheRailBesideIt:
    """`game_pairing` spells the settled statuses itself so it can keep
    importing nothing but the standard library. That is only safe if a drift is
    loud."""

    def test_the_settled_vocabulary_agrees_with_the_tennis_rails(self):
        assert set(SETTLED_STATUSES_CLAIMING_A_RESULT) == set(SETTLED_STATUSES), (
            "game_pairing's settled vocabulary has drifted from "
            "espn_tennis_anchor.SETTLED_STATUSES; one of the two writers now "
            "judges a status the other does not"
        )

    def test_it_is_not_vacuous(self):
        """A tuple that had quietly become empty would satisfy the agreement
        test against an equally empty sibling."""
        assert len(SETTLED_STATUSES_CLAIMING_A_RESULT) >= 2
        assert "completed" in SETTLED_STATUSES_CLAIMING_A_RESULT


class TestTheWriterActuallyConsultsIt:
    """🔴 THE MUTANT EVERY BEHAVIOURAL TEST ABOVE SURVIVES.

    A correct predicate that the loop never calls — or calls and then ignores —
    leaves this whole file green. `odds_polling` writes through an
    `update_values` dict and a Core statement, so no ORM scan can see the gate
    either (the blind spot #6056's own suite recorded). These are structural on
    purpose, and they are the same three the #2772 suite keeps beside them.
    """

    def _source(self):
        from app.tasks import odds_polling

        return textwrap.dedent(inspect.getsource(odds_polling))

    def test_the_scores_feed_calls_the_refusal(self):
        calls = {
            node.func.id
            for node in ast.walk(ast.parse(self._source()))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "clockless_write_repoisons_a_settled_final" in calls, (
            "the Odds API scores feed can overwrite a settled authoritative "
            "final again; the #7147 cleanup would be sweeping residue the "
            "writer re-creates within the hour"
        )

    def test_the_refusal_reaches_the_combined_gate(self):
        """Not merely called — carried. Both score writes are conditioned on
        `_skip_score_write`, so a reason that never joins that flag is a
        judgment made and discarded."""
        assert (
            "_skip_score_write = (\n"
            "                                _clockless_write_would_fight\n"
            "                                or _illegal_tennis_final\n"
            "                                or _repoisons_settled_final\n"
            "                            )"
        ) in self._source(), (
            "the settled-repoison refusal no longer joins _skip_score_write, "
            "so the score write ignores it"
        )

    def test_the_snapshot_is_gated_on_the_same_flag(self):
        """#6056's rule, inherited: a snapshot of a score this pass declined to
        store puts a number in the Score Differential chart the event row never
        held — and `score_snapshots` is the table #7147 is cleaning."""
        assert "and not _skip_score_write\n" in self._source(), (
            "score_snapshots can record a refused settled-final overwrite"
        )

    def test_the_refusal_is_counted_so_it_cannot_be_silently_off(self):
        """An invisible refusal cannot be told from a guard that is off."""
        source = self._source()
        assert "scores_refused_settled_repoison += 1" in source
        assert '"scores_refused_settled_repoison": ' in source, (
            "the counter never reaches the task's summary, so nothing outside "
            "this process can see the guard hold"
        )

    def test_the_effective_status_is_passed_not_the_computed_one(self):
        """`event_status` is None on any pass not changing the status, and a row
        that is ALREADY completed is exactly the row at risk — it would slip
        through a check that read the computed value alone. The same correction
        the tennis arm carries three lines above."""
        source = self._source()
        call = source[
            source.index("_repoisons_settled_final = (") : source.index(
                "_skip_score_write = ("
            )
        ]
        assert "event_obj.status" in call, (
            "the repoison check reads the computed status alone, so an "
            "already-completed row is judged as if it had no status"
        )
        assert "stored_home_score=event_obj.home_score" in call
        assert "stored_away_score=event_obj.away_score" in call
