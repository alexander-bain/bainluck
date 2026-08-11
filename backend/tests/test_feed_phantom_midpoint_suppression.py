"""Guard: a price nobody will trade at never reaches a Discover card (#1574, UX-P011).

The pure rule is unit-tested in ``test_feed_market_quality.py``. This file drives the
REAL ``_score_futures`` so the wiring is covered too — the load_only allow-list, the
``group_type`` read, and the placement of the strip BEFORE leader selection. Every book
below is a production row read on 2026-08-07.

Both directions per gotcha #43: the phantom cards go AND the healthy cards stay.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes.feed import _score_futures
from app.utils.personalization import PersonalizationContext


class _Outcome:
    def __init__(self, id, name, prob, *, bid=None, ask=None):
        self.id = id
        self.name = name
        self.current_probability = prob
        self.probability_change_24h = 0.0
        self.opening_probability = None
        self.rank = None
        self.rank_change_24h = None
        self.team_id = None
        self.calibration_probability = None
        self.current_yes_bid = bid
        self.current_yes_ask = ask


def _stable_now() -> datetime:
    """Midday UTC today — NEVER a bare ``datetime.now()``. Gotcha #44.

    These tests seed ``commence_time`` at ``now - 1 day`` and read back a
    DATE token. Seeded from the real clock, that token flips the moment the
    run crosses UTC midnight, so the suite went green all afternoon Pacific
    and red every evening from 17:00 PT — a nightly deploy landmine that CI
    (which mostly runs earlier in the UTC day) almost never saw.

    Found by INT-037 at 00:12 UTC: 3 failures on pure ``origin/master`` with
    no local changes, while master's own CI was green. Shifting the clock 6h
    back made all 5 pass, which is the proof.

    Pinning the HOUR keeps every relative offset inside one UTC day whatever
    time the suite runs.
    """
    anchor = datetime.now(timezone.utc).replace(
        hour=12, minute=0, second=0, microsecond=0
    )
    # Must always be in the PAST: the production scorer reads the real clock and
    # compares against these seeds, so a noon anchor taken at 00:12 UTC would sit
    # twelve hours in the future and drop the card for a different reason.
    if anchor > datetime.now(timezone.utc):
        anchor -= timedelta(days=1)
    return anchor


class _Market:
    """A real object (not MagicMock) so ``__dict__.get(...)`` reads work."""

    def __init__(self, id, name, category, outcomes, *, group_type=None):
        now = _stable_now()
        self.id = id
        self.name = name
        self.source = "polymarket"
        self.external_id = f"poly-{id}"
        self.sport_id = None
        self.sport = None
        self.category = category
        self.llm_sport_category = category
        self.market_tier = 1
        self.canonical_market_key = None
        self.group_id = None
        self.group_type = group_type
        self.image_url = None
        self.hook_description = None
        self.hook_generated_at = None
        self.hook_leader_at_generation = None
        self.market_metadata = {}
        self.curation_score_adj = 0
        self.volume_24h = 250000
        self.updated_at = now
        self.commence_time = now - timedelta(days=1)
        # Far out so the title-implied staleness calendar can't fire.
        self.resolution_date = now + timedelta(days=120)
        self.status = "open"
        self.created_at = now - timedelta(days=10)
        self.llm_league = None
        self.llm_gender = None
        self.llm_level = None
        self.outcomes = outcomes


def _mock_db(markets):
    db = AsyncMock()

    def make_result(*a, **k):
        r = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = [m.id for m in markets]
        unique = MagicMock()
        unique.all.return_value = markets
        scalars.unique.return_value = unique
        r.scalars.return_value = scalars
        r.all.return_value = []
        return r

    db.execute = AsyncMock(side_effect=make_result)
    return db


async def _run(markets):
    with (
        patch(
            "app.routes.feed._external_curator_recall_market_ids",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.tasks.redis_state.get_async_redis_client",
            side_effect=Exception("no redis in test"),
        ),
    ):
        now = _stable_now()
        ctx = PersonalizationContext()
        items = await _score_futures(_mock_db(markets), now, None, ctx)
    return items


def _ids(items):
    return {i["data"]["id"] for i in items if i["type"] == "futures"}


def _card(items, market_id):
    for i in items:
        if i["type"] == "futures" and i["data"]["id"] == market_id:
            return i["data"]
    return None


# --- specimens ---------------------------------------------------------------


def _spacex():
    # 57782305: 16 rungs, every book quoted 1c/99c -> a confident-looking 50%.
    outs = [
        _Outcome(1000 + n, f"threshold {n}", 0.5, bid=0.01, ask=0.99)
        for n in range(15)
    ]
    outs.append(_Outcome(1099, "No", 0.5))
    return _Market(
        57782305, "What will SpaceX (SPCX) hit Week of August 3 2026?",
        "economics", outs, group_type="polymarket_event",
    )


def _oscars():
    # 58492238: five phantoms ranked ABOVE the genuinely-priced 14% leader.
    outs = [
        _Outcome(2001, "Wild Horse Nine", 0.425, bid=0.03, ask=0.82),
        _Outcome(2002, "Digger", 0.425, bid=0.04, ask=0.81),
        _Outcome(2003, "The Black Ball", 0.415, bid=0.02, ask=0.81),
        _Outcome(2004, "Dune: Part Three", 0.355, bid=0.02, ask=0.69),
        _Outcome(2005, "Michael", 0.355, bid=0.03, ask=0.68),
        _Outcome(2006, "The Odyssey", 0.14, bid=0.10, ask=0.18),
        _Outcome(2007, "UNABOMBER", 0.07, bid=0.04, ask=0.10),
        _Outcome(2008, "Being Heumann", 0.065, bid=0.03, ask=0.10),
    ]
    return _Market(
        58492238, "Oscars 2027: Best Casting Winner",
        "entertainment", outs, group_type="negrisk",
    )


def _nvidia():
    # 57782674: a genuinely well-priced CUMULATIVE ladder with ONE bad rung.
    outs = [
        _Outcome(3001, "up 200", 0.845, bid=0.81, ask=0.88),
        _Outcome(3002, "up 204", 0.735, bid=0.48, ask=0.99),   # the phantom
        _Outcome(3003, "down 196", 0.73, bid=0.70, ask=0.76),
        _Outcome(3004, "down 192", 0.465, bid=0.43, ask=0.50),
        _Outcome(3005, "up 208", 0.285, bid=0.25, ask=0.32),
        _Outcome(3006, "down 188", 0.255, bid=0.22, ask=0.29),
    ]
    return _Market(
        57782674, "What will NVIDIA (NVDA) hit Week of August 3 2026?",
        "economics", outs, group_type="polymarket_event",
    )


def _fed():
    # 20570794: the healthy negRisk control — a tight book that sums to ~100%.
    outs = [
        _Outcome(4001, "No change", 0.56, bid=0.55, ask=0.57),
        _Outcome(4002, "25 bps increase", 0.385, bid=0.37, ask=0.40),
        _Outcome(4003, "25 bps decrease", 0.0605, bid=0.058, ask=0.063),
    ]
    return _Market(
        20570794, "Fed decision in September?", "economics", outs,
        group_type="negrisk",
    )


def _golf():
    # No order book at all (DataGolf model price) — survives by construction.
    outs = [
        _Outcome(5001, "Ben James", 0.842),
        _Outcome(5002, "Doug Ghim", 0.746),
        _Outcome(5003, "Jordan Smith", 0.718),
    ]
    return _Market(58036836, "PGA Championship top 10?", "sports", outs)


# --- suppress ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_spacex_all_fifty_percent_card_never_reaches_the_feed():
    items = await _run([_spacex(), _fed()])
    assert 57782305 not in _ids(items)


@pytest.mark.asyncio
async def test_gapped_exclusive_ladder_never_reaches_the_feed():
    # Alex ruling 2026-08-07: survivors totalling 59.5% are still a gapped partition.
    items = await _run([_oscars(), _fed()])
    assert 58492238 not in _ids(items)


# --- keep (gotcha #43: the flood is capped AND the neighbour stays populated) --


@pytest.mark.asyncio
async def test_healthy_cards_survive_alongside_the_suppressed_ones():
    items = await _run([_spacex(), _oscars(), _fed(), _golf(), _nvidia()])
    ids = _ids(items)
    assert 57782305 not in ids
    assert 58492238 not in ids
    # The whole point of the both-direction guard: the surface stays populated.
    assert 20570794 in ids, "healthy Fed ladder was suppressed"
    assert 58036836 in ids, "model-priced golf field was suppressed"
    assert 57782674 in ids, "healthy NVIDIA ladder was suppressed"


@pytest.mark.asyncio
async def test_nvidia_keeps_its_card_and_drops_only_the_phantom_rung():
    items = await _run([_nvidia(), _fed()])
    card = _card(items, 57782674)
    assert card is not None
    shown = {o["name"] for o in card["top_outcomes"]}
    assert "up 204" not in shown, "the 48c/99c phantom rung is still being shown"
    assert "up 200" in shown, "the real 0.845 leader was dropped"


@pytest.mark.asyncio
async def test_phantoms_are_stripped_before_the_leader_is_chosen():
    """The defect was not only wrong numbers — the phantoms OUTRANKED the real
    prices, so the card named the wrong leader. If the strip ever moves after
    leader selection this goes red while every other test still passes."""
    nvidia = _nvidia()
    items = await _run([nvidia, _fed()])
    card = _card(items, 57782674)
    assert card is not None
    assert card["top_outcomes"][0]["name"] == "up 200"
