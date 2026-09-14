"""#227 Item 2 / #6012: the targeted settlement trigger must REACH the series asked for.

PR #6097 wired ``only_series`` from the admin route through to the broker, and
``test_backfill_kalshi_settled_only_series_route_6012.py`` guards that rung: the
kwargs handed to celery. The suite stopped there. Nothing drove the rung that
decides whether the remedy actually works —

    broker kwargs -> task wrapper -> _backfill_from_settled_events
                  -> which series are asked of the venue, in what order

— which is the rung the remedy nearly died on. ``only_series`` matches by
PREFIX (``s.upper().startswith(_wanted)``), so ``["KXATP"]`` is not the
one-series request it reads as: measured on production 2026-09-14 it selects
31 series / ~22,176 markets, the scan walks them alphabetically under a 420s
budget, every series costs at least one live ``get_events`` round trip (the
"early exit per series" breaks on ``if not events``, i.e. AFTER the fetch), and
the US Open exacta's ``KXATPWTA`` sorts 31st of 31 behind ~22,175 markets. The
attended settlement DO was split into two calls for exactly that reason.

So these guards pin the selection BOTH ways:

* the prefix fan-out is real and is the documented contract (``["KXPGA"]``
  deliberately catches KXPGAR1LEAD/KXPGATOP5/…), and a narrow value lands on
  exactly one series;
* a targeted run bypasses the #230 boost cap and the rotating cursor entirely,
  and leaves the rotation's own cursor untouched, so an operator one-off can
  never reorder or starve the scheduled sweep;
* a blank/whitespace-only value degrades to the scheduled full sweep rather
  than to a scan pinned on nothing.

A later "tidy-up" to exact matching, or a reordering that folds the targeted
path back into the rotation, is then a deliberate and visible change instead of
a silent return to the ~17-day starvation.

These are behavioural, not source scans: each test drives the real function with
a faked DB + venue and reads back the series the venue was asked about. The
function swallows its own exceptions into ``stats["errors"]`` (kalshi.py's outer
handler), so every driven test asserts that list is empty — a broken fake would
otherwise read as a clean pass with nothing measured.
"""

from contextlib import asynccontextmanager

import pytest

import app.tasks.kalshi as kalshi


# Mirrors the production shape of the ATP family, in the DB's own `ORDER BY 1`
# order (the discovery query is `GROUP BY 1 ORDER BY 1`). Columns are
# (series_prefix, has_resolved, has_open).
#
# KXATPWTA is measured on production as the single series behind that prefix,
# carrying ONE open market and NO resolved sibling — which is why no amount of
# boost ordering can reach it (#230's boost needs has_resolved AND has_open) and
# why the targeted trigger is the only remedy for it.
_ATP_FAMILY = [
    ("KXATP", True, True),
    ("KXATPCHALLENGERMATCH", True, True),
    ("KXATPMATCH", True, False),
    ("KXATPSETWINNER", True, True),
    ("KXATPWTA", False, True),
]
_CONTROLS = [
    ("KXNFLGAME", True, True),  # a _PRIORITY_SERIES member, unrelated to ATP
    ("KXPGA", True, False),     # the family only_series was originally built for
]
_SERIES_ROWS = sorted(_ATP_FAMILY + _CONTROLS)

_ROTATION_CURSOR_KEY = "bainluck:settled_series_cursor"


class _Result:
    """Enough of a SQLAlchemy Result for the discovery query and the no-op rest."""

    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)

    def fetchall(self):
        return list(self._rows)

    def scalars(self):
        return self

    def mappings(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return None

    def scalar_one_or_none(self):
        return None

    @property
    def rowcount(self):
        return 0

    def __iter__(self):
        return iter(self._rows)


class _FakeSession:
    def __init__(self, series_rows):
        self._series_rows = series_rows

    async def execute(self, stmt, params=None):
        if "series_prefix" in str(stmt):
            return _Result(self._series_rows)
        return _Result([])

    async def commit(self):
        pass

    async def rollback(self):
        pass


class _FakeVenue:
    """Records what the scan asks Kalshi for, and answers 'nothing settled'.

    Returning ``([], None)`` lands every series on the `if not events: break`
    exit, so each series costs exactly one recorded ask and no DB work — the
    selection is isolated from the page-processing machinery.
    """

    def __init__(self):
        self.asked: list[str] = []

    async def get_events(self, **kwargs):
        self.asked.append(kwargs["series_ticker"])
        return [], None

    async def close(self):
        pass


class _FakeRedis:
    def __init__(self, initial=None):
        self.store = dict(initial or {})
        self.written: list[str] = []

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value
        self.written.append(key)

    def setex(self, key, ttl, value):
        self.store[key] = value
        self.written.append(key)

    def delete(self, key):
        self.store.pop(key, None)


async def _drive(monkeypatch, only_series=None, series_rows=None, redis_seed=None):
    """Run the real `_backfill_from_settled_events` against a faked DB + venue.

    Returns (asked_series, stats, fake_redis).
    """
    venue = _FakeVenue()
    rc = _FakeRedis(redis_seed)
    rows = _SERIES_ROWS if series_rows is None else series_rows

    @asynccontextmanager
    async def _fake_session(*args, **kwargs):
        yield _FakeSession(rows)

    async def _noop_index():
        return None

    monkeypatch.setattr(kalshi, "get_task_session", _fake_session)
    monkeypatch.setattr(
        kalshi, "_ensure_futures_outcomes_external_id_index", _noop_index
    )
    monkeypatch.setattr(
        "app.services.kalshi_api.KalshiAPIService", lambda *a, **k: venue
    )
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda *a, **k: rc)

    stats = await kalshi._backfill_from_settled_events(
        limit=10, only_series=only_series
    )

    # Anti-vacuous: the function swallows exceptions into stats["errors"], so a
    # broken fake would otherwise present as a clean pass over zero series.
    assert stats["errors"] == [], (
        "the driver itself failed — the scan never reached the venue, so nothing "
        f"below was measured: {stats['errors']}"
    )
    return venue.asked, stats, rc


async def test_narrow_prefix_lands_on_exactly_one_series(monkeypatch):
    """`["KXATPWTA"]` reaches the exacta in one ask — the first attended command.

    Production 2026-09-14: `KXATPWTA` matched as a PREFIX (not merely as an
    exact series) returns exactly one series carrying one open market.
    """
    asked, _stats, _rc = await _drive(monkeypatch, only_series=["KXATPWTA"])
    assert asked == ["KXATPWTA"]


async def test_only_series_is_a_prefix_and_fans_out(monkeypatch):
    """`["KXATP"]` is NOT a one-series request — it takes the whole family.

    This is the documented contract (`["KXPGA"]` must catch KXPGAR1LEAD/
    KXPGATOP5/…), and it is also the starvation trap: the family is walked in
    alphabetical order under a 420s budget, every member costs a live round
    trip, and the narrowest member sorts LAST. Anyone changing this to an exact
    match must change this test, and must then re-derive every targeted call
    that relies on the fan-out.
    """
    asked, _stats, _rc = await _drive(monkeypatch, only_series=["KXATP"])

    assert asked == [
        "KXATP",
        "KXATPCHALLENGERMATCH",
        "KXATPMATCH",
        "KXATPSETWINNER",
        "KXATPWTA",
    ], "prefix fan-out or its alphabetical order changed"
    # The two halves of the trap, named separately so a failure says which moved.
    assert len(asked) > 1, "only_series stopped matching by prefix"
    assert asked[0] == "KXATP", "the shortest member no longer sorts first"
    assert asked[-1] == "KXATPWTA", (
        "the narrowest member no longer sorts last — the ordering the two-command "
        "attended remedy was derived from has changed"
    )
    # No control leaks in: the pin is still a pin.
    assert "KXNFLGAME" not in asked and "KXPGA" not in asked


@pytest.mark.parametrize("value", ["  kxatpwta  ", "KxAtPwTa", "kxatpwta"])
async def test_case_and_whitespace_are_normalised(monkeypatch, value):
    """An operator typing a lowercase or padded series still hits the series.

    The route strips, the task upper()s and strips again; a regression in either
    silently degrades a targeted call into a full 1,093-series rotation.
    """
    asked, _stats, _rc = await _drive(monkeypatch, only_series=[value])
    assert asked == ["KXATPWTA"]


@pytest.mark.parametrize("value", [[], ["   "], ["", None]])
async def test_blank_targeting_degrades_to_the_scheduled_sweep(monkeypatch, value):
    """A blank value must mean "the normal sweep", never "a scan pinned on nothing".

    `?only_series=` on the route, or a list of blanks reaching the task, must not
    produce an empty series list — that would be a run that silently does no work
    while reporting success.
    """
    asked, _stats, _rc = await _drive(monkeypatch, only_series=value)
    assert asked, "a blank targeting value emptied the scan"
    assert {"KXNFLGAME", "KXPGA"} <= set(asked), (
        "a blank targeting value pinned the scan instead of degrading to the "
        "full scheduled sweep"
    )


async def test_targeted_run_bypasses_the_rotation_and_leaves_its_cursor_alone(
    monkeypatch,
):
    """An operator one-off must not reorder or advance the scheduled rotation.

    The targeted branch takes `SERIES_PREFIXES` directly instead of calling
    `_order_settled_scan_list`, so neither the #230 boost cap nor the rotating
    cursor applies — and, critically, the rotation cursor is not rewritten, so
    the next scheduled sweep resumes exactly where it was.
    """
    asked, _stats, rc = await _drive(
        monkeypatch,
        only_series=["KXATPWTA"],
        redis_seed={_ROTATION_CURSOR_KEY: "3"},
    )
    assert asked == ["KXATPWTA"]
    assert rc.store[_ROTATION_CURSOR_KEY] == "3", (
        "a targeted run advanced the scheduled rotation's cursor"
    )
    assert _ROTATION_CURSOR_KEY not in rc.written


async def test_scheduled_run_still_rotates(monkeypatch):
    """The contrast case: with no targeting, the rotation cursor IS advanced.

    Without this, the test above would pass just as well if the cursor had been
    removed from the task altogether.
    """
    asked, _stats, rc = await _drive(
        monkeypatch, only_series=None, redis_seed={_ROTATION_CURSOR_KEY: "0"}
    )
    assert asked, "the scheduled sweep asked for nothing"
    assert _ROTATION_CURSOR_KEY in rc.written, (
        "the scheduled sweep no longer advances its rotation cursor"
    )


def test_task_wrapper_forwards_only_series(monkeypatch):
    """The rung between the broker and the scan: `app.tasks.backfill_kalshi_settled`.

    The route hands celery `{"limit": …, "only_series": [...]}`. If the wrapper
    drops the kwarg, every targeted trigger becomes an ordinary rotation run that
    returns cleanly and settles nothing — the exact silent failure #6012 was
    filed for.
    """
    from app.tasks import celery_app
    import app.tasks as tasks_mod

    seen = {}

    def _record(limit, only_series=None):
        seen["limit"] = limit
        seen["only_series"] = only_series
        return "sentinel-coro"

    monkeypatch.setattr(kalshi, "_backfill_from_settled_events", _record)
    monkeypatch.setattr(tasks_mod, "_tracked_run", lambda _label, value: value)

    task = celery_app.tasks["app.tasks.backfill_kalshi_settled"]
    assert task(limit=7, only_series=["KXATPWTA"]) == "sentinel-coro"
    assert seen == {"limit": 7, "only_series": ["KXATPWTA"]}


def test_task_wrapper_default_leaves_scheduled_runs_untargeted(monkeypatch):
    """A beat calls the task with no kwargs; it must stay the full sweep."""
    from app.tasks import celery_app
    import app.tasks as tasks_mod

    seen = {}

    def _record(limit, only_series=None):
        seen["limit"] = limit
        seen["only_series"] = only_series
        return "sentinel-coro"

    monkeypatch.setattr(kalshi, "_backfill_from_settled_events", _record)
    monkeypatch.setattr(tasks_mod, "_tracked_run", lambda _label, value: value)

    task = celery_app.tasks["app.tasks.backfill_kalshi_settled"]
    task()
    assert seen["only_series"] is None
    assert seen["limit"] == 5000
