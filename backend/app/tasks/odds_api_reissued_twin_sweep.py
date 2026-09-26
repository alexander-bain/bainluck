"""Label the Odds API row whose id the provider re-issued. #8422.

**SHIP: /search?q=arsenal lists Fleetwood Town v Arsenal once, at the real
kick-off — not twice, 19 hours apart.** (Pillar: MATCHING.)

This is the WRITE half. :mod:`app.utils.odds_api_reissued_twins` decides; this
module reads the window and the provider's free ``/events`` schedule, banks the
prior value and appends one element to the ghost's ``event_tags``::

    provenance:duplicate-of:<canonical event id>

whose read side already runs on search, the league and team rails and the feed
(:func:`app.utils.proven_duplicates.not_a_proven_duplicate`). Nothing is merged,
deleted or repointed; ``scripts/restore_8422_odds_api_reissued_tags.py --apply``
removes exactly the element this wrote (D51).

It also LIFTS its own label from a row whose id the provider lists again — the
label rests on one fact, and when the fact goes the label goes with it.

PROVIDER COST. ``/events`` costs no quota (``x-requests-last: 0``, measured
2026-09-25) and is read only for sports holding a candidate block or a banked
label, so a quiet pass makes no request at all.

THE VERDICT CONTRACT
════════════════════

The floor is on the POPULATION READ, like the soccer and container siblings: a
re-issue is episodic, so ``complete`` with ``tagged: 0`` is the healthy normal
state and a plan floor would be red most days. ``failed`` when the read raised,
the population fell under :data:`MIN_ROWS_FLOOR`, or the consumer predicate is
gone. A schedule read that raised is DAMAGE (``errors``), never a quiet zero:
its blocks are refused, and the run cannot read ``complete``.

A NEWER id the provider dropped is labelled only when its fully priced lines
all reappear on the listed sibling (#8755, :func:`lines_moved`); the pass reads
``odds_snapshots`` for block members only, so a quiet pass still reads nothing.

Refs #8422, #8755, #2693.
"""

from __future__ import annotations

import asyncio
import json
import os

from app.services.anchor_channel import DUPLICATE_TAG_PREFIX, duplicate_tag
from app.utils.odds_api_reissued_twins import (
    ReissueRow,
    candidate_blocks,
    plan_reissue_tags,
    relisted_banked_ids,
)

#: D51 backup: each ghost's `event_tags` before the append, the canonical the
#: tag names, and the ids that justified it. Its own table so this sweep's undo
#: never restores another sweep's rows.
BAK_TABLE = "bak_8422_odds_api_reissued_tags"

#: The window ahead of now. A re-issue is a future-fixture defect (the provider
#: drops played games from `/events`, so behind now the evidence means nothing).
#: 45 days reaches cup rounds drawn a month out — Fleetwood v Arsenal was 33.
DEFAULT_LOOKAHEAD_DAYS = 45

#: Non-vacuity floor on the rows READ. Measured 2026-09-25: 799 open Odds
#: API-anchored rows across 66 sports in the next 45 days. 100 sits 8x under
#: it — below any seasonal trough, above a read that lost its join.
MIN_ROWS_FLOOR = 100

#: Operator stop switch: any non-empty value stands the sweep down before it
#: touches the database. The restore script alone is not a rollback — the
#: planner selects on the ABSENCE of the tag, so the next pass would re-tag
#: (#6786's lesson). Stop, verify the `skipped` receipt, then restore.
REISSUED_TWIN_SWEEP_DISABLED_ENV = "REISSUED_TWIN_SWEEP_DISABLED"


def sweep_is_disabled() -> bool:
    return bool(os.getenv(REISSUED_TWIN_SWEEP_DISABLED_ENV, "").strip())


_ROW_SELECT = """
SELECT e.id, s.key AS sport_key, e.home_team_name, e.away_team_name,
       e.commence_time, e.status,
       array_agg(a.source_id ORDER BY a.source_id) AS odds_api_ids,
       min(a.first_seen_at) AS first_seen_at,
       CAST(COALESCE(e.event_tags, '[]'::jsonb) AS text) AS tags_text,
       (e.espn_id IS NOT NULL OR e.statpal_fixture_id IS NOT NULL
        OR EXISTS (SELECT 1 FROM event_provider_anchors o
                   WHERE o.event_id = e.id AND o.id_kind = 'game'
                     AND o.source <> 'odds_api')) AS other_anchor
FROM events e
JOIN sports s ON s.id = e.sport_id
JOIN event_provider_anchors a
  ON a.event_id = e.id AND a.source = 'odds_api' AND a.id_kind = 'game'
"""

_POPULATION_SQL = _ROW_SELECT + """
WHERE e.status IN ('scheduled', 'suspended')
  AND e.commence_time > now()
  AND e.commence_time < now() + make_interval(days => :lookahead)
GROUP BY e.id, s.key
"""

#: The same row shape for NAMED ids, with no status or clock filter — the
#: one-off repair's read (`scripts/repair_8755_newer_id_twin.py`), whose rows
#: are past the start the sweep's window requires. The judgement is unchanged.
_BY_ID_SQL = _ROW_SELECT + """
WHERE e.id = ANY(:ids)
GROUP BY e.id, s.key
"""

#: Each block member's FULLY priced lines (#8755). Distinct, so a row's hundreds
#: of snapshots cost one line per price change. The decimals are rendered by
#: Postgres on both rows, so the ghost and its sibling share one spelling.
_BOOK_LINES_SQL = """
SELECT DISTINCT event_id, bookmaker, home_moneyline, away_moneyline,
       CAST(home_spread AS text) AS home_spread, CAST(over_under AS text) AS over_under
FROM odds_snapshots
WHERE event_id = ANY(:ids)
  AND bookmaker IS NOT NULL
  AND home_moneyline IS NOT NULL AND away_moneyline IS NOT NULL
  AND home_spread IS NOT NULL AND over_under IS NOT NULL
"""


async def load_rows(session, *, lookahead: int) -> tuple[list[ReissueRow], dict[int, str]]:
    """Every open Odds API-anchored row in the window. Returns ``(rows, tags)``.

    The provider id comes from `event_provider_anchors` (source ``odds_api``,
    kind ``game``) — an explicit (provider, id) key, never inferred from the
    shape of ``external_id`` (D55).
    """
    from sqlalchemy import text

    result = await session.execute(
        text(_POPULATION_SQL), {"lookahead": int(lookahead)}
    )
    return _rows_from(result)


async def load_rows_by_id(session, ids) -> tuple[list[ReissueRow], dict[int, str]]:
    """The planner's row shape for NAMED ids, with no status or clock filter."""
    from sqlalchemy import text

    return _rows_from(await session.execute(text(_BY_ID_SQL), {"ids": list(ids)}))


async def load_book_lines(session, ids) -> dict[int, frozenset]:
    """``{event_id: frozenset of BookLine}`` for the named rows. #8755."""
    from sqlalchemy import text

    if not ids:
        return {}
    lines: dict[int, set] = {}
    result = await session.execute(text(_BOOK_LINES_SQL), {"ids": list(ids)})
    for r in result:
        lines.setdefault(r.event_id, set()).add(
            (r.bookmaker, int(r.home_moneyline), int(r.away_moneyline),
             r.home_spread, r.over_under)
        )
    return {eid: frozenset(v) for eid, v in lines.items()}


def _rows_from(result) -> tuple[list[ReissueRow], dict[int, str]]:
    rows, current_tags = [], {}
    for r in result:
        tags_text = r.tags_text or "[]"
        current_tags[r.id] = tags_text
        rows.append(
            ReissueRow(
                event_id=r.id,
                sport_key=r.sport_key,
                home=r.home_team_name or "",
                away=r.away_team_name or "",
                commence_time=r.commence_time,
                status=r.status,
                odds_api_ids=frozenset(r.odds_api_ids or ()),
                first_seen_at=r.first_seen_at,
                other_anchor=bool(r.other_anchor),
                already_tagged=DUPLICATE_TAG_PREFIX in tags_text,
            )
        )
    return rows, current_tags


async def load_banked_labels(session) -> dict[int, tuple[str, frozenset[str], int]]:
    """Rows still carrying THIS sweep's label: ``{id: (sport, odds ids, canonical)}``.

    Read through the bank, and only where the exact element this sweep wrote is
    still on the row — so a label already lifted, or restored by hand, is not
    lifted twice. A missing bank table means no label was ever written.
    """
    from sqlalchemy import text

    exists = (
        await session.execute(text("SELECT to_regclass(:t)"), {"t": BAK_TABLE})
    ).scalar()
    if not exists:
        return {}
    result = await session.execute(
        text(
            f"SELECT b.event_id, b.sport_key, b.ghost_odds_api_ids, b.canonical_id "
            f"FROM {BAK_TABLE} b JOIN events e ON e.id = b.event_id "
            f"WHERE COALESCE(e.event_tags, '[]'::jsonb) "
            f"      @> jsonb_build_array(CAST(:prefix AS text) || b.canonical_id::text)"
        ),
        {"prefix": DUPLICATE_TAG_PREFIX},
    )
    return {
        r.event_id: (r.sport_key, frozenset(r.ghost_odds_api_ids.split(",")), r.canonical_id)
        for r in result
    }


async def read_schedules(sport_keys, *, service=None) -> tuple[dict[str, set[str]], list[str]]:
    """``/events`` for each sport. Returns ``(schedules, errors)``.

    A sport whose read raised is ABSENT from ``schedules`` — the planner then
    refuses its blocks — and named in ``errors``, so the run reports damage
    instead of reading an unread schedule as an empty one.
    """
    from app.services.odds_api import OddsAPIService

    schedules: dict[str, set[str]] = {}
    errors: list[str] = []
    if not sport_keys:
        return schedules, errors
    own = service is None
    service = service or OddsAPIService()
    try:
        for sport in sorted(sport_keys):
            try:
                listed = await service.get_events(sport)
                schedules[sport] = {e["id"] for e in listed if e.get("id")}
            except Exception as exc:  # noqa: BLE001 — named, never swallowed
                errors.append(f"{sport}: {type(exc).__name__}: {exc}"[:200])
    finally:
        if own:
            await service.close()
    return schedules, errors


async def ensure_backup(session, tags, current_tags: dict[int, str]) -> int:
    """Bank each ghost's CURRENT `event_tags` before the append.

    ``ON CONFLICT DO NOTHING`` keeps the FIRST banked value — the pre-repair
    one — across re-runs and re-tags.
    """
    from sqlalchemy import text

    await session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BAK_TABLE} ("
            "  event_id bigint PRIMARY KEY,"
            "  canonical_id bigint NOT NULL,"
            "  sport_key text NOT NULL,"
            "  ghost_odds_api_ids text NOT NULL,"
            "  canonical_odds_api_ids text NOT NULL,"
            "  old_tags text NOT NULL,"
            "  banked_at timestamptz NOT NULL DEFAULT now())"
        )
    )
    await session.commit()
    banked = 0
    for tag in tags:
        result = await session.execute(
            text(
                f"INSERT INTO {BAK_TABLE} (event_id, canonical_id, sport_key, "
                f"  ghost_odds_api_ids, canonical_odds_api_ids, old_tags) "
                f"VALUES (:eid, :cid, :sk, :gid, :kid, :old) "
                f"ON CONFLICT (event_id) DO NOTHING"
            ),
            {
                "eid": tag.duplicate_id,
                "cid": tag.canonical_id,
                "sk": tag.sport_key,
                "gid": tag.ghost_odds_api_ids,
                "kid": tag.canonical_odds_api_ids,
                "old": current_tags.get(tag.duplicate_id, "[]"),
            },
        )
        banked += result.rowcount or 0
    await session.commit()
    return banked


async def _one_row_update(session, sql: str, params: dict) -> tuple[int, bool]:
    """One row, one transaction, three attempts (`events` is write-hot)."""
    from sqlalchemy import text

    for attempt in (1, 2, 3):
        try:
            result = await session.execute(text(sql), params)
            await session.commit()
            return result.rowcount or 0, True
        except Exception as exc:  # noqa: BLE001 — retry, then surface
            await session.rollback()
            if attempt == 3:
                print(f"  FAILED event {params.get('eid')}: {exc}")
                return 0, False
            await asyncio.sleep(attempt)
    return 0, False


async def write_tags(session, tags) -> tuple[int, list[int]]:
    """Append the tag — Core SQL, idempotent in the database (gotcha #4)."""
    written, failed = 0, []
    for tag in tags:
        n, ok = await _one_row_update(
            session,
            "UPDATE events "
            "SET event_tags = COALESCE(event_tags, '[]'::jsonb) || CAST(:tag_array AS jsonb) "
            "WHERE id = :eid "
            "  AND NOT COALESCE(event_tags, '[]'::jsonb) @> CAST(:tag_array AS jsonb)",
            {"tag_array": json.dumps([duplicate_tag(tag.canonical_id)]), "eid": tag.duplicate_id},
        )
        written += n
        if not ok:
            failed.append(tag.duplicate_id)
    return written, failed


async def lift_tags(session, lifts: dict[int, int]) -> tuple[int, list[int]]:
    """Remove exactly the element this sweep wrote, ``{ghost: canonical}``."""
    lifted, failed = 0, []
    for event_id, canonical_id in sorted(lifts.items()):
        n, ok = await _one_row_update(
            session,
            "UPDATE events SET event_tags = event_tags - CAST(:tag AS text) "
            "WHERE id = :eid AND event_tags @> jsonb_build_array(CAST(:tag AS text))",
            {"tag": duplicate_tag(canonical_id), "eid": event_id},
        )
        lifted += n
        if not ok:
            failed.append(event_id)
    return lifted, failed


async def tagged_now(session, ghost_ids) -> set[int]:
    """Which of ``ghost_ids`` carry a `duplicate-of` tag, read back from disk."""
    from sqlalchemy import text

    if not ghost_ids:
        return set()
    rows = (
        await session.execute(
            text(
                "SELECT id FROM events WHERE id = ANY(:ids) "
                "  AND CAST(COALESCE(event_tags, '[]'::jsonb) AS text) LIKE :pat"
            ),
            {"ids": list(ghost_ids), "pat": f"%{DUPLICATE_TAG_PREFIX}%"},
        )
    ).all()
    return {r.id for r in rows}


def consumer_is_live() -> bool:
    """Does search still decline a proven duplicate? That is the whole ship.

    The ghosts here carry no markets, so the reader-visible effect is purely
    that `not_a_proven_duplicate` drops the second card. If search stops
    calling it, the tag delivers nothing and must not be written.
    """
    import inspect

    try:
        from app.routes.events import search_events

        return "not_a_proven_duplicate" in inspect.getsource(search_events)
    except Exception:  # noqa: BLE001 — unreadable source is not proof it is live
        return False


async def run_odds_api_reissued_twin_sweep(
    *,
    apply: bool = True,
    lookahead: int = DEFAULT_LOOKAHEAD_DAYS,
    service=None,
    now=None,
) -> dict:
    """One scheduled pass: read, ask the provider, plan, bank, tag, lift."""
    from datetime import datetime, timezone

    from app.tasks.base import get_task_session

    now = now or datetime.now(timezone.utc)
    summary: dict = {
        "task": "odds_api_reissued_twin_sweep",
        "issue": "#8422",
        "apply": apply,
        "measured": True,
        "lookahead_days": lookahead,
    }
    if sweep_is_disabled():
        return {
            **summary,
            "measured": False,
            "terminal": "skipped",
            "tagged": 0,
            "disabled": True,
            "reason": (
                f"stood down: {REISSUED_TWIN_SWEEP_DISABLED_ENV} is set. Nothing "
                f"was read or written"
            ),
        }

    async with get_task_session() as session:
        try:
            rows, current_tags = await load_rows(session, lookahead=lookahead)
            banked = await load_banked_labels(session)
        except Exception as exc:  # noqa: BLE001 — "could not look" is not "nothing to do"
            await session.rollback()
            return {
                **summary,
                "measured": False,
                "terminal": "failed",
                "reason": f"population read raised: {type(exc).__name__}: {exc}"[:300],
            }

        if len(rows) < MIN_ROWS_FLOOR:
            return {
                **summary,
                "measured": False,
                "terminal": "failed",
                "rows_read": len(rows),
                "floor": MIN_ROWS_FLOOR,
                "reason": (
                    f"population floor: read {len(rows)} open Odds API-anchored rows "
                    f"in the next {lookahead}d, below {MIN_ROWS_FLOOR}. This pass "
                    f"could not look"
                ),
            }

        blocks = candidate_blocks(rows, now=now)
        sports = {b[0].sport_key for b in blocks} | {s for s, _, _ in banked.values()}
        schedules, errors = await read_schedules(sports, service=service)
        lines: dict[int, frozenset] = {}
        try:
            lines = await load_book_lines(session, [m.event_id for b in blocks for m in b])
        except Exception as exc:  # noqa: BLE001 — unread lines refuse, and say so
            await session.rollback()
            errors.append(f"book lines: {type(exc).__name__}: {exc}"[:200])
        plan = plan_reissue_tags(blocks, schedules, lines)
        relisted = relisted_banked_ids(
            {eid: (s, oid) for eid, (s, oid, _) in banked.items()}, schedules
        )
        lifts = {eid: banked[eid][2] for eid in relisted}
        consumer = consumer_is_live()

        summary.update(
            {
                "rows_read": len(rows),
                "blocks_examined": plan.blocks_examined,
                "schedules_read": len(schedules),
                "pairs_found": len(plan.tags),
                "refusals": len(plan.refusals),
                "refusal_samples": plan.refusals[:10],
                "labels_held": len(banked),
                "to_lift": len(lifts),
                "consumer_live": consumer,
                "plan_samples": [
                    {"ghost": t.duplicate_id, "canonical": t.canonical_id, "sport": t.sport_key}
                    for t in plan.tags[:10]
                ],
            }
        )

        if plan.tags and not consumer:
            return {
                **summary,
                "terminal": "failed",
                "tagged": 0,
                "reason": (
                    f"refusing to write {len(plan.tags)} tag(s): search no longer "
                    f"calls not_a_proven_duplicate, so the label would hide nothing"
                ),
            }

        if not apply:
            return {**summary, "terminal": "no_work", "tagged": 0, "planned": len(plan.tags)}

        written = lifted = banked_n = 0
        failed: list[int] = []
        missing: list[int] = []
        if plan.tags:
            banked_n = await ensure_backup(session, plan.tags, current_tags)
            written, failed = await write_tags(session, plan.tags)
            confirmed = await tagged_now(session, [t.duplicate_id for t in plan.tags])
            missing = sorted({t.duplicate_id for t in plan.tags} - confirmed)
        if lifts:
            lifted, lift_failed = await lift_tags(session, lifts)
            failed += lift_failed

        damage = errors or failed or missing
        return {
            **summary,
            "terminal": "partial" if damage else "complete",
            "banked": banked_n,
            "planned": len(plan.tags),
            "tagged": written,
            "lifted": lifted,
            "unconfirmed": missing[:20],
            # `errors` is the name `task_verdict._has_damage` reads.
            "errors": (errors + [f"event {i}: write failed" for i in failed])[:20],
        }
