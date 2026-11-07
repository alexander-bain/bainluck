"""Every caller of the sentinel rail: an unchanged finding digests the same at two
instants (#12276, Fable's pre-read on PR #12302).

The cadence holds a "Still RED" comment only while the digest of what a run would
say is unchanged. A run's own clock, a pass's last-run time or any other value
that moves every cycle would change the digest every run, and the cadence would
never apply. Each test builds one caller's real comment and body for one finding
at two wall-clock instants, through the caller's own filing code, and compares
the digests the rail records. Where the text really does move between the two
instants, the test asserts that first, so a pass cannot come from two identical
strings.
"""

import asyncio
import datetime as dt
import importlib
from types import SimpleNamespace

import pytest

sf = importlib.import_module("app.tasks.sentinel_filing")

T1 = dt.datetime(2026, 11, 7, 7, 10, 3, tzinfo=dt.timezone.utc)
T2 = T1 + dt.timedelta(hours=3, minutes=7, seconds=11)


@pytest.fixture
def clock(monkeypatch):
    """Sets the wall clock that ``datetime.now`` reads, both through a
    function-local ``from datetime import datetime`` and through the module-level
    names passed to ``clock.patch``."""
    real = dt.datetime
    state = {"now": T1}

    class Frozen(real):
        @classmethod
        def now(cls, tz=None):
            return state["now"].astimezone(tz) if tz else state["now"].replace(tzinfo=None)

        @classmethod
        def utcnow(cls):
            return state["now"].replace(tzinfo=None)

    monkeypatch.setattr(dt, "datetime", Frozen)

    def patch(*modules):
        for module in modules:
            monkeypatch.setattr(module, "datetime", Frozen)

    def at(instant):
        state["now"] = instant

    return SimpleNamespace(at=at, patch=patch)


@pytest.fixture
def rail(monkeypatch):
    """Every ``reconcile_issue`` call a caller makes, as its keyword arguments."""
    calls = []

    def capture(**kwargs):
        calls.append(kwargs)
        return {"action": "commented", "issue": 1}

    monkeypatch.setattr(sf, "reconcile_issue", capture)
    return calls


def digest(kwargs):
    return sf.red_finding_digest(
        kwargs.get("red_comment"), kwargs.get("red_body"), kwargs.get("red_digest_basis")
    )


def twice(clock, rail, run):
    """``run()`` at T1 and at T2 → the two RED calls it handed the rail."""
    clock.at(T1)
    run()
    clock.at(T2)
    run()
    red = [kw for kw in rail if kw.get("red")]
    assert len(red) == 2, red
    return red


# --- The rail ---------------------------------------------------------------


def test_the_digest_reads_past_a_date_and_time_in_any_spelling():
    for a, b in (
        ("2026-11-07T07:10:03+00:00", "2026-11-07T10:17:14+00:00"),
        ("2026-11-07T07:10:03.123456+00:00", "2026-11-07T10:17:14.9+00:00"),
        ("2026-11-07 07:10:03.123456+00:00", "2026-11-07 10:17:14+00:00"),
        ("2026-11-07T07:10:03Z", "2026-11-08T07:09:58Z"),
        ("as of 2026-11-07 07:10 UTC", "as of 2026-11-07 10:17 UTC"),
    ):
        assert sf.red_finding_digest(f"seen {a}", None) == sf.red_finding_digest(f"seen {b}", None)


def test_the_digest_still_sees_counts_ids_and_bare_dates():
    base = sf.red_finding_digest("3 rows: 101, 102, 103 for 2026-11-07", None)
    assert sf.red_finding_digest("4 rows: 101, 102, 103 for 2026-11-07", None) != base
    assert sf.red_finding_digest("3 rows: 101, 102, 104 for 2026-11-07", None) != base
    assert sf.red_finding_digest("3 rows: 101, 102, 103 for 2026-11-08", None) != base


def test_a_basis_replaces_the_text():
    assert sf.red_finding_digest("count 1", "body 1", "class-a") == sf.red_finding_digest(
        "count 2", "body 2", "class-a"
    )
    assert sf.red_finding_digest("same", "same", "class-a") != sf.red_finding_digest(
        "same", "same", "class-b"
    )


# --- Matching drift (every 15 minutes: the caller the cadence exists for) ----


def test_matching_golden_drift(clock, rail):
    mr = importlib.import_module("app.tasks.matching_reconciliation")

    finding = mr._finding(
        "golden", True, 1,
        "1 adjudicated pairs regressed, 2 negative pairs attached to an event no outside provider corroborates",
        [{"market_id": 709, "title": "Lakers vs Celtics", "failure_class": "twin",
          "expected_event_id": 41, "actual_event_id": 42, "verdict": "regressed"}],
    )
    first, second = twice(clock, rail, lambda: mr.file_findings([finding], open_issues=[]))
    assert digest(first) == digest(second)


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Session:
    def __init__(self, rows=(), scalar=0):
        self.rows, self.value = list(rows), scalar

    async def execute(self, *a, **k):
        return _Rows(self.rows)

    async def scalar(self, *a, **k):
        return self.value


def test_matching_receipt_coverage_whose_floor_moves_every_cycle(clock, rail, monkeypatch):
    """The detail names when the backlog pass last ran, and that pass runs every
    matcher cycle (or, when it is dead, the floor is `now − grace`)."""
    mr = importlib.import_module("app.tasks.matching_reconciliation")
    from app.utils import matcher_pass_runs

    clock.patch(matcher_pass_runs)
    findings = []

    async def check(last_run_at):
        async def read(session, phase, **k):
            return SimpleNamespace(last_run_at=last_run_at, never_attempted_max_id=None)

        monkeypatch.setattr(matcher_pass_runs, "read_pass_run", read)
        findings.append(await mr.check_receipt_coverage(_Session(scalar=7)))

    clock.at(T1)
    asyncio.run(check(T1 - dt.timedelta(minutes=4)))
    clock.at(T2)
    asyncio.run(check(T2 - dt.timedelta(minutes=9)))
    assert findings[0]["detail"] != findings[1]["detail"]

    mr.file_findings([findings[0]], open_issues=[])
    mr.file_findings([findings[1]], open_issues=[])
    assert digest(rail[0]) == digest(rail[1])


def test_matching_receipt_contradictions_whose_attempt_times_move(clock, rail):
    """Each row carries the matcher's last attempt, which moves every cycle."""
    mr = importlib.import_module("app.tasks.matching_reconciliation")

    def check(attempted):
        rows = [(5001, 41, None, "pass2", attempted), (5002, 43, 44, "pass3", attempted)]
        return asyncio.run(mr.check_receipt_contradicts_link(_Session(rows=rows, scalar=3)))

    first, second = check(T1), check(T2)
    assert first["rows"] != second["rows"]
    mr.file_findings([first], open_issues=[])
    mr.file_findings([second], open_issues=[])
    assert digest(rail[0]) == digest(rail[1])


def test_matching_a_changed_finding_still_changes_the_digest(clock, rail):
    mr = importlib.import_module("app.tasks.matching_reconciliation")

    def finding(regressed):
        return mr._finding(
            "golden", True, regressed, f"{regressed} adjudicated pairs regressed",
            [{"market_id": 700 + i, "verdict": "regressed"} for i in range(regressed)],
        )

    mr.file_findings([finding(1)], open_issues=[])
    mr.file_findings([finding(2)], open_issues=[])
    assert digest(rail[0]) != digest(rail[1])


# --- Calibration publish gate (hourly) --------------------------------------


def _verdict(prev_pop, cand_pop):
    from app.utils.calibration_publish_gate import PublishVerdict

    drift = (cand_pop - prev_pop) / prev_pop
    return PublishVerdict(
        ok=False,
        rejections=[{
            "code": "population_shrink",
            "detail": f"population fell {drift * 100:+.1f}% ({prev_pop:,} -> {cand_pop:,}), limit −5%",
        }],
        candidate={"population_version": "v7"},
        published={"population_version": "v7"},
    )


def test_calibration_rejection_whose_counts_move_every_hour(clock, rail):
    """The summary's counts move as outcomes resolve; the failure class is the
    finding, and the caller says so with its fingerprint."""
    pc = importlib.import_module("app.tasks.precompute_calibration")

    clock.at(T1)
    pc._file_publish_gate_rejection(_verdict(100_000, 87_700))
    clock.at(T2)
    pc._file_publish_gate_rejection(_verdict(100_000, 87_741))
    assert rail[0]["red_comment"] != rail[1]["red_comment"]
    assert digest(rail[0]) == digest(rail[1])


def test_calibration_a_new_failure_class_changes_the_digest(clock, rail):
    pc = importlib.import_module("app.tasks.precompute_calibration")
    from app.utils.calibration_publish_gate import PublishVerdict

    pc._file_publish_gate_rejection(_verdict(100_000, 87_700))
    pc._file_publish_gate_rejection(PublishVerdict(
        ok=False,
        rejections=[{"code": "empty_curve", "detail": "candidate carries no buckets"}],
        candidate={"population_version": "v7"},
        published={"population_version": "v7"},
    ))
    assert digest(rail[0]) != digest(rail[1])


# --- Data-quality watchdog (every 2 hours; also self-limited to one a day) ---


def test_watchdog(clock, rail):
    wd = importlib.import_module("app.tasks.data_quality_watchdog")

    clock.patch(wd)
    check = {
        "name": "stale_live_events", "severity": "P2", "threshold": 0,
        "comparison": "gt", "message": "Events stuck live past their window",
    }
    first, second = twice(
        clock, rail, lambda: wd.reconcile_alert_issue(check, 3, "diagnosis", open_issues=[])
    )
    assert first["red_comment"] != second["red_comment"]
    assert digest(first) == digest(second)


# --- The daily sentinels -----------------------------------------------------


def test_flow(clock, rail):
    fs = importlib.import_module("app.tasks.flow_sentinel")

    result = {
        "flow": "resolved_state",
        "checked": 251,
        "failures": [{
            "detail": "live tennis_other event Blinkova vs Kabbaj is LIVE in the database "
                      "but its commence_time is 2.5h in the FUTURE",
            "event_id": 15342993,
        }],
        "evidence": {"live_sampled": 55, "completed_sampled": 196},
    }
    first, second = twice(clock, rail, lambda: fs.file_flow_issue(result, open_issues=[]))
    assert first["red_body"] != second["red_body"]
    assert digest(first) == digest(second)


def test_horizon_needs_page(clock, rail):
    hz = importlib.import_module("app.tasks.horizon_sentinel")

    finding = {
        "slug": "ballon-dor-2026", "name": "Ballon d'Or 2026", "phase": "t_minus_14",
        "severity": "p1", "start": "2026-11-21", "end": "2026-11-21", "days_to_start": 14,
        "archetype": "award", "concept_key": "ballon-dor-2026", "domain": "soccer",
        "marquee": True, "detail": "No page answers at the concept key.",
    }
    first, second = twice(clock, rail, lambda: hz.file_horizon_issue(finding, open_issues=[]))
    assert digest(first) == digest(second)


def test_horizon_calendar_exhaustion(clock, rail):
    hz = importlib.import_module("app.tasks.horizon_sentinel")

    finding = {
        "competition": "ballon-dor", "name": "Ballon d'Or", "domain": "soccer",
        "last_edition_slug": "ballon-dor-2026", "last_edition_end": "2026-11-21",
        "days_left": 14, "severity": "p2",
        "detail": "`majors_calendar.yaml` has no edition of **ballon-dor** after 2026-11-21.",
    }
    first, second = twice(clock, rail, lambda: hz.file_exhaustion_issue(finding, open_issues=[]))
    assert digest(first) == digest(second)


def test_grid(clock, rail):
    gs = importlib.import_module("app.tasks.grid_sentinel")

    classified = {
        "league": "nfl", "phase": "regular",
        "real": [{"severity": "critical", "detail": "Week 10 has two rows for one game"}],
        "explained": [], "watch": [],
    }
    first, second = twice(clock, rail, lambda: gs.file_grid_issue(classified, open_issues=[]))
    assert digest(first) == digest(second)


def test_board(clock, rail):
    bs = importlib.import_module("app.tasks.board_sentinel")

    classified = {
        "real": [{"check": "inbox_untriaged", "severity": "P2", "detail": "#12001 untriaged 49h"}],
        "unknown": [], "counts": {"population_complete": True},
    }
    first, second = twice(clock, rail, lambda: bs.file_board_issue(classified, open_issues=[]))
    assert digest(first) == digest(second)


def test_schedule(clock, rail):
    ss = importlib.import_module("app.tasks.schedule_sentinel")

    clock.patch(ss)
    result = {
        "classified": {
            "league": "nfl", "phase": "regular",
            "real": [{"kind": "missing", "severity": "critical", "detail": "BUF @ MIA is not on our schedule"}],
            "explained": [], "watch": [], "unverified": [],
        },
        "window": "2026-11-06..2026-11-08",
        "coverage": {"truth": "espn"},
        "truth_games": 14,
        "our_events": 13,
    }
    first, second = twice(clock, rail, lambda: ss.file_schedule_issue(result, open_issues=[]))
    assert digest(first) == digest(second)


def test_anchor_schedule(clock):
    """Its comment and body both carry the run's own clock."""
    from tests.test_anchor_schedule_sentinel import _move, _page, _run_with_stub_session

    states = []
    for instant in (T1, T2):
        mp = pytest.MonkeyPatch()
        try:
            states.append(asyncio.run(_run_with_stub_session(
                mp, pages=[_page(moves=[_move()], has_more=False)],
                max_pages=5, deadline_seconds=60.0, now=instant,
            )))
        finally:
            mp.undo()
    first, second = (s["filing"] for s in states)
    assert first["red"] is True and second["red"] is True
    assert first["red_comment"] != second["red_comment"]
    assert digest(first) == digest(second)


def test_grid_register(clock, rail, monkeypatch, tmp_path):
    """It hands the rail no comment and no body to refresh, so its digest is
    the rail's default line — constant by construction."""
    grs = importlib.import_module("app.tasks.grid_register_sentinel")

    class _Db:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    async def run_league(session, league, *, apply, directory):
        return {"league": league, "status": "ok", "classification": "needs_ruling",
                "action": "file_p2_needs_triage", "published": False,
                "fingerprint": f"grid-register-{league}", "findings": ["AMBIGUOUS_ALIAS"],
                "counters": {"live": 3}}

    import app.services.durable_snapshots as dsnap

    async def durable_ok(envelope):
        return {"status": "ok", "identity": envelope.identity, "generation": envelope.generation}

    monkeypatch.setattr(dsnap, "publish_snapshot_standalone", durable_ok)
    monkeypatch.setattr(grs, "_run_league", run_league)
    monkeypatch.setattr("app.services.database.async_session_maker", lambda: _Db())
    monkeypatch.setattr(sf, "list_open_alert_issues", lambda: [])

    for instant in (T1, T2):
        clock.at(instant)
        asyncio.run(grs._run_grid_register_sentinel(file_issues=True, directory=tmp_path))
    league = rail[0]["marker_key"]
    first, second = [kw for kw in rail if kw["marker_key"] == league]
    assert first.get("red_comment") is None and first.get("red_body") is None
    assert digest(first) == digest(second)


def test_tournament_register(clock, rail, monkeypatch):
    trs = importlib.import_module("app.tasks.tournament_register_sentinel")
    from app.services import database

    class _Db:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *exc):
            return False

    async def run_tournament(session, tournament, season, *, directory):
        return {
            "tournament": tournament, "season": season, "status": "ok", "version": 12,
            "registered_count": 378, "candidate_count": 454,
            "findings": ["SETTLEMENT_WITHOUT_RESULT"], "classification": "needs_ruling",
            "action": "file_p2_needs_triage", "publish": False,
            "fingerprint": trs.drift_fingerprint(tournament, season),
        }

    monkeypatch.setattr(database, "async_session_maker", lambda: _Db())
    monkeypatch.setattr(trs, "_run_tournament", run_tournament)
    monkeypatch.setattr(sf, "fetch_open_alert_issues", lambda: sf.OpenIssuesResult(ok=True, issues=[]))

    for instant in (T1, T2):
        clock.at(instant)
        asyncio.run(trs._run_tournament_register_sentinel())
    fp = rail[0]["fingerprint"]
    first, second = [kw for kw in rail if kw.get("red") and kw["fingerprint"] == fp]
    assert digest(first) == digest(second)


# --- The weekly grouping sentinel ---------------------------------------------


def test_grouping(clock, rail, monkeypatch):
    """Its body states the run's time to the minute; its comment line states the
    day (weekly runs are always past the daily mark, so the day cannot hold one)."""
    gsn = importlib.import_module("app.tasks.grouping_sentinel")
    from app.utils.grouping_families import KIND_TITLE_TEMPLATE, Family

    fam = Family(
        kind=KIND_TITLE_TEMPLATE, key="who will win the {n} ballon d'or", label="Who will win the 2026 Ballon d'Or?",
        member_ids=(11, 12, 13), first_created_at=dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc),
    )
    monkeypatch.setattr(sf, "fetch_open_alert_issues", lambda: sf.OpenIssuesResult(ok=True, issues=[]))
    gsn.file_families([fam], T1)
    gsn.file_families([fam], T2)
    first, second = [kw for kw in rail if kw.get("red")]
    assert first["red_body"] != second["red_body"]
    assert digest(first) == digest(second)
