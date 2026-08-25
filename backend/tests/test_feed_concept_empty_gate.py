"""Q407 Item 3 — a concept card that cannot show a probability must not ship.

## The defect this pins

Both surfaces already refuse an empty concept envelope:
`DiscoverViewModel.suppressionReason` (iOS) and `feedItemSuppressionReason`
(`frontend/components/discover/utils.ts`) each return ``empty_concept`` for a
concept with no usable leader and no nameable result. The SERVER had no such
gate, so `_score_event_concepts` kept emitting them.

A card both clients drop is not a harmless no-op — it is a **page slot spent on
nothing**. Measured on production 2026-08-24 at `limit=50&offset=50`:

    {"type": "concept", "score": 54, "reason": "5 fights on the card",
     "headline": "Today",
     "data": {"key": "event:ufc:26aug25",
              "name": "Mario Piazzon vs Guilherme Uriel", "domain": "ufc",
              "status": "upcoming", "fight_count": 5, "entry_count": 0,
              "is_marquee": false, "marquee_whathit": false}}

No `leader`, no `winner`, no `result_summary` — a bare tile carrying a name and
a fight count, ranked third on its page.

## Why it is driven through the live path

`test_concept_leader_warm_population.py` owns the positive acceptance (warm
leaders come back out and every card is renderable). This file owns the
negative: a concept whose leader CANNOT be resolved must not reach the page at
all. Both are driven through the real `_score_event_concepts` and graded with
the same pinned predicate the surfaces use (`feed_item_is_renderable`), because
#1948's lesson was that each half can be individually correct while the join
still leaks.
"""

import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest


LEADERFUL_KEY = "event:ufc:26aug20"
LEADERLESS_KEY = "event:ufc:26aug25"


def _harness(now, warm_keys):
    """Build the lister/redis patches for a concept set with warm `warm_keys`."""
    from app.utils.event_concept_cache import stamp_envelope

    envelopes = {
        key: [
            {"name": "Joshua Van", "probability": 0.5217},
            {"name": "Alexandre Pantoja", "probability": 0.4783},
        ]
        for key in warm_keys
    }
    warm = {
        key: json.dumps(
            stamp_envelope(
                {"primary": {"kind": "winner_field", "competitors": comps}},
                created_at=now,
                lifecycle_watermark=None,
            ),
            default=str,
        )
        for key, comps in envelopes.items()
    }

    async def ufc(db, statuses=None, limit=None):
        # Both concepts are otherwise identical and both score > 0. The ONLY
        # difference between them is whether a leader can be resolved, so a
        # difference in the output can be attributed to nothing else.
        return [
            {
                "key": k,
                "name": k,
                "domain": "ufc",
                "status": "upcoming",
                "start_date": "2026-08-20",
                "is_major": True,
                "fight_count": 5,
                "latest_commence": now,
            }
            for k in (LEADERFUL_KEY, LEADERLESS_KEY)
        ]

    async def empty(db, statuses=None, limit=None):
        return []

    class _Client:
        def _lookup(self, k):
            base = k[: -len(":stale")] if k.endswith(":stale") else k
            for key, raw in warm.items():
                if base.endswith(key):
                    return raw
            return None

        async def get(self, k):
            return self._lookup(k)

        async def mget(self, keys):
            return [self._lookup(k) for k in keys]

    async def _shared():
        return _Client()

    async def _bounded(fn):
        value = await fn()

        class _R:
            is_ok = True

        _R.value = value
        return _R

    return ufc, empty, _shared, _bounded


async def _run(warm_keys):
    from app.routes import feed as feed_mod
    import app.utils.request_cache as rc

    now = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)
    ufc, empty, _shared, _bounded = _harness(now, warm_keys)

    with (
        patch("app.utils.event_ufc.list_ufc_card_concepts", ufc),
        patch("app.utils.event_f1.list_f1_gp_concepts", empty),
        patch("app.utils.event_cycling.list_cycling_concepts", empty),
        patch.object(rc, "get_shared_async_redis", _shared),
        patch.object(rc, "bounded_redis_call", _bounded),
    ):
        return await feed_mod._score_event_concepts(None, now, None)


@pytest.mark.asyncio
async def test_a_concept_with_no_leader_never_reaches_the_page():
    """The production specimen: no leader, not settled → must not be emitted."""
    cards = await _run(warm_keys=[LEADERFUL_KEY])

    keys = [c["data"]["key"] for c in cards]
    assert LEADERLESS_KEY not in keys, (
        f"{LEADERLESS_KEY} has no resolvable leader and is not in a WHAT-HIT "
        f"window, so BOTH surfaces return `empty_concept` for it — the server "
        f"must not spend a page slot shipping it. Emitted: {keys}"
    )
    # The gate must be a scalpel, not a scythe: the sibling that CAN answer
    # something is still served. A gate that drops both would "fix" the empty
    # card by emptying the feed, which is the failure mode being reported.
    assert LEADERFUL_KEY in keys, (
        f"the leaderful sibling was dropped too — the gate is over-filtering. "
        f"Emitted: {keys}"
    )


@pytest.mark.asyncio
async def test_every_emitted_concept_card_passes_the_surfaces_own_predicate():
    """Grade the real output with the pinned mirror both clients implement."""
    from app.tasks.flow_sentinel import feed_item_is_renderable

    cards = await _run(warm_keys=[LEADERFUL_KEY])

    suppressed = [c for c in cards if not feed_item_is_renderable(c)]
    assert suppressed == [], (
        f"{len(suppressed)} emitted concept card(s) would be dropped by BOTH "
        f"surfaces — every one is a page slot spent on a card no user can see: "
        f"{[c['data']['key'] for c in suppressed]}"
    )


@pytest.mark.asyncio
async def test_the_gate_does_not_fire_when_every_leader_is_warm():
    """Control: with both leaders warm, both cards ship. Pins the negative."""
    cards = await _run(warm_keys=[LEADERFUL_KEY, LEADERLESS_KEY])

    keys = sorted(c["data"]["key"] for c in cards)
    assert keys == sorted([LEADERFUL_KEY, LEADERLESS_KEY]), (
        f"both concepts have a usable leader, so the gate must admit both — "
        f"otherwise it is suppressing on something other than renderability. "
        f"Emitted: {keys}"
    )
