"""#2907: the StatPal paths the venue does not publish stay retired.

`app/tasks/statpal_sync.py` called three StatPal endpoints that 404 on every
sport we sync, and `app/services/statpal_api.py` carried six accessors for
them. `_get` turns a 404 into `None` and every one of those accessors turned
`None` into `[]` — which is also what "this team has no injured players" and
"no plays yet" look like. That is gotcha #53, and it is why the whole surface
was DELETED rather than retried: there is no value to read.

Measured 2026-09-09 before the deletion, and it is the reason the guard exists
rather than a tidiness argument:

* `scoring_plays` held **0 rows, lifetime, from every source**;
* **0 of 52,346** events with `win_probability_sources` carried `statpal_plays`
  (89 carried `statpal_injuries` — the working sibling, and the positive control
  that proves the census predicate can see a populated key at all);
* `statpal_plays` nonetheless reported **632 successes / 0 failures in 24h**,
  every 60 seconds, on the `realtime` queue.

Two independent venue reads agree that this is path-level and permanent, not an
outage (notice 26): the vendor's compiled OpenAPI spec publishes 54 paths and
none of them is a teams/roster/team-stats/player-stats/per-fixture-playbyplay
path for any sport, and a keyed live probe 404s on every retired path while
`/v1/nba/standings`, `/v1/nfl/live-plays` and `/v2/soccer/injuries-suspensions`
answer 200 from the same shell.

The guards below are deliberately NOT source scans. A scan for the string
``get_teams`` would match this very file's prose, and — worse — would match the
ESPN and MLB clients, which both have a legitimate `get_teams` of their own that
must keep working. Everything here is asserted against live objects instead.
"""

import pytest


# --- 1. The retired accessors do not come back -------------------------------

#: Deleted from `StatPalAPIService` by authority/083. Each called a path the
#: venue does not publish. Named here so re-adding one is a red test and not a
#: silent 404 loop.
RETIRED_ACCESSORS = (
    "get_teams",
    "get_roster",
    "get_team_stats",
    "get_player_stats",
    "get_game_detail",
    "get_play_by_play",
)

#: Deleted alongside them: their return types had no other consumer.
RETIRED_MODELS = (
    "StatPalTeam",
    "StatPalPlayer",
    "StatPalPlayEvent",
    "StatPalGameDetail",
)


@pytest.mark.parametrize("name", RETIRED_ACCESSORS)
def test_retired_accessor_is_absent_from_the_statpal_client(name):
    """The StatPal client no longer offers a method for an unpublished path.

    Asserted on the CLASS, not on the source text: `get_teams` is also an ESPN
    and an MLB method, and both are live. A grep-based guard would either flag
    those or flag this file's own prose.
    """
    from app.services.statpal_api import StatPalAPIService

    assert not hasattr(StatPalAPIService, name), (
        f"StatPalAPIService.{name} is back. The venue does not publish the path "
        f"it calls (see RETIRED_VENUE_PATHS in app/services/statpal_api.py); "
        f"`_get` will return None and the caller will read it as an empty "
        f"result. If the venue has started publishing it, re-measure and update "
        f"that record in the same change."
    )


@pytest.mark.parametrize("name", RETIRED_MODELS)
def test_retired_model_is_absent(name):
    # `from app.services import ...` and not `import app.services.statpal_api`:
    # importing the same module both ways in one file is CodeQL
    # `py/import-and-import-from` (a note, not a security finding, but avoidable).
    from app.services import statpal_api

    assert not hasattr(statpal_api, name), (
        f"{name} is back in statpal_api. It only ever carried the output of a "
        f"retired accessor."
    )


def test_the_live_accessors_survived():
    """The control. A guard that only asserts absence passes on an empty module.

    Without this, deleting `statpal_api.py` outright would make every assertion
    above pass.
    """
    from app.services.statpal_api import StatPalAPIService

    for name in ("get_injuries", "get_injuries_result", "get_standings", "_get"):
        assert hasattr(StatPalAPIService, name), f"{name} should NOT have been retired"


# --- 2. The retired beats do not come back -----------------------------------

RETIRED_BEATS = (
    "sync-statpal-live-plays",
    "sync-statpal-rosters-daily",
    "sync-statpal-team-stats-weekly",
)

RETIRED_TASK_NAMES = (
    "app.tasks.sync_statpal_live_plays",
    "app.tasks.sync_statpal_rosters",
    "app.tasks.sync_statpal_team_stats",
)


@pytest.mark.parametrize("beat", RETIRED_BEATS)
def test_retired_beat_is_absent_from_the_schedule(beat):
    from app.tasks import celery_app

    assert beat not in celery_app.conf.beat_schedule, (
        f"{beat} is scheduled again. It cannot do anything: the endpoint behind "
        f"it is not published by the venue."
    )


@pytest.mark.parametrize("task_name", RETIRED_TASK_NAMES)
def test_retired_task_is_not_registered(task_name):
    from app.tasks import celery_app

    assert task_name not in celery_app.tasks, f"{task_name} is registered again"


def test_the_live_statpal_beats_survived():
    """Control for the two beat guards above, same reason as the accessor one."""
    from app.tasks import celery_app

    for beat in (
        "sync-statpal-livescores",
        "sync-statpal-standings-daily",
        "sync-statpal-injuries",
    ):
        assert beat in celery_app.conf.beat_schedule, (
            f"{beat} should NOT have been retired — it reads a path the venue "
            f"does publish"
        )


# --- 3. The CLASS guard: a 404 must never read as an empty result ------------
#
# This is the defect itself, not its symptom, and it is asserted on the reader
# that SURVIVED — `get_injuries_result`. It is the shape every retired accessor
# got wrong, so a future accessor written in the old shape has a red test
# waiting for it.


class _FakeStatPal:
    """A StatPal client whose `_get` behaves the way a 404 makes it behave."""

    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    async def _get(self, sport, endpoint, params=None):
        self.calls.append((sport, endpoint))
        return self._payload


@pytest.mark.asyncio
async def test_a_404_is_reported_as_a_failed_read_not_as_an_empty_roster():
    """`_get` returning None is a failure to READ. It is never "nobody is hurt"."""
    from app.services.statpal_api import StatPalAPIService

    client = _FakeStatPal(payload=None)  # what a 404 produces
    result = await StatPalAPIService.get_injuries_result(client, "soccer")

    assert result.injuries == []
    assert result.reason == "fetch_failed", (
        "a 404 collapsed into the same summary as a quiet day — this is the "
        "#2907 defect, one endpoint over"
    )
    assert result.is_alarm is True


@pytest.mark.asyncio
async def test_a_genuinely_empty_payload_is_not_an_alarm():
    """The other direction. Without this the guard passes on `reason` always
    being `fetch_failed`, which would be a different lie."""
    from app.services.statpal_api import StatPalAPIService

    # The canonical empty envelope: nobody sidelined in any league. NOT `{}` and
    # not `{"injuries": []}` — those are unrecognised bodies and are correctly
    # `fetch_failed`, because `empty` is an instruction to clear stored players.
    client = _FakeStatPal(payload={"injuries_suspensions": {"league": []}})
    result = await StatPalAPIService.get_injuries_result(client, "soccer")

    assert result.injuries == []
    assert result.reason == "empty"
    assert result.is_alarm is False


@pytest.mark.asyncio
async def test_a_sport_with_no_published_injury_path_is_not_an_alarm_either():
    """Three outcomes, three reasons. "The venue serves no injury product for
    the NFL" is a fact about the venue, not a failed run — and it must not be
    confused with either of the two above."""
    from app.services.statpal_api import StatPalAPIService

    client = _FakeStatPal(payload=None)
    result = await StatPalAPIService.get_injuries_result(client, "nfl")

    assert result.reason == "no_venue_path"
    assert result.is_alarm is False
    assert client.calls == [], "no request should be made for an unpublished path"
