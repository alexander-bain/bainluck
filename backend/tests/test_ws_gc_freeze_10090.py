"""#10090 — the Polymarket process freezes its long-lived heap at each handover.

`app/utils/ws_gc.py`: production's Polymarket process ran 26-35 full
collections per 2-minute heartbeat at up to 0.3-0.6 s each (10/30 12:33Z+).
These pin what the refreeze promises: survivors are frozen, cyclic garbage the
previous freeze held is reclaimed by the next one, the switch releases a held
freeze, it never raises, and the consumer renews it at both catalog
installations (initial, then every handover) before its heap trim.
"""

import gc
import logging
import re
import weakref
from pathlib import Path

import pytest

from app.utils import ws_gc
from app.utils.ws_gc import GC_FREEZE_ENV, refreeze_long_lived

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _thaw():
    yield
    gc.unfreeze()


class _Node:
    pass


def _cycle():
    a, b = _Node(), _Node()
    a.other, b.other = b, a
    return a, weakref.ref(a)


def test_survivors_are_frozen(monkeypatch):
    monkeypatch.delenv(GC_FREEZE_ENV, raising=False)
    keep = [_Node() for _ in range(100)]
    frozen = refreeze_long_lived("polymarket")
    assert frozen == gc.get_freeze_count() and frozen >= len(keep)
    assert not any(obj is keep[0] for obj in gc.get_objects())  # out of every generation


def test_a_cycle_frozen_alive_is_reclaimed_by_the_next_refreeze(monkeypatch):
    monkeypatch.delenv(GC_FREEZE_ENV, raising=False)
    node, ref = _cycle()
    refreeze_long_lived("polymarket")
    del node
    gc.collect()
    assert ref() is not None  # frozen: no collection walks it (the bounded hold)
    refreeze_long_lived("polymarket")
    assert ref() is None  # the next handover's full collection reclaims it


def test_freed_objects_are_freed_while_frozen(monkeypatch):
    monkeypatch.delenv(GC_FREEZE_ENV, raising=False)
    node = _Node()
    ref = weakref.ref(node)
    refreeze_long_lived("polymarket")
    del node  # no cycle: reference counting frees it, freeze or not
    assert ref() is None


def test_the_switch_releases_a_held_freeze(monkeypatch, caplog):
    monkeypatch.delenv(GC_FREEZE_ENV, raising=False)
    assert refreeze_long_lived("polymarket")
    monkeypatch.setenv(GC_FREEZE_ENV, "0")
    with caplog.at_level(logging.INFO, logger=ws_gc.__name__):
        assert refreeze_long_lived("polymarket") is None
    assert gc.get_freeze_count() == 0
    assert "released (turned off)" in caplog.text
    assert refreeze_long_lived("polymarket") is None  # off and nothing held: no-op


def test_it_logs_its_receipt(monkeypatch, caplog):
    monkeypatch.delenv(GC_FREEZE_ENV, raising=False)
    with caplog.at_level(logging.INFO, logger=ws_gc.__name__):
        refreeze_long_lived("polymarket")
    assert re.search(r"worker-ws gc freeze: arm=polymarket frozen=\d+ collected=\d+ took=\d+ms",
                     caplog.text)


def test_a_failing_collector_never_raises_into_the_consumer(monkeypatch, caplog):
    monkeypatch.delenv(GC_FREEZE_ENV, raising=False)

    def boom():
        raise RuntimeError("collector")

    monkeypatch.setattr(gc, "collect", boom)
    with caplog.at_level(logging.WARNING, logger=ws_gc.__name__):
        assert refreeze_long_lived("polymarket") is None
    assert "worker-ws gc freeze failed" in caplog.text


def test_the_consumer_refreezes_at_both_catalog_installations_before_its_trim():
    source = (BACKEND / "app" / "tasks" / "polymarket_ws.py").read_text()
    handover = source.index('release_free_heap("polymarket")')
    assert source.rfind('refreeze_long_lived("polymarket")', 0, handover) > source.rfind(
        "await refresh_catalog(", 0, handover
    ), "every handover refreezes after installing the catalog, before the trim"
    initial = source.index('_PMCatalogHandoverTiming("initial"')
    nxt = source.index("\n    admission_task = asyncio.create_task(admit_open_contracts())", initial)
    assert 'refreeze("polymarket")' in source[initial:nxt], (
        "the initial catalog is frozen when it is installed"
    )
    # Only the Polymarket consumer: the Kalshi process runs 2-5 full collections.
    assert "refreeze_long_lived" not in (BACKEND / "app" / "tasks" / "kalshi_ws.py").read_text()
