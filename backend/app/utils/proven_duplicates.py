"""The read side of ``provenance:duplicate-of:`` — one predicate, one meaning.

#2263. The registry has been able to write this tag since queue 413 and, in the
words of its own docstring, *"the drain that consumes these tags is #1946 Item 8
and does not exist yet. A tag that outruns its consumer is still the right thing
to write."* This module is the consumer that arrived first, and it is
deliberately the cheap half: it does not drain anything, it declines to PRINT a
row that has been proven to duplicate another.

That split is the point. Deleting a row is irreversible and needs a repair rail
with its own gates; declining to render a second card for one game is reversible
by reverting one predicate, and it is the whole of what the user is complaining
about. A user does not care that two rows exist. They care that tonight's
Dodgers–Tigers game is printed twice, once with a probability and once blank.

## Why a string match and not a JSONB operator

The tag is ``provenance:duplicate-of:<canonical event id>`` — the canonical id
is IN the tag, so there is no single fixed value to test containment against and
``@>`` cannot express "carries any tag with this prefix". The alternatives are
``jsonb_array_elements_text`` in a lateral, which is Postgres-only and would take
the whole guard suite off SQLite, or a cast to text and a prefix match, which is
portable and which this codebase already does for exactly this reason
(``survivor_order()`` in ``feed_event_candidates`` casts
``win_probability_sources`` to ``String`` rather than reach for a JSON operator).

The prefix cannot collide. ``provenance:duplicate-of:`` is written by one
function, :func:`app.services.anchor_channel.duplicate_tag`, and every other tag
in the vocabulary is a fixed string with no free tail.

## What this does NOT do

It does not decide anything. Every judgement about whether two rows are one game
lives at the WRITE side, in ``event_registry._proven_duplicates``, where the
evidence is. This module trusts the tag completely and by design: a reader that
re-litigates the writer's finding is a second matching implementation, and two
matchers that disagree is the failure ruling 048 exists to end.

## The other half of the tag: FOLD, not just HIDE (#2693)

Suppressing the second card is only half of "one match, one card". The other
half is that the surviving card has to carry what the suppressed one was
holding, and on the population this tag was written for it usually was not the
empty row:

    ghosts carrying at least one market          110 / 172
    ghosts carrying MORE markets than their own
      canonical                                   63 / 172
    Andreeva/Potapova, 2026-09-07 QF              ghost 13 markets, canonical 0
    Cerundolo/Blockx,  2026-09-07 QF              ghost 17 markets, canonical 1

So :func:`not_a_proven_duplicate` on its own, applied to those two, does not
remove a duplicate card — it removes the only card with prices on it.
:func:`tagged_duplicate_of` is the reverse lookup that lets a reader fold the
duplicate's markets onto the canonical instead, and it is a READ: nothing is
merged, deleted or repointed, and reverting one predicate puts it all back.
That distinction is the one ``tennis_twin_pairs`` and
``repair_2878_tennis_twin_ghosts`` both draw, and it is why ruling 048 permits
this and would not permit an ``UPDATE futures_markets SET event_id``.

## Why the reverse lookup is an operator and not a LIKE

``not_a_proven_duplicate`` matches the PREFIX, has no fixed value to test, and
is a portable ``CAST … LIKE`` for that reason. The reverse lookup knows the
exact canonical id, so it can name the exact array element — and that turns out
to matter enormously, because it is the difference between an index and a table
scan. Measured on production 2026-09-07, same row, ``EXPLAIN (ANALYZE, BUFFERS)``
root node:

    events.event_tags @> '["provenance:duplicate-of:15304938"]'
        Bitmap Index Scan, ix_events_event_tags        5 blocks     0.06 ms
    CAST(event_tags AS text) LIKE '%"…:15304938"%'
        Seq Scan                                 105,540 blocks  8,296 ms

Four orders of magnitude, on a read that runs on every event page. The GIN index
``ix_events_event_tags (event_tags jsonb_path_ops)`` already exists, so this
needs no migration — it needs the operator the index can answer.

``@>`` is Postgres-only and this repo's guard suite executes against SQLite, so
the predicate is a compiled construct with two renderings rather than a choice
between "fast" and "testable". ``test_proven_duplicate_2263`` pins BOTH: that
SQLite returns the right rows, and that the Postgres rendering is still the one
the index can serve — a silent fall back to ``LIKE`` would keep every test green
and put an eight-second scan on the event page.

Quoting the element (``'%"<tag>"%'``) rather than the bare tag is load-bearing
in the portable arm: ``duplicate-of:1530`` is a prefix of
``duplicate-of:15304938``, and an unquoted LIKE would fold a completely
different match's markets onto the page.
"""

from __future__ import annotations

import re

from sqlalchemy import Boolean, String, func, or_, select
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import ColumnElement

from app.models.models import Event
from app.services.anchor_channel import DUPLICATE_TAG_PREFIX, duplicate_tag

#: The LIKE pattern matching any `provenance:duplicate-of:<id>` element inside
#: the serialised `event_tags` array.
_DUPLICATE_TAG_LIKE = f"%{DUPLICATE_TAG_PREFIX}%"


def not_a_proven_duplicate():
    """A predicate admitting every row NOT proven to duplicate another.

    Use it in any surface that renders one card per game. It is a plain
    ``WHERE`` clause, so it composes with whatever else the surface already
    filters on and costs no join.

    ``event_tags`` is nullable and the overwhelming majority of rows carry no
    tags at all, so the NULL arm is the common case and is stated first. A bare
    ``NOT LIKE`` would drop every untagged row on the floor — ``NULL NOT LIKE x``
    is NULL, not TRUE — which would empty every rail this is added to. That is
    the whole reason this is a function and not an expression pasted into four
    call sites.
    """
    return or_(
        Event.event_tags.is_(None),
        func.cast(Event.event_tags, String).notlike(_DUPLICATE_TAG_LIKE),
    )


class _TaggedDuplicateOf(ColumnElement):
    """``events.event_tags`` carries ``provenance:duplicate-of:<canonical>``.

    One meaning, two renderings, chosen by the dialect at compile time — see the
    module docstring for the 4-orders-of-magnitude measurement that made the
    Postgres rendering non-negotiable and the SQLite one necessary anyway.
    """

    #: A WHERE-clause boolean, so `select().where()` composes with it.
    type = Boolean()
    #: The construct is immutable and its only state is the tag string, which is
    #: a bind value on both arms — so the compiled form is safely cacheable.
    inherit_cache = True

    def __init__(self, canonical_event_id: int):
        self.tag = duplicate_tag(canonical_event_id)


@compiles(_TaggedDuplicateOf, "postgresql")
def _tagged_duplicate_of_postgresql(element, compiler, **kw):
    """`@>` against the exact array element — answered by `ix_events_event_tags`."""
    return compiler.process(Event.event_tags.contains([element.tag]), **kw)


@compiles(_TaggedDuplicateOf)
def _tagged_duplicate_of_portable(element, compiler, **kw):
    """Everything else (the guard suite's SQLite): the quoted-element LIKE.

    The quotes are the whole correctness of this arm — see the module docstring.
    """
    return compiler.process(
        func.cast(Event.event_tags, String).like(f'%"{element.tag}"%'), **kw
    )


def tagged_duplicate_of(canonical_event_id: int):
    """A predicate selecting every row proven to duplicate ``canonical_event_id``.

    The reverse of :func:`not_a_proven_duplicate`: that one asks "should I print
    this row?", this one asks "whose content did I just decline to print?".
    """
    return _TaggedDuplicateOf(canonical_event_id)


async def folded_event_ids(db, canonical_event_id: int) -> list[int]:
    """``canonical_event_id`` plus every row tagged as a duplicate of it.

    The id set a surface should read CONTENT from when it renders one card for
    ``canonical_event_id``. The canonical is always first and always present, so
    a caller can use the result unconditionally and a lookup that finds nothing
    degrades to exactly today's behaviour rather than to an empty page.

    🔴 **Never use this to decide which row to PRINT.** That is
    :func:`not_a_proven_duplicate`, and the two must not be confused: printing
    every id in this list is printing the duplicate card again.

    Errors are not swallowed. This is one indexed lookup costing ~0.06 ms and 5
    blocks; if it fails, the database is failing and a bare ``except`` here
    would turn that into a page that silently loses its prices (gotcha #53).
    """
    rows = await db.execute(
        select(Event.id).where(tagged_duplicate_of(canonical_event_id))
    )
    return [canonical_event_id] + [
        eid for eid in rows.scalars().all() if eid != canonical_event_id
    ]


# ── Folding a TIME SERIES is not folding a market (#3810) ────────────────────
#
# `folded_event_ids` is enough for `futures_markets` because a market is
# self-describing: it names its own outcomes, so it means the same thing
# whichever row it is read from. A `win_prob_snapshots` row is not. It stores
# `home_win_probability` — a number whose meaning is supplied entirely by
# ITS OWN event row's `home_team_name`. Fold two rows that disagree about which
# player is "home" and the chart draws one player's curve as the other's:
# a confidently-plotted, exactly-inverted line. That is worse than the omission
# this issue exists to fix, so the series fold checks orientation and the market
# fold does not.
#
# Measured on production 2026-09-07 over all 12 tagged US Open pairs: orientation
# agrees 12/12 — the ghost says "Shelton", the canonical says "Ben Shelton", and
# the slots correspond in every pair. So this check is a no-op on today's
# population BY MEASUREMENT, not by hope; it is here for the pair that does not
# agree, which nothing else in the system would catch.


def _name_tokens(name: str | None) -> frozenset[str]:
    """Lowercased word tokens of a team/player name, punctuation dropped."""
    if not name:
        return frozenset()
    return frozenset(t for t in re.sub(r"[^\w\s]", " ", name.casefold()).split() if t)


def _same_side(a: str | None, b: str | None) -> bool:
    """True when two spellings denote the same side of one fixture.

    Token subset in EITHER direction, because the two rows spell one player at
    different lengths — the Kalshi-ingested ghost carries ``Shelton`` where the
    canonical carries ``Ben Shelton``.

    Subset and not last-token equality: ``Red Sox`` and ``White Sox`` share a
    last token and are different teams, and this predicate decides whether to
    plot a curve under someone else's name.

    An empty or missing name matches nothing. `home_team_name` is NOT NULL in
    the model, but a blank string reaches here as the empty token set, and
    ``frozenset() <= anything`` is True — so the emptiness test is what stops a
    nameless row from matching both sides at once.
    """
    ta, tb = _name_tokens(a), _name_tokens(b)
    if not ta or not tb:
        return False
    # `issubset` rather than `<=`: identical for sets, but `<=` reads as a total
    # order (and CodeQL's `py/redundant-comparison` flags `x <= y or y <= x` as a
    # tautology on that reading). Subset is a PARTIAL order — `{red,sox}` and
    # `{white,sox}` are incomparable, which is exactly the case this must catch.
    return ta.issubset(tb) or tb.issubset(ta)


def orientation_agrees(
    canonical_home: str | None,
    canonical_away: str | None,
    other_home: str | None,
    other_away: str | None,
) -> bool:
    """True when ``other``'s home/away slots hold the same sides as the canonical's.

    Both directions are asserted, because "aligned" alone is safe against only
    one of the two failures. ``aligned`` rules out a straight swap; ``crossed``
    rules out the AMBIGUOUS pair — two sides whose names match each other as
    well as they match themselves (a Williams v Williams, a Red Sox v White Sox
    near-miss) — where "aligned" can be true by accident. A pair that is both
    aligned and crossed tells us the names cannot distinguish the sides, and the
    honest answer there is to refuse the fold, not to pick one.
    """
    aligned = _same_side(canonical_home, other_home) and _same_side(
        canonical_away, other_away
    )
    crossed = _same_side(canonical_home, other_away) or _same_side(
        canonical_away, other_home
    )
    return aligned and not crossed


async def folded_series_event_ids(db, canonical_event_id: int) -> list[int]:
    """Ids safe to read an ORIENTED time series from for ``canonical_event_id``.

    :func:`folded_event_ids` restricted to the rows whose home/away slots agree
    with the canonical's — see :func:`orientation_agrees`. The canonical is
    always first and always present, so an untagged event returns
    ``[canonical_event_id]`` and the caller compiles to exactly the read it had
    before this existed.

    One indexed lookup, same shape and cost as :func:`folded_event_ids` (the
    ``OR id =`` arm adds the canonical's own row so its names arrive in the same
    round trip). Errors are not swallowed, for the reason given there.
    """
    rows = (
        await db.execute(
            select(Event.id, Event.home_team_name, Event.away_team_name).where(
                or_(
                    Event.id == canonical_event_id,
                    tagged_duplicate_of(canonical_event_id),
                )
            )
        )
    ).all()

    canonical = next((r for r in rows if r[0] == canonical_event_id), None)
    if canonical is None:
        # The canonical itself did not come back (deleted mid-request). Say so
        # by returning the id anyway: the caller's query then finds nothing,
        # which is the truth, rather than folding ghosts onto a row that is gone.
        return [canonical_event_id]

    return [canonical_event_id] + [
        eid
        for eid, home, away in rows
        if eid != canonical_event_id
        and orientation_agrees(canonical[1], canonical[2], home, away)
    ]


def series_row_for_each_source(
    counts: dict[tuple[str, int], int], canonical_event_id: int
) -> dict[str, int]:
    """Pick ONE event row per source to draw that source's series from.

    ``counts`` maps ``(source, event_id)`` to how many snapshots that pair holds;
    the result maps each source to the single ``event_id`` whose readings should
    be plotted for it.

    One row per source, never a union, because the two rows' readings of the
    SAME source are two partial recordings of one price history, and
    concatenating them by timestamp interleaves a stray point into an otherwise
    clean line. Specimen: canonical 15305016 holds ``polymarket × 461`` while its
    ghost 15304989 holds ``polymarket × 1``; merging draws 462 points, one of
    which comes from somewhere else, and the defect it produces is a visible jag
    rather than an error.

    Richest wins, rather than "canonical wins", because the reason this fold
    exists is that the canonical is often the poorer row: on that same pair the
    ghost holds ``kalshi × 1,446`` and the canonical holds none. A rule that
    preferred the canonical would keep a 2-point stub over a 1,446-point curve
    the moment the canonical had any readings at all.

    Ties break to the canonical, then to the lowest id, so the chart a page draws
    does not depend on row order.
    """
    chosen: dict[str, int] = {}
    for source, event_id in sorted(counts):
        best = chosen.get(source)
        if best is None:
            chosen[source] = event_id
            continue
        rank = (counts[(source, event_id)], event_id == canonical_event_id, -event_id)
        best_rank = (counts[(source, best)], best == canonical_event_id, -best)
        if rank > best_rank:
            chosen[source] = event_id
    return chosen
