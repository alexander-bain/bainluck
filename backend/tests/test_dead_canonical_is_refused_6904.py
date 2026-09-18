"""#6904 — the container sweep stops routing a playable game onto a dead page.

**SHIP: a fixture a reader can still open stops being folded into a page that
answers "This event is no longer listed".** (Pillar: MATCHING.)

Production specimen, 2026-09-18 08:30Z. FC Bayern München v 1. FC Union Berlin,
kick-off 18:30Z the same day, is three rows:

    15304969   voided      polymarket   57 markets   <- the sweep's canonical
    15313023   scheduled   polymarket    6 markets   <- tagged duplicate-of:15304969
    15306036   scheduled   odds_api      4 markets   <- the row search returns

`GET /api/events/15304969/game-markets` serves 86 entries, the duplicate's among
them, and `GET /api/events/15304969` answers **410** because `voided` is in
`event_completion.RETIRED_STATUSES` — so `lib/loadFailure.ts` renders *"This
event is no longer listed"* and not one of those markets is drawn.

Cross-tab of every row in `bak_5821_container_twin_tags`, by BOTH rows' status,
re-read 2026-09-18 08:55Z:

    canonical    duplicate      n   dup upcoming
    scheduled    scheduled    102          102
    voided       voided        70           27
    suspended    suspended     30            0
    scheduled    voided        13           10
    completed    suspended      7            0
    voided       scheduled      2            2    <- live rows, onto a dead page
    voided       suspended      2            0

So the rule refuses **74 of 226**: 70 where both rows were already retired and
the tag delivered nothing in either direction, and **4 where the duplicate's own
page still renders** — the cells where the sweep made a reader's page worse than
not running at all.

🔴 THIS CLASS IS NOT A DRAINED BACKLOG; IT REFILLS ON THE HOUR. The same
cross-tab read 220 rows with ONE `voided ← scheduled` at 08:15Z. The 08:28Z beat
banked a second — `15313072` Borussia Mönchengladbach v 1. FSV Mainz 05,
kick-off the next afternoon, 8 markets onto voided `15305781`. Both destinations
were confirmed by hand: `GET /api/events/15304969` and `/api/events/15305781`
each answer **410**.

🔴 THE TWO CONTROLS ARE THE POINT OF THIS FILE. A refusal aimed at "is a voided
row involved" would also kill the 9 `scheduled` canonicals that hold a `voided`
duplicate — a healthy, working case where the destination page renders fine —
and would take the ship's own 102-row majority with it if it ever reached them.
`test_the_refusal_reads_the_elected_canonical_only` and
`test_the_election_decides_whose_status_is_read` pin that from both sides.
"""

from __future__ import annotations

import ast
import inspect
import textwrap

from app.utils.event_completion import RETIRED_STATUSES
from app.utils.polymarket_container_twins import (
    NOT_A_TWIN,
    REFUSE_AMBIGUOUS,
    REFUSE_ANCHORED,
    REFUSE_DEAD_CANONICAL,
    REFUSE_MIXED_KICKOFF,
    REFUSE_NO_ELECTION,
    ContainerMarket,
    ContainerRow,
    plan_container_tags,
)

#: The specimen's real ids, so a reader of a failure can look the rows up.
CANON_ID = 15304969
DUP_ID = 15313023

KICKOFF = "2026-09-18T18:30:00Z"
BASE = "FC Bayern München vs. 1. FC Union Berlin"


def _m(event_id: int, name: str) -> ContainerMarket:
    return ContainerMarket(event_id=event_id, name=name, venue_game_start=KICKOFF)


#: A split family in the shape the venue publishes it: the base-titled market on
#: one row, the `- More Markets` container and what it decomposes into on the
#: other. Every test here varies only the two rows' STATUS, so any verdict
#: change is attributable to the one field under test.
SPLIT_FAMILY = [
    _m(CANON_ID, BASE),
    _m(CANON_ID, f"{BASE} - Halftime Result"),
    _m(DUP_ID, f"{BASE} - More Markets"),
    _m(DUP_ID, f"{BASE}: O/U 3.5"),
]


def _rows(*, winner_status, loser_status, winner=CANON_ID, loser=DUP_ID):
    """A two-row family whose election `winner` wins, with statuses set.

    Ranks are opaque tuples: the judgement only ever COMPARES them, so a fixture
    reproducing `twin_identity_rank`'s internals would be asserting its own copy
    of the election rather than that the real one is deferred to.
    """
    return {
        winner: ContainerRow(winner, identity_rank=(2,), status=winner_status),
        loser: ContainerRow(loser, identity_rank=(1,), status=loser_status),
    }


class TestTheDeadCanonicalRefusal:
    def test_a_retired_canonical_is_refused_and_nothing_is_tagged(self):
        """The specimen. `15304969` is `voided`, so its page answers 410 — and a
        tag naming it would move `15313023`'s markets somewhere no reader can
        open them, while telling `not_a_proven_duplicate` to stop printing the
        row that is still playable."""
        plan = plan_container_tags(
            SPLIT_FAMILY, _rows(winner_status="voided", loser_status="scheduled")
        )
        assert plan.tags == []
        assert plan.refusals == [f"{REFUSE_DEAD_CANONICAL}: {BASE!r} @ {KICKOFF}"]

    def test_every_word_in_the_retired_vocabulary_is_refused(self):
        """Asserted over the SET, not over the word this issue happened to find.

        `RETIRED_STATUSES` holds `merged` as well as `voided`, and its own note
        says a word is added there when it means "stop showing this". A guard
        naming one literal would pass while the sweep went on tagging into the
        other — and would go on passing for whichever word is added next.
        """
        assert RETIRED_STATUSES, "an empty vocabulary would make this loop vacuous"
        for status in sorted(RETIRED_STATUSES):
            plan = plan_container_tags(
                SPLIT_FAMILY, _rows(winner_status=status, loser_status="scheduled")
            )
            assert plan.tags == [], f"{status} canonical was tagged into"
            assert plan.refusals[0].startswith(REFUSE_DEAD_CANONICAL), status

    def test_the_refusal_reads_the_elected_canonical_only(self):
        """🔴 CONTROL, AND THE COST OF GETTING IT WRONG IS 9 WORKING FAMILIES.

        `scheduled` canonical ← `voided` duplicate is the 9-row cell, and it is
        healthy: the destination page renders, so folding the dead row's markets
        onto it is exactly what the sweep is for. A refusal keyed on "is any
        member retired" would delete that cell and deliver nothing in return.
        """
        plan = plan_container_tags(
            SPLIT_FAMILY, _rows(winner_status="scheduled", loser_status="voided")
        )
        assert [(t.duplicate_id, t.canonical_id) for t in plan.tags] == [
            (DUP_ID, CANON_ID)
        ]
        assert plan.refusals == []

    def test_the_election_decides_whose_status_is_read(self):
        """The same two rows, the same two statuses, only the election flipped —
        and the verdict flips with it. Nothing but "read the winner's status"
        satisfies both halves."""
        voided_wins = plan_container_tags(
            SPLIT_FAMILY,
            _rows(
                winner=CANON_ID,
                winner_status="voided",
                loser=DUP_ID,
                loser_status="scheduled",
            ),
        )
        scheduled_wins = plan_container_tags(
            SPLIT_FAMILY,
            _rows(
                winner=DUP_ID,
                winner_status="scheduled",
                loser=CANON_ID,
                loser_status="voided",
            ),
        )

        assert voided_wins.tags == []
        assert [(t.duplicate_id, t.canonical_id) for t in scheduled_wins.tags] == [
            (CANON_ID, DUP_ID)
        ]

    def test_a_live_family_is_untouched(self):
        """The 102-row majority, and the ship this refusal must not eat."""
        plan = plan_container_tags(
            SPLIT_FAMILY, _rows(winner_status="scheduled", loser_status="scheduled")
        )
        assert len(plan.tags) == 1
        assert plan.refusals == []

    def test_a_completed_family_is_still_tagged(self):
        """A finished match is not a retired one. `completed` rows render, and
        "a settled page that draws no totals is the same defect with the same
        fix" is why this sweep reads 45 days BACKWARDS as well as forwards — so
        a refusal that swallowed them would silently halve its own window."""
        plan = plan_container_tags(
            SPLIT_FAMILY, _rows(winner_status="completed", loser_status="completed")
        )
        assert len(plan.tags) == 1
        assert plan.refusals == []

    def test_a_row_with_no_status_is_reachable(self):
        """The documented fall-through, pinned so it is a decision and not an
        accident: the 410 gate asks `is_retired_event_status` of the identical
        value, and a null status renders. A row we could not read a status for
        is not thereby a dead page."""
        plan = plan_container_tags(
            SPLIT_FAMILY, _rows(winner_status=None, loser_status=None)
        )
        assert len(plan.tags) == 1
        assert plan.refusals == []


class TestTheRuleIsWiredToTheRealVocabularyAndTheRealRow:
    def test_the_vocabulary_is_imported_not_respelled(self):
        """🔴 DOCSTRINGS ARE STRIPPED FIRST and that is not tidiness — the
        sibling guard in `test_existing_split_container_family_5821` records a
        mutation that survived because the comment explaining why a call must
        not be deleted contained the call's own name. The module's prose says
        "voided" several times; only the CODE is searched.
        """
        from app.utils import polymarket_container_twins as judgement

        code = _source_without_docstrings(judgement)

        assert "is_retired_event_status" in code
        assert (
            "voided" not in code
        ), "the retired vocabulary is re-spelled here; import it instead"
        assert "merged" not in code

    def test_the_sweep_hands_the_judgement_the_rows_status(self):
        """The judgement can only read a field the WRITE half passes it. Without
        this line every test above passes against a sweep that never reads
        `events.status` at all and tags into dead pages exactly as before."""
        from app.tasks import polymarket_container_twin_sweep as sweep

        code = _source_without_docstrings(sweep.load_rows)

        assert "status=event.status" in code

    def test_the_verdict_names_are_not_interchangeable(self):
        """Six verdicts, six distinct strings, one exported name. A verdict that
        collided with another would route a refusal into the wrong bucket in the
        receipt the operator reads."""
        from app.utils import polymarket_container_twins as judgement

        verdicts = [
            NOT_A_TWIN,
            REFUSE_AMBIGUOUS,
            REFUSE_ANCHORED,
            REFUSE_DEAD_CANONICAL,
            REFUSE_MIXED_KICKOFF,
            REFUSE_NO_ELECTION,
        ]
        assert len(set(verdicts)) == len(verdicts)
        assert "REFUSE_DEAD_CANONICAL" in judgement.__all__


def _source_without_docstrings(target) -> str:
    """The target's source with every docstring blanked; comments are already
    gone by the time `ast` has parsed it."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(target)))
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            node.value.value = ""
    return ast.unparse(tree)
