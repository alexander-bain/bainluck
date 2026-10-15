"""#683 successor: continuation, the attended import's proofs, reader overlap, forecast guard.

PILLAR: TRUTH. SHIP: a settled Kalshi question with missing history gains its
real recoverable pre-resolution probability journey on web and native, with
archive provenance and honest forecast eligibility.

No provider, database or Redis is touched here. The real-Postgres half
(constraints, apply/restore, the two chart routes, the forecast lateral) is
``tests/integration/test_kalshi_archive_store_683_pg.py``.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import kalshi_archive_apply as imp
from app.services import kalshi_archive_recovery as rec
from app.utils import kalshi_archive_history as kah
from app.utils import kalshi_archive_reader as reader
from tests.test_kalshi_archive_recovery_683 import (
    E1,
    SETTLED,
    T1,
    TIPOFF,
    FakeService,
    FakeSession,
    _good_candles,
    _listed,
    _plan,
    _row,
    candle,
    payload_of,
)

UTC = timezone.utc
APP = Path(__file__).resolve().parents[1] / "app"

# A market that lives ~700 days: hourly, chunked into five 4,000-hour windows.
LONG_OPEN = SETTLED - timedelta(hours=4000 * 4 + 1000)


def _long_candles():
    """One priced candle per window, all before tip-off, so every window matters."""
    windows, _ = kah.request_windows(LONG_OPEN, SETTLED, 60)
    out = []
    for i, w in enumerate(windows):
        end = datetime.fromtimestamp(w.start_ts, tz=UTC) + timedelta(hours=3)
        if end < TIPOFF:
            out.append(candle(end, close=f"0.{40 + i}", volume="5.00"))
    return out, windows


class WindowedService(FakeService):
    """Answers each candle request with ONLY the candles inside its window."""

    async def get_historical_market_candlesticks_raw(
        self, ticker, *, period_interval, start_ts, end_ts
    ):
        self.calls.append(("candles", ticker, period_interval, start_ts, end_ts))
        self._maybe_raise()
        return [
            c
            for c in self.candles.get(ticker, [])
            if start_ts <= c["end_period_ts"] <= end_ts
        ]


def _long_service():
    candles, windows = _long_candles()
    svc = WindowedService(
        {E1: [([_listed(T1, E1, opened=LONG_OPEN)], None)]}, {T1: candles}
    )
    return svc, windows


def _candle_calls(svc):
    return [c for c in svc.calls if c[0] == "candles"]


# ── continuation: same bounded budget, no replay ──────────────────────────


class TestContinuation:
    async def test_a_long_outcome_completes_across_runs_at_the_same_budget(self):
        # Budget 3 = cutoff + listing + ONE window per run. Five windows owed.
        svc, windows = _long_service()
        r1 = await _plan(FakeSession([_row(1)]), svc, max_requests=3)
        assert r1["terminal"] == "partial" and r1["held_outcome"]["continuable"]
        carry = r1["continuation"]
        assert carry["stage"] == "candles" and len(carry["read_windows"]) == 1

        reads = [len(_candle_calls(svc))]
        report = r1
        for _ in range(10):
            svc2, _ = _long_service()
            report = await _plan(
                FakeSession([_row(1)]),
                svc2,
                max_requests=3,
                continuation=report["continuation"],
            )
            asked = [(c[3], c[4]) for c in _candle_calls(svc2)]
            # Never re-asks a window it carries.
            carried = {(w["start_ts"], w["end_ts"]) for w in carry["read_windows"]}
            assert not carried & set(asked)
            reads.append(len(asked))
            if report["continuation"] is None:
                break
            assert report["continuation_in"]["status"] == "resumed"
            carry = report["continuation"]
        assert report["terminal"] == "complete"
        assert sum(reads) == len(windows)  # every window asked exactly once overall

        whole_svc, _ = _long_service()
        whole = await _plan(FakeSession([_row(1)]), whole_svc, max_requests=60)
        assert report["plan_digest"] == whole["plan_digest"]
        assert report["importable_points"] == whole["importable_points"] > 0
        assert report["plans"][0]["coverage"] == "complete"
        assert len(report["plans"][0]["windows"]) == len(windows)

    async def test_the_budget_is_never_raised_to_finish(self):
        svc, _ = _long_service()
        r1 = await _plan(FakeSession([_row(1)]), svc, max_requests=3)
        svc2, _ = _long_service()
        r2 = await _plan(
            FakeSession([_row(1)]), svc2, max_requests=3, continuation=r1["continuation"]
        )
        assert r2["max_requests"] == 3 and r2["requests_sent"] <= 3

    async def test_tampered_carried_bytes_refuse_and_ask_nothing(self):
        svc, _ = _long_service()
        r1 = await _plan(FakeSession([_row(1)]), svc, max_requests=3)
        carry = copy.deepcopy(r1["continuation"])
        carry["read_windows"][0]["raw_body"] = carry["read_windows"][0][
            "raw_body"
        ].replace("0.40", "0.90")
        carry = kah.seal_continuation({k: v for k, v in carry.items() if k != "digest"})
        svc2, _ = _long_service()
        r2 = await _plan(FakeSession([_row(1)]), svc2, max_requests=3, continuation=carry)
        assert r2["continuation_in"]["status"] == "refused"
        assert r2["continuation_in"]["reason"] == "carry_raw:raw_sha256_mismatch"
        assert 1 in r2["owed_ids"] and _candle_calls(svc2) == []

    @pytest.mark.parametrize(
        "edit,reason",
        [
            (lambda c: c.update(version=2), "carry_version"),
            (lambda c: c.update(ticker="KXOTHER-1-A"), "carry_digest_mismatch"),
            (lambda c: c.update(period_minutes=1), "carry_digest_mismatch"),
        ],
    )
    async def test_a_carry_that_was_edited_after_sealing_refuses(self, edit, reason):
        svc, _ = _long_service()
        r1 = await _plan(FakeSession([_row(1)]), svc, max_requests=3)
        carry = copy.deepcopy(r1["continuation"])
        edit(carry)
        svc2, _ = _long_service()
        r2 = await _plan(FakeSession([_row(1)]), svc2, max_requests=3, continuation=carry)
        assert r2["continuation_in"]["reason"] == reason
        assert _candle_calls(svc2) == []

    async def test_resealed_window_bounds_that_a_fresh_plan_would_not_ask_refuse(self):
        svc, _ = _long_service()
        r1 = await _plan(FakeSession([_row(1)]), svc, max_requests=3)
        carry = copy.deepcopy(r1["continuation"])
        carry["read_windows"][0]["start_ts"] += 3600
        carry = kah.seal_continuation({k: v for k, v in carry.items() if k != "digest"})
        svc2, _ = _long_service()
        r2 = await _plan(FakeSession([_row(1)]), svc2, max_requests=3, continuation=carry)
        assert r2["continuation_in"]["reason"] == "carry_window_bounds_mismatch"

    async def test_a_carry_for_another_stored_identity_refuses(self):
        svc, _ = _long_service()
        r1 = await _plan(FakeSession([_row(1)]), svc, max_requests=3)
        other = _row(1, evt="KXNCAAMBSPREAD-26APR05OTHER")
        svc2, _ = _long_service()
        r2 = await _plan(
            FakeSession([other]), svc2, max_requests=3, continuation=r1["continuation"]
        )
        assert r2["continuation_in"]["reason"] == "carry_event_ticker_mismatch"

    async def test_a_held_listing_resumes_from_its_cursor_with_the_markets_it_read(self):
        sib = "KXNCAAMBSPREAD-26APR05OKLAWVU-SIB"
        pages = [
            ([_listed(sib, E1)], "1"),
            ([], "2"),
            ([_listed(T1, E1)], None),
        ]
        rows = [_row(1), _row(2, ticker=sib)]
        svc = FakeService({E1: pages}, {T1: _good_candles(), sib: _good_candles()})
        # cutoff + page 1 only: T1 (row 1, asked first) is held mid-listing.
        r1 = await _plan(FakeSession([rows[0]]), svc, max_requests=2)
        held = r1["continuation"]
        assert held["stage"] == "listing" and held["listing_cursor"] == "1"
        assert sib in held["listing_markets"]

        svc2 = FakeService({E1: pages}, {T1: _good_candles(), sib: _good_candles()})
        r2 = await _plan(FakeSession(rows), svc2, max_requests=40, continuation=held)
        listing_cursors = [c[2] for c in svc2.calls if c[0] == "listing"]
        assert listing_cursors == ["1", "2"]  # resumed; page 1 never re-read
        refusals = {p["ticker"]: p["refusal"] for p in r2["plans"]}
        assert refusals == {T1: None, sib: None}  # the sibling is not "absent"

    async def test_a_carry_never_reached_is_reported(self):
        svc, _ = _long_service()
        r1 = await _plan(FakeSession([_row(1)]), svc, max_requests=3)
        svc2 = FakeService({E1: [([_listed(T1, E1)], None)]}, {T1: _good_candles()})
        r2 = await _plan(
            FakeSession([_row(5)]), svc2, outcome_ids=[5], continuation=r1["continuation"]
        )
        assert r2["continuation_in"]["status"] == "not_reached"


# ── lineage on every planned point ────────────────────────────────────────


class TestLineage:
    async def test_every_point_names_the_bytes_it_came_from(self):
        svc = FakeService({E1: [([_listed(T1, E1)], None)]}, {T1: _good_candles()})
        report = await _plan(FakeSession([_row(1)]), svc)
        plan = report["plans"][0]
        window = plan["windows"][0]
        assert window["echoed_ticker"] == T1
        assert window["raw_sha256"] == hashlib.sha256(window["raw_body"].encode()).hexdigest()
        assert {p["raw_sha256"] for p in plan["points"]} == {window["raw_sha256"]}
        assert plan["input_fingerprint"] == kah.input_fingerprint(_row(1))

    async def test_a_body_naming_another_market_is_owed_not_filed(self):
        class Wrong(FakeService):
            async def get_historical_market_candlesticks_payload(self, ticker, **kw):
                return payload_of("KXOTHER-1-A", [], echoed="KXOTHER-1-A")

        svc = Wrong({E1: [([_listed(T1, E1)], None)]}, {T1: _good_candles()})
        report = await _plan(FakeSession([_row(1)]), svc)
        assert report["planned"] == 0 and 1 in report["owed_ids"]

    @pytest.mark.parametrize(
        "body,reason",
        [
            ({"candlesticks": []}, "ticker_missing"),
            ({"ticker": "KXOTHER", "candlesticks": []}, "ticker_mismatch"),
        ],
    )
    def test_the_payload_refuses_a_missing_or_foreign_echo(self, body, reason):
        from app.services.kalshi_api import (
            KalshiArchiveCandlePayload,
            KalshiArchiveResponseMalformed,
        )

        raw = json.dumps(body)
        with pytest.raises(KalshiArchiveResponseMalformed) as info:
            KalshiArchiveCandlePayload.from_raw(
                requested_ticker=T1,
                raw_body=raw,
                raw_sha256=hashlib.sha256(raw.encode()).hexdigest(),
                retrieved_at="x",
            )
        assert info.value.reason == reason


class TestExactIdsMayCarryLiveSnapshots:
    async def test_exact_id_with_live_snapshots_is_planned_and_counted(self):
        svc = FakeService({E1: [([_listed(T1, E1)], None)]}, {T1: _good_candles()})
        report = await _plan(
            FakeSession([_row(1, live_snapshots=4)]), svc, outcome_ids=[1]
        )
        assert report["planned"] == 1 and report["plans"][0]["live_snapshots"] == 4

    async def test_keyset_discovery_stays_the_zero_snapshot_cohort(self):
        svc = FakeService({E1: [([_listed(T1, E1)], None)]}, {T1: _good_candles()})
        report = await _plan(FakeSession([_row(1, live_snapshots=4)]), svc)
        assert report["candidates"] == 0
        assert "NOT EXISTS (" in rec._ID_AFTER and "NOT EXISTS" not in rec._ID_EXACT


# ── the import's proofs (pure half) ───────────────────────────────────────


async def _a_plan():
    svc = FakeService({E1: [([_listed(T1, E1)], None)]}, {T1: _good_candles()})
    return json.loads(json.dumps(await _plan(FakeSession([_row(1)]), svc), default=str))


class TestPlanDocument:
    async def test_a_true_plan_verifies_and_rederives(self):
        report = await _a_plan()
        plans = imp.verify_plan_document(report, report["plan_digest"])
        assert len(plans) == 1
        assert imp.rederivation_refusal(plans[0], report["archive_cutoff"]) is None

    async def test_the_operator_must_type_the_digest(self):
        report = await _a_plan()
        for typed in ("", "0" * 64):
            with pytest.raises(imp.PlanRefused) as info:
                imp.verify_plan_document(report, typed)
            assert info.value.reason == "expected_digest_mismatch"

    async def test_an_edited_point_changes_the_digest_and_refuses(self):
        report = await _a_plan()
        digest = report["plan_digest"]
        report["plans"][0]["points"][0]["probability"] = 0.99
        with pytest.raises(imp.PlanRefused) as info:
            imp.verify_plan_document(report, digest)
        assert info.value.reason == "plan_digest_mismatch"

    async def test_an_edited_point_with_a_recomputed_digest_does_not_follow_from_its_bytes(
        self,
    ):
        report = await _a_plan()
        report["plans"][0]["points"][0]["probability"] = 0.99
        report["plan_digest"] = kah.plan_digest(
            kah.PlannedPoint(**p) for p in report["plans"][0]["points"]
        )
        plans = imp.verify_plan_document(report, report["plan_digest"])
        assert (
            imp.rederivation_refusal(plans[0], report["archive_cutoff"])
            == "points_do_not_follow_from_raw"
        )

    async def test_tampered_window_bytes_refuse(self):
        report = await _a_plan()
        report["plans"][0]["windows"][0]["raw_body"] += " "
        assert imp.rederivation_refusal(
            report["plans"][0], report["archive_cutoff"]
        ).startswith("window_raw:raw_sha256_mismatch")

    async def test_a_plan_without_lineage_from_the_old_planner_refuses(self):
        report = await _a_plan()
        for p in report["plans"][0]["points"]:
            p["raw_sha256"] = None
        report["plan_digest"] = kah.plan_digest(
            kah.PlannedPoint(**p) for p in report["plans"][0]["points"]
        )
        plans = imp.verify_plan_document(report, report["plan_digest"])
        assert (
            imp.rederivation_refusal(plans[0], report["archive_cutoff"])
            == "points_do_not_follow_from_raw"
        )

    async def test_a_recent_tier_plan_refuses(self):
        report = await _a_plan()
        assert (
            imp.rederivation_refusal(report["plans"][0], SETTLED.isoformat())
            == "plan_not_archive_tier"
        )

    def test_not_a_dry_run_refuses(self):
        with pytest.raises(imp.PlanRefused) as info:
            imp.verify_plan_document({"mode": "apply"}, "x")
        assert info.value.reason == "not_a_dry_run_plan"


# ── reader overlap: live wins actual overlap only ─────────────────────────


def _row_at(oid, end, p=0.4, period=60):
    return reader.ArchiveRow(
        outcome_id=oid,
        captured_at=end,
        interval_start=end - timedelta(minutes=period),
        period_minutes=period,
        probability=p,
        price_basis="traded_interval",
    )


def _live(oid, at):
    return SimpleNamespace(outcome_id=oid, captured_at=at)


class TestReaderOverlap:
    T0 = datetime(2026, 4, 1, tzinfo=UTC)

    def _history(self, ends):
        h = reader.ArchiveHistory()
        h.rows = {1: [_row_at(1, self.T0 + timedelta(hours=x)) for x in ends]}
        h.state = "warm"
        return h

    def test_early_live_point_then_a_long_recoverable_gap_keeps_the_gap(self):
        h = self._history(range(1, 50))
        served = h.served(self.T0, [_live(1, self.T0 + timedelta(minutes=30))], [1])
        assert len(served[1]) == 48 and h.claimed_by_live == 1

    def test_a_live_point_inside_an_interval_withholds_only_that_interval(self):
        h = self._history([1, 2, 3])
        live = [_live(1, self.T0 + timedelta(hours=1, minutes=40))]
        served = h.served(self.T0, live, [1])
        assert [r.captured_at for r in served[1]] == [
            self.T0 + timedelta(hours=1),
            self.T0 + timedelta(hours=3),
        ]

    def test_both_interval_edges_are_overlap(self):
        h = self._history([2])
        for at in (self.T0 + timedelta(hours=1), self.T0 + timedelta(hours=2)):
            assert h.served(self.T0, [_live(1, at)], [1]) == {}

    def test_history_after_the_last_live_capture_stands(self):
        h = self._history([5, 6, 7])
        served = h.served(self.T0, [_live(1, self.T0 + timedelta(hours=2))], [1])
        assert len(served[1]) == 3

    def test_another_outcomes_capture_claims_nothing(self):
        h = self._history([1])
        assert len(h.served(self.T0, [_live(2, self.T0 + timedelta(hours=1))], [1])[1]) == 1

    def test_the_served_window_is_respected(self):
        h = self._history([1, 2, 3])
        served = h.served(self.T0 + timedelta(hours=2), [], [1])
        assert len(served[1]) == 2

    def test_a_long_line_is_compacted_by_value_and_keeps_both_endpoints(self):
        h = reader.ArchiveHistory()
        rows = [
            _row_at(1, self.T0 + timedelta(hours=x), p=0.3 + (x % 7) / 100)
            for x in range(1, 2001)
        ]
        h.rows = {1: rows}
        served = h.served(self.T0, [], [1])[1]
        assert len(served) <= reader.SERVE_TARGET_PER_OUTCOME + 2
        assert served[0] == rows[0] and served[-1] == rows[-1]
        assert h.compacted_from == {1: 2000}

    def test_points_are_drawn_as_intervals_with_provenance(self):
        row = _row_at(1, self.T0 + timedelta(hours=1))
        point = reader.history_point(row)
        assert point["provenance"] == point["bookmaker"] == "kalshi_archive"
        assert point["interval_start"] == self.T0.isoformat()
        assert point["period_minutes"] == 60 and point["price_basis"] == "traded_interval"

    async def test_a_non_kalshi_market_issues_no_query(self):
        class NoDb:
            async def execute(self, *a, **k):
                raise AssertionError("queried")

        h = await reader.load_archive_history(
            NoDb(), SimpleNamespace(source="polymarket"), [1], since=self.T0
        )
        assert h.state == "not_applicable" and h.rows == {}

    async def test_an_unreadable_store_never_fails_the_chart(self, monkeypatch):
        monkeypatch.setitem(reader._presence, "value", True)
        monkeypatch.setitem(reader._presence, "checked", 1e18)

        class Boom:
            def begin_nested(self):
                raise RuntimeError("no savepoint")

        h = await reader.load_archive_history(
            Boom(), SimpleNamespace(source="kalshi", id=1), [1], since=self.T0
        )
        assert h.state == "unavailable" and h.rows == {}


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)


class _FakeArchiveDb:
    """Answers the reader's three statements from in-memory rows; records each call."""

    def __init__(self, rows, evidence=()):
        self.rows, self.evidence, self.calls = rows, list(evidence), []

    def begin_nested(self):
        db = self

        class _Savepoint:
            async def __aenter__(self):
                return db

            async def __aexit__(self, *exc):
                return False

        return _Savepoint()

    async def execute(self, sql, params=None):
        self.calls.append((sql, dict(params or {})))
        if sql is reader.READ_SQL:
            out = []
            for oid in params["ids"]:
                mine = sorted(
                    (r for r in self.rows
                     if r.outcome_id == oid and r.interval_end >= params["since"]),
                    key=lambda r: r.interval_end, reverse=True,
                )
                out += mine[: params["cap"]]
            return _FakeResult(out)
        if sql is reader.SKELETON_SQL:
            out = []
            for oid in params["ids"]:
                mine = sorted((r for r in self.rows if r.outcome_id == oid),
                              key=lambda r: r.interval_end)
                n, k = len(mine), max(1, -(-len(mine) // params["cap"]))
                out += [r for i, r in enumerate(mine, 1)
                        if i == 1 or i == n or (i - 1) % k == 0]
            return _FakeResult(out)
        if sql is reader.EVIDENCE_SQL:
            return _FakeResult([e for e in self.evidence if e.outcome_id in params["ids"]])
        raise AssertionError(f"unexpected statement {sql}")


def _stored(oid, end):
    return SimpleNamespace(
        outcome_id=oid, interval_start=end - timedelta(hours=1), interval_end=end,
        period_minutes=60, probability=0.4, price_basis="traded_interval",
    )


class TestFullRange:
    """#683 Root FULL-RANGE finding: `range=full` reads the whole stored lifetime."""

    T0 = datetime(2026, 4, 1, tzinfo=UTC)

    @pytest.fixture(autouse=True)
    def _present(self, monkeypatch):
        monkeypatch.setitem(reader._presence, "value", True)
        monkeypatch.setitem(reader._presence, "checked", 1e18)

    @pytest.mark.parametrize(
        "value, full",
        [("full", True), (" FULL ", True), (None, False), ("", False),
         ("since_start", False), ("fullish", False)],
    )
    def test_only_the_literal_word_asks_for_the_lifetime(self, value, full):
        assert reader.wants_full_range(value) is full

    def test_a_direct_callers_unresolved_query_default_is_todays_read(self):
        from fastapi import Query

        assert reader.wants_full_range(Query(None, alias="range")) is False

    async def test_without_the_option_the_read_is_exactly_the_bounded_one(self):
        db = _FakeArchiveDb([_stored(1, self.T0 + timedelta(hours=h)) for h in range(1, 4)])
        since = self.T0 + timedelta(hours=2)
        h = await reader.load_archive_history(
            db, SimpleNamespace(source="kalshi", id=9), [1], since=since
        )
        assert [c[0] for c in db.calls] == [reader.READ_SQL]
        assert db.calls[0][1]["since"] == since
        assert h.thinned == [] and h.coverage == {} and h.venue_open == {}

    async def test_full_reads_from_the_floor_and_asks_the_skeleton_only_over_the_cap(
        self, monkeypatch
    ):
        monkeypatch.setattr(reader, "READ_CAP_PER_OUTCOME", 4)
        rows = [_stored(1, self.T0 + timedelta(hours=h)) for h in range(1, 12)]
        rows += [_stored(2, self.T0 + timedelta(hours=h)) for h in range(1, 3)]
        db = _FakeArchiveDb(rows, evidence=[
            SimpleNamespace(outcome_id=1, coverage="complete", venue_open_ts=self.T0),
        ])
        h = await reader.load_archive_history(
            db, SimpleNamespace(source="kalshi", id=9), [1, 2],
            since=self.T0 + timedelta(days=400), full_range=True,
        )
        calls = [c[0] for c in db.calls]
        assert calls == [reader.READ_SQL, reader.SKELETON_SQL, reader.EVIDENCE_SQL]
        assert db.calls[0][1]["since"] == reader.LIFETIME_FLOOR
        assert db.calls[1][1]["ids"] == [1]  # outcome 2 is under the cap: never re-read
        ends = [(r.captured_at - self.T0) // timedelta(hours=1) for r in h.rows[1]]
        assert ends == [1, 4, 7, 8, 9, 10, 11]
        assert h.thinned == [1] and h.read_capped == []
        assert len(h.rows[2]) == 2

    def _history(self, coverage=None, opens=None, thinned=()):
        h = reader.ArchiveHistory()
        h.coverage = coverage or {}
        h.venue_open = opens or {}
        h.thinned = list(thinned)
        return h

    def test_window_starts_at_the_first_interval_when_it_precedes_the_live_window(self):
        live = self.T0 + timedelta(days=10)
        row = _row_at(1, self.T0 + timedelta(hours=1))
        block = self._history().range_block(live, [row], [1])
        assert block["window_start"] == self.T0.isoformat()
        assert block["window_start_basis"] == "archive_first_interval"
        assert block["requested"] == "full"

    def test_window_is_the_live_one_when_nothing_older_was_drawn(self):
        live = self.T0
        row = _row_at(1, self.T0 + timedelta(hours=5))
        for served in ([row], []):
            block = self._history().range_block(live, served, [1])
            assert block["window_start"] == live.isoformat()
            assert block["window_start_basis"] == "hours"

    def test_coverage_is_complete_only_when_every_charted_outcome_is(self):
        both = self._history({1: {"complete"}, 2: {"complete"}})
        assert both.range_block(self.T0, [], [1, 2])["archive_coverage"] == "complete"
        # Outcome 2 never imported: incomplete, and no KeyError on the missing leg.
        one = self._history({1: {"complete"}})
        assert one.range_block(self.T0, [], [1, 2])["archive_coverage"] == "incomplete"
        partial = self._history({1: {"incomplete"}})
        assert partial.range_block(self.T0, [], [1])["archive_coverage"] == "incomplete"
        assert self._history().range_block(self.T0, [], [1])["archive_coverage"] is None

    def test_thinned_and_venue_open_name_only_charted_outcomes(self):
        h = self._history(
            {1: {"complete"}, 3: {"complete"}},
            {1: self.T0 + timedelta(hours=2), 3: self.T0},
            thinned=[1, 3],
        )
        block = h.range_block(self.T0 + timedelta(days=1), [], [1])
        assert block["thinned_outcomes"] == [1]
        assert block["archive_venue_open"] == (self.T0 + timedelta(hours=2)).isoformat()

    def test_every_chart_route_accepts_the_option_and_answers_it(self):
        src = (APP / "routes" / "futures.py").read_text()
        assert src.count('Query(None, alias="range", description=_FULL_RANGE_DOC)') == 3
        assert src.count("full_range=full_range,") == 3
        assert src.count('"history_range"') >= 3


# ── the forecast path stays dormant and the staged bank's SQL is unchanged ──


#: SHA-256 of Part A's generated SQL on the PARENT (be9ec5e9e8), computed from
#: the parent's own `_part_a_calibration_sql`, its literal `_part_a_value` and
#: its `_WOULD_CHURN` template (`/tmp/683_parta_fp.py`, quoted in the PR).
PARENT_PART_A_SQL_SHA256 = (
    "1ff7ac76f025a9cb1440872f4650b2802f0fa04b9e559a7306d7111e5672b652"
)


def _churn_template() -> str:
    src = (APP / "tasks" / "backfill_winners.py").read_text()
    return re.search(r'    _WOULD_CHURN = """(.*?)"""', src, re.S).group(1)


class TestForecastIsDormant:
    def test_the_switch_is_off_in_code(self):
        from app.utils import kalshi_archive_forecast as f

        assert f.KALSHI_ARCHIVE_FORECAST_ENABLED is False

    def test_flag_off_part_a_sql_is_byte_identical_to_the_parent(self):
        import importlib

        b = importlib.import_module("app.tasks.backfill_winners")

        sql = b._part_a_calibration_sql(
            _churn_template(),
            b._part_a_value_sql(b.KALSHI_ARCHIVE_FORECAST_ENABLED),
            archive_forecast=b.KALSHI_ARCHIVE_FORECAST_ENABLED,
        )
        assert hashlib.sha256(sql.encode()).hexdigest() == PARENT_PART_A_SQL_SHA256
        assert "kalshi_archive" not in sql

    def test_the_caller_passes_the_switch_to_both_halves(self):
        src = (APP / "tasks" / "backfill_winners.py").read_text()
        assert "_part_a_value_sql(KALSHI_ARCHIVE_FORECAST_ENABLED)" in src
        assert "archive_forecast=KALSHI_ARCHIVE_FORECAST_ENABLED" in src

    def test_flag_on_sql_revalidates_at_consumption(self):
        import importlib

        b = importlib.import_module("app.tasks.backfill_winners")

        sql = b._part_a_calibration_sql(
            "", b._part_a_value_sql(True), archive_forecast=True
        )
        for clause in (
            "k.admission_at_apply = 'forecast'",
            "k.interval_end <= ev.forecast_cutoff_ts",
            "ki.status IN ('applied', 'partial')",
            "(ev.cutoff_inputs->>'commence_time')::timestamptz",
            "CASE WHEN nc.is_threshold THEN NULL ELSE archive.probability END",
        ):
            assert clause in sql, clause
        # Strictly AFTER the live closing line in the COALESCE.
        assert sql.index("closing.probability,") < sql.index("archive.probability")


# ── who may name the archive tables ───────────────────────────────────────


ALLOWED_ARCHIVE_READERS = {
    "models/models.py",
    "services/kalshi_archive_recovery.py",
    "services/kalshi_archive_apply.py",
    "utils/kalshi_archive_reader.py",
    "utils/kalshi_archive_forecast.py",
}


class TestTheStoreIsJoinedOnlyOnPurpose:
    def test_only_the_named_modules_name_the_archive_tables(self):
        hits = {
            str(p.relative_to(APP))
            for p in APP.rglob("*.py")
            if re.search(r"kalshi_archive_(intervals|outcome_evidence|imports)", p.read_text())
        }
        assert hits == ALLOWED_ARCHIVE_READERS

    def test_calibration_reaches_the_archive_only_through_the_forecast_module(self):
        for path in (
            "tasks/backfill_winners.py",
            "tasks/precompute_calibration.py",
            "routes/calibration.py",
            "tasks/calibration_main_build.py",
            "tasks/calibration_sentinel.py",
            "utils/calibration_price_provenance.py",
            "utils/calibration_closing_line.py",
        ):
            src = (APP / path).read_text()
            assert "kalshi_archive_reader" not in src, path
            assert "kalshi_archive_apply" not in src, path

    def test_only_the_three_chart_routes_join_the_reader(self):
        users = {
            str(p.relative_to(APP))
            for p in APP.rglob("*.py")
            if "load_archive_history" in p.read_text()
        }
        assert users == {"utils/kalshi_archive_reader.py", "routes/futures.py"}
        src = (APP / "routes" / "futures.py").read_text()
        # /history, /probability-timeline and /multi-history (Root's WIP review:
        # the web evolution view combines markets through the third).
        assert src.count("await load_archive_history(") == 3

    def test_nothing_schedules_or_calls_the_import(self):
        hits = {
            str(p.relative_to(APP))
            for p in APP.rglob("*.py")
            if "apply_archive_plan" in p.read_text() or "restore_archive_import" in p.read_text()
        }
        assert hits == {"services/kalshi_archive_apply.py"}


# ── the attended script ───────────────────────────────────────────────────


def _load_script(name):
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestScripts:
    def test_import_refuses_a_plan_whose_digest_was_not_typed(self, tmp_path, capsys):
        plan = tmp_path / "p.json"
        plan.write_text(json.dumps({"mode": "dry_run"}))
        mod = _load_script("kalshi_archive_import.py")
        assert mod.main(["apply", "--plan", str(plan), "--expected-digest", "x"]) == 2
        assert "REFUSED" in capsys.readouterr().err

    def test_import_write_is_opt_in(self):
        mod = _load_script("kalshi_archive_import.py")
        args = mod._parse(["apply", "--plan", "p", "--expected-digest", "d"])
        assert args.write is False
        assert mod._parse(["restore", "--import-key", "k"]).write is False

    def test_dry_run_refuses_a_continue_from_without_a_carry(self, tmp_path, capsys):
        f = tmp_path / "r.json"
        f.write_text(json.dumps({"continuation": None}))
        mod = _load_script("kalshi_archive_recovery_dry_run.py")
        assert mod.main(["--continue-from", str(f)]) == 2
