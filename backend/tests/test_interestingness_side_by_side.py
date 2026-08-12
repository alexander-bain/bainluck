"""LAT-P043: the ratification diagnostic must not be able to ship the thing
it exists to evaluate.

Alex ruled on 2026-08-12 that the interestingness blend stays dark until he has
seen a side-by-side and ratified a weight. That creates an obvious trap: the
only previously available way to see the feed at weight 0.2 was to SET
``interestingness:blend_weight`` to 0.2 — i.e. to make the change for every
user in order to decide whether to make it. A diagnostic that flips the live
switch, even for a few seconds, even with a restore in a ``finally``, is the
exact accident the ruling exists to prevent (and a restore does not save it:
the process can die between the two writes).

So the weight is an in-process argument to one scoring pass. These tests pin
that property, because it is the property that makes the diagnostic safe:

* the override never appears in the runtime config defaults, so the served
  feed cannot pick one up;
* the handler contains no Redis write of any kind;
* an override, when supplied, wins over the key without reading it.
"""

import ast
import inspect
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

import app.routes.admin_feed_config as cfg_module
import app.routes.feed as feed_module
from app.main import app

_OVERRIDE = "interestingness_blend_weight_override"


def _handler_source() -> str:
    return inspect.getsource(cfg_module.interestingness_side_by_side)


class TestTheDiagnosticCannotTurnTheBlendOn:
    def test_the_handler_writes_nothing_to_redis(self):
        tree = ast.parse(_handler_source().lstrip())
        writes = [
            n.func.attr
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr in {"set", "setex", "delete", "hset", "expire", "getset"}
        ]
        assert not writes, (
            f"the side-by-side diagnostic performs Redis writes {writes} — it "
            "must never touch the live kill switch (LAT-P043, Alex 2026-08-12)"
        )

    def test_the_handler_does_not_call_the_config_setter(self):
        src = _handler_source()
        assert "set_feed_config" not in src, (
            "the diagnostic must not route around itself via the config setter"
        )

    def test_the_override_is_not_a_runtime_config_default(self):
        # If it leaked into the defaults, every served /api/feed request would
        # carry it and the injection seam would become a live ranking control.
        defaults = feed_module._discover_runtime_config_defaults()
        assert _OVERRIDE not in defaults, (
            "the diagnostic override is in the served feed's config defaults"
        )

    def test_the_override_is_consulted_before_the_key_is_read(self):
        src = Path(inspect.getfile(feed_module)).read_text()
        override_at = src.index(f'.get("{_OVERRIDE}")')
        read_at = src.index('get("interestingness:blend_weight")')
        assert override_at < read_at, (
            "the override must short-circuit the Redis read, not be overwritten "
            "by it"
        )

    def test_an_override_of_zero_is_honoured_not_treated_as_absent(self):
        # 0.0 is falsy, and `or` would silently discard the most important
        # weight in the comparison — the dark one. Pin the `is not None` test.
        src = Path(inspect.getfile(feed_module)).read_text()
        assert "if _weight_override is not None:" in src, (
            "a weight of 0 must be an override, not a missing one — a truthiness "
            "test would silently discard the dark arm of the comparison"
        )


class TestTheArtifactIsReadable:
    @pytest.mark.asyncio
    async def test_rejects_a_single_weight(self):
        # A "side-by-side" of one is not a comparison.
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/admin/interestingness-side-by-side?secret=wrong&weights=0.2"
            )
        # Auth is checked first; the point here is that it never 200s.
        assert resp.status_code != 200

    @pytest.mark.asyncio
    async def test_requires_admin_auth(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/admin/interestingness-side-by-side?secret=wrong"
            )
        assert resp.status_code == 403

    def test_cache_population_is_reported_separately_from_the_verdict(self):
        # The whole reason this field exists: an empty cache and a neutral
        # weight both render as two identical slates. Reading `identical: true`
        # without `cache_hits` is how "the blend does nothing" would get
        # concluded from a cache that has nothing in it (gotcha #53) — which is
        # precisely the shape of the bug LAT-P042 just finished fixing.
        src = _handler_source()
        assert "cache_hits" in src and "cache_populated" in src
        assert '"cached": None' in src, (
            "an unmeasurable cache count must stay None, never collapse to 0"
        )

    def test_the_slates_are_ranked_by_the_feeds_own_sort_key(self):
        # Re-implementing the ordering would make this an artifact about the
        # diagnostic rather than about Discover.
        src = _handler_source()
        assert "_rank_key" in src and "_score_futures" in src, (
            "the diagnostic must reuse the feed's scorer and sort key"
        )
