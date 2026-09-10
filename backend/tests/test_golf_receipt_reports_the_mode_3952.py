"""#3952: the Kalshi scan receipt stops reporting a dry-run rehearsal as work.

**The bug.** `_fix_golf_commence_times` is the one post-loop repair behind a
kill switch — Queue #189's verify-before-enable gate (`golf_commence_fix:enabled`
in Redis, default OFF, gotcha #21), because the Tier-3 heuristic alone can
rewrite ~every resolved golf market and NULL ~15.5K `calibration_probability`
rows. Its `fixed += 1` sits OUTSIDE `if not dry_run:`, so it returns the number
of markets it WOULD have touched. #3192 then published that number as
`post_loop_fixups_ran: {"golf_commence_fixed": 3287}`.

The plain reading of that field — and it is the field's own documented meaning,
"rows it repaired" — is "3,287 golf markets were re-dated this beat". Nothing
was. Measured on the 12:45Z beat of 2026-09-08: 3,287 is **96% of the 3,419**
Kalshi golf markets, a population a writing repair would have drained months
ago, while **714 of them still carry Kalshi's Sunday resolution date** and
DataGolf — the repair's own Tier-1 truth — is 100% Thursday.

This is worse than the silence #3192 removed. A large, specific, reassuring
number is exactly what an operator uses to conclude the area is healthy.

**The shape shipped, and why it is not the pairing the issue first suggested.**
The rehearsal total moves to `post_loop_fixups_dry_run` and `..._ran` carries
**0**. The rejected alternative was to leave 3,287 in `..._ran` and add a list
of dry-run key names beside it. Both are honest to a careful reader; they
differ in what happens to a careless one, and that is the whole decision:

* leave-and-pair fails toward **over**-claiming — miss the second field and you
  read 3,287 repairs that never happened, which is today's bug unchanged;
* route-and-zero fails toward **under**-claiming — miss the new field and you
  read 0, which is true.

An instrument must fail toward under-claiming. So the pairing here is a bonus,
never a prerequisite.

**What the guards below are actually for.** The ship itself is one assertion.
The other seven defend the distinctions this receipt exists to keep, and the
three named here are each a mistake that leaves every other test in the tree
green:

1. **The vanishing trap.** "Report 0 in dry-run" is also satisfied by deleting
   the golf call, by never entering the block, and by dropping the key. The
   positive control (`switch ON`) is what makes the 0 mean "ran and wrote
   nothing" rather than "this assertion is vacuous".
2. **The absent-vs-zero trap.** Routing the key OUT of `..._ran` entirely reads
   identically to "the fix-up never started" — gotcha #53's shape, and the very
   distinction `..._ran` / `..._skipped` / `..._failed` were built to keep. The
   key must be in BOTH maps.
3. **The two-reads trap.** The receipt could name the mode by calling
   `_golf_commence_fix_enabled()` a second time itself. Two independent reads of
   a runtime flag can disagree, and a receipt reporting a mode the repair did
   not run in is this same bug one level up. The caller must read once and pass
   `dry_run=` in.
"""

import json
import os
from contextlib import ExitStack, asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks import kalshi as kalshi_task
from app.tasks import redis_state
from app.utils import kalshi_scan_report as ksr

# The other four post-loop repairs have no kill switch: they write whenever they
# run, so their counts are already honest and must keep flowing to `..._ran`.
_UNGATED = (
    ("golf_round_dates_fixed", "_fix_golf_round_leader_dates"),
    ("hockey_commence_fixed", "_fix_hockey_commence_times"),
    ("tennis_commence_fixed", "_fix_tennis_commence_times"),
    ("stand_in_event_starts_refined", "_refine_stand_in_event_starts"),
)

# Distinct per fix-up so a routing bug that crosses two keys is visible as a
# wrong VALUE rather than passing on a coincidentally equal one.
_UNGATED_RETURNS = {
    "golf_round_dates_fixed": 11,
    "hockey_commence_fixed": 22,
    "tennis_commence_fixed": 33,
    "stand_in_event_starts_refined": 44,
}

# The production reading this issue was filed on.
_REHEARSAL_TOTAL = 3287


class _Redis:
    """Enough Redis for the receipt's ring, permissive about the rest.

    The poller touches Redis for phase markers, the resume cursor and the
    discovery cache; none of those are what is under test, so unknown methods
    are no-ops. The ring methods are real, because the assertions read the ring.
    """

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


class _Result:
    """An empty result set, in every shape the poller asks a result for."""

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


class _Session:
    """An async session that answers everything with nothing.

    A bare `MagicMock` is NOT usable here: `await session.execute(...)` raises
    `object MagicMock can't be used in 'await' expression`, the poller's
    top-level `except` files that into `stats["errors"]` and jumps past the
    whole receipt block — so the gate reads as "no ring entry" rather than as a
    broken fake. The `assert ring` in `_run_poll` is what turns that into a
    legible failure instead of a confusing one.
    """

    async def execute(self, *a, **kw):
        return _Result()

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


async def _run_poll(monkeypatch, *, golf_enabled, golf_returns=_REHEARSAL_TOTAL):
    """Drive the REAL `_poll_kalshi_markets` over an EMPTY scan.

    Zero events means the ingest loop does nothing and the post-loop block is
    reached immediately, well inside its 540s budget — so what runs is the real
    routing code, and the only fakes are the repairs' return values. That is the
    right seam: this gate is about where a count is filed, not about what the
    repairs do to the database (`test_golf_commence_fix.py` owns that, and its
    `test_dry_run_never_writes` is the premise here — dry-run returns a nonzero
    count having executed no UPDATE).

    Returns `(ring_head, calls)` where `calls` records the kwargs each fix-up
    was invoked with.
    """
    fake = _Redis()
    calls: dict = {}

    async def _golf(*a, **kw):
        calls["golf"] = {"args": a, "kwargs": kw}
        return golf_returns

    service = MagicMock()
    service.get_all_events = AsyncMock(return_value=[])
    service.close = AsyncMock()

    @asynccontextmanager
    async def _session_cm(**_budget):
        # #4482: the per-job statement/lock budget is a kwarg on
        # `get_task_session` now, not a `SET` executed on the session.
        yield _Session()

    monkeypatch.setattr(redis_state, "get_redis_client", lambda: fake)
    monkeypatch.setattr(kalshi_task, "get_task_session", _session_cm)
    monkeypatch.setattr(kalshi_task, "_golf_commence_fix_enabled", lambda: golf_enabled)
    monkeypatch.setattr(kalshi_task, "_fix_golf_commence_times", _golf)
    for key, fn in _UNGATED:

        def _make(k):
            async def _f(*a, **kw):
                calls[k] = {"args": a, "kwargs": kw}
                return _UNGATED_RETURNS[k]

            return _f

        monkeypatch.setattr(kalshi_task, fn, _make(key))

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
    return json.loads(ring[0]), calls


@pytest.mark.asyncio
async def test_a_dry_run_reports_zero_repaired_and_files_the_rehearsal_separately(
    monkeypatch,
):
    """The ship. Switch OFF, repair returns 3,287, receipt claims 0 repaired."""
    head, _ = await _run_poll(monkeypatch, golf_enabled=False)

    assert head["post_loop_fixups_ran"]["golf_commence_fixed"] == 0, (
        "the receipt is claiming golf markets were re-dated by a repair the "
        "kill switch held in dry-run — it wrote nothing. This is #3952."
    )
    assert head["post_loop_fixups_dry_run"] == {"golf_commence_fixed": _REHEARSAL_TOTAL}


@pytest.mark.asyncio
async def test_with_the_switch_on_the_count_is_real_work_and_reads_as_such(
    monkeypatch,
):
    """The positive control, and the reason the 0 above is not vacuous.

    Deleting the golf call, dropping the key, or never entering the post-loop
    block all satisfy "reports 0 in dry-run". None of them survive this: with
    the switch ON the same 3,287 must appear in `..._ran` as genuine work, with
    an empty dry-run map.
    """
    head, _ = await _run_poll(monkeypatch, golf_enabled=True)

    assert head["post_loop_fixups_ran"]["golf_commence_fixed"] == _REHEARSAL_TOTAL
    assert head["post_loop_fixups_dry_run"] == {}, (
        "the repair wrote, so nothing is a rehearsal — a non-empty map here "
        "means the mode is being reported off something other than the switch"
    )


@pytest.mark.asyncio
async def test_a_dry_run_fixup_is_still_recorded_as_having_run(monkeypatch):
    """Absent and zero must not wear the same shape (gotcha #53).

    The tempting simplification is to route the key out of `..._ran` altogether
    when it is a rehearsal. That reads exactly like "the fix-up never started",
    which is what `..._skipped` means, and it would throw away the distinction
    the whole #3192 field group exists to keep.
    """
    head, _ = await _run_poll(monkeypatch, golf_enabled=False)

    assert "golf_commence_fixed" in head["post_loop_fixups_ran"]
    assert "golf_commence_fixed" in head["post_loop_fixups_dry_run"]
    assert head["post_loop_fixups_skipped"] == []
    assert head["post_loop_fixups_failed"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [True, False])
async def test_the_caller_passes_the_mode_it_read_rather_than_the_default(
    monkeypatch, enabled
):
    """The two-reads trap.

    `_fix_golf_commence_times(dry_run=None)` re-reads the Redis flag itself. If
    the caller left the default and the receipt read the flag a second time to
    name the mode, the two reads could disagree across a flag flip and the
    receipt would report a mode the repair did not run in — this bug one level
    up. One read, passed in explicitly.
    """
    _, calls = await _run_poll(monkeypatch, golf_enabled=enabled)

    kwargs = calls["golf"]["kwargs"]
    assert kwargs.get("dry_run") is (not enabled), (
        f"the repair was invoked with dry_run={kwargs.get('dry_run')!r} while "
        f"the switch read enabled={enabled} — the caller is not passing the "
        "mode it read"
    )
    assert calls["golf"]["kwargs"]["dry_run"] is not None


@pytest.mark.asyncio
async def test_the_four_ungated_repairs_keep_reporting_their_work_as_work(
    monkeypatch,
):
    """Blast-radius control: only the gated repair changes shape.

    The other four have no kill switch, so their counts were never rehearsals.
    A fix that routed every count through the dry-run map, or that reported 0
    for all five, passes the ship test above and silently blinds four honest
    receipts.
    """
    head, calls = await _run_poll(monkeypatch, golf_enabled=False)

    for key, _fn in _UNGATED:
        assert head["post_loop_fixups_ran"][key] == _UNGATED_RETURNS[key], key
        assert key not in head["post_loop_fixups_dry_run"], key
        assert (
            calls[key]["kwargs"] == {}
        ), f"{key} was handed a dry_run mode it has no switch for"


@pytest.mark.asyncio
async def test_no_key_can_claim_work_and_a_rehearsal_at_once(monkeypatch):
    """The invariant #3952 asks for, stated over the whole receipt.

    A name in the dry-run map wrote nothing, so its `..._ran` entry can only be
    0. Any nonzero pairing means some future gated repair was wired to the new
    field without being routed through it.
    """
    for enabled in (True, False):
        head, _ = await _run_poll(monkeypatch, golf_enabled=enabled)
        ran = head["post_loop_fixups_ran"]
        claiming = {k for k in head["post_loop_fixups_dry_run"] if ran.get(k)}
        assert not claiming, (
            f"{sorted(claiming)} report a rehearsal total AND nonzero repaired "
            "work on the same beat"
        )


def test_the_dry_run_map_reaches_the_serialized_receipt(monkeypatch):
    """`to_dict` is `asdict` + two computed keys, so a new field rides along
    automatically — which is exactly why nothing would notice it being dropped
    from the dataclass. An operator reads the JSON, not the dataclass.
    """
    r = ksr.KalshiScanReport(
        started_at="2026-09-08T12:45:00+00:00",
        post_loop_fixups_ran={"golf_commence_fixed": 0},
        post_loop_fixups_dry_run={"golf_commence_fixed": _REHEARSAL_TOTAL},
    )
    d = r.to_dict()
    assert d["post_loop_fixups_dry_run"] == {"golf_commence_fixed": _REHEARSAL_TOTAL}
    assert json.loads(json.dumps(d))["post_loop_fixups_dry_run"]
    # Default is empty, not absent: a beat with no gated repair says so.
    assert (
        ksr.KalshiScanReport(started_at="x").to_dict()["post_loop_fixups_dry_run"] == {}
    )
