"""LAT-P105 (#1459): the #1090 broaden pass must not score the candidate base twice.

## What this file is defending

A cold Discover build scored every candidate futures market **twice**. The route
ran ``_score_futures`` once under strict staleness windows and then — whenever the
post-filter pool came in under ``_THIN_FUTURES_POOL_FLOOR`` (100), which in an
off-season lull is every build — ran it a SECOND time under relaxed windows and
threw away every market the first pass had already returned.

Measured on production slug ``6010f4b4``, 2026-08-28, eight cold builds with eight
fresh principals (``x-feed-cache: miss`` 8/8): the second pass cost a median
**~383 ms of a median 1,594 ms cold build — 24 %**. It was invisible to every
instrument, because the broaden call passed no ``timing_records``; the number above
is ``futures`` minus the sum of its own ``futures.*`` sub-stages. One admin debug
trace pins it exactly: ``futures.caps`` ends at ``elapsed=1597.88`` and ``futures``
is recorded at ``elapsed=1943.81`` — **345.93 ms with no stage mark on it** —
against a predicted second-pass cost of ``scoring_loop 323.78 + canonical_counts
17.16 + interestingness_cache 10.97 = 351.91``.

``tests/test_feed_broaden_pass_reuse.py`` (Queue 305) removed that pass's
``market_load``. Its scoring loop was left in place. This file removes the loop.

## Why one pass can produce both pools

The two knobs the broaden pass varies — ``stale_no_movement_days`` and
``no_resolution_stale_days`` — reach exactly one decision in the whole scoring
path: the ``runtime_filters["eligible"]`` gate. They never touch a score. And the
relaxed pair is never tighter than the strict pair. So the strict pool is always a
SUBSET of the relaxed pool, and a loop gated on the relaxed thresholds can record,
per market and for three comparisons, whether the strict pair would also have
admitted it.

## What each fixture pins

1. **The identity gate.** Fused output == legacy two-pass output, item for item,
   in order, for both pools and for the merged list the route actually serves.
   Nothing else in this file may be read until this passes.
2. **The win is real.** The fused pass evaluates the runtime filter ``N`` times;
   the legacy path evaluates it ``2N``. That is the mechanism, asserted as a count
   rather than as a wall clock — a wall clock here would measure this machine.
3. **Relaxed is never tighter than strict**, over a sweep including the degenerate
   inputs. This is the premise the subset property rests on.
4. **``eligible_strict`` is absent unless asked for**, so no existing reader of the
   trace dict can come to depend on it by accident.
5. **Half a config is not a licence to widen.** ``broaden_config`` without
   ``capture_broadened`` (or the reverse) must return the plain strict pool.
6. **The kill switch and the route wiring**, including that the legacy path is
   still reachable — it is the rollback.
"""

from __future__ import annotations

import inspect
from datetime import timedelta

import pytest

import app.routes.feed as feed_mod
from app.routes.feed import (
    _broaden_relaxed_config,
    _dedupe_futures_by_canonical,
    _fused_broaden_enabled,
    _market_runtime_filter_trace,
    _score_futures,
    _THIN_FUTURES_POOL_FLOOR,
)
from app.utils.personalization import PersonalizationContext

# One fixture shape for both broaden-pass files, imported rather than copied: two
# copies of "what a market looks like" is how a guard drifts into agreeing with a
# defect it was written to catch.
from tests.test_feed_broaden_pass_reuse import (  # noqa: E402
    NOW,
    _base_hit,
    _CountingDB,
    _ids,
    _Market,
    _no_redis,
)

# The strict windows Discover actually serves under.
STRICT_CONFIG: dict[str, float | bool] = {
    "stale_no_movement_days": 2.0,
    "no_resolution_stale_days": 5.0,
}


def _markets_with_a_stale_tail() -> list[_Market]:
    """Four fresh markets and two whose staleness lands BETWEEN the two windows.

    ``updated_at = NOW - 4d`` with real 24h movement trips ``stale_movement_evidence``
    at the strict window (2 days) and clears it at the relaxed one (7 days). So the
    strict pool is 4 and the relaxed pool is 6 — the case where the two passes
    genuinely disagree, which is the only case where fusing them can go wrong.
    """
    fresh = [_Market(i) for i in (1, 2, 3, 4)]
    stale = []
    for market_id, name, category in (
        (5, "Who wins the Nobel Peace Prize?", "politics"),
        (6, "Will SpaceX fly Starship again this year?", "tech"),
    ):
        m = _Market(market_id)
        m.name = name
        m.category = category
        m.llm_sport_category = category
        m.updated_at = NOW - timedelta(days=4)
        stale.append(m)
    return fresh + stale


def _route_merge(primary: list[dict], broadened: list[dict]) -> list[dict]:
    """Exactly what ``get_feed`` does with the two pools, so identity is tested on
    the list a person is served rather than on an intermediate."""
    if len(primary) >= _THIN_FUTURES_POOL_FLOOR:
        return _dedupe_futures_by_canonical(list(primary))
    seen = {(it.get("data") or {}).get("id") for it in primary}
    added = [it for it in broadened if (it.get("data") or {}).get("id") not in seen]
    return _dedupe_futures_by_canonical(list(primary) + added)


async def _legacy_two_pass(monkeypatch, markets) -> tuple[list[dict], list[dict]]:
    """The path `FEED_FUSED_BROADEN_PASS=0` restores: score, then score again."""
    ctx = PersonalizationContext()
    relaxed = _broaden_relaxed_config(STRICT_CONFIG)
    with _no_redis():
        _base_hit(monkeypatch, [m.id for m in markets], set())
        db = _CountingDB(markets)
        capture: dict = {}
        primary = await _score_futures(
            db, NOW, None, ctx, config=dict(STRICT_CONFIG), capture_base=capture
        )
        broadened = await _score_futures(
            db, NOW, None, ctx, config=relaxed, preloaded_base=capture or None
        )
    return primary, broadened


async def _fused_one_pass(monkeypatch, markets) -> tuple[list[dict], list[dict]]:
    """The path this queue ships: one score, both pools."""
    ctx = PersonalizationContext()
    relaxed = _broaden_relaxed_config(STRICT_CONFIG)
    with _no_redis():
        _base_hit(monkeypatch, [m.id for m in markets], set())
        db = _CountingDB(markets)
        capture_broadened: dict = {}
        primary = await _score_futures(
            db,
            NOW,
            None,
            ctx,
            config=dict(STRICT_CONFIG),
            capture_base={},
            broaden_config=relaxed,
            capture_broadened=capture_broadened,
        )
    return primary, (capture_broadened.get("items") or [])


# ---------------------------------------------------------------------------
# 1. THE IDENTITY GATE — nothing else in this file counts until this passes.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_fixture_actually_makes_the_two_passes_disagree(monkeypatch):
    """A vacuous identity test is worse than none: it certifies the fixture.

    If the stale tail were also strict-eligible, both pools would be the same list
    and every equality below would hold no matter how badly the fusion was wired.
    """
    markets = _markets_with_a_stale_tail()
    primary, broadened = await _legacy_two_pass(monkeypatch, markets)
    # Output order is SCORE order (the caps sort), not candidate order, so
    # membership is asserted sorted and order is left to the identity tests.
    assert sorted(_ids(primary)) == [1, 2, 3, 4], (
        "the strict window must reject the 4-day-stale tail; got "
        f"{_ids(primary)} — the fixture no longer exercises the disagreement"
    )
    assert sorted(_ids(broadened)) == [1, 2, 3, 4, 5, 6], (
        f"the relaxed window must admit the whole base; got {_ids(broadened)}"
    )
    assert set(_ids(broadened)) - set(_ids(primary)) == {5, 6}, (
        "the two passes MUST disagree, or every identity assertion below is "
        "vacuous — it would hold however badly the fusion were wired"
    )


@pytest.mark.asyncio
async def test_fused_output_is_identical_to_the_two_pass_output(monkeypatch):
    """PRIMARY GATE. Both pools, item for item, in order."""
    markets = _markets_with_a_stale_tail()
    legacy_primary, legacy_broadened = await _legacy_two_pass(monkeypatch, markets)
    fused_primary, fused_broadened = await _fused_one_pass(monkeypatch, markets)

    assert _ids(fused_primary) == _ids(legacy_primary)
    assert _ids(fused_broadened) == _ids(legacy_broadened)
    assert fused_primary == legacy_primary, (
        "the strict pool must be byte-identical, not merely the same IDs — a score "
        "or reason that moved is a ranking change wearing a latency change's clothes"
    )
    assert fused_broadened == legacy_broadened


@pytest.mark.asyncio
async def test_the_merged_list_the_route_serves_is_identical(monkeypatch):
    """Identity on the list a person actually gets, after the route's own merge."""
    markets = _markets_with_a_stale_tail()
    legacy = _route_merge(*await _legacy_two_pass(monkeypatch, markets))
    fused = _route_merge(*await _fused_one_pass(monkeypatch, markets))
    assert _ids(fused) == _ids(legacy)
    assert sorted(_ids(fused)) == [1, 2, 3, 4, 5, 6]
    assert fused == legacy


@pytest.mark.asyncio
async def test_identity_holds_when_no_market_is_stale(monkeypatch):
    """The pools coincide; the fused path must not invent a difference."""
    markets = [_Market(i) for i in (1, 2, 3, 4)]
    legacy_primary, legacy_broadened = await _legacy_two_pass(monkeypatch, markets)
    fused_primary, fused_broadened = await _fused_one_pass(monkeypatch, markets)
    assert sorted(_ids(legacy_primary)) == sorted(_ids(legacy_broadened)) == [1, 2, 3, 4]
    assert fused_primary == legacy_primary
    assert fused_broadened == legacy_broadened


@pytest.mark.asyncio
async def test_identity_holds_when_every_market_is_stale(monkeypatch):
    """Strict pool empty, relaxed pool full — the shape #1090 exists for."""
    markets = _markets_with_a_stale_tail()
    for m in markets:
        m.updated_at = NOW - timedelta(days=4)
    legacy_primary, legacy_broadened = await _legacy_two_pass(monkeypatch, markets)
    fused_primary, fused_broadened = await _fused_one_pass(monkeypatch, markets)
    assert _ids(legacy_primary) == []
    assert sorted(_ids(legacy_broadened)) == [1, 2, 3, 4, 5, 6]
    assert fused_primary == legacy_primary
    assert fused_broadened == legacy_broadened
    assert sorted(_ids(_route_merge(fused_primary, fused_broadened))) == [1, 2, 3, 4, 5, 6]


# ---------------------------------------------------------------------------
# 2. THE WIN IS REAL — counted, not timed.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fused_evaluates_the_runtime_filter_once_per_market(monkeypatch):
    """The mechanism of the saving, as a count.

    The runtime filter is the per-market gate both passes ran. Legacy evaluates it
    once per market per pass; fused evaluates it once per market, full stop. A wall
    clock here would measure this laptop; a count measures the change.
    """
    markets = _markets_with_a_stale_tail()
    calls: list[int] = []
    real = feed_mod._market_runtime_filter_trace

    def _counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(feed_mod, "_market_runtime_filter_trace", _counting)

    calls.clear()
    await _legacy_two_pass(monkeypatch, markets)
    legacy_calls = len(calls)

    calls.clear()
    await _fused_one_pass(monkeypatch, markets)
    fused_calls = len(calls)

    assert legacy_calls == 2 * len(markets), (
        f"expected the legacy path to gate every market twice; got {legacy_calls} "
        f"for {len(markets)} markets"
    )
    assert fused_calls == len(markets), (
        f"the fused path must gate every market ONCE; got {fused_calls} for "
        f"{len(markets)} markets — the second pass is still running"
    )


# ---------------------------------------------------------------------------
# 3. THE PREMISE — relaxed is never tighter than strict.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "stale_days,nores_days",
    [
        (2.0, 5.0),  # the shipped defaults
        (0.0, 0.0),
        (1.0, 1.0),
        (7.0, 14.0),  # exactly at the floors
        (30.0, 60.0),  # above the floors, where the multipliers bind
        (-5.0, -5.0),  # degenerate, must still not invert
        (0.25, 0.5),
    ],
)
def test_relaxed_windows_are_never_tighter_than_strict(stale_days, nores_days):
    """The subset property rests on this and on nothing else."""
    strict = {
        "stale_no_movement_days": stale_days,
        "no_resolution_stale_days": nores_days,
    }
    relaxed = _broaden_relaxed_config(strict)
    assert relaxed["stale_no_movement_days"] >= stale_days
    assert relaxed["no_resolution_stale_days"] >= nores_days


def test_relaxed_config_does_not_mutate_or_drop_the_strict_config():
    strict = {
        "stale_no_movement_days": 2.0,
        "no_resolution_stale_days": 5.0,
        "interestingness_blend_weight_override": 0.4,
    }
    before = dict(strict)
    relaxed = _broaden_relaxed_config(strict)
    assert strict == before, "the caller's config must not be mutated"
    assert relaxed["interestingness_blend_weight_override"] == 0.4, (
        "every key except the two staleness windows must survive — the relaxed "
        "pass has to score under the SAME config in every other respect"
    )


def test_relaxed_config_of_none_is_the_defaults_relaxed():
    relaxed = _broaden_relaxed_config(None)
    assert relaxed["stale_no_movement_days"] == 7.0
    assert relaxed["no_resolution_stale_days"] == 14.0


# ---------------------------------------------------------------------------
# 4. THE SECOND VERDICT — present only when asked for, and correct.
# ---------------------------------------------------------------------------


def _trace(market, **kwargs):
    outcomes = [
        {
            "name": o.name,
            "probability": o.current_probability,
            "probability_change_24h": o.probability_change_24h,
            "opening_probability": o.opening_probability,
        }
        for o in market.outcomes
    ]
    return _market_runtime_filter_trace(
        market,
        outcomes,
        outcomes[0]["name"],
        outcomes[0]["probability"],
        NOW,
        sport_category=market.llm_sport_category,
        **kwargs,
    )


def test_eligible_strict_is_absent_unless_the_caller_asks():
    m = _Market(1)
    result = _trace(m, stale_no_movement_days=7, no_resolution_stale_days=14)
    assert "eligible_strict" not in result, (
        "an always-present key is a key someone starts reading; it must appear "
        "only for the caller that asked a second question"
    )


def test_eligible_strict_splits_a_market_the_two_windows_disagree_on():
    m = _Market(1)
    m.updated_at = NOW - timedelta(days=4)
    result = _trace(
        m,
        stale_no_movement_days=7,
        no_resolution_stale_days=14,
        strict_no_movement_days=2,
        strict_no_resolution_stale_days=5,
    )
    assert result["eligible"] is True
    assert result["eligible_strict"] is False


def test_eligible_strict_implies_eligible_on_a_fresh_market():
    m = _Market(1)
    result = _trace(
        m,
        stale_no_movement_days=7,
        no_resolution_stale_days=14,
        strict_no_movement_days=2,
        strict_no_resolution_stale_days=5,
    )
    assert result["eligible"] is True
    assert result["eligible_strict"] is True


def test_a_threshold_independent_blocker_fails_both_verdicts():
    """A market blocked for a reason the windows do not control must be blocked in
    BOTH pools — otherwise the broaden pass becomes a way to smuggle junk in."""
    m = _Market(1)
    m.resolution_date = NOW - timedelta(days=1)  # past_resolution_date
    result = _trace(
        m,
        stale_no_movement_days=7,
        no_resolution_stale_days=14,
        strict_no_movement_days=2,
        strict_no_resolution_stale_days=5,
    )
    assert result["eligible"] is False
    assert result["eligible_strict"] is False
    assert "past_resolution_date" in result["blockers"]


# ---------------------------------------------------------------------------
# 5. HALF A CONFIG IS NOT A LICENCE TO WIDEN.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_broaden_config_without_a_capture_does_not_widen_the_pool(monkeypatch):
    """Somewhere to put the relaxed pool is half the contract. Without it the call
    must behave exactly like a plain strict call — silently returning the RELAXED
    pool as if it were the strict one would put stale cards on the feed."""
    markets = _markets_with_a_stale_tail()
    ctx = PersonalizationContext()
    with _no_redis():
        _base_hit(monkeypatch, [m.id for m in markets], set())
        items = await _score_futures(
            _CountingDB(markets),
            NOW,
            None,
            ctx,
            config=dict(STRICT_CONFIG),
            broaden_config=_broaden_relaxed_config(STRICT_CONFIG),
        )
    assert sorted(_ids(items)) == [1, 2, 3, 4]


@pytest.mark.asyncio
async def test_capture_without_a_broaden_config_leaves_the_capture_empty(monkeypatch):
    markets = _markets_with_a_stale_tail()
    ctx = PersonalizationContext()
    capture: dict = {}
    with _no_redis():
        _base_hit(monkeypatch, [m.id for m in markets], set())
        items = await _score_futures(
            _CountingDB(markets),
            NOW,
            None,
            ctx,
            config=dict(STRICT_CONFIG),
            capture_broadened=capture,
        )
    assert sorted(_ids(items)) == [1, 2, 3, 4]
    assert capture == {}


# ---------------------------------------------------------------------------
# 6. THE SWITCH AND THE WIRING.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_fused_broaden_work_is_named_in_the_stage_timings(monkeypatch):
    """The pass this replaced carried NO stage mark, which is how ~383 ms hid
    inside ``futures`` across four cycles that were all reading that header. Its
    replacement must be nameable — and the key must exist ONLY on the fused path,
    so production can be asked whether the fusion is live rather than inferring it
    from a subtraction."""
    markets = _markets_with_a_stale_tail()
    ctx = PersonalizationContext()
    relaxed = _broaden_relaxed_config(STRICT_CONFIG)

    with _no_redis():
        _base_hit(monkeypatch, [m.id for m in markets], set())
        fused_timings: list[dict] = []
        await _score_futures(
            _CountingDB(markets),
            NOW,
            None,
            ctx,
            config=dict(STRICT_CONFIG),
            timing_records=fused_timings,
            timing_started_at=0.0,
            broaden_config=relaxed,
            capture_broadened={},
        )
        plain_timings: list[dict] = []
        await _score_futures(
            _CountingDB(markets),
            NOW,
            None,
            ctx,
            config=dict(STRICT_CONFIG),
            timing_records=plain_timings,
            timing_started_at=0.0,
        )

    fused_stages = [t["stage"] for t in fused_timings]
    plain_stages = [t["stage"] for t in plain_timings]
    assert "futures.broaden_finalize" in fused_stages, (
        f"the fused broaden work must carry its own stage name; got {fused_stages}"
    )
    assert "futures.broaden_finalize" not in plain_stages
    assert "futures.caps" in fused_stages and "futures.caps" in plain_stages, (
        "the existing caps mark must survive — a post-deploy read compares against "
        "it, and a renamed stage reads as a regression"
    )
    assert fused_stages.index("futures.caps") < fused_stages.index(
        "futures.broaden_finalize"
    ), "caps must still measure the STRICT pool's caps, as it always did"


def test_fusion_is_on_by_default(monkeypatch):
    monkeypatch.delenv("FEED_FUSED_BROADEN_PASS", raising=False)
    assert _fused_broaden_enabled() is True


@pytest.mark.parametrize("off", ["0", "false", "FALSE", "no", "off", " 0 "])
def test_the_kill_switch_turns_fusion_off_without_a_deploy(monkeypatch, off):
    monkeypatch.setenv("FEED_FUSED_BROADEN_PASS", off)
    assert _fused_broaden_enabled() is False


@pytest.mark.parametrize("on", ["1", "true", "yes", "on", "anything-else"])
def test_only_the_named_off_values_turn_fusion_off(monkeypatch, on):
    monkeypatch.setenv("FEED_FUSED_BROADEN_PASS", on)
    assert _fused_broaden_enabled() is True


def test_the_route_wires_the_fused_pass_behind_the_switch():
    """Source guard: the route must gate on the switch, hand the relaxed config to
    the primary pass, and read the broadened pool back out of the capture."""
    src = inspect.getsource(feed_mod.get_feed)
    assert "_fuse_broaden = _fused_broaden_enabled()" in src
    assert "broaden_config=(" in src and "_relaxed_config if _fuse_broaden else None" in src
    assert "capture_broadened=(" in src
    assert '_broaden_capture.get("items")' in src


def test_the_legacy_two_pass_path_is_still_reachable():
    """The rollback has to exist in the tree, not just in a config var. A switch
    whose off position runs deleted code is not a rollback."""
    src = inspect.getsource(feed_mod.get_feed)
    assert "if _fuse_broaden:" in src
    assert "else:" in src
    assert "preloaded_base=_primary_base_capture or None" in src, (
        "the legacy broaden pass, with Queue 305's market_load reuse, must survive"
    )
