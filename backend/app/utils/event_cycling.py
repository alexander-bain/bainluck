"""Cycling adapter for the Event Concept framework — The Tour (Queue #223 Item 3).

A Grand Tour (Tour de France / Giro / Vuelta) is a winner-field event, structurally
the F1-Grand-Prix shape: the General Classification (GC) winner market is the primary
field; the per-stage winner markets, the team classification, and any jersey props
fold in as children. Verified live via the census (2026-07-21): Kalshi carries
"Tour de France Winner" (id 55686927, 184 riders, Pogačar 94.5% favorite),
"Tour de France Team Winner", and per-stage "Tour de France: Stage N Winner"
markets, all ``llm_sport_category == "cycling"``. Polymarket carries no TdF markets.

Config-driven because market titles carry no year ("Tour de France Winner"), while
the concept slug does ("tour-de-france-2026"). Editions are disambiguated by matching
the slug's year against the market ``resolution_date`` year, so a 2027 slug never
resolves 2026 markets. The soccer coherence gate is ported so a broken/stale field
(the "Peru 47%" class) never crowns a nonsense GC leader.

Pure helpers are unit-tested; build_event is exercised via the route test.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.utils.winner_field_selection import prefer_graded_winner_field

# --- Name gates -------------------------------------------------------------
_WINNER_RE = re.compile(r"\b(winner|to win|champion)\b", re.IGNORECASE)
_STAGE_RE = re.compile(r"\bstage\s*\d+", re.IGNORECASE)
_TEAM_RE = re.compile(r"\bteam\b", re.IGNORECASE)
# Secondary classifications / jersey props (green=points, polka dot=KOM/mountains,
# white=young rider). Folded in as props, NOT the GC winner field.
_JERSEY_RE = re.compile(
    r"\b(green\s+jersey|points\s+classification|polka|mountains?\s+classification|"
    r"king\s+of\s+the\s+mountains?|white\s+jersey|young\s+rider|most\s+aggressive)\b",
    re.IGNORECASE,
)
# Any secondary-classification token that disqualifies a market from being the
# OVERALL GC winner field. Critical: without this, "Green Jersey Winner" / "Points
# Classification Winner" pass the winner gate and a fresher sprinter market can be
# crowned the GC leader (the live bug: Mads Pedersen shown as GC leader over Pogačar).
# Excludes the secondary jerseys/classifications but NOT "General Classification".
_NON_GC_RE = re.compile(
    r"\b(green\s+jersey|polka\s*dot|white\s+jersey|points|sprints?|intermediate|"
    r"mountains?|king\s+of\s+the\s+mountain|young\s+rider|combativity|"
    r"most\s+aggressive|super[\s-]?combativity)\b",
    re.IGNORECASE,
)

# L2-83 parity: raw price at/above which a SETTLED GC-winner outcome is the crowned
# winner during the is_winner grading-lag window. Display-only; never authoritative
# (gotcha #21). Mirrors the F1/tennis adapters.
_WON_PRICE_THRESHOLD = 0.97

# Coherence gate (ported from event_soccer — the "Peru 47%" fix).
_MIN_FIELD_SPREAD_RATIO = 0.10
_FIELD_SUM_MIN = 0.70
_FIELD_SUM_MAX = 1.60


@dataclass(frozen=True)
class CyclingRaceConfig:
    slug: str
    display: str
    name_re: re.Pattern
    aliases: tuple[str, ...] = field(default_factory=tuple)


# Editions with (or expecting) markets. Slug carries the year; name_re matches the
# year-less market title. Add Giro/Vuelta editions here as markets appear.
CYCLING_RACES: dict[str, CyclingRaceConfig] = {
    "tour-de-france-2026": CyclingRaceConfig(
        slug="tour-de-france-2026",
        display="Tour de France 2026",
        name_re=re.compile(r"tour\s+de\s+france", re.IGNORECASE),
        aliases=("tour-de-france", "tdf-2026", "tdf", "le-tour-2026"),
    ),
    "giro-2026": CyclingRaceConfig(
        slug="giro-2026",
        display="Giro d'Italia 2026",
        name_re=re.compile(r"giro\s*(d[’']?\s*italia)?", re.IGNORECASE),
        aliases=("giro-ditalia-2026", "giro"),
    ),
    "vuelta-2026": CyclingRaceConfig(
        slug="vuelta-2026",
        display="Vuelta a España 2026",
        name_re=re.compile(r"vuelta(\s+a\s+espa)?", re.IGNORECASE),
        aliases=("vuelta-a-espana-2026", "vuelta"),
    ),
}

_BY_SLUG: dict[str, CyclingRaceConfig] = {}
for _cfg in CYCLING_RACES.values():
    _BY_SLUG[_cfg.slug] = _cfg
    for _a in _cfg.aliases:
        _BY_SLUG.setdefault(_a, _cfg)


def parse_cycling_slug(slug: str) -> CyclingRaceConfig | None:
    """Resolve a slug (canonical or alias) to a race config, else None."""
    if not slug:
        return None
    s = slug.strip().lower()
    return _BY_SLUG.get(s)


def _slug_year(slug: str) -> int | None:
    m = re.search(r"(20\d{2})", slug or "")
    return int(m.group(1)) if m else None


def is_gc_winner_field_market(name: str | None, race_re: re.Pattern | None = None) -> bool:
    """True for the overall GC winner field — a winner market for the race that is
    NOT a per-stage winner, NOT the team classification, and NOT a secondary jersey /
    points / mountains / young-rider classification (those are props, and one of them
    being fresher must never be crowned the GC leader)."""
    n = name or ""
    if race_re is not None and not race_re.search(n):
        return False
    if not _WINNER_RE.search(n):
        return False
    if _STAGE_RE.search(n) or _TEAM_RE.search(n):
        return False
    if _JERSEY_RE.search(n) or _NON_GC_RE.search(n):
        return False
    return True


def is_stage_market(name: str | None) -> bool:
    return bool(_STAGE_RE.search(name or ""))


def is_team_classification_market(name: str | None) -> bool:
    n = name or ""
    return bool(_TEAM_RE.search(n)) and not _STAGE_RE.search(n)


def is_cycling_jersey_prop(name: str | None) -> bool:
    """A secondary classification / jersey market (green/points, polka-dot/mountains,
    white/young-rider, most-aggressive) — surfaced as a prop child, never the GC."""
    n = name or ""
    return bool(_JERSEY_RE.search(n) or _NON_GC_RE.search(n))


def _stage_number(name: str | None) -> int:
    m = re.search(r"stage\s*(\d+)", name or "", re.IGNORECASE)
    return int(m.group(1)) if m else 9999


# --- Coherence gate (ported from event_soccer) ------------------------------
def _real_outcomes(m) -> list:
    from app.utils.outcome_display import is_field_outcome, is_placeholder_outcome_name

    return [
        o
        for o in (m.outcomes or [])
        if o.name
        and not is_field_outcome(o.name)
        and not is_placeholder_outcome_name(o.name)
        and o.current_probability is not None
    ]


def _field_has_real_spread(real: list) -> bool:
    probs = [float(o.current_probability) for o in real if o.current_probability is not None]
    if len(probs) < 2:
        return False
    mx, mn = max(probs), min(probs)
    if mx <= 0:
        return False
    return (mx - mn) / mx >= _MIN_FIELD_SPREAD_RATIO


def _field_is_coherent(real: list) -> bool:
    total = sum(float(o.current_probability) for o in real if o.current_probability is not None)
    return _FIELD_SUM_MIN <= total <= _FIELD_SUM_MAX


def _select_gc_field(candidates: list):
    """Pick the GC winner market. Among candidates whose real field has genuine spread
    AND a coherent ~100% sum, prefer the LARGEST real field (the GC is the whole
    peloton — 184 riders — vs a handful in any stray secondary market), tie-broken by
    freshness. Falls back to the richest real field if none pass the coherence gate
    (Kalshi 184-way independent binaries can sum past the coherence band, gotcha #23 —
    the real GC must never be dropped to an empty page for that). A field with <2 real
    outcomes never qualifies.

    #1177 settled-concept invariant: a graded market (authoritative is_winner rows)
    among the coherent candidates OVERRIDES the freshest/widest ungraded pick — a
    settled Grand Tour's crown must come from the graded winner market, not whichever
    field polled last. Returns (market, real_outcomes)."""
    best = None
    best_key = None  # (n_real, freshness)
    best_real: list = []
    fallback = None
    fallback_real: list = []
    coherent: list = []
    for m in candidates:
        real = _real_outcomes(m)
        if len(real) < 2:
            continue
        # Track a richest-real fallback regardless of gate.
        if len(real) > len(fallback_real):
            fallback, fallback_real = m, real
        if not _field_has_real_spread(real) or not _field_is_coherent(real):
            continue
        freshness = max(
            (o.last_updated for o in real if getattr(o, "last_updated", None) is not None),
            default=datetime.min.replace(tzinfo=timezone.utc),
        )
        coherent.append((m, real, freshness))
        key = (len(real), freshness)
        if best is None or key > best_key:
            best, best_key, best_real = m, key, real
    if best is not None:
        return prefer_graded_winner_field(best, best_real, coherent)
    return fallback, fallback_real


def cycling_status(status: str | None, resolution_date, now) -> str:
    """upcoming / live / settled. A Grand Tour runs ~3 weeks, so the 'live' window is
    wide: within 25 days before resolution_date (Kalshi resolution is race-end/close;
    gotcha #14) counts as in progress."""
    if (status or "").lower() in ("resolved", "closed", "settled", "final"):
        return "settled"
    if resolution_date is not None:
        try:
            if resolution_date < now:
                return "settled"
            days = (resolution_date - now).total_seconds() / 86400
            if days <= 25:  # a 3-week grand tour is "in progress"
                return "live"
        except TypeError:
            pass
    return "upcoming"


def derive_cycling_concept(
    external_id: str | None, name: str | None, llm_sport_category: str | None
) -> dict | None:
    """Discovery-entry helper for search wiring: map a cycling GC-winner market to
    its concept. Returns {key, name, domain} or None."""
    if (llm_sport_category or "").lower() != "cycling":
        return None
    n = name or ""
    for cfg in CYCLING_RACES.values():
        if cfg.name_re.search(n) and is_gc_winner_field_market(n, cfg.name_re):
            return {"key": f"event:cycling:{cfg.slug}", "name": cfg.display, "domain": "cycling"}
    return None


async def list_cycling_concepts(
    db: AsyncSession,
    *,
    statuses: tuple[str, ...] = ("upcoming", "live"),
    limit: int = 10,
) -> list[dict]:
    """Enumerate cycling Grand-Tour concepts for the sports feed (the winner-field
    analogue of list_f1_gp_concepts). Returns lightweight dicts the feed scorer turns
    into concept cards linking to /event/{key}. Read-only, best-effort."""
    from app.models import FuturesMarket

    now = datetime.now(timezone.utc)
    rows = list(
        (
            await db.execute(
                select(
                    FuturesMarket.name,
                    FuturesMarket.status,
                    FuturesMarket.resolution_date,
                ).where(
                    FuturesMarket.llm_sport_category == "cycling",
                    FuturesMarket.status == "open",
                )
            )
        ).all()
    )

    per_race: dict[str, dict] = {}
    for name, status, res in rows:
        for cfg in CYCLING_RACES.values():
            if not cfg.name_re.search(name or ""):
                continue
            # Edition guard: only count this race edition's markets.
            yr = _slug_year(cfg.slug)
            if yr is not None and res is not None and res.year != yr:
                continue
            g = per_race.setdefault(
                cfg.slug, {"cfg": cfg, "markets": 0, "resolution": res, "status": status}
            )
            g["markets"] += 1
            if res is not None and (g["resolution"] is None or res < g["resolution"]):
                g["resolution"] = res
            break

    concepts: list[dict] = []
    for slug, g in per_race.items():
        cfg = g["cfg"]
        res = g["resolution"]
        status = cycling_status(g["status"], res, now)
        if status not in statuses:
            continue
        concepts.append(
            {
                "key": f"event:cycling:{slug}",
                "name": cfg.display,
                "domain": "cycling",
                "status": status,
                "start_date": res.isoformat() if res is not None else None,
                "is_major": True,  # Grand Tours are majors
                "entry_count": g["markets"],
                "latest_commence": res,
            }
        )
    concepts.sort(
        key=lambda x: (x["latest_commence"] or datetime.max.replace(tzinfo=timezone.utc))
    )
    return concepts[:limit]


class CyclingEventAdapter:
    domain = "cycling"

    async def build_event(self, slug: str, db: AsyncSession) -> dict | None:
        from app.models import FuturesMarket
        from app.utils.outcome_display import (
            is_field_outcome,
            is_placeholder_outcome_name,
            normalize_display_probs,
        )

        cfg = parse_cycling_slug(slug)
        if cfg is None:
            return None
        now = datetime.now(timezone.utc)
        slug_year = _slug_year(cfg.slug)

        q = (
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(
                FuturesMarket.llm_sport_category == "cycling",
                FuturesMarket.status == "open",
            )
        )
        all_markets = list((await db.execute(q)).scalars().unique().all())

        # Filter to this race + edition.
        markets = []
        for m in all_markets:
            if not cfg.name_re.search(m.name or ""):
                continue
            if (
                slug_year is not None
                and m.resolution_date is not None
                and m.resolution_date.year != slug_year
            ):
                continue
            markets.append(m)
        if not markets:
            return None

        gc_candidates = [m for m in markets if is_gc_winner_field_market(m.name, cfg.name_re)]
        # #1177: also consider RESOLVED/CLOSED GC winner markets. On settlement the
        # poly/kalshi GC market flips off status='open' while carrying the graded
        # is_winner rows, so an open-only scan sees only the ungraded field and the
        # settled crown would depend on which field polled last. The edition guard
        # (slug_year vs resolution_date, null-date allowed) keeps prior-edition GC
        # markets out. Children (stages/props) stay open-only below.
        graded_q = (
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(
                FuturesMarket.llm_sport_category == "cycling",
                FuturesMarket.status.in_(["resolved", "closed", "settled"]),
            )
        )
        seen_ids = {m.id for m in gc_candidates}
        for m in (await db.execute(graded_q)).scalars().unique().all():
            if m.id in seen_ids or not cfg.name_re.search(m.name or ""):
                continue
            if (
                slug_year is not None
                and m.resolution_date is not None
                and m.resolution_date.year != slug_year
            ):
                continue
            if is_gc_winner_field_market(m.name, cfg.name_re):
                gc_candidates.append(m)
        winner, real_outcomes = _select_gc_field(gc_candidates)
        if winner is None:
            return None

        event_status = cycling_status(winner.status, winner.resolution_date, now)

        competitors = []
        for o in real_outcomes:
            competitors.append(
                {
                    "name": o.name,
                    "probability": (
                        round(float(o.current_probability), 4)
                        if o.current_probability is not None
                        else None
                    ),
                    "won": bool(getattr(o, "is_winner", False)),
                }
            )
        # Crown the price-settled GC winner during the grading-lag window (read RAW
        # price before normalize dilutes a dominant leader). Display-only (gotcha #21).
        if event_status == "settled" and not any(c["won"] for c in competitors):
            top = max(competitors, key=lambda c: (c["probability"] or -1), default=None)
            if top is not None and (top["probability"] or 0) >= _WON_PRICE_THRESHOLD:
                top["won"] = True

        # Normalize ONLY a coherent (~mutually-exclusive) field. A Kalshi grand-tour
        # GC market lists 184 riders as INDEPENDENT YES/NO binaries whose YES prices
        # sum to ~2.8x (heavy overround, gotcha #23); normalizing that would dilute a
        # near-lock favorite (Pogačar 94.5% -> a false 34%). When the raw field sums
        # far past 100% the raw YES price IS the honest per-rider win probability —
        # keep it (Alex: "the blend is the product — one number per question").
        _raw_sum = sum(c["probability"] for c in competitors if c["probability"] is not None)
        if _raw_sum <= _FIELD_SUM_MAX:
            normalize_display_probs(competitors)
        competitors.sort(key=lambda c: (c["probability"] or -1), reverse=True)

        # Children = stages (in order), team classification, jersey props.
        def _child(m, prop_type):
            outs = sorted(
                (m.outcomes or []),
                key=lambda o: float(o.current_probability or 0),
                reverse=True,
            )
            outs = [
                o
                for o in outs
                if o.name
                and not is_field_outcome(o.name)
                and not is_placeholder_outcome_name(o.name)
            ]
            lead = outs[0] if outs else None
            lead_prob = (
                float(lead.current_probability)
                if lead and lead.current_probability is not None
                else None
            )
            return {
                "market_id": m.id,
                "market_name": m.name,
                "kind": "prop",
                "prop_type": prop_type,
                "source": m.source,  # data-only (audit); not rendered
                "probability": round(lead_prob, 4) if lead_prob is not None else None,
                "outcomes": [
                    {
                        "name": o.name,
                        "probability": (
                            round(float(o.current_probability), 4)
                            if o.current_probability is not None
                            else None
                        ),
                    }
                    for o in outs[:4]
                ],
            }

        stage_markets = sorted(
            [m for m in markets if m.id != winner.id and is_stage_market(m.name)],
            key=lambda m: _stage_number(m.name),
        )
        team_markets = [
            m
            for m in markets
            if m.id != winner.id and is_team_classification_market(m.name)
        ]
        jersey_markets = [
            m for m in markets if m.id != winner.id and is_cycling_jersey_prop(m.name)
        ]

        children, stage_ids, class_ids = [], [], []
        for m in stage_markets:
            children.append(_child(m, "stage"))
            stage_ids.append(m.id)
        for m in team_markets:
            children.append(_child(m, "team"))
            class_ids.append(m.id)
        for m in jersey_markets:
            children.append(_child(m, "jersey"))
            class_ids.append(m.id)

        sections = [
            {"type": "winner", "label": "General Classification", "market_ids": [winner.id]}
        ]
        if stage_ids:
            sections.append({"type": "prop", "label": "Stages", "market_ids": stage_ids})
        if class_ids:
            sections.append(
                {"type": "prop", "label": "Classifications & jerseys", "market_ids": class_ids}
            )

        race_iso = (
            winner.resolution_date.isoformat()
            if winner.resolution_date is not None
            else None
        )
        envelope = {
            "event": {
                "key": f"event:cycling:{cfg.slug}",
                "domain": "cycling",
                "name": cfg.display,
                "status": event_status,
                "start_date": race_iso,
                "end_date": race_iso,
                "venue": None,
                "location": None,
                "is_major": True,
            },
            "primary": {
                "kind": "winner_field",
                "label": "General Classification",
                "competitors": competitors,
                "evolution_market_id": winner.id,
            },
            "sections": sections,
            "children": children,
            "movers": [],
        }

        # Shared per-competitor history (one fetch); best-effort.
        try:
            from app.utils.event_concept import attach_competitor_history

            await attach_competitor_history(db, winner.id, competitors)
        except Exception:
            pass

        return envelope
