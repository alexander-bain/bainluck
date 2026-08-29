"""Q436 / CAL-P117 — the calibration closing line stops publishing a coin flip.

The specimen this file exists for, measured on production 2026-08-29:

    market 56675315  "Miami Marlins vs. Houston Astros - Player Props"  (polymarket)
      fm.resolution_date  2026-07-22 00:10Z    <- Polymarket's own endDate = the game
      e.commence_time     2026-07-23 00:10Z    <- the NEXT game in the same series

    outcome 210410292  "Xavier Edwards: Home Runs O/U 1.5"
      the market quoted it   0.0105   (bid 0.0010 / ask 0.0200, two-sided, pre-game)
      the curve published    0.5005   (bid 0.0010 / ask 1.0000, captured 02:42Z,
                                       two and a half hours after first pitch)

Every snapshot row and every timestamp in this file is real, copied from
``futures_odds_snapshots``. They are not illustrative numbers — a fixture that
drifts to something convenient stops being evidence.

Two independent defects produced that 0.5005, and BOTH are exercised here, because
either one alone still publishes a price nobody quoted:

  * the closing-line window ran to the LINKED EVENT's start, so on a mis-linked
    market it swept up post-settlement quotes (`test_clamp_*`);
  * nothing rejected a #1574 fabricated midpoint on the way in, so an empty book's
    average became a forecast (`test_fabricated_*`).

The last class of tests is the one that keeps the rest honest: they assert the
rule appears in the SQL the task ACTUALLY RUNS. A pure-Python guard over a
re-implementation of a SQL rule stays green while the shipped statement quietly
drops it.
"""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from app.tasks.backfill_winners import (
    _part_a_calibration_sql,
    _part_a_repair_sql,
    _part_c_calibration_sql,
)
from app.utils.calibration_closing_line import (
    closing_line_boundary_sql,
    closing_line_lateral_sql,
    is_eligible_closing_snapshot,
    select_closing_line,
)
from app.utils.feed_market_quality import (
    fabricated_midpoint_sql,
    is_fabricated_midpoint,
)


def _t(hh_mm_ss: str, day: int = 22) -> datetime:
    """A 2026-07-{day} UTC instant, written the way the snapshot table stores it."""
    h, m, s = (int(p) for p in hh_mm_ss.split(":"))
    return datetime(2026, 7, day, h, m, s, tzinfo=timezone.utc)


# The market's own settlement (Polymarket endDate) and the wrong event it is linked
# to. The 24-hour gap between them IS the defect's mechanism.
SETTLEMENT = _t("00:10:00", day=22)
LINKED_EVENT_COMMENCE = _t("00:10:00", day=23)

# outcome 210410292 — "Xavier Edwards: Home Runs O/U 1.5". Real rows.
EDWARDS_SNAPSHOTS = [
    (_t("00:05:56"), 0.0105, 0.0010, 0.0200),
    (_t("00:07:56"), 0.0105, 0.0010, 0.0200),
    (_t("00:09:56"), 0.0105, 0.0010, 0.0200),  # the last real pre-game quote
    (_t("02:38:40"), 0.5005, 0.0010, 1.0000),  # book gone; midpoint of nothing
    (_t("02:40:40"), 0.5005, 0.0010, 1.0000),
    (_t("02:42:40"), 0.5005, 0.0010, 1.0000),  # what the curve published
]

# outcome 210410256 — "Tatsuya Imai: Strikeouts O/U 2.5". Also real, and it is the
# reason the clamp cannot be dropped in favour of the midpoint filter: its
# post-settlement book is 0.81/1.00, a 0.19 spread, which sits UNDER
# FEED_PHANTOM_MIN_SPREAD and is therefore not a fabricated midpoint at all. Only
# the boundary can keep it out.
IMAI_SNAPSHOTS = [
    (_t("00:07:56"), 0.8800, 0.8500, 0.9100),
    (_t("00:09:56"), 0.8800, 0.8500, 0.9100),  # the last real pre-game quote
    (_t("00:13:56"), 0.5000, 0.0100, 0.9900),  # fabricated
    (_t("01:44:40"), 0.5050, 0.0100, 1.0000),  # fabricated
    (_t("02:58:40"), 0.9050, 0.8100, 1.0000),  # settled winner's book — NOT fabricated
    (_t("03:02:40"), 0.9050, 0.8100, 1.0000),  # what the curve published
]


# =========================================================================
# The specimen
# =========================================================================


class TestTheSpecimen:
    def test_edwards_publishes_the_market_quote_not_a_coin_flip(self):
        """0.011 -> 0.5005 is the whole queue. This is the permanent red for it."""
        chosen = select_closing_line(
            EDWARDS_SNAPSHOTS,
            event_commence=LINKED_EVENT_COMMENCE,
            resolution_date=SETTLEMENT,
        )
        assert chosen == pytest.approx(0.0105)
        assert chosen != pytest.approx(0.5005)

    def test_imai_publishes_the_market_quote_not_the_settled_book(self):
        chosen = select_closing_line(
            IMAI_SNAPSHOTS,
            event_commence=LINKED_EVENT_COMMENCE,
            resolution_date=SETTLEMENT,
        )
        assert chosen == pytest.approx(0.8800)

    def test_the_whole_container_stops_spraying_around_one_half(self):
        """The container-level signature: 6.2x too many legs published near 0.50.

        Both legs are quoted far from a coin flip and both were published within
        half a point of one. Asserting each leg separately would let a change that
        fixed one and broke the other pass.
        """
        for snapshots in (EDWARDS_SNAPSHOTS, IMAI_SNAPSHOTS):
            chosen = select_closing_line(
                snapshots,
                event_commence=LINKED_EVENT_COMMENCE,
                resolution_date=SETTLEMENT,
            )
            assert not (0.45 <= chosen <= 0.55)


# =========================================================================
# Arm 1 — the boundary clamp
# =========================================================================


class TestClampArm:
    def test_without_the_clamp_the_settled_book_wins(self):
        """Delete the clamp and Imai goes straight back to 0.905.

        This is the arm's justification stated as a test rather than as a comment:
        the midpoint filter cannot see a 0.19-spread book, so if the boundary is
        the linked event's start, a mis-linked market publishes its settled quote.
        """
        assert select_closing_line(
            IMAI_SNAPSHOTS,
            event_commence=LINKED_EVENT_COMMENCE,
            resolution_date=None,
        ) == pytest.approx(0.9050)

    def test_the_clamp_takes_the_earlier_of_the_two(self):
        assert select_closing_line(
            IMAI_SNAPSHOTS,
            event_commence=SETTLEMENT,
            resolution_date=LINKED_EVENT_COMMENCE,
        ) == pytest.approx(0.8800)

    def test_a_correctly_linked_market_is_untouched(self):
        """The must-not-regress control: when the link is right, nothing moves.

        A game market whose event starts when its market settles has the two
        within minutes, so LEAST() picks a boundary the old rule would also have
        picked and the same snapshot is selected.
        """
        near = SETTLEMENT + timedelta(minutes=3)
        assert select_closing_line(
            IMAI_SNAPSHOTS, event_commence=near, resolution_date=SETTLEMENT
        ) == select_closing_line(IMAI_SNAPSHOTS, event_commence=near, resolution_date=None)

    def test_no_resolution_date_leaves_the_boundary_alone(self):
        """Championship futures and anything else Polymarket gives no endDate for."""
        assert select_closing_line(
            IMAI_SNAPSHOTS, event_commence=SETTLEMENT, resolution_date=None
        ) == pytest.approx(0.8800)

    def test_an_absurdly_early_settlement_falls_back_rather_than_inventing(self):
        """The clamp's failure mode, asserted so it stays the safe one.

        A ``resolution_date`` before the market ever traded yields no eligible
        snapshot, and the caller's ``opening_probability`` fallback applies. That
        is the disclosed ``cp_eq_open`` state (gotcha #144 / ruling 103) — never a
        manufactured number. Deliberately NOT floored at ``fm.commence_time``: a
        GREATEST() floor can push the boundary back past settlement on any row
        whose commence_time is a listing date, which is the defect again.
        """
        assert (
            select_closing_line(
                IMAI_SNAPSHOTS,
                event_commence=LINKED_EVENT_COMMENCE,
                resolution_date=_t("00:00:00", day=1),
            )
            is None
        )


# =========================================================================
# Arm 2 — the fabricated midpoint
# =========================================================================


class TestFabricatedMidpointArm:
    def test_a_fabricated_midpoint_before_the_boundary_is_still_refused(self):
        """The arm carries rows the clamp cannot reach.

        Measured: the props containers with NO window overrun still improved from
        corr 0.8740 to 0.9645 under the fix, because an empty book can collapse
        while the market is still open. Here both rows are pre-boundary and only
        the midpoint filter separates them.
        """
        pre_boundary_only = [
            (_t("00:05:56"), 0.0105, 0.0010, 0.0200),
            (_t("00:07:56"), 0.5005, 0.0010, 1.0000),
        ]
        assert select_closing_line(
            pre_boundary_only,
            event_commence=LINKED_EVENT_COMMENCE,
            resolution_date=SETTLEMENT,
        ) == pytest.approx(0.0105)

    def test_eligibility_rejects_the_specimen_book(self):
        assert is_eligible_closing_snapshot(0.5005, 0.0010, 1.0000) is False

    def test_eligibility_keeps_a_real_two_sided_quote(self):
        assert is_eligible_closing_snapshot(0.0105, 0.0010, 0.0200) is True

    def test_eligibility_keeps_a_bookless_model_price(self):
        """DataGolf and derived complements have no book and must pass through."""
        assert is_eligible_closing_snapshot(0.5000, None, None) is True

    @pytest.mark.parametrize("prob", [0.0, 1.0, -0.1, 1.5, None])
    def test_eligibility_refuses_a_settled_marker(self, prob):
        assert is_eligible_closing_snapshot(prob, 0.4, 0.5) is False


# =========================================================================
# The SQL mirror is a mirror
# =========================================================================


# (probability, yes_bid, yes_ask). Real books wherever one exists.
_MIDPOINT_CASES = [
    (0.5005, 0.0010, 1.0000),   # the specimen
    (0.5050, 0.0100, 1.0000),   # Imai, 01:44Z
    (0.5000, 0.0100, 0.9900),   # Imai, 00:13Z
    (0.9050, 0.8100, 1.0000),   # settled winner — spread 0.19, NOT fabricated
    (0.0105, 0.0010, 0.0200),   # a real quote
    (0.8800, 0.8500, 0.9100),   # a real quote
    (0.4650, None, 0.9300),     # the Netflix bucket from #1574
    (0.5000, None, None),       # no book at all — must pass through
    (0.7000, 0.0010, 1.0000),   # wide book, but the price is NOT its midpoint
    (0.5000, 0.0000, 1.0000),   # zero bid is a book, not an absent one
    (0.5004, 0.0010, 1.0000),   # inside the tolerance
    (0.5100, 0.0010, 1.0000),   # outside it
]


class TestSqlMirrorsPython:
    """The SQL is EXECUTED, not pattern-matched.

    SQLite is enough: the generated expression uses only COALESCE, ABS, IS NOT
    NULL, arithmetic and comparison, all of which mean the same thing in SQLite
    and Postgres for these inputs. That makes this a semantic agreement test
    rather than a second re-statement of the rule in assertions.
    """

    @pytest.mark.parametrize("prob,bid,ask", _MIDPOINT_CASES)
    def test_agreement(self, prob, bid, ask):
        expr = fabricated_midpoint_sql(":p", ":b", ":a")
        conn = sqlite3.connect(":memory:")
        try:
            row = conn.execute(
                f"SELECT {expr}", {"p": prob, "b": bid, "a": ask}
            ).fetchone()
        finally:
            conn.close()
        assert bool(row[0]) is is_fabricated_midpoint(prob, bid, ask), (
            f"SQL and Python disagree on (p={prob}, bid={bid}, ask={ask})"
        )

    def test_the_both_null_passthrough_is_present_and_load_bearing(self):
        """Without it COALESCE manufactures a 0/1 book for every bookless row.

        Every model price sitting at exactly 0.50 would then be deleted from the
        curve as a fabrication. The clause is not defensive; it is the difference
        between the SQL and the Python.
        """
        expr = fabricated_midpoint_sql(":p", ":b", ":a")
        assert ":b IS NOT NULL OR :a IS NOT NULL" in expr
        conn = sqlite3.connect(":memory:")
        try:
            got = conn.execute(
                f"SELECT {expr}", {"p": 0.5, "b": None, "a": None}
            ).fetchone()[0]
        finally:
            conn.close()
        assert not got


# =========================================================================
# The rule reaches the statements that run
# =========================================================================


class TestTheShippedStatementsCarryTheRule:
    """Bind the guard to the render.

    Everything above tests a Python function. These tests read the SQL strings the
    Celery task hands to ``text()`` and assert the rule is in them, so the pure
    functions above cannot stay green while the statement loses the fix.
    """

    WOULD_CHURN = "\n AND NOT ({value} = nc.opening_probability)\n"
    PART_A_VALUE = "COALESCE(closing.probability, nc.opening_probability)"

    def _statements(self):
        return {
            "part_a": _part_a_calibration_sql(self.WOULD_CHURN, self.PART_A_VALUE),
            "part_c": _part_c_calibration_sql(),
            "repair": _part_a_repair_sql(self.WOULD_CHURN),
        }

    def test_every_statement_clamps_the_boundary(self):
        for name, sql in self._statements().items():
            assert "LEAST(" in sql and "resolution_date" in sql, name
            assert "captured_at < LEAST(" in sql, name

    def test_no_statement_still_reads_the_bare_event_commence(self):
        """The exact line that shipped the defect, asserted absent."""
        for name, sql in self._statements().items():
            assert "captured_at < nc.commence_time" not in sql, name
            assert "captured_at < s.commence_time" not in sql, name

    def test_every_statement_refuses_a_fabricated_midpoint(self):
        fragment = fabricated_midpoint_sql(
            "fos.probability", "fos.yes_bid", "fos.yes_ask"
        )
        for name, sql in self._statements().items():
            assert f"NOT {fragment}" in sql, name

    def test_the_lateral_is_generated_not_restated(self):
        """Byte-for-byte: the statements embed the shared builder's output."""
        for name, sql in self._statements().items():
            boundary_alias = "nc" if name != "part_c" else "s"
            lateral = closing_line_lateral_sql(
                outcome_id=f"{boundary_alias}.outcome_id",
                boundary=closing_line_boundary_sql(
                    f"{boundary_alias}.commence_time",
                    f"{boundary_alias}.resolution_date",
                ),
                extra_and=(
                    "AND (NOT nc.is_threshold OR fos.yes_bid > 0)"
                    if name == "part_a"
                    else ""
                ),
            )
            assert lateral in sql, name

    def test_part_a_keeps_the_kalshi_threshold_guard(self):
        """#167/#941/#1054 must-not-regress control — a different degeneracy.

        A Kalshi ``N+`` prop's settled no-bid quote can land BEFORE commence_time,
        where no boundary clamp can reach it. Q436 must not have eaten that guard
        on its way past.
        """
        sql = _part_a_calibration_sql(self.WOULD_CHURN, self.PART_A_VALUE)
        assert "AND (NOT nc.is_threshold OR fos.yes_bid > 0)" in sql
        assert "fm.source = 'kalshi'" in sql

    def test_the_repair_is_held_to_the_ruled_cell(self):
        """Alex ruled `polymarket/baseball` on 2026-08-28. Not the other 19 cells.

        The same window overrun exists on ~57,000 resolved markets across both
        sources. Repairing them unasked would move a large slice of the published
        curve with nobody having agreed to it — the population change ruling 103
        exists to put in front of Alex first.
        """
        sql = _part_a_repair_sql(self.WOULD_CHURN)
        assert "fm.source = 'polymarket'" in sql
        assert "fm.llm_sport_category = 'baseball'" in sql

    def test_the_repair_cannot_repair_the_same_row_twice(self):
        """Monotonic, so the phase drains instead of churning (Queue 300's lesson)."""
        sql = _part_a_repair_sql(self.WOULD_CHURN)
        assert "IS DISTINCT FROM nc.current_cal" in sql

    def test_the_repair_never_writes_a_null_over_a_price(self):
        sql = _part_a_repair_sql(self.WOULD_CHURN)
        assert "IS NOT NULL" in sql
        assert "SET calibration_probability = NULL" not in sql

    def test_the_repair_is_cursored_and_batched(self):
        sql = _part_a_repair_sql(self.WOULD_CHURN)
        assert "fo.id > :cursor" in sql
        assert "LIMIT :batch" in sql
        assert "ORDER BY fo.id" in sql
