"""Venue-refuted props retain prices without holding a complete WIN question."""

import asyncio

import pytest

from app.tasks.polymarket_ws import _PMHeadlineEvents, pm_non_speaking_metadata
from app.utils.content_understanding import CONTENT_UNDERSTANDING_KEY
from tests.test_polymarket_withdrawal_speed_10651 import rig


def metadata(label):
    return {CONTENT_UNDERSTANDING_KEY: {
        "v": 1, "venue_type": label, "semantic_type": "other",
    }}


def test_only_present_authoritative_venue_refutations_exclude():
    for label in ("spreads", "totals", "child_moneyline", "tennis_completed_match"):
        assert pm_non_speaking_metadata(metadata(label))
    for data in (None, {}, metadata(None), metadata(""), metadata("moneyline")):
        assert not pm_non_speaking_metadata(data)
    future = metadata("totals")
    future[CONTENT_UNDERSTANDING_KEY]["v"] = 999
    assert not pm_non_speaking_metadata(future)


@pytest.mark.asyncio
async def test_complete_winner_stamps_before_known_prop_and_unknown_stays_joined():
    for data in (metadata("totals"), {}, metadata("moneyline")):
        x = rig(mapping={1: 10, 2: 10, 900: 10}, books={})
        x.ns["open_outcome_ids"].discard(900)  # known prop is a slate leg
        if pm_non_speaking_metadata(data):
            x.ns["non_blend_outcome_ids"].add(900)
        # Large ordinary chunk would have joined winner and prop; the source
        # must deliberately separate their transaction boundaries.
        x.ns["FLUSH_CHUNK_ROWS"] = 500
        task = asyncio.create_task(x.ns["flush_prices"]())
        try:
            await asyncio.wait_for(x.entered.wait(), 1)
            if pm_non_speaking_metadata(data):
                assert ("write", [1, 2]) in x.trace
                assert ("refresh", [10]) in x.trace
                assert set(x.ns["price_buffer"]) == {900}
            else:
                assert ("refresh", [10]) not in x.trace
                assert set(x.ns["price_buffer"]) == {1, 2, 900}
            assert not task.done()
        finally:
            x.release.set()
            assert await asyncio.wait_for(task, 1)
        assert not x.ns["price_buffer"]
        assert x.trace.count(("refresh", [10])) == 1


@pytest.mark.asyncio
async def test_final_drain_keeps_original_full_cohort():
    x = rig(mapping={1: 10, 2: 10, 900: 10}, books={})
    x.ns["open_outcome_ids"].discard(900)
    x.ns["non_blend_outcome_ids"].add(900)
    x.ns["FLUSH_CHUNK_ROWS"] = 500
    task = asyncio.create_task(x.ns["flush_prices"](final=True))
    try:
        await asyncio.wait_for(x.entered.wait(), 1)
        assert ("write", [1, 2, 900]) in x.trace
        assert ("refresh", [10]) not in x.trace
    finally:
        x.release.set()
        assert await asyncio.wait_for(task, 1)
    assert x.marks == [1, 2, 900]


@pytest.mark.asyncio
async def test_known_prop_complements_keep_their_whole_transaction():
    x = rig(batch={1: 0.6, 2: 0.4, 900: 0.2, 901: 0.8},
            mapping={1: 10, 2: 10, 900: 10, 901: 10}, books={})
    x.ns["non_blend_outcome_ids"].update({900, 901})
    x.ns["open_outcome_ids"].difference_update({900, 901})
    x.ns["open_complement_of"].update({900: 901, 901: 900})
    x.ns["FLUSH_CHUNK_ROWS"] = 1
    task = asyncio.create_task(x.ns["flush_prices"]())
    try:
        await asyncio.wait_for(x.entered.wait(), 1)
        assert ("write", [1, 2]) in x.trace
        assert ("refresh", [10]) in x.trace
        assert ("write", [900, 901]) in x.trace
        assert set(x.ns["price_buffer"]) == {900, 901}
    finally:
        x.release.set()
        assert await asyncio.wait_for(task, 1)
    assert not x.ns["price_buffer"]


@pytest.mark.asyncio
async def test_prop_withdrawal_retains_existing_event_fence():
    x = rig(mapping={1: 10, 2: 10, 900: 10}, books={900: (0.2, 0.8)})
    x.ns["non_blend_outcome_ids"].add(900)
    x.release.set()
    assert await x.ns["flush_prices"]()
    assert x.trace.index(("withdraw", [900])) < x.trace.index(("refresh", [10]))
    assert not x.books


def test_owner_view_tracks_late_identity_and_exclusion_changes():
    events, excluded = {1: 10, 2: 10, 900: 10}, {900}
    view = _PMHeadlineEvents(events, excluded)
    assert dict(view) == {1: 10, 2: 10}
    events[901] = 90  # unknown late winner admission remains speaking
    excluded.remove(900)
    assert view[901] == 90 and view[900] == 10
