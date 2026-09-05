"""CAL-P1004 (#1852 FORWARD half): the poll stops declaring losses the venue never did.

CAL-P053 shipped the three-state read (``gradeable_winner``) in August and
``backfill_winners`` adopted it. ``app/tasks/kalshi.py`` did not — FIVE UPDATE
statements there kept their own ``is_winner = (result == "yes")``, and Kalshi
returns the empty STRING for a market it has not called. So the backward repair
spent three weeks draining a population the live poll was refilling every two
hours, onto ``api_settlement``, the top authority rung that
``resolution_authority.is_downgrade`` then protects from correction.

Two of the five were the per-market upserts. The other three were raw SQL, and
one of those is a BATCH update whose partition sent every non-``"yes"`` value —
including ``""`` — to the losing list, which is why the population runs to tens
of thousands of legs rather than a handful.

MEASURED against the venue on 2026-09-04 (public Kalshi ``/markets?tickers=…``,
120 legs our DB graded ``is_winner=false`` / ``api_settlement`` on tier<=2
markets we still call OPEN):

    111  status=active     result=""      still trading, never graded
      8  status=finalized  result="yes"   the venue says they WON
      0  real losses

Not one of the 120 was a true loss. Those two venue states are the
parametrized cases below, quoted from that probe rather than invented.

WHY BOTH A BEHAVIOURAL AND A SOURCE-TEXT GUARD. The judgment is pure and is
tested as such. But the defect was never a wrong judgment — the right judgment
already existed and shipped; the defect was a *write site that did not call it*,
and a third such site added tomorrow would pass every behavioural test in this
file. ``TestNoTwoStateGradeSurvivesInTheTask`` is the guard for the class.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.utils.kalshi_market_status import (
    VENUE_SETTLEMENT_SOURCE,
    graded_columns,
    gradeable_winner,
)

TASK_SOURCE = Path(__file__).resolve().parents[1] / "app" / "tasks" / "kalshi.py"

#: The two venue states the 2026-09-04 probe actually returned for legs we had
#: already graded as losses. Neither may produce a write.
MEASURED_UNGRADED_STATES = [
    pytest.param("active", "", id="111-of-120-still-trading"),
    pytest.param("finalized", "scalar", id="settles-on-a-number-not-a-side"),
    pytest.param("closed", "", id="terminal-but-uncalled"),
    pytest.param("active", None, id="no-result-field-at-all"),
]


class TestTheVenueMustHaveAnswered:
    """An absence is never recorded as a fact (gotcha #53)."""

    @pytest.mark.parametrize("status,result", MEASURED_UNGRADED_STATES)
    def test_ungraded_venue_state_writes_nothing(self, status, result):
        assert graded_columns(status, result) == {}

    @pytest.mark.parametrize("status,result", MEASURED_UNGRADED_STATES)
    def test_and_the_judgment_underneath_agrees(self, status, result):
        assert gradeable_winner(status, result) is None

    def test_the_empty_string_is_the_whole_bug(self):
        """``result is not None`` was the old predicate, and ``""`` passes it.

        Spelled as the old predicate applied to the measured value, so the line
        that reads as a tautology is in fact the defect: the venue's "still
        trading" marker satisfied the guard and then failed ``== "yes"``.
        """
        venue_says_nothing_yet = ""
        assert (venue_says_nothing_yet is not None) is True
        assert graded_columns("active", venue_says_nothing_yet) == {}


class TestARealDeclarationStillLands:
    """The fix must not stop grading — it must stop grading the UNGRADED."""

    def test_venue_says_no(self):
        assert graded_columns("finalized", "no") == {
            "is_winner": False,
            "resolution_source": VENUE_SETTLEMENT_SOURCE,
        }

    def test_venue_says_yes(self):
        assert graded_columns("finalized", "yes") == {
            "is_winner": True,
            "resolution_source": VENUE_SETTLEMENT_SOURCE,
        }

    def test_determined_carries_a_result_too(self):
        assert graded_columns("determined", "yes")["is_winner"] is True

    @pytest.mark.parametrize("result", ["YES", " yes ", "Yes"])
    def test_case_and_whitespace_do_not_lose_a_winner(self, result):
        assert graded_columns("finalized", result)["is_winner"] is True

    def test_the_rung_is_named_once(self):
        """The write site must not spell the authority string itself."""
        assert VENUE_SETTLEMENT_SOURCE == "api_settlement"


class TestAnUngradedPollNeverErases:
    """An empty mapping splatted into an upsert leaves both columns alone.

    This is the shape assertion, not a database round trip: ``set_={... ,
    **graded_cols}`` is what makes "write neither column" the structurally cheap
    branch. A regression that reintroduces ``is_winner=False`` on an unanswered
    venue would show up here as a key that should not be present.
    """

    def test_neither_column_appears_in_an_upsert_payload(self):
        payload = {"last_updated": "now()", **graded_columns("active", "")}
        assert "is_winner" not in payload
        assert "resolution_source" not in payload
        assert payload == {"last_updated": "now()"}

    def test_a_real_grade_does_appear(self):
        payload = {"last_updated": "now()", **graded_columns("finalized", "no")}
        assert payload["is_winner"] is False
        assert payload["resolution_source"] == VENUE_SETTLEMENT_SOURCE


class TestNoTwoStateGradeSurvivesInTheTask:
    """The guard for the CLASS: no write site in the poller may grade by itself.

    ``app/tasks/kalshi.py`` held five independent copies of ``result == "yes"``
    for three weeks after the shared judgment shipped — and CAL-P1004 found the
    last three of them only because an earlier draft of this guard failed. A
    sixth copy is how this recurs, so the file is asserted to contain none — in
    code. Prose may quote the old line (the fix comments do, deliberately), so
    comment lines are stripped before the scan rather than the pattern weakened.
    """

    @staticmethod
    def _code_lines() -> list[str]:
        out = []
        for line in TASK_SOURCE.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            out.append(line.split("  #")[0])
        return out

    #: Any expression whose name ends in ``result`` compared to the literal
    #: ``"yes"``. This is the two-state grade in every form it took in this file:
    #: ``market.result == "yes"``, ``m.result == "yes"``, ``result_val == "yes"``.
    #: The first pattern I wrote here matched only ``.result ==`` and passed while
    #: three ``result_val`` copies were still live, including the batch UPDATE that
    #: produced most of the population — so the pattern is deliberately the
    #: NAME SHAPE, not one spelling of it.
    TWO_STATE_RE = re.compile(r"result\w*\s*==\s*[\"']yes[\"']", re.IGNORECASE)

    def test_no_two_state_grade_remains_anywhere_in_the_file(self):
        offenders = [
            line.strip()
            for line in self._code_lines()
            if self.TWO_STATE_RE.search(line)
        ]
        assert offenders == [], (
            'a write site is grading by itself again — `result == "yes"` maps '
            "every unrecognised venue value onto `this outcome lost`. Call "
            "kalshi_market_status.gradeable_winner()/graded_columns(): "
            + repr(offenders)
        )

    def test_the_ungraded_state_is_never_partitioned_into_losers(self):
        """``if result is None: continue`` was the other half of the bulk bug.

        Skipping only ``None`` leaves ``""`` and ``"scalar"`` in the else-branch.
        The surviving guard must test the three-state judgment, not the raw field.
        """
        code = "\n".join(self._code_lines())
        offenders = re.findall(r"if\s+not\s+\w+\s+or\s+result\w*\s+is\s+None", code)
        assert offenders == [], (
            "an ungraded venue result is being partitioned rather than skipped: "
            + repr(offenders)
        )

    def test_every_grade_site_routes_through_the_shared_judgment(self):
        """Five UPDATE statements graded independently; four decisions now defer.

        Two upsert sites take the column mapping (`graded_columns`). Two raw-SQL
        decisions take the three-state judgment directly (`gradeable_winner`) —
        one of them fans out into the pair of batch UPDATEs that write the yes
        and no lists, which is why four decisions cover five statements. The
        counts are pinned so a new site cannot be added without this test being
        read.
        """
        code = "\n".join(self._code_lines())
        assert code.count("graded_columns(") == 2, code.count("graded_columns(")
        assert code.count("gradeable_winner(") == 2, code.count("gradeable_winner(")

    def test_the_helper_is_imported_not_reimplemented(self):
        code = TASK_SOURCE.read_text()
        assert "from app.utils.kalshi_market_status import" in code
        assert "graded_columns" in code
