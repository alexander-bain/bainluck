"""A withdrawn row is not evidence of agreement, in either direction (#3226).

**SHIP: the 7-day number that decides whether StatPal may become a source of
record stops counting rows the product has already taken down.** (Pillar: TRUTH.
D50.)

The agreement pass never looked at `events.status`. A row retired as `merged` or
`voided` was counted as a live row of ours — it could sit in `ours_only`
forever, or pair with a StatPal fixture and be counted as `both`. Both
directions are wrong and the second is the dangerous one: a sport can flip on
agreement credited by a row whose by-id read returns 410.

WHAT THESE TESTS ARE FOR, BEYOND THE HAPPY PATH
═══════════════════════════════════════════════
Three of them exist because of how this fix could be built *wrongly* and still
look green:

* `TestTheQueryStillSeesEverything` — the tempting fix is a status predicate on
  each stamper's `CANDIDATES` query. That is refused: the comment at
  `stamp_nfl_statpal_fixtures.py:163-169` records that filtering in SQL is what
  made #2963's polluted rows invisible. The row must still ARRIVE and be named.
* `TestLabelIsNotWhatDecides` — our two stampers pass the status string as
  `label` as well, so a fix keyed on `label` passes every obvious test. It is
  still wrong: `label` is documented receipts-only, and tennis's `label` is the
  sport key. This pins the distinction.
* `TestEveryCallerStatesTheStatus` — the module can be perfect while no caller
  passes `event_status`, which is both ends green and the ship dead. Checked by
  AST over the real call sites, not by substring: a `Side(` spanning lines
  defeats a grep.
"""

from __future__ import annotations

import ast
import pathlib
from datetime import datetime, timedelta, timezone

import pytest

from app.utils import event_completion
from app.utils.authority_agreement import (
    DEFAULT_EXCLUDED_KEYS,
    Side,
    build_agreement_row,
)

UTC = timezone.utc
KICKOFF = datetime(2026, 12, 27, 18, 0, tzinfo=UTC)
NORMALIZE = lambda v: (v or "").strip().lower()  # noqa: E731
BACKEND = pathlib.Path(__file__).resolve().parents[1]


def fixture_side(ref: str, away: str, home: str, start: datetime = KICKOFF) -> Side:
    return Side(ref=ref, home=home, away=away, start=start, label="Week 17")


def our_row(
    ref: str,
    away: str,
    home: str,
    *,
    status: str = "scheduled",
    start: datetime = KICKOFF,
    held_id: str | None = None,
    label: str | None = None,
) -> Side:
    return Side(
        ref=ref,
        home=home,
        away=away,
        start=start,
        label=status if label is None else label,
        held_id=held_id,
        event_status=status,
    )


def row_for(fixtures, rows) -> dict:
    return build_agreement_row(
        sport_key="americanfootball_nfl",
        fixtures=fixtures,
        rows=rows,
        normalize=NORMALIZE,
    )


class TestARetiredRowLeavesTheDenominator:
    """The two directions, each on its own, and the arithmetic that follows."""

    @pytest.mark.parametrize("status", sorted(event_completion.RETIRED_STATUSES))
    def test_retired_and_unpaired_is_not_ours_only(self, status):
        """The inflating-`ours_only` direction: a sport pinned below its bar.

        Before #3226 the sanctioned repair — retire the duplicate row — could not
        move the number that judged the sport, so a clean 100 was unreachable by
        the one route the product offers.
        """
        row = row_for(
            [fixture_side("1", "Broncos", "Cardinals")],
            [
                our_row("11", "Broncos", "Cardinals"),
                our_row("99", "Ghost", "Phantom", status=status),
            ],
        )
        assert row["identity"]["ours_only"] == 0
        assert row["identity"]["both"] == 1
        assert row["excluded"]["our_retired"] == 1
        # The exclusion has to leave the denominator, not just the numerator —
        # counting it in both places would report 1/2 and read as disagreement.
        assert row["denominator"] == 1
        assert row["identity"]["pct"] == 100.0

    @pytest.mark.parametrize("status", sorted(event_completion.RETIRED_STATUSES))
    def test_retired_but_pairable_is_not_counted_as_both(self, status):
        """The inflating-`both` direction, which is the one that flips a gate.

        This row WOULD pair — same teams, same kickoff. Counting it credits
        agreement to a row no reader can see.
        """
        row = row_for(
            [fixture_side("1", "Broncos", "Cardinals")],
            [our_row("11", "Broncos", "Cardinals", status=status, held_id="1")],
        )
        assert row["identity"]["both"] == 0
        assert row["identity"]["statpal_only"] == 1
        assert row["excluded"]["our_retired"] == 1
        # StatPal really does have a fixture we no longer carry, so `statpal_only`
        # is the honest bucket — the retirement did not make the fixture go away.
        assert row["denominator"] == 1

    def test_a_live_row_is_untouched(self):
        """The control. Without it, `exclude everything` passes both tests above."""
        row = row_for(
            [fixture_side("1", "Broncos", "Cardinals")],
            [our_row("11", "Broncos", "Cardinals")],
        )
        assert row["identity"]["both"] == 1
        assert row["excluded"]["our_retired"] == 0
        assert row["denominator"] == 1

    def test_an_unstated_status_stays_in_the_denominator(self):
        """`None` is *not stated*, and the safe reading of that is *keep it*.

        A caller that forgets `event_status` then under-excludes and reports a
        WORSE number than the truth. The opposite default would silently inflate
        agreement, which is the failure this whole issue is about.
        """
        row = row_for(
            [fixture_side("1", "Broncos", "Cardinals")],
            [Side(ref="11", home="Cardinals", away="Broncos", start=KICKOFF)],
        )
        assert row["excluded"]["our_retired"] == 0
        assert row["identity"]["both"] == 1

    def test_an_unrecognised_status_stays_in_the_denominator(self):
        """We have no standing to hide a state we do not recognise."""
        row = row_for(
            [fixture_side("1", "Broncos", "Cardinals")],
            [our_row("11", "Broncos", "Cardinals", status="postponed")],
        )
        assert row["excluded"]["our_retired"] == 0
        assert row["identity"]["both"] == 1


class TestTheIssuesOwnProofTable:
    """#3226's reported numbers, reproduced through the shipped code path.

    The issue drove the real `build_agreement_row` with the two production rows
    for Broncos@Cardinals and recorded that `merged` and `voided` were
    indistinguishable from `scheduled`. That table is the regression: if any of
    the first three rows ever stops reading 50.0 for the wrong reason, or the
    fourth stops reading 100.0, the defect is back.
    """

    def _pct(self, status: str | None) -> float:
        phantom = (
            Side(ref="14751059", home="Cardinals", away="Broncos", start=KICKOFF)
            if status is None
            else our_row("14751059", "Broncos", "Cardinals", status=status)
        )
        row = row_for(
            [fixture_side("280624", "Broncos", "Cardinals")],
            [
                our_row(
                    "14781722",
                    "Broncos",
                    "Cardinals",
                    start=KICKOFF + timedelta(minutes=5),
                    held_id="280624",
                ),
                phantom,
            ],
        )
        return row["identity"]["pct"]

    def test_a_live_phantom_halves_the_number(self):
        # `None` here means "no status stated", the pre-#3226 world exactly:
        # the module had nothing to consult, so the phantom counted.
        assert self._pct(None) == 50.0

    @pytest.mark.parametrize("status", ["merged", "voided"])
    def test_retirement_now_moves_the_number_to_a_clean_hundred(self, status):
        assert self._pct(status) == 100.0


class TestTheVocabularyIsSharedNotCopied:
    """Mutating `RETIRED_STATUSES` must move the count, or this is prose.

    The point of importing the function rather than the frozenset is that there
    is ONE definition of retirement. A second copy inside this module would pass
    every test above while drifting from what `/api/events` hides.
    """

    def test_widening_the_vocabulary_excludes_a_previously_counted_row(
        self, monkeypatch
    ):
        before = row_for(
            [fixture_side("1", "Broncos", "Cardinals")],
            [our_row("11", "Broncos", "Cardinals", status="postponed")],
        )
        assert before["excluded"]["our_retired"] == 0

        monkeypatch.setattr(
            event_completion,
            "RETIRED_STATUSES",
            frozenset({"merged", "voided", "postponed"}),
        )
        after = row_for(
            [fixture_side("1", "Broncos", "Cardinals")],
            [our_row("11", "Broncos", "Cardinals", status="postponed")],
        )
        assert after["excluded"]["our_retired"] == 1

    def test_narrowing_the_vocabulary_returns_a_row_to_the_denominator(
        self, monkeypatch
    ):
        """The other direction, so the test cannot pass by excluding everything."""
        monkeypatch.setattr(event_completion, "RETIRED_STATUSES", frozenset())
        row = row_for(
            [fixture_side("1", "Broncos", "Cardinals")],
            [our_row("11", "Broncos", "Cardinals", status="merged", held_id="1")],
        )
        assert row["excluded"]["our_retired"] == 0
        assert row["identity"]["both"] == 1


class TestTheQueryStillSeesEverything:
    """Excluded by CLASSIFICATION, never by a filter on the candidate query.

    #2963's polluted rows went invisible because a query filtered them out. The
    retired row must still arrive, still be counted, and still be NAMED.
    """

    def test_the_retired_row_is_named_in_receipts(self):
        row = row_for(
            [fixture_side("1", "Broncos", "Cardinals")],
            [our_row("99", "Ghost", "Phantom", status="merged")],
        )
        receipts = row["receipts"]["our_retired"]
        assert [r["event_id"] for r in receipts] == ["99"]
        assert receipts[0]["event_status"] == "merged"

    def test_our_retired_is_a_default_key_so_it_always_publishes(self):
        """`0` reads *measured, none*; an absent key reads *nothing at all*.

        The same #3275 distinction the refusal vocabulary was given, applied to
        this exclusion — and it is what makes `our_retired` a name a strategy
        may not reuse (`Join.__post_init__` refuses the collision).
        """
        assert "our_retired" in DEFAULT_EXCLUDED_KEYS
        row = row_for(
            [fixture_side("1", "Broncos", "Cardinals")],
            [our_row("11", "Broncos", "Cardinals")],
        )
        assert row["excluded"]["our_retired"] == 0
        assert row["receipts"]["our_retired"] == []


class TestLabelIsNotWhatDecides:
    """`label` is receipts. `event_status` is consulted. They are not the same.

    Both NFL and v1 pass the status string to BOTH fields, so a fix keyed on
    `label` would pass every other test in this file. Tennis is the proof that
    it would be wrong: its `label` is the sport key.
    """

    def test_a_label_saying_merged_does_not_exclude_a_live_row(self):
        row = row_for(
            [fixture_side("1", "Broncos", "Cardinals")],
            [
                our_row(
                    "11",
                    "Broncos",
                    "Cardinals",
                    status="scheduled",
                    label="merged",
                )
            ],
        )
        assert row["excluded"]["our_retired"] == 0
        assert row["identity"]["both"] == 1

    def test_a_tennis_shaped_label_does_not_stop_the_exclusion(self):
        """Tennis's `label` is `tennis_atp_us_open` and never a status."""
        row = row_for(
            [fixture_side("1", "Broncos", "Cardinals")],
            [
                our_row(
                    "11",
                    "Broncos",
                    "Cardinals",
                    status="merged",
                    label="tennis_atp_us_open",
                )
            ],
        )
        assert row["excluded"]["our_retired"] == 1


class TestEveryCallerStatesTheStatus:
    """Both ends green and the ship dead is the failure this prevents.

    Parsed, not grepped: `Side(` spans several lines at every one of these call
    sites, so a substring guard is defeated by the line break that is already
    there.
    """

    #: Every module that builds a `Side` for OUR side of the comparison. A new
    #: stamper that forgets `event_status` under-excludes silently, so the list
    #: is asserted complete below rather than merely iterated.
    CALLERS = (
        "app/tasks/stamp_nfl_statpal_fixtures.py",
        "app/tasks/stamp_v1_statpal_fixtures.py",
        "app/tasks/link_tennis_statpal_fixtures.py",
    )

    def _side_calls(self, relpath: str) -> list[ast.Call]:
        tree = ast.parse((BACKEND / relpath).read_text())
        return [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Side"
        ]

    @pytest.mark.parametrize("relpath", CALLERS)
    def test_the_row_side_passes_event_status(self, relpath):
        """The `Side` carrying `held_id` is ours; ours must state its status.

        `held_id` is what `events.statpal_fixture_id` holds, so only our side
        ever sets it — which makes it the marker for "this is the row side"
        without this test having to know each caller's variable names.
        """
        ours = [
            call
            for call in self._side_calls(relpath)
            if any(kw.arg == "held_id" for kw in call.keywords)
        ]
        assert ours, f"{relpath} builds no row-side Side (held_id absent)"
        for call in ours:
            assert any(kw.arg == "event_status" for kw in call.keywords), (
                f"{relpath}: a row-side Side omits event_status, so every "
                "retired row in this sport stays in the denominator"
            )

    def test_the_caller_list_is_complete(self):
        """A fourth stamper must land in `CALLERS`, not slip past it."""
        found = sorted(
            str(p.relative_to(BACKEND))
            for p in (BACKEND / "app").rglob("*.py")
            if "Side(" in p.read_text() and "held_id=" in p.read_text()
        )
        assert found == sorted(self.CALLERS)


class TestTennisReadsTheStatusItNeeds:
    """Tennis had to widen its own query, and that is easy to lose in a rebase.

    `MEASUREMENT_ROWS` is the only one of the three candidate queries that did
    not already select `e.status`, so tennis is the sport where this ship breaks
    first and most quietly.
    """

    def test_measurement_rows_selects_status(self):
        from app.tasks.link_tennis_statpal_fixtures import MEASUREMENT_ROWS

        assert "e.status" in MEASUREMENT_ROWS

    def test_the_side_reads_the_column_the_query_added(self):
        """Positional decode: `e.status` is column 6, and `r[6]` must be read.

        A SELECT that gains a column while the decode keeps its old indices is
        the classic silent break — it would put the sport key in `event_status`
        and never raise.
        """
        source = (
            BACKEND / "app/tasks/link_tennis_statpal_fixtures.py"
        ).read_text()
        tree = ast.parse(source)
        sides = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Side"
            and any(kw.arg == "held_id" for kw in node.keywords)
        ]
        assert len(sides) == 1
        kw = {k.arg: k.value for k in sides[0].keywords}
        assert isinstance(kw["event_status"], ast.Subscript)
        assert kw["event_status"].slice.value == 6
