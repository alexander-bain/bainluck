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

from app.routes.league_futures import build_linked_matches, get_league_futures
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
from app.utils.entity_page_tiers import (
    AVAILABILITY_DEGRADED,
    AVAILABILITY_EMPTY,
    conforming_availability,
)
from app.utils.event_tennis import (
    classify_tennis_prop,
    list_tennis_tournament_concepts,
)
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
    # ── UX-P182 (#3447): a hub is a SPORT, a league key is a TOUR ──
    #
    # Sibling league scopes whose matches also belong on this hub. `/hub/tennis`
    # is the site's only tennis surface and was declared `tennis_atp`, so on US
    # Open finals weekend its rail carried 126 cards — 80 of them men's
    # Challenger matches — and not one women's match, while the page's own
    # starred MARQUEE card was the Women's US Open Winner. Sabalenka, Swiatek,
    # Gauff and Osaka rendered nowhere on it.
    #
    # This widens the MATCHES rail only, not `get_league_futures`: `/api/leagues/
    # tennis_atp` is a tour page and is right to be one tour. Every key must
    # share the primary's `llm_sport_category` — `_league_scope_filters` raises
    # otherwise, and `test_route_hub.py` asserts it over every config so a bad
    # pairing fails at test time rather than emptying a rail in production.
    extra_match_sport_keys: tuple[str, ...] = field(default_factory=tuple)
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
    # ── UX-P167 (#2167): the section vocabulary is CONFIG, not page code ──
    #
    # This module's own header says the config entry IS the whole adapter and
    # "everything else is generic". The section HEADINGS were the one thing that
    # never made it in: the page hard-coded MMA's words into a competition-blind
    # map written when MMA was the only hub, so `/hub/tennis` printed
    # "Fight Markets" over 103 tennis markets and `/hub/golf` printed "Fighter
    # Stats" over five golf markets.
    #
    # Only the sport-SPECIFIC words live here. The client keeps a neutral default
    # for every key ("Matches", "Props", "Player Stats"), so a hub that declares
    # nothing — and a payload cached before this shipped — reads plain and true
    # rather than reading like someone else's sport. Overriding is how a hub
    # earns fight vocabulary, not how it escapes it.
    section_labels: dict[str, str] = field(default_factory=dict)
    # Heading over the `upcoming` rail. "Cards" is combat vocabulary; a tennis
    # slam and a golf major are tournaments. Neutral default on the client.
    upcoming_label: str = "Upcoming"
    # ── UX-P210 (repairing CERT-525): the SAME heading with no phase claim in it ──
    #
    # `upcoming_label` asserts a phase about every card underneath it, and that
    # assertion is only sometimes true. Every rail lister here admits `live`
    # alongside `upcoming` by default, and the tennis one also admits `unknown`
    # (UX-P209/CERT-519: it has no trustworthy start signal, so it declines to
    # claim one). A live US Open sitting under "Upcoming Tournaments" is the
    # same false phase claim CERT-519 blocked on the per-card pill, moved one
    # level up — which is exactly what CERT-525 found.
    #
    # So the config declares BOTH words and the CLIENT chooses, because the
    # client is what renders the claim and only the client knows which cards
    # ended up on the rail. This field carries no phase vocabulary at all: it is
    # the noun the rail is a list of, and it is true whatever phase those cards
    # are in. `test_route_hub.py` asserts every config declares one and that no
    # phase word ever gets into it.
    upcoming_label_neutral: str = "Events"


# The combat hubs' shared vocabulary — MMA and boxing are the same sport shape
# (a card of two-sided fights + fight props), so they share one map rather than
# two copies that can drift.
_COMBAT_SECTION_LABELS = {
    "matches": "Fight Markets",
    "props": "Fight Props",
    "season_stats": "Fighter Stats",
}


# Per-domain prop classifiers. Signature: (external_id, name) -> prop_type | None.
_PROP_CLASSIFIERS: dict[str, Callable[[str | None, str | None], str | None]] = {
    "ufc": classify_ufc_prop,
    "boxing": classify_boxing_prop,
    # UX-P180 (#2167): tennis was missing, so every tennis `game_prop` — which
    # `_assign_section` routes to "matches" for all individual sports — was
    # stranded there with no way out. That is the half of the lying heading the
    # linked-matches source does not fix: 55 season-long ranking props sat under
    # "MATCHES · 56" on production.
    "tennis": classify_tennis_prop,
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
        section_labels=_COMBAT_SECTION_LABELS,
        upcoming_label="Upcoming Cards",
        upcoming_label_neutral="Cards",
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
        section_labels=_COMBAT_SECTION_LABELS,
        upcoming_label="Upcoming Cards",
        upcoming_label_neutral="Cards",
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
        # No section overrides — golf takes the neutral defaults. Its
        # `season_stats` section printed "Fighter Stats" over five golf markets
        # until UX-P167 (#2167).
        upcoming_label="Upcoming Tournaments",
        upcoming_label_neutral="Tournaments",
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
        # UX-P182 (#3447): the women's draw. Both tours are `llm_sport_category
        # = "tennis"`; only the league clause differs (KXWTA*/%WTA%/llm_league).
        extra_match_sport_keys=("tennis_wta",),
        concept_domain="tennis",
        # UX-P180 (#2167): tennis earns the props split. Registered for ufc and
        # boxing only until now, which is why tennis ranking props had no route
        # out of the "matches" section `_assign_section` puts every individual
        # sport's game_props into.
        prop_classifier_domain="tennis",
        # No section overrides — tennis takes the neutral defaults. Its `matches`
        # section printed "Fight Markets" over 103 tennis markets during US Open
        # week until UX-P167 (#2167).
        upcoming_label="Upcoming Tournaments",
        upcoming_label_neutral="Tournaments",
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
        # Neutral defaults. Esports printed "Fight Markets" over 98 markets until
        # UX-P167 (#2167). `upcoming_label` is declared even though this hub has
        # no rail today (no `concept_domain`), so wiring one later cannot
        # resurrect "Upcoming Cards" by omission.
        upcoming_label="Upcoming Tournaments",
        upcoming_label_neutral="Tournaments",
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
    """Drop far-future not-yet-started concepts more than ``horizon_days`` ahead.

    Only cards that have NOT been asserted to be under way are capped —
    live/in-progress/settled cards keep their near-now times. A concept with no
    parseable date is kept (fail-open: never hide a real card because its date
    field was missing). Prefers the ``latest_commence`` datetime, falling back to
    the serialized ``start_date`` ISO string.

    UX-P209: the test is "not asserted live", not "says upcoming". It was the
    latter, and a lister that stops making an affirmative claim would then have
    slipped every far-future card past the cap without one line of this function
    changing — the same absence-reads-as-a-value class CERT-519 blocked one layer
    down. ``unknown`` means we do not know the phase, which is not a reason to
    exempt a card dated eight months out. No tennis domain reaches here today
    (``_HORIZON_CAPPED_DOMAINS`` is combat-only), so this is the class being
    closed where it lives rather than a behaviour change; the guard drives the
    function directly.
    """
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=horizon_days)
    kept: list[dict] = []
    for c in concepts:
        if (c.get("status") or "") not in ("upcoming", "unknown"):
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
        # UX-P178: this is an ALLOWLIST, so a key the lister emits but this
        # function does not name is dropped silently while the route still
        # returns 200. The tennis rail has no start date to serve — its only
        # date is when the tournament ends — so `end_date` must be named here
        # or those cards lose their date entirely. `None` for the domains that
        # do know a real start.
        "end_date": c.get("end_date"),
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
    from app.utils.entity_page_tiers import is_unpriced_card, resolve_entity_tier

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

    # ── UX-P180 (#2167): the matches rail reads the markets that ARE linked ──
    #
    # `get_league_futures` filters `event_id IS NULL`, which is right for the
    # futures/awards sections it also feeds and exactly wrong for `matches`: a
    # real match is precisely a market with an `event_id`. Composed from that one
    # source, the rail could only ever show head-to-heads the matcher FAILED to
    # link, so `/hub/tennis` headed "MATCHES · 56" over zero US Open singles
    # while 204 linked ones were excluded.
    #
    # Additive and unconditional. It is not a tennis fix: MMA and boxing read
    # 42/42 and 12/12 match-shaped today only because combat markets are not
    # linked to events, so the same bug is latent on every hub the moment its
    # sport starts matching. A sport with no linked matches gets an empty list
    # and an unchanged page.
    #
    # Linked rows lead: they are the matches actually being played, ordered
    # live-first then soonest-first, and the unlinked remainder keeps its own
    # order behind them.
    try:
        linked_matches = await build_linked_matches(
            cfg.sport_key, db, also_sport_keys=cfg.extra_match_sport_keys
        )
    except Exception:
        logger.exception("hub linked matches failed for %s", cfg.slug)
        linked_matches = []
        # The page keeps its futures sections, but a matches rail missing the
        # actual matches is the defect this ship removes — declare it.
        losses.append(("hub_linked_matches_failed", LOSS_PARTIAL))
    if linked_matches:
        seen_ids = {m.get("id") for m in linked_matches}
        existing_matches = [
            m for m in (sections.get("matches") or []) if m.get("id") not in seen_ids
        ]
        sections["matches"] = linked_matches + existing_matches

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

    # ── UX-P061 (#1742, epic #1741): the entity envelope ──
    #
    # Spec §7: every count the page renders arrives IN the payload; clients never
    # derive `shown/total` by measuring arrays. Spec §2 / ruling 021: the TIER is a
    # typed backend field, because the moment web and SwiftUI each count arrays to
    # pick a layout, the same competition renders as a map on one and an answer on
    # the other and the parity bug is unfindable — both clients are "correct".
    #
    # `degraded` is taken from the typed losses this build already records, so a
    # hub that lost its market sections cannot present as fresh (ruling 025 clause
    # 4). The counts come from the shared resolver — never reimplemented here, or
    # the histogram would predict a tier the page does not render.
    now = datetime.now(timezone.utc)
    tiering = resolve_entity_tier(
        sections,
        now=now,
        entity_is_real=True,  # a hub slug exists in HUB_CONFIGS or the route 404s
        record_n=0,  # the record strip lands on competitions at step 2 (#1744)
        next_event_count=len(upcoming),
        season_known=False,
    )

    # ── UX-P181 (#2167): the hub stops RENDERING what it already counts as dropped ──
    #
    # The histogram above has always classified a market with no priced outcome as
    # `unpriced`, and `section_counts.dropped` has always published that number —
    # but nothing ever removed the row, so the payload asserted an impossibility.
    # Measured on production 2026-09-05, after the linked-match rail shipped:
    #
    #     /api/hub/tennis  matches  {"total": 126, "shown": 126, "dropped": 47}
    #
    # and on the page those 47 were cards holding a match name and NOTHING else —
    # no players, no probability — ten of them consecutively. It is not a tennis
    # artefact: boxing renders 10 blank cards of 12, MMA 28 of 42.
    #
    # Fail closed, which is the contract this product already shipped everywhere
    # else: L2-215 (#1486) made Discover and Sports drop an envelope with no
    # renderable content at both web boundaries and in the native view model. The
    # hub is the surface that never got the guard, not a place where a different
    # rule applies.
    #
    # The TIER is deliberately resolved on the UNFILTERED sections above. It is a
    # function of `answers`, which never counted these rows, so a hub cannot change
    # shape because we stopped drawing blanks — and the counts below keep reporting
    # the whole pool, so the exclusion stays visible (ruling 025 clause 3: a swallow
    # that counts is detection).
    rendered: dict = {}
    for name, rows in sections.items():
        kept = [m for m in (rows or []) if not is_unpriced_card(m, now=now)]
        if kept:
            rendered[name] = kept
    sections = rendered

    response = {
        "competition": cfg.slug,
        "label": cfg.label,
        "title": cfg.title,
        "emoji": cfg.emoji,
        "blurb": cfg.blurb,
        "sport_key": cfg.sport_key,
        # UX-P167 (#2167): the heading vocabulary travels WITH the payload, the
        # same way `label`/`title`/`blurb` already do. A hub that overrides
        # nothing serves `{}` — an explicit "no sport-specific words here",
        # which the client renders as its neutral defaults.
        "section_labels": dict(cfg.section_labels),
        "upcoming_label": cfg.upcoming_label,
        "upcoming_label_neutral": cfg.upcoming_label_neutral,
        "upcoming": upcoming,
        "sections": sections,
        "total_markets": sum(len(v) for v in sections.values()),
        "tier": tiering["tier"],
        "pool_counts": tiering["pool_counts"],
        # Per-section total/shown/dropped, and the three now RECONCILE: `shown` is
        # measured on the rows actually served, not assumed equal to `total`. It
        # was assumed, and the assumption was false the moment a section carried a
        # dropped row — the field said "we cap nothing here" while `dropped` said
        # 47 (spec §4: uncounted caps are concealment; an uncounted *non*-cap is
        # the same lie in the other direction).
        "section_counts": {
            name: {
                "total": s["total"],
                "shown": len(sections.get(name) or []),
                "dropped": s["unpriced"],
                "answers": s["answers"],
            }
            for name, s in tiering["per_section"].items()
        },
        # The build's own view of whether it lost anything, so the route can stamp
        # a conforming availability without re-deriving it from the cache slot.
        "_build_degraded": any(sev == LOSS_DEGRADED for _, sev in losses),
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


def _with_entity_envelope(payload: dict, legacy_availability: str) -> dict:
    """Stamp ruling 025's conforming `availability` beside the legacy field.

    UX-P061 (#1742). Register E10 / doctrine C17: `event_concept_cache` declares
    availability as `live | stale_ok | unavailable`, a THIRD vocabulary for a fact
    rulings 025 already named `fresh | stale | degraded | empty`. The entity
    envelope adopts the ruled vocabulary from day one (spec §7).

    ADDITIVE, deliberately. The legacy field stays exactly where it is, because
    other consumers read it and this queue is not a migration of the cache tier.
    What changes is that an entity CLIENT now has a conforming field to read, and
    the two can be reconciled when the cache tier is migrated.

    The degraded case is the one that matters: a build that lost its market
    sections is served promptly and therefore looks `live`, while being a page
    missing its substance. Ruling 025 clause 4 is exactly that — a plausible
    substitute served without declaration.
    """
    stamped = with_availability(payload, legacy_availability)
    degraded = bool(stamped.get("_build_degraded"))
    if not stamped.get("sections") and not stamped.get("upcoming"):
        # Nothing to show and nothing lost = genuinely empty, not degraded.
        conforming = AVAILABILITY_EMPTY if not degraded else AVAILABILITY_DEGRADED
    else:
        conforming = conforming_availability(legacy_availability, degraded=degraded)
    out = {**stamped, "availability": conforming}
    out.pop("_build_degraded", None)
    return out


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
        return _with_entity_envelope(primary, AVAILABILITY_LIVE)

    # 2. THE FIX (#1651): a MISS serves the mirror and schedules one rebuild,
    #    instead of walking past a healthy snapshot into a full rebuild. There is
    #    deliberately no negative-cache read here — unlike a concept key, a hub
    #    slug either exists in HUB_CONFIGS or 404s above, so "known absent" is
    #    already answered without touching Redis.
    stale = read_slot(rc, keys.stale)
    if stale is not None:
        _schedule_refresh(rc, keys, cfg.slug)
        return _with_entity_envelope(stale, AVAILABILITY_STALE_OK)

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
            return _with_entity_envelope(rescued, AVAILABILITY_STALE_OK)
        raise

    # 4. The empty-build rescue, kept: it is correct, it was just insufficient on
    #    its own. `build_hub` never raises, so a total upstream failure arrives
    #    here as an empty page rather than as the exception handled above.
    if is_empty_hub(payload):
        rescued = read_slot(rc, keys.stale)
        if rescued is not None:
            logger.warning("hub built empty for %s — serving stale", cfg.slug)
            return _with_entity_envelope(rescued, AVAILABILITY_STALE_OK)

    return _with_entity_envelope(payload, AVAILABILITY_LIVE)
