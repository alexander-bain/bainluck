"""SENTRY-R6 / queue 368 — the ops cache must expire on the BILLING BOUNDARY,
not only on its clock.

The defect, in one sentence: ``GET /api/admin/ops-snapshot`` holds a 5-minute
in-process cache, and the discard ceiling it carries
(``sentry_filter.ceiling_per_day``) is one cycle of declared need — so it STEPS
at ``BILLING_CYCLE_RESET_DAY``. Live enforcement re-derives on the boundary
(``discard_ceiling_reading`` memoises on the cycle, never on a clock); the cache
did not. For up to five minutes after every boundary the ops route exported the
PRE-boundary ceiling while the filter enforced the new one — the same
display-vs-enforcement split ``C-CERT-SENTRY-R4`` blocked on, one level up, and
with the same consequence: a band of discard rates the page calls a breach and
the enforcement does not.

The specimen is the Feb 21 boundary, because it is the one where the number
visibly moves: a 31-day cycle derives 4,657/day and the 28-day cycle that opens
next derives 4,206/day. Between them sits a 451/day band.

Note the Aug 21 boundary flips the cycle KEY while leaving the ceiling equal
(31 days on both sides). That is why the guard keys on the cycle identity rather
than on the ceiling value: the payload carries other cycle-derived facts
(``cycle_days``, the rate window), and a cache that only noticed when the
headline number happened to move would be right by luck.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.utils import sentry_budget


# The two sides of the boundary. Both are safely inside their cycle, so nothing
# here depends on the wall clock (gotcha #44 — the anchor carries its own dates).
BEFORE = datetime(2026, 2, 18, 12, 0, tzinfo=timezone.utc)   # cycle 2026-01-21, 31d
AFTER = datetime(2026, 2, 22, 12, 0, tzinfo=timezone.utc)    # cycle 2026-02-21, 28d


def _freeze(monkeypatch, when: datetime) -> None:
    """Freeze every ``now=None`` read in ``sentry_budget`` at ``when``.

    ``_utc`` is the single funnel every cycle-derived function passes through,
    so patching it is a whole frozen clock rather than a per-call override.
    """
    monkeypatch.setattr(
        sentry_budget, "_utc", lambda now: when if now is None else now
    )


class TestTheBoundaryActuallyMoves:
    """If these fail, the specimen below is vacuous — assert the premise first."""

    def test_cycle_identity_differs_across_the_boundary(self):
        assert sentry_budget.cycle_key(BEFORE) != sentry_budget.cycle_key(AFTER)

    def test_ceiling_differs_across_the_boundary(self):
        before = sentry_budget.discard_ceiling_per_day(BEFORE)
        after = sentry_budget.discard_ceiling_per_day(AFTER)
        assert before != after, (
            "the Feb 21 boundary must move the ceiling for this specimen to bite"
        )
        assert sentry_budget.cycle_length_days(BEFORE) == 31
        assert sentry_budget.cycle_length_days(AFTER) == 28


class TestDerivationCycleHelper:
    def test_reports_the_live_cycle(self, monkeypatch):
        import app.routes.admin as admin_mod

        _freeze(monkeypatch, BEFORE)
        assert admin_mod._ops_derivation_cycle() == sentry_budget.cycle_key(BEFORE)

    def test_underivable_cycle_is_none_not_a_guess(self, monkeypatch):
        """An unreadable cycle must be ``None`` — the fail-closed signal — and
        never a plausible-looking key. gotcha #53: an absence and a reading must
        not share a shape."""
        import app.routes.admin as admin_mod

        def _boom():
            raise RuntimeError("cycle unavailable")

        monkeypatch.setattr(sentry_budget, "cycle_key", _boom)
        assert admin_mod._ops_derivation_cycle() is None


def _install_cold_sources(monkeypatch):
    """Every warm source cold, admin auth bypassed. The snapshot still builds."""
    import app.routes.admin as admin_mod
    import app.tasks.redis_state as rs

    monkeypatch.setattr(admin_mod, "_check_admin_secret", lambda *a, **k: True)
    fake_redis = MagicMock()
    fake_redis.get.return_value = None
    fake_redis.llen.return_value = 0
    monkeypatch.setattr(rs, "get_redis_client", lambda *a, **k: fake_redis)
    monkeypatch.setattr(rs, "get_task_metrics", lambda label: {"health": "no_data"})
    monkeypatch.setattr(rs, "get_all_task_metrics", lambda: [])
    monkeypatch.setattr(rs, "get_odds_api_quota", lambda: {"status": "no_data"})
    admin_mod._OPS_SNAPSHOT_CACHE["at"] = 0.0
    admin_mod._OPS_SNAPSHOT_CACHE["data"] = None
    admin_mod._OPS_SNAPSHOT_CACHE["cycle"] = None
    return admin_mod


@pytest.mark.asyncio
async def test_boundary_flip_invalidates_the_cache_within_the_ttl(monkeypatch):
    """THE SPECIMEN. Warm the cache before the boundary, flip it, read the route
    again well inside the 5-minute TTL, and assert the reading is the NEW one.

    Before the fix this returned ``cache: hit`` carrying the 31-day ceiling.
    """
    admin_mod = _install_cold_sources(monkeypatch)

    _freeze(monkeypatch, BEFORE)
    first = await admin_mod.get_ops_snapshot(request=MagicMock(), secret="x", fresh=False)
    assert first.get("cache") != "hit"
    assert first["derivation_cycle"] == sentry_budget.cycle_key(BEFORE)
    ceiling_before = first["sentry_filter"]["ceiling_per_day"]
    assert ceiling_before == sentry_budget.discard_ceiling_per_day(BEFORE)

    # Same process, same in-process cache, seconds later — but a new cycle.
    _freeze(monkeypatch, AFTER)
    second = await admin_mod.get_ops_snapshot(request=MagicMock(), secret="x", fresh=False)

    assert second.get("cache") != "hit", (
        "a cache keyed only on age serves the pre-boundary ceiling for 5 minutes"
    )
    assert second["derivation_cycle"] == sentry_budget.cycle_key(AFTER)
    assert second["sentry_filter"]["ceiling_per_day"] == (
        sentry_budget.discard_ceiling_per_day(AFTER)
    )
    assert second["sentry_filter"]["ceiling_per_day"] != ceiling_before


@pytest.mark.asyncio
async def test_cache_still_serves_within_one_cycle(monkeypatch):
    """The fix must not defeat the cache — inside one cycle it still hits.

    Both directions, per the standing rule for a cap or a guard: the stale read
    is refused AND the surface it protects stays populated.
    """
    admin_mod = _install_cold_sources(monkeypatch)

    _freeze(monkeypatch, BEFORE)
    first = await admin_mod.get_ops_snapshot(request=MagicMock(), secret="x", fresh=False)
    assert first.get("cache") != "hit"

    second = await admin_mod.get_ops_snapshot(request=MagicMock(), secret="x", fresh=False)
    assert second["cache"] == "hit"
    assert second["derivation_cycle"] == sentry_budget.cycle_key(BEFORE)
    assert second["cache_ttl_s"] == admin_mod._OPS_SNAPSHOT_TTL
    assert second["sentry_filter"]["ceiling_per_day"] == (
        first["sentry_filter"]["ceiling_per_day"]
    )


@pytest.mark.asyncio
async def test_underivable_cycle_fails_closed_to_recompute(monkeypatch):
    """When the cycle cannot be established, serve nothing from cache.

    Latency is the cost of being wrong this way. The other way costs a wrong
    number wearing a fresh timestamp, which is what this whole guard is about.
    """
    admin_mod = _install_cold_sources(monkeypatch)

    _freeze(monkeypatch, BEFORE)
    first = await admin_mod.get_ops_snapshot(request=MagicMock(), secret="x", fresh=False)
    assert first.get("cache") != "hit"

    monkeypatch.setattr(admin_mod, "_ops_derivation_cycle", lambda: None)
    second = await admin_mod.get_ops_snapshot(request=MagicMock(), secret="x", fresh=False)
    assert second.get("cache") != "hit"
    assert second["derivation_cycle"] is None


@pytest.mark.asyncio
async def test_fresh_true_still_bypasses(monkeypatch):
    admin_mod = _install_cold_sources(monkeypatch)

    _freeze(monkeypatch, BEFORE)
    await admin_mod.get_ops_snapshot(request=MagicMock(), secret="x", fresh=False)
    forced = await admin_mod.get_ops_snapshot(request=MagicMock(), secret="x", fresh=True)
    assert forced.get("cache") != "hit"
    assert forced["derivation_cycle"] == sentry_budget.cycle_key(BEFORE)
