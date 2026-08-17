"""The board-drift sentinel must re-detect the drift it was created out of (#1878).

That is the acceptance bar, in chain queue 344's own words: *a drift sentinel
that cannot retro-detect the drift that motivated it is not yet a sentinel.*

The 2026-08-11 state, reconstructed
-----------------------------------
Chain queue 344 was written 2026-08-12 from an orphan LIST taken 2026-08-11,
and by the time it ran on 08-14 the list was wrong in both directions:

* it named **4** orphans, and computing the invariant instead found **3 more**
  — ``QUEUE-STAGED-339T-SEASON-SWEEP.md``,
  ``QUEUE-STAGED-CAL-COHORT-HEALTH-SENTINEL.md``,
  ``QUEUE-STAGED-CAL-P045-RULING-024-COMBINED.md``. The last self-declared
  ``status: consumed`` for code that had been REVERTED (``90602414``);
* ``CHAIN.md`` asserted since 08-13 that queue 316's file was "flipped to
  ``consumed``". Only the ``status:`` line INSIDE the file was — the filename
  never changed, and the invariant keys on filenames.

The single most likely way this gets built wrong is that it reads a list
somewhere. ``test_it_finds_the_three_orphans_the_brief_missed`` is the test
that catches that, and it is why the fixture below contains all seven staged
files while CHAIN.md mentions only some of them.
"""

from __future__ import annotations

import pytest

from app.utils.board_drift import (
    ALL_CONDITIONS,
    ConditionResult,
    Finding,
    condition_a_orphan_staged_queues,
    condition_b_dead_promotes_after,
    condition_c_stale_ready_items,
    condition_d_chain_row_file_mismatch,
    condition_e_prose_only_disposition,
    condition_f_over_age_held_rows,
    staged_queue_is_resolved,
    summarise,
)

# --- the 2026-08-11 directory, as it actually stood ------------------------

#: The four the brief knew about.
_ORPHANS_ON_THE_LIST = [
    "QUEUE-STAGED-316-CAL-EXIT-EXAM.md",
    "QUEUE-STAGED-317-SEARCH.md",
    "QUEUE-STAGED-318-GRID.md",
    "QUEUE-STAGED-333-TAUTOLOGY.md",
]

#: The three it did not. Computing the invariant is the ONLY way to reach these.
_ORPHANS_THE_BRIEF_MISSED = [
    "QUEUE-STAGED-339T-SEASON-SWEEP.md",
    "QUEUE-STAGED-CAL-COHORT-HEALTH-SENTINEL.md",
    "QUEUE-STAGED-CAL-P045-RULING-024-COMBINED.md",
]

#: Already dispositioned by FILENAME — must not be reported.
_RESOLVED = [
    "QUEUE-STAGED-344-BOARD-RECONCILIATION.consumed.md",
    "QUEUE-STAGED-310-OLD.superseded.md",
    "QUEUE-NEXT.consumed.md",  # not a QUEUE-STAGED-* file at all
]

HANDOFF_0811 = _ORPHANS_ON_THE_LIST + _ORPHANS_THE_BRIEF_MISSED + _RESOLVED + [
    "CHAIN.md", "QUEUE.md", "README.md", "LANE-lane1.lock",
]

#: CHAIN.md as of 08-11: it names none of the staged files, and it carries the
#: 316 prose claim that made the split invisible.
CHAIN_0811 = """
## THE CHAIN
| 345 | NFL hub | staged |
| 344 | board reconciliation | running |

## RECONCILED
Queue 316's file was flipped to `consumed` on 08-13 — nothing further owed.
See `QUEUE-STAGED-316-CAL-EXIT-EXAM.md` for the record.
"""


class TestConditionAOrphanStagedQueues:

    def test_it_finds_every_orphan_whose_filename_the_chain_never_names(self):
        """Six of the seven — and the seventh is (e)'s, deliberately.

        316's filename IS in CHAIN.md, inside the sentence claiming it was
        already flipped to `consumed`. So (a) is correctly silent on it: its
        question is "does any chain text name this file", and the answer is
        yes. **The mention that satisfies (a) is exactly the mention that hides
        the drift** — which is why the spec added (e) as (a)'s complement
        rather than widening (a).
        """
        r = condition_a_orphan_staged_queues(HANDOFF_0811, CHAIN_0811)
        assert r.verdict == "fail"
        expected = set(_ORPHANS_ON_THE_LIST + _ORPHANS_THE_BRIEF_MISSED) - {
            "QUEUE-STAGED-316-CAL-EXIT-EXAM.md"}
        assert {f.subject for f in r.findings} == expected
        assert len(expected) == 6

    def test_the_two_conditions_together_cover_all_seven(self):
        """Neither check alone sees the whole 08-11 orphan generation."""
        a = condition_a_orphan_staged_queues(HANDOFF_0811, CHAIN_0811)
        e = condition_e_prose_only_disposition(CHAIN_0811, HANDOFF_0811)
        covered = {f.subject for f in a.findings} | {f.subject for f in e.findings}
        assert covered == set(_ORPHANS_ON_THE_LIST + _ORPHANS_THE_BRIEF_MISSED)

    def test_it_finds_the_three_orphans_the_brief_missed(self):
        """THE test. If this fails while the previous one passes, the check is
        reading a list from somewhere and must be rewritten."""
        r = condition_a_orphan_staged_queues(HANDOFF_0811, CHAIN_0811)
        subjects = {f.subject for f in r.findings}
        for missed in _ORPHANS_THE_BRIEF_MISSED:
            assert missed in subjects, (
                f"{missed} was invisible to the orphan check — this is chain "
                "344's failure verbatim: a list of known orphans cannot find "
                "an unknown one"
            )

    def test_filename_resolved_queues_are_not_reported(self):
        r = condition_a_orphan_staged_queues(HANDOFF_0811, CHAIN_0811)
        for resolved in _RESOLVED:
            assert resolved not in {f.subject for f in r.findings}

    def test_a_queue_named_in_the_chain_is_not_an_orphan(self):
        chain = CHAIN_0811 + "\n| 317 | search | `QUEUE-STAGED-317-SEARCH.md` |\n"
        r = condition_a_orphan_staged_queues(HANDOFF_0811, chain)
        assert "QUEUE-STAGED-317-SEARCH.md" not in {f.subject for f in r.findings}

    def test_the_denominator_is_examined_not_found(self):
        """A clean directory must read `pass`, and an EMPTY one `unknown`."""
        clean = condition_a_orphan_staged_queues(
            ["QUEUE-STAGED-1.md"], "names QUEUE-STAGED-1.md")
        assert clean.verdict == "pass" and clean.checked == 1
        empty = condition_a_orphan_staged_queues(["CHAIN.md"], "")
        assert empty.verdict == "unknown", (
            "nothing examined is not a pass — #1147's chart_density reported a "
            "green empty pass for 21 days"
        )

    @pytest.mark.parametrize("name,resolved", [
        ("QUEUE-STAGED-X.consumed.md", True),
        ("QUEUE-STAGED-X.promoted.md", True),
        ("QUEUE-STAGED-X.superseded.md", True),
        # Real specimens from the live directory: the marker carries its REASON,
        # so it is not the last token. Requiring it to be cost five false
        # orphans on the first live run.
        ("QUEUE-STAGED-1-US-OPEN-ALIAS.superseded-by-4c491eaf-and-1793.md", True),
        ("QUEUE-STAGED-CAL-P045.consumed-then-REVERTED-90602414.md", True),
        ("QUEUE-STAGED-X.md", False),
        # A queue ABOUT consumed things is not a consumed queue. Matching
        # loosely and case-insensitively let this dispose of itself by its own
        # subject matter — the marker must be lowercase after a literal dot,
        # which is what the live directory actually writes.
        ("QUEUE-STAGED-CONSUMED-THINGS.md", False),
        ("QUEUE-STAGED-PROMOTED-QUEUE-AUDIT.md", False),
    ])
    def test_resolution_is_read_from_the_filename(self, name, resolved):
        assert staged_queue_is_resolved(name) is resolved


class TestConditionBDeadPromotesAfter:

    def test_it_finds_318_to_317_and_317_to_316(self):
        files = {
            "QUEUE-STAGED-318-GRID.md": "queue_id: 318\npromotes-after: 317\n",
            "QUEUE-STAGED-317-SEARCH.md": "queue_id: 317\npromotes-after: 316\n",
            "QUEUE-STAGED-345-NFL.md": "queue_id: 345\npromotes-after: 344\n",
        }
        r = condition_b_dead_promotes_after(files, dead_queue_ids={"316", "317"})
        assert {f.subject for f in r.findings} == {
            "QUEUE-STAGED-318-GRID.md", "QUEUE-STAGED-317-SEARCH.md"}
        assert r.checked == 3, "the denominator is queues WITH a promotes-after"

    def test_a_live_gate_is_not_reported(self):
        files = {"q.md": "promotes-after: 344\n"}
        assert condition_b_dead_promotes_after(files, {"316"}).verdict == "pass"

    def test_prose_in_the_gate_is_not_a_gate(self):
        """`promotes-after: nothing (legacy file)` means NO gate.

        The first live run read the word "nothing" as a queue id, found no live
        queue by that name, and reported the file as permanently blocked. It is
        skipped before the denominator, because an examined-gates count that
        includes non-gates is the wrong denominator, not just a wrong finding.
        """
        files = {"legacy.md": "promotes-after: nothing (legacy file)\n"}
        r = condition_b_dead_promotes_after(files, {"316"})
        assert r.findings == [] and r.checked == 0

    def test_a_gate_on_a_COMPLETED_queue_is_still_drift(self):
        """Real specimen, live directory: 334 waits on 333, which is promoted.

        The gate has already fired and 334 is still sitting staged. Per the
        spec this counts — "done/superseded/orphaned" — because a queue waiting
        on an event that already happened is as stuck as one waiting on an
        event that never will, and reads identically from outside.
        """
        files = {"QUEUE-STAGED-334-DEPENDENCY-HYGIENE.md":
                 'status: staged\npromotes-after: 333 (B4 dispositions)\n'}
        r = condition_b_dead_promotes_after(files, {"333"})
        assert len(r.findings) == 1 and r.checked == 1

    def test_files_without_the_key_are_not_counted(self):
        r = condition_b_dead_promotes_after({"q.md": "queue_id: 1\n"}, {"316"})
        assert r.checked == 0 and r.verdict == "unknown"


class TestConditionCStaleReadyItems:

    def test_the_banner_that_stood_from_0811_to_0814(self):
        r = condition_c_stale_ready_items([("#1234 grid tile", 17)])
        assert r.verdict == "fail" and r.findings[0].severity == "P3"

    def test_it_escalates_past_thirty_days(self):
        r = condition_c_stale_ready_items([("#1234", 31)])
        assert r.findings[0].severity == "P2"

    def test_a_fresh_ready_column_passes(self):
        r = condition_c_stale_ready_items([("#1", 3), ("#2", 13)])
        assert r.verdict == "pass" and r.checked == 2

    def test_an_empty_board_is_unknown_not_pass(self):
        assert condition_c_stale_ready_items([]).verdict == "unknown"


class TestConditionDChainRowFileMismatch:
    """P1 — the 333 substitution. The only condition that misdirects work."""

    def test_it_finds_the_333_substitution(self):
        rows = [("333", "QUEUE-STAGED-333-TAUTOLOGY.md")]
        files = {"QUEUE-STAGED-333-TAUTOLOGY.md":
                 "queue_id: 341\nThis file now stages the 341 season sweep.\n"}
        r = condition_d_chain_row_file_mismatch(rows, files)
        assert r.verdict == "fail"
        assert r.findings[0].severity == "P1"

    def test_a_missing_file_is_also_p1(self):
        r = condition_d_chain_row_file_mismatch([("350", "gone.md")], {})
        assert r.findings[0].severity == "P1"

    def test_a_matching_row_passes(self):
        rows = [("333", "f.md")]
        r = condition_d_chain_row_file_mismatch(rows, {"f.md": "queue_id: 333\n"})
        assert r.verdict == "pass"

    def test_a_substring_queue_id_does_not_falsely_match(self):
        """`33` must not be satisfied by a file that only mentions `333`.

        Without the boundary the check passes on near-misses, which is the
        failure mode it exists to catch, wearing a different number.
        """
        r = condition_d_chain_row_file_mismatch(
            [("33", "f.md")], {"f.md": "queue_id: 333\n"})
        assert r.verdict == "fail"


class TestConditionEProseOnlyDisposition:

    def test_it_finds_the_316_prose_filename_split(self):
        r = condition_e_prose_only_disposition(CHAIN_0811, HANDOFF_0811)
        assert r.verdict == "fail"
        assert r.findings[0].subject == "QUEUE-STAGED-316-CAL-EXIT-EXAM.md"

    def test_prose_matching_a_resolved_filename_reports_nothing(self):
        """Prose and filename AGREE, so there is no split to report.

        The verdict is `unknown` rather than `pass`, and that is deliberate:
        nothing was examined, because the only candidate was excluded before
        the check ran. Calling that a pass is the exact false green this
        module's `checked == 0` rule exists to prevent — a green from a
        denominator of zero.
        """
        chain = ("`QUEUE-STAGED-344-BOARD-RECONCILIATION.consumed.md` was "
                 "consumed on 08-14.")
        files = ["QUEUE-STAGED-344-BOARD-RECONCILIATION.consumed.md"]
        r = condition_e_prose_only_disposition(chain, files)
        assert r.findings == [] and r.checked == 0 and r.verdict == "unknown"

    def test_prose_about_a_deleted_file_reports_nothing(self):
        """If the file is gone, the disposition was real — nothing to report."""
        chain = "`QUEUE-STAGED-999-OLD.md` was consumed."
        r = condition_e_prose_only_disposition(chain, [])
        assert r.findings == [] and r.checked == 0

    def test_a_live_unresolved_file_mentioned_WITHOUT_a_disposition_passes(self):
        """The real pass case: something examined, nothing wrong.

        Distinguished from the two above because this one has a non-zero
        denominator — the file is on disk, unresolved, and named in the chain,
        and the chain simply makes no claim about its disposition.
        """
        chain = "| 317 | search | `QUEUE-STAGED-317-SEARCH.md` | staged |"
        r = condition_e_prose_only_disposition(chain, ["QUEUE-STAGED-317-SEARCH.md"])
        assert r.checked == 1 and r.verdict == "pass"

    def test_chain_text_with_no_dispositions_is_unknown(self):
        assert condition_e_prose_only_disposition("## THE CHAIN\n", []).verdict \
            == "unknown"


class TestConditionFOverAgeHeldRows:

    def test_it_finds_both_over_age_rows_from_the_0815_table(self):
        r = condition_f_over_age_held_rows([
            ("339T item 4", 9), ("341 items 1/2/3", 6),
            ("350 item 2b", 3), ("351 all three", 2),
        ])
        assert {f.subject for f in r.findings} == {"339T item 4", "341 items 1/2/3"}
        assert r.checked == 4

    def test_ten_windows_escalates_to_p1(self):
        r = condition_f_over_age_held_rows([("339T item 4", 10)])
        assert r.findings[0].severity == "P1"

    def test_a_young_table_passes(self):
        assert condition_f_over_age_held_rows([("x", 1)]).verdict == "pass"

    def test_an_empty_table_is_unknown(self):
        """An empty HELD table is indistinguishable from an unparsed one."""
        assert condition_f_over_age_held_rows([]).verdict == "unknown"


class TestTheEnvelope:

    def _retro(self):
        return [
            condition_a_orphan_staged_queues(HANDOFF_0811, CHAIN_0811),
            condition_b_dead_promotes_after(
                {"QUEUE-STAGED-318-GRID.md": "promotes-after: 317\n",
                 "QUEUE-STAGED-317-SEARCH.md": "promotes-after: 316\n"},
                {"316", "317"}),
            condition_c_stale_ready_items([("#1234 grid tile", 17)]),
            condition_d_chain_row_file_mismatch(
                [("333", "QUEUE-STAGED-333-TAUTOLOGY.md")],
                {"QUEUE-STAGED-333-TAUTOLOGY.md": "queue_id: 341\n"}),
            condition_e_prose_only_disposition(CHAIN_0811, HANDOFF_0811),
            condition_f_over_age_held_rows([("339T item 4", 9), ("341", 6)]),
        ]

    def test_the_retro_run_goes_RED_on_all_six(self):
        """#1878's acceptance, and the directive's: its first run must PROVE it
        can go RED. A sentinel whose red path has never executed is a sentinel
        whose red path is untested."""
        out = summarise(self._retro())
        assert out["verdict"] == "fail"
        for letter in ALL_CONDITIONS:
            assert out["conditions"][letter]["verdict"] == "fail", (
                f"condition {letter} did not detect its own motivating drift"
            )
        assert out["worst_severity"] == "P1"

    def test_every_condition_is_present_even_when_it_did_not_run(self):
        """An absent key reads as 'nothing to report' to every consumer."""
        out = summarise([ConditionResult("a", checked=1)])
        assert set(out["conditions"]) == set(ALL_CONDITIONS)
        assert out["conditions"]["d"]["verdict"] == "unknown"
        assert out["verdict"] == "unknown", (
            "five conditions did not run and the envelope reported pass"
        )

    def test_all_clean_is_pass(self):
        out = summarise([ConditionResult(c, checked=3) for c in ALL_CONDITIONS])
        assert out["verdict"] == "pass" and out["finding_count"] == 0

    def test_one_unknown_downgrades_an_otherwise_clean_run(self):
        results = [ConditionResult(c, checked=3) for c in ALL_CONDITIONS[:5]]
        results.append(ConditionResult("f", checked=0))
        assert summarise(results)["verdict"] == "unknown"

    def test_a_fail_outranks_an_unknown(self):
        results = [ConditionResult(c, checked=3) for c in ALL_CONDITIONS[:4]]
        results.append(ConditionResult("e", checked=0))
        results.append(ConditionResult(
            "f", checked=1, findings=[Finding("f", "P2", "row", "held 6")]))
        assert summarise(results)["verdict"] == "fail"

    def test_the_envelope_never_invents_a_severity(self):
        assert summarise([ConditionResult(c, checked=1)
                          for c in ALL_CONDITIONS])["worst_severity"] is None
