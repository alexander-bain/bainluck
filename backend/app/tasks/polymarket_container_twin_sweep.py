"""Tag the Polymarket container row as a duplicate, so its markets serve. #5821.

**SHIP: a match page stops hiding its spread and every total on a duplicate row
the page has already folded away.** (Pillar: MATCHING.)

This is the WRITE half. :mod:`app.utils.polymarket_container_twins` decides; this
module reads the window, banks the prior value and appends one element.

One element is appended to the duplicate's ``event_tags``::

    provenance:duplicate-of:<canonical event id>

which ``app.utils.proven_duplicates.folded_event_ids`` already turns into "serve
this row's markets on the canonical's page" inside ``_build_game_markets``. The
duplicate keeps its row, its id and its markets; nothing is merged, deleted or
repointed, and ``scripts/restore_5821_container_twin_tags.py --apply`` removes
exactly the element this wrote (D51).

WHY THIS IS THE REPAIR AND NOT THE ONE THE ISSUE FIRST PLANNED
═══════════════════════════════════════════════════════════════

CERT-2793 BLOCKed the forward fix for being forward-only and named this repair
``5821-EXISTING-SPLIT-CONTAINERS-COLLAPSE``. The plan recorded on the issue on
2026-09-13 was to re-date ~4,760 rows from ``venue_game_start`` so that the
existing ``fold_twin_events`` key would group them.

**That is no longer the population and this sweep deliberately does not do it.**
Re-measured 2026-09-17: the pairs now share a commence instant exactly, the card
fold already collapses them, and ``/api/events/search`` returns one row. What
survives is the half a card fold cannot reach — the fold hides the card and
leaves the loser's markets on the loser. So the repair is a tag, not a
4,760-row rewrite of a time column during launch week.

THE VERDICT CONTRACT
════════════════════

The band sits on the POPULATION, never on the plan. The legacy split families
are a fixed backlog that this sweep drains and the forward fix
(``_polymarket_container_sibling_event_id``, ``d15f9b4d8``) stops refilling —
container rows minted fell from 85/day and 50/day on 09-12/13 to 0–2/day since.
So an empty plan is the HEALTHY end state here, and a plan floor would start
failing on exactly the day the ship is finished. ``markets_read`` is the floor
that proves the pass still reached its rows.

Refs #5821, #2693, CERT-2793.
"""

from __future__ import annotations

import asyncio
import json

from app.services.anchor_channel import DUPLICATE_TAG_PREFIX, duplicate_tag
from app.utils.polymarket_container_twins import (
    ContainerMarket,
    ContainerRow,
    plan_container_tags,
)

#: D51 backup. Holds each duplicate's `event_tags` exactly as they were before
#: the append, plus the canonical the tag names, so the undo can remove ONE
#: element rather than clobber a shared multi-valued column.
#:
#: Its own table rather than the soccer or tennis sweep's, deliberately: sharing
#: one would make the repairs' undos inseparable, and "roll back the container
#: sweep" would silently restore every soccer ghost too.
BAK_TABLE = "bak_5821_container_twin_tags"

#: The window the sweep reads, in days either side of now.
#:
#: Symmetric, and both halves are load-bearing. The LOOKAHEAD carries the rows a
#: reader can still open — 60 of the 180 families measured on 2026-09-17 had not
#: kicked off. The LOOKBACK carries the rest: a split family does not heal when
#: the match ends, and a settled page that draws no totals is the same defect
#: with the same fix.
#:
#: Measured before it was chosen rather than argued: ±45 days reads 11,391
#: market rows over 1,845 events, which is one bounded SELECT of small tuples.
DEFAULT_LOOKBACK_DAYS = 45
DEFAULT_LOOKAHEAD_DAYS = 45


async def load_rows(session, *, lookback: int, lookahead: int):
    """Every Polymarket market carrying both venue signals, plus its row's ids.

    Returns ``(markets, rows, current_tags)``.

    Markets with no ``venue_game_start`` are not read at all. One of the two
    venue signals is missing, the key cannot be formed, and the judgement would
    skip them anyway — leaving them in the read would only make the population
    floor below look healthier than the evidence is.
    """
    from sqlalchemy import text

    result = await session.execute(
        text(
            "SELECT fm.event_id, fm.name, "
            "       fm.market_metadata->>'venue_game_start' AS vgs, "
            "       e.espn_id, e.statpal_fixture_id, "
            "       CAST(COALESCE(e.event_tags, '[]'::jsonb) AS text) AS tags_text "
            "FROM futures_markets fm "
            "JOIN events e ON e.id = fm.event_id "
            "WHERE fm.source = 'polymarket' "
            "  AND fm.market_metadata->>'venue_game_start' IS NOT NULL "
            "  AND e.commence_time BETWEEN "
            "        now() - CAST(:lookback AS interval) "
            "    AND now() + CAST(:lookahead AS interval)"
        ),
        {"lookback": f"{lookback} days", "lookahead": f"{lookahead} days"},
    )

    markets: list[ContainerMarket] = []
    starts: dict[int, set[str]] = {}
    ids: dict[int, tuple[object, object]] = {}
    current_tags: dict[int, str] = {}

    for row in result:
        markets.append(
            ContainerMarket(
                event_id=row.event_id, name=row.name or "", venue_game_start=row.vgs
            )
        )
        starts.setdefault(row.event_id, set()).add(row.vgs)
        ids[row.event_id] = (row.espn_id, row.statpal_fixture_id)
        current_tags[row.event_id] = row.tags_text or "[]"

    rows = {
        event_id: ContainerRow(
            event_id=event_id,
            espn_id=ids[event_id][0],
            statpal_fixture_id=ids[event_id][1],
            venue_game_starts=frozenset(starts.get(event_id, ())),
        )
        for event_id in ids
    }
    return markets, rows, current_tags


def already_tagged_ids(current_tags: dict[int, str]) -> set[int]:
    """Which rows already carry SOME `duplicate-of` tag.

    A row already proven a duplicate of something is left entirely alone. It is
    not re-judged and it is not given a second canonical — two ``duplicate-of``
    elements on one row is a state no consumer has a rule for, and this sweep
    must never be the thing that creates it.
    """
    return {
        event_id
        for event_id, tags in current_tags.items()
        if DUPLICATE_TAG_PREFIX in (tags or "")
    }


def fold_is_live() -> bool:
    """Is ``_build_game_markets`` still the consumer that makes this pay?

    The tag is inert on its own: it suppresses a card that ``fold_twin_events``
    already suppresses, and the ENTIRE user-visible effect of this sweep is that
    ``folded_event_ids`` serves the duplicate's markets on the canonical's page.
    If that call is ever removed, this sweep keeps writing tags and quietly
    delivers nothing — the exact shape of a repair that passes its own mechanism
    and ships no ship. The same guard the tennis and soccer sweeps carry, for
    the same reason.
    """
    import inspect

    try:
        from app.routes.events import folded_market_read_filters

        return "folded_event_ids" in inspect.getsource(folded_market_read_filters)
    except Exception:  # noqa: BLE001 — unreadable source is not proof it is live
        return False


async def ensure_backup(session, tags, current_tags: dict[int, str]) -> int:
    """Bank each duplicate's CURRENT `event_tags` before anything is appended.

    ``ON CONFLICT DO NOTHING`` keeps the FIRST banked value, which is the
    pre-repair one: a re-run after a partial apply must not overwrite a clean
    banked array with one that already carries the tag we wrote.
    """
    from sqlalchemy import text

    await session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BAK_TABLE} ("
            "  event_id bigint PRIMARY KEY,"
            "  canonical_id bigint NOT NULL,"
            "  old_tags text NOT NULL,"
            "  banked_at timestamptz NOT NULL DEFAULT now())"
        )
    )
    await session.commit()

    banked = 0
    for tag in tags:
        result = await session.execute(
            text(
                f"INSERT INTO {BAK_TABLE} (event_id, canonical_id, old_tags) "
                "VALUES (:eid, :cid, :old) ON CONFLICT (event_id) DO NOTHING"
            ),
            {
                "eid": tag.duplicate_id,
                "cid": tag.canonical_id,
                "old": current_tags.get(tag.duplicate_id, "[]"),
            },
        )
        banked += result.rowcount or 0
    await session.commit()
    return banked


async def write_tags(session, tags, *, progress_every: int = 0):
    """Append the duplicate tag to each row, ONE ROW PER TRANSACTION.

    Core SQL with a server-side ``||``, never an ORM assignment: ``event_tags``
    is JSONB and gotcha #4 is that a JSONB ORM assignment can silently fail to
    persist. The ``NOT @>`` makes it idempotent in the DATABASE rather than in
    this process's memory, so a re-run cannot double-append.

    Returns ``(written, failed_ids)``. Failures are RETAINED, not merely
    printed: on a worker whose stdout nobody reads, a printed FAILED line that
    never reaches the caller is indistinguishable from a clean run (gotcha #53).
    """
    from sqlalchemy import text

    written, failed = 0, []
    for index, tag in enumerate(tags, start=1):
        payload = json.dumps([duplicate_tag(tag.canonical_id)])
        for attempt in (1, 2, 3):
            try:
                result = await session.execute(
                    text(
                        "UPDATE events "
                        "SET event_tags = COALESCE(event_tags, '[]'::jsonb) "
                        "                 || CAST(:tag_array AS jsonb) "
                        "WHERE id = :eid "
                        "  AND NOT COALESCE(event_tags, '[]'::jsonb) "
                        "          @> CAST(:tag_array AS jsonb)"
                    ),
                    {"tag_array": payload, "eid": tag.duplicate_id},
                )
                await session.commit()
                written += result.rowcount or 0
                break
            except Exception as exc:  # noqa: BLE001 — retry, then surface
                await session.rollback()
                if attempt == 3:
                    print(f"  FAILED event {tag.duplicate_id} after 3 attempts: {exc}")
                    failed.append(tag.duplicate_id)
                else:
                    await asyncio.sleep(attempt)
        if progress_every and index % progress_every == 0:
            print(f"  … {index}/{len(tags)} processed, {written} tagged")
    return written, failed


async def tagged_now(session, duplicate_ids) -> set[int]:
    """Which of ``duplicate_ids`` carry a `duplicate-of` tag, read back from disk.

    The post-write proof, and it re-reads rather than trusting ``rowcount``:
    :func:`write_tags` is idempotent in the database, so a row that was already
    tagged returns 0 and a row whose write silently did not land returns 0 too.
    Only a read tells those apart (gotcha #53).
    """
    from sqlalchemy import text

    if not duplicate_ids:
        return set()
    rows = (
        await session.execute(
            text(
                "SELECT id FROM events "
                "WHERE id = ANY(:ids) "
                "  AND CAST(COALESCE(event_tags, '[]'::jsonb) AS text) LIKE :pat"
            ),
            {"ids": list(duplicate_ids), "pat": f"%{DUPLICATE_TAG_PREFIX}%"},
        )
    ).all()
    return {r.id for r in rows}


async def run_polymarket_container_twin_sweep(
    *,
    apply: bool = True,
    lookback: int = DEFAULT_LOOKBACK_DAYS,
    lookahead: int = DEFAULT_LOOKAHEAD_DAYS,
) -> dict:
    """One scheduled pass: read the window, plan, bank, tag. Returns the summary.

    ``apply`` defaults to TRUE, for the reason its two siblings do: this appends
    a reversible label with no deleter and banks the prior value first, which is
    exactly D51's shape. A dry-run schedule would measure the defect every hour
    and leave the page drawing no spread and no total.
    """
    from app.tasks.base import get_task_session

    summary: dict = {
        "task": "polymarket_container_twin_sweep",
        "issue": "#5821",
        "fold": "#2693",
        "apply": apply,
        "measured": True,
        "lookback_days": lookback,
        "lookahead_days": lookahead,
    }

    async with get_task_session() as session:
        try:
            markets, rows, current_tags = await load_rows(
                session, lookback=lookback, lookahead=lookahead
            )
        except Exception as exc:  # noqa: BLE001 — "I could not look" is not "nothing to do"
            await session.rollback()
            return {
                **summary,
                "measured": False,
                "terminal": "failed",
                "reason": f"population read raised: {type(exc).__name__}: {exc}"[:300],
            }

        if not markets:
            return {
                **summary,
                "terminal": "no_work",
                "markets_read": 0,
                "reason": (
                    f"no Polymarket markets carrying venue_game_start in the "
                    f"window (-{lookback}d/+{lookahead}d), so this pass can "
                    f"vouch for nothing"
                ),
            }

        plan = plan_container_tags(markets, rows)
        tagged = already_tagged_ids(current_tags)
        todo = [t for t in plan.tags if t.duplicate_id not in tagged]
        folding = fold_is_live()

        summary.update(
            {
                "markets_read": len(markets),
                "rows_read": plan.rows_considered,
                "keys_examined": plan.keys_examined,
                # Beside the total and never folded into it: a join that stops
                # attaching markets takes THIS to zero while `keys_examined`
                # stays healthy, and only the pair says which half went dark.
                "split_keys_examined": plan.split_keys_examined,
                "pairs_found": len(plan.tags),
                "refusals": len(plan.refusals),
                "refusal_samples": plan.refusals[:10],
                "already_tagged": len(plan.tags) - len(todo),
                "to_tag": len(todo),
                # The consumer check, reported whether or not there is work: a
                # sweep whose fold has been removed writes tags that deliver
                # nothing, and that must be visible on a quiet day too.
                "fold_live": folding,
            }
        )

        if not todo:
            return {
                **summary,
                "terminal": "no_work",
                "reason": (
                    "every split family in the window is already tagged — the "
                    "healthy end state for a drained backlog"
                ),
            }

        if not apply:
            return {**summary, "terminal": "planned", "tagged": 0}

        banked = await ensure_backup(session, todo, current_tags)
        written, failed = await write_tags(session, todo, progress_every=50)
        confirmed = await tagged_now(session, [t.duplicate_id for t in todo])

        return {
            **summary,
            "terminal": "applied" if not failed else "partial",
            "banked": banked,
            "tagged": written,
            # Read back from disk, not `rowcount`. See `tagged_now`.
            "confirmed_on_disk": len(confirmed),
            "failed": failed[:20],
            "failed_count": len(failed),
        }
