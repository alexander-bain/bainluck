"""The Under/No SNAPSHOT carries a book — proved by EXECUTING the writer.

CERT-403C blocked the staged snapshot change on three findings. This file
answers the first and the third; the second (the Option A/B policy decision) is
recorded in ``QUEUE-STAGED-CAL-UNDER-LEG-SNAPSHOT-BOOK.md`` and in the writer's
own comment, because a decision is not a test.

Finding 3 is why this file exists rather than four more lines in
``test_polymarket_under_leg_book.py``:

    "[P2] The existing 18-test file does not cover the staged snapshot change
     and its writer pins are source-reading ... its writer tests use
     inspect.getsource, slice the Under block, and assert strings ... A
     source-level green can survive a dead or shadow implementation."
    fix-sketch: "execute _process_event_batch with a fake session/insert
     recorder and assert the second FuturesOddsSnapshot statement's bound values
     contain the mirrored bid, ask, and last price; prove the same test fails on
     ee25e1cd."

So every assertion below reads **bound parameters off a compiled statement the
shipping code actually emitted**, never the source text. The distinction is not
pedantic: `assert "yes_bid=under_best_bid," in source` passes if the line is
inside a branch that never runs, inside a second dead copy of the writer, or
after an early `continue`. Compiling what `session.execute` was handed cannot.

RED-FIRST, BY EXECUTION. At ``ee25e1cd`` (CAL-P095's head, the subject CERT-403C
graded) ``test_the_under_snapshot_carries_the_mirrored_book`` fails with the
three columns absent from the emitted insert, and
``test_the_under_snapshot_book_mirrors_the_over_book`` fails on ``KeyError``.
The receipt is in the queue report; re-run it by installing
``git show ee25e1cd:backend/app/tasks/polymarket.py`` over the working copy.
"""

from __future__ import annotations

import contextlib
from collections import defaultdict
from datetime import datetime, timezone

import pytest
from sqlalchemy.dialects import postgresql

from app.services.polymarket_api import PolymarketEvent, PolymarketMarket


def _fresh_stats() -> dict:
    """The counter dict the writer expects its caller to have seeded.

    ``defaultdict(int)`` because ``_process_event_batch`` increments a dozen
    keys without creating them, and its own per-event ``try/except`` would
    swallow the resulting ``KeyError`` as an "error" for that event — silently
    skipping the very branch under test while the harness looked healthy.
    """
    stats: dict = defaultdict(int)
    stats["errors"] = []
    return stats


class _Result:
    """Permissive stand-in for whatever the writer asks of a result.

    Deliberately answers every shape rather than only the ones the current path
    happens to call. A recorder that raises on an unexpected accessor turns an
    unrelated refactor into a red test about nothing, and the next person
    weakens the assertions to get green.
    """

    def __init__(self, ident: int) -> None:
        self._ident = ident

    def scalar_one(self):
        return self._ident

    def scalar_one_or_none(self):
        return None

    def scalar(self):
        return None

    def first(self):
        return None

    def all(self):
        return []

    def fetchall(self):
        return []

    def scalars(self):
        return self

    @property
    def rowcount(self):
        return 0

    def __iter__(self):
        return iter(())


class RecordingSession:
    """Records every statement handed to ``execute`` and hands back ids."""

    def __init__(self) -> None:
        self.statements: list[object] = []
        self._next_id = 1000

    async def execute(self, stmt, *args, **kwargs):
        self.statements.append(stmt)
        self._next_id += 1
        return _Result(self._next_id)

    async def commit(self):
        return None

    async def rollback(self):
        return None

    async def flush(self):
        return None

    def add(self, *_a, **_k):
        return None


def _bound_params(stmt) -> dict:
    """The values the database would actually receive for this statement."""
    return stmt.compile(dialect=postgresql.dialect()).params


def _snapshots_by_outcome(session: RecordingSession) -> dict[str, dict]:
    """``external_id -> bound params of that outcome's snapshot INSERT``.

    NOT positional. The first draft of this helper indexed the snapshot list and
    called ``[1]`` the Under leg, and execution immediately disproved it: the
    writer emits **six** snapshots for this fixture, because the parent-market
    path writes its own after the two decomposed sub-markets, and a sub-market
    the writer legitimately refuses (no book at a mid-range price) drops out of
    the sequence entirely and shifts every later index by two.

    So each snapshot is keyed to the ``futures_outcomes`` upsert immediately
    preceding it — which is exactly how the writer pairs them, via the
    ``.returning(FuturesOutcome.id)`` whose value becomes ``outcome_id``. The
    ``_yes``/``_no`` suffix on ``external_id`` then names the leg with no
    counting involved.
    """
    out: dict[str, dict] = {}
    pending: str | None = None
    for stmt in session.statements:
        table = getattr(stmt, "table", None)
        if table is None:
            continue
        if table.name == "futures_outcomes":
            pending = _bound_params(stmt).get("external_id")
        elif table.name == "futures_odds_snapshots" and pending is not None:
            out[pending] = _bound_params(stmt)
            pending = None
    return out


#: One game event with two sub-markets, ``neg_risk=False`` — the decomposed-pair
#: branch, which is the one that writes an Over snapshot and an Under snapshot.
#: The book is deliberately ASYMMETRIC and non-degenerate (bid 0.42, ask 0.46,
#: last 0.44) so a mirrored value can never be confused with the original: the
#: complement of each is a different number, and the three complements are
#: different from each other.
OVER_BID, OVER_ASK, OVER_LAST = 0.42, 0.46, 0.44


def _event() -> PolymarketEvent:
    return PolymarketEvent(
        id="evt-p097",
        title="Yankees vs Red Sox",
        slug="yankees-red-sox",
        active=True,
        closed=False,
        neg_risk=False,
        tags=["Sports", "MLB", "Baseball"],
        start_date=datetime(2026, 8, 25, 23, 5, tzinfo=timezone.utc),
        markets=[
            PolymarketMarket(
                condition_id="0xcafe01",
                question="Yankees vs Red Sox o/u 8.5 runs",
                outcomes=["Over", "Under"],
                outcome_prices=[0.55, 0.45],
                best_bid=OVER_BID,
                best_ask=OVER_ASK,
                last_trade_price=OVER_LAST,
                volume=125_000.0,
                active=True,
            ),
            PolymarketMarket(
                condition_id="0xcafe02",
                question="Yankees vs Red Sox moneyline",
                outcomes=["Yes", "No"],
                outcome_prices=[0.61, 0.39],
                best_bid=0.60,
                best_ask=0.62,
                last_trade_price=0.61,
                volume=90_000.0,
                active=True,
            ),
        ],
    )


async def _run_writer(monkeypatch) -> RecordingSession:
    """Execute the real ``_process_event_batch`` against a recording session."""
    from app.models.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome
    from app.tasks import polymarket as poly
    from app.utils.market_label_normalization import compute_market_tier
    from app.utils.odds_math import probability_to_american
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    session = RecordingSession()

    @contextlib.asynccontextmanager
    async def _fake_session():
        yield session

    monkeypatch.setattr(poly, "get_task_session", _fake_session)

    stats: dict = _fresh_stats()
    await poly._process_event_batch(
        [_event()],
        stats,
        FuturesMarket,
        FuturesOutcome,
        FuturesOddsSnapshot,
        pg_insert,
        probability_to_american,
        compute_market_tier,
    )
    assert not stats["errors"], f"writer raised: {stats['errors']}"
    return session


#: The o/u sub-market the assertions land on. Named once so a fixture change
#: cannot leave a test silently pointing at the moneyline pair next to it.
OU_CID = "0xcafe01"


class TestTheUnderSnapshotIsWritten:
    """The three columns, read off the statement the writer emitted."""

    @pytest.mark.asyncio
    async def test_both_legs_of_the_ou_pair_get_a_snapshot(self, monkeypatch):
        """Guards the harness itself before anything is concluded from it.

        If the fixture stopped reaching the decomposed branch — or the writer
        refused the market, which it legitimately does for a mid-range price
        with no book — every assertion below would pass vacuously over a missing
        key. That is the shape of false green this whole file exists to refuse,
        so it is checked first and by name rather than by count.
        """
        snaps = _snapshots_by_outcome(await _run_writer(monkeypatch))
        assert f"{OU_CID}_yes" in snaps, "the Over leg never reached a snapshot"
        assert f"{OU_CID}_no" in snaps, "the Under leg never reached a snapshot"

    @pytest.mark.asyncio
    async def test_the_under_snapshot_carries_the_mirrored_book(self, monkeypatch):
        """RED at ee25e1cd: the three keys are absent from the emitted insert."""
        under = _snapshots_by_outcome(await _run_writer(monkeypatch))[f"{OU_CID}_no"]
        for column in ("yes_bid", "yes_ask", "last_price"):
            assert column in under, (
                f"the Under snapshot insert never mentions {column!r} — "
                f"POLY_PLACEHOLDER_EXCLUDE reads exactly this column, so its "
                f"absence excludes the leg regardless of whether it traded"
            )
            assert under[column] is not None, f"{column} emitted as NULL"

    @pytest.mark.asyncio
    async def test_the_under_snapshot_book_mirrors_the_over_book(self, monkeypatch):
        """The values are the CLOB identity, not merely present.

        A snapshot carrying the Over side's own bid would satisfy the previous
        test and be wrong in the most damaging way available: it would report
        the wrong token's book as this token's evidence.
        """
        under = _snapshots_by_outcome(await _run_writer(monkeypatch))[f"{OU_CID}_no"]
        assert under["yes_bid"] == pytest.approx(1 - OVER_ASK)
        assert under["yes_ask"] == pytest.approx(1 - OVER_BID)
        assert under["last_price"] == pytest.approx(1 - OVER_LAST)

    @pytest.mark.asyncio
    async def test_the_over_snapshot_still_carries_its_own_unmirrored_book(
        self, monkeypatch
    ):
        """The mirror must not leak onto the leg that already had a real book."""
        over = _snapshots_by_outcome(await _run_writer(monkeypatch))[f"{OU_CID}_yes"]
        assert over["yes_bid"] == pytest.approx(OVER_BID)
        assert over["yes_ask"] == pytest.approx(OVER_ASK)
        assert over["last_price"] == pytest.approx(OVER_LAST)

    @pytest.mark.asyncio
    async def test_the_spread_survives_the_flip(self, monkeypatch):
        """A book judged untradeable on one leg stays untradeable on the other.

        ``(1-bid) - (1-ask) == ask - bid``. Asserted on the EMITTED rows rather
        than on ``complementary_book`` in isolation, because the helper being
        correct says nothing about which of its three return values reached
        which column — and a transposed ask/bid pair would still be
        NULL-preserving, still mirrored, and still wrong.
        """
        snaps = _snapshots_by_outcome(await _run_writer(monkeypatch))
        over, under = snaps[f"{OU_CID}_yes"], snaps[f"{OU_CID}_no"]
        assert (under["yes_ask"] - under["yes_bid"]) == pytest.approx(
            over["yes_ask"] - over["yes_bid"]
        )

    @pytest.mark.asyncio
    async def test_a_missing_bid_mirrors_to_a_null_ask_not_a_zero(self, monkeypatch):
        """NULL in, NULL out, PER COLUMN — a fabricated 0 reads as a real book.

        ``POLY_PLACEHOLDER_EXCLUDE`` tests ``yes_bid > 0``, so a manufactured
        zero is not a harmless default: it is indistinguishable from a book that
        existed and showed nothing, which is the exact inference the whole 232x
        asymmetry was built on.

        Only ``best_bid`` is removed, not the whole book. Removing all three
        made this test assert nothing at all: a mid-range price with no bid, no
        ask and no trade fails the #151 cp-capture guard in
        ``_resolve_market_probability_with_source``, so the writer CORRECTLY
        refuses the market and never reaches the snapshot. The surviving ask and
        trade keep the market real while still leaving one column absent, which
        is the case the mirror has to get right.
        """
        from app.models.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome
        from app.tasks import polymarket as poly
        from app.utils.market_label_normalization import compute_market_tier
        from app.utils.odds_math import probability_to_american
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        event = _event()
        event.markets[0].best_bid = None

        session = RecordingSession()

        @contextlib.asynccontextmanager
        async def _fake_session():
            yield session

        monkeypatch.setattr(poly, "get_task_session", _fake_session)
        stats: dict = _fresh_stats()
        await poly._process_event_batch(
            [event], stats, FuturesMarket, FuturesOutcome, FuturesOddsSnapshot,
            pg_insert, probability_to_american, compute_market_tier,
        )
        assert not stats["errors"], f"writer raised: {stats['errors']}"

        under = _snapshots_by_outcome(session)[f"{OU_CID}_no"]
        # no_ask = 1 - yes_bid, and yes_bid is absent -> absent, never 1.0 or 0.
        assert under["yes_ask"] is None, (
            "an absent Yes bid became a concrete No ask — the mirror invented a "
            "price the book never showed"
        )
        # The two columns that DO have a counterpart still mirror.
        assert under["yes_bid"] == pytest.approx(1 - OVER_ASK)
        assert under["last_price"] == pytest.approx(1 - OVER_LAST)


class TestTheReleaseIsForwardOnly:
    """Gate 6 of the staged spec, as a diff property rather than a promise."""

    def test_no_update_or_regrade_reaches_the_resolution_columns(self):
        """No historical row is rewritten and nothing is re-graded.

        The staged spec's own release posture, and gotcha #21. Checked over the
        Under block's source because this is a claim about what the code does
        NOT contain — the one question source text is the right oracle for.
        """
        import inspect

        from app.tasks import polymarket

        # #3613: the old end-marker moved out with the parent-leg build. Bound
        # the slice by the poll's OWN source and the CAL-P006 guard that
        # genuinely follows the Under block (see the twin note in
        # tests/test_polymarket_under_leg_book.py).
        src = inspect.getsource(polymarket._process_event_batch)
        start = src.index("# Create Under/No outcome if available")
        end = src.index("# CAL-P006 (#1527)")
        # COMMENTS STRIPPED FIRST. The block discusses all three columns at
        # length — that prose is the reason the fix is scoped the way it is, and
        # a check that cannot tell an explanation from a write would force the
        # next author to delete the explanation to keep the test green.
        block = "\n".join(
            line.split("#", 1)[0] for line in src[start:end].splitlines()
        )
        for column in ("is_winner", "resolution_source", "calibration_probability"):
            for form in (f"{column}=", f'"{column}":', f"{column} ="):
                assert form not in block, (
                    f"the Under writer ASSIGNS {column!r} — this change is "
                    f"capture-only and must never re-grade (gotcha #21)"
                )
