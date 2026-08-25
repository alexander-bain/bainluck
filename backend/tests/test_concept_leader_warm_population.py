"""#1948 — the concept tier went dark, and the warm list is why.

THE INCIDENT, so these tests cannot be "simplified" back into the bug.

UX-P089 (#1934) made `_resolve_concept_leader` cache-only. That was correct: its
cold-build fallback was 10.08s of an 11.71s feed against a 6s client budget. But
the only writer of that cache was `warm_event_concepts`, and its population was a
hand-written tuple of FOUR GOLF MAJORS. So every non-golf concept resolved to no
leader, and `leader is None` is the suppress state on both surfaces — all nine
concept cards on the first page were dropped by iOS and by web, in the same
integration that shipped web's renderer for exactly those cards (#1939).

Measured on production 2026-08-17 at master `522caea4`, BEFORE this fix:

    GET /api/feed?limit=50   →  4 concept cards, every one with no `leader` key
    GET /api/event/event:cycling:vuelta-2026
                             →  30 competitors, Tadej Pogačar 0.751

The probability was RIGHT THERE, one Redis key away, and the feed shipped a
directory entry instead.

The fix is not a longer hand-written list — that re-arms the same trap for the
next domain. It is that the warmer consumes the FEED'S OWN enumeration
(`app/utils/event_concept_population.py`), so the warm population and the leader
population are one function and cannot drift.
"""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest

from app.config.event_concept_warm_keys import WARM_CONCEPT_KEYS
from app.tasks import event_concept_warmer as warmer
from app.utils import event_concept_population as population

# The Vuelta specimen, verbatim from the production envelope that was being
# ignored. Kept as data so the number in the assertion is the number that was
# measured, not one invented to make a test pass.
VUELTA_KEY = "event:cycling:vuelta-2026"
VUELTA_LEADER = "Tadej Pogacar"
VUELTA_PROBABILITY = 0.751
VUELTA_FIELD_SIZE = 30

# The four UFC cards on the same production page, all suppressed.
UFC_KEYS = (
    "event:ufc:26aug19",
    "event:ufc:26aug20",
    "event:ufc:26aug22",
    "event:ufc:26aug23",
)


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, bytes] = {}

    def get(self, k):
        return self.store.get(k)

    def set(self, k, v, nx=False, ex=None):
        if nx and k in self.store:
            return None
        self.store[k] = v.encode() if isinstance(v, str) else v
        return True

    def setex(self, k, ttl, v):
        self.store[k] = v.encode() if isinstance(v, str) else v

    def delete(self, k):
        return int(self.store.pop(k, None) is not None)

    def eval(self, script, numkeys, *args):
        key, token = args[0], args[1]
        expected = token.encode() if isinstance(token, str) else token
        if self.store.get(key) == expected:
            self.store.pop(key, None)
            return 1
        return 0


@asynccontextmanager
async def _fake_session():
    yield object()


def _concept(key, status="upcoming"):
    return {"key": key, "name": key, "domain": key.split(":")[1], "status": status}


# ---------------------------------------------------------------------------
# The population itself
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_unsettled_population_is_every_unsettled_concept_not_four_golf_majors():
    """THE REGRESSION, stated as one assertion.

    The Vuelta and the four UFC cards must all be in the population the warmer
    walks. Before #1948 the answer for every one of them was "no" — the
    population was `("event:golf:the-open-championship", "event:golf:the-masters",
    "event:golf:u-s-open", "event:golf:pga-championship")` and nothing else.
    """

    async def ufc(db, statuses=None, limit=None):
        return [_concept(k) for k in UFC_KEYS]

    async def f1(db, statuses=None, limit=None):
        return []

    async def cycling(db, statuses=None, limit=None):
        return [_concept(VUELTA_KEY, status="live")]

    with (
        patch("app.utils.event_ufc.list_ufc_card_concepts", ufc),
        patch("app.utils.event_f1.list_f1_gp_concepts", f1),
        patch("app.utils.event_cycling.list_cycling_concepts", cycling),
    ):
        keys = await population.list_unsettled_concept_keys(object())

    assert VUELTA_KEY in keys, (
        "the Vuelta is not in the warm population — Pogacar 0.751 is sitting in "
        "an envelope the feed will never read, which IS #1948"
    )
    for k in UFC_KEYS:
        assert k in keys
    assert len(keys) == 5
    assert not any(k.startswith("event:golf:") for k in keys), (
        "the leader population is the UNSETTLED concepts; the golf majors are a "
        "separate, latency-motivated tier"
    )


@pytest.mark.asyncio
async def test_a_settled_concept_is_not_in_the_leader_population():
    """"Settled means settled" (standing Alex ruling).

    A settled concept's card leads with its WHAT-HIT result, resolved by
    `_resolve_concept_champion`, and `_leader` is explicitly None for it. Warming
    it under the leader tier would spend the load-bearing tier's budget on keys
    whose leader is never read.
    """

    async def ufc(db, statuses=None, limit=None):
        # The listers filter by `statuses`; assert the population ASKS for the
        # right ones rather than trusting a fake to filter.
        assert statuses == ("upcoming", "live"), statuses
        return [_concept(k) for k in UFC_KEYS]

    async def empty(db, statuses=None, limit=None):
        return []

    with (
        patch("app.utils.event_ufc.list_ufc_card_concepts", ufc),
        patch("app.utils.event_f1.list_f1_gp_concepts", empty),
        patch("app.utils.event_cycling.list_cycling_concepts", empty),
    ):
        keys = await population.list_unsettled_concept_keys(object())

    assert set(keys) == set(UFC_KEYS)


@pytest.mark.asyncio
async def test_one_broken_lister_does_not_empty_the_whole_tier():
    """Gotcha #42: a throw inside a per-item loop must not wipe the pass.

    A throw in `_score_events` emptied the entire Sports tab (#1091). The same
    shape here would delete every concept card because one adapter is unwell.
    """

    async def boom(db, statuses=None, limit=None):
        raise RuntimeError("the UFC lister is unwell")

    async def cycling(db, statuses=None, limit=None):
        return [_concept(VUELTA_KEY)]

    async def empty(db, statuses=None, limit=None):
        return []

    with (
        patch("app.utils.event_ufc.list_ufc_card_concepts", boom),
        patch("app.utils.event_f1.list_f1_gp_concepts", empty),
        patch("app.utils.event_cycling.list_cycling_concepts", cycling),
    ):
        keys = await population.list_unsettled_concept_keys(object())

    assert keys == (VUELTA_KEY,), "the healthy sibling did not survive"


@pytest.mark.asyncio
async def test_a_key_listed_twice_is_warmed_once():
    async def dup(db, statuses=None, limit=None):
        return [_concept(VUELTA_KEY), _concept(VUELTA_KEY)]

    async def empty(db, statuses=None, limit=None):
        return []

    with (
        patch("app.utils.event_ufc.list_ufc_card_concepts", dup),
        patch("app.utils.event_f1.list_f1_gp_concepts", empty),
        patch("app.utils.event_cycling.list_cycling_concepts", dup),
    ):
        keys = await population.list_unsettled_concept_keys(object())

    assert keys == (VUELTA_KEY,)


# ---------------------------------------------------------------------------
# The warmer consumes it
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_scheduled_warm_run_builds_the_vuelta_and_the_majors():
    """The end-to-end shape of the fix: one scheduled run covers BOTH tiers."""
    built: list[str] = []

    async def build(key, db, rc, adapter=None):
        built.append(key)
        return {"event": {"name": key}}

    async def pop():
        return (VUELTA_KEY,) + UFC_KEYS

    with (
        patch("app.tasks.base.get_task_session", _fake_session),
        patch("app.utils.event_concept_cache.build_and_cache", build),
        patch("app.utils.event_concept_cache.get_client", return_value=_FakeRedis()),
        patch.object(warmer, "_leader_population", pop),
    ):
        summary = await warmer._warm_event_concepts()

    assert VUELTA_KEY in built
    for k in UFC_KEYS:
        assert k in built
    for k in WARM_CONCEPT_KEYS:
        assert k in built, "the #1107 golf majors must not be dropped by this fix"

    assert summary["terminal"] == "complete"
    assert summary["leader_population"] == 5
    assert summary["total"] == 5 + len(WARM_CONCEPT_KEYS)
    assert summary["built"] == summary["total"]


@pytest.mark.asyncio
async def test_the_leader_tier_is_warmed_before_the_majors():
    """Ordering is load-bearing, not cosmetic.

    A missed MAJOR is a slow page — the route still builds it inline. A missed
    LEADER is a DELETED CARD, because `_resolve_concept_leader` is cache-only
    and both surfaces suppress a leaderless concept. The tier that cannot
    degrade gracefully must not run on whatever the other one left behind.
    """
    order: list[str] = []

    async def build(key, db, rc, adapter=None):
        order.append(key)
        return {"event": {"name": key}}

    async def pop():
        return (VUELTA_KEY,)

    with (
        patch("app.tasks.base.get_task_session", _fake_session),
        patch("app.utils.event_concept_cache.build_and_cache", build),
        patch("app.utils.event_concept_cache.get_client", return_value=_FakeRedis()),
        patch.object(warmer, "_leader_population", pop),
    ):
        await warmer._warm_event_concepts()

    assert order[0] == VUELTA_KEY
    assert order[1:] == list(WARM_CONCEPT_KEYS)


@pytest.mark.asyncio
async def test_the_majors_cannot_starve_the_leader_tier():
    """Gotcha #34, and it is the reason the tiers have separate budgets.

    "Never share a single counter between two kinds of work across a loop — the
    early work exhausts the limit before the later work is reached." Majors cost
    11-35s each against leaders' 0.24-1.37s. On one shared deadline the majors
    would consume it every single run and the load-bearing tier would never be
    reached — silently. That is #1948 again, wearing a budget for a hat.
    """
    built: list[str] = []

    async def build(key, db, rc, adapter=None):
        if key.startswith("event:golf:"):
            await asyncio.sleep(10)  # pathological major
        built.append(key)
        return {"event": {"name": key}}

    async def pop():
        return (VUELTA_KEY,) + UFC_KEYS

    with (
        patch("app.tasks.base.get_task_session", _fake_session),
        patch("app.utils.event_concept_cache.build_and_cache", build),
        patch("app.utils.event_concept_cache.get_client", return_value=_FakeRedis()),
        patch.object(warmer, "_leader_population", pop),
        patch.object(warmer, "PER_KEY_TIMEOUT_SECONDS", 0.05),
        patch.object(warmer, "MAJORS_TIER_BUDGET_SECONDS", 0.05),
    ):
        summary = await warmer._warm_event_concepts()

    assert VUELTA_KEY in built, "the majors starved the load-bearing tier"
    assert set(UFC_KEYS).issubset(set(built))
    assert not any(b.startswith("event:golf:") for b in built)
    assert summary["terminal"] == "partial", (
        "a run that failed every major reported complete"
    )


@pytest.mark.asyncio
async def test_a_key_the_budget_never_reached_is_reported_not_dropped():
    """NO SILENT CAPS.

    A key skipped for budget is not `absent` (which asserts it resolves to
    nothing) and must not be counted as completed. A warmer that skipped half
    the leader tier and reported GREEN is the false-GREEN class #1515 exists
    for — and the reader would have no way to know which cards went dark.
    """

    async def build(key, db, rc, adapter=None):
        await asyncio.sleep(10)
        return {"event": {"name": key}}

    async def pop():
        return (VUELTA_KEY,) + UFC_KEYS

    with (
        patch("app.tasks.base.get_task_session", _fake_session),
        patch("app.utils.event_concept_cache.build_and_cache", build),
        patch("app.utils.event_concept_cache.get_client", return_value=_FakeRedis()),
        patch.object(warmer, "_leader_population", pop),
        patch.object(warmer, "LEADER_PER_KEY_TIMEOUT_SECONDS", 0.02),
        patch.object(warmer, "LEADER_TIER_BUDGET_SECONDS", 0.03),
        patch.object(warmer, "PER_KEY_TIMEOUT_SECONDS", 0.02),
    ):
        summary = await warmer._warm_event_concepts()

    assert summary["budget_skipped"], "keys were dropped from the summary entirely"
    assert summary["terminal"] == "partial"
    accounted = (
        summary["built"]
        + len(summary["absent"])
        + len(summary["locked"])
        + len(summary["budget_skipped"])
        + len(summary["errors"])
    )
    assert accounted == summary["total"], (
        "every target must appear in exactly one bucket — a key that is in none "
        "of them is a key nobody can find out about"
    )


@pytest.mark.asyncio
async def test_an_unavailable_population_leaves_the_majors_warming():
    """A DB failure in the new tier must not take #1107's warmer down with it."""

    async def build(key, db, rc, adapter=None):
        return {"event": {"name": key}}

    async def boom():
        raise RuntimeError("no session")

    with (
        patch("app.tasks.base.get_task_session", _fake_session),
        patch("app.utils.event_concept_cache.build_and_cache", build),
        patch("app.utils.event_concept_cache.get_client", return_value=_FakeRedis()),
        patch.object(warmer, "_leader_population", boom),
    ):
        with pytest.raises(RuntimeError):
            await warmer._warm_event_concepts()


@pytest.mark.asyncio
async def test_the_real_leader_population_helper_is_total():
    """`_leader_population` itself must never raise — it is the seam the test
    above stubs, so its own totality needs its own proof."""

    @asynccontextmanager
    async def broken_session():
        raise RuntimeError("db down")
        yield  # pragma: no cover

    with patch("app.tasks.base.get_task_session", broken_session):
        assert await warmer._leader_population() == ()


# ---------------------------------------------------------------------------
# The budget arithmetic
# ---------------------------------------------------------------------------


def test_the_two_tier_budgets_fit_inside_the_task_soft_limit():
    """Pinned as arithmetic so raising a tier budget without raising the task's
    soft_time_limit fails HERE rather than in production as a SIGKILL — which is
    recorded as `no_data` and therefore as nothing at all."""
    from app.tasks import celery_app

    task = celery_app.tasks["app.tasks.warm_event_concepts"]
    soft, hard = task.soft_time_limit, task.time_limit

    assert soft is not None and hard is not None
    assert soft < hard
    assert hard <= 300, "at or above the global 300s hard SIGKILL"
    assert (
        warmer.LEADER_TIER_BUDGET_SECONDS + warmer.MAJORS_TIER_BUDGET_SECONDS <= soft
    ), (
        f"leaders {warmer.LEADER_TIER_BUDGET_SECONDS}s + majors "
        f"{warmer.MAJORS_TIER_BUDGET_SECONDS}s exceeds the {soft}s soft limit"
    )


def test_the_leader_per_key_bound_is_generous_against_the_measured_build():
    """Measured 0.24-1.37s per key on production. 10s is ~7x the slowest sample,
    which is headroom for a bad day without letting one key eat the tier."""
    assert warmer.LEADER_PER_KEY_TIMEOUT_SECONDS >= 5
    assert (
        warmer.LEADER_PER_KEY_TIMEOUT_SECONDS < warmer.LEADER_TIER_BUDGET_SECONDS
    ), "one key could consume the whole tier budget"


def test_the_feed_and_the_warmer_read_the_same_population_function():
    """The anti-drift assertion, and the whole point of #1948's fix.

    Two enumerations of one population is what caused this incident. If someone
    re-inlines the listers into `feed.py`, or gives the warmer its own list
    again, this fails.
    """
    import inspect

    from app.routes import feed as feed_mod

    src = inspect.getsource(feed_mod._score_event_concepts)
    assert "list_all_concepts" in src, (
        "the feed stopped using the shared population — the warm list can drift "
        "from the rendered list again, which IS #1948"
    )
    for gone in (
        "list_ufc_card_concepts",
        "list_f1_gp_concepts",
        "list_cycling_concepts",
    ):
        assert gone not in src, (
            f"{gone} is called inline in the feed again; the warmer cannot see it"
        )


# ---------------------------------------------------------------------------
# The acceptance: zero leaderless-suppressed concepts when leaders exist upstream
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_zero_concept_cards_are_suppressed_when_the_leaders_are_warm():
    """THE DIRECTIVE'S ACCEPTANCE, driven through the LIVE path.

    Not a unit test of the resolver — `test_feed_concept_leader.py` already owns
    that. This drives the real `_score_event_concepts`, which calls the real
    `_resolve_concept_leader` against real servable envelopes, and then grades
    every emitted card with the SAME suppression predicate the surfaces use
    (`feed_item_is_renderable`, the sentinel's pinned mirror of
    `DiscoverViewModel.suppressionReason` / `feedItemSuppressionReason`).

    That end-to-end shape is what makes it an acceptance rather than a
    restatement: #1948 happened precisely because each half was individually
    correct. The resolver worked, the warmer worked, the renderers worked — and
    nine cards still vanished, because nothing tested the join.

    The Vuelta specimen is the payload: Pogačar 0.751 of 30 must come back out
    the other end and the card must be renderable.
    """
    import json
    from datetime import datetime, timezone

    from app.routes import feed as feed_mod
    from app.tasks.flow_sentinel import feed_item_is_renderable
    from app.utils.event_concept_cache import stamp_envelope

    now = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)

    # The warm cache, keyed exactly as the warmer would have written it.
    envelopes = {
        VUELTA_KEY: [
            {"name": VUELTA_LEADER, "probability": VUELTA_PROBABILITY},
            *[{"name": f"rider{i}", "probability": 0.01} for i in range(VUELTA_FIELD_SIZE - 1)],
        ],
        "event:ufc:26aug20": [
            {"name": "Joshua Van", "probability": 0.5217},
            {"name": "Alexandre Pantoja", "probability": 0.4783},
        ],
        "event:ufc:26aug22": [
            {"name": "Anthony Hernandez", "probability": 0.635},
            {"name": "Gregory Rodrigues", "probability": 0.385},
        ],
    }
    warm: dict[str, str] = {}
    for key, comps in envelopes.items():
        warm[key] = json.dumps(
            stamp_envelope(
                {"primary": {"kind": "winner_field", "competitors": comps}},
                created_at=now,
                lifecycle_watermark=None,
            ),
            default=str,
        )

    async def ufc(db, statuses=None, limit=None):
        return [
            {"key": k, "name": k, "domain": "ufc", "status": "upcoming",
             "start_date": "2026-08-20", "is_major": True, "fight_count": 12,
             "latest_commence": now}
            for k in ("event:ufc:26aug20", "event:ufc:26aug22")
        ]

    async def cycling(db, statuses=None, limit=None):
        return [{"key": VUELTA_KEY, "name": "Vuelta", "domain": "cycling",
                 "status": "live", "start_date": "2026-08-17", "is_major": True,
                 "entry_count": VUELTA_FIELD_SIZE, "latest_commence": now}]

    async def empty(db, statuses=None, limit=None):
        return []

    # Serve the envelopes the way production serves them — out of Redis, and out
    # of BOTH slots the producer writes. UX-P095 (#1948): the reader fetches the
    # 60s primary and the 24h mirror in one `mget`, because the primary is alive
    # for roughly 8% of the day and reading it alone is the defect this file's
    # acceptance is named for.
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

    import app.utils.request_cache as rc

    with (
        patch("app.utils.event_ufc.list_ufc_card_concepts", ufc),
        patch("app.utils.event_f1.list_f1_gp_concepts", empty),
        patch("app.utils.event_cycling.list_cycling_concepts", cycling),
        patch.object(rc, "get_shared_async_redis", _shared),
        patch.object(rc, "bounded_redis_call", _bounded),
    ):
        cards = await feed_mod._score_event_concepts(None, now, None)

    assert len(cards) == 3, f"expected 3 concept cards, got {len(cards)}"

    suppressed = [c for c in cards if not feed_item_is_renderable(c)]
    assert suppressed == [], (
        f"{len(suppressed)} concept card(s) would be dropped by BOTH surfaces "
        f"while their leaders sit in the cache — that is #1948: "
        f"{[c['data']['key'] for c in suppressed]}"
    )

    vuelta = next(c for c in cards if c["data"]["key"] == VUELTA_KEY)
    leader = vuelta["data"]["leader"]
    assert leader["name"] == VUELTA_LEADER
    assert leader["probability"] == pytest.approx(VUELTA_PROBABILITY)
    assert leader["field_size"] == VUELTA_FIELD_SIZE


@pytest.mark.asyncio
async def test_the_same_page_with_a_cold_cache_is_the_incident_and_is_all_suppressed():
    """The control, and it is what makes the test above non-vacuous.

    Identical concepts, identical code, EMPTY cache — the state master shipped.
    Every card must be suppressed. If this ever goes green, the assertion above
    stopped proving anything, because the suppression predicate would no longer
    be able to see the defect at all.
    """
    from datetime import datetime, timezone

    from app.routes import feed as feed_mod
    from app.tasks.flow_sentinel import feed_item_is_renderable

    now = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)

    async def cycling(db, statuses=None, limit=None):
        return [{"key": VUELTA_KEY, "name": "Vuelta", "domain": "cycling",
                 "status": "live", "start_date": "2026-08-17", "is_major": True,
                 "entry_count": VUELTA_FIELD_SIZE, "latest_commence": now}]

    async def empty(db, statuses=None, limit=None):
        return []

    async def _shared():
        raise RuntimeError("cold")

    import app.utils.request_cache as rc

    with (
        patch("app.utils.event_ufc.list_ufc_card_concepts", empty),
        patch("app.utils.event_f1.list_f1_gp_concepts", empty),
        patch("app.utils.event_cycling.list_cycling_concepts", cycling),
        patch.object(rc, "get_shared_async_redis", _shared),
    ):
        cards = await feed_mod._score_event_concepts(None, now, None)

    # Q407 Item 3 (Alex directive, 2026-08-24): the leaderless card is now
    # suppressed AT THE SERVER, so the cold-cache page is empty rather than full
    # of cards only the clients throw away. Before the gate this asserted
    # `len(cards) == 1` + `not feed_item_is_renderable(cards[0])`.
    assert cards == [], (
        "a concept whose leader cannot be resolved must not reach the page at "
        f"all — the server gate is missing or regressed. Emitted: "
        f"{[c['data']['key'] for c in cards]}"
    )

    # The non-vacuity control this test exists for is UNCHANGED in substance: the
    # suppression predicate must still be able to SEE a leaderless card. It just
    # can no longer be handed one by the route, so it is handed the shape the
    # route used to emit. If this ever passes, the surfaces changed and the
    # alarm's mirror is stale — which is exactly what the original assertion
    # guarded, and the reason it is kept rather than deleted with the card.
    leaderless_shape = {
        "type": "concept",
        "score": 40,
        "data": {
            "key": VUELTA_KEY,
            "name": "Vuelta",
            "domain": "cycling",
            "status": "live",
            "entry_count": VUELTA_FIELD_SIZE,
            "marquee_whathit": False,
        },
    }
    assert not feed_item_is_renderable(leaderless_shape), (
        "a leaderless concept card must be suppressed — if this renders, the "
        "surfaces changed and the alarm's mirror is stale"
    )
