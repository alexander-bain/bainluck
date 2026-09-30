"""#9149 (one-way chain half) — a Polymarket family is one claimant, not two.

THE SHIP: Türkiye 0-1 France (Nations League, 2026-09-25 18:45Z). `15195323` is
the played, ESPN-anchored row a reader lands on, and it serves ZERO markets.
`15310856` is the Polymarket game row (`soccer_other`, unanchored, `suspended`)
holding **401** markets; `15310897` holds 61 more and already carries
`provenance:duplicate-of:15310856`, written by the Polymarket container rail off
a shared provider event id. The fourth pass counted the two copies as rivals and
refused the block as ambiguous on every run, so the result page kept a
sportsbook-only chart while 401 graded markets sat on a row reading "suspended".

`strandable_family_heads` drops a market-holding copy whose `duplicate_of` names
ANOTHER market-holding copy in the same block. What must stay true:

* only a proof pointing INSIDE the strandable set collapses anything — a copy
  naming a row elsewhere (or the played row) is still a rival and still refuses;
* a pair naming EACH OTHER (the #9149 cycle) has no head, so both drop and
  nothing is decided;
* the member keeps its own proof: the tag goes on the head, never the member.

Population drive (production -45d/+5d soccer, 5,558 rows, 2026-09-27): NEW 1 tag
(this specimen), LOST 0.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.utils.soccer_ghost_twins import (  # noqa: E402
    NOT_A_TWIN,
    REFUSE_AMBIGUOUS,
    TWIN_FOUND,
    SoccerRow,
    classify_stranded_block,
    plan_ghost_tags,
    strandable_family_heads,
)

#: Offsets from a fixed anchor (gotcha #44). The real kick-off was 2026-09-25
#: 18:45Z and all three rows share it; only "two days after, same minute" matters.
NOW = datetime(2026, 9, 27, 20, 0, tzinfo=timezone.utc)
KICKOFF = NOW - timedelta(days=2, hours=1, minutes=15)

CANON_ID = 15195323
HEAD_ID = 15310856
MEMBER_ID = 15310897


def row(event_id, *, sport_key="soccer_other", status="suspended", scored=False,
        anchored=False, market_count=0, duplicate_of=None, when=KICKOFF):
    return SoccerRow(
        event_id=event_id,
        sport_key=sport_key,
        home_team_name="Türkiye",
        away_team_name="France",
        commence_time=when,
        status=status,
        has_final_score=scored,
        is_fixture_anchored=anchored,
        market_count=market_count,
        duplicate_of=duplicate_of,
    )


def played(**kw):
    base = dict(sport_key="soccer_uefa_nations_league", status="completed",
                scored=True, anchored=True, market_count=0)
    return row(CANON_ID, **{**base, **kw})


def head(**kw):
    return row(HEAD_ID, **{**dict(market_count=401), **kw})


def member(**kw):
    return row(MEMBER_ID, **{**dict(market_count=61, duplicate_of=HEAD_ID), **kw})


class TestTheSpecimen:
    def test_the_head_is_tagged_onto_the_played_row(self):
        outcome, tag, _ = classify_stranded_block([played(), head(), member()], now=NOW)
        assert outcome == TWIN_FOUND
        assert tag is not None
        assert (tag.ghost_id, tag.canonical_id) == (HEAD_ID, CANON_ID)
        assert "401 market(s)" in tag.reason

    def test_control_without_the_proof_the_block_is_still_refused(self):
        """The same three rows with the member's proof erased is the pre-#9149
        shape, and it must keep refusing: two unrelated market-holding copies
        are exactly what the ambiguity rule exists for."""
        outcome, tag, explanation = classify_stranded_block(
            [played(), head(), member(duplicate_of=None)], now=NOW
        )
        assert outcome == REFUSE_AMBIGUOUS
        assert tag is None
        assert "2 market-holding cop(ies)" in explanation

    def test_it_reaches_the_tag_through_the_whole_planner(self):
        """End to end through `plan_ghost_tags`, with the real sport keys — the
        played row is `soccer_uefa_nations_league`, both copies `soccer_other`."""
        plan = plan_ghost_tags([played(), head(), member()], now=NOW)
        pairs = {(t.ghost_id, t.canonical_id) for t in plan.tags}
        assert (HEAD_ID, CANON_ID) in pairs
        assert all(t.ghost_id != MEMBER_ID for t in plan.tags)
        assert all(t.ghost_id != CANON_ID for t in plan.tags)

    def test_control_the_planner_tags_nothing_without_the_proof(self):
        plan = plan_ghost_tags([played(), head(), member(duplicate_of=None)], now=NOW)
        assert not [t for t in plan.tags if CANON_ID == t.canonical_id]


class TestOnlyAProofInsideTheSetCollapses:
    def test_a_copy_naming_a_row_outside_the_block_still_counts(self):
        outcome, tag, _ = classify_stranded_block(
            [played(), head(), member(duplicate_of=42)], now=NOW
        )
        assert outcome == REFUSE_AMBIGUOUS
        assert tag is None

    def test_a_copy_naming_the_played_row_still_counts(self):
        """The played row is not strandable, so a proof naming it collapses
        nothing here — two copies remain and the block refuses."""
        outcome, tag, _ = classify_stranded_block(
            [played(), head(), member(duplicate_of=CANON_ID)], now=NOW
        )
        assert outcome == REFUSE_AMBIGUOUS
        assert tag is None

    def test_a_mutual_pair_has_no_head_and_decides_nothing(self):
        """The #9149 cycle: each copy names the other. Neither is the head, so
        both drop, and the pass must not pick one."""
        outcome, tag, explanation = classify_stranded_block(
            [played(), head(duplicate_of=MEMBER_ID), member()], now=NOW
        )
        assert outcome == NOT_A_TWIN
        assert tag is None
        assert "no played row with a market-holding copy" in explanation


class TestThePureHelper:
    def test_it_keeps_the_head_and_every_unrelated_copy(self):
        other = row(7, market_count=3)
        kept = strandable_family_heads([head(), member(), other])
        assert [r.event_id for r in kept] == [HEAD_ID, 7]

    def test_a_three_row_chain_keeps_only_its_root(self):
        tail = row(8, market_count=2, duplicate_of=MEMBER_ID)
        kept = strandable_family_heads([head(), member(), tail])
        assert [r.event_id for r in kept] == [HEAD_ID]

    def test_rows_with_no_proof_are_untouched(self):
        rows = [head(), row(9, market_count=1)]
        assert strandable_family_heads(rows) == rows
