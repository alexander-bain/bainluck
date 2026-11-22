"""#12577 — Public read-only endpoints for live-hydrated paired-metric award & playoff sets."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import get_db
from app.services.paired_metric_register import (
    find_paired_set_id_for_market,
    load_live_paired_metric_sets,
)

router = APIRouter()

_OSCARS_PRESENTATION_ORDER: tuple[str, ...] = (
    "oscars-2027-best-picture",
    "oscars-2027-best-director",
    "oscars-2027-best-actor",
    "oscars-2027-best-actress",
    "oscars-2027-best-animated",
)


@router.get("/paired-metrics")
async def list_paired_metrics(
    ceremony: Optional[str] = Query(default=None, max_length=64),
    set_id: Optional[str] = Query(default=None, max_length=96),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return live DB-hydrated paired-metric sets (e.g. `?ceremony=oscars`)."""
    if set_id:
        loaded = await load_live_paired_metric_sets(db, set_ids=[set_id.strip()])
        sets_list = [loaded[set_id.strip()]] if set_id.strip() in loaded else []
        return {"sets": sets_list, "count": len(sets_list)}

    ceremony_clean = (ceremony or "").strip().lower()
    if ceremony_clean in {"oscars", "the-oscars", "oscars-2027", "academy-awards"}:
        loaded = await load_live_paired_metric_sets(db, prefix="oscars-")
        ordered = [loaded[sid] for sid in _OSCARS_PRESENTATION_ORDER if sid in loaded]
        for sid, val in loaded.items():
            if sid not in _OSCARS_PRESENTATION_ORDER:
                ordered.append(val)
        return {"sets": ordered, "count": len(ordered)}

    loaded = await load_live_paired_metric_sets(db)
    sets_list = list(loaded.values())
    return {"sets": sets_list, "count": len(sets_list)}


@router.get("/paired-metrics/by-market/{market_id}")
async def get_paired_metric_by_market(
    market_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the live-hydrated paired-metric set containing `market_id`, or `{"set": null}`."""
    matched_set_id = find_paired_set_id_for_market(market_id)
    if not matched_set_id:
        return {"set": None}
    loaded = await load_live_paired_metric_sets(db, set_ids=[matched_set_id])
    return {"set": loaded.get(matched_set_id)}
