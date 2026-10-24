"""The MLB postseason reads every question it holds, a page at a time. #9886.

**SHIP: the automatic MLB postseason hub can include every eligible game
question instead of stopping at a truncated market slice.** (Pillars: MATCHING
/ DISCOVER / TRUTH.)

Authority's first enabled assembly (2026-10-24 01:49Z, retained under
`authority/artifacts-authority-5341-a2-20261023T2311Z/p2`) read 43 games and 39
of our rows, then stopped at 5,000 questions: 4,937 candidates + 63 game-winner
exclusions = the single read's cap, `markets_truncated: true`. The read now
pages on `fm.id`; each page is the same bounded statement the single read was,
and `MARKET_READ_MAX_PAGES` bounds how many run. These tests drive the real
harvest path (`run_mlb_postseason_assembly` → `assemble_container`) through the
v3 suite's in-memory session, which answers each page exactly as its SQL says.
"""

from __future__ import annotations

import pytest

from app.tasks.container_assembly import VENUE_FETCH_LIMIT, _one_collection_run
from app.tasks.container_mlb_playoffs_assembly import (
    MARKET_READ_MAX_PAGES,
    MARKETS_FOR_EVENTS_SQL,
    UNIDENTIFIED_IN_SPAN_SQL,
    gather_mlb_postseason_candidates,
    run_mlb_postseason_assembly,
)
from app.utils.container_mlb_playoffs import (
    INCOMPLETE_MARKETS_TRUNCATED,
    INCOMPLETE_NO_EVENT_ROW,
    INCOMPLETE_STRANDED_QUESTIONS,
    MarketRow,
)
from tests import test_container_mlb_playoffs_v3 as _v3
from tests.test_container_mlb_playoffs_v3 import (
    CWS_HOU_G2_EVENT,
    G1_EVENT,
    G2_EVENT,
    ODDS_TWIN,
    POST_2026,
    _boards,
    _Container,
    _edge_rows,
    _rows,
    _Session,
)

# The v3 suite's board fixtures, shared rather than copied.
corpus = _v3.corpus
g2 = _v3.g2

EVENTS = (G1_EVENT, G2_EVENT, CWS_HOU_G2_EVENT)


def _questions(n, *, start=70_000_000, step=3, events=EVENTS):
    """``n`` questions with gapped ids dealt round-robin across ``events``, so
    every page boundary falls between two different games' rows."""
    return [
        MarketRow(start + i * step, events[i % len(events)], f"Q{i}", f"KXMLBQ-{i}", "kalshi", "binary", "open")
        for i in range(n)
    ]


def _market_reads(session):
    return [p for s, p in session.reads if s == MARKETS_FOR_EVENTS_SQL]


def _market_candidates(report_or_harvest):
    members = report_or_harvest.members
    return [c.child_id for c in members.candidates if c.child_type == "market"]


@pytest.mark.asyncio
async def test_more_questions_than_one_page_are_all_read_and_the_postseason_is_complete(corpus):
    # The predecessor read ONE page of `limit` and called this partial.
    questions = _questions(11)
    session = _Session(_rows(), questions)
    report = await run_mlb_postseason_assembly(
        session, _Container(), _boards(corpus), POST_2026, apply=True, limit=3
    )
    assert report["terminal"] == "complete" and report["incomplete"] == []
    assert report["harvest"]["markets_truncated"] is False
    assert report["harvest"]["candidates"]["market"] == 11
    edged = sorted(e["child_id"] for e in _edge_rows(session) if e["child_type"] == "market")
    assert edged == [q.id for q in questions]
    ids = [q.id for q in questions]
    # Each page starts strictly after the last id the previous page KEPT.
    assert [(p["after_id"], p["limit"]) for p in _market_reads(session)] == [
        (0, 4), (ids[2], 4), (ids[5], 4), (ids[8], 4)
    ]


@pytest.mark.asyncio
async def test_no_id_is_skipped_or_read_twice_at_any_page_boundary(corpus):
    questions = _questions(23, step=7)
    for limit in (1, 2, 3, 5, 22, 23, 24):
        session = _Session(_rows(), questions)
        harvest = await gather_mlb_postseason_candidates(
            session, _boards(corpus), POST_2026, limit=limit, max_pages=23
        )
        # Ascending id order — the single read's order — exactly once each.
        assert _market_candidates(harvest) == [q.id for q in questions], limit
        assert harvest.markets_truncated is False, limit


@pytest.mark.asyncio
async def test_exactly_full_pages_need_no_empty_page_to_end(corpus):
    session = _Session(_rows(), _questions(6))
    harvest = await gather_mlb_postseason_candidates(session, _boards(corpus), POST_2026, limit=3)
    assert len(_market_reads(session)) == 2
    assert len(_market_candidates(harvest)) == 6 and harvest.markets_truncated is False


@pytest.mark.asyncio
async def test_a_population_that_exactly_fills_the_budget_is_complete(corpus):
    session = _Session(_rows(), _questions(6))
    report = await run_mlb_postseason_assembly(
        session, _Container(), _boards(corpus), POST_2026, limit=3, max_pages=2
    )
    assert report["terminal"] == "complete"
    assert report["harvest"]["markets_truncated"] is False


@pytest.mark.asyncio
async def test_one_question_past_the_budget_is_partial_and_keeps_the_rest(corpus):
    questions = _questions(7)
    session = _Session(_rows(), questions)
    report = await run_mlb_postseason_assembly(
        session, _Container(), _boards(corpus), POST_2026, apply=True, limit=3, max_pages=2
    )
    assert report["terminal"] == "partial"
    assert report["incomplete"] == [INCOMPLETE_MARKETS_TRUNCATED]
    assert report["harvest"]["markets_truncated"] is True
    assert len(_market_reads(session)) == 2  # the budget, never a third page
    edged = sorted(e["child_id"] for e in _edge_rows(session) if e["child_type"] == "market")
    # Deterministic: the first six by id survive, the seventh is not guessed at.
    assert edged == [q.id for q in questions[:6]]


@pytest.mark.asyncio
async def test_the_production_cap_no_longer_stops_a_postseason_at_one_read(corpus):
    # The retained harvest's shape: more questions than VENUE_FETCH_LIMIT, read
    # at the shipped defaults. The predecessor stopped at 5,000 → partial.
    n = VENUE_FETCH_LIMIT + 1_001
    session = _Session(_rows(), _questions(n, step=1))
    report = await run_mlb_postseason_assembly(session, _Container(), _boards(corpus), POST_2026)
    assert report["terminal"] == "complete"
    assert report["harvest"]["candidates"]["market"] == n
    assert len(_market_reads(session)) == 2
    assert MARKET_READ_MAX_PAGES * VENUE_FETCH_LIMIT > n


@pytest.mark.asyncio
async def test_a_small_postseason_is_still_one_read(corpus):
    session = _Session(_rows(), _questions(4))
    await gather_mlb_postseason_candidates(session, _boards(corpus), POST_2026)
    [read] = _market_reads(session)
    assert read["after_id"] == 0 and read["limit"] == VENUE_FETCH_LIMIT + 1


@pytest.mark.asyncio
async def test_truncation_keeps_every_other_reason_and_their_order(corpus):
    # A missing row, a capped read and stranded questions are all reported.
    twin_questions = [MarketRow(5, ODDS_TWIN.id, "x", "X", "kalshi", "binary", "open")]
    session = _Session(
        _rows(include=(G1_EVENT, G2_EVENT)),
        _questions(7, events=(G1_EVENT, G2_EVENT)) + twin_questions,
        unidentified=[ODDS_TWIN],
    )
    report = await run_mlb_postseason_assembly(
        session, _Container(), _boards(corpus), POST_2026, limit=3, max_pages=2
    )
    assert report["incomplete"] == [
        INCOMPLETE_NO_EVENT_ROW,
        INCOMPLETE_MARKETS_TRUNCATED,
        INCOMPLETE_STRANDED_QUESTIONS,
    ]
    assert report["reason"] == INCOMPLETE_NO_EVENT_ROW


class _FailingSession(_Session):
    """Raises on the Nth market page, as a statement timeout would."""

    def __init__(self, *args, fail_on_page, **kwargs):
        super().__init__(*args, **kwargs)
        self.fail_on_page = fail_on_page
        self.rolled_back = False

    async def execute(self, stmt, params=None):
        if getattr(stmt, "text", None) == MARKETS_FOR_EVENTS_SQL:
            if len(_market_reads(self)) + 1 == self.fail_on_page:
                raise RuntimeError("canceling statement due to statement timeout")
        return await super().execute(stmt, params)

    async def rollback(self):
        self.rolled_back = True


@pytest.mark.asyncio
async def test_a_failed_page_assembles_nothing_and_the_run_fails(corpus):
    session = _FailingSession(_rows(), _questions(11), fail_on_page=2)

    async def _run():
        return await run_mlb_postseason_assembly(
            session, _Container(), _boards(corpus), POST_2026, apply=True, limit=3
        )

    run = await _one_collection_run(session, POST_2026.slug, "mlb", _run, apply=True)
    assert run["terminal"] == "failed" and run["reason"] == "assembly_error"
    assert session.rolled_back and not session.committed
    assert session.writes == []
    # Nothing after the failed page ran: no report read, no partial harvest.
    assert UNIDENTIFIED_IN_SPAN_SQL not in [s for s, _ in session.reads]


@pytest.mark.asyncio
@pytest.mark.parametrize("budget", [{"limit": 0}, {"max_pages": 0}, {"limit": -1}])
async def test_a_zero_budget_is_refused_before_any_read(corpus, budget):
    # Zero pages would read no question and report none missing.
    session = _Session(_rows(), _questions(4))
    with pytest.raises(ValueError):
        await gather_mlb_postseason_candidates(session, _boards(corpus), POST_2026, **budget)
    assert session.reads == []
