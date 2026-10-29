"""#10090 — the scores pass commits its stale-event writes before the live EI step.

``detect_and_close_stale_events`` closes or suspends live rows with Core
UPDATEs. Those row locks used to ride the pass's one commit at the very end,
after ``update_live_ei`` had read every live game's snapshots and computed EI in
Python. Now the pass commits first; EI then commits its own skip-locked write
(``tests/integration/test_the_live_ei_write_holds_no_live_row_10090_pg.py``).

Drives the real ``_poll_all_odds`` on the lat-p159 fakes and records the order
of the three calls. On unfixed ``origin/master`` dca1ff3baf the order reads
stale, EI, commit.
"""

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks import odds_polling
from tests.test_live_cadence_lat_p159 import _FakeRedis, _FakeSession

pytestmark = pytest.mark.asyncio


async def _run_pass():
    calls: list[str] = []
    session = _FakeSession(
        [("basketball_nba", datetime.now(timezone.utc) - timedelta(minutes=5), True)],
        [],
    )

    async def _commit():
        calls.append("commit")

    session.commit = _commit

    async def _stale(_session):
        calls.append("stale")
        return {"closed": 1, "suspended": 0}

    async def _ei(_session):
        calls.append("ei")
        return 0

    service = MagicMock()
    service.get_odds = AsyncMock(return_value=[])
    service.get_scores = AsyncMock(return_value=[])
    service.close = AsyncMock()
    service.last_requests_remaining = None
    service.last_requests_used = None

    class _CM:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_a):
            return False

    with patch("app.tasks.odds_polling.check_quota_guard", return_value=(True, "ok_600000")), \
            patch("app.tasks.odds_polling.OddsAPIService", return_value=service), \
            patch("app.tasks.odds_polling.get_redis_client",
                  return_value=_FakeRedis(time.time() - 100.0)), \
            patch("app.tasks.odds_polling.get_task_session", return_value=_CM()), \
            patch("app.tasks.odds_polling.detect_and_close_stale_events", _stale), \
            patch("app.tasks.odds_polling.update_poll_state", MagicMock()), \
            patch("app.tasks.excitement_index.update_live_ei", _ei):
        await odds_polling._poll_all_odds()
    return calls


async def test_the_stale_event_writes_are_committed_before_live_ei_runs():
    calls = await _run_pass()

    assert "stale" in calls and "ei" in calls, calls
    after_stale = calls[calls.index("stale") + 1:]
    assert after_stale[: after_stale.index("ei")] == ["commit"], calls
