"""Generic Event Concept page route — slice 1 (#999).

`GET /api/event/{key}` renders any individual-competitor event (golf tournament,
and — future slices — tennis slam / UFC card / F1 GP / awards) through one
domain-parameterized aggregator. The key is `event:<domain>:<slug>`
(e.g. `event:golf:2026-masters`). Golf delegates to the existing golf aggregation
(parity bar); other domains add an adapter in `utils/event_concept.py`.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import get_db
from app.utils.event_concept import parse_event_key, get_adapter

router = APIRouter(tags=["event-concept"])


@router.get("/{key}")
async def get_event_concept(key: str, db: AsyncSession = Depends(get_db)):
    """Return the generic event envelope for `key` (event:<domain>:<slug>)."""
    domain, slug = parse_event_key(key)
    adapter = get_adapter(domain)
    if adapter is None:
        raise HTTPException(status_code=404, detail=f"No event adapter for domain '{domain}'")
    envelope = await adapter.build_event(slug, db)
    if envelope is None:
        raise HTTPException(status_code=404, detail=f"Event '{key}' not found")
    return envelope
