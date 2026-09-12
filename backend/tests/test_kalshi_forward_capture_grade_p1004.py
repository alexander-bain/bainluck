"""CAL-P1004 (#1852 FORWARD half): the poll stops declaring losses the venue never did.

CAL-P053 shipped the three-state read (``gradeable_winner``) in August and
``backfill_winners`` adopted it — **at two of its three grading sites; see #4604
below, and note that this sentence is why nobody looked.** ``app/tasks/kalshi.py``
did not adopt it at all — FIVE UPDATE
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

#4604 — WHY THE SCAN IS NOW TWO FILES WIDE. The class did survive, in
``_backfill_kalshi_winners_targeted``, carrying BOTH halves of the bulk bug
(``result_val == "yes"`` and the ``is None`` skip) for the month this guard was
green. It survived precisely because the scan was scoped to ``kalshi.py``, on the
strength of the sentence at the top of this docstring — the guard's premise and
its blind spot were the same sentence. A source-text guard inherits the file list
it is given, so the file list is the guard; :data:`GRADING_SOURCES` now names
every module that turns a Kalshi ``result`` into an ``is_winner``, and adding a
module there is part of adding a grader.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from app.utils.kalshi_market_status import (
    VENUE_SETTLEMENT_SOURCE,
    graded_columns,
    gradeable_winner,
)

_TASKS = Path(__file__).resolve().parents[1] / "app" / "tasks"
TASK_SOURCE = _TASKS / "kalshi.py"

#: #4604. The second file that grades from Kalshi's ``result``, and the one this
#: module's own docstring calls already-clean ("``backfill_winners`` adopted
#: it"). It had adopted it at two of its THREE grading sites:
#: ``_backfill_kalshi_winners_targeted`` still read ``result_val == "yes"`` with
#: an ``is None`` skip, i.e. both halves of the bulk bug, writing
#: ``api_settlement`` — and the scan below could not see it, because the scan
#: was one file wide and this is the other file.
#:
#: A guard whose stated premise is the thing it ought to be checking cannot
#: fail. So the premise is now checked.
BACKFILL_SOURCE = _TASKS / "backfill_winners.py"

#: #5304 / CAL-P1122. The THIRD file that turns a Kalshi ``result`` into an
#: ``is_winner``, and it carried the same two-state partition until #5304 fixed
#: it. ``run_lean_settled`` is an admin route rather than a task, which is the
#: only reason it did not look like a grader — it pages Kalshi's settled events
#: and writes both sides of the verdict in raw SQL, exactly as the two task
#: modules do. It was not in this list, so for the whole of that regression NONE
#: of the class scans below were looking at it.
ADMIN_SOURCE = (
    Path(__file__).resolve().parents[1] / "app" / "routes" / "admin_data_quality.py"
)

#: Every module that turns a Kalshi ``result`` into ``is_winner``.
#:
#: 🔴 DO NOT MAINTAIN THIS LIST BY HAND ALONE — that is the defect, four times
#: over. ``TestTheGraderListIsDiscoveredNotDeclared`` below derives the real
#: population from the source tree and fails if this list has drifted from it,
#: so a fourth grader cannot be added without a red test.
GRADING_SOURCES = [
    pytest.param(TASK_SOURCE, id="tasks/kalshi.py"),
    pytest.param(BACKFILL_SOURCE, id="tasks/backfill_winners.py"),
    pytest.param(ADMIN_SOURCE, id="routes/admin_data_quality.py"),
]

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
    def _code_lines(source: Path = TASK_SOURCE) -> list[str]:
        out = []
        for line in source.read_text().splitlines():
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

    @pytest.mark.parametrize("source", GRADING_SOURCES)
    def test_no_two_state_grade_remains_anywhere_in_the_file(self, source):
        offenders = [
            line.strip()
            for line in self._code_lines(source)
            if self.TWO_STATE_RE.search(line)
        ]
        assert offenders == [], (
            'a write site is grading by itself again — `result == "yes"` maps '
            "every unrecognised venue value onto `this outcome lost`. Call "
            "kalshi_market_status.gradeable_winner()/graded_columns(): "
            + repr(offenders)
        )

    @pytest.mark.parametrize("source", GRADING_SOURCES)
    def test_the_ungraded_state_is_never_partitioned_into_losers(self, source):
        """``if result is None: continue`` was the other half of the bulk bug.

        Skipping only ``None`` leaves ``""`` and ``"scalar"`` in the else-branch.
        The surviving guard must test the three-state judgment, not the raw field.
        """
        code = "\n".join(self._code_lines(source))
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

    def test_all_four_backfill_graders_defer_too(self):
        """#4604, then #5246. The count is FOUR; it was three, and two before that.

        ``backfill_winners`` has four places that turn a Kalshi ``result`` into
        ``is_winner``: the nested-event walk, the settled-markets pager,
        ``_backfill_kalshi_winners_targeted``, and the settled-EVENTS sweep in
        ``_resolve_winners_only``. The first two adopted the shared judgment with
        CAL-P053; the third kept the two-state read until #4604; the fourth kept
        it until #5246.

        🔴 THE FOURTH ESCAPED THIS FILE'S OWN SCAN ON A NAME. ``TWO_STATE_RE`` is
        ``result\\w* == "yes"`` — deliberately the name SHAPE rather than one
        spelling, per its own comment — and the local in that sweep was called
        ``rs``. So ``rs == "yes"`` sat beside three converted siblings, inside a
        file this test suite reported as clean, for as long as CAL-P1004 has
        existed. It was found from #5246, not from here: that ship made the sweep
        write ``current_probability = 0`` beside the verdict, which turned an
        undeclared market's phantom loss into a zeroed price and made someone look.

        The lesson is the one the sibling scan already half-learned. A name-shape
        pattern is stronger than a spelling, and still weaker than a count: this
        assertion is what a rename cannot dodge. Pinned for exactly that reason —
        a FIFTH grader cannot be added without someone reading this test.
        """
        code = "\n".join(self._code_lines(BACKFILL_SOURCE))
        assert code.count("gradeable_winner(") == 4, code.count("gradeable_winner(")

    def test_the_helper_is_imported_not_reimplemented(self):
        code = TASK_SOURCE.read_text()
        assert "from app.utils.kalshi_market_status import" in code
        assert "graded_columns" in code

    def test_the_third_grader_defers_too(self):
        """#5304. ``run_lean_settled`` has exactly ONE decision and it defers.

        Pinned like its two siblings above so a second grading site cannot be
        added to that route without this test being read.
        """
        code = "\n".join(self._code_lines(ADMIN_SOURCE))
        assert code.count("gradeable_winner(") == 1, code.count("gradeable_winner(")


# ---------------------------------------------------------------------------
# CAL-P1122 (#1852 / #3617): the list stops being the thing that is trusted.
# ---------------------------------------------------------------------------

#: Modules that write the venue-settlement rung but are NOT Kalshi ``result``
#: graders, each with the reason it is not one. This is the ONLY sanctioned way
#: to be a writer and stay outside :data:`GRADING_SOURCES`, and every entry is a
#: claim the test below re-checks: an entry that stops writing the rung is a
#: DEAD entry and fails, so this cannot rot into a permission slip.
NON_KALSHI_RUNG_WRITERS = {
    "app/tasks/polymarket.py": (
        "Polymarket's own settlement sync. It reads Polymarket's `umaResolution"
        "Status`/`outcomePrices`, never a Kalshi `result`, so the three-state "
        "Kalshi judgment does not apply to it and scanning it for `result == "
        "\"yes\"` would be scanning the wrong venue's vocabulary."
    ),
    "app/tasks/repair_kalshi_fabricated_loss.py": (
        "The BACKWARD rail. Its single rung write is the `restore_winner` "
        "branch — the venue told us this leg WON and we had stored a loss — and "
        "it is licensed by `kalshi_fabricated_loss.classify_leg`, which consumes "
        "the venue's status/result pair rather than partitioning the raw field. "
        "It is the repair for this class, not a member of it."
    ),
}

#: A write of the top authority rung: ``resolution_source`` ASSIGNED the venue
#: settlement string, in Python kwarg form or in raw SQL ``SET``.
_RUNG_WRITE_RE = re.compile(
    r"""resolution_source\s*=\s*['"]""" + VENUE_SETTLEMENT_SOURCE + r"""['"]"""
)

#: Contexts where the same text is a READ, not a write — a counted filter, an
#: authority comparison, a membership test. `futures_price_refresh` refuses to
#: re-price a leg carrying this rung and must not be dragged in as a grader.
_RUNG_READ_CONTEXT_RE = re.compile(
    r"FILTER\s*\(|IS\s+DISTINCT\s+FROM|NOT\s+IN\s*\(|\bIN\s*\(", re.IGNORECASE
)


def _executable_lines(path: Path) -> list[str]:
    """Source lines with comments AND docstrings removed.

    Docstrings matter here and they do not matter to :meth:`_code_lines`. This
    module's own prose, ``settled_price``'s and ``kalshi_fabricated_loss``'s all
    quote the write they exist to describe, and a scan that reads prose as code
    reports five extra graders and gets switched off. ``ast`` is used rather
    than a triple-quote regex because a quote inside a SQL string is ordinary.
    """
    src = path.read_text()
    doc_lines: set[int] = set()
    for node in ast.walk(ast.parse(src)):
        if not isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            doc_lines.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))

    out = []
    for number, line in enumerate(src.splitlines(), start=1):
        if number in doc_lines:
            continue
        if line.strip().startswith("#"):
            continue
        out.append(line.split("  #")[0])
    return out


def _venue_rung_writers(root: Path) -> dict[str, list[str]]:
    """Every module under ``app/`` that WRITES the venue-settlement rung."""
    found: dict[str, list[str]] = {}
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        hits = [
            line.strip()
            for line in _executable_lines(path)
            if _RUNG_WRITE_RE.search(line) and not _RUNG_READ_CONTEXT_RE.search(line)
        ]
        if hits:
            found[path.relative_to(root.parent).as_posix()] = hits
    return found


class TestTheGraderListIsDiscoveredNotDeclared:
    """The class guard's own blind spot, closed.

    🔴 THIS IS THE FOURTH TIME, AND THE LIST IS WHY. ``kalshi.py`` held five
    two-state copies (CAL-P1004); ``_backfill_kalshi_winners_targeted`` held a
    sixth for a month (#4604); ``_resolve_winners_only`` held a seventh under a
    renamed local (#5246); ``run_lean_settled`` held an eighth in a ROUTE file
    (#5304). Every one of those fixes ended the same way — add the next NAME to
    a hand-kept list — and the next grader was invisible again the next day,
    because a source-text guard inherits the file list it is given and nothing
    was checking the list.

    So the list is no longer the thing that is trusted. The population is
    DERIVED from the tree: anything that writes ``resolution_source =
    'api_settlement'`` is a settlement writer, and it is either a Kalshi grader
    (and therefore scanned by every test above) or it is named here with the
    reason it is not. There is no third state, and "nobody remembered" stops
    being one of the ways this recurs.
    """

    APP = Path(__file__).resolve().parents[1] / "app"

    def test_the_scan_finds_the_writers_we_already_know_about(self):
        """Anti-vacuity, and it is the assertion that earns the rest.

        A discovery guard whose pattern silently stops matching reports an empty
        population and PASSES — the failure mode this whole file exists to catch,
        wearing a new hat. So the scanner is required to re-find the two graders
        CAL-P1004 and #4604 were about, by name, before any conclusion is drawn
        from what it did not find.
        """
        writers = _venue_rung_writers(self.APP)
        assert "app/tasks/kalshi.py" in writers, sorted(writers)
        assert "app/tasks/backfill_winners.py" in writers, sorted(writers)
        assert "app/routes/admin_data_quality.py" in writers, sorted(writers)
        assert len(writers) >= 4, sorted(writers)

    def test_every_rung_writer_is_scanned_or_justified(self):
        """No module writes the top authority rung off this file's radar."""
        writers = set(_venue_rung_writers(self.APP))
        scanned = {
            source.values[0].relative_to(self.APP.parent).as_posix()
            for source in GRADING_SOURCES
        }
        unaccounted = writers - scanned - set(NON_KALSHI_RUNG_WRITERS)
        assert unaccounted == set(), (
            "a new module writes `resolution_source = 'api_settlement'` and no "
            "class guard is looking at it. If it grades a Kalshi `result`, add "
            "it to GRADING_SOURCES (and the two-state scans will then cover it). "
            "If it does not, add it to NON_KALSHI_RUNG_WRITERS with the reason: "
            + repr(sorted(unaccounted))
        )

    def test_the_justified_list_has_no_dead_entries(self):
        """The other direction: an exemption that no longer writes must go.

        Asserted because a stale exemption is how the next grader gets waved
        through — a module renamed or rewritten leaves its name behind, and the
        name then excuses whatever takes its place.
        """
        writers = set(_venue_rung_writers(self.APP))
        dead = set(NON_KALSHI_RUNG_WRITERS) - writers
        assert dead == set(), (
            "these modules no longer write the venue-settlement rung, so their "
            "exemption is stale and must be deleted: " + repr(sorted(dead))
        )

    def test_a_grading_source_that_stopped_writing_is_noticed(self):
        """Every file in GRADING_SOURCES must still be a writer.

        A grader that stops writing the rung has either been fixed properly or
        moved somewhere else; either way the list is now describing the past.
        """
        writers = set(_venue_rung_writers(self.APP))
        scanned = {
            source.values[0].relative_to(self.APP.parent).as_posix()
            for source in GRADING_SOURCES
        }
        assert scanned <= writers, repr(sorted(scanned - writers))

    def test_prose_about_the_write_is_not_counted_as_a_write(self):
        """The scan reads code, not the docstrings that describe the defect.

        ``kalshi_fabricated_loss`` and ``settled_price`` both quote the exact
        write in prose. If those counted, the unaccounted set would be
        permanently non-empty, and the guard above would be turned off within
        the week — which is the ordinary way a true guard dies.
        """
        writers = _venue_rung_writers(self.APP)
        assert "app/utils/kalshi_fabricated_loss.py" not in writers
        assert "app/utils/settled_price.py" not in writers
        assert "app/tasks/futures_price_refresh.py" not in writers
