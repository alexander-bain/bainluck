"""CAL-P073 — the #1912 rail's pages compose into an ATTENDED PROGRAMME.

C-APPLY-PRE-1912-R2 input 1. The rail was already row-safe: a content-addressed
plan, compare-and-set on the cohort-defining state, counted exclusions, a
persisted invalidation debt. None of that is attendance. One Alex MC is being
asked to cover **~5,661 calls**, and Fable's contract for that is explicit —
it may do so *only if mid-wave progress is readable*.

Three things were missing, and this file pins all three.

**1. There was no resume cursor at all.** ``_dry_run`` called
``_load_cohort(..., before_id=None)`` unconditionally. The dispatcher in
``routes/admin_repairs.py`` declares an ``after_id`` query parameter and passes
it *only to repairs whose signature accepts one* — this one did not, so an
operator could send a cursor, get a 200, and be served the same first page. The
cohort self-drains on APPLY (a written row gains a ``resolution_source`` and
leaves the HAVING), which is why the wave appeared to advance; two consecutive
DRY-RUNS returned the identical 40 markets forever. A rail whose only way
forward is to write is not attendable.

**2. Progress lived in a response body**, so it died with the terminal that
printed it, and a second operator could not tell call 300 from call 1.

**3. The zero-population canaries were not evaluated anywhere.** They are a
tripwire on the COHORT PREDICATE: this rail crowns outcomes from a venue answer,
and the failure that would not announce itself is the population quietly
widening past what was measured — which is exactly the claim the MC authorises.
"""

from __future__ import annotations

import inspect

import pytest

from app.tasks import repair_pm_never_graded as rail
from app.tasks.repair_pm_never_graded import (
    CANARY_CLEAN,
    CANARY_TRIPPED,
    CANARY_UNMEASURED,
    PROGRESS_IDENTITY,
    ZERO_POPULATION_CANARIES,
    evaluate_canaries,
    fold_progress,
)

# ---------------------------------------------------------------------------
# 1. The canary panel — and UNMEASURED IS NOT CLEAN
# ---------------------------------------------------------------------------


def test_the_four_canaries_are_the_four_fable_named():
    assert set(ZERO_POPULATION_CANARIES) == {"rodeo", "olympics", "legal", "crypto"}


def test_all_zero_is_clean_and_every_canary_is_returned():
    out = evaluate_canaries({}, note="ok")
    assert out["measured"] is True
    assert out["verdict"] == CANARY_CLEAN
    assert out["tripped"] == []
    # EVERY canary is returned, not just the interesting ones. A panel that
    # omits the quiet ones cannot be read as a panel.
    assert set(out["canaries"]) == set(ZERO_POPULATION_CANARIES)
    assert all(c["markets"] == 0 for c in out["canaries"].values())


def test_one_non_zero_canary_trips_the_whole_panel():
    out = evaluate_canaries({"rodeo": 3}, note="ok")
    assert out["verdict"] == CANARY_TRIPPED
    assert out["tripped"] == ["rodeo"]
    assert out["canaries"]["rodeo"] == {"markets": 3, "verdict": CANARY_TRIPPED}
    assert out["canaries"]["legal"]["verdict"] == CANARY_CLEAN
    assert "HALT" in out["note"]


def test_an_unreadable_panel_is_unmeasured_and_never_clean():
    """The one that matters. Gotcha #53, inside the instrument built to stop it.

    A tripwire that could not be read has not been read. If this degraded to
    ``clean`` the panel would be at its most reassuring exactly when it had
    stopped working.
    """
    out = evaluate_canaries(None, note="canary_read_failed: TimeoutError")
    assert out["measured"] is False
    assert out["verdict"] == CANARY_UNMEASURED
    assert out["verdict"] != CANARY_CLEAN
    assert set(out["canaries"]) == set(ZERO_POPULATION_CANARIES)
    assert all(c["markets"] is None for c in out["canaries"].values())
    assert all(c["verdict"] == CANARY_UNMEASURED for c in out["canaries"].values())
    assert "canary_read_failed" in out["reason"]


def test_tripped_outranks_unmeasured_outranks_clean():
    """Precedence degrades in the safe direction, and only one way."""
    assert evaluate_canaries({"crypto": 1}, note="ok")["verdict"] == CANARY_TRIPPED
    assert evaluate_canaries(None, note="x")["verdict"] == CANARY_UNMEASURED
    assert evaluate_canaries({}, note="ok")["verdict"] == CANARY_CLEAN


@pytest.mark.asyncio
async def test_the_canary_read_is_bounded_and_fails_to_unmeasured(monkeypatch):
    class _S:
        def __init__(self):
            self.statements = []

        async def execute(self, stmt, params=None):
            sql = " ".join(str(stmt).split())
            self.statements.append(sql)
            if "statement_timeout" in sql:
                return None
            raise RuntimeError("canceling statement due to statement timeout")

        async def rollback(self):
            pass

    s = _S()
    out = await rail._read_canaries(s)
    assert out["verdict"] == CANARY_UNMEASURED
    assert any("statement_timeout" in x for x in s.statements)
    # Tighter than the full census: this runs on EVERY call and shares the
    # 25 s budget with the venue round-trips.
    assert rail._CANARY_TIMEOUT_MS < rail._CENSUS_TIMEOUT_MS


def test_the_canary_query_uses_the_one_cohort_predicate():
    """Two definitions of one cohort is how a rail counts rows it never drains."""
    assert rail.POPULATION_HAVING_SQL in rail._CANARY_SQL


# ---------------------------------------------------------------------------
# 2. Durable progress
# ---------------------------------------------------------------------------


def test_progress_accumulates_across_calls():
    a = fold_progress(None, mode="dry_run", examined_markets=40,
                      planned_markets=31, cursor=900)
    assert a["calls"] == 1 and a["dry_runs"] == 1 and a["applies"] == 0
    assert a["examined_markets_total"] == 40
    assert a["resume_after_id"] == 900

    b = fold_progress(a, mode="apply", written_legs=62, written_markets=31,
                      cursor=None)
    assert b["calls"] == 2 and b["dry_runs"] == 1 and b["applies"] == 1
    assert b["examined_markets_total"] == 40      # the apply examined none
    assert b["written_legs_total"] == 62
    assert b["written_markets_total"] == 31


def test_a_cursorless_call_keeps_the_last_real_resume_point():
    """A position does not decay by going unused — unlike a tally.

    An apply produces no cursor. Blanking ``resume_after_id`` on every apply
    would make the wave un-resumable precisely after the calls that matter.
    """
    a = fold_progress(None, mode="dry_run", examined_markets=40, cursor=900)
    b = fold_progress(a, mode="apply", written_legs=10, cursor=None)
    assert b["last_cursor"] is None
    assert b["resume_after_id"] == 900


def test_progress_survives_a_junk_prior_record():
    """A corrupt slot must not zero a wave that really happened, nor crash it."""
    out = fold_progress(
        {"calls": "many", "examined_markets_total": None, "resume_after_id": 42},
        mode="dry_run", examined_markets=5, cursor=None,
    )
    assert out["calls"] == 1
    assert out["examined_markets_total"] == 5
    assert out["resume_after_id"] == 42


def test_the_5661_call_claim_is_checkable_against_the_record():
    """``calls`` is what turns the MC's number into something falsifiable."""
    rec = None
    for _ in range(7):
        rec = fold_progress(rec, mode="dry_run", examined_markets=40, cursor=1)
    assert rec["calls"] == 7
    assert rec["examined_markets_total"] == 280


@pytest.mark.asyncio
async def test_a_non_durable_progress_write_says_so_rather_than_reporting_progress(
    monkeypatch,
):
    async def _canaries(_s):
        return evaluate_canaries({}, note="ok")

    async def _load():
        return None, "missing"

    async def _save(_rec):
        return False, "progress persist rejected: conflict"

    monkeypatch.setattr(rail, "_read_canaries", _canaries)
    monkeypatch.setattr(rail, "_load_progress", _load)
    monkeypatch.setattr(rail, "_save_progress", _save)

    out = await rail.progress_read(object(), mode="dry_run", examined_markets=40,
                                   cursor=7)
    assert out["durable"] is False
    assert "NOT DURABLE" in out["attendance"]
    assert out["identity"] == PROGRESS_IDENTITY


# ---------------------------------------------------------------------------
# 3. The resume cursor, proven over MORE THAN ONE page
# ---------------------------------------------------------------------------


class _CohortRow:
    def __init__(self, mid):
        self.id = mid
        self.cond_id = f"0x{mid:04x}"
        self.market_name = f"market {mid}"
        self.resolution_date = None
        self.created_at = None
        self.event_linked = False


def _install_page_fakes(monkeypatch, population):
    """Serve ``population`` (id-DESC) through the real keyset predicate.

    The fake reproduces ``_load_cohort``'s contract rather than its SQL: an
    id-descending walk, ``id < before_id`` when a cursor is given.
    """
    calls: list[dict] = []

    async def _load_cohort(session, limit, before_id, cohort=None):
        calls.append({"limit": limit, "before_id": before_id, "cohort": cohort})
        rows = sorted(population, reverse=True)
        if before_id is not None:
            rows = [r for r in rows if r < before_id]
        return [_CohortRow(r) for r in rows[:limit]]

    async def _load_outcomes(session, ids):
        return {i: [{"id": i * 10, "name": "Yes", "external_id": f"{i}_yes"},
                    {"id": i * 10 + 1, "name": "No", "external_id": f"{i}_no"}]
                for i in ids}

    async def _fetch_and_map(service, r, outcomes):
        return {"tier": "resolved_direct", "winner_id": r.id * 10,
                "loser_id": r.id * 10 + 1, "integrity_ok": True}

    class _Svc:
        async def close(self):
            pass

    import app.tasks.clob_resolve as clob
    import app.services.polymarket_api as pmapi

    monkeypatch.setattr(clob, "_load_cohort", _load_cohort)
    monkeypatch.setattr(clob, "_load_outcomes", _load_outcomes)
    monkeypatch.setattr(clob, "_fetch_and_map", _fetch_and_map)
    monkeypatch.setattr(pmapi, "PolymarketAPIService", lambda *a, **k: _Svc())

    async def _save_plan(plan):
        return True, "ok"

    async def _progress(session, **kw):
        return {"stub": True, **kw}

    monkeypatch.setattr(rail, "_save_plan", _save_plan)
    monkeypatch.setattr(rail, "progress_read", _progress)
    return calls


@pytest.mark.asyncio
async def test_the_cursor_walks_more_than_one_forty_market_page(monkeypatch):
    """The directive's explicit bar: proven over MORE THAN ONE 40-market page.

    Three consecutive pages over a 100-market population, each resuming from
    the previous page's ``next_cursor``. The pages must be DISJOINT and must
    cover the population in order — which is the property that was absent, and
    absent silently.
    """
    population = list(range(1, 101))
    _install_page_fakes(monkeypatch, population)

    seen: list[int] = []
    cursor = None
    for expected_first in (100, 60, 20):
        out = await rail.repair(object(), False, limit=40, after_id=cursor)
        ids = [r for r in range(expected_first, expected_first - 40, -1) if r >= 1]
        assert out["resumed_after_id"] == cursor
        assert out["examined_markets"] == len(ids)
        seen.extend(ids)
        cursor = out["next_cursor"]

    assert len(seen) == len(set(seen)) == 100, "pages overlapped or dropped rows"
    assert sorted(seen) == population
    assert cursor == 1


@pytest.mark.asyncio
async def test_without_a_cursor_every_dry_run_returns_the_same_page(monkeypatch):
    """The defect, pinned as a REGRESSION GUARD rather than described.

    This is what the rail did on every call before CAL-P073, and it is still
    the correct behaviour for a cursorless call — the bug was that a cursor
    could not be supplied, not that the first page is the first page.
    """
    _install_page_fakes(monkeypatch, list(range(1, 101)))
    a = await rail.repair(object(), False, limit=40)
    b = await rail.repair(object(), False, limit=40)
    assert a["next_cursor"] == b["next_cursor"] == 61
    assert a["examined_markets"] == b["examined_markets"] == 40


@pytest.mark.asyncio
async def test_the_cursor_comes_from_what_was_EXAMINED_not_what_was_planned(
    monkeypatch,
):
    """A page of pure exclusions still moved through the population.

    Deriving the cursor from the PLANNED set would re-walk every unplannable
    market forever — the wave would stall on the first page the venue cannot
    answer, and stall silently, because each call would look like a normal
    zero-plan dry-run.
    """
    _install_page_fakes(monkeypatch, list(range(1, 101)))

    import app.tasks.clob_resolve as clob

    async def _all_excluded(service, r, outcomes):
        return {"not_found": True}

    monkeypatch.setattr(clob, "_fetch_and_map", _all_excluded)

    out = await rail.repair(object(), False, limit=40)
    assert out["planned_markets"] == 0
    assert out["examined_markets"] == 40
    assert out["next_cursor"] == 61, "a fully-excluded page must still advance"
    assert out["verdicts"]["not_at_venue"] == 40


@pytest.mark.asyncio
async def test_a_short_page_reports_exhaustion(monkeypatch):
    _install_page_fakes(monkeypatch, list(range(1, 11)))
    out = await rail.repair(object(), False, limit=40)
    assert out["page_exhausted"] is True
    assert out["examined_markets"] == 10


@pytest.mark.asyncio
async def test_an_empty_page_offers_no_cursor_rather_than_a_guessed_one(monkeypatch):
    _install_page_fakes(monkeypatch, [])
    out = await rail.repair(object(), False, limit=40)
    assert out["next_cursor"] is None
    assert "NO CURSOR" in out["next_page"]


# ---------------------------------------------------------------------------
# 4. The wiring that made the cursor unreachable
# ---------------------------------------------------------------------------


def test_the_dispatcher_will_actually_pass_the_cursor_through():
    """STRUCTURAL. The router forwards a parameter only if the repair DECLARES it.

    ``run_repair`` builds its kwargs from
    ``inspect.signature(fn).parameters`` — so a repair that omits ``after_id``
    receives a 200 and silently ignores the operator's cursor. That is how this
    one shipped: the query parameter existed, was documented, and went nowhere.
    """
    params = inspect.signature(rail.repair).parameters
    assert "after_id" in params, (
        "routes/admin_repairs.run_repair only forwards params the repair "
        "declares; without this the cursor is accepted and dropped"
    )
    assert list(params)[:2] == ["session", "apply"], (
        "the dispatcher calls fn(db, apply, **extra) POSITIONALLY"
    )
    assert params["after_id"].default is None


def test_both_response_shapes_carry_the_attendance_block():
    """Progress is returned on the dry-run AND the apply.

    The apply is the call that changes the population, so a wave record that
    counted only dry-runs would drift further from the truth with every write.
    """
    src = inspect.getsource(rail._dry_run)
    assert 'mode="dry_run"' in src and "progress_read(" in src
    src_apply = inspect.getsource(rail._apply_reviewed_plan)
    assert 'mode="apply"' in src_apply and "progress_read(" in src_apply
