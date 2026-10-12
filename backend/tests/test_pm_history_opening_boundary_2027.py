"""#2027 — the CLOB-history rail never banks a post-resolution quote as an opening.

`_backfill_polymarket_price_history` used to stamp the FIRST history point as
`opening_probability` with no capture time and no resolution check, so a market
first priced after it settled banked its settled 0.99 as the opening. These
tests start the real function (fake DB session + fake venue client, no network)
on pre-resolution, post-resolution, missing-boundary and side-identity rows.
"""

from __future__ import annotations

import asyncio
from collections import namedtuple
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest

import app.services.polymarket_api as pm_api
import app.tasks.polymarket as pm
from app.tasks.polymarket import (
    HISTORY_OPENING_HINDSIGHT,
    HISTORY_OPENING_NO_BOUNDARY,
    HISTORY_OPENING_NO_INTERIOR_QUOTE,
    HISTORY_OPENING_OK,
    choose_history_opening,
    history_token_for_outcome,
)

BOUNDARY = datetime(2026, 1, 1, tzinfo=timezone.utc)
CID = "0xabc123"
Row = namedtuple(
    "Row", "id external_id market_external_id resolution_date settled_at"
)


def _ts(dt: datetime) -> int:
    return int(dt.timestamp())


class _Result:
    def __init__(self, rows=None, rowcount=None):
        self._rows = rows or []
        self.rowcount = rowcount

    def fetchall(self):
        return self._rows


class _Session:
    def __init__(self, rows, update_rowcount):
        self.rows = rows
        self.update_rowcount = update_rowcount
        self.selects: list[str] = []
        self.updates: list[tuple[str, dict]] = []
        self.inserts = 0
        self.committed = False

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "UPDATE futures_outcomes" in sql:
            self.updates.append((sql, dict(params or {})))
            return _Result(rowcount=self.update_rowcount)
        if "SELECT fo.id" in sql:
            self.selects.append(sql)
            return _Result(rows=self.rows)
        self.inserts += 1
        return _Result()

    async def commit(self):
        self.committed = True


class _Service:
    def __init__(self, clob_ids, history_by_token):
        self.clob_ids = clob_ids
        self.history_by_token = history_by_token
        self.tokens_asked: list[str] = []

    async def get_event_by_id(self, event_id):
        return {"markets": [{"conditionId": CID, "clobTokenIds": self.clob_ids}]}

    async def get_prices_history(self, token_id, interval, fidelity):
        self.tokens_asked.append(token_id)
        return self.history_by_token.get(token_id, [])

    async def close(self):
        pass


def _run(monkeypatch, rows, history_by_token, clob_ids='["tok_yes","tok_no"]',
         update_rowcount=1, mode="resolved_zero"):
    session = _Session(rows, update_rowcount)
    service = _Service(clob_ids, history_by_token)

    @asynccontextmanager
    async def fake_session():
        yield session

    async def no_sleep(_):
        return None

    monkeypatch.setattr(pm, "get_task_session", fake_session)
    monkeypatch.setattr(pm_api, "PolymarketAPIService", lambda: service)
    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    stats = asyncio.run(pm._backfill_polymarket_price_history(limit=10, mode=mode))
    return stats, session, service


def _row(external_id=f"{CID}_yes", resolution_date=BOUNDARY, settled_at=None):
    return Row(1, external_id, "evt1", resolution_date, settled_at)


# ── the real rail ────────────────────────────────────────────────────────────


def test_pre_resolution_quote_is_stamped_with_its_own_capture_time(monkeypatch):
    quote_at = BOUNDARY - timedelta(days=1)
    stats, session, _ = _run(
        monkeypatch, [_row()], {"tok_yes": [{"t": _ts(quote_at), "p": 0.45}]}
    )
    assert stats["errors"] == []
    assert len(session.updates) == 1
    sql, params = session.updates[0]
    assert params["price"] == 0.45
    assert params["captured_at"] == quote_at
    assert "opening_captured_at = :captured_at" in sql
    assert "opening_source = 'clob_history'" in sql
    assert stats["opening_written"] == 1
    assert stats["opening_refused_hindsight"] == 0


def test_single_post_resolution_point_is_not_an_opening(monkeypatch):
    """The coordinator's specimen: one point, so no ordering assumption."""
    quote_at = BOUNDARY + timedelta(days=1)
    stats, session, _ = _run(
        monkeypatch, [_row()], {"tok_yes": [{"t": _ts(quote_at), "p": 0.99}]}
    )
    assert session.updates == []
    assert stats["opening_refused_hindsight"] == 1
    assert stats["opening_written"] == 0
    # The observation itself is still kept as a dated snapshot.
    assert stats["snapshots_created"] == 1
    assert session.inserts == 1
    assert stats["outcomes_processed"] == 1


def test_missing_resolution_boundary_fails_closed(monkeypatch):
    quote_at = BOUNDARY - timedelta(days=1)
    stats, session, _ = _run(
        monkeypatch,
        [_row(resolution_date=None, settled_at=BOUNDARY)],
        {"tok_yes": [{"t": _ts(quote_at), "p": 0.45}]},
    )
    assert session.updates == []
    assert stats["opening_refused_no_boundary"] == 1
    assert stats["snapshots_created"] == 1


def test_an_early_observed_settlement_tightens_the_boundary(monkeypatch):
    """Scheduled to close Jan 1, seen settled Dec 1: a Dec 15 quote is hindsight."""
    settled = BOUNDARY - timedelta(days=31)
    quote_at = BOUNDARY - timedelta(days=17)
    stats, session, _ = _run(
        monkeypatch,
        [_row(settled_at=settled)],
        {"tok_yes": [{"t": _ts(quote_at), "p": 0.97}]},
    )
    assert session.updates == []
    assert stats["opening_refused_hindsight"] == 1


def test_earliest_pre_boundary_quote_wins_whatever_the_list_order(monkeypatch):
    early = BOUNDARY - timedelta(days=3)
    mid = BOUNDARY - timedelta(days=2)
    late = BOUNDARY + timedelta(days=1)
    history = [
        {"t": _ts(late), "p": 0.99},
        {"t": _ts(mid), "p": 0.42},
        {"t": _ts(early), "p": 0.40},
    ]
    stats, session, _ = _run(monkeypatch, [_row()], {"tok_yes": history})
    assert len(session.updates) == 1
    _, params = session.updates[0]
    assert (params["price"], params["captured_at"]) == (0.40, early)
    assert stats["snapshots_created"] == 3


def test_an_existing_opening_is_kept_and_counted(monkeypatch):
    quote_at = BOUNDARY - timedelta(days=1)
    stats, session, _ = _run(
        monkeypatch,
        [_row()],
        {"tok_yes": [{"t": _ts(quote_at), "p": 0.45}]},
        update_rowcount=0,
    )
    sql, _ = session.updates[0]
    assert "AND opening_probability IS NULL" in sql
    assert stats["opening_kept_existing"] == 1
    assert stats["opening_written"] == 0


def test_no_interior_quote_is_counted_not_written(monkeypatch):
    quote_at = BOUNDARY - timedelta(days=1)
    stats, session, _ = _run(
        monkeypatch, [_row()], {"tok_yes": [{"t": _ts(quote_at), "p": 1.0}]}
    )
    assert session.updates == []
    assert stats["opening_no_interior_quote"] == 1


def test_under_leg_reads_the_under_token_not_the_over_token(monkeypatch):
    quote_at = BOUNDARY - timedelta(days=1)
    stats, session, service = _run(
        monkeypatch,
        [_row(external_id=f"{CID}_no")],
        {
            "tok_yes": [{"t": _ts(quote_at), "p": 0.70}],
            "tok_no": [{"t": _ts(quote_at), "p": 0.30}],
        },
    )
    assert service.tokens_asked == ["tok_no"]
    assert session.updates[0][1]["price"] == 0.30


def test_under_leg_without_its_own_token_is_skipped(monkeypatch):
    quote_at = BOUNDARY - timedelta(days=1)
    stats, session, service = _run(
        monkeypatch,
        [_row(external_id=f"{CID}_no")],
        {"tok_yes": [{"t": _ts(quote_at), "p": 0.70}]},
        clob_ids='["tok_yes"]',
    )
    assert service.tokens_asked == []
    assert session.updates == []
    assert stats["outcomes_skipped"] == 1


@pytest.mark.parametrize("mode", ["resolved_zero", "open_sparse"])
def test_both_population_reads_carry_the_boundary(monkeypatch, mode):
    quote_at = BOUNDARY + timedelta(days=1)
    stats, session, _ = _run(
        monkeypatch,
        [_row(external_id=CID)],
        {"tok_yes": [{"t": _ts(quote_at), "p": 0.99}]},
        mode=mode,
    )
    assert "fm.resolution_date" in session.selects[0]
    assert "fm.settled_at" in session.selects[0]
    assert session.updates == []
    assert stats["opening_refused_hindsight"] == 1


# ── the pure helpers ─────────────────────────────────────────────────────────


def test_a_quote_exactly_at_the_boundary_is_still_a_price():
    """`<=` is the complement of the reader's `opening_captured_at > resolution_date`."""
    verdict, point = choose_history_opening([(BOUNDARY, 0.5)], BOUNDARY, None)
    assert verdict == HISTORY_OPENING_OK and point == (BOUNDARY, 0.5)
    verdict, _ = choose_history_opening(
        [(BOUNDARY + timedelta(seconds=1), 0.5)], BOUNDARY, None
    )
    assert verdict == HISTORY_OPENING_HINDSIGHT


def test_naive_boundary_reads_as_utc():
    naive = BOUNDARY.replace(tzinfo=None)
    verdict, _ = choose_history_opening(
        [(BOUNDARY - timedelta(hours=1), 0.5)], naive, None
    )
    assert verdict == HISTORY_OPENING_OK


def test_a_later_observed_settlement_does_not_loosen_the_boundary():
    verdict, _ = choose_history_opening(
        [(BOUNDARY + timedelta(days=1), 0.5)],
        BOUNDARY,
        BOUNDARY + timedelta(days=5),
    )
    assert verdict == HISTORY_OPENING_HINDSIGHT


def test_unparseable_boundary_fails_closed():
    verdict, _ = choose_history_opening([(BOUNDARY, 0.5)], "2026-01-01", None)
    assert verdict == HISTORY_OPENING_NO_BOUNDARY
    verdict, _ = choose_history_opening([], BOUNDARY, None)
    assert verdict == HISTORY_OPENING_NO_INTERIOR_QUOTE


def test_token_choice_follows_the_outcome_side():
    ids = {"0xee": ["y", "n"]}
    assert history_token_for_outcome("0xee", ids) == "y"
    assert history_token_for_outcome("0xee_yes", ids) == "y"
    assert history_token_for_outcome("0xee_no", ids) == "n"
    # `rstrip("_yes")` would have eaten the trailing `ee` of the condition id.
    assert history_token_for_outcome("0xee_yes", {"0x": ["wrong"], **ids}) == "y"
    assert history_token_for_outcome("0xee_no", {"0xee": ["y"]}) is None
    assert history_token_for_outcome("0xff_yes", ids) is None


# ── open_sparse identity + one bad event never aborts its siblings ──────────
# Production 2026-10-12 15:18Z: open_sparse sent `fm.external_id` (a condition
# hash) to Gamma's /events/{id}, Gamma answered 422, `get_event_by_id` re-raised
# outside any per-event guard, and the task-level catch ended the pass with zero
# work for every healthy event behind it.

import httpx  # noqa: E402

GOOD_QUOTE_AT = BOUNDARY - timedelta(days=2)


def _http_error(code: int) -> httpx.HTTPStatusError:
    req = httpx.Request("GET", "https://gamma-api.polymarket.com/events/x")
    return httpx.HTTPStatusError("refused", request=req, response=httpx.Response(code, request=req))


class _RefusingService(_Service):
    """Raises the given status for the named event ids, answers the rest."""

    def __init__(self, refusals: dict, *args):
        super().__init__(*args)
        self.refusals = refusals
        self.events_asked: list = []

    async def get_event_by_id(self, event_id):
        self.events_asked.append(event_id)
        if event_id in self.refusals:
            raise _http_error(self.refusals[event_id])
        return await super().get_event_by_id(event_id)


def _run_refusing(monkeypatch, rows, refusals, mode="open_sparse"):
    session = _Session(rows, 1)
    service = _RefusingService(
        refusals, '["tok_yes","tok_no"]', {"tok_yes": [{"t": _ts(GOOD_QUOTE_AT), "p": 0.4}]}
    )

    @asynccontextmanager
    async def fake_session():
        yield session

    async def no_sleep(_):
        return None

    monkeypatch.setattr(pm, "get_task_session", fake_session)
    monkeypatch.setattr(pm_api, "PolymarketAPIService", lambda: service)
    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    stats = asyncio.run(pm._backfill_polymarket_price_history(limit=10, mode=mode))
    return stats, session, service


def _event_row(oid: int, event_id):
    return Row(oid, f"{CID}_yes", event_id, BOUNDARY, None)


@pytest.mark.parametrize("mode", ["open_sparse", "resolved_zero"])
def test_a_provider_422_on_one_event_leaves_the_healthy_sibling_done(monkeypatch, mode):
    stats, session, service = _run_refusing(
        monkeypatch, [_event_row(1, "0xconditionhash"), _event_row(2, "12345")],
        {"0xconditionhash": 422}, mode=mode,
    )
    assert service.events_asked == ["0xconditionhash", "12345"]
    assert stats["events_provider_refused"] == 1
    assert stats["events_fetched"] == 1
    assert stats["outcomes_processed"] == 1
    assert stats["opening_written"] == 1
    assert [u[1]["oid"] for u in session.updates] == [2]
    assert session.committed is True
    assert not any(e.startswith("task_error") for e in stats["errors"])


def test_a_429_ends_the_pass_but_keeps_the_work_already_done(monkeypatch):
    stats, session, service = _run_refusing(
        monkeypatch,
        [_event_row(1, "111"), _event_row(2, "222"), _event_row(3, "333")],
        {"222": 429},
    )
    assert service.events_asked == ["111", "222"]  # 333 never asked
    assert stats["rate_limited"] is True
    assert stats["events_provider_refused"] == 0
    assert stats["opening_written"] == 1
    assert session.committed is True


@pytest.mark.parametrize("missing", [None, ""])
def test_a_row_with_no_event_id_is_skipped_not_guessed(monkeypatch, missing):
    stats, session, service = _run_refusing(
        monkeypatch, [_event_row(1, missing), _event_row(2, "12345")], {},
    )
    assert service.events_asked == ["12345"]
    assert stats["outcomes_skipped_no_event_id"] == 1
    assert stats["opening_written"] == 1


def test_open_sparse_reads_the_gamma_event_identity_not_the_condition_hash(monkeypatch):
    stats, session, _ = _run_refusing(monkeypatch, [_event_row(1, "12345")], {})
    sql = " ".join(session.selects[0].split())
    assert "fm.external_id AS market_external_id" not in sql
    assert "market_metadata->>'polymarket_event_id'" in sql
    assert "left(fm.group_id, 11) = 'polymarket:'" in sql
    # identity-less rows never take a LIMIT slot
    where = sql.split("WHERE", 1)[1]
    assert "polymarket_event_id' IS NOT NULL" in where
