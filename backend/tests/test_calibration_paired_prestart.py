"""The paired early/final pre-start cohort — CAL-P1215 and CAL-P1330 (#6176, #1544, #997).

Two halves, and both are load-bearing:

* the SQL guards assert the STATEMENT says what the module's prose says, because
  nothing in CI executes it against a database and a rule that exists only in a
  docstring is not a rule;
* the Python guards are the control set from
  ``artifacts/other-model-paired-accuracy/paired_accuracy_example.py``, ported
  one-to-one to the classes this module emits, plus the four classes that
  example predates.

``backend/scripts/probe_paired_prestart_sql.py`` closes the gap between them: it
runs the real statement against a throwaway local Postgres over the same
synthetic fixture and asserts the SQL and the Python agree row for row. It needs
a database, so it is a developer gate rather than a CI one — the SQL-text guards
below are what CI can hold.

EVERY NUMBER IN THIS FILE IS SYNTHETIC.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.calibration_closing_line import closing_line_lateral_sql
from app.utils.event_completion import DERIVED_COMMENCE_SOURCES
from app.utils.event_rails import (
    POLL_CLOCK_STAMP_TOLERANCE,
    _POLL_CLOCK_FALLBACK_SOURCES,
)
from app.utils.resolution_authority import CALIBRATION_TRUTH_ELIGIBLE_SOURCES
from app.utils import calibration_paired_prestart as mod
from app.utils.calibration_paired_prestart import (
    DEFAULT_EARLY_MAX_STALE_SECONDS,
    DEFAULT_FINAL_MAX_STALE_SECONDS,
    DEFAULT_LEAD_SECONDS,
    MIN_CLUSTERS_FOR_MARGIN,
    MODEL_FORECAST_SOURCES,
    PAIR_CLASSES,
    PAIRED_CLASSES,
    as_of_sql,
    boundary_is_anchored,
    brier,
    classify_pair,
    forecast_kind,
    leg_calibration,
    log_loss,
    paired_feasibility_sql,
    paired_improvement,
    paired_legs_sql,
    result_is_independent,
    start_is_contradicted_sql,
    start_is_reported_sql,
    start_refusal,
)

H = timedelta(hours=1)
D = timedelta(days=1)
T0 = datetime(2026, 1, 10, 20, 0, tzinfo=timezone.utc)


class Ev:
    """A duck-typed event row. The rule reads four columns and nothing else."""

    def __init__(self, commence=T0, source="espn", created=None, completed=None):
        self.commence_time = commence
        self.commence_time_source = source
        # `Event.created_at` is a bare DateTime on the model (naive UTC), so the
        # fixture is naive here too — a fixture that hands the rule an aware
        # datetime would never exercise the normalisation the real row needs.
        self.created_at = (
            created if created is not None else (T0 - 30 * D).replace(tzinfo=None)
        )
        self.completed_at = completed if completed is not None else T0 + 3 * H


def snap(at, p, *, book="kalshi", valid_until=None, yes_bid=None, yes_ask=None):
    """One ``futures_odds_snapshots`` row in the shape the rule consumes."""
    return (at, p, yes_bid, yes_ask, book, valid_until)


def standard(early, final, *, book="kalshi"):
    """One look 26h out (re-confirmed at 25h) and one an hour before the start."""
    return [
        snap(T0 - 26 * H, early, book=book, valid_until=T0 - 25 * H),
        snap(T0 - 1 * H, final, book=book, yes_bid=final - 0.01, yes_ask=final + 0.01),
    ]


def classify(snapshots, **kw):
    kw.setdefault("event", Ev())
    kw.setdefault("market_source", "kalshi")
    kw.setdefault("resolution_date", T0 + 3 * H)
    return classify_pair(snapshots, **kw)


# ---------------------------------------------------------------------------
# The SQL half
# ---------------------------------------------------------------------------


def test_the_shipped_closing_line_lateral_is_untouched_by_this_work():
    """CAL-P1330 added no argument to the module ``backfill_winners`` embeds.

    Everything the paired rule needs — the bookmaker predicate, the extra
    columns, the earlier boundary — was already expressible through
    ``extra_and``/``columns``/``boundary``. Stating that here means a future
    change to the shipped emitter has to break this test on purpose.
    """
    default = closing_line_lateral_sql(outcome_id="fo.id", boundary="B")
    assert "AND fos.bookmaker" not in default
    assert "valid_until" not in default
    assert default.count("SELECT fos.probability") == 1


def test_no_leg_is_selected_first_ever_captured():
    """The early leg is a closing line against an EARLIER boundary, not the
    first snapshot we happened to take. An ``ASC`` lateral is the defect."""
    sql = paired_legs_sql()
    assert "ORDER BY fos.captured_at ASC" not in sql
    # Four leg laterals: the two book-blind ones that name the failure, and the
    # chooser's two. Every one of them is a "last price before X" selection.
    assert sql.count("ORDER BY fos.captured_at DESC") == 4


def test_the_early_leg_is_the_shared_boundary_minus_one_lead():
    sql = paired_legs_sql(lead_seconds=DEFAULT_LEAD_SECONDS)
    boundary = "LEAST(e.commence_time, COALESCE(fm.resolution_date, e.commence_time))"
    assert f"({boundary} - INTERVAL '{DEFAULT_LEAD_SECONDS} seconds')" in sql
    # and the final leg is that same boundary with no interval applied
    assert f"AND fos.captured_at < {boundary}\n" in sql


def test_lead_is_a_parameter_so_a_second_rung_is_a_call_not_a_rewrite():
    seven_days = 7 * 24 * 3600
    sql = paired_legs_sql(lead_seconds=seven_days)
    assert f"INTERVAL '{seven_days} seconds'" in sql
    assert f"INTERVAL '{DEFAULT_LEAD_SECONDS} seconds'" not in sql


@pytest.mark.parametrize("bad", [0, -1, 24.5, "86400"])
def test_a_lead_that_is_not_a_positive_int_is_refused_before_it_reaches_sql(bad):
    with pytest.raises(ValueError):
        as_of_sql("B", bad)


def test_freshness_reads_the_last_confirmation_not_the_first_sighting():
    """``captured_at`` is when a VALUE was first seen; retention moves the last
    look into ``valid_until``. Reading the wrong one lets a stale price pose as
    the final one."""
    sql = paired_legs_sql()
    assert "COALESCE(fos.valid_until, fos.captured_at) AS last_seen_at" in sql
    assert sql.count("last_seen_at") >= 8  # 4 emissions + the freshness tests


def test_freshness_falls_back_to_the_capture_when_the_run_crosses_the_instant():
    """CAL-P1331. The clamp this replaces was ``LEAST(last_seen_at, instant)``,
    and it did the OPPOSITE of what it claimed: a run confirmed after the
    instant clamped TO the instant and scored staleness zero — the freshest
    possible reading, awarded for a look taken after the event began. The last
    look we can prove fell before the instant is ``captured_at``."""
    sql = paired_legs_sql()
    assert "LEAST(early.last_seen_at," not in sql
    assert "LEAST(final.last_seen_at," not in sql
    for leg in ("early", "final", "ef", "ff"):
        assert f"THEN {leg}.last_seen_at ELSE {leg}.captured_at END" in sql


def test_a_run_crossing_the_instant_is_its_own_refusal_not_a_polling_gap():
    """``*_stale`` means we stopped watching; this population we were still
    watching. Two findings, two fixes, so the walk counts them apart."""
    sql = paired_legs_sql()
    assert "no_final_unconfirmed_span" in sql
    assert "no_early_unconfirmed_span" in sql
    # The span branch must be decided BEFORE the plain stale branch, or every
    # one of these rows reports as a polling gap and the class is unreachable.
    assert sql.index("no_final_unconfirmed_span") < sql.index("'no_final_stale'")
    assert sql.index("no_early_unconfirmed_span") < sql.index("'no_early_stale'")


def test_each_leg_carries_its_own_staleness_bound():
    sql = paired_legs_sql(early_max_stale_seconds=111, final_max_stale_seconds=222)
    assert "<= 111" in sql and "<= 222" in sql


def test_both_per_book_legs_are_held_to_one_bookmaker():
    sql = paired_legs_sql()
    # once for each of the chooser's two legs, and never on the union legs
    assert sql.count("AND fos.bookmaker = b.bookmaker") == 2


def test_the_book_is_chosen_before_the_legs_are_scored():
    """Native book first, then alphabetically. Shopping across books for
    whichever pair looks best is a selection effect, not a measurement."""
    sql = paired_legs_sql()
    assert "ORDER BY (b.bookmaker <> fm.source), b.bookmaker" in sql
    assert "LIMIT 1\n) pair_book ON true" in sql


def test_both_legs_carry_the_identical_eligibility_clause():
    """An early leg selected under a laxer filter manufactures improvement."""
    sql = paired_legs_sql()
    eligibility = "AND fos.probability > 0 AND fos.probability < 1"
    assert sql.count(eligibility) == 4  # one per leg lateral
    assert sql.count("NOT (") >= 4  # the fabricated-midpoint guard on every leg


def test_start_provenance_sql_is_derived_from_the_house_sets_both_directions():
    """Not a third list. A source added to either set must reach this predicate
    without anybody remembering this line."""
    rendered = start_is_reported_sql()
    for source in DERIVED_COMMENCE_SOURCES:
        assert f"'{source}'" in rendered
    for source in _POLL_CLOCK_FALLBACK_SOURCES:
        assert f"'{source}'" in rendered
    quoted = {
        token.strip().strip("'")
        for chunk in rendered.split("IN (")[1:]
        for token in chunk.split(")")[0].split(",")
    }
    assert quoted == set(DERIVED_COMMENCE_SOURCES) | set(_POLL_CLOCK_FALLBACK_SOURCES)
    assert str(int(POLL_CLOCK_STAMP_TOLERANCE.total_seconds())) in rendered


def test_the_poll_clock_arm_needs_all_three_conditions():
    """Each arm alone is far too broad — ``commence_time_source = 'kalshi'``
    covers 610 real rail rows. The conjunction is the test."""
    rendered = start_is_reported_sql()
    assert "EXTRACT(SECOND FROM e.commence_time) <> 0" in rendered
    assert "AT TIME ZONE 'UTC'" in rendered  # naive created_at, aware commence_time
    assert rendered.count(" AND ") >= 3


def test_start_contradiction_covers_both_of_our_own_columns():
    rendered = start_is_contradicted_sql()
    assert "e.completed_at <= e.commence_time" in rendered  # gotcha #46
    assert f"INTERVAL '{mod.START_CONTRADICTION_TOLERANCE_SECONDS} seconds'" in rendered


def test_provenance_is_decided_before_any_snapshot_is_read():
    """The CASE order is the rule's order: a leg drawn before a stand-in is not
    a pre-event forecast, however good the snapshots are."""
    sql = paired_legs_sql()
    order = [
        sql.index(f"'{klass}'")
        for klass in (
            mod.PAIR_UNANCHORED_BOUNDARY,
            mod.PAIR_START_PROVENANCE_UNKNOWN,
            mod.PAIR_START_NOT_REPORTED,
            mod.PAIR_START_CONTRADICTED,
            mod.PAIR_SETTLEMENT_PRECEDES_START,
            mod.PAIR_PAIRED_UNCHANGED,
        )
    ]
    assert order == sorted(order)


def test_population_uses_resolution_source_not_market_source():
    """The allowlist is HOW the outcome was graded, never WHICH venue quoted it."""
    sql = paired_legs_sql()
    assert "fo.resolution_source" in sql
    assert "fm.source IN ('api_settlement'" not in sql
    assert "fo.is_winner IS NOT NULL" in sql


def test_result_not_independent_is_python_only_and_that_is_deliberate():
    """The SQL holds the rule in its WHERE, so the feasibility denominator stays
    the graded population every other calibration reader uses. The class exists
    for row-level Python callers, and the asymmetry is asserted rather than
    discovered."""
    sql = paired_legs_sql()
    assert f"'{mod.PAIR_RESULT_NOT_INDEPENDENT}'" not in sql
    assert mod.PAIR_RESULT_NOT_INDEPENDENT in PAIR_CLASSES


def test_forecast_kind_rides_on_every_row_and_is_derived_from_the_constant():
    sql = paired_legs_sql()
    for source in MODEL_FORECAST_SOURCES:
        assert f"'{source}'" in sql
    assert "THEN 'model' ELSE 'market' END AS forecast_kind" in sql


def test_cluster_id_rides_on_every_row():
    """Both sides of a game are ONE piece of evidence; the reader of this
    statement cannot cluster without the column."""
    assert "fm.event_id AS cluster_id" in paired_legs_sql()


def test_feasibility_reports_classes_per_source_and_counts_events():
    sql = paired_feasibility_sql()
    assert "GROUP BY source, forecast_kind, pair_class" in sql
    assert "COUNT(DISTINCT cluster_id) AS n_events" in sql


def test_feasibility_literals_are_type_checked():
    with pytest.raises(TypeError):
        paired_feasibility_sql(cursor="0")


def test_feasibility_carries_the_cursor_forward_for_the_next_window():
    assert "MAX(outcome_id) AS max_outcome_id" in paired_feasibility_sql()


def test_task_statement_binds_while_the_bus_statement_uses_literals():
    assert "fo.id > :cursor" in paired_legs_sql()
    assert "fo.id > 4200" in paired_feasibility_sql(cursor=4200)


# ---------------------------------------------------------------------------
# The Python rule — the control set, one test per named refusal
# ---------------------------------------------------------------------------


def test_an_ordinary_two_look_outcome_pairs():
    assert classify(standard(0.55, 0.70)) == ("paired", 0.55, 0.70)


def test_a_refused_pair_never_returns_probabilities_to_score():
    for klass, early, final in (
        classify(standard(0.55, 0.70), event=Ev(source="kalshi_ticker")),
        classify(standard(0.55, 0.70), event=None),
        classify([snap(T0 - 7 * D, 0.03, valid_until=T0 - 6 * D)]),
    ):
        assert klass not in PAIRED_CLASSES
        assert early is None and final is None


def test_unequal_lead_the_first_ever_snapshot_is_not_the_early_leg():
    """THE defect CAL-P1330 removes: a 30-days-out look and a 26-hours-out look
    are not the same forecast, and picking the older one measures when our
    poller started."""
    rows = standard(0.55, 0.70) + [snap(T0 - 30 * D, 0.40, valid_until=T0 - 29 * D)]
    assert classify(rows) == ("paired", 0.55, 0.70)


def test_a_reconfirmed_flat_price_supplies_both_legs_and_is_counted_apart():
    """We looked repeatedly and it did not move. Dropping it would bias the
    cohort toward markets that moved.

    🔴 CAL-P1331 MOVED THIS FIXTURE, and the move is the point. It used to be
    captured 3 days out with ``valid_until`` an hour before the start, and it
    passed only because the old clamp scored the EARLY leg's staleness as zero
    against a confirmation taken 23 hours after the early instant. Rule 8 is
    intact — a flat run still supplies both legs — but it has to be a run whose
    proven looks actually cover both instants, so the capture moves inside the
    early leg's own staleness bound. The old fixture is not deleted; it is the
    second assertion, where it now names its refusal.
    """
    covered = [snap(T0 - 30 * H, 0.70, valid_until=T0 - 1 * H)]
    assert classify(covered) == ("paired_unchanged", 0.70, 0.70)

    # Same flat price, but the only proof before the early instant is 3 days
    # old: we cannot say what the market showed a day out, only that the value
    # was the same at both ends of a span that swallows the question.
    spans = [snap(T0 - 3 * D, 0.70, valid_until=T0 - 1 * H)]
    assert classify(spans)[0] == "no_early_unconfirmed_span"


def test_a_repeated_value_with_no_reconfirmation_is_refused():
    """The converse of the test above, and the reason it is safe: without a
    ``valid_until`` reaching the final window, the same row is a week-old price
    posing as the last one."""
    rows = [snap(T0 - 3 * D, 0.70)]
    assert classify(rows)[0] == "no_final_stale"


def test_missing_close_the_opening_fallback_is_never_consulted():
    """C1. ``backfill_winners`` stores the opening under the closing line's name
    on this population; this rule reads snapshots and nothing else."""
    rows = [snap(T0 - 26 * H, 0.35, valid_until=T0 - 25 * H)]
    assert classify(rows)[0] == "no_final_stale"


def test_an_after_start_price_is_never_a_candidate():
    """C2. The in-game 0.97 would score a Brier of 0.0009 — brilliant, and not a
    forecast."""
    rows = [
        snap(T0 - 26 * H, 0.55, valid_until=T0 - 25 * H),
        snap(T0 + timedelta(minutes=20), 0.97),
    ]
    assert classify(rows)[0] == "no_final_stale"
    assert brier(0.97, True) < 0.001  # what admitting it would have bought


def test_a_price_derived_winner_cannot_grade_the_price():
    """C3. ``settlement_sync`` crowned the outcome FROM the close."""
    assert (
        classify(
            standard(0.55, 0.90),
            is_winner=True,
            resolution_source="settlement_sync",
            eligible_sources=CALIBRATION_TRUTH_ELIGIBLE_SOURCES,
        )[0]
        == "result_not_independent"
    )


def test_ungraded_truth_is_not_a_loss():
    assert (
        classify(
            standard(0.55, 0.90),
            is_winner=None,
            resolution_source="api_settlement",
            eligible_sources=CALIBRATION_TRUTH_ELIGIBLE_SOURCES,
        )[0]
        == "result_not_independent"
    )


def test_the_result_gate_is_skipped_only_when_the_caller_says_so():
    """Passing no allowlist means "the statement's WHERE already applied it",
    and it is the only way to skip the gate — there is no silent default."""
    assert classify(standard(0.55, 0.70), is_winner=None)[0] == "paired"
    assert result_is_independent(
        True, "api_settlement", eligible_sources=["api_settlement"]
    )
    assert not result_is_independent(
        None, "api_settlement", eligible_sources=["api_settlement"]
    )


def test_a_ticker_date_stand_in_start_is_refused():
    """C4. Midnight UTC of a ticker date, for a match played that afternoon."""
    ev = Ev(commence=T0.replace(hour=0), source="kalshi_ticker")
    assert classify(standard(0.55, 0.70), event=ev)[0] == "start_not_reported"


def test_a_poll_clock_stamp_is_refused_and_a_real_fixture_beside_it_is_not():
    """The positive control matters as much as the specimen: each arm of
    ``commence_time_was_never_a_kickoff`` alone would take real fixtures with
    it."""
    minted = (T0 - 2 * D).replace(second=17, microsecond=316804)
    stamped = Ev(commence=minted, source="kalshi", created=minted.replace(tzinfo=None))
    real = (T0 - 2 * D).replace(second=0, microsecond=0)
    discovered = Ev(commence=real, source="kalshi", created=real.replace(tzinfo=None))
    assert start_refusal(stamped) == "start_not_reported"
    assert start_refusal(discovered, resolution_date=real + 3 * H) is None


def test_a_start_nobody_can_vouch_for_is_its_own_class():
    """``commence_time_is_a_reported_start(None)`` answers True, deliberately,
    for a PROMOTION rule. A truth measurement may not score against an
    unprovenanced instant — counted apart so the walk reports what that costs."""
    assert start_refusal(Ev(source=None)) == "start_provenance_unknown"


def test_no_linked_event_means_the_boundary_is_a_settlement_date():
    """A "final pre-event" leg drawn before a settlement date can sit anywhere
    inside the event, including after the result was effectively known."""
    assert start_refusal(None) == "unanchored_boundary"
    assert start_refusal(Ev(commence=None)) == "unanchored_boundary"


def test_our_own_columns_contradicting_the_start_are_a_refusal():
    assert start_refusal(Ev(completed=T0 - 1 * H)) == "start_contradicted"  # gotcha #46
    assert start_refusal(Ev(), resolution_date=T0 - 1 * D) == "start_contradicted"
    # minutes of disagreement are not a contradiction
    assert start_refusal(Ev(), resolution_date=T0 + 3 * H) is None


def test_a_settlement_before_the_start_is_refused_not_clamped():
    """CAL-P1333 / codex local check 2. The band ``start_contradicted`` leaves.

    A settlement can never truly precede the start it belongs to, so one of the
    two columns is wrong. Inside the 6h tolerance the old rule said "close
    enough" and let ``LEAST`` re-anchor the whole measurement on the settlement
    timestamp. Both edges are pinned so neither the tolerance nor the new bare
    ``<`` can be moved without this failing.
    """
    # inside the tolerance: used to fall through to the clamp, now refused
    assert (
        start_refusal(Ev(), resolution_date=T0 - 1 * H) == "settlement_precedes_start"
    )
    assert (
        start_refusal(Ev(), resolution_date=T0 - 5 * H) == "settlement_precedes_start"
    )
    # one second before the start is still before the start
    assert (
        start_refusal(Ev(), resolution_date=T0 - timedelta(seconds=1))
        == "settlement_precedes_start"
    )
    # beyond it the flagrant arm still owns the row, and the two stay distinct
    assert start_refusal(Ev(), resolution_date=T0 - 7 * H) == "start_contradicted"
    # settling AT the start is not settling before it
    assert start_refusal(Ev(), resolution_date=T0) is None


def test_a_wrong_late_start_no_longer_admits_an_in_game_price():
    """The probe specimen, run through the real ``classify_pair``.

    A game starting 19:00 and settling 22:30 whose stored ``commence_time`` is
    the market CLOSE time of 23:00 (gotcha #14). ``LEAST`` clamped the boundary
    to 22:30, so the last price before it — taken at 21:45, deep inside the game
    — was scored as a final PRE-EVENT forecast. ``completed_at`` is NULL here,
    which is what let it through: that is the only arm that used to fire.
    """
    real_start = datetime(2026, 1, 10, 19, 0, tzinfo=timezone.utc)
    settlement = datetime(2026, 1, 10, 22, 30, tzinfo=timezone.utc)
    close_time = datetime(2026, 1, 10, 23, 0, tzinfo=timezone.utc)
    in_game = datetime(2026, 1, 10, 21, 45, tzinfo=timezone.utc)
    rows = [
        snap(real_start - 25 * H, 0.50, valid_until=real_start - 24 * H),
        snap(in_game, 0.94, yes_bid=0.93, yes_ask=0.95),
    ]

    # `completed_at` NULL is the condition — set after construction because the
    # fixture's `completed=None` means "use the default", not "the column is
    # NULL", and this specimen needs the column genuinely empty.
    wrong_late = Ev(commence=close_time)
    wrong_late.completed_at = None
    klass, early, final = classify_pair(
        rows, event=wrong_late, market_source="kalshi", resolution_date=settlement
    )
    assert klass == "settlement_precedes_start"
    assert (early, final) == (None, None), "a refused row may never score"

    # CONTROL: the same snapshots against the TRUE start were always refused,
    # so the in-game price is not something the rule wants in general.
    correct = Ev(commence=real_start)
    correct.completed_at = None
    control, _, _ = classify_pair(
        rows, event=correct, market_source="kalshi", resolution_date=settlement
    )
    assert control not in PAIRED_CLASSES
    assert control == "no_final_stale"


def test_the_refusal_fires_before_the_clamp_can_move_start():
    """Named in ``classify_pair``'s comment: the clamp is dead only because the
    ladder refuses first. Pin the ordering that makes it dead, so reordering the
    ladder cannot quietly restore an in-game boundary."""
    assert PAIR_CLASSES.index(mod.PAIR_SETTLEMENT_PRECEDES_START) < PAIR_CLASSES.index(
        mod.PAIR_PAIRED
    )
    # every row the clamp could act on is refused before it is reached
    assert start_refusal(Ev(), resolution_date=T0 - 1 * H) is not None


def test_the_settlement_boundary_branch_carries_no_tolerance():
    """The SQL half. A tolerance here would re-open the band the Python half
    closes, and the two would disagree only on production."""
    rendered = mod.settlement_precedes_start_sql()
    assert "fm.resolution_date < e.commence_time" in rendered
    assert "INTERVAL" not in rendered, "the residual band is the whole point"
    assert mod.settlement_precedes_start_sql() in paired_legs_sql()


def test_start_refusal_refuses_a_bare_timestamp():
    """The pre-CAL-P1330 signature took ``commence_time``. Read through getattr
    a datetime answers "unanchored" for every row — a wrong answer that looks
    like a finding."""
    with pytest.raises(TypeError):
        start_refusal(T0)


def test_boundary_is_anchored_is_the_single_provenance_question():
    assert boundary_is_anchored(Ev(), resolution_date=T0 + 3 * H)
    assert not boundary_is_anchored(Ev(source="kalshi_ticker"))
    assert not boundary_is_anchored(None)


def test_legs_from_two_sportsbooks_are_not_a_forecast_change():
    """C5. ``probability`` is one book's raw, margin-inclusive number."""
    rows = [
        snap(T0 - 26 * H, 0.52, book="draftkings", valid_until=T0 - 25 * H),
        snap(T0 - 1 * H, 0.58, book="fanduel", yes_bid=0.57, yes_ask=0.59),
    ]
    assert classify(rows, market_source="odds_api")[0] == "legs_from_different_books"


def test_one_book_holding_both_legs_pairs_even_when_another_book_is_present():
    """The control for the test above: the presence of a second book must not
    refuse a pair the native book fully supplies."""
    rows = standard(0.55, 0.70, book="kalshi") + [
        snap(T0 - 2 * H, 0.61, book="draftkings", yes_bid=0.60, yes_ask=0.62)
    ]
    assert classify(rows)[0] == "paired"


def test_a_fabricated_midpoint_is_not_a_price():
    """C6. bid 0.001 / ask 1.000 is "nobody will trade this at any price"."""
    rows = [
        snap(T0 - 26 * H, 0.55, valid_until=T0 - 25 * H),
        snap(T0 - 1 * H, 0.5005, yes_bid=0.001, yes_ask=1.0),
    ]
    assert classify(rows)[0] == "no_final_stale"


def test_only_starting_to_watch_inside_the_lead_window_is_its_own_class():
    """E5. A usable final leg and nothing at all a day out."""
    rows = [snap(T0 - 1 * H, 0.50, yes_bid=0.49, yes_ask=0.51)]
    assert classify(rows)[0] == "no_early_none_before"


def test_an_early_leg_we_stopped_confirming_is_stale_not_absent():
    """Two different findings; summing them would hide which this is."""
    rows = [
        snap(T0 - 20 * D, 0.30, valid_until=T0 - 19 * D),
        snap(T0 - 1 * H, 0.50, yes_bid=0.49, yes_ask=0.51),
    ]
    assert classify(rows)[0] == "no_early_stale"


def test_a_look_after_the_start_never_freshens_the_final_leg():
    """CAL-P1331, the commissioning directive's first correctness check.

    One collapsed run, first seen three days before the start. Its ONLY
    pre-start observation is that three-day-old capture; retention discarded
    every intermediate timestamp, so the ``valid_until`` two hours PAST the
    start proves a look before the start and a look after it and nothing about
    the interval this test is asking about.

    Before the repair this returned ``('paired_unchanged', 0.62, 0.62)`` — a
    perfectly scored pair — because the clamp gave it staleness zero. The row
    below it is the same price refused for being stale; the only difference
    between the two was evidence from after the event began.
    """
    crosses = [snap(T0 - 3 * D, 0.62, valid_until=T0 + 2 * H)]
    assert classify(crosses)[0] == "no_final_unconfirmed_span"
    assert classify(crosses)[1:] == (None, None)

    ends_before = [snap(T0 - 3 * D, 0.62, valid_until=T0 - 2 * D)]
    assert classify(ends_before)[0] == "no_final_stale"


def test_a_later_look_never_freshens_the_early_leg_either():
    """The same defect at the 24h boundary, and it needs no after-START
    evidence at all: a run last confirmed two hours before the start still
    crosses a boundary a DAY before it, which lent this thirty-day-old price a
    staleness of zero and paired it as the market's view "a day out"."""
    rows = [
        snap(T0 - 30 * D, 0.20, valid_until=T0 - 2 * H),
        snap(T0 - 1 * H, 0.80, yes_bid=0.79, yes_ask=0.81),
    ]
    assert classify(rows)[0] == "no_early_unconfirmed_span"


def test_a_confirmation_before_the_cutoff_still_pairs():
    """The control that keeps the repair from being a blanket refusal: the
    directive's own words are that identical values may legitimately pair when
    actual pre-cutoff confirmation exists. Same thirty-day-old capture as the
    test above, confirmed 25h out — an hour BEFORE the early instant."""
    rows = [
        snap(T0 - 30 * D, 0.20, valid_until=T0 - 25 * H),
        snap(T0 - 1 * H, 0.80, yes_bid=0.79, yes_ask=0.81),
    ]
    assert classify(rows) == ("paired", 0.20, 0.80)


def test_the_staleness_bounds_are_parameters_and_they_bind():
    rows = [snap(T0 - 26 * H, 0.35, valid_until=T0 - 25 * H)]
    assert classify(rows)[0] == "no_final_stale"
    assert classify(rows, final_max_stale_seconds=30 * 3600)[0] == "paired_unchanged"


def test_every_emitted_class_is_declared():
    """A class the module can return but never named would be invisible to the
    walk's report."""
    seen = {
        classify(standard(0.55, 0.70))[0],
        classify(standard(0.55, 0.70), event=Ev(source="kalshi_ticker"))[0],
        classify(standard(0.55, 0.70), event=None)[0],
        classify(standard(0.55, 0.70), event=Ev(source=None))[0],
        classify(standard(0.55, 0.70), event=Ev(completed=T0 - 1 * H))[0],
        classify([snap(T0 - 3 * D, 0.70, valid_until=T0 - 1 * H)])[0],
        classify([snap(T0 - 26 * H, 0.35, valid_until=T0 - 25 * H)])[0],
        classify([snap(T0 - 1 * H, 0.5, yes_bid=0.49, yes_ask=0.51)])[0],
        classify([], is_winner=None, resolution_source=None, eligible_sources=["x"])[0],
        classify([snap(T0 - 3 * D, 0.62, valid_until=T0 + 2 * H)])[0],
        classify(
            [
                snap(T0 - 30 * D, 0.20, valid_until=T0 - 2 * H),
                snap(T0 - 1 * H, 0.80, yes_bid=0.79, yes_ask=0.81),
            ]
        )[0],
    }
    assert seen <= set(PAIR_CLASSES)
    assert len(seen) >= 10


def test_forecast_kind_separates_a_model_from_a_market():
    assert forecast_kind("datagolf") == "model"
    assert forecast_kind("kalshi") == "market"
    assert forecast_kind("odds_api") == "market"  # a market with no volume feed


# ---------------------------------------------------------------------------
# The measure
# ---------------------------------------------------------------------------

#: The report's §3(B) worked example: three two-sided games plus one that never
#: moved. Four events, eight outcomes, one event that got WORSE.
WORKED_PAIRS = [
    (0.55, 0.70, True),
    (0.45, 0.30, False),  # E1 improved
    (0.60, 0.50, True),
    (0.40, 0.50, False),  # E2 got worse
    (0.50, 0.65, True),
    (0.50, 0.35, False),  # E3 improved
    (0.70, 0.70, True),
    (0.30, 0.30, False),  # E7 never moved
]
WORKED_EVENTS = ["E1", "E1", "E2", "E2", "E3", "E3", "E7", "E7"]


def test_the_worked_example_from_the_report_reproduces_exactly():
    """If these numbers move, either the module changed or the report is wrong.
    Either way somebody must look; they are not incidental."""
    s = paired_improvement(WORKED_PAIRS, cluster_ids=WORKED_EVENTS)
    assert s["n"] == 8 and s["n_events"] == 4
    assert s["early_mean"] == pytest.approx(0.175625)
    assert s["final_mean"] == pytest.approx(0.138125)
    assert s["mean_delta"] == pytest.approx(0.0375)
    assert (s["events_improved"], s["events_worse"], s["events_unchanged"]) == (2, 1, 1)


def test_positive_mean_delta_means_the_final_forecast_was_better():
    s = paired_improvement([(0.50, 0.90, True), (0.50, 0.80, True)])
    assert s["mean_delta"] > 0


def test_a_cohort_that_got_worse_is_reported_not_suppressed():
    s = paired_improvement(
        [(0.90, 0.50, True), (0.80, 0.50, True)], cluster_ids=["a", "b"]
    )
    assert s["mean_delta"] < 0
    assert s["events_worse"] == 2 and s["events_improved"] == 0


def test_two_legs_of_one_game_are_one_piece_of_evidence():
    """The naive error bar counts them as two and is too narrow."""
    s = paired_improvement(WORKED_PAIRS, cluster_ids=WORKED_EVENTS)
    assert s["cluster_se"] > s["se"]


def test_one_outcome_per_cluster_collapses_toward_the_naive_error():
    pairs = [
        (0.50, 0.60, True),
        (0.50, 0.40, False),
        (0.30, 0.20, False),
        (0.70, 0.80, True),
    ]
    s = paired_improvement(pairs, cluster_ids=["a", "b", "c", "d"])
    assert s["cluster_se"] == pytest.approx(s["se"], rel=0.4)


def test_no_margin_is_published_below_the_cluster_floor():
    s = paired_improvement(WORKED_PAIRS, cluster_ids=WORKED_EVENTS)
    assert s["n_events"] < MIN_CLUSTERS_FOR_MARGIN
    assert s["displayable_margin"] is None
    assert s["cluster_se"] is not None  # computed and reportable, just not shown


def test_a_margin_appears_once_there_are_enough_events():
    pairs = [(0.50, 0.60, i % 2 == 0) for i in range(MIN_CLUSTERS_FOR_MARGIN)]
    clusters = [f"E{i}" for i in range(MIN_CLUSTERS_FOR_MARGIN)]
    s = paired_improvement(pairs, cluster_ids=clusters)
    assert s["n_events"] == MIN_CLUSTERS_FOR_MARGIN
    assert s["displayable_margin"] == s["cluster_se"]


def test_without_cluster_ids_no_margin_is_publishable():
    """A number whose clustering nobody declared cannot be defended, so the
    absence of the argument is a refusal rather than a fallback."""
    s = paired_improvement(WORKED_PAIRS)
    assert s["displayable_margin"] is None
    assert s["cluster_se"] is None and s["n_events"] is None
    assert s["se"] is not None


def test_pooling_a_model_with_market_prices_raises():
    """Not a rule a caller has to remember: ``datagolf`` is a model output and
    averaging it with quoted prices is not a number of anything."""
    with pytest.raises(ValueError, match="must not be pooled"):
        paired_improvement(
            [(0.50, 0.60, True), (0.12, 0.10, False)],
            forecast_kinds=["market", "model"],
        )


def test_a_single_kind_cohort_is_fine():
    s = paired_improvement(
        [(0.12, 0.10, False), (0.20, 0.15, False)], forecast_kinds=["model", "model"]
    )
    assert s["n"] == 2


@pytest.mark.parametrize("kwarg", ["cluster_ids", "forecast_kinds"])
def test_a_parallel_sequence_of_the_wrong_length_raises(kwarg):
    with pytest.raises(ValueError):
        paired_improvement(
            [(0.5, 0.6, True), (0.5, 0.4, False)], **{kwarg: ["only-one"]}
        )


def test_empty_and_single_pair_cohorts_return_none_not_zero():
    """A perfect-looking score standing in for no data is gotcha #53 at the top
    of this product's most-cited number."""
    assert paired_improvement([]) is None
    assert paired_improvement([(0.5, 0.6, True)]) is None


def test_n_counts_outcomes_not_legs():
    assert paired_improvement([(0.5, 0.6, True), (0.5, 0.4, False)])["n"] == 2


def test_unknown_score_raises_before_it_is_used():
    with pytest.raises(ValueError):
        paired_improvement(WORKED_PAIRS, score="rmse")


def test_log_loss_and_brier_can_be_selected_independently():
    a = paired_improvement(WORKED_PAIRS, score="brier")
    b = paired_improvement(WORKED_PAIRS, score="log_loss")
    assert a["mean_delta"] != b["mean_delta"]


def test_brier_is_squared_error_against_the_realised_outcome():
    assert brier(1.0, True) == 0.0
    assert brier(0.0, True) == 1.0
    assert brier(0.5, False) == 0.25


def test_log_loss_is_finite_at_the_extremes():
    assert log_loss(1.0, False) > 0 and log_loss(1.0, False) != float("inf")


def test_the_aggregate_can_point_the_opposite_way_from_the_paired_result():
    """Section (A) of the report's worked example, as a guard.

    The early group is full of 3% longshots (a tiny Brier by construction); the
    late group is coin flips we only began polling two hours out. The aggregate
    says forecasts got WORSE. On the outcomes that appear in BOTH groups they
    got better. This is the whole reason the paired cohort exists, so it is
    asserted rather than described.
    """
    early_only = [brier(0.03, False) for _ in range(10)]
    late_only = [brier(0.50, i % 2 == 0) for i in range(4)]
    paired_early = [brier(e, w) for e, _, w in WORKED_PAIRS]
    paired_final = [brier(f, w) for _, f, w in WORKED_PAIRS]

    aggregate_early = early_only + paired_early
    aggregate_late = late_only + paired_final
    assert sum(aggregate_late) / len(aggregate_late) > sum(aggregate_early) / len(
        aggregate_early
    )

    s = paired_improvement(WORKED_PAIRS, cluster_ids=WORKED_EVENTS)
    assert s["mean_delta"] > 0  # the same rows, the opposite conclusion


# ---------------------------------------------------------------------------
# Calibration is a separate sentence
# ---------------------------------------------------------------------------


def test_calibration_is_computed_on_both_legs_of_the_same_population():
    out = leg_calibration(WORKED_PAIRS)
    assert set(out) == {"early_ece_pp", "late_ece_pp"}
    assert out["early_ece_pp"] is not None and out["late_ece_pp"] is not None


def test_perfect_calibration_is_not_accuracy():
    """A forecaster who says 50% on every coin flip is perfectly calibrated and
    useless. The page needs both words."""
    coin = [(0.5, True), (0.5, False)] * 50
    sharp = (
        [(0.9, True)] * 45
        + [(0.9, False)] * 5
        + [(0.1, False)] * 45
        + [(0.1, True)] * 5
    )
    for forecasts in (coin, sharp):
        gap = abs(
            sum(p for p, _ in forecasts) / len(forecasts)
            - sum(w for _, w in forecasts) / len(forecasts)
        )
        assert gap == pytest.approx(0.0, abs=1e-9)
    assert sum(brier(p, w) for p, w in coin) / len(coin) == pytest.approx(0.25)
    assert sum(brier(p, w) for p, w in sharp) / len(sharp) == pytest.approx(0.09)


def test_a_forecast_can_sharpen_while_calibration_worsens():
    """Early: 50% on ten coin flips, five of which won — perfectly calibrated,
    Brier 0.25. Final: 0.8 on every winner and 0.2 on every loser — Brier 0.04,
    and 20 points off the diagonal in both bins. Sharper AND worse calibrated,
    which is why the page may not collapse the two words into one."""
    pairs = [(0.50, 0.80, True)] * 5 + [(0.50, 0.20, False)] * 5
    s = paired_improvement(pairs)
    out = leg_calibration(pairs)
    assert s["mean_delta"] > 0  # sharper
    assert out["early_ece_pp"] == pytest.approx(0.0, abs=1e-9)
    assert out["late_ece_pp"] > out["early_ece_pp"]  # and further off the diagonal


def test_empty_calibration_is_absent_not_zero():
    out = leg_calibration([])
    assert out["early_ece_pp"] is None and out["late_ece_pp"] is None


# ---------------------------------------------------------------------------
# The constants are policy, and policy is stated
# ---------------------------------------------------------------------------


def test_the_lead_is_twenty_four_hours_and_one_rung_only():
    """CAL-P1330's recorded decision. A 7-day rung is legitimate only as its own
    paired set — comparing it against this one is the cross-population defect
    the module exists to remove."""
    assert DEFAULT_LEAD_SECONDS == 24 * 3600


def test_the_final_bound_is_tighter_than_the_early_one():
    """The hour before a start is polled far more often than the day before; a
    bound tighter than the cadence empties the cohort for a reason that has
    nothing to do with the market."""
    assert DEFAULT_FINAL_MAX_STALE_SECONDS < DEFAULT_EARLY_MAX_STALE_SECONDS
    assert DEFAULT_FINAL_MAX_STALE_SECONDS >= 6 * 3600


def test_the_minimum_separation_constant_is_gone():
    """A fixed 24h lead makes it unnecessary: two instants a day apart cannot be
    one poll sampled twice. Leaving it would leave two definitions of a pair."""
    assert not hasattr(mod, "DEFAULT_MIN_SEPARATION_SECONDS")
    assert not hasattr(mod, "PAIR_TOO_CLOSE")
    assert "legs_too_close" not in PAIR_CLASSES


def test_the_first_ever_snapshot_selector_is_gone_not_aliased():
    """An alias would keep old call sites compiling while silently answering a
    different question. A NameError names itself."""
    assert not hasattr(mod, "select_paired_legs")
