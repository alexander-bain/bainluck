"""#4920 — the Browse tile promises what its own page renders.

THE DEFECT, measured on production 2026-09-11 04:36-05:05Z. All 28 visible
tiles over-promised and not one was correct: cricket advertised 784 and
rendered 1, tennis 4,995 -> 11, politics 6,757 -> 100. The tile counted rows the
CANDIDATE predicate admits; the page renders what survives the pipeline.

The tests below are grouped by the thing that can break:

* the MERGE — a measured count wins, an unmeasured one does not become a zero;
* the SPLIT — how a rendered payload becomes the tile's two numbers;
* the PASS — one bad category must not wipe its siblings, and a pass that
  publishes nothing must not read green;
* the CADENCE — the period is derived, not typed.

🔴 THE LOAD-BEARING ASSERTION IS `test_a_cold_category_keeps_its_candidate_count`.
`/categories` deletes a tile whose counts sum to zero (#2627). So the failure
mode of this ship is not "a wrong number" but "an empty Browse grid", and it
fires whenever absence gets confused with zero.
"""

from __future__ import annotations

import pytest

from app.routes import feed as feed_module
from app.utils import tag_counts_cache

# ---------------------------------------------------------------------------
# THE MERGE
# ---------------------------------------------------------------------------


def _candidates() -> dict[str, dict[str, int]]:
    """The candidate map, shaped like production's."""
    return {
        "tennis": {"events": 368, "futures": 4627},
        "cricket": {"events": 9, "futures": 775},
        "horse_racing": {"events": 1, "futures": 0},
        "hockey": {"events": 16, "futures": 144},
    }


@pytest.fixture
def merge_harness(monkeypatch):
    """Drive `get_tag_counts` with a fixed candidate map and a fixed cache."""

    def _install(rendered, created_at="2026-09-11T05:00:00+00:00"):
        async def _fake_candidates(_db):
            return _candidates()

        monkeypatch.setattr(feed_module, "_candidate_tag_counts", _fake_candidates)
        monkeypatch.setattr(
            tag_counts_cache, "read", lambda rc=None: (rendered, created_at)
        )

    return _install


@pytest.mark.asyncio
async def test_a_rendered_category_overrides_its_candidate_count(merge_harness):
    """The ship: the tile stops advertising 4,995 for a page that renders 11."""
    merge_harness({"tennis": {"events": 0, "futures": 11}})

    body = await feed_module.get_tag_counts(db=None)

    assert body["counts"]["tennis"] == {
        "events": 0,
        "futures": 11,
        "source": "rendered",
    }


@pytest.mark.asyncio
async def test_a_cold_category_keeps_its_candidate_count(merge_harness):
    """Absence is NOT zero — the tile survives a cold Redis (#2627).

    If this ever fails by returning zeros, `/categories` renders an empty grid
    the moment the producer misses its beats. That is a worse defect than the
    one this ship fixes, which is why it is asserted before the fix itself.
    """
    merge_harness({})  # nothing measured at all

    body = await feed_module.get_tag_counts(db=None)

    assert body["counts"]["tennis"] == {
        "events": 368,
        "futures": 4627,
        "source": "candidate",
    }
    # and every tile still sums above zero, i.e. no tile disappears
    for cat, entry in body["counts"].items():
        if cat == "horse_racing":
            continue  # candidate 1 + 0; still non-zero, see the next test
        assert entry["events"] + entry["futures"] > 0


@pytest.mark.asyncio
async def test_a_measured_zero_is_published_and_deletes_the_tile(merge_harness):
    """A MEASURED zero is a real answer — #2627 working, not a regression.

    `horse_racing` advertised 1 and rendered 0 on production. Once measured, the
    tile is a door onto an empty page and `/categories` is right to remove it.
    """
    merge_harness({"horse_racing": {"events": 0, "futures": 0}})

    body = await feed_module.get_tag_counts(db=None)

    entry = body["counts"]["horse_racing"]
    assert entry == {"events": 0, "futures": 0, "source": "rendered"}
    assert entry["events"] + entry["futures"] == 0  # the frontend drops it


@pytest.mark.asyncio
async def test_an_unmeasured_sibling_is_untouched_by_a_measured_one(merge_harness):
    """A partial publish corrects what it measured and nothing else."""
    merge_harness({"cricket": {"events": 0, "futures": 1}})

    body = await feed_module.get_tag_counts(db=None)

    assert body["counts"]["cricket"]["source"] == "rendered"
    assert body["counts"]["cricket"]["futures"] == 1
    assert body["counts"]["hockey"] == {
        "events": 16,
        "futures": 144,
        "source": "candidate",
    }


@pytest.mark.asyncio
async def test_the_merge_never_invents_a_category(merge_harness):
    """A rendered category absent from the candidate map may not create a tile.

    The producer enumerates FROM the candidate map, so this means the two have
    drifted. Correcting a number is this route's job; adding a tile is not.
    """
    merge_harness({"underwater_basket_weaving": {"events": 3, "futures": 4}})

    body = await feed_module.get_tag_counts(db=None)

    assert "underwater_basket_weaving" not in body["counts"]
    assert set(body["counts"]) == set(_candidates())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad",
    [
        {"events": "0", "futures": 11},  # wrong type
        {"events": 0},  # half written
        {},  # empty
        "not-a-dict",
        None,
    ],
)
async def test_a_malformed_entry_is_not_measured(merge_harness, bad):
    """A malformed entry falls back to the candidate count, never to zero."""
    merge_harness({"tennis": bad})

    body = await feed_module.get_tag_counts(db=None)

    assert body["counts"]["tennis"] == {
        "events": 368,
        "futures": 4627,
        "source": "candidate",
    }


@pytest.mark.asyncio
async def test_an_unreadable_cache_serves_candidate_counts(monkeypatch):
    """Redis being down degrades to today's behaviour, it does not 500.

    This route already spent its whole life returning a plain-text 500 from an
    unhandled exception (the GROUP BY collision); it does not get to do that
    again over a cache read.
    """

    async def _fake_candidates(_db):
        return _candidates()

    def _boom(rc=None):
        raise RuntimeError("redis is down")

    monkeypatch.setattr(feed_module, "_candidate_tag_counts", _fake_candidates)
    monkeypatch.setattr(tag_counts_cache, "read", _boom)

    with pytest.raises(RuntimeError):
        # The route does not swallow it here; `tag_counts_cache.read` is the
        # layer that must. Asserting the raise pins WHERE the guard lives, so a
        # later edit cannot quietly move it and leave neither layer guarding.
        await feed_module.get_tag_counts(db=None)


def test_the_cache_read_is_the_layer_that_swallows(monkeypatch):
    """`tag_counts_cache.read` returns empty rather than raising."""

    class _Boom:
        def get(self, *_a, **_k):
            raise RuntimeError("redis is down")

    counts, created = tag_counts_cache.read(_Boom())

    assert counts == {}
    assert created is None


@pytest.mark.asyncio
async def test_every_entry_is_labelled_with_its_source(merge_harness):
    """`source` is present on every category so the fix is verifiable outside."""
    merge_harness({"tennis": {"events": 0, "futures": 11}})

    body = await feed_module.get_tag_counts(db=None)

    assert {e["source"] for e in body["counts"].values()} == {
        "rendered",
        "candidate",
    }
    assert body["rendered_built_at"] == "2026-09-11T05:00:00+00:00"


# ---------------------------------------------------------------------------
# THE SPLIT
# ---------------------------------------------------------------------------


def test_the_split_maps_the_types_the_feed_actually_emits():
    """`event` -> events; `futures` and `bundle` -> markets.

    The four type strings are the ones production emits for category feeds
    (measured: baseball `{event: 2, futures: 41}`, tennis `{bundle: 1,
    futures: 10}`, politics `{futures: 97, bundle: 3}`).
    """
    items = [
        {"type": "event"},
        {"type": "event"},
        {"type": "futures"},
        {"type": "bundle"},
    ]

    assert tag_counts_cache.split_rendered_items(items) == {
        "events": 2,
        "futures": 2,
    }


def test_an_empty_render_is_a_measured_zero_not_an_absence():
    """An empty items list is a real answer: this category renders nothing."""
    assert tag_counts_cache.split_rendered_items([]) == {
        "events": 0,
        "futures": 0,
    }


@pytest.mark.parametrize("payload", [None, {}, "items", 7])
def test_an_unusable_payload_is_not_measured(payload):
    """Anything that is not a list is NOT MEASURED — `None`, never a zero.

    This is the error-body trap in its own right: a rate-limited or errored
    response is a dict with no `items` key, and `.get("items")` hands back None.
    Reading that as "renders nothing" would delete the tile.
    """
    assert tag_counts_cache.split_rendered_items(payload) is None


def test_an_unknown_item_type_is_counted_as_neither():
    """A type nobody has seen yet is not silently counted as a market."""
    assert tag_counts_cache.split_rendered_items(
        [{"type": "event"}, {"type": "something_new"}, "junk"]
    ) == {"events": 1, "futures": 0}


# ---------------------------------------------------------------------------
# THE PASS
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_one_failing_category_does_not_wipe_its_siblings(monkeypatch):
    """gotcha #42 — a per-item failure costs that item and nothing else."""
    from app.tasks import tag_counts_warm

    published: dict = {}

    async def _cats():
        return ["tennis", "cricket", "hockey"]

    async def _measure(category):
        if category == "cricket":
            return None  # errored / timed out inside the measurer
        return {"events": 0, "futures": 11}

    monkeypatch.setattr(tag_counts_warm, "_candidate_categories", _cats)
    monkeypatch.setattr(tag_counts_warm, "_measure_one_category", _measure)
    monkeypatch.setattr(
        tag_counts_cache,
        "publish",
        lambda counts, rc=None: published.update(counts) or "stamp-2",
    )
    stamps = iter([({}, "stamp-1"), (published, "stamp-2")])
    monkeypatch.setattr(tag_counts_cache, "read", lambda rc=None: next(stamps))

    result = await tag_counts_warm._warm_tag_counts()

    assert result["terminal"] == "complete"
    assert result["measured"] == 2
    assert result["attempted"] == 3
    assert set(published) == {"tennis", "hockey"}
    assert "cricket" not in published  # absent, NOT zero


@pytest.mark.asyncio
async def test_a_pass_that_measures_nothing_does_not_publish(monkeypatch):
    """Zero yield reads FAILED and leaves the previous publish alone (#53)."""
    from app.tasks import tag_counts_warm

    calls: list = []

    async def _cats():
        return ["tennis", "cricket"]

    async def _measure(_category):
        return None

    cache = tag_counts_cache
    monkeypatch.setattr(tag_counts_warm, "_candidate_categories", _cats)
    monkeypatch.setattr(tag_counts_warm, "_measure_one_category", _measure)
    monkeypatch.setattr(cache, "publish", lambda *a, **k: calls.append("published"))
    monkeypatch.setattr(cache, "read", lambda rc=None: ({}, "stamp-1"))

    result = await tag_counts_warm._warm_tag_counts()

    assert result["terminal"] == "failed"
    assert result["published"] is False
    assert calls == []  # the previous publish is left readable


@pytest.mark.asyncio
async def test_a_swallowed_write_reads_failed(monkeypatch):
    """`set()` returning is not Redis keeping — the stamp must CHANGE (#53)."""
    from app.tasks import tag_counts_warm

    async def _cats():
        return ["tennis"]

    async def _measure(_category):
        return {"events": 0, "futures": 11}

    cache = tag_counts_cache
    monkeypatch.setattr(tag_counts_warm, "_candidate_categories", _cats)
    monkeypatch.setattr(tag_counts_warm, "_measure_one_category", _measure)
    monkeypatch.setattr(cache, "publish", lambda *a, **k: "ignored")
    # The stamp never moves: the write was swallowed.
    monkeypatch.setattr(cache, "read", lambda rc=None: ({}, "stamp-1"))

    result = await tag_counts_warm._warm_tag_counts()

    assert result["terminal"] == "failed"
    assert result["published"] is False


@pytest.mark.asyncio
async def test_a_measurer_that_raises_is_contained(monkeypatch):
    """`_measure_one_category` never raises out — proven on the real function."""
    from app.tasks import tag_counts_warm

    def _explode(*_a, **_k):
        raise RuntimeError("the pipeline fell over")

    monkeypatch.setattr(tag_counts_warm, "get_feed", _explode, raising=False)
    monkeypatch.setattr("app.routes.feed.get_feed", _explode)

    assert await tag_counts_warm._measure_one_category("tennis") is None


# ---------------------------------------------------------------------------
# THE CADENCE AND THE BOUNDS
# ---------------------------------------------------------------------------


def test_the_period_is_derived_from_the_slots_own_ttl():
    """Not a literal — a queue moving the TTL moves the beat (#2236)."""
    from app.tasks import tag_counts_warm
    from app.utils.tag_counts_cache import FRESH_TTL_SECONDS

    assert tag_counts_warm.warm_period_seconds() == FRESH_TTL_SECONDS // (
        tag_counts_warm.MISSED_DELIVERY_ALLOWANCE + 1
    )


def test_the_period_is_a_whole_number_of_minutes_that_divides_an_hour():
    """The beat spells `*/N`, so a period like 7 fires :00, :07 ... :00.

    An uneven cadence is invisible to an assertion on the number itself, which
    is why this asserts the property the crontab actually depends on.
    """
    from app.tasks import tag_counts_warm

    minutes = tag_counts_warm.warm_period_minutes()
    assert minutes >= 1
    assert tag_counts_warm.warm_period_seconds() == minutes * 60
    assert 60 % minutes == 0


def test_the_count_limit_clears_the_observed_candidate_ceiling():
    """The split is counted from `items`, and items are capped by the limit.

    Production returns at most 100 items for a category (`politics`, stable
    across limit 20..400). Asking at or below that ceiling would publish a
    confident undercount for the largest categories.
    """
    from app.tasks import tag_counts_warm

    observed_ceiling = 100
    assert tag_counts_warm.COUNT_LIMIT > observed_ceiling


def test_the_pass_is_bounded_in_both_directions():
    """A wedged category is bounded, and so is the pass around it."""
    from app.tasks import tag_counts_warm

    assert tag_counts_warm.PER_CATEGORY_TIMEOUT_SECONDS > 0
    assert (
        tag_counts_warm.PER_CATEGORY_TIMEOUT_SECONDS
        < tag_counts_warm.PASS_BUDGET_SECONDS
    )
    # Enough room for every tile `/categories` can display (28 measured).
    assert tag_counts_warm.MAX_CATEGORIES >= 28


@pytest.mark.asyncio
async def test_the_pass_stops_starting_work_at_its_budget(monkeypatch):
    """The budget bounds the pass and still publishes what it measured."""
    from app.tasks import tag_counts_warm

    published: dict = {}
    # started=0.0, first budget check=0.0 (inside), second=1000.0 (blown).
    # The first category must be ATTEMPTED, or this exercises the zero-yield
    # path instead of the budget path and proves nothing about the budget.
    clock = iter([0.0, 0.0] + [1000.0] * 40)

    async def _cats():
        return ["a", "b", "c"]

    async def _measure(category):
        return {"events": 1, "futures": 1}

    cache = tag_counts_cache
    monkeypatch.setattr(tag_counts_warm, "_candidate_categories", _cats)
    monkeypatch.setattr(tag_counts_warm, "_measure_one_category", _measure)
    monkeypatch.setattr(tag_counts_warm.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(
        cache, "publish", lambda counts, rc=None: published.update(counts)
    )
    stamps = iter([({}, "s1"), ({}, "s2")])
    monkeypatch.setattr(cache, "read", lambda rc=None: next(stamps))

    result = await tag_counts_warm._warm_tag_counts()

    # First category is attempted (clock reads 0), then the budget is blown.
    assert result["budget_exhausted"] is True
    assert result["attempted"] < 3


def test_the_beat_is_wired_to_the_background_queue():
    """A measurement pass belongs on `background`, never on `realtime`."""
    from app.tasks import celery_app

    entry = celery_app.conf.beat_schedule["warm-tag-counts"]
    assert entry["task"] == "app.tasks.warm_tag_counts"
    assert entry["options"]["queue"] == "background"


def test_the_beat_never_fires_inside_the_settlement_sweep_window():
    """This beat must not add to the pile the settlement sweep runs under.

    The sweep holds its slot for its whole deadline, and
    `test_the_run_window_does_not_sit_under_a_growing_pile` caps the background
    crontab fires inside that window. The first draft of this beat derived a
    12-minute period, `*/12` fired at :36 — inside :31-:44 — and turned that
    guard red at `19 <= 18`. The remedy taken was to slow this beat to 15 rather
    than to raise a sibling's ceiling.

    Derived from the sweep's OWN schedule and deadline, never from a copy of
    :31 or 13, so this follows the sweep if it moves. Note the arithmetic
    constraint behind the fix: a p-periodic schedule has a fire inside ANY
    window of length >= p, so no period at or below the window length can pass
    this — which is why 15 is the fastest cadence available here, not a
    preference.
    """
    import math

    from app.tasks import celery_app, tag_counts_warm
    from app.tasks.settlement_sweep import SWEEP_DEADLINE_S

    # Keyed by the same name the sweep's own guard uses. Indexed, not `.get`:
    # a renamed beat must raise here, because a guard that quietly finds no
    # window would pass on everything.
    sweep = celery_app.conf.beat_schedule["settlement-capture-sweep-nightly"][
        "schedule"
    ]
    (sweep_minute,) = set(sweep.minute)
    span = math.ceil(SWEEP_DEADLINE_S / 60)
    window = {(sweep_minute + off) % 60 for off in range(span + 1)}

    period = tag_counts_warm.warm_period_minutes()
    fires = set(range(0, 60, period))

    assert not (fires & window), (
        f"warm-tag-counts fires at {sorted(fires & window)}, inside the "
        f"settlement sweep's :{sweep_minute:02d}+{span}m window. Slow the beat "
        "(a period <= the window length cannot avoid it) rather than raising "
        "SWEEP_WINDOW_COFIRE_CEILING."
    )


def test_the_measurer_passes_every_get_feed_parameter_explicitly():
    """An OMITTED route parameter arrives as the `Query(...)` object itself.

    That object is truthy and stringifies into the feed's cache key, so a
    parameter this task forgets does not raise — it quietly measures a
    different feed than the reader gets, and publishes the answer as truth.
    `_prewarm_feed_shape` carries the same warning in a comment; this asserts
    it, so `get_feed` GAINING a parameter reddens here instead of shipping a
    silently wrong count.
    """
    import ast
    import inspect

    from app.routes.feed import get_feed
    from app.tasks import tag_counts_warm

    expected = set(inspect.signature(get_feed).parameters)

    source = inspect.getsource(tag_counts_warm)
    passed: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "get_feed":
            passed = {kw.arg for kw in node.keywords if kw.arg}

    assert passed, "no get_feed(...) call found in tag_counts_warm"
    assert expected - passed == set(), (
        "these get_feed parameters are not passed explicitly and will arrive "
        f"as Query objects: {sorted(expected - passed)}"
    )
    assert (
        passed - expected == set()
    ), f"these arguments are not get_feed parameters: {sorted(passed - expected)}"
