"""The bound that holds is the CLOCK, not the row count. #2953.

`DEFAULT_LIMIT` was 100 on the strength of a measured "~0.2s per ESPN call".
Re-measured against production on 2026-09-04, the real cost is **~0.59s/row**
(10 rows in 5.66s, 20 in 11.52s, 40 in 23.32s — near-zero fixed cost). So the
default was ~59 seconds of fetching against Heroku's 30-second router: every
caller who omitted `limit` got a bare HTML error page carrying no `reason` and
no `correlation_id`, and on `apply` it was the worst shape a destructive
endpoint can have — killed *after* the writes committed.

The old guard could not catch this. It asserted `DEFAULT_LIMIT * 0.2 < 25`,
which is arithmetic over a constant nobody re-measured: the test stayed green
while the thing it described stopped being true. **A row count is a guess at a
duration.** The fix is to stop guessing — `EXAMINE_BUDGET_SECONDS` ends the
loop on the clock, so a caller who passes `limit=500` gets a truncated page and
a cursor instead of an H12.

What a deadline can get wrong, and what each test here pins:

* **Counting rows it never asked about.** The tail the clock cut off got no
  ESPN call, so it may not be summarised — least of all as `agrees`, which is
  the reading that sounds like an all-clear.
* **Handing back a cursor that skips the tail.** `next_cursor` is built from
  `rows[-1]`. Leave `rows` at full length and the cursor names the last row
  *loaded* rather than the last row *answered*, and the sweep steps over the
  gap permanently — with every field in the response looking healthy.
* **Trusting a count over evidence in hand.** `has_more` compares `remaining`
  against `examined`, but `remaining` is a separate COUNT that can go stale by
  a settle. When the deadline leaves a row on the table we have direct evidence
  of one, and it must outrank the count.
* **Printing the wrong remedy.** "raise limit above N" sent to someone whose
  page ended at 18 seconds tells them to make the next one time out.

The clock is injected, never slept on: `_Clock` advances only when the rail
asks it the time, so these tests are deterministic and instant.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.tasks import reconcile_anchor_schedule as rail
from app.utils.anchor_schedule import AnchoredRow
from app.utils.authority_id_collisions import AuthorityRecord

UTC = timezone.utc

#: One kickoff, many fixtures — the tie an NFL Sunday actually is, and the shape
#: a cursor bug hides inside.
TIE = datetime(2026, 9, 13, 17, 0, tzinfo=UTC)


class _Clock:
    """A monotonic clock that moves only when the rail reads it.

    Substituted for the whole `_time` module reference inside the rail, so no
    other module's timekeeping is touched and nothing sleeps.
    """

    def __init__(self, step: float):
        self.step = step
        self.now = 0.0
        self.reads = 0

    def monotonic(self) -> float:
        value = self.now
        self.reads += 1
        self.now += self.step
        return value


def _row(event_id: int) -> AnchoredRow:
    return AnchoredRow(
        event_id=event_id,
        sport_key="americanfootball_nfl",
        home_team_name="Home",
        away_team_name="Away",
        espn_id=f"4018730{event_id % 100:02d}",
        commence_time=TIE,
        status="scheduled",
        completed_at=None,
        commence_time_source="espn",
    )


def _wire(monkeypatch, rows, *, eligible, remaining, clock=None):
    """Load `rows`, answer for every one of them, and control the clock.

    The authority AGREES with every row on purpose. It makes the tail-counting
    test sharp: if an un-examined row were ever summarised it would land in
    `agrees`, the one bucket a reviewer reads as "nothing to do here".
    """

    async def _load_rows(session, **kwargs):
        return list(rows)

    async def _count_eligible(session, **kwargs):
        return remaining if kwargs.get("cursor") else eligible

    async def _fetch_record(service, sport_keys, authority_id):
        return AuthorityRecord(
            authority_id=authority_id,
            home_names=frozenset({"home"}),
            away_names=frozenset({"away"}),
            starts_at=TIE,
            label="Away v Home",
        )

    monkeypatch.setattr(rail, "_load_rows", _load_rows)
    monkeypatch.setattr(rail, "_count_eligible", _count_eligible)
    monkeypatch.setattr(
        "app.tasks.repair_authority_id_collisions._fetch_record", _fetch_record
    )
    monkeypatch.setattr("app.services.espn_api.get_espn_service", lambda: object())
    if clock is not None:
        monkeypatch.setattr(rail, "_time", clock)


class TestTheRouterBoundStaysOffTheBatchCaller:
    """A bound built for the endpoint must not silently shrink the sweep.

    `reconcile`'s defaults describe the ONE caller behind Heroku's 30-second
    router. The nightly sentinel runs in a Celery worker with its own 300s
    deadline and no router at all, so inheriting either default costs it reach
    it never needed to give up: at `limit=25` the 12-page cap binds first and a
    night covers 300 rows instead of ~500, and at `budget_seconds=18` every
    100-row page would be cut at ~30.

    Both were live regressions in the first draft of #2953 — the shared
    constant was doing two jobs, and shrinking it for one silently shrank the
    other.
    """

    def test_the_sweep_does_not_inherit_the_routers_page_size(self):
        from app.tasks import anchor_schedule_sentinel as sweep

        assert sweep.SWEEP_PAGE_LIMIT > rail.DEFAULT_LIMIT

    def test_the_sweep_page_cap_is_not_what_bounds_a_night(self):
        """The deadline should bind before the page cap, or reach is left unused."""
        from app.tasks import anchor_schedule_sentinel as sweep

        seconds_per_page = sweep.SWEEP_PAGE_LIMIT * 0.59
        pages_the_deadline_allows = sweep.DEFAULT_DEADLINE_SECONDS / seconds_per_page
        assert pages_the_deadline_allows < sweep.DEFAULT_MAX_PAGES

    def test_the_sweeps_per_page_budget_clears_a_full_page(self):
        """Otherwise `reconcile` truncates every page and the cap returns."""
        from app.tasks import anchor_schedule_sentinel as sweep

        assert sweep.SWEEP_PAGE_BUDGET_SECONDS > sweep.SWEEP_PAGE_LIMIT * 0.59

    def test_the_sweep_passes_its_own_budget_rather_than_taking_the_default(self):
        """The wiring, not just the constants: a constant nobody passes is a comment."""
        import inspect

        from app.tasks import anchor_schedule_sentinel as sweep

        source = inspect.getsource(sweep)
        assert "budget_seconds=SWEEP_PAGE_BUDGET_SECONDS" in source
        # And the router's constant is no longer imported here at all, so it
        # cannot come back as a default by accident.
        assert "DEFAULT_LIMIT," not in source


class TestTheDefaultLimitIsMeasured:
    """The constant, and the arithmetic that let the wrong one stand."""

    def test_the_default_limit_fits_the_router_at_the_measured_cost(self):
        """At the REAL per-row cost, not the one the old comment assumed.

        This is the assertion that would have gone red on 2026-09-03. Stated
        against the measured 0.59s so that re-measuring is what changes it —
        the previous version's 0.2 was a number the test carried rather than
        one anything checked.
        """
        measured_seconds_per_row = 0.59
        # Half the 30s router window; the other half is the count query, the
        # writes, the undo record and the JSON.
        assert rail.DEFAULT_LIMIT * measured_seconds_per_row < 15.0

    def test_the_old_default_would_now_fail_this_bar(self):
        """The regression arm: 100 rows is ~59s and must not read as safe.

        Without this, a future edit could restore 100 and the test above would
        be the only thing standing in the way — with no record that 100 is the
        specific value that broke.
        """
        assert 100 * 0.59 > 30.0

    def test_the_time_budget_and_the_default_page_do_not_fight(self):
        """The safety must not fire on the ordinary path, and must beat the router.

        These two bounds have to be ordered, not merely both small:

            DEFAULT_LIMIT * cost  <=  EXAMINE_BUDGET_SECONDS  <  router

        Get the left inequality backwards and the default page truncates itself
        every single call — the budget stops being a safety net and becomes the
        page size, silently halving the rail's throughput. Get the right one
        backwards and the budget is decoration, because the router fires first.
        """
        default_page_cost = rail.DEFAULT_LIMIT * 0.59
        assert default_page_cost <= rail.EXAMINE_BUDGET_SECONDS
        assert rail.EXAMINE_BUDGET_SECONDS < 30.0


@pytest.mark.asyncio
class TestTheClockEndsThePage:
    """A slow authority truncates the page instead of timing out the router."""

    async def test_a_normal_page_is_not_marked_stopped(self, monkeypatch):
        """CONTROL ARM. A page that never hits the budget reports `stopped_by: None`.

        Both arms matter: a `stopped_by` that is always set is as useless as one
        that is never set, and only this test can tell the two apart.
        """
        rows = [_row(14780140 + n) for n in range(5)]
        # 1s per read against an 18s budget — the clock cannot fire.
        _wire(monkeypatch, rows, eligible=5, remaining=5, clock=_Clock(step=1.0))

        result = await rail.reconcile(None, limit=5)

        assert result["stopped_by"] is None
        assert result["examined"] == 5
        assert result["by_verdict"]["agrees"] == 5

    async def test_the_budget_stops_the_loop_early(self, monkeypatch):
        """10s per read against an 18s budget: two rows answered, then stop."""
        rows = [_row(14780140 + n) for n in range(5)]
        _wire(monkeypatch, rows, eligible=5, remaining=5, clock=_Clock(step=10.0))

        result = await rail.reconcile(None, limit=5)

        assert result["stopped_by"] == "budget"
        assert result["examined"] == 2

    async def test_the_unexamined_tail_is_never_counted_as_agreeing(self, monkeypatch):
        """The three rows nobody asked about are in no bucket at all.

        The authority agrees with every row here, so a tail that leaked into
        the summary would leak into `agrees` — and a reviewer reading
        `agrees=5` on a five-row window would call the window clean.
        """
        rows = [_row(14780140 + n) for n in range(5)]
        _wire(monkeypatch, rows, eligible=5, remaining=5, clock=_Clock(step=10.0))

        result = await rail.reconcile(None, limit=5)

        assert result["by_verdict"]["agrees"] == 2
        assert sum(result["by_verdict"].values()) == 2
        assert result["examined"] == 2

    async def test_the_cursor_names_the_last_ANSWERED_row_not_the_last_loaded(
        self, monkeypatch
    ):
        """The tail-skipping defect, pinned by identity rather than by count.

        Five rows loaded, two answered. The cursor must resume at row two. If
        `rows` is not trimmed to the answered prefix, `rows[-1]` is row FIVE
        and rows three and four are stepped over for good — silently, with
        `terminal: partial` and a cursor that both look correct.
        """
        rows = [_row(14780140 + n) for n in range(5)]
        _wire(monkeypatch, rows, eligible=5, remaining=5, clock=_Clock(step=10.0))

        result = await rail.reconcile(None, limit=5)

        second_row = rows[1]
        assert result["next_cursor"] == rail.encode_cursor(
            second_row.commence_time, second_row.event_id
        )
        last_loaded = rows[-1]
        assert result["next_cursor"] != rail.encode_cursor(
            last_loaded.commence_time, last_loaded.event_id
        )

    async def test_a_stale_remaining_count_cannot_swallow_the_tail(self, monkeypatch):
        """Evidence in hand outranks a count taken separately.

        `remaining` is its own COUNT query and can go stale by a settle. Here
        it says 2 while five rows are loaded and two are answered, so the
        `remaining > examined` comparison alone yields `has_more: false` and no
        cursor — the sweep abandons three rows while every field reads healthy.
        The deadline saw those rows, so its evidence decides.

        The call is CURSORED on purpose. `remaining` is only its own count on a
        cursored call — uncursored it is just `eligible`, so an uncursored
        version of this test exercises `5 > 2` and passes whether or not the
        deadline's evidence is consulted at all. (It did, until this note.)
        """
        rows = [_row(14780140 + n) for n in range(5)]
        _wire(monkeypatch, rows, eligible=5, remaining=2, clock=_Clock(step=10.0))

        result = await rail.reconcile(
            None, limit=5, cursor=rail.encode_cursor(TIE, 14780100)
        )

        assert result["examined"] == 2
        assert result["has_more"] is True
        assert result["next_cursor"] is not None
        assert result["truncated"] is True

    async def test_a_budget_stop_never_terminates_no_work(self, monkeypatch):
        """`no_work` is an all-clear and a truncated page has not earned one."""
        rows = [_row(14780140 + n) for n in range(5)]
        _wire(monkeypatch, rows, eligible=5, remaining=5, clock=_Clock(step=10.0))

        result = await rail.reconcile(None, limit=5)

        assert result["terminal"] == "partial"


class TestTheOperatorIsToldWhichRemedyToUse:
    """Two ways to truncate, two remedies — printing the wrong one costs a run."""

    def test_a_budget_stop_does_not_advise_raising_the_limit(self):
        line = rail.summarize_for_operator(
            {
                "measured": True,
                "terminal": "partial",
                "examined": 2,
                "eligible": 5,
                "remaining": 5,
                "truncated": True,
                "has_more": True,
                "next_cursor": "2026-09-13T17:00:00+00:00|14780141",
                "stopped_by": "budget",
                "moved": 0,
                "stale": 0,
                "by_verdict": {"agrees": 2},
            }
        )

        assert "raise limit" not in line.lower()
        assert "budget" in line.lower()

    def test_a_limit_truncation_still_advises_raising_the_limit(self):
        """CONTROL ARM: the pre-existing wording survives for its own case."""
        line = rail.summarize_for_operator(
            {
                "measured": True,
                "terminal": "partial",
                "examined": 5,
                "eligible": 685,
                "remaining": 5,
                "truncated": True,
                "has_more": False,
                "next_cursor": None,
                "stopped_by": None,
                "moved": 0,
                "stale": 0,
                "by_verdict": {"agrees": 5},
            }
        )

        assert "TAIL" in line
