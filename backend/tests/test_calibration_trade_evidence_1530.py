"""CAL-P044 — #1530 / ruling 011: trade evidence, and the SQL that must agree with it.

The load-bearing test in this file is
:class:`TestTheSqlAndThePythonAgree`. Everything else pins a clause; that one
pins the pair. ``outcome_is_calibration_liquid`` and ``KALSHI_LIQUIDITY_EXISTS``
are maintained as a twin the same way and their comment says "keep the two in
sync" — which is a request, not a mechanism. Here the SQL is EXECUTED against
the same matrix the Python classifier is, so "in sync" is asserted rather than
asked for.

It runs on stdlib ``sqlite3``. The predicate is plain ANSI ``CASE`` over
comparisons, and the one semantic that could differ across engines — ``NULL > 0``
and ``NULL = 0`` both being NULL rather than false — is identical in SQLite and
PostgreSQL, and is asserted directly below so the oracle cannot quietly stop
being an oracle. (No local PostgreSQL exists in this sandbox; a real-PG harness
would be strictly better and is not available.)
"""

from __future__ import annotations

import sqlite3

import pytest

from app.tasks.census_trade_evidence import (
    build_census,
    cohort_key,
    cohorts_sql,
    is_complete_walk,
    merge_windows,
    totals,
)
from app.utils.calibration_trade_evidence import (
    CLASSES,
    EVIDENCED_CLASSES,
    EXCLUDED_SOURCES,
    TRADED_CLASSES,
    classify,
    empty_counts,
    summarise,
    trade_evidence_sql,
    unrecognised_classes,
)

# Every interesting combination, including the ones that should never occur —
# a negative volume and an excluded source that somehow reports one — because
# the classifier's job is to be total, and a partition with an unreachable
# branch is still a partition that has to answer.
MATRIX = [
    ("kalshi", 5, 100),
    ("kalshi", 5, None),
    ("kalshi", 0, 100),
    ("kalshi", 0, 0),
    ("kalshi", 0, None),
    ("kalshi", None, 100),
    ("kalshi", None, 0),
    ("kalshi", None, None),
    ("polymarket", 1, None),
    ("polymarket", 0, None),
    ("polymarket", None, None),
    ("polymarket", None, 7),
    ("odds_api", 999, 999),
    ("odds_api", None, None),
    ("odds_api", 0, None),
    ("datagolf", 42, 42),
    ("datagolf", None, None),
    ("kalshi", -1, None),
    ("kalshi", -1, 5),
]


class TestTheRuleItself:
    def test_volume_above_zero_is_traded(self):
        assert classify("kalshi", 5, None) == "traded"
        assert classify("polymarket", 1, None) == "traded"

    def test_an_explicit_zero_is_untraded_and_is_never_laundered_into_unknown(self):
        # The other half of gotcha #53. "We looked and there were no trades" and
        # "we have no figure" are different facts; collapsing the first into the
        # second discards the only rows that can ever falsify the tier.
        assert classify("kalshi", 0, None) == "untraded"
        assert classify("kalshi", 0, 500) == "untraded", (
            "outcome-level evidence outranks the market-level backup: an outcome "
            "that reports zero volume did not trade, whatever its market did"
        )

    def test_null_volume_is_never_untraded(self):
        # THE ruling (011). Polymarket is 95.2% NULL on volume with four explicit
        # zeros in thirty days; reading NULL as untraded publishes 95% of
        # Polymarket as never-traded.
        for open_interest in (None, 0, 1, 10_000):
            assert classify("polymarket", None, open_interest) != "untraded"

    def test_the_open_interest_backup_is_its_own_class_not_traded(self):
        assert classify("kalshi", None, 100) == "traded_open_interest"
        assert classify("kalshi", None, 100) != "traded", (
            "open interest is market-level: it proves the market traded, not that "
            "this leg did, and a weaker claim has to stay visibly weaker"
        )

    def test_open_interest_zero_or_null_leaves_it_unknown(self):
        assert classify("kalshi", None, 0) == "unknown"
        assert classify("kalshi", None, None) == "unknown"

    @pytest.mark.parametrize("source", EXCLUDED_SOURCES)
    def test_an_excluded_source_is_named_excluded_before_volume_is_read(self, source):
        # ORDER, not just membership. If the source test moved below the volume
        # clauses, this row would read 'traded' — and an odds_api row reported as
        # traded is a claim about a column that does not exist for it.
        assert classify(source, 999, 999) == "not_applicable"
        assert classify(source, 0, None) == "not_applicable", (
            "and it must not read 'untraded' either — excluded is not evidence"
        )
        assert classify(source, None, None) == "not_applicable", (
            "nor 'unknown', which would read as 'we might find out later'"
        )

    def test_a_negative_volume_is_unknown_rather_than_invented(self):
        assert classify("kalshi", -1, None) == "unknown"

    def test_the_classifier_is_total_over_the_declared_partition(self):
        for source, volume, oi in MATRIX:
            assert classify(source, volume, oi) in CLASSES


class TestTheSqlAndThePythonAgree:
    """The oracle. Two definitions of one rule is the failure; this is the check."""

    @staticmethod
    def _sqlite_classify(rows):
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE fm (id INTEGER, source TEXT, open_interest INTEGER)")
        con.execute("CREATE TABLE fo (id INTEGER, market_id INTEGER, volume INTEGER)")
        for i, (source, volume, oi) in enumerate(rows):
            con.execute("INSERT INTO fm VALUES (?,?,?)", (i, source, oi))
            con.execute("INSERT INTO fo VALUES (?,?,?)", (i, i, volume))
        case = trade_evidence_sql()
        cur = con.execute(
            f"SELECT fo.id, {case} FROM fo JOIN fm ON fm.id = fo.market_id ORDER BY fo.id"
        )
        return [value for _, value in cur.fetchall()]

    def test_null_comparison_semantics_match_postgres(self):
        # The one assumption the oracle rests on, asserted rather than trusted:
        # in BOTH engines `NULL > 0` and `NULL = 0` are NULL, so a NULL volume
        # falls through both volume clauses instead of matching one. If SQLite
        # ever disagreed, every equivalence assertion below would silently start
        # comparing the Python rule against a different rule.
        con = sqlite3.connect(":memory:")
        assert con.execute("SELECT NULL > 0").fetchone()[0] is None
        assert con.execute("SELECT NULL = 0").fetchone()[0] is None
        assert con.execute("SELECT CASE WHEN NULL > 0 THEN 'y' ELSE 'n' END").fetchone()[0] == "n"

    def test_every_matrix_row_classifies_identically_in_sql_and_python(self):
        assert self._sqlite_classify(MATRIX) == [classify(*row) for row in MATRIX]

    def test_the_oracle_is_not_vacuous_it_catches_a_reordered_case(self):
        # Mutation: hoist the volume clause above the source exclusion. This is
        # the single most plausible "tidy-up" edit to that CASE, and it changes
        # a real answer — so the oracle has to notice, or it is decoration.
        broken = (
            "(CASE"
            " WHEN fo.volume > 0 THEN 'traded'"
            " WHEN fm.source IN ('odds_api', 'datagolf') THEN 'not_applicable'"
            " WHEN fo.volume = 0 THEN 'untraded'"
            " WHEN fo.volume IS NULL AND fm.open_interest > 0 THEN 'traded_open_interest'"
            " ELSE 'unknown' END)"
        )
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE fm (id INTEGER, source TEXT, open_interest INTEGER)")
        con.execute("CREATE TABLE fo (id INTEGER, market_id INTEGER, volume INTEGER)")
        con.execute("INSERT INTO fm VALUES (1,'odds_api',999)")
        con.execute("INSERT INTO fo VALUES (1,1,999)")
        mutated = con.execute(
            f"SELECT {broken} FROM fo JOIN fm ON fm.id = fo.market_id"
        ).fetchone()[0]
        assert mutated == "traded"
        assert classify("odds_api", 999, 999) == "not_applicable"
        assert mutated != classify("odds_api", 999, 999)


class TestTheDerivedFigures:
    def test_unknown_is_excluded_from_the_traded_share_denominator(self):
        counts = {"traded": 60, "untraded": 20, "unknown": 920}
        summary = summarise(counts)
        # 60/80, not 60/1000. The unknown rows say nothing in either direction;
        # counting them as if they said "untraded" is the artifact, restated.
        assert summary["traded_share_of_evidenced_pct"] == 75.0
        assert summary["evidenced_n"] == 80
        assert summary["evidence_coverage_pct"] == 8.0

    def test_open_interest_counts_as_traded_in_the_share(self):
        assert summarise({"traded_open_interest": 3, "untraded": 1})[
            "traded_share_of_evidenced_pct"
        ] == 75.0

    def test_no_evidence_reads_as_cannot_say_never_as_zero_percent_traded(self):
        summary = summarise({"unknown": 500})
        assert summary["traded_share_of_evidenced_pct"] is None
        assert summary["evidence_coverage_pct"] == 0.0

    def test_an_empty_cohort_divides_by_nothing_and_says_so(self):
        summary = summarise({})
        assert summary["n"] == 0
        assert summary["traded_share_of_evidenced_pct"] is None
        assert summary["evidence_coverage_pct"] is None

    def test_every_class_is_always_present_including_the_zeros(self):
        assert set(empty_counts()) == set(CLASSES)
        assert set(summarise({"traded": 1})) >= set(CLASSES)

    def test_the_class_groupings_are_a_consistent_subset_of_the_partition(self):
        assert set(TRADED_CLASSES) < set(EVIDENCED_CLASSES) < set(CLASSES)
        assert "unknown" not in EVIDENCED_CLASSES
        assert "not_applicable" not in EVIDENCED_CLASSES


class TestTheWalkFolds:
    @staticmethod
    def _cohort(source, moved, klass, n, wins=0, pred=0.0):
        return {
            "source": source,
            "price_moved": moved,
            "trade_evidence": klass,
            "n": n,
            "wins": wins,
            "sum_pred": pred,
        }

    def test_windows_sum_rather_than_average(self):
        merged = merge_windows([
            {"cohorts": [self._cohort("kalshi", False, "traded", 10, 3, 4.0)]},
            {"cohorts": [self._cohort("kalshi", False, "traded", 90, 7, 36.0)]},
        ])
        row = merged[cohort_key("kalshi", False, "traded")]
        assert (row["n"], row["wins"], row["sum_pred"]) == (100, 10, 40.0)

    def test_the_price_moved_tristate_round_trips_and_null_is_its_own_cohort(self):
        # None is a real third value (the sportsbook rows), not a missing one. If
        # it keyed the same as False it would land in "price unchanged" and
        # invent a claim about movement that no row made.
        assert len({
            cohort_key("kalshi", True, "traded"),
            cohort_key("kalshi", False, "traded"),
            cohort_key("kalshi", None, "traded"),
        }) == 3

    def test_a_null_price_moved_row_lands_in_neither_movement_cohort(self):
        census = build_census([{
            "rows_walked": 1,
            "exhausted": True,
            "cohorts": [self._cohort("odds_api", None, "not_applicable", 25)],
        }])
        source = census["by_source"][0]
        assert source["n"] == 25
        assert source["price_moved_cohort"]["n"] == 0
        assert source["price_unchanged_cohort"]["n"] == 0

    def test_a_partial_walk_is_not_complete(self):
        assert is_complete_walk([{"exhausted": False}]) is False
        assert is_complete_walk([]) is False
        assert is_complete_walk([{"exhausted": False}, {"exhausted": True}]) is True

    def test_an_incomplete_census_still_reports_and_says_it_is_incomplete(self):
        # Both directions (gotcha #43): it must not go silent when partial, and
        # it must not claim completeness. A census that only speaks when whole
        # goes quiet exactly when the caller needs to know it is not.
        census = build_census([{
            "rows_walked": 5,
            "exhausted": False,
            "cohorts": [self._cohort("kalshi", True, "traded", 5)],
        }])
        assert census["complete"] is False
        assert census["totals"]["traded"] == 5

    def test_an_unrecognised_class_turns_the_contract_red_by_name(self):
        census = build_census([{
            "rows_walked": 1,
            "exhausted": True,
            "cohorts": [self._cohort("kalshi", True, "sort_of_traded", 1)],
        }])
        assert census["contract_ok"] is False
        assert census["unrecognised_classes"] == ["sort_of_traded"]

    def test_a_clean_census_is_green_and_totals_every_class(self):
        census = build_census([{
            "rows_walked": 3,
            "exhausted": True,
            "cohorts": [
                self._cohort("kalshi", False, "traded", 61),
                self._cohort("kalshi", False, "untraded", 6),
                self._cohort("kalshi", False, "unknown", 33),
            ],
        }])
        assert census["contract_ok"] is True
        assert census["unrecognised_classes"] == []
        assert set(census["totals"]) == set(CLASSES)
        assert census["overall"]["traded_share_of_evidenced_pct"] == 91.0

    def test_unrecognised_classes_helper_ignores_the_declared_ones(self):
        assert unrecognised_classes(CLASSES) == []
        assert unrecognised_classes(list(CLASSES) + ["nope"]) == ["nope"]

    def test_totals_are_all_classes_even_when_nothing_was_measured(self):
        assert totals({}) == empty_counts()


class TestTheCensusStatement:
    def test_it_reads_the_truth_eligibility_allowlist_not_a_local_denylist(self):
        from app.utils.resolution_authority import CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL

        assert CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL in cohorts_sql()

    def test_it_reads_the_same_price_moved_expression_the_page_publishes(self):
        # A paraphrase here would compare the new evidence against something
        # /calibration does not actually plot, which is worse than not comparing.
        import inspect

        from app.tasks import precompute_calibration

        producer = inspect.getsource(precompute_calibration._calibration_population_ctes)
        expression = (
            "fo.calibration_probability IS NOT NULL"
            " AND fo.calibration_probability IS DISTINCT FROM fo.opening_probability"
        )
        assert expression.replace(" ", "") in producer.replace("\n", " ").replace(" ", "")
        assert expression.replace(" ", "") in cohorts_sql().replace(" ", "")

    def test_the_window_is_row_bounded_not_id_width(self):
        # The measured lesson from census_reachability: outcome ids are not
        # uniformly dense, so a fixed id span is thousands of rows in one region
        # and millions in another.
        from app.tasks.census_trade_evidence import _BOUNDS_SQL

        assert "LIMIT :scan" in _BOUNDS_SQL
        assert "ORDER BY id ASC" in _BOUNDS_SQL

    def test_the_statement_never_writes(self):
        import inspect

        from app.tasks import census_trade_evidence

        source = inspect.getsource(census_trade_evidence)
        for verb in ("UPDATE ", "INSERT ", "DELETE ", "ALTER "):
            assert verb not in source.upper().replace("STATEMENT_TIMEOUT", "")


# ---------------------------------------------------------------------------
# #1870 consumer half — the Polymarket receipt.
# ---------------------------------------------------------------------------

_NOW = "2026-10-02T18:00:00+00:00"


def _forward(amount):
    """A receipt exactly as the forward poller writes it."""
    from datetime import datetime, timezone

    from app.tasks.polymarket import polymarket_activity_volume

    out = polymarket_activity_volume(
        amount, observed_at=datetime(2026, 10, 2, 18, tzinfo=timezone.utc)
    )
    return out.scalar, out.receipt


def _recovery(evidence, *, n_trades=None, gamma_volume=None):
    """A receipt exactly as the recovery rail writes it."""
    from app.utils.polymarket_evidence import PMEvidence, build_evidence_receipt

    return build_evidence_receipt(
        PMEvidence(evidence), n_trades=n_trades, gamma_volume=gamma_volume
    )


def _meta(receipt):
    return {"volume_evidence": receipt}


class TestThePolymarketReceipt:
    def test_the_forward_probe_string_is_the_pollers_own(self):
        from app.tasks.polymarket import POLYMARKET_CONDITION_VOLUME_PROBE
        from app.utils.calibration_trade_evidence import FORWARD_EVIDENCE_PROBE

        assert FORWARD_EVIDENCE_PROBE == POLYMARKET_CONDITION_VOLUME_PROBE

    def test_a_fractional_forward_receipt_beside_null_is_traded(self):
        # THE ship. Gamma said 0.25; the integer column holds NULL; the old rule
        # read 'unknown' and the reader saw nothing about a market that traded.
        scalar, receipt = _forward(0.25)
        assert scalar is None
        assert classify("polymarket", scalar, None) == "unknown", "the old reading"
        assert classify("polymarket", scalar, None, _meta(receipt)) == "traded"

    def test_a_recovery_traded_receipt_beside_a_manufactured_zero_is_traded(self):
        # The historical rows: the old rail wrote int(0.25) == 0 beside this.
        receipt = _recovery("traded", n_trades=0, gamma_volume=0.25)
        assert classify("polymarket", 0, None) == "untraded", "the old reading"
        assert classify("polymarket", 0, None, _meta(receipt)) == "traded"

    def test_gamma_zero_with_real_trades_is_traded(self):
        receipt = _recovery("traded", n_trades=4, gamma_volume=0.0)
        assert classify("polymarket", 0, None, _meta(receipt)) == "traded"
        assert classify("polymarket", None, None, _meta(receipt)) == "traded"

    def test_a_positive_integral_forward_row_stays_traded(self):
        scalar, receipt = _forward(405.9)
        assert scalar == 405
        assert classify("polymarket", scalar, None, _meta(receipt)) == "traded"

    def test_a_confirmed_zero_survives_from_both_writers(self):
        scalar, receipt = _forward(0)
        assert scalar == 0
        assert classify("polymarket", 0, None, _meta(receipt)) == "untraded"
        assert classify("polymarket", None, None, _meta(receipt)) == "untraded"
        rec = _recovery("confirmed_zero", n_trades=0)
        assert classify("polymarket", 0, None, _meta(rec)) == "untraded"
        rec0 = _recovery("confirmed_zero", n_trades=0, gamma_volume=0.0)
        assert classify("polymarket", None, None, _meta(rec0)) == "untraded"

    def test_a_confirmed_zero_receipt_beside_positive_volume_is_an_explicit_conflict(self):
        _, receipt = _forward(0)
        assert classify("polymarket", 12, None, _meta(receipt)) == "unknown"
        assert classify("polymarket", 12, None) == "traded", "the scalar alone"

    def test_a_confirmed_zero_outranks_market_open_interest_like_a_scalar_zero(self):
        _, receipt = _forward(0)
        assert classify("polymarket", None, 50, _meta(receipt)) == "untraded"

    def test_unfetched_null_with_no_receipt_stays_unknown(self):
        for meta in (None, {}, {"polymarket_event_id": "123"}):
            assert classify("polymarket", None, None, meta) == "unknown"

    def test_an_unaddressable_receipt_is_not_evidence(self):
        receipt = _recovery("unaddressable")
        assert classify("polymarket", None, None, _meta(receipt)) == "unknown"

    @pytest.mark.parametrize(
        "receipt",
        [
            {"verdict": "traded", "probe": "something-else", "gamma_volume": 5.0},
            {"verdict": "traded", "probe": "gamma:events:condition-volume", "gamma_volume": 5.0},
            {"verdict": "traded", "probe": "gamma:events:condition-volume", "grain": "condition"},
            {"verdict": "traded", "probe": "gamma:events:condition-volume", "grain": "condition", "gamma_volume": "5"},
            {"verdict": "traded", "probe": "gamma:events:condition-volume", "grain": "condition", "gamma_volume": True},
            {"verdict": "traded", "probe": "gamma:events:condition-volume", "grain": "condition", "gamma_volume": 0},
            {"verdict": "traded", "probe": "gamma:events:condition-volume", "grain": "condition", "gamma_volume": -1},
            {"verdict": "traded", "probe": "clob:existence+data-api:trades+gamma:events"},
            {"verdict": "traded", "probe": "clob:existence+data-api:trades+gamma:events", "n_trades": 0, "gamma_volume": 0},
            {"verdict": "TRADED", "probe": "clob:existence+data-api:trades+gamma:events", "n_trades": 3},
            {"verdict": None, "probe": "clob:existence+data-api:trades+gamma:events", "n_trades": 3},
            "traded",
            ["traded"],
            None,
        ],
    )
    def test_a_malformed_or_unsupported_traded_receipt_cannot_claim_trading(self, receipt):
        assert classify("polymarket", None, None, _meta(receipt)) == "unknown"
        # ...and it never erases what the scalar already says.
        assert classify("polymarket", 0, None, _meta(receipt)) == "untraded"
        assert classify("polymarket", 7, None, _meta(receipt)) == "traded"

    @pytest.mark.parametrize(
        "receipt",
        [
            {"verdict": "confirmed_zero", "probe": "gamma:events:condition-volume", "grain": "condition"},
            {"verdict": "confirmed_zero", "probe": "gamma:events:condition-volume", "grain": "condition", "gamma_volume": 0.25},
            {"verdict": "confirmed_zero", "probe": "clob:existence+data-api:trades+gamma:events"},
            {"verdict": "confirmed_zero", "probe": "clob:existence+data-api:trades+gamma:events", "n_trades": 2},
            {"verdict": "confirmed_zero", "probe": "clob:existence+data-api:trades+gamma:events", "n_trades": 0, "gamma_volume": "0"},
            {"verdict": "confirmed_zero", "probe": "clob:existence+data-api:trades+gamma:events", "n_trades": 0, "gamma_volume": 3.0},
        ],
    )
    def test_a_malformed_confirmed_zero_receipt_cannot_claim_zero(self, receipt):
        assert classify("polymarket", None, None, _meta(receipt)) == "unknown"
        assert classify("polymarket", 12, None, _meta(receipt)) == "traded"

    @pytest.mark.parametrize("market_metadata", ["{}", 5, ["volume_evidence"], {"volume_evidence": "x"}])
    def test_a_non_mapping_metadata_is_not_evidence(self, market_metadata):
        assert classify("polymarket", None, None, market_metadata) == "unknown"

    @pytest.mark.parametrize("source", EXCLUDED_SOURCES)
    def test_excluded_sources_stay_not_applicable_even_with_a_receipt(self, source):
        _, receipt = _forward(0.25)
        assert classify(source, None, None, _meta(receipt)) == "not_applicable"

    def test_a_receipt_on_a_non_polymarket_row_is_ignored(self):
        _, receipt = _forward(0.25)
        assert classify("kalshi", None, None, _meta(receipt)) == "unknown"
        assert classify("kalshi", 0, None, _meta(receipt)) == "untraded"
        assert classify("kalshi", None, 9, _meta(receipt)) == "traded_open_interest"

    def test_open_interest_stays_the_weaker_class_when_no_receipt(self):
        assert classify("polymarket", None, 7, None) == "traded_open_interest"


class TestTheReceiptCohortFigures:
    def test_a_confirmed_zero_only_cohort_reads_zero_percent_with_its_n(self):
        _, receipt = _forward(0)
        rows = [classify("polymarket", 0, None, _meta(receipt)) for _ in range(6)]
        counts = empty_counts()
        for klass in rows:
            counts[klass] += 1
        summary = summarise(counts)
        assert summary["traded_share_of_evidenced_pct"] == 0.0
        assert summary["evidenced_n"] == 6

    def test_an_unfetched_only_cohort_reads_none_never_zero(self):
        counts = empty_counts()
        for _ in range(6):
            counts[classify("polymarket", None, None, None)] += 1
        summary = summarise(counts)
        assert summary["traded_share_of_evidenced_pct"] is None
        assert summary["evidenced_n"] == 0


class TestTheReceiptSqlRendering:
    def test_without_metadata_the_case_is_byte_identical_to_the_scalar_rule(self):
        # Backwards compatibility, pinned: the default render must not grow JSONB
        # (the SQLite oracle above executes it, and SQLite has no jsonb_typeof).
        default = trade_evidence_sql()
        assert "jsonb" not in default and "volume_evidence" not in default
        assert default == (
            "(CASE WHEN fm.source IN ('odds_api', 'datagolf') THEN 'not_applicable'"
            " WHEN fo.volume > 0 THEN 'traded' WHEN fo.volume = 0 THEN 'untraded'"
            " WHEN fo.volume IS NULL AND fm.open_interest > 0 THEN 'traded_open_interest'"
            " ELSE 'unknown' END)"
        )

    def test_the_source_exclusion_still_comes_first_with_metadata(self):
        sql = trade_evidence_sql(metadata="fm.market_metadata")
        assert sql.index("'not_applicable'") < sql.index("volume_evidence")

    def test_the_census_reads_the_receipt_aware_rule(self):
        # FAILS ON REVERT of the census wiring: the census would render the
        # scalar-only CASE and keep publishing receipt-backed rows as unknown.
        assert trade_evidence_sql(metadata="fm.market_metadata") in cohorts_sql()
