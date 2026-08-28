"""RED-FIRST GATE for LAT-P104 — the shared concept stage stops being thrown
away while it is still fresh.

LAT-P103 parked this as `LAT-P103-1`:

    the concept stage key buckets on **30 s** while its TTL is **60 s**, so the
    key changes twice per TTL and every rotation costs a fleet-wide rebuild.
    Whether the bucket can widen (what actually moves in the concept build
    inside 60 s [...]) is a measurement nobody has taken, and it is a strictly
    larger lever than this queue's, on the same artifact.

## The evidence, which was already paid for

No new production read was needed. LAT-P103's own BEFORE instrument is a natural
experiment: ten cold builds, ten principals, ten unwarmed shapes, slug
`ba3be25f`, 2026-08-27. Across those same ten requests —

    canonical_counts   reused 10/10   key carries NO clock component
    concepts           reused  6/10   key carries a 30-second clock bucket

Two artifacts, one instrument, one difference between their keys. The stage that
rotates its key twice a minute is the stage that failed to be reused, and the
cost of each failure is LAT-P084's measured concept build: **865-1249 ms**, paid
by whichever person's Discover open happens to land on the rotation.

## The claim this file executes

Staleness is `min(TTL, bucket)` — an entry is served only while `age < TTL` AND
the bucket has not turned. So a bucket **wider** than the TTL cannot make any
reader staler; it can only stop the key from discarding entries the TTL still
considers fresh. Widening from 30 s to an hour therefore takes the concept
stage's rebuild rate from `1/30 s` to `1/TTL + 1/3600 s`, with no change to how
stale a card's text can be.

That is arithmetic. What is NOT arithmetic — and is the thing the parked item
said had never been established — is the premise that the concept build's
`now`-sensitivity is coarser than an hour. It is established here by
enumeration rather than by sampling, because there are exactly four inputs:

    marquee_pin_state(key, now)   windows open at UTC midnight and expire at
                                  UTC 12:00 (settlement = midnight after the
                                  end day; whathit = settlement + 36 h)
    _score_event_concept(c, now)  reads `now.date()` and nothing finer
    _concept_headline(c, now)     reads `now.date()` and nothing finer
    list_all_concepts(db, ...)    takes no clock at all

`grep -n 'now' `over the body of `_score_event_concepts` returns those three
call sites and nothing else. The finest grid any of them moves on is 12 hours;
an hour is the coarsest bucket that still lands exactly on all of them.

`test_the_now_sensitivity_of_the_concept_build_is_coarser_than_the_bucket` is
what keeps that premise true after this session: an hour-granularity branch
added to any of the three goes red HERE, at the place the bucket width is
justified, instead of shipping an hour of stale text.

## RED-FIRST — the measured matrix, not the predicted one

Five mutations, each applied alone from a `cp` backup and each restore verified
by `cmp` AND `shasum` before the next (LAT-P100 lost a whole battery to stacked
mutations, gotcha #51). Counts are what pytest actually printed:

    M1  `feed.py` call site restored to `_shared_time_bucket(now, 30)`   2 fail
        -> the two route gates in section 4.
    M2  `clock_bucket_s` returns `float(CLOCK_BUCKET_S)`, clamp removed  1 fail
        -> the env-raise invariant. This is the one that catches the defect
           coming back via `FEED_SHARED_BUILD_TTL_S` with no deploy.
    M3  the clock component dropped from `_concept_key` entirely         1 fail
        -> the cell-boundary rebuild. Proves the bucket is not merely
           vestigial once it is wider than the TTL.
    M4  the L1 TTL check disabled (`if False and ...`)                   1 fail
        -> `test_widening_the_key_did_not_widen_staleness`. The pair M3/M4 is
           what separates "the key stopped churning" from "nothing expires".
    M5  a `"Starts in N min"` branch added to `_concept_headline`       10 fail
        -> the enumeration, and ONLY on the `starts-later-today` row. That is
           the guard the bucket width rests on, and the row set exists because
           a single far-off row misses it (see `CONCEPT_ROWS`).

**Corrected, 2026-08-28:** this section previously claimed M1 also reddened the
key-stability gates. It does not, and the run says so — `test_the_key_component_
is_stable_across_a_full_ttl` reads `clock_bucket_s()` directly, so no call-site
mutation can move it; only M2 can. The sentence was a prediction that was never
executed. It is replaced by the counts above, which were.

The enumeration and invariant tests stay green under M1, correctly: they
describe the build, not the fix.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw
from app.utils.principal_independent_cache import (
    CLOCK_BUCKET_S,
    DEFAULT_TTL_S,
    clock_bucket_s,
    shared_build_ttl_s,
    time_bucket,
)

UTC = timezone.utc

#: A fixed instant used by every clock test in this file. Deliberately NOT
#: derived from the wall clock: an anchor that branches on "what time is it"
#: is not an anchor (gotcha #44 — offset first, then truncate). 18:10:00Z sits
#: 600 s after its cell opens and 3,000 s before the next one, so a +35 s step
#: cannot silently cross a boundary and turn a red test green for the wrong
#: reason.
ANCHOR = datetime(2026, 8, 27, 18, 10, 0, tzinfo=UTC)

#: Offset from ANCHOR to the first instant of the NEXT hourly cell.
NEXT_CELL_S = 3000.0

#: Longer than the 30 s bucket this queue removes, shorter than the 60 s TTL.
#: The whole defect lives in exactly this gap.
STEP_S = 35.0


# --------------------------------------------------------------------------
# 1. The arithmetic: a key that turns faster than the TTL discards fresh work
# --------------------------------------------------------------------------


def test_the_bucket_is_never_finer_than_the_ttl():
    """The invariant LAT-P104 exists to establish, at the default TTL."""
    assert clock_bucket_s() >= DEFAULT_TTL_S, (
        f"the clock bucket is {clock_bucket_s()}s against a {DEFAULT_TTL_S}s TTL; "
        "a key that turns before the TTL expires throws away a fresh artifact "
        "and charges the next person the rebuild"
    )


def test_the_bucket_stays_wider_than_the_ttl_when_the_ttl_is_raised_by_env(
    monkeypatch,
):
    """`FEED_SHARED_BUILD_TTL_S` is a no-deploy runtime lever, so the invariant
    has to survive it being pulled.

    This is why `clock_bucket_s()` clamps instead of returning the constant: a
    bare `CLOCK_BUCKET_S` would put the defect back one env var later, and it
    would come back silently — nothing about a slower feed says "someone raised
    the TTL past the bucket"."""
    monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S", "7200")

    assert shared_build_ttl_s() == 7200.0
    assert CLOCK_BUCKET_S < 7200.0, "precondition: the raised TTL must exceed the constant"
    assert clock_bucket_s() >= 7200.0, (
        "raising the TTL past CLOCK_BUCKET_S must widen the bucket with it, not "
        "leave a key that turns 2x per TTL"
    )


def test_ttl_zero_does_not_narrow_the_bucket(monkeypatch):
    """`FEED_SHARED_BUILD_TTL_S=0` is the whole-module kill switch. It must not
    reach into the bucket clamp and produce a degenerate width — the kill
    switch's job is to stop sharing, and it does that at `get_or_build`."""
    monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S", "0")

    assert shared_build_ttl_s() == 0.0
    assert clock_bucket_s() == float(CLOCK_BUCKET_S)


def test_the_key_component_is_stable_across_a_full_ttl():
    """The direct statement of the fix: within one TTL the key does not move.

    RED under the 30 s literal — 35 s apart is two different 30 s buckets."""
    first = time_bucket(ANCHOR, clock_bucket_s())
    later = time_bucket(ANCHOR + timedelta(seconds=DEFAULT_TTL_S), clock_bucket_s())

    assert first == later, (
        "the concept key changed inside one TTL, so the fleet rebuilt a "
        "865-1249ms stage whose result was still fresh"
    )


def test_the_thirty_second_literal_is_what_moved_the_key():
    """Pins the defect itself, so the gate above cannot be read as vacuous.

    If this ever fails, `time_bucket` stopped bucketing and every other
    assertion in this file is measuring nothing."""
    assert time_bucket(ANCHOR, 30) != time_bucket(ANCHOR + timedelta(seconds=STEP_S), 30)


# --------------------------------------------------------------------------
# 2. Boundary alignment — the bucket's remaining job
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "boundary,what",
    [
        (datetime(2026, 8, 28, 0, 0, 0, tzinfo=UTC), "UTC midnight: `now.date()` rolls"),
        (datetime(2026, 8, 28, 12, 0, 0, tzinfo=UTC), "UTC 12:00: the whathit pin expires"),
    ],
)
def test_the_key_turns_exactly_at_every_boundary_the_build_has(boundary, what):
    """An hourly grid lands on both boundary families, so the key flips AT the
    content change rather than up to a TTL after it.

    This is the reason the bucket is not simply deleted in favour of the TTL:
    with no clock component at all, a card built at 23:59:30 saying "Tomorrow"
    would keep saying it into the new day for the rest of its TTL."""
    before = time_bucket(boundary - timedelta(seconds=1), clock_bucket_s())
    after = time_bucket(boundary, clock_bucket_s())

    assert before != after, f"the key did not turn at {what}"


def test_two_principals_arriving_moments_apart_share_a_key():
    """LAT-P084's original property, unchanged by the widening: bucketing on the
    CLOCK (not on an offset from a per-request `now`) is what makes two people
    who open Discover 200 ms apart land on one build."""
    a = time_bucket(ANCHOR, clock_bucket_s())
    b = time_bucket(ANCHOR + timedelta(milliseconds=200), clock_bucket_s())

    assert a == b


# --------------------------------------------------------------------------
# 3. The premise: what the concept build's `now` actually gates
#
# The parked item called this "a measurement nobody has taken". It is not a
# measurement — the inputs are enumerable and they are enumerated here.
# --------------------------------------------------------------------------


def _concept_row(**over):
    """A concept row shaped like `list_all_concepts` output."""
    row = {
        "key": "event:ufc:p104",
        "name": "UFC 999",
        "domain": "ufc",
        "status": "upcoming",
        "start_date": date(2026, 8, 29),
        "latest_commence": datetime(2026, 8, 29, 2, 0, tzinfo=UTC),
        "is_major": True,
        "fight_count": 12,
        "entry_count": 0,
    }
    row.update(over)
    return row


#: The rows the invariance check runs over. A single row is NOT enough and this
#: list exists because a single row was tried first: a `latest_commence` two
#: days out never reaches the same-day arm, so a "Starting soon" branch added
#: inside `if days_until <= 0` was invisible to the guard and the mutation that
#: should have reddened it came back green. The set spans every arm both
#: clock-reading helpers have — same-day (the one that was missed), tomorrow,
#: within the week, far-off, live, and no-start-time — so a sub-hour branch
#: added to any of them has somewhere to show up.
CONCEPT_ROWS = [
    pytest.param(
        _concept_row(
            key="p104:today",
            start_date=date(2026, 8, 27),
            latest_commence=datetime(2026, 8, 27, 18, 40, tzinfo=UTC),
        ),
        id="starts-later-today",
    ),
    pytest.param(
        _concept_row(
            key="p104:underway",
            start_date=date(2026, 8, 27),
            latest_commence=datetime(2026, 8, 27, 17, 55, tzinfo=UTC),
        ),
        id="started-minutes-ago",
    ),
    pytest.param(
        _concept_row(
            key="p104:tomorrow",
            start_date=date(2026, 8, 28),
            latest_commence=datetime(2026, 8, 28, 2, 0, tzinfo=UTC),
        ),
        id="tomorrow",
    ),
    pytest.param(_concept_row(), id="this-week"),
    pytest.param(
        _concept_row(
            key="p104:far",
            start_date=date(2026, 10, 30),
            latest_commence=datetime(2026, 10, 30, 2, 0, tzinfo=UTC),
        ),
        id="far-off",
    ),
    pytest.param(_concept_row(key="p104:live", status="live"), id="live"),
    pytest.param(
        _concept_row(key="p104:nostart", latest_commence=None, start_date=None),
        id="no-start-time",
    ),
]


#: Offsets that stay inside ANCHOR's hourly cell, chosen to straddle every
#: sub-hour period anyone might reach for — the removed 30 s bucket, a minute,
#: half an hour — and ending on the cell's last second. If any concept-build
#: input moves across this set, an hourly bucket is too coarse and the constant
#: must come down.
WITHIN_ONE_CELL = [0, 1, 29, 30, 31, 59, 60, 61, 1799, 1800, 2999]


@pytest.mark.parametrize("row", CONCEPT_ROWS)
@pytest.mark.parametrize("offset_s", WITHIN_ONE_CELL)
def test_the_now_sensitivity_of_the_concept_build_is_coarser_than_the_bucket(
    offset_s, row
):
    """All three `now` consumers in `_score_event_concepts` are invariant inside
    one hourly cell — so an hourly key cannot serve text that a finer key would
    have refreshed.

    A future author who adds a minute-granularity branch (a "starts in 20
    minutes" headline, say) fails here. That is the point: the bucket width is
    only defensible while this holds, and this is where it is stated."""
    from app.routes.feed import _concept_headline, _score_event_concept
    from app.utils.majors_calendar import marquee_pin_state

    later = ANCHOR + timedelta(seconds=offset_s)

    assert time_bucket(ANCHOR, clock_bucket_s()) == time_bucket(
        later, clock_bucket_s()
    ), "precondition: the two instants must be in the same cell"

    assert _score_event_concept(row, ANCHOR) == _score_event_concept(row, later)
    assert _concept_headline(row, ANCHOR) == _concept_headline(row, later)

    entries = {
        row["key"]: {
            "marquee": True,
            "start": date(2026, 8, 27),
            "end": date(2026, 8, 29),
            "concept_key": row["key"],
        }
    }
    assert marquee_pin_state(row["key"], ANCHOR, entries=entries) == marquee_pin_state(
        row["key"], later, entries=entries
    )


def test_the_enumeration_is_not_vacuous_across_a_cell_boundary():
    """The invariance above would also hold for a build that ignored `now`
    entirely. These are the crossings that prove the three consumers really do
    read the clock, so the test above is constraining something."""
    from app.routes.feed import _concept_headline, _score_event_concept
    from app.utils.majors_calendar import marquee_pin_state

    row = _concept_row()

    # `now.date()` rolling changes both the score bonus and the headline text.
    day_before = datetime(2026, 8, 28, 23, 59, 59, tzinfo=UTC)
    day_after = datetime(2026, 8, 29, 0, 0, 0, tzinfo=UTC)
    assert _concept_headline(row, day_before) != _concept_headline(row, day_after)
    assert _score_event_concept(row, day_before) != _score_event_concept(row, day_after)

    # The whathit pin expires at settlement + 36h = UTC 12:00.
    entries = {
        row["key"]: {
            "marquee": True,
            "start": date(2026, 8, 27),
            "end": date(2026, 8, 29),
            "concept_key": row["key"],
        }
    }
    # settlement = 2026-08-30 00:00Z, whathit_end = 2026-08-31 12:00Z
    assert (
        marquee_pin_state(
            row["key"], datetime(2026, 8, 31, 11, 59, 59, tzinfo=UTC), entries=entries
        )
        == "whathit"
    )
    assert (
        marquee_pin_state(
            row["key"], datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC), entries=entries
        )
        is None
    )


def test_the_concept_population_lister_takes_no_clock():
    """The fourth input, checked structurally rather than by reading it once.

    `list_all_concepts` is where the concept rows come from. If it ever grows a
    clock, its freshness stops being TTL-bounded and starts being bucket-bounded,
    and the width chosen here would need re-deriving."""
    import inspect

    from app.utils import event_concept_population

    source = inspect.getsource(event_concept_population)
    offending = [
        line
        for line in source.splitlines()
        if ("utcnow" in line or "datetime.now" in line) and not line.lstrip().startswith("#")
    ]
    assert offending == [], (
        "the shared concept population now reads a clock: " f"{offending}"
    )


# --------------------------------------------------------------------------
# 4. THE HEADLINE GATE — the route, two people, one build, 35 seconds apart
# --------------------------------------------------------------------------


def _concept_card():
    return {
        "type": "concept",
        "score": 61,
        "reason": "12 fights on the card",
        "headline": "This week",
        "data": {"key": "event:ufc:p104", "name": "UFC 999", "domain": "ufc"},
        "_sort_time": 1787594136.0,
    }


@pytest.fixture(autouse=True)
def _clean_shared_cache():
    """A process-global cache that leaks between tests is the one failure mode
    that makes a sharing test pass for the wrong reason."""
    from app.utils.principal_independent_cache import clear_shared_builds

    clear_shared_builds()
    yield
    clear_shared_builds()


@pytest.fixture
def stepping_clock(monkeypatch):
    """Advance the feed's `now` by a fixed step between requests.

    `feed.py` does `from datetime import datetime`, so `feed_module.datetime` is
    the whole module's clock and patching it gives every stage of a build one
    consistent instant — which is what a real request has. The stand-in is a
    `datetime` SUBCLASS so `isinstance` checks and every other `datetime.*`
    classmethod in the module keep working; only `now()` is redirected."""
    from app.routes import feed as feed_module

    state = {"offset": 0.0}

    class _SteppedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: D102 - stands in for datetime.now
            moment = ANCHOR + timedelta(seconds=state["offset"])
            return moment if tz is not None else moment.replace(tzinfo=None)

    monkeypatch.setattr(feed_module, "datetime", _SteppedDatetime)
    return state


@pytest.fixture
def counting_concepts(monkeypatch):
    """Count the principal-independent build and, independently, the
    principal-dependent one.

    `concepts == 1` on its own would also be satisfied by a second request that
    never reached a cold build at all. `personalization == 2` is the witness
    that two real builds happened, so `concepts == 1` can only mean reuse."""
    from app.routes import feed as feed_module

    counts: dict[str, list] = {"concepts": [], "personalization": []}

    async def _stub(db, now, sport_filter, ctx=None):
        counts["concepts"].append(now)
        return [_concept_card()]

    _real_ctx = feed_module._load_personalization_context

    async def _counting_ctx(*a, **kw):
        counts["personalization"].append(1)
        return await _real_ctx(*a, **kw)

    monkeypatch.setattr(feed_module, "_score_event_concepts", _stub)
    monkeypatch.setattr(feed_module, "_load_personalization_context", _counting_ctx)
    return counts


@pytest.fixture
async def feed_client(monkeypatch):
    """A feed client over a mocked DB, so two principals can be taken without
    Postgres."""
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")

    from app.main import app

    session = AsyncMock()

    def _empty_result():
        from unittest.mock import MagicMock

        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        result.scalars.return_value.first.return_value = None
        result.scalar_one_or_none.return_value = None
        result.scalar.return_value = None
        result.fetchall.return_value = []
        result.all.return_value = []
        result.first.return_value = None
        return result

    session.execute.return_value = _empty_result()

    async def _mock_get_db():
        yield session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user

    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_a_second_cold_build_35s_later_reuses_the_concept_stage(
    feed_client, counting_concepts, stepping_clock
):
    """THE gate. Two people, two cold builds, 35 seconds apart, ONE concept build.

    35 s is inside the 60 s TTL and outside the 30 s bucket, which is precisely
    the window in which the old key threw a fresh artifact away. RED before this
    change: the second request built again."""
    r1 = await feed_client.get(
        "/api/feed?limit=5", headers={"X-Session-Id": "p104-principal-A"}
    )
    stepping_clock["offset"] = STEP_S
    r2 = await feed_client.get(
        "/api/feed?limit=5", headers={"X-Session-Id": "p104-principal-B"}
    )

    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text

    # Both must be genuine builds, or this says nothing about sharing.
    assert r1.headers.get("X-Feed-Cache") in ("miss", "error"), dict(r1.headers)
    assert r2.headers.get("X-Feed-Cache") in ("miss", "error"), dict(r2.headers)
    assert len(counting_concepts["personalization"]) == 2, (
        "both requests must have reached a real cold build; personalization ran "
        f"{len(counting_concepts['personalization'])} time(s)"
    )

    assert len(counting_concepts["concepts"]) == 1, (
        "the concept stage was built "
        f"{len(counting_concepts['concepts'])} times across two cold builds "
        f"{STEP_S}s apart, inside one {DEFAULT_TTL_S}s TTL — the key turned while "
        "the artifact was still fresh"
    )


@pytest.mark.asyncio
async def test_the_reuse_is_named_on_the_header_so_production_can_read_it(
    feed_client, counting_concepts, stepping_clock
):
    """`X-Feed-Shared` is the production evidence rail for this change: the
    pre-registered post-deploy check is two requests 35 s apart against one
    unwarmed shape, where the second must name `concepts`."""
    await feed_client.get("/api/feed?limit=5", headers={"X-Session-Id": "p104-hdr-A"})
    stepping_clock["offset"] = STEP_S
    r2 = await feed_client.get(
        "/api/feed?limit=5", headers={"X-Session-Id": "p104-hdr-B"}
    )

    shared = r2.headers.get("X-Feed-Shared", "")
    assert "concepts" in shared, (
        f"X-Feed-Shared was {shared!r}; the post-deploy gate reads this header and "
        "would have no way to see the fix"
    )


@pytest.mark.asyncio
async def test_widening_the_key_did_not_widen_staleness():
    """Widening the KEY must not widen STALENESS — the TTL is the bound and it
    still bites at 60 s, on one key, inside one hourly cell.

    Held at `get_or_build` rather than through the route on purpose: the TTL
    ages on `time.monotonic`, which two back-to-back httpx calls advance by
    milliseconds no matter what the feed's `now` says. A route-level "90 s
    later" would move the wrong clock and pass while proving nothing. Here the
    clock is injected, so the assertion means the same thing at 03:00 as at
    15:00.

    Without this pair, "the key never turns inside an hour" would be
    indistinguishable from "the cache never expires", and a concept card could
    carry an hour-old headline."""
    from app.utils.principal_independent_cache import get_or_build

    ticks = {"t": 1000.0}
    builds = {"n": 0}

    async def _build():
        builds["n"] += 1
        return [_concept_card()]

    # The real key shape, so this is the artifact under discussion and not a
    # generic cache probe.
    key = ("all", (), time_bucket(ANCHOR, clock_bucket_s()))

    await get_or_build("concepts", key, _build, clock=lambda: ticks["t"])
    ticks["t"] = 1000.0 + DEFAULT_TTL_S - 1.0
    await get_or_build("concepts", key, _build, clock=lambda: ticks["t"])
    assert builds["n"] == 1, "rebuilt inside the TTL"

    ticks["t"] = 1000.0 + DEFAULT_TTL_S + 1.0
    await get_or_build("concepts", key, _build, clock=lambda: ticks["t"])
    assert builds["n"] == 2, (
        "the concept stage was reused past its TTL; the key widened but the "
        "staleness bound must not have"
    )


@pytest.mark.asyncio
async def test_the_stage_is_rebuilt_across_the_bucket_boundary(
    feed_client, counting_concepts, stepping_clock
):
    """The clock component is still doing its remaining job. Crossing the hour
    boundary rebuilds, so a date rollover or an expiring whathit pin refreshes
    at the boundary instead of a TTL later."""
    await feed_client.get("/api/feed?limit=5", headers={"X-Session-Id": "p104-cell-A"})
    # ANCHOR is 18:10:00Z; this lands on 19:00:00Z exactly. The monotonic clock
    # the TTL reads has advanced by milliseconds, so this is unambiguously a
    # BUCKET crossing and not a TTL expiry — which is what makes it evidence
    # that the clock component still exists at all.
    stepping_clock["offset"] = NEXT_CELL_S
    await feed_client.get("/api/feed?limit=5", headers={"X-Session-Id": "p104-cell-B"})

    assert len(counting_concepts["concepts"]) == 2, (
        "the key did not turn at the cell boundary, so a date rollover would "
        "keep serving yesterday's headline for the rest of the TTL"
    )


@pytest.mark.asyncio
async def test_the_kill_switch_still_builds_every_time(
    feed_client, counting_concepts, stepping_clock, monkeypatch
):
    """`FEED_SHARED_BUILD_TTL_S=0` disables the module. It must survive the
    bucket clamp reading the same env var."""
    monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S", "0")

    await feed_client.get("/api/feed?limit=5", headers={"X-Session-Id": "p104-kill-A"})
    stepping_clock["offset"] = 1.0
    await feed_client.get("/api/feed?limit=5", headers={"X-Session-Id": "p104-kill-B"})

    assert len(counting_concepts["concepts"]) == 2, (
        "the whole-module kill switch stopped killing"
    )
