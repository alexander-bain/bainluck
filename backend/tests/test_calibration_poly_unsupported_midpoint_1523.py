"""#1523 — a bid the book does not support is not evidence for a 0.50 price.

WHY THIS FILE EXISTS. ``POLY_PLACEHOLDER_EXCLUDE`` (#151/#997) kept a near-0.50
Polymarket leg whenever ANY snapshot showed ``yes_bid > 0``. Table tennis legs sit
at a 0.03 / 0.97 book for their whole captured life, never trade, and keep a
stored 0.50, so they were graded as coin flips. On the 2026-10-12 01:42Z publish
``table_tennis`` read ECE 7.1 over n=10,256 with the 0.5-0.6 bucket winning 41.5%.

WHAT IS GUARDED, AND HOW. Every test executes the module's REAL
``POLY_PLACEHOLDER_EXCLUDE`` against seeded tables, framed exactly as the
producer interpolates it (``{expr} AS is_poly_placeholder`` over a ``vm`` join).
The specimens are production rows transcribed from a saved read
(``tests/fixtures/calibration_1523_poly_unsupported_midpoint.json``), not
invented shapes. Each assertion is paired with the pre-#1523 rule, kept here as a
literal, so a specimen test cannot pass because the fixture was too weak to tell
the two rules apart. Mutation arms rebuild the shipped string with one clause
removed and require the guard to see the difference.

WHAT MUST SURVIVE, and the controls that hold it: a near-0.50 leg that TRADED,
even beside a wide book; a near-0.50 leg with a TIGHT two-sided book and no
trade; a leg whose bid was captured with NO ask (unknown, not refuted); pair
symmetry (the partner of an excluded leg leaves with it); the [0.45, 0.55]
band (a wide book outside it is not this rule's business); and Kalshi, which has
its own liquidity and writer-bar rungs.

WHAT THIS FILE DOES NOT CLAIM. How many rows move in each category, and whether
any category crosses the 3.0 bar either way. That is the measurement receipt
#1523 is waiting on, not a unit test's.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tasks import precompute_calibration as pc  # noqa: E402
from app.tasks.precompute_calibration import (  # noqa: E402
    POLY_PLACEHOLDER_EXCLUDE,
    POLY_PLACEHOLDER_PRE1523_EXCLUDE,
    POLY_PLACEHOLDER_RULE_TEXT,
)

FIXTURE = Path(__file__).parent / "fixtures" / "calibration_1523_poly_unsupported_midpoint.json"

#: The rule as it stood before #1523 (CAL-P992's pair-symmetric shape with the
#: #151 evidence test). A literal, so this arm keeps describing the old rule even
#: after the shipped constant moves.
PRE_1523_SQL = (
    "((vm.source = 'polymarket'\n"
    "     AND COALESCE(fo.calibration_probability, fo.opening_probability) >= 0.45\n"
    "     AND COALESCE(fo.calibration_probability, fo.opening_probability) <= 0.55\n"
    "     AND NOT EXISTS (\n"
    "        SELECT 1 FROM futures_odds_snapshots fos\n"
    "        WHERE fos.outcome_id = fo.id\n"
    "          AND (fos.yes_bid > 0 OR fos.last_price > 0)))"
    "\n     OR (vm.source = 'polymarket'\n"
    "     AND (SELECT COUNT(*) FROM futures_outcomes fo8\n"
    "          WHERE fo8.market_id = fo.market_id) = 2\n"
    "     AND EXISTS (\n"
    "        SELECT 1 FROM futures_outcomes fo9\n"
    "        WHERE fo9.market_id = fo.market_id AND fo9.id <> fo.id\n"
    "          AND COALESCE(fo9.calibration_probability,\n"
    "                       fo9.opening_probability) >= 0.45\n"
    "          AND COALESCE(fo9.calibration_probability,\n"
    "                       fo9.opening_probability) <= 0.55\n"
    "          AND NOT EXISTS (\n"
    "             SELECT 1 FROM futures_odds_snapshots fos9\n"
    "             WHERE fos9.outcome_id = fo9.id\n"
    "               AND (fos9.yes_bid > 0 OR fos9.last_price > 0))))"
    ")"
)

#: Clauses of the shipped leg/partner evidence test, verbatim, so each mutation
#: arm removes exactly one of them.
LEG_UNKNOWN_ASK = "fos.yes_ask IS NULL\n                        OR "
PARTNER_EVIDENCE = (
    "               AND (fos9.last_price > 0\n"
    "                    OR (fos9.yes_bid > 0 AND fos9.yes_bid <= 1\n"
    "                        AND (fos9.yes_ask IS NULL\n"
    "                             OR (fos9.yes_ask >= fos9.yes_bid AND fos9.yes_ask <= 1\n"
    "                                 AND fos9.yes_ask - fos9.yes_bid < 0.50)))))"
)

CREATE = """
    CREATE TABLE futures_outcomes (
        id INTEGER PRIMARY KEY,
        market_id INTEGER,
        name TEXT,
        calibration_probability REAL,
        opening_probability REAL
    );
    CREATE TABLE futures_odds_snapshots (
        id INTEGER PRIMARY KEY,
        outcome_id INTEGER,
        yes_bid REAL,
        yes_ask REAL,
        last_price REAL
    );
    CREATE TABLE vm (market_id INTEGER, source TEXT);
"""

PROBE = """
    SELECT fo.id, {expr} AS is_poly_placeholder
    FROM futures_outcomes fo
    JOIN vm ON vm.market_id = fo.market_id
    ORDER BY fo.id
"""

# Synthetic controls. Ids are far from the production specimens so a reader can
# tell at a glance which rows are real.
TIGHT_BOOK = 900001  # bid 0.47 / ask 0.53, no trade: a real coin flip
TIGHT_BOOK_PARTNER = 900002
UNKNOWN_ASK = 900011  # bid 0.48, no ask recorded, no trade
UNKNOWN_ASK_PARTNER = 900012
ZERO_ASK = 900021  # bid 0.48, ask 0: a crossed book, not a missing one
ZERO_ASK_PARTNER = 900022
CROSSED = 900101  # bid 0.55 / ask 0.45: "spread" -0.10, no trade
CROSSED_PARTNER = 900102
ASK_ABOVE_ONE = 900111  # bid 0.80 / ask 1.20, no trade
ASK_ABOVE_ONE_PARTNER = 900112
BID_ABOVE_ONE = 900121  # bid 1.50, no ask, no trade
BID_ABOVE_ONE_PARTNER = 900122
AT_BOUNDARY = 900031  # bid 0.25 / ask 0.75: spread exactly 0.50, no trade
AT_BOUNDARY_PARTNER = 900032
INSIDE_BOUNDARY = 900041  # bid 0.255 / ask 0.745: spread 0.49, no trade
INSIDE_BOUNDARY_PARTNER = 900042
MIXED_HISTORY = 900051  # one wide snapshot, then one tight one
MIXED_HISTORY_PARTNER = 900052
WIDE_LEG = 900061  # wide, never traded
TRADED_PARTNER = 900062  # traded at 0.50: leaves with its half-book partner
OUT_OF_BAND = 900071  # cp 0.30 on a 0.03 / 0.97 book
OUT_OF_BAND_PARTNER = 900072  # cp 0.70, same book from the other side
KALSHI_WIDE = 900081  # Kalshi leg on a 0.03 / 0.97 book near 0.50
KALSHI_WIDE_PARTNER = 900082
NO_SNAPSHOTS = 900091  # no snapshot row at all
NO_SNAPSHOTS_PARTNER = 900092


def _insert_outcome(conn, outcome_id, market_id, cp, snapshots):
    conn.execute(
        text(
            "INSERT INTO futures_outcomes "
            "(id, market_id, name, calibration_probability, opening_probability) "
            "VALUES (:i, :m, :n, :p, :p)"
        ),
        {"i": outcome_id, "m": market_id, "n": str(outcome_id), "p": cp},
    )
    for bid, ask, last in snapshots:
        conn.execute(
            text(
                "INSERT INTO futures_odds_snapshots "
                "(outcome_id, yes_bid, yes_ask, last_price) VALUES (:i, :b, :a, :l)"
            ),
            {"i": outcome_id, "b": bid, "a": ask, "l": last},
        )


def _insert_market(conn, market_id, source):
    conn.execute(
        text("INSERT INTO vm (market_id, source) VALUES (:m, :s)"),
        {"m": market_id, "s": source},
    )


def _specimens():
    return json.loads(FIXTURE.read_text())


@pytest.fixture(scope="module")
def seeded():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        for stmt in CREATE.split(";"):
            if stmt.strip():
                conn.execute(text(stmt))

        for market in _specimens()["markets"]:
            _insert_market(conn, market["market_id"], "polymarket")
            for o in market["outcomes"]:
                _insert_outcome(conn, o["id"], market["market_id"], o["cp"], o["snapshots"])

        synthetic = [
            # (market_id, source, [(outcome_id, cp, snapshots), ...])
            (800001, "polymarket", [
                (TIGHT_BOOK, 0.50, [(0.47, 0.53, None)]),
                (TIGHT_BOOK_PARTNER, 0.50, [(0.47, 0.53, None)]),
            ]),
            (800002, "polymarket", [
                (UNKNOWN_ASK, 0.50, [(0.48, None, None)]),
                (UNKNOWN_ASK_PARTNER, 0.50, [(0.48, None, None)]),
            ]),
            (800003, "polymarket", [
                (ZERO_ASK, 0.50, [(0.48, 0.0, None)]),
                (ZERO_ASK_PARTNER, 0.50, [(0.48, 0.0, None)]),
            ]),
            (800004, "polymarket", [
                (AT_BOUNDARY, 0.50, [(0.25, 0.75, None)]),
                (AT_BOUNDARY_PARTNER, 0.50, [(0.25, 0.75, None)]),
            ]),
            (800005, "polymarket", [
                (INSIDE_BOUNDARY, 0.50, [(0.255, 0.745, None)]),
                (INSIDE_BOUNDARY_PARTNER, 0.50, [(0.255, 0.745, None)]),
            ]),
            (800006, "polymarket", [
                (MIXED_HISTORY, 0.50, [(0.03, 0.97, None), (0.46, 0.54, None)]),
                (MIXED_HISTORY_PARTNER, 0.50, [(0.03, 0.97, None), (0.46, 0.54, None)]),
            ]),
            (800007, "polymarket", [
                (WIDE_LEG, 0.50, [(0.03, 0.97, None)]),
                (TRADED_PARTNER, 0.50, [(0.03, 0.97, 0.50)]),
            ]),
            (800008, "polymarket", [
                (OUT_OF_BAND, 0.30, [(0.03, 0.97, None)]),
                (OUT_OF_BAND_PARTNER, 0.70, [(0.03, 0.97, None)]),
            ]),
            (800009, "kalshi", [
                (KALSHI_WIDE, 0.50, [(0.03, 0.97, None)]),
                (KALSHI_WIDE_PARTNER, 0.50, [(0.03, 0.97, None)]),
            ]),
            (800010, "polymarket", [
                (NO_SNAPSHOTS, 0.50, []),
                (NO_SNAPSHOTS_PARTNER, 0.50, []),
            ]),
            (800011, "polymarket", [
                (CROSSED, 0.50, [(0.55, 0.45, None)]),
                (CROSSED_PARTNER, 0.50, [(0.55, 0.45, None)]),
            ]),
            (800012, "polymarket", [
                (ASK_ABOVE_ONE, 0.50, [(0.80, 1.20, None)]),
                (ASK_ABOVE_ONE_PARTNER, 0.50, [(0.80, 1.20, None)]),
            ]),
            (800013, "polymarket", [
                (BID_ABOVE_ONE, 0.50, [(1.50, None, None)]),
                (BID_ABOVE_ONE_PARTNER, 0.50, [(1.50, None, None)]),
            ]),
        ]
        for market_id, source, legs in synthetic:
            _insert_market(conn, market_id, source)
            for outcome_id, cp, snaps in legs:
                _insert_outcome(conn, outcome_id, market_id, cp, snaps)
    return engine


def _flags(engine, expr) -> dict[int, bool]:
    with engine.begin() as conn:
        rows = conn.execute(text(PROBE.format(expr=expr))).all()
    return {r[0]: bool(r[1]) for r in rows}


@pytest.fixture(scope="module")
def shipped(seeded):
    return _flags(seeded, POLY_PLACEHOLDER_EXCLUDE)


@pytest.fixture(scope="module")
def before(seeded):
    return _flags(seeded, PRE_1523_SQL)


class TestTheSpecimensLeave:
    """The production rows #1523 was traced on."""

    def test_a_far_bid_for_life_no_longer_vouches_for_0505(self, shipped, before):
        # 217613510: 11 snapshots, bid 0.03-0.06, ask 0.94-0.97, never traded.
        assert before[217613510] is False, "fixture too weak: the old rule kept it"
        assert shipped[217613510] is True

    def test_the_binary_whose_both_legs_sat_at_a_wide_book_leaves_whole(self, shipped, before):
        # 229038158/159: bid 0.02-0.03, ask 0.97-0.98, no trade, both stored 0.500.
        assert (before[229038158], before[229038159]) == (False, False)
        assert (shipped[229038158], shipped[229038159]) == (True, True)

    def test_the_field_bundle_loses_its_last_published_leg(self, shipped, before):
        # 58635840 is a 5-leg `field` bundle that resolved with 2 winners. Its
        # four siblings never showed a bid and were already out; the one leg the
        # old rule kept was the wide-book one. So the book rule alone removes the
        # whole bundle: no bundle-cell exclusion is needed for THIS market.
        legs = (217613510, 217613511, 217613512, 217613513, 217613514)
        assert [before[i] for i in legs] == [False, True, True, True, True]
        assert all(shipped[i] for i in legs)


class TestSupportedForecastsSurvive:
    def test_a_trade_beside_a_wide_book_keeps_the_leg(self, shipped, before):
        # 228977428 (production): bid 0.08, ask 0.69, last_price 0.50.
        assert shipped[228977428] is False and before[228977428] is False

    def test_a_tight_two_sided_book_with_no_trade_keeps_the_pair(self, shipped):
        assert shipped[TIGHT_BOOK] is False and shipped[TIGHT_BOOK_PARTNER] is False

    def test_any_supporting_snapshot_is_enough(self, shipped):
        # One 0.03/0.97 snapshot does not cancel a later 0.46/0.54 one.
        assert shipped[MIXED_HISTORY] is False and shipped[MIXED_HISTORY_PARTNER] is False

    def test_spread_just_under_the_bar_is_supported(self, shipped):
        assert shipped[INSIDE_BOUNDARY] is False


class TestMissingEvidenceStaysUnknown:
    """A snapshot that never recorded an ask has not refuted its bid."""

    def test_a_bid_with_no_recorded_ask_is_kept_as_before(self, shipped, before):
        assert before[UNKNOWN_ASK] is False
        assert shipped[UNKNOWN_ASK] is False and shipped[UNKNOWN_ASK_PARTNER] is False



class TestAnInvalidBookIsNotEvidence:
    """Root's quote-validity constraint: a small "spread" on a crossed or
    out-of-range book supports nothing. Nothing upstream enforces these facts."""

    def test_a_crossed_book_does_not_support(self, shipped, before):
        assert before[CROSSED] is False
        assert shipped[CROSSED] is True and shipped[CROSSED_PARTNER] is True

    def test_a_zero_ask_is_crossed_not_missing(self, shipped, before):
        assert before[ZERO_ASK] is False
        assert shipped[ZERO_ASK] is True and shipped[ZERO_ASK_PARTNER] is True

    def test_an_ask_above_one_does_not_support(self, shipped, before):
        assert before[ASK_ABOVE_ONE] is False
        assert shipped[ASK_ABOVE_ONE] is True

    def test_a_bid_above_one_does_not_support_even_without_an_ask(self, shipped, before):
        assert before[BID_ABOVE_ONE] is False
        assert shipped[BID_ABOVE_ONE] is True

    def test_no_snapshot_at_all_is_handled_exactly_as_before(self, shipped, before):
        # Excluded before #1523 and after; #1523 changes nothing about it.
        assert before[NO_SNAPSHOTS] is True and shipped[NO_SNAPSHOTS] is True
        assert before[NO_SNAPSHOTS_PARTNER] is True and shipped[NO_SNAPSHOTS_PARTNER] is True


class TestBoundaryAndScope:
    def test_a_spread_of_exactly_050_does_not_support(self, shipped, before):
        # The Kalshi writer's own bar is `< 0.50`; 0.50 itself is refused there.
        assert before[AT_BOUNDARY] is False
        assert shipped[AT_BOUNDARY] is True and shipped[AT_BOUNDARY_PARTNER] is True

    def test_the_band_is_unchanged(self, shipped):
        assert shipped[OUT_OF_BAND] is False and shipped[OUT_OF_BAND_PARTNER] is False

    def test_kalshi_is_not_this_rules_business(self, shipped):
        assert shipped[KALSHI_WIDE] is False and shipped[KALSHI_WIDE_PARTNER] is False


class TestPairSymmetrySurvives:
    def test_the_partner_of_a_newly_excluded_leg_leaves_with_it(self, shipped, before):
        # The partner traded; under CAL-P992 half a book is still not a forecast.
        assert (before[WIDE_LEG], before[TRADED_PARTNER]) == (False, False)
        assert (shipped[WIDE_LEG], shipped[TRADED_PARTNER]) == (True, True)


class TestTheOnlyRowsThatMoveAreBidBearing:
    def test_every_row_the_new_rule_adds_had_a_bid_and_no_supporting_snapshot(
        self, shipped, before
    ):
        """New ⊇ old, and the difference is exactly the wide-book cohort.

        No row the old rule excluded is readmitted (the change only narrows), and
        every newly excluded row is one of the named wide-book cases or the
        partner of one.
        """
        readmitted = {i for i, v in before.items() if v and not shipped[i]}
        assert readmitted == set()
        newly = {i for i, v in shipped.items() if v and not before[i]}
        assert newly == {
            217613510,
            229038158,
            229038159,
            AT_BOUNDARY,
            AT_BOUNDARY_PARTNER,
            WIDE_LEG,
            TRADED_PARTNER,
            ZERO_ASK,
            ZERO_ASK_PARTNER,
            CROSSED,
            CROSSED_PARTNER,
            ASK_ABOVE_ONE,
            ASK_ABOVE_ONE_PARTNER,
            BID_ABOVE_ONE,
            BID_ABOVE_ONE_PARTNER,
        }


class TestTheDisclosedCountIsTheDifference:
    """``poly_unsupported_bid_excluded`` counts what #1523 adds, nothing else."""

    def test_the_census_twin_is_the_pre_1523_rule_verbatim(self):
        # If the twin drifted from the old rule, the disclosed narrowing would
        # measure something other than the change the succession declares.
        assert POLY_PLACEHOLDER_PRE1523_EXCLUDE == PRE_1523_SQL

    def test_the_delta_flag_selects_exactly_the_newly_excluded_rows(self, seeded, shipped, before):
        expr = f"(({POLY_PLACEHOLDER_EXCLUDE}) AND NOT ({POLY_PLACEHOLDER_PRE1523_EXCLUDE}))"
        delta = {i for i, v in _flags(seeded, expr).items() if v}
        assert delta == {i for i, v in shipped.items() if v and not before[i]}
        assert delta, "fixture moved nothing; the count would be vacuously zero"

    def test_the_producer_flags_rows_with_the_twin(self):
        sql = pc._calibration_population_ctes()
        assert "AS is_poly_placeholder_pre1523" in sql
        assert POLY_PLACEHOLDER_PRE1523_EXCLUDE in sql
        main = pc._main_futures_sql(frozen=False)
        assert "MAX(ubs.poly_unsupported_bid_excluded) AS poly_unsupported_bid_excluded" in main

    def test_the_count_is_a_declared_staged_census_column(self):
        from app.utils.calibration_staged_futures import (
            DEFAULT_CENSUS_COLUMNS,
            DISTINCT_CENSUS_COLUMNS,
        )

        assert "poly_unsupported_bid_excluded" in DEFAULT_CENSUS_COLUMNS
        # COUNT(*), not COUNT(DISTINCT ...): sums across units as-is.
        assert "poly_unsupported_bid_excluded" not in DISTINCT_CENSUS_COLUMNS


class TestTheIdentityMovesWithTheRule:
    def test_the_population_predicate_hashes_the_rule_by_value(self, monkeypatch):
        base = pc.population_predicate_fingerprint()
        monkeypatch.setattr(pc, "POLY_PLACEHOLDER_EXCLUDE", PRE_1523_SQL)
        assert pc.population_predicate_fingerprint() != base, (
            "the old and new rules would publish under one predicate digest"
        )

    def test_the_census_twin_does_not_move_the_population_predicate(self, monkeypatch):
        base = pc.population_predicate_fingerprint()
        monkeypatch.setattr(pc, "POLY_PLACEHOLDER_PRE1523_EXCLUDE", "(false)")
        assert pc.population_predicate_fingerprint() == base

    def test_the_main_input_hashes_both_by_value(self, monkeypatch):
        base = pc._main_input_fingerprint()
        monkeypatch.setattr(pc, "POLY_PLACEHOLDER_EXCLUDE", PRE_1523_SQL)
        moved_rule = pc._main_input_fingerprint()
        monkeypatch.undo()
        monkeypatch.setattr(pc, "POLY_PLACEHOLDER_PRE1523_EXCLUDE", "(false)")
        moved_twin = pc._main_input_fingerprint()
        assert base != moved_rule and base != moved_twin


class TestMutationsAreVisible:
    """Each clause of the new evidence test is load-bearing on these fixtures."""

    def test_dropping_the_unknown_ask_carve_out_would_remove_unrefuted_rows(self, seeded):
        assert LEG_UNKNOWN_ASK in POLY_PLACEHOLDER_EXCLUDE
        mutant = POLY_PLACEHOLDER_EXCLUDE.replace(LEG_UNKNOWN_ASK, "")
        flags = _flags(seeded, mutant)
        assert flags[UNKNOWN_ASK] is True, "the guard cannot see the carve-out"

    @pytest.mark.parametrize(
        "clause, row",
        [
            ("{a}.yes_ask >= {a}.yes_bid AND ", CROSSED),
            (" AND {a}.yes_ask <= 1", ASK_ABOVE_ONE),
            (" AND {a}.yes_bid <= 1", BID_ABOVE_ONE),
        ],
        ids=["ordered", "ask_in_range", "bid_in_range"],
    )
    def test_each_validity_clause_is_load_bearing(self, seeded, clause, row):
        # Removed from the leg AND the partner clause together: pair symmetry
        # would otherwise re-exclude the row through its untouched partner.
        mutant = POLY_PLACEHOLDER_EXCLUDE
        for alias in ("fos", "fos9"):
            text_ = clause.format(a=alias)
            assert mutant.count(text_) == 1, text_
            mutant = mutant.replace(text_, "")
        assert _flags(seeded, mutant)[row] is False, (
            f"the guard cannot see the {clause!r} clause"
        )

    def test_dropping_the_partner_evidence_breaks_symmetry_of_evidence(self, seeded):
        # With the partner clause still on the OLD evidence test, the traded
        # partner of a wide leg would publish alone.
        assert POLY_PLACEHOLDER_EXCLUDE.count(PARTNER_EVIDENCE) == 1
        mutant = POLY_PLACEHOLDER_EXCLUDE.replace(
            PARTNER_EVIDENCE,
            "               AND (fos9.yes_bid > 0 OR fos9.last_price > 0))",
        )
        assert mutant != POLY_PLACEHOLDER_EXCLUDE, "partner clause text moved"
        flags = _flags(seeded, mutant)
        assert flags[WIDE_LEG] is True
        assert flags[TRADED_PARTNER] is False, (
            "the guard cannot tell whether the partner clause uses the new evidence"
        )

    def test_loosening_the_bar_to_inclusive_would_keep_the_boundary_row(self, seeded):
        assert POLY_PLACEHOLDER_EXCLUDE.count("< 0.50") == 2
        mutant = POLY_PLACEHOLDER_EXCLUDE.replace("< 0.50", "<= 0.50")
        assert _flags(seeded, mutant)[AT_BOUNDARY] is False

    def test_dropping_the_trade_clause_would_remove_a_traded_leg(self, seeded):
        mutant = POLY_PLACEHOLDER_EXCLUDE.replace(
            "fos.last_price > 0\n               OR ", ""
        )
        assert mutant != POLY_PLACEHOLDER_EXCLUDE
        assert _flags(seeded, mutant)[228977428] is True


class TestDisclosure:
    def test_the_rule_text_says_what_the_evidence_test_is(self):
        lowered = POLY_PLACEHOLDER_RULE_TEXT.lower()
        assert "0.50 or more above the bid" in lowered
        assert "at or above the bid, at most 1" in lowered
        assert "no recorded ask still counts" in lowered
        # It says what our snapshots show, never that the market never traded.
        assert "no captured snapshot shows a trade" in lowered
        assert "never traded" not in lowered


# ---------------------------------------------------------------------------
# The publish gate: a table-tennis collapse is excused ONLY up to what this rule
# says it removed there (Root's 1523 disclosure-loss probe: one declared row
# must never excuse 5,132 more).
# ---------------------------------------------------------------------------

from datetime import datetime, timezone  # noqa: E402

from app.utils.calibration_publish_gate import (  # noqa: E402
    PREDICATE_FIELD,
    census,
    evaluate_publish,
)

TT_PUBLISHED = 10_256  # served 2026-10-12 01:42Z, all Polymarket
TT_REMOVED = 5_133  # the size of Root's probe; any count exercises the bound
OTHER = {"soccer": {"polymarket": 206_925, "kalshi": 40_000}}
BASE_POP = sum(sum(c.values()) for c in OTHER.values()) + TT_PUBLISHED


def _payload(*, tt_cells, predicate, block=None):
    cells = dict(OTHER, table_tennis=tt_cells)
    buckets = []
    for category, by_source in sorted(cells.items()):
        for source, n in sorted(by_source.items()):
            for idx, (part, moved) in enumerate(((n // 2, True), (n - n // 2, False))):
                buckets.append({
                    "bucket_idx": 4 + idx, "source": source, "category": category,
                    "n": part, "winners": part // 2, "sum_prob": part * 0.5,
                    "price_moved": moved,
                })
    total = sum(sum(c.values()) for c in cells.values())
    payload = {
        "buckets": buckets,
        "by_category": [
            {"category": name, "outcomes": sum(c.values()), "ece": 1.5}
            for name, c in cells.items()
        ],
        "by_source": [{"source": "polymarket", "outcomes": total}],
        "total_outcomes": total,
        "total_markets": total - 100,
        "total_winners": total // 3,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "liquidity_filter": {"applies_to": "kalshi"},
        "mex_normalization": {"applied": True},
        "truth_evidence": {"rungs": []},
        "population_version": "q271",
        PREDICATE_FIELD: predicate,
    }
    if block is not None:
        payload["poly_unsupported_bid_filter"] = block
    return payload


def _block(excluded=TT_REMOVED, by_cell=None):
    return {
        "applies_to": "polymarket",
        "rule": "r",
        "excluded": excluded,
        "excluded_by_cell": (
            {"polymarket/table_tennis": excluded} if by_cell is None else by_cell
        ),
    }


def _gate(*, lost_extra=0, block=None):
    prev = _payload(tt_cells={"polymarket": TT_PUBLISHED}, predicate="a" * 32)
    cand = _payload(
        tt_cells={"polymarket": TT_PUBLISHED - TT_REMOVED - lost_extra},
        predicate="b" * 32,
        block=_block() if block is None else block,
    )
    return evaluate_publish(cand, prev)


def _record(verdict, code, *, rejections=False):
    items = verdict.rejections if rejections else verdict.observations
    return {r.get("category"): r for r in items if r.get("code") == code}


class TestTheGateBoundsTheDisclosure:
    def test_the_rules_own_removal_publishes_with_its_arithmetic(self):
        verdict = _gate()
        assert verdict.ok, verdict.summary()
        obs = _record(verdict, "category_collapse_disclosed_exclusion")["table_tennis"]
        assert obs["magnitude_uncheckable"] is False
        acct = obs["score_unit_accounting"]
        assert (acct["explained"], acct["unexplained"]) == (TT_REMOVED, 0)
        assert acct["sources"] == [f"polymarket {TT_REMOVED:,}"]

    def test_valid_forecasts_lost_beside_the_rule_refuse(self):
        # 2,000 more of the same cell vanished: 39% of what the rule left.
        verdict = _gate(lost_extra=2_000)
        assert not verdict.ok
        acct = _record(verdict, "category_collapse", rejections=True)[
            "table_tennis"]["score_unit_accounting"]
        assert (acct["explained"], acct["unexplained"]) == (TT_REMOVED, 2_000)

    def test_one_declared_row_cannot_excuse_the_rest(self):
        """Root's probe, against this rung: a count of 1 explains 1."""
        verdict = _gate(block=_block(excluded=1))
        assert not verdict.ok
        acct = _record(verdict, "category_collapse", rejections=True)[
            "table_tennis"]["score_unit_accounting"]
        assert (acct["explained"], acct["unexplained"]) == (1, TT_REMOVED - 1)

    def test_the_twenty_percent_tolerance_holds_on_what_the_rule_left(self):
        retained = TT_PUBLISHED - TT_REMOVED  # 5,123; 20% is 1,024.6
        assert _gate(lost_extra=1_024).ok
        assert not _gate(lost_extra=1_025).ok
        assert retained == 5_123

    @pytest.mark.parametrize(
        "block",
        [
            _block(excluded=TT_REMOVED + 1,
                   by_cell={"polymarket/table_tennis": TT_REMOVED}),  # cells do not sum
            _block(by_cell={"table_tennis": TT_REMOVED}),  # no source in the key
            _block(by_cell={"polymarket/table_tennis": -5}),  # not a count
            _block(by_cell={"polymarket/soccer": TT_REMOVED}),  # names another cell
        ],
        ids=["not_summing", "sourceless_key", "negative", "other_cell"],
    )
    def test_fails_closed_when_the_per_cell_count_is_unusable(self, block):
        verdict = _gate(block=block)
        assert not verdict.ok
        assert "table_tennis" in _record(verdict, "category_collapse", rejections=True)

    def test_a_missing_per_cell_map_discloses_nothing_and_refuses(self):
        block = _block()
        block.pop("excluded_by_cell")
        verdict = _gate(block=block)
        assert not verdict.ok
        assert "table_tennis" in _record(verdict, "category_collapse", rejections=True)

    def test_the_census_reads_the_delta_section(self):
        cand = _payload(tt_cells={"polymarket": 1}, predicate="b" * 32, block=_block())
        got = census(cand)["poly_unsupported_bid"]
        assert got["excluded"] == TT_REMOVED
        assert got["by_cell"] == {"table_tennis": {"polymarket": TT_REMOVED}}


def _bundle(n=1):
    """The unbounded rung newly naming the same cell, as Root's replay did.

    Its own per-cell number is a candidate-side total (overlaps other rungs and
    the baseline's exclusions); the gate must not add it to the bounded count.
    """
    return {"applies_to": "polymarket", "excluded": n,
            "excluded_by_cell": {"polymarket/table_tennis": n}}


def _mixed_gate(*, lost_extra=0, block=None, bundle_n=1):
    prev = _payload(tt_cells={"polymarket": TT_PUBLISHED}, predicate="a" * 32)
    cand = _payload(
        tt_cells={"polymarket": TT_PUBLISHED - TT_REMOVED - lost_extra},
        predicate="b" * 32,
        block=_block() if block is None else block,
    )
    cand["nonexclusive_bundle_filter"] = _bundle(bundle_n)
    return evaluate_publish(cand, prev)


class TestAnUnboundedLabelBesideTheRuleExcusesNothing:
    """Root's 50e8 replay: 1 declared bid row + a bundle label naming the same
    category read PASS / magnitude_uncheckable over 5,133 lost. A bounded rung in
    the category means the label waiver is never reached; only bounded counts
    explain, and the unbounded rung explains none of the drop."""

    def test_the_exact_count_still_publishes_and_names_the_uncounted_rung(self):
        verdict = _mixed_gate()
        assert verdict.ok, verdict.summary()
        obs = _record(verdict, "category_collapse_disclosed_exclusion")["table_tennis"]
        assert obs["magnitude_uncheckable"] is False
        acct = obs["score_unit_accounting"]
        assert (acct["explained"], acct["unexplained"]) == (TT_REMOVED, 0)
        assert acct["unbounded_disclosures"] == ["nonexclusive_bundle_filter"]
        assert "explains none of the drop" in obs["detail"]

    def test_one_declared_row_plus_a_label_refuses(self):
        verdict = _mixed_gate(block=_block(excluded=1))
        assert not verdict.ok
        rej = _record(verdict, "category_collapse", rejections=True)["table_tennis"]
        acct = rej["score_unit_accounting"]
        assert (acct["explained"], acct["unexplained"]) == (1, TT_REMOVED - 1)
        assert "nonexclusive_bundle_filter also names this category" in rej["detail"]
        assert not _record(verdict, "category_collapse_disclosed_exclusion")

    def test_extra_same_category_loss_plus_a_label_refuses(self):
        verdict = _mixed_gate(lost_extra=2_000)
        assert not verdict.ok
        acct = _record(verdict, "category_collapse", rejections=True)[
            "table_tennis"]["score_unit_accounting"]
        assert (acct["explained"], acct["unexplained"]) == (TT_REMOVED, 2_000)

    def test_the_labels_own_count_is_never_added(self):
        # The bundle states the whole loss; a count that cannot be deduped
        # against the bid set or the baseline buys nothing.
        verdict = _mixed_gate(block=_block(excluded=1), bundle_n=TT_REMOVED)
        assert not verdict.ok
        acct = _record(verdict, "category_collapse", rejections=True)[
            "table_tennis"]["score_unit_accounting"]
        assert acct["explained"] == 1

    @pytest.mark.parametrize("listed", [False, True], ids=["no_cells", "cell_listed"])
    def test_missing_counts_plus_a_label_refuse(self, listed):
        # cell_listed is Root's replay shape; no_cells names no cell at all, so
        # the rung is absent from the disclosure and must still refuse.
        block = _block()
        block.pop("excluded_by_cell")
        if listed:
            block["excluded_cells"] = [["polymarket", "table_tennis"]]
        verdict = _mixed_gate(block=block)
        assert not verdict.ok
        assert "table_tennis" in _record(verdict, "category_collapse", rejections=True)

    def test_the_tolerance_is_unchanged_on_the_mixed_path(self):
        assert _mixed_gate(lost_extra=1_024).ok
        assert not _mixed_gate(lost_extra=1_025).ok

    def test_a_label_alone_keeps_its_inherited_excuse(self):
        """Pure legacy, outside this path: no bounded rung names the category."""
        prev = _payload(tt_cells={"polymarket": TT_PUBLISHED}, predicate="a" * 32)
        cand = _payload(tt_cells={"polymarket": TT_PUBLISHED - TT_REMOVED},
                        predicate="b" * 32)
        cand["nonexclusive_bundle_filter"] = _bundle()
        verdict = evaluate_publish(cand, prev)
        assert verdict.ok, verdict.summary()
        obs = _record(verdict, "category_collapse_disclosed_exclusion")["table_tennis"]
        assert obs["magnitude_uncheckable"] is True
        assert "score_unit_accounting" not in obs


# ---------------------------------------------------------------------------
# The producer half of that count.
# ---------------------------------------------------------------------------


class TestTheProducerCountsWhatWouldHavePublished:
    def test_deduped_is_split_and_materialized_once(self):
        sql = pc._calibration_population_ctes()
        assert "deduped_eligible AS MATERIALIZED (" in sql
        assert "deduped AS NOT MATERIALIZED (" in sql
        eligible = sql.split("deduped_eligible AS MATERIALIZED (", 1)[1].split(
            "deduped AS NOT MATERIALIZED (", 1)[0]
        # The placeholder rule is the ONE filter moved out of the eligible set.
        assert "is_poly_placeholder" not in eligible
        assert "WHERE NOT is_poly_placeholder" in sql.split(
            "deduped AS NOT MATERIALIZED (", 1)[1]

    def test_the_count_is_taken_from_the_eligible_set_in_both_plans(self):
        for frozen in (False, True):
            main = pc._main_futures_sql(frozen=frozen)
            summary = main.split("poly_unsupported_bid_summary AS (", 1)[1].split(
                "\n            )", 1)[0]
            assert summary.count("FROM deduped_eligible") == 2
            assert summary.count(
                "is_poly_placeholder\n                        AND NOT is_poly_placeholder_pre1523"
            ) == 1
            assert "CROSS JOIN poly_unsupported_bid_summary ubs" in main
            assert "MAX(ubs.poly_unsupported_bid_by_cell) AS poly_unsupported_bid_by_cell" in main
            assert "'{}') AS poly_unsupported_bid_by_cell" in main

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ('{"polymarket/table_tennis": 3}', {"polymarket/table_tennis": 3}),
            ("{}", {}),
            (None, None),
            ("not json", None),
            ('{"polymarket/x": -1}', None),
            ('{"polymarket/x": 1.5}', None),
            ('["polymarket/x"]', None),
        ],
    )
    def test_the_payload_reads_the_map_or_states_unknown(self, raw, expected):
        assert pc._parse_count_map(raw) == expected


class TestTheStagedMergeSumsTheMapPerKey:
    def _rows(self, by_cell, excluded):
        from types import SimpleNamespace

        from app.utils.calibration_staged_futures import DEFAULT_CENSUS_COLUMNS

        base = {name: 0 for name in DEFAULT_CENSUS_COLUMNS}
        base.update(poly_unsupported_bid_by_cell=by_cell,
                    poly_unsupported_bid_excluded=excluded)
        return [SimpleNamespace(
            bucket_idx=5, source="polymarket", category="table_tennis",
            price_moved=False, is_nonexclusive_bundle=False,
            n=1, winners=0, sum_prob=0.5, sum_sq_err=0.25, avg_prob=0.5, **base)]

    def test_units_sum_per_key(self):
        from app.utils.calibration_staged_futures import merge_futures_rows

        merged = merge_futures_rows([
            self._rows('{"polymarket/table_tennis":2}', 2),
            self._rows('{"polymarket/table_tennis":3,"polymarket/chess":1}', 4),
            self._rows("{}", 0),
        ])
        row = merged[0]
        assert json.loads(row.poly_unsupported_bid_by_cell) == {
            "polymarket/chess": 1, "polymarket/table_tennis": 5}
        assert row.poly_unsupported_bid_excluded == 6

    def test_an_unreadable_unit_makes_the_map_unknown_not_partial(self):
        from app.utils.calibration_staged_futures import merge_futures_rows

        merged = merge_futures_rows([
            self._rows('{"polymarket/table_tennis":2}', 2),
            self._rows("garbage", 1),
        ])
        assert merged[0].poly_unsupported_bid_by_cell is None

    def test_the_map_banks_as_a_string(self):
        from app.utils.calibration_staged_futures import (
            decode_unit_rows,
            encode_unit_rows,
        )

        rows = self._rows('{"polymarket/table_tennis":2}', 2)
        back = decode_unit_rows(json.loads(json.dumps(encode_unit_rows(rows))))
        assert back[0].poly_unsupported_bid_by_cell == '{"polymarket/table_tennis":2}'
