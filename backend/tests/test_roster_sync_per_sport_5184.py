"""#5184 — the daily roster sync must be able to finish, and keep what it reached.

`sync_rosters` used to run all eight sports in ONE task and ONE transaction:
~536 ESPN team fetches at ~1s each (0.5s client delay + a 0.3s loop sleep +
the request) against a 270s soft time limit. It timed out every day and the
rollback discarded every roster it had fetched — the stored Cowboys roster
predated the 2026 draft, 193 of 207 college-football teams had none, and
Jeremiah Smith's Heisman legs could never link to Ohio State.

Two guards, one per half of the fix:
1. the beat schedules one run PER SPORT, covering ROSTER_SPORTS exactly, and
   never an all-sports run;
2. `_sync_espn_rosters` commits after each team, so a run cut short by its
   time limit keeps every team it already wrote.
"""

import pytest


def _roster_beats():
    from app.tasks import celery_app

    return {
        name: entry
        for name, entry in celery_app.conf.beat_schedule.items()
        if entry.get("task") == "app.tasks.sync_rosters"
    }


def test_every_roster_sport_has_its_own_beat_run():
    from app.tasks.roster_sync import ROSTER_SPORTS

    sports = [(e.get("kwargs") or {}).get("sport_key") for e in _roster_beats().values()]
    assert sorted(s for s in sports if s) == sorted(ROSTER_SPORTS)


def test_no_beat_run_syncs_every_sport_at_once():
    for name, entry in _roster_beats().items():
        assert (entry.get("kwargs") or {}).get("sport_key"), (
            f"{name} runs sync_rosters with no sport_key — the all-sports run "
            "cannot finish inside the task's time limit (#5184)"
        )


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _Team:
    def __init__(self, tid, espn_id, name):
        self.id = tid
        self.espn_id = espn_id
        self.name = name


class _Session:
    """Answers the two SELECTs, then logs every write and commit in order."""

    def __init__(self, teams):
        self._answers = [_Result(teams), _Result(teams)]
        self.log: list[str] = []

    async def execute(self, stmt, *args, **kwargs):
        if self._answers:
            return self._answers.pop(0)
        self.log.append("write")
        return _Result([])

    async def commit(self):
        self.log.append("commit")


class _TimeLimit(Exception):
    """Stands in for celery's SoftTimeLimitExceeded, raised mid-run."""


@pytest.mark.asyncio
async def test_a_run_cut_short_has_committed_every_team_it_wrote(monkeypatch):
    from app.models.models import Team
    from app.tasks import roster_sync

    rosters = {
        "1": [{"name": "Jeremiah Smith", "position": "WR"}],
        "2": [],  # ESPN answered "no players" — also a write, also committed
        "3": [{"name": "Caleb Downs", "position": "S"}],
    }

    class _ESPN:
        async def get_team_roster(self, sport_key, team_id):
            if team_id == "4":
                raise _TimeLimit()
            return rosters[team_id]

    monkeypatch.setattr("app.services.espn_api.get_espn_service", lambda: _ESPN())

    session = _Session([_Team(10 + i, str(i), f"T{i}") for i in (1, 2, 3, 4)])
    with pytest.raises(_TimeLimit):
        await roster_sync._sync_espn_rosters(
            session, Team, 1, "americanfootball_ncaaf"
        )

    # Each of the three writes is followed by its own commit before the next
    # team is fetched; the rollback of the interrupted run loses nothing.
    assert session.log == ["write", "commit"] * 3
