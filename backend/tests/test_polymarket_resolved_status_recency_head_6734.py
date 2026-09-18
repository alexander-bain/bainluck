"""#6734 — the sweep that drains `open` rows never reached the rows that closed today.

`d0800601a` fixed the **writer**: it stops a sub-market the venue has closed from
being stamped `open` again. That half is forward-only by construction, and the
stock it cannot reach turned out to be the bigger number.

What was measured on production 2026-09-18 (`artifacts-446/`)
-------------------------------------------------------------
A random 200 of the 3,939 Polymarket sub-markets stored `open` and untouched for
6h+: **10 are CLOSED and UMA-resolved at the venue while we stamp `open`**, and
**7 of those are structurally stuck rather than in-flight lag** — closed 6.8 to
14.9 hours earlier by the venue's own `closedTime`, across one to two full cycles
of the sweep that exists to drain them.

Four checks, each made because the previous one came back innocent:

1. The venue read is fine — `/events?id=…` returns all seven events, every child
   `closed: true` / `umaResolutionStatus: resolved`.
2. The classifier is fine — `settled_legs()` on that exact payload returns
   settled 16 / open 0, so the CERT-751 mixed-children guard is inert here.
3. Id matching is fine — every condition id matches the venue's payload exactly.
4. **Reach is the defect.** Per-minute id bands of the resolves each of the four
   2026-09-17 runs wrote:

   | sweep  | first band | last band     | stopped |
   |--------|------------|---------------|---------|
   | 05:30Z | 329,566    | **1,017,957** | 05:39   |
   | 11:30Z | 1,024,503  | **1,037,305** | 11:33   |
   | 17:30Z | 13,362     | **992,846**   | 17:37   |
   | 23:30Z | 10,017     | **1,010,496** | 23:39   |

   Three of four started at the BOTTOM of the range and exhausted the 600s budget
   around 1.0M, short of the 1,028,971–1,036,113 band where all seven stuck
   specimens live. 7,486 of the 17,560 events in the population sit above the
   23:30Z stopping point — 43% of it, unvisited. A run that does reach the tail
   wraps the cursor to 0, so the next one starts at the oldest id again.

The low band is not dead weight (23:30Z resolved 961 rows in its first minute at
ids 10,017–119,097), so the repair is not "walk newest-first" — that starves the
backlog, gotcha #41's first clause, and the backlog is productive. It is
gotcha #41's actual prescription: **both bounds**. The newest slice gets a
guaranteed, bounded share of the wall clock first; the ascending cursor keeps the
rest and its own progress.

What a reader was seeing, and why it compounds
----------------------------------------------
`GET /api/events/15313889/game-markets` served market `61262638` at
`probability 1.0, is_winner null, resolution_source null` — 7.5h after the venue
closed and resolved it — directly beneath its own mirror handicap that IS graded.
And `clob_resolve` selects `WHERE fm.source='polymarket' AND fm.status='resolved'`
(`tasks/clob_resolve.py:318`), so a row stranded at `open` is invisible to the
grader too: it can never acquire the verdict that would make it render correctly.

What these guards pin
---------------------
Ordering, and only ordering. `settled_legs`, the UPDATE and the mixed-children
guard are untouched by this change, so the head cannot resolve anything the
cursor would not have resolved on reaching it. The properties that must not
regress are therefore about WHICH ids arrive first, that the head is bounded,
and that it never touches the cursor the backlog walks on.

Every assertion here is clock-free: it reads the ORDER of the calls the task
made, never how long it took (gotcha #44 — a test anchor that branches on the
clock is not an anchor).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

import app.services.polymarket_api as poly_api_mod
import app.tasks.polymarket as poly_mod
import app.tasks.redis_state as redis_state
from app.utils.polymarket_settlement_scan import GAMMA_MAX_IDS_PER_REQUEST

#: Must match `_sync_polymarket_resolved_status`'s own constant. Stated here
#: rather than imported because it is a local in the task: if it moves, these
#: guards should fail loudly rather than silently re-derive the new value and
#: assert nothing (a guard that computes its own expectation from the code under
#: test measures nothing).
HEAD_EVENTS = 4000

CURSOR_KEY = "bainluck:polymarket_resolved_sync:cursor"


class _RecordingRedis:
    """A fake Redis that remembers the ORDER of cursor writes.

    One instance is shared across every `get_redis_client()` call in a run — the
    sibling file's fake hands out a fresh one each time, which is fine for its
    questions and useless for these: "did the head write the cursor" is a
    question about a sequence, and a new dict per call has no sequence.
    """

    def __init__(self):
        self.store = {}
        self.setex_calls = []
        self.deleted = []

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = str(value)
        self.setex_calls.append((key, str(value)))

    def delete(self, key):
        self.store.pop(key, None)
        self.deleted.append(key)
        return 1


def _open_event(eid):
    """An event the venue still trades. Costs the sweep a read and no write."""
    return {
        "id": str(eid),
        "closed": False,
        "markets": [
            {
                "conditionId": f"0x{eid:x}",
                "closed": False,
                "outcomePrices": '["0.54", "0.46"]',
            }
        ],
    }


def _closed_event(eid):
    """An event the venue has closed and resolved — the thing to be drained."""
    return {
        "id": str(eid),
        "closed": True,
        "markets": [
            {
                "conditionId": f"0x{eid:x}",
                "closed": True,
                "umaResolutionStatus": "resolved",
                "outcomePrices": '["0", "1"]',
            }
        ],
    }


class _Harness:
    """Drives the real task against a fake Gamma, recording call order."""

    def __init__(self, events):
        self.events = list(events)
        self.by_id = {str(e["id"]): e for e in self.events}
        self.statements = []
        self.id_calls = []
        self.redis = _RecordingRedis()

    def install(self, monkeypatch):
        monkeypatch.setattr(
            redis_state, "get_redis_client", lambda *a, **k: self.redis
        )

        class _Scalar:
            def __init__(self, v):
                self._v = v

            def scalar(self):
                return self._v

        class _Rows:
            def __init__(self, rows):
                self._rows = rows

            def fetchall(self):
                return self._rows

        harness = self

        async def _execute(stmt, params=None):
            sql = str(getattr(stmt, "text", stmt))
            if "ORDER BY eid::bigint" in sql:
                # The population, ascending — exactly what production returns.
                return _Rows([(str(e["id"]),) for e in harness.events])
            if "commence_time" in sql and "count(*)" in sql:
                return _Scalar(3939)
            if "COUNT(*)" in sql or "count(*)" in sql:
                return _Scalar(5)
            harness.statements.append((sql, dict(params or {})))
            return MagicMock(rowcount=1)

        session = AsyncMock()
        session.execute = AsyncMock(side_effect=_execute)
        session.commit = AsyncMock()

        class _CM:
            async def __aenter__(self):
                return session

            async def __aexit__(self, *a):
                return False

        monkeypatch.setattr(poly_mod, "get_task_session", lambda: _CM())

        class _Service:
            def __init__(self, *a, **k):
                pass

            async def get_events(self, **kw):
                return []

            async def get_events_by_ids(self, event_ids):
                harness.id_calls.append([str(i) for i in event_ids])
                return [
                    harness.by_id[str(i)]
                    for i in event_ids
                    if str(i) in harness.by_id
                ]

            async def close(self):
                return None

        monkeypatch.setattr(poly_api_mod, "PolymarketAPIService", _Service)
        return self

    @property
    def requested(self):
        """Every id the run asked Gamma for, in order."""
        return [eid for batch in self.id_calls for eid in batch]

    @property
    def resolve_params(self):
        return [
            p
            for s, p in self.statements
            if "UPDATE futures_markets" in s and "status = 'resolved'" in s
        ]


def _population(n, first_id=1_000_000, closed_ids=()):
    """`n` events ascending by id, as Gamma numbers them: newest id is newest."""
    closed = set(closed_ids)
    return [
        _closed_event(first_id + i) if (first_id + i) in closed
        else _open_event(first_id + i)
        for i in range(n)
    ]


@pytest.mark.asyncio
class TestTheNewestEventsAreReachedFirst:
    async def test_the_first_batch_is_the_newest_ids_not_the_oldest(
        self, monkeypatch
    ):
        """The defect, stated as an order.

        4,500 events: pre-fix the run opens on ids 1,000,000–1,000,099, the
        oldest hundred, and only arrives at today's closures ~44 batches later
        (on production, after the budget had already expired). This is the
        assertion that fails on the pre-fix tree.
        """
        h = _Harness(_population(4500)).install(monkeypatch)
        await poly_mod._sync_polymarket_resolved_status()

        newest_hundred = [
            str(i) for i in range(1_004_499, 1_004_499 - GAMMA_MAX_IDS_PER_REQUEST, -1)
        ]
        assert h.id_calls[0] == newest_hundred

    async def test_the_head_is_walked_newest_first_within_itself(
        self, monkeypatch
    ):
        """A truncated head must drop its OLD end, never the fresh one.

        The head is the only arm that can be cut off by its own budget, so the
        direction it walks decides what a short run loses. Ascending inside the
        head would lose exactly the freshest ids — the defect, rebuilt inside
        the fix.
        """
        h = _Harness(_population(4500)).install(monkeypatch)
        await poly_mod._sync_polymarket_resolved_status()

        head_requested = h.requested[:HEAD_EVENTS]
        assert head_requested == sorted(head_requested, key=int, reverse=True)
        assert head_requested[0] == "1004499"
        assert head_requested[-1] == str(1_004_499 - HEAD_EVENTS + 1)

    async def test_a_freshly_closed_newest_event_is_resolved_in_the_same_run(
        self, monkeypatch
    ):
        """The ship, not the mechanism: the row a reader was seeing drains."""
        h = _Harness(
            _population(4500, closed_ids=(1_004_499,))
        ).install(monkeypatch)
        await poly_mod._sync_polymarket_resolved_status()

        resolved_cids = [
            cid for p in h.resolve_params for cid in p.get("raw_cids", [])
        ]
        assert f"0x{1_004_499:x}" in resolved_cids


@pytest.mark.asyncio
class TestTheHeadNeverTouchesTheBacklogCursor:
    async def test_no_cursor_is_written_while_the_head_drains(self, monkeypatch):
        """The head holds the HIGHEST ids in the population.

        Writing one into the cursor would jump the ascending walk past every id
        it has not read yet, and the backlog would be declared swept without
        being visited — a far worse bug than the one being fixed, and an
        invisible one, because the run's own counters would look healthy.
        """
        h = _Harness(_population(4500)).install(monkeypatch)
        await poly_mod._sync_polymarket_resolved_status()

        head_batches = HEAD_EVENTS // GAMMA_MAX_IDS_PER_REQUEST
        assert len(h.id_calls) > head_batches, "the run never left the head"

        # Not one cursor write may name an id from the head band.
        head_ids = {str(i) for i in range(1_004_499, 1_004_499 - HEAD_EVENTS, -1)}
        written = [v for _, v in h.redis.setex_calls]
        assert not (set(written) & head_ids)

    async def test_the_first_cursor_written_belongs_to_the_backlog(
        self, monkeypatch
    ):
        """Positive form of the guard above.

        "No head id was written" is also satisfied by a run that writes no
        cursor at all, which would silently stop the backlog resuming. So pin
        what the first write IS: the last id of the first ascending batch.
        """
        h = _Harness(_population(4500)).install(monkeypatch)
        await poly_mod._sync_polymarket_resolved_status()

        assert h.redis.setex_calls, "the backlog stopped recording its progress"
        key, first_value = h.redis.setex_calls[0]
        assert key == CURSOR_KEY
        assert first_value == str(1_000_000 + GAMMA_MAX_IDS_PER_REQUEST - 1)


@pytest.mark.asyncio
class TestTheBacklogIsNotStarved:
    async def test_the_oldest_id_is_still_reached_in_the_same_run(
        self, monkeypatch
    ):
        """Gotcha #41's first clause is the failure mode on the other side.

        The 23:30Z production run resolved 961 rows in its first minute at ids
        10,017–119,097: the old band is a real backlog, not dead weight. An arm
        that fixes recency by abandoning it trades one starvation for another.
        """
        h = _Harness(_population(4500)).install(monkeypatch)
        await poly_mod._sync_polymarket_resolved_status()

        assert "1000000" in h.requested

    async def test_the_backlog_resumes_ascending_where_the_head_ends(
        self, monkeypatch
    ):
        """The head is a detour, not a re-ordering of the walk itself."""
        h = _Harness(_population(4500)).install(monkeypatch)
        await poly_mod._sync_polymarket_resolved_status()

        head_batches = HEAD_EVENTS // GAMMA_MAX_IDS_PER_REQUEST
        tail_requested = h.requested[HEAD_EVENTS:]
        assert h.id_calls[head_batches][0] == "1000000"
        assert tail_requested == sorted(tail_requested, key=int)


@pytest.mark.asyncio
class TestTheArmIsBoundedAndDoesNotDoubleWork:
    async def test_no_event_is_asked_for_twice(self, monkeypatch):
        """The head is carved OUT of the walk, not laid on top of it.

        Without the `head_set` exclusion the newest 4,000 would be fetched
        twice per run — 40 wasted Gamma calls out of a budget whose shortage is
        the whole defect.
        """
        h = _Harness(_population(4500)).install(monkeypatch)
        await poly_mod._sync_polymarket_resolved_status()

        requested = h.requested
        assert len(requested) == len(set(requested)) == 4500

    async def test_a_population_smaller_than_the_head_is_swept_exactly_once(
        self, monkeypatch
    ):
        """The boundary: head larger than the population.

        `all_ids[-4000:]` on a 50-event list is all 50, so the tail must come
        out empty rather than replaying them.
        """
        h = _Harness(_population(50)).install(monkeypatch)
        stats = await poly_mod._sync_polymarket_resolved_status()

        requested = h.requested
        assert len(requested) == len(set(requested)) == 50
        assert stats["swept_full_population"] is True

    async def test_the_run_reports_how_much_of_the_head_it_actually_swept(
        self, monkeypatch
    ):
        """"The head swept clean" and "the head ran out of time" must not
        return the same shape (gotcha #53). A run whose head was truncated is
        the signal that the budget needs re-sizing, and it is invisible unless
        the skipped count is carried separately from the head size."""
        h = _Harness(_population(4500)).install(monkeypatch)
        stats = await poly_mod._sync_polymarket_resolved_status()

        assert stats["head_events"] == HEAD_EVENTS
        assert stats["head_events_swept"] == HEAD_EVENTS
        assert stats["head_events_skipped"] == 0
