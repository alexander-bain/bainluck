import asyncio, sys, types
from app.utils import clock_bridge as cb
from app.utils.pm_stage_trace import PMStageTrace


class Recorder:
    def __init__(self):
        self.calls = []

    def armed(self, role, window_left_s):
        self.calls.append((role, round(window_left_s, 3)))


def test_pm_mapped_at_start_but_unmapped_at_armed_never_bridges(monkeypatch):
    recorder = Recorder()
    monkeypatch.setattr(cb, "_BRIDGE", recorder)
    t = [0.0]
    wall, mono = (lambda: 1_000_000.0 + t[0]), (lambda: 500.0 + t[0])
    event_of = {11: 1}
    env = {"WS_PM_TRACE_EVENT": "1", "WS_PM_TRACE_OUTCOMES": "11",
           "WS_PM_TRACE_ARM_AT": str(wall() + 60), "WS_PM_TRACE_EXPIRES_AT": str(wall() + 360)}
    trace = PMStageTrace.from_env(env, run="r", event_of=event_of, wall=wall, mono=mono,
                                  emit=lambda record: None)
    cb.attach(trace, "polymarket")
    assert trace is not None and not trace.stopped
    event_of[11] = 2  # the slate moved the outcome before ARMED
    t[0] = 61.0
    assert not trace.active() and trace.stopped
    assert recorder.calls == []


def test_the_bridge_connection_carries_the_150ms_server_statement_timeout(monkeypatch):
    seen = {}

    async def connect(dsn, **kwargs):
        seen.update(kwargs, dsn=dsn)
        return object()

    monkeypatch.setitem(sys.modules, "asyncpg", types.SimpleNamespace(connect=connect))
    asyncio.run(cb._connect({"DATABASE_URL": "postgres://u:p@db.example/d"}))
    assert seen["server_settings"]["statement_timeout"] == "150"
    assert seen["timeout"] == cb.CONNECT_TIMEOUT_S and seen["ssl"] == "require"
