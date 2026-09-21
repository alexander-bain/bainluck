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

    def decr(self, key):
        self.kv[key] = int(self.kv.get(key, 0)) - 1
        return self.kv[key]

    def expire(self, key, seconds):
        self.ttl[key] = seconds

    def delete(self, key):
        self.kv.pop(key, None)


class _InterleavingRedis(_Redis):
    """One Redis, two readers: the second arrives *during* the first's refusal.

    `hook` fires immediately after an INCR lands and before its caller can undo
    it — the window a refusal is unavoidably open for, and the only window in
    which a refused request holds a unit of anything. It disarms itself, so the
    reader running inside it cannot recurse.
    """

    def __init__(self):
        super().__init__()
        self.hook = None
        self.during = None

    def incr(self, key):
        value = super().incr(key)
        hook, self.hook = self.hook, None
        if hook is not None:
            self.during = hook()
        return value


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


def _sequence(rc, count, *, thin, coarse, first_market=1):
    """`count` reads of `count` DIFFERENT markets against ONE Redis, in order.

    Different markets because the claim is per-market: reusing one id would
    answer `already_claimed` and never reach the budget this is about.
    """
    return [
        fill.plan_on_demand_fill(
            _market(market_id=first_market + i), [_outcome()], None,
            chart_is_thin=thin, chart_is_coarse=coarse, now=NOW, rc=rc,
        )
        for i in range(count)
    ]


def test_coarse_fills_cannot_spend_the_whole_hour_and_starve_a_thin_chart():
    """The cap that is also the recall's limit, avoided on purpose.

    Coarse is the common case — our futures captures are hourly, so on 1D and 1W
    most markets qualify — while a thin chart is rare. One shared budget would
    let coarse fills take the hour most hours, and the reader who loses that race
    is the one looking at NO line at all. So a third of every hour is reserved.
    """
    assert fill.COARSE_FILL_CAP < fill.HOURLY_FILL_CAP

    def _at(spent, coarse_spent, *, thin, coarse):
        rc = _Redis()
        rc.kv[gmh.budget_key(NOW.strftime("%Y%m%d%H"))] = spent
        rc.kv[gmh.coarse_budget_key(NOW.strftime("%Y%m%d%H"))] = coarse_spent
        return fill.plan_on_demand_fill(
            _market(), [_outcome()], None,
            chart_is_thin=thin, chart_is_coarse=coarse, now=NOW, rc=rc,
        )

    cap, hourly = fill.COARSE_FILL_CAP, fill.HOURLY_FILL_CAP
    assert _at(cap, cap, thin=False, coarse=True)["reason"] == "coarse_hourly_cap"
    assert _at(cap, cap, thin=True, coarse=False)["enqueue"] is True
    assert _at(hourly, 0, thin=True, coarse=False)["reason"] == "hourly_cap"
    assert _at(cap - 2, cap - 2, thin=False, coarse=True)["enqueue"] is True


def test_refused_coarse_reads_leave_the_thin_reserve_where_they_found_it():
    """🔴 THE DEFECT CERT-3255 MEASURED — one Redis, one hour, in sequence.

    The reserve was two caps over ONE counter, and the counter was advanced
    before the cap was consulted. So a coarse read that was REFUSED — which did
    no work, sent nothing to the venue, started no fill — had still spent a unit
    of the hour on its way to being told no. Coarse is the norm, so the twenty
    units held back for empty charts drained fastest exactly when coarse traffic
    was heaviest, and the reader with no line at all was refused for a budget
    that had been consumed entirely by refusals.

    The graded sequence, verbatim: fill the coarse share, then twenty more coarse
    reads are turned away, then a thin market asks. It was answered `hourly_cap`
    at a counter of 61. Nothing here is a fresh double — the depletion only
    exists ACROSS requests, so a per-assertion Redis cannot see it.
    """
    rc = _Redis()
    bkey = gmh.budget_key(NOW.strftime("%Y%m%d%H"))

    accepted = _sequence(rc, fill.COARSE_FILL_CAP, thin=False, coarse=True)
    assert all(p["enqueue"] for p in accepted), "the coarse share must be spendable"
    assert int(rc.kv[bkey]) == fill.COARSE_FILL_CAP

    refused = _sequence(rc, 20, thin=False, coarse=True, first_market=1000)
    assert [p["reason"] for p in refused] == ["coarse_hourly_cap"] * 20
    assert int(rc.kv[bkey]) == fill.COARSE_FILL_CAP, (
        "twenty refusals did no work and must have cost the hour nothing"
    )
    assert int(rc.kv[gmh.coarse_budget_key(NOW.strftime("%Y%m%d%H"))]) == fill.COARSE_FILL_CAP, (
        "the refusals walked coarseness's own counter past its cap instead"
    )

    thin = fill.plan_on_demand_fill(
        _market(market_id=2000), [_outcome()], None,
        chart_is_thin=True, chart_is_coarse=False, now=NOW, rc=rc,
    )
    assert thin == {"enqueue": True, "reason": "claimed"}


def test_the_coarse_share_is_taken_out_of_the_hour_and_not_added_to_it():
    """Two ceilings would have been easier code and 100 requests an hour.

    Coarse fills count against the hourly cap as well as their own share, so the
    traffic a reader can point at the venues is unchanged by this ship. The thin
    population's guarantee is what moved: at least `HOURLY - COARSE` fills of the
    hour cannot be taken by coarseness, however much of it arrives.
    """
    rc = _Redis()
    coarse = _sequence(rc, fill.COARSE_FILL_CAP, thin=False, coarse=True)
    assert all(p["enqueue"] for p in coarse)

    room = fill.HOURLY_FILL_CAP - fill.COARSE_FILL_CAP
    thin = _sequence(rc, room, thin=True, coarse=False, first_market=1000)
    assert all(p["enqueue"] for p in thin)
    assert room > 0, "the reserve is what the thin population is guaranteed"

    over = fill.plan_on_demand_fill(
        _market(market_id=2000), [_outcome()], None,
        chart_is_thin=True, chart_is_coarse=False, now=NOW, rc=rc,
    )
    assert over["reason"] == "hourly_cap"
    assert int(rc.kv[gmh.budget_key(NOW.strftime("%Y%m%d%H"))]) == fill.HOURLY_FILL_CAP


def test_a_thin_read_that_arrives_mid_refusal_is_not_charged_for_it():
    """The concurrency half: a refusal is open for a moment, and that is enough.

    Undoing the increment makes a refusal cost nothing once it has FINISHED.
    In between, on one shared counter, the coarse request that is on its way to
    being told no is indistinguishable from work in progress — so a thin reader
    landing in that window is refused for a unit nobody will ever use. Two
    readers a millisecond apart is the ordinary case on a public GET, not the
    exotic one, and separate counters are what make the window unreachable
    rather than merely brief.

    Seeded one below the hour's cap, so the thin read here succeeds or fails
    ONLY on whether the in-flight coarse increment could reach its counter.
    """
    rc, hour = _InterleavingRedis(), NOW.strftime("%Y%m%d%H")
    rc.kv[gmh.budget_key(hour)] = fill.HOURLY_FILL_CAP - 1
    rc.kv[gmh.coarse_budget_key(hour)] = fill.COARSE_FILL_CAP

    rc.hook = lambda: fill.plan_on_demand_fill(
        _market(market_id=2000), [_outcome()], None,
        chart_is_thin=True, chart_is_coarse=False, now=NOW, rc=rc,
    )
    coarse = fill.plan_on_demand_fill(
        _market(market_id=1), [_outcome()], None,
        chart_is_thin=False, chart_is_coarse=True, now=NOW, rc=rc,
    )

    assert coarse["reason"] == "coarse_hourly_cap"
    assert rc.during == {"enqueue": True, "reason": "claimed"}, (
        "the thin reader was charged for a coarse refusal that was still in flight"
    )
    assert int(rc.kv[gmh.budget_key(hour)]) == fill.HOURLY_FILL_CAP
    assert int(rc.kv[gmh.coarse_budget_key(hour)]) == fill.COARSE_FILL_CAP


def test_a_coarse_read_the_HOUR_refuses_keeps_its_share_too():
    """The other half of "a refusal costs nothing", on the second counter.

    A coarse read clears its own share and is then refused by the hour. It did no
    work either, so the coarse unit it took on the way through has to go back —
    otherwise a full hour quietly eats the coarse share as well, and the next
    hour starts with coarseness poorer for fills that never happened.
    """
    rc, hour = _Redis(), NOW.strftime("%Y%m%d%H")
    rc.kv[gmh.budget_key(hour)] = fill.HOURLY_FILL_CAP
    rc.kv[gmh.coarse_budget_key(hour)] = 0

    plan = fill.plan_on_demand_fill(
        _market(), [_outcome()], None,
        chart_is_thin=False, chart_is_coarse=True, now=NOW, rc=rc,
    )
    assert plan["reason"] == "hourly_cap"
    assert int(rc.kv[gmh.coarse_budget_key(hour)]) == 0
    assert int(rc.kv[gmh.budget_key(hour)]) == fill.HOURLY_FILL_CAP
    assert gmh.claim_key(1) not in rc.kv, "a refused read kept its claim"


def test_an_unmeasured_caller_behaves_exactly_as_before():
    """`chart_is_coarse` defaults False, so nothing that does not opt in moves."""
    assert fill.plan_on_demand_fill(
        _market(), [_outcome()], None, chart_is_thin=False, now=NOW, rc=_Redis(),
    ) == {"enqueue": False, "reason": "chart_not_thin"}
