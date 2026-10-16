"""#1853 — a settled Kalshi event whose legs moved to the archive still gets graded.

PILLAR: TRUTH. SHIP: a settled Kalshi question gets its venue-backed result
instead of remaining ungraded.

The specimen is real: ``KXUECLSCORE-26JUL30LEVIFK``'s exhausted archive listing
(retained bytes, sha256 pinned in the repair script) and the 30 stored legs read
on 2026-10-15 — 22 with no grade and no source, 8 already ``api_settlement``.

Three layers, each with its own controls:

1. ``plan_archive_grades`` — the shared decision. On the specimen it plans the
   22 and only the 22; the 8 authoritative controls (including the lone ``yes``)
   are refused as already graded; a scalar or empty result is refused.
2. The grader's archive arm — DORMANT unless asked; when asked, a legless live
   read is followed by #2722's exact-event primitive, and a 429, an empty
   listing, a foreign leg or a live read that HAS legs grades nothing from it.
3. The attended repair's loader — the retained bytes must hash, be exhausted,
   name one event and repeat no ticker, or nothing is planned.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

import app.tasks.backfill_winners as bw
from app.utils import kalshi_archive_grades as kag

ROOT = Path(__file__).resolve().parents[1]
STORED = json.loads((ROOT / "tests" / "fixtures" / "kalshi_archive_1853_stored.json").read_text())
EVENT = STORED["event_ticker"]


def _script():
    spec = importlib.util.spec_from_file_location(
        "repair_1853_archive_grades", ROOT / "scripts" / "repair_1853_archive_grades.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _stored():
    return [
        kag.StoredLeg(r["outcome_id"], r["external_id"], r["resolution_source"], r["is_winner"])
        for r in STORED["stored"]
    ]


# --------------------------------------------------------------- 1. decision
class TestThePlanOnTheSpecimen:
    def test_it_plans_the_22_ungraded_legs_and_nothing_else(self):
        legs = _script().load_archive_legs()
        grades, refused = kag.plan_archive_grades(legs, _stored())
        ungraded = {r["outcome_id"] for r in STORED["stored"] if r["resolution_source"] is None}
        assert len(ungraded) == 22
        assert {g.outcome_id for g in grades} == ungraded
        assert all(g.is_winner is False for g in grades), "every planned leg is a venue no"
        assert all((g.status, g.result) == ("finalized", "no") for g in grades)

    def test_the_eight_authoritative_controls_are_preserved(self):
        legs = _script().load_archive_legs()
        _, refused = kag.plan_archive_grades(legs, _stored())
        authoritative = {r["outcome_id"] for r in STORED["stored"] if r["resolution_source"]}
        assert len(authoritative) == 8
        assert set(refused[kag.ALREADY_GRADED]) == authoritative
        # Including the event's only winner — this ship recovers no new WINNER.
        lone_yes = [r for r in STORED["stored"] if r["is_winner"] is True]
        assert len(lone_yes) == 1 and lone_yes[0]["outcome_id"] in authoritative
        assert refused[kag.ABSENT] == [] and refused[kag.NO_VERDICT] == []

    def test_a_planned_leg_is_mapped_by_its_own_ticker(self):
        legs = _script().load_archive_legs()
        grades, _ = kag.plan_archive_grades(legs, _stored())
        by_id = {r["outcome_id"]: r["external_id"] for r in STORED["stored"]}
        assert all(g.ticker == by_id[g.outcome_id] for g in grades)


class TestThePlanRefusesWhatItCannotRead:
    def _leg(self, ticker, status="finalized", result="no"):
        return {"ticker": ticker, "event_ticker": "E", "status": status, "result": result}

    @pytest.mark.parametrize("result", ["scalar", "", None])
    def test_no_mappable_verdict_is_never_a_loss(self, result):
        grades, refused = kag.plan_archive_grades(
            [self._leg("E-1", result=result)], [kag.StoredLeg(1, "E-1", None, None)]
        )
        assert grades == [] and refused[kag.NO_VERDICT] == [1]

    def test_a_stored_leg_the_listing_does_not_name_is_refused(self):
        grades, refused = kag.plan_archive_grades(
            [self._leg("E-1")], [kag.StoredLeg(2, "E-2", None, None)]
        )
        assert grades == [] and refused[kag.ABSENT] == [2]

    def test_a_soft_existing_grade_is_not_overwritten(self):
        grades, refused = kag.plan_archive_grades(
            [self._leg("E-1", result="yes")], [kag.StoredLeg(3, "E-1", "clean_resolution", False)]
        )
        assert grades == [] and refused[kag.ALREADY_GRADED] == [3]

    def test_a_grade_without_a_source_is_still_a_grade(self):
        grades, refused = kag.plan_archive_grades(
            [self._leg("E-1")], [kag.StoredLeg(4, "E-1", None, False)]
        )
        assert grades == [] and refused[kag.ALREADY_GRADED] == [4]


# ------------------------------------------------------- 2. the grader's arm
class _Result:
    def __init__(self, rows=(), rowcount=0):
        self._rows = list(rows)
        self.rowcount = rowcount

    def all(self):
        return list(self._rows)


class _Session:
    """Answers the archive arm's stored-legs read; counts and records UPDATEs."""

    def __init__(self, stored_rows, *, cas_misses=()):
        self.stored_rows = stored_rows
        self.cas_misses = set(cas_misses)
        self.archive_writes: list[tuple[int, bool]] = []
        self.statements: list[str] = []

    async def execute(self, stmt, params=None):
        try:
            sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        except Exception:
            sql = str(stmt)
        self.statements.append(sql)
        if "ORDER BY fo.id" in sql and "fo.external_id" in sql:
            return _Result(rows=self.stored_rows)
        if sql.upper().startswith("UPDATE FUTURES_OUTCOMES") and "resolution_source IS NULL" in sql:
            oid = int(sql.split("futures_outcomes.id = ")[1].split()[0])
            if oid in self.cas_misses:
                return _Result(rowcount=0)
            self.archive_writes.append((oid, "is_winner=true" in sql.replace(" ", "")))
            return _Result(rowcount=1)
        return _Result(rowcount=1 if sql.upper().startswith("UPDATE") else 0)

    async def commit(self):
        return None

    async def rollback(self):
        return None


class _SessionCM:
    def __init__(self, session):
        self._session = session

    def __call__(self, *a, **k):
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *a):
        return False


class _Venue:
    """A live read and an archive listing, each answered as configured."""

    def __init__(self, live, archive=None, archive_error=None):
        self.live = live
        self.archive = archive
        self.archive_error = archive_error
        self.archive_asked: list[str] = []

    async def get_event(self, ticker):
        return self.live

    async def get_historical_markets(self, *, event_ticker=None, limit=100, cursor=None, **_):
        self.archive_asked.append(event_ticker)
        if self.archive_error is not None:
            raise self.archive_error
        return list(self.archive or []), None

    async def close(self):
        return None


class _FakeRedis:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = value

    def delete(self, key):
        self.store.pop(key, None)


class _HTTP429(Exception):
    def __init__(self):
        super().__init__("429")
        self.response = type("R", (), {"status_code": 429, "headers": {}})()


def _leg(ticker, result, event=EVENT, status="finalized"):
    return {"ticker": ticker, "event_ticker": event, "status": status, "result": result}


THREE_STORED = [
    (101, f"{EVENT}-A", None, None),  # never graded, venue no  -> graded
    (102, f"{EVENT}-B", "api_settlement", True),  # authoritative control
    (103, f"{EVENT}-C", None, None),  # never graded, venue scalar -> refused
]
THREE_ARCHIVE = [_leg(f"{EVENT}-A", "no"), _leg(f"{EVENT}-B", "yes"), _leg(f"{EVENT}-C", "scalar")]


async def _drive(monkeypatch, venue, session, **kw):
    async def _sel(session_, limit_, cursor_, *, include_tail=True):
        return [EVENT], []

    async def _none(*a, **k):
        return []

    monkeypatch.setattr(bw, "_select_kalshi_settlement_tickers", _sel)
    for name in (
        "_select_kalshi_early_settled_tickers",
        "_select_kalshi_early_settled_longdated_tickers",
        "_select_kalshi_status_sync_tickers",
        "_select_kalshi_retracted_open_tickers",
        "_select_kalshi_expiring_ungraded_tickers",
    ):
        monkeypatch.setattr(bw, name, _none)
    monkeypatch.setattr(bw, "get_task_session", _SessionCM(session))
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda *a, **k: _FakeRedis())
    monkeypatch.setattr("app.services.kalshi_api.KalshiAPIService", lambda *a, **k: venue)
    return await bw._backfill_kalshi_winners(limit=100, **kw)


@pytest.mark.asyncio
class TestTheArchiveArm:
    async def test_it_is_dormant_unless_asked(self, monkeypatch):
        venue = _Venue({"markets": []}, archive=THREE_ARCHIVE)
        session = _Session(THREE_STORED)
        stats = await _drive(monkeypatch, venue, session)
        assert venue.archive_asked == [], "a deploy alone must not start reading the archive"
        assert session.archive_writes == [] and stats["archive_graded"] == 0

    async def test_a_legless_live_read_is_graded_from_the_archive(self, monkeypatch):
        venue = _Venue({"markets": []}, archive=THREE_ARCHIVE)
        session = _Session(THREE_STORED)
        stats = await _drive(monkeypatch, venue, session, archive_requests=10)
        assert venue.archive_asked == [EVENT]
        assert session.archive_writes == [(101, False)], "only the never-graded venue no"
        assert stats["archive_graded"] == 1 and stats["losers_set"] == 1
        assert stats["archive_refused"] == {kag.ALREADY_GRADED: 1, kag.NO_VERDICT: 1}
        assert stats["archive_reads"] == {"read": 1}
        # No price-crown guess, no status flip on an archive-graded event.
        assert not any("clean_resolution" in s for s in session.statements)
        assert not any(s.upper().startswith("UPDATE FUTURES_MARKETS") for s in session.statements)

    async def test_the_write_is_the_live_arms_settled_values(self, monkeypatch):
        venue = _Venue({"markets": []}, archive=THREE_ARCHIVE)
        session = _Session(THREE_STORED)
        await _drive(monkeypatch, venue, session, archive_requests=10)
        write = next(s for s in session.statements if "futures_outcomes.id = 101" in s)
        assert "resolution_source='api_settlement'" in write.replace(" ", "")
        assert "current_probability=0.0" in write.replace(" ", "")
        assert "resolution_sourceISNULL" in write.replace(" ", "")
        assert "is_winnerISNULL" in write.replace(" ", "")

    async def test_a_leg_graded_since_the_read_is_left_alone(self, monkeypatch):
        venue = _Venue({"markets": []}, archive=THREE_ARCHIVE)
        session = _Session(THREE_STORED, cas_misses={101})
        stats = await _drive(monkeypatch, venue, session, archive_requests=10)
        assert session.archive_writes == []
        assert stats["archive_refused"]["changed_since_read"] == 1
        assert stats["archive_graded"] == 0

    @pytest.mark.parametrize(
        "archive, error, outcome",
        [
            ([], None, "empty"),
            ([_leg(f"{EVENT}-A", "no", event="KXOTHER-26JUL30X")], None, "wrong_event"),
            (None, _HTTP429(), "rate_limited"),
            (None, TimeoutError("read timeout"), "error"),
        ],
    )
    async def test_an_unread_archive_grades_nothing(self, monkeypatch, archive, error, outcome):
        venue = _Venue({"markets": []}, archive=archive, archive_error=error)
        session = _Session(THREE_STORED)
        stats = await _drive(monkeypatch, venue, session, archive_requests=10)
        assert stats["archive_reads"] == {outcome: 1}
        assert session.archive_writes == [] and stats["archive_graded"] == 0

    async def test_a_live_read_with_legs_never_asks_the_archive(self, monkeypatch):
        venue = _Venue({"markets": [_leg(f"{EVENT}-A", "no")]}, archive=THREE_ARCHIVE)
        session = _Session(THREE_STORED)
        stats = await _drive(monkeypatch, venue, session, archive_requests=10)
        assert venue.archive_asked == [] and stats["archive_reads"] == {}

    async def test_dry_run_writes_nothing(self, monkeypatch):
        venue = _Venue({"markets": []}, archive=THREE_ARCHIVE)
        session = _Session(THREE_STORED)
        stats = await _drive(monkeypatch, venue, session, archive_requests=10, dry_run=True)
        assert session.archive_writes == [] and stats["archive_graded"] == 0


# ---------------------------------------------------- 3. the attended repair
class TestTheRetainedBytes:
    def test_the_pinned_bytes_load(self):
        legs = _script().load_archive_legs()
        assert len(legs) == 30 and {leg["event_ticker"] for leg in legs} == {EVENT}

    def _write(self, tmp_path, body):
        p = tmp_path / "archive.json"
        p.write_text(json.dumps(body))
        return p, hashlib.sha256(p.read_bytes()).hexdigest()

    def test_a_different_byte_is_refused(self, tmp_path):
        mod = _script()
        p, _ = self._write(tmp_path, {"cursor": "", "markets": [_leg(f"{EVENT}-A", "no")]})
        with pytest.raises(mod.Refused, match="hash"):
            mod.load_archive_legs(p)

    @pytest.mark.parametrize(
        "body, why",
        [
            ({"cursor": "next", "markets": [_leg(f"{EVENT}-A", "no")]}, "exhausted"),
            ({"cursor": "", "markets": [_leg(f"{EVENT}-A", "no", event="X")]}, "another event"),
            ({"cursor": "", "markets": [_leg(f"{EVENT}-A", "no")] * 2}, "repeats"),
            ({"cursor": "", "markets": []}, "no legs"),
        ],
    )
    def test_an_unproven_listing_is_refused(self, tmp_path, monkeypatch, body, why):
        mod = _script()
        p, digest = self._write(tmp_path, body)
        monkeypatch.setattr(mod, "ARCHIVE_SHA256", digest)
        with pytest.raises(mod.Refused, match=why):
            mod.load_archive_legs(p)

    def test_the_digest_names_the_plan_not_its_order(self):
        mod = _script()
        a = mod.ApprovedGrade(1, "T1", False, "finalized", "no", '{"id": 1}')
        b = mod.ApprovedGrade(2, "T2", False, "finalized", "no", '{"id": 2}')
        assert mod.plan_digest([a, b]) == mod.plan_digest([b, a])
        assert mod.plan_digest([a]) != mod.plan_digest([a, b])

    def test_the_digest_binds_each_legs_approved_version(self):
        """Root 004: same id, same verdict, a moved row is a different plan; and
        a grade carrying no approved version cannot be digested or backed up."""
        mod = _script()
        a = mod.ApprovedGrade(1, "T1", False, "finalized", "no", '{"id": 1, "current_probability": 0.47}')
        moved = mod.ApprovedGrade(1, "T1", False, "finalized", "no", '{"id": 1, "current_probability": 0.61}')
        assert mod.plan_digest([a]) != mod.plan_digest([moved])
        with pytest.raises(mod.Refused, match="approved version"):
            mod.plan_digest([kag.ArchiveGrade(1, "T1", False, "finalized", "no")])

    def test_writes_refuse_off_the_named_app(self):
        mod = _script()
        with pytest.raises(mod.Refused):
            mod.refuse_unless_named_app({"HEROKU_APP_NAME": "bainluck"})
        with pytest.raises(mod.Refused):
            mod.refuse_unless_named_app({})
        mod.refuse_unless_named_app({"HEROKU_APP_NAME": "bainluck-heavy"})

    def test_the_ownership_contract_is_whole_row(self):
        """Shape only — the behaviour is the real-PG file's. Apply CASes the WHOLE
        before-image of a frozen row; restore requires the WHOLE after-image."""
        sql = {k: " ".join(v.split()) for k, v in _script().SQL.items()}
        assert "to_jsonb(fo) = CAST(:approved_before AS jsonb)" in sql["bak_copy"]
        assert "to_jsonb(fo) = b.before_row" in sql["apply_one"]
        assert "b.plan_digest = :digest" in sql["apply_one"]
        assert "AND b.applied AND to_jsonb(fo) = b.after_row" in sql["restore"]
        assert "applied = false, after_row = NULL" in sql["close_restored"]
        assert "ownership_lost_at = NOW()" in sql["close_lost"]
