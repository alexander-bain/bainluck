"""live/036 — the nightly sweep pre-warms what a reader reaches; the page fills the rest.

THE RULING these guard (Fable-5, 2026-09-02, options (b) + (c)):

    "Narrow the nightly sweep to what a reader can reach — tournament events,
     major-league games, and any event with a live/upcoming card or a Discover
     placement in the next 7 days; drop the 44,315 backlog as a goal. Plus
     on-demand: when /api/events/{id}/history serves a thin chart for an
     eligible event, enqueue that event's backfill immediately (hourly candles
     for events older than 7 days, 1-minute for live/recent). The US Open is the
     ship; February soccer is not."

WHY IT WAS RULED. CERT-730's second finding, measured on production: 44,315
candidates inside Kalshi's retention floor, ~550 new per day, a nightly budget
of 60. ~739 nights for ONE traversal of a population that grows every night. No
value of `limit` fixes an arithmetic that is the wrong shape.

THE TWO HALVES ARE ONE DESIGN, and neither is safe alone:

  * the nightly is allowed to be aggressive about what it SKIPS only because
    on-demand catches whatever a person actually opens;
  * on-demand is allowed to be cheap and rate-limited only because the nightly
    has already pre-warmed the pages people are most likely to open.

Measured against the real population, 2026-09-02, over the ±7-day window:
KEPT 1,152 events / 28 sport keys — DROPPED 3,390 / 40, of which `soccer_other`
is 2,409 and `esports` 463. The entire US Open cohort survives.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.tasks.event_chart_backfill import (
    COARSE_GRANULARITY_AGE_DAYS,
    HISTORICAL_UNNARROWED_POPULATION,
    KALSHI_PERIOD_INTERVALS,
    READER_REACH_LOOKAHEAD_DAYS,
    READER_REACH_LOOKBACK_DAYS,
    THIN_CHART_CANDIDATES_SQL,
    THIN_MAX_EXPECTED_POINTS,
    choose_period_interval,
    granularity_floor_minutes,
    is_reader_reachable_sport_key,
)

UTC = timezone.utc


# ---------------------------------------------------------------------------
# (b) THE NARROWING — who a reader can reach
# ---------------------------------------------------------------------------


def test_the_specimen_survives_the_narrowing():
    """🔴 THE TRAP THIS WHOLE CLASSIFIER IS SHAPED AROUND.

    The obvious authority for "is this a major league" is `LEAGUE_CLASS`, and it
    spells the US Open `tennis_us_open`. The EVENTS do not: event 15300759 —
    Vallejo v Monfils, the single-dot chart that is this program's specimen and
    the reason live/035 exists — carries plain `tennis_atp`.

    A classifier built on `LEAGUE_CLASS` alone therefore excludes the exact
    event the queue was opened to fix, silently, while looking correct. The
    control below is the load-bearing half of this test: it asserts the trap is
    still ARMED, so if someone later adds `tennis_atp` to `LEAGUE_CLASS` this
    test stops being vacuous by construction and says so.
    """
    from app.utils.league_classification import LEAGUE_CLASS

    assert is_reader_reachable_sport_key("tennis_atp") is True

    if "tennis_atp" in LEAGUE_CLASS:
        pytest.fail(
            "`tennis_atp` is now in LEAGUE_CLASS, so this test no longer proves "
            "the fallback that keeps the specimen reachable. Re-point the "
            "control at whatever tour key LEAGUE_CLASS still omits."
        )


def test_the_whole_us_open_cohort_is_reachable():
    """"The US Open is the ship." All four keys it is spread across."""
    for key in (
        "tennis_atp",
        "tennis_wta",
        "tennis_atp_us_open",
        "tennis_wta_us_open",
    ):
        assert is_reader_reachable_sport_key(key) is True, key


def test_major_leagues_and_tournament_keys_are_reachable():
    for key in (
        "baseball_mlb",
        "americanfootball_ncaaf",
        "americanfootball_ncaaf_fcs",
        "soccer_epl",
        "golf_pga",
        "tennis_wta_cincinnati_open",
        "mma_mixed_martial_arts",
    ):
        assert is_reader_reachable_sport_key(key) is True, key


def test_february_soccer_is_not_the_ship():
    """The DROPPED half, by measured volume. This is the narrowing itself.

    `soccer_other` alone was 2,409 of the 4,542 events in the reader window —
    53% of the budget spent on the population Alex named as explicitly not the
    ship. Dropped here does not mean abandoned: any one of these fills the
    moment somebody opens its page (see the on-demand guards below).
    """
    for key in (
        "soccer_other",
        "baseball_other",
        "tennis_other",
        "americanfootball_other",
        "basketball_other",
        "icehockey_other",
        "esports",
        "esports_other",
    ):
        assert is_reader_reachable_sport_key(key) is False, key


def test_an_absent_sport_key_is_not_reachable():
    assert is_reader_reachable_sport_key(None) is False
    assert is_reader_reachable_sport_key("") is False


def test_the_prefix_rule_requires_its_separator():
    """A tournament key is a base key plus `_something`, not a string prefix.

    Without the separator, a base key `tennis_atp` would make `tennis_atpx`
    reachable — the same class as the initials-are-wildcards defect: a prefix
    test with no boundary matches things nobody meant.
    """
    assert is_reader_reachable_sport_key("tennis_atp_us_open") is True
    assert is_reader_reachable_sport_key("tennis_atpx") is False


# ---------------------------------------------------------------------------
# (b) THE SELECTOR — the narrowing has to reach the database
# ---------------------------------------------------------------------------


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)

    def all(self):
        return list(self._rows)


class _ScopedSession:
    """Answers the reachability lookup, then records the candidate scan."""

    def __init__(self, sports, rows=()):
        self.sports = sports
        self.rows = rows
        self.params = None
        self.scans = 0

    async def execute(self, statement, params=None):
        if params is None:
            return _RowsResult(self.sports)
        self.scans += 1
        self.params = dict(params)
        return _RowsResult(self.rows)


def _candidate(event_id, *, lifetime_hours, points):
    last = datetime(2026, 9, 1, tzinfo=UTC)
    return SimpleNamespace(
        event_id=event_id,
        market_first_seen=last - timedelta(hours=lifetime_hours),
        market_last_seen=last,
        point_count=points,
    )


async def test_the_scan_is_filtered_to_reachable_sport_ids():
    """The classifier must reach the QUERY, not just exist beside it."""
    from app.tasks.event_chart_backfill import select_thin_chart_page

    session = _ScopedSession(
        sports=[(11, "tennis_atp"), (22, "soccer_other"), (33, "baseball_mlb")],
        rows=[_candidate(1, lifetime_hours=130, points=1)],
    )

    await select_thin_chart_page(session, limit=5)

    assert session.params["sport_ids"] == [11, 33], (
        "soccer_other must not be selectable by the nightly"
    )


async def test_the_reader_window_reaches_forwards_as_well_as_back():
    """The "live/upcoming card" half of the ruling.

    `commence_time <= NOW()` used to be a hard bound, and it excluded every
    upcoming match — which on this cohort is exactly where the interesting curve
    already exists. The specimen's own market had FIVE DAYS of pre-match drift
    before its `events` row was created; on an upcoming match that drift is the
    whole chart, not a prologue to it.
    """
    from app.tasks.event_chart_backfill import select_thin_chart_page

    session = _ScopedSession(sports=[(11, "tennis_atp")], rows=[])
    await select_thin_chart_page(session, limit=5)

    assert session.params["lookahead_days"] == READER_REACH_LOOKAHEAD_DAYS > 0
    assert session.params["lookback_days"] == READER_REACH_LOOKBACK_DAYS > 0
    assert "+ make_interval(days => :lookahead_days)" in THIN_CHART_CANDIDATES_SQL
    assert "e.commence_time <= NOW()\n" not in THIN_CHART_CANDIDATES_SQL, (
        "the past-only bound is what excluded upcoming cards"
    )


async def test_no_reachable_sport_selects_nothing_and_never_scans_unfiltered():
    """A broken classifier must select NOTHING, not EVERYTHING.

    `IN ()` on an empty expanding bind is the accident this guards: an empty
    allowlist that falls through to an unfiltered scan would quietly restore the
    44,315-event sweep under a name that says it was narrowed. Gotcha #53's
    shape — the failure has to be loud, and it must not do work.
    """
    from app.tasks.event_chart_backfill import select_thin_chart_page

    session = _ScopedSession(sports=[(22, "soccer_other")], rows=[])

    page = await select_thin_chart_page(session, limit=5)

    assert page.event_ids == []
    assert page.exhausted is True
    assert session.scans == 0, "it must not issue the candidate scan at all"


async def test_the_cursor_is_preserved_when_the_classifier_finds_nothing():
    """A classifier failure must not also destroy the ring position.

    Returning `next_cursor=None` with `exhausted=True` would CLEAR the stored
    cursor, so one bad night would restart the ring at its oldest end and
    re-walk everything already judged.
    """
    from app.tasks.event_chart_backfill import select_thin_chart_page

    where_we_were = (datetime(2026, 8, 12, tzinfo=UTC), 4242)
    session = _ScopedSession(sports=[], rows=[])

    page = await select_thin_chart_page(session, limit=5, after=where_we_were)

    assert page.next_cursor == where_we_were


def test_the_backlog_is_no_longer_the_sweeps_denominator():
    """"Drop the 44,315 backlog as a goal" — as a code property, not a comment."""
    import app.tasks.event_chart_backfill as mod

    assert mod.MEASURED_REACHABLE_POPULATION < HISTORICAL_UNNARROWED_POPULATION
    source = mod._note_budget_shortfall.__code__.co_consts
    assert not any(
        c == HISTORICAL_UNNARROWED_POPULATION for c in source if isinstance(c, int)
    ), "the shortfall arithmetic must not inline the abandoned backlog"


# ---------------------------------------------------------------------------
# (c) GRANULARITY — hourly for old, 1-minute for live/recent
# ---------------------------------------------------------------------------


def test_recent_events_keep_minute_granularity_and_old_ones_go_hourly():
    day = 86400
    assert granularity_floor_minutes(0) == 1
    assert granularity_floor_minutes(3 * day) == 1
    assert granularity_floor_minutes((COARSE_GRANULARITY_AGE_DAYS + 1) * day) == 60
    assert granularity_floor_minutes(60 * day) == 60


def test_an_unknown_age_reads_as_recent_not_as_old():
    """The safe direction for an unknown is the FINER curve.

    Overpaying for one event costs a few seconds of a nightly. Drawing a
    five-day match as 120 hourly dots costs the shape of the story, and nobody
    looking at the chart can tell it happened.
    """
    assert granularity_floor_minutes(None) == 1


def test_an_event_that_has_not_started_is_as_recent_as_it_gets():
    """A future `commence_time` must not read as a huge age via its sign."""
    from app.tasks.event_chart_backfill import _event_age_seconds

    future = SimpleNamespace(
        completed_at=None,
        commence_time=datetime.now(UTC) + timedelta(days=3),
    )
    assert _event_age_seconds(future) == 0.0
    assert granularity_floor_minutes(_event_age_seconds(future)) == 1


def test_the_granularity_floor_never_returns_an_unsupported_interval():
    """Kalshi answers `period_interval=5` with junk, not an error.

    Four candles for a window that yields 1,134 at 1-minute — an answer shaped
    like data, which is worse than a refusal. A floor that is not itself a
    supported interval must round UP to one.
    """
    for floor in (2, 5, 15, 59):
        chosen = choose_period_interval(5 * 86400, min_interval=floor)
        assert chosen in KALSHI_PERIOD_INTERVALS
        assert chosen >= floor


def test_the_floor_is_a_floor_and_the_request_budget_can_still_go_coarser():
    """A months-long market must not be dragged back to minute paging by a `1`."""
    ten_years = 3650 * 86400
    assert choose_period_interval(ten_years, min_interval=1) == 1440


def test_an_hourly_floor_costs_one_request_where_minutes_cost_several():
    """The throughput half of ruling (c), in requests rather than in prose."""
    from app.tasks.event_chart_backfill import candle_windows

    span = 5 * 86400
    fine = choose_period_interval(span, min_interval=1)
    coarse = choose_period_interval(span, min_interval=60)

    fine_requests = len(candle_windows(0, span, period_minutes=fine))
    coarse_requests = len(candle_windows(0, span, period_minutes=coarse))

    assert coarse_requests < fine_requests
    assert coarse_requests == 1


async def test_an_old_event_stops_asking_polymarket_for_minute_data():
    from app.tasks.event_chart_backfill import fetch_polymarket_series

    asked = []

    class _Service:
        async def get_prices_history(self, *, token_id, interval, fidelity):
            asked.append(fidelity)
            return [{"t": 1, "p": 0.5}]

    market = SimpleNamespace(
        id=1, market_metadata={"clob_token_ids": ["tok-1", "tok-2"]},
        group_id=None, external_id=None,
    )
    outcome = SimpleNamespace(name="Yes", external_id="cond-1", rank=1)

    await fetch_polymarket_series(
        _Service(), market, outcome, stats={}, min_period_minutes=60
    )
    assert asked == [60]


async def test_a_recent_event_keeps_the_one_to_sixty_fallback():
    """CONTROL, and it is the one that matters.

    The 1→60 retry is NOT a granularity preference — it is the disambiguation
    for a token that answers empty at minute fidelity (gotcha #53: an empty 200
    is a response shape, not an absence). Collapsing it into the coarse path
    would turn "this token does not serve minute data" back into "this market
    has no history".
    """
    from app.tasks.event_chart_backfill import fetch_polymarket_series

    asked = []

    class _EmptyThenFull:
        async def get_prices_history(self, *, token_id, interval, fidelity):
            asked.append(fidelity)
            return [] if fidelity == 1 else [{"t": 1, "p": 0.5}]

    market = SimpleNamespace(
        id=1, market_metadata={"clob_token_ids": ["tok-1", "tok-2"]},
        group_id=None, external_id=None,
    )
    outcome = SimpleNamespace(name="Yes", external_id="cond-1", rank=1)

    points = await fetch_polymarket_series(
        _EmptyThenFull(), market, outcome, stats={}, min_period_minutes=1
    )
    assert asked == [1, 60]
    assert points, "the hourly retry must still rescue the series"


# ---------------------------------------------------------------------------
# (c) ON DEMAND — the page a reader actually opened
# ---------------------------------------------------------------------------


class _MinResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _OnDemandSession:
    def __init__(self, first_seen):
        self.first_seen = first_seen
        self.queries = 0

    async def execute(self, statement, params=None):
        self.queries += 1
        return _MinResult(self.first_seen)


class _FakeRedis:
    """Enough of the client for the claim, and it RECORDS, so dedupe is provable."""

    def __init__(self):
        self.store = {}
        self.deleted = []

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    def incr(self, key):
        self.store[key] = int(self.store.get(key, 0)) + 1
        return self.store[key]

    def expire(self, key, seconds):
        return True

    def delete(self, key):
        self.deleted.append(key)
        self.store.pop(key, None)
        return 1


@pytest.fixture
def redis(monkeypatch):
    client = _FakeRedis()
    monkeypatch.setattr(
        "app.tasks.redis_state.get_redis_client", lambda *a, **k: client
    )
    return client


@pytest.fixture
def enqueued(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.tasks.backfill_event_chart_history.apply_async",
        lambda **kw: calls.append(kw),
    )
    return calls


def _event(event_id=15300759, *, completed_days_ago=1):
    return SimpleNamespace(
        id=event_id,
        completed_at=datetime.now(UTC) - timedelta(days=completed_days_ago),
        commence_time=datetime.now(UTC) - timedelta(days=completed_days_ago),
    )


async def test_the_specimens_thin_chart_enqueues_its_own_fill(redis, enqueued):
    """THE SHIP for ruling (c): one dot served, one fill started.

    Event 15300759 served ONE point for a market that had been live for five
    days. That is the exact response that must now start its own repair.
    """
    from app.tasks.event_chart_backfill import maybe_enqueue_on_demand_fill

    session = _OnDemandSession(datetime.now(UTC) - timedelta(days=5))

    verdict = await maybe_enqueue_on_demand_fill(session, _event(), served_points=1)

    assert verdict["enqueued"] is True
    assert enqueued == [
        {"kwargs": {"event_ids": [15300759], "limit": 1}, "queue": "background"}
    ]


async def test_a_drawn_chart_costs_nothing_at_all(redis, enqueued):
    """The cheap gate is load-bearing: this runs on every history request.

    Asserting only "did not enqueue" would pass on a version that ran both
    queries first. The point is that a healthy chart reaches NO query.
    """
    from app.tasks.event_chart_backfill import maybe_enqueue_on_demand_fill

    session = _OnDemandSession(datetime.now(UTC) - timedelta(days=5))

    verdict = await maybe_enqueue_on_demand_fill(
        session, _event(), served_points=THIN_MAX_EXPECTED_POINTS
    )

    assert verdict is None
    assert session.queries == 0
    assert enqueued == []


async def test_the_cheap_gate_cannot_reject_a_real_candidate(redis, enqueued):
    """The gate's threshold must be exactly the thinness rule's own ceiling.

    A gate TIGHTER than `is_thin_chart`'s cap would silently refuse events the
    real predicate accepts — a narrowing nobody ruled, hidden inside an
    optimisation, and invisible because both versions "did not enqueue".

    So this probes the widest series that is still thin: one point below the
    cap, over a lifetime long enough that the real predicate wants all of them.
    It must get PAST the gate and reach the query. Pairing it with
    `test_a_drawn_chart_costs_nothing_at_all` pins the threshold from both
    sides — one asserts the gate stops at the cap, this asserts it stops no
    earlier.
    """
    from app.tasks.event_chart_backfill import (
        is_thin_chart,
        maybe_enqueue_on_demand_fill,
    )

    just_under = THIN_MAX_EXPECTED_POINTS - 1
    long_life = 10 * 24 * 3600
    assert is_thin_chart(just_under, long_life), "control: this IS thin"

    session = _OnDemandSession(datetime.now(UTC) - timedelta(days=10))
    verdict = await maybe_enqueue_on_demand_fill(
        session, _event(), served_points=just_under
    )

    assert session.queries == 1, "the gate must not swallow a real candidate"
    assert verdict["enqueued"] is True


async def test_a_short_match_that_is_already_drawn_does_not_enqueue(redis, enqueued):
    """🔴 THE GAP BETWEEN THE CHEAP GATE AND THE REAL RULE.

    Found by the mutation battery: deleting the `is_thin_chart` call left every
    guard green, because every thin/thick case tested either sat above the
    cheap gate's 120 or was genuinely thin. A two-hour match with 50 points is
    neither — well below the gate, and comfortably DRAWN for the life it had.

    Without the thinness rule that chart enqueues a pointless venue fetch on
    every single page view, and nothing in the response would ever say so.
    """
    from app.tasks.event_chart_backfill import (
        THIN_POINTS_PER_HOUR,
        is_thin_chart,
        maybe_enqueue_on_demand_fill,
    )

    two_hours = 2 * 3600
    assert not is_thin_chart(50, two_hours), (
        f"control: 50 points over 2h is drawn at {THIN_POINTS_PER_HOUR}/hour"
    )

    session = _OnDemandSession(datetime.now(UTC) - timedelta(hours=3))
    short_match = SimpleNamespace(
        id=777,
        completed_at=datetime.now(UTC) - timedelta(hours=1),
        commence_time=datetime.now(UTC) - timedelta(hours=3),
    )

    verdict = await maybe_enqueue_on_demand_fill(
        session, short_match, served_points=50
    )

    assert verdict is None
    assert enqueued == [], "a drawn chart must never spend a venue request"


async def test_a_second_reader_inside_the_ttl_does_not_enqueue_again(redis, enqueued):
    """A page being shared and opened twenty times costs ONE fill."""
    from app.tasks.event_chart_backfill import maybe_enqueue_on_demand_fill

    session = _OnDemandSession(datetime.now(UTC) - timedelta(days=5))

    first = await maybe_enqueue_on_demand_fill(session, _event(), served_points=1)
    second = await maybe_enqueue_on_demand_fill(session, _event(), served_points=1)

    assert first["enqueued"] is True
    assert second == {"enqueued": False, "reason": "already_claimed"}
    assert len(enqueued) == 1


async def test_a_crawler_is_stopped_by_the_hourly_cap(redis, enqueued):
    """`/api/events/{id}/history` is a public GET over enumerable ids.

    Without a global bound, a bot walking every event id converts page views
    into unbounded outbound venue traffic.
    """
    from app.tasks.event_chart_backfill import ON_DEMAND_HOURLY_CAP, claim_on_demand_fill

    granted = sum(
        1 for event_id in range(ON_DEMAND_HOURLY_CAP + 25)
        if claim_on_demand_fill(event_id)[0]
    )

    assert granted == ON_DEMAND_HOURLY_CAP


async def test_a_capped_event_does_not_stay_claimed_for_six_hours(redis):
    """The claim is handed BACK when the budget refuses it.

    Otherwise one busy hour suppresses that event's fill for the rest of the
    day — the cap would silently become a six-hour blocklist.
    """
    from app.tasks.event_chart_backfill import (
        ON_DEMAND_CLAIM_KEY,
        claim_on_demand_fill,
    )

    for event_id in range(200):
        claimed, reason = claim_on_demand_fill(event_id)
        if not claimed:
            assert reason == "hourly_cap"
            assert ON_DEMAND_CLAIM_KEY.format(event_id=event_id) in redis.deleted
            return
    pytest.fail("the hourly cap never fired")


async def test_no_redis_refuses_the_claim_rather_than_failing_open(monkeypatch):
    """🔴 FAILS CLOSED, and it is the only Redis touch in this module that does.

    Everywhere else a missing hint means "do the work anyway", because the cost
    is one wasted scan. Here the caller is a public GET and the Redis key IS the
    dedupe: failing open turns one crawler into one enqueued task per request.
    """
    from app.tasks.event_chart_backfill import claim_on_demand_fill

    def _boom(*a, **k):
        raise RuntimeError("redis down")

    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", _boom)

    assert claim_on_demand_fill(1) == (False, "no_redis")


async def test_an_expired_market_is_not_chased(redis, enqueued):
    """Past the retention floor the candles are provably gone (gotcha #35)."""
    from app.tasks.event_chart_backfill import maybe_enqueue_on_demand_fill
    from app.utils.kalshi_retention import PROVABLY_PURGED_AGE_DAYS

    session = _OnDemandSession(datetime.now(UTC) - timedelta(days=400))
    old = _event(completed_days_ago=PROVABLY_PURGED_AGE_DAYS + 10)

    verdict = await maybe_enqueue_on_demand_fill(session, old, served_points=1)

    assert verdict == {"enqueued": False, "reason": "beyond_retention_floor"}
    assert enqueued == []


async def test_an_event_with_no_venue_market_says_so_rather_than_enqueueing(
    redis, enqueued
):
    """Not every thin chart is one this rail can fix, and that is not the same
    as the chart being fine (gotcha #53)."""
    from app.tasks.event_chart_backfill import maybe_enqueue_on_demand_fill

    verdict = await maybe_enqueue_on_demand_fill(
        _OnDemandSession(None), _event(), served_points=1
    )

    assert verdict == {"enqueued": False, "reason": "no_venue_markets"}
    assert enqueued == []


async def test_a_broken_refill_never_costs_the_reader_their_chart(redis, enqueued):
    """The chart endpoint must survive anything this rail does (gotcha #42)."""
    from app.tasks.event_chart_backfill import maybe_enqueue_on_demand_fill

    class _Exploding:
        async def execute(self, *a, **k):
            raise RuntimeError("database on fire")

    assert await maybe_enqueue_on_demand_fill(
        _Exploding(), _event(), served_points=1
    ) is None


async def test_on_demand_is_not_limited_to_the_nightlys_narrow_population(
    redis, enqueued
):
    """🔴 THE POINT OF THE PAIR.

    A February soccer match is deliberately outside the nightly's population.
    The instant somebody opens it, it becomes an event a reader reached — and
    reachability is what the whole design is keyed on. If this ever starts
    consulting `is_reader_reachable_sport_key`, the ruling's second half is gone
    and the dropped 3,390 are dropped for good.
    """
    from app.tasks.event_chart_backfill import (
        is_reader_reachable_sport_key,
        maybe_enqueue_on_demand_fill,
    )

    assert is_reader_reachable_sport_key("soccer_other") is False

    session = _OnDemandSession(datetime.now(UTC) - timedelta(days=3))
    february_soccer = _event(event_id=999001)
    february_soccer.sport = SimpleNamespace(key="soccer_other")

    verdict = await maybe_enqueue_on_demand_fill(
        session, february_soccer, served_points=1
    )

    assert verdict["enqueued"] is True


async def test_an_old_page_view_fills_at_hourly_and_a_recent_one_at_minute(
    redis, enqueued
):
    from app.tasks.event_chart_backfill import maybe_enqueue_on_demand_fill

    session = _OnDemandSession(datetime.now(UTC) - timedelta(days=40))

    recent = await maybe_enqueue_on_demand_fill(
        session, _event(event_id=1, completed_days_ago=2), served_points=1
    )
    old = await maybe_enqueue_on_demand_fill(
        session,
        _event(event_id=2, completed_days_ago=COARSE_GRANULARITY_AGE_DAYS + 5),
        served_points=1,
    )

    assert recent["min_period_minutes"] == 1
    assert old["min_period_minutes"] == 60
