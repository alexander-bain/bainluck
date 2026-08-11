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

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.routes.league_futures import get_league_futures
from app.services import get_db
from app.utils.event_boxing import classify_boxing_prop, list_boxing_card_concepts
from app.utils.event_concept import list_golf_tournament_concepts
from app.utils.event_concept_cache import (
    AVAILABILITY_LIVE,
    AVAILABILITY_STALE_OK,
    ConceptCacheKeys,
    acquire_refresh_lock,
    cache_keys,
    get_client,
    read_slot,
    release_refresh_lock,
    stamp_envelope,
    with_availability,
    write_payload,
)
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
    # L2-92 (B4): esports drops in as a sections-ONLY hub. The data is messy —
    # thousands of per-map "Team A vs Team B" matchup rows across LoL/CS2/Valorant/
    # Dota with no clean per-tournament grouping yet — so this hub surfaces the
    # genuine tournament outrights only (MSI/LCK/LPL/Worlds/EWC/The International
    # winners). No concept_domain: per-tournament event-concept pages wait for
    # engine-owned grouping (the person/entity work). league_futures does the
    # category-wide, futures-only filtering (see _CATEGORY_WIDE_FUTURES_ONLY).
    "esports": HubConfig(
        slug="esports",
        label="Esports",
        title="Esports",
        emoji="🎮",
        blurb=(
            "Tournament and season titles across League of Legends, Counter-Strike, "
            "Valorant, and Dota — every market translated into plain probabilities."
        ),
        sport_key="esports",
        concept_domain=None,
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


# Upcoming-rail horizon (L2-101 Item 2). Combat cards get a far-future cap: a
# numbered main event ~1yr out (e.g. a 2027 UFC card) sorts marquee-first in the
# combat lister and floats to the top of the rail, padding it and pushing soon
# cards off. Cap the horizon at the route level (disjoint from the combat parse
# engine) so soonest-first ordering is preserved but noise is dropped. Golf/tennis
# are intentionally exempt — their majors are legitimately scheduled many months
# ahead, so hiding them would be a regression.
_UPCOMING_LIMIT = 20
_UPCOMING_FETCH_LIMIT = 60  # over-fetch so the horizon cap doesn't shrink the rail
_HORIZON_CAPPED_DOMAINS = {"ufc", "boxing"}
_UPCOMING_HORIZON_DAYS = 90


def _within_horizon(concepts: list[dict], horizon_days: int) -> list[dict]:
    """Drop far-future ``upcoming`` concepts more than ``horizon_days`` ahead.

    Only ``status == "upcoming"`` cards are capped — live/in-progress/settled cards
    keep their near-now times. A concept with no parseable date is kept (fail-open:
    never hide a real card because its date field was missing). Prefers the
    ``latest_commence`` datetime, falling back to the serialized ``start_date`` ISO
    string.
    """
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=horizon_days)
    kept: list[dict] = []
    for c in concepts:
        if (c.get("status") or "") != "upcoming":
            kept.append(c)
            continue
        raw = c.get("latest_commence") or c.get("start_date")
        dt: "datetime | None" = None
        if isinstance(raw, datetime):
            dt = raw
        elif isinstance(raw, str):
            try:
                dt = datetime.fromisoformat(raw)
            except ValueError:
                dt = None
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt > cutoff:
                continue  # beyond the horizon — drop
        kept.append(c)
    return kept


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


# ---------------------------------------------------------------------------
# Cache tier (#1651) — policy lives in `utils/event_concept_cache.py`
# ---------------------------------------------------------------------------
#
# This tier is the SECOND customer of that module (ruling 005, extract-on-touch;
# contract in `docs/contracts/cache-envelope.md`). It had the same 3-min primary +
# 24h mirror shape as `routes/event.py` and the same defect: **the mirror was read
# only when the build came back EMPTY**, so it rescued a failed build and did
# nothing at all for a cold one. Every 180 seconds the first reader of each hub
# paid a full rebuild with a perfectly good snapshot one GET away — measured in
# production on 2026-08-10, golf 2.745s cold vs 0.285s warm (9.6x), tennis 1.622s
# vs 0.353s, esports 1.101s vs 0.451s.
#
# The keys are unchanged (`bainluck:hub:<slug>`), so this is an adoption of the
# existing policy and not a migration: `cache_keys` takes the prefix.

HUB_CACHE_PREFIX = "bainluck:hub:"

#: How fresh a *live* hit is. Unchanged at 180s — what changed is that expiry no
#: longer costs the reader a rebuild, so this stopped being a latency knob.
HUB_PRIMARY_TTL = 180


def hub_cache_keys(slug: str) -> ConceptCacheKeys:
    """The four Redis keys one hub owns. Shared by the route and the refresh task
    so the two can never disagree about where the mirror lives."""
    return cache_keys(slug, prefix=HUB_CACHE_PREFIX)


def _schedule_refresh(rc, keys: ConceptCacheKeys, slug: str) -> None:
    """Kick exactly one background rebuild for `slug` and return immediately.

    Single-flight: a burst of readers arriving behind one TTL expiry produces one
    rebuild, not one per reader. The owner token travels WITH the dispatch because
    this request acquires the lock and the worker releases it (#1678 finding 1) —
    a producer that cannot name the token does not get to release.

    Best-effort throughout: the caller has already decided to serve the mirror, and
    nothing here may turn a served page into an error. If the dispatch itself
    fails the lock is released, so a dead broker costs the next reader a retry
    rather than wedging the key for REFRESH_LOCK_TTL.
    """
    token = acquire_refresh_lock(rc, keys)
    if not token:
        return
    try:
        from app.tasks import celery_app

        celery_app.send_task(
            "app.tasks.refresh_hub", args=[slug, token], queue="background"
        )
    except Exception:
        logger.warning("hub: refresh dispatch failed for %s", slug, exc_info=True)
        release_refresh_lock(rc, keys, token)


async def build_hub(cfg: HubConfig, db: AsyncSession) -> dict:
    """Build one hub payload from the database. Never raises.

    Both swallow points declare a typed loss where the failure happens, which is
    the only place that knows what was lost: the market sections are the page's
    substance, so losing them is `degraded`; the upcoming rail is real content
    alongside a surviving page, so losing it is `partial`.
    """
    from app.utils.event_concept_cache import LOSS_DEGRADED, LOSS_PARTIAL, note_build_loss

    losses: list[tuple[str, str]] = []

    # Upcoming events (best-effort — a hub without a lister is sections-only).
    upcoming: list[dict] = []
    if cfg.concept_domain:
        lister = _UPCOMING_LISTERS.get(cfg.concept_domain)
        if lister is not None:
            try:
                if cfg.concept_domain in _HORIZON_CAPPED_DOMAINS:
                    # Over-fetch, drop far-future upcoming cards, then trim — so
                    # dropping a year-out marquee card doesn't shrink the rail.
                    concepts = await lister(db, limit=_UPCOMING_FETCH_LIMIT)
                    concepts = _within_horizon(concepts, _UPCOMING_HORIZON_DAYS)
                    concepts = concepts[:_UPCOMING_LIMIT]
                else:
                    concepts = await lister(db, limit=_UPCOMING_LIMIT)
                upcoming = [_serialize_concept(c) for c in concepts]
            except Exception:
                logger.exception("hub upcoming lister failed for %s", cfg.slug)
                upcoming = []
                losses.append(("hub_upcoming_lister_failed", LOSS_PARTIAL))

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
        losses.append(("hub_league_futures_failed", LOSS_DEGRADED))

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
    for reason, severity in losses:
        note_build_loss(response, reason, severity)
    return response


def is_empty_hub(payload: dict) -> bool:
    """A hub with neither an upcoming rail nor any section is not a page."""
    return not payload.get("upcoming") and not payload.get("sections")


async def build_and_cache_hub(cfg: HubConfig, db: AsyncSession, rc=None) -> dict:
    """Build one hub, stamp the envelope, write both slots, return the payload.

    One implementation for the route's cold path and the background refresh, so
    the two cannot drift in what they store.

    **An empty build never overwrites a good mirror.** This is the ordering the
    pre-#1651 route had for free by checking emptiness before its `setex`, and it
    is easy to lose when the write moves into a shared helper: writing first would
    clobber the 24h snapshot with the blank page and then "rescue" by reading back
    the blank we just stored. The rescue must have something to rescue.
    """
    from app.utils.event_concept_cache import take_build_quality

    keys = hub_cache_keys(cfg.slug)
    built = await build_hub(cfg, db)
    quality, reasons = take_build_quality(built)
    payload = stamp_envelope(
        built,
        created_at=datetime.now(timezone.utc),
        # An explicit allowed unknown per the contract. A hub is a composition of
        # other tiers' data and has no single lifecycle event of its own; claiming
        # a watermark we cannot compute is the fabrication #1678 finding 3 is about.
        lifecycle_watermark=None,
        quality=quality,
        quality_reasons=reasons,
    )
    if is_empty_hub(payload) and read_slot(rc, keys.stale) is not None:
        return payload
    write_payload(rc, keys, payload, primary_ttl=HUB_PRIMARY_TTL)
    return payload


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

    keys = hub_cache_keys(cfg.slug)
    rc = get_client()

    # 1. A live hit inside the primary TTL.
    primary = read_slot(rc, keys.primary)
    if primary is not None:
        return with_availability(primary, AVAILABILITY_LIVE)

    # 2. THE FIX (#1651): a MISS serves the mirror and schedules one rebuild,
    #    instead of walking past a healthy snapshot into a full rebuild. There is
    #    deliberately no negative-cache read here — unlike a concept key, a hub
    #    slug either exists in HUB_CONFIGS or 404s above, so "known absent" is
    #    already answered without touching Redis.
    stale = read_slot(rc, keys.stale)
    if stale is not None:
        _schedule_refresh(rc, keys, cfg.slug)
        return with_availability(stale, AVAILABILITY_STALE_OK)

    # 3. Nothing usable cached — build inline. A cold miss must still SERVE, so
    #    this path stays synchronous and is never gated on the refresh task.
    try:
        payload = await build_and_cache_hub(cfg, db, rc)
    except Exception:
        # Re-read the mirror rather than trusting step 2: a concurrent refresh may
        # have landed one while we were building.
        rescued = read_slot(rc, keys.stale)
        if rescued is not None:
            logger.warning("hub build failed for %s — serving stale", cfg.slug)
            return with_availability(rescued, AVAILABILITY_STALE_OK)
        raise

    # 4. The empty-build rescue, kept: it is correct, it was just insufficient on
    #    its own. `build_hub` never raises, so a total upstream failure arrives
    #    here as an empty page rather than as the exception handled above.
    if is_empty_hub(payload):
        rescued = read_slot(rc, keys.stale)
        if rescued is not None:
            logger.warning("hub built empty for %s — serving stale", cfg.slug)
            return with_availability(rescued, AVAILABILITY_STALE_OK)

    return with_availability(payload, AVAILABILITY_LIVE)
