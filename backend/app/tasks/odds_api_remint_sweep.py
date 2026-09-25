"""#7993 — the scheduled half of :mod:`app.utils.odds_api_remints`.

Reads every upcoming combat row carrying an Odds API id, asks the provider's
free ``/events`` listing about each sport that holds a same-pair group, and
appends ``provenance:duplicate-of:<canonical>`` to every row the provider has
re-minted. The judgement is in the util. This module owns the reads, the D51
backup and the write.

UNATTENDED UNDER D51, like its three siblings: a reversible label with no
deleter, the prior ``event_tags`` banked into :data:`BAK_TABLE` first, and
``scripts/restore_7993_odds_api_remint_tags.py --apply`` removes exactly the
element this task added.

THE VERDICT CONTRACT
════════════════════
``complete``  every listing it needed was read, and every decidable ghost carries
              its label. ``written: 0`` is the healthy steady state: re-mints are
              episodic, and on most runs there is nothing to fold.
``partial``   a listing could not be read, or a planned ghost is still untagged.
              The other sports' work stands.
``failed``    the population read raised (``measured: false``), or no needed
              listing could be read at all, so the run can vouch for nothing.
``no_work``   no upcoming combat row carries a provider id. That is "I looked
              and there was nothing", never GREEN.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.utils.odds_api_remints import (
    COMBAT_SPORT_PREFIXES,
    RemintRow,
    plan_remint_tags,
    sports_needing_listing,
)
from app.utils.proven_duplicates import canonical_id_from_tags

#: D51 backup: the ghost's `event_tags` as they were before the append, plus the
#: canonical the tag names, so the undo removes ONE element. Its own table, so
#: rolling this pairing back never touches another sweep's labels.
BAK_TABLE = "bak_7993_odds_api_remint_tags"

#: A superset read. `is_in_scope` re-applies every clause in Python, so this SQL
#: only chooses what to look at and licenses nothing. The patterns are bind
#: parameters because `text()` reads a literal `:x` as one (gotcha #45).
_POPULATION_SQL = """
SELECT e.id,
       s.key AS sport_key,
       e.external_id,
       e.home_team_name,
       e.away_team_name,
       e.commence_time,
       e.home_score,
       e.away_score,
       e.completed_at,
       CAST(COALESCE(e.event_tags, '[]'::jsonb) AS text) AS tags_text,
       CAST(COALESCE(e.win_probability_sources, '{}'::jsonb) AS text) AS sources_text
  FROM events e
  JOIN sports s ON s.id = e.sport_id
 WHERE (s.key LIKE :mma OR s.key LIKE :boxing)
   AND e.commence_time > now()
   AND e.external_id ~ :id_re
   AND e.status NOT IN ('voided', 'merged')
 ORDER BY e.id
"""


async def load_rows(session) -> list:
    from sqlalchemy import text

    mma, boxing = (f"{p}%" for p in COMBAT_SPORT_PREFIXES)
    return (
        await session.execute(
            text(_POPULATION_SQL),
            {"mma": mma, "boxing": boxing, "id_re": "^[0-9a-f]{32}$"},
        )
    ).all()


def price_sources(sources_text) -> frozenset[str]:
    """The weighted sources that hold a reading — the keys the hero fold can
    gap-fill from. Decided by `parse_source_entry`, never by key presence: a
    JSON `null` is a present key with no reading."""
    from app.utils.aggregation import SOURCE_WEIGHTS, parse_source_entry

    try:
        sources = json.loads(sources_text) if isinstance(sources_text, str) else sources_text
    except (TypeError, ValueError):
        return frozenset()
    if not isinstance(sources, dict):
        return frozenset()
    return frozenset(
        key
        for key, entry in sources.items()
        if key in SOURCE_WEIGHTS and parse_source_entry(entry)[0] is not None
    )


def to_remint_rows(rows) -> list[RemintRow]:
    """Plain scalars, copied before any commit boundary (gotcha #6)."""
    return [
        RemintRow(
            event_id=r.id,
            sport_key=r.sport_key,
            external_id=r.external_id,
            home_team_name=r.home_team_name,
            away_team_name=r.away_team_name,
            commence_time=r.commence_time,
            has_result=(
                r.home_score is not None
                or r.away_score is not None
                or r.completed_at is not None
            ),
            duplicate_of=canonical_id_from_tags(r.tags_text),
            price_sources=price_sources(r.sources_text),
        )
        for r in rows
    ]


async def fetch_listings(sports, service=None) -> tuple[dict, dict]:
    """``({sport: frozenset(ids)}, {sport: error})``. A sport whose listing raised
    is ABSENT from the first dict, so the planner refuses it rather than reading
    every one of its rows as dropped."""
    from app.services.odds_api import OddsAPIService

    listed: dict[str, frozenset[str]] = {}
    errors: dict[str, str] = {}
    if not sports:
        return listed, errors
    owned = service is None
    service = service or OddsAPIService()
    try:
        for sport in sorted(sports):
            try:
                events = await service.get_events(sport)
                listed[sport] = frozenset(
                    e["id"] for e in events if isinstance(e, dict) and e.get("id")
                )
            except Exception as exc:  # noqa: BLE001 — one sport's listing, not the run
                errors[sport] = f"{type(exc).__name__}: {exc}"[:200]
    finally:
        if owned:
            await service.close()
    return listed, errors


async def ensure_backup(session, tags, current_tags: dict[int, str]) -> int:
    """Bank each ghost's CURRENT `event_tags`. `DO NOTHING` keeps the first,
    pre-repair value if a later run re-banks the same row."""
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
                "eid": tag.ghost_id,
                "cid": tag.canonical_id,
                "old": current_tags.get(tag.ghost_id, "[]"),
            },
        )
        banked += result.rowcount or 0
    await session.commit()
    return banked


async def run_odds_api_remint_sweep(*, apply: bool = True, service=None) -> dict:
    """One pass: read, ask the provider, plan, bank, tag, read back."""
    from app.tasks.base import get_task_session
    from app.tasks.tennis_twin_sweep import tagged_now, write_tags

    summary: dict = {
        "task": "odds_api_remint_sweep",
        "issue": "#7993",
        "apply": apply,
        "measured": True,
    }
    now = datetime.now(timezone.utc)

    async with get_task_session() as session:
        try:
            raw = await load_rows(session)
        except Exception as exc:  # noqa: BLE001 — "I could not look" is not "nothing to do"
            await session.rollback()
            return {
                **summary,
                "measured": False,
                "terminal": "failed",
                "reason": f"population read raised: {type(exc).__name__}: {exc}"[:300],
            }
        if not raw:
            return {
                **summary,
                "terminal": "no_work",
                "reason": "no upcoming combat row carries an Odds API id",
                "rows_read": 0,
            }

        rows = to_remint_rows(raw)
        needed = sports_needing_listing(rows, now)
        listed, listing_errors = await fetch_listings(needed, service=service)
        plan = plan_remint_tags(rows, listed, now)

        summary.update(
            {
                "rows_read": len(rows),
                "listings_needed": sorted(needed),
                "listings_read": {s: len(ids) for s, ids in sorted(listed.items())},
                "listing_errors": listing_errors,
                "groups_examined": plan.groups_examined,
                "already_tagged": plan.already_tagged,
                "tags_to_write": len(plan.tags),
                "refusals": len(plan.refusals),
                "refusal_sample": plan.refusals[:20],
                "tag_sample": [
                    f"{t.ghost_id} -> {t.canonical_id}" for t in plan.tags[:20]
                ],
            }
        )

        if needed and not listed:
            return {
                **summary,
                "terminal": "failed",
                "reason": (
                    f"no provider listing could be read for {sorted(needed)}, so "
                    f"no same-pair group could be judged"
                ),
                "written": 0,
            }

        written, failed, still_untagged, banked = 0, [], [], 0
        if plan.tags and not apply:
            return {
                **summary,
                "terminal": "no_work",
                "reason": f"dry run — {len(plan.tags)} tag(s) withheld",
                "written": 0,
            }
        if plan.tags:
            current = {r.id: (r.tags_text or "[]") for r in raw}
            banked = await ensure_backup(session, plan.tags, current)
            written, failed = await write_tags(session, plan.tags, progress_every=0)
            after = await tagged_now(session, [t.ghost_id for t in plan.tags])
            still_untagged = [t.ghost_id for t in plan.tags if t.ghost_id not in after]

        problems = []
        if listing_errors:
            problems.append(f"listing unread for {sorted(listing_errors)}")
        if failed:
            problems.append(f"{len(failed)} row(s) exhausted retries: {failed[:20]}")
        if still_untagged:
            problems.append(
                f"{len(still_untagged)} planned ghost(s) untagged after the run: "
                f"{still_untagged[:20]}"
            )
        result = {
            **summary,
            "terminal": "partial" if problems else "complete",
            "reason": (
                "; ".join(problems)
                if problems
                else f"{written} re-minted row(s) now fold onto the row the provider lists"
            ),
            "written": written,
            "banked": banked,
            "failed_ids": failed[:20],
            "still_untagged": still_untagged[:20],
        }
        if written:
            result["undo"] = "python3 scripts/restore_7993_odds_api_remint_tags.py --apply"
        return result


def _json_default(value):
    return value.isoformat() if isinstance(value, datetime) else str(value)


def main() -> None:  # pragma: no cover — CLI entry for a detached one-off
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the tags")
    args = parser.parse_args()
    out = asyncio.run(run_odds_api_remint_sweep(apply=args.apply))
    print(json.dumps(out, indent=2, default=_json_default))


if __name__ == "__main__":  # pragma: no cover
    main()
