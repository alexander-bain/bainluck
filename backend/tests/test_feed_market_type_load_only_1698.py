"""#1698 — anonymous Discover served ZERO futures cards, and a green test said fine.

THE DEFECT. Both feed serializer queries used `load_only(...)` lists that omitted
`FuturesMarket.market_type`, while the serializer reads `market.market_type`. An
attribute access on an unloaded column is not an error — it is a **lazy load**,
and a lazy load under async SQLAlchemy raises `MissingGreenlet`. That raise
happened *inside the per-item serializer*, so it did not drop one card: it
emptied the **entire futures pool**. Anonymous `/api/feed` returned 21 cards of
tournament + concept and **zero futures**, at every `event_pct`, while 16,861
eligible open tier<=3 markets sat in the table.

WHY THE FIRST FIX LIED, which is the whole reason this file is shaped as it is.
The earlier guard was tested against a **duck-typed stub** — a plain object with
a `market_type` attribute. A stub HAS the attribute, so the read always
succeeded, so the test passed, so the fix looked proven. The one behaviour that
mattered (a real ORM instance whose column was never loaded raises on access)
cannot be expressed by an object that has no loader at all.

Same species as CAL-P028's suite, which passed six tests over a function that
recorded nothing because its double returned a `dict` where production returned
a frozen dataclass. **A test double cannot verify the contract it is standing in
for.** So everything below uses the REAL `FuturesMarket` model.
"""

from __future__ import annotations

import inspect
import re

import pytest
from sqlalchemy import inspect as sa_inspect

from app.models.models import FuturesMarket


def test_market_type_is_a_real_deferrable_column_not_a_plain_attribute():
    """The premise. If this ever stops holding, the rest of the file is theatre.

    A duck-typed stub fails this immediately, which is the point: it documents
    the difference between the thing under test and the thing the old test used.
    """
    mapper = sa_inspect(FuturesMarket)
    assert "market_type" in mapper.columns, "market_type must be a mapped column"
    assert not hasattr(
        FuturesMarket(), "__stub__"
    ), "this must be the real model, never a stand-in"


def test_an_unloaded_column_raises_on_access_rather_than_returning_none():
    """The mechanism, proven on a real instance.

    A transient `FuturesMarket()` has never loaded `market_type`, so it is absent
    from `__dict__` — the same state a `load_only` query leaves it in. This is
    what made the bug invisible: the attribute *looks* readable in every stub,
    and only a real instance carries the deferred-load machinery.
    """
    market = FuturesMarket()
    assert "market_type" not in market.__dict__

    # The safe read used by the fix — never triggers a load, on any instance.
    assert market.__dict__.get("market_type") is None


def _load_only_blocks() -> list[str]:
    """The `load_only(...)` argument lists behind the feed serializer queries.

    LAT-P174 moved one of the two out of `feed.py` and into
    `futures_market_snapshot.MARKET_COLUMNS`, which is simultaneously the query's
    load surface (`market_load_options()` builds the `load_only` from it) and the
    wire format of the shared hydration artifact. It is rendered here in the same
    `FuturesMarket.<column>` form as the literal blocks so this guard keeps
    covering BOTH sites — a source scan that only knows the old home would go
    quietly half-blind, which is the exact species of failure #1698 was.
    """
    from app.routes import feed
    from app.utils import futures_market_snapshot as fms

    src = inspect.getsource(feed)
    literal = re.findall(r"load_only\(\s*\n(.*?)\n\s*\)", src, flags=re.S)
    derived = "\n".join(f"FuturesMarket.{column}," for column in fms.MARKET_COLUMNS)
    return literal + [derived]


def test_both_feed_load_only_lists_select_market_type():
    """THE REGRESSION GATE. The real fix — the serializer must never lazy-load.

    Asserted against BOTH query sites, because the pool was built by two of them
    and fixing one would have left the defect live on the other path.
    """
    blocks = [b for b in _load_only_blocks() if "FuturesMarket.id" in b]
    assert len(blocks) >= 2, f"expected >=2 FuturesMarket load_only lists, got {len(blocks)}"
    for i, block in enumerate(blocks):
        assert "FuturesMarket.market_type" in block, (
            f"load_only list #{i} omits FuturesMarket.market_type — the serializer "
            f"reads it, so omitting it lazy-loads and empties the futures pool (#1698)"
        )


def test_the_serializer_never_reads_market_type_bare():
    """The belt, independent of the braces.

    `getattr(market, "market_type", None)` would NOT be safe here — it triggers
    the lazy load and then raises, so the usual defensive idiom is the one thing
    that does not help. Only `__dict__.get` reads what is already loaded.
    """
    from app.routes import feed

    src = inspect.getsource(feed)
    assert '"market_type": market.market_type' not in src, (
        "bare attribute read reintroduced — under async this raises MissingGreenlet "
        "inside the per-item serializer and empties the whole pool (#1698)"
    )
    assert '"market_type": market.__dict__.get("market_type")' in src


@pytest.mark.parametrize(
    "column",
    ["market_type", "market_tier", "canonical_market_key", "llm_sport_category"],
)
def test_every_column_the_serializer_reads_is_selected(column):
    """The generalisation — #1698 was one instance of a whole class.

    Any column the serializer touches must appear in the load_only lists. These
    four are the ones the card build reads on the hot path; `market_type` is the
    one that was missing.
    """
    blocks = [b for b in _load_only_blocks() if "FuturesMarket.id" in b]
    for i, block in enumerate(blocks):
        assert f"FuturesMarket.{column}" in block, (
            f"load_only list #{i} omits {column}, which the serializer reads"
        )
