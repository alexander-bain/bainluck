"""CAL-P1215 (#1544, #997) — guards for the paired early/late pre-start cohort.

The module under test decides which outcomes may be used to answer "do forecasts
improve before an event?". Every guard here exists because the corresponding
mistake would publish a number that looks like an answer and is not:

* an asymmetric eligibility filter manufactures improvement out of the filter;
* a degenerate pair (one snapshot read twice) reads as "no improvement";
* a NULL boundary silently admits post-settlement prices;
* an unpaired standard error reports "no detectable change" on a real one;
* an empty cohort returning ``0.0`` publishes a perfect score for no data.
"""

import math
from datetime import datetime, timedelta, timezone

import pytest

from app.utils.calibration_closing_line import (
    closing_line_boundary_sql,
    closing_line_lateral_sql,
)
from app.utils.calibration_paired_prestart import (
    DEFAULT_MIN_SEPARATION_SECONDS,
    PAIR_NO_LEG,
    PAIR_PAIRED,
    PAIR_SINGLE_LEG,
    PAIR_CLASSES,
    PAIR_TOO_CLOSE,
    PAIR_UNANCHORED_BOUNDARY,
    boundary_is_anchored,
    brier,
    classify_pair,
    leg_calibration,
    log_loss,
    paired_feasibility_sql,
    paired_improvement,
    paired_legs_sql,
    select_paired_legs,
)

T0 = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
COMMENCE = T0 + timedelta(days=2)


def snap(hours, probability, yes_bid=None, yes_ask=None):
    """One ``futures_odds_snapshots`` row in the shape the selector consumes."""
    return (T0 + timedelta(hours=hours), probability, yes_bid, yes_ask)


# ---------------------------------------------------------------------------
# The shared eligibility rule must stay shared
# ---------------------------------------------------------------------------


def test_default_lateral_emission_is_byte_identical_after_the_order_param():
    """Adding ``order``/``columns`` must not move the SQL Part A already runs.

    ``backfill_winners`` embeds this string and a Q436 guard asserts it appears
    verbatim in the shipped statement. If a default changed, that guard would be
    asserting against a statement the task no longer runs.
    """
    emitted = closing_line_lateral_sql(outcome_id="s.outcome_id", boundary="s.bound")
    assert "ORDER BY fos.captured_at DESC" in emitted
    # The default select list is the single column every existing caller reads.
    assert "SELECT fos.probability\n" in emitted
    assert "fos.captured_at," not in emitted


def test_both_legs_carry_the_identical_eligibility_clause():
    """The early leg may not be selected under a laxer filter than the late leg.

    This is the guard that makes the comparison honest: if the two legs could
    admit different snapshots, any measured "improvement" would partly be the
    filter changing, not the forecast changing. The two laterals must therefore
    differ in their sort direction and in NOTHING else.
    """
    kwargs = dict(
        outcome_id="fo.id",
        boundary="BOUND",
        columns="fos.probability, fos.captured_at",
    )
    early = closing_line_lateral_sql(order="ASC", **kwargs)
    late = closing_line_lateral_sql(order="DESC", **kwargs)

    assert early != late
    assert early.replace("captured_at ASC", "captured_at DESC") == late

    # ...and both of those are what the paired statement actually embeds.
    sql = paired_legs_sql()
    boundary = "LEAST(e.commence_time, COALESCE(fm.resolution_date, e.commence_time))"
    for leg in (early, late):
        assert leg.replace("BOUND", boundary) in sql


def test_order_is_validated_because_it_is_interpolated_into_sql():
    with pytest.raises(ValueError, match="order must be ASC or DESC"):
        closing_line_lateral_sql(outcome_id="fo.id", boundary="b", order="DESC; DROP")


def test_population_uses_resolution_source_not_market_source():
    """Truth-eligibility is keyed on HOW the row was graded, not on who quoted it.

    The allowlist holds ``resolution_source`` values (``box_score``,
    ``clob_authoritative``, ...). Reading it as a market-source list would select
    an empty population while looking entirely plausible.
    """
    sql = paired_legs_sql()
    assert "fo.resolution_source IN (" in sql
    assert "fm.source IN (" not in sql
    assert "'box_score'" in sql


def test_both_legs_share_one_boundary_expression():
    """Two boundaries would let the late leg run past the early leg's start."""
    sql = paired_legs_sql()
    boundary = "LEAST(e.commence_time, COALESCE(fm.resolution_date, e.commence_time))"
    assert sql.count(f"fos.captured_at < {boundary}") == 2


def test_task_statement_binds_while_the_bus_statement_uses_literals():
    """The db-query rail does not bind; a task caller must not interpolate ids."""
    assert "fo.id > :cursor" in paired_legs_sql()
    assert "LIMIT :scan" in paired_legs_sql()

    bus = paired_feasibility_sql(cursor=4321, scan=1000)
    assert "fo.id > 4321" in bus
    assert "LIMIT 1000" in bus
    assert ":cursor" not in bus and ":scan" not in bus


def test_feasibility_literals_are_type_checked():
    """They are interpolated, not bound, so a string is refused rather than run."""
    with pytest.raises(TypeError, match="pass ints"):
        paired_feasibility_sql(cursor="0; DROP TABLE futures_outcomes")


def test_feasibility_carries_the_cursor_forward_for_the_next_window():
    """A row-bounded walk needs its own bookmark, or it rescans the first window."""
    assert "MAX(outcome_id) AS max_outcome_id" in paired_feasibility_sql()


def test_feasibility_reports_the_failure_classes_separately():
    """"We never looked twice" and "the market is illiquid" are different findings.

    Iterates :data:`PAIR_CLASSES` rather than a hand-written tuple: a class added
    to the module and not to the statement is exactly the drift this catches, and
    a literal list here would have to be remembered instead.
    """
    sql = paired_feasibility_sql()
    assert "GROUP BY source, pair_class" in sql
    for klass in PAIR_CLASSES:
        assert f"'{klass}'" in sql, f"{klass} is unreachable in the walk's own SQL"


def test_least_ignores_a_null_commence_so_the_boundary_becomes_the_settlement_date():
    """The witness that ``unanchored_boundary`` closes a LIVE hole, not a theoretical one.

    ``closing_line_boundary_sql`` emits
    ``LEAST(e.commence_time, COALESCE(fm.resolution_date, e.commence_time))``, and
    its own docstring records that **Postgres LEAST ignores NULL arguments** — the
    COALESCE is for the reader. So with no linked event the boundary does NOT go
    NULL and drop the row: it quietly becomes ``resolution_date``, a settlement
    stamp, and the outcome scored as though that were its kick-off.

    Asserted from the shipped emission rather than from memory, because the whole
    finding rests on this one operator's NULL semantics. If that expression is
    ever changed to null out instead, this test should fail and the class can be
    revisited.
    """
    boundary = closing_line_boundary_sql("e.commence_time", "fm.resolution_date")
    assert boundary == "LEAST(e.commence_time, COALESCE(fm.resolution_date, e.commence_time))"
    assert "COALESCE(fm.resolution_date, e.commence_time)" in boundary


def test_the_unanchored_branch_is_first_in_the_sql_case():
    """Order is the guarantee: it must win over every leg-shaped reason.

    A row with no event start can also have no snapshots. If the branches were
    the other way round it would be reported as ``no_eligible_leg`` and the
    provenance requirement would look free — the feasibility walk would
    under-count what it costs, which is the number the decision rests on.
    """
    sql = paired_legs_sql()
    case = sql[sql.index("CASE") : sql.index("END AS pair_class")]
    assert case.index(f"'{PAIR_UNANCHORED_BOUNDARY}'") < case.index(f"'{PAIR_NO_LEG}'")
    assert "WHEN e.commence_time IS NULL" in case


def test_boundary_is_anchored_is_the_single_provenance_question():
    """One function, so the SQL branch, the mirror and the callers cannot diverge."""
    assert boundary_is_anchored(COMMENCE) is True
    assert boundary_is_anchored(None) is False


# ---------------------------------------------------------------------------
# The Python selector must mirror the SQL branch for branch
# ---------------------------------------------------------------------------


def test_picks_first_and_last_eligible_snapshot():
    klass, early, late = select_paired_legs(
        [snap(30, 0.55), snap(1, 0.40), snap(12, 0.48)],
        event_commence=COMMENCE,
    )
    assert (klass, early, late) == (PAIR_PAIRED, 0.40, 0.55)


def test_unsorted_input_is_sorted_not_trusted():
    """The SQL sorts; a caller handing rows in arrival order must get the same pair."""
    rows = [snap(30, 0.55), snap(1, 0.40), snap(12, 0.48)]
    assert select_paired_legs(rows, event_commence=COMMENCE) == select_paired_legs(
        list(reversed(rows)), event_commence=COMMENCE
    )


def test_single_snapshot_is_not_a_pair():
    """One reading is not an early AND a late forecast, and must not score as one."""
    klass, early, late = select_paired_legs([snap(1, 0.40)], event_commence=COMMENCE)
    assert klass == PAIR_SINGLE_LEG
    assert early is None and late is None


def test_legs_closer_than_the_separation_floor_are_refused():
    klass, early, late = select_paired_legs(
        [snap(1, 0.40), snap(2, 0.44)], event_commence=COMMENCE
    )
    assert klass == PAIR_TOO_CLOSE
    assert early is None and late is None


def test_a_refused_pair_never_returns_probabilities_to_score():
    """A caller must not be able to score a pair the selector rejected."""
    for rows in ([], [snap(1, 0.4)], [snap(1, 0.4), snap(2, 0.5)]):
        klass, early, late = select_paired_legs(rows, event_commence=COMMENCE)
        assert klass != PAIR_PAIRED
        assert early is None and late is None


def test_post_boundary_snapshots_are_excluded():
    """A quote at or after the start is not a pre-start forecast."""
    klass, _, _ = select_paired_legs(
        [snap(1, 0.40), snap(48, 0.90), snap(60, 0.99)],
        event_commence=COMMENCE,
    )
    assert klass == PAIR_SINGLE_LEG, "only the pre-start quote should survive"


def test_boundary_clamps_to_the_earlier_of_commence_and_resolution():
    """Q436: a mis-linked market's boundary must not sit past its own settlement."""
    resolution = T0 + timedelta(hours=10)
    klass, _, _ = select_paired_legs(
        [snap(1, 0.40), snap(20, 0.95)],
        event_commence=COMMENCE,
        resolution_date=resolution,
    )
    assert klass == PAIR_SINGLE_LEG, "the 20h quote is post-settlement"


def test_null_boundary_admits_nothing():
    """`captured_at < NULL` is NULL in SQL — the Python half must not be laxer.

    CAL-P1216b refines the CLASS without weakening the guarantee: a missing event
    start is now reported as ``unanchored_boundary`` rather than folded into
    ``no_eligible_leg``, because "nobody told us when this started" and "nobody
    quoted it twice" are different findings. What must never change is the part
    this test was written for — no probabilities come back.
    """
    klass, early, late = select_paired_legs(
        [snap(1, 0.40), snap(30, 0.55)], event_commence=None, resolution_date=None
    )
    assert klass == PAIR_UNANCHORED_BOUNDARY
    assert early is None and late is None


def test_a_settlement_date_alone_never_anchors_a_pre_event_leg():
    """codex 17:11Z: *LEAST of two timestamps alone does not prove real event start.*

    The dangerous shape, and the reason the class exists: there IS a boundary
    here — a resolution date 30 hours out — and two well-separated, perfectly
    eligible quotes sit before it. Under the old rule that is a clean ``paired``
    row. But ``resolution_date`` is a SETTLEMENT stamp, at or after the end of
    the thing, so the "final pre-event forecast" could have been taken while the
    event was being decided. A pair like that makes late forecasts look brilliant
    precisely because they were no longer forecasts.

    Refused, and refused with its own name so the feasibility walk can report
    what the requirement costs instead of burying it in ``no_eligible_leg``.
    """
    klass, early, late = select_paired_legs(
        [snap(1, 0.40), snap(25, 0.93)],
        event_commence=None,
        resolution_date=T0 + timedelta(hours=30),
    )
    assert klass == PAIR_UNANCHORED_BOUNDARY
    assert early is None and late is None, "an unvouched boundary must score nothing"

    # ...and the SAME two snapshots ARE a pair once a real start anchors them.
    anchored, early_p, late_p = select_paired_legs(
        [snap(1, 0.40), snap(25, 0.93)],
        event_commence=T0 + timedelta(hours=30),
        resolution_date=T0 + timedelta(hours=30),
    )
    assert anchored == PAIR_PAIRED
    assert (early_p, late_p) == (0.40, 0.93)


def test_fabricated_midpoint_legs_are_rejected():
    """bid 0.001 / ask 1.000 midpoint 0.5005 is the #1574 phantom, not a price."""
    klass, early, late = select_paired_legs(
        [snap(1, 0.5005, 0.001, 1.000), snap(30, 0.5005, 0.001, 1.000)],
        event_commence=COMMENCE,
    )
    assert klass == PAIR_NO_LEG


def test_classify_pair_matches_the_sql_case_order():
    # The FIRST branch, and it wins over every other reason — an outcome with no
    # provable start is not a thin pair, it is not a pair at all. Asserted with
    # timestamps that would otherwise classify `paired`, so this cannot pass by
    # landing on some other branch.
    assert (
        classify_pair(
            T0,
            T0 + timedelta(seconds=DEFAULT_MIN_SEPARATION_SECONDS),
            boundary_anchored=False,
        )
        == PAIR_UNANCHORED_BOUNDARY
    )
    # Unstated provenance is REFUSED, not assumed: the fail-closed default is the
    # whole protection, since a caller that forgets to say is exactly the caller
    # that has not checked.
    assert classify_pair(T0, T0 + timedelta(hours=9)) == PAIR_UNANCHORED_BOUNDARY
    # `event_commence` derives it, so a caller holding the timestamp need not
    # also hold the boolean.
    assert (
        classify_pair(T0, T0 + timedelta(hours=9), event_commence=COMMENCE) == PAIR_PAIRED
    )

    assert classify_pair(None, None, boundary_anchored=True) == PAIR_NO_LEG
    assert classify_pair(T0, T0, boundary_anchored=True) == PAIR_SINGLE_LEG
    assert classify_pair(T0, T0 - timedelta(hours=1), boundary_anchored=True) == PAIR_SINGLE_LEG
    assert classify_pair(T0, T0 + timedelta(seconds=DEFAULT_MIN_SEPARATION_SECONDS - 1), boundary_anchored=True) == PAIR_TOO_CLOSE
    assert classify_pair(T0, T0 + timedelta(seconds=DEFAULT_MIN_SEPARATION_SECONDS), boundary_anchored=True) == PAIR_PAIRED


# ---------------------------------------------------------------------------
# Proper scores
# ---------------------------------------------------------------------------


def test_brier_is_squared_error_against_the_realised_outcome():
    assert brier(1.0, True) == 0.0
    assert brier(0.0, True) == 1.0
    assert brier(0.5, True) == pytest.approx(0.25)
    assert brier(0.25, False) == pytest.approx(0.0625)


def test_log_loss_is_finite_at_the_extremes():
    """Eligibility rejects p in {0,1}; an unfiltered caller must still not get inf."""
    assert log_loss(0.0, True) > 0 and log_loss(0.0, True) != float("inf")
    assert log_loss(1.0, False) > 0 and log_loss(1.0, False) != float("inf")
    assert log_loss(0.5, True) == pytest.approx(log_loss(0.5, False))


def test_positive_mean_delta_means_the_final_forecast_was_better():
    """The sign convention IS the reader's sentence — backwards inverts the claim."""
    # Early 0.5, late 0.9, outcome happened: the late forecast is much better.
    out = paired_improvement([(0.5, 0.9, True)] * 8)
    assert out is not None
    assert out["mean_delta"] > 0
    assert out["late_mean"] < out["early_mean"]


def test_negative_mean_delta_is_reported_not_suppressed():
    """If the data contradicts the expectation, the module must say so (Alex)."""
    out = paired_improvement([(0.9, 0.5, True)] * 8)
    assert out is not None
    assert out["mean_delta"] < 0


def test_empty_and_single_pair_cohorts_return_none_not_zero():
    """gotcha #53: a perfect-looking score standing in for no data."""
    assert paired_improvement([]) is None
    assert paired_improvement([(0.4, 0.6, True)]) is None


def test_standard_error_is_paired_not_marginal():
    """Correlated legs: the paired SE sees a consistent shift a marginal one hides.

    These three outcomes sit at very different prices, so each leg's own Brier
    scores are widely spread — but every pair moves the same direction by a
    similar amount. The paired error bar makes the improvement detectable; an
    error bar built from the two marginal variances calls it noise.
    """
    pairs = [(0.20, 0.30, True), (0.50, 0.60, True), (0.80, 0.90, True)]
    out = paired_improvement(pairs)
    assert out is not None
    assert out["mean_delta"] > 0

    n = len(pairs)
    early = [brier(e, y) for e, _, y in pairs]
    late = [brier(lt, y) for _, lt, y in pairs]

    def variance(xs):
        m = sum(xs) / len(xs)
        return sum((x - m) ** 2 for x in xs) / (len(xs) - 1)

    unpaired_se = math.sqrt(variance(early) / n + variance(late) / n)

    assert out["se"] < unpaired_se / 5
    # The whole point: paired resolves the shift, unpaired does not.
    assert out["mean_delta"] > 2 * out["se"]
    assert out["mean_delta"] < 2 * unpaired_se


def test_n_counts_outcomes_not_legs():
    out = paired_improvement([(0.4, 0.6, True), (0.3, 0.2, False)])
    assert out is not None and out["n"] == 2


def test_unknown_score_raises_before_it_is_used():
    with pytest.raises(ValueError, match="unknown score"):
        paired_improvement([(0.4, 0.6, True), (0.3, 0.2, False)], score="accuracy")


def test_log_loss_and_brier_can_be_selected_independently():
    pairs = [(0.4, 0.6, True)] * 5
    assert paired_improvement(pairs, score="brier")["mean_delta"] == pytest.approx(
        brier(0.4, True) - brier(0.6, True)
    )
    assert paired_improvement(pairs, score="log_loss")["mean_delta"] == pytest.approx(
        log_loss(0.4, True) - log_loss(0.6, True)
    )


# ---------------------------------------------------------------------------
# Calibration is reported SEPARATELY from the proper score (Alex)
# ---------------------------------------------------------------------------


def test_calibration_is_computed_on_both_legs_of_the_same_population():
    out = leg_calibration([(0.4, 0.6, True), (0.4, 0.6, False)])
    assert set(out) == {"early_ece_pp", "late_ece_pp"}
    assert out["early_ece_pp"] is not None and out["late_ece_pp"] is not None


def test_a_forecast_can_sharpen_while_calibration_worsens():
    """Why the two numbers are reported apart rather than summarised into one.

    Base rate 0.8. The early leg quotes 0.8 on everything: perfectly calibrated,
    and uninformative. The late leg separates the winners (0.9) from the losers
    (0.6) but overshoots on both: a much better Brier score, and a worse ECE.
    A single "did it improve?" number would have to pick one of those and hide
    the other.
    """
    pairs = [(0.8, 0.9, True)] * 8 + [(0.8, 0.6, False)] * 2
    score = paired_improvement(pairs)
    cal = leg_calibration(pairs)
    assert score is not None and score["mean_delta"] > 0, "sharper by Brier"
    assert cal["early_ece_pp"] == pytest.approx(0.0), "early leg is on the diagonal"
    assert cal["late_ece_pp"] > cal["early_ece_pp"], "but further off the diagonal"


def test_empty_calibration_is_absent_not_zero():
    out = leg_calibration([])
    assert out == {"early_ece_pp": None, "late_ece_pp": None}
