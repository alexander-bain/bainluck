"""#12042: worker-background logs one memory line per task, so a spike names its task.

Nov 10 (16:04-17:14Z): worker-background (512 MB) was above 95% of quota in 78 of
208 runtime samples and peaked at 1,001 MB (518 MB swap) while two long tasks
overlapped; a window could not say which grew. Each task now logs its child's RSS
at start, at end, and its peak during the task (VmHWM reset at the start).
"""
import inspect
import logging

import pytest

from app import tasks as tasks_pkg
from app.tasks import task_memory as tm


@pytest.fixture
def fake_proc(monkeypatch):
    state = {"rss": 180.0, "peak": 950.0, "resets": 0}
    monkeypatch.setattr(tm, "rss_mb", lambda: state["rss"])
    monkeypatch.setattr(tm, "peak_rss_mb", lambda: state["peak"])

    def reset():
        state["resets"] += 1
        state["peak"] = state["rss"]
        return True

    monkeypatch.setattr(tm, "reset_peak", reset)
    tm._started.clear()
    return state


def test_a_worker_background_task_logs_start_end_and_its_own_peak(monkeypatch, fake_proc, caplog):
    monkeypatch.setenv("DYNO", "worker-background.1")
    with caplog.at_level(logging.INFO, logger=tm.__name__):
        tm.task_started("t1")
        assert fake_proc["resets"] == 1  # the earlier 950 MB peak is not this task's
        fake_proc["peak"], fake_proc["rss"] = 612.0, 240.0
        tm.task_finished("t1", "app.tasks.precompute_category_pages")
    line = caplog.records[-1].getMessage()
    assert line.startswith("task_memory task=app.tasks.precompute_category_pages ")
    assert "rss_start_mb=180.0" in line and "rss_end_mb=240.0" in line and "peak_mb=612.0" in line
    assert tm._started == {}


@pytest.mark.parametrize("dyno", ["web.1", "worker-realtime.1", "worker-heavy.1", ""])
def test_other_dynos_log_nothing(monkeypatch, fake_proc, caplog, dyno):
    monkeypatch.setenv("DYNO", dyno)
    with caplog.at_level(logging.INFO, logger=tm.__name__):
        tm.task_started("t1")
        tm.task_finished("t1", "x")
    assert not [r for r in caplog.records if "task_memory" in r.getMessage()]
    assert fake_proc["resets"] == 0


def test_a_finish_without_a_start_still_logs_with_an_unknown_start(monkeypatch, fake_proc, caplog):
    monkeypatch.setenv("DYNO", "worker-background.1")
    with caplog.at_level(logging.INFO, logger=tm.__name__):
        tm.task_finished("never-started", "x")
    assert "rss_start_mb=None" in caplog.records[-1].getMessage()


def test_instrumentation_never_raises(monkeypatch):
    monkeypatch.setenv("DYNO", "worker-background.1")
    def boom():
        raise RuntimeError("no /proc")
    monkeypatch.setattr(tm, "rss_mb", boom)
    tm.task_started("t1")
    tm.task_finished("t1", "x")


def test_reset_peak_is_false_where_proc_is_missing(monkeypatch):
    import builtins
    real_open = builtins.open
    def fake_open(path, *a, **k):
        if str(path) == "/proc/self/clear_refs":
            raise FileNotFoundError(path)
        return real_open(path, *a, **k)
    monkeypatch.setattr(builtins, "open", fake_open)
    assert tm.reset_peak() is False


def test_the_worker_signals_are_wired():
    src = inspect.getsource(tasks_pkg)
    assert "task_memory.task_started(task_id)" in src
    assert "task_memory.task_finished(task_id" in src
