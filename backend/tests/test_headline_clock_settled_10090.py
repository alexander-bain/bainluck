"""#10090 headline clock: a waiting input whose game a read now sees finished.

Alex 2026-10-31: "If there's no valid price to show, I won't count that as a
miss. It's a miss if we have unnecessary delays." A venue tick received after
the game's recorded end has no live headline to move (the page shows the
result), so it leaves the clock and is counted as ``settled=``. A tick received
before the end was a real wait: it ends at the read that saw the end, at its
full age. Specimen: 07:06Z 11/01, a J-League Kalshi tick 28 s after full time
sat 91 s and was reported as ``late:mutate_read_required``.
"""

import time
from datetime import datetime, timezone
from types import SimpleNamespace

from app.tasks import live_blend_refresh as module
from app.tasks.live_blend_refresh import LiveBlendRefresher

MONO = 1000.0


def _refresher(monkeypatch):
    monkeypatch.setattr(module, "_mono", lambda: MONO)
    return LiveBlendRefresher("kalshi")


def _read(eid, *, status="completed", ended_ago=None):
    """What `_read_groups` hands on: the event row as the read saw it."""
    ended = (None if ended_ago is None
             else datetime.fromtimestamp(time.time() - ended_ago, timezone.utc))
    return {eid: (SimpleNamespace(id=eid, status=status, completed_at=ended), [])}


def test_an_input_received_after_full_time_leaves_the_clock(monkeypatch):
    r = _refresher(monkeypatch)
    r._hl_pending[1] = [MONO - 3.0, "mutate_read_required", None, 1]

    r._hl_settle_finished(_read(1, ended_ago=31.0))

    assert r._hl_pending == {}
    assert r._hl_summary() == "n=0 late=0 settled=1"


def test_an_input_received_before_full_time_is_a_wait_ended_at_the_read(monkeypatch):
    r = _refresher(monkeypatch)
    r._hl_pending[1] = [MONO - 40.0, "mutate_read_required", None, 1]

    r._hl_settle_finished(_read(1, ended_ago=10.0))

    assert r._hl_pending == {}
    line = r._hl_summary()
    assert "max_ms=40000 worst=1:40000:mutate_read_required>stamp_settled[f-,a1]" in line
    assert line.endswith("late=0 settled=0")


def test_a_finished_status_without_an_end_time_is_counted(monkeypatch):
    """No recorded end, nothing to compare: the wait counts at its age."""
    r = _refresher(monkeypatch)
    r._hl_pending[1] = [MONO - 2.0, "na_proof", None, 2]

    r._hl_settle_finished(_read(1, status="final"))

    assert "worst=1:2000:na_proof>stamp_settled[f-,a2]" in r._hl_summary()


def test_a_live_event_is_untouched(monkeypatch):
    r = _refresher(monkeypatch)
    entry = [MONO - 3.0, "receipt", None, 1]
    r._hl_pending[1] = entry

    r._hl_settle_finished(_read(1, status="live"))

    assert r._hl_pending == {1: entry}
    assert r._hl_summary() == "n=0 late=0 settled=0"


def test_the_read_path_settles_before_it_returns():
    """Wired into `_read_groups` (every read, not only preview-ticket reads)."""
    import inspect

    source = inspect.getsource(LiveBlendRefresher._read_groups)
    assert "self._hl_settle_finished(grouped)" in source
    assert source.index("self._hl_settle_finished(grouped)") < source.index(
        "if preview_ticket is not None:")
