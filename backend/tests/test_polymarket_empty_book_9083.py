"""#9083: a Polymarket book with no bid and no offer below a dollar is not an opening.

Specimen: ``/events/15319167`` led its props rail with "Turner's 1+ hits + runs +
rbis was marked 1% — and it hit". The 1% was Phase 0c-repair promoting a snapshot
of bid NULL / ask 1.00 / last 0.01 (the Under: bid 0.00 / ask NULL / last 0.99).
The only book guard on that promotion is Kalshi-scoped (CERT-2508), so this
Polymarket shape passed.

The real-Postgres half (Phase 0c executed, the rail applied and restored) is
``tests/integration/test_polymarket_empty_book_openings_9083_real_postgres.py``.
"""

from __future__ import annotations

import importlib
import inspect
import itertools

import pytest

from app.tasks.polymarket import complementary_book
from app.utils.polymarket_empty_book import (
    EMPTY_BOOK_TICK,
    POLYMARKET_BOOKMAKER,
    empty_polymarket_book_sql,
    is_empty_polymarket_book,
)


def _module_source(path: str) -> str:
    """Source of the MODULE by path (``app.tasks`` shadows ``backfill_winners``)."""
    return inspect.getsource(importlib.import_module(path))


def _eval_sql(bid, ask, bookmaker) -> bool:
    """Evaluate the emitted SQL under Python semantics, one snapshot row at a time."""
    sql = empty_polymarket_book_sql("fos")
    expr = (
        sql.replace("fos.bookmaker", repr(bookmaker))
        .replace("fos.yes_bid IS NOT NULL", f"_notnull({bid!r})")
        .replace("fos.yes_ask IS NOT NULL", f"_notnull({ask!r})")
        .replace("fos.yes_bid", repr(bid))
        .replace("fos.yes_ask", repr(ask))
        .replace("COALESCE", "_coalesce")
        .replace(" AND ", " and ")
        .replace(" OR ", " or ")
        .replace(" = ", " == ")
    )
    return bool(
        eval(  # noqa: S307 - fixed expression built from a constant
            expr,
            {
                "_coalesce": lambda v, d: d if v is None else v,
                "_notnull": lambda v: v is not None,
            },
        )
    )


class TestTheRule:
    def test_the_specimen_over_is_refused(self):
        # Trea Turner H+R+RBI O/U 0.5, Over: bid NULL / ask 1.00, priced 0.01.
        assert is_empty_polymarket_book(None, 1.0) is True

    def test_the_specimen_under_is_refused(self):
        # The same book from the other token: bid 0.00 / ask NULL, priced 0.99.
        assert is_empty_polymarket_book(0.0, None) is True

    @pytest.mark.parametrize(
        "bid,ask",
        [
            (None, 0.99),  # Mookie Betts H+R+RBI O/U 1.5 Over, production
            (0.0, 0.99),   # Victor Bericoto Under, production
            (0.01, 1.0),   # its Over, the same book
            (0.0, 1.0),
        ],
    )
    def test_a_dust_book_is_refused(self, bid, ask):
        assert is_empty_polymarket_book(bid, ask) is True

    @pytest.mark.parametrize(
        "bid,ask,why",
        [
            (0.45, 0.51, "Griffin Jax 5+ K control: a two-sided book"),
            (0.95, None, "lone bid: somebody will pay 95c"),
            (0.02, 1.0, "a 2c bid is a bid"),
            (None, 0.36, "lone ask: an offer at 36c bounds the price"),
            (0.0, 0.98, "an ask a tick inside the dollar is an offer"),
        ],
    )
    def test_a_book_that_quotes_something_is_kept(self, bid, ask, why):
        assert is_empty_polymarket_book(bid, ask) is False, why

    def test_no_recorded_book_is_not_evidence(self):
        """Both NULL is a pre-CAL-P097 Under snapshot (493,415 of them), not an
        empty book. Refusing it would stop every one being promotable."""
        assert is_empty_polymarket_book(None, None) is False

    def test_a_leg_and_its_twin_always_agree(self):
        """The pair is one book. Swept over every cent book, NULL sides included,
        through the writer's own ``complementary_book`` arithmetic (which does NOT
        round: ``1 - 0.99`` is ``0.010000000000000009``)."""
        cents = [None] + [c / 100 for c in range(0, 101)]
        splits = []
        for bid, ask in itertools.product(cents, cents):
            if bid is not None and ask is not None and bid > ask:
                continue
            no_bid, no_ask, _ = complementary_book(bid, ask, None)
            if is_empty_polymarket_book(bid, ask) != is_empty_polymarket_book(
                no_bid, no_ask
            ):
                splits.append((bid, ask))
        assert splits == [], f"{len(splits)} books split across the pair: {splits[:5]}"

    def test_the_tick_is_one_cent(self):
        assert EMPTY_BOOK_TICK == 0.01


class TestTheSql:
    @pytest.mark.parametrize(
        "bid,ask",
        [
            (None, 1.0), (0.0, None), (None, 0.99), (0.0, 0.99), (0.01, 1.0),
            (0.0, 1.0), (0.45, 0.51), (0.95, None), (0.02, 1.0), (None, 0.36),
            (0.0, 0.98), (None, None), (0.0100, 0.9900),
        ],
    )
    def test_sql_and_python_agree_book_for_book(self, bid, ask):
        assert _eval_sql(bid, ask, POLYMARKET_BOOKMAKER) is is_empty_polymarket_book(
            bid, ask
        )

    @pytest.mark.parametrize("bookmaker", ["kalshi", "draftkings", "datagolf_model"])
    def test_the_sql_is_false_for_every_other_venue(self, bookmaker):
        """CERT-2508's lesson, mirrored: one venue's book rule never governs another's."""
        assert _eval_sql(None, 1.0, POLYMARKET_BOOKMAKER) is True, "control"
        assert _eval_sql(None, 1.0, bookmaker) is False

    def test_is_never_null_so_it_is_safe_under_not(self):
        """Every nullable column is COALESCEd or IS-tested; a NULL here, under
        Phase 0c's ``NOT (...)``, would drop the snapshot from the lateral."""
        sql = empty_polymarket_book_sql("fos")
        assert sql.count("COALESCE(") == 2, sql
        assert "fos.yes_bid IS NOT NULL OR fos.yes_ask IS NOT NULL" in sql
        assert f"fos.bookmaker = '{POLYMARKET_BOOKMAKER}'" in sql

    def test_refuses_an_alias_that_is_not_an_identifier(self):
        with pytest.raises(ValueError):
            empty_polymarket_book_sql("fos; DROP TABLE futures_outcomes")


def _phase_0c_block() -> str:
    source = _module_source("app.tasks.backfill_winners")
    marker = "opening_source = 'first_snapshot'"
    start = source.rindex("WITH first_snaps AS", 0, source.index(marker))
    return source[start : source.index(marker)]


class TestPhase0cCarriesTheGuard:
    def test_the_promotion_refuses_the_empty_polymarket_book(self):
        block = _phase_0c_block()
        assert 'AND NOT {empty_polymarket_book_sql("fos")}' in block, (
            "Phase 0c promotes a Polymarket snapshot without checking its book — "
            "the #9083 '1% and it hit' opening, restored"
        )

    def test_the_guard_skips_the_snapshot_not_the_outcome(self):
        """Inside the LATERAL's WHERE, before its ORDER BY: a leg that opened on an
        empty book and later got a real one still gets that real opening."""
        block = _phase_0c_block()
        lateral = block.index("CROSS JOIN LATERAL")
        guard = block.index("empty_polymarket_book_sql")
        order = block.index("ORDER BY fos.captured_at")
        assert lateral < guard < order

    def test_the_shipped_constants_carry_the_rendered_rule(self):
        bw = importlib.import_module("app.tasks.backfill_winners")
        rendered = empty_polymarket_book_sql("fos")
        assert f"NOT {rendered}" in bw.PHASE_0C_REPAIR_SQL
        assert f"NOT {rendered}" in bw.PHASE_0C_REPAIR_SQL_BOUNDED


class TestTheRail:
    def test_the_rail_filters_honest_candidates_exactly_as_phase_0c_does(self):
        """Fixed point: the replacement lateral applies Phase 0c's filters, so a
        row this rail withdraws or reprices is one Phase 0c leaves alone."""
        from app.tasks import repair_polymarket_empty_book_openings as rail
        from app.utils.kalshi_empty_book import lone_ask_on_empty_book_sql

        bw = importlib.import_module("app.tasks.backfill_winners")
        for clause in (
            "fos.probability > 0 AND fos.probability < 1",
            f"NOT {lone_ask_on_empty_book_sql('fos')}",
            f"NOT {empty_polymarket_book_sql('fos')}",
            "fos.captured_at <= fm.resolution_date",
            "ORDER BY fos.captured_at ASC",
        ):
            assert clause in bw.PHASE_0C_REPAIR_SQL, clause
            assert clause in rail._BOUND_SQL, clause

    def test_the_provenance_clause_ties_the_opening_to_its_own_snapshot(self):
        from app.tasks import repair_polymarket_empty_book_openings as rail

        for clause in (
            "bad.captured_at = fo.opening_captured_at",
            "bad.probability = fo.opening_probability",
            empty_polymarket_book_sql("bad"),
            "fo.opening_source = 'first_snapshot'",
        ):
            assert clause in rail._BOUND_SQL, clause

    def test_the_rail_holds_no_price_rule_of_its_own(self):
        """Both book rules are imported. A literal threshold here is a third copy."""
        from app.tasks import repair_polymarket_empty_book_openings as rail

        src = inspect.getsource(rail)
        code = src[src.index('"""', src.index('"""') + 3) + 3 :]
        for literal in ("0.99", "0.01", "0.5)", "<= 0.0", ">= 0.9"):
            assert literal not in code, literal

    def test_the_rail_writes_only_the_opening_and_its_copy(self):
        from app.tasks import repair_polymarket_empty_book_openings as rail

        set_clause = rail._APPLY_SQL.split("SET", 1)[1].split("FROM scope", 1)[0]
        for forbidden in ("is_winner", "resolution_source", "last_updated"):
            assert forbidden not in set_clause, forbidden

    def test_both_names_are_registered(self):
        from app.routes.admin_repairs import _REPAIRS as REPAIRS

        assert REPAIRS["polymarket-empty-book-openings"] == (
            "app.tasks.repair_polymarket_empty_book_openings",
            "repair",
        )
        assert REPAIRS["polymarket-empty-book-openings-restore"] == (
            "app.tasks.repair_polymarket_empty_book_openings",
            "restore",
        )
