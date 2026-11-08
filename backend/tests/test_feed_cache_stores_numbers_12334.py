"""#12334 — every feed Redis tier stores a probability as a number.

THE SHIP: a Discover card prints its percentage instead of `—`. On the cached
feed (`page_base_stale_hit`), `top_outcomes[].probability` arrived as text,
for example `"0.067500"`: a `NUMERIC` column's `Decimal`, stored through
`json.dumps(..., default=str)`. A fresh build went out through FastAPI's
encoder as a number, so only cached readers got the string, and the card's
`Number.isFinite` check printed `—` for it. That held for the Grab earnings
card, the NASCAR Championship card and the rows of the Washington Power and
Middle East bundles.

  A  red first: the old codec stores the Decimal as its text;
  B  the ship: every specimen string from the live feed comes back a number,
     on a card and on a bundle row nested one level deeper;
  C  the stored shape is the shape FastAPI serves a fresh build. A payload of
     plain JSON is stored byte-for-byte as before, and a value the encoder
     refuses is stored as its text, never raised;
  D  every feed cache write in `routes/feed.py` goes through the codec, so a
     new tier cannot bring the split back.
"""

import ast
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from fastapi.encoders import jsonable_encoder

from app.utils.feed_cache import dumps_feed_cache

FEED_ROUTE = Path(__file__).resolve().parents[1] / "app" / "routes" / "feed.py"

#: The six strings the live feed served (the issue body's API excerpt).
SPECIMENS = ["0.105000", "0.067500", "0.460000", "0.345000", "0.235000", "0.320000"]


def _card(prob_text: str, card_id: int = 68943109) -> dict:
    """A futures card as the feed builds it: its top outcome read off a NUMERIC."""
    return {
        "type": "futures",
        "data": {
            "id": card_id,
            "name": "Will Grab (GRAB) beat quarterly earnings?",
            "hero_probability_source": "blend",
            "top_outcomes": [
                {
                    "id": 1,
                    "name": "Grab (GRAB)",
                    "probability": Decimal(prob_text),
                    "rendered_percent": 7,
                }
            ],
        },
    }


def _bundle(prob_texts) -> dict:
    """A theme bundle: its rows sit one level deeper, where the Middle East rows were."""
    return {
        "type": "theme_bundle",
        "data": {"items": [_card(t, card_id=i) for i, t in enumerate(prob_texts)]},
    }


def _probabilities(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "probability":
                yield value
            yield from _probabilities(value)
    elif isinstance(node, list):
        for value in node:
            yield from _probabilities(value)


class TestTheDefectReproduces:
    def test_the_old_codec_stored_the_decimal_as_its_text(self):
        stored = json.loads(json.dumps(_card("0.067500"), default=str))
        assert stored["data"]["top_outcomes"][0]["probability"] == "0.067500"


class TestTheCacheStoresNumbers:
    def test_every_specimen_comes_back_a_number(self):
        for text in SPECIMENS:
            stored = json.loads(dumps_feed_cache(_card(text)))
            value = stored["data"]["top_outcomes"][0]["probability"]
            assert isinstance(value, float), (text, value)
            assert value == float(Decimal(text))

    def test_a_bundle_row_comes_back_a_number(self):
        page = {"items": [_bundle(SPECIMENS[:3]), _card(SPECIMENS[3])]}
        values = list(_probabilities(json.loads(dumps_feed_cache(page))))
        assert len(values) == 4
        assert all(isinstance(v, float) for v in values), values

    def test_a_label_stays_text(self):
        stored = json.loads(dumps_feed_cache(_card("0.067500")))
        assert stored["data"]["hero_probability_source"] == "blend"


class TestTheStoredShapeIsTheServedShape:
    def test_what_is_stored_is_what_fastapi_serves_a_fresh_build(self):
        payload = {
            "items": [_bundle(SPECIMENS[:2]), _card(SPECIMENS[2])],
            "built_at": datetime(2020, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
            "count": Decimal("20"),
            "ratio": Decimal("0.500"),
            "pair": ("a", "b"),
        }
        assert json.loads(dumps_feed_cache(payload)) == jsonable_encoder(payload)

    def test_an_integral_decimal_is_an_int_as_fastapi_serves_it(self):
        assert json.loads(dumps_feed_cache({"n": Decimal("3")})) == {"n": 3}

    def test_a_datetime_is_iso_8601_not_its_str(self):
        when = datetime(2020, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        assert json.loads(json.dumps({"t": when}, default=str))["t"] == "2020-01-02 03:04:05+00:00"
        assert json.loads(dumps_feed_cache({"t": when}))["t"] == "2020-01-02T03:04:05+00:00"

    def test_a_payload_of_plain_json_is_stored_byte_for_byte_as_before(self):
        plain = {"items": [{"id": 1, "p": 0.0675, "name": "Grab", "tags": ["a"], "x": None}]}
        assert dumps_feed_cache(plain) == json.dumps(plain, default=str)

    def test_a_value_the_encoder_refuses_is_stored_as_its_text(self):
        """The publishes swallow their own failures, so a codec that raised would
        switch the cache off silently. This keeps the old codec's answer instead."""
        refused = object()
        assert json.loads(dumps_feed_cache({"x": refused})) == {"x": str(refused)}


def _enclosing_function(tree: ast.AST) -> dict:
    """Map each call node to the name of the function it sits in."""
    owner = {}
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for node in ast.walk(fn):
                if isinstance(node, ast.Call):
                    owner.setdefault(id(node), fn.name)
    return owner


class TestEveryFeedCacheWriteUsesTheCodec:
    TIER_JSON = {
        "_shared_json",  # the inert principal share
        "_composed_json",  # the composed opening manifest
        "_payload_json",  # the response cache, fresh + :stale
        "_manifest_json",  # the edition manifest
        "_seated_json",  # the seated manifest
        "_page_base_json",  # the page base, fresh + :stale + durable last-good
    }

    def test_each_tiers_json_is_built_by_the_codec(self):
        tree = ast.parse(FEED_ROUTE.read_text())
        built_by = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in self.TIER_JSON:
                        func = node.value.func
                        built_by[target.id] = getattr(func, "id", None) or getattr(func, "attr", None)
        assert built_by == {name: "dumps_feed_cache" for name in self.TIER_JSON}

    def test_default_str_survives_only_in_the_log_line(self):
        """`_log_opening_outcome` writes a log line, never a cache entry; any other
        `dumps(..., default=str)` in the route is a tier storing text again."""
        tree = ast.parse(FEED_ROUTE.read_text())
        owner = _enclosing_function(tree)
        sites = set()
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and getattr(node.func, "attr", None) == "dumps"
                and any(
                    k.arg == "default" and isinstance(k.value, ast.Name) and k.value.id == "str"
                    for k in node.keywords
                )
            ):
                sites.add(owner.get(id(node)))
        assert sites <= {"_log_opening_outcome"}, sites
