"""One condition, one outcome — drop a binary leg that duplicates its own rung.

A Polymarket event is served to us twice over: the parent "field" row carries
one outcome per sub-market, keyed by the BARE condition id and named after the
sub-market's subject (``groupItemTitle`` — "90+", "Zoë Kravitz", "December
31"); the decomposition branch of ``tasks/polymarket.py`` writes each
sub-market's two legs keyed ``{condition_id}_yes`` / ``{condition_id}_no`` and
named literally "Yes" / "No".

Those two conventions are supposed to live on two different market rows. On
1,455 markets they do not — the same ``market_id`` holds both the bare rung and
its ``_yes``/``_no`` twin, and because ``uq_outcome_market_external`` is
``(market_id, external_id)`` the schema is perfectly happy about it: three
legally distinct rows describing one condition.

The consequence is not cosmetic. The legs carry the sub-market's own price, so
a "No" at 64.5% outranks every named rung and gets crowned the card's leader:

    "New favorite: No: Who will Taylor Swift's bridesmai... (64%)"

on a market whose ten actual people all render 0%. Measured 2026-08-31 across
the whole population: 1,455 affected markets (all Polymarket), 2,910 duplicate
rows, and **188 of the 346 open ones are currently crowning one of these legs**
— "US forces enter Iran by..?" reads "Yes 100%".

WHAT MAKES THIS SAFE TO DROP, and why the rule needs both halves. A bare
condition id is ``0x`` + 64 hex characters, so no legitimate one ends in
``_yes`` or ``_no``; and a leg is only redundant if the rung it duplicates is
actually present. So a row is dropped ONLY when

    1. its ``external_id`` ends in ``_yes`` or ``_no``, AND
    2. the id with that suffix removed is ALSO an ``external_id`` on the SAME
       market.

Both conditions held on 1,455 of 1,455 affected markets and the second is what
keeps the rule from touching a correctly decomposed sub-market row, where the
legs are the only outcomes and no bare twin exists. This is a dedup driven by a
POSITIVE fact — the rung is present, here it is — never an inference from
something's absence (gotcha #53).

``removesuffix``, never ``rstrip``: ``"0x…e084_yes".rstrip("_yes")`` strips a
character SET and would eat trailing ``e``/``s``/``y``/``_`` from the hex too.
(The same mistake is live at ``tasks/polymarket.py`` in the CLOB history
backfill — reported separately, not fixed here.)
"""

from __future__ import annotations

from typing import Iterable, Hashable

#: The two suffixes the sub-market decomposition branch appends to a condition
#: id. Order is irrelevant; a row carries at most one of them.
BINARY_LEG_SUFFIXES: tuple[str, ...] = ("_yes", "_no")


def binary_leg_base(external_id: str | None) -> str | None:
    """The condition id a ``_yes``/``_no`` leg was built from, else ``None``.

    ``None`` for anything that is not a suffixed leg — including ``None``
    itself, which ``futures_outcomes.external_id`` permits.
    """
    if not external_id:
        return None
    for suffix in BINARY_LEG_SUFFIXES:
        if external_id.endswith(suffix):
            return external_id[: -len(suffix)]
    return None


def duplicate_leg_external_ids(external_ids: Iterable[str | None]) -> set[str]:
    """The ``external_id``s that duplicate a bare rung on the same market.

    Takes every ``external_id`` on ONE market and returns the subset that is a
    ``_yes``/``_no`` leg whose bare condition is also present. Callers filter
    their own rows against it, so this stays free of any row shape.

    Passing ids from more than one market would let a rung on market A justify
    dropping a leg on market B — the caller owns that scoping, deliberately,
    because the two known readers already hold their rows grouped by market.
    """
    present = {eid for eid in external_ids if eid}
    return {
        eid
        for eid in present
        if (base := binary_leg_base(eid)) is not None and base in present
    }


def drop_duplicate_legs(
    rows: Iterable[Hashable],
    external_id_of,
) -> list:
    """``rows`` for one market, with the duplicate ``_yes``/``_no`` legs removed.

    ``external_id_of`` reads the id off a row, so this works for ORM objects,
    row tuples and plain dicts without this module importing any of them.
    Order is preserved: callers rank before or after and must not have their
    sequence reshuffled underneath them.
    """
    rows = list(rows)
    duplicates = duplicate_leg_external_ids(external_id_of(r) for r in rows)
    if not duplicates:
        return rows
    return [r for r in rows if external_id_of(r) not in duplicates]
