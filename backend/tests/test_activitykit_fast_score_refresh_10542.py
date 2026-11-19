"""#10542 step 5: fast ESPN score refresh gated on active Live Activities.

Verifies:
* Quiet nights (0 active registrations) make zero ESPN calls.
* Active Live Activities refresh ESPN scores BEFORE observation capture, with
  one scoreboard request per distinct sport and a single-event fallback on
  midnight-UTC rollover.
* Refresher failures/timeouts fail open so APNs delivery still runs on stored
  readings and the ESPN HTTP client is always closed.
* The kill switch ``ACTIVITYKIT_FAST_SCORE_REFRESH_ENABLED=false`` disables the
  refresher cleanly.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.services import activitykit_fast_score_refresh as fast_refresh
from app.services import activitykit_runtime as runtime
from app.tasks import activitykit_runtime as runtime_task

NOW = datetime(2026, 6, 15, 22, 0, tzinfo=timezone.utc)
VALID_TOKEN = "header.payload.signature"


class _FakeSession:
    def __init__(self, *, rows=None, events=None):
        self._rows = list(rows or [])
        self._events = list(events or [])
        self.committed = 0
        self.savepoints = 0
        self.closed = False

    async def execute(self, stmt, *args, **kwargs):
        sql = str(stmt)
        if "activitykit_registrations" in sql:
            rows = self._rows
            return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: rows))
        if self._events:
            events = self._events
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: events))
        rows = self._rows
        return SimpleNamespace(all=lambda: rows)

    @asynccontextmanager
    async def begin_nested(self):
        self.savepoints += 1
        yield self

    async def commit(self):
        self.committed += 1


class _SessionSequence:
    """Returns a fresh fake session per `async with sessions() as s:` block."""

    def __init__(self, sessions_list):
        self._sessions = list(sessions_list)
        self.opened = 0

    def __call__(self):
        idx = self.opened
        self.opened += 1
        sess = self._sessions[idx]

        @asynccontextmanager
        async def _cm():
            yield sess

        return _cm()


class _FakeESPN:
    def __init__(self, *, scoreboards=None, single_events=None, supported=None, delay=0.0):
        self.scoreboards = dict(scoreboards or {})
        self.single_events = dict(single_events or {})
        self.supported = set(supported or {"basketball_nba", "icehockey_nhl"})
        self.delay = delay
        self.scoreboard_calls: list[str] = []
        self.event_calls: list[tuple[str, str]] = []
        self.closed = False

    def _get_espn_path(self, sport_key: str):
        return ("basketball", "nba") if sport_key in self.supported else None

    async def get_scoreboard(self, sport_key: str):
        self.scoreboard_calls.append(sport_key)
        if self.delay:
            await asyncio.sleep(self.delay)
        val = self.scoreboards.get(sport_key, [])
        if isinstance(val, Exception):
            raise val
        return val

    async def get_event(self, sport_key: str, event_id: str):
        self.event_calls.append((sport_key, event_id))
        if self.delay:
            await asyncio.sleep(self.delay)
        val = self.single_events.get((sport_key, event_id))
        if isinstance(val, Exception):
            raise val
        return val

    async def close(self):
        self.closed = True


class TestRunActivityKitPageRefresherHook:
    @pytest.mark.asyncio
    async def test_quiet_night_never_calls_score_refresher(self, monkeypatch):
        monkeypatch.setattr(runtime, "cleanup_expired", AsyncMock(return_value=0))
        sessions = _SessionSequence([_FakeSession(rows=[])])
        refresher = AsyncMock()
        adapter = SimpleNamespace(capture=AsyncMock())
        worker = SimpleNamespace(observe=AsyncMock(), reserve=AsyncMock(), send=AsyncMock())

        result = await runtime.run_activitykit_page(
            sessions,
            adapter,
            worker,
            transport=object(),
            provider_token=AsyncMock(return_value=VALID_TOKEN),
            policy=runtime.RuntimePolicy(enabled=True),
            clock=lambda: NOW,
            score_refresher=refresher,
        )

        assert result.status == "complete"
        assert result.scanned == 0
        refresher.assert_not_awaited()
        adapter.capture.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_refresher_runs_before_capture_with_deduped_event_ids(self, monkeypatch):
        monkeypatch.setattr(runtime, "cleanup_expired", AsyncMock(return_value=0))
        rows = [
            {"activity_id": "act-1", "event_id": 101},
            {"activity_id": "act-2", "event_id": 101},
            {"activity_id": "act-3", "event_id": 202},
        ]
        sessions = _SessionSequence([_FakeSession(rows=rows)])
        order: list[tuple[str, object]] = []

        async def _refresher(event_ids):
            order.append(("refresh", list(event_ids)))

        async def _capture(event_id):
            order.append(("capture", event_id))
            return SimpleNamespace(snapshot=f"snap-{event_id}", sequence=1)

        adapter = SimpleNamespace(capture=_capture)
        worker = SimpleNamespace(
            observe=AsyncMock(return_value=True),
            reserve=AsyncMock(return_value="res"),
            send=AsyncMock(return_value="accepted"),
        )

        result = await runtime.run_activitykit_page(
            sessions,
            adapter,
            worker,
            transport=object(),
            provider_token=AsyncMock(return_value=VALID_TOKEN),
            policy=runtime.RuntimePolicy(enabled=True),
            clock=lambda: NOW,
            score_refresher=_refresher,
        )

        assert result.status == "complete"
        assert result.scanned == 3
        assert result.accepted == 3
        assert order == [("refresh", [101, 202]), ("capture", 101), ("capture", 202)]

    @pytest.mark.asyncio
    async def test_refresher_error_fails_open_and_delivery_still_runs(self, monkeypatch):
        monkeypatch.setattr(runtime, "cleanup_expired", AsyncMock(return_value=0))
        rows = [{"activity_id": "act-1", "event_id": 101}]
        sessions = _SessionSequence([_FakeSession(rows=rows)])
        refresher = AsyncMock(side_effect=RuntimeError("ESPN unreachable"))
        adapter = SimpleNamespace(
            capture=AsyncMock(return_value=SimpleNamespace(snapshot="snap", sequence=7))
        )
        worker = SimpleNamespace(
            observe=AsyncMock(return_value=True),
            reserve=AsyncMock(return_value="res"),
            send=AsyncMock(return_value="accepted"),
        )

        result = await runtime.run_activitykit_page(
            sessions,
            adapter,
            worker,
            transport=object(),
            provider_token=AsyncMock(return_value=VALID_TOKEN),
            policy=runtime.RuntimePolicy(enabled=True),
            clock=lambda: NOW,
            score_refresher=refresher,
        )

        assert result.status == "complete"
        assert result.accepted == 1
        refresher.assert_awaited_once_with([101])
        adapter.capture.assert_awaited_once_with(101)


class TestRefreshActiveLiveActivityScores:
    @pytest.mark.asyncio
    async def test_batches_by_sport_and_writes_via_canonical_updater(self):
        # Two NBA games share one scoreboard fetch; both update and commit.
        read_session = _FakeSession(
            rows=[
                (101, "4010001", "basketball_nba"),
                (102, "4010002", "basketball_nba"),
            ]
        )
        ev1 = SimpleNamespace(id=101, espn_id="4010001")
        ev2 = SimpleNamespace(id=102, espn_id="4010002")
        write_session = _FakeSession(events=[ev1, ev2])
        sessions = _SessionSequence([read_session, write_session])

        ee1 = SimpleNamespace(espn_id="4010001", home_score=88, away_score=84)
        ee2 = SimpleNamespace(espn_id="4010002", home_score=51, away_score=49)
        fake_espn = _FakeESPN(scoreboards={"basketball_nba": [ee1, ee2]})
        updater = AsyncMock(side_effect=[True, False])

        summary = await fast_refresh.refresh_active_live_activity_scores(
            sessions,
            [101, 102, 101],
            espn_factory=lambda: fake_espn,
            updater=updater,
            clock=lambda: NOW,
        )

        assert fake_espn.scoreboard_calls == ["basketball_nba"]
        assert fake_espn.event_calls == []
        assert fake_espn.closed is True
        assert updater.await_count == 2
        for call in updater.await_args_list:
            assert call.kwargs["observed_at"] == NOW
        assert write_session.savepoints == 2
        assert write_session.committed == 1
        assert summary == {
            "checked": 2,
            "sports_fetched": 1,
            "matched": 2,
            "refreshed": 1,
            "errors": 0,
        }

    @pytest.mark.asyncio
    async def test_rollover_fallback_uses_get_event_when_absent_from_scoreboard(self):
        read_session = _FakeSession(rows=[(201, "4019999", "icehockey_nhl")])
        ev = SimpleNamespace(id=201, espn_id="4019999")
        write_session = _FakeSession(events=[ev])
        sessions = _SessionSequence([read_session, write_session])

        ee = SimpleNamespace(espn_id="4019999", home_score=3, away_score=2)
        fake_espn = _FakeESPN(
            scoreboards={"icehockey_nhl": []},
            single_events={("icehockey_nhl", "4019999"): ee},
        )
        updater = AsyncMock(return_value=True)

        summary = await fast_refresh.refresh_active_live_activity_scores(
            sessions,
            [201],
            espn_factory=lambda: fake_espn,
            updater=updater,
            clock=lambda: NOW,
        )

        assert fake_espn.scoreboard_calls == ["icehockey_nhl"]
        assert fake_espn.event_calls == [("icehockey_nhl", "4019999")]
        assert fake_espn.closed is True
        assert summary["matched"] == 1
        assert summary["refreshed"] == 1
        assert summary["errors"] == 0

    @pytest.mark.asyncio
    async def test_no_eligible_rows_makes_zero_espn_calls(self):
        sessions = _SessionSequence([_FakeSession(rows=[])])
        espn_factory = Mock(side_effect=AssertionError("must not construct ESPN client"))

        summary = await fast_refresh.refresh_active_live_activity_scores(
            sessions,
            [301],
            espn_factory=espn_factory,
            clock=lambda: NOW,
        )

        espn_factory.assert_not_called()
        assert summary == {
            "checked": 0,
            "sports_fetched": 0,
            "matched": 0,
            "refreshed": 0,
            "errors": 0,
        }

    @pytest.mark.asyncio
    async def test_espn_timeout_fails_open_and_closes_client(self):
        read_session = _FakeSession(rows=[(401, "4015555", "basketball_nba")])
        sessions = _SessionSequence([read_session])
        fake_espn = _FakeESPN(scoreboards={"basketball_nba": []}, delay=0.5)

        summary = await fast_refresh.refresh_active_live_activity_scores(
            sessions,
            [401],
            espn_factory=lambda: fake_espn,
            timeout_seconds=0.05,
            clock=lambda: NOW,
        )

        assert fake_espn.closed is True
        assert summary["errors"] == 1
        assert summary["refreshed"] == 0


class TestTaskKillSwitch:
    @staticmethod
    def _provider_env():
        key = ec.generate_private_key(ec.SECP256R1())
        pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
        return {
            "ACTIVITYKIT_RUNTIME_ENABLED": "true",
            "ACTIVITYKIT_APNS_BUNDLE_ID": "com.example.test",
            "ACTIVITYKIT_APNS_ENVIRONMENT": "sandbox",
            "ACTIVITYKIT_APNS_TEAM_ID": "ABCDEFGHIJ",
            "ACTIVITYKIT_APNS_KEY_ID": "0123456789",
            "ACTIVITYKIT_APNS_PRIVATE_KEY": pem,
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize("flag,expect_callable", [(None, True), ("true", True), ("false", False)])
    async def test_fast_refresh_kill_switch(self, monkeypatch, flag, expect_callable):
        for k, v in self._provider_env().items():
            monkeypatch.setenv(k, v)
        if flag is None:
            monkeypatch.delenv("ACTIVITYKIT_FAST_SCORE_REFRESH_ENABLED", raising=False)
        else:
            monkeypatch.setenv("ACTIVITYKIT_FAST_SCORE_REFRESH_ENABLED", flag)

        engine = SimpleNamespace(dispose=AsyncMock())
        transport = SimpleNamespace(aclose=AsyncMock())
        monkeypatch.setattr(runtime_task, "_get_task_engine", Mock(return_value=engine))
        monkeypatch.setattr(runtime_task, "async_sessionmaker", Mock(return_value="sessions"))
        monkeypatch.setattr(runtime_task, "ActivityKitAPNsTransport", Mock(return_value=transport))
        page = AsyncMock(return_value={"status": "complete", "terminal": "complete"})
        monkeypatch.setattr(runtime_task, "run_serialized_page", page)

        result = await runtime_task.run_activitykit_runtime()
        assert result["terminal"] == "complete"
        refresher = page.call_args.kwargs.get("score_refresher")
        assert callable(refresher) is expect_callable
