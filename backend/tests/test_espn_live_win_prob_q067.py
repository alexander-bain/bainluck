"""Queue 067 — the ESPN win-probability line is a curve, not a flat line.

Three defects, one symptom (`/events/{id}/models` draws ESPN as a flat, janky
line), each guarded here:

A. ESPN's scoreboard carries `situation.lastPlay.probability` for NFL and WNBA
   and NOT for MLB, so the live pass is blind for baseball. Measured over 21 days
   of completed espn_id-matched games: NFL p50 116 live ESPN points per game,
   WNBA p50 80, MLB p50 5. `sync_espn_live_win_probability` fills that in from
   ESPN's core probabilities feed.

B. `get_win_probability` divided `homeWinPercentage` by 100. That field is
   already a 0-1 FRACTION on both surfaces ESPN serves it from (probed
   2026-08-31: MLB 0.499, NFL 0.5853, NBA 0.137), so the backfill wrote 118,824
   rows across 989 events with 118,821 of them below 2% — a line glued to the
   floor of the chart.

C. `compute_and_write_stat_model` stopped at `ee.status != "in"`, which is what
   ESPN reports during a rain delay. On COL-BAL 2026-08-31 ESPN's own
   play-by-play wallclock shows a 97.5-minute stoppage (End 5th 02:01:21Z -> Top
   6th 03:38:54Z) and our own model was not recomputed once across it, so the
   hero's relative-age decay demoted it to the 0.1 weight floor.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.sql import Update

from app.services.espn_api import (
    ESPNAPIService,
    ESPNLiveWinProbability,
    _normalize_win_percentage,
)
from app.tasks import espn_live_win_prob as mod
from app.utils.espn_helpers import espn_game_is_in_play


# ---------------------------------------------------------------------------
# B — the scale of ESPN's homeWinPercentage
# ---------------------------------------------------------------------------

class TestWinPercentageScale:
    def test_a_fraction_is_left_alone(self):
        # The shape ESPN actually serves today, on every league probed.
        assert _normalize_win_percentage(0.5853) == pytest.approx(0.5853)
        assert _normalize_win_percentage(0.137) == pytest.approx(0.137)
        assert _normalize_win_percentage(0.0) == 0.0

    def test_a_percentage_is_divided(self):
        # The historical scoreboard shape, which is why the rule is conditional
        # rather than "never divide".
        assert _normalize_win_percentage(83.1) == pytest.approx(0.831)
        assert _normalize_win_percentage(100) == pytest.approx(1.0)

    def test_junk_is_none_not_a_crash(self):
        assert _normalize_win_percentage(None) is None
        assert _normalize_win_percentage("n/a") is None

    def test_backfill_series_keeps_its_scale(self):
        """RED before the fix: this returned 0.005853, not 0.5853.

        118,824 production rows were written at that scale. This is the guard
        for the class, so it asserts the whole series, not one point.
        """
        svc = ESPNAPIService()
        payload = {
            "winprobability": [
                {"playId": "1", "secondsLeft": 3600, "homeWinPercentage": 0.5853},
                {"playId": "2", "secondsLeft": 1800, "homeWinPercentage": 0.137},
                {"playId": "3", "secondsLeft": 0, "homeWinPercentage": 0.9910},
            ]
        }

        async def fake_get(url):
            return payload

        svc._get = fake_get
        series = asyncio.run(svc.get_win_probability("baseball_mlb", "1"))

        assert [p["home_win_probability"] for p in series] == pytest.approx(
            [0.5853, 0.137, 0.9910]
        )
        # The defect's signature: everything under 2%.
        assert not [p for p in series if p["home_win_probability"] < 0.02]


# ---------------------------------------------------------------------------
# A — reading the core probabilities feed
# ---------------------------------------------------------------------------

def _core_responses(point_count=60, home=0.368, ref_scheme="http"):
    """The three payloads ESPN's core probabilities feed actually returns."""
    ref = (
        f"{ref_scheme}://sports.core.api.espn.com/v2/sports/baseball/leagues/mlb"
        f"/events/401816755/competitions/401816755/probabilities/4018167551404990057"
        f"?lang=en&region=us"
    )
    return {
        "index": {"count": point_count, "pageIndex": 1, "pageSize": 1,
                  "pageCount": point_count, "items": []},
        "page": {"count": point_count, "pageCount": point_count,
                 "items": [{"$ref": ref}]},
        "point": {"$ref": ref, "homeWinPercentage": home,
                  "awayWinPercentage": round(1 - home, 4),
                  "lastModified": "2026-09-01T04:32Z"},
    }


class _RecordingService(ESPNAPIService):
    """An ESPNAPIService whose HTTP layer is a script, and which counts calls."""

    def __init__(self, script, statuses=None):
        super().__init__()
        self.script = script
        self.statuses = statuses or {}
        self.urls = []

    async def _get_with_status(self, url):
        self.urls.append(url)
        if "?limit=1&page=" in url:
            key = "page"
        elif url.endswith("probabilities?limit=1"):
            key = "index"
        else:
            key = "point"
        status = self.statuses.get(key, 200)
        if status != 200:
            return status, None
        return 200, self.script[key]


class TestGetLiveWinProbability:
    def test_reads_the_newest_point(self):
        svc = _RecordingService(_core_responses(home=0.368))
        r = asyncio.run(svc.get_live_win_probability("baseball_mlb", "401816755"))

        assert r is not None and r.supported
        assert r.home_win_probability == pytest.approx(0.368)
        assert r.point_count == 60
        assert r.play_id == "4018167551404990057"
        assert len(svc.urls) == 3

    def test_the_self_link_is_rewritten_to_https(self):
        """ESPN self-links over http and our client does not follow redirects,
        so the raw $ref reads as a 126-byte non-answer."""
        svc = _RecordingService(_core_responses(ref_scheme="http"))
        asyncio.run(svc.get_live_win_probability("baseball_mlb", "401816755"))
        assert svc.urls[-1].startswith("https://")
        assert not any(u.startswith("http://") for u in svc.urls)

    def test_an_unmoved_feed_costs_one_request(self):
        """The rate-limit claim, asserted as a request COUNT.

        ESPN adds a point about every 122 s (measured p50 over a full game) and
        we ask every 60 s, so roughly half of all cycles land here.
        """
        svc = _RecordingService(_core_responses(point_count=60))
        r = asyncio.run(
            svc.get_live_win_probability("baseball_mlb", "401816755",
                                         known_point_count=60)
        )
        assert len(svc.urls) == 1
        assert r is not None and r.supported
        assert r.home_win_probability is None   # nothing new to report
        assert r.point_count == 60

    def test_a_moved_feed_spends_the_other_two(self):
        svc = _RecordingService(_core_responses(point_count=61))
        r = asyncio.run(
            svc.get_live_win_probability("baseball_mlb", "401816755",
                                         known_point_count=60)
        )
        assert len(svc.urls) == 3
        assert r.home_win_probability == pytest.approx(0.368)

    def test_400_is_unsupported_not_a_transient_miss(self):
        """Gotcha #53. Soccer answers 400 'Probabilities are not supported' and
        that is permanent; an empty answer is not."""
        svc = _RecordingService(_core_responses(), statuses={"index": 400})
        r = asyncio.run(svc.get_live_win_probability("soccer_epl", "401879295"))
        assert r is not None
        assert r.supported is False
        assert r.home_win_probability is None

    def test_a_timeout_is_not_an_unsupported_league(self):
        svc = _RecordingService(_core_responses(), statuses={"index": 503})
        r = asyncio.run(svc.get_live_win_probability("baseball_mlb", "1"))
        assert r is None      # try again next cycle, do not retire the league

    def test_an_unopened_feed_reads_as_no_point_yet(self):
        script = _core_responses()
        script["index"] = {"count": 0, "pageCount": 0, "items": []}
        svc = _RecordingService(script)
        r = asyncio.run(svc.get_live_win_probability("baseball_mlb", "1"))
        assert r is None
        assert len(svc.urls) == 1


# ---------------------------------------------------------------------------
# A — the task
# ---------------------------------------------------------------------------

def _row(event_id=1, sport_key="baseball_mlb", stamp_age_s=3600, sources=None):
    # Staleness is measured against the wall clock the task itself reads, so the
    # anchor is `now` minus an offset — offset first, no branch on the clock
    # (gotcha #44).
    now = datetime.now(timezone.utc)
    if sources is None:
        if stamp_age_s is None:
            sources = {"kalshi": {"value": 0.29, "updated_at": now.isoformat()}}
        else:
            sources = {
                "kalshi": {"value": 0.29, "updated_at": now.isoformat()},
                "espn": {
                    "value": 0.526,
                    "updated_at": (now - timedelta(seconds=stamp_age_s)).isoformat(),
                },
            }
    return SimpleNamespace(
        id=event_id, espn_id=f"4018167{event_id:02d}", sport_key=sport_key,
        home_score=1, away_score=2, game_clock="0:00", period="Top 8th",
        win_probability_sources=sources,
    )


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    """Enough session to run the task: one candidate select, then updates,
    snapshot lookups and adds."""

    def __init__(self, rows, existing_snapshot=None):
        self.rows = rows
        self.existing_snapshot = existing_snapshot
        self.updates = []
        self.added = []
        self.commits = 0

    async def execute(self, stmt):
        if isinstance(stmt, Update):
            self.updates.append(stmt.compile().params)
            return _FakeResult([])
        # Told apart by what they select, not by call order — the task runs more
        # than once per test and a counter would silently stop serving
        # candidates on the second cycle.
        names = {c["name"] for c in stmt.column_descriptions}
        if "espn_id" in names:
            return _FakeResult(self.rows)
        return _FakeResult([self.existing_snapshot] if self.existing_snapshot else [])

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


class _Ctx:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *a):
        return False


class _ScriptedService:
    """Stands in for ESPNAPIService inside the task."""

    def __init__(self, readings):
        self.readings = readings          # sport_key -> ESPNLiveWinProbability|None
        self.calls = []
        self.closed = False

    async def get_live_win_probability(self, sport_key, event_id, known_point_count=None):
        self.calls.append((sport_key, event_id, known_point_count))
        value = self.readings.get(sport_key)
        return value(known_point_count) if callable(value) else value

    async def close(self):
        self.closed = True


def _run(monkeypatch, rows, readings, budget=mod.DEFAULT_EVENT_BUDGET,
         existing_snapshot=None):
    mod._reset_caches_for_test()
    session = _FakeSession(rows, existing_snapshot=existing_snapshot)
    service = _ScriptedService(readings)
    monkeypatch.setattr(mod, "get_task_session", lambda: _Ctx(session))
    monkeypatch.setattr(
        "app.services.espn_api.ESPNAPIService", lambda *a, **k: service
    )
    stats = asyncio.run(mod._sync_espn_live_win_probability(budget=budget))
    return stats, session, service


class TestLiveWinProbTask:
    def test_a_stale_mlb_game_is_refreshed(self, monkeypatch):
        stats, session, service = _run(
            monkeypatch,
            [_row(stamp_age_s=2600)],
            {"baseball_mlb": ESPNLiveWinProbability(0.177, point_count=65)},
        )

        assert stats["refreshed"] == 1
        assert stats["value_changed"] == 1
        assert service.closed is True

        params = session.updates[0]
        assert params["espn_win_prob_home"] == pytest.approx(0.177)
        espn = params["win_probability_sources"]["espn"]
        assert espn["value"] == pytest.approx(0.177)
        # The stamp is the point of the whole task.
        assert _parse(espn["updated_at"]) > datetime.now(timezone.utc) - timedelta(seconds=60)
        # Siblings survive the JSONB write (gotcha #4's other half).
        assert params["win_probability_sources"]["kalshi"]["value"] == 0.29

        # Both series get the point: espn_snapshots feeds the models page,
        # win_prob_snapshots feeds the multi-source chart.
        assert {type(o).__name__ for o in session.added} == {
            "ESPNSnapshot", "WinProbSnapshot"
        }

    def test_an_unchanged_reading_still_refreshes_the_stamp(self, monkeypatch):
        """The ship. A source reporting the same number is not a stale source —
        withholding the stamp is what let the hero decay ESPN to the 0.1 floor
        while ESPN was still answering."""
        first = ESPNLiveWinProbability(0.177, point_count=65)
        unmoved = ESPNLiveWinProbability(None, point_count=65)

        seen = {"n": 0}

        def script(known):
            seen["n"] += 1
            return first if seen["n"] == 1 else unmoved

        mod._reset_caches_for_test()
        session = _FakeSession([_row(stamp_age_s=2600)])
        service = _ScriptedService({"baseball_mlb": script})
        monkeypatch.setattr(mod, "get_task_session", lambda: _Ctx(session))
        monkeypatch.setattr(
            "app.services.espn_api.ESPNAPIService", lambda *a, **k: service
        )

        asyncio.run(mod._sync_espn_live_win_probability())
        stats = asyncio.run(mod._sync_espn_live_win_probability())

        assert stats["refreshed"] == 1
        assert stats["unchanged_reaffirmed"] == 1
        assert stats["value_changed"] == 0
        # Stamp written on the second cycle...
        assert len(session.updates) == 2
        assert session.updates[1]["win_probability_sources"]["espn"]["value"] == (
            pytest.approx(0.177)
        )
        # ...and NO second chart point, because nothing happened in the game.
        assert len(session.added) == 2

    def test_a_fresh_reading_is_left_alone(self, monkeypatch):
        """NFL/WNBA are served by the scoreboard pass; this task must not spend
        a single request on them."""
        stats, _session, service = _run(
            monkeypatch,
            [_row(sport_key="americanfootball_nfl", stamp_age_s=10)],
            {"americanfootball_nfl": ESPNLiveWinProbability(0.6, point_count=9)},
        )
        assert stats["already_fresh"] == 1
        assert stats["refreshed"] == 0
        assert service.calls == []

    def test_a_never_stamped_game_sorts_in_and_is_probed(self, monkeypatch):
        stats, session, _ = _run(
            monkeypatch,
            [_row(stamp_age_s=None)],
            {"baseball_mlb": ESPNLiveWinProbability(0.44, point_count=3)},
        )
        assert stats["refreshed"] == 1
        assert session.updates[0]["win_probability_sources"]["espn"]["value"] == (
            pytest.approx(0.44)
        )

    def test_an_unsupported_league_is_asked_once_per_worker(self, monkeypatch):
        """Soccer has no ESPN win probability anywhere. One 400 retires the
        league; the 9 other matches on the slate cost nothing."""
        rows = [_row(event_id=i, sport_key="soccer_epl") for i in range(1, 11)]
        stats, _session, service = _run(
            monkeypatch, rows,
            {"soccer_epl": ESPNLiveWinProbability(None, supported=False)},
        )
        assert len(service.calls) == 1
        assert stats["unsupported_league"] == 10
        assert stats["refreshed"] == 0

    def test_the_budget_is_bounded_and_says_what_it_dropped(self, monkeypatch, caplog):
        """No silent caps — a trimmed slate must not read as a covered slate."""
        rows = [_row(event_id=i) for i in range(1, 9)]
        with caplog.at_level(logging.WARNING, logger=mod.__name__):
            stats, _session, service = _run(
                monkeypatch, rows,
                {"baseball_mlb": ESPNLiveWinProbability(0.5, point_count=4)},
                budget=3,
            )
        assert len(service.calls) == 3
        assert stats["refreshed"] == 3
        assert stats["over_budget"] == 5
        assert "5 stale live games NOT refreshed" in caplog.text

    def test_one_bad_game_does_not_wipe_the_pass(self, monkeypatch):
        """Gotcha #42."""
        def script(known):
            raise RuntimeError("ESPN exploded")

        mod._reset_caches_for_test()
        rows = [_row(event_id=1, sport_key="baseball_mlb"),
                _row(event_id=2, sport_key="basketball_nba")]
        session = _FakeSession(rows)
        service = _ScriptedService({
            "baseball_mlb": script,
            "basketball_nba": ESPNLiveWinProbability(0.71, point_count=8),
        })
        monkeypatch.setattr(mod, "get_task_session", lambda: _Ctx(session))
        monkeypatch.setattr(
            "app.services.espn_api.ESPNAPIService", lambda *a, **k: service
        )
        stats = asyncio.run(mod._sync_espn_live_win_probability())

        assert stats["refreshed"] == 1
        assert len(stats["errors"]) == 1
        assert session.updates[0]["espn_win_prob_home"] == pytest.approx(0.71)

    def test_no_live_games_is_a_named_outcome(self, monkeypatch):
        stats, _session, service = _run(monkeypatch, [], {})
        assert stats["status"] == "no_live_espn_events"
        assert service.calls == []


def _parse(raw):
    parsed = datetime.fromisoformat(raw)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# C — the model keeps running through a stopped clock
# ---------------------------------------------------------------------------

class TestGameIsInPlay:
    def test_in_progress_is_in_play(self):
        assert espn_game_is_in_play("in", "live") is True
        assert espn_game_is_in_play("in", None) is True

    def test_a_rain_delay_on_a_live_event_is_in_play(self):
        """The COL-BAL case: 97.5 minutes between End 5th and Top 6th."""
        assert espn_game_is_in_play("status_delayed", "live") is True
        assert espn_game_is_in_play("status_rain_delay", "live") is True

    def test_a_delay_on_an_event_we_have_settled_is_not(self):
        assert espn_game_is_in_play("status_delayed", "completed") is False
        assert espn_game_is_in_play("status_delayed", "scheduled") is False

    def test_finals_and_pregame_are_never_in_play(self):
        for status in ("post", "scheduled", "pre", "status_final"):
            assert espn_game_is_in_play(status, "live") is False

    def test_a_suspended_game_stops(self):
        """A suspended game resumes on another DATE. Our own status can sit at
        'live' for many hours; re-affirming a reading for a game nobody is
        playing is exactly the staleness this queue is removing."""
        assert espn_game_is_in_play("status_suspended", "live") is False
        assert espn_game_is_in_play("status_postponed", "live") is False
        assert espn_game_is_in_play("status_canceled", "live") is False

    def test_an_empty_status_stops(self):
        assert espn_game_is_in_play(None, "live") is False
        assert espn_game_is_in_play("", "live") is False


class TestStatModelThroughADelay:
    """The predicate above is only worth having if the writer that RUNS honours
    it, so these drive `compute_and_write_stat_model` itself."""

    @staticmethod
    def _event():
        return SimpleNamespace(
            id=7, status="live", opening_home_spread=-1.5,
            opening_home_probability=0.55,
            win_probability_sources={"kalshi": {"value": 0.3,
                                                "updated_at": datetime.now(timezone.utc).isoformat()}},
        )

    @staticmethod
    def _espn(status):
        return SimpleNamespace(
            status=status, home_score=1, away_score=2, clock=None,
            period=6, status_detail="Delayed" if status != "in" else "Top 6th",
        )

    def _run(self, espn_status):
        from app.utils.espn_helpers import compute_and_write_stat_model

        event = self._event()
        session = _FakeSession([])
        stats = {}
        wrote = asyncio.run(
            compute_and_write_stat_model(
                session, event, self._espn(espn_status), "baseball_mlb", stats
            )
        )
        return wrote, session, stats

    def test_the_model_runs_during_a_delay(self):
        wrote, session, stats = self._run("status_delayed")
        assert wrote is True
        assert stats.get("stat_model_clock_stopped") == 1
        stamped = session.updates[0]["win_probability_sources"]["stat_model"]
        assert _parse(stamped["updated_at"]) > datetime.now(timezone.utc) - timedelta(minutes=5)

    def test_the_model_still_runs_normally(self):
        wrote, session, stats = self._run("in")
        assert wrote is True
        assert "stat_model_clock_stopped" not in stats
        assert "stat_model" in session.updates[0]["win_probability_sources"]

    def test_the_model_does_not_run_after_the_final(self):
        wrote, session, _stats = self._run("post")
        assert wrote is False
        assert session.updates == []
