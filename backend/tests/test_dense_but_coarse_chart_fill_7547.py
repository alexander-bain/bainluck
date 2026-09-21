"""#7547 — a chart can be FULL and still be wrong about the week.

PILLAR: TRUTH / FORMATTING. SHIP: a reader scrubbing a futures chart's "1W" sees
the week's real movement instead of a flat line.

The first presentation of #7547 widened the fine retrieval tier from 24h to 144h
and proved the venue serves it. CERT-3252 blocked it for a reason the A/B could
not see: the widened tier is unreachable on the reader's own route. Production
`GET /api/futures/40533/history?hours=168` answers with 960 points,
`venue_history.state=cold`, `points_served=0`, `fill=chart_not_thin` — the market
has no bank, and `plan_on_demand_fill`'s density fence asks only HOW MANY points
a window holds. 960 is plenty, so no fill is ever started, so the finer tier
never runs and the reader's chart does not move.

Count and resolution are different questions. The specimen's 960 points are
ninety-six HOURLY captures on each of ten lines (measured 2026-09-21 on
production: median gap 3,607 s = 60.1 min, on every line) of a market the venue
published 643 one-cent moves on in the same week.

So these are the rules that keep the second question answerable, and the fence
that made the first answer honest:

  * dense-but-coarse asks for fine history (the ship);
  * dense-and-already-fine does NOT (the #7736 fence, which deleting the density
    rule outright would have taken with it);
  * the trigger is measured PER LINE, never on a pooled stream;
  * it is bounded to the windows the fine tier can actually cover.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.tasks import generic_market_history_fill as fill
from app.utils import generic_market_history as gmh
from app.utils.futures_chart_series import FINE_TIER_HOURS, KALSHI_FINE_INTERVAL

NOW = datetime(2026, 9, 21, 17, 0, 0, tzinfo=timezone.utc)


def _line(*, spacing_minutes: float, count: int, start: datetime = NOW):
    """One outcome's capture instants at a fixed cadence, newest at `start`."""
    return [start - timedelta(minutes=spacing_minutes * i) for i in range(count)]


def _market(source="kalshi", market_id=1, external_id="KXSB-27", status="open"):
    return SimpleNamespace(
        id=market_id, source=source, external_id=external_id, status=status,
        market_metadata=None,
    )


def _outcome(oid=10, external_id="KXSB-27-BUF", name="Bills"):
    return SimpleNamespace(id=oid, external_id=external_id, name=name)


class _Redis:
    def __init__(self):
        self.kv: dict = {}
        self.ttl: dict = {}

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.kv:
            return None
        self.kv[key], self.ttl[key] = value, ex
        return True

    def incr(self, key):
        self.kv[key] = int(self.kv.get(key, 0)) + 1
        return self.kv[key]

    def expire(self, key, seconds):
        self.ttl[key] = seconds

    def delete(self, key):
        self.kv.pop(key, None)


def _plan(*, thin=False, coarse=False, payload=None):
    return fill.plan_on_demand_fill(
        _market(), [_outcome()], payload,
        chart_is_thin=thin, chart_is_coarse=coarse, now=NOW, rc=_Redis(),
    )


# ── The ship ────────────────────────────────────────────────────────────────

def test_the_specimens_hourly_captures_across_a_week_read_as_coarse():
    """The production shape CERT-3252 measured, at the cadence it measured.

    Ten lines, ninety-six captures each, 60.1 minutes apart — 960 points, which
    is six times the thin gate's threshold of 20 and therefore invisible to it.
    """
    lines = [_line(spacing_minutes=60.1, count=96) for _ in range(10)]
    assert sum(len(x) for x in lines) == 960

    assert gmh.captures_are_coarse(lines, window_hours=168) is True
    assert gmh.captures_are_coarse(lines, window_hours=24) is True


def test_a_dense_but_coarse_chart_gets_past_the_density_fence_and_claims_a_fill():
    """The whole block: `chart_not_thin` was the reason the fine tier never ran."""
    assert _plan(thin=False, coarse=False) == {
        "enqueue": False, "reason": "chart_not_thin",
    }
    assert _plan(thin=False, coarse=True) == {"enqueue": True, "reason": "claimed"}


def test_a_stale_empty_answer_on_a_coarse_chart_is_asked_again():
    """The second `chart_not_thin` refusal, on the aged-payload arm.

    Repairing only the `age is None` arm would fix a market that never had a
    bank and permanently strand one whose last answer came back empty — the same
    defect, one branch further down, and no test would have said so.
    """
    stale = {
        "schema": gmh.SCHEMA, "version": gmh.CACHE_VERSION, "scale": gmh.SCALE,
        "market_id": 1, "market_source": "kalshi", "market_external_id": "KXSB-27",
        "attempted_at": (
            NOW - timedelta(seconds=fill.REFRESH_AFTER_SECONDS + 60)
        ).isoformat(),
        "built_at": None, "status": "empty", "outcomes": {},
    }
    assert _plan(thin=False, coarse=False, payload=stale)["reason"] == "chart_not_thin"
    assert _plan(thin=False, coarse=True, payload=stale)["enqueue"] is True


# ── The fences the ship must not take with it ───────────────────────────────

def test_a_chart_our_own_polls_already_draw_finely_still_refuses():
    """#7736's fence, restated as resolution rather than as row count.

    A live-polled market is captured every two minutes. That is 2x the fine
    interval, not 10x, so the fetch has nothing to add and the request is not
    made. Without this the repair becomes "every densely-polled market on the
    site asks the venue", which is what the fence has always been for.
    """
    fine = [_line(spacing_minutes=2, count=500) for _ in range(10)]
    assert gmh.captures_are_coarse(fine, window_hours=24) is False
    assert gmh.captures_are_coarse(fine, window_hours=168) is False
    assert _plan(thin=False, coarse=False)["reason"] == "chart_not_thin"


def test_coarseness_is_measured_per_line_and_never_on_a_pooled_stream():
    """Ten hourly lines are not one six-minute line.

    Pooling ten outcomes captured once an hour yields a merged stream whose
    median gap is about six minutes, which reads as minute data. The failure
    points the SAFE way for the venue and the WRONG way for the reader — no
    request is made, the chart stays flat, and nothing anywhere looks broken.
    That is why this is the assertion and not a comment.
    """
    lines = [
        _line(spacing_minutes=60, count=96, start=NOW - timedelta(minutes=6 * i))
        for i in range(10)
    ]
    assert gmh.captures_are_coarse(lines, window_hours=168) is True

    pooled = [sorted(ts for line in lines for ts in line)]
    pooled_gaps = sorted(
        (pooled[0][i + 1] - pooled[0][i]).total_seconds()
        for i in range(len(pooled[0]) - 1)
    )
    assert pooled_gaps[len(pooled_gaps) // 2] < 600, "fixture must reproduce the trap"
    assert gmh.captures_are_coarse(pooled, window_hours=168) is False


def test_the_densest_line_speaks_so_one_abandoned_outcome_cannot_trigger_a_fill():
    """A market captured every minute, plus one longshot nobody polls."""
    lines = [_line(spacing_minutes=1, count=500) for _ in range(9)]
    lines.append(_line(spacing_minutes=180, count=20))
    assert gmh.captures_are_coarse(lines, window_hours=24) is False


def test_a_single_capture_is_not_a_spacing():
    """One point per line is the THIN gate's case, not this one.

    Answering "coarse" for it would make this predicate a second, looser thin
    gate that fires on exactly the charts the first one already handles.
    """
    assert gmh.captures_are_coarse([[NOW]], window_hours=24) is False
    assert gmh.captures_are_coarse([[], []], window_hours=24) is False
    assert gmh.captures_are_coarse([], window_hours=24) is False


# ── The bound on outbound venue traffic ─────────────────────────────────────

def test_long_windows_the_fine_tier_cannot_cover_do_not_trigger_a_fill():
    """1M and ALL are out; 1D and 1W are in.

    The fine tier reaches `FINE_TIER_HOURS` and no further, so on a 30-day chart
    compacted to ~80 points a fill improves a sliver nobody can see, at the price
    of a real venue request on a public GET.
    """
    lines = [_line(spacing_minutes=60, count=96) for _ in range(10)]
    assert gmh.captures_are_coarse(lines, window_hours=24) is True
    assert gmh.captures_are_coarse(lines, window_hours=168) is True
    assert gmh.captures_are_coarse(lines, window_hours=720) is False
    assert gmh.captures_are_coarse(lines, window_hours=None) is False


def test_the_coarse_threshold_is_derived_from_the_tier_it_would_fetch():
    """Not a literal that can drift away from the tier it describes.

    If the fine interval ever stops being one minute, this threshold moves with
    it; a hardcoded 600 would silently keep describing the old tier.
    """
    assert (
        KALSHI_FINE_INTERVAL * 60 * gmh.COARSE_CAPTURE_MULTIPLE == 600
    ), "the fine tier is one minute, so an order of magnitude coarser is 10 min"

    just_inside = [_line(spacing_minutes=10, count=50) for _ in range(3)]
    just_outside = [_line(spacing_minutes=9, count=50) for _ in range(3)]
    assert gmh.captures_are_coarse(just_inside, window_hours=24) is True
    assert gmh.captures_are_coarse(just_outside, window_hours=24) is False


def test_the_window_bound_is_derived_from_the_fine_tiers_reach():
    """The 1W band qualifies only because the tier reaches 144 of its 168 hours."""
    lines = [_line(spacing_minutes=60, count=96) for _ in range(3)]
    cutoff = FINE_TIER_HOURS / gmh.COARSE_TRIGGER_MIN_WINDOW_COVERAGE
    assert gmh.captures_are_coarse(lines, window_hours=cutoff - 1) is True
    assert gmh.captures_are_coarse(lines, window_hours=cutoff + 1) is False


def test_coarse_fills_cannot_spend_the_whole_hour_and_starve_a_thin_chart():
    """The cap that is also the recall's limit, avoided on purpose.

    Coarse is the common case — our futures captures are hourly, so on 1D and 1W
    most markets qualify — while a thin chart is rare. One shared budget would
    let coarse fills take the hour most hours, and the reader who loses that race
    is the one looking at NO line at all. So a third of every hour is reserved.
    """
    assert fill.COARSE_FILL_CAP < fill.HOURLY_FILL_CAP

    def _at(spent, *, thin, coarse):
        rc = _Redis()
        rc.kv[gmh.budget_key(NOW.strftime("%Y%m%d%H"))] = spent
        return fill.plan_on_demand_fill(
            _market(), [_outcome()], None,
            chart_is_thin=thin, chart_is_coarse=coarse, now=NOW, rc=rc,
        )

    assert _at(fill.COARSE_FILL_CAP, thin=False, coarse=True)["reason"] == "coarse_hourly_cap"
    assert _at(fill.COARSE_FILL_CAP, thin=True, coarse=False)["enqueue"] is True
    assert _at(fill.HOURLY_FILL_CAP, thin=True, coarse=False)["reason"] == "hourly_cap"
    assert _at(fill.COARSE_FILL_CAP - 2, thin=False, coarse=True)["enqueue"] is True


def test_an_unmeasured_caller_behaves_exactly_as_before():
    """`chart_is_coarse` defaults False, so nothing that does not opt in moves."""
    assert fill.plan_on_demand_fill(
        _market(), [_outcome()], None, chart_is_thin=False, now=NOW, rc=_Redis(),
    ) == {"enqueue": False, "reason": "chart_not_thin"}
