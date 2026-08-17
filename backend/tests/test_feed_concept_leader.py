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

import pytest

from app.routes.feed import _resolve_concept_leader


class _FakeAdapter:
    def __init__(self, envelope):
        self._envelope = envelope

    async def build_event(self, slug, db):
        return self._envelope


@pytest.fixture
def envelope_source(monkeypatch):
    """Drive `_resolve_concept_leader` off a supplied envelope.

    Patches the concept-adapter module the resolver imports lazily, and forces the
    warm-Redis read to miss so the adapter path is the one under test.
    """

    def _install(envelope):
        import app.utils.event_concept as ec
        import app.utils.request_cache as rc

        monkeypatch.setattr(ec, "get_adapter", lambda domain: _FakeAdapter(envelope))
        monkeypatch.setattr(ec, "parse_event_key", lambda key: ("ufc", "slug"))

        class _Miss:
            is_ok = False
            value = None

        async def _bounded(_fn):
            return _Miss()

        async def _shared():
            return object()

        monkeypatch.setattr(rc, "bounded_redis_call", _bounded)
        monkeypatch.setattr(rc, "get_shared_async_redis", _shared)

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
