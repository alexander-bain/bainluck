"""`GET /api/containers/{slug}` — one container, its members, by section.

#2927 Phase 4. The generic read path the hub flips to once container output
covers what the register renders (spec §5 M4). Until then it is behind
``CONTAINERS_READ_ENABLED`` and serves 404, so the route can ship, be exercised
and be measured without any user reaching a half-assembled hub.

THE HUB READS SECTIONS; IT DOES NOT CLASSIFY. Every member arrives with the
class that was computed once at assembly and stored on its edge (doctrine
§C.4). Three consumers re-deriving a class is how six sections become four in
one place and eight in another, so this route does no classification at all —
it groups by a column.

`unclassified` IS RETURNED, ALWAYS, AND LAST. A member we could not classify is
a member we would otherwise silently lose, which is the failure this program
exists to end. It is never filtered out here and never folded into another
section; it gets the last slot so a hub can render it as a trailing group or a
count without deciding to hide it.

WHY THE FLAG DEFAULTS TO OFF. A container that has not been assembled yet
returns an honest 404 rather than an empty hub. An empty section list rendered
as a page is indistinguishable, from outside, from a tournament with nothing
on — and #2215's empty-card lesson is that the fail-closed direction is the
only safe one.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import get_db
from app.utils.container_graph import CLASS_UNCLASSIFIED, EDGE_CLASSES

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Containers"])


def containers_read_enabled() -> bool:
    """Read at call time, not at import.

    A module-level constant would freeze the flag at dyno boot, so turning the
    hub on would need a restart — and a flag you have to restart to flip is a
    flag nobody flips during an incident.
    """
    return os.getenv("CONTAINERS_READ_ENABLED", "false").lower() == "true"


#: The order sections are rendered in. Explicit rather than alphabetical: the
#: hub's first screen should be the draw, not the props.
#:
#: `unclassified` is pinned LAST by construction below rather than by sitting
#: last in this tuple, so a future edit that reorders these cannot accidentally
#: promote it above a real section.
CLASS_ORDER = (
    "match_winner",
    "doubles",
    "advancement",
    "title",
    "prop",
    "side_question",
)


def order_classes(present: set) -> list:
    """Named sections in policy order, then anything new, then unclassified.

    The middle term matters: a class added to the vocabulary and not to
    ``CLASS_ORDER`` still renders, at the end but before `unclassified`. The
    alternative — dropping it — would make adding a class a silent way to hide
    a whole section, which is the same failure as dropping a member.
    """
    ordered = [c for c in CLASS_ORDER if c in present]
    extras = sorted(present - set(CLASS_ORDER) - {CLASS_UNCLASSIFIED})
    tail = [CLASS_UNCLASSIFIED] if CLASS_UNCLASSIFIED in present else []
    return ordered + extras + tail


@router.get("/{slug}")
async def get_container(
    slug: str = Path(..., min_length=1, max_length=200),
    include_children: bool = Query(
        True, description="Include members of nested containers (draws)."
    ),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """One container, its nested containers, and its members grouped by class."""
    if not containers_read_enabled():
        raise HTTPException(status_code=404, detail="Not found")

    row = (
        await db.execute(
            text(
                "SELECT id, kind, name, slug, category, status, "
                "       window_start, window_end, parent_container_id "
                "FROM containers WHERE slug = :slug"
            ),
            {"slug": slug},
        )
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Container not found")

    container_id = int(row[0])

    children = (
        await db.execute(
            text(
                "SELECT id, kind, name, slug, status FROM containers "
                "WHERE parent_container_id = :id ORDER BY name"
            ),
            {"id": container_id},
        )
    ).fetchall()

    # The parent's own members plus, optionally, its draws'. One query rather
    # than one per child: a five-draw tournament would otherwise cost six round
    # trips to answer one page.
    parent_ids = [container_id]
    if include_children:
        parent_ids.extend(int(c[0]) for c in children)

    members = (
        await db.execute(
            text(
                "SELECT e.class, e.child_type, e.child_id, e.parent_id, "
                "       e.source, e.confidence "
                "FROM event_edges e "
                "WHERE e.kind = 'contains' AND e.parent_type = 'container' "
                "  AND e.parent_id = ANY(:ids) "
                # `class` then `child_id` so the payload is deterministic —
                # a hub diffing two responses must not see phantom churn from
                # an unstable sort.
                "ORDER BY e.class, e.child_id"
            ),
            {"ids": parent_ids},
        )
    ).fetchall()

    by_class: dict = {}
    for member in members:
        member_class = member[0] or CLASS_UNCLASSIFIED
        by_class.setdefault(member_class, []).append(
            {
                "type": member[1],
                "id": int(member[2]),
                "container_id": int(member[3]),
                "source": member[4],
                "confidence": float(member[5]) if member[5] is not None else None,
            }
        )

    sections = [
        {
            "class": member_class,
            "count": len(by_class[member_class]),
            "members": by_class[member_class],
        }
        for member_class in order_classes(set(by_class))
    ]

    return {
        "container": {
            "id": container_id,
            "kind": row[1],
            "name": row[2],
            "slug": row[3],
            "category": row[4],
            "status": row[5],
            "window_start": row[6].isoformat() if row[6] else None,
            "window_end": row[7].isoformat() if row[7] else None,
            "parent_container_id": int(row[8]) if row[8] is not None else None,
        },
        "children": [
            {
                "id": int(c[0]),
                "kind": c[1],
                "name": c[2],
                "slug": c[3],
                "status": c[4],
            }
            for c in children
        ],
        "sections": sections,
        "member_count": sum(s["count"] for s in sections),
        # Stated in the payload rather than left for a reader to work out: an
        # empty container and a container nobody has assembled look identical
        # from outside, and gotcha #53 is the standing lesson that an empty
        # 200 is a response shape, not an absence.
        "assembled": bool(members),
        "known_classes": sorted(EDGE_CLASSES),
    }
