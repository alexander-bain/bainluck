"""Default DNPL scope reaches PM's executed price-chunk custody boundary."""

import pytest

from app.tasks.live_blend_refresh import LiveBlendRefresher
from app.utils.blend_preview import PreviewEventScope
from tests.test_pm_quote_lock_bound_10090 import writer_rig
from tests.test_ws_flush_cadence_10090 import _FakeTime


@pytest.mark.parametrize("event_id", [10, 15334205])
async def test_price_chunk_records_default_scope_write_custody(monkeypatch, event_id):
    clock = _FakeTime(monkeypatch, t=1000)
    r, state = writer_rig(
        clock, batch={1: .6, 2: .4}, mapping={1: event_id, 2: event_id}, books={},
    )
    state.held = False
    # Keep this rig's isolated persistence and stamp witnesses, but obtain
    # eligibility exactly as a newly constructed production worker does.
    scope = LiveBlendRefresher("polymarket").preview_events
    assert isinstance(scope, PreviewEventScope)
    with pytest.raises(TypeError):
        iter(scope)
    r.ns["blend_refresher"].preview_events = scope
    r.ns.update(observation_continuity={}, routing_generation=0)
    boundary = r.ns["catalog_boundary"]
    write = r.ns["write_chunk"]
    seen = []

    async def witnessed_write(*args, **kwargs):
        seen.append((set(boundary.observation_writing),
                     dict(boundary.observation_write_epoch)))
        return await write(*args, **kwargs)

    r.ns["write_chunk"] = witnessed_write
    assert await r.ns["flush_prices"](flush_started=1000)
    assert seen == [({event_id}, {event_id: 1})]
    assert state.commits == [1, 2]
    # The observation-drain wrapper's finally clears custody; this extracted
    # rig bypasses that wrapper and executes the price chunk and stamp only.
