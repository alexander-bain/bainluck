"""#219E Item 3 (BAINLUCK-SZ): market_metadata must stay object-shaped.

The market-shape backfill concatenated a shape object onto existing metadata
with `COALESCE(market_metadata, '{}') || jsonb_build_object(...)`. COALESCE only
replaces SQL NULL — a jsonb value of `null` (JSON null) slips through, and
`'null'::jsonb || '{...}'::jsonb` evaluates to the ARRAY `[null, {...}]` (a
Postgres jsonb-concat quirk). ~369 rows ended up array-shaped, and `dict()` on
that raised "cannot convert dictionary update sequence element #0 to a
sequence", killing hook generation for the market.

Guard both ends: the writer must coalesce NON-OBJECTS (not just NULL) before the
concat, and the reader must tolerate/recover a malformed array.
"""

import inspect

from app.tasks.backfill_market_shapes import _backfill_market_shapes
from app.tasks.enrich_markets import enrich_market_hooks


def test_shape_writer_guards_against_non_object_metadata():
    """The `||` left operand must be forced to an object, not bare COALESCE."""
    src = inspect.getsource(_backfill_market_shapes)
    assert "jsonb_build_object('shape'" in src, "shape writer shape changed"
    # bare COALESCE(market_metadata, '{}') does NOT catch JSON null / arrays and
    # produces [null, {...}] — the corruption. The object-typed guard must exist.
    assert "jsonb_typeof(market_metadata) = 'object'" in src, (
        "shape writer must coalesce NON-OBJECT metadata (json null / array / "
        "scalar) to '{}' before the || concat, or it recreates the [null, {...}] "
        "array corruption (#219E / BAINLUCK-SZ)"
    )
    assert "COALESCE(market_metadata, '{}'::jsonb)\n" not in src, (
        "the bare COALESCE that caused the corruption must be gone"
    )


def test_hook_reader_recovers_from_array_metadata():
    """Hook generation must not `dict()` raw metadata that could be an array."""
    src = inspect.getsource(enrich_market_hooks)
    assert "next_metadata = dict(market.market_metadata or {})" not in src, (
        "raw dict(market_metadata) crashes on the array-corruption rows "
        "(#219E / BAINLUCK-SZ)"
    )
    # the defensive normalization must handle dict / list / other
    assert "isinstance(_md, dict)" in src and "isinstance(_md, list)" in src, (
        "hook generation must normalize array/malformed market_metadata instead "
        "of calling dict() on it (#219E / BAINLUCK-SZ)"
    )
