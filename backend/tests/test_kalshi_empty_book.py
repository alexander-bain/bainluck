"""A lone ask on an empty Kalshi book is not a price (#4745).

The measured claim these tests defend: resolved Kalshi legs whose earliest
snapshot was bid 0.00 / ask > 0.50 / no trade were published at a mean 0.94 and
actually won ~14% — 34,281 of them, across every family. The live poller has
refused to write that shape since 52eee9b6 (2026-07-13); nothing stopped
``backfill_winners`` Phase 0c-repair from promoting the ones already stored.
"""

from __future__ import annotations

import importlib
import inspect

import pytest

from app.utils.kalshi_empty_book import (
    ASK_ONLY_TRUSTED_MAX,
    is_lone_ask_on_empty_book,
    lone_ask_on_empty_book_sql,
)


def _backfill_winners_source() -> str:
    """Source of the MODULE, not the celery task that shadows its name.

    ``app.tasks.__init__`` defines a function called ``backfill_winners``, so
    ``from app.tasks import backfill_winners`` hands back the task wrapper and
    ``inspect.getsource`` returns twelve lines that contain no SQL at all —
    a source-scan guard that can never fail. Import the module by path.
    """
    module = importlib.import_module("app.tasks.backfill_winners")
    return inspect.getsource(module)


class TestIsLoneAskOnEmptyBook:
    """The Python side of the rule."""

    @pytest.mark.parametrize(
        "bid,ask,last",
        [
            (0.0, 0.98, 0.0),   # Mitch Marner: 3+ points, published 0.98
            (0.0, 0.98, None),  # same book, no trade field at all
            (0.0, 0.51, 0.0),   # just above the trusted ceiling
            (0.0, 1.0, 0.0),    # the settled shell
        ],
    )
    def test_refuses_the_untaken_offer(self, bid, ask, last):
        assert is_lone_ask_on_empty_book(bid, ask, last) is True

    @pytest.mark.parametrize(
        "bid,ask,last,why",
        [
            (0.07, 1.0, 0.0, "a lone BID is a real price — someone will pay it"),
            (0.0, 0.50, 0.0, "at the ceiling the poller still trusts an ask-only book"),
            (0.0, 0.40, 0.0, "a longshot ask-only book is trusted below the ceiling"),
            (0.0, 0.98, 0.05, "a real trade outranks the book it sits in"),
            (0.95, 0.97, 0.0, "a tight two-sided book is the honest mid"),
            (None, 0.98, 0.0, "no book recorded — the candle rails store no bid"),
            (0.0, None, 0.0, "no ask recorded"),
            (None, None, None, "nothing recorded at all"),
        ],
    )
    def test_accepts_everything_that_is_a_price(self, bid, ask, last, why):
        assert is_lone_ask_on_empty_book(bid, ask, last) is False, why

    def test_a_missing_bid_is_not_a_zero_bid(self):
        """``None`` means we never saw a book; 0.00 means nobody would pay.

        Conflating them would make this predicate claim knowledge about every
        candle-rail row, which stores no bid or ask at all.
        """
        assert is_lone_ask_on_empty_book(None, 0.98, 0.0) is False
        assert is_lone_ask_on_empty_book(0.0, 0.98, 0.0) is True


class TestLoneAskOnEmptyBookSql:
    """The SQL side of the rule, and that it is the SAME rule."""

    def test_emits_a_boolean_over_the_given_alias(self):
        sql = lone_ask_on_empty_book_sql("fos")
        assert "fos.yes_bid" in sql
        assert "fos.yes_ask" in sql
        assert "fos.last_price" in sql
        assert str(ASK_ONLY_TRUSTED_MAX) in sql

    def test_refuses_an_alias_that_is_not_an_identifier(self):
        with pytest.raises(ValueError):
            lone_ask_on_empty_book_sql("fos; DROP TABLE futures_outcomes")

    def test_is_never_null_so_it_is_safe_under_NOT(self):
        """A NULL book must make the expression FALSE, not NULL.

        Phase 0c-repair uses this under ``NOT (...)``. If the expression went
        NULL on an absent book, ``NOT NULL`` is NULL, the row is filtered out,
        and every candle-rail snapshot silently stops being promotable — a
        far larger change than the one intended.
        """
        sql = lone_ask_on_empty_book_sql("fos")
        assert sql.count("COALESCE") == 3, sql

    @pytest.mark.parametrize(
        "bid,ask,last",
        [
            (0.0, 0.98, 0.0),
            (0.0, 0.98, None),
            (0.07, 1.0, 0.0),
            (0.0, 0.50, 0.0),
            (0.0, 0.98, 0.05),
            (None, 0.98, 0.0),
            (0.0, None, 0.0),
            (None, None, None),
        ],
    )
    def test_sql_and_python_agree_book_for_book(self, bid, ask, last):
        """Evaluate the emitted SQL in Python's own semantics and compare.

        A price policy that exists twice drifts. This is the same binding
        ``test_kalshi_candle_price`` puts on its own pair of reducers.
        """
        sql = lone_ask_on_empty_book_sql("fos")
        expr = (
            sql.replace("fos.yes_bid", repr(bid))
            .replace("fos.yes_ask", repr(ask))
            .replace("fos.last_price", repr(last))
            .replace("COALESCE", "_coalesce")
            .replace(" AND ", " and ")
            .replace(" = ", " == ")
        )
        evaluated = eval(  # noqa: S307 - fixed expression built from a constant
            expr, {"_coalesce": lambda v, d: d if v is None else v, "None": None}
        )
        assert bool(evaluated) is is_lone_ask_on_empty_book(bid, ask, last)


class TestBoundToTheLivePoller:
    """The constant is not free-floating — it mirrors a shipped guard."""

    def test_ceiling_matches_the_pollers_ask_only_cap(self):
        """``_kalshi_yes_probability`` rule 3 is where this number came from.

        If someone widens the poller's ask-only cap without widening this, the
        promotion starts refusing rows the poller happily writes; narrow it the
        other way and the promotion re-admits the shape this ship removed.
        """
        from app.tasks.kalshi import _kalshi_yes_probability

        at_ceiling = _kalshi_yes_probability(0.0, ASK_ONLY_TRUSTED_MAX, 0.0)
        above_ceiling = _kalshi_yes_probability(0.0, ASK_ONLY_TRUSTED_MAX + 0.01, 0.0)

        assert at_ceiling == pytest.approx(ASK_ONLY_TRUSTED_MAX), (
            "the poller should still trust an ask-only book AT the ceiling"
        )
        assert above_ceiling is None, (
            "the poller should store nothing above the ceiling; this module's "
            "ceiling must be the same number"
        )

    def test_the_two_agree_on_every_book_the_poller_refuses_outright(self):
        """Where the poller writes nothing, the promotion must promote nothing.

        Anything the poller reduces to ``None`` never becomes a snapshot, so the
        only rows this predicate can meet are ones the poller once accepted.
        The overlap that matters is the ask-only band.
        """
        from app.tasks.kalshi import _kalshi_yes_probability

        for ask_cents in range(1, 100):
            ask = ask_cents / 100.0
            poller = _kalshi_yes_probability(0.0, ask, 0.0)
            refused_here = is_lone_ask_on_empty_book(0.0, ask, 0.0)
            assert (poller is None) is refused_here, (
                f"ask={ask}: poller={poller!r} but predicate refused={refused_here}"
            )


class TestPhase0cRepairUsesTheGuard:
    """The promotion query must actually carry the rule."""

    def test_promotion_sql_excludes_the_empty_book(self):
        source = _backfill_winners_source()
        marker = "opening_source = 'first_snapshot'"
        assert marker in source, "Phase 0c-repair moved; this guard test is stale"

        # The promotion's own SQL block, not the whole module.
        block_start = source.rindex("WITH first_snaps AS", 0, source.index(marker))
        block = source[block_start : source.index(marker)]

        assert "lone_ask_on_empty_book_sql" in block, (
            "Phase 0c-repair promotes the earliest snapshot without checking the "
            "book it recorded — the #4745 regression, restored"
        )
        assert "NOT " in block

    def test_guard_filters_the_snapshot_not_the_outcome(self):
        """A leg that opened on an empty book and later traded keeps an opening.

        The predicate belongs inside the LATERAL's WHERE (skip that row, take
        the next honest one), never in the outer WHERE (drop the leg entirely).
        """
        source = _backfill_winners_source()
        marker = "opening_source = 'first_snapshot'"
        block_start = source.rindex("WITH first_snaps AS", 0, source.index(marker))
        block = source[block_start : source.index(marker)]

        guard_at = block.index("lone_ask_on_empty_book_sql")
        lateral_at = block.index("CROSS JOIN LATERAL")
        order_at = block.index("ORDER BY fos.captured_at")

        assert lateral_at < guard_at < order_at, (
            "the guard must sit in the LATERAL's WHERE, before its ORDER BY, so "
            "it skips the fabricated row rather than the whole outcome"
        )
