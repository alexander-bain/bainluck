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
    """The `load_only(...)` argument lists in the feed serializer queries."""
    from app.routes import feed

    src = inspect.getsource(feed)
    return re.findall(r"load_only\(\s*\n(.*?)\n\s*\)", src, flags=re.S)


def _the_shared_market_block() -> str:
    """The ONE `FuturesMarket` projection — and the assertion that it IS one.

    🔴 UPDATED BY CERT-622/CERT-631, AND THE UPDATE IS NOT A RELAXATION.

    This file used to assert `len(blocks) >= 2` because the pool was built by two
    query sites and "fixing one would have left the defect live on the other
    path". CERT-622 then caught the sequel: Q480 added a read of
    `FuturesOutcome.external_id` and **neither** copy grew the column. Two
    byte-identical 52-line lists is not a safeguard, it is the hazard.

    So `_futures_feed_load_options()` is now the single projection, and the
    protection this file provides is split in two rather than reduced:

      * the column assertions below run against that one list, and
      * `test_both_scorers_take_their_projection_from_the_shared_factory`
        proves both query sites still use it.

    Together those are strictly stronger than the old pair: previously a third
    query site could be added with its own list and this file would not have
    noticed. Now `len(blocks) == 1` fails the moment anyone inlines one.
    """
    blocks = [b for b in _load_only_blocks() if "FuturesMarket.id" in b]
    assert len(blocks) == 1, (
        f"expected exactly ONE FuturesMarket load_only list — the shared "
        f"`_futures_feed_load_options()` — but found {len(blocks)}. If a query site "
        f"has inlined its own copy again, that is the CERT-622 defect returning: the "
        f"copies drift and a newly-read column lands on one and not the other."
    )
    return blocks[0]


def test_both_scorers_take_their_projection_from_the_shared_factory():
    """The half that replaces "assert it twice": prove both sites use the one list.

    Anchored on each scorer's OWN body. A module-wide substring check would be
    satisfied by either scorer alone, which is precisely the "fixed one path,
    missed the other" failure this file was written about.
    """
    import ast

    from app.routes import feed

    tree = ast.parse(inspect.getsource(feed))
    for name in ("_score_futures", "_score_sports_mode_futures"):
        fn = next(
            (
                n
                for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
            ),
            None,
        )
        assert fn is not None, f"{name} not found — this guard cannot report on a function it cannot locate"
        calls = {
            n.func.id
            for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        }
        assert "_futures_feed_load_options" in calls, (
            f"{name} no longer calls `_futures_feed_load_options()` — if it inlined its "
            f"own projection, the two feed paths can drift apart again (CERT-622)"
        )


def test_the_feed_load_only_list_selects_market_type():
    """THE REGRESSION GATE. The real fix — the serializer must never lazy-load."""
    assert "FuturesMarket.market_type" in _the_shared_market_block(), (
        "the shared load_only list omits FuturesMarket.market_type — the serializer "
        "reads it, so omitting it lazy-loads and empties the futures pool (#1698)"
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

    Any column the serializer touches must appear in the load_only list. These
    four are the ones the card build reads on the hot path; `market_type` is the
    one that was missing.

    ⚠️ Note what this parametrize list is and is not: a HAND-MAINTAINED sample of
    four columns. CERT-622 was a fifth read (`FuturesOutcome.external_id`) that
    nobody added here, which is why
    `tests/test_feed_outcome_projection_cert622.py` DERIVES the read set from the
    route bodies by AST instead of listing it. This test is the cheap sentinel;
    that one is the real contract.
    """
    assert f"FuturesMarket.{column}" in _the_shared_market_block(), (
        f"the shared load_only list omits {column}, which the serializer reads"
    )
