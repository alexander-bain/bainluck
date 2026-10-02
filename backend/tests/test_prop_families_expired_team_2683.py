"""Guards for #2683: a team page's props section 500s after a budgeted rollback.

WHAT PRODUCTION SHOWED. Sentry BAINLUCK-1FC, 20 events in the 24 h to
2026-10-02 (latest `GET /api/teams/atlanta-braves/prop-families`, 10:41Z):
`MissingGreenlet` raised from `build_and_cache_prop_families` reading
`team.id` to compute its cache keys. ux had read the same 500 at ~2.9 s on the
Red Sox and Yankees pages, whose team page then rendered without its props.

WHY. The cold build is budgeted (LAT-P164). A branch that times out rolls the
session back, and a rollback expires every ORM object in it — `team` included
(gotcha #6). `build_prop_families` copies its own scalars before the first
branch for exactly this reason, but its caller and the route read `team.id`
AFTER the build, which is a lazy load inside an async session.

Every existing prop-families guard hands the route a `SimpleNamespace` team,
which never expires — which is why none of them could see this. The double
here is a team whose `id` raises the driver's real error once the build has
"rolled back", so a post-build read fails the test the way it fails in
production.
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import MissingGreenlet

from app.routes import prop_families as route
from app.utils.event_concept_cache import (
    LOSS_DEGRADED,
    LOSS_PARTIAL,
    note_build_loss,
)


class _ExpiringTeam:
    """A Team whose attributes lazy-load (and therefore raise) once expired."""

    def __init__(self, team_id: int = 4242, name: str = "Atlanta Braves"):
        self._id = team_id
        self._name = name
        self.expired = False

    def _read(self, value):
        if self.expired:
            raise MissingGreenlet(
                "greenlet_spawn has not been called; can't call await_only() here."
            )
        return value

    @property
    def id(self):
        return self._read(self._id)

    @property
    def name(self):
        return self._read(self._name)


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, bytes] = {}

    def get(self, k):
        return self.store.get(k)

    def set(self, k, v, nx=False, ex=None):
        if nx and k in self.store:
            return None
        self.store[k] = v.encode() if isinstance(v, str) else v
        return True

    def setex(self, k, ttl, v):
        self.store[k] = v.encode() if isinstance(v, str) else v

    def delete(self, k):
        return int(self.store.pop(k, None) is not None)

    def eval(self, script, numkeys, *args):
        # Every guarded write in this module publishes only onto an absent or
        # unchanged key; a fresh fake has neither, so "absent" is the case.
        key, value = args[0], args[-1]
        if key in self.store:
            return 0
        self.store[key] = value.encode() if isinstance(value, str) else value
        return 1


def _rolling_back_build(team, *, families: list, loss: tuple[str, str] | None,
                        unusable: bool = False):
    """A `build_prop_families` that ends the way a timed-out branch does: the
    session rolled back, so the caller's `team` is expired on return."""

    async def _build(t, db, cap, budget_ms=None):
        assert t is team
        payload = {
            "team": {"id": team._id, "name": team._name, "slug": None},
            "families": families,
            "total_families": len(families),
        }
        if loss is not None:
            note_build_loss(payload, *loss)
        team.expired = True
        return payload, unusable

    return _build


_FAMILY = {"family_key": "mvp", "label": "MVP", "rows": [{"name": "Acuña"}]}


class TestBuildAndCacheDoesNotReadTheExpiredTeam:
    @pytest.mark.parametrize(
        "families,loss",
        [
            pytest.param([_FAMILY], None, id="full"),
            pytest.param([_FAMILY], ("branch_timeout:outcome_name", LOSS_PARTIAL),
                         id="timeout-partial-with-rows"),
            pytest.param([], ("branch_timeout:outcome_name", LOSS_PARTIAL),
                         id="timeout-partial-empty"),
            pytest.param([_FAMILY], ("branch_deferred:outcome_roster", LOSS_PARTIAL),
                         id="deferred-partial"),
        ],
    )
    async def test_every_outcome_survives_a_rollback(self, families, loss):
        team = _ExpiringTeam()
        rc = _FakeRedis()
        with patch.object(route, "build_prop_families",
                          _rolling_back_build(team, families=families, loss=loss)):
            payload, _degraded = await route.build_and_cache_prop_families(
                team, MagicMock(), 400, rc
            )
        assert payload["families"] == families

    async def test_the_cache_key_is_the_teams_own_id(self):
        """Strawman guard: the copied id must be THE team's id, not a default.
        A fix that sidestepped the read with a constant would pass the test above
        and write every team into one key."""
        team = _ExpiringTeam(team_id=4242)
        rc = _FakeRedis()
        with patch.object(route, "build_prop_families",
                          _rolling_back_build(team, families=[_FAMILY], loss=None)):
            await route.build_and_cache_prop_families(team, MagicMock(), 400, rc)
        keys = route.prop_families_cache_keys(4242, route._resolve_cap(400))
        assert keys.primary in rc.store


class TestTheRouteServesAfterARollback:
    async def _get(self, team, build):
        rc = _FakeRedis()
        scheduled = MagicMock()
        with patch.object(route, "resolve_team", return_value=team), \
             patch.object(route, "get_client", return_value=rc), \
             patch.object(route, "_schedule_refresh", scheduled), \
             patch.object(route, "build_prop_families", build):
            body = await route.get_team_prop_families("atlanta-braves", 400, MagicMock())
        return body, scheduled

    async def test_a_deferred_cold_build_returns_the_section_and_schedules_by_id(self):
        team = _ExpiringTeam(team_id=4242)
        body, scheduled = await self._get(
            team,
            _rolling_back_build(team, families=[_FAMILY],
                                loss=("branch_deferred:outcome_roster", LOSS_PARTIAL)),
        )
        assert body["families"] == [_FAMILY]
        assert scheduled.call_count == 1
        assert scheduled.call_args.args[2] == 4242

    async def test_a_build_that_lost_everything_still_serves(self):
        """The degraded arm logs the team id before returning — the last
        post-build read on the route."""
        team = _ExpiringTeam(team_id=4242)
        body, _ = await self._get(
            team,
            _rolling_back_build(team, families=[],
                                loss=("branch_timeout:team_id", LOSS_DEGRADED),
                                unusable=True),
        )
        assert body["families"] == []

    def test_the_double_really_raises_once_expired(self):
        """Without this the suite is vacuous: a double that never raised would
        pass against the pre-fix code too."""
        team = _ExpiringTeam()
        assert team.id == 4242
        team.expired = True
        with pytest.raises(MissingGreenlet):
            team.id
