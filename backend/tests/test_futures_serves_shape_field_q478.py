"""lane1-Q478 — the futures payloads serve the shape field they already store.

TOP-PRODUCT-DEFECTS item 10. `market_shape.py` (#194) classifies every futures
market into one of seven shapes and stores it on `FuturesMarket.market_type`.
`frontend/lib/marketShape.ts` states the contract in its own docstring:

    "Every surface -- Discover cards, detail pages, concept pages -- keys off
     that ONE field so the card system and the page system stay in lockstep."

Measured in production on 2026-08-31, before this fix:

    SELECT market_type FROM futures_markets WHERE id = 109349;  -- 'quantity'
    GET /api/futures/109349 -> 26 top-level keys, and `market_type` is not one.

So the detail page was not ignoring the shape field. It had never been given it,
and no amount of frontend work could have dispatched on it. `market_type` was
classified, stored, cohorted on by calibration -- and never served.

These tests pin the field onto both payload builders. They are deliberately about
the CONTRACT (the key is present and carries the stored value), not about any one
market's classification, which `test_market_shape*.py` owns.
"""

import ast
import inspect
import textwrap

import pytest

from app.routes import futures as futures_routes
from app.utils import market_shape


def _payload_keys(func_src: str) -> set[str]:
    """Every string key assigned in a dict literal `return` inside `func_src`."""
    # textwrap.dedent, NOT inspect.cleandoc: cleandoc strips the body's own
    # indentation relative to the `def` and the parse dies on the docstring.
    tree = ast.parse(textwrap.dedent(func_src))
    keys: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for k in node.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    keys.add(k.value)
    return keys


class TestShapeFieldIsServed:
    def test_the_detail_payload_carries_market_type(self):
        """`GET /api/futures/{id}` serves the shape field.

        Anchored on the AST of the payload dict rather than on a substring, so a
        mention of `market_type` in a comment or an unrelated call cannot satisfy
        it (the containment-guard failure class).
        """
        src = inspect.getsource(futures_routes._format_market_detail)
        assert "market_type" in _payload_keys(src)

    def test_both_payload_builders_bind_market_type_to_the_model_attribute(self):
        """The key must be wired to `.market_type`, not to a literal or a guess.

        A `"market_type": None` placeholder would satisfy a key-presence check and
        serve nothing, which is the same absence-as-truth shape (gotcha #53) in a
        new place.
        """
        src = inspect.getsource(futures_routes)
        tree = ast.parse(src)
        bindings: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            for k, v in zip(node.keys, node.values):
                if isinstance(k, ast.Constant) and k.value == "market_type":
                    # want: <something>.market_type
                    assert isinstance(v, ast.Attribute), (
                        f'"market_type" is bound to {ast.dump(v)[:80]}, not to a '
                        "model attribute"
                    )
                    assert v.attr == "market_type"
                    bindings.append(ast.unparse(v))
        # Two payloads must carry it: the detail response and each market row of
        # the group response. Fewer than two means one surface is still blind.
        assert len(bindings) >= 2, (
            f"expected the detail AND group payloads to serve market_type, "
            f"found {len(bindings)}: {bindings}"
        )


class TestVocabularyParityWithTheFrontendMirror:
    """The mirror in `frontend/lib/marketShape.ts` had drifted, and the drift was
    silent by construction: `resolveShape()` prefers the stored value only when
    `isMarketShape()` accepts it, so an unrecognised shape falls through to the
    name-guessing fallback rather than raising.

    Read from the FRONTEND SOURCE, so this fails when either side moves.
    """

    def _mirror_shapes(self) -> set[str]:
        import pathlib
        import re

        here = pathlib.Path(__file__).resolve().parents[2]
        ts = (here / "frontend" / "lib" / "marketShape.ts").read_text()
        # `export const SHAPE_FOO = "foo";`
        return set(re.findall(r'export const SHAPE_[A-Z_]+ = "([a-z_]+)";', ts))

    def test_every_backend_shape_exists_in_the_frontend_mirror(self):
        missing = market_shape.ALL_SHAPES - self._mirror_shapes()
        assert not missing, (
            f"shapes classified by the backend but unknown to the frontend: "
            f"{sorted(missing)}. A market of that shape silently falls back to "
            f"the structural heuristic on every surface."
        )

    def test_the_mirror_invents_no_shape_the_backend_never_assigns(self):
        extra = self._mirror_shapes() - set(market_shape.ALL_SHAPES)
        assert not extra, f"frontend knows shapes the backend never stores: {sorted(extra)}"

    def test_participation_is_the_shape_that_had_drifted(self):
        """Named explicitly so a future tidy-up cannot quietly drop it again."""
        assert "participation" in market_shape.ALL_SHAPES
        assert "participation" in self._mirror_shapes()
