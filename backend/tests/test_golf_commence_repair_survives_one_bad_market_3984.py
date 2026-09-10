"""#3984: one unevaluable market must not abort the whole golf repair.

**The ship.** `_fix_golf_commence_times` evaluates ~3,400 resolved Kalshi golf
markets in a single loop with no per-market guard, so the FIRST market that
raises takes the entire pass into `post_loop_fixups_failed` — thousands of
markets that would have been repaired, lost to one bad row. That is gotcha #42
("one bad item must never wipe a scoring pass") unapplied to this loop. The
operator deciding Queue #189 then sees a repair that produced nothing, with no
way to tell "nothing to do" from "died on row 1".

**Two independent halves, both guarded here.**

1. *The contract half.* Tier 2 builds its target from
   `datetime.fromisoformat(schedule_by_key[key])`. That returns an AWARE
   datetime only because `_get_golf_schedule` (`routes/golf.py`) happens to
   emit `f"{t.start_date}T00:00:00+00:00"` — an offset suffix produced in a
   different module, relied on by this module's arithmetic, guarded by nothing.
   `futures_markets.commence_time` is `DateTime(timezone=True)`, so the moment
   that f-string emits a bare date the `>1h` comparison raises
   `TypeError: can't subtract offset-naive and offset-aware datetimes` — and it
   sits OUTSIDE Tier 2's `except (ValueError, TypeError)`, so the except does
   not catch it.

2. *The blast-radius half.* Whatever raises and for whatever reason, it must
   cost ONE market, not all of them.

**A correction, recorded because the reasoning error is the reusable part.**
#3984 was originally filed claiming Tier 2 crashes in production today, "latent
— nothing reaches Tier 2". Production falsified it hours later: the 16:45Z scan
on `20bf161c` published `"schedule": 62` with `failed: []`. Tier 2 fires 62
times a beat and does not crash, because of that offset suffix. The filing
inferred "the path is unreached" from "the repair succeeded", when the simpler
reading was "the path is reached and does not crash" — a theory that explains an
absence by assuming its own trigger never fires is unfalsifiable until you
measure the trigger. What survives is the unguarded cross-module contract above,
and the blast radius, which was always true.
"""

import json
import os
from contextlib import ExitStack, asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.routes.golf as golf_mod
from app.tasks import kalshi as kalshi_task
from app.tasks import redis_state
from app.utils import kalshi_scan_report as ksr


# ── Fakes for driving the REAL _fix_golf_commence_times ─────────────────────


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _MockSession:
    """Serves canned SELECT results in order; records every statement issued.

    The log holds `(sql, params)`, not just the SQL. Logging the statement text
    alone makes any assertion about a WRITTEN VALUE vacuous — every run of this
    repair emits byte-identical UPDATE text and carries the datetime in the
    bound params, so a test comparing statements would pass no matter what
    instant was written. A mutation that shifted the timezone survived exactly
    that mistake.
    """

    def __init__(self, results, log):
        self._results = list(results)
        self._i = 0
        self._log = log

    async def execute(self, stmt, params=None):
        self._log.append((str(stmt), params))
        if self._i < len(self._results):
            r = self._results[self._i]
            self._i += 1
            return r
        return _Result([])

    async def commit(self):
        # Same (sql, params) shape as every other entry, so readers can unpack
        # the log uniformly.
        self._log.append(("COMMIT", None))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


# DataGolf stores midnight UTC on Round 1; the repair backs up 18h from it.
_DG_ROUND_1 = _utc(2026, 6, 5)


def _install(monkeypatch, markets, *, schedule=None, raise_on=None):
    """Drive the real repair over `markets`.

    `schedule` is the live-schedule payload Tier 2 reads. `raise_on` is a market
    name for which `_normalize_tournament` blows up — the generic "one row is
    poison" case, deliberately NOT a tz failure so it stays a real test of the
    per-market guard after the tz contract is defended.
    """
    dg_row = _Row(name="Masters Tournament", commence_time=_DG_ROUND_1)

    log: list = []
    sessions = iter(
        [
            _MockSession([_Result([dg_row])], log),
            _MockSession([_Result(markets)], log),
        ]
    )
    monkeypatch.setattr(
        kalshi_task,
        "get_task_session",
        # #4482: the budget is a kwarg on `get_task_session` now, not a `SET`.
        lambda **_budget: next(sessions),
    )

    async def _schedule(*a, **k):
        return schedule

    monkeypatch.setattr(golf_mod, "_get_golf_schedule", _schedule)

    def _norm(name, sched=None):
        if raise_on is not None and name == raise_on:
            raise RuntimeError("normalizer exploded on this row")
        if "Masters" in name:
            return "masters"
        if "Open Championship" in name:
            return "the_open"
        return "other"

    monkeypatch.setattr(golf_mod, "_normalize_tournament", _norm)
    return log


# ── Half 1: the cross-module tz contract ────────────────────────────────────

_BARE_DATE_SCHEDULE = [{"key": "the_open", "start_date": "2026-07-16"}]


@pytest.mark.asyncio
async def test_tier_2_survives_a_schedule_that_emits_a_bare_date(monkeypatch):
    """The guard for the unguarded contract. RED before this ship.

    `_get_golf_schedule` emits an offset today; nothing enforces that it keeps
    doing so. Feed Tier 2 a bare `"2026-07-16"` — the shape a date column
    stringifies to without the f-string's suffix — and the repair must still
    resolve the market on Tier 2 rather than raising out of the loop.
    """
    m = _Row(id=1, name="Open Championship Winner", commence_time=_utc(2026, 7, 19, 18))
    _install(monkeypatch, [m], schedule=_BARE_DATE_SCHEDULE)
    detail: dict = {}

    fixed = await kalshi_task._fix_golf_commence_times(dry_run=True, detail=detail)

    assert fixed == 1, (
        "the bare-date market was not reported as fixable — Tier 2 either raised "
        "out of the loop or silently fell through to the heuristic"
    )
    assert detail == {"datagolf_db": 0, "schedule": 1, "heuristic": 0}, (
        f"expected the market to resolve on Tier 2, got {detail}. A "
        "`heuristic: 1` here means the tz failure was swallowed by Tier 2's "
        "`except` and the 4.5-day guess quietly took over — which is worse than "
        "crashing, because it moves the market onto the untrusted tier while "
        "the receipt reports business as usual."
    )


@pytest.mark.asyncio
async def test_a_bare_date_is_read_as_midnight_utc_not_shifted_by_a_local_zone(
    monkeypatch,
):
    """The normalization has to pick the SAME instant the offset form produces.

    `_get_golf_schedule`'s `…T00:00:00+00:00` means midnight UTC, so a bare date
    must be coerced to midnight UTC too. Coercing to local time (or to the
    server's zone) would silently move every Tier-2 target by hours, which is
    the class of bug this repair exists to fix.
    """
    def _written(log):
        writes = [p for s, p in log if "UPDATE futures_markets" in s and p]
        assert len(writes) == 1, f"expected exactly one market write, got {writes}"
        return writes[0]["start"]

    m = _Row(id=1, name="Open Championship Winner", commence_time=_utc(2026, 7, 19, 18))
    log = _install(monkeypatch, [m], schedule=_BARE_DATE_SCHEDULE)
    await kalshi_task._fix_golf_commence_times(dry_run=False, detail={})

    offset_form = [{"key": "the_open", "start_date": "2026-07-16T00:00:00+00:00"}]
    m2 = _Row(
        id=1, name="Open Championship Winner", commence_time=_utc(2026, 7, 19, 18)
    )
    log2 = _install(monkeypatch, [m2], schedule=offset_form)
    await kalshi_task._fix_golf_commence_times(dry_run=False, detail={})

    # Absolute, not merely self-consistent: midnight UTC on 2026-07-16, less the
    # 18h eve-of-Round-1 convention the repair applies to every tier. Asserting
    # only that the two forms AGREE would be satisfied by both being wrong in
    # the same direction, which is what a changed default zone would do.
    assert _written(log) == _utc(2026, 7, 15, 6), (
        f"the bare date was not read as midnight UTC — wrote {_written(log)}, "
        "so the coercion assumed some other zone and moved every Tier-2 target"
    )
    assert _written(log) == _written(log2), (
        "the bare-date form and the offset form resolved to different instants"
    )


# ── Half 2: one bad market costs one market ─────────────────────────────────


def _three_markets():
    return [
        _Row(id=1, name="Masters Tournament Winner", commence_time=_utc(2026, 6, 10)),
        _Row(id=2, name="POISON Invitational", commence_time=_utc(2026, 7, 1, 18)),
        _Row(id=3, name="Obscure Invitational Winner", commence_time=_utc(2026, 7, 1)),
    ]


@pytest.mark.asyncio
async def test_one_unevaluable_market_does_not_abort_the_pass(monkeypatch):
    """The blast-radius guard. RED before this ship.

    Before: the RuntimeError on market 2 propagates out of
    `_fix_golf_commence_times`, the caller files `golf_commence_fixed` into
    `post_loop_fixups_failed`, and markets 1 and 3 — which were perfectly
    repairable — are lost with it. In production that is one row costing 3,287.
    """
    _install(monkeypatch, _three_markets(), raise_on="POISON Invitational")
    detail: dict = {}
    unevaluable: dict = {}

    fixed = await kalshi_task._fix_golf_commence_times(
        dry_run=True, detail=detail, unevaluable=unevaluable
    )

    assert fixed == 2, (
        f"expected the two healthy markets to survive the poison row, got {fixed}"
    )
    assert detail == {"datagolf_db": 1, "schedule": 0, "heuristic": 1}
    assert unevaluable == {"RuntimeError": 1}, (
        f"the skipped row was swallowed rather than surfaced, got {unevaluable}"
    )


@pytest.mark.asyncio
async def test_an_unevaluable_market_is_counted_in_neither_the_count_nor_the_tiers(
    monkeypatch,
):
    """#3956's invariant has to survive the new skip path.

    The tier breakdown accounts for the headline count and nothing else. A row
    that could not be evaluated has no tier, so it must appear in neither — the
    failure mode being a repair that reports N fixed while its breakdown sums to
    N+1 because a half-resolved poison row incremented a tier on its way out.
    """
    _install(monkeypatch, _three_markets(), raise_on="POISON Invitational")
    detail: dict = {}
    unevaluable: dict = {}

    fixed = await kalshi_task._fix_golf_commence_times(
        dry_run=True, detail=detail, unevaluable=unevaluable
    )

    assert sum(detail.values()) == fixed, (
        f"detail {detail} sums to {sum(detail.values())} but the repair reports "
        f"{fixed} — the skipped row leaked into the breakdown"
    )
    assert sum(unevaluable.values()) == 1


@pytest.mark.asyncio
async def test_a_clean_pass_reports_no_unevaluable_rows(monkeypatch):
    """The positive control: the counter is not simply always populated.

    Without this, a `unevaluable` that counted every market would satisfy the
    assertions above.
    """
    _install(monkeypatch, _three_markets())
    unevaluable: dict = {}

    fixed = await kalshi_task._fix_golf_commence_times(
        dry_run=True, unevaluable=unevaluable
    )

    assert fixed == 3, "all three markets are more than an hour off"
    assert unevaluable == {}, f"a clean pass reported skipped rows: {unevaluable}"


@pytest.mark.asyncio
async def test_a_reused_unevaluable_dict_does_not_accumulate_across_runs(monkeypatch):
    """Same contract as `detail`: cleared, not merged into.

    A caller hoisting the dict out of the beat loop would otherwise publish a
    running total, which reads as an error rate that only ever grows.
    """
    unevaluable = {"TypeError": 99, "StaleError": 4}

    _install(monkeypatch, _three_markets(), raise_on="POISON Invitational")
    await kalshi_task._fix_golf_commence_times(dry_run=True, unevaluable=unevaluable)

    assert unevaluable == {"RuntimeError": 1}, (
        "a stale key or an accumulated count survived the run"
    )


@pytest.mark.asyncio
async def test_both_out_params_stay_optional_for_the_count_only_callers(monkeypatch):
    """`backfill_winners` and the admin endpoint pass neither.

    They want the count; adding a second out-param must not have made either
    mandatory, and the count must be identical without them.
    """
    _install(monkeypatch, _three_markets(), raise_on="POISON Invitational")
    assert await kalshi_task._fix_golf_commence_times(dry_run=True) == 2


# ── The count reaches the receipt ───────────────────────────────────────────


class _Redis:
    """Enough Redis for the receipt's ring; permissive about the rest."""

    def __init__(self):
        self.kv = {}
        self.lists = {}

    def setex(self, key, ttl, value):
        self.kv[key] = value

    def set(self, key, value, **kw):
        self.kv[key] = value

    def get(self, key):
        return self.kv.get(key)

    def lpush(self, key, value):
        self.lists.setdefault(key, []).insert(0, value)

    def ltrim(self, key, start, end):
        self.lists[key] = self.lists.get(key, [])[start : end + 1]

    def lrange(self, key, start, end):
        return self.lists.get(key, [])[start : end + 1]

    def lindex(self, key, idx):
        try:
            return self.lists.get(key, [])[idx]
        except IndexError:
            return None

    def lset(self, key, idx, value):
        self.lists[key][idx] = value

    def expire(self, key, ttl):
        pass

    def __getattr__(self, _name):
        return lambda *a, **k: None


class _EmptyResult:
    rowcount = 0

    def fetchall(self):
        return []

    def fetchone(self):
        return None

    def first(self):
        return None

    def scalar(self):
        return None

    def scalar_one_or_none(self):
        return None

    def one_or_none(self):
        return None

    def keys(self):
        return []

    def mappings(self):
        return self

    def scalars(self):
        return self

    def all(self):
        return []

    def __iter__(self):
        return iter([])


class _EmptySession:
    """Answers everything with nothing.

    A bare `MagicMock` is NOT usable: `await session.execute(...)` raises, the
    poller's top-level `except` swallows it and the whole receipt block is
    skipped — which reads as "no ring entry", not as a broken fake. The
    `assert ring` in `_run_poll` is what makes that legible.
    """

    async def execute(self, *a, **kw):
        return _EmptyResult()

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def flush(self):
        pass

    async def close(self):
        pass

    def add(self, *a, **kw):
        pass

    def expunge_all(self):
        pass


_TIERS = {"datagolf_db": 1200, "schedule": 87, "heuristic": 2000}
_TOTAL = sum(_TIERS.values())


async def _run_poll(monkeypatch, *, golf_enabled, errors):
    """Drive the real `_poll_kalshi_markets` over an EMPTY scan.

    Zero events means the post-loop block is reached immediately and the real
    routing runs; the only fake is the golf repair itself, which fills both
    out-params the way the real one does.
    """
    fake = _Redis()

    async def _golf(*a, **kw):
        d = kw.get("detail")
        if d is not None:
            d.clear()
            d.update(_TIERS)
        u = kw.get("unevaluable")
        if u is not None:
            u.clear()
            u.update(errors)
        return _TOTAL

    async def _other(*a, **kw):
        return 0

    service = MagicMock()
    service.get_all_events = AsyncMock(return_value=[])
    service.close = AsyncMock()

    @asynccontextmanager
    async def _session_cm(**_budget):
        # #4482: budget kwargs, not a `SET` on the session.
        yield _EmptySession()

    monkeypatch.setattr(redis_state, "get_redis_client", lambda: fake)
    monkeypatch.setattr(kalshi_task, "get_task_session", _session_cm)
    monkeypatch.setattr(kalshi_task, "_golf_commence_fix_enabled", lambda: golf_enabled)
    monkeypatch.setattr(kalshi_task, "_fix_golf_commence_times", _golf)
    for fn in (
        "_fix_golf_round_leader_dates",
        "_fix_hockey_commence_times",
        "_fix_tennis_commence_times",
        "_refine_stand_in_event_starts",
    ):
        monkeypatch.setattr(kalshi_task, fn, _other)

    with ExitStack() as es:
        es.enter_context(
            patch("app.services.kalshi_api.KalshiAPIService", return_value=service)
        )
        es.enter_context(patch.dict(os.environ, {"KALSHI_API_KEY": "test-key"}))
        await kalshi_task._poll_kalshi_markets()

    ring = fake.lists.get(ksr._RING_KEY, [])
    assert ring, (
        "the beat published no ring entry at all, so nothing below is a round "
        "trip — the harness broke, not the ship"
    )
    return json.loads(ring[0])


@pytest.mark.asyncio
async def test_the_skipped_row_count_reaches_the_published_receipt(monkeypatch):
    """The number has to be readable, or it is not published (#3956's lesson).

    `logger.info` is not a publication surface: `heroku logs` is EPERM from the
    agent sandbox, so a count that goes only there does not exist for the
    operator who has to decide Queue #189.
    """
    head = await _run_poll(
        monkeypatch, golf_enabled=False, errors={"TypeError": 3, "KeyError": 1}
    )

    assert head["post_loop_fixups_row_errors"] == {
        "golf_commence_fixed": {"TypeError": 3, "KeyError": 1}
    }
    # The pass still completed and still reported its work: a skipped row is
    # not a failed fix-up, and the two must stay distinguishable.
    assert head["post_loop_fixups_dry_run"]["golf_commence_fixed"] == _TOTAL
    assert "golf_commence_fixed" not in head["post_loop_fixups_failed"]


@pytest.mark.asyncio
async def test_row_errors_are_not_filed_as_deadline_casualties(monkeypatch):
    """`post_loop_fixups_skipped` already means something else.

    It lists fix-ups the block declined to START because the beat ran out of
    budget. Rows this fix-up could not evaluate are a different fact about a
    fix-up that DID run, and folding them together would report a repair as
    never-started when it in fact ran and dropped four rows.
    """
    head = await _run_poll(monkeypatch, golf_enabled=False, errors={"TypeError": 3})

    assert head["post_loop_fixups_skipped"] == [], (
        "row-level skips leaked into the deadline-casualty list"
    )
    assert head["post_loop_fixups_row_errors"]


@pytest.mark.asyncio
async def test_a_clean_beat_files_no_row_errors_but_still_proves_it_ran(monkeypatch):
    """Absence here is unambiguously zero, because another field proves the run.

    Filing every clean beat with an empty map would bloat the receipt for no
    reading gain: "did this fix-up run at all" is already answered by
    `post_loop_fixups_ran` / `_dry_run` (present) versus `_failed` / `_skipped`.
    So the map stays empty on a clean beat — and this test pins the pairing that
    makes that safe to read.
    """
    head = await _run_poll(monkeypatch, golf_enabled=False, errors={})

    assert head["post_loop_fixups_row_errors"] == {}
    assert "golf_commence_fixed" in head["post_loop_fixups_dry_run"], (
        "with no row-error key, this is the field that proves the repair ran — "
        "if it is absent too, an empty row-error map is unreadable"
    )


def test_the_new_field_survives_serialization_and_defaults_to_empty():
    """`to_dict` is `asdict`; the receipt is read over HTTP.

    Empty rather than absent (gotcha #53): a receipt that predates the field and
    a beat that dropped no rows must not wear the same shape.
    """
    fresh = ksr.KalshiScanReport(started_at="2026-09-08T00:00:00+00:00").to_dict()
    assert fresh["post_loop_fixups_row_errors"] == {}

    report = ksr.KalshiScanReport(started_at="2026-09-08T14:45:00+00:00")
    report.post_loop_fixups_row_errors = {"golf_commence_fixed": {"TypeError": 3}}
    round_tripped = json.loads(json.dumps(report.to_dict()))

    assert round_tripped["post_loop_fixups_row_errors"] == {
        "golf_commence_fixed": {"TypeError": 3}
    }
