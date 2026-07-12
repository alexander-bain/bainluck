"""Generic competition HUB (landing) route — B1 / #1028.

`GET /api/hub/{competition}` returns a single, config-driven landing page for a
competition (MMA first — boxing/esports/awards drop in by adding a config entry
plus, if needed, an upcoming-events lister). It stitches together data that
already exists elsewhere so the hub is a thin composition layer, not a new
pipeline:

  * **upcoming**  — event-concept descriptors (e.g. UFC cards) via a per-domain
                    lister. These link to the generic event-concept page
                    (`/event/<key>`) built in #999 / L2-84.
  * **sections**  — futures / awards / props from the league-futures endpoint
                    (`app.routes.league_futures.get_league_futures`), which
                    already classifies markets by section.

Adding a new competition is config, not new page code: register a `HubConfig`
in `HUB_CONFIGS` and (only if the competition has grouped event pages) a lister
in `_UPCOMING_LISTERS`.
"""

import json as _json
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.routes.league_futures import get_league_futures
from app.services import get_db
from app.utils.event_boxing import classify_boxing_prop, list_boxing_card_concepts
from app.utils.event_concept import list_golf_tournament_concepts
from app.utils.event_tennis import list_tennis_tournament_concepts
from app.utils.event_ufc import classify_ufc_prop, list_ufc_card_concepts

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Competition Hub"])


# ---------------------------------------------------------------------------
# Config: one entry per competition. This is the whole "adapter" — everything
# else in this module is generic.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HubConfig:
    slug: str  # URL slug, e.g. "mma"
    label: str  # short nav label, e.g. "MMA"
    title: str  # hero title, e.g. "Mixed Martial Arts"
    emoji: str
    blurb: str
    # sport_key feeding the league-futures sections (futures/awards/props).
    sport_key: str
    # domain of the event-concept lister used for the "upcoming" rail. None means
    # this competition has no grouped event pages yet (sections-only hub).
    concept_domain: str | None = None
    # section keys (as produced by league_futures) to hide on this hub because
    # they are redundant with the upcoming rail.
    hide_sections: tuple[str, ...] = field(default_factory=tuple)
    # If set, split the coarse "matches" section into fights vs props: any
    # market the classifier tags (returns a non-None prop_type) moves to a
    # dedicated "props" section. league_futures lumps combat-sport game_props
    # in with fights, so this recovers a real props section on the hub.
    prop_classifier_domain: str | None = None


# Per-domain prop classifiers. Signature: (external_id, name) -> prop_type | None.
_PROP_CLASSIFIERS: dict[str, Callable[[str | None, str | None], str | None]] = {
    "ufc": classify_ufc_prop,
    "boxing": classify_boxing_prop,
}


HUB_CONFIGS: dict[str, HubConfig] = {
    "mma": HubConfig(
        slug="mma",
        label="MMA",
        title="Mixed Martial Arts",
        emoji="🥊",
        blurb=(
            "Upcoming UFC cards, fight props, and title odds — every market "
            "translated into plain probabilities."
        ),
        sport_key="mma_mixed_martial_arts",
        concept_domain="ufc",
        prop_classifier_domain="ufc",
    ),
    # B5 (L2-86): boxing drops in as ONE config entry — the combat engine
    # (event_combat/event_boxing) supplies the upcoming lister + prop classifier,
    # league_futures already routes boxing markets, and the frontend hub page is
    # generic. No new page code.
    "boxing": HubConfig(
        slug="boxing",
        label="Boxing",
        title="Boxing",
        emoji="🥊",
        blurb=(
            "Upcoming fight cards, method-and-round props, and title odds — every "
            "market translated into plain probabilities."
        ),
        sport_key="boxing_boxing",
        concept_domain="boxing",
        prop_classifier_domain="boxing",
    ),
    # B6 (L2-87): golf + tennis hubs drop in as config over the winner-field event
    # concepts. Each links to the per-event surface (/event/event:golf|tennis:<slug>);
    # the bespoke golf page stays the default for live scores (Alex's ruling). No
    # prop_classifier_domain — that split is combat-specific.
    "golf": HubConfig(
        slug="golf",
        label="Golf",
        title="Golf",
        emoji="⛳",
        blurb=(
            "Upcoming tournaments — majors and tour events — with winner fields, "
            "top-finish props, and matchups translated into plain probabilities."
        ),
        sport_key="golf_pga",
        concept_domain="golf",
    ),
    "tennis": HubConfig(
        slug="tennis",
        label="Tennis",
        title="Tennis",
        emoji="🎾",
        blurb=(
            "Upcoming slams and tour events with winner fields, matchups, and props "
            "— every market translated into plain probabilities."
        ),
        sport_key="tennis_atp",
        concept_domain="tennis",
    ),
}


# Per-domain upcoming-event listers. Each returns lightweight concept dicts
# ({key, name, domain, status, start_date, is_major, fight_count, ...}) that the
# frontend links to `/event/<key>`. Signature: (db, *, limit) -> list[dict].
_UPCOMING_LISTERS: dict[str, Callable[..., Awaitable[list[dict]]]] = {
    "ufc": list_ufc_card_concepts,
    "boxing": list_boxing_card_concepts,
    "golf": list_golf_tournament_concepts,
    "tennis": list_tennis_tournament_concepts,
}


def _serialize_concept(c: dict) -> dict:
    """Drop non-JSON-safe / internal fields from a concept descriptor."""
    return {
        "key": c.get("key"),
        "name": c.get("name"),
        "domain": c.get("domain"),
        "status": c.get("status"),
        "start_date": c.get("start_date"),
        "is_major": bool(c.get("is_major")),
        "fight_count": c.get("fight_count"),
    }


@router.get("/{competition}")
async def get_competition_hub(
    competition: str = Path(..., description="Competition slug (e.g. 'mma')"),
    db: AsyncSession = Depends(get_db),
):
    """Config-driven competition landing page: upcoming events + futures sections."""
    cfg = HUB_CONFIGS.get(competition.lower())
    if cfg is None:
        raise HTTPException(
            status_code=404, detail=f"No hub configured for '{competition}'"
        )

    # Whole-hub Redis cache (3 min primary + 24h stale fallback), mirroring the
    # league_futures caching pattern.
    _cache_key = f"bainluck:hub:{cfg.slug}"
    _stale_key = f"{_cache_key}:stale"
    _rc = None
    try:
        from app.tasks.redis_state import get_redis_client

        _rc = get_redis_client()
        cached = _rc.get(_cache_key)
        if cached:
            return _json.loads(cached.decode() if isinstance(cached, bytes) else cached)
    except Exception:
        _rc = None

    # Upcoming events (best-effort — a hub without a lister is sections-only).
    upcoming: list[dict] = []
    if cfg.concept_domain:
        lister = _UPCOMING_LISTERS.get(cfg.concept_domain)
        if lister is not None:
            try:
                concepts = await lister(db, limit=20)
                upcoming = [_serialize_concept(c) for c in concepts]
            except Exception:
                logger.exception("hub upcoming lister failed for %s", cfg.slug)
                upcoming = []

    # Futures / awards / props via the shared league-futures endpoint.
    sections: dict = {}
    try:
        league = await get_league_futures(sport_key=cfg.sport_key, db=db)
        sections = {
            k: v
            for k, v in (league.get("sections") or {}).items()
            if k not in cfg.hide_sections
        }
    except Exception:
        logger.exception("hub league_futures failed for %s", cfg.slug)
        sections = {}

    # Recover a real props section: league_futures lumps combat-sport game_props
    # into "matches" alongside fights. Pull the classifier-tagged ones out.
    classifier = (
        _PROP_CLASSIFIERS.get(cfg.prop_classifier_domain)
        if cfg.prop_classifier_domain
        else None
    )
    if classifier is not None and sections.get("matches"):
        fights: list = []
        moved_props: list = []
        for m in sections["matches"]:
            prop_type = classifier(m.get("external_id"), m.get("name"))
            if prop_type:
                m = {**m, "prop_type": prop_type, "section": "props"}
                moved_props.append(m)
            else:
                fights.append(m)
        if fights:
            sections["matches"] = fights
        else:
            sections.pop("matches", None)
        if moved_props:
            sections["props"] = (sections.get("props") or []) + moved_props

    # If everything came back empty, this is likely a transient failure — fall
    # back to the last good snapshot rather than serving a blank hub.
    if not upcoming and not sections and _rc is not None:
        try:
            stale = _rc.get(_stale_key)
            if stale:
                return _json.loads(
                    stale.decode() if isinstance(stale, bytes) else stale
                )
        except Exception:
            pass

    response = {
        "competition": cfg.slug,
        "label": cfg.label,
        "title": cfg.title,
        "emoji": cfg.emoji,
        "blurb": cfg.blurb,
        "sport_key": cfg.sport_key,
        "upcoming": upcoming,
        "sections": sections,
        "total_markets": sum(len(v) for v in sections.values()),
    }

    try:
        if _rc:
            payload = _json.dumps(response, default=str)
            _rc.setex(_cache_key, 180, payload)
            _rc.setex(_stale_key, 86400, payload)
    except Exception:
        pass

    return response
