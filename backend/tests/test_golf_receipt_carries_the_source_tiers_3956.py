"""#3956: the golf repair publishes WHICH TIER its count came from.

**The ship.** 714 Kalshi golf markets still carry Kalshi's Sunday resolution
date instead of the day the tournament starts. Fixing that means turning on
Queue #189's kill switch, and nobody can responsibly turn it on from the count
alone: `_fix_golf_commence_times` resolves each market through three tiers —
DataGolf's own stored start, the live DataGolf schedule, and a
`close_time - 4.5 days` heuristic — and its own docstring warns that the
heuristic tier alone can rewrite ~every resolved golf market (~1.7K markets /
~15.5K cal_prob outcomes). "3,287 would move" is only actionable beside "and N
of them are a guess". That breakdown went to `logger.info`, and `heroku logs` is
EPERM from the agent sandbox, so in practice it did not exist for the operator.

**The trap this file mostly exists for.** The issue's suggested scope was
"carry `source_counts` onto the receipt". `source_counts` is the wrong number.
It is incremented where a market's TIER IS RESOLVED, which happens for every
market in the query (it requires a non-NULL commence_time, so Tier 3 always
catches), while `fixed` only increments for the markets whose target is more
than an hour away. On 2026-09-08 that is 3,393 considered vs 3,287 reported.

Publishing the considered split beside the reported count would be a tier
breakdown silently describing 106 markets the repair leaves alone — and those
106 are precisely the ones already ~correct, which skews them toward Tier 1. So
it would UNDER-state the heuristic share and make enabling look SAFER than it
is: the same over-claiming shape #3952 just removed from the count itself,
re-introduced one field along, in the exact direction the kill switch exists to
guard. `test_the_breakdown_counts_the_fixed_set_not_the_considered_set` is the
guard for that and it fails against the suggested shape.
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
    """Serves canned SELECT results in order; records every statement issued."""

    def __init__(self, results, log):
        self._results = list(results)
        self._i = 0
        self._log = log

    async def execute(self, stmt, params=None):
        self._log.append(str(stmt))
        if self._i < len(self._results):
            r = self._results[self._i]
            self._i += 1
            return r
        return _Result([])

    async def commit(self):
        self._log.append("COMMIT")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


# DataGolf stores midnight UTC on Round 1; the repair backs up 18h from it.
_DG_ROUND_1 = _utc(2026, 6, 5)
_DG_TARGET = _utc(2026, 6, 4, 6)


def _install_population(monkeypatch):
    """Three resolved Kalshi golf markets: two that move, one that does not.

    The load-bearing one is `already_right`: Tier 1 resolves for it, so it lands
    in `source_counts`, but its commence_time is ALREADY the target, so it never
    reaches `fixed`. It is the shape of the 106 real markets that separate the
    considered set from the reported one — and, like them, it sits on the
    trustworthy tier, which is why counting it inflates `datagolf_db`.

    Tier 2 (the live DataGolf schedule) is deliberately NOT exercised, and the
    schedule is returned empty to keep it unreachable. It cannot fire against a
    faithful fixture: `futures_markets.commence_time` is `DateTime(timezone=True)`
    so production rows are tz-AWARE, while Tier 2 builds its target from
    `datetime.fromisoformat("2026-07-16")`, which is naive. The `>1h` comparison
    below is outside Tier 2's `except (ValueError, TypeError)`, so the first
    market resolving that way raises `TypeError: can't subtract offset-naive and
    offset-aware datetimes` and takes the WHOLE repair down into
    `post_loop_fixups_failed`. Filed as #3984 and deliberately not fixed here,
    because changing which tier a market resolves to would change the very
    numbers this ship publishes for the Queue #189 decision.
    """
    dg_row = _Row(name="Masters Tournament", commence_time=_DG_ROUND_1)

    tier1_fixed = _Row(
        id=1, name="Masters Tournament Winner", commence_time=_utc(2026, 6, 10, 18)
    )
    already_right = _Row(
        id=2, name="Masters Tournament Top 5", commence_time=_DG_TARGET
    )
    tier3_fixed = _Row(
        id=3, name="Obscure Invitational Winner", commence_time=_utc(2026, 7, 1, 18)
    )

    log: list = []
    sessions = iter(
        [
            _MockSession([_Result([dg_row])], log),
            _MockSession([_Result([tier1_fixed, already_right, tier3_fixed])], log),
        ]
    )
    monkeypatch.setattr(kalshi_task, "get_task_session", lambda: next(sessions))

    async def _schedule(*a, **k):
        return None

    monkeypatch.setattr(golf_mod, "_get_golf_schedule", _schedule)

    def _norm(name, schedule=None):
        return "masters" if "Masters" in name else "other"

    monkeypatch.setattr(golf_mod, "_normalize_tournament", _norm)
    return log


# ── The ship ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_breakdown_counts_the_fixed_set_not_the_considered_set(monkeypatch):
    """The guard against the shape the issue itself suggested.

    Three markets, all three resolve a tier, only two cross the >1h threshold.
    The breakdown must describe the two. Carrying `source_counts` instead
    reports `datagolf_db: 2` and sums to 3 — a split describing a market the
    repair would not touch, biased toward the trustworthy tier.
    """
    _install_population(monkeypatch)
    detail: dict = {}

    fixed = await kalshi_task._fix_golf_commence_times(dry_run=True, detail=detail)

    assert fixed == 2, "expected two of the three markets to be more than an hour off"
    assert detail == {"datagolf_db": 1, "schedule": 0, "heuristic": 1}, (
        "the breakdown is describing markets the repair leaves alone. A "
        "`datagolf_db: 2` here is the considered set (`source_counts`) leaking "
        "onto the receipt: it counts the market that was already correctly "
        "dated, which over-states the trustworthy tier and under-states the "
        "4.5-day guess — the direction Queue #189's gate exists to prevent."
    )


@pytest.mark.asyncio
async def test_the_breakdown_always_sums_to_the_count_it_is_published_beside(
    monkeypatch,
):
    """The invariant, stated independently of the tier split above.

    This is the one an operator relies on without knowing any of the above: the
    numbers in the detail account for the headline count and nothing else. A
    future tier added to the resolver but not to the fixed-set counter fails
    here even if the split in the test above is updated to match it.
    """
    _install_population(monkeypatch)
    detail: dict = {}

    fixed = await kalshi_task._fix_golf_commence_times(dry_run=True, detail=detail)

    assert sum(detail.values()) == fixed, (
        f"detail {detail} sums to {sum(detail.values())} but the repair reports "
        f"{fixed} — the breakdown and the count describe different populations"
    )


@pytest.mark.asyncio
async def test_the_breakdown_is_of_a_rehearsal_and_still_writes_nothing(monkeypatch):
    """Publishing the tiers must not have turned the dry run into a real one.

    The whole ship is read-only; #3952's premise (dry-run returns a nonzero
    count having executed no UPDATE) has to survive it.
    """
    log = _install_population(monkeypatch)
    detail: dict = {}

    await kalshi_task._fix_golf_commence_times(dry_run=True, detail=detail)

    assert detail, "nothing published, so the rest of this gate proves nothing"
    assert not any("UPDATE" in s for s in log), "dry-run must not UPDATE"
    assert "COMMIT" not in log, "dry-run must not commit"


@pytest.mark.asyncio
async def test_the_out_param_is_optional_for_the_callers_that_want_the_count(
    monkeypatch,
):
    """`backfill_winners` and the admin endpoint call this with no `detail`.

    Widening the return type would have churned them; the opt-in out-param must
    therefore stay genuinely optional, and the count identical without it.
    """
    _install_population(monkeypatch)
    assert await kalshi_task._fix_golf_commence_times(dry_run=True) == 2


@pytest.mark.asyncio
async def test_a_reused_detail_dict_does_not_accumulate_across_runs(monkeypatch):
    """The out-param is cleared, not merged into.

    A caller that hoists the dict out of the loop would otherwise publish the
    sum of every beat so far, which reads as a repair whose backlog is growing.
    """
    detail = {"datagolf_db": 999, "stale_tier": 7}

    _install_population(monkeypatch)
    await kalshi_task._fix_golf_commence_times(dry_run=True, detail=detail)

    assert detail == {"datagolf_db": 1, "schedule": 0, "heuristic": 1}, (
        "a stale key or an accumulated count survived the run"
    )


# ── The breakdown reaches the receipt, in the right mode's map ──────────────


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
    poller's top-level `except` files it into `stats["errors"]` and skips the
    whole receipt block — so it reads as "no ring entry", not as a broken fake.
    The `assert ring` below is what makes that legible.
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


async def _run_poll(monkeypatch, *, golf_enabled):
    """Drive the real `_poll_kalshi_markets` over an EMPTY scan.

    Zero events means the post-loop block is reached immediately and the real
    routing runs; the only fake is the golf repair, which fills its `detail`
    out-param the way the real one does.
    """
    fake = _Redis()

    async def _golf(*a, **kw):
        d = kw.get("detail")
        if d is not None:
            d.clear()
            d.update(_TIERS)
        return _TOTAL

    async def _other(*a, **kw):
        return 0

    service = MagicMock()
    service.get_all_events = AsyncMock(return_value=[])
    service.close = AsyncMock()

    @asynccontextmanager
    async def _session_cm():
        yield _EmptySession()

    monkeypatch.setattr(redis_state, "get_redis_client", lambda: fake)
    monkeypatch.setattr(kalshi_task, "get_task_session", _session_cm)
    monkeypatch.setattr(
        kalshi_task, "_golf_commence_fix_enabled", lambda: golf_enabled
    )
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
async def test_a_rehearsal_breakdown_is_filed_under_the_rehearsal(monkeypatch):
    """Switch OFF: the detail follows its count into the dry-run map.

    The count and its breakdown must never end up in different maps — a
    breakdown read against the other mode's number is exactly the misreading
    #3952 split the counts to prevent.
    """
    head = await _run_poll(monkeypatch, golf_enabled=False)

    assert head["post_loop_fixups_dry_run_detail"] == {"golf_commence_fixed": _TIERS}
    assert head["post_loop_fixups_ran_detail"] == {}, (
        "a breakdown of work that never happened is filed as work"
    )
    assert (
        sum(head["post_loop_fixups_dry_run_detail"]["golf_commence_fixed"].values())
        == head["post_loop_fixups_dry_run"]["golf_commence_fixed"]
    ), "the published breakdown does not account for the published count"


@pytest.mark.asyncio
async def test_with_the_switch_on_the_breakdown_describes_real_work(monkeypatch):
    """The positive control, and the reason the assertions above are not vacuous.

    Never populating either field, or dropping the golf call entirely, also
    satisfies "ran_detail is empty in dry-run". Neither survives this.
    """
    head = await _run_poll(monkeypatch, golf_enabled=True)

    assert head["post_loop_fixups_ran_detail"] == {"golf_commence_fixed": _TIERS}
    assert head["post_loop_fixups_dry_run_detail"] == {}, (
        "the repair wrote, so nothing is a rehearsal"
    )


def test_the_new_fields_survive_serialization_with_their_shape(monkeypatch):
    """`to_dict` is `asdict`, so a nested dict must round-trip through JSON.

    The receipt is read over HTTP; a field that only exists in-process is the
    unreachable-number bug this ship is fixing.
    """
    report = ksr.KalshiScanReport(started_at="2026-09-08T14:45:00+00:00")
    report.post_loop_fixups_dry_run = {"golf_commence_fixed": _TOTAL}
    report.post_loop_fixups_dry_run_detail = {"golf_commence_fixed": dict(_TIERS)}

    round_tripped = json.loads(json.dumps(report.to_dict()))

    assert round_tripped["post_loop_fixups_dry_run_detail"] == {
        "golf_commence_fixed": _TIERS
    }
    assert round_tripped["post_loop_fixups_ran_detail"] == {}


def test_both_detail_fields_default_to_empty_rather_than_absent():
    """Absent and empty must not wear the same shape (gotcha #53).

    An empty map says the beat got here and had nothing to file; a missing key
    would say the receipt predates the field. Both fields therefore always
    serialize.
    """
    fresh = ksr.KalshiScanReport(started_at="2026-09-08T00:00:00+00:00").to_dict()

    assert fresh["post_loop_fixups_ran_detail"] == {}
    assert fresh["post_loop_fixups_dry_run_detail"] == {}
