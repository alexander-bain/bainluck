"""CAL-P992 (#1978, calibration-027 A): the placeholder filter must be pair-symmetric.

WHY THIS FILE EXISTS. ``POLY_PLACEHOLDER_EXCLUDE`` is a per-LEG rule and Polymarket
O/U markets have two legs that are not written the same way: the Over comes from a
real order book, the Under is stored as ``1 - Over`` and usually never carries a book
of its own. So the leg rule fired on 398 Under legs and ZERO Over legs in
``polymarket/basketball/quantity``, deleted the bookless half of each pair, and
published the survivor alone — 398 orphan Over legs at a mean 0.4966 that win 9.8%.
The curve was grading half a book against the venue's settlement.

WHAT IS GUARDED, AND HOW. The rule is a SQL string, so a guard that asserts on its
TEXT proves nothing about what the database does with it. Every test below executes
the module's real ``POLY_PLACEHOLDER_EXCLUDE`` against a seeded table and reads the
per-outcome boolean back. The DEFECT ARM runs ``LEG_ONLY_DEFECT_SQL`` — the
pre-CAL-P992 shape, kept verbatim HERE rather than exported from the module, because
every module-level SQL constant in ``precompute_calibration`` is a hole the
calibration fingerprint does not hash and
``test_a_behaviour_only_input_does_not_widen_the_sql_shaping_hole`` counts them. So
the fixture proves the two shapes disagree without widening that hole, and no
assertion below can pass merely because the fixture was too weak to tell them apart.

THREE CONTROLS, because a symmetry rule is exactly the kind of change that is easy to
over-apply: a two-leg pair where BOTH legs traded must keep both legs; a multi-outcome
FIELD market must not lose its partners (the measured ``field`` control moved zero
rows); and a Kalshi pair must be untouched, since Kalshi has its own all-bands
liquidity contract and this rule is Polymarket-only.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tasks.precompute_calibration import (  # noqa: E402
    POLY_PLACEHOLDER_EXCLUDE,
    POLY_PLACEHOLDER_RULE_TEXT,
)

#: The rule as it stood before CAL-P992 — the per-leg test with no partner clause.
#: Pinned as a literal so this arm keeps describing the defect even if the shipped
#: constant is rewritten again; a defect arm that imports the thing it is supposed to
#: contradict can only ever agree with it.
LEG_ONLY_DEFECT_SQL = (
    "(vm.source = 'polymarket'\n"
    "     AND COALESCE(fo.calibration_probability, fo.opening_probability) >= 0.45\n"
    "     AND COALESCE(fo.calibration_probability, fo.opening_probability) <= 0.55\n"
    "     AND NOT EXISTS (\n"
    "        SELECT 1 FROM futures_odds_snapshots fos\n"
    "        WHERE fos.outcome_id = fo.id\n"
    "          AND (fos.yes_bid > 0 OR fos.last_price > 0)))"
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
        last_price REAL
    );
    CREATE TABLE vm (market_id INTEGER, source TEXT);
"""

#: The rule is interpolated into the producer's big query as a bare expression
#: aliased to ``is_poly_placeholder``. This harness reproduces that exact framing —
#: including the ``vm`` join the rule reads ``source`` from — so a change that only
#: parses inside a different set of parentheses cannot pass here.
PROBE = """
    SELECT fo.name, {expr} AS is_poly_placeholder
    FROM futures_outcomes fo
    JOIN vm ON vm.market_id = fo.market_id
    ORDER BY fo.id
"""


def _seed(conn, market_id, source, legs):
    conn.execute(
        text("INSERT INTO vm (market_id, source) VALUES (:m, :s)"),
        {"m": market_id, "s": source},
    )
    for outcome_id, name, price, has_book in legs:
        conn.execute(
            text(
                "INSERT INTO futures_outcomes "
                "(id, market_id, name, calibration_probability, opening_probability) "
                "VALUES (:i, :m, :n, :p, :p)"
            ),
            {"i": outcome_id, "m": market_id, "n": name, "p": price},
        )
        if has_book:
            conn.execute(
                text(
                    "INSERT INTO futures_odds_snapshots "
                    "(outcome_id, yes_bid, last_price) VALUES (:i, 0.48, 0.49)"
                ),
                {"i": outcome_id},
            )
        else:
            # Present but EMPTY evidence: a snapshot row that never showed a bid or
            # a trade. Seeding no row at all would let a rule that forgot the
            # `yes_bid > 0 OR last_price > 0` test pass by accident.
            conn.execute(
                text(
                    "INSERT INTO futures_odds_snapshots "
                    "(outcome_id, yes_bid, last_price) VALUES (:i, 0, 0)"
                ),
                {"i": outcome_id},
            )


@pytest.fixture
def seeded():
    """One half-book O/U pair, plus the three controls."""
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        for stmt in CREATE.strip().split(";"):
            if stmt.strip():
                conn.execute(text(stmt))

        # THE DEFECT. Polymarket writes the Over from a real book and the Under as
        # its complement, so only the Under trips the leg rule — and the Over that
        # survives is half a book priced at a coin flip.
        _seed(
            conn,
            1,
            "polymarket",
            [
                (10, "half_book_over", 0.4966, True),
                (11, "half_book_under", 0.5034, False),
            ],
        )
        # CONTROL 1 — a genuine two-leg coin flip. Both legs traded, so neither is
        # a placeholder and pair symmetry has nothing to act on. #151's census is
        # explicit that has-bid near-0.50 poly outcomes resolve at 0.43-0.55 and
        # MUST stay in the curve.
        _seed(
            conn,
            2,
            "polymarket",
            [
                (20, "real_coinflip_yes", 0.51, True),
                (21, "real_coinflip_no", 0.49, True),
            ],
        )
        # CONTROL 2 — a FIELD market: three outcomes, one of them a bookless
        # near-0.50 placeholder. Only that leg may leave; a rule that reached for
        # "the rest of the market" would empty the cell the fold measured as moving
        # zero rows.
        _seed(
            conn,
            3,
            "polymarket",
            [
                (30, "field_placeholder", 0.50, False),
                (31, "field_runner_a", 0.30, True),
                (32, "field_runner_b", 0.20, True),
            ],
        )
        # CONTROL 3 — Kalshi. Its never-traded rows are already excluded in ALL
        # price bands by KALSHI_LIQUIDITY_EXISTS, a different contract; this rule
        # must not reach across the source boundary.
        _seed(
            conn,
            4,
            "kalshi",
            [
                (40, "kalshi_over", 0.4966, True),
                (41, "kalshi_under", 0.5034, False),
            ],
        )
    return engine


def _flags(engine, expr):
    with engine.begin() as conn:
        rows = conn.execute(text(PROBE.format(expr=expr))).all()
    return {name: bool(flag) for name, flag in rows}


class TestHalfABookIsNotAForecast:
    """The ship: an excluded leg takes its partner with it."""

    def test_the_defect_arm_publishes_the_orphan_over(self, seeded):
        """The failure, executed. This is what the curve was grading."""
        flags = _flags(seeded, LEG_ONLY_DEFECT_SQL)

        assert flags["half_book_under"] is True, (
            "fixture check: the bookless Under must trip the leg rule, or this "
            "file is not reproducing the half-book"
        )
        assert flags["half_book_over"] is False, (
            "RED-FIRST ANCHOR: under the per-leg rule the booked Over survives "
            "alone at 0.4966 and goes on to win 9.8% of the time. If this is "
            "already True the fixture is not showing the defect."
        )

    def test_both_legs_of_a_half_book_pair_leave_together(self, seeded):
        flags = _flags(seeded, POLY_PLACEHOLDER_EXCLUDE)

        assert flags["half_book_under"] is True
        assert flags["half_book_over"] is True, (
            "pair symmetry: if the exclusion removed one leg of a two-leg market "
            "the partner may not publish alone"
        )

    def test_a_pair_that_both_traded_keeps_both_legs(self, seeded):
        """Control 1. The rule may only touch rows that are ALREADY half-excluded."""
        flags = _flags(seeded, POLY_PLACEHOLDER_EXCLUDE)

        assert flags["real_coinflip_yes"] is False
        assert flags["real_coinflip_no"] is False, (
            "a genuine 50/50 with a book on both sides is the signal this curve "
            "exists to measure — excluding it would be the cure killing the patient"
        )

    def test_a_field_market_loses_only_its_placeholder_leg(self, seeded):
        """Control 2. `= 2` is the whole blast radius, and it is measured."""
        flags = _flags(seeded, POLY_PLACEHOLDER_EXCLUDE)

        assert flags["field_placeholder"] is True
        assert flags["field_runner_a"] is False
        assert flags["field_runner_b"] is False, (
            "the fold measured ZERO rows moving in the `field` control; a rule "
            "that fires here contradicts the measurement it was authorised on"
        )

    def test_kalshi_pairs_are_untouched(self, seeded):
        """Control 3. The source boundary, executed rather than read off the string."""
        flags = _flags(seeded, POLY_PLACEHOLDER_EXCLUDE)

        assert flags["kalshi_over"] is False
        assert flags["kalshi_under"] is False, (
            "Kalshi's never-traded rows are excluded all-bands by a different "
            "contract; reaching them from here would double-apply two policies"
        )


class TestTheRuleIsWiredTheWayTheProducerReadsIt:
    """The expression must survive being interpolated bare into the big query."""

    def test_the_shipped_expression_still_contains_the_leg_rule(self):
        """Pair symmetry ADDS a clause; it must not have replaced the original one."""
        assert LEG_ONLY_DEFECT_SQL in POLY_PLACEHOLDER_EXCLUDE, (
            "#151's per-leg census is still the reason a bookless near-0.50 poly "
            "outcome leaves the curve. Symmetry is a second clause, not a swap."
        )

    def test_a_top_level_or_cannot_escape_its_parentheses(self):
        """`{...} AS is_poly_placeholder` — an unwrapped OR would bind rightwards.

        Balance-checked rather than eyeballed: the constant is assembled from a
        dozen concatenated fragments, which is exactly the shape where a dropped
        paren type-checks, imports, and silently changes what the curve publishes.
        """
        assert POLY_PLACEHOLDER_EXCLUDE.startswith("((")
        assert POLY_PLACEHOLDER_EXCLUDE.endswith("))")
        assert POLY_PLACEHOLDER_EXCLUDE.count("(") == POLY_PLACEHOLDER_EXCLUDE.count(
            ")"
        ), "unbalanced parentheses in the shipped placeholder expression"

        depth = 0
        for char in POLY_PLACEHOLDER_EXCLUDE[:-1]:
            depth += (char == "(") - (char == ")")
            assert depth > 0, (
                "the expression must never return to depth 0 before its final "
                "character, or the trailing clauses sit OUTSIDE the wrapper and "
                "the OR binds against whatever the query puts next"
            )

    def test_the_user_facing_rule_text_names_the_symmetry(self):
        """/calibration surfaces this string. A silent filter is the thing to avoid."""
        lowered = POLY_PLACEHOLDER_RULE_TEXT.lower()
        assert "pair-symmetric" in lowered
        assert "partner" in lowered, (
            "the page prints this sentence as the reason rows were excluded; if it "
            "still describes only the per-leg rule the disclosure understates what "
            "the filter removed"
        )
