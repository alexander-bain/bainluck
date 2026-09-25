"""A backfilled ESPN win-probability point is drawn when its play happened. #8514.

WHAT A READER SAW. On `/events/15318166` (Mets @ Rangers, Final 3–1, first pitch
18:35Z, `completed_at` 21:08:18Z) ESPN's line trailed Kalshi, Polymarket and MLB
by 15–40 minutes and the payload carried nine ESPN readings AFTER the final at
Rangers 84–91%. `_backfill_espn_win_probability` spread ESPN's points evenly from
first pitch to the earlier of "first pitch + 3.5 h" and "now"; the backfill ran
~21:35Z, so a 153-minute game was drawn over 180 minutes. The rows carried
`backfilled: true`, which neither the retention collapse (it checks `backfill`)
nor the 7878.v1 evidence contract read, so they counted as observed coverage.

THE FIX, IN FOUR PLACES, EACH GUARDED HERE:

* `ESPNAPIService.get_win_probability` joins each point's `playId` to the play's
  `wallclock` in the same `/summary` payload;
* the backfill stores a point at that instant with `time_basis =
  "play_wallclock"`, or not at all, and never stores one instant twice;
* a newest-first run re-reads recent games that hold only the old estimates, in
  an arm of its own so the permanently full first arm cannot starve it;
* the served history calls those rows `play_history` / `estimated_time` (drawn,
  never evidence), and drops the estimates from a series that has evidenced rows.

`tests/fixtures/espn_play_wallclocks_8514.json` is ESPN's own `/summary` for the
specimen (MLB 401817067) and one NFL game, trimmed to `winprobability` plus the
`id`/`wallclock` of the plays it names — captured 2026-09-25, not hand-written.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from app.services.espn_api import ESPNAPIService, _play_wallclocks
from app.tasks import espn_sync
from app.utils.winprob_evidence import (
    ESTIMATED_BASIS,
    PLAY_WALLCLOCK_BASIS,
    drop_superseded_estimates,
    espn_wp_backfill_basis,
    served_evidence,
)

FIXTURE = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "espn_play_wallclocks_8514.json").read_text()
)
MLB = FIXTURE["mlb"]
NFL = FIXTURE["nfl"]

UTC = timezone.utc
FIRST_PITCH = datetime.fromisoformat(MLB["commence_time"])
COMPLETED_AT = datetime.fromisoformat(MLB["completed_at"])
#: When the specimen's backfill evidently ran (the issue: ~27 min after the final).
BACKFILL_RAN = datetime(2026, 9, 24, 21, 35, tzinfo=UTC)


def _mlb_summary():
    return {"winprobability": MLB["winprobability"], "plays": MLB["plays"]}


def _nfl_summary():
    return {"winprobability": NFL["winprobability"], "drives": NFL["drives"]}


async def _parse(payload, sport_key):
    client = ESPNAPIService()

    async def _fake_get(url):
        assert "summary?event=" in url
        return payload

    client._get = _fake_get
    try:
        return await client.get_win_probability(sport_key, "401817067")
    finally:
        await client.close()


# ── The join ────────────────────────────────────────────────────────────────


class TestTheJoin:
    async def test_every_specimen_point_carries_its_plays_wallclock(self):
        series = await _parse(_mlb_summary(), "baseball_mlb")

        assert len(series) == 64
        stamps = [p["wallclock"] for p in series]
        assert all(isinstance(s, datetime) and s.tzinfo is not None for s in stamps)
        assert stamps[0] == datetime(2026, 9, 24, 18, 39, 39, tzinfo=UTC)
        assert stamps[-1] == datetime(2026, 9, 24, 21, 6, 11, tzinfo=UTC)
        assert stamps == sorted(stamps)
        assert all(FIRST_PITCH <= s <= COMPLETED_AT for s in stamps)

    async def test_the_join_is_by_play_id_not_by_position(self):
        """The fixture lists five plays no point names FIRST, so a zip would
        stamp every point with the wrong play; reversing the list must not
        change a single stamp either."""
        forward = await _parse(_mlb_summary(), "baseball_mlb")
        payload = _mlb_summary()
        payload["plays"] = list(reversed(payload["plays"]))
        backward = await _parse(payload, "baseball_mlb")

        assert [p["wallclock"] for p in forward] == [p["wallclock"] for p in backward]
        by_id = {p["id"]: p["wallclock"] for p in MLB["plays"]}
        for point in forward:
            expected = datetime.fromisoformat(by_id[point["play_id"]].replace("Z", "+00:00"))
            assert point["wallclock"] == expected

    async def test_football_plays_nested_under_drives_are_joined(self):
        series = await _parse(_nfl_summary(), "americanfootball_nfl")

        assert len(series) == 185
        joined = [p for p in series if p["wallclock"] is not None]
        assert len(joined) == 184
        # The one ESPN point that names no listed play has no evidenced time.
        assert [p["play_id"] for p in series if p["wallclock"] is None] == ["4018729481"]

    def test_a_play_without_a_parseable_wallclock_is_left_out(self):
        out = _play_wallclocks({"plays": [
            {"id": "a", "wallclock": "2026-09-24T18:39:39Z"},
            {"id": "b", "wallclock": "not a time"},
            {"id": "c"},
            {"id": None, "wallclock": "2026-09-24T18:40:00Z"},
            "not a play",
        ]})
        assert out == {"a": datetime(2026, 9, 24, 18, 39, 39, tzinfo=UTC)}


# ── The stamp ───────────────────────────────────────────────────────────────


class TestTheStamp:
    def test_the_wallclock_is_the_stamp(self):
        at = datetime(2026, 9, 24, 20, 0, tzinfo=UTC)
        assert espn_sync._wp_backfill_evidenced_time({"wallclock": at}, BACKFILL_RAN) == at

    def test_no_wallclock_is_no_stamp(self):
        assert espn_sync._wp_backfill_evidenced_time({"wallclock": None}, BACKFILL_RAN) is None
        assert espn_sync._wp_backfill_evidenced_time({}, BACKFILL_RAN) is None

    def test_a_wallclock_in_the_future_is_no_stamp(self):
        later = BACKFILL_RAN + timedelta(seconds=1)
        assert espn_sync._wp_backfill_evidenced_time({"wallclock": later}, BACKFILL_RAN) is None

    def test_the_old_spread_put_specimen_points_after_the_final(self):
        """The strawman the fixture must be able to tell apart: the pre-#8514
        stamping, fed the specimen's shape, lands points after `completed_at`.
        If this stopped holding, the specimen assertions below would prove
        nothing about the defect."""
        total = len(MLB["winprobability"])
        spread = [
            espn_sync._wp_backfill_snap_time(FIRST_PITCH, i, total, "baseball_mlb", BACKFILL_RAN)
            for i in range(total)
        ]
        assert sum(1 for t in spread if t > COMPLETED_AT) >= 9


# ── The task, end to end through the real parser ────────────────────────────


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)


class _Session:
    """Answers the task's reads from canned rows and records every insert."""

    def __init__(self, first_arm, reread_arm, stored=None):
        self.first_arm = first_arm
        self.reread_arm = reread_arm
        self.stored = stored or {}
        self.selects = []
        self.inserts = []
        self.commits = 0

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if sql.lstrip().upper().startswith("INSERT"):
            self.inserts.append(stmt.compile(dialect=postgresql.dialect()).params)
            return _Result([])
        self.selects.append((sql, params))
        if "SELECT captured_at FROM win_prob_snapshots" in sql:
            return _Result([(t,) for t in self.stored.get(params["e"], [])])
        if "has_estimate" in sql:
            return _Result(self.reread_arm)
        return _Result(self.first_arm)

    async def commit(self):
        self.commits += 1


def _row(event_id, espn_id="401817067", sport_key="baseball_mlb", n=0):
    return SimpleNamespace(
        id=event_id, espn_id=espn_id, commence_time=FIRST_PITCH,
        sport_key=sport_key, espn_snap_count=n,
    )


@pytest.fixture
def run_task(monkeypatch):
    """Run the real task against `_Session`, with ESPN answering from the fixture
    through the real `get_win_probability` parser."""
    payloads = {"401817067": _mlb_summary(), "401872948": _nfl_summary()}
    fetched = []

    class _Service(ESPNAPIService):
        async def _get(self, url):
            espn_id = url.rsplit("=", 1)[1]
            fetched.append(espn_id)
            return payloads[espn_id]

    async def _no_sleep(_):
        return None

    monkeypatch.setattr("app.services.espn_api.ESPNAPIService", _Service)
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)

    async def _run(session, **kw):
        @asynccontextmanager
        async def _session_cm():
            yield session

        monkeypatch.setattr(espn_sync, "get_task_session", _session_cm)
        stats = await espn_sync._backfill_espn_win_probability(**kw)
        return stats, fetched

    return _run


def _stamps(session, event_id=None):
    return [
        p["captured_at"] for p in session.inserts
        if event_id is None or p["event_id"] == event_id
    ]


class TestTheBackfill:
    async def test_the_specimen_is_stored_at_its_play_times(self, run_task):
        session = _Session(first_arm=[], reread_arm=[_row(MLB["event_id"], n=51)])
        stats, _ = await run_task(session)

        expected = sorted({
            datetime.fromisoformat(p["wallclock"].replace("Z", "+00:00"))
            for p in MLB["plays"]
            if p["id"] in {w["playId"] for w in MLB["winprobability"]}
        })
        stamps = _stamps(session)
        assert sorted(stamps) == expected
        assert len(stamps) == len(set(stamps))
        # The reader's claim: nothing after the final, nothing before first pitch.
        assert max(stamps) <= COMPLETED_AT
        assert min(stamps) >= FIRST_PITCH
        assert stats["restamp_candidates"] == 1
        assert stats["snapshots_created"] == len(expected)

    async def test_each_row_says_how_it_got_its_time(self, run_task):
        session = _Session(first_arm=[_row(MLB["event_id"], n=2)], reread_arm=[])
        await run_task(session)

        assert session.inserts
        for p in session.inserts:
            state = p["game_state"]
            assert state["backfilled"] is True
            assert state["time_basis"] == PLAY_WALLCLOCK_BASIS
            assert "seconds_left" in state
            assert state["play_id"]
            assert p["source"] == "espn"
            assert espn_wp_backfill_basis(state) == PLAY_WALLCLOCK_BASIS

    async def test_a_point_with_no_play_time_is_not_stored(self, run_task):
        session = _Session(
            first_arm=[_row(14780546, espn_id="401872948", sport_key="americanfootball_nfl")],
            reread_arm=[],
        )
        stats, _ = await run_task(session)

        assert stats["points_unevidenced"] == 1
        assert len(session.inserts) <= 184
        assert all(p["captured_at"] is not None for p in session.inserts)

    async def test_an_instant_already_stored_is_not_stored_again(self, run_task):
        """The table has no unique key, so `ON CONFLICT DO NOTHING` never fired and
        a re-selected game was written again every run."""
        first = await _parse(_mlb_summary(), "baseball_mlb")
        already = [first[0]["wallclock"], first[10]["wallclock"], first[-1]["wallclock"]]
        session = _Session(
            first_arm=[], reread_arm=[_row(MLB["event_id"], n=51)],
            stored={MLB["event_id"]: already},
        )
        stats, _ = await run_task(session)

        stamps = set(_stamps(session))
        assert not stamps & set(already)
        assert stats["points_already_stored"] >= 3

    async def test_the_reread_arm_goes_first_and_is_not_processed_twice(self, run_task):
        session = _Session(
            first_arm=[_row(14780546, espn_id="401872948", sport_key="americanfootball_nfl"),
                       _row(MLB["event_id"], n=51)],
            reread_arm=[_row(MLB["event_id"], n=51)],
        )
        stats, fetched = await run_task(session)

        assert fetched == ["401817067", "401872948"]
        assert stats["events_checked"] == 2

    async def test_the_oldest_first_run_does_not_reread(self, run_task):
        session = _Session(first_arm=[], reread_arm=[_row(MLB["event_id"], n=51)])
        stats, fetched = await run_task(session, oldest_first=True)

        assert not any("has_estimate" in sql for sql, _ in session.selects)
        assert fetched == []
        assert stats["restamp_candidates"] == 0

    async def test_the_reread_arm_asks_for_estimate_only_recent_games(self, run_task):
        session = _Session(first_arm=[], reread_arm=[])
        before = datetime.now(UTC)
        await run_task(session)

        sql, params = next((s, p) for s, p in session.selects if "has_estimate" in s)
        assert "NOT wps.game_state ? 'time_basis'" in sql
        assert "wps.game_state ? 'seconds_left'" in sql
        assert "AND NOT spread.has_evidenced" in sql
        assert params["basis"] == PLAY_WALLCLOCK_BASIS
        assert params["limit"] == espn_sync._WP_RESTAMP_LIMIT
        window = before - params["window_start"]
        assert timedelta(days=espn_sync._WP_RESTAMP_WINDOW_DAYS) - timedelta(minutes=1) \
            <= window <= timedelta(days=espn_sync._WP_RESTAMP_WINDOW_DAYS) + timedelta(minutes=1)


# ── What the history serves ─────────────────────────────────────────────────


def _pt(minute, state, home=0.6):
    return {
        "timestamp": (FIRST_PITCH + timedelta(minutes=minute)).isoformat(),
        "home_probability": home,
        "game_state": state,
    }


LEGACY = {"seconds_left": None, "backfilled": True}
EVIDENCED = {"seconds_left": None, "backfilled": True, "time_basis": PLAY_WALLCLOCK_BASIS,
             "play_id": "4018170670001990057"}
LIVE_READING = {"period": "Top 9th", "home_score": 3, "away_score": 1}
PERIOD_MARKER = {"period": "3rd", "backfilled": True}  # game_state_backfill's shape


class TestTheBasis:
    @pytest.mark.parametrize("state,expected", [
        (EVIDENCED, PLAY_WALLCLOCK_BASIS),
        (LEGACY, ESTIMATED_BASIS),
        ({"seconds_left": 1200, "backfilled": True}, ESTIMATED_BASIS),
        (PERIOD_MARKER, None),
        (LIVE_READING, None),
        ({"seconds_left": None, "backfilled": "true"}, None),
        (None, None),
        ("not a dict", None),
    ])
    def test_the_backfill_signature(self, state, expected):
        assert espn_wp_backfill_basis(state) == expected


class TestServedKind:
    def test_an_evidenced_backfill_point_is_play_history(self):
        assert served_evidence(_pt(10, EVIDENCED)) == {"kind": "play_history"}

    def test_an_estimated_point_is_estimated_time(self):
        assert served_evidence(_pt(10, LEGACY)) == {"kind": "estimated_time"}

    def test_a_stamped_estimate_is_still_not_observed(self):
        """A pre-#8514 retention pass could merge 200-s-apart estimates and stamp
        a span; that stamp must not turn an invented time into coverage."""
        state = {**LEGACY, "evidence_span": {
            "contract": "7878.v1", "resolution_s": 300,
            "covered_through": "2026-09-24T19:00:00.000000Z",
        }}
        assert served_evidence(_pt(10, state)) == {"kind": "estimated_time"}

    def test_a_finished_games_last_backfill_point_is_not_a_terminal_row(self):
        assert served_evidence(_pt(10, EVIDENCED), terminal_row=True) == {"kind": "play_history"}

    def test_a_live_reading_and_a_period_marker_are_unchanged(self):
        assert served_evidence(_pt(10, LIVE_READING)) is None
        assert served_evidence(_pt(10, PERIOD_MARKER)) is None


class TestSupersession:
    def test_estimates_go_when_evidenced_points_exist(self):
        series = [
            _pt(0, LEGACY), _pt(3, EVIDENCED), _pt(4, LIVE_READING),
            _pt(6, LEGACY), _pt(9, EVIDENCED), _pt(12, PERIOD_MARKER),
        ]
        kept, dropped = drop_superseded_estimates(series)

        assert dropped == 2
        assert [p["game_state"] for p in kept] == [EVIDENCED, LIVE_READING, EVIDENCED, PERIOD_MARKER]

    def test_a_series_of_estimates_alone_is_served_whole(self):
        series = [_pt(0, LEGACY), _pt(3, LEGACY), _pt(4, LIVE_READING)]
        kept, dropped = drop_superseded_estimates(series)

        assert dropped == 0
        assert kept == series

    def test_the_route_supersedes_before_the_blend_and_the_metadata(self):
        """The aggregate line is built from `win_prob_history`, and the legend's
        `snapshot_count` is rendered: both must see the series after the drop."""
        source = pathlib.Path(espn_sync.__file__).parents[1].joinpath("routes", "events.py").read_text()
        drop = source.index("drop_superseded_estimates(\n")
        assert source.count("win_prob_sources_meta[source_key] = {") == 1
        assert drop < source.index("win_prob_sources_meta[source_key] = {")
        assert drop < source.index("aggregate_line = []", drop)
        assert drop < source.index("_extend_win_prob_history_to_live_edge(\n        win_prob_history,", drop)
