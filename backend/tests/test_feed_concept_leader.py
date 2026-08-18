"""#1882 — concept cards carried no probability, only a market count.

`_score_event_concepts` serialised `fight_count`/`entry_count` and no outcomes, so
a card titled "Alexandre Pantoja vs Joshua Van" rendered as a title and a count on
a product whose premise is translating markets into probabilities.

The probability was never missing from the DATA. Measured 2026-08-17 against
production `GET /api/event/event:ufc:26aug20`: the envelope's
`primary.competitors` is already `[{name, probability}]` (Joshua Van 0.5217 /
Alexandre Pantoja 0.4783). The feed just never asked. These tests pin that the
resolver reads it, picks the right end of it, and refuses the shapes it must.
"""

import json
from datetime import datetime, timezone

import pytest

from app.routes.feed import _resolve_concept_leader


class _FakeAdapter:
    """Records whether the resolver reached for a BUILD. It must not."""

    def __init__(self, envelope=None):
        self._envelope = envelope
        self.build_calls = 0

    async def build_event(self, slug, db):
        self.build_calls += 1
        return self._envelope


def _servable(payload: dict) -> str:
    """Stamp a payload with a real, current-generation envelope and encode it.

    UX-P089: the resolver now refuses a payload the DETAIL page would refuse
    (`is_servable_envelope`), so a test fixture must produce the genuine article.
    Built through the production stamper rather than a hand-written dict, so a
    generation bump or a sixth contract field updates these fixtures for free
    instead of silently making every one of them a `generation_mismatch` miss
    that still passes the `is None` assertions.
    """
    from app.utils.event_concept_cache import stamp_envelope

    return json.dumps(
        stamp_envelope(
            payload,
            created_at=datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc),
            lifecycle_watermark=None,
        ),
        default=str,
    )


@pytest.fixture
def envelope_source(monkeypatch):
    """Drive `_resolve_concept_leader` off a supplied envelope, VIA THE CACHE.

    UX-P089 (#1934) rewrote this fixture, and the rewrite is the point. It used
    to force the Redis read to MISS and serve the envelope from a fake adapter —
    so every test in this file exercised the cold-cache `adapter.build_event()`
    path, and the whole suite was green while that path cost the feed its load
    budget. The fixtures agreed with the bug, which is the third time this
    codebase has been bitten by exactly that (L2-179 concepts, #1886 bundles).

    Now the envelope is served the way production serves it — out of Redis — and
    the adapter is installed only so a test can assert it is NEVER CALLED.
    """

    def _install(envelope, *, cached=True):
        import app.utils.event_concept as ec
        import app.utils.request_cache as rc

        adapter = _FakeAdapter(envelope)
        monkeypatch.setattr(ec, "get_adapter", lambda domain: adapter)
        monkeypatch.setattr(ec, "parse_event_key", lambda key: ("ufc", "slug"))

        raw = _servable(envelope) if cached else None

        class _Result:
            is_ok = cached
            value = raw

        async def _bounded(_fn):
            return _Result()

        async def _shared():
            return object()

        monkeypatch.setattr(rc, "bounded_redis_call", _bounded)
        monkeypatch.setattr(rc, "get_shared_async_redis", _shared)
        return adapter

    return _install


def _envelope(competitors):
    return {"primary": {"kind": "head_to_head", "competitors": competitors}}


class TestTheLeaderIsResolved:
    async def test_the_measured_production_shape(self, envelope_source):
        # Verbatim from GET /api/event/event:ufc:26aug20 on 2026-08-17.
        envelope_source(
            _envelope(
                [
                    {"name": "Joshua Van", "probability": 0.5217},
                    {"name": "Alexandre Pantoja", "probability": 0.4783},
                ]
            )
        )
        leader = await _resolve_concept_leader(None, "event:ufc:26aug20")
        assert leader is not None, "the probability is in the envelope; the feed must read it"
        assert leader["name"] == "Joshua Van"
        assert leader["probability"] == pytest.approx(0.5217)
        assert leader["field_size"] == 2

    async def test_the_favourite_is_the_max_not_the_first(self, envelope_source):
        # The adapters sort favourite-first TODAY. A card that leads with the
        # underdog because a sort changed is #1860's "the top line reads as the
        # answer, and the answer is the complement" defect, so the max is taken
        # explicitly rather than trusting position 0.
        envelope_source(
            _envelope(
                [
                    {"name": "Underdog", "probability": 0.20},
                    {"name": "Favourite", "probability": 0.65},
                    {"name": "Middle", "probability": 0.15},
                ]
            )
        )
        leader = await _resolve_concept_leader(None, "event:f1:gp")
        assert leader["name"] == "Favourite"
        assert leader["probability"] == pytest.approx(0.65)
        assert leader["field_size"] == 3

    async def test_movement_is_carried_when_present(self, envelope_source):
        envelope_source(
            _envelope([{"name": "A", "probability": 0.7, "movement_24h": 0.031}])
        )
        leader = await _resolve_concept_leader(None, "event:ufc:x")
        assert leader["movement_24h"] == pytest.approx(0.031)

    async def test_movement_falls_back_to_the_other_field_name(self, envelope_source):
        envelope_source(
            _envelope(
                [{"name": "A", "probability": 0.7, "probability_change_24h": -0.02}]
            )
        )
        leader = await _resolve_concept_leader(None, "event:ufc:x")
        assert leader["movement_24h"] == pytest.approx(-0.02)

    async def test_absent_movement_is_none_not_zero(self, envelope_source):
        # Zero is a measured non-move; None is an absence. Rendering them the same
        # would print "▲0" for "we don't know".
        envelope_source(_envelope([{"name": "A", "probability": 0.7}]))
        leader = await _resolve_concept_leader(None, "event:ufc:x")
        assert leader["movement_24h"] is None


class TestItRefusesRatherThanFabricates:
    """The L2-159 contract: never invent a probability."""

    async def test_empty_field_yields_no_leader(self, envelope_source):
        envelope_source(_envelope([]))
        assert await _resolve_concept_leader(None, "event:ufc:x") is None

    async def test_competitors_without_probabilities_yield_no_leader(self, envelope_source):
        envelope_source(_envelope([{"name": "A"}, {"name": "B", "probability": None}]))
        assert await _resolve_concept_leader(None, "event:ufc:x") is None

    async def test_nameless_competitor_yields_no_leader(self, envelope_source):
        envelope_source(_envelope([{"name": "   ", "probability": 0.9}]))
        assert await _resolve_concept_leader(None, "event:ufc:x") is None

    async def test_out_of_range_probability_is_refused(self, envelope_source):
        # Gotcha #23: independent binaries can sum past 100%. A SINGLE leader over
        # 1.0 is corrupt, not merely confident, and must not reach a card.
        envelope_source(_envelope([{"name": "A", "probability": 1.4}]))
        assert await _resolve_concept_leader(None, "event:ufc:x") is None
        envelope_source(_envelope([{"name": "A", "probability": -0.1}]))
        assert await _resolve_concept_leader(None, "event:ufc:x") is None

    async def test_empty_envelope_yields_no_leader(self, envelope_source):
        envelope_source({})
        assert await _resolve_concept_leader(None, "event:ufc:x") is None

    async def test_an_adapter_explosion_never_breaks_the_feed(self, monkeypatch):
        import app.utils.event_concept as ec
        import app.utils.request_cache as rc

        class _Boom:
            async def build_event(self, slug, db):
                raise RuntimeError("adapter down")

        class _Miss:
            is_ok = False
            value = None

        async def _bounded(_fn):
            return _Miss()

        async def _shared():
            return object()

        monkeypatch.setattr(rc, "bounded_redis_call", _bounded)
        monkeypatch.setattr(rc, "get_shared_async_redis", _shared)
        monkeypatch.setattr(ec, "get_adapter", lambda d: _Boom())
        monkeypatch.setattr(ec, "parse_event_key", lambda k: ("ufc", "s"))

        assert await _resolve_concept_leader(None, "event:ufc:x") is None


class TestTheLeaderNeverBuilds:
    """UX-P089 (#1934) — the cost half, which is why Discover showed two cards.

    MEASURED on production 2026-08-17, three cold identified-key builds of
    `GET /api/feed?limit=50&offset=0&event_pct=0.15`:

        total 4318ms / 4295ms / 11708ms
        concepts stage  2710ms / 2804ms / 10075ms

    The native client's entire initial-load budget is 6s
    (`DiscoverViewModel.retryBudget`), the deadline error is non-retryable, and
    every identified principal has its own cache key with a 5s fresh TTL and a
    300s stale tier. So a signed-in reader returning more than five minutes after
    their last visit cold-builds, and the tail of that distribution cannot be
    delivered at all — Discover settles to last-good or honest-empty.

    The cause was a copied fallback. `_resolve_concept_champion` prices its cold
    build explicitly and correctly: it runs only for SETTLED marquee concepts, a
    handful per 36h. `_resolve_concept_leader` inherited the fallback but not the
    pricing — it runs for EVERY unsettled concept and is awaited serially, 10-14
    per slate. These tests pin the deletion.
    """

    async def test_a_cold_envelope_yields_no_leader_and_never_builds(
        self, envelope_source
    ):
        adapter = envelope_source(
            _envelope([{"name": "Joshua Van", "probability": 0.52}]), cached=False
        )
        assert await _resolve_concept_leader(None, "event:ufc:26aug20") is None
        assert adapter.build_calls == 0, (
            "a cold concept envelope must cost the feed NOTHING — one build here "
            "is 10-14 builds per request, serially, inside a 6s client budget"
        )

    async def test_a_warm_envelope_is_served_without_building(self, envelope_source):
        adapter = envelope_source(
            _envelope([{"name": "Joshua Van", "probability": 0.5217}])
        )
        leader = await _resolve_concept_leader(None, "event:ufc:26aug20")
        assert leader is not None and leader["name"] == "Joshua Van"
        assert adapter.build_calls == 0

    def test_the_build_fallback_is_deleted_not_merely_unreached(self):
        """A reachable-but-unused path is a path that comes back.

        Source-level, deliberately: the behavioural tests above prove the adapter
        is not called for the shapes they exercise, and prove nothing about a
        shape nobody thought to write. `build_event` must not appear in this
        function's CODE at all.

        The docstring is stripped before matching, and that is not a convenience
        — the docstring is *supposed* to name the deleted path and say why it went
        (gotcha #32's lesson: a deletion that is not explained is re-added by the
        next reader citing the original rationale). Matching raw source would
        force the fix and its explanation to be mutually exclusive.
        """
        import ast
        import inspect
        import textwrap

        from app.routes import feed

        def _code_only(fn) -> str:
            tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
            node = tree.body[0]
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                body = body[1:]
            return "\n".join(ast.unparse(stmt) for stmt in body)

        code = _code_only(feed._resolve_concept_leader)
        assert "build_event" not in code
        assert "get_adapter" not in code
        # ...while the champion, whose cold build IS priced, keeps its fallback.
        assert "build_event" in _code_only(feed._resolve_concept_champion)

    async def test_an_unservable_envelope_is_a_miss_not_a_probability(
        self, monkeypatch
    ):
        """A payload the DETAIL page would refuse must not become a feed number.

        #1678 finding 2's shape: a single-field `cache` block passed the old
        generation-only check and was read as a complete envelope. A Discover
        card leading with a probability lifted out of a payload nobody would
        serve is that defect wearing the reader's clothes.
        """
        import app.utils.request_cache as rc

        raw = json.dumps(
            {
                "primary": {"competitors": [{"name": "A", "probability": 0.9}]},
                "cache": {"generation": 3},  # four of five contract fields absent
            }
        )

        class _Hit:
            is_ok = True
            value = raw

        async def _bounded(_fn):
            return _Hit()

        async def _shared():
            return object()

        monkeypatch.setattr(rc, "bounded_redis_call", _bounded)
        monkeypatch.setattr(rc, "get_shared_async_redis", _shared)

        assert await _resolve_concept_leader(None, "event:ufc:x") is None


class TestSettledMeansSettled:
    """The standing Alex ruling, asserted at the one place both are resolved."""

    def test_the_serializer_makes_leader_and_champion_mutually_exclusive(self):
        import inspect

        from app.routes import feed

        source = inspect.getsource(feed._score_event_concepts)
        # The leader is resolved only when NOT in the WHAT-HIT window. Pinning the
        # guard rather than the comment: a settled card leading with a live
        # probability is the exact thing "settled means settled" forbids.
        assert "if _is_whathit" in source
        assert "_resolve_concept_leader" in source
        assert '**({"leader": _leader} if _leader else {})' in source

    def test_the_leader_key_is_absent_not_null_when_unresolved(self):
        # `**({} )` rather than `"leader": None` — so the client's "has a leader"
        # test is a presence test and an older client ignores the key entirely.
        import inspect

        from app.routes import feed

        source = inspect.getsource(feed._score_event_concepts)
        assert '"leader": None' not in source
