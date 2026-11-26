#!/usr/bin/env python3
"""Promote Keep-graded scout sets from the blind morning deck into public PR files (#13102, 385: A).

Reads ``ranking_judgments`` (``surface="grade_scout_morning_deck"``) and joins
against the Redis sealed key (``bainluck:fun_scout:deck_key:<date>``). Never
runs automatically on grade submission; requires explicit invocation to write
``backend/data/containers/<slug>.json`` for standard PR review & merge.

Default is ``--dry-run``. Pass ``--write`` to emit container files.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import desc, select  # noqa: E402

from app.models.models import RankingJudgment  # noqa: E402
from app.services.database import async_session_maker  # noqa: E402
from app.tasks.discover_fun_scout import retire_scout_set_durable  # noqa: E402
from app.utils.roundup_containers import CONTAINERS_DATA_DIR, validate_roundup_definition  # noqa: E402
from app.utils.scout_morning_deck import (  # noqa: E402
    DATE_PARAM_RE,
    SCOUT_DECK_KEY_REDIS_PREFIX,
    SCOUT_DECK_SURFACE,
)

_SAFE_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,95}$")


def latest_grades_by_item(
    judgments: Sequence[Mapping[str, Any]],
    *,
    deck_date: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Return newest judgment per ``item_id`` (optionally scoped to ``deck_date``)."""
    latest: dict[str, dict[str, Any]] = {}
    for row in judgments:
        meta = row.get("label_metadata")
        meta_dict = meta if isinstance(meta, Mapping) else {}
        row_date = str(meta_dict.get("deck_date") or "").strip()
        if deck_date and row_date != deck_date:
            continue
        item_id = str(meta_dict.get("item_id") or row.get("market_name") or "").strip()
        if not item_id or item_id in latest:
            continue
        label = str(meta_dict.get("grade") or row.get("label") or "").strip()
        if label not in ("Keep", "Fix", "Drop"):
            continue
        latest[item_id] = {
            "item_id": item_id,
            "grade": label,
            "note": str(meta_dict.get("note") or row.get("notes") or "").strip(),
            "deck_date": row_date,
        }
    return latest


def plan_scout_promotions(
    judgments: Sequence[Mapping[str, Any]],
    sealed_key: Mapping[str, Any],
    *,
    deck_date: str | None = None,
) -> dict[str, Any]:
    """Classify Keep/Fix/Drop actions, ignoring public decoys and validating Keep definitions."""
    entries = sealed_key.get("entries") if isinstance(sealed_key, Mapping) else None
    if not isinstance(entries, Mapping):
        entries = {}
    target_date = deck_date or (
        str(sealed_key.get("deck_date") or "").strip() if isinstance(sealed_key, Mapping) else ""
    )
    grades = latest_grades_by_item(judgments, deck_date=target_date or None)

    to_promote: list[dict[str, Any]] = []
    to_retire: list[str] = []
    fix_notes: list[dict[str, str]] = []
    ignored_decoys: list[str] = []

    for item_id, info in sorted(grades.items()):
        key_entry = entries.get(item_id)
        if not isinstance(key_entry, Mapping):
            continue
        origin = str(key_entry.get("origin") or "")
        slug = str(key_entry.get("slug") or "").strip().lower()
        if origin != "scout":
            ignored_decoys.append(item_id)
            continue
        if not _SAFE_SLUG_RE.match(slug):
            continue

        grade = info["grade"]
        if grade == "Keep":
            raw_def = dict(key_entry.get("rule_definition") or {})
            raw_def["slug"] = slug
            raw_def["stage"] = "public"
            scout_meta = dict(raw_def.get("scout") or {})
            scout_meta["requires_fable_look"] = False
            scout_meta["promoted_from_deck_date"] = target_date
            graded_member_ids = [
                int(mid)
                for mid in (key_entry.get("member_ids") or ())
                if isinstance(mid, int) and mid > 0
            ]
            if not graded_member_ids:
                graded_member_ids = [
                    int(mid)
                    for mid in (scout_meta.get("graded_member_ids") or ())
                    if isinstance(mid, int) and mid > 0
                ]
            if graded_member_ids:
                scout_meta["graded_member_ids"] = graded_member_ids
            raw_def["scout"] = scout_meta
            validated = validate_roundup_definition(raw_def)
            to_promote.append({"item_id": item_id, "slug": slug, "definition": validated})
        elif grade == "Drop":
            to_retire.append(slug)
        elif grade == "Fix":
            fix_notes.append({"item_id": item_id, "slug": slug, "note": info["note"]})

    return {
        "deck_date": target_date,
        "promote": to_promote,
        "retire": to_retire,
        "fix": fix_notes,
        "ignored_decoys": ignored_decoys,
    }


def apply_scout_promotions(
    plan: Mapping[str, Any],
    *,
    containers_dir: Path = CONTAINERS_DATA_DIR,
    write: bool = False,
    retire_drops: bool = False,
) -> dict[str, Any]:
    """Write Keep-promoted public container definitions to disk (only when ``write=True``)."""
    written_files: list[str] = []
    retired_slugs: list[str] = []
    base = Path(containers_dir).resolve()

    if write:
        base.mkdir(parents=True, exist_ok=True)
        for item in plan.get("promote") or ():
            slug = str(item["slug"])
            if not _SAFE_SLUG_RE.match(slug):
                raise ValueError(f"Unsafe slug rejected: {slug!r}")
            dest = (base / f"{slug}.json").resolve()
            if dest.parent != base:
                raise ValueError(f"Path escape rejected: {dest}")
            dest.write_text(
                json.dumps(item["definition"], indent=2) + "\n",
                encoding="utf-8",
            )
            written_files.append(str(dest))

    if retire_drops:
        for slug in plan.get("retire") or ():
            ok, _err = retire_scout_set_durable(str(slug))
            if ok:
                retired_slugs.append(str(slug))

    return {
        "dry_run": not write,
        "written_files": written_files,
        "retired_slugs": retired_slugs,
        "promote_count": len(plan.get("promote") or ()),
        "retire_count": len(plan.get("retire") or ()),
        "fix_count": len(plan.get("fix") or ()),
        "ignored_decoy_count": len(plan.get("ignored_decoys") or ()),
    }


async def _load_judgments_from_db() -> list[dict[str, Any]]:
    async with async_session_maker() as db:
        rows = (
            await db.execute(
                select(RankingJudgment)
                .where(RankingJudgment.surface == SCOUT_DECK_SURFACE)
                .order_by(desc(RankingJudgment.created_at), desc(RankingJudgment.id))
            )
        ).scalars().all()
        return [
            {
                "market_name": r.market_name,
                "label": r.label,
                "notes": r.notes,
                "label_metadata": r.label_metadata,
            }
            for r in rows
        ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Promote Keep-graded scout sets to public containers (#13102).")
    parser.add_argument("--date", required=True, help="Morning deck YYYY-MM-DD")
    parser.add_argument("--write", action="store_true", help="Write public container JSON files (default is dry-run)")
    parser.add_argument("--retire-drops", action="store_true", help="Mark Drop slugs in Redis retired set")
    parser.add_argument("--containers-dir", type=Path, default=CONTAINERS_DATA_DIR)
    args = parser.parse_args(argv)

    if not DATE_PARAM_RE.match(args.date):
        raise SystemExit(f"Invalid --date {args.date!r}; expected YYYY-MM-DD")

    from app.tasks.redis_state import get_redis_client

    rc = get_redis_client(fast_fail=True)
    raw_key = rc.get(f"{SCOUT_DECK_KEY_REDIS_PREFIX}:{args.date}")
    if not raw_key:
        raise SystemExit(f"No sealed deck key found in Redis for {args.date}")
    sealed_key = json.loads(raw_key.decode("utf-8") if isinstance(raw_key, (bytes, bytearray)) else str(raw_key))

    judgments = asyncio.run(_load_judgments_from_db())
    plan = plan_scout_promotions(judgments, sealed_key, deck_date=args.date)
    summary = apply_scout_promotions(
        plan,
        containers_dir=args.containers_dir,
        write=bool(args.write),
        retire_drops=bool(args.retire_drops),
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
