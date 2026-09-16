"""One question, one row — drop a settled-and-lost rung that duplicates a live one.

Sibling of :mod:`app.utils.duplicate_condition_outcomes`, which drops a
``_yes``/``_no`` leg that duplicates its own bare rung. Same family (one
condition, one outcome, decided per market on a POSITIVE fact), different
population, so it is kept in its own module rather than widening that one's
pinned suite.

WHAT A READER SEES (#6508, measured on production 2026-09-16)
=============================================================

``GET /api/futures/113486`` — *"Will Zelenskyy talk to Putin by...?"* — serves::

    December 31    10.0%
    December 31     0.0%

Two rows, one label, two answers, and nothing on the page that tells them
apart. Four boards print exactly this (``112914`` Lyman, ``113039`` and
``113040`` Israel×Hamas, ``113486`` Zelenskyy) and a fifth prints it twice over
(``112938`` Fed Chair — ``Rick Rieder`` and ``James Bullard``).

REACH, MEASURED ON THE POPULATION THIS CODE SERVES
==================================================

Those six labels are what #6508 names. They are not the reach. One query over
all **36,369 open markets** (``JOIN LATERAL`` off ``futures_markets``) says the
rule fires on **13 labels across 12 boards**: the six above, plus seven
Polymarket tennis boards — ``61121801``, ``61121805``, ``61121812``,
``61141858``, ``61167356``, ``61167377``, ``61167383``.

The tennis seven are the same shape, not a second population. On ``61121801``
the repeated label is the PROP leg ``W35 Shenyang: … Set Handicap +/-1.5``,
carried by two condition ids: one settled at ``0.000000`` and one live at
``0.375000``. One question, an old resolved leg and a current one — which is
the case above with a longer name. (They are emphatically *not* the two sides
of the match: the player rows, ``Valeria Savinykh`` and its opponent, appear
once each and are never touched.)

WHY THE ROWS ARE BOTH REAL, AND WHY DEDUP-BY-NAME IS THE WRONG FIX
==================================================================

Both rows are genuine venue markets; neither number is wrong. On the date
boards the pair is a **prior cycle** still attached: the venue's own
``end_date_iso`` reads ``2026-01-01`` on one leg and ``2027-01-01`` on the
other, and the closed one's slug says ``…-in-2025-816``. Deleting a row because
its NAME repeats would therefore delete a true row and pick the survivor on an
arbitrary sort key — the refutation is on #6508, where the same instinct would
have removed one of two genuinely distinct *"Mehmet Oz confirmed as …"*
questions.

AND WHY CAPTURING THE VENUE'S TEXT IS NOT THE FIX EITHER
========================================================

The obvious repair — keep the venue's member question and print the part that
differs — was measured against the venue before this was written, and it is
**inert on 8 of the 13 boards**: the two questions are byte-for-byte the same
string. ``113486`` serves *"Will Zelenskyy talk to Putin by December 31?"* for
BOTH legs; so do ``113039``, ``113040``, ``112900``, ``8414987``, ``13641466``
and ``112938``'s Rieder pair. There is no role, no year and no qualifier to
keep. Where a year does exist it is on the LIVE leg only — the closed Lyman
leg's question has no year at all, only its slug does.

THE FACT THAT DOES SEPARATE THEM IS ONE WE ALREADY STORE
========================================================

Every pair is one settled leg beside one unsettled leg. The settled one carries
``resolution_source`` (``'api_settlement'``) with ``is_winner=False`` — a
definite venue NO — while the live one carries ``resolution_source=NULL``. So
nothing has to be captured, ingested or parsed: the discriminator is in
``futures_outcomes`` today and the serializer simply never asked.

THREE GUARDS, AND EACH ONE IS A POPULATION THIS MUST NOT TOUCH
==============================================================

1. **A survivor must be UNSETTLED**, and that is ``_is_unsettled`` — a test on
   ``resolution_source`` alone, never ``not _is_definite_loss(...)``. When every
   row in the group is settled the rule stays silent: it cannot tell which
   result belongs to which question, and guessing would attach a real grade to
   the wrong one. This keeps it off ``189`` (Heisman, ``Josh Hoover`` under two
   Kalshi tickers, both graded) and ``109506`` (``Man I Need``, both graded).

   THE SPELLING IS THE WHOLE GUARD, and the first version of this module got it
   wrong. It asked for a sibling that was *not a definite loss*, and a settled
   WINNER is not a definite loss — so a winner anchored the group and the rule
   dropped the graded loser beside it. Measured over all 36,369 open markets
   (not the 13 boards the issue named), that wrong spelling fired on five extra
   labels, every one of them deleting a true result:

   * ``109373`` *"How many Senators vote to confirm … as Chair"* — ten rungs
     share one name, nine graded losses and one win. It dropped **nine graded
     rungs** and left one, and ``outcome_count`` then called a ten-rung ladder
     a one-rung one.
   * ``61085841``, ``61110424``, ``61135826``, ``61141865`` — settled tennis
     prop legs (``… Set Handicap +/-1.5`` carried by two condition ids), one
     graded win and one graded loss. It dropped the loss.

   A census taken on the population the ISSUE named could not see any of them,
   because this runs in ``_format_market_detail``, which serves every board.

2. **A survivor must be ID-ANCHORED.** A row whose ``external_id`` is blank has
   no venue leg behind it, so it cannot be the thing a settled row is
   superseded BY. Without this guard the rule would fire on ``113545`` and
   ``114237``, drop the priced-and-graded row, and leave the reader looking at
   a lone unbacked row reading **100%** — strictly worse than the duplicate it
   removed. Those two rows are #6524 and are deliberately left alone here.

3. **Only a definite LOSS is dropped.** ``is_winner is False``, never a falsy
   test: ``None`` means ungraded, and an ungraded row is not a superseded one.
   A winner is never dropped under any circumstances — settled means settled.

WHAT IT DOES NOT CLAIM
======================

It does not assert the surviving row's price is trustworthy. On ``112938`` the
survivor's own venue question is the corrupted string ``"archWill Trump
nominate James Bullard as the next Fed chair?"`` with ``active=false``; whether
a deactivated leg should still be priced is a separate, unmeasured question and
is not answered here. What this fixes is narrower and complete: the page stops
printing one label twice with two different numbers.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Callable, Iterable


def _is_definite_loss(resolution_source, is_winner) -> bool:
    """Settled by the venue AND graded a loss.

    ``is_winner is False`` rather than ``not is_winner`` — see guard 3. A row
    with a grade but no verdict is ungraded for this purpose.
    """
    return bool(resolution_source) and is_winner is False


def _is_unsettled(resolution_source) -> bool:
    """The venue has not answered this leg.

    The anchor test, and deliberately NOT ``not _is_definite_loss(...)`` — a
    settled WINNER is not a definite loss, so that spelling admitted it as an
    anchor and let the rule drop a graded result. Guard 1 in full, with the
    five labels it was measured to be wrong on, is in the module docstring.
    """
    return not bool(resolution_source)


def superseded_name_twins(
    rows: Iterable,
    *,
    name_of: Callable,
    external_id_of: Callable,
    is_winner_of: Callable,
    resolution_source_of: Callable,
) -> list:
    """The rows that are a settled-and-lost duplicate of a live sibling.

    Accessors are passed in rather than read off the row, so this module stays
    free of any row shape and imports nothing from the ORM — the same contract
    its sibling :func:`~app.utils.duplicate_condition_outcomes.drop_duplicate_legs`
    keeps.

    Callers must pass the rows of ONE market. Grouping is by name, so rows from
    two markets would let a live rung on market A supersede a settled rung on
    market B; the caller owns that scoping, deliberately.
    """
    rows = list(rows)

    by_name: dict = defaultdict(list)
    for row in rows:
        name = name_of(row)
        if not name:
            continue
        by_name[name].append(row)

    superseded = []
    for group in by_name.values():
        if len(group) < 2:
            continue
        # Guards 1 and 2: the row that supersedes must itself be unsettled AND
        # backed by a venue id. Absence of such a row means we say nothing.
        has_live_anchor = any(
            _is_unsettled(resolution_source_of(r))
            and str(external_id_of(r) or "").strip()
            for r in group
        )
        if not has_live_anchor:
            continue
        superseded.extend(
            r
            for r in group
            if _is_definite_loss(resolution_source_of(r), is_winner_of(r))
        )
    return superseded


def drop_superseded_name_twins(
    rows: Iterable,
    *,
    name_of: Callable,
    external_id_of: Callable,
    is_winner_of: Callable,
    resolution_source_of: Callable,
) -> list:
    """``rows`` with every superseded name twin removed, order preserved.

    Callers rank before or after this and must not have their sequence
    reshuffled underneath them.
    """
    rows = list(rows)
    drop = superseded_name_twins(
        rows,
        name_of=name_of,
        external_id_of=external_id_of,
        is_winner_of=is_winner_of,
        resolution_source_of=resolution_source_of,
    )
    if not drop:
        return rows
    drop_ids = {id(r) for r in drop}
    return [r for r in rows if id(r) not in drop_ids]


__all__ = ["drop_superseded_name_twins", "superseded_name_twins"]
