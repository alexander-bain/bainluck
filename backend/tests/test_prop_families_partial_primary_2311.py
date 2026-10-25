"""#2311 — a partial build never replaces a FULL build in the 15-minute primary.

Seahawks, 2026-10-24: a refresh published a full Prop Races build at 09:41:51Z;
a second refresh lost both roster branches to the 12 s expiry and published a
partial at 09:44:58Z, three minutes into the full build's window. Readers lost
the Season Receiving Yards race and Shaheed's Next Team row. The 24h mirror was
already protected from exactly this (CERT-480); the primary was written
unconditionally.

The guards below pin both partial arms (timeout and deferral), the race the
compare-and-set closes, and the two directions that must NOT change: a partial
still fills an empty or partial primary (the rebuild loop stays closed), and a
full build still replaces anything.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.routes import prop_families as route
from app.utils import event_concept_cache as cache_mod
from tests.test_prop_families_partial_lat_p145 import _FakeRedis, _stored

TEAM_ID = 12
KEYS = route.prop_families_cache_keys(TEAM_ID, 400)


def _team():
    return SimpleNamespace(
        id=TEAM_ID, name="Seattle Seahawks", slug="seattle-seahawks",
        roster_players=[{"name": "Rashid Shaheed"}],
    )


def _fake_build(label: str, reasons: list[str]):
    """A build that returns one family and the given losses, nothing else."""

    async def _build(team, db, cap, budget_ms=None):
        payload = {
            "team": {"id": TEAM_ID, "name": "Seattle Seahawks", "slug": "seattle-seahawks"},
            "families": [{"family_key": label, "rows": []}],
            "total_families": 1,
        }
        for reason in reasons:
            cache_mod.note_build_loss(payload, reason, cache_mod.LOSS_PARTIAL)
        return payload, False

    return _build


TIMEOUT = ["branch_timeout:outcome_roster", "branch_timeout:market_roster"]
DEFERRED = ["branch_deferred:outcome_roster", "branch_deferred:market_roster"]


async def _publish(rc, label: str, reasons: list[str]):
    with patch.object(route, "build_prop_families", _fake_build(label, reasons)):
        return await route.build_and_cache_prop_families(_team(), None, 400, rc)


def _primary(rc):
    return _stored(rc, KEYS.primary)


def _quality(payload):
    return (payload or {}).get(cache_mod.ENVELOPE_FIELD, {}).get("quality")


def _family(payload):
    return payload["families"][0]["family_key"]


class _PrimaryRacingRedis(_FakeRedis):
    """Lands a COMPLETE build between the partial's primary read and its write.

    Injected once, at the primary GET itself, and the pre-race value is what the
    caller receives — the worst interleaving and the only one worth pinning.
    """

    def __init__(self, full_bytes):
        super().__init__()
        self._full_bytes = full_bytes
        self.raced = False

    def get(self, k):
        seen = super().get(k)
        if k == KEYS.primary and not self.raced:
            self.raced = True
            super().setex(k, route.PROP_FAMILIES_PRIMARY_TTL, self._full_bytes)
        return seen


class TestAPartialNeverReplacesAFullPrimary:
    async def test_the_seahawks_order_keeps_the_full_build(self):
        """Full at 09:41:51Z, timeout partial at 09:44:58Z: the full stays."""
        rc = _FakeRedis()
        await _publish(rc, "full_build", [])
        assert _quality(_primary(rc)) == cache_mod.QUALITY_FULL

        payload, degraded = await _publish(rc, "partial_build", TIMEOUT)

        assert _quality(_primary(rc)) == cache_mod.QUALITY_FULL
        assert _family(_primary(rc)) == "full_build"
        # The refresh task reads THIS to report its own terminal: its build fell
        # short, and declining the write must not turn that into a success.
        assert degraded is False
        assert _quality(payload) == cache_mod.QUALITY_PARTIAL

    async def test_a_deferred_partial_does_not_replace_it_either(self):
        rc = _FakeRedis()
        await _publish(rc, "full_build", [])
        await _publish(rc, "deferred_build", DEFERRED)
        assert _family(_primary(rc)) == "full_build"

    async def test_the_full_builds_ttl_is_not_extended(self):
        """Declining is a no-op on the slot: the full build keeps its own expiry,
        so the page still refreshes on the cadence the primary TTL promises."""
        rc = _FakeRedis()
        await _publish(rc, "full_build", [])
        writes_before = list(rc.writes)
        await _publish(rc, "partial_build", TIMEOUT)
        assert KEYS.primary not in rc.writes[len(writes_before):]

    async def test_the_mirror_is_untouched_too(self):
        rc = _FakeRedis()
        await _publish(rc, "full_build", [])
        await _publish(rc, "partial_build", TIMEOUT)
        assert _family(_stored(rc, KEYS.stale)) == "full_build"


class TestAFullLandingMidDecisionSurvives:
    async def test_a_full_landing_between_read_and_write_is_not_overwritten(self):
        rc = _PrimaryRacingRedis(cache_mod.encode_payload(
            cache_mod.stamp_envelope(
                {"team": {"id": TEAM_ID}, "families": [{"family_key": "raced_full", "rows": []}],
                 "total_families": 1},
                created_at=cache_mod._utcnow(),
                lifecycle_watermark=None,
                quality=cache_mod.QUALITY_FULL,
            )
        ))
        await _publish(rc, "partial_build", TIMEOUT)
        assert rc.raced is True, "the interleaving never happened — guard is vacuous"
        assert _family(_primary(rc)) == "raced_full"

    async def test_the_deferred_arm_is_guarded_the_same_way(self):
        rc = _PrimaryRacingRedis(cache_mod.encode_payload(
            cache_mod.stamp_envelope(
                {"team": {"id": TEAM_ID}, "families": [{"family_key": "raced_full", "rows": []}],
                 "total_families": 1},
                created_at=cache_mod._utcnow(),
                lifecycle_watermark=None,
                quality=cache_mod.QUALITY_FULL,
            )
        ))
        await _publish(rc, "deferred_build", DEFERRED)
        assert rc.raced is True
        assert _family(_primary(rc)) == "raced_full"


class TestWhatMustNotChange:
    async def test_a_partial_still_fills_an_empty_primary(self):
        """Never writing would bring back the twelve-second rebuild loop."""
        rc = _FakeRedis()
        await _publish(rc, "partial_build", TIMEOUT)
        assert _family(_primary(rc)) == "partial_build"
        assert rc.ttls[KEYS.primary] == route.PROP_FAMILIES_PRIMARY_TTL

    async def test_a_deferred_partial_still_fills_an_empty_primary(self):
        rc = _FakeRedis()
        await _publish(rc, "deferred_build", DEFERRED)
        assert _family(_primary(rc)) == "deferred_build"
        assert rc.store.get(KEYS.stale) is None, "a deferral never takes the mirror"

    async def test_a_newer_partial_still_replaces_an_older_partial(self):
        rc = _FakeRedis()
        await _publish(rc, "older_partial", TIMEOUT)
        await _publish(rc, "newer_partial", TIMEOUT)
        assert _family(_primary(rc)) == "newer_partial"

    async def test_a_full_build_still_replaces_a_partial(self):
        rc = _FakeRedis()
        await _publish(rc, "partial_build", TIMEOUT)
        await _publish(rc, "full_build", [])
        assert _family(_primary(rc)) == "full_build"
        assert _family(_stored(rc, KEYS.stale)) == "full_build"

    async def test_a_full_build_still_replaces_a_full_build(self):
        rc = _FakeRedis()
        await _publish(rc, "first_full", [])
        await _publish(rc, "second_full", [])
        assert _family(_primary(rc)) == "second_full"
