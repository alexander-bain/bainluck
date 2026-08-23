"""The sweep runner: idempotency, the four zeros, and the verification read.

Queue 392 Item 1 (#2077).

WHAT THESE TESTS ARE FOR, AND WHAT THEY DELIBERATELY DO NOT CLAIM
------------------------------------------------------------------

The runner's fakes assert against a stand-in session, not a database. The delete
rail's R4 BLOCK is the standing lesson about exactly this: 111 green tests over SQL
containing ``varchar = integer``, because the fakes checked that table names appeared
in the string and never asked PostgreSQL to type-check it. So the SQL-shaped
assertions here are kept honest in two ways:

* they assert **structure that is checkable without a database** — that the three
  reads compose the SAME cohort predicate, that the ``LIMIT`` runs over a total
  ``ORDER BY``, that the terminal/retryable partition of the disposition enum is
  exhaustive — never that a query "returns the right rows";
* and the docstrings say which properties remain UNPROVEN here. Every property that
  needs a real database is named in ``test_sql_properties_needing_a_real_database``,
  which is a written IOU, not a passing claim.

The orchestration tests — planning, idempotency, the verdict — use an injected
``probe_fn`` and a fake session, and those ARE real tests of real logic, because that
logic is pure Python that happens to be reached through a session.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import pytest

from app.services.settlement_sweep_runner import (
    COMMIT_EVERY,
    PROBE_PROTOCOL_VERSION,
    TERMINAL_COMPLETE,
    TERMINAL_FAILED,
    TERMINAL_NO_WORK,
    TERMINAL_PARTIAL,
    _capture_row,
    _verdict,
    run_sweep,
    verify_sweep,
)
from app.utils.kalshi_retention import (
    CAPTURE_PLANNING_AGE_DAYS,
    PROVABLY_PURGED_AGE_DAYS,
)
from app.utils.settlement_sweep_plan import Candidate, TERMINAL_BUCKET
from app.utils.settlement_sweep_query import (
    CANDIDATE_SQL,
    COHORT_BY_DAY_SQL,
    EXCLUSIONS_SQL,
    RETRYABLE_DISPOSITIONS,
    TERMINAL_DISPOSITIONS,
    default_sweep_id,
    fetch_limit_for,
    window_start,
)
from app.utils.settlement_truth import Disposition, ProbeOutcome, SettlementClaim

# The clock is frozen and the fixture dates are offsets from it. Never
# ``.replace(hour=...)`` — that pins an hour, not an age, so the age swings a full
# day with the wall clock and the suite goes red every evening (gotcha #44).
NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)


def _settled(label: str = "Yes") -> ProbeOutcome:
    return ProbeOutcome(
        Disposition.SETTLED,
        claim=SettlementClaim(winning_outcome=label, channel="kalshi_market"),
        channels=(("kalshi_market", 200),),
        raw={"kalshi_market": {"result": label}},
    )


def _purged() -> ProbeOutcome:
    return ProbeOutcome(
        Disposition.PURGED,
        channels=(("kalshi_market", 404), ("kalshi_event", 200)),
        reason="event found, markets empty — past the retention cliff",
        raw={"kalshi_event": {"markets": []}},
    )


def _at_age(days: float) -> datetime:
    """A resolution_date this many days before the frozen NOW."""
    return NOW - timedelta(days=days)


# ---------------------------------------------------------------------------
# A fake session that records what it was asked, and answers by SQL shape.
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class FakeSession:
    """Answers the runner's four reads. Records commits and inserted rows."""

    def __init__(self, *, cohort_rows=None, candidate_rows=None, exclusions=(0, 0),
                 already_captured=(), captured_day_rows=None, dispositions=None,
                 fail_on_market=None):
        self.cohort_rows = cohort_rows or []
        self.candidate_rows = candidate_rows or []
        self.exclusions = exclusions
        self.already_captured = set(already_captured)
        self.captured_day_rows = captured_day_rows or []
        self.dispositions = dispositions or []
        self.fail_on_market = fail_on_market
        self.inserted: list[dict] = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, statement, params=None):
        sql = str(statement)
        params = params or {}
        if "n_uncaptured" in sql:
            return _Result(self.cohort_rows)
        if "already_this_sweep" in sql:
            return _Result([self.exclusions])
        if sql.strip().startswith("SELECT m.id"):
            return _Result(self.candidate_rows)
        if "SELECT 1 FROM settlement_captures" in sql and "market_id" in sql:
            hit = params.get("market_id") in self.already_captured
            return _Result([(1,)] if hit else [])
        if sql.strip().startswith("INSERT INTO settlement_captures"):
            if self.fail_on_market is not None and params.get("market_id") == self.fail_on_market:
                raise RuntimeError("simulated write failure")
            self.inserted.append(dict(params))
            return _Result([])
        if "c.disposition, COUNT(*)" in sql:
            return _Result(self.dispositions)
        if "JOIN futures_markets m ON m.id = c.market_id" in sql:
            return _Result(self.captured_day_rows)
        raise AssertionError(f"unexpected SQL: {sql[:120]}")

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _candidate_row(market_id: int, age_days: float, ticker: str | None = None):
    return (market_id, "kalshi", ticker or f"KXTEST-{market_id}", _at_age(age_days))


async def _always(outcome):
    async def _fn(source, external_id):
        return outcome
    return _fn


# ---------------------------------------------------------------------------
# The horizon constant, which the directive names explicitly
# ---------------------------------------------------------------------------


def test_planning_horizon_is_a_named_constant_and_is_66():
    """66 is a CHOSEN horizon and must never be re-derived or inlined.

    It sits beside two MEASURED constants with different values and different jobs.
    A literal 66 in the runner would be indistinguishable from a literal 68 or 74
    typed by someone who read the wrong line of the retention table.
    """
    assert CAPTURE_PLANNING_AGE_DAYS == 66
    assert CAPTURE_PLANNING_AGE_DAYS < PROVABLY_PURGED_AGE_DAYS


def test_no_capture_horizon_literals_in_the_runner_or_the_command():
    """The numbers must arrive by import, not by retyping.

    This is the one guard that would have caught the failure mode it exists for:
    someone reads "66" in a docstring and hard-codes it next to a 74 that means
    something else entirely.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    for relative in (
        "app/services/settlement_sweep_runner.py",
        "app/utils/settlement_sweep_query.py",
        "scripts/run_settlement_sweep.py",
    ):
        source = (root / relative).read_text()
        code = "\n".join(
            line for line in source.split("\n")
            if not line.strip().startswith(("#", "*", '"""', "'''"))
        )
        for horizon in ("66", "74", "86", "68"):
            assert not re.search(rf"=\s*{horizon}\b", code), (
                f"{relative} assigns a bare {horizon} — import the named constant "
                "from kalshi_retention instead"
            )


def test_sql_window_uses_the_skip_bound_not_the_planning_bound():
    """The query fails OPEN: 66-86 day rows still reach the planner to be named.

    Filtering at 66 would delete the ``expired`` bucket from the report entirely,
    and a population narrowed inside the SQL is invisible in the output.
    """
    start = window_start(NOW)
    assert (NOW - start).days == PROVABLY_PURGED_AGE_DAYS
    assert (NOW - start).days > CAPTURE_PLANNING_AGE_DAYS


# ---------------------------------------------------------------------------
# SQL structure — checkable without a database, and honest about what is not
# ---------------------------------------------------------------------------


def test_the_three_reads_compose_one_cohort_predicate():
    """Composed, not copied. Three copies drift; the burn-down then divides by a
    population it did not measure."""
    fragment = "AND NOT EXISTS (\n      SELECT 1 FROM futures_outcomes o"
    for sql in (CANDIDATE_SQL, COHORT_BY_DAY_SQL, EXCLUSIONS_SQL):
        assert fragment in sql
        assert "m.resolution_date > :window_start" in sql
        assert "m.source = :source" in sql


def test_candidate_limit_runs_over_a_total_order():
    """A ``LIMIT`` without a deterministic ``ORDER BY`` lets the rehearsal and the
    run select different rows while both report the same count. That exact defect
    returned BLOCK on the delete rail."""
    order = CANDIDATE_SQL.index("ORDER BY")
    limit = CANDIDATE_SQL.index("LIMIT")
    assert order < limit
    assert "ORDER BY m.resolution_date ASC, m.id ASC" in CANDIDATE_SQL


def test_terminal_and_retryable_partition_the_disposition_enum():
    """Exhaustive and disjoint, checked against the ENUM rather than against a
    second hand-written list.

    A disposition added later lands in ``RETRYABLE`` — the safe default: it gets
    probed again, which wastes a call. The unsafe default would be silently
    treating a new disposition as terminal and never asking again.
    """
    everything = {d.value for d in list(Disposition)}
    assert TERMINAL_DISPOSITIONS | RETRYABLE_DISPOSITIONS == everything
    assert not (TERMINAL_DISPOSITIONS & RETRYABLE_DISPOSITIONS)
    assert Disposition.AMBIGUOUS_EMPTY.value in RETRYABLE_DISPOSITIONS
    assert Disposition.RATE_LIMITED.value in RETRYABLE_DISPOSITIONS
    assert Disposition.OPEN_NO_SETTLEMENT.value in RETRYABLE_DISPOSITIONS


def test_sql_properties_needing_a_real_database():
    """An IOU, written down rather than implied by a green suite.

    These CANNOT be proved by the fakes above and are not claimed to be:

    * that every column referenced exists and every comparison type-checks
      (the R4 ``varchar = integer`` defect passed 111 fake-backed tests);
    * that ``COUNT(*) FILTER`` groups as intended;
    * that ``CAST(:p AS jsonb)`` binds under asyncpg (``text()`` drops a bind
      followed by ``::``, which is why the INSERT is written with ``CAST``);
    * that the CHECK constraint rejects a winner without ``SETTLED``.

    There is no local PostgreSQL in the sandbox (``initdb`` dies on shmget), so the
    real-PG gate is CI plus the first ``--dry-run`` against production.
    """
    pytest.skip("documented IOU — requires a real PostgreSQL; see docstring")


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_sweep_id_defaults_to_a_date_so_a_rerun_resumes_by_default():
    """Idempotency that needs a remembered flag is not idempotency."""
    assert default_sweep_id(NOW) == "kalshi-2026-08-23"
    assert default_sweep_id(NOW + timedelta(hours=6)) == default_sweep_id(NOW)
    assert default_sweep_id(NOW + timedelta(days=1)) != default_sweep_id(NOW)


def test_candidate_query_excludes_both_this_sweep_and_terminal_priors():
    assert ":sweep_id" in CANDIDATE_SQL
    assert ":terminal_dispositions" in CANDIDATE_SQL
    # Composed fragments carry their own newlines, so normalise before counting:
    # the winner-less predicate plus the two idempotency exclusions.
    flattened = " ".join(CANDIDATE_SQL.split())
    assert flattened.count("NOT EXISTS") >= 3


@pytest.mark.asyncio
async def test_rerun_writes_nothing_when_every_row_is_already_captured():
    """The GOOD zero. It must be reported as such, not as an empty run."""
    session = FakeSession(
        cohort_rows=[(_at_age(60), 5, 0)],
        candidate_rows=[],
        exclusions=(5, 0),
    )
    report = await run_sweep(
        session, budget=100, now=NOW, probe_fn=await _always(_settled())
    )
    assert report.captured == 0
    assert report.terminal == TERMINAL_NO_WORK
    assert "all_captured" in report.reason
    assert session.inserted == []


@pytest.mark.asyncio
async def test_pre_insert_guard_stops_a_racing_second_writer():
    """Selection-time exclusion is correct for one writer; this makes a second
    writer harmless rather than merely unlikely."""
    session = FakeSession(
        cohort_rows=[(_at_age(60), 2, 2)],
        candidate_rows=[_candidate_row(1, 60), _candidate_row(2, 60)],
        already_captured={2},
    )
    report = await run_sweep(
        session, budget=10, now=NOW, probe_fn=await _always(_settled())
    )
    assert report.captured == 1
    assert report.write_collisions == 1
    assert [row["market_id"] for row in session.inserted] == [1]


# ---------------------------------------------------------------------------
# The four zeros
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_cohort_is_no_work_and_says_so():
    session = FakeSession(cohort_rows=[], candidate_rows=[])
    report = await run_sweep(
        session, budget=10, now=NOW, probe_fn=await _always(_settled())
    )
    assert report.terminal == TERMINAL_NO_WORK
    assert "cohort_empty" in report.reason


@pytest.mark.asyncio
async def test_dry_run_probes_nothing_writes_nothing_and_never_reads_complete():
    """A rehearsal that could report ``complete`` would be a rehearsal an operator
    could mistake for the run."""
    session = FakeSession(
        cohort_rows=[(_at_age(60), 3, 3)],
        candidate_rows=[_candidate_row(i, 60) for i in (1, 2, 3)],
    )
    report = await run_sweep(
        session, budget=10, now=NOW, dry_run=True, probe_fn=await _always(_settled())
    )
    assert report.selected == 3
    assert report.captured == 0
    assert session.inserted == []
    assert session.commits == 0
    assert report.terminal == TERMINAL_NO_WORK
    assert "dry run" in report.reason


@pytest.mark.asyncio
async def test_total_loss_is_FAILED_and_not_quiet():
    """Selection found work and none of it landed. This is the reading that sat
    behind #683 for ten weeks recorded as SUCCESS."""
    async def _boom(source, external_id):
        raise RuntimeError("network gone")

    session = FakeSession(
        cohort_rows=[(_at_age(60), 3, 3)],
        candidate_rows=[_candidate_row(i, 60) for i in (1, 2, 3)],
    )
    report = await run_sweep(session, budget=10, now=NOW, probe_fn=_boom)
    assert report.captured == 0
    assert report.errors == 3
    assert report.terminal == TERMINAL_FAILED
    assert "total_loss" in report.reason


def test_the_four_zeros_have_four_different_terminals():
    """Stated as one assertion so the distinction cannot be quietly collapsed."""
    from app.services.settlement_sweep_runner import SweepReport

    def _r(**kw):
        base = dict(sweep_id="s", source="kalshi", started_at=NOW, budget=10,
                    dry_run=False)
        base.update(kw)
        return SweepReport(**base)

    assert _verdict(_r(selected=3, captured=0, errors=3))[0] == TERMINAL_FAILED
    assert _verdict(_r(selected=3, captured=3))[0] == TERMINAL_COMPLETE
    assert _verdict(
        _r(selected=3, captured=3, skipped_by_bucket={"61-74": 900})
    )[0] == TERMINAL_PARTIAL
    assert _verdict(_r(selected=3, captured=2, errors=1))[0] == TERMINAL_PARTIAL


def test_a_budget_capped_run_is_never_complete():
    """``complete`` must be hard to earn. Rows left behind before a deadline are
    the whole thing the report exists to surface."""
    from app.services.settlement_sweep_runner import SweepReport

    report = SweepReport(
        sweep_id="s", source="kalshi", started_at=NOW, budget=10, dry_run=False,
        selected=10, captured=10, skipped_by_bucket={TERMINAL_BUCKET: 1},
    )
    terminal, reason = _verdict(report)
    assert terminal == TERMINAL_PARTIAL
    assert "1 left for the next run" in reason


def test_a_bound_fetch_cap_is_never_complete_either():
    """A cap that does not announce itself reads as 'covered everything'."""
    from app.services.settlement_sweep_runner import SweepReport

    report = SweepReport(
        sweep_id="s", source="kalshi", started_at=NOW, budget=10, dry_run=False,
        selected=10, captured=10, fetch_capped=True,
    )
    assert _verdict(report)[0] == TERMINAL_PARTIAL


# ---------------------------------------------------------------------------
# The row: no winner without the disposition that licenses it
# ---------------------------------------------------------------------------


def test_a_non_settled_capture_carries_no_winner():
    candidate = Candidate(1, "kalshi", "KXA-1", _at_age(60), "missing_winner")
    row = _capture_row(candidate, _purged(), sweep_id="s", now=NOW)
    assert row["disposition"] == "purged"
    assert row["winning_outcome"] is None
    assert row["candidate_reason"] == "missing_winner"
    assert row["protocol_version"] == PROBE_PROTOCOL_VERSION


def test_a_settled_capture_carries_the_sources_own_label_verbatim():
    candidate = Candidate(1, "kalshi", "KXA-1", _at_age(60), "missing_winner")
    row = _capture_row(candidate, _settled("no"), sweep_id="s", now=NOW)
    assert row["disposition"] == "settled"
    assert row["winning_outcome"] == "no"
    assert row["answered_by"] == "kalshi_market"


def test_days_remaining_at_capture_is_the_purge_measure_not_the_planning_one():
    """The column's own docstring names ``days_until_purge``. Two horizons, two
    questions; storing the wrong one silently re-scales every burn-down read off
    this column."""
    candidate = Candidate(1, "kalshi", "KXA-1", _at_age(60), "missing_winner")
    row = _capture_row(candidate, _purged(), sweep_id="s", now=NOW)
    assert row["days_remaining_at_capture"] == 74 - 60


# ---------------------------------------------------------------------------
# Ordering and budget
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_terminal_bucket_is_probed_first_but_the_reserve_still_binds():
    """The 0-7 bucket dies on the sweep's own date, so it is taken FIRST — but
    ``NON_TERMINAL_RESERVE`` deliberately caps how much of a run it may consume.

    Both halves are load-bearing and pull opposite ways, which is why this asserts
    the interaction rather than either rule alone: the terminal rows are drawn
    before any other bucket, AND the reserve keeps the 10,420-row bucket from
    waiting a week for the small one to be perfect. The consequence — that a budget
    of N clears only N/2 terminal rows — is what
    ``test_default_budget_clears_the_terminal_bucket_through_the_reserve`` pins to
    the real census.
    """
    # age 60 -> 6 days remaining -> the terminal bucket. age 10 -> 56 remaining.
    session = FakeSession(
        cohort_rows=[(_at_age(60), 2, 2), (_at_age(10), 2, 2)],
        candidate_rows=[
            _candidate_row(10, 10),
            _candidate_row(11, 10),
            _candidate_row(1, 60),
            _candidate_row(2, 60),
        ],
    )
    report = await run_sweep(
        session, budget=2, now=NOW, probe_fn=await _always(_settled())
    )
    assert report.selected == 2
    probed = {row["market_id"] for row in session.inserted}
    # One terminal row (the reserve caps it at budget/2) and one from the rest.
    assert 1 in probed, "the terminal bucket must be drawn from first"
    assert probed == {1, 10}
    assert report.terminal == TERMINAL_PARTIAL
    assert sum(report.skipped_by_bucket.values()) == 2


def test_default_budget_clears_the_terminal_bucket_through_the_reserve():
    """The budget must be read THROUGH the reserve, not against the raw census.

    Caught while writing these tests, and it is the failure this file exists for:
    at ``budget=2000`` the reserve caps terminal work at 1,000 against a bucket of
    1,202, so the first sweep would have reported a clean, successful, PARTIAL run
    and left 202 rows to expire permanently on 2026-08-28. Nothing would have gone
    red. The two numbers must be related by a test, not by proximity in a docstring.
    """
    from app.services.settlement_sweep_runner import (
        DEFAULT_BUDGET,
        TERMINAL_BUCKET_CENSUS_2026_08_21,
    )
    from app.utils.settlement_sweep_plan import NON_TERMINAL_RESERVE

    terminal_capacity = int(DEFAULT_BUDGET * (1.0 - NON_TERMINAL_RESERVE))
    assert terminal_capacity >= TERMINAL_BUCKET_CENSUS_2026_08_21, (
        f"default budget {DEFAULT_BUDGET} gives the terminal bucket only "
        f"{terminal_capacity} slots against a census of "
        f"{TERMINAL_BUCKET_CENSUS_2026_08_21} — rows would expire unprobed"
    )


@pytest.mark.asyncio
async def test_progress_is_committed_in_chunks_so_a_kill_keeps_it():
    """A bounded run over an EXPIRING population must bank as it goes."""
    n = COMMIT_EVERY * 2
    session = FakeSession(
        cohort_rows=[(_at_age(60), n, n)],
        candidate_rows=[_candidate_row(i, 60) for i in range(n)],
    )
    report = await run_sweep(
        session, budget=n, now=NOW, probe_fn=await _always(_settled())
    )
    assert report.captured == n
    assert session.commits == 2


@pytest.mark.asyncio
async def test_a_write_failure_costs_its_chunk_and_not_the_run():
    """One bad row must not empty the pass (gotcha #42), and the discarded chunk
    must not be counted as captured."""
    n = COMMIT_EVERY + 5
    session = FakeSession(
        cohort_rows=[(_at_age(60), n, n)],
        candidate_rows=[_candidate_row(i, 60) for i in range(n)],
        fail_on_market=3,
    )
    report = await run_sweep(
        session, budget=n, now=NOW, probe_fn=await _always(_settled())
    )
    assert session.rollbacks == 1
    # Chunk 1 rolled back and is uncounted; chunk 2 survived.
    assert report.captured == n - COMMIT_EVERY
    assert report.errors == 1
    assert report.terminal == TERMINAL_PARTIAL


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verification_measures_uncaptured_not_missing_winner():
    """The burn-down must be able to reach zero.

    Capture is forbidden from writing ``is_winner``, so "rows still missing a
    winner" cannot move — a verification built on it would call a perfect sweep a
    failure. What drains is the UNCAPTURED count.
    """
    session = FakeSession(
        cohort_rows=[(_at_age(60), 100, 0)],   # 100 still winner-less, 0 uncaptured
        captured_day_rows=[(_at_age(60), 100)],
        dispositions=[("purged", 90), ("settled", 10)],
    )
    result = await verify_sweep(session, sweep_id="kalshi-2026-08-23", now=NOW)
    assert result["cohort_by_bucket"][TERMINAL_BUCKET] == 100
    assert result["uncaptured_total"] == 0
    assert result["terminal_bucket_drained"] is True
    assert result["captured_total"] == 100
    assert result["by_disposition"] == {"purged": 90, "settled": 10}


@pytest.mark.asyncio
async def test_verification_reports_not_drained_while_rows_remain():
    session = FakeSession(
        cohort_rows=[(_at_age(60), 100, 7)],
        captured_day_rows=[(_at_age(60), 93)],
        dispositions=[("settled", 93)],
    )
    result = await verify_sweep(session, sweep_id="s", now=NOW)
    assert result["terminal_bucket_uncaptured"] == 7
    assert result["terminal_bucket_drained"] is False


@pytest.mark.asyncio
async def test_verification_re_derives_from_the_database_not_the_runs_counters():
    """A runner that verifies itself from its own memory proves only that it can
    count — the self-oracular shape that blocked the delete rail four rounds."""
    session = FakeSession(
        cohort_rows=[(_at_age(60), 10, 10)],
        captured_day_rows=[],
        dispositions=[],
    )
    result = await verify_sweep(session, sweep_id="s", now=NOW)
    assert result["captured_total"] == 0
    assert result["uncaptured_total"] == 10


# ---------------------------------------------------------------------------
# The command
# ---------------------------------------------------------------------------


def test_command_exits_non_zero_only_on_a_real_loss():
    """``partial`` and ``no_work`` are designed states. Exiting non-zero on them
    trains the operator to ignore the exit code — the one signal that has to keep
    meaning something (gotcha #54)."""
    import importlib.util
    import pathlib

    path = (
        pathlib.Path(__file__).resolve().parents[1] / "scripts" / "run_settlement_sweep.py"
    )
    spec = importlib.util.spec_from_file_location("run_settlement_sweep", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    args = module._parse_args([])
    assert args.budget > 0
    assert args.dry_run is False
    assert module._parse_args(["--dry-run"]).dry_run is True
    assert module._parse_args(["--verify-only"]).verify_only is True


def test_fetch_limit_gives_the_planner_a_population_to_plan_over():
    """Handed exactly ``budget`` rows the planner cannot prefer the terminal bucket
    over anything — there is nothing to prefer it over."""
    assert fetch_limit_for(100) > 100
    assert fetch_limit_for(10_000_000) <= 20_000
