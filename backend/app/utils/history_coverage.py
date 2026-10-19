"""#10090 — `history_fold_revision`: which source revisions a fresh chart build has read past.

## the ship

A source-removal recovery can finish honestly when the event's valid chart has
no live edge to pin.

## why a second field

`blend_edge_fold_revision` is the revision of the fold the pinned edge's VALUE
came from, and it is null whenever nothing is pinned: a chart left with one
source after a removal, no win-probability series, a stale pre-match line, an
edge outside its window. In those legitimate cases a page holding a removal
floor (`{row_id: rev}` from the live frame or detail) could never learn that
the chart it was handed already reflects the removal, and it re-asked forever.

`history_fold_revision` is a different claim, and never a substitute value:

    every series this response draws was read at or after a database snapshot
    in which each listed row's `win_probability_sources_rev` was at least the
    listed number, and the build read exactly the listed rows.

It is NOT a probability to adopt, a source-observation clock, proof of a new
chart point, or permission to pin a historical edge. Same row-revision space
as detail's `blend_fold_revision` and the live frame's `rev`
(`app/utils/wps_revision.py`), so a client compares component-wise.

## how it is read, and why each check exists

The vector is read ONCE, by `folded_revision_vector` — the statement detail's
vector comes from, without the price bags this caller never uses — after the
build has resolved WHICH rows it will chart and BEFORE it reads any of their
history. Under READ COMMITTED
every later statement on the build's session sees every commit that statement
saw, so a removal it counts is in the snapshot rows read after it (the
withdrawal vertex commits with the bag change, `tasks/polymarket_ws.py`). A
revision read at the END would not do: a removal committing between the
history read and that read would be certified by a chart that never saw it.

Two inputs are read before the prefix, so each is checked against it rather
than trusted:

* MEMBERSHIP. `folded_series_event_ids` chose the rows the series reads use.
  The prefix re-derives the canonical + tagged-twin set in its own statement;
  if a twin was tagged or untagged in between, the two sets differ and there
  is no claim — otherwise the vector could name a row whose history was never
  read. Absorbed rows (#3391) come from one serve-time fold shared by both; a
  fold that crashed or hit its candidate cap is incomplete membership and
  makes no claim either.
* THE CANONICAL'S BAG. The ORM row loaded first is what this build reads its
  own bag from (scoring plays, the hero's speaking sources). The revision
  bumps on EVERY bag change, so equal revisions mean the identical bag; a bag
  that moved between the two reads makes no claim.

Everything that can make a body partial — a swallowed read error
(`event_history_cache.mark_partial`), a refill just enqueued — also makes no
claim, and only a `fresh=true` build makes one at all: an ordinary build may be
cached and served long after it was read.

Missing proof stays missing. Every refusal is ``None``, never a smaller vector
and never a borrowed one.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional


def _rev(value: Any) -> Optional[int]:
    # `bool` is an `int`; a True would compare as revision 1.
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def coverage_from_prefix(
    prefix_vector: Optional[dict],
    *,
    canonical_id: Any,
    canonical_loaded_rev: Any,
    read_row_ids: Iterable[Any],
    membership_complete: bool,
) -> Optional[dict[str, int]]:
    """The prefix vector, if it certifies exactly the rows this build reads.

    ``prefix_vector`` is `folded_revision_vector`'s vector,
    read before any history; ``read_row_ids`` are the rows the series reads use
    (`folded_series_event_ids`); ``canonical_loaded_rev`` is the revision on the
    canonical row this build took its own bag from.
    """
    if not membership_complete or not isinstance(prefix_vector, dict):
        return None
    if not prefix_vector or any(_rev(v) is None for v in prefix_vector.values()):
        return None
    try:
        read = {str(int(row_id)) for row_id in read_row_ids}
        canonical = str(int(canonical_id))
    except (TypeError, ValueError):
        return None
    if set(prefix_vector) != read or canonical not in read:
        return None
    loaded = _rev(canonical_loaded_rev)
    if loaded is None or prefix_vector[canonical] != loaded:
        return None
    return {key: int(value) for key, value in prefix_vector.items()}


async def read_coverage_prefix(
    db,
    event,
    absorbed,
    read_row_ids,
    *,
    membership_complete: bool,
) -> Optional[dict[str, int]]:
    """Read the revision vector a fresh history build may later certify.

    Call after the build has chosen its rows and before it reads any history.
    One indexed statement; errors are not swallowed, for the reason
    `folded_series_event_ids` gives (a failed read here aborts the transaction
    every later read shares, so hiding it would only move the failure).
    """
    from app.utils.proven_duplicates import folded_revision_vector

    vector = await folded_revision_vector(db, event, absorbed)
    return coverage_from_prefix(
        vector,
        canonical_id=getattr(event, "id", None),
        canonical_loaded_rev=getattr(event, "win_probability_sources_rev", None),
        read_row_ids=read_row_ids,
        membership_complete=membership_complete,
    )


def served_history_coverage(
    prefix: Optional[dict[str, int]],
    *,
    build_complete: bool,
    on_demand_backfill: Any,
) -> Optional[dict[str, int]]:
    """``prefix`` if the build that read it finished whole, else ``None``."""
    if prefix is None or not build_complete:
        return None
    if isinstance(on_demand_backfill, dict) and on_demand_backfill.get("enqueue"):
        return None
    return dict(prefix)
