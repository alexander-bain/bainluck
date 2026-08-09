"""UX-P028 — the external-curator recall lane must be age-bounded.

The UX-P027 consumption census established that accepted rows in
``external_curator_ground_truth_items`` feed a LIVE Discover lane. This cycle's
production read established what was actually in that table: **three rows, last
imported 2026-05-19** — 82 days stale on the day of the fix — while the lane went
on seeding the candidate pool AND granting each matched market
``_EXTERNAL_CURATOR_RECALL_SCORE_BONUS`` (+25) on the ranking score.

So the lane was steering the default landing page from a fossil, silently. These
tests keep the age bound in place, and keep BOTH callers on the same clock.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.dialects import postgresql

import app.routes.feed as feed_mod
from app.utils.external_curator_freshness import RECALL_MAX_AGE_DAYS

NOW = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)


class _Result:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


class _FakeSession:
    """Records every statement, answers the two queries the lane issues."""

    def __init__(self, *, names, market_ids):
        self.statements = []
        self._responses = [_Result(names), _Result(market_ids)]

    async def execute(self, statement):
        self.statements.append(statement)
        return self._responses.pop(0)


def _compiled(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


@pytest.mark.asyncio
async def test_row_query_bounds_imported_at_by_the_recall_cutoff():
    db = _FakeSession(names=["France to win the 2026 World Cup"], market_ids=[7])
    await feed_mod._external_curator_recall_market_ids(db, [], now=NOW)

    sql = _compiled(db.statements[0])
    cutoff = (NOW - timedelta(days=RECALL_MAX_AGE_DAYS)).isoformat()

    assert "imported_at" in sql
    assert cutoff[:10] in sql, (
        "the curator row query must filter on the freshness cutoff; without it a "
        "dead producer keeps boosting Discover rank forever"
    )


@pytest.mark.asyncio
async def test_a_stale_corpus_yields_no_recall_and_therefore_no_bonus():
    """Fail closed. No ids returned means no pool seeding AND no +25, because
    the bonus keys off membership in this very id set."""
    db = _FakeSession(names=[], market_ids=[])
    ids = await feed_mod._external_curator_recall_market_ids(db, [], now=NOW)

    assert ids == []
    # It must not even reach the market query — no names, nothing to match.
    assert len(db.statements) == 1


@pytest.mark.asyncio
async def test_a_fresh_corpus_still_recalls_normally():
    """Both directions (gotcha #43): the bound must not disable a healthy lane."""
    db = _FakeSession(
        names=["France to win the 2026 World Cup"], market_ids=[11, 12, 13]
    )
    ids = await feed_mod._external_curator_recall_market_ids(db, [], now=NOW)

    assert ids == [11, 12, 13]
    assert len(db.statements) == 2


@pytest.mark.asyncio
async def test_blank_names_are_skipped_without_killing_the_lane():
    db = _FakeSession(names=["", "   ", "Real market name"], market_ids=[42])
    ids = await feed_mod._external_curator_recall_market_ids(db, [], now=NOW)
    assert ids == [42]


def test_both_callers_pass_their_own_now_to_the_recall_lane():
    """The trace and the production builder must age the corpus on the SAME
    clock they build the rest of the pools on — a second `datetime.now()` inside
    the lane would be a second source of truth for 'today'."""
    for name, fn in (
        ("trace", feed_mod._discover_candidate_pool_trace),
        ("builder", feed_mod._compute_ordered_candidate_ids),
    ):
        src = inspect.getsource(fn)
        assert "now=now," in src, (
            f"{name} must pass its own `now` into _external_curator_recall_market_ids"
        )


def test_the_lane_documents_that_it_grants_the_rank_bonus():
    """It boosts rank by +25 while its old docstring said it did not.

    A docstring that contradicts the code is worse than none: the UX-P027 census
    read that one and repeated its claim as a finding. The doc must now name the
    bonus constant, so the next reader traces it to the scoring loop instead of
    trusting prose.
    """
    src = inspect.getsource(feed_mod._external_curator_recall_market_ids)
    assert "_EXTERNAL_CURATOR_RECALL_SCORE_BONUS" in src

    # And the bonus really is keyed off this lane's output, in both places.
    scoring_src = inspect.getsource(feed_mod)
    assert "rank_score += _EXTERNAL_CURATOR_RECALL_SCORE_BONUS" in scoring_src
