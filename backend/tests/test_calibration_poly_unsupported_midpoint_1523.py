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

#: The leg clause's "a missing ask is unknown" carve-out, as it appears in the
#: shipped string. The mutation arm removes exactly this text.
LEG_UNKNOWN_ASK = "fos.yes_ask IS NULL OR fos.yes_ask <= 0\n                        OR "
PARTNER_UNKNOWN_ASK = (
    "fos9.yes_ask IS NULL OR fos9.yes_ask <= 0\n                             OR "
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
ZERO_ASK = 900021  # bid 0.48, ask 0 (not a real ask), no trade
ZERO_ASK_PARTNER = 900022
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

    def test_a_zero_ask_is_not_a_book(self, shipped, before):
        assert before[ZERO_ASK] is False
        assert shipped[ZERO_ASK] is False

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

    def test_the_producer_counts_it_from_both_flags(self):
        sql = pc._calibration_population_ctes()
        assert "AS is_poly_placeholder_pre1523" in sql
        assert POLY_PLACEHOLDER_PRE1523_EXCLUDE in sql
        main = pc._main_futures_sql(frozen=False)
        assert (
            "is_poly_placeholder AND NOT is_poly_placeholder_pre1523) "
            "AS poly_unsupported_bid_excluded" in main
        )
        assert "MAX(ls.poly_unsupported_bid_excluded) AS poly_unsupported_bid_excluded" in main

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

    def test_dropping_the_partner_carve_out_breaks_symmetry_of_evidence(self, seeded):
        # With the partner clause still on the OLD evidence test, the traded
        # partner of a wide leg would publish alone.
        assert PARTNER_UNKNOWN_ASK in POLY_PLACEHOLDER_EXCLUDE
        mutant = POLY_PLACEHOLDER_EXCLUDE.replace(
            "               AND (fos9.last_price > 0\n"
            "                    OR (fos9.yes_bid > 0\n"
            "                        AND (" + PARTNER_UNKNOWN_ASK
            + "fos9.yes_ask - fos9.yes_bid < 0.50)))))",
            "               AND (fos9.yes_bid > 0 OR fos9.last_price > 0)))",
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
        assert "0.50 or more above it" in lowered
        assert "no recorded ask still counts" in lowered
        # It says what our snapshots show, never that the market never traded.
        assert "no captured snapshot shows a trade" in lowered
        assert "never traded" not in lowered
